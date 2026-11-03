"""E6 runner on the mock: predictive maintenance configurations B0, B1, C1, C2 and C3.

Design section 7 of docs/PREDICTIVE_MAINTENANCE_DESIGN.md. Development seeds only: the module
reads the ``dev`` list of ``data/seeds.json`` and has no option for any other set. One seed is
one machine, so the sample is the number of seeds and the intervals are wide. No model runs;
the tool calls go to an in-memory backend that is idempotent by key.

Truth and prediction stay apart (AGENTS.md 9.8). The telemetry comes from the simulator's
machine model (``waggle.sim.machines`` and ``telemetry``); the failure tick and onset tick go to
the scorer only. The predictor reads numbers and has its own parameter file, and
``check_parameter_separation`` refuses to run if the two files share a name or a value. The
threshold limits, persistence, lead target, stock and the synthetic failure log used for
diagnosis are assumptions of this runner, not tuned values and not measurements.

Not measured here: downtime and robots stopped before a hazard zone (no repair and no robots in
this loop), and any LLM step (sheet extraction and diagnosis are deterministic here).
"""

import argparse
import json
import math
import shutil
import statistics
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Final

from waggle.experiments.e1_stats import wilson
from waggle.experiments.failure_log import FailureCase, generate_failure_log
from waggle.maintenance.diagnosis import DiagnosisProposal, diagnose
from waggle.maintenance.loop import AlertPolicy, MaintenanceLoop, PartPlan
from waggle.maintenance.predictor import (
    Assessment,
    Predictor,
    Reading,
    default_params_path,
    load_params,
)
from waggle.maintenance.scoring import Outcome, score
from waggle.maintenance.sheet import ManualSheet, default_sheet, load_sheet
from waggle.maintenance.tool_port import McpToolPort, ToolCallDenied
from waggle.sim import machines, telemetry

ROOT: Final = Path(__file__).resolve().parents[3]
SEEDS_PATH: Final = ROOT / "data" / "seeds.json"
CONFIGS: Final = ("B0", "B1", "C1", "C2", "C3")
TARGET_LAYER: Final = "predictor, alert loop and catalog check"
HORIZON_S: Final = 3200
SMALL_SAMPLE: Final = 30
PERSISTENCE: Final = 5
LEAD_TARGET_TICKS: Final = 20000
WARN_LIMITS: Final = (45.0, 2.5, 6.0)
CRITICAL_LIMITS: Final = (65.0, 5.0, 8.0)
DIAGNOSIS_WINDOW: Final = 60
DIAGNOSIS_K: Final = 5
LOG_SEED: Final = 7
LOG_COUNT: Final = 300
CATALOG: Final = frozenset({"PART-BRG-01", "PART-LUB-01", "PART-ALN-01"})
STOCK: Final = {"PART-BRG-01": 1, "PART-LUB-01": 0, "PART-ALN-01": 1}
TECHNICIANS: Final = ("tech-1", "tech-2")
TRUE_PART: Final = {
    machines.BEARING: "PART-BRG-01",
    machines.LUBE: "PART-LUB-01",
    machines.OFFSET: "PART-ALN-01",
}
MODE_NAME: Final = {
    machines.BEARING: "BEARING_WEAR",
    machines.LUBE: "LUBRICATION_LOSS",
    machines.OFFSET: "MISALIGNMENT",
}
NOT_MEASURED: Final = ("downtime", "robots_stopped_before_hazard", "llm_steps")
REQUIRED_RESULT_FIELDS: Final = frozenset(
    {
        "experiment",
        "commit",
        "seed_set",
        "configuration_id",
        "model_ids",
        "prompt_versions",
        "date",
        "per_seed_outcomes",
        "counts",
        "proportions",
        "failing_seeds",
        "parameters",
        "telemetry_source",
        "not_measured",
    }
)

Assessor = Callable[[telemetry.TelemetrySample], Assessment]
AssessorFactory = Callable[[], Assessor]
Record = dict[str, Any]


class ResultValidationError(ValueError):
    """A result document is missing a required field or has an invalid one."""


@dataclass(frozen=True)
class Trace:
    """One machine's telemetry plus the truth, which only the scorer reads."""

    seed: int
    samples: tuple[telemetry.TelemetrySample, ...]
    mode: int
    onset_tick: int | None
    failure_tick: int | None


