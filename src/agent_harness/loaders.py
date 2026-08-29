from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EvaluationSuite, SafetyPolicy, TestCase


class SuiteValidationError(ValueError):
    pass


def load_suite(path: str | Path) -> EvaluationSuite:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SuiteValidationError(f"Suite not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise SuiteValidationError(f"Invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    return suite_from_dict(data)


def suite_from_dict(data: dict[str, Any]) -> EvaluationSuite:
    if not isinstance(data, dict):
        raise SuiteValidationError("Suite must be a JSON object")
    name = data.get("name")
    cases_data = data.get("cases")
    if not isinstance(name, str) or not name.strip():
        raise SuiteValidationError("Suite requires a non-empty 'name'")
    if not isinstance(cases_data, list) or not cases_data:
        raise SuiteValidationError("Suite requires at least one case")

    policy_data = data.get("policy", {})
    if not isinstance(policy_data, dict):
        raise SuiteValidationError("'policy' must be an object")
    allowed_policy_fields = set(SafetyPolicy.__dataclass_fields__)
    unknown = set(policy_data) - allowed_policy_fields
    if unknown:
        raise SuiteValidationError(f"Unknown policy fields: {', '.join(sorted(unknown))}")
    policy = SafetyPolicy(**policy_data)

    cases: list[TestCase] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(cases_data):
        if not isinstance(raw, dict):
            raise SuiteValidationError(f"Case {index} must be an object")
        case_id, prompt = raw.get("id"), raw.get("prompt")
        if not isinstance(case_id, str) or not case_id.strip():
            raise SuiteValidationError(f"Case {index} requires a non-empty 'id'")
        if case_id in seen_ids:
            raise SuiteValidationError(f"Duplicate case id: {case_id}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SuiteValidationError(f"Case '{case_id}' requires a non-empty 'prompt'")
        seen_ids.add(case_id)
        cases.append(TestCase(
            id=case_id,
            prompt=prompt,
            turns=raw.get("turns", []),
            expected=raw.get("expected", {}),
            forbidden=raw.get("forbidden", []),
            tags=raw.get("tags", []),
            metadata=raw.get("metadata", {}),
        ))
    return EvaluationSuite(name=name, cases=cases, policy=policy, description=data.get("description", ""))
