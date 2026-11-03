"""Belief builder: a snapshot of tracked entities and a declared prior become sampler inputs.

The input is plain data (a frozen dataclass or a mapping with fixed keys), so this module does not
import ``waggle.control``: the caller copies the fields of its tracks. The output holds the humans
the fleet already tracks (position and velocity), the declared prior for the ones it cannot see,
and a SHA-256 digest of the whole snapshot and prior. The digest replaces the constant that used
to seed the variants, so two different snapshots give different variant seeds.

A tracked entity with a missing, non-finite or mistyped value is rejected with ``BeliefError``.
It is never skipped: dropping a track would remove a human from every variant.
"""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from waggle.validation.belief import HumanPrior, HumanState

_KEYS: Final = ("entity_id", "x", "y", "vx", "vy", "sigma", "seen_tick")


class BeliefError(ValueError):
    """A tracked entity or snapshot has a value the belief cannot be built from."""


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BeliefError(f"{name} must be a number")
    if not math.isfinite(value):
        raise BeliefError(f"{name} must be finite")
    return float(value)


def _count(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BeliefError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class TrackedEntity:
    """One tracked human: world position and velocity, position sigma, tick last seen."""

    entity_id: int
    x: float
    y: float
    vx: float
    vy: float
    sigma: float
    seen_tick: int

    def __post_init__(self) -> None:
        """Refuse a value the sampler could not use."""
        _count("entity_id", self.entity_id)
        _count("seen_tick", self.seen_tick)
        for name in ("x", "y", "vx", "vy", "sigma"):
            _finite(name, getattr(self, name))
        if self.sigma < 0:
            raise BeliefError("sigma must not be negative")


@dataclass(frozen=True)
class TrackSnapshot:
    """Tracked entities at one scenario tick."""

    tick: int
    entities: tuple[TrackedEntity, ...]


@dataclass(frozen=True)
class Belief:
    """What the validator assumes at t = 0: known humans, the prior for hidden ones, a digest."""

    known_humans: tuple[HumanState, ...]
    prior: HumanPrior
    snapshot_digest: str


def entity_from_mapping(row: Mapping[str, object]) -> TrackedEntity:
    """Build an entity from a mapping with exactly the seven keys; anything else is rejected."""
    if set(row) != set(_KEYS):
        raise BeliefError("a tracked entity needs exactly the keys " + ", ".join(_KEYS))
    return TrackedEntity(
        entity_id=_count("entity_id", row["entity_id"]),
        x=_finite("x", row["x"]),
        y=_finite("y", row["y"]),
        vx=_finite("vx", row["vx"]),
        vy=_finite("vy", row["vy"]),
        sigma=_finite("sigma", row["sigma"]),
        seen_tick=_count("seen_tick", row["seen_tick"]),
    )


def _digest(snapshot: TrackSnapshot, prior: HumanPrior, ordered: list[TrackedEntity]) -> str:
    body = {
        "tick": snapshot.tick,
        "entities": [[e.entity_id, e.x, e.y, e.vx, e.vy, e.sigma, e.seen_tick] for e in ordered],
        "prior": [prior.prior_id, prior.version, sorted(prior.region_densities.items())],
    }
    text = json.dumps(body, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_belief(snapshot: TrackSnapshot, prior: HumanPrior) -> Belief:
    """Turn a snapshot and a declared prior into the inputs of ``sample_humans`` and the seeds.

    Entities are revalidated (a dataclass can be built with ``object.__setattr__`` or a subclass),
    ordered by id, and a repeated id is rejected.
    """
    _count("tick", snapshot.tick)
    ordered = sorted(snapshot.entities, key=lambda e: e.entity_id)
    for entity in ordered:
        entity.__post_init__()
    ids = [e.entity_id for e in ordered]
    if len(set(ids)) != len(ids):
        raise BeliefError("an entity id is repeated")
    known = tuple(HumanState((e.x, e.y), (e.vx, e.vy)) for e in ordered)
    return Belief(known, prior, _digest(snapshot, prior, ordered))
