from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from .adapters import AgentAdapter
from .engine import EvaluationEngine
from .models import EvaluationSuite


@dataclass(slots=True)
class ExperimentConfig:
    trials: int = 3
    workers: int = 4
    seed: int | None = None


def run_experiment(suite: EvaluationSuite, adapter_factory: Callable[[int], AgentAdapter], config: ExperimentConfig) -> dict:
    if config.trials < 1:
        raise ValueError("trials must be at least 1")
    started = datetime.now(UTC).isoformat()
    reports: list[tuple[int, dict]] = []

    def run_trial(index: int) -> tuple[int, dict]:
        adapter = adapter_factory(index)
        report = EvaluationEngine(adapter).run(suite)
        report.metadata.update({"trial": index, "seed": config.seed + index if config.seed is not None else None})
        return index, report.to_dict()

    with ThreadPoolExecutor(max_workers=min(config.workers, config.trials)) as pool:
        futures = [pool.submit(run_trial, index) for index in range(config.trials)]
        for future in as_completed(futures):
            reports.append(future.result())
    reports.sort(key=lambda item: item[0])
    report_dicts = [item[1] for item in reports]
    pass_rates = [report["summary"]["pass_rate"] for report in report_dicts]
    all_results = [result for report in report_dicts for result in report["results"]]
    latencies = [float(result["latency_ms"]) for result in all_results]
    costs = [float(result.get("metrics", {}).get("cost_usd", 0)) for result in all_results]
    total_passes = sum(result["passed"] for result in all_results)
    low, high = wilson_interval(total_passes, len(all_results))
    case_outcomes: dict[str, set[bool]] = {}
    for result in all_results:
        case_outcomes.setdefault(result["case_id"], set()).add(bool(result["passed"]))
    return {
        "version": 1,
        "suite_name": suite.name,
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "config": {"trials": config.trials, "workers": config.workers, "seed": config.seed},
        "statistics": {
            "mean_pass_rate": round(statistics.mean(pass_rates), 4),
            "pass_rate_stdev": round(statistics.stdev(pass_rates), 4) if len(pass_rates) > 1 else 0.0,
            "pass_rate_95ci": [round(low, 4), round(high, 4)],
            "p50_latency_ms": round(percentile(latencies, 50), 2),
            "p95_latency_ms": round(percentile(latencies, 95), 2),
            "total_cost_usd": round(sum(costs), 6),
            "flaky_cases": sorted(case_id for case_id, outcomes in case_outcomes.items() if len(outcomes) > 1),
        },
        "trials": report_dicts,
    }


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * quantile / 100
    lower, upper = math.floor(rank), math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
