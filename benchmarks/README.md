# Benchmarks

`provider-smoke.json` is the paid, native-provider integration gate. It executes two typed tool workflows and one injection case. Store sanitized reports under `docs/runs/`; never commit raw provider headers or unredacted production traces.

The repository's broader security suite is inspired by threat categories studied by AgentDojo, but it is **not an AgentDojo score**. To claim an AgentDojo result, run the upstream benchmark unchanged, pin its commit and model IDs, publish utility and attack-success metrics, and disclose every defense and refusal policy. This project does not manufacture cross-tool benchmark numbers from its own fixtures.

| Evidence | Runs | Report |
|---|---:|---|
| Deterministic workflow gate | 3+ trials | Mean, 95% Wilson CI, flaky cases |
| OpenAI provider smoke | 3+ trials | Model ID, tokens, latency, tool/argument correctness |
| Anthropic provider smoke | 3+ trials | Model ID, tokens, latency, tool/argument correctness |
| Upstream AgentDojo | Upstream protocol | Utility, attack success, defense configuration |
