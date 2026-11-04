"""E5 experiment runner for safety advisors (ADVISORS_DESIGN sections 11 to 14).

Target layer: the fast-layer extra-cap input and the organizer boundary (AGENTS.md 9.4).
Implemented, not evaluated, on a scripted provider. The scripted answers prove nothing about
a real model.

Configurations:
- C0: Safety advisor off (fast layer alone).
- C1: Safety advisor on (scripted provider and recorded caution log).
- C1_REPLAY: Deterministic replay of the recorded caution log from C1.
Configurations C2, C3, and C4 require the organizer, which is not implemented, and are refused
with UnsupportedConfigurationError.
"""

import json
import logging
import math
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from waggle.experiments import e1_stats
from waggle.experiments.advisor_bridge import AdvisorBridge
from waggle.experiments.e1_config import BY_NAME, E1Config
from waggle.experiments.e1_rig import streams_for
from waggle.experiments.e5_rig import E5Rig
from waggle.governance.advisor_input import (
    AdvisorInputLimits,
    TrustedFacts,
)
from waggle.governance.caution import CautionConfig
from waggle.governance.caution_log import CautionLog
from waggle.governance.classifier import GuardClassifier, MockClassifier
from waggle.llm.advisor_runtime import (
    ADVISOR_PROMPT_HASH,
    ADVISOR_PROMPT_VERSION,
    AdvisorResult,
    AdvisorRuntime,
)
from waggle.llm.budget import PROVIDERS, BudgetGuard
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.errors import ProviderError
from waggle.llm.models import Completion, LlmRequest
from waggle.llm.providers import MockProvider, Provider, ScriptedProvider
from waggle.llm.routing import load_routes
from waggle.sim import robots, scenarios, world
from waggle.sim.params import DT, HUMAN_RADIUS

logger = logging.getLogger("waggle.experiments.e5")

SEEDS_PATH: Final = Path("data/seeds.json")
TARGET_LAYER: Final = "fast-layer extra-cap input and organizer boundary"
RUNNABLE_CONFIGS: Final = frozenset({"C0", "C1", "C1_REPLAY"})
ORGANIZER_CONFIGS: Final = frozenset({"C2", "C3", "C4"})
VALID_NONE_JSON: Final = '{"action":"none","speed_cap":null,"duration_ticks":null,"code":null}'
_MODEL_ENV: Final[dict[str, str]] = {
    "META_MODEL_ID": "meta-model",
    "META_VOICE_MODEL_ID": "meta-voice",
    "BASETEN_MODEL_ID": "baseten-model",
    "MODAL_GLIMMER_MODEL_ID": "modal-glimmer",
    "MODAL_SPARK_OPEN_MODEL_ID": "modal-spark",
    "VERTEX_MODEL_ID": "vertex-model",
}

REQUIRED_RESULT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "commit",
        "seed_set",
        "configuration_id",
        "prompt_version",
        "prompt_hash",
        "provider_mode",
        "fallback_flag",
        "event_log_digest",
        "per_seed_outcomes",
        "rejected_counts_by_reason",
        "call_counts",
        "date",
    }
)


class UnsupportedConfigurationError(ValueError):
    """Raised when a requested configuration requires unimplemented components (e.g. C2-C4)."""


class ResultValidationError(ValueError):
    """Raised when a result document is missing required fields or has invalid fields."""


@dataclass(frozen=True)
class RunSpec:
    """Specification of one E5 experiment run."""

    config: str
    scenario: str
    seed: int
    provider_script: Mapping[str, Any] | str | ScriptedProvider | None = None
    replay_log: str | None = None
    ticks: int | None = None
    failure_window: tuple[int, int] | None = None
    trigger_ticks: tuple[int, ...] | None = None


class _WindowFailingProvider:
    """Wraps a provider to simulate a forced outage window during [start_tick, end_tick)."""

    def __init__(
        self, inner: Provider, window: tuple[int, int] | None, get_tick: Callable[[], int]
    ) -> None:
        self._inner, self._window, self._get_tick = inner, window, get_tick
        self.name = inner.name

    def estimate_cost(self, request: LlmRequest) -> float:
        return self._inner.estimate_cost(request)

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        t = self._get_tick()
        if self._window is not None and self._window[0] <= t < self._window[1]:
            raise ProviderError(f"{self.name}: forced failure window at tick {t}")
        return self._inner.complete(request, model_id)


def _point_in_box(point: NDArray[np.float64], poly_obj: world.Polygon) -> bool:
    pts = np.asarray(poly_obj.points, dtype=np.float64)
    return bool(
        len(pts) >= 3
        and pts[:, 0].min() <= point[0] <= pts[:, 0].max()
        and pts[:, 1].min() <= point[1] <= pts[:, 1].max()
    )


