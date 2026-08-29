from agent_harness.telemetry import redact_value, write_jsonl_trace


def test_nested_trace_redaction(tmp_path):
    secret = "sk-" + "a" * 30
    value = redact_value({"authorization": "Bearer abcdefghijklmnop", "nested": [secret]})
    assert value["authorization"] == "[REDACTED]"
    assert value["nested"] == ["[REDACTED]"]
    path = tmp_path / "trace.jsonl"
    write_jsonl_trace({"suite_name": "x", "results": [{"case_id": "a", "model": "m", "trace": [{"input": secret}]}]}, path)
    assert secret not in path.read_text()
