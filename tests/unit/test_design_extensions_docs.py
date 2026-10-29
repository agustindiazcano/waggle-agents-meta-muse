"""Sensing, missions and failure-history designs are recorded in every document."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARK = "designed, not implemented"


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _adr(number: int) -> str:
    match = re.search(
        rf"^## ADR-{number:03d}:.*?(?=^## ADR-|\Z)", _read("docs/DECISIONS.md"), re.S | re.M
    )
    assert match is not None, f"ADR-{number:03d} not found"
    return match.group(0)


@pytest.mark.parametrize(
    ("number", "title", "terms"),
    [
        (
            18,
            "Sensing model and predictive caution",
            ["lidar", "closest point of approach", "floor"],
        ),
        (19, "Missions and handoff", ["idempotency key", "rendezvous", "fencing"]),
        (20, "Failure history and purchase orders", ["create_purchase_order", "catalog", "never"]),
    ],
)
def test_adr_is_proposed_with_its_key_terms(number: int, title: str, terms: list[str]) -> None:
    adr = _adr(number)
    assert title in adr.splitlines()[0]
    assert "Status: proposed" in adr
    for term in terms:
        assert term in adr, f"ADR-{number:03d} lacks {term!r}"


def test_architecture_has_new_sections_tool_and_tables() -> None:
    text = _read("docs/ARCHITECTURE.md")
    for heading in ("## Sensing and prediction", "## Missions and handoff"):
        assert heading in text
    for name in ("failure_history", "purchase_orders", "create_purchase_order"):
        assert name in text
    diagram = text.split("```mermaid")[1].split("```")[0]
    for node in ("LIDAR", "PRED", "HANDOFF", "create_purchase_order"):
        assert node in diagram, f"diagram lacks {node}"


def test_plan_phases_carry_the_new_work() -> None:
    plan = _read("PLAN.md")
    pattern = r"^## Phase (\w+):.*?\n(.*?)(?=^## |\Z)"
    phase = {m.group(1): m.group(2).lower() for m in re.finditer(pattern, plan, re.S | re.M)}
    assert "lidar" in phase["1"] and "s01 to s36" in phase["1"]
    assert "closest point of approach" in phase["2"] and "e1 ablation reported" in phase["2"]
    assert "handoff" in phase["3"]
    assert "failure log" in phase["6"] and "create_purchase_order" in phase["6"]


def test_experiments_cover_new_configurations_and_scenarios() -> None:
    text = _read("docs/EXPERIMENTS.md")
    for term in (
        "lidar with beacons",
        "envelope with prediction",
        "Wilson",
        "near-misses",
        "false stops",
        "Coordinated handoff",
        "double deliveries",
        "double repair starts",
        "duplicate purchase orders",
        "without the failure history",
    ):
        assert term in text, term
    for n in range(31, 37):
        assert f"S{n}" in text, f"S{n} missing"
    assert "S01 to S30" not in text


def test_threat_model_has_t14_to_t16() -> None:
    text = _read("docs/THREAT_MODEL.md")
    for tid in ("T14", "T15", "T16"):
        assert re.search(rf"^\| {tid} \|", text, re.M), tid


def test_readme_marks_new_elements_not_implemented() -> None:
    text = _read("README.md")
    assert text.count(MARK) >= 3
    assert "lidar is simulated" in text.lower()
    assert "not in the control loop" in text.lower()


def test_pending_asks_for_numpy_approval() -> None:
    assert re.search(r"numpy.*runtime dependency", _read("PENDING.md"), re.I)
