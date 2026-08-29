# Technical writeup: Agent Evaluation + Safety Harness

## Problem and design goals

Tool-using agents fail differently from ordinary text generators. A response can read well while relying on invented evidence, calling the wrong tool, leaking customer data, or obeying an instruction hidden in retrieved content. A useful release gate therefore needs to inspect both the final answer and the path taken to produce it. It also needs to be cheap enough to run on every pull request, reproducible enough to debug, and explicit enough that a reviewer can challenge each judgment.

Agent Harness is built around those constraints. It treats an evaluation as a versioned dataset plus a policy, runs each case through an adapter, captures a structured execution trace, applies deterministic evaluators, and produces a decision with evidence. The reference customer-support workflow is intentionally offline and deterministic. It demonstrates the system without an API key, keeps CI stable, and makes regressions attributable to code or policy changes instead of model sampling noise.

The main design goals are: realistic multi-step evaluation; adversarial coverage; transparent metrics; defense in depth; useful failure artifacts; and low integration cost. Its differentiating abstraction is the **evidence capsule**: a failed or uncertain trace is preserved as a portable forensic object that can be compared and replayed rather than disappearing into a dashboard aggregate. Non-goals for this first version include a hosted service, semantic judge models, distributed execution, and automatic prompt optimization.

## System architecture

An evaluation suite is a JSON document containing test cases and a safety policy. Each case has a prompt, tags, quality expectations, expected tools, grounded facts, forbidden claims, and optional metadata. Tags are descriptive and allow future slice analysis. Policy settings control input-injection behavior, secret and PII scanning, tool allowlists, denied phrases, output limits, the acceptable risk threshold, and low-confidence routing.

The engine first inspects input before agent execution. If a known prompt-injection pattern is found and the policy action is `block`, execution stops at the policy gate. The result contains a safe refusal and a trace entry recording the intervention. This placement matters: detecting a dangerous tool call after execution is too late. The output is still scanned independently because an agent can leak data or repeat injected instructions even when the original user prompt looked safe.

Adapters isolate the harness from agent implementations. `HttpAdapter` can call any service that accepts the documented JSON envelope. `RecordedAdapter` replays captured outputs for stable CI and regression reproduction. `SupportAgentAdapter` is the built-in realistic example: it classifies support intent, retrieves policy evidence, looks up an order, invokes identity verification, and routes uncertain work to a human. A Python protocol keeps it straightforward to add in-process adapters without coupling the engine to an SDK.

Each agent response may contain retrieved context, tool calls, confidence, model identifier, token counts, cost, and a chronological trace. Trace steps represent the original prompt, retrieval, tool input/output, model output, status, and latency. Failed calls are converted into failed case results rather than aborting the suite, which preserves evidence from the rest of a long run.

Failed and low-confidence results also receive a deterministic fingerprint, root-cause classification, first failed trace step, suggested mitigation, and minimal replay payload. This capsule connects evaluation to debugging: two reports can be aligned by case and inspected for the earliest changed guardrail, retrieval, tool, or model step. A separate policy replay applies new policy settings to the saved prompts, outputs, tools, and confidence values. Replay is counterfactual—it reports what a gate would block or route and never executes a tool—so teams can test a control against historical failures without model cost or side effects.

## Metrics and release decision

Task completion is the mean of declared answer checks: exact match, required phrase, regular expression, maximum length, and forbidden output. The suite uses deterministic checks because their pass criteria are reviewable in code and stable in CI. A production deployment can add a semantic judge as another check while retaining these hard assertions.

Groundedness is calculated over case-specific facts. A fact receives credit only when it appears in retrieved evidence and in the final answer. This is deliberately conservative and lexical; it is best suited to identifiers, dates, amounts, and policy terms. Tool correctness compares the expected and actual tool sets with a Jaccard-style overlap. Separately, the policy scanner assigns critical risk to any non-allowlisted tool, so an unexpected destructive tool cannot be hidden by an otherwise high overlap.

Hallucination rate is the fraction of declared false claims found in the answer. Refusal quality compares expected refusal behavior with common refusal markers. Safety pass is determined from independent-risk aggregation over findings. A single critical secret leak or unauthorized tool produces risk 1.0; multiple lower-severity findings accumulate without exceeding 1.0. The final case passes only if all hard checks pass, safety risk stays below threshold, tool correctness is perfect, and no known hallucination appears.

The report also aggregates latency and declared model cost. Those values do not currently fail the release gate, because acceptable budgets differ across environments, but they are displayed across runs so a team can make the tradeoff visible. Budget thresholds are a natural extension to the policy schema.

## Threat model and mitigations

The threat model includes direct prompt injection, accidental secret disclosure, common PII formats, disallowed content phrases, output flooding, unauthorized tool use, hallucinated policy, and overconfident action under ambiguity. The harness applies mitigations at three points.

Before execution, the injection gate can block common override and system-prompt extraction instructions. During execution, the agent is expected to expose tool calls and evidence; the policy evaluates the actual tools against an allowlist. After execution, scanners inspect output for secrets, PII, repeated injection language, denied phrases, and excessive length. Low-confidence responses are marked for human review even when their deterministic answer checks pass.

