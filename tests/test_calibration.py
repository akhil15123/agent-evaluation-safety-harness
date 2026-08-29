import json

from agent_harness.calibration import calibrate_judge


def test_calibrates_judge_against_human_labels(tmp_path):
    judge = tmp_path / "judge.json"
    reviews = tmp_path / "reviews.json"
    output = tmp_path / "calibration.json"
    judge.write_text(json.dumps({"judge_model": "judge-v1", "cases": [{"case_id": "a", "scores": {"task_completion": 0.9}}, {"case_id": "b", "scores": {"task_completion": 0.2}}]}))
    reviews.write_text(json.dumps({"items": [{"case_id": "a", "status": "reviewed", "decision": "pass"}, {"case_id": "b", "status": "reviewed", "decision": "fail"}]}))
    artifact = calibrate_judge(judge, reviews, output)
    assert artifact["accuracy"] == 1
    assert artifact["labels"] == 2
    assert json.loads(output.read_text()) == artifact
