"""E10 compound-fault templates on development seeds (EXPERIMENTS.md E10).

Templates are fixtures, not labels or results. Each declares its target layer before
any run, a hazard zone that makes the faulty plan fail the geofence stage, a safe plan
the deterministic baseline returns, and the faulty plan a scripted planner returns
first. The static map and fleet mirror the validator test rig geometry on map A.
"""

import json
from dataclasses import dataclass
from typing import Final

from waggle.coordination.corridors import Direction
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.params import RobotKind
from waggle.sim.scenarios import load_map
from waggle.validation.belief import HumanPrior
from waggle.validation.belief_builder import Belief, TrackSnapshot, build_belief
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan import PlanContext
from waggle.validation.plan_rollout import RolloutConfig

ZONES: Final = frozenset(
    {"lane_1", "station_1", "depot_n", "corridor_s", "aisle_1", "connector_e", "corridor_n"}
)
CONTEXT: Final = PlanContext({"R1": 1.5, "R2": 1.5}, frozenset({"ITEM-1"}), ZONES)
ROBOT_START: Final = {"R1": "sw", "R2": "ne"}


def _node(label: str, robot: str, target: str) -> dict[str, object]:
    return {
        "label": label,
        "robot_id": robot,
        "item_id": None,
        "target_zone_id": target,
        "action": "MOVE",
        "corridor_zone_ids": [],
        "avoid_zone_ids": [],
        "wait_for": [],
        "speed_cap_mps": None,
    }


def _raw(*nodes: dict[str, object]) -> str:
    return json.dumps(
        {"nodes": list(nodes), "rationale": "r", "escalate": False, "escalation_reason": None}
    )


@dataclass(frozen=True)
class CrisisTemplate:
    """One compound-fault template with its faulty and safe scripted plans."""

    id: str
    seed: int
    target_layer: str
    fault: str
    hazard_zone_id: str
    safe_second_target: str

    @property
    def mission_id(self) -> str:
        """Mission id of this template incident."""
        return f"e10-{self.id}"

    @property
    def faulty_raw(self) -> str:
        """Plan that enters the hazard zone and must be rejected."""
        return _raw(_node("a", "R1", self.hazard_zone_id), _node("b", "R2", "connector_e"))

    @property
    def safe_raw(self) -> str:
        """Plan that avoids the hazard zone and must pass validation."""
        return _raw(_node("a", "R1", "connector_e"), _node("b", "R2", self.safe_second_target))

    @property
    def baseline_raw(self) -> str:
        """Deterministic recovery plan: the same safe moves, proposed by code."""
        return self.safe_raw


def _both(a: str, b: str, cost: float, corridor: str | None = None) -> tuple[AisleEdge, ...]:
    back = Direction.REVERSE if corridor else Direction.FORWARD
    return (AisleEdge(a, b, cost, corridor), AisleEdge(b, a, cost, corridor, back))


def _graph() -> AisleGraph:
    points = {
        "sw": (3.0, 2.0),
        "sm": (20.0, 2.0),
        "se": (37.0, 2.0),
        "nw": (3.0, 22.0),
        "nm": (20.0, 22.0),
        "ne": (37.0, 22.0),
        "isle": (20.0, 9.0),
    }
    edges = (
        *_both("sw", "sm", 17.0),
        *_both("sm", "se", 17.0),
        *_both("nw", "nm", 18.0),
        *_both("nm", "ne", 17.0),
        *_both("se", "ne", 20.0),
        *_both("sw", "nw", 20.0, "lane_1"),
    )
    return AisleGraph(tuple(AisleNode(k, *v) for k, v in points.items()), edges)


def template_static(template: CrisisTemplate) -> StaticMap:
    """Trusted static map of one template."""
    return StaticMap(
        world=load_map("A"),
        graph=_graph(),
        zone_anchor={
            "station_1": "nw",
            "depot_n": "ne",
            "corridor_s": "sm",
            "aisle_1": "isle",
            "connector_e": "se",
            "lane_1": "sw",
        },
        robot_start=dict(ROBOT_START),
        clearance_m=0.9,
    )


def template_config(template: CrisisTemplate) -> RolloutConfig:
    """Rollout policy of one template. The separation margin is the existing default."""
    return RolloutConfig(
        robot_kinds={"R1": RobotKind.CARRIER, "R2": RobotKind.CARRIER},
        hazard_zone_ids=frozenset({template.hazard_zone_id}),
        separation_margin_m=0.5,
        seed=template.seed,
    )


def template_belief(template: CrisisTemplate) -> Belief:
    """Empty-track belief with a zero-density prior, as in the validator tests."""
    return build_belief(TrackSnapshot(tick=0, entities=()), HumanPrior("p", "v1", {"aisle_2": 0.0}))


TEMPLATES: Final[tuple[CrisisTemplate, ...]] = (
    CrisisTemplate(
        "blocked-aisle",
        101,
        "plan_validator_geofence",
        "aisle blocked, station hazard",
        "station_1",
        "depot_n",
    ),
    CrisisTemplate(
        "fault-occupied",
        202,
        "plan_validator_geofence",
        "dead robot in lane zone",
        "lane_1",
        "station_1",
    ),
    CrisisTemplate(
        "thermal-geofence",
        303,
        "plan_validator_geofence",
        "thermal fault at aisle",
        "aisle_1",
        "station_1",
    ),
)


def get_template(template_id: str) -> CrisisTemplate:
    """Return the template called ``template_id`` or raise KeyError."""
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    raise KeyError(template_id)
