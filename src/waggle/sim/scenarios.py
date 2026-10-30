"""Scenario format, generators for S01 to S18, seeds and replay by seed. Control never imports it.

A scenario holds a seed, a map, robots with routes, humans with plans, scripted events, a
declared target layer, an expected outcome and the flag ``unavoidable_at_spawn``. Generation is
a pure function of the scenario id and the seed. The ``compound`` field is a reserved schema
for the compound crisis templates of E10 and is always None in S01 to S18.
"""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from waggle.sim import detector, engine, humans, params, robots, scripted, streams, world
from waggle.sim.params import DT, HUMAN_RADIUS, HUMAN_WALK_SPEED, RobotKind, RobotParams

Point = tuple[float, float]
SCENARIO_IDS = [f"S{n:02d}" for n in range(1, 19)]
MASTER_SEED = 20261027
DEV_PER_SCENARIO = 5
HELDOUT_PER_SCENARIO = 12
SEPARATION_MARGIN = 0.5
NEAR_MISS_MARGIN = 0.2
DENSITY_TICKS = 1200
CORRIDOR_Y = 3.0
KIND_CYCLE = (
    RobotKind.CARRIER,
    RobotKind.PARTS_RUNNER,
    RobotKind.TECH_REPAIR,
    RobotKind.FORKLIFT,
)


# ---------------------------------------------------------------- maps


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _zone(
    zone_id: str, kind: str, box: list[list[float]], capacity: int | None = None
) -> dict[str, Any]:
    zone: dict[str, Any] = {"id": zone_id, "kind": kind, "polygon": box}
    if capacity is not None:
        zone["capacity"] = capacity
    return zone


def _map_a() -> dict[str, Any]:
    return {
        "version": 1,
        "name": "map_a",
        "bounds": [0.0, 0.0, 40.0, 24.0],
        "walls": [],
        "racks": [_rect(6, 5, 34, 7), _rect(6, 11, 34, 13), _rect(6, 17, 34, 19)],
        "zones": [
            _zone("corridor_s", "transit", _rect(0, 0, 40, 5)),
            _zone("aisle_1", "aisle", _rect(6, 7, 34, 11)),
            _zone("aisle_2", "aisle", _rect(6, 13, 34, 17)),
            _zone("corridor_n", "transit", _rect(0, 19, 40, 24)),
            _zone("lane_1", "one_lane_aisle", _rect(0, 5, 6, 19), 1),
            _zone("connector_e", "aisle", _rect(34, 5, 40, 19)),
            _zone("corner_se", "blind_corner", _rect(34, 5, 37, 8)),
            _zone("station_1", "station", _rect(2, 20, 8, 23)),
            _zone("depot_n", "depot", _rect(30, 20, 38, 23)),
        ],
    }


def _map_b() -> dict[str, Any]:
    return {
        "version": 1,
        "name": "map_b",
        "bounds": [0.0, 0.0, 30.0, 30.0],
        "walls": [],
        "racks": [
            _rect(3, 6, 12, 12),
            _rect(18, 6, 27, 12),
            _rect(3, 18, 12, 27),
            _rect(18, 18, 27, 27),
        ],
        "zones": [
            _zone("corridor_s", "transit", _rect(0, 0, 30, 6)),
            _zone("cross_h", "aisle", _rect(0, 12, 30, 18)),
            _zone("cross_v", "aisle", _rect(12, 6, 18, 30)),
            _zone("corridor_n", "transit", _rect(0, 27, 30, 30)),
            _zone("lane_b", "one_lane_aisle", _rect(0, 6, 3, 12), 1),
            _zone("corner_1", "blind_corner", _rect(12, 12, 15, 15)),
            _zone("depot_b", "depot", _rect(24, 1, 29, 5)),
        ],
    }


def load_map(name: str) -> world.World:
    """Map ``A`` or ``B`` as a World. Raises ValueError for any other name."""
    if name == "A":
        return world.parse_world(_map_a())
    if name == "B":
        return world.parse_world(_map_b())
    raise ValueError(f"unknown map {name!r}, expected 'A' or 'B'")


# ---------------------------------------------------------------- format


@dataclass(frozen=True)
class RobotSpec:
    """One robot: class, start pose, route of waypoints, initial speed and load flag."""

    kind: RobotKind
    pose: tuple[float, float, float]
    route: tuple[Point, ...]
    initial_speed: float = 0.0
    load_raised: bool = False


@dataclass(frozen=True)
class HumanSpec:
    """One human: how it moves and where it starts."""

    plan: humans.HumanPlan
    start: Point


