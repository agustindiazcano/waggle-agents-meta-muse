"""Tests for advisor runtime, prompt versioning, and invariants I11 and I12.

ADVISORS_DESIGN 5, 8, 13, 14 (feat/advisor-runtime).
All tests use the mock and scripted providers with no network and no keys.
"""

import ast
import threading
import time
from pathlib import Path

import pytest
from llm_support import build

from waggle.governance.advisor_input import (
    AdvisorInputLimits,
    InboundMessage,
    TrustedFacts,
)
from waggle.governance.caution import CautionAction, CautionConfig
from waggle.governance.caution_log import CautionLog
from waggle.governance.classifier import MockClassifier
from waggle.llm.advisor_runtime import (
    ADVISOR_PROMPT_HASH,
    ADVISOR_PROMPT_PATH,
    ADVISOR_PROMPT_VERSION,
    AdvisorRuntime,
    advisor_request_id,
    render_advisor_prompt,
)
from waggle.llm.errors import ProviderError
from waggle.llm.models import Completion, LlmRequest
from waggle.llm.providers import ScriptedProvider

CONFIG = CautionConfig(max_window_ticks=20, h_max_ticks=10, n_max_holds=3)
INPUT_LIMITS = AdvisorInputLimits(
    max_prompt_chars=2000,
    min_interval_ticks=5,
    max_calls_per_task=10,
    max_messages=5,
)

FACTS = TrustedFacts(
    robot_id="R1",
    chassis="forklift",
    speed=1.0,
    active_reasons=("OCCLUSION",),
    zone="Z1",
    task_step="travel",
    nearest_distance=4.2,
    occluded=False,
    geofences=("G1",),
    lease_holders=(("corr_1", "R2"),),
)

VALID_SLOW = '{"action":"slow","speed_cap":0.5,"duration_ticks":5,"code":null}'
VALID_HOLD = '{"action":"hold","speed_cap":null,"duration_ticks":4,"code":null}'
VALID_NONE = '{"action":"none","speed_cap":null,"duration_ticks":null,"code":null}'
EXTRA_FIELD = '{"action":"slow","speed_cap":0.5,"duration_ticks":5,"code":null,"extra":"bad"}'
WIDENING = '{"action":"slow","speed_cap":2.5,"duration_ticks":5,"code":null}'
NEGATIVE_CAP = '{"action":"slow","speed_cap":-0.5,"duration_ticks":5,"code":null}'
GARBAGE = "this is not json at all"


def _make_runtime(
    script_by_role: dict[str, str | ProviderError] | None = None,
    script_by_request: dict[str, str | ProviderError] | None = None,
    timeout_s: float = 2.0,
    max_response_chars: int = 1024,
    rate_limit_ticks: int = 5,
    caps: dict[str, str] | None = None,
    cost: float = 0.01,
    classifier: MockClassifier | None = None,
) -> tuple[AdvisorRuntime, CautionLog, ScriptedProvider]:
    provider = ScriptedProvider(
        "baseten",
        by_role=script_by_role or {"advisor": VALID_SLOW},
        by_request=script_by_request,
        cost_usd=cost,
    )
    providers = ("meta", "baseten", "modal", "vertex")
    extra_caps = caps or {f"{p.upper()}_SPEND_CAP_USD": "1.0" for p in providers}
    client, _, _ = build(providers={"baseten": provider}, caps=extra_caps, cost=cost)
    log = CautionLog(CONFIG)
    clf = classifier or MockClassifier(response='{"label":"benign","reason_code":"ok"}')
    runtime = AdvisorRuntime(
        client=client,
        caution_log=log,
        config=CONFIG,
        timeout_s=timeout_s,
        max_response_chars=max_response_chars,
        rate_limit_ticks=rate_limit_ticks,
        classifier=clf,
        input_limits=INPUT_LIMITS,
    )
    return runtime, log, provider


def test_prompt_file_is_versioned_and_states_untrusted_data_and_speed_cap() -> None:
    assert ADVISOR_PROMPT_PATH.name == "advisor_v1.txt"
    assert ADVISOR_PROMPT_VERSION == "advisor-v1"
    text = ADVISOR_PROMPT_PATH.read_text(encoding="utf-8")
    assert "advisor-v1" in text
    assert ADVISOR_PROMPT_HASH
    assert "untrusted data" in text
    assert "speed cap" in text


def test_prompt_rendering_substitutes_snapshot() -> None:
    prompt = render_advisor_prompt("test_snapshot_content")
    assert "test_snapshot_content" in prompt
    assert "untrusted data" in prompt


