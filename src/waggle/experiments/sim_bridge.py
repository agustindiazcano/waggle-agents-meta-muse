"""The trusted writer for simulator runs: publish the tick and occupancy (ADR-041).

The simulator owns ground truth, so this bridge reads it and writes the shared tick and one
occupancy record per zone. Only the live simulation publishes. A rollout fork must not: its
ticks would move the shared tick backwards and the writer rejects that. Occupancy comes from
the same conservative derivation the simulator admission adapter uses, so an unknown pose is
published as unknown, never as clear.
"""

from typing import Protocol

from waggle.coordination.corridors import ZoneObservation
from waggle.sim import state


class TrustedWriter(Protocol):
    """The write side of ``TrustedStateRepository``."""

    def advance_tick(self, tick: int) -> None:
        """Move the shared tick forward, or raise."""
        ...

    def record(self, zone_id: str, observed_tick: int, occupants: tuple[str, ...] | None) -> bool:
        """Store one occupancy record; False when a newer one is stored."""
        ...


class OccupancyView(Protocol):
    """Derives current zone occupancy from the simulator state."""

    def occupancy(self, sim: state.SimState) -> tuple[ZoneObservation, ...]:
        """One observation per zone at the simulator tick."""
        ...


class SimTrustedBridge:
    """Publishes the simulator tick and zone occupancy to a trusted writer."""

    def __init__(self, writer: TrustedWriter, view: OccupancyView) -> None:
        self._writer = writer
        self._view = view

    def publish(self, sim: state.SimState) -> int:
        """Write the tick, then every zone observation. Returns the number accepted.

        A regressing tick raises before any observation is written. A writer error propagates:
        a missing publication must read as stale downstream, never as clear.
        """
        self._writer.advance_tick(sim.tick)
        accepted = 0
        for observation in self._view.occupancy(sim):
            if self._writer.record(
                observation.resource_id, observation.observed_tick, observation.occupants
            ):
                accepted += 1
        return accepted
