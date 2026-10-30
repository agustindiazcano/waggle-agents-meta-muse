"""Crisis replanning design (ADR-023 to ADR-025, E10, Phase 5C) is recorded in every document."""

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


def _section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}.*?\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.S | re.M)
    assert match is not None, f"{heading} not found"
    return match.group(1)


@pytest.mark.parametrize(
    "term",
    [
        "Crisis replanning with counterexample-guided validation",
        "Status: proposed",
        "belief state",
        "K = 5",
        "H simulated seconds (default 45",
        "H/2",
        "CEGIS",
        "LLM-Modulo",
        "not formal verification",
        "COLLISION",
        "SEPARATION_VIOLATION",
        "GEOFENCE_INTRUSION",
        "CORRIDOR_DEADLOCK",
        "LEASE_CONFLICT",
        "ROUTE_INFEASIBLE",
        "NO_PROGRESS",
        "UNSAFE_TERMINAL_STATE",
        "Maximum 3 iterations",
        "at most 20",
        "corridor_zone_ids",
        "avoid_zone_ids",
        "wait_for",
        "speed_cap_mps",
        "never produced by the model",
        "never forwarded to another model",
        "never frozen",
    ],
)
def test_adr_023_records_the_design(term: str) -> None:
    assert term in _adr(23), f"ADR-023 lacks {term!r}"


@pytest.mark.parametrize(
    ("number", "terms"),
    [
        (24, ["Occlusion-aware speed cap", "phantom human", "minimum speed floor", "S_sep(v)"]),
        (
            25,
            [
                "Simulator state layout and rollout cost",
                "snapshot()",
                "from_snapshot()",
                "deepcopy",
                "pure function",
                "code speed on this machine",
            ],
        ),
    ],
)
def test_adr_024_and_025(number: int, terms: list[str]) -> None:
    adr = _adr(number)
    assert "Status: proposed" in adr
    for term in terms:
        assert term in adr, f"ADR-{number:03d} lacks {term!r}"


def test_adr_017_is_amended_with_the_e4_configurations() -> None:
    adr = _adr(17)
    assert "Amendment" in adr
    for term in ("role-specialized", "SOP compliance", "provenance and injection"):
        assert term in adr, term


def test_threat_model_has_t17_and_t18() -> None:
    text = _read("docs/THREAT_MODEL.md")
    for tid in ("T17", "T18"):
        assert re.search(rf"^\| {tid} \|", text, re.M), tid


def test_experiments_have_e10_and_the_new_e1_and_e4_configurations() -> None:
    text = _read("docs/EXPERIMENTS.md")
    e10 = _section(text, "E10")
    for term in (
        "strong deterministic recovery baseline",
        "Muse open loop",
        "Muse with validator feedback",
        "role-specialized court",
        "120 s",
        "30, 45 and 60",
        "beyond the deterministic baseline",
    ):
        assert term in e10, term
    e1 = _section(text, "E1")
    for term in ("radial 1D distance", "swept footprint plus occlusion cap", "CPA prediction"):
        assert term in e1, term
    e4 = _section(text, "E4")
    assert "role-specialized" in e4 and "non-Muse member on Vertex" in e4
    assert "FAULT_OCCUPIED" in text


def test_plan_has_phase_5c_and_the_design_notes() -> None:
    plan = _read("PLAN.md")
    phase_5c = _section(plan, "Phase 5C")
    assert "waggle.validation" in phase_5c and "E10" in phase_5c
    assert "Exit" in phase_5c
    assert "swept curvilinear" in _section(plan, "Phase 2").lower()
    phase3 = _section(plan, "Phase 3")
    assert "FAULT_OCCUPIED" in phase3 and "acquire, release, expire and stale-token" in phase3
    assert "advisory lock" in _section(plan, "Phase 4")
    assert "viewer v0" in plan.lower()


def test_architecture_has_the_replanning_sections_and_diagram_nodes() -> None:
    text = _read("docs/ARCHITECTURE.md")
    for heading in (
        "## Crisis replanning",
        "## Occlusion-aware speed cap",
        "## Plan schema",
        "## Prompt requirements",
    ):
        assert heading in text, heading
    diagram = text.split("```mermaid")[1].split("```")[0]
    for node in ("CRISIS", "VALIDATOR", "BELIEF", "ROLLOUT"):
        assert node in diagram, node
    assert "local lease view" in text.lower()
    assert "src/waggle/llm/prompts/" in text
    assert "hashtextextended" in text


def test_readme_marks_the_new_layers_and_priorities_stay() -> None:
    readme = _read("README.md")
    assert readme.count("designed, not implemented") >= 8
    assert "Crisis replanning" in readme
    assert "not formal verification" in readme.lower()


def test_pending_asks_for_the_missing_e9_definition() -> None:
    assert re.search(r"E9.*(not defined|define)", _read("PENDING.md"), re.I)
