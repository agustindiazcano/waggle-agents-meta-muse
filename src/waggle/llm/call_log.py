"""Call log interface and an in-memory implementation.

The llm_calls table arrives in a later phase and will implement the same interface.
"""

from typing import Protocol

from waggle.llm.models import CallRecord


class CallLog(Protocol):
    """Append-only log of LLM calls."""

    def record(self, record: CallRecord) -> None:
        """Append one record."""

    def records(self) -> list[CallRecord]:
        """Return all records in order."""


class InMemoryCallLog:
    """Call log kept in a list, for tests and local runs."""

    def __init__(self) -> None:
        self._records: list[CallRecord] = []

    def record(self, record: CallRecord) -> None:
        """Append one record."""
        self._records.append(record)

    def records(self) -> list[CallRecord]:
        """Return a copy of all records in order."""
        return list(self._records)