def _extract_facts(
    sim: Any,
    robot_index: int,
    robot_id: str,
    scenario: scenarios.Scenario,
    box: world.World,
    last_reason: str | None,
) -> TrustedFacts:
    poses = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)
    speeds = np.asarray(sim.state.arrays["robot_speed"], dtype=np.float64)
    humans = np.asarray(sim.state.arrays["human_pos"], dtype=np.float64).reshape(-1, 2)
    pos = poses[robot_index, :2]
    h_min = float(np.min(np.hypot(*(humans - pos).T) - HUMAN_RADIUS)) if len(humans) else 99.0
    r_gaps = [
        float(np.hypot(*(poses[j, :2] - pos)))
        for j in range(len(scenario.robots))
        if j != robot_index
    ]
    nearest = max(0.0, round(min([h_min, *r_gaps]) if r_gaps else h_min, 2))
    zone_name = next(
        (z.id for z in box.zones if z.kind != "wall" and _point_in_box(pos, z.polygon)), "corridor"
    )
    return TrustedFacts(
        robot_id=robot_id,
        chassis=scenario.robots[robot_index].kind.value,
        speed=round(float(speeds[robot_index]), 2),
        active_reasons=(last_reason,) if last_reason is not None else ("REQUEST",),
        zone=zone_name,
        task_step="travel",
        nearest_distance=nearest,
        occluded=False,
        geofences=(),
        lease_holders=(),
    )


def _context_changed(current: TrustedFacts, last: TrustedFacts | None) -> bool:
    if last is None:
        return True
    if current.active_reasons != last.active_reasons:
        return True
    if current.zone != last.zone:
        return True
    return (current.nearest_distance < 3.0) != (last.nearest_distance < 3.0)


def _build_provider(spec: RunSpec, current_tick_holder: list[int]) -> Provider:
    raw = spec.provider_script
    inner: Provider
    if isinstance(raw, str):
        inner = ScriptedProvider("baseten", by_role={"advisor": raw})
    elif isinstance(raw, Mapping):
        by_role: dict[str, Any] = {}
        by_request: dict[str, Any] = {}
        if "by_role" in raw or "by_request" in raw:
            by_role = dict(raw.get("by_role", {}))
            by_request = dict(raw.get("by_request", {}))
        else:
            for k, v in raw.items():
                if k in ("advisor", "guard", "director", "court_1", "court_2", "court_3"):
                    by_role[k] = v
                else:
                    by_request[k] = v
        if "advisor" not in by_role and not by_request:
            by_role["advisor"] = VALID_NONE_JSON
        inner = ScriptedProvider("baseten", by_role=by_role, by_request=by_request)
    elif isinstance(raw, ScriptedProvider):
        inner = raw
    else:
        inner = ScriptedProvider("baseten", by_role={"advisor": VALID_NONE_JSON})

    if spec.failure_window is not None:
        return _WindowFailingProvider(inner, spec.failure_window, lambda: current_tick_holder[0])
    return inner


