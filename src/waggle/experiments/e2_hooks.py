"""E2 chaos harness hooks: kill switch and delayed database transaction wrapper.

These components hook a worker process into the seeded fault schedule. The kill switch
terminates worker processes at scheduled lifecycle points, and the delayed database
wrapper injects delays before and at transaction commits.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol, runtime_checkable

import psycopg

from waggle.db.connection import Row
from waggle.experiments.e2_faults import FaultSchedule, KillPoint, ScheduleError, db_delay


class KillSwitch:
    """Fires process kills planned by a fault schedule at task lifecycle points."""

    def __init__(self, schedule: FaultSchedule, kill: Callable[[], None]) -> None:
        """Store the fault schedule and the kill callable."""
        self._schedule = schedule
        self._kill = kill
        self._fired: list[tuple[int, int, KillPoint]] = []

    @property
    def fired(self) -> tuple[tuple[int, int, KillPoint], ...]:
        """Chronological sequence of fired kill events."""
        return tuple(self._fired)

    def reach(self, point: KillPoint, task_index: int, attempt: int) -> bool:
        """Check whether to kill at this point; fire if planned and record hit."""
        if (
            not isinstance(point, KillPoint)
            or type(task_index) is not int
            or task_index < 0
            or type(attempt) is not int
            or attempt < 1
        ):
            raise ScheduleError("invalid task_index, attempt, or kill point")

        if self._schedule.kill_for(task_index, attempt) == point:
            self._fired.append((task_index, attempt, point))
            self._kill()
            return True
        return False


@runtime_checkable
class TransactionSource(Protocol):
    """Source of scoped database transactions."""

    def transaction(self) -> AbstractContextManager[psycopg.Connection[Row]]:
        """Open a transaction context."""
        ...


class DelayedDatabase:
    """Decorates a transaction source with fault-injection delays."""

    def __init__(
        self,
        inner: TransactionSource,
        schedule: FaultSchedule,
        worker: int,
        sleep: Callable[[float], None],
    ) -> None:
        """Store transaction source, schedule, worker index, and sleep callable."""
        if type(worker) is not int or not 0 <= worker < schedule.params.workers:
            raise ScheduleError("worker index out of range")
        self._inner = inner
        self._schedule = schedule
        self._worker = worker
        self._sleep = sleep
        self._calls = 0

    @property
    def calls(self) -> int:
        """Number of transactions started on this instance."""
        return self._calls

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection[Row]]:
        """Open a transaction with fault-injection delays."""
        call_index = self._calls
        self._calls += 1
        delay = db_delay(self._schedule, self._worker, call_index)
        if delay.before_ms > 0:
            self._sleep(delay.before_ms / 1000.0)
        with self._inner.transaction() as connection:
            yield connection
            if delay.commit_ms > 0:
                self._sleep(delay.commit_ms / 1000.0)
