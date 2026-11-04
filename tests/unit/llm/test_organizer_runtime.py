"""Tests for organizer runtime, prompt versioning, tool dispatch boundary and loop/turn caps.

ADVISORS_DESIGN 6, 8, 9, 13, 14 (feat/organizer-boundary).
All tests run offline on scripted and mock providers with no network and no keys.
"""

import ast
import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from llm_support import build

from waggle.governance.advisor_input import InboundMessage, TrustedFacts
from waggle.governance.caution import CautionAction, CautionConfig
from waggle.governance.caution_log import CautionLog
from waggle.governance.classifier import MockClassifier
from waggle.governance.organizer import ArgScalar, OrganizerAction, OrganizerLimits
from waggle.llm.errors import ProviderError
from waggle.llm.models import Completion, LlmRequest
from waggle.llm.organizer_runtime import (
    ORGANIZER_PROMPT_HASH,
    ORGANIZER_PROMPT_PATH,
    ORGANIZER_PROMPT_VERSION,
    OrganizerRuntime,
    organizer_request_id,
    render_organizer_prompt,
)
from waggle.llm.providers import ScriptedProvider

CONFIG = CautionConfig(max_window_ticks=20, h_max_ticks=10, n_max_holds=3)
LIMITS = OrganizerLimits(
    max_prompt_chars=2000,
    min_interval_ticks=5,
    max_turns_per_task=4,
    max_messages_per_task=2,
    max_identical_repeats=2,
    h_max_ticks=10,
)

FACTS = TrustedFacts(
    robot_id="R1",
    chassis="carrier",
    speed=1.0,
    active_reasons=("OCCLUSION",),
    zone="Z1",
    task_step="travel",
    nearest_distance=3.0,
    occluded=True,
    geofences=(),
    lease_holders=(("corr_1", "R2"),),
)

VALID_NONE = (
    '{"action":"none","duration_ticks":null,"tool":null,'
    '"arguments":null,"recipient":null,"status":null}'
)
VALID_YIELD = (
    '{"action":"yield_hold","duration_ticks":6,"tool":null,'
    '"arguments":null,"recipient":null,"status":null}'
)
VALID_TOOL = (
    '{"action":"call_tool","duration_ticks":null,"tool":"release_zone",'
    '"arguments":{"zone_id":"corr_1"},"recipient":null,"status":null}'
)
VALID_MSG = (
    '{"action":"send_message","duration_ticks":null,"tool":null,'
    '"arguments":null,"recipient":"R2","status":"waiting"}'
)
DISALLOWED_TOOL = (
    '{"action":"call_tool","duration_ticks":null,"tool":"dispatch_tech",'
    '"arguments":{"ticket_id":"T1"},"recipient":null,"status":null}'
)


