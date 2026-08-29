from __future__ import annotations

import argparse
import os
import sys

from .adapters import EchoAdapter, HttpAdapter, RecordedAdapter
from .dashboard import write_regression_dashboard
from .demo_agent import SupportAgentAdapter
from .engine import EvaluationEngine
from .forensics import compare_reports, write_comparison
from .loaders import SuiteValidationError, load_suite
from .replay import replay_policy
from .reporting import write_html_report, write_json_report
from .review import apply_review, write_review_queue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-harness", description="Evaluate AI agents for quality and safety.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Run an evaluation suite")
    run.add_argument("suite", help="Path to a JSON evaluation suite")
    target = run.add_mutually_exclusive_group()
    target.add_argument("--recorded", metavar="PATH", help="Use recorded responses from JSON")
    target.add_argument("--endpoint", metavar="URL", help="POST cases to an HTTP agent endpoint")
    target.add_argument("--demo-agent", action="store_true", help="Run the built-in tool-using support agent")
    run.add_argument("--model", default="support-agent-v2", help="Model/version label for the demo agent")
    run.add_argument("--header", action="append", default=[], metavar="NAME=VALUE", help="HTTP header; supports $ENV_VAR values")
    run.add_argument("--json", dest="json_path", default="report.json", help="JSON report path")
    run.add_argument("--html", dest="html_path", help="Self-contained HTML report path")
    run.add_argument("--review-queue", help="Write failed/ambiguous cases to this JSON file")
    run.add_argument("--label", help="Human-readable run label used by dashboards")
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
        return _run(args)
    except (SuiteValidationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    if args.recorded:
        adapter = RecordedAdapter.from_file(args.recorded)
    elif args.endpoint:
        adapter = HttpAdapter(args.endpoint, headers=_parse_headers(args.header))
    elif args.demo_agent:
        adapter = SupportAgentAdapter(args.model)
    else:
        adapter = EchoAdapter()
    report = EvaluationEngine(adapter).run(suite)
    report.metadata.update({"run_label": args.label or args.model, "harness_version": "0.2.0"})
    write_json_report(report, args.json_path)
    if args.html_path:
        write_html_report(report, args.html_path)
    if args.review_queue:
        review_count = write_review_queue(report, args.review_queue)
        print(f"Review queue: {args.review_queue} ({review_count} cases)")

    summary = report.to_dict()["summary"]
    state = "PASS" if report.passed else "FAIL"
    print(f"{state}  {report.suite_name}  {summary['total']} cases  {summary['pass_rate']:.0%} passed  risk {summary['average_risk']:.0%}")
    print(f"JSON report: {args.json_path}")
    if args.html_path:
        print(f"HTML report: {args.html_path}")
    return 0 if report.passed or args.no_fail else 1


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
