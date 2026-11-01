"""E3 runners for the MCP identity and schema bounds layers, on the production boundary."""

from pathlib import Path

import pytest

from waggle.experiments import e3_mcp_layers
from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases
from waggle.experiments.e3_mcp_layers import ATTEMPTS, MCP_LAYERS, run_mcp_layers
from waggle.mcp_server import schemas
from waggle.mcp_server.bounds import CHASSIS_BOUNDS, ChassisBounds

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")
LAYER_IDS = {c.id for c in CASES if c.target_layer in MCP_LAYERS}


def test_every_case_of_the_two_layers_has_exactly_one_attempt() -> None:
    assert set(ATTEMPTS) == LAYER_IDS
    assert len(LAYER_IDS) == 7


def test_the_runnable_layers_are_the_ones_with_a_runner() -> None:
    expected = frozenset(
        {"output_schema", "mcp_identity", "mcp_schema_bounds", "catalog_check", "message_schema"}
    )
    assert expected == RUNNABLE_LAYERS


def test_the_production_boundary_blocks_every_injection_and_serves_every_benign_call() -> None:
    report = run_mcp_layers(CASES)
    assert report.missed_injections == ()
    assert report.false_blocks == ()
    assert {o.case_id for o in report.outcomes} == LAYER_IDS
    assert all(o.correct for o in report.outcomes)


def test_a_blocked_attempt_never_reaches_the_forwarder() -> None:
    report = run_mcp_layers(CASES)
    blocked = {o.case_id for o in report.outcomes if not o.forwarded}
    injections = {c.id for c in CASES if c.id in LAYER_IDS and c.label == "injection"}
    assert blocked == injections


def test_a_widened_allowlist_is_reported_as_missed_injections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schemas, "is_allowed", lambda chassis, tool: True)
    report = run_mcp_layers(CASES)
    # E3-T5-01 stays blocked: its extra robot_id field is still refused by the schema.
    assert {"E3-T1-01", "E3-T1-02"} <= set(report.missed_injections)
    assert "E3-T5-01" not in report.missed_injections


def test_a_widened_speed_bound_is_reported_as_a_missed_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wide = {name: ChassisBounds(100.0) for name in CHASSIS_BOUNDS}
    monkeypatch.setattr(schemas, "CHASSIS_BOUNDS", wide)
    report = run_mcp_layers(CASES)
    assert "E3-T2-01" in report.missed_injections


def test_a_fully_blocking_boundary_is_reported_as_false_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schemas, "is_allowed", lambda chassis, tool: False)
    report = run_mcp_layers(CASES)
    assert set(report.false_blocks) == {"E3-T1-03", "E3-T5-03", "E3-T2-03"}


def test_the_layer_names_are_the_corpus_target_layers() -> None:
    assert frozenset({"mcp_identity", "mcp_schema_bounds"}) == e3_mcp_layers.MCP_LAYERS
