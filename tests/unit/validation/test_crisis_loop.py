"""Crisis planner loop: up to three rounds, then an escalation, never an unvalidated plan."""

import ast
import json
from pathlib import Path

import pytest
from validation_rig import CONTEXT, SAFE, SAFE_START, _config, _node, _static

from waggle.validation.belief import HumanPrior
from waggle.validation.belief_builder import TrackSnapshot, build_belief
from waggle.validation.crisis_loop import CrisisResult, run_crisis_loop

PRIOR = HumanPrior("p", "v1", {"aisle_2": 0.0})
BELIEF = build_belief(TrackSnapshot(tick=0, entities=()), PRIOR)


def _raw(*nodes: dict[str, object], escalate: bool = False) -> str:
    return json.dumps(
        {
            "nodes": list(nodes),
            "rationale": "r",
            "escalate": escalate,
            "escalation_reason": "needs_operator" if escalate else None,
        }
    )


GOOD = _raw(SAFE[0])
# station_1 is a hazard zone in the rejecting runs: the geofence stage refuses this plan.
BAD = _raw(_node("a", "R1", "connector_e"), _node("b", "R2", "station_1"))
HAZARD = frozenset({"station_1"})


class Scripted:
    """A proposer that returns scripted raw outputs and records the feedback it received."""

    def __init__(self, outputs: list[str | Exception]) -> None:
        self.outputs = outputs
        self.feedback: list[str | None] = []

    def propose(self, feedback: str | None) -> str:
        self.feedback.append(feedback)
        out = self.outputs[len(self.feedback) - 1]
        if isinstance(out, Exception):
            raise out
        return out


def _run(
    proposer: Scripted, *, hazard: frozenset[str] = frozenset(), rounds: int = 3
) -> CrisisResult:
    return run_crisis_loop(
        proposer,
        mission_id="m-1",
        context=CONTEXT,
        static=_static(SAFE_START),
        config=_config(hazard_zone_ids=hazard),
        belief=BELIEF,
        k=2,
        max_attempts=1000,
        variant_timeout_s=60.0,
        max_rounds=rounds,
    )


def test_a_valid_first_plan_is_accepted_in_one_round() -> None:
    proposer = Scripted([GOOD])
    result = _run(proposer)
    assert result.status == "accepted"
    assert result.plan is not None
    assert result.rounds == 1
    assert proposer.feedback == [None]


def test_a_rejected_plan_is_fed_back_as_data_and_the_next_round_can_pass() -> None:
    proposer = Scripted([BAD, GOOD])
    result = _run(proposer, hazard=HAZARD)
    assert result.status == "accepted"
    assert result.rounds == 2
    fed = json.loads(proposer.feedback[1] or "")
    assert fed["kind"] == "validator_feedback"
    assert fed["counterexamples"]


def test_three_rejected_rounds_escalate_and_never_return_a_plan() -> None:
    proposer = Scripted([BAD, BAD, BAD, GOOD])
    result = _run(proposer, hazard=HAZARD)
    assert result.status == "escalated"
    assert result.plan is None
    assert result.rounds == 3
    assert result.reason == "rounds_exhausted"
    assert len(proposer.feedback) == 3


def test_unparseable_output_and_proposer_errors_count_as_rejected_rounds() -> None:
    proposer = Scripted(["not json", RuntimeError("boom"), '{"nodes": 1}'])
    result = _run(proposer)
    assert result.status == "escalated"
    assert result.plan is None
    assert [r.outcome for r in result.history] == [
        "unparseable",
        "proposer_error",
        "unparseable",
    ]
    assert json.loads(proposer.feedback[1] or "")["kind"] == "plan_rejected"
    assert "boom" not in (proposer.feedback[2] or "")


def test_a_plan_that_asks_for_the_operator_escalates_at_once() -> None:
    result = _run(Scripted([_raw(escalate=True), GOOD]))
    assert result.status == "escalated"
    assert result.plan is None
    assert result.reason == "plan_requested"
    assert result.rounds == 1


def test_rounds_above_three_or_below_one_are_refused() -> None:
    for bad in (0, 4, -1):
        with pytest.raises(ValueError):
            _run(Scripted([GOOD]), rounds=bad)


def test_the_loop_module_imports_no_llm_side() -> None:
    source = Path(__file__).parents[3] / "src" / "waggle" / "validation" / "crisis_loop.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not [m for m in imported if m.startswith(("waggle.llm", "waggle.governance"))]