def dev_seeds(path: Path = SEEDS_PATH) -> list[int]:
    """Every development seed, sorted and unique. There is no other seed set here."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return sorted({int(s) for seeds in raw["dev"].values() for s in seeds})


def _flatten(tree: Mapping[str, Any], prefix: str = "") -> dict[str, float]:
    flat: dict[str, float] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        elif isinstance(value, int | float):
            flat[f"{prefix}{key}"] = float(value)
    return flat


def check_parameter_separation(
    sim_file: Path | None = None, predictor_file: Path | None = None
) -> None:
    """Raise ValueError if the two parameter files share a name or a numeric value."""
    sim = _flatten(json.loads((sim_file or machines.default_params_path()).read_text("utf-8")))
    pred = _flatten(json.loads((predictor_file or default_params_path()).read_text("utf-8")))
    names = {k.rsplit(".", 1)[-1] for k in sim} & {k.rsplit(".", 1)[-1] for k in pred}
    values = set(sim.values()) & set(pred.values())
    if names or values:
        raise ValueError("simulator and predictor parameters overlap")


def build_trace(
    seed: int,
    params: machines.DegradationParams | None = None,
    mode: int | None = None,
    horizon_s: int = HORIZON_S,
) -> Trace:
    """Run one simulated machine to its failure or the horizon and keep its telemetry."""
    sim = telemetry.build_engine(
        seed,
        1,
        params or machines.load_params(),
        telemetry.load_noise(),
        modes=None if mode is None else [mode],
    )
    samples: list[telemetry.TelemetrySample] = []
    failure: int | None = None
    for _ in range(int(horizon_s / machines.STEP_SECONDS)):
        sim.engine.run(machines.STRIDE_TICKS)
        samples.append(telemetry.read(sim)[0])
        truth = sim.engine.state.arrays
        if int(truth["machine_fail_tick"][0]) >= 0:
            failure = int(truth["machine_fail_tick"][0])
            break
    truth = sim.engine.state.arrays
    onset = int(truth["machine_onset_tick"][0])
    return Trace(
        seed,
        tuple(samples),
        int(truth["machine_mode"][0]),
        None if onset < 0 else onset,
        failure,
    )


class InMemoryBackend:
    """MCP-style tool backend for the mock: stock, tickets and technicians in memory.

    Idempotent by key unless ``idempotent`` is False, which exists to show that the duplicate
    metric would catch a backend that is not.
    """

    def __init__(self, stock: Mapping[str, int], idempotent: bool = True) -> None:
        self.stock = dict(stock)
        self._idempotent = idempotent
        self._seen: dict[tuple[str, str], object] = {}
        self._calls: dict[str, list[str]] = {"tickets": [], "reservations": [], "orders": []}
        self.log: list[tuple[str, dict[str, object]]] = []

    @property
    def created(self) -> dict[str, int]:
        """Entities created so far (a reservation counts only when granted)."""
        return {name: len(keys) for name, keys in self._calls.items()}

    def duplicates(self) -> int:
        """Creations beyond one per distinct key."""
        return sum(len(keys) - len(set(keys)) for keys in self._calls.values())

    def __call__(self, tool: str, arguments: dict[str, object]) -> object:
        """Serve one tool call. Raises ToolCallDenied for an unknown part or tool."""
        self.log.append((tool, dict(arguments)))
        key = str(arguments.get("idempotency_key", arguments.get("ticket_id", "")))
        if self._idempotent and (tool, key) in self._seen:
            return self._seen[(tool, key)]
        result = self._serve(tool, arguments, key)
        self._seen[(tool, key)] = result
        return result

    def _serve(self, tool: str, arguments: dict[str, object], key: str) -> object:
        if tool == "open_ticket":
            self._calls["tickets"].append(key)
            return {"ticket_id": f"tkt-{len(self._calls['tickets'])}", "created": True}
        if tool == "dispatch_tech":
            return {"dispatched": True}
        part, quantity = str(arguments.get("part_number")), int(str(arguments.get("quantity")))
        if tool not in {"reserve_part", "create_purchase_order"} or part not in self.stock:
            raise ToolCallDenied("not available")
        if tool == "create_purchase_order":
            self._calls["orders"].append(key)
            return {"ordered": True, "reason": "ok"}
        if self.stock[part] < quantity:
            return {"reserved": False, "reason": "insufficient"}
        self.stock[part] -= quantity
        self._calls["reservations"].append(key)
        return {"reserved": True, "reason": "ok"}


def is_wrong_part(mode: int | None, part_number: str | None) -> bool:
    """Whether an ordered part does not fit the true failing mode. No part is never wrong.

    A machine with no failing mode (healthy) has no right part, so any order for it is wrong.
    """
    if part_number is None:
        return False
    return mode is None or TRUE_PART[mode] != part_number


@cache
def _failure_log() -> tuple[FailureCase, ...]:
    return generate_failure_log(LOG_SEED, LOG_COUNT)


class _Plans(Mapping[str, PartPlan]):
    """Part plans resolved on first use from the sheet and a diagnosis of recent telemetry."""

    def __init__(self, sheet: ManualSheet, seen: list[telemetry.TelemetrySample]) -> None:
        self._sheet = sheet
        self._seen = seen
        self._plan: PartPlan | None = None
        self._resolved = False

    def _resolve(self) -> PartPlan | None:
        if not self._resolved:
            self._resolved = True
            self._plan = self._decide()
        return self._plan

    def _decide(self) -> PartPlan | None:
        if not self._sheet.parts:
            return None
        window = [
            s
            for s in self._seen[-DIAGNOSIS_WINDOW:]
            if all(math.isfinite(v) for v in (s.temperature, s.vibration, s.current))
        ]
        if not window:
            return None
        found = diagnose(
            _failure_log(),
            max(0.0, max(s.temperature for s in window)),
            max(0.0, max(s.vibration for s in window)),
            max(0.0, max(s.current for s in window)),
            CATALOG,
            DIAGNOSIS_K,
        )
        if not isinstance(found, DiagnosisProposal):
            return None
        plan = self._sheet.plan_for(found.mode, CATALOG)
        return plan if plan is not None and plan.part_number == found.part_number else None

    def get(self, key: str, default: PartPlan | None = None) -> PartPlan | None:  # type: ignore[override]  # lazy lookup
        """The single machine's plan, or the default when the sheet and diagnosis give none."""
        return self._resolve() or default

    def __getitem__(self, key: str) -> PartPlan:
        plan = self._resolve()
        if plan is None:
            raise KeyError(key)
        return plan

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


