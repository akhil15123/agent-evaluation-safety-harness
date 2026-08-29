from agent_harness.models import TestCase as HarnessCase
from agent_harness.providers import AnthropicMessagesAdapter, OllamaChatAdapter, OpenAIResponsesAdapter
from agent_harness.tooling import ToolSandbox, ToolSpec, object_schema


def test_openai_tool_loop_records_usage(monkeypatch):
    responses = iter([
        {"id": "r1", "status": "completed", "usage": {"input_tokens": 10, "output_tokens": 4}, "output": [{"type": "function_call", "name": "lookup", "call_id": "c1", "arguments": "{\"id\":\"42\"}"}]},
        {"id": "r2", "status": "completed", "usage": {"input_tokens": 7, "output_tokens": 6}, "output_text": "Order 42 found", "output": []},
    ])
    monkeypatch.setattr("agent_harness.providers._post_json", lambda *_a, **_k: next(responses))
    tool = ToolSpec("lookup", "lookup", object_schema({"id": {"type": "string"}}, ["id"]), lambda a, _s: {"id": a["id"]})
    result = OpenAIResponsesAdapter("test", ToolSandbox([tool]), api_key="fake").invoke(HarnessCase("x", "find order"))
    assert result.output == "Order 42 found"
    assert result.tool_calls == ["lookup"]
    assert (result.input_tokens, result.output_tokens) == (17, 10)


def test_anthropic_tool_loop(monkeypatch):
    responses = iter([
        {"stop_reason": "tool_use", "usage": {"input_tokens": 8, "output_tokens": 3}, "content": [{"type": "tool_use", "id": "t1", "name": "lookup", "input": {"id": "7"}}]},
        {"stop_reason": "end_turn", "usage": {"input_tokens": 5, "output_tokens": 4}, "content": [{"type": "text", "text": "Found 7"}]},
    ])
    monkeypatch.setattr("agent_harness.providers._post_json", lambda *_a, **_k: next(responses))
    tool = ToolSpec("lookup", "lookup", object_schema({"id": {"type": "string"}}, ["id"]), lambda a, _s: a)
    result = AnthropicMessagesAdapter("test", ToolSandbox([tool]), api_key="fake").invoke(HarnessCase("x", "find"))
    assert result.output == "Found 7"
    assert result.tool_calls == ["lookup"]


def test_ollama_adapter(monkeypatch):
    monkeypatch.setattr("agent_harness.providers._post_json", lambda *_a, **_k: {"message": {"content": "local"}, "prompt_eval_count": 2, "eval_count": 1})
    result = OllamaChatAdapter("local").invoke(HarnessCase("x", "hello"))
    assert result.output == "local"
    assert result.input_tokens == 2
