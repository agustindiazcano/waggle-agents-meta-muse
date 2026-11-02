"""Predictor input and output types.

The input is a machine id, a tick and four numbers. It has no field for fault state, onset or
wear: the predictor must infer trouble from telemetry alone (design section 4, AGENTS.md 9.8).
"""

import math
from dataclasses import dataclass


class PredictorError(ValueError):
    """Invalid predictor input or parameters. Raised instead of returning a quiet default."""


@dataclass(frozen=True)
class Reading:
    """One telemetry reading. All four values must be finite."""

    machine_id: int
    tick: int
    temperature: float
    vibration: float
    current: float
    load: float

    def __post_init__(self) -> None:
        """Fail closed on a value that cannot be scored."""
        for name in ("temperature", "vibration", "current", "load"):
            if not math.isfinite(getattr(self, name)):
                raise PredictorError(f"{name} must be finite")
        if self.tick < 0:
            raise PredictorError("tick must not be negative")


@dataclass(frozen=True)
class Assessment:
    """The predictor's view of one machine after one reading.

    ``flag`` is the CUSUM state (P1). ``time_to_limit_ticks`` is the one-node estimate (P2),
    None when the fitted model does not reach the limit. ``scorable`` is False for a reading
    after a gap in ticks: nothing was updated and the flag is not trusted.
    """

    machine_id: int
    tick: int
    warm: bool
    scorable: bool
    flag: bool
    flagged: tuple[str, ...]
    time_to_limit_ticks: int | None