def test_request_id_is_derived_from_robot_id_and_tick() -> None:
    rid = advisor_request_id("R1", 42)
    assert rid == "advisor-R1-42"
    assert advisor_request_id("R1", 42) == advisor_request_id("R1", 42)
    assert advisor_request_id("R1", 42) != advisor_request_id("R2", 42)
    assert advisor_request_id("R1", 42) != advisor_request_id("R1", 43)


def test_valid_caution_accepted_recorded_and_limit_returned() -> None:
    runtime, log, provider = _make_runtime({"advisor": VALID_SLOW})
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "accepted"
    assert result.reason is None
    assert len(log.events) == 1
    event = log.events[0]
    assert event.robot_id == "R1"
    assert event.action == CautionAction.SLOW
    assert event.speed_cap == 0.5
    assert len(result.limits) == 1
    assert result.limits[0].speed_cap == 0.5
    assert provider.calls == 1


def test_extra_field_is_rejected() -> None:
    runtime, log, _ = _make_runtime({"advisor": EXTRA_FIELD})
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "rejected"
    assert result.reason == "unknown_field"
    assert len(log.events) == 0
    assert result.limits == ()


def test_widening_cap_is_rejected() -> None:
    runtime, log, _ = _make_runtime({"advisor": WIDENING})
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "rejected"
    assert result.reason == "widening"
    assert len(log.events) == 0
    assert result.limits == ()


def test_negative_cap_is_rejected() -> None:
    runtime, log, _ = _make_runtime({"advisor": NEGATIVE_CAP})
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "rejected"
    assert result.reason == "bad_value"
    assert len(log.events) == 0
    assert result.limits == ()


def test_garbage_text_is_rejected() -> None:
    runtime, log, _ = _make_runtime({"advisor": GARBAGE})
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "rejected"
    assert result.reason == "not_an_object"
    assert len(log.events) == 0
    assert result.limits == ()


def test_oversize_response_yields_no_caution_and_oversize_label() -> None:
    runtime, log, _ = _make_runtime({"advisor": VALID_SLOW}, max_response_chars=20)
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "oversize"
    assert result.reason == "too_long"
    assert len(log.events) == 0
    assert result.limits == ()


def test_provider_error_yields_no_caution_and_error_label() -> None:
    err = ProviderError("simulated provider error")
    runtime, log, _ = _make_runtime({"advisor": err})
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "error"
    assert "simulated provider error" in (result.reason or "")
    assert len(log.events) == 0
    assert result.limits == ()


class SlowProvider(ScriptedProvider):
    """Provider that simulates high latency for timeout testing."""

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        time.sleep(0.15)
        return super().complete(request, model_id)


def test_timeout_yields_no_caution_and_timeout_label() -> None:
    provider = SlowProvider(
        "baseten",
        by_role={"advisor": VALID_SLOW},
        cost_usd=0.01,
    )
    providers = ("meta", "baseten", "modal", "vertex")
    extra_caps = {f"{p.upper()}_SPEND_CAP_USD": "1.0" for p in providers}
    client, _, _ = build(providers={"baseten": provider}, caps=extra_caps, cost=0.01)
    log = CautionLog(CONFIG)
    runtime = AdvisorRuntime(
        client=client,
        caution_log=log,
        config=CONFIG,
        timeout_s=0.05,
        max_response_chars=1024,
        rate_limit_ticks=5,
        classifier=MockClassifier(response='{"label":"benign","reason_code":"ok"}'),
        input_limits=INPUT_LIMITS,
    )
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "timeout"
    assert result.reason == "timeout"
    assert len(log.events) == 0
    assert result.limits == ()


