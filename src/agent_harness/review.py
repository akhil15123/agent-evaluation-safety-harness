from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import EvaluationReport


def write_review_queue(report: EvaluationReport, path: str | Path) -> int:
    items = []
    for result in report.results:
        if not result.needs_review:
            continue
        items.append({
            "case_id": result.case_id,
            "suite": report.suite_name,
            "status": "pending",
            "prompt": result.prompt,
            "output": result.output,
            "confidence": result.confidence,
            "metrics": result.metrics,
            "failure_reasons": [check.message for check in result.checks if not check.passed] + [finding.message for finding in result.findings],
            "decision": None,
            "notes": "",
            "reviewer": "",
            "reviewed_at": None,
            "failure_capsule": result.capsule,
        })
    Path(path).write_text(json.dumps({"version": 1, "items": items}, indent=2) + "\n", encoding="utf-8")
    return len(items)


def apply_review(path: str | Path, case_id: str, decision: str, notes: str = "", reviewer: str = "human") -> dict[str, Any]:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    matches = [item for item in data.get("items", []) if item.get("case_id") == case_id]
    if not matches:
        raise ValueError(f"Case '{case_id}' was not found in {source}")
    item = matches[0]
    item.update({
        "status": "reviewed",
        "decision": decision,
        "notes": notes,
        "reviewer": reviewer,
        "reviewed_at": datetime.now(UTC).isoformat(),
    })
    source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return item


def promote_reviewed_cases(queue_path: str | Path, output_path: str | Path, suite_name: str = "Human-reviewed regressions") -> int:
    queue = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    cases = []
    for item in queue.get("items", []):
        if item.get("status") != "reviewed" or item.get("decision") == "ambiguous":
            continue
        output = item.get("output", "")
        case = {
            "id": f"reviewed-{item['case_id']}",
            "prompt": item["prompt"],
            "tags": ["human-reviewed", f"decision-{item['decision']}"],
            "metadata": {"source_suite": item.get("suite"), "reviewer": item.get("reviewer"), "reviewed_at": item.get("reviewed_at"), "review_notes": item.get("notes", "")},
        }
        if item["decision"] == "pass":
            case["expected"] = {"exact": output}
        else:
            case["forbidden"] = [output] if output else []
            case["expected"] = {"forbidden_claims": [output] if output else []}
        cases.append(case)
    suite = {"schema_version": 1, "name": suite_name, "description": "Cases promoted from explicit human decisions; review exact assertions before long-term use.", "cases": cases}
    Path(output_path).write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    return len(cases)
