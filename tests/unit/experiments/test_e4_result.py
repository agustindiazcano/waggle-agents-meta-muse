"""E4 result record and exclusive result file (AGENTS.md 9.2 and 9.6)."""

import json
from pathlib import Path

import pytest

from waggle.experiments.e4_configs import CONFIGURATIONS
from waggle.experiments.e4_metrics import RunRecord, Summary, VoteRecord
from waggle.experiments.e4_result import (
    WARNING,
    ResultExistsError,
    build_record,
    result_path,
    write_result,
)


def _vote(role: str, verdict: str | None, label: str | None = None) -> VoteRecord:
    return VoteRecord(role, verdict, None if verdict else "timeout", f"model-{role}", label)


def _runs() -> list[RunRecord]:
    return [
        RunRecord("r1", "risky", 0, "execute", "unanimous", (_vote("court_1", "approve"),)),
        RunRecord("b1", "benign", 0, "escalate", "reject", (_vote("court_1", "reject"),)),
        RunRecord(
            "b2", "benign", 0, "execute", "unanimous", (_vote("court_1", "approve", "fallback:x"),)
        ),
    ]


def _record(seed_set: str = "development", held_out: bool = False) -> Summary:
    return build_record(
        config=CONFIGURATIONS["A_single"],
        seed_set=seed_set,
        held_out=held_out,
        commit="abc1234",
        run_date="2026-11-02",
        runs=_runs(),
        prompt_version="court-v1",
        prompt_hash="f" * 64,
    )


def test_the_record_has_the_fields_the_protocol_requires() -> None:
    record = _record()
    for key in (
        "commit",
        "seed_set",
        "model_ids",
        "prompt_version",
        "prompt_hash",
        "date",
        "realized_composition",
        "fallback_labels",
        "held_out",
    ):
        assert key in record
    assert record["commit"] == "abc1234" and record["date"] == "2026-11-02"
    assert record["held_out"] is False
    assert record["model_ids"] == {"court_1": ["model-court_1"]}
    assert record["fallback_labels"] == ["fallback:x"]
    assert record["prompt_version"] == "court-v1"


def test_the_record_carries_the_fixed_warning_and_the_scripted_mode() -> None:
    record = _record()
    assert record["warning"] == WARNING
    assert "not a model result" in WARNING.lower()
    assert record["provider_mode"] == "scripted"


def test_the_metrics_come_in_the_protocol_order_with_false_approvals_first() -> None:
    metrics = _record()["metrics"]
    assert isinstance(metrics, dict)
    assert list(metrics)[:4] == ["false_approvals", "false_blocks", "ambiguous", "escalation"]
    assert metrics["false_approvals"]["case_ids"] == ["r1"]
    assert metrics["false_blocks"]["case_ids"] == ["b1"]
    assert {"agreement", "error_correlation", "latency", "cost"} <= set(metrics)


def test_failing_case_ids_and_the_repeat_label_are_listed() -> None:
    record = _record()
    assert record["failing_case_ids"] == {"false_approvals": ["r1"], "false_blocks": ["b1"]}
    assert record["repeats"] == 1
    assert "not independent" in str(record["repeat_note"]).lower()


def test_realized_composition_lists_each_run() -> None:
    composition = _record()["realized_composition"]
    assert composition[0] == {
        "case_id": "r1",
        "repeat": 0,
        "request_suffix": "-r0",
        "members": [{"role": "court_1", "model_id": "model-court_1", "fallback_label": None}],
    }


def test_held_out_flag_must_match_the_seed_set() -> None:
    with pytest.raises(ValueError, match="held_out"):
        _record(seed_set="held_out", held_out=False)
    with pytest.raises(ValueError, match="held_out"):
        _record(seed_set="development", held_out=True)
    assert _record(seed_set="held_out", held_out=True)["held_out"] is True


def test_an_empty_commit_or_date_is_refused() -> None:
    with pytest.raises(ValueError, match="commit"):
        build_record(
            config=CONFIGURATIONS["A_single"],
            seed_set="development",
            held_out=False,
            commit=" ",
            run_date="2026-11-02",
            runs=_runs(),
            prompt_version="court-v1",
            prompt_hash="f" * 64,
        )


def test_the_result_file_is_created_once_and_never_overwritten(tmp_path: Path) -> None:
    path = result_path(tmp_path, "A_single", "development")
    assert path.name == "e4_A_single_development.json"
    write_result(path, _record())
    first = path.read_text(encoding="utf-8")
    with pytest.raises(ResultExistsError):
        write_result(path, _record())
    assert path.read_text(encoding="utf-8") == first
    assert json.loads(first)["warning"] == WARNING


def test_the_baseline_and_court_configurations_get_different_paths(tmp_path: Path) -> None:
    names = {result_path(tmp_path, n, "development").name for n in CONFIGURATIONS}
    assert len(names) == len(CONFIGURATIONS)


def test_a_path_with_separators_in_the_config_name_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        result_path(tmp_path, "../x", "development")
