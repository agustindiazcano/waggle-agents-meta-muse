"""A scripted fake database for repository unit tests: it records SQL and returns canned rows."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

Handler = Callable[[str, tuple[object, ...]], tuple[object, ...] | None]


class FakeCursor:
    """The result of one execute call."""

    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class FakeConnection:
    """Records every statement and answers it through ``handler`` (a SELECT) or None."""

    def __init__(self, handler: Handler, log: list[str]) -> None:
        self._handler = handler
        self._log = log

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self._log.append(" ".join(sql.split()))
        return FakeCursor(self._handler(sql, params))


class FakeDatabase:
    """Stands in for ``Database``; one connection per transaction, statements kept in ``log``."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.log: list[str] = []
        self.transactions = 0

    @contextmanager
    def transaction(self) -> Iterator[FakeConnection]:
        self.transactions += 1
        yield FakeConnection(self._handler, self.log)

    def writes(self) -> list[str]:
        """The INSERT and UPDATE statements seen so far."""
        return [s for s in self.log if s.startswith(("INSERT", "UPDATE"))]
