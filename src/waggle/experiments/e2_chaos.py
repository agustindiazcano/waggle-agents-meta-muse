"""E2 chaos runner: one run in a fresh schema with real worker processes and a seeded fault plan.

``run_once`` creates a unique schema on the configured PostgreSQL service, migrates it, creates the
tasks, starts one OS process per worker (``waggle.experiments.e2_chaos_worker``), restarts a worker
that a planned kill ended, runs the production recovery sweeper with the true clock, and stops when
every task is terminal or at the horizon. The oracle then judges the event log and the final rows;
nothing is taken from what the repositories answered during the run. A log the oracle cannot judge,
or a run that exceeds its crash limit, is an undecided record and never a pass. The schema is
dropped and the worker log directory deleted on every path.

The seed fixes the fault plan, not the operating system scheduling, so two runs with the same seed
can differ (``docs/E2_CHAOS_DESIGN.md``). Nothing here changes the ACK, retry, fencing or audit
logic: both arms call the repositories as they are, and the sweeper is the production one.
"""

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

from waggle.coordination.task_model import TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.schema import migrate
from waggle.db.tasks import TaskRepository
from waggle.experiments.e2_chaos_worker import ARMS, WorkerRun, make_clock
from waggle.experiments.e2_faults import FaultParams, ScheduleError, build_schedule
from waggle.experiments.e2_log import load_oracle_inputs
from waggle.experiments.e2_oracle import TERMINAL, OracleError, judge_tasks
from waggle.experiments.e2_result import run_record, undecided_record
from waggle.experiments.e2_worker import EXIT_KILLED, WorkerConfig, task_id

_STOP_WAIT_S = 5.0


@dataclass(frozen=True)
class ChaosConfig:
    """One run. Tick rate, lease and timings are assumptions to calibrate on development seeds."""

    arm: str
    seed: int
    params: FaultParams
    lease_ticks: int = 400
    ticks_per_second: int = 1000
    handler_s: float = 0.02
    idle_s: float = 0.05
    max_attempts: int = 3
    max_crashes: int = 50
    start_delay_s: float = 1.0
    sweep_every_s: float = 0.2
    check_every_s: float = 0.5
    poll_s: float = 0.05

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ScheduleError("unknown arm")
        if self.ticks_per_second < 1 or self.lease_ticks < 1 or self.max_attempts < 1:
            raise ScheduleError("ticks_per_second, lease_ticks and max_attempts must be positive")
        if self.max_crashes < 0:
            raise ScheduleError("max_crashes must not be negative")
        timings = (self.handler_s, self.idle_s, self.start_delay_s, self.sweep_every_s)
        if min(*timings, self.check_every_s, self.poll_s) < 0:
            raise ScheduleError("timings must not be negative")


def classify_exit(code: int) -> str:
    """Exit code of a worker: finished at the horizon, killed on purpose, or crashed."""
    if code == 0:
        return "finished"
    return "killed" if code == EXIT_KILLED else "crashed"


def schema_name(arm: str, seed: int) -> str:
    """A unique, safe schema name for one run."""
    return f"e2_{arm}_{seed}_{uuid4().hex[:8]}"


def worker_command(
    config: ChaosConfig, *, worker: int, incarnation: int, t0: float, schema: str
) -> list[str]:
    """The command line of one worker incarnation; the database address stays in the environment."""
    run = WorkerRun(
        arm=config.arm,
        seed=config.seed,
        params=config.params,
        config=WorkerConfig(
            worker=worker,
            incarnation=incarnation,
            horizon=config.params.horizon,
            lease_ticks=config.lease_ticks,
            handler_s=config.handler_s,
            idle_s=config.idle_s,
        ),
        t0=t0,
        ticks_per_second=config.ticks_per_second,
        schema=schema,
    )
    return [sys.executable, "-m", "waggle.experiments.e2_chaos_worker", "--run", run.to_json()]


@dataclass
class _Outcome:
    ended_by: str
    restarts: int = 0
    crashes: int = 0
    sweep_errors: int = 0
    reason: str | None = None


def _populate(repo: TaskRepository, config: ChaosConfig) -> None:
    for index in range(config.params.tasks):
        name = task_id(index)
        repo.create(TaskDefinition(name, (), config.max_attempts, 0), 0)
        for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
            repo.advance(name, state, f"setup-{index}-{state.value}", 0)


