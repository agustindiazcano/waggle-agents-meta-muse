"""Read the oracle inputs of an E2 run from the database, without changing anything.

The event log and the final task rows are the only evidence the oracle uses
(``waggle.experiments.e2_oracle``). Every column is type checked: a value of the wrong type raises
``OracleError`` so a damaged log is reported as undecided and never counted as a pass.
"""

from waggle.db.connection import Database
from waggle.experiments.e2_oracle import OracleError, TaskEvent


def _int(value: object) -> int:
    if type(value) is not int:
        raise OracleError("an integer column held another type")
    return value


def _text(value: object) -> str:
    if type(value) is not str:
        raise OracleError("a text column held another type")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _int(value)


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def load_oracle_inputs(database: Database) -> tuple[tuple[TaskEvent, ...], dict[str, str]]:
    """Return the task events ordered by ``event_no`` and the final state of every task."""
    with database.transaction() as connection:
        event_rows = connection.execute(
            "SELECT event_no,task_id,event_kind,state,token,worker_id,expires_tick,observed_tick "
            "FROM task_events ORDER BY event_no"
        ).fetchall()
        state_rows = connection.execute("SELECT task_id,state FROM tasks").fetchall()
    events = tuple(
        TaskEvent(
            _int(row[0]),
            _text(row[1]),
            _text(row[2]),
            _text(row[3]),
            _int(row[4]),
            _optional_text(row[5]),
            _optional_int(row[6]),
            _int(row[7]),
        )
        for row in event_rows
    )
    return events, {_text(row[0]): _text(row[1]) for row in state_rows}
