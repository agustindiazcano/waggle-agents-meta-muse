"""waggle.experiments.e1_diagnosis: cause classification for E1 stops and collisions."""

import json
from pathlib import Path
from typing import Any

import pytest

from waggle.experiments import e1_diagnosis
from waggle.experiments.e1_diagnosis import Cause

ROOT = Path(__file__).resolve().parents[3]
TARGETS = ("S03", "S06", "S11")


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "scenario": "S06",
        "seed": 1,
        "tasks_completed": 0,
        "counts": {
            "human_collisions": 0,
            "robot_collisions": 0,
            "separation_violations": 0,
            "near_misses": 0,
        },
        "stop_episodes": {},
        "false_stops": 0,
    }
    record.update(overrides)
    return record


def _dev_seeds() -> dict[str, list[int]]:
    data: dict[str, Any] = json.loads((ROOT / "data" / "seeds.json").read_text(encoding="utf-8"))
    return {sid: [int(s) for s in data["dev"][sid]] for sid in TARGETS}


def test_s03_facts_show_a_head_on_pair_with_no_humans() -> None:
    for seed in _dev_seeds()["S03"]:
        facts = e1_diagnosis.scenario_facts("S03", seed)
        assert facts.human_count == 0
        assert facts.head_on_pair
        assert not facts.human_stopped_on_route


def test_s06_and_s11_facts_put_the_stopped_human_on_the_route() -> None:
    for sid in ("S06", "S11"):
        for seed in _dev_seeds()[sid]:
            facts = e1_diagnosis.scenario_facts(sid, seed)
            assert facts.human_count == 1
            assert facts.human_stopped_on_route
            assert facts.human_final_point == (26.0, 3.0)
            assert facts.adversarial_fraction is not None
            assert 0.5 <= facts.adversarial_fraction <= 1.5


def test_a_stopped_run_in_s03_is_a_head_on_stop_not_a_mystery() -> None:
    got = e1_diagnosis.classify_run(
        "envelope_oracle",
        _record(scenario="S03", stop_episodes={"envelope": 92}, false_stops=92),
        {"S03": [1]},
    )
    assert got.cause is Cause.HEAD_ON_ONE_LANE
    assert "one-lane" in got.evidence


def test_a_stopped_run_behind_the_s06_human_is_a_legitimate_stop() -> None:
    got = e1_diagnosis.classify_run(
        "envelope_oracle",
        _record(stop_episodes={"envelope": 53, "estop": 1}, false_stops=2),
        {"S06": [1]},
    )
    assert got.cause is Cause.HUMAN_STOPPED_ON_ROUTE
    assert got.tasks_completed == 0


def test_a_robot_collision_without_control_is_a_head_on_collision() -> None:
    record = _record(scenario="S03")
    record["counts"] = dict(record["counts"], robot_collisions=1)
    got = e1_diagnosis.classify_run("no_control", record, _dev_seeds() | {"S03": [1]})
    assert got.cause is Cause.ROBOT_ROBOT_COLLISION_HEAD_ON


def test_a_human_collision_is_split_by_the_adversarial_fraction() -> None:
    record = _record(seed=_dev_seeds()["S06"][3])  # fraction 0.597, inside stopping distance
    record["counts"] = dict(record["counts"], human_collisions=1)
    got = e1_diagnosis.classify_run("no_control", record, _dev_seeds() | {"S03": [1]})
    assert got.cause is Cause.HUMAN_COLLISION_INSIDE_STOPPING_DISTANCE

    record = _record(seed=_dev_seeds()["S06"][1])  # fraction 1.476, outside stopping distance
    record["counts"] = dict(record["counts"], human_collisions=1)
    got = e1_diagnosis.classify_run("no_control", record, _dev_seeds() | {"S03": [1]})
    assert got.cause is Cause.HUMAN_COLLISION_OUTSIDE_STOPPING_DISTANCE


def test_an_unexplained_false_stop_is_not_silently_passed() -> None:
    facts = e1_diagnosis.ScenarioFacts(
        scenario="S06",
        seed=1,
        robot_count=1,
        human_count=1,
        head_on_pair=False,
        human_final_point=(0.0, 20.0),
        human_route_distance_m=17.0,
        human_stopped_on_route=False,
        adversarial_fraction=1.2,
    )
    got = e1_diagnosis.classify_record_with_facts(
        "envelope_oracle",
        _record(scenario="S06", stop_episodes={"envelope": 1}, false_stops=1),
        facts,
    )
    assert got.cause is Cause.UNEXPLAINED_STOP


def test_a_clean_run_is_reported_as_clean() -> None:
    got = e1_diagnosis.classify_run("envelope_oracle", _record(), {"S06": [1]})
    assert got.cause is Cause.NO_STOP_OR_COLLISION


def test_missing_counts_are_an_error_not_an_empty_pass() -> None:
    with pytest.raises(ValueError, match="counts"):
        e1_diagnosis.classify_run("envelope_oracle", {"scenario": "S06", "seed": 1}, {"S06": [1]})


def test_a_seed_outside_the_development_set_is_refused() -> None:
    with pytest.raises(ValueError, match="development"):
        e1_diagnosis.classify_run(
            "envelope_oracle", _record(seed=999999999), allowed_seeds=_dev_seeds()
        )


def test_committed_dev_results_classify_with_no_unexplained_controlled_stops() -> None:
    allowed = _dev_seeds()
    summary = e1_diagnosis.summarize_committed(ROOT / "results" / "e1" / "dev", allowed)
    assert set(summary) >= set(TARGETS)
    for sid in TARGETS:
        causes = summary[sid]
        assert sum(causes.values()) == 40  # 8 configurations times 5 development seeds
    controlled_stops = summary["S03"][Cause.HEAD_ON_ONE_LANE.name]
    assert controlled_stops == 35  # 7 controlled configurations, no_control has no stops
    assert summary["S06"][Cause.HUMAN_STOPPED_ON_ROUTE.name] == 35
    assert summary["S11"][Cause.HUMAN_STOPPED_ON_ROUTE.name] == 35
    assert Cause.UNEXPLAINED_STOP.name not in summary["S03"]
    assert Cause.UNEXPLAINED_STOP.name not in summary["S06"]
