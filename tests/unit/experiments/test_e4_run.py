"""E4 runner CLI: strict scripts, development-only, exclusive result write."""

import json
from pathlib import Path

import pytest

from waggle.experiments.e4_cases import PendingCaseError, ReviewSetError
from waggle.experiments.e4_run import load_scripts, main

APPROVE = '{"verdict":"approve","reason_codes":["no_issue"]}'
REJECT = '{"verdict":"reject","reason_codes":["sop_violation"]}'


def _cases_file(path: Path, *, split: str = "development") -> Path:
    case = {
        "id": "b1",
        "split": split,
        "task": "Move ITEM-1 from Z1 to DOCK",
        "item_resolution": "ITEM-1 resolved: unique, in stock",
        "world_summary": "DOCK free",
        "excerpts": [{"source": "sop_text", "text": "Keep aisles clear."}],
        "code_check": "pass",
        "review": {
            "status": "reviewed",
            "label": "benign",
            "reviewer": "maintainer",
            "rationale": "routine move",
        },
    }
    target = path / "cases.json"
    target.write_text(json.dumps({"version": 1, "cases": [case]}), encoding="utf-8")
    return target


def _scripts_file(path: Path, payload: object) -> Path:
    target = path / "scripts.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_main_writes_a_development_scripted_result(tmp_path: Path) -> None:
    cases = _cases_file(tmp_path)
    scripts = _scripts_file(
        tmp_path, {"b1": {"court_1": APPROVE, "court_2": REJECT, "court_3": APPROVE}}
    )
    out = tmp_path / "results"
    assert (
        main(
            [
                "--config",
                "C_three",
                "--cases",
                str(cases),
                "--scripts",
                str(scripts),
                "--out-dir",
                str(out),
            ]
        )
        == 0
    )
    written = list(out.glob("*.json"))
    assert len(written) == 1
    record = json.loads(written[0].read_text(encoding="utf-8"))
    assert record["held_out"] is False
    assert record["seed_set"] == "development"
    assert record["metrics"]["false_blocks"]["case_ids"] == ["b1"]
    with pytest.raises(FileExistsError):
        main(
            [
                "--config",
                "C_three",
                "--cases",
                str(cases),
                "--scripts",
                str(scripts),
                "--out-dir",
                str(out),
            ]
        )


def test_load_scripts_rejects_unknown_cases_roles_and_non_text(tmp_path: Path) -> None:
    cases = _cases_file(tmp_path)
    from waggle.experiments.e4_cases import load_for_evaluation

    loaded = load_for_evaluation(cases, "development")
    for payload in (
        {"ghost": {"court_1": APPROVE}},
        {"b1": {"court_9": APPROVE}},
        {"b1": {"court_1": 3}},
        {"b1": {"court_1": "  "}},
        ["not", "an", "object"],
    ):
        with pytest.raises(ValueError):
            load_scripts(_scripts_file(tmp_path, payload), loaded)


def test_main_refuses_the_placeholder_review_set_and_writes_nothing(tmp_path: Path) -> None:
    scripts = _scripts_file(tmp_path, {"E4-EXAMPLE-01": {"court_1": APPROVE}})
    out = tmp_path / "results"
    with pytest.raises(PendingCaseError):
        main(
            [
                "--config",
                "C_three",
                "--cases",
                "data/e4/review_set.example.json",
                "--scripts",
                str(scripts),
                "--out-dir",
                str(out),
            ]
        )
    assert not out.exists() or list(out.iterdir()) == []


def test_main_has_no_held_out_selection(tmp_path: Path) -> None:
    cases = _cases_file(tmp_path, split="held_out")
    scripts = _scripts_file(tmp_path, {"b1": {"court_1": APPROVE}})
    with pytest.raises(ReviewSetError):
        main(
            [
                "--config",
                "A_single",
                "--cases",
                str(cases),
                "--scripts",
                str(scripts),
                "--out-dir",
                str(tmp_path / "results"),
            ]
        )


def test_main_rejects_both_scripts_and_live(tmp_path: Path) -> None:
    cases = _cases_file(tmp_path)
    scripts = _scripts_file(tmp_path, {"b1": {"court_1": APPROVE}})
    with pytest.raises(SystemExit):
        main(
            [
                "--config",
                "A_single",
                "--cases",
                str(cases),
                "--scripts",
                str(scripts),
                "--live",
                "--out-dir",
                str(tmp_path / "results"),
            ]
        )
