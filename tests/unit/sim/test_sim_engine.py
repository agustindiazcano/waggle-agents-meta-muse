"""Tick loop, seeded streams, canonical hash, snapshot and fork."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from waggle.sim import engine, state, streams

Arrays = dict[str, NDArray[np.float64]]


def walk(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
    """Toy system: every entity takes a random step from its own stream."""
    pos = sim.arrays["pos"]
    for i in range(pos.shape[0]):
        pos[i] += rngs[f"humans/{i}"].normal(0.0, 0.1, size=2)


def make(seed: int, entities: int = 3) -> engine.Engine:
    arrays: Arrays = {"pos": np.zeros((entities, 2))}
    return engine.Engine(seed, arrays, [walk], {"humans": entities})


def test_same_seed_gives_the_same_hash_at_every_tick() -> None:
    a, b = make(11), make(11)
    for _ in range(50):
        a.step()
        b.step()
        assert a.state_hash() == b.state_hash()


def test_different_seeds_differ() -> None:
    a, b = make(1), make(2)
    a.run(20)
    b.run(20)
    assert a.state_hash() != b.state_hash()


def test_the_tick_counter_advances_and_is_part_of_the_hash() -> None:
    a = make(5)
    h0 = a.state_hash()
    a.step()
    assert a.state.tick == 1
    assert a.state_hash() != h0


def test_hash_is_a_stable_hex_digest_of_fixed_length() -> None:
    digest = make(3).state_hash()
    assert len(digest) == 64 and int(digest, 16) >= 0


def test_adding_an_entity_does_not_change_the_streams_of_the_others() -> None:
    three = streams.make_streams(7, "humans", 3)
    four = streams.make_streams(7, "humans", 4)
    for a, b in zip(three, four[:3], strict=True):
        assert a.random(5).tolist() == b.random(5).tolist()


def test_subsystems_have_independent_streams() -> None:
    humans = streams.make_streams(7, "humans", 1)[0].random(5).tolist()
    lidar = streams.make_streams(7, "lidar", 1)[0].random(5).tolist()
    assert humans != lidar


def test_adding_an_entity_does_not_change_the_trajectories_of_the_others() -> None:
    small, large = make(9, 3), make(9, 4)
    small.run(30)
    large.run(30)
    assert small.state.arrays["pos"].tolist() == large.state.arrays["pos"][:3].tolist()


def test_unknown_subsystem_is_rejected() -> None:
    with pytest.raises(ValueError, match="subsystem"):
        streams.make_streams(1, "weather", 1)


def test_negative_seed_or_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        streams.make_streams(-1, "humans", 1)
    with pytest.raises(ValueError):
        streams.make_streams(1, "humans", -1)


def test_hash_ignores_negative_zero_and_rounds_floats() -> None:
    a = state.canonical_hash(0, {"x": np.array([0.0, 1.0])}, {})
    b = state.canonical_hash(0, {"x": np.array([-0.0, 1.0 + 1e-12])}, {})
    assert a == b


def test_hash_changes_when_a_value_changes_beyond_the_rounding() -> None:
    a = state.canonical_hash(0, {"x": np.array([1.0])}, {})
    b = state.canonical_hash(0, {"x": np.array([1.0 + 1e-6])}, {})
    assert a != b


def test_hash_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        state.canonical_hash(0, {"x": np.array([np.nan])}, {})


def test_hash_does_not_depend_on_array_insertion_order() -> None:
    a = state.canonical_hash(0, {"a": np.array([1.0]), "b": np.array([2.0])}, {})
    b = state.canonical_hash(0, {"b": np.array([2.0]), "a": np.array([1.0])}, {})
    assert a == b


def test_snapshot_fork_matches_the_original_run() -> None:
    original = make(21)
    original.run(10)
    fork = original.fork()
    original.run(25)
    fork.run(25)
    assert fork.state.tick == original.state.tick == 35
    assert fork.state_hash() == original.state_hash()


def test_running_a_fork_never_mutates_the_original() -> None:
    original = make(4)
    original.run(7)
    before = original.state_hash()
    fork = original.fork()
    fork.run(40)
    assert original.state_hash() == before
    assert original.state.tick == 7


def test_fork_copies_arrays_and_rng_states_so_they_are_isolated() -> None:
    original = make(8)
    original.run(3)
    snap = original.snapshot()
    snap_pos = snap.arrays["pos"].copy()
    original.run(5)
    assert snap.arrays["pos"].tolist() == snap_pos.tolist()
    assert snap.arrays["pos"] is not original.state.arrays["pos"]
    key = "humans/0"
    state_before = snap.rng_states[key]["state"]["state"]
    original.run(5)
    assert snap.rng_states[key]["state"]["state"] == state_before


def test_snapshot_arrays_are_contiguous() -> None:
    original = make(8)
    assert original.snapshot().arrays["pos"].flags["C_CONTIGUOUS"]


def test_from_snapshot_restores_the_same_hash() -> None:
    original = make(13)
    original.run(12)
    restored = engine.Engine.from_snapshot(original.snapshot(), [walk])
    assert restored.state_hash() == original.state_hash()


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(0, 2**31), before=st.integers(0, 30), after=st.integers(0, 30))
def test_fork_at_t_then_n_ticks_equals_the_original_at_t_plus_n(
    seed: int, before: int, after: int
) -> None:
    original = make(seed)
    original.run(before)
    fork = original.fork()
    fork.run(after)
    original.run(after)
    assert fork.state_hash() == original.state_hash()


def test_a_system_failure_does_not_advance_the_tick() -> None:
    def boom(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        raise RuntimeError("system failed")

    sim = engine.Engine(1, {"pos": np.zeros((1, 2))}, [boom], {"humans": 1})
    with pytest.raises(RuntimeError):
        sim.step()
    assert sim.state.tick == 0
