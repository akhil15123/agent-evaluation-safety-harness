import json
from pathlib import Path

from agent_harness.forensics import compare_reports
from agent_harness.replay import replay_policy

ROOT = Path(__file__).parents[1]


def test_trace_comparison_finds_fixes():
    comparison = compare_reports(ROOT / "docs/runs/baseline-v1.json", ROOT / "docs/runs/guardrailed-v2.json")
    assert comparison["summary"]["fixed"] == 2
    assert comparison["summary"]["regressed"] == 0
    warranty = next(case for case in comparison["cases"] if case["case_id"] == "hallucination-warranty-trap")
    assert warranty["first_divergence"]["layer"] == "model"


def test_counterfactual_policy_replay(tmp_path):
    output = tmp_path / "replay.json"
    replay = replay_policy(ROOT / "docs/runs/baseline-v1.json", ROOT / "examples/strict-policy.json", output)
    assert replay["summary"]["pre_execution_blocks"] == 1
    assert replay["summary"]["human_routes"] == 1
    assert json.loads(output.read_text())["summary"] == replay["summary"]


def test_comparison_html_renders_status_pills_and_signed_delta_chips(tmp_path):
    from agent_harness.forensics import write_comparison

    comparison = compare_reports(ROOT / "docs/runs/baseline-v1.json", ROOT / "docs/runs/guardrailed-v2.json")
    write_comparison(comparison, tmp_path / "c.json", tmp_path / "c.html")
    page = (tmp_path / "c.html").read_text()
    assert "<span class='status fixed'>Fixed</span>" in page
    # risk went down on a fixed case, which is an improvement
    assert "chip up" in page and "Risk ▼" in page
    assert "{&quot;quality&quot;" not in page  # no raw JSON dicts in the delta column
    assert json.loads((tmp_path / "c.json").read_text()) == comparison
