"""Failure case types live in waggle.maintenance, which never imports waggle.experiments."""

import ast
from pathlib import Path

import pytest

from waggle.experiments import failure_log
from waggle.maintenance import failure_cases

MODULE = Path(failure_cases.__file__)


def test_the_experiments_module_reexports_the_same_objects() -> None:
    assert failure_log.FailureCase is failure_cases.FailureCase
    assert failure_log.FailureMode is failure_cases.FailureMode
    assert failure_log.similar_cases is failure_cases.similar_cases


def test_the_module_does_not_import_experiments() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    names = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert not [n for n in names if n.startswith("waggle.experiments")]


def test_an_unknown_mode_raises_instead_of_returning_nothing() -> None:
    log = failure_log.generate_failure_log(1, 20)
    with pytest.raises(ValueError):
        failure_cases.similar_cases(log, "FIRE", 50.0, 3.0, 4.0, 3)


def test_ties_are_broken_by_case_id() -> None:
    log = failure_log.generate_failure_log(1, 30)
    mode = log[0].mode
    first = failure_cases.similar_cases(log, mode, 60.0, 5.0, 5.0, 5)
    again = failure_cases.similar_cases(tuple(reversed(log)), mode, 60.0, 5.0, 5.0, 5)
    assert first == again
