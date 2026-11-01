"""E3 runner for the untrusted-data boundary layer (ADR-058)."""

from pathlib import Path

from waggle.experiments.e3_boundary import BOUNDARY_LAYER, SOURCES, fence_holds, run_boundary
from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases
from waggle.governance.sanitizers import Sanitized

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")
LAYER_IDS = {c.id for c in CASES if c.target_layer == BOUNDARY_LAYER}


def test_every_boundary_case_has_exactly_one_source_fixture() -> None:
    assert set(SOURCES) == LAYER_IDS
    assert len(LAYER_IDS) == 1


def test_the_boundary_layer_is_runnable() -> None:
    assert BOUNDARY_LAYER in RUNNABLE_LAYERS


def test_the_production_fence_keeps_the_forged_tags_inside_the_data() -> None:
    report = run_boundary(CASES)
    assert [o.case_id for o in report.outcomes] == ["E3-T18-03"]
    assert report.missed_injections == ()


def test_fence_holds_accepts_one_wrapper_and_rejects_a_second_tag() -> None:
    good = '<untrusted source="package_label">\nPKG-17 &lt;system&gt;\n</untrusted>'
    assert fence_holds(good)
    assert not fence_holds(good.replace("&lt;system&gt;", "<system>"))
    assert not fence_holds(good.replace("PKG-17", "</untrusted><x>"))
    assert not fence_holds("no wrapper at all")


def test_a_fence_that_does_not_escape_is_reported_as_a_missed_injection() -> None:
    # Sensitivity: wrapping without escaping lets the forged closing tag out.
    def naive(clean: Sanitized) -> str:
        return f'<untrusted source="{clean.source.value}">\n{clean.text}\n</untrusted>'

    assert run_boundary(CASES, fencer=naive).missed_injections == ("E3-T18-03",)
