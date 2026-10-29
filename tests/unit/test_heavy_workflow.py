from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "heavy.yml").read_text(encoding="utf-8")


def test_manual_trigger_only_with_inputs() -> None:
    assert "workflow_dispatch:" in WORKFLOW
    assert "marker:" in WORKFLOW
    assert "seed_set:" in WORKFLOW
    assert "push:" not in WORKFLOW
    assert "pull_request:" not in WORKFLOW


def test_github_hosted_runner_with_postgres_service() -> None:
    assert "runs-on: ubuntu-latest" in WORKFLOW
    assert "services:" in WORKFLOW
    assert "pgvector/pgvector" in WORKFLOW


def test_marker_comes_from_env_and_is_validated() -> None:
    assert 'pytest -m "$MARKER"' in WORKFLOW
    assert "${{ inputs.marker }}" in WORKFLOW
    assert "run: uv run pytest -m ${{ inputs" not in WORKFLOW  # no direct expression in shell


def test_exit_code_5_allowance_is_explicit() -> None:
    assert "-eq 5" in WORKFLOW
    assert "remove" in WORKFLOW.lower()  # comment pointing at the PENDING item


def test_results_are_uploaded_as_artifact() -> None:
    assert "actions/upload-artifact" in WORKFLOW
    assert "results/**/*.json" in WORKFLOW


def test_provider_secrets_only_in_this_workflow() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "secrets." not in ci
    assert "secrets.META_API_KEY" in WORKFLOW
