"""Speed measurement of the tick loop: schema, labels and the result layout."""

import json
from pathlib import Path

import pytest
import sim_speed


def test_measure_returns_the_labeled_figures() -> None:
    data = sim_speed.measure(ticks=200, rollout_ticks=100, forks=2, entities=4)
    assert data["seed_set"] == "dev"
    assert data["experiment"] == "e8"
    assert "code speed on this machine" in data["label"]
    assert data["empty_loop"]["ticks_per_second"] > 0
    assert data["fork_rollout"]["ticks_per_second"] > 0
    assert data["fork_rollout"]["forks"] == 2
    for key in ("commit", "date", "numpy_version", "platform", "dt", "entities"):
        assert key in data, key


def test_measure_rejects_nonpositive_sizes() -> None:
    with pytest.raises(ValueError):
        sim_speed.measure(ticks=0, rollout_ticks=10, forks=1, entities=1)


def test_main_writes_a_result_file_in_the_dev_layout(tmp_path: Path) -> None:
    code = sim_speed.main(
        [
            "--results-dir",
            str(tmp_path),
            "--ticks",
            "100",
            "--rollout-ticks",
            "50",
            "--forks",
            "1",
            "--scenario-ticks",
            "30",
            "--variants",
            "2",
            "--workers",
            "2",
        ]
    )
    assert code == 0
    files = list((tmp_path / "e8" / "dev").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["seed_set"] == "dev"


def test_scenario_rollout_measures_ten_robots_with_lidar() -> None:
    data = sim_speed.measure_scenario_rollout("S14", seed=1, ticks=80, forks=2)
    assert data["scenario"] == "S14" and data["robots"] == 10
    assert data["lidar_scans_per_rollout"] > 0
    assert data["ticks_per_second"] > 0
    assert "code speed on this machine" in data["label"]


def test_main_includes_the_scenario_rollout(tmp_path: Path) -> None:
    code = sim_speed.main(
        [
            "--results-dir",
            str(tmp_path),
            "--ticks",
            "100",
            "--rollout-ticks",
            "50",
            "--forks",
            "1",
            "--scenario-ticks",
            "60",
            "--variants",
            "2",
            "--workers",
            "2",
        ]
    )
    assert code == 0
    doc = json.loads(next((tmp_path / "e8" / "dev").glob("*.json")).read_text(encoding="utf-8"))
    assert doc["scenario_rollout"]["robots"] == 10
    assert doc["scenario_rollout_fast_lidar"]["lidar_mode"] == "fast"
    assert doc["variants"]["results_equal"] is True


def test_fast_lidar_mode_scans_as_often_as_the_exact_mode() -> None:
    exact = sim_speed.measure_scenario_rollout("S14", seed=1, ticks=40, forks=1)
    fast = sim_speed.measure_scenario_rollout("S14", seed=1, ticks=40, forks=1, lidar_mode="fast")
    assert fast["lidar_scans_per_rollout"] == exact["lidar_scans_per_rollout"] > 0
    assert fast["lidar_mode"] == "fast"


def test_an_unknown_lidar_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        sim_speed.measure_scenario_rollout("S14", seed=1, ticks=10, forks=1, lidar_mode="x")


def test_measure_variants_compares_serial_and_parallel_results() -> None:
    data = sim_speed.measure_variants("S14", [1, 2], ticks=30, workers=2)
    assert data["results_equal"] is True
    assert data["variants"] == 2 and data["workers"] == 2
    with pytest.raises(ValueError):
        sim_speed.measure_variants("S14", [], ticks=30, workers=2)
