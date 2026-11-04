"""Tests for the E5 runner (ADVISORS_DESIGN sections 11 to 14).

Target layer: fast-layer extra-cap input and organizer boundary.
All tests run offline on scripted and mock providers with no network and no keys.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e5_advisors import (
    E5Runner,
    RunSpec,
    UnsupportedConfigurationError,
    dev_pairs,
    dev_seeds,
    run_one,
    validate_result_document,
    write_result_file,
)
from waggle.governance.advisor_input import AdvisorInputLimits
from waggle.governance.caution import CautionConfig
from waggle.governance.classifier import MockClassifier

SEED_S01 = 419688070  # First development seed of S01
SHORT_TICKS = 25

VALID_SLOW = '{"action":"slow","speed_cap":0.2,"duration_ticks":50,"code":null}'
VALID_NONE = '{"action":"none","speed_cap":null,"duration_ticks":null,"code":null}'
VALID_ASK_YIELD = '{"action":"ask_organizer","speed_cap":null,"duration_ticks":null,"code":"yield"}'
WIDENING = '{"action":"slow","speed_cap":5.0,"duration_ticks":50,"code":null}'
ORG_YIELD = (
    '{"action":"yield_hold","duration_ticks":20,"tool":null,'
    '"arguments":null,"recipient":null,"status":null}'
)
ORG_NONE = (
    '{"action":"none","duration_ticks":null,"tool":null,'
    '"arguments":null,"recipient":null,"status":null}'
)

CAUTION_CFG = CautionConfig(max_window_ticks=100, h_max_ticks=50, n_max_holds=3)
INPUT_LIMITS = AdvisorInputLimits(
    max_prompt_chars=2000,
    min_interval_ticks=5,
    max_calls_per_task=10,
    max_messages=5,
)
CLASSIFIER = MockClassifier(response='{"label":"benign","reason_code":"ok"}')


def _make_runner(
    timeout_s: float = 2.0,
    rate_limit_ticks: int = 5,
    max_response_chars: int = 1024,
) -> E5Runner:
    return E5Runner(
        caution_config=CAUTION_CFG,
        input_limits=INPUT_LIMITS,
        timeout_s=timeout_s,
        rate_limit_ticks=rate_limit_ticks,
        max_response_chars=max_response_chars,
        near_threshold_m=3.0,
        classifier=CLASSIFIER,
        base_config=BY_NAME["envelope_oracle"],
    )


def test_c0_and_c1_silent_advisor_give_same_trajectory() -> None:
    runner = _make_runner()
    spec_c0 = RunSpec(
        config="C0",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
    )
    spec_c1 = RunSpec(
        config="C1",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        provider_script={"advisor": VALID_NONE},
    )
    record_c0 = runner.run_one(spec_c0)
    record_c1 = runner.run_one(spec_c1)

    assert record_c0["final_hash"] == record_c1["final_hash"]
    assert record_c0["distance_m"] == record_c1["distance_m"]
    assert record_c1["widening_ticks"] == 0
    assert record_c1["cautions_issued"] == 0


def test_scripted_caution_lowers_speed_and_widening_is_zero() -> None:
    runner = _make_runner()
    spec_c0 = RunSpec(
        config="C0",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
    )
    spec_c1 = RunSpec(
        config="C1",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        provider_script={"advisor": VALID_SLOW},
    )
    record_c0 = runner.run_one(spec_c0)
    record_c1 = runner.run_one(spec_c1)

    assert record_c1["widening_ticks"] == 0
    assert record_c1["cautions_issued"] > 0
    assert record_c1["distance_m"] < record_c0["distance_m"]
    assert record_c1["speed_sums"]["limited"] < record_c0["speed_sums"]["limited"]


def test_scripted_widening_is_rejected_and_counted_by_reason() -> None:
    runner = _make_runner()
    spec_c1 = RunSpec(
        config="C1",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        provider_script={"advisor": WIDENING},
    )
    record_c1 = runner.run_one(spec_c1)

    assert record_c1["widening_ticks"] == 0
    assert record_c1["cautions_issued"] == 0
    assert record_c1["cautions_rejected"].get("widening", 0) > 0


def test_c1_replay_matches_digest_and_counts_of_c1_run() -> None:
    runner = _make_runner()
    spec_c1 = RunSpec(
        config="C1",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        provider_script={"advisor": VALID_SLOW},
    )
    record_c1 = runner.run_one(spec_c1)
    replay_log = record_c1["caution_log_jsonl"]
    assert replay_log

    spec_replay = RunSpec(
        config="C1_REPLAY",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        replay_log=replay_log,
    )
    record_replay = runner.run_one(spec_replay)

    assert record_replay["event_log_digest"] == record_c1["event_log_digest"]
    assert record_replay["counts"] == record_c1["counts"]
    assert record_replay["final_hash"] == record_c1["final_hash"]
    assert record_replay["distance_m"] == record_c1["distance_m"]
    assert record_replay["widening_ticks"] == 0


def test_c2_organizer_only_and_c3_combined_and_c3_replay_match() -> None:
    runner = _make_runner()
    spec_c0 = RunSpec(config="C0", scenario="S01", seed=SEED_S01, ticks=SHORT_TICKS)
    spec_c2 = RunSpec(
        config="C2",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        provider_script={"organizer": ORG_YIELD},
    )
    spec_c3 = RunSpec(
        config="C3",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        provider_script={"advisor": VALID_ASK_YIELD, "organizer": ORG_YIELD},
    )
    record_c0 = runner.run_one(spec_c0)
    record_c2 = runner.run_one(spec_c2)
    record_c3 = runner.run_one(spec_c3)

    assert record_c2["widening_ticks"] == 0
    assert record_c2["organizer_calls"] > 0
    assert record_c2["advisor_calls"] == 0
    assert record_c2["cautions_issued"] > 0
    assert record_c2["distance_m"] < record_c0["distance_m"]

    assert record_c3["widening_ticks"] == 0
    assert record_c3["advisor_calls"] > 0
    assert record_c3["organizer_calls"] > 0
    assert record_c3["cautions_issued"] > 0

    spec_c3_replay = RunSpec(
        config="C3_REPLAY",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        replay_log=record_c3["caution_log_jsonl"],
    )
    record_c3_replay = runner.run_one(spec_c3_replay)
    assert record_c3_replay["event_log_digest"] == record_c3["event_log_digest"]
    assert record_c3_replay["final_hash"] == record_c3["final_hash"]
    assert record_c3_replay["distance_m"] == record_c3["distance_m"]
    assert record_c3_replay["widening_ticks"] == 0


def test_c4_fleet_planner_raises_typed_error() -> None:
    runner = _make_runner()
    spec = RunSpec(config="C4", scenario="S01", seed=SEED_S01, ticks=SHORT_TICKS)
    with pytest.raises(UnsupportedConfigurationError):
        runner.run_one(spec)


def test_unknown_scenario_or_seed_raises() -> None:
    runner = _make_runner()
    spec_unknown_scenario = RunSpec(config="C0", scenario="S99", seed=SEED_S01, ticks=SHORT_TICKS)
    with pytest.raises(ValueError, match="unknown scenario"):
        runner.run_one(spec_unknown_scenario)

    spec_unknown_seed = RunSpec(config="C0", scenario="S01", seed=999999999, ticks=SHORT_TICKS)
    with pytest.raises(ValueError, match="unknown seed"):
        runner.run_one(spec_unknown_seed)


def test_runner_never_reads_held_out_seed_list(tmp_path: Path) -> None:
    fake_seeds = {
        "dev": {"S01": [1001, 1002]},
    }
    fake_file = tmp_path / "seeds.json"
    fake_file.write_text(json.dumps(fake_seeds), encoding="utf-8")

    loaded_seeds = dev_seeds("S01", seeds_path=fake_file)
    assert loaded_seeds == [1001, 1002]

    pairs = dev_pairs(["S01"], seeds_path=fake_file)
    assert pairs == [("S01", 1001), ("S01", 1002)]


def test_result_file_has_every_required_field_and_bad_field_fails(tmp_path: Path) -> None:
    valid_doc: dict[str, Any] = {
        "commit": "abc1234",
        "seed_set": "dev",
        "configuration_id": "C1",
        "prompt_version": "advisor-v1",
        "prompt_hash": "dummyhash",
        "provider_mode": "mock",
        "fallback_flag": False,
        "event_log_digest": "dummy_digest",
        "per_seed_outcomes": [],
        "rejected_counts_by_reason": {},
        "call_counts": 0,
        "date": "2026-11-03T00:00:00Z",
    }
    target_path = tmp_path / "test_result.json"
    write_result_file(target_path, valid_doc)
    assert target_path.exists()

    content = json.loads(target_path.read_text(encoding="utf-8"))
    assert content["configuration_id"] == "C1"

    # Missing field must fail validation
    invalid_doc = dict(valid_doc)
    del invalid_doc["event_log_digest"]
    with pytest.raises(ValueError, match="missing required field"):
        validate_result_document(invalid_doc)

    with pytest.raises(ValueError, match="missing required field"):
        write_result_file(tmp_path / "invalid.json", invalid_doc)


def test_forced_provider_failure_window_completes_with_zero_widening() -> None:
    runner = _make_runner()
    spec = RunSpec(
        config="C1",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
        provider_script={"advisor": VALID_SLOW},
        failure_window=(0, 15),
    )
    record = runner.run_one(spec)

    assert record["widening_ticks"] == 0
    assert record["advisor_calls"] > 0


def test_runner_validates_parameters() -> None:
    with pytest.raises(ValueError, match="timeout_s must be finite and positive"):
        _make_runner(timeout_s=-1.0)

    with pytest.raises(ValueError, match="rate_limit_ticks must be non-negative"):
        _make_runner(rate_limit_ticks=-5)

    with pytest.raises(ValueError, match="max_response_chars must be positive"):
        _make_runner(max_response_chars=0)


def test_module_level_run_one_executes() -> None:
    spec = RunSpec(
        config="C0",
        scenario="S01",
        seed=SEED_S01,
        ticks=SHORT_TICKS,
    )
    record = run_one(
        spec,
        caution_config=CAUTION_CFG,
        input_limits=INPUT_LIMITS,
        timeout_s=2.0,
        rate_limit_ticks=5,
        max_response_chars=1024,
        near_threshold_m=3.0,
        classifier=CLASSIFIER,
        base_config=BY_NAME["envelope_oracle"],
    )
    assert record["config"] == "C0"
    assert record["widening_ticks"] == 0


def test_the_reasons_given_to_the_advisor_are_fast_layer_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The draft passed a track id as a reason. Only a Reason value or REQUEST is valid."""
    from waggle.control.types import Reason
    from waggle.llm import advisor_runtime

    seen: list[tuple[str, ...]] = []
    original = advisor_runtime.AdvisorRuntime.advise

    def spy(self: Any, facts: Any, **kwargs: Any) -> Any:
        seen.append(tuple(facts.active_reasons))
        return original(self, facts, **kwargs)

    monkeypatch.setattr(advisor_runtime.AdvisorRuntime, "advise", spy)
    runner = _make_runner()
    runner.run_one(
        RunSpec(
            "C1",
            "S01",
            SEED_S01,
            provider_script=VALID_NONE,
            ticks=SHORT_TICKS,
            trigger_ticks=(0, 10, 20),
        )
    )
    allowed = {r.value for r in Reason} | {"REQUEST"}
    assert seen
    assert all(reason in allowed for reasons in seen for reason in reasons)
