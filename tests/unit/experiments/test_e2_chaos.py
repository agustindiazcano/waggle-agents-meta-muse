"""E2 chaos runner: the pure helpers. The run itself needs processes and PostgreSQL (cloud only)."""

import re
from dataclasses import replace

import pytest

from waggle.experiments.e2_chaos import (
    ChaosConfig,
    classify_exit,
    schema_name,
    worker_command,
)
from waggle.experiments.e2_chaos_worker import parse_run
from waggle.experiments.e2_faults import FaultParams, ScheduleError
from waggle.experiments.e2_worker import EXIT_KILLED

CONFIG = ChaosConfig(arm="fenced", seed=3, params=FaultParams(workers=2, tasks=10, horizon=500))


def test_exit_codes_are_classified() -> None:
    assert classify_exit(0) == "finished"
    assert classify_exit(EXIT_KILLED) == "killed"
    assert classify_exit(1) == "crashed"
    assert classify_exit(-9) == "crashed"
    assert classify_exit(2) == "crashed"


def test_schema_names_are_safe_unique_and_name_their_run() -> None:
    first, second = schema_name("fenced", 3), schema_name("fenced", 3)
    assert first != second
    for name in (first, second):
        assert re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name)
        assert name.startswith("e2_fenced_3_")


def test_the_worker_command_carries_a_valid_run_and_no_secret() -> None:
    command = worker_command(CONFIG, worker=1, incarnation=4, t0=50.0, schema="e2_fenced_3_ab")
    assert command[1:3] == ["-m", "waggle.experiments.e2_chaos_worker"]
    assert command[3] == "--run"
    run = parse_run(command[4])
    assert (run.arm, run.seed, run.config.worker, run.config.incarnation) == ("fenced", 3, 1, 4)
    assert run.config.horizon == CONFIG.params.horizon
    assert run.t0 == 50.0
    assert all("postgres" not in part for part in command)


def test_invalid_configuration_fails_closed() -> None:
    with pytest.raises(ScheduleError):
        replace(CONFIG, arm="other")
    with pytest.raises(ScheduleError):
        replace(CONFIG, ticks_per_second=0)
    with pytest.raises(ScheduleError):
        replace(CONFIG, lease_ticks=0)
    with pytest.raises(ScheduleError):
        replace(CONFIG, max_crashes=-1)
    with pytest.raises(ScheduleError):
        replace(CONFIG, start_delay_s=-1.0)
