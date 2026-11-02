"""Synthetic failure log generator and case retrieval (ADR-020).

Parameters in ``LOG_PARAMETERS`` are assumptions, not measurements (see AGENTS.md section 4).
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

import numpy as np

_CASE_ID_RE = re.compile(r"^fl-\d+$")
_PART_NUMBER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_MACHINE_CLASSES = frozenset({"conveyor", "pump", "lift"})

LOG_PARAMETERS: Mapping[str, float] = MappingProxyType(
    {
        "LOG_TICKS_MU": 6.73,
        "LOG_TICKS_SIGMA": 0.43,
        "LOG_TEMP_BASE_C": 51.3,
        "LOG_TEMP_BEARING_SHIFT_C": 23.7,
        "LOG_TEMP_LUBE_SHIFT_C": 31.4,
        "LOG_TEMP_MISALIGN_SHIFT_C": 13.9,
        "LOG_TEMP_NOISE_SIGMA_C": 2.87,
        "LOG_VIB_BASE_RMS": 2.63,
        "LOG_VIB_BEARING_SHIFT_RMS": 4.19,
        "LOG_VIB_LUBE_SHIFT_RMS": 2.37,
        "LOG_VIB_MISALIGN_SHIFT_RMS": 3.71,
        "LOG_VIB_NOISE_SIGMA_RMS": 0.39,
        "LOG_CURR_BASE_A": 4.33,
        "LOG_CURR_BEARING_SHIFT_A": 2.67,
        "LOG_CURR_LUBE_SHIFT_A": 1.41,
        "LOG_CURR_MISALIGN_SHIFT_A": 3.89,
        "LOG_CURR_NOISE_SIGMA_A": 0.47,
    }
)


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


def generate_failure_log(seed: int, count: int) -> tuple[FailureCase, ...]:
    """Generate a deterministic synthetic failure log."""
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("Invalid seed")

    if not isinstance(count, int) or isinstance(count, bool) or not (1 <= count <= 10000):
        raise ValueError("Invalid count")

    bit_generator = np.random.PCG64(np.random.SeedSequence([seed, 20]))
    rng = np.random.Generator(bit_generator)

    machine_classes = ("conveyor", "pump", "lift")
    modes = (
        FailureMode.BEARING_WEAR,
        FailureMode.LUBRICATION_LOSS,
        FailureMode.MISALIGNMENT,
    )

    cases: list[FailureCase] = []
    for i in range(count):
        case_id = f"fl-{i:05d}"
        machine_class = machine_classes[int(rng.integers(0, 3))]
        mode = modes[int(rng.integers(0, 3))]

        raw_ticks = int(
            rng.lognormal(
                mean=LOG_PARAMETERS["LOG_TICKS_MU"],
                sigma=LOG_PARAMETERS["LOG_TICKS_SIGMA"],
            )
        )
        onset_to_failure_ticks = max(1, raw_ticks)

        if mode == FailureMode.BEARING_WEAR:
            t_shift = LOG_PARAMETERS["LOG_TEMP_BEARING_SHIFT_C"]
            v_shift = LOG_PARAMETERS["LOG_VIB_BEARING_SHIFT_RMS"]
            c_shift = LOG_PARAMETERS["LOG_CURR_BEARING_SHIFT_A"]
            part_number = "PART-BRG-01"
        elif mode == FailureMode.LUBRICATION_LOSS:
            t_shift = LOG_PARAMETERS["LOG_TEMP_LUBE_SHIFT_C"]
            v_shift = LOG_PARAMETERS["LOG_VIB_LUBE_SHIFT_RMS"]
            c_shift = LOG_PARAMETERS["LOG_CURR_LUBE_SHIFT_A"]
            part_number = "PART-LUB-01"
        else:
            t_shift = LOG_PARAMETERS["LOG_TEMP_MISALIGN_SHIFT_C"]
            v_shift = LOG_PARAMETERS["LOG_VIB_MISALIGN_SHIFT_RMS"]
            c_shift = LOG_PARAMETERS["LOG_CURR_MISALIGN_SHIFT_A"]
            part_number = "PART-ALN-01"

        raw_temp = float(
            rng.normal(
                LOG_PARAMETERS["LOG_TEMP_BASE_C"] + t_shift,
                LOG_PARAMETERS["LOG_TEMP_NOISE_SIGMA_C"],
            )
        )
        raw_vib = float(
            rng.normal(
                LOG_PARAMETERS["LOG_VIB_BASE_RMS"] + v_shift,
                LOG_PARAMETERS["LOG_VIB_NOISE_SIGMA_RMS"],
            )
        )
        raw_curr = float(
            rng.normal(
                LOG_PARAMETERS["LOG_CURR_BASE_A"] + c_shift,
                LOG_PARAMETERS["LOG_CURR_NOISE_SIGMA_A"],
            )
        )

        cases.append(
            FailureCase(
                case_id=case_id,
                machine_class=machine_class,
                mode=mode,
                onset_to_failure_ticks=onset_to_failure_ticks,
                peak_temperature_c=max(0.0, raw_temp),
                peak_vibration_rms=max(0.0, raw_vib),
                peak_current_a=max(0.0, raw_curr),
                part_number=part_number,
            )
        )

    return tuple(cases)


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
