from __future__ import annotations

import hashlib
import json

from .models import CaseResult

CONTROL_MAP = {
    "prompt_injection": "Add an input/retrieval injection gate before agent execution.",
    "secret_leakage": "Redact sensitive values and block egress before returning output.",
    "pii": "Require identity verification and tokenize or redact customer data.",
    "tool_policy": "Move this tool behind an allowlist and server-side authorization check.",
    "content_policy": "Add a domain-specific output policy before response delivery.",
    "output_limit": "Enforce a bounded response or tool-output budget.",
    "low_confidence": "Route below-threshold responses to a human or clarifying step.",
    "quality": "Add a grounded response template and a deterministic regression assertion.",
}


def build_failure_capsule(result: CaseResult) -> dict:
    categories = [finding.category for finding in result.findings]
    failed_checks = [check.name for check in result.checks if not check.passed]
    if categories:
        root_cause = categories[0]
    elif result.confidence < 0.55:
        root_cause = "low_confidence"
    elif failed_checks:
        root_cause = "quality"
    elif result.error:
        root_cause = "execution_error"
    else:
        root_cause = "ambiguous"
    identity = json.dumps({
        "case_id": result.case_id,
        "prompt": result.prompt,
        "tools": result.tool_calls,
        "categories": categories,
        "failed_checks": failed_checks,
    }, sort_keys=True).encode()
    fingerprint = hashlib.sha256(identity).hexdigest()[:16]
    return {
        "fingerprint": fingerprint,
        "root_cause": root_cause,
        "failed_checks": failed_checks,
        "finding_categories": categories,
        "first_failed_step": _first_failed_step(result),
        "suggested_control": CONTROL_MAP.get(root_cause, "Inspect the trace and add a case-specific policy or evaluator."),
        "replay_payload": {
            "prompt": result.prompt,
            "output": result.output,
            "tool_calls": result.tool_calls,
            "retrieved_context": result.retrieved_context,
            "confidence": result.confidence,
            "model": result.model,
        },
    }


def _first_failed_step(result: CaseResult) -> dict | None:
    for step in result.trace:
        if step.get("status") not in (None, "ok"):
            return {"step": step.get("step"), "type": step.get("type"), "name": step.get("name"), "status": step.get("status")}
    if result.findings and result.trace:
        step = result.trace[-1]
        return {"step": step.get("step"), "type": step.get("type"), "name": step.get("name"), "status": "policy_failure"}
    return None
