"""The observation module is a leaf, so control can import it without reaching ground truth.

The import-linter contract ``control-no-ground-truth`` also flags indirect import chains.
If ``waggle.sim.__init__`` or ``waggle.sim.observations`` imported a ground-truth module,
``waggle.control`` would reach it through them and the contract would break.
"""

import ast
from pathlib import Path

import pytest

SIM = Path(__file__).resolve().parents[2] / "src" / "waggle" / "sim"
GROUND_TRUTH = ["world", "entities", "engine", "detector", "sensors"]


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(("." * node.level) + (node.module or ""))
    return names


def test_sim_package_init_imports_nothing() -> None:
    assert _imports(SIM / "__init__.py") == []


def test_observations_module_exists_and_is_a_leaf() -> None:
    path = SIM / "observations.py"
    assert path.is_file()
    offending = [n for n in _imports(path) if "waggle" in n or n.startswith(".")]
    assert offending == [], f"observations must not import project modules: {offending}"


@pytest.mark.parametrize("name", GROUND_TRUTH)
def test_ground_truth_module_exists(name: str) -> None:
    assert (SIM / f"{name}.py").is_file()