def _threshold_factory(limits: tuple[float, float, float]) -> AssessorFactory:
    def make() -> Assessor:
        def assess(s: telemetry.TelemetrySample) -> Assessment:
            values = (s.temperature, s.vibration, s.current)
            flag = any(v >= lim for v, lim in zip(values, limits, strict=True))
            return Assessment(
                s.machine_id, s.tick, True, True, flag, ("threshold",) if flag else (), None
            )

        return assess

    return make


def _predictor_factory() -> Assessor:
    predictor = Predictor(load_params())

    def assess(s: telemetry.TelemetrySample) -> Assessment:
        return predictor.update(
            Reading(s.machine_id, s.tick, s.temperature, s.vibration, s.current, s.load)
        )

    return assess


def _policy(config: str) -> AlertPolicy:
    if config in ("B0", "B1"):
        return AlertPolicy(persistence=1, lead_target_ticks=1, use_estimate=False)
    return AlertPolicy(PERSISTENCE, LEAD_TARGET_TICKS, use_estimate=config in ("C2", "C3"))


def _factory(config: str) -> AssessorFactory:
    if config == "B0":
        return _threshold_factory(CRITICAL_LIMITS)
    if config == "B1":
        return _threshold_factory(WARN_LIMITS)
    return _predictor_factory


def _sheet(config: str, name: str) -> ManualSheet:
    if config == "C3":
        return default_sheet(name)
    parts = {m: {"part_number": TRUE_PART[k], "quantity": 1} for k, m in MODE_NAME.items()}
    return load_sheet({"machine_id": name, "zone_id": "zone-m", "parts": parts})


def _held(s: telemetry.TelemetrySample) -> Assessment:
    return Assessment(s.machine_id, s.tick, False, False, False, (), None)


