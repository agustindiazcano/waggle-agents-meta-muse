"""Bounded feedback message from counterexamples to the planner (design section 3).

The message is built by code from typed fields. Nothing the plan wrote as text reaches it:
the plan rationale is not an input, a node is named by its position in the plan, and a robot or
zone id is echoed only after a lookup in the trusted fleet and map. Any other value becomes the
fixed token ``UNKNOWN``. The planner side treats the JSON as data.
"""

import json
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from waggle.validation.counterexample import (
    MAX_ENTITIES,
    Counterexample,
    CounterexampleCode,
)

MAX_COUNTEREXAMPLES: Final = 5
UNKNOWN: Final = "UNKNOWN"
HUMAN: Final = "human"
_SEVERITY: Final = {code: rank for rank, code in enumerate(CounterexampleCode)}


@dataclass(frozen=True)
class TrustedIds:
    """What the message may name: the fleet, the map zones and the plan labels in plan order."""

    robots: frozenset[str]
    zones: frozenset[str]
    node_labels: tuple[str, ...]


def _sort_key(cx: Counterexample) -> tuple[float, int, int, str, str, str]:
    time = cx.time_s if cx.time_s is not None else -1.0
    return (
        time,
        _SEVERITY[CounterexampleCode(cx.code)],
        cx.variant if cx.variant is not None else -1,
        cx.node or "",
        cx.zone or "",
        cx.rule.value if cx.rule is not None else "",
    )


def _number(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, 3)


def _node(label: str | None, ids: TrustedIds) -> int | str | None:
    if label is None:
        return None
    if label in ids.node_labels:
        return ids.node_labels.index(label) + 1
    return UNKNOWN


def _zone(zone: str | None, ids: TrustedIds) -> str | None:
    if zone is None:
        return None
    return zone if zone in ids.zones else UNKNOWN


def _entity(name: str, ids: TrustedIds) -> str:
    if name == HUMAN or name in ids.robots or name in ids.zones:
        return name
    return UNKNOWN


def _item(cx: Counterexample, ids: TrustedIds) -> dict[str, object]:
    place = cx.place_xy_m
    return {
        "code": CounterexampleCode(cx.code).value,
        "variant": cx.variant,
        "time_s": _number(cx.time_s),
        "node": _node(cx.node, ids),
        "entities": [_entity(name, ids) for name in cx.entities[:MAX_ENTITIES]],
        "zone": _zone(cx.zone, ids),
        "place_xy_m": None if place is None else [_number(place[0]), _number(place[1])],
        "min_clearance_m": _number(cx.min_clearance_m),
        "rule": cx.rule.value if cx.rule is not None else None,
    }


def build_feedback(counterexamples: Iterable[Counterexample], ids: TrustedIds) -> str:
    """JSON feedback with at most five counterexamples and a count per code for the rest."""
    ordered = sorted(counterexamples, key=_sort_key)
    shown, excess = ordered[:MAX_COUNTEREXAMPLES], ordered[MAX_COUNTEREXAMPLES:]
    counts = Counter(CounterexampleCode(cx.code) for cx in excess)
    omitted = {code.value: counts[code] for code in CounterexampleCode if counts[code]}
    body: dict[str, object] = {
        "kind": "validator_feedback",
        "counterexamples": [_item(cx, ids) for cx in shown],
        "omitted": omitted,
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=True)
