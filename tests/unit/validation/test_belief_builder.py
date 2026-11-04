"""Belief builder: tracked entities and a declared prior become the sampler inputs (ADR-023)."""

import ast
import math
from pathlib import Path
from typing import Any

import pytest

from waggle.validation.belief import HumanPrior, HumanState
from waggle.validation.belief_builder import (
    BeliefError,
    TrackedEntity,
    TrackSnapshot,
    build_belief,
    entity_from_mapping,
)

PRIOR = HumanPrior("p1", "v1", {"station_1": 0.01})


def _entity(eid: int = 1, /, **over: Any) -> TrackedEntity:  # Any: bad types on purpose
    base: dict[str, Any] = {
        "entity_id": eid,
        "x": 4.0,
        "y": 5.0,
        "vx": 0.5,
        "vy": -0.5,
        "sigma": 0.2,
        "seen_tick": 7,
    }
    base.update(over)
    return TrackedEntity(**base)


def test_known_humans_come_from_the_tracked_entities_with_their_velocity() -> None:
    belief = build_belief(TrackSnapshot(tick=9, entities=(_entity(2), _entity(1, x=1.0))), PRIOR)
    assert belief.known_humans == (
        HumanState((1.0, 5.0), (0.5, -0.5)),
        HumanState((4.0, 5.0), (0.5, -0.5)),
    )
    assert belief.prior is PRIOR


def test_digest_is_deterministic_independent_of_order_and_sensitive_to_every_field() -> None:
    a, b = _entity(1), _entity(2, x=9.0)
    base = build_belief(TrackSnapshot(3, (a, b)), PRIOR).snapshot_digest
    assert base == build_belief(TrackSnapshot(3, (b, a)), PRIOR).snapshot_digest
    assert len(base) == 64
    changed = [
        TrackSnapshot(4, (a, b)),
        TrackSnapshot(3, (a, _entity(2, x=9.001))),
        TrackSnapshot(3, (a, _entity(2, vy=0.4))),
        TrackSnapshot(3, (a, _entity(2, sigma=0.3))),
        TrackSnapshot(3, (a, _entity(2, seen_tick=6))),
        TrackSnapshot(3, (a,)),
    ]
    digests = {build_belief(s, PRIOR).snapshot_digest for s in changed}
    assert base not in digests
    assert len(digests) == len(changed)
    other_prior = HumanPrior("p1", "v2", {"station_1": 0.01})
    assert build_belief(TrackSnapshot(3, (a, b)), other_prior).snapshot_digest != base


@pytest.mark.parametrize("field", ["x", "y", "vx", "vy", "sigma"])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_value_is_rejected_not_skipped(field: str, bad: float) -> None:
    with pytest.raises(BeliefError):
        _entity(**{field: bad})


def test_other_bad_values_are_rejected() -> None:
    bad_values: list[dict[str, object]] = [
        {"sigma": -0.1},
        {"x": True},
        {"x": "1.0"},
        {"entity_id": True},
        {"seen_tick": -1},
    ]
    for over in bad_values:
        with pytest.raises(BeliefError):
            _entity(**over)
    with pytest.raises(BeliefError):
        build_belief(TrackSnapshot(tick=-1, entities=()), PRIOR)
    with pytest.raises(BeliefError):
        build_belief(TrackSnapshot(tick=1, entities=(_entity(1), _entity(1, x=2.0))), PRIOR)


def test_a_mapping_with_a_missing_or_extra_key_is_rejected() -> None:
    row = {"entity_id": 1, "x": 1.0, "y": 2.0, "vx": 0.0, "vy": 0.0, "sigma": 0.1, "seen_tick": 0}
    assert entity_from_mapping(row) == TrackedEntity(1, 1.0, 2.0, 0.0, 0.0, 0.1, 0)
    for key in row:
        with pytest.raises(BeliefError):
            entity_from_mapping({k: v for k, v in row.items() if k != key})
    with pytest.raises(BeliefError):
        entity_from_mapping({**row, "extra": 1})


def test_an_empty_snapshot_is_valid_and_has_a_real_digest() -> None:
    belief = build_belief(TrackSnapshot(tick=0, entities=()), PRIOR)
    assert belief.known_humans == ()
    assert len(belief.snapshot_digest) == 64


def test_the_module_does_not_import_control_or_the_llm_side() -> None:
    source = Path(__file__).parents[3] / "src" / "waggle" / "validation" / "belief_builder.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    banned = ("waggle.control", "waggle.llm", "waggle.governance", "waggle.mcp_server", "random")
    assert not [m for m in imported if m.startswith(banned)]
