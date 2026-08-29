from __future__ import annotations

import html
import json
from pathlib import Path

from .models import EvaluationReport


def write_json_report(report: EvaluationReport, path: str | Path) -> None:
    Path(path).write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")


def write_html_report(report: EvaluationReport, path: str | Path) -> None:
    summary = report.to_dict()["summary"]
    rows = []
    for result in report.results:
        findings = "".join(
            f'<li><strong>{html.escape(f.severity.upper())}</strong> · {html.escape(f.message)}</li>'
            for f in result.findings
        ) or "<li>None</li>"
        trace = "".join(
            f'<li><span>{html.escape(str(step.get("type", "step"))).upper()}</span><strong>{html.escape(str(step.get("name", "")))}</strong><small>{html.escape(str(step.get("status", "ok")))}</small></li>'
            for step in result.trace
        ) or "<li>No trace supplied</li>"
        mitigations = ", ".join(result.mitigations) or "None"
        rows.append(f"""
        <article class="case {'pass' if result.passed else 'fail'}">
          <div class="case-head"><div><span class="status">{'PASS' if result.passed else 'FAIL'}</span><h2>{html.escape(result.case_id)}</h2></div><div class="scores">Quality {result.quality_score:.0%}<br>Risk {result.risk_score:.0%}</div></div>
          <details><summary>Prompt & response</summary><h3>Prompt</h3><pre>{html.escape(result.prompt)}</pre><h3>Response</h3><pre>{html.escape(result.output or result.error or '')}</pre></details>
          <details><summary>Safety findings ({len(result.findings)})</summary><ul>{findings}</ul></details>
          <details><summary>Execution trace ({len(result.trace)} steps)</summary><ol class="trace">{trace}</ol></details>
          <p class="meta">Model: {html.escape(result.model)} · Confidence: {result.confidence:.0%} · Tools: {html.escape(', '.join(result.tool_calls) or 'none')} · Mitigations: {html.escape(mitigations)}</p>
        </article>""")

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(report.suite_name)} · Agent Harness</title>
<style>
:root{{--ink:#14213d;--muted:#65758b;--paper:#f6f8fb;--card:#fff;--green:#0f8a5f;--red:#d64545;--line:#dce3ec}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,sans-serif}}main{{max-width:960px;margin:auto;padding:48px 20px}}header{{background:linear-gradient(135deg,#14213d,#254c77);color:white;padding:32px;border-radius:18px;box-shadow:0 12px 30px #14213d22}}h1{{margin:0 0 4px;font-size:32px}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;opacity:.7;font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}.metric,.case{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}}.metric strong{{display:block;font-size:28px}}.metric span,.scores,.meta{{color:var(--muted)}}.case{{margin:12px 0;border-left:5px solid var(--green)}}.case.fail{{border-left-color:var(--red)}}.case-head,.case-head>div{{display:flex;align-items:center;justify-content:space-between;gap:12px}}.case h2{{font-size:18px}}.status{{font-size:11px;font-weight:800;color:white;background:var(--green);padding:4px 7px;border-radius:5px}}.fail .status{{background:var(--red)}}details{{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}}summary{{cursor:pointer;font-weight:650}}pre{{white-space:pre-wrap;background:#f1f4f8;padding:12px;border-radius:8px;overflow:auto}}.trace{{padding-left:25px}}.trace li{{padding:5px}}.trace span{{color:#3366ff;font-size:10px;font-weight:800;margin-right:8px}}.trace small{{color:var(--muted);float:right}}.meta{{font-size:12px}}@media(max-width:650px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main><header><div class="eyebrow">Agent Evaluation + Safety Harness</div><h1>{html.escape(report.suite_name)}</h1><div>Generated {html.escape(report.finished_at)}</div></header>
<section class="grid"><div class="metric"><strong>{summary['pass_rate']:.0%}</strong><span>Pass rate</span></div><div class="metric"><strong>{summary['average_quality']:.0%}</strong><span>Avg. quality</span></div><div class="metric"><strong>{summary['average_risk']:.0%}</strong><span>Avg. risk</span></div><div class="metric"><strong>{summary['total']}</strong><span>Test cases</span></div></section>
{''.join(rows)}<p class="eyebrow">Built with Agent Harness</p></main></body></html>"""
    Path(path).write_text(document, encoding="utf-8")
