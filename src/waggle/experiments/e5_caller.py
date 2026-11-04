"""Caller of the advisor and organizer runtimes inside the E5 rig (ADVISORS_DESIGN 8, 11).

Each tick, for each robot, the caller reads the facts from the simulator and the rig, decides by
a context-change rule whether to evaluate, and calls ``AdvisorRuntime.advise`` and/or
``OrganizerRuntime.organize``. Any caution or yield hold lands in the caution log, which the
bridge reads, so the caller can only reduce motion. A fact the state does not expose is passed as
unknown (None), never as an invented default. A failure of either runtime is counted and leaves
the limits already in force.
"""

import logging
from typing import Any, Protocol

import numpy as np

from waggle.experiments.e5_rig import E5Rig
from waggle.governance.advisor_input import InboundMessage, TrustedFacts
from waggle.governance.caution import CautionAction
from waggle.llm.advisor_runtime import AdvisorResult
from waggle.llm.errors import LlmError
from waggle.llm.organizer_runtime import OrganizerResult
from waggle.sim import robots, scenarios, world
from waggle.sim.params import HUMAN_RADIUS

logger = logging.getLogger("waggle.experiments.e5.caller")
ERROR_KEY = "advisor_error"
ORGANIZER_ERROR_KEY = "organizer_error"
NO_HUMAN_GAP_M = 99.0


class Advisor(Protocol):
    """What the caller needs from the advisor runtime: ``AdvisorRuntime.advise``."""

    def advise(
        self,
        facts: TrustedFacts,
        *,
        tick: int,
        current_cap: float,
        class_max: float,
        run_id: str,
        task_id: str,
        latency_ticks: int = 0,
    ) -> AdvisorResult:
        """Run one advisor evaluation step."""
        ...


class Organizer(Protocol):
    """What the caller needs from the organizer runtime: ``OrganizerRuntime.organize``."""

    def organize(
        self,
        facts: TrustedFacts,
        *,
        tick: int,
        class_max: float,
        run_id: str,
        task_id: str,
        ask_signals: tuple[str, ...] = (),
        messages: list[InboundMessage] | None = None,
        latency_ticks: int = 0,
    ) -> OrganizerResult:
        """Run one organizer evaluation step."""
        ...


def _point_in_box(point: Any, zone: world.Polygon) -> bool:
    pts = np.asarray(zone.points, dtype=np.float64)
    return bool(
        len(pts) >= 3
        and pts[:, 0].min() <= point[0] <= pts[:, 0].max()
        and pts[:, 1].min() <= point[1] <= pts[:, 1].max()
    )


def extract_facts(
    sim: Any,
    robot_index: int,
    robot_id: str,
    scenario: scenarios.Scenario,
    box: world.World,
    last_reason: str | None,
    *,
    occluded: bool | None,
) -> TrustedFacts:
    """Facts for one robot from the simulator arrays, the map and the rig.

    Speed, zone and nearest distance come from the state. ``occluded`` is passed by the caller
    from the rig. The task step, the geofences and the lease holders are not exposed by the
    simulator or the rig, so they are None (unknown).
    """
    poses = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)
    speeds = np.asarray(sim.state.arrays["robot_speed"], dtype=np.float64)
    humans = np.asarray(sim.state.arrays["human_pos"], dtype=np.float64).reshape(-1, 2)
    pos = poses[robot_index, :2]
    h_min = (
        float(np.min(np.hypot(*(humans - pos).T) - HUMAN_RADIUS)) if len(humans) else NO_HUMAN_GAP_M
    )
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
        task_step=None,
        nearest_distance=nearest,
        occluded=occluded,
        geofences=None,
        lease_holders=None,
    )


def context_changed(
    current: TrustedFacts, last: TrustedFacts | None, *, near_threshold_m: float
) -> bool:
    """True when the advisor should be asked again: first look, reasons, zone or near/far flip."""
    if last is None:
        return True
    if current.active_reasons != last.active_reasons:
        return True
    if current.zone != last.zone:
        return True
    return (current.nearest_distance < near_threshold_m) != (
        last.nearest_distance < near_threshold_m
    )