class FakeToolDispatch:
    """Fake MCP boundary port recording authenticated robot identity and tool arguments."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[tuple[str, str, dict[str, ArgScalar], str]] = []

    def call_tool(
        self,
        *,
        robot_id: str,
        tool: str,
        arguments: Mapping[str, ArgScalar],
        request_id: str,
    ) -> Mapping[str, object]:
        self.calls.append((robot_id, tool, dict(arguments), request_id))
        if self.should_fail:
            raise RuntimeError("simulated MCP boundary failure")
        return {"ok": True, "tool": tool}


def _make_runtime(
    script_by_role: dict[str, str | ProviderError] | None = None,
    timeout_s: float = 2.0,
    max_response_chars: int = 1024,
    caps: dict[str, str] | None = None,
    cost: float = 0.01,
    classifier: MockClassifier | None = None,
    tool_dispatch: FakeToolDispatch | None = None,
) -> tuple[OrganizerRuntime, CautionLog, ScriptedProvider]:
    provider = ScriptedProvider(
        "baseten",
        by_role=script_by_role or {"organizer": VALID_YIELD},
        cost_usd=cost,
    )
    providers = ("meta", "baseten", "modal", "vertex")
    extra_caps = caps or {f"{p.upper()}_SPEND_CAP_USD": "1.0" for p in providers}
    client, _, _ = build(providers={"baseten": provider}, caps=extra_caps, cost=cost)
    log = CautionLog(CONFIG)
    clf = classifier or MockClassifier(response='{"label":"benign","reason_code":"ok"}')
    runtime = OrganizerRuntime(
        client=client,
        caution_log=log,
        caution_config=CONFIG,
        limits=LIMITS,
        timeout_s=timeout_s,
        max_response_chars=max_response_chars,
        max_messages=5,
        classifier=clf,
        tool_dispatch=tool_dispatch,
    )
    return runtime, log, provider


def test_prompt_file_is_versioned_and_fences_untrusted_data() -> None:
    assert ORGANIZER_PROMPT_PATH.name == "organizer_v1.txt"
    assert ORGANIZER_PROMPT_VERSION == "organizer-v1"
    text = ORGANIZER_PROMPT_PATH.read_text(encoding="utf-8")
    assert "organizer-v1" in text
    assert ORGANIZER_PROMPT_HASH
    assert "untrusted" in text
    rendered = render_organizer_prompt("sample_context_block")
    assert "sample_context_block" in rendered


def test_request_id_is_derived_from_robot_and_tick() -> None:
    assert organizer_request_id("R1", 15) == "organizer-R1-15"
    assert organizer_request_id("R1", 15) != organizer_request_id("R2", 15)


def test_yield_hold_records_caution_event_and_zero_speed_limit() -> None:
    runtime, log, provider = _make_runtime({"organizer": VALID_YIELD})
    res = runtime.organize(
        FACTS,
        tick=10,
        class_max=2.0,
        run_id="run-1",
        task_id="task-1",
        ask_signals=("yield",),
    )
    assert res.status == "accepted"
    assert res.decision is not None
    assert res.decision.action is OrganizerAction.YIELD_HOLD
    assert res.hold_event is not None
    assert res.hold_event.action is CautionAction.HOLD
    assert res.hold_event.speed_cap == 0.0
    assert len(log.events) == 1
    assert len(res.limits) == 1
    assert res.limits[0].speed_cap == 0.0
    assert provider.calls == 1


def test_tool_call_uses_authenticated_robot_identity_and_catches_dispatch_errors() -> None:
    dispatch = FakeToolDispatch(should_fail=False)
    runtime, log, _ = _make_runtime({"organizer": VALID_TOOL}, tool_dispatch=dispatch)
    res = runtime.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert res.status == "accepted"
    assert res.tool_outcome == {"ok": True, "tool": "release_zone"}
    assert dispatch.calls == [("R1", "release_zone", {"zone_id": "corr_1"}, res.request_id)]
    assert len(log.events) == 0

    # Exception inside tool dispatch returns tool_error without crashing the process (AGENTS.md 6.5)
    failing_dispatch = FakeToolDispatch(should_fail=True)
    runtime_err, _, _ = _make_runtime({"organizer": VALID_TOOL}, tool_dispatch=failing_dispatch)
    res_err = runtime_err.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert res_err.status == "tool_error"
    assert res_err.reason == "tool_dispatch_failed"


def test_send_message_validates_and_records_outbound_message() -> None:
    runtime, _, _ = _make_runtime({"organizer": VALID_MSG})
    res = runtime.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert res.status == "accepted"
    assert res.outbound_message is not None
    assert json.loads(res.outbound_message) == {
        "sender": "R1",
        "recipient": "R2",
        "status": "waiting",
    }
    assert len(runtime.outbound_messages) == 1


def test_disallowed_tool_and_loop_detection_are_rejected() -> None:
    runtime_bad, log, _ = _make_runtime({"organizer": DISALLOWED_TOOL})
    res_bad = runtime_bad.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert res_bad.status == "rejected"
    assert res_bad.reason == "disallowed_tool"
    assert len(log.events) == 0

    # Loop detection after max_identical_repeats=2 identical yield_hold decisions
    runtime_loop, _, _ = _make_runtime({"organizer": VALID_YIELD})
    r1 = runtime_loop.organize(FACTS, tick=0, class_max=2.0, run_id="run-1", task_id="task-1")
    r2 = runtime_loop.organize(FACTS, tick=5, class_max=2.0, run_id="run-1", task_id="task-1")
    r3 = runtime_loop.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert r1.status == "accepted"
    assert r2.status == "accepted"
    assert r3.status == "rejected"
    assert r3.reason == "loop_detected"


def test_repeated_request_id_returns_cached_result_without_second_call() -> None:
    dispatch = FakeToolDispatch()
    runtime, _, provider = _make_runtime({"organizer": VALID_TOOL}, tool_dispatch=dispatch)
    r1 = runtime.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    r2 = runtime.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert r1.status == "accepted"
    assert r2.status == "cached"
    assert r2.cached is True
    assert provider.calls == 1
    assert len(dispatch.calls) == 1


def test_same_robot_tick_in_different_runs_and_tasks_never_reuses_a_decision() -> None:
    runtime, _, provider = _make_runtime({"organizer": VALID_NONE})
    results = [
        runtime.organize(FACTS, tick=10, class_max=2.0, run_id=run, task_id=task)
        for run, task in (("run-1", "task-1"), ("run-2", "task-1"), ("run-2", "task-2"))
    ]
    assert all(r.status == "accepted" and not r.cached for r in results)
    assert len({r.request_id for r in results}) == 3
    assert provider.calls == 3


class RefusedToolDispatch(FakeToolDispatch):
    """A tool returns an explicit failure receipt without raising."""

    def call_tool(
        self, *, robot_id: str, tool: str, arguments: Mapping[str, ArgScalar], request_id: str
    ) -> Mapping[str, object]:
        return {"ok": False, "error": "denied"}


class MalformedToolDispatch(FakeToolDispatch):
    """A broken adapter returns a value outside its declared contract."""

    def call_tool(
        self, *, robot_id: str, tool: str, arguments: Mapping[str, ArgScalar], request_id: str
    ) -> Mapping[str, object]:
        return None  # type: ignore[return-value]  # exercise malformed external receipt


def test_malformed_tool_receipt_becomes_an_error_result() -> None:
    runtime, _, _ = _make_runtime({"organizer": VALID_TOOL}, tool_dispatch=MalformedToolDispatch())
    result = runtime.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert result.status == "tool_error"


def test_failed_tool_receipt_is_never_accepted_or_cached_as_success() -> None:
    runtime, _, _ = _make_runtime({"organizer": VALID_TOOL}, tool_dispatch=RefusedToolDispatch())
    result = runtime.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
    assert result.status == "tool_error"
    assert result.reason == "tool_dispatch_refused"


class BlockedProvider(ScriptedProvider):
    """Provider that blocks until released by the test."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.release = threading.Event()

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        self.release.wait(5.0)
        return super().complete(request, model_id)


def test_timeout_bounds_wait_and_degrades_safely() -> None:
    provider = BlockedProvider("baseten", by_role={"organizer": VALID_YIELD}, cost_usd=0.01)
    providers = ("meta", "baseten", "modal", "vertex")
    caps = {f"{p.upper()}_SPEND_CAP_USD": "1.0" for p in providers}
    client, _, _ = build(providers={"baseten": provider}, caps=caps, cost=0.01)
    runtime = OrganizerRuntime(
        client=client,
        caution_log=CautionLog(CONFIG),
        caution_config=CONFIG,
        limits=LIMITS,
        timeout_s=0.05,
        max_response_chars=1024,
        max_messages=5,
        classifier=MockClassifier(response='{"label":"benign","reason_code":"ok"}'),
    )
    started = time.monotonic()
    try:
        res = runtime.organize(FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1")
        elapsed = time.monotonic() - started
    finally:
        provider.release.set()
    assert res.status == "timeout"
    assert res.limits == ()
    assert elapsed < 1.5


def test_unscored_inbound_message_is_withheld_from_organizer_prompt() -> None:
    clf = MockClassifier(response='{"label":"uncertain","reason_code":"ambiguous"}')
    runtime, _, provider = _make_runtime({"organizer": VALID_NONE}, classifier=clf)
    msg = InboundMessage(
        authenticated_sender="R2",
        raw='{"sender":"R2","recipient":"R1","status":"blocked"}',
    )
    res = runtime.organize(
        FACTS, tick=10, class_max=2.0, run_id="run-1", task_id="task-1", messages=[msg]
    )
    assert res.status == "accepted"
    assert provider.calls == 1
    assert "sender=R2 status=blocked" not in runtime.last_rendered_prompt
    assert '<untrusted source="robot_message">' not in runtime.last_rendered_prompt


def test_ast_imports_no_forbidden_modules() -> None:
    target_path = Path(__file__).parents[3] / "src" / "waggle" / "llm" / "organizer_runtime.py"
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
