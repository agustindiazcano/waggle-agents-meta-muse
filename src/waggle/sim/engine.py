"""Fixed-step tick loop with seeded streams, snapshot and fork (ADR-021, ADR-025).

Ground truth is owned here. Systems are plain functions that change the state arrays and draw
from named streams. No wall clock is read and nothing outside the seed affects a run.
"""

from collections.abc import Callable, Mapping, Sequence

import numpy as np

from waggle.sim import state, streams

System = Callable[[state.SimState, dict[str, np.random.Generator]], None]


def _blank_generator() -> np.random.Generator:
    """A generator whose state is overwritten at once by a restore."""
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(0)))


class Engine:
    """One simulation run."""

    def __init__(
        self,
        seed: int,
        arrays: Mapping[str, state.Array],
        systems: Sequence[System],
        stream_counts: Mapping[str, int],
    ) -> None:
        rngs: dict[str, np.random.Generator] = {}
        for subsystem in sorted(stream_counts):
            made = streams.make_streams(seed, subsystem, stream_counts[subsystem])
            for index, generator in enumerate(made):
                rngs[f"{subsystem}/{index}"] = generator
        self._start(
            state.SimState(0, {name: state.copy_array(a) for name, a in arrays.items()}),
            rngs,
            systems,
        )

    def _start(
        self,
        sim: state.SimState,
        rngs: dict[str, np.random.Generator],
        systems: Sequence[System],
    ) -> None:
        self.state = sim
        self.rngs = rngs
        self.systems = list(systems)

    def step(self) -> None:
        """Advance one tick. If a system raises, the tick does not advance."""
        for system in self.systems:
            system(self.state, self.rngs)
        self.state.tick += 1

    def run(self, ticks: int) -> None:
        """Advance ``ticks`` ticks."""
        for _ in range(ticks):
            self.step()

    def _rng_states(self) -> dict[str, state.RngState]:
        return {name: state.copy_plain(gen.bit_generator.state) for name, gen in self.rngs.items()}

    def state_hash(self) -> str:
        """Canonical hash of the tick, the arrays and every stream state."""
        return state.canonical_hash(self.state.tick, self.state.arrays, self._rng_states())

    def snapshot(self) -> state.Snapshot:
        """An isolated copy of the state and of all stream states."""
        return state.Snapshot(
            self.state.tick,
            {name: state.copy_array(a) for name, a in self.state.arrays.items()},
            self._rng_states(),
        )

    @classmethod
    def from_snapshot(cls, snap: state.Snapshot, systems: Sequence[System]) -> "Engine":
        """Rebuild an engine from a snapshot. The snapshot is copied, never shared."""
        rngs: dict[str, np.random.Generator] = {}
        for name, rng_state in snap.rng_states.items():
            generator = _blank_generator()
            generator.bit_generator.state = state.copy_plain(rng_state)
            rngs[name] = generator
        engine = cls.__new__(cls)
        engine._start(
            state.SimState(snap.tick, {n: state.copy_array(a) for n, a in snap.arrays.items()}),
            rngs,
            systems,
        )
        return engine

    def fork(self) -> "Engine":
        """A copy that continues from this tick and never affects this engine."""
        return Engine.from_snapshot(self.snapshot(), self.systems)
