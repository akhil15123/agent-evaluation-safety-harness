from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class ToolPolicyError(RuntimeError):
    """Raised before a tool executes when its contract or policy is violated."""


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any], dict[str, Any]], Any]
    side_effect: str = "none"
    egress: bool = False
    requires_confirmation: bool = False

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }

    def anthropic_schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.parameters}


@dataclass(slots=True)
class ToolExecution:
    name: str
    arguments: dict[str, Any]
    output: Any
    status: str
    side_effect: str
    approved: bool
    blocked_reason: str | None = None
    canary_hits: list[str] = field(default_factory=list)

    def to_trace(self, step: int) -> dict[str, Any]:
        return {
            "step": step,
            "type": "tool",
            "name": self.name,
            "input": self.arguments,
            "output": self.output,
            "status": self.status,
            "side_effect": self.side_effect,
            "approved": self.approved,
            "blocked_reason": self.blocked_reason,
            "canary_hits": self.canary_hits,
        }


class ToolSandbox:
    """Contract-enforcing simulator that prevents unsafe tool effects before execution."""

    def __init__(
        self,
        tools: list[ToolSpec],
        *,
        state: dict[str, Any] | None = None,
        approvals: set[str] | None = None,
        canaries: list[str] | None = None,
    ):
        self.tools = {tool.name: tool for tool in tools}
        self.state = copy.deepcopy(state or {})
        self.approvals = approvals or set()
        self.canaries = canaries or []
        self.executions: list[ToolExecution] = []

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecution:
        spec = self.tools.get(name)
        if not spec:
            return self._blocked(name, arguments, "unknown_tool")
        try:
            validate_json_schema(arguments, spec.parameters)
        except ToolPolicyError as exc:
            return self._blocked(name, arguments, f"invalid_arguments: {exc}", spec)
        approved = not spec.requires_confirmation or name in self.approvals
        if not approved:
            return self._blocked(name, arguments, "human_confirmation_required", spec)
        serialized = json.dumps(arguments, sort_keys=True)
        canary_hits = [canary for canary in self.canaries if canary in serialized]
        if spec.egress and canary_hits:
            execution = self._blocked(name, arguments, "sensitive_canary_egress", spec)
            execution.canary_hits = canary_hits
            return execution
        output = spec.handler(arguments, self.state)
        execution = ToolExecution(name, arguments, output, "ok", spec.side_effect, approved)
        self.executions.append(execution)
        return execution

    def schemas(self, provider: str) -> list[dict[str, Any]]:
        if provider == "anthropic":
            return [tool.anthropic_schema() for tool in self.tools.values()]
        return [tool.openai_schema() for tool in self.tools.values()]

    def _blocked(self, name: str, arguments: dict[str, Any], reason: str, spec: ToolSpec | None = None) -> ToolExecution:
        execution = ToolExecution(name, arguments, {"error": reason}, "blocked", spec.side_effect if spec else "unknown", False, reason)
        self.executions.append(execution)
        return execution


def validate_json_schema(value: dict[str, Any], schema: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise ToolPolicyError("arguments must be an object")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [name for name in required if name not in value]
    if missing:
        raise ToolPolicyError(f"missing required fields: {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        unknown = set(value) - set(properties)
        if unknown:
            raise ToolPolicyError(f"unknown fields: {', '.join(sorted(unknown))}")
    for name, item in value.items():
        definition = properties.get(name, {})
        expected = definition.get("type")
        checks: dict[str, type | tuple[type, ...]] = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
        if expected in checks and not isinstance(item, checks[expected]):
            raise ToolPolicyError(f"'{name}' must be {expected}")
        if "enum" in definition and item not in definition["enum"]:
            raise ToolPolicyError(f"'{name}' must be one of {definition['enum']}")
        if isinstance(item, str) and definition.get("pattern") and not re.fullmatch(definition["pattern"], item):
            raise ToolPolicyError(f"'{name}' does not match its contract")


def object_schema(properties: dict[str, dict[str, Any]], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}
