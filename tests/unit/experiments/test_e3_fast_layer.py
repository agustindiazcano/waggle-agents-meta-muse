"""E3 runner for the fast layer: an untrusted text cannot widen what the reflex layer allows."""

from pathlib import Path

from waggle.control.types import ControlRequest, Limit, Reason
from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases
from waggle.experiments.e3_fast_layer import (
    FAST_LAYER,
    HAZARD_READING,
    REQUEST,
    run_fast_layer,
)
from waggle.sim.observations import RobotOdometry
from waggle.sim.params import RobotParams

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")
LAYER_IDS = {c.id for c in CASES if c.target_layer == FAST_LAYER}


def test_the_fast_layer_has_exactly_the_sop_widening_case() -> None:
    assert {"E3-T2-02"} == LAYER_IDS


def test_the_fast_layer_is_runnable() -> None:
    assert FAST_LAYER in RUNNABLE_LAYERS


def test_the_trusted_geofence_still_caps_speed_whatever_the_text_says() -> None:
    report = run_fast_layer(CASES)
    (outcome,) = report.outcomes
    assert outcome.case_id == "E3-T2-02"
    assert not outcome.forwarded
    assert outcome.code == Reason.GEOFENCE.value
    assert report.missed_injections == ()


def test_a_limiter_that_ignores_the_geofence_reports_the_missed_injection() -> None:
    # Sensitivity: if the cap does not drop below the request, the injection counts as forwarded.
    def blind(request: ControlRequest, p: RobotParams, odom: RobotOdometry) -> Limit:
        return Limit(p.max_speed, Reason.GEOFENCE)

    report = run_fast_layer(CASES, limiter=blind)
    assert report.missed_injections == ("E3-T2-02",)


def test_the_request_is_faster_than_the_cap_so_the_check_can_fail() -> None:
    assert REQUEST.speed > 0.0
    assert HAZARD_READING.value >= HAZARD_READING.critical
