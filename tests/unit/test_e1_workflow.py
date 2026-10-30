"""The E1 workflow: manual, development seeds only, one job per configuration, no secrets."""

from pathlib import Path

from waggle.experiments.e1_config import CONFIGS

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "e1.yml").read_text(encoding="utf-8")


def test_manual_trigger_only() -> None:
    assert "workflow_dispatch:" in WORKFLOW
    assert "push:" not in WORKFLOW
    assert "pull_request:" not in WORKFLOW


def test_there_is_no_way_to_ask_for_held_out_seeds() -> None:
    assert "heldout" not in WORKFLOW.replace("held-out", "")
    assert "seed_set" not in WORKFLOW
    assert "inputs:" not in WORKFLOW


def test_every_configuration_has_a_job_in_the_matrix() -> None:
    for config in CONFIGS:
        assert f"          - {config.name}\n" in WORKFLOW


def test_the_configuration_comes_from_env_and_not_from_a_shell_expression() -> None:
    assert 'experiments-dev --config "$CONFIG"' in WORKFLOW
    assert "CONFIG: ${{ matrix.config }}" in WORKFLOW


def test_no_secrets_and_read_only_token() -> None:
    assert "secrets." not in WORKFLOW
    assert "contents: read" in WORKFLOW


def test_results_and_report_are_uploaded() -> None:
    assert "results/e1/dev/*.json" in WORKFLOW
    assert "results/e1/dev/report.md" in WORKFLOW
    assert "uv run report" in WORKFLOW
