"""E2 handoff oracle: double deliveries and early unblocking, counted from the task event log.

It complements ``waggle.experiments.e2_oracle`` and does not edit it. The input is the same
``task_events`` rows, so every count is reproducible from the log and never from what a repository
answered. The oracle fails closed: events out of order, or a claim without an expiry, raise
``OracleError`` and the run is undecided, never a pass.

Definitions, all assumptions to review (``docs/E2_CHAOS_DESIGN.md``):

- An attempt is live from its claim until an event leaves the ASSIGNED and EXECUTING states.
- A handoff event is stale when no attempt is live or the live attempt has another token.
- A double delivery is an accepted handoff that is not the first one for its task, or a stale
  handoff while another attempt is live: two runners then both believed they delivered.
- A dependent task is unblocked early when it is claimed after an accepted stale handoff of the
  task it depends on, because the dependency was marked done by a superseded attempt.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from waggle.experiments.e2_oracle import ACTIVE, OracleError, TaskEvent


@dataclass(frozen=True)
class HandoffReport:
    """Counts from the handoff events of one log."""

    double_deliveries: int
    stale_handoffs_accepted: int
    dependents_unblocked_early: int
    handoffs_accepted: int


def _check(events: Sequence[TaskEvent]) -> None:
    last = 0
    for event in events:
        if event.event_no <= last:
            raise OracleError("events must be in strictly increasing event_no order")
        last = event.event_no
        if event.kind == "claimed" and event.expires_tick is None:
            raise OracleError("a claimed event needs an expiry")


def judge_handoffs(events: Sequence[TaskEvent], dependencies: Mapping[str, str]) -> HandoffReport:
    """Count double deliveries, stale handoffs and dependents claimed after a stale handoff.

    ``dependencies`` maps a dependent task to the task it waits for.
    """
    _check(events)
    live: dict[str, int] = {}
    accepted: dict[str, int] = {}
    tainted: set[str] = set()
    double = stale = early = total = 0
    for event in events:
        current = live.get(event.task_id)
        if event.kind == "claimed":
            if dependencies.get(event.task_id) in tainted:
                early += 1
            live[event.task_id] = event.token
            continue
        if event.kind == "handoff":
            total += 1
            accepted[event.task_id] = accepted.get(event.task_id, 0) + 1
            is_stale = current is None or current != event.token
            if is_stale:
                stale += 1
                tainted.add(event.task_id)
            if accepted[event.task_id] > 1 or (is_stale and current is not None):
                double += 1
        if event.state not in ACTIVE:
            live.pop(event.task_id, None)
    return HandoffReport(double, stale, early, total)
