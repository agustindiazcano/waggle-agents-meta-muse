"""Simulation conventions (ADR-021) and the Phase 1 scope are recorded and consistent."""

import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _adr(number: int) -> str:
    pattern = rf"^## ADR-{number:03d}:.*?(?=^## ADR-|\Z)"
    match = re.search(pattern, _read("docs/DECISIONS.md"), re.S | re.M)
    assert match is not None, f"ADR-{number:03d} not found"
    return match.group(0)


def _phase(number: str) -> str:
    pattern = rf"^## Phase {number}:.*?\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, _read("PLAN.md"), re.S | re.M)
    assert match is not None
    return match.group(1)


def wilson_upper(failures: int, n: int, z: float = 1.96) -> float:
    """Upper bound of the Wilson score interval for a proportion."""
    p = failures / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre + margin) / (1 + z * z / n)


def test_wilson_upper_bounds_match_the_documented_figures() -> None:
    assert round(wilson_upper(0, 216) * 100, 1) == 1.7
    assert round(wilson_upper(0, 100) * 100, 1) == 3.7
    text = _read("docs/EXPERIMENTS.md")
    assert "216" in text and "1.7%" in text and "3.7%" in text


@pytest.mark.parametrize(
    "term",
    [
        "Status: proposed",
        "dt = 0.025",
        "40 Hz",
        "integer multiple",
        "10 Hz",
        "every 4 ticks",
        "SeedSequence",
        "default_rng",
        "uuid",
        "secrets",
        "iteration over a set",
        "canonical",
        "sorted keys",
        "golden",
        "same process",
        "numpy version",
        "closed sets",
        "exact touch",
        "disc or an oriented rectangle",
        "waggle.sim.observations",
        "leaf",
    ],
)
def test_adr_021_records_the_convention(term: str) -> None:
    adr = _adr(21)
    assert "Simulation conventions" in adr.splitlines()[0]
    assert term in adr, f"ADR-021 lacks {term!r}"


def test_phase_1_scope_is_s01_to_s18_without_telemetry() -> None:
    phase = _phase("1").lower()
    assert "s01 to s18" in phase
    assert "s19" not in phase and "s36" not in phase
    assert "telemetry generator" not in phase
    assert "dt = 0.025" in phase or "0.025" in phase


def test_phase_6_receives_the_telemetry_generator_and_later_scenarios() -> None:
    phase = _phase("6").lower()
    assert "telemetry generator" in phase
    assert "s19 to s36" in phase


def test_experiments_fix_the_seed_split() -> None:
    text = _read("docs/EXPERIMENTS.md")
    for term in (
        "5 development seeds",
        "12 held-out seeds",
        "90 development runs",
        "data/seeds.json",
    ):
        assert term in text, term


def test_readme_states_the_reproduction_scope() -> None:
    text = _read("README.md").lower()
    assert "same platform and numpy version" in text
    assert "cloud run" in text and "linux" in text