@dataclass(frozen=True)
class Scenario:
    """A fully specified run. ``events`` lists (tick, text) notes of scripted events."""

    id: str
    family: str
    target_layer: str
    expected_outcome: str
    map_name: str
    seed: int
    robots: tuple[RobotSpec, ...]
    humans: tuple[HumanSpec, ...]
    duration_ticks: int
    separation_margin: float
    near_miss_margin: float
    unavoidable_at_spawn: bool
    events: tuple[tuple[int, str], ...] = ()
    compound: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable form."""
        return {
            "id": self.id,
            "family": self.family,
            "target_layer": self.target_layer,
            "expected_outcome": self.expected_outcome,
            "map_name": self.map_name,
            "seed": self.seed,
            "robots": [
                {
                    "kind": r.kind.value,
                    "pose": list(r.pose),
                    "route": [list(p) for p in r.route],
                    "initial_speed": r.initial_speed,
                    "load_raised": r.load_raised,
                }
                for r in self.robots
            ],
            "humans": [
                {
                    "kind": h.plan.kind,
                    "speed": h.plan.speed,
                    "path": [list(p) for p in h.plan.path],
                    "start_tick": h.plan.start_tick,
                    "turn_sigma": h.plan.turn_sigma,
                    "start": list(h.start),
                }
                for h in self.humans
            ],
            "duration_ticks": self.duration_ticks,
            "separation_margin": self.separation_margin,
            "near_miss_margin": self.near_miss_margin,
            "unavoidable_at_spawn": self.unavoidable_at_spawn,
            "events": [list(e) for e in self.events],
            "compound": None if self.compound is None else dict(self.compound),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Scenario":
        """Rebuild a scenario from ``to_dict`` output."""
        robot_specs = tuple(
            RobotSpec(
                RobotKind(r["kind"]),
                (float(r["pose"][0]), float(r["pose"][1]), float(r["pose"][2])),
                tuple((float(p[0]), float(p[1])) for p in r["route"]),
                float(r["initial_speed"]),
                bool(r["load_raised"]),
            )
            for r in data["robots"]
        )
        human_specs = tuple(
            HumanSpec(
                humans.HumanPlan(
                    h["kind"],
                    float(h["speed"]),
                    tuple((float(p[0]), float(p[1])) for p in h["path"]),
                    int(h["start_tick"]),
                    float(h["turn_sigma"]),
                ),
                (float(h["start"][0]), float(h["start"][1])),
            )
            for h in data["humans"]
        )
        return cls(
            id=data["id"],
            family=data["family"],
            target_layer=data["target_layer"],
            expected_outcome=data["expected_outcome"],
            map_name=data["map_name"],
            seed=int(data["seed"]),
            robots=robot_specs,
            humans=human_specs,
            duration_ticks=int(data["duration_ticks"]),
            separation_margin=float(data["separation_margin"]),
            near_miss_margin=float(data["near_miss_margin"]),
            unavoidable_at_spawn=bool(data["unavoidable_at_spawn"]),
            events=tuple((int(e[0]), str(e[1])) for e in data["events"]),
            compound=data["compound"],
        )


# ---------------------------------------------------------------- unavoidable at spawn


def unavoidable_at_spawn(
    robot_starts: Sequence[Point],
    robot_params: Sequence[RobotParams],
    human_starts: Sequence[Point],
    human_radius: float,
) -> bool:
    """True when a human spawns inside the minimum possible stopping distance of a robot at
    its speed cap, so no controller could avoid the contact."""
    for (rx, ry), p in zip(robot_starts, robot_params, strict=True):
        reach = humans.max_speed_stop_distance(p) + p.length / 2 + human_radius
        if any(math.hypot(hx - rx, hy - ry) < reach for hx, hy in human_starts):
            return True
    return False


# ---------------------------------------------------------------- generators


def _finish(
    sid: str,
    family: str,
    layer: str,
    outcome: str,
    map_name: str,
    seed: int,
    robot_specs: list[RobotSpec],
    human_specs: list[HumanSpec],
    ticks: int,
    events: tuple[tuple[int, str], ...] = (),
) -> Scenario:
    flag = unavoidable_at_spawn(
        [(r.pose[0], r.pose[1]) for r in robot_specs],
        [params.ROBOT_PARAMS[r.kind] for r in robot_specs],
        [h.start for h in human_specs],
        HUMAN_RADIUS,
    )
    return Scenario(
        sid, family, layer, outcome, map_name, seed, tuple(robot_specs), tuple(human_specs),
        ticks, SEPARATION_MARGIN, NEAR_MISS_MARGIN, flag, events,
    )  # fmt: skip


def _rng(seed: int) -> np.random.Generator:
    return streams.make_streams(seed, "scenario", 1)[0]


def _adversarial(
    sid: str, seed: int, kind: RobotKind, how: str, family: str, raised: bool = False
) -> Scenario:
    p = params.ROBOT_PARAMS[kind]
    fraction = humans.draw_fraction(_rng(seed))
    step_out = how == "step_out"
    crossing = (36.0 if step_out else 26.0, CORRIDOR_Y)
    start = (36.0, 6.0) if step_out else (crossing[0], 4.8)
    build = {
        "step_out": humans.adversarial_step_out,
        "cross": humans.adversarial_crossing,
        "stop": humans.adversarial_stop_in_aisle,
    }[how]
    plan = build(
        p, fraction=fraction, crossing=crossing, robot_start=(2.0, CORRIDOR_Y),
        human_start=start, human_speed=HUMAN_WALK_SPEED,
    )  # fmt: skip
    top = p.max_speed * (0.6 if raised else 1.0)
    robot = RobotSpec(kind, (2.0, CORRIDOR_Y, 0.0), ((38.0, CORRIDOR_Y),), top, raised)
    ticks = round((crossing[0] / top + 8.0) / DT)
    event = (plan.start_tick, f"human enters at fraction {fraction:.3f} of the stopping distance")
    return _finish(
        sid, family, "fast_layer", "a human collision is expected without control", "A", seed,
        [robot], [HumanSpec(plan, start)], ticks, (event,),
    )  # fmt: skip


def _one_lane(sid: str, seed: int) -> Scenario:
    a = RobotSpec(RobotKind.CARRIER, (3.0, 6.0, math.pi / 2), ((3.0, 18.0),))
    b = RobotSpec(RobotKind.CARRIER, (3.0, 18.0, -math.pi / 2), ((3.0, 6.0),))
    return _finish(
        sid, "Blind corners and narrow aisles", "leases_and_fencing",
        "two robots meet head-on in the one-lane aisle without coordination", "A", seed,
        [a, b], [], round(10.0 / DT),
    )  # fmt: skip


def _slots(map_name: str, count: int) -> list[tuple[Point, float, tuple[Point, Point]]]:
    """Start slots (position, heading, route) in clear corridors, in opposing lanes."""
    if map_name == "A":
        rows = [(1.5, 0.0, 38.0, 2.0), (3.5, math.pi, 2.0, 38.0)]
        columns, x0 = 15, 3.0
    else:
        rows = [(1.5, 0.0, 28.0, 2.5), (3.5, math.pi, 2.5, 28.0), (28.5, 0.0, 28.0, 2.5)]
        columns, x0 = 11, 2.5
    slots: list[tuple[Point, float, tuple[Point, Point]]] = []
    for column in range(columns):
        for y, heading, goal, back in rows:
            slots.append(((x0 + 2.5 * column, y), heading, ((goal, y), (back, y))))
    return slots[:count]


def _density(sid: str, seed: int, count: int, map_name: str) -> Scenario:
    rng = _rng(seed)
    order = rng.permutation(len(KIND_CYCLE))
    slots = _slots(map_name, count)
    robot_specs = []
    for i, ((x, y), heading, route) in enumerate(slots):
        kind = KIND_CYCLE[int(order[i % len(KIND_CYCLE)])]
        robot_specs.append(RobotSpec(kind, (x, y, heading), route))
    walkers = {3: 2, 10: 4, 30: 8}[count]
    lane_y = (9.0, 15.0) if map_name == "A" else (15.0, 15.0)
    starts = [(10.0 + 3.5 * k, lane_y[k % 2]) for k in range(walkers)]
    plans = [humans.HumanPlan.walker(HUMAN_WALK_SPEED, 0.5) for _ in range(walkers)]
    human_specs = [HumanSpec(plan, start) for plan, start in zip(plans, starts, strict=True)]
    return _finish(
        sid, "Density", "fast_layer",
        "robots share the map with walking humans; collisions are expected without control",
        map_name, seed, robot_specs, human_specs, DENSITY_TICKS,
    )  # fmt: skip


_BLIND = "Blind corners and narrow aisles"
_ADVERSARIAL = "Adversarial humans"


def generate(scenario_id: str, seed: int) -> Scenario:
    """Build scenario ``S01`` to ``S18`` for ``seed``. Pure: same input, same scenario."""
    if scenario_id not in SCENARIO_IDS:
        raise ValueError(f"unknown scenario {scenario_id!r}")
    if seed < 0:
        raise ValueError("seed must not be negative")
    n = int(scenario_id[1:])
    table: dict[int, tuple[RobotKind, str, str, bool]] = {
        1: (RobotKind.FORKLIFT, "step_out", _BLIND, False),
        2: (RobotKind.CARRIER, "step_out", _BLIND, False),
        4: (RobotKind.PARTS_RUNNER, "step_out", _BLIND, False),
        5: (RobotKind.FORKLIFT, "step_out", _BLIND, True),
        6: (RobotKind.TECH_REPAIR, "stop", _BLIND, False),
        7: (RobotKind.CARRIER, "cross", _ADVERSARIAL, False),
        8: (RobotKind.FORKLIFT, "cross", _ADVERSARIAL, False),
        9: (RobotKind.PARTS_RUNNER, "cross", _ADVERSARIAL, False),
        10: (RobotKind.TECH_REPAIR, "cross", _ADVERSARIAL, False),
        11: (RobotKind.CARRIER, "stop", _ADVERSARIAL, False),
        12: (RobotKind.FORKLIFT, "stop", _ADVERSARIAL, False),
    }
    if n == 3:
        return _one_lane(scenario_id, seed)
    if n in table:
        kind, how, family, raised = table[n]
        return _adversarial(scenario_id, seed, kind, how, family, raised)
    count = (3, 10, 30)[(n - 13) % 3]
    return _density(scenario_id, seed, count, "A" if n <= 15 else "B")


# ---------------------------------------------------------------- seeds


def generate_seeds(master_seed: int) -> dict[str, Any]:
    """Development and held-out seeds for S01 to S18 from one master seed.

    All 306 seeds are drawn together without replacement, so no seed appears twice anywhere
    and the development and held-out sets are disjoint.
    """
    per = DEV_PER_SCENARIO + HELDOUT_PER_SCENARIO
    rng = np.random.default_rng(np.random.SeedSequence(master_seed))
    drawn = [int(v) for v in rng.choice(10**9, size=per * len(SCENARIO_IDS), replace=False)]
    dev: dict[str, list[int]] = {}
    held: dict[str, list[int]] = {}
    for index, sid in enumerate(SCENARIO_IDS):
        chunk = drawn[index * per : (index + 1) * per]
        dev[sid], held[sid] = chunk[:DEV_PER_SCENARIO], chunk[DEV_PER_SCENARIO:]
    return {"master_seed": master_seed, "dev": dev, "heldout": held}


def write_seeds_once(path: Path, master_seed: int) -> bool:
    """Write the seed file only if it does not exist. Returns whether it wrote."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(generate_seeds(master_seed), indent=2) + chr(10)
    path.write_bytes(text.encode("utf-8"))  # bytes: the same file on every platform
    return True


