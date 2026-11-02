"""E2 log loader: turns database rows into oracle inputs and fails on a damaged column."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import pytest

from waggle.db.connection import Database
from waggle.experiments.e2_log import load_oracle_inputs
from waggle.experiments.e2_oracle import OracleError, TaskEvent

EVENT_COLUMNS = "SELECT event_no"


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _Connection:
    def __init__(self, events: list[tuple[object, ...]], states: list[tuple[object, ...]]) -> None:
        self._events = events
        self._states = states

    def execute(self, sql: str) -> _Cursor:
        return _Cursor(self._events if sql.startswith(EVENT_COLUMNS) else self._states)


class _FakeDatabase:
    def __init__(self, events: list[tuple[object, ...]], states: list[tuple[object, ...]]) -> None:
        self._connection = _Connection(events, states)

    @contextmanager
    def transaction(self) -> Iterator[_Connection]:
        yield self._connection


def _load(events: list[tuple[object, ...]], states: list[tuple[object, ...]]) -> object:
    return load_oracle_inputs(cast(Database, _FakeDatabase(events, states)))


def test_rows_become_events_and_final_states() -> None:
    claimed = (1, "t1", "claimed", "ASSIGNED", 1, "w1", 10, 0)
    done = (2, "t1", "done", "DONE", 1, None, None, 3)
    events, states = load_oracle_inputs(
        cast(Database, _FakeDatabase([claimed, done], [("t1", "DONE")]))
    )
    assert events == (
        TaskEvent(1, "t1", "claimed", "ASSIGNED", 1, "w1", 10, 0),
        TaskEvent(2, "t1", "done", "DONE", 1, None, None, 3),
    )
    assert states == {"t1": "DONE"}


@pytest.mark.parametrize(
    "row",
    [
        ("1", "t1", "claimed", "ASSIGNED", 1, "w1", 10, 0),
        (1, 7, "claimed", "ASSIGNED", 1, "w1", 10, 0),
        (1, "t1", "claimed", "ASSIGNED", True, "w1", 10, 0),
        (1, "t1", "claimed", "ASSIGNED", 1, 5, 10, 0),
        (1, "t1", "claimed", "ASSIGNED", 1, "w1", "10", 0),
        (1, "t1", "claimed", "ASSIGNED", 1, "w1", 10, None),
    ],
)
def test_a_column_of_the_wrong_type_is_undecided_not_a_pass(row: tuple[object, ...]) -> None:
    with pytest.raises(OracleError):
        _load([row], [("t1", "ASSIGNED")])


def test_a_final_state_of_the_wrong_type_is_undecided() -> None:
    with pytest.raises(OracleError):
        _load([], [("t1", 3)])
