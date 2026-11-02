"""Cloud-only: the handoff chaos scenes S31 to S35 in both arms against PostgreSQL."""

from typing import cast

import pytest

from waggle.db.connection import Database
from waggle.experiments.e2_faults import KillPoint, ReplayMode
from waggle.experiments.e2_handoff import METRICS, run_fresh
from waggle.experiments.e2_handoff_scenes import SCENES, plan_for

pytestmark = pytest.mark.heavy

SEEDS = range(6)


def _run(database: Database, arm: str, scene: str, seed: int) -> dict[str, object]:
    return run_fresh(Database(database.dsn), arm, scene, seed)


def _report(record: dict[str, object]) -> dict[str, int]:
    assert record["undecided"] is False, record["reason"]
    return cast(dict[str, int], record["report"])


def _outcomes(record: dict[str, object]) -> dict[str, bool]:
    return cast(dict[str, bool], record["outcomes"])


@pytest.mark.parametrize("scene", SCENES)
def test_production_counts_nothing_in_every_scene(database: Database, scene: str) -> None:
    for seed in SEEDS:
        report = _report(_run(database, "fenced", scene, seed))
        assert {name: report[name] for name in METRICS} == dict.fromkeys(METRICS, 0), seed


def test_production_finishes_every_delivery_it_can(database: Database) -> None:
    for scene, expected in (("S31", 1), ("S32", 1), ("S34", 2), ("S35", 1)):
        for seed in SEEDS:
            assert _report(_run(database, "fenced", scene, seed))["tasks_done"] == expected, seed
    for seed in SEEDS:
        assert _report(_run(database, "fenced", "S33", seed))["tasks_done"] == 2, seed


def test_baseline_double_delivers_when_a_stale_runner_resumes(database: Database) -> None:
    for seed in SEEDS:
        record = _run(database, "baseline", "S35", seed)
        report = _report(record)
        assert report["stale_handoffs_accepted"] == 1, seed
        assert report["double_deliveries"] == 1, seed
        assert _outcomes(record)["stale_delivery_accepted"] is True


def test_baseline_unblocks_the_repair_early(database: Database) -> None:
    for seed in SEEDS:
        record = _run(database, "baseline", "S33", seed)
        assert _report(record)["dependents_unblocked_early"] == 1, seed
        assert _outcomes(record)["repair_claimed_before_delivery"] is True


def test_baseline_in_s31_fails_only_when_the_stale_copy_arrives_after_recovery(
    database: Database,
) -> None:
    seen = set()
    for seed in range(12):
        plan = plan_for(seed, "S31")
        report = _report(_run(database, "baseline", "S31", seed))
        late = plan.replay_mode is ReplayMode.AFTER_RECOVERY
        delivered_first = plan.kill_point is KillPoint.AFTER_COMPLETE
        expected = 1 if late and not delivered_first else 0
        assert report["stale_handoffs_accepted"] == expected, (seed, plan)
        seen.add(expected)
    assert seen == {0, 1}


@pytest.mark.parametrize("scene", ["S32", "S34"])
def test_scenes_the_baseline_does_not_break_are_clean_controls(
    database: Database, scene: str
) -> None:
    for seed in SEEDS:
        report = _report(_run(database, "baseline", scene, seed))
        assert {name: report[name] for name in METRICS} == dict.fromkeys(METRICS, 0), seed


def test_duplicate_delivery_is_replayed_or_denied_in_both_arms(database: Database) -> None:
    for arm in ("fenced", "baseline"):
        for seed in SEEDS:
            outcomes = _outcomes(_run(database, arm, "S32", seed))
            assert outcomes == {
                "delivered": True,
                "same_id_replayed": True,
                "new_id_accepted": False,
            }


def test_contention_keeps_the_second_runner_out_until_the_release(database: Database) -> None:
    outcomes = _outcomes(_run(database, "fenced", "S34", 1))
    assert outcomes["second_entered_while_held"] is False
    assert outcomes["second_delivered_while_held"] is False
    assert outcomes["first_delivered"] is True
    assert outcomes["second_entered_after_release"] is True
    assert outcomes["second_delivered"] is True


def test_the_repair_waits_while_the_part_is_late(database: Database) -> None:
    for arm in ("fenced", "baseline"):
        outcomes = _outcomes(_run(database, arm, "S33", 1))
        assert outcomes["repair_claimed_while_part_late"] is False


def test_the_same_seed_gives_the_same_record(database: Database) -> None:
    for arm in ("fenced", "baseline"):
        assert _run(database, arm, "S31", 3) == _run(database, arm, "S31", 3)
