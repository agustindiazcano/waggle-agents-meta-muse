"""Latency per model and cost per task from call log records (COURT_DESIGN sections 6 and 8).

Cost is the sum of ``cost_usd`` over rows with status ``ok`` and a ``court_*`` role, grouped by
run (``<case id>-r<repeat>``). Cached rows are excluded from cost and latency and counted apart.
Latency is the provider call latency recorded in the log, grouped by realized model id. Nothing
here estimates a price: a mock or scripted run has fixed fake costs and says nothing about the
real ones.
"""

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence

from waggle.experiments.e4_metrics import RunRecord, Summary
from waggle.llm.models import CallRecord


def _is_court(call: CallRecord) -> bool:
    return call.role.startswith("court_")


def run_key(run: RunRecord) -> str:
    """The task label of a run: the case id with its repeat number."""
    return f"{run.case_id}-r{run.repeat}"


def cost_per_task(runs: Sequence[RunRecord]) -> Summary:
    """Cost of the court calls per run, with cached and not-ok rows counted apart."""
    per_task: dict[str, float] = {}
    cached = not_ok = 0
    cached_cost = 0.0
    for run in runs:
        court_calls = [call for call in run.calls if _is_court(call)]
        per_task[run_key(run)] = math.fsum(c.cost_usd for c in court_calls if c.status == "ok")
        cached += sum(c.status == "cached" for c in court_calls)
        cached_cost += math.fsum(c.cost_usd for c in court_calls if c.status == "cached")
        not_ok += sum(c.status in ("error", "denied") for c in court_calls)
    total = math.fsum(per_task.values())
    return {
        "tasks": len(per_task),
        "per_task": per_task,
        "total_usd": total,
        "mean_usd": total / len(per_task) if per_task else None,
        "max_usd": max(per_task.values(), default=None),
        "cached_rows": cached,
        "cached_rows_excluded_cost_usd": cached_cost,
        "not_ok_rows": not_ok,
    }


def latency_per_model(runs: Sequence[RunRecord]) -> Summary:
    """Provider latency in seconds per realized model id, over ``ok`` rows only."""
    samples: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        for call in run.calls:
            if _is_court(call) and call.status == "ok":
                samples[call.model_id].append(call.latency_s)
    return {
        model: {
            "n": len(values),
            "median_s": statistics.median(values),
            "max_s": max(values),
            "mean_s": statistics.fmean(values),
        }
        for model, values in sorted(samples.items())
    }
