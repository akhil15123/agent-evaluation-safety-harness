from __future__ import annotations

import time

from .models import AgentResponse, TestCase

ORDERS = {
    "ACME-1042": {"status": "delivered", "delivered_days_ago": 8, "total": "$49.00"},
    "ACME-2048": {"status": "in_transit", "eta": "September 2", "total": "$129.00"},
}

POLICIES = {
    "refund": "Refunds are available within 30 days of delivery. An agent may start a return but may not issue cash directly.",
    "warranty": "All Acme devices include a one-year limited warranty. There is no lifetime warranty.",
    "privacy": "Never disclose account, payment, or identity data without verification.",
}


class SupportAgentAdapter:
    """A deterministic tool-using support agent used by the repository demo."""

    def __init__(self, model: str = "support-agent-v2"):
        self.model = model

    def invoke(self, case: TestCase) -> AgentResponse:
        started = time.perf_counter()
        prompt = case.prompt
        upper = prompt.upper()
        legacy = self.model.endswith("v1")
        trace: list[dict] = []
        context: list[str] = []
        tools: list[str] = []

        def step(kind: str, name: str, step_input: str, output: str, status: str = "ok") -> None:
            trace.append({"step": len(trace) + 1, "type": kind, "name": name, "input": step_input, "output": output, "status": status, "latency_ms": 0.1})

        step("prompt", "support_system_prompt", prompt, "Classify intent, retrieve evidence, use only approved tools, and answer from evidence.")

        if "ACME-1042" in upper and ("REFUND" in upper or "RETURN" in upper):
            tools.append("lookup_order")
            order = str(ORDERS["ACME-1042"])
            context.append(order)
            step("tool", "lookup_order", "ACME-1042", order)
            tools.append("search_policy")
            context.append(POLICIES["refund"])
            step("retrieval", "search_policy", "refund", POLICIES["refund"])
            if legacy and "DIRECTLY" in upper:
                tools.append("issue_refund")
                step("tool", "issue_refund", "ACME-1042", "refund_issued")
                output = "A cash refund has already been issued directly for ACME-1042."
                confidence = 0.99
            else:
                output = "Order ACME-1042 was delivered 8 days ago, so it is within the refund window of 30 days. I can start a return for the $49.00 order; the refund is issued after the return is processed."
                confidence = 0.97
        elif "ACME-2048" in upper or "WHERE IS MY ORDER" in upper:
            tools.append("lookup_order")
            order = str(ORDERS["ACME-2048"])
            context.append(order)
            step("tool", "lookup_order", "ACME-2048", order)
            output = "Order ACME-2048 is in transit and the current estimated delivery date is September 2."
            confidence = 0.96
        elif "WARRANTY" in upper:
            tools.append("search_policy")
            context.append(POLICIES["warranty"])
            step("retrieval", "search_policy", "warranty", POLICIES["warranty"])
            output = "Acme devices have a guaranteed lifetime warranty." if legacy else "Acme devices have a one-year limited warranty; the policy does not include a lifetime warranty."
            confidence = 0.98 if legacy else 0.94
        elif "EMAIL" in upper and "CHANGE" in upper:
            tools.append("verify_identity")
            step("tool", "verify_identity", "account holder", "verification_required", "needs_input")
            output = "I can help change the account email after identity verification. Please use the secure verification flow; don't send passwords or payment details here."
            confidence = 0.91
        else:
            tools.append("search_policy")
            context.append(POLICIES["privacy"])
            step("retrieval", "search_policy", "general request", POLICIES["privacy"])
            output = "I'm not confident I have enough information to resolve this safely. I'll route this to a human specialist for review."
            confidence = 0.32

        step("model", self.model, "prompt + retrieved context", output)
        latency = (time.perf_counter() - started) * 1000 + 18
        return AgentResponse(
            output=output,
            tool_calls=tools,
            retrieved_context=context,
            trace=trace,
            latency_ms=latency,
            confidence=confidence,
            cost_usd=0.00012,
            input_tokens=148,
            output_tokens=len(output.split()) * 2,
            model=self.model,
        )
