"""Map accepted cautions to a plain speed-limit list (ADVISORS_DESIGN 4 and 7).

The result is data for a caller to hand to the fast layer later. Nothing here imports
``waggle.control``. A limit is an upper bound on speed magnitude, so combining limits by a
minimum can only lower motion, never raise it and never change the sign of a command.
"""

import math
from dataclasses import dataclass
from typing import Final

from waggle.governance.caution_log import CautionLog

ADVISOR_SOURCE: Final = "advisor"


@dataclass(frozen=True)
class SpeedLimit:
    """An upper bound on speed magnitude in m/s from one accepted caution."""

    speed_cap: float
    source: str
    call_request_id: str


def speed_limits_at(
    log: CautionLog, robot_id: str, tick: int, *, class_max: float
) -> tuple[SpeedLimit, ...]:
    """Limits from the cautions of ``robot_id`` in force at ``tick``, in log order.

    A cap above ``class_max`` is lowered to it. A ``class_max`` that is not a finite
    non-negative number fails closed: every active caution then maps to a zero cap.
    """
    usable = math.isfinite(class_max) and class_max >= 0.0
    out: list[SpeedLimit] = []
    for event in log.active_at(robot_id, tick):
        cap = event.speed_cap
        bound = 0.0 if cap is None or not usable else min(cap, class_max)
        out.append(SpeedLimit(bound, ADVISOR_SOURCE, event.call_request_id))
    return tuple(out)


def apply_speed_limits(speed: float, limits: tuple[SpeedLimit, ...]) -> float:
    """Clip ``speed`` to the tightest limit. The sign is kept and the magnitude never grows.

    A non-finite ``speed`` returns 0.0.
    """
    if not math.isfinite(speed):
        return 0.0
    magnitude = abs(speed)
    for limit in limits:
        magnitude = min(magnitude, max(limit.speed_cap, 0.0))
    return math.copysign(magnitude, speed) if magnitude else 0.0
