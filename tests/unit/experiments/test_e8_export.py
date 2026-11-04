"""Automated llm_calls export feeding the existing E8 report runner."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from waggle.experiments.e8_export import build_export, export_calls, fetch_call_records
from waggle.experiments.e8_metrics import summarize_calls
from waggle.experiments.e8_run import load_calls, main

ROWS = [
    ("req-1", "task-1", "advisor", "meta", "model-1", "ok", 10, 2, 0.25, 0.01, None),
    ("req-2", None, "advisor", "meta", "model-1", "error", 0, 0, 0.0, 0.0, "backup"),
    ("req-3", "task-1", "advisor", "meta", "model-1", "cached", 0, 0, 0.0, 0.0, None),
]


class FakeCursor:
    """Cursor returning fixed rows."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all rows."""
        return list(self._rows)


class FakeConnection:
    """Connection recording the executed query."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows
        self.sql = ""
        self.params: tuple[object, ...] = ()

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> FakeCursor:
        """Record the query and return fixed rows."""
        self.sql = sql
        self.params = params
        return FakeCursor(self._rows)


class FakeDatabase:
    """Database stand-in with the transaction shape of waggle.db.Database."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.connection = FakeConnection(rows)

    @contextmanager
    def transaction(self) -> Iterator[FakeConnection]:
        """Yield the fake connection."""
        yield self.connection


def test_fetch_filters_by_mode_in_insertion_order() -> None:
    database = FakeDatabase(list(ROWS))
    records = fetch_call_records(database, mode="http")
    assert "WHERE mode = %s" in database.connection.sql
    assert "ORDER BY call_id" in database.connection.sql
    assert database.connection.params == ("http",)
    assert [record.request_id for record in records] == ["req-1", "req-2", "req-3"]
    assert records[1].task_id is None
    assert records[1].fallback_label == "backup"
    assert summarize_calls(records)["status_counts"] == {
        "ok": 1,
        "denied": 0,
        "error": 1,
        "cached": 1,
    }


def test_build_export_round_trips_through_existing_loader(tmp_path: Path) -> None:
    records = fetch_call_records(FakeDatabase(list(ROWS)), mode="mock")
    document = build_export(
        records, mode="mock", commit="abc123", prompt_versions={"advisor": "v1"}
    )
    assert set(document) == {"source", "mode", "commit", "prompt_versions", "records"}
    rows = document["records"]
    assert isinstance(rows, list)
    assert set(rows[0]) == {
        "request_id",
        "task_id",
        "role",
        "provider",
        "model_id",
        "status",
        "tokens_in",
        "tokens_out",
        "latency_s",
        "cost_usd",
        "fallback_label",
    }
    path = tmp_path / "calls-export.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded, metadata = load_calls(path)
    assert loaded == records
    assert metadata["mode"] == "mock"
    assert summarize_calls(loaded) == summarize_calls(records)


def test_export_calls_writes_export_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "calls-export.json"
    document = export_calls(
        FakeDatabase(list(ROWS)),
        mode="http",
        commit="abc123",
        prompt_versions={"advisor": "v1"},
        output=output,
    )
    assert json.loads(output.read_text(encoding="utf-8")) == document
    with pytest.raises(FileExistsError):
        export_calls(
            FakeDatabase(list(ROWS)),
            mode="http",
            commit="abc123",
            prompt_versions={"advisor": "v1"},
            output=output,
        )


@pytest.mark.parametrize(
    "mode,commit,prompt_versions,rows",
    [
        ("unknown", "abc123", {"advisor": "v1"}, ROWS),
        ("http", "", {"advisor": "v1"}, ROWS),
        ("http", "abc123", {}, ROWS),
        ("http", "abc123", {"other": "v1"}, ROWS),
        ("http", "abc123", {"advisor": "v1"}, []),
        (
            "http",
            "abc123",
            {"advisor": "v1"},
            [("r", "t", "advisor", "meta", "m", "bogus", 0, 0, 0.0, 0.0, None)],
        ),
    ],
)
def test_export_rejects_invalid_inputs(
    mode: str,
    commit: str,
    prompt_versions: dict[str, str],
    rows: list[tuple[object, ...]],
) -> None:
    with pytest.raises(ValueError):
        export_calls(
            FakeDatabase(list(rows)),
            mode=mode,
            commit=commit,
            prompt_versions=prompt_versions,
            output=Path("unused.json"),
        )


def test_export_cli_uses_injected_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "calls-export.json"
    monkeypatch.setattr(
        "waggle.experiments.e8_run._database_from_environ",
        lambda: FakeDatabase(list(ROWS)),
    )
    assert (
        main(
            [
                "export",
                "--mode",
                "http",
                "--commit",
                "abc123",
                "--prompt-version",
                "advisor=v1",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    records, metadata = load_calls(output)
    assert len(records) == 3
    assert metadata["commit"] == "abc123"
    report = tmp_path / "report.json"
    assert main(["calls", "--input", str(output), "--output", str(report)]) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["llm_calls"]["total_rows"] == 3
