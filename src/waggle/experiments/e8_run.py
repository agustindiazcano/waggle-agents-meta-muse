"""Cloud E8 measurements and reports from metadata-only llm_calls exports.

Run with ``uv run python -m waggle.experiments.e8_run --help``. No provider is called.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e1_rig import ControlRig, streams_for
from waggle.experiments.e8_export import CallDatabase, export_calls
from waggle.experiments.e8_extrapolation import extrapolate
from waggle.experiments.e8_metrics import latency_summary, summarize_calls
from waggle.llm.models import CallRecord, CallStatus
from waggle.sim import robots, scenarios

_CONFIG = "envelope_occlusion_cpa_lidar_beacons"
_SEED = 20261027
_FIELDS = {
    "request_id",
    "task_id",
    "role",
    "provider",
    "model_id",
    "status",
    "tokens_in",
    "tokens_out",
    "latency_s",
    "cost_usd",
    "fallback_label",
}


def measure_control(*, ticks: int, warmup_ticks: int) -> dict[str, object]:
    """Measure production control_step in S01; timers exclude sensor generation.

    This fixed synthetic benchmark uses no evaluation seed list. Warmup calls are discarded.
    """
    for value, low in ((ticks, 1), (warmup_ticks, 0)):
        if type(value) is not int or not low <= value <= 100_000:
            raise ValueError("ticks and warmup_ticks must be bounded integers")
    config = BY_NAME[_CONFIG]
    scenario = scenarios.generate("S01", _SEED)
    sim, _ = scenarios.build_engine(scenario, streams_for(config, len(scenario.robots)))
    fleet = robots.RobotFleet(
        [robot.kind for robot in scenario.robots],
        load_raised=[robot.load_raised for robot in scenario.robots],
    )
    rig = ControlRig(config, fleet, scenarios.load_map(scenario.map_name))
    sim.systems.insert(1, rig.system())
    sim.run(warmup_ticks)
    rig.tally.latency_us.clear()
    sim.run(ticks)
    samples = [value / 1_000_000 for value in rig.tally.latency_us]
    return {
        "configuration": _CONFIG,
        "scenario": "S01",
        "seed": _SEED,
        "robots": fleet.count,
        "ticks": ticks,
        "warmup_ticks": warmup_ticks,
        "control_calls": len(samples),
        "latency_s": latency_summary(samples),
        "scope": "code latency of production control_step inside the simulator; "
        "excludes sensor generation, simulator physics and networking; "
        "not a hardware real-time bound or a representative scenario sweep",
    }


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"invalid {name}")
    return value


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _count(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {name}")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"invalid {name}")
    return float(value)


def _record(raw: object) -> CallRecord:
    if not isinstance(raw, dict) or set(raw) != _FIELDS:
        raise ValueError("call record must contain exactly the metadata fields")
    status = raw["status"]
    if status not in ("ok", "error", "denied", "cached"):
        raise ValueError("invalid status")
    return CallRecord(
        request_id=_text(raw["request_id"], "request_id"),
        task_id=_optional_text(raw["task_id"], "task_id"),
        role=_text(raw["role"], "role"),
        provider=_text(raw["provider"], "provider"),
        model_id=_text(raw["model_id"], "model_id"),
        status=cast(CallStatus, status),
        tokens_in=_count(raw["tokens_in"], "tokens_in"),
        tokens_out=_count(raw["tokens_out"], "tokens_out"),
        latency_s=_number(raw["latency_s"], "latency_s"),
        cost_usd=_number(raw["cost_usd"], "cost_usd"),
        fallback_label=_optional_text(raw["fallback_label"], "fallback_label"),
    )


def load_calls(path: Path) -> tuple[list[CallRecord], dict[str, object]]:
    """Read strict metadata-only exports; reject absent provenance and empty samples."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "source",
        "mode",
        "commit",
        "prompt_versions",
        "records",
    }:
        raise ValueError("invalid call export fields")
    if raw["source"] != "llm_calls" or raw["mode"] not in ("mock", "http"):
        raise ValueError("source must be llm_calls with explicit mock or http mode")
    commit = _text(raw["commit"], "source commit")
    prompts = raw["prompt_versions"]
    if not isinstance(prompts, dict) or not prompts:
        raise ValueError("prompt_versions must be a nonempty object")
    versions = {_text(k, "prompt role"): _text(v, "prompt version") for k, v in prompts.items()}
    rows = raw["records"]
    if not isinstance(rows, list):
        raise ValueError("records must be a list")
    records = [_record(row) for row in rows]
    if not {record.role for record in records}.issubset(versions):
        raise ValueError("prompt_versions must cover every recorded role")
    summarize_calls(records)
    return records, {
        "source": "llm_calls",
        "mode": raw["mode"],
        "commit": commit,
        "prompt_versions": versions,
        "provenance": "caller-supplied metadata export; not independently authenticated",
    }