# ---------------------------------------------------------------- run


@dataclass(frozen=True)
class RunRecord:
    """The outcome of one run: episode counts, completed tasks and the per-tick hashes."""

    scenario_id: str
    seed: int
    ticks: int
    counts: dict[str, int]
    tasks_completed: int
    final_hash: str
    hashes: tuple[str, ...]


def build_engine(
    scenario: Scenario, extra_streams: Mapping[str, int] | None = None
) -> tuple[engine.Engine, detector.Detector]:
    """The engine of a scenario with no control (driver, dynamics, humans, detector)."""
    box = load_map(scenario.map_name)
    fleet = robots.RobotFleet(
        [r.kind for r in scenario.robots], load_raised=[r.load_raised for r in scenario.robots]
    )
    crowd = humans.Crowd([h.plan for h in scenario.humans], box)
    driver = scripted.WaypointDriver(fleet, [r.route for r in scenario.robots])
    poses = np.array([r.pose for r in scenario.robots], dtype=np.float64)
    speeds = np.array([r.initial_speed for r in scenario.robots], dtype=np.float64)
    starts = np.array([h.start for h in scenario.humans], dtype=np.float64).reshape(-1, 2)
    arrays = {
        **fleet.initial_arrays(poses, speeds),
        **crowd.initial_arrays(starts),
        **driver.initial_arrays(),
    }
    active = np.asarray(arrays["robot_active"], dtype=np.float64)
    active[:, 0] = speeds
    det = detector.Detector(
        fleet.params,
        separation_margin=scenario.separation_margin,
        near_miss_margin=scenario.near_miss_margin,
    )
    arrays.update(det.initial_arrays(poses, starts))
    stream_counts = {"humans": len(scenario.humans), **(extra_streams or {})}
    sim = engine.Engine(
        scenario.seed,
        arrays,
        [driver.system(), fleet.system(), crowd.system(), det.system()],
        stream_counts,
    )
    return sim, det


def run_scenario(scenario: Scenario, ticks: int | None = None) -> RunRecord:
    """Run a scenario with no control: the waypoint driver only. Replay by seed is exact."""
    sim, det = build_engine(scenario)
    total = scenario.duration_ticks if ticks is None else ticks
    hashes: list[str] = []
    for _ in range(total):
        sim.step()
        hashes.append(sim.state_hash())
    tasks = int(np.asarray(sim.state.arrays["script_tasks"], dtype=np.int64).sum())
    return RunRecord(
        scenario.id, scenario.seed, total, det.counts(sim.state), tasks, sim.state_hash(),
        tuple(hashes),
    )  # fmt: skip
