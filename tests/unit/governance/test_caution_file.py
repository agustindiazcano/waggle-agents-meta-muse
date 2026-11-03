"""Caution log file: JSON lines, atomic write, fail closed load (no database)."""

from pathlib import Path

import pytest

from waggle.governance.caution import (
    CautionAction,
    CautionConfig,
    CautionEvent,
    CautionRejected,
)
from waggle.governance.caution_file import load_caution_log, write_caution_log
from waggle.governance.caution_log import CautionLog

CONFIG = CautionConfig(max_window_ticks=100, h_max_ticks=50, n_max_holds=3)


def _event(request_id: str, tick: int = 5) -> CautionEvent:
    return CautionEvent(
        run_id="run-1",
        robot_id="robot-0",
        issue_tick=tick,
        effective_tick=tick,
        expiry_tick=tick + 20,
        action=CautionAction.SLOW,
        speed_cap=0.3,
        code=None,
        call_request_id=request_id,
        validator_verdict="accepted",
    )


def _log(*ids: str) -> CautionLog:
    log = CautionLog(CONFIG)
    for n, request_id in enumerate(ids):
        log.submit(_event(request_id, tick=5 + n), owner_robot="robot-0", task_id="t")
    return log


def test_round_trip_keeps_events_and_digest(tmp_path: Path) -> None:
    log = _log("a-1", "a-2")
    target = tmp_path / "cautions.jsonl"
    write_caution_log(target, log)
    loaded = load_caution_log(target, CONFIG)
    assert loaded.events == log.events
    assert loaded.digest() == log.digest()


def test_path_is_independent_of_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    target = tmp_path / "out" / "c.jsonl"
    write_caution_log(target, _log("a-1"))
    assert target.exists()
    assert list(other.iterdir()) == []


def test_write_leaves_no_temp_file_and_replaces_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "c.jsonl"
    write_caution_log(target, _log("a-1"))
    write_caution_log(target, _log("b-1", "b-2"))
    assert [p.name for p in tmp_path.iterdir()] == ["c.jsonl"]
    assert len(load_caution_log(target, CONFIG).events) == 2


def test_a_failed_write_keeps_the_old_file_and_cleans_the_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "c.jsonl"
    write_caution_log(target, _log("a-1"))
    before = target.read_text(encoding="utf-8")

    def boom(src: object, dst: object) -> None:
        raise OSError("disk")

    monkeypatch.setattr("waggle.governance.caution_file.os.replace", boom)
    with pytest.raises(OSError):
        write_caution_log(target, _log("b-1"))
    assert target.read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == ["c.jsonl"]


def test_a_bad_line_rejects_the_whole_file(tmp_path: Path) -> None:
    target = tmp_path / "c.jsonl"
    write_caution_log(target, _log("a-1", "a-2"))
    good = target.read_text(encoding="utf-8").splitlines()
    target.write_text("\n".join([good[0], '{"action":"slow"}', good[1]]) + "\n", encoding="utf-8")
    with pytest.raises(CautionRejected):
        load_caution_log(target, CONFIG)


def test_a_widening_event_in_the_file_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "c.jsonl"
    write_caution_log(target, _log("a-1"))
    text = target.read_text(encoding="utf-8").replace('"expiry_tick":25', '"expiry_tick":9999')
    target.write_text(text, encoding="utf-8")
    with pytest.raises(CautionRejected):
        load_caution_log(target, CONFIG)


def test_a_non_utf8_or_missing_file_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(CautionRejected):
        load_caution_log(bad, CONFIG)
    with pytest.raises(FileNotFoundError):
        load_caution_log(tmp_path / "missing.jsonl", CONFIG)


def test_an_empty_log_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "c.jsonl"
    write_caution_log(target, CautionLog(CONFIG))
    assert load_caution_log(target, CONFIG).events == ()
