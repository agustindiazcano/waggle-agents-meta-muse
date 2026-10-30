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
        ["--results-dir", str(tmp_path), "--ticks", "100", "--rollout-ticks", "50", "--forks", "1"]
    )
    assert code == 0
    files = list((tmp_path / "e8" / "dev").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["seed_set"] == "dev"
