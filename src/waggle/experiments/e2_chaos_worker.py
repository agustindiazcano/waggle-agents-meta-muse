"""Entry point of one E2 chaos worker process: ``python -m waggle.experiments.e2_chaos_worker``.

The chaos runner starts it with ``--run <json>`` and ``DATABASE_URL`` in the environment. The
configuration is strict: unknown or missing fields, an unknown arm or an unsafe schema name stop
the process before any connection is opened. The process connects to the run schema through a
``DelayedDatabase``, picks the repository of its arm, and runs ``run_worker`` with a kill that ends
the process with ``os._exit`` so no ``finally`` block runs, as in a crash. It writes nothing to
stdout; its counts go to stderr as one JSON line.

Both arms share everything except the repository class: ``fenced`` is the production
``TaskRepository`` and ``baseline`` is the no-fencing subclass. This module is one of the two that
may import the baseline (``tests/unit/experiments/test_e2_baseline.py``).
"""

import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import NoReturn, cast

from waggle.db.connection import Database
from waggle.db.tasks import TaskRepository
from waggle.experiments.e2_baseline import NoFencingTaskRepository
from waggle.experiments.e2_faults import FaultParams, ScheduleError, build_schedule
from waggle.experiments.e2_hooks import DelayedDatabase, KillSwitch
from waggle.experiments.e2_worker import EXIT_KILLED, WorkerConfig, run_worker

ARMS = ("fenced", "baseline")
_SCHEMA = re.compile(r"[a-z_][a-z0-9_]{0,62}")
_RUN_KEYS = {"arm", "seed", "params", "config", "t0", "ticks_per_second", "schema"}


@dataclass(frozen=True)
class WorkerRun:
    """Everything one worker process needs to know, apart from the database address."""

    arm: str
    seed: int
    params: FaultParams
    config: WorkerConfig
    t0: float
    ticks_per_second: int
    schema: str

    def to_json(self) -> str:
        """The plain-data form passed on the command line."""
        return json.dumps(
            {
                "arm": self.arm,
                "seed": self.seed,
                "params": asdict(self.params),
                "config": asdict(self.config),
                "t0": self.t0,
                "ticks_per_second": self.ticks_per_second,
                "schema": self.schema,
            },
            sort_keys=True,
        )


def _fields(value: object, keys: set[str], what: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ScheduleError(f"{what} must be an object with exactly its declared fields")
    return value


def parse_run(text: str) -> WorkerRun:
    """Read and validate a run; anything unexpected raises ``ScheduleError``."""
    try:
        loaded: object = json.loads(text)
    except ValueError as error:
        raise ScheduleError("run configuration is not JSON") from error
    data = _fields(loaded, _RUN_KEYS, "run")
    params_data = _fields(data["params"], set(FaultParams.__dataclass_fields__), "params")
    config_data = _fields(data["config"], set(WorkerConfig.__dataclass_fields__), "config")
    arm, seed, t0, rate, schema = (
        data["arm"],
        data["seed"],
        data["t0"],
        data["ticks_per_second"],
        data["schema"],
    )
    if arm not in ARMS:
        raise ScheduleError("unknown arm")
    if type(seed) is not int or type(rate) is not int or rate < 1:
        raise ScheduleError("seed and ticks_per_second must be integers, the rate positive")
    if type(t0) not in (int, float):
        raise ScheduleError("t0 must be a number")
    if not isinstance(schema, str) or _SCHEMA.fullmatch(schema) is None:
        raise ScheduleError("unsafe schema name")
    try:
        params = FaultParams(**params_data)  # type: ignore[arg-type]
        config = WorkerConfig(**config_data)  # type: ignore[arg-type]
    except TypeError as error:
        raise ScheduleError("params or config has a field of the wrong kind") from error
    if config.worker >= params.workers:
        raise ScheduleError("worker is outside the parameters")
    return WorkerRun(str(arm), seed, params, config, float(t0), rate, schema)  # type: ignore[arg-type]


def make_clock(t0: float, ticks_per_second: int, now: Callable[[], float]) -> Callable[[], int]:
    """A tick counter shared by all processes through the wall clock and a common start."""
    if type(ticks_per_second) is not int or ticks_per_second < 1:
        raise ScheduleError("ticks_per_second must be a positive integer")

    def clock() -> int:
        return max(0, int((now() - t0) * ticks_per_second))

    return clock


def repository_for(arm: str) -> type[TaskRepository]:
    """The repository class of an arm."""
    if arm == "fenced":
        return TaskRepository
    if arm == "baseline":
        return NoFencingTaskRepository
    raise ScheduleError("unknown arm")


def _die() -> NoReturn:
    os._exit(EXIT_KILLED)


def main(argv: Sequence[str], environ: Mapping[str, str]) -> int:
    """Run one worker incarnation; returns 0 at the horizon."""
    if len(argv) != 2 or argv[0] != "--run":
        sys.stderr.write("usage: e2_chaos_worker --run <json>\n")
        return 2
    run = parse_run(argv[1])
    root = Database.from_environ(environ)
    database = Database(root.dsn, schema=run.schema)
    schedule = build_schedule(run.seed, run.params)
    delayed = DelayedDatabase(database, schedule, run.config.worker, time.sleep)
    # TaskRepository only calls ``transaction()``, which DelayedDatabase provides.
    repo = repository_for(run.arm)(cast(Database, delayed))
    stats = run_worker(
        run.config,
        repo,
        schedule,
        KillSwitch(schedule, _die),
        make_clock(run.t0, run.ticks_per_second, time.time),
        time.sleep,
        lambda: False,
    )
    sys.stderr.write(json.dumps({"worker": run.config.worker, **asdict(stats)}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], os.environ))