def _database_from_environ() -> CallDatabase:
    """Build the production database handle from DATABASE_URL, without logging it."""
    from waggle.db.connection import Database

    return Database.from_environ(os.environ)


def _prompt_versions(values: Sequence[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for value in values:
        role, separator, version = value.partition("=")
        if not separator or not role.strip() or not version.strip() or role in versions:
            raise ValueError("prompt versions must use ROLE=VERSION once per role")
        versions[role] = version
    return versions


def _commit() -> str:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git is required for result provenance")
    return subprocess.run(
        [git, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    """Write one E8 report exclusively; existing result files are never replaced."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fast = commands.add_parser("fast", help="measure the existing production control rig")
    fast.add_argument("--ticks", type=int, default=200)
    fast.add_argument("--warmup-ticks", type=int, default=20)
    export = commands.add_parser("export", help="export llm_calls metadata from the database")
    export.add_argument("--mode", choices=("mock", "http"), required=True)
    export.add_argument("--commit", required=True)
    export.add_argument("--prompt-version", action="append", required=True)
    export.add_argument(
        "--task-id",
        action="append",
        help="select a task from the source run; repeat for more tasks",
    )
    calls = commands.add_parser("calls", help="report a metadata-only llm_calls export")
    calls.add_argument("--input", type=Path, required=True)
    calls.add_argument("--fleet-size", type=int)
    calls.add_argument("--calls-per-robot", type=int, default=1)
    calls.add_argument("--concurrency", type=int, default=10)
    calls.add_argument("--seed", type=int, default=0)
    for command in (fast, calls, export):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.command == "export":
        export_calls(
            _database_from_environ(),
            mode=args.mode,
            commit=args.commit,
            prompt_versions=_prompt_versions(args.prompt_version),
            output=args.output,
            task_ids=args.task_id,
        )
        return 0
    report: dict[str, object] = {
        "experiment": "e8",
        "seed_set": "benchmark",
        "commit": _commit(),
        "date": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "model_ids": [],
        "prompt_versions": {},
        "extrapolation": None,
    }
    if args.command == "fast":
        report["fast_layer"] = measure_control(ticks=args.ticks, warmup_ticks=args.warmup_ticks)
        report["llm_calls"] = None
    else:
        records, metadata = load_calls(args.input)
        report.update(source=metadata, llm_calls=summarize_calls(records), fast_layer=None)
        report["model_ids"] = sorted({record.model_id for record in records})
        report["prompt_versions"] = metadata["prompt_versions"]
        if args.fleet_size is not None:
            if len({(r.provider, r.model_id, r.role) for r in records}) != 1:
                raise ValueError("extrapolation requires one provider, model and role")
            attempts = [r for r in records if r.status in ("ok", "error")]
            if not attempts:
                raise ValueError("extrapolation requires attempted calls")
            measured = [r.latency_s for r in attempts if r.status == "ok"]
            report["extrapolation"] = extrapolate(
                measured,
                failure_rate=sum(r.status == "error" for r in attempts) / len(attempts),
                fleet_size=args.fleet_size,
                calls_per_robot=args.calls_per_robot,
                concurrency=args.concurrency,
                seed=args.seed,
            )
            report["extrapolation_calibration"] = {
                "attempted_rows": len(attempts),
                "error_rows": sum(r.status == "error" for r in attempts),
                "latency_rows": len(measured),
                "note": "Error latency is unmeasured by the production client. "
                "Failed-call durations use the successful-call empirical distribution. "
                "Call rows and repeats are not independent experimental samples.",
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
