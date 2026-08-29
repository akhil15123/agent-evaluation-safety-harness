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
