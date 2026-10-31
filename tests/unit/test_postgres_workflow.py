"""The PostgreSQL integration workflow is manual, bounded and has no provider secrets."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_postgres_workflow_runs_real_database_tests_without_model_credentials() -> None:
    workflow = (ROOT / ".github/workflows/postgres.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow and "pull_request:" not in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "timeout-minutes:" in workflow
    assert "pgvector/pgvector:pg16" in workflow
    assert "pg_isready" in workflow
    assert "DATABASE_URL:" in workflow
    assert "secrets." not in workflow
    assert "tests/integration/db -m heavy" in workflow
    assert "uv sync --locked" in workflow
    assert "if: always()" in workflow
    assert "postgres-test-report.xml" in workflow
