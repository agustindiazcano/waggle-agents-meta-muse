"""Failure cases and nearest-case retrieval, shared by diagnosis and the synthetic log (ADR-079).

The types and the retrieval live in ``waggle.maintenance`` so that production code does not
import ``waggle.experiments``. The generator that fills a log stays in the experiments package.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

_CASE_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_PART_NUMBER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_MACHINE_CLASSES = frozenset({"conveyor", "pump", "lift"})


class FailureMode(StrEnum):
    """Failure mode classification for warehouse machines."""

    BEARING_WEAR = "BEARING_WEAR"
    LUBRICATION_LOSS = "LUBRICATION_LOSS"
    MISALIGNMENT = "MISALIGNMENT"


@dataclass(frozen=True)
class FailureCase:
    """Historical or synthetic record of one machine failure event."""

    case_id: str
    machine_class: str
    mode: FailureMode
    onset_to_failure_ticks: int
    peak_temperature_c: float
    peak_vibration_rms: float
    peak_current_a: float
    part_number: str

    def __post_init__(self) -> None:
        """Validate all fields and raise ValueError without echoing input values."""
        if not isinstance(self.case_id, str) or _CASE_ID_RE.fullmatch(self.case_id) is None:
            raise ValueError("Invalid case_id")

        if self.machine_class not in _MACHINE_CLASSES:
            raise ValueError("Invalid machine_class")

        if not isinstance(self.mode, FailureMode):
            raise ValueError("Invalid mode")

        if (
            not isinstance(self.onset_to_failure_ticks, int)
            or isinstance(self.onset_to_failure_ticks, bool)
            or self.onset_to_failure_ticks < 1
        ):
            raise ValueError("Invalid onset_to_failure_ticks")

        for val in (self.peak_temperature_c, self.peak_vibration_rms, self.peak_current_a):
            if (
                not isinstance(val, (int, float))
                or isinstance(val, bool)
                or not math.isfinite(val)
                or val < 0.0
            ):
                raise ValueError("Invalid peak measurement")

        if (
            not isinstance(self.part_number, str)
            or _PART_NUMBER_RE.fullmatch(self.part_number) is None
        ):
            raise ValueError("Invalid part_number")


def _population_std(values: Sequence[float]) -> float:
    """Calculate population standard deviation with a floor of 1e-9."""
    if not values:
        return 1e-9
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return max(1e-9, math.sqrt(variance))


def similar_cases(
    log: Sequence[FailureCase],
    mode: FailureMode | str,
    temperature_c: float,
    vibration_rms: float,
    current_a: float,
    k: int,
) -> tuple[FailureCase, ...]:
    """Retrieve the k nearest cases of the specified mode by normalized peak values."""
    if not isinstance(k, int) or isinstance(k, bool) or not (1 <= k <= 50):
        raise ValueError("Invalid k")

    for val in (temperature_c, vibration_rms, current_a):
        if (
            not isinstance(val, (int, float))
            or isinstance(val, bool)
            or not math.isfinite(val)
            or val < 0.0
        ):
            raise ValueError("Invalid query telemetry value")

    try:
        wanted = FailureMode(mode)
    except ValueError:
        raise ValueError("Invalid mode") from None

    matching = [case for case in log if case.mode == wanted]
    if not matching:
        return ()

    spread_t = _population_std([case.peak_temperature_c for case in log])
    spread_v = _population_std([case.peak_vibration_rms for case in log])
    spread_c = _population_std([case.peak_current_a for case in log])

    def _distance_key(case: FailureCase) -> tuple[float, str]:
        dt = (case.peak_temperature_c - temperature_c) / spread_t
        dv = (case.peak_vibration_rms - vibration_rms) / spread_v
        dc = (case.peak_current_a - current_a) / spread_c
        dist_sq = dt * dt + dv * dv + dc * dc
        return dist_sq, case.case_id

    sorted_cases = sorted(matching, key=_distance_key)
    return tuple(sorted_cases[:k])
