"""The E2 simulator sweep is opt-in, cloud-only and development-only."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/e2.yml"


def test_e2_workflow_is_manual_and_development_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "inputs:" not in text
    assert "secrets." not in text
    assert "contents: read" in text
    assert "timeout-minutes:" in text


def test_e2_workflow_runs_the_production_runner_and_requires_an_artifact() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "uv sync --locked" in text
    assert "uv run python -m waggle.experiments.e2_simulator" in text
    assert "results/e2/dev/s03_admission_*.json" in text
    assert "if-no-files-found: error" in text
    assert "|| true" not in text
    assert "exit 0" not in text
