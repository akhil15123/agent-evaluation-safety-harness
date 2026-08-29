from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

REDACTIONS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{12,}"),
]


def write_jsonl_trace(report: dict[str, Any], path: str | Path) -> None:
    with Path(path).open("a", encoding="utf-8") as handle:
        for result in report.get("results", []):
            for step in result.get("trace", []):
                event = {
                    "suite": report.get("suite_name"),
                    "case_id": result.get("case_id"),
                    "model": result.get("model"),
                    "step": redact_value(step),
                }
                handle.write(json.dumps(event, sort_keys=True) + "\n")


def export_open_telemetry(report: dict[str, Any], service_name: str = "agent-harness") -> int:
    """Export a completed report as OpenTelemetry spans when the optional extra is installed."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise RuntimeError("Install the observability extra: pip install 'agent-evaluation-safety-harness[observability]'") from exc
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("agent_harness", "1.0.0")
    count = 0
    with tracer.start_as_current_span("evaluation.run") as run_span:
        run_span.set_attribute("evaluation.suite", report.get("suite_name", ""))
        for result in report.get("results", []):
            with tracer.start_as_current_span("evaluation.case") as case_span:
                case_span.set_attribute("case.id", result.get("case_id", ""))
                case_span.set_attribute("case.passed", bool(result.get("passed")))
                case_span.set_attribute("case.risk", float(result.get("risk_score", 0)))
                for step in result.get("trace", []):
                    with tracer.start_as_current_span(f"agent.{step.get('type', 'step')}") as step_span:
                        step_span.set_attribute("step.name", str(step.get("name", "")))
                        step_span.set_attribute("step.status", str(step.get("status", "")))
                        count += 1
    provider.shutdown()
    return count


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in REDACTIONS:
            value = pattern.sub("[REDACTED]", value)
        return value
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.casefold() in {"authorization", "api_key", "token", "secret"} else redact_value(item) for key, item in value.items()}
    return value