class AdvisorCaller:
    """Per tick caller of the advisor and organizer for every robot of a run."""

    def __init__(
        self,
        advisor: Advisor | None,
        *,
        robot_ids: tuple[str, ...],
        run_id: str,
        near_threshold_m: float,
        trigger_ticks: tuple[int, ...] | None,
        organizer: Organizer | None = None,
    ) -> None:
        self._advisor = advisor
        self._organizer = organizer
        self._robot_ids = robot_ids
        self._run_id = run_id
        self._near = near_threshold_m
        self._triggers = trigger_ticks
        self._last: list[TrustedFacts | None] = [None] * len(robot_ids)
        self._inbox: dict[str, list[InboundMessage]] = {r: [] for r in robot_ids}
        self.advisor_calls = 0
        self.organizer_calls = 0
        self.failures = 0
        self.rejected: dict[str, int] = {}

    def step(
        self,
        *,
        sim: Any,
        tick: int,
        rig: E5Rig,
        scenario: scenarios.Scenario,
        box: world.World,
        fleet: robots.RobotFleet,
    ) -> None:
        """Ask the advisor and/or organizer for each robot whose context changed at ``tick``."""
        for i, robot_id in enumerate(self._robot_ids):
            facts = extract_facts(
                sim, i, robot_id, scenario, box, rig.last_reasons[i], occluded=rig.occluded(i)
            )
            if self._triggers is not None:
                due = tick in self._triggers
            else:
                due = tick == 0 or context_changed(
                    facts, self._last[i], near_threshold_m=self._near
                )
            if due:
                signals = self._ask(i, facts, tick, fleet) if self._advisor is not None else ()
                if self._organizer is not None:
                    self._ask_organizer(i, facts, tick, fleet, signals)
                self._last[i] = facts

    def _ask(
        self, index: int, facts: TrustedFacts, tick: int, fleet: robots.RobotFleet
    ) -> tuple[str, ...]:
        assert self._advisor is not None
        cap = float(fleet.max_speed[index])
        try:
            result = self._advisor.advise(
                facts,
                tick=tick,
                current_cap=cap,
                class_max=cap,
                run_id=self._run_id,
                task_id=f"task-{facts.robot_id}",
                latency_ticks=0,
            )
        except (LlmError, ValueError, RuntimeError, OSError) as err:
            logger.warning("advisor failed for %s at tick %d: %s", facts.robot_id, tick, err)
            self.failures += 1
            self.advisor_calls += 1
            self.rejected[ERROR_KEY] = self.rejected.get(ERROR_KEY, 0) + 1
            return ()
        if result.status != "rate_limited":
            self.advisor_calls += 1
        if result.status == "rejected" and result.reason:
            self.rejected[result.reason] = self.rejected.get(result.reason, 0) + 1
        if (
            result.event is not None
            and result.event.action is CautionAction.ASK_ORGANIZER
            and result.event.code is not None
        ):
            return (result.event.code,)
        return ()

    def _ask_organizer(
        self,
        index: int,
        facts: TrustedFacts,
        tick: int,
        fleet: robots.RobotFleet,
        ask_signals: tuple[str, ...],
    ) -> None:
        assert self._organizer is not None
        cap = float(fleet.max_speed[index])
        inbox = list(self._inbox.get(facts.robot_id, ()))
        self._inbox[facts.robot_id] = []
        try:
            result = self._organizer.organize(
                facts,
                tick=tick,
                class_max=cap,
                run_id=self._run_id,
                task_id=f"task-{facts.robot_id}",
                ask_signals=ask_signals,
                messages=inbox,
                latency_ticks=0,
            )
        except (LlmError, ValueError, RuntimeError, OSError) as err:
            logger.warning("organizer failed for %s at tick %d: %s", facts.robot_id, tick, err)
            self.failures += 1
            self.organizer_calls += 1
            self.rejected[ORGANIZER_ERROR_KEY] = self.rejected.get(ORGANIZER_ERROR_KEY, 0) + 1
            return
        if result.status != "rate_limited":
            self.organizer_calls += 1
        if result.status in ("rejected", "tool_error") and result.reason:
            self.rejected[result.reason] = self.rejected.get(result.reason, 0) + 1
        if (
            result.outbound_message is not None
            and result.decision is not None
            and result.decision.recipient in self._inbox
        ):
            self._inbox[result.decision.recipient].append(
                InboundMessage(
                    authenticated_sender=facts.robot_id,
                    raw=result.outbound_message,
                )
            )
