"""E10 result record and its exclusive file (AGENTS.md 9.2, 9.5 and 9.6).

Every record built here comes from the scripted harness and carries a fixed warning:
it checks harness arithmetic, it is not a model result. The file is created
exclusively and an existing result for the same configuration is never overwritten.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from waggle.experiments.e1_stats import wilson
from waggle.experiments.e10_configs import Configuration

SCHEMA_VERSION: Final = 1
WARNING: Final = (
    "SCRIPTED RUN. This file checks the harness arithmetic only (counts, intervals). "
    "It is not a model result and must never be reported as one."
)
PROVIDER_MODE: Final = "scripted"
SEED_SETS: Final = ("development", "held_out")


class ResultExistsError(FileExistsError):
    """A result file for this configuration and seed set already exists."""


@dataclass(frozen=True)
class RunRecord:
    """One template run in one configuration."""

    template_id: str
    seed: int
    status: str
    rounds: int
    calls: int
    cost_usd: float
    counterexamples: int
    outcomes: tuple[str, ...]


def result_path(out_dir: Path, config_name: str, seed_set: str) -> Path:
    """Path of the result file of one configuration on one seed set."""
    if seed_set not in SEED_SETS:
        raise ValueError(f"seed set must be one of {list(SEED_SETS)}")
    if not config_name or not all(c.isalnum() or c in "_-" for c in config_name):
        raise ValueError("configuration name must be alphanumeric, underscore or hyphen")
    return out_dir / f"e10_{config_name}_{seed_set}.json"


def build_record(
    *,
    config: Configuration,
    seed_set: str,
    commit: str,
    run_date: str,
    runs: Sequence[RunRecord],
    prompt_version: str,
) -> dict[str, object]:
    """Assemble the result record with Wilson interval and failing seeds listed."""
    if seed_set not in SEED_SETS:
        raise ValueError(f"seed set must be one of {list(SEED_SETS)}")
    if not commit.strip() or not run_date.strip():
        raise ValueError("commit and run_date are required")
    accepted = sum(1 for r in runs if r.status == "accepted")
    low, high = wilson(accepted, len(runs))
    return {
        "schema_version": SCHEMA_VERSION,
        "warning": WARNING,
        "provider_mode": PROVIDER_MODE,
        "configuration": {
            "name": config.name,
            "label": config.label,
            "uses_llm": config.uses_llm,
            "max_rounds": config.max_rounds,
        },
        "seed_set": seed_set,
        "held_out": seed_set == "held_out",
        "commit": commit,
        "date": run_date,
        "prompt_version": prompt_version,
        "model_ids": {"planner": ["scripted-meta-wonder"]} if config.uses_llm else {},
        "runs": len(runs),
        "failing_seeds": [r.seed for r in runs if r.status != "accepted"],
        "metrics": {
            "accepted": {"count": accepted, "total": len(runs), "wilson95": [low, high]},
            "escalations": sum(1 for r in runs if r.status == "escalated"),
            "counterexamples": sum(r.counterexamples for r in runs),
            "calls": sum(r.calls for r in runs),
            "cost_usd": round(sum(r.cost_usd for r in runs), 6),
            "rounds": sum(r.rounds for r in runs),
        },
        "records": [
            {
                "template_id": r.template_id,
                "seed": r.seed,
                "status": r.status,
                "rounds": r.rounds,
                "calls": r.calls,
                "cost_usd": r.cost_usd,
                "counterexamples": r.counterexamples,
                "outcomes": list(r.outcomes),
            }
            for r in runs
        ],
        "notes": [
            "Small sample: templates are fixtures on development seeds, not independent layouts.",
            "No court configuration: no existing interface reviews a plan.",
            "Accepted plans are not executed here; the extended rollout metric is not measured.",
        ],
    }


def write_result(path: Path, record: dict[str, object]) -> None:
    """Create the result file exclusively. An existing file is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
    except FileExistsError:
        raise ResultExistsError(f"{path.name} exists and is not overwritten") from None
