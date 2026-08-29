from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .adapters import AgentAdapter, EchoAdapter, HttpAdapter, RecordedAdapter, ResilientAdapter
from .calibration import calibrate_judge
from .dashboard import write_regression_dashboard
from .demo_agent import SupportAgentAdapter
from .engine import EvaluationEngine
from .experiment import ExperimentConfig, run_experiment
from .forensics import compare_reports, write_comparison
from .judge import judge_report
from .loaders import SuiteValidationError, load_suite
from .providers import OllamaChatAdapter, ProviderWorkflowAdapter
from .redteam import generate_redteam
from .replay import replay_policy
from .reporting import write_html_report, write_json_report
from .review import apply_review, promote_reviewed_cases, write_review_queue
from .server import serve_dashboard
from .store import RunStore
from .telemetry import export_open_telemetry, write_jsonl_trace
from .workflows import WorkflowAgentAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-harness", description="Evaluate AI agents for quality and safety.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Run an evaluation suite")
    run.add_argument("suite", help="Path to a JSON evaluation suite")
    _add_target_arguments(run)
    run.add_argument("--json", dest="json_path", default="report.json", help="JSON report path")
    run.add_argument("--html", dest="html_path", help="Self-contained HTML report path")
    run.add_argument("--review-queue", help="Write failed/ambiguous cases to this JSON file")
    run.add_argument("--label", help="Human-readable run label used by dashboards")
    run.add_argument("--db", help="Persist this run and its review items to SQLite")
    run.add_argument("--jsonl-trace", help="Append redacted step events to a JSONL file")
    run.add_argument("--otel", action="store_true", help="Export the completed run through OpenTelemetry OTLP")
    run.add_argument("--no-fail", action="store_true", help="Always exit 0")

    dashboard = commands.add_parser("dashboard", help="Compare multiple evaluation reports")
    dashboard.add_argument("reports", nargs="+", help="JSON report files in chronological order")
    dashboard.add_argument("--output", default="dashboard.html", help="Dashboard output path")

    review = commands.add_parser("review", help="Record a human decision for a queued case")
    review.add_argument("queue", help="Review queue JSON path")
    review.add_argument("case_id", help="Case to review")
    review.add_argument("--decision", choices=("pass", "fail", "ambiguous"), required=True)
    review.add_argument("--notes", default="")
    review.add_argument("--reviewer", default=os.environ.get("USER", "human"))

    compare = commands.add_parser("compare", help="Find the first trace divergence between two runs")
    compare.add_argument("baseline", help="Baseline report JSON")
    compare.add_argument("candidate", help="Candidate report JSON")
    compare.add_argument("--json", dest="json_path", default="comparison.json")
    compare.add_argument("--html", dest="html_path")

    replay = commands.add_parser("replay", help="Counterfactually apply a policy to a saved report")
    replay.add_argument("report", help="Saved report JSON")
    replay.add_argument("policy", help="Policy JSON")
    replay.add_argument("--output", default="policy-replay.json")

    experiment = commands.add_parser("experiment", help="Run repeated concurrent trials with confidence intervals")
    experiment.add_argument("suite")
    _add_target_arguments(experiment)
    experiment.add_argument("--trials", type=int, default=3)
    experiment.add_argument("--workers", type=int, default=4)
    experiment.add_argument("--seed", type=int)
    experiment.add_argument("--output", default="experiment.json")

    serve = commands.add_parser("serve", help="Start the persistent dashboard and human-review API")
    serve.add_argument("--db", default="agent-harness.db")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--auth-token", help="Bearer token; defaults to AGENT_HARNESS_AUTH_TOKEN")

    judge = commands.add_parser("judge", help="Add optional semantic judge-model scores to a report")
    judge.add_argument("report")
    judge.add_argument("--model", default="gpt-5-mini")
    judge.add_argument("--output", default="judge-report.json")

    redteam = commands.add_parser("generate-redteam", help="Generate lineage-preserving adversarial cases from a suite or failed report")
    redteam.add_argument("source")
    redteam.add_argument("--variants", type=int, default=3)
    redteam.add_argument("--output", default="generated-redteam.json")

    promote = commands.add_parser("promote-reviews", help="Promote explicit human decisions into a regression suite")
    promote.add_argument("queue")
    promote.add_argument("--output", default="human-regressions.json")
    promote.add_argument("--suite-name", default="Human-reviewed regressions")

    calibrate = commands.add_parser("calibrate-judge", help="Calibrate a judge threshold against reviewed pass/fail labels")
    calibrate.add_argument("judge_report")
    calibrate.add_argument("reviews")
    calibrate.add_argument("--metric", default="task_completion")
    calibrate.add_argument("--output", default="judge-calibration.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "dashboard":
            write_regression_dashboard(args.reports, args.output)
            print(f"Dashboard: {args.output}")
            return 0
        if args.command == "review":
            item = apply_review(args.queue, args.case_id, args.decision, args.notes, args.reviewer)
            print(f"Reviewed {item['case_id']}: {item['decision']}")
            return 0
        if args.command == "compare":
            comparison = compare_reports(args.baseline, args.candidate)
            write_comparison(comparison, args.json_path, args.html_path)
            summary = comparison["summary"]
            print(f"Trace diff: {summary['fixed']} fixed, {summary['regressed']} regressed, {summary['still_failing']} still failing")
            print(f"Comparison: {args.json_path}")
            return 1 if summary["regressed"] else 0
        if args.command == "replay":
            replay = replay_policy(args.report, args.policy, args.output)
            summary = replay["summary"]
            print(f"Policy replay: {summary['pre_execution_blocks']} blocks, {summary['prevented_tool_calls']} tool calls prevented, {summary['human_routes']} human routes")
            print(f"Replay: {args.output}")
            return 0
        if args.command == "experiment":
            suite = load_suite(args.suite)
            artifact = run_experiment(suite, lambda _trial: _adapter_from_args(args), ExperimentConfig(args.trials, args.workers, args.seed))
            Path(args.output).write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
            stats = artifact["statistics"]
            print(f"Experiment: {stats['mean_pass_rate']:.0%} mean pass · 95% CI {stats['pass_rate_95ci']} · {len(stats['flaky_cases'])} flaky")
            print(f"Experiment report: {args.output}")
            return 0
        if args.command == "serve":
            serve_dashboard(args.db, args.host, args.port, args.auth_token)
            return 0
        if args.command == "judge":
            artifact = judge_report(args.report, args.output, args.model)
            print(f"Judged {len(artifact['cases'])} cases: {args.output}")
            return 0
        if args.command == "generate-redteam":
            generated_suite = generate_redteam(args.source, args.output, args.variants)
            print(f"Generated {len(generated_suite['cases'])} adversarial cases: {args.output}")
            return 0
        if args.command == "promote-reviews":
            count = promote_reviewed_cases(args.queue, args.output, args.suite_name)
            print(f"Promoted {count} reviewed cases: {args.output}")
            return 0
        if args.command == "calibrate-judge":
            artifact = calibrate_judge(args.judge_report, args.reviews, args.output, args.metric)
            print(f"Judge calibration: threshold {artifact['recommended_threshold']} · accuracy {artifact['accuracy']:.0%} · {args.output}")
            return 0
        return _run(args)
    except (SuiteValidationError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    adapter = _adapter_from_args(args)
    report = EvaluationEngine(adapter).run(suite)
    model_label = args.model or _default_model(args)
    report.metadata.update({"run_label": args.label or model_label, "harness_version": "1.0.0"})
    write_json_report(report, args.json_path)
    if args.html_path:
        write_html_report(report, args.html_path)
    if args.review_queue:
        review_count = write_review_queue(report, args.review_queue)
        print(f"Review queue: {args.review_queue} ({review_count} cases)")
    report_dict = report.to_dict()
    if args.db:
        run_id = RunStore(args.db).ingest_report(report_dict, args.label)
        print(f"Database run: {run_id}")
    if args.jsonl_trace:
        write_jsonl_trace(report_dict, args.jsonl_trace)
        print(f"JSONL trace: {args.jsonl_trace}")
    if args.otel:
        count = export_open_telemetry(report_dict)
        print(f"OpenTelemetry spans: {count}")

    summary = report.to_dict()["summary"]
    state = "PASS" if report.passed else "FAIL"
    print(f"{state}  {report.suite_name}  {summary['total']} cases  {summary['pass_rate']:.0%} passed  risk {summary['average_risk']:.0%}")
    print(f"JSON report: {args.json_path}")
    if args.html_path:
        print(f"HTML report: {args.html_path}")
    return 0 if report.passed or args.no_fail else 1


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--recorded", metavar="PATH", help="Use recorded responses from JSON")
    target.add_argument("--endpoint", metavar="URL", help="POST cases to an HTTP agent endpoint")
    target.add_argument("--demo-agent", action="store_true", help="Run the deterministic customer-support agent")
    target.add_argument("--workflow-agent", action="store_true", help="Run the deterministic cross-workflow sandbox agent")
    target.add_argument("--openai", action="store_true", help="Run a real OpenAI Responses API agent with isolated tools")
    target.add_argument("--anthropic", action="store_true", help="Run a real Anthropic Messages API agent with isolated tools")
    target.add_argument("--ollama", action="store_true", help="Run a local Ollama model")
    parser.add_argument("--model", help="Provider model ID or local version label")
    parser.add_argument("--header", action="append", default=[], metavar="NAME=VALUE", help="HTTP header; supports $ENV_VAR values")
    parser.add_argument("--requests-per-second", type=float, default=0.0, help="Maximum adapter invocations per second")
    parser.add_argument("--retries", type=int, default=2, help="Retries for rate limits and transient provider errors")


def _default_model(args: argparse.Namespace) -> str:
    if getattr(args, "openai", False):
        return "gpt-5-mini"
    if getattr(args, "anthropic", False):
        return "claude-sonnet-4-20250514"
    if getattr(args, "ollama", False):
        return "llama3.2"
    if getattr(args, "workflow_agent", False):
        return "workflow-agent-v1"
    return "support-agent-v2"


def _adapter_from_args(args: argparse.Namespace) -> AgentAdapter:
    model = args.model or _default_model(args)
    adapter: AgentAdapter
    if args.recorded:
        adapter = RecordedAdapter.from_file(args.recorded)
    elif args.endpoint:
        adapter = HttpAdapter(args.endpoint, headers=_parse_headers(args.header))
    elif args.demo_agent:
        adapter = SupportAgentAdapter(model)
    elif args.workflow_agent:
        adapter = WorkflowAgentAdapter(model)
    elif args.openai:
        adapter = ProviderWorkflowAdapter("openai", model)
    elif args.anthropic:
        adapter = ProviderWorkflowAdapter("anthropic", model)
    elif args.ollama:
        adapter = OllamaChatAdapter(model)
    else:
        adapter = EchoAdapter()
    return ResilientAdapter(adapter, args.requests_per_second, args.retries)


def _parse_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Invalid header '{item}'; expected NAME=VALUE")
        name, value = item.split("=", 1)
        if value.startswith("$"):
            env_name = value[1:]
            if env_name not in os.environ:
                raise ValueError(f"Environment variable '{env_name}' is not set")
            value = os.environ[env_name]
        headers[name] = value
    return headers


if __name__ == "__main__":
    raise SystemExit(main())
