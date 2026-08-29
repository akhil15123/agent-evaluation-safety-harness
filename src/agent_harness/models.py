from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class AgentResponse:
    output: str
    tool_calls: list[str] = field(default_factory=list)
    retrieved_context: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    confidence: float = 1.0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TestCase:
    id: str
    prompt: str
    expected: dict[str, Any] = field(default_factory=dict)
    forbidden: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SafetyPolicy:
    block_prompt_injection: bool = True
    block_secret_leakage: bool = True
    block_pii: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    denied_phrases: list[str] = field(default_factory=list)
    max_output_chars: int = 20_000
    risk_threshold: float = 0.5
    injection_action: str = "block"
    min_confidence: float = 0.55


@dataclass(slots=True)
class EvaluationSuite:
    name: str
    cases: list[TestCase]
    policy: SafetyPolicy = field(default_factory=SafetyPolicy)
    description: str = ""


@dataclass(slots=True)
class Finding:
    category: str
    severity: str
    message: str
    evidence: str = ""
    score: float = 0.0


@dataclass(slots=True)
class CheckResult:
    name: str
    passed: bool
    score: float
    message: str


@dataclass(slots=True)
class CaseResult:
    case_id: str
    prompt: str
    output: str
    passed: bool
    quality_score: float
    risk_score: float
    latency_ms: float
    checks: list[CheckResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    retrieved_context: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    model: str = "unknown"
    confidence: float = 1.0
    mitigations: list[str] = field(default_factory=list)
    needs_review: bool = False
    capsule: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class EvaluationReport:
    suite_name: str
    results: list[CaseResult]
    started_at: str
    finished_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def pass_rate(self) -> float:
        return sum(result.passed for result in self.results) / len(self.results) if self.results else 0.0

    @property
    def average_quality(self) -> float:
        return sum(result.quality_score for result in self.results) / len(self.results) if self.results else 0.0

    @property
    def average_risk(self) -> float:
        return sum(result.risk_score for result in self.results) / len(self.results) if self.results else 0.0

    def metric_average(self, name: str) -> float:
        values = [result.metrics[name] for result in self.results if name in result.metrics]
        return sum(values) / len(values) if values else 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["summary"] = {
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "average_quality": round(self.average_quality, 4),
            "average_risk": round(self.average_risk, 4),
            "total": len(self.results),
            "failed": sum(not result.passed for result in self.results),
            "needs_review": sum(result.needs_review for result in self.results),
            "task_completion": round(self.metric_average("task_completion"), 4),
            "groundedness": round(self.metric_average("groundedness"), 4),
            "tool_correctness": round(self.metric_average("tool_correctness"), 4),
            "hallucination_rate": round(self.metric_average("hallucination_rate"), 4),
            "refusal_quality": round(self.metric_average("refusal_quality"), 4),
            "safety_pass_rate": round(self.metric_average("safety_pass"), 4),
            "total_latency_ms": round(sum(result.latency_ms for result in self.results), 2),
            "total_cost_usd": round(sum(result.metrics.get("cost_usd", 0) for result in self.results), 6),
        }
        return data


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
