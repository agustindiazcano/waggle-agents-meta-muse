"""Simulation state: contiguous numpy arrays, a tick counter and a canonical hash (ADR-025).

The state type is the same for ground truth and for belief states. What populates it differs.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

HASH_DECIMALS = 9
"""Floats are rounded to this many decimals before hashing. Roughly 1 nanometer in meters."""

Array = NDArray[np.generic]
RngState = dict[str, Any]  # numpy exposes a bit generator state as a plain nested dict


@dataclass
class SimState:
    """Mutable state of one run: the tick and named arrays (poses, velocities, zone tokens)."""

    tick: int
    arrays: dict[str, Array]


@dataclass(frozen=True)
class Snapshot:
    """An isolated copy of a state and of every random stream, for fork and replay."""

    tick: int
    arrays: dict[str, Array]
    rng_states: dict[str, RngState]


def copy_plain(value: Any) -> Any:  # nested dict/int/str tree of an RNG state, no deepcopy
    """Copy a tree of dicts, ints and strings."""
    if isinstance(value, dict):
        return {key: copy_plain(item) for key, item in value.items()}
    return value


def copy_array(array: Array) -> Array:
    """A C-contiguous copy of ``array``."""
    return array.copy(order="C")


def _canonical_values(array: Array, decimals: int) -> list[Any]:
    if np.issubdtype(array.dtype, np.floating):
        if not np.all(np.isfinite(array)):
            raise ValueError("state arrays must hold only finite values to be hashed")
        floats = array.astype(np.float64)
        return list((np.round(floats, decimals) + 0.0).ravel().tolist())  # + 0.0: -0.0 to 0.0
    return list(array.ravel().tolist())


def canonical_hash(
    tick: int,
    arrays: Mapping[str, Array],
    rng_states: Mapping[str, RngState],
    decimals: int = HASH_DECIMALS,
) -> str:
    """SHA-256 of a canonical serialization: sorted keys, floats rounded to ``decimals``.

    The digest depends only on values, never on dict insertion order. It is not a golden
    value: tests compare two runs in the same process.
    """
    payload = {
        "tick": tick,
        "arrays": {
            name: {
                "dtype": str(array.dtype),
                "shape": list(array.shape),
                "data": _canonical_values(array, decimals),
            }
            for name, array in arrays.items()
        },
        "rng": dict(rng_states),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
