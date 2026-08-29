import json

import pytest

from agent_harness.store import RunStore


def sample_report():
    return {
        "suite_name": "suite",
        "finished_at": "2026-01-01T00:00:00+00:00",
        "metadata": {"run_label": "candidate"},
        "summary": {"passed": False, "pass_rate": 0.0},
        "results": [{
            "case_id": "case-1",
            "prompt": "hello",
            "output": "uncertain",
            "passed": False,
            "needs_review": True,
            "confidence": 0.3,
            "metrics": {},
            "findings": [],
            "trace": [],
            "capsule": {"root_cause": "low_confidence"},
            "model": "model-v1",
        }],
    }


def test_store_ingest_and_optimistic_review(tmp_path):
    store = RunStore(tmp_path / "runs.db")
    run_id = store.ingest_report(sample_report())
    assert store.list_runs()[0]["id"] == run_id
    assert store.get_run(run_id)["suite_name"] == "suite"
    review = store.list_reviews("pending")[0]
    decided = store.decide_review(review["id"], "ambiguous", "needs context", "alex", review["version"])
    assert decided["status"] == "reviewed"
    assert decided["version"] == 2
    with pytest.raises(RuntimeError, match="another reviewer"):
        store.decide_review(review["id"], "pass", "", "sam", review["version"])


def test_store_persists_json_payload(tmp_path):
    store = RunStore(tmp_path / "runs.db")
    store.ingest_report(sample_report(), "manual-label")
    run = store.list_runs()[0]
    assert run["label"] == "manual-label"
    assert json.loads(run["summary_json"])["pass_rate"] == 0
