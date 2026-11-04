"""Synthetic failure log generator and case retrieval (ADR-020).

Parameters in ``LOG_PARAMETERS`` are assumptions, not measurements (see AGENTS.md section 4).
"""

from collections.abc import Mapping
from types import MappingProxyType

import numpy as np

from waggle.maintenance.failure_cases import FailureCase, FailureMode, similar_cases

__all__ = ["LOG_PARAMETERS", "FailureCase", "FailureMode", "generate_failure_log", "similar_cases"]

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
