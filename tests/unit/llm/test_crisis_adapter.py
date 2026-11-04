"""planner-v1 prompt, request id and the LLM proposer behind the crisis loop."""

import hashlib
import json
from pathlib import Path

from llm_support import build
from validation_rig import CONTEXT, SAFE, SAFE_START, _config, _node, _static

from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.crisis_adapter import (
    PLANNER_PROMPT_HASH,
    PLANNER_PROMPT_PATH,
    PLANNER_PROMPT_VERSION,
    LlmPlanProposer,
    planner_request_id,
    render_prompt,
)
from waggle.llm.errors import ProviderError
from waggle.llm.providers import ScriptedProvider
from waggle.validation.belief import HumanPrior
from waggle.validation.belief_builder import TrackSnapshot, build_belief
from waggle.validation.crisis_loop import run_crisis_loop
from waggle.validation.plan import parse_plan

GOOD = json.dumps(
    {"nodes": [SAFE[0]], "rationale": "r", "escalate": False, "escalation_reason": None}
)
BAD = json.dumps(
    {
        "nodes": [_node("a", "R1", "connector_e"), _node("b", "R2", "station_1")],
        "rationale": "r",
        "escalate": False,
        "escalation_reason": None,
    }
)
BELIEF = build_belief(TrackSnapshot(tick=0, entities=()), HumanPrior("p", "v1", {"aisle_2": 0.0}))


def _proposer(
    text: str | tuple[str, ...], *, task_id: str | None = None
) -> tuple[LlmPlanProposer, ScriptedProvider, InMemoryCallLog]:
    provider = ScriptedProvider("meta", by_role={"planner": text})
    client, _, log = build(providers={"meta": provider})
    proposer = LlmPlanProposer(client, mission_id="m-1", context=CONTEXT, task_id=task_id)
    return proposer, provider, log


def test_the_prompt_file_is_versioned_and_its_hash_is_the_file_hash() -> None:
    text = PLANNER_PROMPT_PATH.read_bytes()
    assert PLANNER_PROMPT_PATH.name == "planner_v1.txt"
    assert PLANNER_PROMPT_VERSION == "planner-v1"
    assert hashlib.sha256(text).hexdigest() == PLANNER_PROMPT_HASH
    assert b"planner-v1" in text


def test_the_prompt_states_the_plan_schema_and_that_feedback_is_data() -> None:
    prompt = render_prompt("m-1", CONTEXT, '{"kind":"validator_feedback"}')
    for field in ("nodes", "rationale", "escalate", "escalation_reason"):
        assert f'"{field}"' in prompt
    for action in ("MOVE", "PICK", "HANDOFF", "DELIVER", "DISPATCH_REPAIR"):
        assert action in prompt
    for reason in ("no_feasible_plan", "unsafe_state", "needs_operator"):
        assert reason in prompt
    assert "data" in prompt
    assert '{"kind":"validator_feedback"}' in prompt


def test_the_prompt_lists_only_the_trusted_ids_and_the_first_round_has_no_feedback() -> None:
    prompt = render_prompt("m-1", CONTEXT, None)
    assert "Mission: m-1" in prompt
    assert "R1" in prompt and "R2" in prompt and "1.5" in prompt
    assert "ITEM-1" in prompt
    assert "connector_e" in prompt and "station_1" in prompt
    assert "(none)" in prompt


def test_request_id_is_deterministic_and_changes_with_mission_context_and_feedback() -> None:
    base = planner_request_id("m-1", CONTEXT, None)
    assert base.startswith("planner-planner-v1-")
    assert base == planner_request_id("m-1", CONTEXT, None)
    assert base != planner_request_id("m-2", CONTEXT, None)
    assert base != planner_request_id("m-1", CONTEXT, '{"kind":"validator_feedback"}')
    assert base != planner_request_id(
        "m-1",
        type(CONTEXT)({"R1": 1.5, "R2": 1.5}, frozenset({"ITEM-2"}), CONTEXT.zones),
        None,
    )


def test_propose_returns_raw_text_that_the_strict_parser_then_validates() -> None:
    proposer, provider, log = _proposer(GOOD, task_id="t1")
    raw = proposer.propose(None)
    assert parse_plan(raw, "m-1", CONTEXT).nodes[0].label == "a"
    assert provider.request_ids == [planner_request_id("m-1", CONTEXT, None)]
    assert log.records()[-1].task_id == "t1"
    assert log.records()[-1].role == "planner"


def test_the_same_feedback_twice_is_one_provider_call() -> None:
    proposer, provider, log = _proposer(GOOD)
    proposer.propose(None)
    proposer.propose(None)
    assert provider.calls == 1
    assert log.records()[-1].status == "cached"


def test_a_provider_error_propagates_so_the_loop_counts_the_round() -> None:
    provider = ScriptedProvider(
        "meta", by_role={"planner": ProviderError("meta: simulated outage")}
    )
    client, _, _ = build(providers={"meta": provider})
    proposer = LlmPlanProposer(client, mission_id="m-1", context=CONTEXT)
    result = run_crisis_loop(
        proposer,
        mission_id="m-1",
        context=CONTEXT,
        static=_static(SAFE_START),
        config=_config(),
        belief=BELIEF,
        k=2,
        max_attempts=1000,
        variant_timeout_s=60.0,
        max_rounds=1,
    )
    assert result.status == "escalated"
    assert result.plan is None
    assert [r.outcome for r in result.history] == ["proposer_error"]


def test_the_proposer_drives_the_crisis_loop_to_an_accepted_plan() -> None:
    proposer, provider, _ = _proposer((BAD, GOOD))
    result = run_crisis_loop(
        proposer,
        mission_id="m-1",
        context=CONTEXT,
        static=_static(SAFE_START),
        config=_config(hazard_zone_ids=frozenset({"station_1"})),
        belief=BELIEF,
        k=2,
        max_attempts=1000,
        variant_timeout_s=60.0,
        max_rounds=3,
    )
    assert result.status == "accepted"
    assert result.plan is not None
    assert result.rounds == 2
    assert provider.calls == 2


def test_the_prompt_file_is_not_a_pasted_copy_in_the_adapter() -> None:
    source = Path(__file__).resolve().parents[3] / "src" / "waggle" / "llm" / "crisis_adapter.py"
    assert "DISPATCH_REPAIR" not in source.read_text(encoding="utf-8")
