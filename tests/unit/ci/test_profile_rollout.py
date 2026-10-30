"""Rollout profiler: result layout and the component grouping."""

import json
from pathlib import Path

import profile_rollout
import pytest


def test_profile_returns_the_breakdown_per_function_and_component() -> None:
    data = profile_rollout.profile("S14", seed=1, ticks=40, lidar_mode="fast", top=8)
    assert len(data["top_functions"]) == 8
    first = data["top_functions"][0]
    assert {"function", "component", "calls", "own_seconds", "cumulative_seconds"} <= set(first)
    seconds = [row["own_seconds"] for row in data["top_functions"]]
    assert seconds == sorted(seconds, reverse=True)
    assert set(data["own_seconds_by_component"]) <= {"detector", "lidar", "core", "other"}
    assert data["own_seconds_by_component"]["detector"] > 0


def test_main_writes_a_labeled_result_file(tmp_path: Path) -> None:
    code = profile_rollout.main(
        [
            "--results-dir",
            str(tmp_path),
            "--label",
            "after",
            "--ticks",
            "30",
            "--lidar-mode",
            "fast",
        ]
    )
    assert code == 0
    files = list((tmp_path / "e8" / "dev").glob("profile_after_fast_*.json"))
    assert len(files) == 1
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["kind"] == "profile" and doc["seed_set"] == "dev"
    assert "code speed on this machine" in doc["label"]


def test_main_requires_a_label() -> None:
    with pytest.raises(SystemExit):
        profile_rollout.main([])


@pytest.mark.parametrize(
    ("filename", "component"),
    [("src/waggle/sim/detector.py", "detector"), ("x/sensors.py", "lidar"), ("m.py", "other")],
)
def test_component_grouping_is_by_file_name(filename: str, component: str) -> None:
    assert profile_rollout._component(filename) == component
