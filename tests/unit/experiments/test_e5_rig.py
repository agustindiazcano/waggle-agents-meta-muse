"""The E5 rig must not change a run when no advisor is attached."""

import dataclasses
from typing import Any

import pytest

from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e5_advisors import E5Runner, RunSpec
from waggle.governance.advisor_input import AdvisorInputLimits
from waggle.governance.caution import CautionConfig
from waggle.governance.classifier import MockClassifier

SEED_S01 = 419688070  # First development seed of S01
SHORT_TICKS = 25
CAUTION_CFG = CautionConfig(max_window_ticks=100, h_max_ticks=50, n_max_holds=3)
INPUT_LIMITS = AdvisorInputLimits(
    max_prompt_chars=2000, min_interval_ticks=5, max_calls_per_task=10, max_messages=5
)
CLASSIFIER = MockClassifier(response='{"label":"benign","reason_code":"ok"}')


def test_c0_without_advisor_equals_the_e1_run_of_the_same_configuration() -> None:
    """The E5 rig copies the E1 rig step. With no advisor they must give the same run."""
    from waggle.experiments import e1_run

    name = "envelope_occlusion_cpa_lidar_beacons"
    runner = E5Runner(
        caution_config=CAUTION_CFG,
        input_limits=INPUT_LIMITS,
        timeout_s=2.0,
        rate_limit_ticks=5,
        max_response_chars=1024,
        near_threshold_m=3.0,
        classifier=CLASSIFIER,
        base_config=BY_NAME[name],
    )
    e5 = runner.run_one(RunSpec("C0", "S01", SEED_S01, ticks=SHORT_TICKS))
    e1 = e1_run.run_one(e1_run.RunSpec(name, "S01", SEED_S01, ticks=SHORT_TICKS))
    assert e5["final_hash"] == e1["final_hash"]
    assert e5["counts"] == e1["counts"]
    assert e5["stop_episodes"] == e1["stop_episodes"]


def test_the_widening_counter_counts_a_planted_widening(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every other test asserts 0, so none would notice a counter that never counts."""
    from waggle.experiments import e5_rig

    real = e5_rig.control_step  # type: ignore[attr-defined]

    def widening(state: Any, inputs: Any, *, advisor_limits: Any) -> Any:
        new_state, out = real(state, inputs, advisor_limits=advisor_limits)
        if advisor_limits:
            out = dataclasses.replace(out, speed=out.speed + 100.0)
        return new_state, out

    monkeypatch.setattr(e5_rig, "control_step", widening)
    runner = E5Runner(
        caution_config=CAUTION_CFG,
        input_limits=INPUT_LIMITS,
        timeout_s=2.0,
        rate_limit_ticks=5,
        max_response_chars=1024,
        near_threshold_m=3.0,
        classifier=CLASSIFIER,
        base_config=BY_NAME["envelope_occlusion_cpa_lidar_beacons"],
    )
    slow = '{"action":"slow","speed_cap":0.2,"duration_ticks":50,"code":null}'
    record = runner.run_one(
        RunSpec("C1", "S01", SEED_S01, provider_script=slow, ticks=SHORT_TICKS, trigger_ticks=(0,))
    )
    assert record["widening_ticks"] > 0
