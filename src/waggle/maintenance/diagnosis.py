"""Diagnosis retrieval over the failure log (design section 6, advisory only).

Proposes a failure mode and the part that fixed the nearest past cases of that mode. It holds no
authority and calls no model: the proposal is data. The part number is checked against the
caller's catalog in code (AGENTS.md 8.7), and a part that is not in the catalog, a log with no
usable case, or supporting cases that disagree on the part all return an escalation, never a
part. An unknown candidate mode raises.
"""

import math
from collections.abc import Collection, Sequence, Set
from dataclasses import dataclass
from typing import Literal

from waggle.experiments.failure_log import FailureCase, FailureMode, similar_cases

EscalationReason = Literal["no_similar_case", "mixed_parts", "part_not_in_catalog"]
_FLOOR = 1e-9


@dataclass(frozen=True)
class DiagnosisProposal:
    """A mode, the part of its supporting cases and the ids of those cases."""

    mode: FailureMode
    part_number: str
    supporting_case_ids: tuple[str, ...]
    mean_distance: float


@dataclass(frozen=True)
class DiagnosisEscalation:
    """No proposal: a person decides. It carries no part number by design."""

    reason: EscalationReason
    mode: FailureMode | None = None


def _spread(values: Sequence[float]) -> float:
    mean = sum(values) / len(values)
    return max(_FLOOR, math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)))


def _mean_distance(
    cases: Sequence[FailureCase], log: Sequence[FailureCase], point: tuple[float, float, float]
) -> float:
    spreads = (
        _spread([c.peak_temperature_c for c in log]),
        _spread([c.peak_vibration_rms for c in log]),
        _spread([c.peak_current_a for c in log]),
    )
    total = 0.0
    for case in cases:
        peaks = (case.peak_temperature_c, case.peak_vibration_rms, case.peak_current_a)
        total += math.sqrt(
            sum(((p - q) / s) ** 2 for p, q, s in zip(peaks, point, spreads, strict=True))
        )
    return total / len(cases)


def _parse_modes(modes: Collection[FailureMode | str] | None) -> tuple[FailureMode, ...]:
    if modes is None:
        return tuple(FailureMode)
    parsed: list[FailureMode] = []
    for mode in modes:
        try:
            parsed.append(FailureMode(mode))
        except ValueError:
            raise ValueError("Invalid mode") from None
    return tuple(parsed)


def diagnose(
    log: Sequence[FailureCase],
    temperature_c: float,
    vibration_rms: float,
    current_a: float,
    catalog: Set[str],
    k: int = 5,
    modes: Collection[FailureMode | str] | None = None,
) -> DiagnosisProposal | DiagnosisEscalation:
    """Propose the mode whose k nearest past cases are closest to the reading.

    Raises ValueError for an unknown mode, a bad ``k`` or a reading that is not finite and
    non-negative. Ties go to the first mode in the order given.
    """
    candidates = _parse_modes(modes)
    point = (temperature_c, vibration_rms, current_a)
    best: tuple[float, FailureMode, tuple[FailureCase, ...]] | None = None
    for mode in candidates:
        found = similar_cases(log, mode, temperature_c, vibration_rms, current_a, k)
        if not found:
            continue
        distance = _mean_distance(found, log, point)
        if best is None or distance < best[0]:
            best = (distance, mode, found)
    if best is None:
        return DiagnosisEscalation("no_similar_case")
    distance, mode, found = best
    parts = {case.part_number for case in found}
    if len(parts) != 1:
        return DiagnosisEscalation("mixed_parts", mode)
    part = next(iter(parts))
    if part not in catalog:
        return DiagnosisEscalation("part_not_in_catalog", mode)
    return DiagnosisProposal(mode, part, tuple(c.case_id for c in found), distance)
