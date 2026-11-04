"""E9 planted defects: registry, source patching on a copy, and the kill runner."""

import json
from pathlib import Path

import pytest

from waggle.experiments.e9_defects import DEFECTS, PlantedDefect, apply_defect, defect_by_id
from waggle.experiments.e9_run import DefectOutcome, run_campaign, write_result

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_IDS = {"margin_lowered", "cap_raises_speed", "stale_scan_accepted", "fencing_inverted"}


def _toy(tmp_path: Path) -> Path:
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    return tmp_path


TOY = PlantedDefect(
    id="toy",
    summary="toy defect",
    source="mod.py",
    old="VALUE = 1",
    new="VALUE = 2",
    detectors=("tests/test_toy.py::test_value",),
)


def test_the_registry_covers_the_four_designed_defects() -> None:
    assert {d.id for d in DEFECTS} == EXPECTED_IDS
    for defect in DEFECTS:
        assert defect.detectors, defect.id
        assert defect.old != defect.new
        source = (ROOT / defect.source).read_text(encoding="utf-8")
        assert source.count(defect.old) == 1, defect.id


def test_every_detector_node_exists_in_its_test_file() -> None:
    for defect in DEFECTS:
        for node in defect.detectors:
            path, _, name = node.partition("::")
            text = (ROOT / path).read_text(encoding="utf-8")
            assert f"def {name}(" in text, node


def test_apply_defect_replaces_exactly_once_and_refuses_a_missing_anchor() -> None:
    assert apply_defect("VALUE = 1\n", TOY) == "VALUE = 2\n"
    with pytest.raises(ValueError, match="toy"):
        apply_defect("VALUE = 9\n", TOY)
    with pytest.raises(ValueError, match="toy"):
        apply_defect("VALUE = 1\nVALUE = 1\n", TOY)


def test_defect_by_id_refuses_an_unknown_id() -> None:
    assert defect_by_id("margin_lowered").id == "margin_lowered"
    with pytest.raises(ValueError, match="unknown planted defect"):
        defect_by_id("nope")


def test_a_defect_is_killed_when_its_detector_fails_and_survives_when_it_passes(
    tmp_path: Path,
) -> None:
    _toy(tmp_path)
    outcomes = run_campaign(
        [TOY], root=tmp_path, run_detector=lambda _d, _r: 1, run_baseline=lambda _d, _r: 0
    )
    assert outcomes == (DefectOutcome("toy", "killed", "tests/test_toy.py::test_value"),)
    outcomes = run_campaign(
        [TOY], root=tmp_path, run_detector=lambda _d, _r: 0, run_baseline=lambda _d, _r: 0
    )
    assert outcomes[0].status == "survived"


def test_a_broken_detector_is_reported_not_counted_as_a_kill(tmp_path: Path) -> None:
    _toy(tmp_path)
    outcomes = run_campaign(
        [TOY], root=tmp_path, run_detector=lambda _d, _r: 1, run_baseline=lambda _d, _r: 1
    )
    assert outcomes[0].status == "detector_broken"


def test_the_campaign_never_mutates_the_real_tree(tmp_path: Path) -> None:
    _toy(tmp_path)
    run_campaign([TOY], root=tmp_path, run_detector=lambda _d, _r: 1, run_baseline=lambda _d, _r: 0)
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_write_result_records_counts_and_survivors(tmp_path: Path) -> None:
    outcomes = (
        DefectOutcome("a", "killed", "t.py::test_a"),
        DefectOutcome("b", "survived", "t.py::test_b"),
    )
    path = write_result(outcomes, tmp_path / "e9.json", commit="abc", date="2026-11-04")
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["commit"] == "abc"
    assert body["seed_set"] == "dev"
    assert body["planted"] == 2
    assert body["killed"] == 1
    assert body["survived"] == ["b"]
    assert body["outcomes"][0]["first_detector"] == "t.py::test_a"


def test_the_stale_scan_defect_is_killed_by_its_real_detector(tmp_path: Path) -> None:
    defect = defect_by_id("stale_scan_accepted")
    outcomes = run_campaign([defect], root=ROOT, work_root=tmp_path)
    assert outcomes[0].status == "killed"
