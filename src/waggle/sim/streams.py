"""Seeded random streams: independent per subsystem and per entity (ADR-021).

A stream is built only from a child of ``numpy.random.SeedSequence``. The children of one
subsystem come from ``spawn``, whose i-th child does not depend on how many are spawned, so
adding an entity at the end never changes the streams of the others.
"""

import numpy as np

SUBSYSTEMS = ("robots", "humans", "lidar", "beacons", "scenario")
"""Fixed order: a subsystem's position is part of its spawn key, so never reorder this."""


def make_streams(root_seed: int, subsystem: str, count: int) -> list[np.random.Generator]:
    """``count`` independent generators for one subsystem of a run with ``root_seed``."""
    if subsystem not in SUBSYSTEMS:
        raise ValueError(f"unknown subsystem {subsystem!r}, expected one of {SUBSYSTEMS}")
    if root_seed < 0 or count < 0:
        raise ValueError("root_seed and count must not be negative")
    parent = np.random.SeedSequence(root_seed, spawn_key=(SUBSYSTEMS.index(subsystem),))
    return [np.random.default_rng(child) for child in parent.spawn(count)]
