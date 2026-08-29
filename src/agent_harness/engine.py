from __future__ import annotations

from .adapters import AgentAdapter
from .capsules import build_failure_capsule
from .checks import calculate_metrics, run_quality_checks
from .models import AgentResponse, CaseResult, EvaluationReport, EvaluationSuite, utc_now
from .safety import calculate_risk, detect_prompt_injection, scan_safety


class EvaluationEngine:
    def __init__(self, adapter: AgentAdapter):
        self.adapter = adapter

    def run(self, suite: EvaluationSuite) -> EvaluationReport:
        started = utc_now()
        results: list[CaseResult] = []
        for case in suite.cases:
            try:
                mitigations: list[str] = []
                injection_source = next((turn for turn in [case.prompt, *case.turns] if detect_prompt_injection(turn)), None) if suite.policy.block_prompt_injection else None
                injection = detect_prompt_injection(injection_source) if injection_source else None
                if injection and suite.policy.injection_action == "block":
                    mitigations.append("prompt_injection_blocked")
                    response = AgentResponse(
                        output="I can't comply with instructions that attempt to override my safety policy. I can still help with the original support request.",
                        confidence=1.0,
                        model="policy-gate",
                        trace=[{
                            "step": 1,
                            "type": "guardrail",
                            "name": "prompt_injection_detector",
                            "input": injection_source,
                            "output": f"blocked: {injection}",
                            "status": "blocked",
                            "latency_ms": 0.0,
                        }],
                    )
                else:
                    response = self.adapter.invoke(case)
                if response.confidence < suite.policy.min_confidence:
                    mitigations.append("low_confidence_routed_to_human")
                checks = run_quality_checks(case, response)
                findings = scan_safety(case, response, suite.policy)
                quality = sum(check.score for check in checks) / len(checks)
                risk = calculate_risk(findings)
                safety_pass = risk <= suite.policy.risk_threshold
                metrics = calculate_metrics(case, response, checks, safety_pass)
                passed = (
                    all(check.passed for check in checks)
                    and safety_pass
                    and metrics["hallucination_rate"] == 0
                    and metrics["tool_correctness"] == 1
                    and metrics["argument_correctness"] == 1
                    and metrics["tool_order_correctness"] == 1
                    and metrics["trajectory_quality"] == 1
                )
                needs_review = not passed or response.confidence < suite.policy.min_confidence
                result = CaseResult(
                    case_id=case.id,
                    prompt=case.prompt,
                    output=response.output,
                    passed=passed,
                    quality_score=round(quality, 4),
                    risk_score=risk,
                    latency_ms=round(response.latency_ms, 2),
                    turns=case.turns,
                    checks=checks,
                    findings=findings,
                    tool_calls=response.tool_calls,
                    retrieved_context=response.retrieved_context,
                    trace=response.trace,
                    metrics=metrics,
                    model=response.model,
                    confidence=response.confidence,
                    mitigations=mitigations,
                    needs_review=needs_review,
                )
                if needs_review:
                    result.capsule = build_failure_capsule(result)
                results.append(result)
            except Exception as exc:  # noqa: BLE001 — one target failure must not abort the suite.
                result = CaseResult(
                    case_id=case.id,
                    prompt=case.prompt,
                    output="",
                    passed=False,
                    quality_score=0.0,
                    risk_score=1.0,
                    latency_ms=0.0,
                    turns=case.turns,
                    error=str(exc),
                    needs_review=True,
                )
                result.capsule = build_failure_capsule(result)
                results.append(result)
        return EvaluationReport(suite.name, results, started, utc_now())
