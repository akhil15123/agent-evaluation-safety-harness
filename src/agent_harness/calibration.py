from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def calibrate_judge(judge_path: str, reviews_path: str, output_path: str, metric: str = "task_completion") -> dict[str, Any]:
    judged = json.loads(Path(judge_path).read_text(encoding="utf-8"))
    reviews = json.loads(Path(reviews_path).read_text(encoding="utf-8"))
    labels = {item["case_id"]: 1 if item.get("decision") == "pass" else 0 for item in reviews.get("items", []) if item.get("status") == "reviewed" and item.get("decision") in {"pass", "fail"}}
    pairs = []
    for case in judged.get("cases", []):
        score = case.get("scores", {}).get(metric)
        if case["case_id"] in labels and isinstance(score, (int, float)):
            pairs.append((float(score), labels[case["case_id"]]))
    if not pairs:
        raise ValueError("No overlapping numeric judge scores and reviewed pass/fail labels")
    candidates = sorted({0.0, 0.5, 1.0, *(score for score, _label in pairs)})
    best_threshold, best_accuracy = max(((threshold, sum((score >= threshold) == bool(label) for score, label in pairs) / len(pairs)) for threshold in candidates), key=lambda item: (item[1], -abs(item[0] - 0.5)))
    artifact = {
        "judge_model": judged.get("judge_model"),
        "metric": metric,
        "labels": len(pairs),
        "recommended_threshold": best_threshold,
        "accuracy": round(best_accuracy, 4),
        "brier_score": round(sum((score - label) ** 2 for score, label in pairs) / len(pairs), 4),
        "warning": "Calibration is descriptive; use representative independent labels before production gating.",
    }
    Path(output_path).write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact
