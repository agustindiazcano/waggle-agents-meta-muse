"""Pairwise error correlation against hand-computed 2 by 2 tables (COURT_DESIGN section 8)."""

import math

from waggle.experiments.e4_configs import CONFIGURATIONS
from waggle.experiments.e4_correlation import MIN_CELL, error_correlation, phi
from waggle.experiments.e4_metrics import RunRecord, VoteRecord


def _vote(role: str, verdict: str | None) -> VoteRecord:
    return VoteRecord(role, verdict, None if verdict else "timeout", f"m-{role}", None)


def _run(i: int, label: str, verdicts: dict[str, str | None]) -> RunRecord:
    votes = tuple(_vote(role, verdict) for role, verdict in verdicts.items())
    return RunRecord(f"c{i}", label, 0, "escalate", "x", votes)


def _pair_runs(n11: int, n10: int, n01: int, n00: int) -> list[RunRecord]:
    """Risky cases: approve is an error, reject is correct."""
    err, ok = "approve", "reject"
    plan = [(err, err)] * n11 + [(err, ok)] * n10 + [(ok, err)] * n01 + [(ok, ok)] * n00
    return [_run(i, "risky", {"court_1": a, "court_2": b}) for i, (a, b) in enumerate(plan)]


def test_phi_matches_the_hand_computed_table() -> None:
    # (2*2 - 1*1) / sqrt(3 * 3 * 3 * 3) = 3 / 9
    assert math.isclose(phi(2, 1, 1, 2) or 0.0, 1 / 3)
    assert phi(3, 0, 0, 3) == 1.0
    assert phi(0, 3, 3, 0) == -1.0


def test_phi_is_undefined_when_a_margin_is_zero() -> None:
    assert phi(0, 0, 0, 5) is None
    assert phi(5, 0, 0, 0) is None
    assert phi(0, 0, 0, 0) is None


def test_the_report_gives_the_table_and_phi_for_a_same_family_pair() -> None:
    out = error_correlation(_pair_runs(2, 1, 1, 2), CONFIGURATIONS["B_two"])
    assert out["cross_family"] == []
    (pair,) = out["same_family"]
    assert pair["roles"] == ["court_1", "court_2"]
    assert pair["table"] == {
        "both_wrong": 2,
        "only_first_wrong": 1,
        "only_second_wrong": 1,
        "neither": 2,
    }
    assert pair["n"] == 6
    assert math.isclose(pair["phi"], 1 / 3)


def test_a_cell_below_the_minimum_is_flagged_as_too_small() -> None:
    out = error_correlation(_pair_runs(2, 1, 1, 2), CONFIGURATIONS["B_two"])
    pair = out["same_family"][0]
    assert pair["too_small"] is True
    assert pair["small_cells"] == ["both_wrong", "only_first_wrong", "only_second_wrong", "neither"]
    big = error_correlation(
        _pair_runs(MIN_CELL, MIN_CELL, MIN_CELL, MIN_CELL), CONFIGURATIONS["B_two"]
    )["same_family"][0]
    assert big["too_small"] is False and big["small_cells"] == []


def test_a_zero_margin_gives_no_phi_and_is_flagged() -> None:
    out = error_correlation(_pair_runs(0, 0, 0, 8), CONFIGURATIONS["B_two"])
    pair = out["same_family"][0]
    assert pair["phi"] is None and pair["too_small"] is True


def test_pairs_are_split_by_declared_family() -> None:
    runs = []
    for i, (a, b, c) in enumerate(
        [("approve", "approve", "reject"), ("reject", "reject", "reject")]
    ):
        runs.append(_run(i, "risky", {"court_1": a, "court_2": b, "court_3": c}))
    out = error_correlation(runs, CONFIGURATIONS["D_cross_family"])
    assert [p["roles"] for p in out["same_family"]] == [["court_1", "court_2"]]
    assert [p["roles"] for p in out["cross_family"]] == [
        ["court_1", "court_3"],
        ["court_2", "court_3"],
    ]
    same = CONFIGURATIONS["C_three"]
    assert error_correlation(runs, same)["cross_family"] == []


def test_missing_votes_and_ambiguous_cases_are_left_out_of_the_table() -> None:
    runs = [
        _run(0, "risky", {"court_1": "approve", "court_2": None}),
        _run(1, "ambiguous", {"court_1": "approve", "court_2": "approve"}),
        _run(2, "benign", {"court_1": "reject", "court_2": "reject"}),
    ]
    pair = error_correlation(runs, CONFIGURATIONS["B_two"])["same_family"][0]
    assert pair["n"] == 1
    assert pair["table"]["both_wrong"] == 1


def test_a_single_reviewer_or_the_baseline_has_no_pairs() -> None:
    for name in ("A_single", "baseline_no_court"):
        out = error_correlation([], CONFIGURATIONS[name])
        assert out["same_family"] == [] and out["cross_family"] == []


def test_the_report_labels_repeats_as_not_independent() -> None:
    out = error_correlation(_pair_runs(1, 1, 1, 1), CONFIGURATIONS["B_two"])
    assert "not independent" in out["note"]
