"""E4 configurations (COURT_DESIGN sections 3 and 8, decision 1).

Each configuration is a separate labeled run on identical cases. The baseline "no court" has no
reviewer, so only the code checks decide and the contribution of the court is an ablation
(AGENTS.md 9.3). Families are declared labels used to split the error correlation into same
family and cross family pairs. The role-to-route mapping stays in ``routes.toml``: the cross
family variant needs a ``court_3`` route to a non-Muse provider, which is a configuration change
for the maintainer. Role checklist variants are not defined here.
"""

from dataclasses import dataclass
from typing import Final, Literal

from waggle.llm.court_adapter import COURT_ROLES

PairKind = Literal["same_family", "cross_family"]


@dataclass(frozen=True)
class Configuration:
    """A named reviewer composition. ``families`` is parallel to ``roles``."""

    name: str
    label: str
    roles: tuple[str, ...]
    families: tuple[str, ...]
    court: bool

    def __post_init__(self) -> None:
        if len(self.roles) != len(self.families) or len(set(self.roles)) != len(self.roles):
            raise ValueError(f"{self.name}: roles must be distinct and match the families")
        if self.court != bool(self.roles):
            raise ValueError(f"{self.name}: a court needs reviewers, a non-court has none")
        if not set(self.roles) <= set(COURT_ROLES):
            raise ValueError(f"{self.name}: roles must be court roles")


BASELINE: Final = Configuration(
    "baseline_no_court", "No court: code checks only", (), (), court=False
)
CONFIGURATIONS: Final[dict[str, Configuration]] = {
    c.name: c
    for c in (
        Configuration("A_single", "A: single reviewer", ("court_1",), ("muse",), True),
        Configuration("B_two", "B: two reviewers", COURT_ROLES[:2], ("muse", "muse"), True),
        Configuration("C_three", "C: three reviewers", COURT_ROLES, ("muse",) * 3, True),
        Configuration(
            "D_cross_family",
            "D: two Muse plus one non-Muse reviewer",
            COURT_ROLES,
            ("muse", "muse", "non_muse"),
            True,
        ),
        BASELINE,
    )
}


def get_configuration(name: str) -> Configuration:
    """Return the configuration called ``name`` or raise KeyError."""
    return CONFIGURATIONS[name]


def pair_kind(config: Configuration, role_a: str, role_b: str) -> PairKind:
    """Whether two reviewers of ``config`` are from the same declared family."""
    for role in (role_a, role_b):
        if role not in config.roles:
            raise ValueError(f"{role} is not in configuration {config.name}")
    family = dict(zip(config.roles, config.families, strict=True))
    return "same_family" if family[role_a] == family[role_b] else "cross_family"
