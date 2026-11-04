"""Production crisis composition uses the shared client and deterministic validator."""

import json

import pytest
from llm_support import CAPS, MODEL_ENV
from validation_rig import CONTEXT, SAFE, SAFE_START, _config, _static

from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.crisis_runtime import CrisisRuntime
from waggle.llm.errors import ConfigError, ProviderError
from waggle.llm.providers import ScriptedProvider
from waggle.validation.belief import HumanPrior
from waggle.validation.belief_builder import TrackSnapshot, build_belief

GOOD = json.dumps(
    {"nodes": [SAFE[0]], "rationale": "r", "escalate": False, "escalation_reason": None}
)


def test_runtime_logs_mock_proposal_and_accepts_only_validated_plan() -> None:
    provider = ScriptedProvider("meta", by_role={"planner": GOOD})
    log = InMemoryCallLog()
    runtime = CrisisRuntime.from_environment(
        {"WAGGLE_LLM_PROVIDER": "mock", **CAPS, **MODEL_ENV},
        log,
        fallbacks_enabled=False,
        providers={"meta": provider},
    )
    belief = build_belief(
        TrackSnapshot(tick=0, entities=()), HumanPrior("p", "v1", {"aisle_2": 0.0})
    )
    result = runtime.replan(
        mission_id="m-1",
        context=CONTEXT,
        static=_static(SAFE_START),
        config=_config(),
        belief=belief,
        k=2,
        max_attempts=1000,
        variant_timeout_s=60.0,
        max_rounds=1,
        task_id="crisis-1",
    )
    assert result.status == "accepted"
    assert result.plan is not None
    assert log.records()[-1].task_id == "crisis-1"
    assert provider.calls == 1


def test_runtime_provider_outage_escalates_without_a_plan() -> None:
    runtime = CrisisRuntime.from_environment(
        {"WAGGLE_LLM_PROVIDER": "mock", **CAPS, **MODEL_ENV},
        InMemoryCallLog(),
        fallbacks_enabled=False,
        providers={"meta": ScriptedProvider("meta", by_role={"planner": ProviderError("offline")})},
    )
    belief = build_belief(
        TrackSnapshot(tick=0, entities=()), HumanPrior("p", "v1", {"aisle_2": 0.0})
    )
    result = runtime.replan(
        mission_id="m-1",
        context=CONTEXT,
        static=_static(SAFE_START),
        config=_config(),
        belief=belief,
        k=2,
        max_attempts=1000,
        variant_timeout_s=60.0,
        max_rounds=1,
    )
    assert result.status == "escalated"
    assert result.plan is None
    assert result.history[0].outcome == "proposer_error"


def test_real_mode_cannot_accept_scripted_provider_override() -> None:
    with pytest.raises(ConfigError):
        CrisisRuntime.from_environment(
            {"WAGGLE_LLM_PROVIDER": "http"},
            InMemoryCallLog(),
            fallbacks_enabled=False,
            providers={"meta": ScriptedProvider("meta", by_role={"planner": GOOD})},
        )
