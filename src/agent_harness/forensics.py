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


# Metric name -> True when an increase is an improvement.
_DELTA_DIRECTION = {"quality": True, "tool_correctness": True, "risk": False, "hallucination_rate": False}
_DELTA_LABELS = {"quality": "Quality", "tool_correctness": "Tools", "risk": "Risk", "hallucination_rate": "Halluc."}
_STATUS_LABELS = {
    "fixed": "Fixed",
    "regressed": "Regressed",
    "still_failing": "Still failing",
    "stable_pass": "Stable pass",
    "added": "Added",
    "removed": "Removed",
}


def _delta_chip(name: str, value: float) -> str:
    label = _DELTA_LABELS.get(name, name.replace("_", " ").title())
    if abs(value) < 1e-9:
        return f"<span class='chip flat'>{html.escape(label)} ±0</span>"
    improved = (value > 0) == _DELTA_DIRECTION.get(name, True)
    tone = "up" if improved else "down"
    arrow = "▲" if value > 0 else "▼"
    return f"<span class='chip {tone}' title='{html.escape(name)}: {value:+.4f}'>{html.escape(label)} {arrow} {abs(value) * 100:.0f}%</span>"


def _divergence_cell(divergence: dict | None) -> str:
    if not divergence:
        return "<span class='layer none'>identical</span>"
    layer = html.escape(str(divergence.get("layer", "execution")))
    step = f" <span class='step'>step {divergence['step']}</span>" if divergence.get("step") else ""
    detail = json.dumps({"before": divergence.get("before"), "after": divergence.get("after")}, indent=2, default=str)
    return (
        f"<details><summary><span class='layer'>{layer}</span>{step}</summary>"
        f"<pre>{html.escape(detail)}</pre></details>"
    )


def write_comparison(comparison: dict, json_path: str, html_path: str | None = None) -> None:
    Path(json_path).write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    if not html_path:
        return
    order = {"regressed": 0, "still_failing": 1, "fixed": 2, "added": 3, "removed": 4, "stable_pass": 5}
    cases = sorted(comparison["cases"], key=lambda case: (order.get(case["status"], 9), case["case_id"]))
    rows = "".join(
        "<tr>"
        f"<td class='case'>{html.escape(case['case_id'])}</td>"
        f"<td><span class='status {case['status']}'>{_STATUS_LABELS.get(case['status'], case['status'])}</span></td>"
        f"<td>{_divergence_cell(case.get('first_divergence'))}</td>"
        f"<td><div class='deltas'>{''.join(_delta_chip(name, value) for name, value in case.get('delta', {}).items())}</div></td>"
        "</tr>"
        for case in cases
    )
    summary = comparison["summary"]
    tiles = "".join(
        f"<div class='tile {key if summary.get(key) else 'zero'}'><strong>{summary.get(key, 0)}</strong><span>{label}</span></div>"
        for key, label in (("fixed", "fixed"), ("regressed", "regressed"), ("still_failing", "still failing"), ("stable_pass", "stable"))
    )
    verdict = "No regressions" if not summary.get("regressed") else f"{summary['regressed']} regression(s)"
    verdict_class = "ok" if not summary.get("regressed") else "bad"
    style = """
:root{--bg:#f4f7fb;--card:#fff;--line:#e3e8f0;--text:#12213c;--muted:#667085;--good:#067a5b;--good-bg:#e6f6f0;--bad:#b4233c;--bad-bg:#fdecef;--ink:#1d3a8a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1120px;margin:40px auto;padding:0 20px}
.hero{background:linear-gradient(135deg,#0f1f47,#1d3a8a 60%,#2f5bd3);color:#fff;border-radius:18px;padding:28px 30px;box-shadow:0 20px 50px -25px rgba(15,31,71,.6)}
.kicker{font-size:11px;letter-spacing:.14em;font-weight:700;opacity:.75}
h1{font-size:clamp(24px,3.6vw,36px);margin:8px 0 6px;letter-spacing:-.02em}
.verdict{display:inline-flex;gap:8px;align-items:center;padding:5px 12px;border-radius:999px;font-size:13px;font-weight:700;background:rgba(255,255,255,.14)}
.verdict.ok::before{content:"✓"}.verdict.bad::before{content:"!"}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;display:grid;gap:2px}
.tile strong{font-size:30px;line-height:1;font-variant-numeric:tabular-nums}.tile span{color:var(--muted);font-size:13px}
.tile.zero strong{color:#98a2b3}.tile.fixed strong{color:var(--good)}.tile.regressed strong,.tile.still_failing strong{color:var(--bad)}
.table-wrap{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:720px}
th,td{padding:13px 16px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
tr:last-child td{border-bottom:0}tbody tr:hover{background:#f8fafd}
th{color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}
.case{font:600 13px ui-monospace,SFMono-Regular,Menlo,monospace}
.status{display:inline-block;white-space:nowrap;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;background:#eef1f6;color:var(--muted)}
.status.fixed{background:var(--good-bg);color:var(--good)}.status.regressed,.status.still_failing{background:var(--bad-bg);color:var(--bad)}
.layer{display:inline-block;padding:2px 8px;border-radius:6px;background:#eaf0ff;color:var(--ink);font:600 12px ui-monospace,SFMono-Regular,Menlo,monospace}
.layer.none{background:#eef1f6;color:var(--muted)}.step{color:var(--muted);font-size:12px;margin-left:6px}
details summary{cursor:pointer;list-style:none}details summary::-webkit-details-marker{display:none}
details summary::after{content:" ▸";color:var(--muted);font-size:11px}details[open] summary::after{content:" ▾"}
pre{margin:10px 0 0;padding:10px 12px;max-width:420px;max-height:260px;overflow:auto;background:#0f1f47;color:#dbe4ff;border-radius:10px;font-size:11.5px}
.deltas{display:flex;flex-wrap:wrap;gap:6px}
.chip{white-space:nowrap;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
.chip.up{background:var(--good-bg);color:var(--good)}.chip.down{background:var(--bad-bg);color:var(--bad)}.chip.flat{background:#f1f3f7;color:#98a2b3}
footer{color:var(--muted);font-size:12.5px;margin:14px 2px}
@media(max-width:640px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.hero{padding:22px}}
"""
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Trace comparison · {html.escape(comparison['baseline'])} → {html.escape(comparison['candidate'])}</title><style>{style}</style></head><body><main>
<section class="hero"><div class="kicker">AGENT FLIGHT RECORDER · TRACE COMPARISON</div><h1>{html.escape(comparison['baseline'])} → {html.escape(comparison['candidate'])}</h1><span class="verdict {verdict_class}">{verdict}</span></section>
<div class="tiles">{tiles}</div>
<div class="table-wrap"><table><thead><tr><th>Case</th><th>Status</th><th>First divergence</th><th>Metric delta (candidate − baseline)</th></tr></thead><tbody>{rows}</tbody></table></div>
<footer>Green means the change moved the metric in the safe direction (quality and tool correctness up, risk and hallucination down). Expand a divergence to see the first differing step.</footer>
</main></body></html>"""
    Path(html_path).write_text(document, encoding="utf-8")
