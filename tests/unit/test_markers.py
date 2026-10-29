"""The heavy and llm markers are registered, deselectable, and excluded identically by CI."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from waggle import tasks

ROOT = Path(__file__).resolve().parents[2]

SAMPLE = """
import pytest

@pytest.mark.{marker}
def test_marked() -> None:
    pass

def test_plain() -> None:
    pass
"""


def _collect(tmp_path: Path, marker: str, expr: str | None) -> subprocess.CompletedProcess[str]:
    (tmp_path / "test_sample.py").write_text(SAMPLE.format(marker=marker), encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(ROOT / "pyproject.toml"),
        "--rootdir",
        str(tmp_path),
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        str(tmp_path / "test_sample.py"),
    ]
    if expr is not None:
        cmd += ["-m", expr]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)


@pytest.mark.parametrize("marker", ["heavy", "llm"])
def test_marker_is_registered(tmp_path: Path, marker: str) -> None:
    result = _collect(tmp_path, marker, None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_marked" in result.stdout


@pytest.mark.parametrize("marker", ["heavy", "llm"])
def test_marker_is_deselectable(tmp_path: Path, marker: str) -> None:
    result = _collect(tmp_path, marker, f"not {marker}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_plain" in result.stdout
    assert "test_marked" not in result.stdout


def test_unregistered_marker_is_rejected(tmp_path: Path) -> None:
    result = _collect(tmp_path, "not_a_registered_marker", None)
    assert result.returncode != 0


def test_ci_and_workflow_exclude_the_same_markers() -> None:
    assert tasks.MARKER_EXPR == "not heavy and not llm"
    assert tasks.TEST[0][-2:] == ["-m", tasks.MARKER_EXPR]
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    match = re.search(r'pytest .*-m "([^"]+)"', workflow)
    assert match is not None, "ci.yml pytest step has no marker expression"
    assert match.group(1) == tasks.MARKER_EXPR
