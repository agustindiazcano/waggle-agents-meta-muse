"""Per-machine scoring of alerts against ground truth, in plain ticks (design section 7).

The truth (failure tick, onset tick) is passed in by the scorer. The predictor never sees it,
and this module imports nothing from the simulator. A failure with no alert strictly before
the failure tick is MISSED: a blind predictor is never counted as detected, and no fallback
threshold is credited to it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    """What happened on one machine."""

    DETECTED = "detected"
    MISSED = "missed"
    FALSE_ALARM = "false_alarm"
    QUIET = "quiet"


@dataclass(frozen=True)
class MachineScore:
    """Outcome plus lead time (failure minus alert) and detection delay (alert minus onset)."""

    outcome: Outcome
    lead_ticks: int | None = None
    detection_delay_ticks: int | None = None


def score(
    failure_tick: int | None, first_alert_tick: int | None, onset_tick: int | None = None
) -> MachineScore:
    """Score one machine. ``failure_tick`` None means it never failed in the horizon."""
    for name, tick in (
        ("failure_tick", failure_tick),
        ("first_alert_tick", first_alert_tick),
        ("onset_tick", onset_tick),
    ):
        if tick is not None and tick < 0:
            raise ValueError(f"{name} must not be negative: tick {tick}")
    if failure_tick is None:
        return MachineScore(Outcome.QUIET if first_alert_tick is None else Outcome.FALSE_ALARM)
    if onset_tick is not None and onset_tick > failure_tick:
        raise ValueError("onset must not come after the failure")
    if first_alert_tick is None or first_alert_tick >= failure_tick:
        return MachineScore(Outcome.MISSED)
    delay = None if onset_tick is None else first_alert_tick - onset_tick
    return MachineScore(Outcome.DETECTED, failure_tick - first_alert_tick, delay)


def tally(scores: Sequence[MachineScore]) -> dict[str, int]:
    """Raw counts of every outcome, zeros included. Proportions and intervals come later."""
    counts = {outcome.value: 0 for outcome in Outcome}
    for item in scores:
        counts[item.outcome.value] += 1
    return counts
