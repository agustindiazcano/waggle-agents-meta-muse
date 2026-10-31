"""Database configuration and transaction lifecycle without a local database."""

from unittest.mock import MagicMock

import psycopg
import pytest

from waggle.db.connection import Database


def test_missing_configuration_fails_without_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = MagicMock()
    monkeypatch.setattr(psycopg, "connect", connect)
    for environ in ({}, {"DATABASE_URL": " "}):
        with pytest.raises(ValueError, match="DATABASE_URL"):
            Database.from_environ(environ)
    connect.assert_not_called()


def test_dsn_is_hidden_from_repr() -> None:
    database = Database("postgresql://localhost/test")
    assert "postgresql" not in repr(database)


@pytest.mark.parametrize("timeout", [0, -1, True])
def test_invalid_timeouts_are_rejected(timeout: int) -> None:
    with pytest.raises(ValueError):
        Database("postgresql://localhost/test", connect_timeout_s=timeout)
    with pytest.raises(ValueError):
        Database("postgresql://localhost/test", statement_timeout_ms=timeout)


@pytest.mark.parametrize("schema", ["", "public,other", "bad-schema", "x" * 64])
def test_invalid_schema_is_rejected(schema: str) -> None:
    with pytest.raises(ValueError):
        Database("postgresql://localhost/test", schema=schema)


def test_each_transaction_opens_and_closes_its_own_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = MagicMock(), MagicMock()
    first.__enter__.return_value = first
    second.__enter__.return_value = second
    connect = MagicMock(side_effect=[first, second])
    monkeypatch.setattr(psycopg, "connect", connect)
    database = Database.from_environ({"DATABASE_URL": "postgresql://localhost/test"})
    with database.transaction() as connection:
        assert connection is first
    with pytest.raises(ValueError, match="operation failed"), database.transaction():
        raise ValueError("operation failed")
    assert connect.call_count == 2
    assert connect.call_args.kwargs["connect_timeout"] == 5
    assert "statement_timeout=5000" in connect.call_args.kwargs["options"]
    assert "lock_timeout=3000" in connect.call_args.kwargs["options"]
    first.execute.assert_called_once_with("SELECT set_config('search_path', %s, true)", ("public",))
    assert first.__exit__.call_args.args[0] is None
    assert second.__exit__.call_args.args[0] is ValueError
