"""The compatibility check reads the machine from the ticket and fails closed on any gap."""

from unittest.mock import MagicMock

import pytest
from db_fakes import FakeDatabase

from waggle.db.compatibility import CompatibilityRepository, IncompatiblePart, require_compatible
from waggle.db.connection import Database
from waggle.db.tickets import UnknownTicket


def _database(
    ticket: tuple[object, ...] | None, pair: tuple[object, ...] | None = (1,)
) -> FakeDatabase:
    def handler(sql: str, params: tuple[object, ...]) -> tuple[object, ...] | None:
        if "FROM maintenance_tickets" in sql:
            return ticket
        if "FROM part_compatibility" in sql:
            return pair
        raise AssertionError(sql)

    return FakeDatabase(handler)


def _check(database: FakeDatabase, ticket_id: str = "tkt-1", part: str = "P-1") -> None:
    with database.transaction() as connection:
        require_compatible(connection, ticket_id, part)  # type: ignore[arg-type]


@pytest.mark.parametrize("status", ["open", "dispatched"])
def test_a_listed_pair_on_an_open_or_dispatched_ticket_passes(status: str) -> None:
    _check(_database((status, "C1")))


def test_the_machine_comes_from_the_ticket_row() -> None:
    seen: list[tuple[object, ...]] = []

    def handler(sql: str, params: tuple[object, ...]) -> tuple[object, ...] | None:
        if "FROM maintenance_tickets" in sql:
            return ("open", "C1")
        seen.append(params)
        return (1,)

    with FakeDatabase(handler).transaction() as connection:
        require_compatible(connection, "tkt-1", "BRG-6204")  # type: ignore[arg-type]
    assert seen == [("C1", "BRG-6204")]


def test_an_unlisted_pair_is_incompatible() -> None:
    with pytest.raises(IncompatiblePart):
        _check(_database(("open", "C1"), pair=None))


def test_an_unknown_ticket_is_refused_before_the_pair_is_read() -> None:
    database = _database(None)
    with pytest.raises(UnknownTicket):
        _check(database)
    assert not any("part_compatibility" in s for s in database.log)


def test_a_ticket_that_is_neither_open_nor_dispatched_is_refused() -> None:
    with pytest.raises(UnknownTicket):
        _check(_database(("closed", "C1")))


def test_a_ticket_row_with_a_missing_machine_fails_closed() -> None:
    with pytest.raises(UnknownTicket):
        _check(_database(("open", None)))


@pytest.mark.parametrize("bad", ["", "a b", "x" * 65, "m;DROP", "café"])
def test_malformed_ids_never_connect(bad: str) -> None:
    database = MagicMock(spec=Database)
    repo = CompatibilityRepository(database)
    with pytest.raises(ValueError):
        repo.add(bad, "P-1")
    with pytest.raises(ValueError):
        repo.add("M-1", bad)
    with pytest.raises(ValueError):
        repo.exists(bad, "P-1")
    database.transaction.assert_not_called()


def test_add_inserts_one_row() -> None:
    database = FakeDatabase(lambda _sql, _params: None)
    CompatibilityRepository(database).add("C1", "BRG-6204")  # type: ignore[arg-type]
    assert database.writes() == [
        "INSERT INTO part_compatibility (machine_id, part_number) VALUES (%s, %s)"
    ]


def test_exists_and_count_read_the_table() -> None:
    database = _database(None, pair=(1,))
    repo = CompatibilityRepository(database)  # type: ignore[arg-type]
    assert repo.exists("C1", "BRG-6204") is True
    assert CompatibilityRepository(_database(None, pair=None)).exists("C1", "X") is False  # type: ignore[arg-type]
    assert CompatibilityRepository(_database(None, pair=(3,))).count() == 3  # type: ignore[arg-type]
