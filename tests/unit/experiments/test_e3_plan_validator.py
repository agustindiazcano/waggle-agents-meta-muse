"""E3 runner for the plan validator layer, geofence check only (ADR-060)."""

from pathlib import Path

from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases
from waggle.experiments.e3_plan_validator import (
    HAZARD,
    PLANS,
    VALIDATOR_LAYER,
    run_plan_validator,
)
from waggle.validation.geofence import Counterexample
from waggle.validation.plan import Plan

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")
LAYER_IDS = {c.id for c in CASES if c.target_layer == VALIDATOR_LAYER}


def test_every_validator_case_has_exactly_one_plan_fixture() -> None:
    assert set(PLANS) == LAYER_IDS
    assert len(LAYER_IDS) == 2


def test_the_validator_layer_is_runnable() -> None:
    assert VALIDATOR_LAYER in RUNNABLE_LAYERS


def test_the_route_through_the_hazard_is_blocked_and_the_detour_is_served() -> None:
    report = run_plan_validator(CASES)
    by_id = {o.case_id: o for o in report.outcomes}
    assert not by_id["E3-T18-01"].forwarded
    assert by_id["E3-T18-01"].code == "GEOFENCE_INTRUSION"
    assert by_id["E3-T18-04"].forwarded
    assert report.missed_injections == () and report.false_blocks == ()


def test_a_checker_that_finds_nothing_reports_the_missed_injection() -> None:
    # Sensitivity: a validator that never reports a counterexample lets the route through.
    def blind(plan: Plan, hazard: frozenset[str]) -> tuple[Counterexample, ...]:
        return ()

    assert run_plan_validator(CASES, checker=blind).missed_injections == ("E3-T18-01",)


def test_a_checker_that_blocks_everything_reports_the_benign_false_block() -> None:
    def paranoid(plan: Plan, hazard: frozenset[str]) -> tuple[Counterexample, ...]:
        return (Counterexample("GEOFENCE_INTRUSION", "n1", "Z1"),)

    assert run_plan_validator(CASES, checker=paranoid).false_blocks == ("E3-T18-04",)


def test_the_hazard_is_the_trusted_zone_of_the_case_setup() -> None:
    assert frozenset({"Z1"}) == HAZARD
