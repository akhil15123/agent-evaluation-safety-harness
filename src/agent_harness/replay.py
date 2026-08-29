from __future__ import annotations

import json
from pathlib import Path

from .models import AgentResponse, SafetyPolicy, TestCase
from .safety import calculate_risk, detect_prompt_injection, scan_safety


def replay_policy(report_path: str, policy_path: str, output_path: str) -> dict:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    raw_policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    policy = SafetyPolicy(**raw_policy)
    cases = []
    for result in report["results"]:
        prompt = result["prompt"]
        injection = detect_prompt_injection(prompt) if policy.block_prompt_injection else None
        would_block = bool(injection and policy.injection_action == "block")
        response = AgentResponse(
            output=result.get("output", ""),
            tool_calls=result.get("tool_calls", []),
            retrieved_context=result.get("retrieved_context", []),
            confidence=float(result.get("confidence", 1)),
            model=result.get("model", "unknown"),
        )
        findings = scan_safety(TestCase(result["case_id"], prompt), response, policy)
        risk = calculate_risk(findings)
        cases.append({
            "case_id": result["case_id"],
            "would_block_before_execution": would_block,
            "prevented_tool_calls": response.tool_calls if would_block else [],
            "would_route_to_human": response.confidence < policy.min_confidence,
            "risk_score": risk,
            "finding_categories": [finding.category for finding in findings],
            "safety_pass": would_block or risk <= policy.risk_threshold,
        })
    replay = {
        "source_report": str(report_path),
        "policy": raw_policy,
        "summary": {
            "cases": len(cases),
            "pre_execution_blocks": sum(case["would_block_before_execution"] for case in cases),
            "prevented_tool_calls": sum(len(case["prevented_tool_calls"]) for case in cases),
            "human_routes": sum(case["would_route_to_human"] for case in cases),
            "safety_pass_rate": sum(case["safety_pass"] for case in cases) / len(cases) if cases else 0,
        },
        "cases": cases,
    }
    Path(output_path).write_text(json.dumps(replay, indent=2) + "\n", encoding="utf-8")
    return replay
