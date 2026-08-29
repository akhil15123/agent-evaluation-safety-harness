from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def compare_reports(baseline_path: str, candidate_path: str) -> dict[str, Any]:
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    candidate = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
    base_cases = {result["case_id"]: result for result in baseline["results"]}
    candidate_cases = {result["case_id"]: result for result in candidate["results"]}
    cases = []
    for case_id in sorted(base_cases.keys() | candidate_cases.keys()):
        before, after = base_cases.get(case_id), candidate_cases.get(case_id)
        if not before or not after:
            cases.append({"case_id": case_id, "status": "added" if after else "removed", "first_divergence": None})
            continue
        if not before["passed"] and after["passed"]:
            status = "fixed"
        elif before["passed"] and not after["passed"]:
            status = "regressed"
        elif before["passed"] and after["passed"]:
            status = "stable_pass"
        else:
            status = "still_failing"
        cases.append({
            "case_id": case_id,
            "status": status,
            "first_divergence": _first_divergence(before, after),
            "delta": {
                "quality": round(after["quality_score"] - before["quality_score"], 4),
                "risk": round(after["risk_score"] - before["risk_score"], 4),
                "tool_correctness": round(after.get("metrics", {}).get("tool_correctness", 0) - before.get("metrics", {}).get("tool_correctness", 0), 4),
                "hallucination_rate": round(after.get("metrics", {}).get("hallucination_rate", 0) - before.get("metrics", {}).get("hallucination_rate", 0), 4),
            },
        })
    return {
        "baseline": baseline.get("metadata", {}).get("run_label", Path(baseline_path).stem),
        "candidate": candidate.get("metadata", {}).get("run_label", Path(candidate_path).stem),
        "summary": {
            "fixed": sum(case["status"] == "fixed" for case in cases),
            "regressed": sum(case["status"] == "regressed" for case in cases),
            "still_failing": sum(case["status"] == "still_failing" for case in cases),
            "stable_pass": sum(case["status"] == "stable_pass" for case in cases),
        },
        "cases": cases,
    }


def _first_divergence(before: dict, after: dict) -> dict | None:
    if before.get("mitigations") != after.get("mitigations"):
        return {"layer": "guardrail", "before": before.get("mitigations", []), "after": after.get("mitigations", [])}
    before_trace, after_trace = before.get("trace", []), after.get("trace", [])
    for index in range(max(len(before_trace), len(after_trace))):
        left = before_trace[index] if index < len(before_trace) else None
        right = after_trace[index] if index < len(after_trace) else None
        left_key = _step_key(left)
        right_key = _step_key(right)
        if left_key != right_key:
            kind = (right or left or {}).get("type", "execution")
            return {"layer": kind, "step": index + 1, "before": left_key, "after": right_key}
    if before.get("output") != after.get("output"):
        return {"layer": "output", "before": before.get("output"), "after": after.get("output")}
    return None


def _step_key(step: dict | None) -> dict | None:
    if step is None:
        return None
    return {key: step.get(key) for key in ("type", "name", "input", "output", "status")}


def write_comparison(comparison: dict, json_path: str, html_path: str | None = None) -> None:
    Path(json_path).write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    if not html_path:
        return
    rows = "".join(f"<tr><td>{html.escape(case['case_id'])}</td><td class='{case['status']}'>{case['status'].replace('_', ' ')}</td><td>{html.escape((case.get('first_divergence') or {}).get('layer', 'none'))}</td><td><code>{html.escape(json.dumps(case.get('delta', {})))}</code></td></tr>" for case in comparison["cases"])
    summary = comparison["summary"]
    document = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Trace comparison</title><style>body{{background:#f4f7fb;color:#12213c;font:15px system-ui;margin:0}}main{{max-width:1050px;margin:45px auto;padding:0 20px}}h1{{font-size:34px}}.hero,table{{background:white;border:1px solid #dce3ef;border-radius:14px}}.hero{{padding:24px;margin-bottom:18px}}table{{border-collapse:separate;border-spacing:0;width:100%;overflow:hidden}}th,td{{padding:14px;border-bottom:1px solid #e3e8f0;text-align:left}}th{{color:#667085;font-size:12px}}.fixed{{color:#078061;font-weight:700}}.regressed,.still_failing{{color:#c13d52;font-weight:700}}code{{font-size:11px}}</style></head><body><main><div class="hero"><div>AGENT FLIGHT RECORDER</div><h1>{html.escape(comparison['baseline'])} → {html.escape(comparison['candidate'])}</h1><p>{summary['fixed']} fixed · {summary['regressed']} regressed · {summary['stable_pass']} stable</p></div><table><thead><tr><th>Case</th><th>Status</th><th>First divergence</th><th>Metric delta</th></tr></thead><tbody>{rows}</tbody></table></main></body></html>"""
    Path(html_path).write_text(document, encoding="utf-8")
