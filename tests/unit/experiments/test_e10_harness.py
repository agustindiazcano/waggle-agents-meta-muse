"""E10 crisis harness: mock only, baseline ablation, same templates and seeds."""

import json
from pathlib import Path

import pytest

from waggle.experiments.e10_cases import TEMPLATES, get_template
from waggle.experiments.e10_configs import CONFIGURATIONS, get_configuration
from waggle.experiments.e10_harness import run_e10, run_template
from waggle.experiments.e10_result import ResultExistsError
from waggle.llm.providers import ScriptMissingError


def _scripts() -> dict[str, tuple[str, ...]]:
    return {t.id: (t.faulty_raw, t.safe_raw) for t in TEMPLATES}


def test_templates_are_development_compound_faults_with_distinct_seeds() -> None:
    assert len(TEMPLATES) >= 3
    assert len({t.seed for t in TEMPLATES}) == len(TEMPLATES)
    assert all(t.target_layer for t in TEMPLATES)
    assert all(t.faulty_raw != t.safe_raw for t in TEMPLATES)
    with pytest.raises(KeyError):
        get_template("nope")


def test_deterministic_baseline_uses_no_llm_and_accepts_safe_plan() -> None:
    template = TEMPLATES[0]
    record = run_template(CONFIGURATIONS["deterministic_baseline"], template, {})
    assert record.status == "accepted"
    assert record.calls == 0
    assert record.cost_usd == 0.0
    assert record.seed == template.seed


def test_open_loop_escalates_when_first_plan_is_rejected() -> None:
    template = TEMPLATES[0]
    record = run_template(
        CONFIGURATIONS["llm_open_loop"], template, {template.id: (template.faulty_raw,)}
    )
    assert record.status == "escalated"
    assert record.rounds == 1
    assert record.calls == 1
    assert record.counterexamples >= 1


def test_validator_feedback_recovers_on_second_round() -> None:
    template = TEMPLATES[0]
    record = run_template(CONFIGURATIONS["llm_validator_feedback"], template, _scripts())
    assert record.status == "accepted"
    assert record.rounds == 2
    assert record.calls == 2


def test_missing_script_is_a_real_error_not_an_empty_pass() -> None:
    with pytest.raises(ScriptMissingError):
        run_template(CONFIGURATIONS["llm_open_loop"], TEMPLATES[0], {})


def test_run_e10_writes_dev_result_with_baseline_and_failing_seeds(tmp_path: Path) -> None:
    path = run_e10(
        CONFIGURATIONS["llm_validator_feedback"],
        TEMPLATES,
        _scripts(),
        commit="abc123",
        run_date="2026-11-04",
        out_dir=tmp_path,
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["seed_set"] == "development"
    assert record["held_out"] is False
    assert record["provider_mode"] == "scripted"
    assert record["prompt_version"] == "planner-v1"
    assert record["metrics"]["accepted"]["count"] == len(TEMPLATES)
    assert record["failing_seeds"] == []
    assert record["runs"] == len(TEMPLATES)
    assert record["configuration"]["name"] == "llm_validator_feedback"
    with pytest.raises(ResultExistsError):
        run_e10(
            CONFIGURATIONS["llm_validator_feedback"],
            TEMPLATES,
            _scripts(),
            commit="abc123",
            run_date="2026-11-04",
            out_dir=tmp_path,
        )


def test_run_e10_refuses_held_out_and_empty() -> None:
    with pytest.raises(ValueError):
        run_e10(
            CONFIGURATIONS["deterministic_baseline"],
            TEMPLATES,
            {},
            commit="abc",
            run_date="2026-11-04",
            out_dir=Path("unused"),
            seed_set="held_out",
        )
    with pytest.raises(ValueError):
        run_e10(
            CONFIGURATIONS["deterministic_baseline"],
            (),
            {},
            commit="abc",
            run_date="2026-11-04",
            out_dir=Path("unused"),
        )


def test_unknown_configuration_raises() -> None:
    with pytest.raises(KeyError):
        get_configuration("court_feedback")
