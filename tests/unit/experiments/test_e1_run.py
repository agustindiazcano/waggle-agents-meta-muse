"""waggle.experiments.e1_run: control in the loop, result documents and the dev-only command."""

import json
from pathlib import Path
from typing import Any

import pytest

from waggle.experiments import e1_run
from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e1_run import RunSpec
from waggle.sim import scenarios

SEED = 66447779  # S07: the no-control baseline has one human collision here
SHORT = 120

REQUIRED = {
    "experiment",
    "configuration",
    "configuration_detail",
    "seed_set",
    "commit",
    "date",
    "numpy_version",
    "platform",
    "dt",
    "definitions",
    "counts",
    "counts_excluding_unavoidable",
    "proportions",
    "unavoidable_cases",
    "tasks_completed",
    "tasks_per_simulated_hour",
    "stops",
    "latency",
    "failing_seeds",
    "assumptions",
    "runs",
    "model_ids",
    "prompt_versions",
    "notes",
}


def _stable(record: dict[str, Any]) -> dict[str, Any]:
    """A record without the wall clock latency, which differs between two identical runs."""
    return {k: v for k, v in record.items() if k != "latency"}


def test_no_control_through_the_harness_equals_the_phase_1_baseline_run() -> None:
    scenario = scenarios.generate("S07", SEED)
    expected = scenarios.run_scenario(scenario)
    got = e1_run.run_one(RunSpec("no_control", "S07", SEED))
    assert got["counts"] == expected.counts
    assert got["tasks_completed"] == expected.tasks_completed
    assert got["final_hash"] == expected.final_hash
    assert got["counts"]["human_collisions"] == 1  # known value from the committed baseline


def test_the_envelope_avoids_the_collision_the_baseline_has() -> None:
    got = e1_run.run_one(RunSpec("envelope_oracle", "S07", SEED))
    assert got["counts"]["human_collisions"] == 0
    assert got["counts"]["robot_collisions"] == 0
    assert got["latency"]["n"] > 0


def test_two_identical_runs_agree_except_for_the_latency() -> None:
    spec = RunSpec("envelope_occlusion_cpa_lidar_beacons", "S07", SEED, SHORT)
    assert _stable(e1_run.run_one(spec)) == _stable(e1_run.run_one(spec))


def test_workers_do_not_change_the_results() -> None:
    specs = [
        RunSpec("envelope_lidar", "S07", SEED, SHORT),
        RunSpec("radial_lidar", "S07", SEED, SHORT),
    ]
    serial = e1_run.run_set(specs, workers=1)
    parallel = e1_run.run_set(specs, workers=2)
    assert [_stable(r) for r in serial] == [_stable(r) for r in parallel]


def test_the_oracle_and_the_lidar_configurations_see_different_scans() -> None:
    oracle = e1_run.run_one(RunSpec("envelope_oracle", "S07", SEED, 400))
    lidar = e1_run.run_one(RunSpec("envelope_lidar", "S07", SEED, 400))
    assert oracle["final_hash"] != lidar["final_hash"]


def test_a_stop_is_counted_once_per_episode_with_its_reason() -> None:
    record = e1_run.run_one(RunSpec("envelope_oracle", "S01", 419688070))
    stops = record["stop_episodes"]
    assert stops and all(count >= 1 for count in stops.values())
    assert record["false_stops"] <= sum(stops.values())


def test_the_document_has_every_required_field_and_is_a_dev_result() -> None:
    config = BY_NAME["envelope_lidar"]
    runs = e1_run.run_set([RunSpec(config.name, "S07", SEED, SHORT)])
    document = e1_run.assemble(config, runs)
    assert set(document) >= REQUIRED
    assert document["seed_set"] == "dev" and document["experiment"] == "e1"
    assert document["configuration"] == "envelope_lidar"
    assert set(document["definitions"]) >= {"collision", "stop_episode", "false_stop"}
    proportion = document["proportions"]["human_collision"]
    assert (
        proportion["runs"] == 1 and 0.0 <= proportion["wilson95_low"] <= proportion["wilson95_high"]
    )


def test_the_document_counts_are_the_sum_of_the_runs() -> None:
    config = BY_NAME["envelope_lidar"]
    runs = e1_run.run_set(
        [RunSpec(config.name, "S07", SEED, SHORT), RunSpec(config.name, "S07", 420555216, SHORT)]
    )
    document = e1_run.assemble(config, runs)
    for key in e1_run.COUNT_KEYS:
        assert document["counts"][key] == sum(r["counts"][key] for r in runs)
    assert document["tasks_completed"] == sum(r["tasks_completed"] for r in runs)


def test_failing_seeds_and_unavoidable_cases_are_listed() -> None:
    config = BY_NAME["no_control"]
    runs = [
        {
            "scenario": "S07", "seed": 1, "robots": 1, "ticks": 40, "unavoidable_at_spawn": True,
            "tasks_completed": 0,
            "counts": dict.fromkeys(e1_run.COUNT_KEYS, 0) | {"human_collisions": 1},
            "final_hash": "x", "stop_episodes": {}, "false_stops": 0,
            "latency": {"n": 0, "median_us": 0.0, "p99_us": 0.0, "max_us": 0.0},
        },
    ]  # fmt: skip
    document = e1_run.assemble(config, runs)
    assert document["failing_seeds"] == [{"scenario": "S07", "seed": 1}]
    assert document["unavoidable_cases"] == [{"scenario": "S07", "seed": 1}]
    assert document["counts_excluding_unavoidable"]["human_collisions"] == 0
    assert document["counts"]["human_collisions"] == 1


def _seeds_without_heldout(path: Path) -> None:
    dev = json.loads(Path("data/seeds.json").read_text(encoding="utf-8"))["dev"]
    path.write_text(json.dumps({"dev": dev}), encoding="utf-8")


def test_the_command_writes_one_dev_file_per_configuration_and_never_reads_heldout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seeds = tmp_path / "seeds.json"
    _seeds_without_heldout(seeds)
    monkeypatch.setattr(e1_run, "SEEDS_PATH", seeds)
    code = e1_run.main(
        ["--config", "envelope_lidar", "no_control", "--scenarios", "S03", "--ticks", "40",
         "--results-dir", str(tmp_path / "results")]
    )  # fmt: skip
    assert code == 0
    files = sorted((tmp_path / "results" / "e1" / "dev").glob("*.json"))
    assert [f.name.split("_2")[0] for f in files] == ["envelope_lidar", "no_control"]
    assert not (tmp_path / "results" / "e1" / "heldout").exists()
    document = json.loads(files[0].read_text(encoding="utf-8"))
    assert document["seed_set"] == "dev" and len(document["runs"]) == 5
    assert "wrote" in capsys.readouterr().out


def test_an_unknown_configuration_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = e1_run.main(["--config", "nonsense", "--results-dir", str(tmp_path)])
    assert code == 2
    assert "unknown configuration" in capsys.readouterr().err
    assert not (tmp_path / "e1").exists()


def test_the_command_has_no_heldout_option() -> None:
    with pytest.raises(SystemExit):
        e1_run.main(["--seed-set", "heldout"])
