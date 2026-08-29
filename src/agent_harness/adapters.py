from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from .models import AgentResponse, TestCase


class AgentAdapter(Protocol):
    def invoke(self, case: TestCase) -> AgentResponse: ...


@dataclass(slots=True)
class EchoAdapter:
    """Deterministic adapter for smoke tests and harness development."""

    prefix: str = "Agent received: "

    def invoke(self, case: TestCase) -> AgentResponse:
        return AgentResponse(output=f"{self.prefix}{case.prompt}", latency_ms=0.0)


@dataclass(slots=True)
class RecordedAdapter:
    """Returns checked-in responses, enabling reproducible offline evaluations."""

    responses: dict[str, AgentResponse]

    def invoke(self, case: TestCase) -> AgentResponse:
        if case.id not in self.responses:
            raise KeyError(f"No recorded response for case '{case.id}'")
        return self.responses[case.id]

    @classmethod
    def from_file(cls, path: str) -> RecordedAdapter:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        responses = {
            case_id: AgentResponse(
                output=value["output"],
                tool_calls=value.get("tool_calls", []),
                retrieved_context=value.get("retrieved_context", []),
                trace=value.get("trace", []),
                latency_ms=float(value.get("latency_ms", 0)),
                confidence=float(value.get("confidence", 1)),
                cost_usd=float(value.get("cost_usd", 0)),
                input_tokens=int(value.get("input_tokens", 0)),
                output_tokens=int(value.get("output_tokens", 0)),
                model=value.get("model", "recorded"),
                metadata=value.get("metadata", {}),
            )
            for case_id, value in data.items()
        }
        return cls(responses)


@dataclass(slots=True)
class HttpAdapter:
    """Calls an agent endpoint using {prompt, case_id, metadata} JSON."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0

    def invoke(self, case: TestCase) -> AgentResponse:
        payload = json.dumps({
            "prompt": case.prompt,
            "case_id": case.id,
            "metadata": case.metadata,
        }).encode()
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json", **self.headers},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode())
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Agent endpoint failed: {exc}") from exc
        latency = (time.perf_counter() - started) * 1000
        if not isinstance(body.get("output"), str):
            raise TypeError("Agent response must contain a string 'output'")
        return AgentResponse(
            output=body["output"],
            tool_calls=body.get("tool_calls", []),
            retrieved_context=body.get("retrieved_context", []),
            trace=body.get("trace", []),
            latency_ms=latency,
            confidence=float(body.get("confidence", 1)),
            cost_usd=float(body.get("cost_usd", 0)),
            input_tokens=int(body.get("input_tokens", 0)),
            output_tokens=int(body.get("output_tokens", 0)),
            model=body.get("model", "http-agent"),
            metadata=body.get("metadata", {}),
        )


class ResilientAdapter:
    """Provider-neutral request pacing and bounded retry wrapper."""

    def __init__(self, adapter: AgentAdapter, requests_per_second: float = 0.0, retries: int = 0):
        self.adapter = adapter
        self.interval = 1 / requests_per_second if requests_per_second > 0 else 0.0
        self.retries = max(0, retries)
        self._lock = threading.Lock()
        self._next_request = 0.0

    def invoke(self, case: TestCase) -> AgentResponse:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._pace()
            try:
                return self.adapter.invoke(case)
            except RuntimeError as exc:
                last_error = exc
                if attempt >= self.retries or not _retryable(str(exc)):
                    raise
                time.sleep(min(2**attempt * 0.25, 4.0))
        raise RuntimeError(str(last_error))

    def _pace(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_request - now)
            self._next_request = max(now, self._next_request) + self.interval
        if wait:
            time.sleep(wait)


def _retryable(message: str) -> bool:
    lowered = message.casefold()
    return any(marker in lowered for marker in ("http 429", "http 500", "http 502", "http 503", "http 504", "timed out", "temporarily unavailable"))
