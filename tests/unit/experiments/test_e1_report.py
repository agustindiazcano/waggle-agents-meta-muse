"""waggle.experiments.e1_report: tables from result files only, missing is never zero."""

import json
from pathlib import Path
from typing import Any

import pytest

from waggle.experiments import e1_report, e1_run
from waggle.experiments.e1_config import BY_NAME, CONFIGS


def _run(
    scenario: str,
    seed: int,
    tasks: int,
    human: int = 0,
    stops: int = 0,
    distance: float | None = None,
    speeds: tuple[float, float] = (0.0, 0.0),
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "scenario": scenario,
        "seed": seed,
        "robots": 1,
        "ticks": 400,
        "unavoidable_at_spawn": False,
        "tasks_completed": tasks,
        "counts": dict.fromkeys(e1_run.COUNT_KEYS, 0) | {"human_collisions": human},
        "final_hash": "h",
        "stop_episodes": {"envelope": stops} if stops else {},
        "false_stops": stops,
        "latency": {"n": 10, "median_us": 900.0, "p99_us": 1500.0, "max_us": 2000.0}
        if stops
        else {"n": 0, "median_us": 0.0, "p99_us": 0.0, "max_us": 0.0},
    }
    if distance is not None:
        record["distance_m"] = distance
        record["speed_sums"] = {"requested": speeds[0], "limited": speeds[1]}
    return record


def _write(results: Path, name: str, runs: list[dict[str, Any]], date: str | None = None) -> Path:
    document = e1_run.assemble(BY_NAME[name], runs)
    if date is not None:
        document["date"] = date
    out = results / "e1" / "dev"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}_{document['date'].replace(':', '')}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_the_latest_file_of_a_configuration_wins(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 10)], "2026-10-30T10:00:00+00:00")
    _write(tmp_path, "no_control", [_run("S07", 1, 99)], "2026-10-31T10:00:00+00:00")
    docs = e1_report.load_latest(tmp_path)
    assert docs["no_control"]["tasks_completed"] == 99


def test_other_experiments_and_heldout_files_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 10)])
    out = tmp_path / "e1" / "dev"
    (out / "other.json").write_text(json.dumps({"experiment": "e2"}), encoding="utf-8")
    (out / "held.json").write_text(
        json.dumps({"experiment": "e1", "seed_set": "heldout", "configuration": "x", "date": "z"}),
        encoding="utf-8",
    )
    assert set(e1_report.load_latest(tmp_path)) == {"no_control"}


def test_a_missing_configuration_is_marked_missing_and_not_zero(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 10, human=1)])
    text = e1_report.render(e1_report.load_latest(tmp_path))
    for config in CONFIGS[1:]:
        assert f"| `{config.name}` | missing |" in text
    assert "1/1 (100.0%" in text


def test_throughput_is_the_ratio_to_no_control_on_the_same_runs(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 40)])
    _write(tmp_path, "envelope_lidar", [_run("S07", 1, 10, stops=3)])
    docs = e1_report.load_latest(tmp_path)
    assert e1_report._ratio(docs, "envelope_lidar") == pytest.approx(0.25)
    assert "| 0.25 |" in e1_report.render(docs)


def test_the_ratio_is_not_available_without_a_baseline(tmp_path: Path) -> None:
    _write(tmp_path, "envelope_lidar", [_run("S07", 1, 10, stops=3)])
    docs = e1_report.load_latest(tmp_path)
    assert e1_report._ratio(docs, "envelope_lidar") is None
    assert "n/a" in e1_report.render(docs)


def test_the_ablation_table_shows_the_change_between_the_pair(tmp_path: Path) -> None:
    _write(tmp_path, "envelope_lidar", [_run("S07", 1, 10, human=3, stops=2)])
    _write(tmp_path, "envelope_occlusion_lidar", [_run("S07", 1, 8, human=1, stops=5)])
    text = e1_report.render(e1_report.load_latest(tmp_path))
    assert (
        "| occlusion cap | `envelope_lidar` | `envelope_occlusion_lidar` | -2 | +0 | +3 |" in text
    )
    assert "| CPA | `envelope_occlusion_lidar` | `envelope_occlusion_cpa_lidar` | missing |" in text


def test_every_failing_seed_is_listed(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 111, 10, human=1), _run("S08", 222, 10)])
    text = e1_report.render(e1_report.load_latest(tmp_path))
    assert "`no_control` (1): S07/111" in text


def test_the_report_states_its_limits(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 10)])
    text = e1_report.render(e1_report.load_latest(tmp_path))
    assert "Development seeds only. Held-out seeds were not run." in text
    assert "not calibrated" in text
    assert "not a real-time bound" in text


def test_main_writes_the_report_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 10)])
    assert e1_report.main([str(tmp_path)]) == 0
    assert (tmp_path / "e1" / "dev" / "report.md").read_text(encoding="utf-8").startswith("# E1")
    assert "wrote" in capsys.readouterr().out


def test_main_fails_when_there_are_no_result_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert e1_report.main([str(tmp_path)]) == 1
    assert "no E1 result files" in capsys.readouterr().err
    assert not (tmp_path / "e1" / "dev" / "report.md").exists()


def test_the_ratio_only_compares_runs_that_both_configurations_have(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 40), _run("S08", 2, 400)])
    _write(tmp_path, "envelope_lidar", [_run("S07", 1, 10, stops=3)])
    docs = e1_report.load_latest(tmp_path)
    assert e1_report._ratio(docs, "envelope_lidar") == pytest.approx(0.25)


def test_distance_is_the_ratio_to_no_control_on_the_same_runs(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 40, distance=100.0)])
    _write(tmp_path, "envelope_lidar", [_run("S07", 1, 0, stops=1, distance=40.0, speeds=(10, 4))])
    docs = e1_report.load_latest(tmp_path)
    assert e1_report._distance_ratio(docs, "envelope_lidar") == pytest.approx(0.40)
    assert docs["envelope_lidar"]["speed_ratio"] == pytest.approx(0.4)
    text = e1_report.render(docs)
    assert "| 0.40 | 0.40 |" in text


def test_files_without_the_speed_fields_give_n_a_and_do_not_crash(tmp_path: Path) -> None:
    _write(tmp_path, "no_control", [_run("S07", 1, 40)])
    _write(tmp_path, "envelope_lidar", [_run("S07", 1, 10, stops=3)])
    docs = e1_report.load_latest(tmp_path)
    assert e1_report._distance_ratio(docs, "envelope_lidar") is None
    assert docs["envelope_lidar"]["speed_ratio"] is None
    assert "n/a | n/a |" in e1_report.render(docs)
