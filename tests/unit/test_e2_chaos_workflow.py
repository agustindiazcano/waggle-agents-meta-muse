"""The E2 chaos workflow is opt-in, cloud-only and development-only."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/e2_chaos.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_the_chaos_workflow_is_manual_and_has_no_secrets() -> None:
    text = _text()
    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "secrets." not in text
    assert "contents: read" in text
    assert "timeout-minutes:" in text


def test_it_uses_the_postgres_service_and_names_its_image() -> None:
    text = _text()
    assert "pgvector/pgvector:pg16" in text
    assert "E2_POSTGRES_IMAGE" in text
    assert "DATABASE_URL" in text


def test_it_runs_the_sweep_on_development_seeds_only() -> None:
    text = _text()
    assert "uv sync --locked" in text
    assert "uv run python -m waggle.experiments.e2_sweep" in text
    assert "--seed-set development" in text
    assert "held_out" not in text
    assert "results/e2/dev/chaos_*.json" in text
    assert "if-no-files-found: error" in text
    assert "|| true" not in text
    assert "exit 0" not in text


def test_inputs_reach_the_command_through_environment_variables() -> None:
    lines = _text().splitlines()
    assert not [line for line in lines if "run:" in line and "inputs." in line]
    assert any(line.strip() == "ARM: ${{ inputs.arm }}" for line in lines)
    assert any(line.strip() == "SEEDS: ${{ inputs.seeds }}" for line in lines)
    assert any('--arm "$ARM"' in line and '--seeds "$SEEDS"' in line for line in lines)