class E5Runner:
    """Configures and runs E5 experiment configurations (C0, C1, C1_REPLAY)."""

    def __init__(
        self,
        *,
        caution_config: CautionConfig,
        input_limits: AdvisorInputLimits,
        timeout_s: float,
        rate_limit_ticks: int,
        max_response_chars: int,
        classifier: GuardClassifier | None = None,
        base_config: E1Config | None = None,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        if rate_limit_ticks < 0:
            raise ValueError("rate_limit_ticks must be non-negative")
        if max_response_chars < 1:
            raise ValueError("max_response_chars must be positive")
        self.caution_config = caution_config
        self.input_limits = input_limits
        self.timeout_s = timeout_s
        self.rate_limit_ticks = rate_limit_ticks
        self.max_response_chars = max_response_chars
        self.classifier = classifier or MockClassifier(
            response='{"label":"benign","reason_code":"ok"}'
        )
        self.base_config = base_config or BY_NAME["envelope_occlusion_cpa_lidar_beacons"]

    def run_one(self, spec: RunSpec) -> dict[str, Any]:
        """Execute one E5 experiment run and return the run record."""
        # Validate scenario and seed
        seeds = dev_seeds(spec.scenario)
        if spec.seed not in seeds:
            raise ValueError(f"unknown seed {spec.seed} for scenario {spec.scenario}")

        # Refuse C2, C3, C4 or unknown configurations
        if spec.config in ORGANIZER_CONFIGS:
            raise UnsupportedConfigurationError(
                f"Configuration {spec.config} requires the organizer, which is not implemented"
            )
        if spec.config not in RUNNABLE_CONFIGS:
            raise UnsupportedConfigurationError(f"unknown configuration {spec.config}")

        scenario = scenarios.generate(spec.scenario, spec.seed)
        box = scenarios.load_map(scenario.map_name)
        robot_ids = tuple(f"robot-{i}" for i in range(len(scenario.robots)))

        caution_log: CautionLog
        bridge: AdvisorBridge | None = None
        runtime: AdvisorRuntime | None = None
        current_tick_holder = [0]
        advisor_calls = 0
        cautions_rejected: dict[str, int] = {}

        if spec.config == "C0":
            caution_log = CautionLog(self.caution_config)
        elif spec.config == "C1_REPLAY":
            if spec.replay_log is None:
                raise ValueError("C1_REPLAY requires replay_log")
            caution_log = CautionLog.from_jsonl(spec.replay_log, self.caution_config)
            bridge = AdvisorBridge(caution_log, robot_ids)
        else:
            caution_log = CautionLog(self.caution_config)
            bridge = AdvisorBridge(caution_log, robot_ids)
            provider = _build_provider(spec, current_tick_holder)
            call_log = InMemoryCallLog()
            guard = BudgetGuard({f"{p.upper()}_SPEND_CAP_USD": "10.0" for p in PROVIDERS}, call_log)
            client = LlmClient(
                providers={p: provider if p == "baseten" else MockProvider(p) for p in PROVIDERS},
                table=load_routes(),
                guard=guard,
                log=call_log,
                environ=_MODEL_ENV,
                fallbacks_enabled=False,
            )
            runtime = AdvisorRuntime(
                client=client,
                caution_log=caution_log,
                config=self.caution_config,
                timeout_s=self.timeout_s,
                max_response_chars=self.max_response_chars,
                rate_limit_ticks=self.rate_limit_ticks,
                classifier=self.classifier,
                input_limits=self.input_limits,
            )

        sim, det = scenarios.build_engine(
            scenario, streams_for(self.base_config, len(scenario.robots))
        )
        fleet = robots.RobotFleet(
            [r.kind for r in scenario.robots],
            load_raised=[r.load_raised for r in scenario.robots],
        )
        rig = E5Rig(self.base_config, fleet, box, advisor=bridge)
        sim.systems.insert(1, rig.system())

        total = scenario.duration_ticks if spec.ticks is None else spec.ticks
        distance = 0.0
        last_facts: list[TrustedFacts | None] = [None] * len(scenario.robots)

        for tick in range(total):
            current_tick_holder[0] = tick

            # Evaluate safety advisor for each robot if runtime is active
            if runtime is not None:
                for i in range(len(scenario.robots)):
                    facts = _extract_facts(sim, i, robot_ids[i], scenario, box, rig.last_reasons[i])
                    should_call = (
                        tick in spec.trigger_ticks
                        if spec.trigger_ticks is not None
                        else (tick == 0 or _context_changed(facts, last_facts[i]))
                    )
                    if should_call:
                        res: AdvisorResult = runtime.advise(
                            facts,
                            tick=tick,
                            current_cap=float(fleet.max_speed[i]),
                            class_max=float(fleet.max_speed[i]),
                            run_id=f"run-{spec.scenario}-{spec.seed}",
                            task_id=f"task-{robot_ids[i]}",
                            latency_ticks=0,
                        )
                        if res.status != "rate_limited":
                            advisor_calls += 1
                        if res.status == "rejected" and res.reason:
                            cautions_rejected[res.reason] = cautions_rejected.get(res.reason, 0) + 1
                        last_facts[i] = facts

            sim.step()
            distance += float(np.abs(np.asarray(sim.state.arrays["robot_speed"])).sum()) * DT

        tasks = int(np.asarray(sim.state.arrays["script_tasks"], dtype=np.int64).sum())
        counts = det.counts(sim.state)

        # Records and documents are JSON trees of mixed values, so dict[str, Any] is used for them.
        return {
            "scenario": spec.scenario,
            "seed": spec.seed,
            "config": spec.config,
            "robots": len(scenario.robots),
            "ticks": total,
            "tasks_completed": tasks,
            "counts": counts,
            "final_hash": sim.state_hash(),
            "distance_m": distance,
            "speed_sums": {
                "requested": rig.tally.requested_speed,
                "limited": rig.tally.limited_speed,
            },
            "stop_episodes": dict(sorted(rig.tally.stop_episodes.items())),
            "false_stops": rig.tally.false_stops,
            "min_separation_m": rig.min_separation_m,
            "widening_ticks": rig.widening_ticks,
            "cautions_issued": len(caution_log.events),
            "cautions_rejected": cautions_rejected,
            "advisor_calls": advisor_calls,
            "event_log_digest": caution_log.digest(),
            "caution_log_jsonl": caution_log.to_jsonl(),
        }


def run_one(
    spec: RunSpec,
    *,
    caution_config: CautionConfig,
    input_limits: AdvisorInputLimits,
    timeout_s: float,
    rate_limit_ticks: int,
    max_response_chars: int,
    classifier: GuardClassifier | None = None,
    base_config: E1Config | None = None,
) -> dict[str, Any]:
    """Module-level runner function running one spec."""
    runner = E5Runner(
        caution_config=caution_config,
        input_limits=input_limits,
        timeout_s=timeout_s,
        rate_limit_ticks=rate_limit_ticks,
        max_response_chars=max_response_chars,
        classifier=classifier,
        base_config=base_config,
    )
    return runner.run_one(spec)


def dev_seeds(scenario_id: str, seeds_path: Path = SEEDS_PATH) -> list[int]:
    """Return the development seeds for one scenario. Never reads held-out seeds."""
    dev = json.loads(seeds_path.read_text(encoding="utf-8"))["dev"]
    if scenario_id not in dev:
        raise ValueError(f"unknown scenario: {scenario_id}")
    return [int(s) for s in dev[scenario_id]]


def dev_pairs(scenario_ids: Sequence[str], seeds_path: Path = SEEDS_PATH) -> list[tuple[str, int]]:
    """Return (scenario, seed) pairs for development seeds. Never reads held-out seeds."""
    dev = json.loads(seeds_path.read_text(encoding="utf-8"))["dev"]
    for sid in scenario_ids:
        if sid not in dev:
            raise ValueError(f"unknown scenario: {sid}")
    return [(sid, int(s)) for sid in scenario_ids for s in dev[sid]]


def _commit() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        out = subprocess.run(
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def validate_result_document(doc: Mapping[str, Any]) -> None:
    """Validate that the result document has all required fields and valid types."""
    missing = REQUIRED_RESULT_FIELDS - set(doc)
    if missing:
        raise ResultValidationError(f"missing required field: {sorted(missing)}")
    if doc["seed_set"] != "dev":
        raise ResultValidationError("seed_set must be 'dev'")
    if doc["provider_mode"] != "mock":
        raise ResultValidationError("provider_mode must be 'mock'")
    if not isinstance(doc["date"], str) or len(doc["date"]) < 10:
        raise ResultValidationError("date must be an ISO timestamp string")
    if not isinstance(doc["event_log_digest"], str):
        raise ResultValidationError("event_log_digest must be a string")


def write_result_file(path: Path, document: Mapping[str, Any]) -> None:
    """Validate and write the result document to ``path``. Nothing is written when it is invalid."""
    validate_result_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def assemble(
    config: str,
    runs: Sequence[dict[str, Any]],
    *,
    event_log_digest: str,
    rejected_counts: Mapping[str, int],
    call_counts: int,
    failure_window: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Assemble individual run records into a complete result document."""
    # Records and documents are JSON trees of mixed values, so dict[str, Any] is used for them.
    failing = [
        {"scenario": r["scenario"], "seed": r["seed"]}
        for r in runs
        if r["counts"]["human_collisions"] or r["counts"]["robot_collisions"]
    ]
    proportions: dict[str, Any] = {}
    n = len(runs)
    for k in ("human_collisions", "robot_collisions", "separation_violations", "near_misses"):
        hits = sum(1 for r in runs if r["counts"][k] > 0)
        low, high = e1_stats.wilson(hits, n)
        prop: dict[str, Any] = {
            "hits": hits,
            "total": n,
            "wilson95_low": low,
            "wilson95_high": high,
        }
        if n < 30:
            prop["small_sample"] = True
        proportions[k] = prop

    return {
        "experiment": "e5",
        "target_layer": TARGET_LAYER,
        "configuration_id": config,
        "seed_set": "dev",
        "commit": _commit(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "prompt_version": ADVISOR_PROMPT_VERSION,
        "prompt_hash": ADVISOR_PROMPT_HASH,
        "provider_mode": "mock",
        "fallback_flag": False,
        "event_log_digest": event_log_digest,
        "forced_failure_window": list(failure_window) if failure_window else None,
        "rejected_counts_by_reason": dict(rejected_counts),
        "call_counts": call_counts,
        "widening_ticks_total": sum(r["widening_ticks"] for r in runs),
        "failing_seeds": sorted(failing, key=lambda f: (f["scenario"], f["seed"])),
        "proportions": proportions,
        "per_seed_outcomes": list(runs),
        "notes": (
            "Target layer declared before runs: fast-layer extra-cap input and organizer "
            "boundary. Implemented, not evaluated, on a scripted provider. Scripted answers "
            "prove nothing about a real model."
        ),
    }
