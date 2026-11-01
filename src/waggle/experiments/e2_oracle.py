"""E2 oracle: violation counts computed from the event log, never from repository answers.

The inputs are the ``task_events`` rows ordered by ``event_no``, the final state of each task and
samples of trusted zone occupancy. Nothing here touches a database, a clock or a random stream, so
every count is reproducible from the same inputs (AGENTS.md 5.10). The oracle fails closed: an
event of an unknown kind, an event out of order, a task with events but no final state, or an
invalid sample raises ``OracleError`` instead of yielding a passing report. An unknown zone
occupant is counted as undecided, never as safe.

Definitions, all assumptions to review (``docs/E2_CHAOS_DESIGN.md``):

- A claim is a double assignment when the same task still has a live attempt at the claim tick.
  An attempt is live from its claim until a terminal event or recovery, and not past its expiry.
- A write (``executing``, ``done``, ``failed``, ``handoff``) is stale when no attempt is live or
  the live attempt has another token. It is an expired write when the token is the live one but
  the tick is at or past the expiry of that claim.
- A task is recovered when it had a ``recovered`` event and ended ``DONE``. Recovery time is the
  gap between the expiry of the abandoned attempt and the next claim of that task.
- A task is stuck when its final state is not terminal.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

ACTIVE = frozenset({"ASSIGNED", "EXECUTING"})
TERMINAL = frozenset({"DONE", "FAILED", "REJECTED", "ESCALATED", "ABORTED"})
_WRITES = frozenset({"executing", "done", "failed", "handoff"})
_KINDS = frozenset({"created", "advanced", "claimed", "recovered"}) | _WRITES


class OracleError(ValueError):
    """The log cannot be judged; the run is undecided and must not count as a pass."""


@dataclass(frozen=True)
class TaskEvent:
    """One ``task_events`` row, reduced to the columns the oracle reads."""

    event_no: int
    task_id: str
    kind: str
    state: str
    token: int
    worker_id: str | None
    expires_tick: int | None
    observed_tick: int


@dataclass(frozen=True)
class ZoneSample:
    """Trusted occupancy of one zone at one tick; ``robots`` is None when unknown."""

    tick: int
    zone_id: str
    robots: frozenset[str] | None
    capacity: int


@dataclass(frozen=True)
class TaskReport:
    """Counts from a task event log."""

    double_assignments: int
    stale_writes_accepted: int
    expired_writes_accepted: int
    tasks_recovered: int
    recovery_ticks: tuple[int, ...]
    tasks_stuck: tuple[str, ...]
    tasks_done: int
    tasks_total: int


@dataclass(frozen=True)
class ZoneReport:
    """Counts from zone occupancy samples."""

    violation_samples: int
    violating_ticks: tuple[int, ...]
    undecided_samples: int


@dataclass
class _Attempt:
    token: int
    expires: int


@dataclass
class _Task:
    live: _Attempt | None = None
    abandoned_expiry: int | None = None
    recovered: bool = False


def _check(events: Sequence[TaskEvent]) -> None:
    last = 0
    for event in events:
        if event.kind not in _KINDS:
            raise OracleError(f"unknown event kind: {event.kind}")
        if event.event_no <= last:
            raise OracleError("events must be in strictly increasing event_no order")
        last = event.event_no


def judge_tasks(events: Sequence[TaskEvent], final_states: Mapping[str, str]) -> TaskReport:
    """Count double assignments, stale and expired writes, recoveries and stuck tasks."""
    _check(events)
    tasks: dict[str, _Task] = {}
    double = stale = expired = 0
    recovery: list[int] = []
    for event in events:
        task = tasks.setdefault(event.task_id, _Task())
        live = task.live
        if event.kind == "claimed":
            if event.expires_tick is None:
                raise OracleError("a claimed event needs an expiry")
            if live is not None and event.observed_tick < live.expires:
                double += 1
            if task.abandoned_expiry is not None:
                recovery.append(event.observed_tick - task.abandoned_expiry)
                task.abandoned_expiry = None
            task.live = _Attempt(event.token, event.expires_tick)
            continue
        if event.kind in _WRITES:
            if live is None or live.token != event.token:
                stale += 1
            elif event.observed_tick >= live.expires:
                expired += 1
        if event.kind == "recovered":
            task.recovered = True
            task.abandoned_expiry = live.expires if live is not None else None
        if event.state not in ACTIVE:
            task.live = None
    missing = sorted(set(tasks) - set(final_states))
    if missing:
        raise OracleError("no final state for: " + ", ".join(missing))
    stuck = tuple(sorted(t for t, state in final_states.items() if state not in TERMINAL))
    recovered = sum(1 for t, task in tasks.items() if task.recovered and final_states[t] == "DONE")
    done = sum(1 for state in final_states.values() if state == "DONE")
    return TaskReport(
        double, stale, expired, recovered, tuple(recovery), stuck, done, len(final_states)
    )


def judge_zones(samples: Sequence[ZoneSample]) -> ZoneReport:
    """Count samples that hold more robots than the zone capacity."""
    ticks: list[int] = []
    undecided = 0
    for sample in samples:
        if sample.capacity < 1:
            raise OracleError(f"{sample.zone_id}: capacity must be at least 1")
        if sample.robots is None:
            undecided += 1
        elif len(sample.robots) > sample.capacity:
            ticks.append(sample.tick)
    return ZoneReport(len(ticks), tuple(ticks), undecided)