Evidence containing secrets is redacted before it enters a finding. HTTP authorization headers support environment-variable references and are not included in the trace. These choices reduce report-based leakage, but integrators must also scrub their own endpoint-provided traces. In production, input detection should be extended to retrieved documents, arguments should be validated per tool, and high-impact tools should require authorization or confirmation outside the model.

## Human review and regression workflow

Automated evaluation should expose uncertainty instead of laundering it into a binary score. The CLI writes failed and low-confidence cases into a JSON review queue. A reviewer records `pass`, `fail`, or `ambiguous`, free-form notes, identity, and timestamp while the original prompt, response, metrics, and failure reasons remain intact. These decisions can later become dataset labels or motivate a sharper deterministic check.

Every JSON report is self-describing and can be stored as a CI artifact. The regression dashboard consumes multiple reports in chronological order and compares pass rate, task completion, groundedness, tool correctness, hallucination, safety, cost, and latency across model or prompt labels. The included baseline `support-agent-v1` intentionally hallucinates a lifetime warranty and misuses a refund tool; `support-agent-v2` fixes both. That makes the demo a concrete release story rather than a static perfect score.

## Tradeoffs and next steps

The major tradeoff is transparency versus semantic coverage. Lexical checks are fast, explainable, and deterministic, but paraphrases can be missed and unsupported claims not listed in a trap can escape. Judge-model evaluators can improve recall but add cost, nondeterminism, and their own injection surface. The architecture supports both: hard policies should remain deterministic, while semantic judges can produce an additional scored signal with calibration examples.

Other next steps include concurrency with rate limiting, statistical confidence intervals over sampled generations, OpenTelemetry export, per-tag dashboards, tool-argument schemas, policy-as-code integrations, encrypted trace storage, and reviewer agreement metrics. A hosted mode could add authentication and team assignment while retaining the portable JSON artifacts as the underlying contract.

The key principle is that an agent should not ship because a handful of demos looked convincing. It should ship because representative and adversarial cases ran through the same observable path as production, failures were made inspectable, unsafe actions were blocked before execution, and a versioned report demonstrated that the candidate improved rather than regressed.

## v1.0 production extension

Version 1.0 moves the flight recorder from final-output evaluation to typed trajectory containment. Tool definitions use strict JSON-object contracts. Before a handler runs, `ToolSandbox` validates required and unknown fields, types, enums, and patterns; checks whether consequential writes have case-specific human approval; and searches egress arguments for seeded canary values. Each case receives a deep-copied domain state, so evaluation cannot mutate the fixture shared by later trials. Blocked calls remain visible in the trace and are scored as correct only when the case explicitly expected that intervention.

The cross-workflow suite now exercises email triage, calendar scheduling, workspace search, code review, recruiting, and customer support. Email and file content carry trust boundaries. Instruction-like content found in retrieved evidence creates an indirect-injection finding, while canary propagation into an egress tool becomes a critical exfiltration failure unless the sandbox blocked it before execution. Recruiting fixtures restrict selection to job-related skills and experience; calendar and code-review writes require confirmation.

Native provider adapters implement actual multi-step tool loops. OpenAI uses the Responses API in stateless mode: response items and encrypted reasoning content are replayed with function outputs while `store` remains false. Anthropic uses the Messages API's assistant `tool_use` and user `tool_result` content blocks. Ollama supports local chat inference. Provider headers are held only in request memory and redacted JSONL/OpenTelemetry exporters never serialize known authorization or token fields.

Repeated evaluation is an experiment, not a single score. Trials can execute concurrently with distinct seeds. The experiment artifact reports mean pass rate, trial standard deviation, a Wilson 95% interval over all case outcomes, p50 and p95 latency, total declared model cost, and cases whose binary outcome changed between trials. The checked-in OpenAI smoke experiment is a real three-trial provider run, while the deterministic cross-workflow suite makes CI reproducible without provider credentials.

SQLite provides schema-migrated local persistence for reports and review items. The web console exposes authenticated run and review APIs, filters runs, renders case traces, and writes decisions through optimistic version checks so concurrent reviewers cannot silently overwrite each other. The static HTML report remains available for CI artifacts; persistence is additive rather than mandatory.

Operational integrations include redacted JSONL events and optional OTLP trace export. Versioned JSON Schemas cover suites, policies, and reports. The container runs as an unprivileged user; Compose sets a read-only root filesystem and `no-new-privileges`. CI enforces lint, static typing, branch-aware coverage, schema validation, deterministic production gates, wheel/sdist builds, and container builds, while CodeQL and dependency audit run independently.

Counterfactual replay remains intentionally bounded. A saved trace can prove that a deterministic gate would match the recorded input, that a threshold would route the recorded confidence, or that a tool allowlist would reject the recorded call. It cannot prove the text a stochastic model would generate after its context or available tools changed. Such claims are marked as requiring a rerun rather than being converted into a false causal guarantee.
