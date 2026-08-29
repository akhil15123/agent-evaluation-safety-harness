import json
from pathlib import Path

from agent_harness.adapters import RecordedAdapter
from agent_harness.demo_agent import SupportAgentAdapter
from agent_harness.engine import EvaluationEngine
from agent_harness.loaders import load_suite, suite_from_dict
from agent_harness.models import AgentResponse
from agent_harness.review import apply_review, write_review_queue


def test_demo_suite_passes():
    suite_path = Path(__file__).parents[1] / "examples" / "support-suite.json"
    report = EvaluationEngine(SupportAgentAdapter()).run(load_suite(suite_path))
    assert report.passed
    assert report.pass_rate == 1
    assert report.metric_average("hallucination_rate") == 0
    assert any(result.mitigations == ["prompt_injection_blocked"] for result in report.results)
    assert any(result.needs_review for result in report.results)


def test_failed_call_does_not_abort_suite():
    suite = suite_from_dict({"name": "x", "cases": [{"id": "missing", "prompt": "hi"}]})
    report = EvaluationEngine(RecordedAdapter({})).run(suite)
    assert not report.passed
    assert report.results[0].error


def test_review_queue_round_trip(tmp_path):
    suite = suite_from_dict({"name": "x", "cases": [{"id": "bad", "prompt": "hi", "expected": {"contains": "bye"}}]})
    report = EvaluationEngine(RecordedAdapter({"bad": AgentResponse("hello")})).run(suite)
    queue = tmp_path / "queue.json"
    assert write_review_queue(report, queue) == 1
    apply_review(queue, "bad", "fail", "Unsupported answer", "alex")
    item = json.loads(queue.read_text())["items"][0]
    assert item["status"] == "reviewed"
    assert item["reviewer"] == "alex"
