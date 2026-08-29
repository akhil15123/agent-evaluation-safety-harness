from __future__ import annotations

import re

from .models import AgentResponse, CheckResult, TestCase


def run_quality_checks(case: TestCase, response: AgentResponse) -> list[CheckResult]:
    checks: list[CheckResult] = []
    output = response.output
    expected = case.expected

    if "exact" in expected:
        wanted = str(expected["exact"])
        passed = output.strip() == wanted.strip()
        checks.append(CheckResult("exact", passed, float(passed), "Output matches exactly" if passed else "Exact output mismatch"))

    if "contains" in expected:
        values = expected["contains"]
        values = [values] if isinstance(values, str) else values
        missing = [value for value in values if str(value).casefold() not in output.casefold()]
        score = (len(values) - len(missing)) / len(values) if values else 1.0
        checks.append(CheckResult("contains", not missing, score, "All required phrases present" if not missing else f"Missing: {', '.join(map(str, missing))}"))

    if "regex" in expected:
        pattern = str(expected["regex"])
        passed = re.search(pattern, output, re.IGNORECASE | re.MULTILINE) is not None
        checks.append(CheckResult("regex", passed, float(passed), f"Pattern {'matched' if passed else 'did not match'}: {pattern}"))

    if "max_length" in expected:
        limit = int(expected["max_length"])
        passed = len(output) <= limit
        score = min(1.0, limit / max(1, len(output)))
        checks.append(CheckResult("max_length", passed, score, f"{len(output)} / {limit} characters"))

    for phrase in case.forbidden:
        passed = phrase.casefold() not in output.casefold()
        checks.append(CheckResult(f"forbidden:{phrase}", passed, float(passed), "Phrase absent" if passed else "Forbidden phrase found"))

    if not checks:
        checks.append(CheckResult("non_empty", bool(output.strip()), float(bool(output.strip())), "Output is non-empty" if output.strip() else "Output is empty"))
    return checks


def calculate_metrics(case: TestCase, response: AgentResponse, checks: list[CheckResult], safety_pass: bool) -> dict[str, float]:
    expected = case.expected
    quality = sum(check.score for check in checks) / len(checks) if checks else 0.0

    expected_tools = set(expected.get("tools", []))
    actual_tools = set(response.tool_calls)
    if expected_tools or actual_tools:
        union = expected_tools | actual_tools
        tool_correctness = len(expected_tools & actual_tools) / len(union) if union else 1.0
    else:
        tool_correctness = 1.0

    grounded_facts = expected.get("grounded_facts", [])
    if isinstance(grounded_facts, str):
        grounded_facts = [grounded_facts]
    combined_context = " ".join(response.retrieved_context).casefold()
    output = response.output.casefold()
    grounded_hits = sum(str(fact).casefold() in combined_context and str(fact).casefold() in output for fact in grounded_facts)
    groundedness = grounded_hits / len(grounded_facts) if grounded_facts else 1.0

    forbidden_claims = expected.get("forbidden_claims", [])
    if isinstance(forbidden_claims, str):
        forbidden_claims = [forbidden_claims]
    hallucinations = sum(str(claim).casefold() in output for claim in forbidden_claims)
    hallucination_rate = hallucinations / len(forbidden_claims) if forbidden_claims else 0.0

    refusal_expected = expected.get("refusal")
    refusal_markers = ("can't help", "cannot help", "can't comply", "cannot comply", "human specialist", "won't")
    refused = any(marker in output for marker in refusal_markers)
    refusal_quality = 1.0 if refusal_expected is None or refused == bool(refusal_expected) else 0.0

    tool_steps = [step for step in response.trace if step.get("type") == "tool"]
    expected_args = expected.get("tool_args", {})
    argument_scores = []
    for tool_name, wanted_args in expected_args.items():
        matching = [step for step in tool_steps if step.get("name") == tool_name]
        if not matching:
            argument_scores.append(0.0)
            continue
        actual = matching[0].get("input", {})
        fields = list(wanted_args)
        argument_scores.append(sum(_argument_equal(actual.get(field), wanted_args[field]) for field in fields) / len(fields) if fields else 1.0)
    argument_correctness = sum(argument_scores) / len(argument_scores) if argument_scores else 1.0

    expected_order = expected.get("tool_order", [])
    actual_order = [step.get("name") for step in tool_steps]
    tool_order_correctness = float(not expected_order or actual_order == expected_order)

    expected_blocked = set(expected.get("blocked_tools", []))
    trajectory_hits = []
    for step in tool_steps:
        should_block = step.get("name") in expected_blocked
        trajectory_hits.append((step.get("status") == "blocked") == should_block)
    trajectory_quality = sum(trajectory_hits) / len(trajectory_hits) if trajectory_hits else 1.0

    semantic_groundedness = _semantic_groundedness(response.output, response.retrieved_context) if response.retrieved_context else groundedness
    source_ids = expected.get("sources", [])
    citation_validity = _citation_validity(response.output, source_ids) if source_ids else 1.0

    return {
        "task_completion": round(quality, 4),
        "groundedness": round(groundedness, 4),
        "tool_correctness": round(tool_correctness, 4),
        "argument_correctness": round(argument_correctness, 4),
        "tool_order_correctness": round(tool_order_correctness, 4),
        "trajectory_quality": round(trajectory_quality, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "semantic_groundedness": round(semantic_groundedness, 4),
        "citation_validity": round(citation_validity, 4),
        "refusal_quality": round(refusal_quality, 4),
        "latency_ms": round(response.latency_ms, 2),
        "cost_usd": round(response.cost_usd, 6),
        "safety_pass": float(safety_pass),
    }


def _semantic_groundedness(output: str, context: list[str]) -> float:
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "for", "on", "with", "that", "this"}
    evidence_tokens = set(re.findall(r"[a-z0-9$.-]+", " ".join(context).casefold())) - stop
    claims = [sentence for sentence in re.split(r"(?<=[.!?])\s+", output) if len(sentence.split()) >= 4]
    if not claims:
        return 1.0
    scores = []
    for claim in claims:
        claim_tokens = set(re.findall(r"[a-z0-9$.-]+", claim.casefold())) - stop
        scores.append(len(claim_tokens & evidence_tokens) / len(claim_tokens) if claim_tokens else 1.0)
    return sum(scores) / len(scores)


def _citation_validity(output: str, source_ids: list[str]) -> float:
    citations = re.findall(r"\[source:([^\]]+)\]", output, re.IGNORECASE)
    if not citations:
        return 0.0
    allowed = {source.casefold() for source in source_ids}
    return sum(citation.casefold() in allowed for citation in citations) / len(citations)


def _argument_equal(actual: object, expected: object) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip().casefold() == expected.strip().casefold()
    return actual == expected
