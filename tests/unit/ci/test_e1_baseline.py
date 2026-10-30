"""No-control baseline document: required fields, dev-only, unavoidable cases separated."""

import json
from pathlib import Path

import e1_baseline
import pytest

from waggle.sim import scenarios

REQUIRED = {
    "experiment",
    "configuration",
    "seed_set",
    "commit",
    "date",
    "numpy_version",
    "platform",
    "dt",
    "definitions",
    "counts",
    "counts_excluding_unavoidable",
    "unavoidable_cases",
    "tasks_per_simulated_hour",
    "failing_seeds",
    "runs",
    "model_ids",
    "prompt_versions",
    "notes",
}


def short_document() -> dict[str, object]:
    pairs = [("S03", 7), ("S13", 8)]
    return e1_baseline.run_baseline(pairs, ticks=80)


def test_the_document_has_every_required_field_and_is_a_dev_result() -> None:
    doc = short_document()
    assert set(doc) >= REQUIRED
    assert doc["seed_set"] == "dev" and doc["experiment"] == "e1"
    assert doc["configuration"] == "no_control"
    definitions = doc["definitions"]
    assert isinstance(definitions, dict)
    assert set(definitions) == {"collision", "separation_violation", "near_miss"}


def test_counts_runs_and_tasks_are_consistent() -> None:
    doc = short_document()
    runs = doc["runs"]
    assert isinstance(runs, list) and len(runs) == 2
    counts = doc["counts"]
    assert isinstance(counts, dict)
    for key in ("human_collisions", "robot_collisions", "separation_violations", "near_misses"):
        assert counts[key] == sum(r["counts"][key] for r in runs)
    rate = doc["tasks_per_simulated_hour"]
    assert isinstance(rate, float) and rate >= 0


def test_unavoidable_cases_are_listed_separately_and_never_hidden() -> None:
    doc = e1_baseline.assemble(
        [
            {
                "scenario": "S99",
                "seed": 1,
                "ticks": 10,
                "unavoidable_at_spawn": True,
                "tasks_completed": 0,
                "counts": {
                    "human_collisions": 2,
                    "robot_collisions": 0,
                    "separation_violations": 2,
                    "near_misses": 0,
                },
            },
            {
                "scenario": "S98",
                "seed": 2,
                "ticks": 10,
                "unavoidable_at_spawn": False,
                "tasks_completed": 1,
                "counts": {
                    "human_collisions": 1,
                    "robot_collisions": 0,
                    "separation_violations": 1,
                    "near_misses": 0,
                },
            },
        ]
    )
    assert doc["counts"]["human_collisions"] == 3
    assert doc["counts_excluding_unavoidable"]["human_collisions"] == 1
    assert [c["scenario"] for c in doc["unavoidable_cases"]] == ["S99"]
    assert doc["failing_seeds"] == [{"scenario": "S98", "seed": 2}, {"scenario": "S99", "seed": 1}]


def test_main_writes_under_dev_and_uses_only_development_seeds(tmp_path: Path) -> None:
    code = e1_baseline.main(
        ["--results-dir", str(tmp_path), "--scenarios", "S03", "S13", "--ticks", "40"]
    )
    assert code == 0
    files = list((tmp_path / "e1" / "dev").glob("*.json"))
    assert len(files) == 1
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    dev = json.loads(Path("data/seeds.json").read_text(encoding="utf-8"))["dev"]
    used = {(r["scenario"], r["seed"]) for r in doc["runs"]}
    assert used == {(s, seed) for s in ("S03", "S13") for seed in dev[s]}
    assert not (tmp_path / "e1" / "heldout").exists()


def test_there_is_no_way_to_ask_for_held_out_seeds(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        e1_baseline.main(["--results-dir", str(tmp_path), "--seed-set", "heldout"])


def test_the_baseline_covers_exactly_s01_to_s18_by_default() -> None:
    assert e1_baseline.default_scenarios() == scenarios.SCENARIO_IDS
