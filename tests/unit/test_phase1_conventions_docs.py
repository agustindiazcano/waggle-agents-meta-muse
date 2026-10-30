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


def test_adr_021_states_2d_floor_plane_and_3d_rendering() -> None:
    adr = _adr(21)
    for term in ("floor plane", "Height is not modeled", "Three.js", "FPV"):
        assert term in adr, term
    readme = _read("README.md")
    assert "floor plane" in readme and "Height is not modeled" in readme


def test_robot_table_has_kinematic_parameters() -> None:
    text = _read("docs/ARCHITECTURE.md")
    for term in (
        "bicycle model",
        "minimum turning radius",
        "differential drive",
        "maximum angular speed",
        "load_raised",
        "swept footprint",
    ):
        assert term in text, term


def test_route_planner_is_recorded_in_plan_architecture_and_e2() -> None:
    plan = _phase("3").lower()
    assert "a*" in plan and "capacity one" in plan and "fencing" in plan
    assert "without deadlock" in plan and "s13 to s18" in plan
    assert "route planner" in _read("docs/ARCHITECTURE.md").lower()
    assert "deadlock" in _read("docs/EXPERIMENTS.md").lower()


def test_phase_1_lists_kinematics() -> None:
    phase = _phase("1").lower()
    assert "non-holonomic" in phase and "swept footprint" in phase and "load_raised" in phase


@pytest.mark.parametrize(
    "term",
    [
        "waggle.sim.params",
        "waggle.validation",
        "Comments and strings",
        "4 ticks",
        "6 ticks",
        "radius of 0.30 m",
        "maximum steering angle",
        "load_raised",
        "PICK, HANDOFF, DELIVER and DISPATCH_REPAIR",
        "belief states",
        "unavoidable_at_spawn",
    ],
)
def test_adr_021_matches_the_brief(term: str) -> None:
    assert term in _adr(21), f"ADR-021 lacks {term!r}"


def test_architecture_lists_the_sim_module_layout_and_footprints() -> None:
    text = _read("docs/ARCHITECTURE.md")
    section = text.split("## Simulator module layout", 1)[1].split("\n## ", 1)[0]
    for module in (
        "world",
        "params",
        "observations",
        "robots",
        "humans",
        "detector",
        "sensors",
        "scenarios",
        "scripted",
    ):
        assert f"`{module}`" in section, module
    assert "Footprint (length x width, m)" in text


def test_experiments_define_unavoidable_at_spawn_and_master_seed() -> None:
    text = _read("docs/EXPERIMENTS.md")
    assert "unavoidable_at_spawn" in text
    assert "fixed master seed" in text


@pytest.mark.parametrize(
    "term",
    [
        "explicit Euler",
        "v*dt/2 + a*dt^2/2",
        "n = ceil(v/(a*dt))",
        "quantization of the delay",
        "2.4 m wide",
    ],
)
def test_adr_021_derives_the_stopping_distance_bound(term: str) -> None:
    assert term in _adr(21), f"ADR-021 lacks {term!r}"


@pytest.mark.parametrize(
    "term", ["no false negatives", "0.005 rad", "brute-force fine-substep", "1.58 mm"]
)
def test_adr_021_records_the_detector_tolerance(term: str) -> None:
    assert term in _adr(21), f"ADR-021 lacks {term!r}"


def test_architecture_documents_the_lidar_defaults() -> None:
    section = _read("docs/ARCHITECTURE.md").split("## Sensing and prediction", 1)[1]
    section = section.split("\n## ", 1)[0]
    for term in ("360 rays", "12 m", "0.02 m", "dropout probability 0.01", "10 Hz", "NaN"):
        assert term in section, term


@pytest.mark.parametrize(
    "term",
    [
        "no_control",
        "0.5 m",
        "0.2 m",
        "counted as episodes",
        "waypoint driver",
        "results/e1/dev/",
        "development seeds only",
        "map A",
        "map B",
    ],
)
def test_experiments_define_the_no_control_baseline(term: str) -> None:
    text = _read("docs/EXPERIMENTS.md")
    section = text.split("## E1:", 1)[1].split("\n## ", 1)[0]
    assert term in section, f"E1 lacks {term!r}"
