"""E2 sweep: development seeds per arm, the run conditions and the result file."""

import json
from pathlib import Path

import pytest

from waggle.experiments.e2_chaos import ChaosConfig
from waggle.experiments.e2_faults import FaultParams, ScheduleError, build_schedule
from waggle.experiments.e2_oracle import TaskReport
from waggle.experiments.e2_result import run_record
from waggle.experiments.e2_sweep import (
    DEVELOPMENT_SEEDS,
    environment,
    main,
    parse_args,
    run_sweep,
)

ENV = {"GITHUB_SHA": "abc1234", "E2_POSTGRES_IMAGE": "pgvector/pgvector:pg16"}


def _fake_runner(config: ChaosConfig) -> dict[str, object]:
    report = TaskReport(0, 0, 0, 0, (), (), config.params.tasks, config.params.tasks)
    return run_record(
        arm=config.arm,
        seed=config.seed,
        schedule=build_schedule(config.seed, config.params),
        report=report,
        restarts=0,
        wall_s=0.1,
        ended_by="all_terminal",
    )


def test_development_seeds_are_thirty_unique_integers() -> None:
    assert len(DEVELOPMENT_SEEDS) == 30
    assert len(set(DEVELOPMENT_SEEDS)) == 30


def test_defaults_are_the_design_assumptions() -> None:
    args = parse_args([])
    assert args.arms == ("fenced", "baseline")
    assert args.seeds == DEVELOPMENT_SEEDS
    assert (args.params.workers, args.params.tasks, args.params.horizon) == (8, 500, 20000)


def test_seed_count_and_overrides() -> None:
    args = parse_args(["--arm", "fenced", "--seeds", "3", "--tasks", "20", "--workers", "2"])
    assert args.arms == ("fenced",)
    assert args.seeds == DEVELOPMENT_SEEDS[:3]
    assert (args.params.tasks, args.params.workers) == (20, 2)


@pytest.mark.parametrize(
    "argv",
    [
        ["--seeds", "0"],
        ["--seeds", "31"],
        ["--arm", "other"],
        ["--seed-set", "held_out"],
        ["--tasks", "0"],
    ],
)
def test_bad_arguments_fail_closed(argv: list[str]) -> None:
    with pytest.raises((ScheduleError, SystemExit)):
        parse_args(argv)


def test_the_environment_records_the_conditions() -> None:
    env = environment(ENV)
    assert env["commit"] == "abc1234"
    assert env["postgres_image"] == "pgvector/pgvector:pg16"
    assert isinstance(env["schema_revision"], int)
    assert isinstance(env["python"], str) and env["python"]


@pytest.mark.parametrize("missing", ["GITHUB_SHA", "E2_POSTGRES_IMAGE"])
def test_a_missing_condition_is_an_error_not_a_blank(missing: str) -> None:
    environ = {key: value for key, value in ENV.items() if key != missing}
    with pytest.raises(ScheduleError):
        environment(environ)


def test_the_sweep_runs_the_same_seeds_in_order_for_one_arm() -> None:
    seen: list[tuple[str, int]] = []

    def runner(config: ChaosConfig) -> dict[str, object]:
        seen.append((config.arm, config.seed))
        return _fake_runner(config)

    records = run_sweep("baseline", DEVELOPMENT_SEEDS[:4], FaultParams(), runner)
    assert [seed for _, seed in seen] == list(DEVELOPMENT_SEEDS[:4])
    assert {arm for arm, _ in seen} == {"baseline"}
    assert len(records) == 4


def test_main_writes_one_file_per_arm_and_never_overwrites(tmp_path: Path) -> None:
    argv = ["--seeds", "2", "--tasks", "10", "--workers", "2", "--out", str(tmp_path)]
    status = main(argv, ENV, runner=_fake_runner)
    assert status == 0
    files = sorted(tmp_path.glob("chaos_*.json"))
    assert [f.name.split("_")[1] for f in files] == ["baseline", "fenced"]
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["seed_set"] == "development"
    assert data["llm_calls"] == 0
    assert data["seeds"] == list(DEVELOPMENT_SEEDS[:2])


def test_main_refuses_when_the_environment_is_incomplete(tmp_path: Path) -> None:
    with pytest.raises(ScheduleError):
        main(["--out", str(tmp_path)], {}, runner=_fake_runner)
