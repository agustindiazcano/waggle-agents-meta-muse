"""E2 simulator component: paired admission ablation and explicit result summaries."""

import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from waggle.experiments.corridor_admission import build_s03_admission
from waggle.experiments.e2_simulator import RunResult, main, summarize, write_report


def test_baseline_keeps_the_same_initial_state_and_moves_the_waiter() -> None:
    enabled, _, _ = build_s03_admission(7)
    disabled, _, _ = build_s03_admission(7, admission_enabled=False)
    assert enabled.state_hash() == disabled.state_hash()
    enabled.run(12)
    disabled.run(12)
    assert enabled.state.arrays["robot_pose"][1, 0] == 9.0
    assert disabled.state.arrays["robot_pose"][1, 0] < 9.0
    assert disabled.state.arrays["admission_owner"][0] == -1


def _run(seed: int, enabled: bool = True) -> RunResult:
    return RunResult(seed, enabled, 3200, 2, 2, 5, 0, 0, 0, 0, "hash")


def test_summary_uses_runs_not_ticks_and_lists_failures() -> None:
    good = _run(1)
    failed = replace(
        _run(2),
        completed_routes=1,
        double_occupancy_ticks=17,
        robot_collisions=2,
        stalled_unfinished_robots=1,
    )
    summary = summarize((good, failed))
    assert summary.completed_runs.successes == 1
    assert summary.completed_runs.total == 2
    assert summary.occupancy_violation_runs.successes == 1
    assert summary.robot_collision_runs.successes == 1
    assert summary.double_occupancy_ticks == 17
    assert summary.robot_collisions == 2
    assert summary.failing_seeds == (2,)
    assert summary.small_sample


def test_empty_duplicate_or_mixed_configuration_results_are_rejected() -> None:
    for runs in ((), (_run(1), _run(1)), (_run(1), _run(2, False))):
        with pytest.raises(ValueError):
            summarize(runs)


def test_wilson_known_zero_out_of_ten_value() -> None:
    summary = summarize(tuple(replace(_run(i), completed_routes=0) for i in range(10)))
    assert summary.completed_runs.low == 0.0
    assert summary.completed_runs.high == pytest.approx(0.2775327998628892)


def test_cloud_cli_refuses_local_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="cloud"):
        main([])


def test_report_writer_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    target.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_report({"scope": "E2 simulator component"}, target)
    assert target.read_text(encoding="utf-8") == "keep"


def test_factory_rejects_non_boolean_ablation_flag() -> None:
    with pytest.raises(ValueError):
        build_s03_admission(7, admission_enabled=np.bool_(False))  # type: ignore[arg-type]


def test_scoring_counts_known_occupancy_and_unfinished_robot_stall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from waggle.experiments import e2_simulator

    sim, admission, det = build_s03_admission(7)
    sim.systems = []
    sim.state.arrays["robot_pose"][:] = [[3.0, 9.0, 0.0], [3.0, 12.0, 0.0]]
    sim.state.arrays["script_wp"][0] = 2
    sim.state.arrays["script_tasks"][0] = 2

    def factory(seed: int, *, admission_enabled: bool) -> tuple[object, ...]:
        return sim, admission, det

    monkeypatch.setattr(e2_simulator, "build_s03_admission", factory)
    result = e2_simulator.run_case(7, True, ticks=3, stall_ticks=2)
    assert result.double_occupancy_ticks == 3
    assert result.stalled_unfinished_robots == 1
    assert result.completed_routes == 1
    assert result.completed_waypoints == 2
    assert result.robot_collisions == 0


def test_unknown_occupancy_is_a_scoring_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from waggle.experiments import e2_simulator

    sim, admission, det = build_s03_admission(7)
    sim.systems = []
    sim.state.arrays["robot_pose"][0, 0] = np.nan

    def factory(seed: int, *, admission_enabled: bool) -> tuple[object, ...]:
        return sim, admission, det

    monkeypatch.setattr(e2_simulator, "build_s03_admission", factory)
    with pytest.raises(RuntimeError, match="unknown occupancy"):
        e2_simulator.run_case(7, True, ticks=1)


def test_comparison_pairs_identical_seeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from waggle.experiments import e2_simulator

    called: list[tuple[int, bool]] = []

    def fake_run(seed: int, enabled: bool) -> RunResult:
        called.append((seed, enabled))
        return _run(seed, enabled)

    monkeypatch.setattr(e2_simulator, "run_case", fake_run)
    results = e2_simulator.run_comparison((8, 9))
    assert called == [(8, False), (9, False), (8, True), (9, True)]
    assert len(results) == 4
    for seeds in ((), (1, 1), (-1,)):
        with pytest.raises(ValueError):
            e2_simulator.run_comparison(seeds)


def test_cloud_report_has_provenance_and_explicit_unmeasured_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import json

    from waggle.experiments import e2_simulator

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(e2_simulator, "_commit", lambda: "a" * 40)
    monkeypatch.setattr(e2_simulator, "dev_pairs", lambda ids: [("S03", 1), ("S03", 2)])
    monkeypatch.setattr(e2_simulator, "run_case", lambda seed, enabled: _run(seed, enabled))
    assert main([]) == 0
    files = list((tmp_path / "results/e2/dev").glob("*.json"))
    assert len(files) == 1
    report = json.loads(files[0].read_text(encoding="utf-8"))
    assert report["commit"] == "a" * 40
    assert report["seed_set"] == "dev"
    assert report["seeds"] == [1, 2]
    assert len(report["runs"]) == 4
    assert len(report["summaries"]) == 2
    assert "cycle-proven deadlocks" in report["not_measured"]
    assert report["llm_calls"] == 0
    assert report["model_ids"] == []


def test_failed_comparison_never_writes_a_passing_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from waggle.experiments import e2_simulator

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(e2_simulator, "_commit", lambda: "a" * 40)
    monkeypatch.setattr(e2_simulator, "dev_pairs", lambda ids: [("S03", 1)])

    def fail(seeds: tuple[int, ...]) -> tuple[RunResult, ...]:
        raise RuntimeError("scoring failed")

    monkeypatch.setattr(e2_simulator, "run_comparison", fail)
    with pytest.raises(RuntimeError, match="scoring failed"):
        main([])
    assert not (tmp_path / "results").exists()


def test_writer_rejects_nan_before_creating_a_file(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    with pytest.raises(ValueError):
        write_report({"invalid": float("nan")}, target)
    assert not target.exists()


def test_missing_git_dependency_is_a_real_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from waggle.experiments import e2_simulator

    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="git is required"):
        e2_simulator._commit()


def test_heldout_option_is_not_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(SystemExit) as stopped:
        main(["--seed-set", "heldout"])
    assert stopped.value.code == 2


def test_impossible_counts_are_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_run(7), completed_routes=3)
    with pytest.raises(ValueError):
        replace(_run(7), ticks=0)
    with pytest.raises(ValueError):
        replace(_run(7), double_occupancy_ticks=3201)
