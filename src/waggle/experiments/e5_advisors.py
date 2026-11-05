"""E5 experiment runner for safety advisors (ADVISORS_DESIGN sections 11 to 14).

Target layer: the fast-layer extra-cap input and the organizer boundary (AGENTS.md 9.4).
Implemented, not evaluated, on a scripted provider. The scripted answers prove nothing about
a real model.

Configurations:
- C0: Safety advisor off, organizer off (fast layer alone).
- C1: Safety advisor on, organizer off (scripted provider and recorded caution log).
- C1_REPLAY: Deterministic replay of the recorded caution log from C1.
- C2: Safety advisor off, organizer on.
- C3: Safety advisor on, organizer on.
- C3_REPLAY: Deterministic replay of the recorded caution log from C3.
- C4: Both robot roles plus one fleet MOVE plan on explicitly supplied topology.
Non-MOVE actions, dependencies and lease-requiring routes are refused.
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

from waggle.experiments import e1_stats
from waggle.experiments.advisor_bridge import AdvisorBridge
from waggle.experiments.e1_config import BY_NAME, E1Config
from waggle.experiments.e1_rig import streams_for
from waggle.experiments.e5_caller import AdvisorCaller
from waggle.experiments.e5_fleet import (
    apply_fleet_plan,
    fleet_context,
    fleet_record,
    propose_fleet_plan,
)
from waggle.experiments.e5_rig import E5Rig
from waggle.governance.advisor_input import AdvisorInputLimits
from waggle.governance.caution import CautionConfig
from waggle.governance.caution_file import load_caution_log
from waggle.governance.caution_log import CautionLog
from waggle.governance.classifier import GuardClassifier, MockClassifier
from waggle.governance.organizer import OrganizerLimits
from waggle.llm.advisor_runtime import (
    ADVISOR_PROMPT_HASH,
    ADVISOR_PROMPT_VERSION,
    AdvisorRuntime,
)
from waggle.llm.budget import PROVIDERS, BudgetGuard
from waggle.llm.call_log import CallLog, InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.client_factory import build_client
from waggle.llm.errors import ConfigError, ProviderError
from waggle.llm.models import Completion, LlmRequest
from waggle.llm.organizer_runtime import McpToolDispatch, OrganizerRuntime
from waggle.llm.provider_config import select_mode
from waggle.llm.providers import MockProvider, Provider, ScriptedProvider
from waggle.llm.routing import load_routes
from waggle.sim import robots, scenarios
from waggle.sim.params import DT
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan_rollout import RolloutConfig

logger = logging.getLogger("waggle.experiments.e5")

SEEDS_PATH: Final = Path("data/seeds.json")
TARGET_LAYER: Final = "fast-layer extra-cap input and organizer boundary"
RUNNABLE_CONFIGS: Final = frozenset({"C0", "C1", "C1_REPLAY", "C2", "C3", "C3_REPLAY", "C4"})
REPLAY_CONFIGS: Final = frozenset({"C1_REPLAY", "C3_REPLAY"})
VALID_FLEET_JSON: Final = (
    '{"nodes":[],"rationale":"no scripted plan","escalate":true,'
    '"escalation_reason":"needs_operator"}'
)
VALID_NONE_JSON: Final = '{"action":"none","speed_cap":null,"duration_ticks":null,"code":null}'
VALID_ORGANIZER_NONE_JSON: Final = (
    '{"action":"none","duration_ticks":null,"tool":null,'
    '"arguments":null,"recipient":null,"status":null}'
)
_MODEL_ENV: Final[dict[str, str]] = {
    "META_MODEL_ID": "meta-model",
    "META_WONDER_MODEL_ID": "meta-wonder",
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
    """Raised for unknown configurations or missing fleet planning inputs."""


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
    replay_path: Path | None = None
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


def _build_provider(spec: RunSpec, current_tick_holder: list[int]) -> Provider:
    raw = spec.provider_script
    inner: Provider
    if isinstance(raw, str):
        inner = ScriptedProvider(
            "baseten",
            by_role={
                "advisor": raw,
                "organizer": VALID_ORGANIZER_NONE_JSON,
                "planner": VALID_FLEET_JSON,
            },
        )
    elif isinstance(raw, Mapping):
        by_role: dict[str, Any] = {}
        by_request: dict[str, Any] = {}
        if "by_role" in raw or "by_request" in raw:
            by_role = dict(raw.get("by_role", {}))
            by_request = dict(raw.get("by_request", {}))
        else:
            for k, v in raw.items():
                if k in (
                    "advisor",
                    "organizer",
                    "guard",
                    "director",
                    "planner",
                    "court_1",
                    "court_2",
                    "court_3",
                ):
                    by_role[k] = v
                else:
                    by_request[k] = v
        if "advisor" not in by_role and not by_request:
            by_role["advisor"] = VALID_NONE_JSON
        if "organizer" not in by_role and not by_request:
            by_role["organizer"] = VALID_ORGANIZER_NONE_JSON
        if "planner" not in by_role and not by_request:
            by_role["planner"] = VALID_FLEET_JSON
        inner = ScriptedProvider("baseten", by_role=by_role, by_request=by_request)
    elif isinstance(raw, ScriptedProvider):
        inner = raw
    else:
        inner = ScriptedProvider(
            "baseten",
            by_role={
                "advisor": VALID_NONE_JSON,
                "organizer": VALID_ORGANIZER_NONE_JSON,
                "planner": VALID_FLEET_JSON,
            },
        )

    if spec.failure_window is not None:
        return _WindowFailingProvider(inner, spec.failure_window, lambda: current_tick_holder[0])
    return inner


class E5Runner:
    """Run E5 configurations, including bounded MOVE-only C4 on supplied topology."""

    def __init__(
        self,
        *,
        caution_config: CautionConfig,
        input_limits: AdvisorInputLimits,
        timeout_s: float,
        rate_limit_ticks: int,
        max_response_chars: int,
        near_threshold_m: float,
        classifier: GuardClassifier | None = None,
        base_config: E1Config | None = None,
        client_environ: Mapping[str, str] | None = None,
        call_log: CallLog | None = None,
        organizer_limits: OrganizerLimits | None = None,
        tool_dispatch: McpToolDispatch | None = None,
        fleet_static: StaticMap | None = None,
        fleet_rollout: RolloutConfig | None = None,
    ) -> None:
        if not math.isfinite(near_threshold_m) or near_threshold_m <= 0.0:
            raise ValueError("near_threshold_m must be finite and positive")
        if call_log is not None and client_environ is None:
            raise ValueError("call_log needs client_environ: caps and model ids come from it")
        if client_environ is not None and select_mode(client_environ) != "mock":
            raise ConfigError("the E5 harness runs in mock mode only")
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
        self.near_threshold_m = near_threshold_m
        self._client_environ = client_environ
        self._call_log = call_log
        self.organizer_limits = organizer_limits or OrganizerLimits(
            max_prompt_chars=input_limits.max_prompt_chars,
            min_interval_ticks=max(1, rate_limit_ticks),
            max_turns_per_task=input_limits.max_calls_per_task,
            max_messages_per_task=input_limits.max_messages,
            max_identical_repeats=caution_config.n_max_holds,
            h_max_ticks=caution_config.h_max_ticks,
        )
        self._tool_dispatch = tool_dispatch
        self.fleet_static = fleet_static
        self.fleet_rollout = fleet_rollout

    def _make_client(self, provider: Provider) -> LlmClient:
        """Client over the scripted provider for the primary advisor route. Fallbacks are off.

        Without an injected environment the harness keeps its own in-memory log and fixed caps.
        With one, the client comes from ``build_client`` and the injected log (mock mode only).
        """
        table = load_routes()
        primary_names = {
            table.get("advisor").primary.provider,
            table.get("organizer").primary.provider,
            table.get("planner").primary.provider,
            provider.name,
        }
        override = {p: provider if p in primary_names else MockProvider(p) for p in PROVIDERS}
        if self._client_environ is not None:
            return build_client(
                self._client_environ,
                self._call_log if self._call_log is not None else InMemoryCallLog(),
                fallbacks_enabled=False,
                providers=override,
            )
        call_log = InMemoryCallLog()
        guard = BudgetGuard({f"{p.upper()}_SPEND_CAP_USD": "10.0" for p in PROVIDERS}, call_log)
        return LlmClient(
            providers=override,
            table=table,
            guard=guard,
            log=call_log,
            environ=_MODEL_ENV,
            fallbacks_enabled=False,
        )

    def _replay_log(self, spec: RunSpec) -> CautionLog:
        """The recorded log of a replay, from the text or from the file. Exactly one source."""
        if spec.replay_path is not None and spec.replay_log is None:
            return load_caution_log(spec.replay_path, self.caution_config)
        if spec.replay_log is not None and spec.replay_path is None:
            return CautionLog.from_jsonl(spec.replay_log, self.caution_config)
        raise ValueError("C1_REPLAY requires exactly one of replay_log and replay_path")

    def run_one(self, spec: RunSpec) -> dict[str, Any]:
        """Execute one E5 experiment run and return the run record."""
        # Validate scenario and seed
        seeds = dev_seeds(spec.scenario)
        if spec.seed not in seeds:
            raise ValueError(f"unknown seed {spec.seed} for scenario {spec.scenario}")

        if spec.config not in RUNNABLE_CONFIGS:
            raise UnsupportedConfigurationError(f"unknown configuration {spec.config}")

        scenario = scenarios.generate(spec.scenario, spec.seed)
        box = scenarios.load_map(scenario.map_name)
        robot_ids = tuple(f"robot-{i}" for i in range(len(scenario.robots)))
        fleet_result = None
        fleet_routes: dict[str, list[list[float]]] = {}
        if spec.config == "C4":
            if self.fleet_static is None or self.fleet_rollout is None:
                raise UnsupportedConfigurationError("C4 requires fleet topology and rollout policy")
            context = fleet_context(scenario, self.fleet_static, self.fleet_rollout)

        caution_log: CautionLog
        bridge: AdvisorBridge | None = None
        runtime: AdvisorRuntime | None = None
        org_runtime: OrganizerRuntime | None = None
        current_tick_holder = [0]

        if spec.config == "C0":
            caution_log = CautionLog(self.caution_config)
        elif spec.config in REPLAY_CONFIGS:
            caution_log = self._replay_log(spec)
            bridge = AdvisorBridge(caution_log, robot_ids)
        else:
            caution_log = CautionLog(self.caution_config)
            bridge = AdvisorBridge(caution_log, robot_ids)
            provider = _build_provider(spec, current_tick_holder)
            client = self._make_client(provider)
            if spec.config in ("C1", "C3", "C4"):
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
            if spec.config in ("C2", "C3", "C4"):
                org_runtime = OrganizerRuntime(
                    client=client,
                    caution_log=caution_log,
                    caution_config=self.caution_config,
                    limits=self.organizer_limits,
                    timeout_s=self.timeout_s,
                    max_response_chars=self.max_response_chars,
                    max_messages=self.input_limits.max_messages,
                    classifier=self.classifier,
                    tool_dispatch=self._tool_dispatch,
                )

        if spec.config == "C4":
            assert self.fleet_static is not None and self.fleet_rollout is not None
            fleet_result = propose_fleet_plan(
                client,
                scenario=scenario,
                mission_id=f"fleet-{spec.scenario}-{spec.seed}",
                context=context,
                static=self.fleet_static,
                config=self.fleet_rollout,
                timeout_s=self.timeout_s,
                max_response_chars=self.max_response_chars,
            )

        sim, det = scenarios.build_engine(
            scenario, streams_for(self.base_config, len(scenario.robots))
        )
        fleet = robots.RobotFleet(
            [r.kind for r in scenario.robots],
            load_raised=[r.load_raised for r in scenario.robots],
        )
        if fleet_result is not None:
            fleet_routes = apply_fleet_plan(fleet_result, sim, scenario)
        rig = E5Rig(self.base_config, fleet, box, advisor=bridge)
        sim.systems.insert(1, rig.system())

        total = scenario.duration_ticks if spec.ticks is None else spec.ticks
        distance = 0.0
        caller = (
            None
            if (runtime is None and org_runtime is None)
            else AdvisorCaller(
                runtime,
                robot_ids=robot_ids,
                run_id=f"run-{spec.scenario}-{spec.seed}",
                near_threshold_m=self.near_threshold_m,
                trigger_ticks=spec.trigger_ticks,
                organizer=org_runtime,
            )
        )

        for tick in range(total):
            current_tick_holder[0] = tick
            if caller is not None:
                caller.step(sim=sim, tick=tick, rig=rig, scenario=scenario, box=box, fleet=fleet)
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
            "cautions_rejected": {} if caller is None else dict(caller.rejected),
            "advisor_calls": 0 if caller is None else caller.advisor_calls,
            "organizer_calls": 0 if caller is None else caller.organizer_calls,
            **fleet_record(fleet_result, fleet_routes),
            "messages_sent": 0 if org_runtime is None else len(org_runtime.outbound_messages),
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
    near_threshold_m: float,
    classifier: GuardClassifier | None = None,
    base_config: E1Config | None = None,
    client_environ: Mapping[str, str] | None = None,
    call_log: CallLog | None = None,
    fleet_static: StaticMap | None = None,
    fleet_rollout: RolloutConfig | None = None,
) -> dict[str, Any]:
    """Module-level runner function running one spec."""
    runner = E5Runner(
        caution_config=caution_config,
        input_limits=input_limits,
        timeout_s=timeout_s,
        rate_limit_ticks=rate_limit_ticks,
        max_response_chars=max_response_chars,
        near_threshold_m=near_threshold_m,
        classifier=classifier,
        base_config=base_config,
        client_environ=client_environ,
        call_log=call_log,
        fleet_static=fleet_static,
        fleet_rollout=fleet_rollout,
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
            [git, "-c", "safe.directory=*", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
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
