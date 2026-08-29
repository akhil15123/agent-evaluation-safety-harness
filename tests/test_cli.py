from pathlib import Path

from agent_harness.cli import main

ROOT = Path(__file__).parents[1]


def test_run_experiment_and_artifact_commands(tmp_path):
    report = tmp_path / "report.json"
    html = tmp_path / "report.html"
    queue = tmp_path / "queue.json"
    database = tmp_path / "runs.db"
    trace = tmp_path / "trace.jsonl"
    assert main([
        "run", str(ROOT / "examples/workflows-suite.json"), "--workflow-agent",
        "--json", str(report), "--html", str(html), "--review-queue", str(queue),
        "--db", str(database), "--jsonl-trace", str(trace),
    ]) == 0
    assert all(path.exists() for path in (report, html, queue, database, trace))

    experiment = tmp_path / "experiment.json"
    assert main(["experiment", str(ROOT / "examples/workflows-suite.json"), "--workflow-agent", "--trials", "2", "--workers", "2", "--output", str(experiment)]) == 0
    assert experiment.exists()

    dashboard = tmp_path / "dashboard.html"
    baseline = ROOT / "docs/runs/baseline-v1.json"
    candidate = ROOT / "docs/runs/guardrailed-v2.json"
    assert main(["dashboard", str(baseline), str(candidate), "--output", str(dashboard)]) == 0
    comparison = tmp_path / "comparison.json"
    comparison_html = tmp_path / "comparison.html"
    assert main(["compare", str(baseline), str(candidate), "--json", str(comparison), "--html", str(comparison_html)]) == 0
    replay = tmp_path / "replay.json"
    assert main(["replay", str(baseline), str(ROOT / "examples/strict-policy.json"), "--output", str(replay)]) == 0
    assert all(path.exists() for path in (dashboard, comparison, comparison_html, replay))

    assert main(["review", str(queue), "ambiguous-cross-workflow-request", "--decision", "ambiguous", "--notes", "needs context", "--reviewer", "alex"]) == 0


def test_cli_validation_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert main(["run", str(bad)]) == 2
    assert "Invalid JSON" in capsys.readouterr().err


def test_judge_command_is_routed(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_harness.cli.judge_report", lambda *_a: {"cases": [{"case_id": "x"}]})
    assert main(["judge", "report.json", "--output", str(tmp_path / "judge.json")]) == 0
