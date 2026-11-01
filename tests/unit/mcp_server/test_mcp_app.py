"""Entry point wiring: settings come from the environment and a missing value fails closed."""

import io
import json
from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.mcp_audit import RateLimit
from waggle.db.schema import LATEST_REVISION
from waggle.mcp_server.app import (
    ConfigError,
    Settings,
    build_forwarder,
    build_server,
    main,
    parse_settings,
)
from waggle.mcp_server.bounds import MapExtent
from waggle.mcp_server.identity import Identity

TOKEN = "d" * 43
ENV = {
    "DATABASE_URL": "postgresql://user:secret-password@localhost:1/none",
    "WAGGLE_MCP_TOKEN": TOKEN,
    "WAGGLE_MCP_EXTENT": "0,0,100,60",
    "WAGGLE_MCP_RATE_MAX_CALLS": "30",
    "WAGGLE_MCP_RATE_WINDOW_S": "10",
    "WAGGLE_MCP_TIMEOUT_S": "5",
}


def test_parse_settings_reads_every_value() -> None:
    settings = parse_settings(ENV)
    assert settings == Settings(
        token=TOKEN,
        extent=MapExtent(0.0, 0.0, 100.0, 60.0),
        limit=RateLimit(30, 10),
        timeout_s=5.0,
    )


@pytest.mark.parametrize(
    "missing",
    [
        "WAGGLE_MCP_TOKEN",
        "WAGGLE_MCP_EXTENT",
        "WAGGLE_MCP_RATE_MAX_CALLS",
        "WAGGLE_MCP_RATE_WINDOW_S",
        "WAGGLE_MCP_TIMEOUT_S",
    ],
)
def test_a_missing_setting_fails_closed_and_names_the_variable(missing: str) -> None:
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        parse_settings(env)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("WAGGLE_MCP_EXTENT", "0,0,100"),
        ("WAGGLE_MCP_EXTENT", "0,0,nan,60"),
        ("WAGGLE_MCP_EXTENT", "10,0,5,60"),
        ("WAGGLE_MCP_RATE_MAX_CALLS", "0"),
        ("WAGGLE_MCP_RATE_MAX_CALLS", "many"),
        ("WAGGLE_MCP_RATE_WINDOW_S", "99999"),
        ("WAGGLE_MCP_TIMEOUT_S", "0"),
        ("WAGGLE_MCP_TIMEOUT_S", "61"),
        ("WAGGLE_MCP_TIMEOUT_S", "nan"),
    ],
)
def test_an_invalid_setting_is_refused(name: str, value: str) -> None:
    with pytest.raises(ConfigError, match=name):
        parse_settings({**ENV, name: value})


def test_the_error_never_contains_the_token_or_the_database_url() -> None:
    env = {**ENV, "WAGGLE_MCP_EXTENT": "bad"}
    with pytest.raises(ConfigError) as caught:
        parse_settings(env)
    text = str(caught.value)
    assert TOKEN not in text
    assert "secret-password" not in text


def test_a_short_token_is_refused() -> None:
    with pytest.raises(ConfigError, match="WAGGLE_MCP_TOKEN"):
        parse_settings({**ENV, "WAGGLE_MCP_TOKEN": "short"})


def test_build_server_builds_without_connecting_to_the_database() -> None:
    server = build_server(ENV, Database(ENV["DATABASE_URL"]), session="test")
    reply = server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    assert reply is not None
    assert json.loads(reply)["error"]["code"] == -32602


def test_main_without_configuration_exits_nonzero_and_writes_only_to_stderr() -> None:
    out, err = io.StringIO(), io.StringIO()
    code = main({}, io.StringIO(""), out, err)
    assert code == 2
    assert out.getvalue() == ""
    assert "DATABASE_URL" in err.getvalue()


def test_main_refuses_an_old_schema_revision() -> None:
    out, err = io.StringIO(), io.StringIO()
    code = main(ENV, io.StringIO(""), out, err, revision=lambda _db: LATEST_REVISION - 1)
    assert code == 2
    assert out.getvalue() == ""
    assert "revision" in err.getvalue()
    assert "secret-password" not in err.getvalue()


def test_main_refuses_when_the_revision_cannot_be_read() -> None:
    def broken(_db: Database) -> int:
        raise RuntimeError("could not connect to postgresql://user:secret-password@host")

    out, err = io.StringIO(), io.StringIO()
    code = main(ENV, io.StringIO(""), out, err, revision=broken)
    assert code == 2
    assert "secret-password" not in err.getvalue()


def test_main_serves_lines_when_the_revision_matches() -> None:
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    out, err = io.StringIO(), io.StringIO()
    code = main(ENV, io.StringIO(request + "\n"), out, err, revision=lambda _db: LATEST_REVISION)
    assert code == 0
    assert json.loads(out.getvalue())["result"] == {}
    assert err.getvalue() == ""


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_inventory", {"part_number": "P-1"}),
        ("reserve_part", {"part_number": "P-1", "quantity": 1, "idempotency_key": "k"}),
        ("open_ticket", {"machine_id": "M-1", "idempotency_key": "k", "summary": "s"}),
        ("dispatch_tech", {"ticket_id": "tkt-0123456789abcdef", "zone_id": "z"}),
        ("create_purchase_order", {"part_number": "P-1", "quantity": 1, "idempotency_key": "k"}),
    ],
)
def test_maintenance_tools_are_wired_to_the_database(tool: str, args: dict[str, object]) -> None:
    """A wired tool reaches the database and fails to connect; an unwired one is unavailable."""
    database = MagicMock(spec=Database)
    database.transaction.side_effect = ConnectionError("no database in unit tests")
    forwarder = build_forwarder(database)
    with pytest.raises(ConnectionError):
        forwarder.forward(Identity("maintenance", "maint-0"), tool, args, 5.0)
    database.transaction.assert_called()
