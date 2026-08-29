from agent_harness.adapters import ResilientAdapter
from agent_harness.models import AgentResponse
from agent_harness.models import TestCase as HarnessCase


class FlakyAdapter:
    def __init__(self):
        self.calls = 0

    def invoke(self, _case):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Provider returned HTTP 429")
        return AgentResponse("ok")


def test_transient_error_is_retried(monkeypatch):
    monkeypatch.setattr("agent_harness.adapters.time.sleep", lambda _seconds: None)
    inner = FlakyAdapter()
    response = ResilientAdapter(inner, retries=1).invoke(HarnessCase("x", "hello"))
    assert response.output == "ok"
    assert inner.calls == 2
