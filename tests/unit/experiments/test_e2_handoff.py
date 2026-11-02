"""E2 handoff chaos: the seeded scene plan and the summary, both pure and database free."""

from waggle.experiments.e2_faults import KillPoint, ReplayMode
from waggle.experiments.e2_handoff import aggregate_scenes
from waggle.experiments.e2_handoff_scenes import ARMS, SCENES, TARGET_LAYERS, plan_for


def test_the_scenes_are_s31_to_s35_and_each_declares_a_target_layer() -> None:
    assert SCENES == ("S31", "S32", "S33", "S34", "S35")
    assert set(TARGET_LAYERS) == set(SCENES)
    assert all(TARGET_LAYERS[scene] for scene in SCENES)
    assert ARMS == ("fenced", "baseline")


def test_the_plan_is_pure_in_the_seed_and_the_scene() -> None:
    assert plan_for(7, "S31") == plan_for(7, "S31")
    assert plan_for(7, "S31") != plan_for(8, "S31") or plan_for(7, "S32") != plan_for(8, "S32")


def test_the_plan_varies_the_kill_point_and_the_replay_mode_across_seeds() -> None:
    plans = [plan_for(seed, "S31") for seed in range(40)]
    assert {plan.kill_point for plan in plans} == set(KillPoint)
    assert {plan.replay_mode for plan in plans} == set(ReplayMode)


def test_scenes_of_one_seed_get_their_own_draw() -> None:
    drawn = {(plan_for(seed, scene).kill_point) for seed in range(5) for scene in SCENES}
    assert len(drawn) > 1


def _record(
    arm: str, scene: str, seed: int, *, double: int = 0, undecided: bool = False
) -> dict[str, object]:
    report: dict[str, int] | None = None
    if not undecided:
        report = {
            "double_deliveries": double,
            "stale_handoffs_accepted": double,
            "dependents_unblocked_early": 0,
            "stale_writes_accepted": 0,
            "double_assignments": 0,
            "violation_samples": 0,
            "tasks_stuck": 0,
        }
    return {"arm": arm, "scene": scene, "seed": seed, "undecided": undecided, "report": report}


def test_the_summary_counts_runs_events_seeds_and_the_wilson_interval() -> None:
    records = [
        _record("baseline", "S35", 1, double=1),
        _record("baseline", "S35", 2, double=1),
        _record("baseline", "S35", 3),
        _record("fenced", "S35", 1),
        _record("fenced", "S35", 2),
    ]
    summary = aggregate_scenes(records)
    baseline = summary["baseline"]["S35"]
    assert baseline.runs == 3 and baseline.decided_runs == 3
    metric = baseline.metrics["double_deliveries"]
    assert metric.runs_with_event == 2
    assert metric.events == 2
    assert metric.failing_seeds == (1, 2)
    low, high = metric.wilson95
    assert 0.0 < low < 2 / 3 < high < 1.0
    assert summary["fenced"]["S35"].metrics["double_deliveries"].runs_with_event == 0
    assert baseline.small_sample is True


def test_an_undecided_run_is_counted_apart_and_never_as_a_pass() -> None:
    records = [_record("fenced", "S31", 1), _record("fenced", "S31", 2, undecided=True)]
    entry = aggregate_scenes(records)["fenced"]["S31"]
    assert entry.runs == 2
    assert entry.decided_runs == 1
    assert entry.undecided_seeds == (2,)
