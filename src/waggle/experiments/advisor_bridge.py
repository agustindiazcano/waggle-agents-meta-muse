"""Harness bridge from recorded advisor cautions to fast-layer limits (ADR-064).

``waggle.control`` must not import ``waggle.governance``, so the two meet here, in the harness.
The bridge only reads the caution log and builds ``Limit(speed_cap, Reason.ADVISOR)`` values. A
limit is an upper bound on speed, so what it feeds into the fast layer can only reduce motion.
The log holds recorded events, so a replay of a stored log is exact. Nothing here reads a clock.
"""

from collections.abc import Sequence

from waggle.control.types import Limit, Reason
from waggle.governance.caution_limits import SpeedLimit, speed_limits_at
from waggle.governance.caution_log import CautionLog


def fast_layer_limits(limits: Sequence[SpeedLimit]) -> tuple[Limit, ...]:
    """Plain speed limits as advisor limits for ``control_step``, in the same order."""
    return tuple(Limit(item.speed_cap, Reason.ADVISOR) for item in limits)


class AdvisorBridge:
    """Per tick advisor limits for the robots of a run, read from a caution log.

    ``robot_ids`` maps the fleet index to the robot id used in the log. An index outside the list
    has no limits. The call signature matches the ``advisor`` hook of ``ControlRig``.
    """

    def __init__(self, log: CautionLog, robot_ids: Sequence[str]) -> None:
        self._log = log
        self._robot_ids = tuple(robot_ids)

    def __call__(self, robot_index: int, tick: int, class_max: float) -> tuple[Limit, ...]:
        """Limits in force for the robot at ``tick``. A bad ``class_max`` fails closed to zero."""
        if not 0 <= robot_index < len(self._robot_ids):
            return ()
        active = speed_limits_at(self._log, self._robot_ids[robot_index], tick, class_max=class_max)
        return fast_layer_limits(active)
