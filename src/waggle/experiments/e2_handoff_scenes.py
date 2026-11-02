"""E2 handoff chaos scenes S31 to S35, scripted step by step on a real database.

Each scene runs against one migrated schema with the production corridor and task repositories.
The two arms differ in one object: ``fenced`` uses ``TaskRepository``, ``baseline`` uses
``NoFencingHandoffRepository``. Everything else, the sweeper, the corridor table, the finisher and
the trusted occupancy stand-in, is shared, so a difference in the oracle counts comes from the
handoff path alone.

Faults come from ``waggle.experiments.e2_faults`` through ``scene_schedule``: the kill point of
the first attempt and the replay mode of the stale runner are drawn from the seed, one draw per
scene. A kill here is an exception that abandons the runner mid step (``RunnerKilled``), raised by
the ``KillSwitch`` of ``e2_hooks``. It is not a process kill: real process kills are the chaos
runner's job. A killed runner leaves its credential behind, and a stale runner (a zombie) later
sends it, which is what the baseline accepts and production refuses.

The trusted occupancy is a scripted stand-in (``ScriptedOccupancy``) and the clock is a list of
ticks written in each scene, so a scene is deterministic for a seed. Nothing here edits production
code or the earlier E2 modules.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from waggle.coordination.corridors import (
    CorridorRequest,
    Direction,
    ZoneObservation,
    ZoneToken,
)
from waggle.coordination.task_model import TaskCredential, TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.tasks import TaskRepository, TaskResult
from waggle.experiments.e2_faults import (
    FaultParams,
    FaultSchedule,
    KillPoint,
    ReplayMode,
    build_schedule,
)
from waggle.experiments.e2_handoff_baseline import NoFencingHandoffRepository
from waggle.experiments.e2_hooks import KillSwitch
from waggle.experiments.e2_oracle import ZoneSample
from waggle.experiments.e2_worker import task_id
from waggle.handoff_finisher import HandoffFinisher

ARMS = ("fenced", "baseline")
SCENES = ("S31", "S32", "S33", "S34", "S35")
TARGET_LAYERS = {
    "S31": "lease expiry, fencing token",
    "S32": "idempotency key",
    "S33": "task dependency, safe hold",
    "S34": "lease with capacity one",
    "S35": "fencing token",
}
LEASE = 10


class RunnerKilled(Exception):
    """A planned kill abandoned the runner at a lifecycle point."""


@dataclass(frozen=True)
class ScenePlan:
    """The faults drawn for one scene of one seed."""

    kill_point: KillPoint
    replay_mode: ReplayMode


def scene_schedule(seed: int) -> FaultSchedule:
    """One kill and one replay per scene, the scene number being the task index."""
    params = FaultParams(
        workers=2,
        tasks=len(SCENES),
        kill_rate=1.0,
        max_kills_per_task=1,
        replay_rate=1.0,
        clock_jumps_per_worker=0,
        delay_rate=0.0,
    )
    return build_schedule(seed, params)


def plan_for(seed: int, scene: str) -> ScenePlan:
    """The kill point of the first attempt and the replay mode for ``scene`` under ``seed``."""
    index = SCENES.index(scene)
    schedule = scene_schedule(seed)
    point = schedule.kill_for(index, 1)
    replay = schedule.replay_for(index)
    if point is None or replay is None:
        raise ValueError("the scene schedule must plan a kill and a replay for every scene")
    return ScenePlan(point, replay.mode)


class ScriptedOccupancy:
    """Trusted occupancy stand-in: what a scene says is in a zone, observed at the asked tick."""

    def __init__(self) -> None:
        self._at: dict[str, tuple[str, ...]] = {}

    def put(self, zone: str, occupants: tuple[str, ...]) -> None:
        """Set who is in ``zone`` from now on."""
        self._at[zone] = occupants

    def observe(self, zone_ids: tuple[str, ...], now_tick: int) -> tuple[ZoneObservation, ...]:
        """One observation per zone at ``now_tick``."""
        return tuple(ZoneObservation(z, now_tick, self._at.get(z, ())) for z in zone_ids)


@dataclass
class Run:
    """What a runner holds: its credential and the zone token it was granted, if any."""

    worker: str
    credential: TaskCredential
    attempt: int
    zone: ZoneToken | None = None


@dataclass
class SceneResult:
    """What a scene reports besides the event log: its dependencies, samples and outcomes."""

    dependencies: dict[str, str] = field(default_factory=dict)
    samples: list[ZoneSample] = field(default_factory=list)
    outcomes: dict[str, bool] = field(default_factory=dict)


class Bench:
    """The shared objects of one scene and the runner steps built on them."""

    def __init__(self, database: Database, arm: str, schedule: FaultSchedule, scene: int) -> None:
        if arm not in ARMS:
            raise ValueError("unknown arm")
        self.tasks: TaskRepository = (
            NoFencingHandoffRepository(database) if arm == "baseline" else TaskRepository(database)
        )
        self.corridors = CorridorRepository(database)
        self.occupancy = ScriptedOccupancy()
        self.finisher = HandoffFinisher(self.tasks, self.corridors, self.occupancy)
        self.switch = KillSwitch(schedule, self._kill)
        self.scene = scene
        self.kills = False
        self.runs: list[Run] = []
        self.result = SceneResult()
        self.zones: list[str] = []
        self._requests = 0

    @staticmethod
    def _kill() -> None:
        raise RunnerKilled

    def rid(self, label: str) -> str:
        """A request id that is unique within the scene."""
        self._requests += 1
        return f"{label}-{self._requests}"

    def zone(self, name: str) -> str:
        """Register ``name`` as a zone of this scene and return it."""
        self.corridors.register((name,))
        self.zones.append(name)
        return name

    def task(self, name: str, *, zone: str | None = None, after: str | None = None) -> str:
        """Create an approved task, optionally with a handoff zone or a dependency."""
        deps = (after,) if after is not None else ()
        self.tasks.create(TaskDefinition(name, deps, 3, 0, zone))
        for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
            self.tasks.advance(name, state, f"{name}-{state.value}", 0)
        if after is not None:
            self.result.dependencies[name] = after
        return name

    def reach(self, point: KillPoint, attempt: int) -> None:
        """A kill point of the first attempt; a no-op when kills are off for the scene."""
        if self.kills:
            self.switch.reach(point, self.scene, attempt)

    def begin(self, worker: str, zone: str, now: int, *, enter: bool = True) -> Run | None:
        """Claim, start and, when asked, enter the zone. A planned kill raises RunnerKilled."""
        claimed = self.tasks.claim(worker, self.rid("claim"), now, LEASE)
        if not claimed.accepted or claimed.task is None:
            return None
        run = Run(worker, claimed.task.credential(), claimed.task.attempt)
        self.runs.append(run)
        self.reach(KillPoint.AFTER_CLAIM, run.attempt)
        if not self.tasks.start(run.credential, self.rid("start"), now).accepted:
            return run
        self.reach(KillPoint.AFTER_START, run.attempt)
        if enter:
            self.enter(run, zone, now)
            self.reach(KillPoint.IN_HANDLER, run.attempt)
        return run

    def enter(self, run: Run, zone: str, now: int) -> bool:
        """Reserve ``zone`` and drive in. A denied reservation leaves the runner outside."""
        observed = self.occupancy.observe((zone,), now)
        request = CorridorRequest(run.worker, (zone,), Direction.FORWARD)
        reserved = self.corridors.reserve(request, now, observed, LEASE)
        if not reserved.granted:
            return False
        run.zone = reserved.tokens[0]
        self.occupancy.put(zone, (run.worker,))
        self.sample(zone, now)
        return True

    def leave(self, run: Run, zone: str, now: int) -> None:
        """Drive out of the zone and release it with clear occupancy."""
        self.occupancy.put(zone, ())
        self.sample(zone, now)
        if run.zone is not None:
            self.corridors.release(
                run.worker, (run.zone,), now, self.occupancy.observe((zone,), now)
            )

    def sample(self, zone: str, now: int) -> None:
        """Record who is in ``zone`` for the zone oracle."""
        occupants = self.occupancy.observe((zone,), now)[0].occupants or ()
        self.result.samples.append(ZoneSample(now, zone, frozenset(occupants), 1))

    def finish(self, run: Run, now: int) -> TaskResult:
        """Complete through the production finisher; a planned kill may follow."""
        self.reach(KillPoint.BEFORE_COMPLETE, run.attempt)
        result = self.finisher.complete(run.credential, self.rid("finish"), now)
        if result.accepted:
            self.reach(KillPoint.AFTER_COMPLETE, run.attempt)
        return result

    def zombie(self, run: Run, zone: str, now: int) -> TaskResult:
        """A stale runner resumes and delivers with the credential and zone token it remembers."""
        token = run.zone if run.zone is not None else ZoneToken(zone, 0)
        observation = self.occupancy.observe((zone,), now)[0]
        return self.tasks.complete_handoff(
            run.credential, token, observation, self.rid("zombie"), now
        )

    def sweep(self, now: int) -> None:
        """The production sweeper: requeue expired attempts, expire clear zones."""
        self.tasks.recover(now)
        self.corridors.expire(now, self.occupancy.observe(tuple(self.zones), now))

    def tow(self, zone: str, now: int) -> None:
        """Remove a dead chassis from the zone and let the expiry clear the latch."""
        self.occupancy.put(zone, ())
        self.sample(zone, now)
        self.sweep(now)


def _attempt(bench: Bench, worker: str, zone: str, now: int) -> Run | None:
    """One full runner pass; a planned kill ends it and the run stays in ``bench.runs``."""
    try:
        run = bench.begin(worker, zone, now)
        if run is not None:
            bench.finish(run, now)
        return run
    except RunnerKilled:
        return bench.runs[-1] if bench.runs else None


def _reclaim_and_deliver(
    bench: Bench, first: Run | None, zone: str, mode: ReplayMode, key: str
) -> None:
    """Recover after a kill or pause, then let the same worker name take the task again."""
    bench.sweep(20)
    if first is not None and mode is ReplayMode.DURING_RECOVERY:
        bench.result.outcomes[key] = bench.zombie(first, zone, 20).accepted
    bench.tow(zone, 30)
    second = bench.begin("w1", zone, 31)
    if first is not None and mode is ReplayMode.AFTER_RECOVERY:
        bench.result.outcomes[key] = bench.zombie(first, zone, 33).accepted
    if second is not None:
        bench.finish(second, 34)


def scene_s31(bench: Bench, plan: ScenePlan) -> None:
    """Runner killed mid delivery, recovered, and a stale copy of it replays its credential."""
    zone = bench.zone("z0")
    bench.task(task_id(0), zone=zone)
    bench.kills = True
    first = _attempt(bench, "w1", zone, 0)
    bench.kills = False
    if _done(bench, task_id(0)):
        return
    _reclaim_and_deliver(bench, first, zone, plan.replay_mode, "stale_delivery_accepted")


def scene_s32(bench: Bench, plan: ScenePlan) -> None:
    """The same handoff delivered twice, once with the same request id and once with a new one."""
    zone = bench.zone("z0")
    bench.task(task_id(0), zone=zone)
    run = bench.begin("w1", zone, 0)
    if run is None or run.zone is None:
        return
    request = bench.rid("finish")
    observation = bench.occupancy.observe((zone,), 1)[0]
    delivered = bench.tasks.complete_handoff(run.credential, run.zone, observation, request, 1)
    again = 1 if plan.replay_mode is ReplayMode.DURING_RECOVERY else 2
    observation = bench.occupancy.observe((zone,), again)[0]
    same = bench.tasks.complete_handoff(run.credential, run.zone, observation, request, again)
    other = bench.tasks.complete_handoff(
        run.credential, run.zone, observation, bench.rid("duplicate"), again
    )
    bench.result.outcomes["delivered"] = delivered.accepted
    bench.result.outcomes["same_id_replayed"] = same.replayed
    bench.result.outcomes["new_id_accepted"] = other.accepted


def scene_s33(bench: Bench, plan: ScenePlan) -> None:
    """A technician waits for a late part; a stale delivery must not release the repair."""
    zone = bench.zone("z0")
    part = bench.task(task_id(0), zone=zone)
    bench.task(task_id(1), after=part)
    first = bench.begin("w1", zone, 0, enter=False)
    held = bench.tasks.claim("tech", bench.rid("tech"), 1, LEASE)
    bench.result.outcomes["repair_claimed_while_part_late"] = held.accepted
    bench.sweep(20)
    second = bench.begin("w1", zone, 21)
    if first is not None:
        bench.zombie(first, zone, 22)
    early = bench.tasks.claim("tech", bench.rid("tech"), 23, LEASE)
    bench.result.outcomes["repair_claimed_before_delivery"] = early.accepted
    if early.accepted:
        _repair(bench, early, 23)
    if second is not None:
        bench.finish(second, 24)
    if not early.accepted:
        late = bench.tasks.claim("tech", bench.rid("tech"), 25, LEASE)
        bench.result.outcomes["repair_claimed_after_delivery"] = late.accepted
        if late.accepted:
            _repair(bench, late, 25)


def _repair(bench: Bench, claimed: TaskResult, now: int) -> None:
    """The technician starts and completes the repair task it claimed."""
    if claimed.task is None:
        return
    credential = claimed.task.credential()
    if bench.tasks.start(credential, bench.rid("start"), now).accepted:
        bench.tasks.complete(credential, bench.rid("done"), now + 1)


def scene_s34(bench: Bench, plan: ScenePlan) -> None:
    """Two runners, two tasks, one zone of capacity one: the second waits for the first."""
    zone = bench.zone("z0")
    bench.task(task_id(0), zone=zone)
    bench.task(task_id(1), zone=zone)
    one = bench.begin("w1", zone, 0)
    two = bench.begin("w2", zone, 0)
    if one is None or two is None:
        return
    bench.result.outcomes["second_entered_while_held"] = two.zone is not None
    bench.result.outcomes["second_delivered_while_held"] = bench.finish(two, 1).accepted
    bench.result.outcomes["first_delivered"] = bench.finish(one, 2).accepted
    bench.leave(one, zone, 3)
    entered = bench.enter(two, zone, 4)
    bench.result.outcomes["second_entered_after_release"] = entered
    if entered:
        bench.result.outcomes["second_delivered"] = bench.finish(two, 5).accepted


def scene_s35(bench: Bench, plan: ScenePlan) -> None:
    """A stalled runner is reassigned to the same worker name, then resumes and delivers."""
    zone = bench.zone("z0")
    bench.task(task_id(0), zone=zone)
    first = bench.begin("w1", zone, 0, enter=False)
    bench.sweep(20)
    second = bench.begin("w1", zone, 21)
    if first is not None:
        bench.result.outcomes["stale_delivery_accepted"] = bench.zombie(first, zone, 23).accepted
    if second is not None:
        bench.result.outcomes["live_delivery_accepted"] = bench.finish(second, 24).accepted


def _done(bench: Bench, name: str) -> bool:
    task = bench.tasks.get(name)
    return task is not None and task.state is TaskState.DONE


SCENE_FUNCTIONS: dict[str, Callable[[Bench, ScenePlan], None]] = {
    "S31": scene_s31,
    "S32": scene_s32,
    "S33": scene_s33,
    "S34": scene_s34,
    "S35": scene_s35,
}
