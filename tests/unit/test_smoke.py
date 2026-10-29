import importlib
import tomllib
from pathlib import Path

import pytest

import waggle

ROOT = Path(__file__).resolve().parents[2]

SUBPACKAGES = [
    "sim",
    "control",
    "coordination",
    "mcp_server",
    "governance",
    "maintenance",
    "multimodal",
    "llm",
    "api",
    "db",
]

TASK_TARGETS = [
    "lint",
    "type",
    "test",
    "ci",
    "experiments-dev",
    "experiments-test",
    "report",
]


def test_package_has_version() -> None:
    assert isinstance(waggle.__version__, str)
    assert waggle.__version__


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_importable(name: str) -> None:
    assert importlib.import_module(f"waggle.{name}")


def test_all_task_targets_declared_as_scripts() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    for target in TASK_TARGETS:
        assert target in scripts, f"missing script for target {target!r}"


def test_env_example_has_names_only() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assignments = [x for x in lines if x and not x.startswith("#")]
    assert assignments
    for line in assignments:
        name, _, value = line.partition("=")
        assert name.isupper(), line
        assert value == "", f"{name} must not carry a value in .env.example"
