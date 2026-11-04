"""E4 result record and its exclusive file (AGENTS.md 9.2 and 9.6, COURT_DESIGN section 8).

The record holds commit, seed set, realized model ids, prompt version and hash, date, realized
composition, fallback labels and ``held_out``. A scripted record carries the fixed scripted
warning: it checks arithmetic, it is not a model result. A live record carries the live
warning and its realized model ids. The file is created exclusively and an existing result
for the same configuration is never overwritten.
"""

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from waggle.experiments.e4_cases import SEED_SETS
from waggle.experiments.e4_configs import Configuration
from waggle.experiments.e4_correlation import error_correlation
from waggle.experiments.e4_metrics import (
    RunRecord,
    Summary,
    agreement,
    ambiguous_outcomes,
    escalation,
    false_approvals,
    false_blocks,
)
from waggle.experiments.e4_perf import cost_per_task, latency_per_model

SCHEMA_VERSION: Final = 1
WARNING: Final = (
    "SCRIPTED RUN. This file checks the harness arithmetic only (counts, intervals, correlation). "
    "It is not a model result and must never be reported as one."
)
PROVIDER_MODE: Final = "scripted"
LIVE_PROVIDER_MODE: Final = "live"
LIVE_WARNING: Final = (
    "LIVE RUN. Real provider calls on the declared routes with fallbacks disabled. "
    "Realized model ids and fallback labels are recorded per case."
)
_REPEAT_NOTE: Final = (
    "Repeats of one case are repeats, not independent samples. Case level counts are the "
    "independent unit."
)


class ResultExistsError(FileExistsError):
    """A result file for this configuration and seed set already exists."""


def result_path(out_dir: Path, config_name: str, seed_set: str) -> Path:
    """Path of the result file of one configuration on one seed set."""
    if seed_set not in SEED_SETS:
        raise ValueError(f"seed set must be one of {list(SEED_SETS)}")
    if not config_name or not all(c.isalnum() or c in "_-" for c in config_name):
        raise ValueError("configuration name must be alphanumeric, underscore or hyphen")
    return out_dir / f"e4_{config_name}_{seed_set}.json"


def _composition(runs: Sequence[RunRecord]) -> list[Summary]:
    return [
        {
            "case_id": run.case_id,
            "repeat": run.repeat,
            "request_suffix": f"-r{run.repeat}",
            "members": [
                {"role": v.role, "model_id": v.model_id, "fallback_label": v.fallback_label}
                for v in run.votes
            ],
        }
        for run in runs
    ]


def _model_ids(runs: Sequence[RunRecord]) -> dict[str, list[str]]:
    ids: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        for vote in run.votes:
            if vote.model_id:
                ids[vote.role].add(vote.model_id)
    return {role: sorted(values) for role, values in sorted(ids.items())}


def build_record(
    *,
    config: Configuration,
    seed_set: str,
    held_out: bool,
    commit: str,
    run_date: str,
    runs: Sequence[RunRecord],
    prompt_version: str,
    prompt_hash: str,
    provider_mode: str = PROVIDER_MODE,
) -> Summary:
    """Assemble the result record. Metrics follow the order of COURT_DESIGN section 8."""
    if provider_mode not in (PROVIDER_MODE, LIVE_PROVIDER_MODE):
        raise ValueError(f"unknown provider mode {provider_mode!r}")
    if seed_set not in SEED_SETS or held_out != (seed_set == "held_out"):
        raise ValueError("held_out must be true exactly for the held_out seed set")
    if not commit.strip() or not run_date.strip():
        raise ValueError("commit and run_date are required")
    approvals, blocks = false_approvals(runs), false_blocks(runs)
    return {
        "schema_version": SCHEMA_VERSION,
        "warning": WARNING if provider_mode == PROVIDER_MODE else LIVE_WARNING,
        "provider_mode": provider_mode,
        "configuration": {
            "name": config.name,
            "label": config.label,
            "roles": list(config.roles),
            "families": list(config.families),
            "court": config.court,
        },
        "seed_set": seed_set,
        "held_out": held_out,
        "commit": commit,
        "date": run_date,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "model_ids": _model_ids(runs),
        "fallback_labels": sorted(
            {v.fallback_label for r in runs for v in r.votes if v.fallback_label}
        ),
        "realized_composition": _composition(runs),
        "repeats": len({run.repeat for run in runs}),
        "repeat_note": _REPEAT_NOTE,
        "runs": len(runs),
        "failing_case_ids": {
            "false_approvals": approvals["case_ids"],
            "false_blocks": blocks["case_ids"],
        },
        "metrics": {
            "false_approvals": approvals,
            "false_blocks": blocks,
            "ambiguous": ambiguous_outcomes(runs),
            "escalation": escalation(runs),
            "agreement": agreement(runs),
            "error_correlation": error_correlation(runs, config),
            "latency": latency_per_model(runs),
            "cost": cost_per_task(runs),
        },
    }


def write_result(path: Path, record: Summary) -> None:
    """Create the result file exclusively. An existing file is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=False)
            handle.write("\n")
    except FileExistsError:
        raise ResultExistsError(f"{path.name} exists and is not overwritten") from None
