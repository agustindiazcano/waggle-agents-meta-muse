"""E2 chaos worker entry: strict configuration, shared clock and the repository of each arm."""

import json
from dataclasses import replace

import pytest

from waggle.db.tasks import TaskRepository
from waggle.experiments.e2_baseline import NoFencingTaskRepository
from waggle.experiments.e2_chaos_worker import (
    WorkerRun,
    make_clock,
    parse_run,
    repository_for,
)
from waggle.experiments.e2_faults import FaultParams, ScheduleError
from waggle.experiments.e2_worker import WorkerConfig

RUN = WorkerRun(
    arm="fenced",
    seed=7,
    params=FaultParams(workers=2, tasks=10, horizon=500),
    config=WorkerConfig(worker=1, incarnation=2, horizon=500, lease_ticks=40),
    t0=1000.0,
    ticks_per_second=1000,
    schema="e2_run_7",
)


def test_a_run_round_trips_through_its_json_form() -> None:
    assert parse_run(RUN.to_json()) == RUN


def test_the_json_form_is_plain_data() -> None:
    data = json.loads(RUN.to_json())
    assert data["arm"] == "fenced"
    assert data["params"]["workers"] == 2
    assert data["config"]["incarnation"] == 2


@pytest.mark.parametrize("text", ["", "not json", "[]", "{}", '{"arm": "fenced"}'])
def test_malformed_configuration_fails_closed(text: str) -> None:
    with pytest.raises(ScheduleError):
        parse_run(text)


def test_an_unknown_field_is_rejected() -> None:
    data = json.loads(RUN.to_json())
    data["extra"] = 1
    with pytest.raises(ScheduleError):
        parse_run(json.dumps(data))


def test_an_unknown_arm_is_rejected() -> None:
    data = json.loads(RUN.to_json())
    data["arm"] = "both"
    with pytest.raises(ScheduleError):
        parse_run(json.dumps(data))


@pytest.mark.parametrize("schema", ["", "Bad-Name", "x" * 64, "public; drop"])
def test_an_unsafe_schema_name_is_rejected(schema: str) -> None:
    data = json.loads(RUN.to_json())
    data["schema"] = schema
    with pytest.raises(ScheduleError):
        parse_run(json.dumps(data))


def test_a_worker_outside_the_parameters_is_rejected() -> None:
    data = json.loads(RUN.to_json())
    data["config"]["worker"] = 2
    with pytest.raises(ScheduleError):
        parse_run(json.dumps(data))


def test_the_shared_clock_counts_ticks_since_the_common_start() -> None:
    now = [1000.0]
    clock = make_clock(1000.0, 1000, lambda: now[0])
    assert clock() == 0
    now[0] = 1001.5
    assert clock() == 1500


def test_the_clock_never_goes_negative_before_the_start() -> None:
    clock = make_clock(1000.0, 1000, lambda: 990.0)
    assert clock() == 0


def test_the_clock_rejects_a_nonpositive_rate() -> None:
    with pytest.raises(ScheduleError):
        make_clock(0.0, 0, lambda: 0.0)


def test_each_arm_gets_its_repository() -> None:
    assert repository_for("fenced") is TaskRepository
    assert repository_for("baseline") is NoFencingTaskRepository
    with pytest.raises(ScheduleError):
        repository_for("other")


def test_replacing_a_field_keeps_the_run_valid() -> None:
    other = replace(RUN, seed=8)
    assert parse_run(other.to_json()).seed == 8
