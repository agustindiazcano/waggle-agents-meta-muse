"""E10 configurations (EXPERIMENTS.md E10).

The deterministic baseline has the crisis planner layer disabled: code proposes the
recovery plan and the same validator decides. The LLM configurations differ only in
the round bound: open loop gets one round, validator feedback gets up to three. A
court configuration is not defined here; no existing interface reviews a plan, so
adding one would invent a contract. That gap is reported, not hidden.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Configuration:
    """A named crisis configuration. ``uses_llm`` is False only for the baseline."""

    name: str
    label: str
    uses_llm: bool
    max_rounds: int

    def __post_init__(self) -> None:
        if not 1 <= self.max_rounds <= 3:
            raise ValueError(f"{self.name}: max_rounds must be between 1 and 3")
        if not self.uses_llm and self.max_rounds != 1:
            raise ValueError(f"{self.name}: the deterministic baseline runs one round")


CONFIGURATIONS: Final[dict[str, Configuration]] = {
    c.name: c
    for c in (
        Configuration("deterministic_baseline", "Deterministic recovery, planner off", False, 1),
        Configuration("llm_open_loop", "Planner open loop, no feedback", True, 1),
        Configuration("llm_validator_feedback", "Planner with validator feedback", True, 3),
    )
}


def get_configuration(name: str) -> Configuration:
    """Return the configuration called ``name`` or raise KeyError."""
    return CONFIGURATIONS[name]