def run_trace(
    config: str,
    trace: Trace,
    assessor_factory: AssessorFactory | None = None,
    policy: AlertPolicy | None = None,
) -> Record:
    """Feed one trace through a configuration and score it against the truth.

    ``assessor_factory`` and ``policy`` replace the configuration's own, for tests.
    """
    if config not in CONFIGS:
        raise ValueError("unknown configuration")
    name = f"machine-{trace.seed}"
    backend = InMemoryBackend(STOCK)
    port = McpToolPort(backend, TECHNICIANS, lambda t: False)
    seen: list[telemetry.TelemetrySample] = []
    loop = MaintenanceLoop(
        policy or _policy(config), port, _Plans(_sheet(config, name), seen), lambda i: name
    )
    assess = (assessor_factory or _factory(config))()
    first_alert: int | None = None
    unscorable: list[int] = []
    for sample in trace.samples:
        if trace.failure_tick is not None and sample.tick > trace.failure_tick:
            break
        seen.append(sample)
        finite = all(
            math.isfinite(v)
            for v in (sample.temperature, sample.vibration, sample.current, sample.load)
        )
        if not finite:
            unscorable.append(sample.tick)
        step = loop.step(assess(sample) if finite else _held(sample))
        if first_alert is None and any(a.kind == "open_ticket" for a in step.actions):
            first_alert = sample.tick
    return _record(config, trace, backend, loop, first_alert, unscorable)


def _record(
    config: str,
    trace: Trace,
    backend: InMemoryBackend,
    loop: MaintenanceLoop,
    first_alert: int | None,
    unscorable: list[int],
) -> Record:
    scored = score(trace.failure_tick, first_alert, trace.onset_tick)
    outcome = scored.outcome.value
    if trace.failure_tick is None and trace.onset_tick is not None:
        outcome = "censored"
    stock_calls = [c for c in backend.log if c[0] in ("reserve_part", "create_purchase_order")]
    part = str(stock_calls[0][1]["part_number"]) if stock_calls else None
    truth_mode = trace.mode if trace.onset_tick is not None else None
    created = backend.created
    return {
        "seed": trace.seed,
        "configuration_id": config,
        "mode": MODE_NAME[trace.mode],
        "onset_tick": trace.onset_tick,
        "failure_tick": trace.failure_tick,
        "first_alert_tick": first_alert,
        "ticket_id": "tkt-1" if created["tickets"] else None,
        "part_number": part,
        "stock_action": (
            "reserved" if created["reservations"] else "ordered" if created["orders"] else None
        ),
        "wrong_part": is_wrong_part(truth_mode, part),
        "dispatched": loop.phase(0) == "done",
        "phase": loop.phase(0),
        "outcome": outcome,
        "lead_ticks": scored.lead_ticks,
        "detection_delay_ticks": scored.detection_delay_ticks,
        "held_readings": len(unscorable),
        "unscorable_ticks": unscorable,
        "tickets_created": created["tickets"],
        "reservations_created": created["reservations"],
        "orders_created": created["orders"],
        "duplicates": backend.duplicates(),
    }


def run_config(
    config: str, seeds: Sequence[int] | None = None, traces: Mapping[int, Trace] | None = None
) -> list[Record]:
    """Run one configuration over development seeds (all of them by default)."""
    check_parameter_separation()
    chosen = list(seeds) if seeds is not None else dev_seeds()
    allowed = set(dev_seeds())
    if not set(chosen) <= allowed:
        raise ValueError("only development seeds are allowed")
    return [
        run_trace(config, traces[s] if traces and s in traces else build_trace(s)) for s in chosen
    ]


def _proportion(hits: int, total: int) -> dict[str, Any]:
    low, high = wilson(hits, total)
    out: dict[str, Any] = {"hits": hits, "total": total, "wilson95_low": low, "wilson95_high": high}
    out["small_sample"] = total < SMALL_SAMPLE
    return out


