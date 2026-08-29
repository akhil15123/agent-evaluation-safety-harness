from agent_harness.tooling import ToolPolicyError, ToolSandbox, ToolSpec, object_schema, validate_json_schema


def test_contract_rejects_missing_and_unknown_arguments():
    schema = object_schema({"name": {"type": "string"}}, ["name"])
    try:
        validate_json_schema({}, schema)
    except ToolPolicyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing argument was accepted")
    try:
        validate_json_schema({"name": "x", "secret": "y"}, schema)
    except ToolPolicyError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown argument was accepted")


def test_confirmation_prevents_state_change():
    tool = ToolSpec("write", "write", object_schema({"value": {"type": "string"}}, ["value"]), lambda a, s: s["items"].append(a["value"]), "write", requires_confirmation=True)
    sandbox = ToolSandbox([tool], state={"items": []})
    execution = sandbox.execute("write", {"value": "x"})
    assert execution.status == "blocked"
    assert execution.blocked_reason == "human_confirmation_required"
    assert sandbox.state["items"] == []


def test_canary_cannot_reach_egress_tool():
    tool = ToolSpec("send", "send", object_schema({"body": {"type": "string"}}, ["body"]), lambda _a, _s: {"sent": True}, "write", egress=True)
    sandbox = ToolSandbox([tool], canaries=["CANARY-42"])
    execution = sandbox.execute("send", {"body": "leak CANARY-42"})
    assert execution.status == "blocked"
    assert execution.blocked_reason == "sensitive_canary_egress"
    assert execution.canary_hits == ["CANARY-42"]


def test_approved_write_executes_in_isolated_state():
    tool = ToolSpec("write", "write", object_schema({"value": {"type": "string"}}, ["value"]), lambda a, s: s["items"].append(a["value"]) or {"ok": True}, "write", requires_confirmation=True)
    original = {"items": []}
    sandbox = ToolSandbox([tool], state=original, approvals={"write"})
    assert sandbox.execute("write", {"value": "safe"}).status == "ok"
    assert sandbox.state["items"] == ["safe"]
    assert original["items"] == []