def _open_tasks(database: Database) -> int:
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT count(*) FROM tasks WHERE NOT (state = ANY(%s))", (sorted(TERMINAL),)
        ).fetchone()
    return int(row[0]) if row is not None and type(row[0]) is int else -1


def _log_tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-400:]
    except OSError:
        return "no log"


def _stop(processes: dict[int, tuple[subprocess.Popen[bytes], int]]) -> None:
    for process, _ in processes.values():
        process.terminate()
    for process, _ in processes.values():
        try:
            process.wait(timeout=_STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=_STOP_WAIT_S)


def _supervise(
    database: Database, repo: TaskRepository, config: ChaosConfig, schema: str, logs: Path
) -> _Outcome:
    t0 = time.time() + config.start_delay_s
    clock = make_clock(t0, config.ticks_per_second, time.time)
    processes: dict[int, tuple[subprocess.Popen[bytes], int]] = {}
    outcome = _Outcome("horizon")

    def spawn(worker: int, incarnation: int) -> None:
        command = worker_command(
            config, worker=worker, incarnation=incarnation, t0=t0, schema=schema
        )
        with (logs / f"w{worker}-g{incarnation}.log").open("wb") as log:
            process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=log, env=os.environ.copy()
            )
        processes[worker] = (process, incarnation)

    try:
        for worker in range(config.params.workers):
            spawn(worker, 0)
        next_sweep = next_check = 0.0
        while True:
            now_tick = clock()
            if now_tick >= config.params.horizon:
                return outcome
            for worker, (process, incarnation) in list(processes.items()):
                code = process.poll()
                if code is None:
                    continue
                kind = classify_exit(code)
                if kind == "finished":
                    del processes[worker]
                    continue
                if kind == "killed":
                    outcome.restarts += 1
                else:
                    outcome.crashes += 1
                    if outcome.crashes > config.max_crashes:
                        tail = _log_tail(logs / f"w{worker}-g{incarnation}.log")
                        outcome.ended_by = "aborted"
                        outcome.reason = f"worker crash limit exceeded; last log: {tail}"
                        return outcome
                spawn(worker, incarnation + 1)
            now = time.monotonic()
            if now >= next_sweep:
                try:
                    repo.recover(now_tick)
                except psycopg.Error:
                    outcome.sweep_errors += 1
                next_sweep = now + config.sweep_every_s
            if now >= next_check:
                if _open_tasks(database) == 0:
                    outcome.ended_by = "all_terminal"
                    return outcome
                next_check = now + config.check_every_s
            time.sleep(config.poll_s)
    finally:
        _stop(processes)


def run_once(root: Database, config: ChaosConfig) -> dict[str, object]:
    """Run one configuration and seed in a fresh schema; return its record."""
    schema = schema_name(config.arm, config.seed)
    schedule = build_schedule(config.seed, config.params)
    started = time.monotonic()
    with root.transaction() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        database = Database(root.dsn, schema=schema)
        migrate(database, expected_revision=0)
        repo = TaskRepository(database)
        _populate(repo, config)
        with tempfile.TemporaryDirectory(prefix="e2-logs-") as logs:
            outcome = _supervise(database, repo, config, schema, Path(logs))
        wall = time.monotonic() - started
        if outcome.reason is not None:
            return undecided_record(
                arm=config.arm,
                seed=config.seed,
                schedule=schedule,
                reason=outcome.reason,
                restarts=outcome.restarts,
                wall_s=wall,
            )
        try:
            events, states = load_oracle_inputs(database)
            report = judge_tasks(events, states)
        except OracleError as error:
            return undecided_record(
                arm=config.arm,
                seed=config.seed,
                schedule=schedule,
                reason=str(error),
                restarts=outcome.restarts,
                wall_s=wall,
            )
        record = run_record(
            arm=config.arm,
            seed=config.seed,
            schedule=schedule,
            report=report,
            restarts=outcome.restarts,
            wall_s=wall,
            ended_by=outcome.ended_by,
        )
        record["crashes"] = outcome.crashes
        record["sweep_errors"] = outcome.sweep_errors
        return record
    finally:
        with root.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
