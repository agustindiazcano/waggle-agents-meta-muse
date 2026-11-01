"""Geofence check of a validated plan against trusted hazard zones (ADR-060).

This is the deterministic part of the plan validator that needs no rollout: a plan fails when
a node targets a hazard zone or lists one as a required corridor. The hazard set comes from
trusted state (telemetry thresholds, static geofences), never from text. It does not check the
geometry of a path through open transit zones, which only the rollout validator (ADR-023) can.
"""

from dataclasses import dataclass

from waggle.validation.plan import Plan


@dataclass(frozen=True)
class Counterexample:
    """Why a plan fails: ``code`` is a counterexample name of the replanning design."""

    code: str
    node: str
    zone: str


def check_geofence(plan: Plan, hazard: frozenset[str]) -> tuple[Counterexample, ...]:
    """Every node and hazard zone the plan enters, in node then zone order."""
    found: list[Counterexample] = []
    for node in plan.nodes:
        entered = (*node.corridor_zone_ids, node.target_zone_id)
        for zone in dict.fromkeys(entered):
            if zone in hazard:
                found.append(Counterexample("GEOFENCE_INTRUSION", node.label, zone))
    return tuple(found)
