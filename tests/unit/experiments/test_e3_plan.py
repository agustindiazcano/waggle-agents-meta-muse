"""E3 runner for the plan schema layer (ADR-059)."""

from pathlib import Path

from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases
from waggle.experiments.e3_plan import BASE_PLAN, CONTEXT, PLAN_SCHEMA_LAYER, run_plan_schema
from waggle.validation.plan import Plan, PlanContext, parse_plan

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")


def test_the_plan_schema_layer_is_runnable() -> None:
    assert PLAN_SCHEMA_LAYER in RUNNABLE_LAYERS


def test_the_base_plan_alone_is_accepted_so_only_the_injected_fields_decide() -> None:
    import json

    plan = parse_plan(json.dumps(BASE_PLAN), "e3-plan", CONTEXT)
    assert isinstance(plan, Plan) and len(plan.nodes) == 1


def test_the_executable_field_plan_is_rejected() -> None:
    report = run_plan_schema(CASES)
    assert [o.case_id for o in report.outcomes] == ["E3-T18-02"]
    assert report.missed_injections == ()
    assert report.outcomes[0].code == "unknown_field"


def test_a_parser_that_ignores_extra_fields_is_reported() -> None:
    # Sensitivity: a parser that only reads the known fields accepts the injected ones.
    def lax(raw: str, mission_id: str, context: PlanContext) -> object:
        return object()

    assert run_plan_schema(CASES, parser=lax).missed_injections == ("E3-T18-02",)
