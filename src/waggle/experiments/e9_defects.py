"""Hand-written planted defects for E9 (EXPERIMENTS.md, E9).

Each defect is one exact source replacement, applied only to a temporary copy of
the tree by ``waggle.experiments.e9_run``. Production source is never patched:
the point is to check that the existing tests notice a weakened safety check.
Each defect declares, before any run, the test nodes expected to catch it.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PlantedDefect:
    """One planted weakening: an exact replacement in one source file."""

    id: str
    summary: str
    source: str
    old: str
    new: str
    detectors: tuple[str, ...]


DEFECTS: Final[tuple[PlantedDefect, ...]] = (
    PlantedDefect(
        id="margin_lowered",
        summary="human separation margin lowered from 0.3 m to 0.05 m",
        source="src/waggle/control/params.py",
        old="human_margin: float = 0.3",
        new="human_margin: float = 0.05",
        detectors=(
            "tests/unit/control/test_control_envelope.py"
            "::test_separation_distance_matches_the_formula",
        ),
    ),
    PlantedDefect(
        id="cap_raises_speed",
        summary="arbiter takes the largest cap instead of the smallest",
        source="src/waggle/control/arbiter.py",
        old="allowed = min([class_cap, *(cap for cap, _ in checked)])",
        new="allowed = max([class_cap, *(cap for cap, _ in checked)])",
        detectors=(
            "tests/unit/control/test_control_arbiter.py"
            "::test_the_smallest_cap_wins_and_names_the_binding_reason",
            "tests/unit/control/test_control_arbiter.py"
            "::test_adding_a_limit_never_raises_the_speed",
        ),
    ),
    PlantedDefect(
        id="stale_scan_accepted",
        summary="scan age upper bound dropped, so a stale scan is accepted",
        source="src/waggle/control/perception.py",
        old="if not 0 <= tick - scan.tick <= pp.max_scan_age_ticks:",
        new="if not 0 <= tick - scan.tick:",
        detectors=(
            "tests/unit/control/test_control_perception.py"
            "::test_a_scan_older_than_the_limit_is_stale_and_exactly_the_limit_is_not",
        ),
    ),
    PlantedDefect(
        id="fencing_inverted",
        summary="lease token comparison inverted, so a stale holder passes",
        source="src/waggle/coordination/leases.py",
        old="and token == state.token",
        new="and token != state.token",
        detectors=(
            "tests/unit/coordination/test_leases.py"
            "::test_token_check_fails_closed_on_missing_future_and_expired_values",
        ),
    ),
)


def defect_by_id(defect_id: str) -> PlantedDefect:
    """Return the defect with this id, or raise ValueError."""
    for defect in DEFECTS:
        if defect.id == defect_id:
            return defect
    raise ValueError(f"unknown planted defect: {defect_id}")


def apply_defect(source_text: str, defect: PlantedDefect) -> str:
    """Return the source with the defect applied. The anchor must appear exactly once."""
    if source_text.count(defect.old) != 1:
        raise ValueError(f"{defect.id}: anchor not found exactly once in {defect.source}")
    return source_text.replace(defect.old, defect.new)