class BlockedProvider(ScriptedProvider):
    """Provider that blocks until the test releases it, so a slow call is not a sleep guess."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.release = threading.Event()

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        self.release.wait(5.0)
        return super().complete(request, model_id)


def test_the_timeout_bounds_the_wait_and_does_not_wait_for_the_provider() -> None:
    provider = BlockedProvider("baseten", by_role={"advisor": VALID_SLOW}, cost_usd=0.01)
    providers = ("meta", "baseten", "modal", "vertex")
    caps = {f"{p.upper()}_SPEND_CAP_USD": "1.0" for p in providers}
    client, _, _ = build(providers={"baseten": provider}, caps=caps, cost=0.01)
    runtime = AdvisorRuntime(
        client=client,
        caution_log=CautionLog(CONFIG),
        config=CONFIG,
        timeout_s=0.05,
        max_response_chars=1024,
        rate_limit_ticks=5,
        classifier=MockClassifier(response='{"label":"benign","reason_code":"ok"}'),
        input_limits=INPUT_LIMITS,
    )
    started = time.monotonic()
    try:
        result = runtime.advise(
            FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
        )
        elapsed = time.monotonic() - started
    finally:
        provider.release.set()
    assert result.status == "timeout" and result.limits == ()
    assert elapsed < 1.5


def test_the_classifier_and_the_input_limits_are_required() -> None:
    client, _, _ = build(providers={}, caps={}, cost=0.01)
    with pytest.raises(TypeError):
        AdvisorRuntime(  # type: ignore[call-arg]
            client=client,
            caution_log=CautionLog(CONFIG),
            config=CONFIG,
            timeout_s=1.0,
            max_response_chars=10,
            rate_limit_ticks=1,
        )


def test_budget_denial_yields_no_caution_and_budget_label() -> None:
    providers = ("meta", "baseten", "modal", "vertex")
    zero_caps = {f"{p.upper()}_SPEND_CAP_USD": "0.0" for p in providers}
    runtime, log, _ = _make_runtime(
        {"advisor": VALID_SLOW},
        caps=zero_caps,
        cost=1.0,
    )
    result = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "budget_denied"
    assert len(log.events) == 0
    assert result.limits == ()


def test_repeated_request_id_served_from_cache_and_single_log_record() -> None:
    runtime, log, provider = _make_runtime({"advisor": VALID_SLOW})
    res1 = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res1.status == "accepted"
    assert len(log.events) == 1
    assert provider.calls == 1

    res2 = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res2.status in ("accepted", "cached")
    assert res2.cached is True
    assert len(log.events) == 1
    assert provider.calls == 1
    assert res2.limits == res1.limits


def test_rate_limit_enforced_per_robot() -> None:
    runtime, _log, provider = _make_runtime(
        {"advisor": VALID_SLOW},
        rate_limit_ticks=10,
    )
    res1 = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res1.status == "accepted"
    assert provider.calls == 1

    # Call at tick 15 is too soon (15 - 10 = 5 < 10).
    res2 = runtime.advise(
        FACTS, tick=15, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res2.status == "rate_limited"
    assert res2.reason == "too_soon"
    assert provider.calls == 1

    # Call at tick 20 is allowed (20 - 10 = 10 >= 10).
    res3 = runtime.advise(
        FACTS, tick=20, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res3.status == "accepted"
    assert provider.calls == 2


def test_determinism_same_input_and_script_give_same_output() -> None:
    runtime1, log1, _ = _make_runtime({"advisor": VALID_SLOW})
    runtime2, log2, _ = _make_runtime({"advisor": VALID_SLOW})
    res1 = runtime1.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    res2 = runtime2.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res1.status == res2.status
    assert res1.limits == res2.limits
    assert res1.event == res2.event
    assert log1.events == log2.events


def test_ast_imports_no_forbidden_modules() -> None:
    target_path = Path(__file__).parents[3] / "src" / "waggle" / "llm" / "advisor_runtime.py"
    tree = ast.parse(target_path.read_text(encoding="utf-8"), filename=str(target_path))
    forbidden_prefixes = (
        "waggle.sim",
        "waggle.control",
        "waggle.mcp_server",
        "http",
        "urllib",
        "httpx",
        "requests",
        "aiohttp",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    assert not alias.name.startswith(prefix), f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for prefix in forbidden_prefixes:
                assert not mod.startswith(prefix), f"Forbidden from-import: {mod}"


def test_i11_unscored_message_withheld_and_signal_recorded() -> None:
    clf = MockClassifier(response='{"label":"uncertain","reason_code":"ambiguous"}')
    runtime, log, provider = _make_runtime(
        {"advisor": VALID_SLOW},
        classifier=clf,
    )
    raw_msg = '{"sender":"R2","recipient":"R1","status":"blocked"}'
    msg = InboundMessage(authenticated_sender="R2", raw=raw_msg)
    res = runtime.advise(
        FACTS,
        tick=10,
        current_cap=1.5,
        class_max=2.0,
        run_id="run-1",
        task_id="task-1",
        messages=[msg],
    )
    assert res.status == "accepted"
    # An unscored_input signal event was recorded in the caution log.
    unscored_events = [e for e in log.events if e.code == "unscored_input"]
    assert len(unscored_events) == 1
    assert unscored_events[0].action == CautionAction.ASK_ORGANIZER
    # The message itself was withheld from the model prompt.
    assert provider.calls == 1
    # Verify that the model was called without the withheld message.
    assert "blocked" not in runtime.last_rendered_prompt


def test_i12_repeated_request_id_returns_cached_result_with_no_second_call() -> None:
    runtime, _log, provider = _make_runtime({"advisor": VALID_HOLD})
    res1 = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res1.status == "accepted"
    assert provider.calls == 1
    res2 = runtime.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert res2.cached is True
    assert provider.calls == 1
    assert res2.limits == res1.limits
