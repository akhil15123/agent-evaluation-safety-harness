from __future__ import annotations

import html
import json
from pathlib import Path


def write_regression_dashboard(report_paths: list[str], output: str) -> None:
    runs = []
    for report_path in report_paths:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        summary = data["summary"]
        models = sorted({result.get("model", "unknown") for result in data.get("results", [])})
        runs.append({
            "label": data.get("metadata", {}).get("run_label") or Path(report_path).stem,
            "suite": data["suite_name"],
            "model": ", ".join(models),
            "finished": data["finished_at"],
            **summary,
        })

    def pct(value: float) -> str:
        return f"{value:.0%}"

    rows = "".join(f"""
      <tr><td><strong>{html.escape(run['label'])}</strong><small>{html.escape(run['finished'][:19])}</small></td><td>{html.escape(run['model'])}</td>
      <td>{pct(run['pass_rate'])}</td><td>{pct(run['task_completion'])}</td><td>{pct(run['groundedness'])}</td><td>{pct(run['tool_correctness'])}</td>
      <td class="{'bad' if run['hallucination_rate'] else ''}">{pct(run['hallucination_rate'])}</td><td>{pct(run['safety_pass_rate'])}</td><td>${run['total_cost_usd']:.5f}</td><td>{run['total_latency_ms']:.0f} ms</td></tr>
    """ for run in runs)
    latest = runs[-1] if runs else {}
    previous = runs[-2] if len(runs) > 1 else latest

    def delta(metric: str) -> str:
        value = latest.get(metric, 0) - previous.get(metric, 0)
        return f"{value:+.1%} vs prior"

    cards = "".join(
        f'<div class="card"><span>{label}</span><strong>{pct(latest.get(metric, 0))}</strong><small>{delta(metric)}</small></div>'
        for label, metric in (("Pass rate", "pass_rate"), ("Groundedness", "groundedness"), ("Tool correctness", "tool_correctness"), ("Safety pass", "safety_pass_rate"))
    )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent Harness · Regressions</title>
<style>:root{{--navy:#101b35;--blue:#3366ff;--paper:#f3f6fb;--line:#dce3ef;--muted:#667085}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--navy);font:14px/1.5 Inter,system-ui,sans-serif}}main{{max-width:1200px;margin:auto;padding:42px 20px}}header{{display:flex;justify-content:space-between;align-items:end}}h1{{font-size:32px;margin:0}}.tag{{background:#dfe7ff;color:#2047bd;border-radius:20px;padding:6px 12px;font-weight:700}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,.table-wrap{{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 6px 18px #14213d0b}}.card{{padding:18px}}.card span,.card small,td small{{color:var(--muted);display:block}}.card strong{{display:block;font-size:29px;margin:4px 0}}.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:1000px}}th,td{{text-align:left;padding:14px;border-bottom:1px solid var(--line);white-space:nowrap}}th{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}}tr:last-child td{{border:0}}.bad{{color:#c63838;font-weight:700}}@media(max-width:750px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}</style></head>
<body><main><header><div><div class="tag">REGRESSION MONITOR</div><h1>Agent quality over time</h1></div><p>{len(runs)} evaluation runs</p></header><section class="cards">{cards}</section><div class="table-wrap"><table><thead><tr><th>Run</th><th>Model</th><th>Pass</th><th>Task</th><th>Grounded</th><th>Tools</th><th>Halluc.</th><th>Safety</th><th>Cost</th><th>Latency</th></tr></thead><tbody>{rows}</tbody></table></div></main></body></html>"""
    Path(output).write_text(document, encoding="utf-8")
