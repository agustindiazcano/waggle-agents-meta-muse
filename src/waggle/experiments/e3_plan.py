"""E3 runner for the plan schema layer (ADR-059).

The case text asks the planner to return a plan that carries extra fields. The runner performs
that: it takes the JSON object quoted in the case input, adds its fields to a valid base plan
and parses the result with the production schema. An injection counts as blocked when the schema
rejects the plan. The layer has no benign case in the corpus.

``BASE_PLAN`` and ``CONTEXT`` are fixtures. The base plan is valid on its own, which a test
checks, so the injected fields alone decide the outcome. They need maintainer review.
"""

import json
from collections.abc import Callable

from waggle.experiments.e3_eval import Case
from waggle.experiments.e3_mcp_layers import LayerOutcome, LayerReport
from waggle.validation.plan import PlanContext, PlanRejected, parse_plan

PLAN_SCHEMA_LAYER = "plan_schema"
CONTEXT = PlanContext(
    robot_max_speed_mps={"C1": 1.5, "F1": 2.0},
    items=frozenset({"ITEM-17"}),
    zones=frozenset({"Z1", "Z2", "DOCK"}),
)
BASE_PLAN: dict[str, object] = {
    "nodes": [
        {
            "label": "n1",
            "robot_id": "C1",
            "item_id": None,
            "target_zone_id": "DOCK",
            "action": "MOVE",
            "corridor_zone_ids": [],
            "avoid_zone_ids": ["Z1"],
            "wait_for": [],
            "speed_cap_mps": None,
        }
    ],
    "rationale": "route outside Z1",
    "escalate": False,
    "escalation_reason": None,
}
_MISSION = "e3-plan"

Parser = Callable[[str, str, PlanContext], object]


def _injected_fields(text: str) -> dict[str, object]:
    """The JSON object quoted in the case input."""
    start = text.index("{")
    body, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(body, dict):
        raise ValueError("the quoted JSON is not an object")
    return body


def _run(case: Case, parser: Parser) -> LayerOutcome:
    if case.label not in ("injection", "benign"):
        raise ValueError(f"{case.id}: only injection and benign cases can be run")
    raw = json.dumps({**BASE_PLAN, **_injected_fields(case.input)})
    try:
        parser(raw, _MISSION, CONTEXT)
        accepted, code = True, None
    except PlanRejected as error:
        accepted, code = False, error.code
    return LayerOutcome(case.id, case.target_layer, case.label, accepted, code)


def run_plan_schema(cases: tuple[Case, ...], parser: Parser = parse_plan) -> LayerReport:
    """Run every reviewed plan schema case through ``parser`` in id order."""
    chosen = sorted((c for c in cases if c.target_layer == PLAN_SCHEMA_LAYER), key=lambda c: c.id)
    return LayerReport(tuple(_run(c, parser) for c in chosen))
