"""Phase 2 design (ADR-026 to ADR-028, E1 configurations, control layout) is recorded everywhere."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CONFIGURATIONS = [
    "no_control",
    "radial_lidar",
    "envelope_oracle",
    "envelope_lidar",
    "envelope_lidar_beacons",
    "envelope_occlusion_lidar",
    "envelope_occlusion_cpa_lidar",
    "envelope_occlusion_cpa_lidar_beacons",
]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _adr(number: int) -> str:
    pattern = rf"^## ADR-{number:03d}:.*?(?=^## ADR-|\Z)"
    match = re.search(pattern, _read("docs/DECISIONS.md"), re.S | re.M)
    assert match is not None, f"ADR-{number:03d} not found"
    return match.group(0)


@pytest.mark.parametrize(
    ("number", "title", "terms"),
    [
        (
            26,
            "Perception and tracking",
            ["LidarScan", "RobotOdometry", "stale", "cluster", "track", "fails closed", "NaN"],
        ),
        (
            27,
            "Control interface and limit arbitration",
            ["ControlOutput", "minimum", "never raises", "reason", "curvature", "fail closed"],
        ),
        (
            28,
            "E1 metrics and the eight configurations",
            ["false stop", "throughput", "code latency", "Wilson", "development seeds", "ablation"],
        ),
    ],
)
def test_adr_is_proposed_with_its_key_terms(number: int, title: str, terms: list[str]) -> None:
    adr = _adr(number)
    assert title in adr.splitlines()[0]
    assert "Status: proposed" in adr
    for term in terms:
        assert term in adr, f"ADR-{number:03d} lacks {term!r}"


@pytest.mark.parametrize("name", CONFIGURATIONS)
def test_every_configuration_is_named_in_adr_028_and_e1(name: str) -> None:
    assert name in _adr(28), f"ADR-028 lacks {name}"
    assert name in _read("docs/EXPERIMENTS.md"), f"EXPERIMENTS.md lacks {name}"


def test_architecture_lists_the_control_modules() -> None:
    text = _read("docs/ARCHITECTURE.md")
    assert "## Control module layout" in text
    for module in ["types", "perception", "tracking", "envelope", "occlusion", "cpa", "arbiter"]:
        assert f"| `{module}` |" in text, f"control module {module} missing"


def test_plan_phase_2_lists_the_branches_b11_to_b17() -> None:
    text = _read("PLAN.md")
    start = text.index("## Phase 2: Fast control layer")
    phase = text[start : text.index("## Phase 3", start)]
    for branch in [
        "docs/phase2-design",
        "feat/control-envelope",
        "feat/control-tracking",
        "feat/control-occlusion",
        "feat/control-cpa",
        "feat/control-reflex",
        "feat/e1-harness",
    ]:
        assert branch in phase, f"{branch} missing from Phase 2"
