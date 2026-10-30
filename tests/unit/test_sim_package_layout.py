"""The observation module is a leaf, so control can import it without reaching ground truth.

The import-linter contract ``control-no-ground-truth`` also flags indirect import chains.
If ``waggle.sim.__init__`` or ``waggle.sim.observations`` imported a ground-truth module,
``waggle.control`` would reach it through them and the contract would break.
"""

import ast
from pathlib import Path

import pytest

SIM = Path(__file__).resolve().parents[2] / "src" / "waggle" / "sim"
LEAVES = {"__init__", "observations", "params"}
GROUND_TRUTH = [
    "world",
    "state",
    "streams",
    "engine",
    "robots",
    "humans",
    "detector",
    "sensors",
    "hullgap",
    "fastlidar",
    "rollout",
    "scenarios",
    "scripted",
]


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


def test_params_module_is_a_leaf() -> None:
    path = SIM / "params.py"
    assert path.is_file()
    offending = [n for n in _imports(path) if "waggle" in n or n.startswith(".")]
    assert offending == [], f"params must not import project modules: {offending}"


def test_every_sim_module_is_a_leaf_or_forbidden_to_control() -> None:
    """The contract lists each non-leaf module, so a new module cannot slip past it."""
    import tomllib

    config = tomllib.loads((SIM.parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    contract = next(
        c
        for c in config["tool"]["importlinter"]["contracts"]
        if c["id"] == "control-no-ground-truth"
    )
    forbidden = {m.removeprefix("waggle.sim.") for m in contract["forbidden_modules"]}
    modules = {p.stem for p in SIM.glob("*.py")} - LEAVES
    assert modules == forbidden, f"contract and modules differ: {modules ^ forbidden}"


def test_observations_module_exists_and_is_a_leaf() -> None:
    path = SIM / "observations.py"
    assert path.is_file()
    offending = [n for n in _imports(path) if "waggle" in n or n.startswith(".")]
    assert offending == [], f"observations must not import project modules: {offending}"


@pytest.mark.parametrize("name", GROUND_TRUTH)
def test_ground_truth_module_exists(name: str) -> None:
    assert (SIM / f"{name}.py").is_file()
