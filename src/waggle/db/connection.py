"""Short-lived PostgreSQL transactions with bounded connection and query waits."""

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import tuple_row

Row = tuple[object, ...]


@dataclass(frozen=True)
class Database:
    """Connection configuration; never include the DSN in repr or logs."""

    dsn: str = field(repr=False)
    schema: str = "public"
    connect_timeout_s: int = 5
    statement_timeout_ms: int = 5000
    lock_timeout_ms: int = 3000

    def __post_init__(self) -> None:
        if not isinstance(self.dsn, str) or not self.dsn.strip():
            raise ValueError("DATABASE_URL is required")
        if re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", self.schema) is None:
            raise ValueError("invalid database schema")
        for timeout in (
            self.connect_timeout_s,
            self.statement_timeout_ms,
            self.lock_timeout_ms,
        ):
            if type(timeout) is not int or not 0 < timeout <= 2**31 - 1:
                raise ValueError("database timeouts must be positive bounded integers")

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "Database":
        """Require DATABASE_URL without logging or returning its value in an error."""
        return cls(environ.get("DATABASE_URL", ""))

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection[Row]]:
        """Open a new connection, commit or roll back, then close it on every path."""
        options = (
            f"-c statement_timeout={self.statement_timeout_ms} "
            f"-c lock_timeout={self.lock_timeout_ms}"
        )
        with psycopg.connect(
            self.dsn,
            connect_timeout=self.connect_timeout_s,
            options=options,
            row_factory=tuple_row,
        ) as connection:
            connection.execute("SELECT set_config('search_path', %s, true)", (self.schema,))
            yield connection
