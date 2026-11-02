"""Simulator and predictor share no equations, parameters or imports (AGENTS.md 9.8).

The design (section 4) names the checks: two parameter files whose keys and values do not
overlap, an AST test that the predictor imports nothing from ``waggle.sim``, and a type test
that the predictor input has no field for fault state. The import-linter contract
``predictor-no-sim`` covers indirect chains.
"""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SIM_FILE = ROOT / "data" / "sim" / "degradation.json"
PREDICTOR_FILE = ROOT / "data" / "maintenance" / "predictor.json"
PREDICTOR_DIR = ROOT / "src" / "waggle" / "maintenance" / "predictor"
SIM_DIR = ROOT / "src" / "waggle" / "sim"


def _flatten(tree: dict[str, object], prefix: str = "") -> dict[str, float]:
    flat: dict[str, float] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        elif isinstance(value, int | float):
            flat[f"{prefix}{key}"] = float(value)
    return flat


def _leaves(flat: dict[str, float]) -> set[str]:
    return {key.rsplit(".", 1)[-1] for key in flat}


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(("." * node.level) + (node.module or ""))
    return names


def test_parameter_files_exist_and_are_not_empty() -> None:
    assert _flatten(json.loads(SIM_FILE.read_text(encoding="utf-8")))
    assert _flatten(json.loads(PREDICTOR_FILE.read_text(encoding="utf-8")))


def test_parameter_key_sets_do_not_overlap() -> None:
    sim = _flatten(json.loads(SIM_FILE.read_text(encoding="utf-8")))
    pred = _flatten(json.loads(PREDICTOR_FILE.read_text(encoding="utf-8")))
    assert _leaves(sim) & _leaves(pred) == set()
    assert set(sim) & set(pred) == set()


def test_parameter_values_do_not_overlap() -> None:
    sim = set(_flatten(json.loads(SIM_FILE.read_text(encoding="utf-8"))).values())
    pred = set(_flatten(json.loads(PREDICTOR_FILE.read_text(encoding="utf-8"))).values())
    assert sim & pred == set()


def test_predictor_modules_import_nothing_from_the_simulator() -> None:
    modules = sorted(PREDICTOR_DIR.glob("*.py"))
    assert modules, "the predictor package must exist"
    for path in modules:
        offending = [n for n in _imports(path) if n.startswith("waggle.sim") or n == "waggle"]
        assert offending == [], f"{path.name} imports {offending}"


def test_predictor_modules_use_only_the_standard_library_numpy_and_themselves() -> None:
    allowed_roots = {"numpy", "math", "json", "dataclasses", "pathlib", "collections", "typing"}
    allowed_roots |= {"__future__", "waggle"}
    for path in sorted(PREDICTOR_DIR.glob("*.py")):
        for name in _imports(path):
            if name.startswith("."):
                continue
            root = name.split(".")[0]
            assert root in allowed_roots, f"{path.name} imports {name}"
            if root == "waggle":
                assert name.startswith("waggle.maintenance.predictor"), f"{path.name}: {name}"


def test_simulator_modules_import_nothing_from_maintenance() -> None:
    for path in sorted(SIM_DIR.glob("*.py")):
        offending = [n for n in _imports(path) if n.startswith("waggle.maintenance")]
        assert offending == [], f"{path.name} imports {offending}"
