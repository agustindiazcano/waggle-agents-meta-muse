"""Entry point wiring for the MCP server (ADR-047).

Every setting is required and read from the environment. A missing or invalid value stops the
process before it reads a line, and no error text carries a setting value.
"""

import math
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TextIO
from uuid import uuid4

from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.identities import PostgresIdentityStore
from waggle.db.mcp_audit import McpAuditRepository, RateLimit
from waggle.db.occupancy import TrustedStateRepository
from waggle.db.schema import LATEST_REVISION, current_revision
from waggle.db.tasks import TaskRepository
from waggle.mcp_server.boundary import Boundary
from waggle.mcp_server.bounds import MapExtent
from waggle.mcp_server.forwarder import FencedForwarder
from waggle.mcp_server.transport import LineServer, serve_stdio

_TOKEN_MIN = 32
_TIMEOUT_MAX_S = 60.0


class ConfigError(Exception):
    """A setting is missing or invalid. The message names the variable, never its value."""


@dataclass(frozen=True)
class Settings:
    """Everything the server needs besides the database address."""

    token: str
    extent: MapExtent
    limit: RateLimit
    timeout_s: float


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "")
    if not value.strip():
        raise ConfigError(f"{name} is required")
    return value.strip()


def _integer(environ: Mapping[str, str], name: str) -> int:
    try:
        return int(_required(environ, name))
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None


def _extent(environ: Mapping[str, str]) -> MapExtent:
    name = "WAGGLE_MCP_EXTENT"
    parts = _required(environ, name).split(",")
    try:
        if len(parts) != 4:
            raise ValueError("four values")
        return MapExtent(*(float(part) for part in parts))
    except ValueError:
        raise ConfigError(f"{name} must be x_min,y_min,x_max,y_max with finite values") from None


def _timeout(environ: Mapping[str, str]) -> float:
    name = "WAGGLE_MCP_TIMEOUT_S"
    try:
        value = float(_required(environ, name))
    except ValueError:
        raise ConfigError(f"{name} must be a number") from None
    if not math.isfinite(value) or not 0 < value <= _TIMEOUT_MAX_S:
        raise ConfigError(f"{name} must be above 0 and at most {_TIMEOUT_MAX_S:g}")
    return value


def parse_settings(environ: Mapping[str, str]) -> Settings:
    """Read and validate every setting, or raise ConfigError."""
    token = _required(environ, "WAGGLE_MCP_TOKEN")
    if len(token) < _TOKEN_MIN:
        raise ConfigError("WAGGLE_MCP_TOKEN is too short")
    try:
        limit = RateLimit(
            _integer(environ, "WAGGLE_MCP_RATE_MAX_CALLS"),
            _integer(environ, "WAGGLE_MCP_RATE_WINDOW_S"),
        )
    except ValueError:
        raise ConfigError(
            "WAGGLE_MCP_RATE_MAX_CALLS or WAGGLE_MCP_RATE_WINDOW_S out of range"
        ) from None
    return Settings(token, _extent(environ), limit, _timeout(environ))


def build_server(environ: Mapping[str, str], database: Database, session: str) -> LineServer:
    """Wire the boundary over the database repositories. Opens no connection."""
    settings = parse_settings(environ)
    trusted = TrustedStateRepository(database)
    forwarder = FencedForwarder(
        CorridorRepository(database), TaskRepository(database), trusted, trusted
    )
    boundary = Boundary(
        PostgresIdentityStore(database),
        McpAuditRepository(database),
        forwarder,
        settings.extent,
        settings.limit,
        settings.timeout_s,
    )
    return LineServer(boundary, settings.token, session)


def main(
    environ: Mapping[str, str],
    source: TextIO,
    sink: TextIO,
    errors: TextIO,
    revision: Callable[[Database], int] = current_revision,
) -> int:
    """Serve stdio until end of input. Return 2 when configuration or schema is wrong."""
    try:
        database = Database.from_environ(environ)
        server = build_server(environ, database, uuid4().hex[:16])
    except (ConfigError, ValueError) as err:
        message = str(err) if isinstance(err, ConfigError) else "DATABASE_URL is required"
        errors.write(f"mcp_server configuration error: {message}\n")
        return 2
    try:
        installed = revision(database)
    except Exception as err:
        # Fail closed. Only the exception class is reported: driver text can carry the address.
        errors.write(f"mcp_server cannot read the schema revision: {type(err).__name__}\n")
        return 2
    if installed != LATEST_REVISION:
        errors.write(f"mcp_server needs schema revision {LATEST_REVISION}, found {installed}\n")
        return 2
    serve_stdio(server, source, sink)
    return 0


def run() -> int:
    """Process entry: real environment and standard streams."""
    return main(os.environ, sys.stdin, sys.stdout, sys.stderr)
