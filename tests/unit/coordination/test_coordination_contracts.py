"""Coordination stays deterministic and isolated from the LLM side."""

import tomllib
from pathlib import Path

from determinism_scan import scan_tree

ROOT = Path(__file__).resolve().parents[3]


def test_coordination_has_enforced_import_contract() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contract = next(
        c
        for c in config["tool"]["importlinter"]["contracts"]
        if c["id"] == "sim-control-no-llm-side"
    )
    assert "waggle.coordination" in contract["source_modules"]
    assert set(contract["forbidden_modules"]) == {
        "waggle.llm",
        "waggle.governance",
        "waggle.maintenance",
        "waggle.mcp_server",
    }


def test_coordination_has_no_clock_network_or_global_random() -> None:
    assert scan_tree(ROOT / "src" / "waggle", ("coordination",)) == []
