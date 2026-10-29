"""Each import-linter contract is checked twice.

Real contracts must pass on ``src/waggle``. The same contracts, loaded from a
separate config under ``tests/importlint_fixtures``, must fail on a fixture
package that violates them. The fixtures live outside ``src/waggle`` on purpose.
"""

import configparser
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from waggle.tasks import venv_tool

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "importlint_fixtures"

CONTRACT_IDS = [
    "sim-control-no-llm-side",
    "mcp-server-no-governance",
    "control-no-ground-truth",
]


def _lint(contract: str | None, cwd: Path, config: Path) -> subprocess.CompletedProcess[str]:
    cmd = [venv_tool("lint-imports"), "--config", str(config)]
    if contract is not None:
        cmd += ["--contract", contract]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_real_contracts_pass_on_src_waggle() -> None:
    result = _lint(None, ROOT, ROOT / "pyproject.toml")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("contract", CONTRACT_IDS)
def test_real_contract_passes(contract: str) -> None:
    result = _lint(contract, ROOT, ROOT / "pyproject.toml")
    assert result.returncode == 0, result.stdout + result.stderr


def test_lint_imports_fails_on_fixtures() -> None:
    result = _lint(None, FIXTURES, FIXTURES / ".importlinter")
    assert result.returncode != 0, result.stdout + result.stderr


@pytest.mark.parametrize("contract", CONTRACT_IDS)
def test_each_contract_fails_on_its_fixture(contract: str) -> None:
    result = _lint(contract, FIXTURES, FIXTURES / ".importlinter")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "BROKEN" in result.stdout


def test_fixture_config_mirrors_real_contracts() -> None:
    real = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    real_contracts = {c["id"]: c for c in real["tool"]["importlinter"]["contracts"]}
    assert set(real_contracts) == set(CONTRACT_IDS)

    parser = configparser.ConfigParser()
    parser.read(FIXTURES / ".importlinter", encoding="utf-8")
    for contract_id in CONTRACT_IDS:
        section = f"importlinter:contract:{contract_id}"
        assert parser.has_section(section), f"fixture config lacks {contract_id}"
        for key in ("source_modules", "forbidden_modules"):
            fixture_side = {m.removeprefix("fixture_pkg.") for m in parser[section][key].split()}
            real_side = {m.removeprefix("waggle.") for m in real_contracts[contract_id][key]}
            assert fixture_side == real_side, f"{contract_id}.{key} drifted from pyproject"
