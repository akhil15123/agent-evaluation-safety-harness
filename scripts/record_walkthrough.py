from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
CAST = ROOT / "docs/walkthrough/agent-harness.cast"
TRANSCRIPT = ROOT / "docs/walkthrough/transcript.txt"

COMMANDS = [
    ["agent-harness", "run", "examples/workflows-suite.json", "--workflow-agent", "--json", "/tmp/walkthrough-report.json", "--db", "/tmp/walkthrough.db", "--jsonl-trace", "/tmp/walkthrough.jsonl"],
    ["agent-harness", "experiment", "examples/workflows-suite.json", "--workflow-agent", "--trials", "3", "--workers", "3", "--seed", "42", "--output", "/tmp/walkthrough-experiment.json"],
    ["agent-harness", "compare", "docs/runs/baseline-v1.json", "docs/runs/guardrailed-v2.json", "--json", "/tmp/walkthrough-comparison.json"],
    ["agent-harness", "replay", "docs/runs/baseline-v1.json", "examples/strict-policy.json", "--output", "/tmp/walkthrough-replay.json"],
]


def main() -> int:
    env = {**os.environ, "PATH": f"{ROOT / '.venv/bin'}:{os.environ.get('PATH', '')}"}
    events: list[list[object]] = []
    transcript: list[str] = []
    clock = 0.5
    events.append([clock, "o", "\x1b[1;34mAGENT HARNESS v1.0 — real evaluation walkthrough\x1b[0m\r\n\r\n"])
    for command in COMMANDS:
        display = "$ " + " ".join(command)
        transcript.append(display)
        for chunk in _chunks(display, 5):
            clock += 0.035
            events.append([clock, "o", chunk])
        clock += 0.1
        events.append([clock, "o", "\r\n"])
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
        output = completed.stdout + completed.stderr
        elapsed = time.perf_counter() - started
        transcript.append(output.rstrip())
        for line in output.splitlines():
            clock += 0.2
            color = "\x1b[31m" if line.startswith(("FAIL", "error:")) else "\x1b[32m" if line.startswith(("PASS", "Experiment", "Trace diff", "Policy replay")) else "\x1b[37m"
            events.append([clock, "o", f"{color}{line}\x1b[0m\r\n"])
        clock += min(1.2, max(0.4, elapsed / 4))
        events.append([clock, "o", "\r\n"])
        if completed.returncode:
            return completed.returncode
    events.append([clock + 0.4, "o", "\x1b[1;36mEvidence complete: trace → capsule → mitigation → replay → proof\x1b[0m\r\n"])
    header = {"version": 2, "width": 118, "height": 28, "timestamp": int(time.time()), "env": {"SHELL": "/bin/zsh", "TERM": "xterm-256color"}, "title": "Agent Harness v1.0 walkthrough"}
    CAST.write_text(json.dumps(header) + "\n" + "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    TRANSCRIPT.write_text("\n\n".join(transcript) + "\n", encoding="utf-8")
    print(f"Recorded {CAST}")
    return 0


def _chunks(value: str, size: int) -> list[str]:
    return [value[index:index + size] for index in range(0, len(value), size)]


if __name__ == "__main__":
    sys.exit(main())
