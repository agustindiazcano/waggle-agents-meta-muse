"""E4 configurations: separate labeled configurations on identical cases (COURT_DESIGN 3, 8)."""

import pytest

from waggle.experiments.e4_configs import (
    BASELINE,
    CONFIGURATIONS,
    Configuration,
    get_configuration,
    pair_kind,
)
from waggle.llm.court_adapter import COURT_ROLES


def test_the_design_configurations_exist_as_separate_labels() -> None:
    assert set(CONFIGURATIONS) == {
        "A_single",
        "B_two",
        "C_three",
        "D_cross_family",
        "baseline_no_court",
    }
    assert [len(CONFIGURATIONS[n].roles) for n in ("A_single", "B_two", "C_three")] == [1, 2, 3]
    assert CONFIGURATIONS["D_cross_family"].roles == COURT_ROLES


def test_the_baseline_has_no_reviewer_and_is_not_a_court() -> None:
    assert BASELINE.roles == ()
    assert BASELINE.court is False
    assert all(c.court for n, c in CONFIGURATIONS.items() if n != BASELINE.name)


def test_roles_are_distinct_court_roles_and_families_match_roles() -> None:
    for config in CONFIGURATIONS.values():
        assert len(set(config.roles)) == len(config.roles)
        assert set(config.roles) <= set(COURT_ROLES)
        assert len(config.families) == len(config.roles)


def test_only_the_cross_family_variant_mixes_families() -> None:
    mixed = {n for n, c in CONFIGURATIONS.items() if len(set(c.families)) > 1}
    assert mixed == {"D_cross_family"}


def test_pair_kind_separates_same_family_from_cross_family() -> None:
    cross = CONFIGURATIONS["D_cross_family"]
    assert pair_kind(cross, "court_1", "court_2") == "same_family"
    assert pair_kind(cross, "court_1", "court_3") == "cross_family"
    assert pair_kind(CONFIGURATIONS["C_three"], "court_1", "court_3") == "same_family"


def test_pair_kind_refuses_a_role_outside_the_configuration() -> None:
    with pytest.raises(ValueError, match="court_3"):
        pair_kind(CONFIGURATIONS["B_two"], "court_1", "court_3")


def test_get_configuration_refuses_an_unknown_name() -> None:
    assert get_configuration("B_two").name == "B_two"
    with pytest.raises(KeyError):
        get_configuration("E_whatever")


def test_a_malformed_configuration_is_refused() -> None:
    with pytest.raises(ValueError):
        Configuration("x", "x", ("court_1",), ("muse", "muse"), True)
    with pytest.raises(ValueError):
        Configuration("x", "x", ("court_1", "court_1"), ("muse", "muse"), True)
    with pytest.raises(ValueError):
        Configuration("x", "x", (), (), True)