def _summary(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def _commit() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        out = subprocess.run(
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


def assemble(config: str, records: Sequence[Record]) -> Record:
    """Build the result document from per-seed records: raw counts, Wilson intervals, seeds."""
    failing = [r for r in records if r["failure_tick"] is not None]
    healthy = [r for r in records if r["onset_tick"] is None]
    ticketed = [r for r in records if r["ticket_id"] is not None]
    ordered = [r for r in records if r["part_number"] is not None]
    outcomes = [r["outcome"] for r in records]
    false_alarms = sum(1 for r in healthy if r["ticket_id"] is not None)
    hours = len(healthy) * HORIZON_S / 3600.0
    counts: dict[str, Any] = {
        "seeds": len(records),
        "failures": len(failing),
        "healthy_machines": len(healthy),
        "healthy_machine_hours": hours,
        "false_alarms_per_100_machine_hours": (false_alarms / hours * 100.0) if hours else None,
        "outcomes": {o.value: outcomes.count(o.value) for o in Outcome}
        | {"censored": outcomes.count("censored")},
        "duplicates": sum(r["duplicates"] for r in records),
        "held_readings": sum(r["held_readings"] for r in records),
        "escalated": sum(1 for r in records if r["phase"] == "escalated"),
        "detection_delay_ticks": _summary(
            [r["detection_delay_ticks"] for r in failing if r["detection_delay_ticks"] is not None]
        ),
        "lead_ticks": _summary([r["lead_ticks"] for r in failing if r["lead_ticks"] is not None]),
    }
    proportions = {
        "detected": _proportion(sum(r["outcome"] == "detected" for r in failing), len(failing)),
        "missed": _proportion(sum(r["outcome"] == "missed" for r in failing), len(failing)),
        "false_alarm": _proportion(false_alarms, len(healthy)),
        "wrong_part_orders": _proportion(sum(r["wrong_part"] for r in ordered), len(ordered)),
        "dispatched": _proportion(sum(r["dispatched"] for r in ticketed), len(ticketed)),
    }
    return {
        "experiment": "e6",
        "target_layer": TARGET_LAYER,
        "configuration_id": config,
        "seed_set": "dev",
        "commit": _commit(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_ids": [],
        "prompt_versions": [],
        "telemetry_source": "waggle.sim.machines and waggle.sim.telemetry (one machine per seed)",
        "parameters": {
            "horizon_s": HORIZON_S,
            "persistence": PERSISTENCE,
            "lead_target_ticks": LEAD_TARGET_TICKS,
            "warn_limits": list(WARN_LIMITS),
            "critical_limits": list(CRITICAL_LIMITS),
            "diagnosis_k": DIAGNOSIS_K,
            "diagnosis_log": {"seed": LOG_SEED, "count": LOG_COUNT},
            "stock": dict(STOCK),
            "assumptions_untuned": True,
        },
        "per_seed_outcomes": list(records),
        "counts": counts,
        "proportions": proportions,
        "failing_seeds": [r["seed"] for r in records if r["outcome"] in ("missed", "false_alarm")],
        "not_measured": list(NOT_MEASURED),
    }


def validate_result_document(doc: Mapping[str, Any]) -> None:
    """Reject a document with a missing field, a non-development seed set or a bad date."""
    missing = REQUIRED_RESULT_FIELDS - set(doc)
    if missing:
        raise ResultValidationError(f"missing required field: {sorted(missing)}")
    if doc["seed_set"] != "dev":
        raise ResultValidationError("seed_set must be 'dev'")
    if doc["configuration_id"] not in CONFIGS:
        raise ResultValidationError("unknown configuration")
    if not isinstance(doc["date"], str) or len(doc["date"]) < 10:
        raise ResultValidationError("date must be an ISO timestamp string")


def write_result_file(path: Path, document: Mapping[str, Any]) -> None:
    """Validate and write the document. Nothing is written when it is invalid."""
    validate_result_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run configurations over development seeds and write one result file each."""
    parser = argparse.ArgumentParser(description="E6 mock runner (development seeds only)")
    parser.add_argument("--config", choices=[*CONFIGS, "all"], default="all")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "e6_dev")
    args = parser.parse_args(argv)
    chosen = CONFIGS if args.config == "all" else (args.config,)
    traces = {s: build_trace(s) for s in dev_seeds()}
    for config in chosen:
        doc = assemble(config, run_config(config, traces=traces))
        write_result_file(args.out / f"e6_{config}.json", doc)
        sys.stderr.write(f"wrote {args.out / f'e6_{config}.json'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
