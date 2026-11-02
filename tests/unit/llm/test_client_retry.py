"""Capped retry with backoff and a per-call timeout in LlmClient, for transport errors only."""

import threading

import pytest
from llm_support import build, req

from waggle.llm.errors import BudgetExceededError, ConfigError, ProviderError, TaskCapExceededError
from waggle.llm.models import Completion, LlmRequest
from waggle.llm.providers import MockProvider, ScriptedProvider
from waggle.llm.task_caps import TaskCaps


def _flaky(failures: int, role: str = "director") -> ScriptedProvider:
    steps: tuple[str | ProviderError, ...] = (ProviderError("boom"),) * failures + ("ok",)
    return ScriptedProvider("meta", by_role={role: steps}, cost_usd=0.1)


def test_default_is_one_attempt_as_before() -> None:
    provider = _flaky(1)
    client, _, _ = build(providers={"meta": provider})
    with pytest.raises(ProviderError):
        client.call(req("director"))
    assert provider.calls == 1


def test_a_transport_error_is_retried_with_exponential_backoff() -> None:
    provider = _flaky(2)
    sleeps: list[float] = []
    client, _, log = build(
        providers={"meta": provider}, retries=3, backoff_s=0.5, sleep=sleeps.append
    )
    assert client.call(req("director")).text == "ok"
    assert provider.calls == 3
    assert sleeps == [0.5, 1.0]
    assert [r.status for r in log.records()] == ["error", "error", "ok"]


def test_the_retry_cap_is_respected_then_the_error_propagates() -> None:
    provider = _flaky(10)
    sleeps: list[float] = []
    client, _, log = build(
        providers={"meta": provider}, retries=2, backoff_s=1.0, sleep=sleeps.append
    )
    with pytest.raises(ProviderError):
        client.call(req("director"))
    assert provider.calls == 3
    assert sleeps == [1.0, 2.0]
    assert [r.status for r in log.records()] == ["error", "error", "error"]


def test_a_retried_success_is_cached_by_request_id() -> None:
    provider = _flaky(1)
    client, _, _ = build(providers={"meta": provider}, retries=1, sleep=lambda s: None)
    client.call(req("director", "same"))
    client.call(req("director", "same"))
    assert provider.calls == 2


def test_only_transport_errors_are_retried() -> None:
    client, providers, _ = build(cost=0.6, retries=3, sleep=lambda s: None)
    client.call(req("director", "a"))
    with pytest.raises(BudgetExceededError):
        client.call(req("director", "b"))
    assert providers["meta"].calls == 1

    capped, capped_providers, _ = build(
        task_caps=TaskCaps(max_calls=1, max_cost_usd=10.0), cost=0.01, retries=3
    )
    capped.call(req("director", "a", task_id="t"))
    with pytest.raises(TaskCapExceededError):
        capped.call(req("director", "b", task_id="t"))
    assert capped_providers["meta"].calls == 1


def test_a_missing_script_is_not_retried() -> None:
    provider = ScriptedProvider("meta", by_role={})
    client, _, _ = build(providers={"meta": provider}, retries=3, sleep=lambda s: None)
    with pytest.raises(Exception, match="no script") as info:
        client.call(req("director"))
    assert not isinstance(info.value, ProviderError)


def test_retries_do_not_change_fallback_labeling() -> None:
    primary = ScriptedProvider("baseten", by_role={"advisor": ProviderError("down")})
    client, providers, log = build(
        providers={"baseten": primary},
        fallbacks=True,
        retries=1,
        sleep=lambda s: None,
    )
    client.call(req("advisor"))
    assert primary.calls == 2
    assert providers["modal"].calls == 1
    assert log.records()[-1].fallback_label == "fallback:baseten->modal:error"


def test_invalid_settings_fail_closed() -> None:
    with pytest.raises(ConfigError):
        build(retries=-1)
    with pytest.raises(ConfigError):
        build(backoff_s=-0.1)
    with pytest.raises(ConfigError):
        build(backoff_s=float("nan"))
    with pytest.raises(ConfigError):
        build(timeout_s=0.0)


class _Slow(MockProvider):
    def __init__(self, release: threading.Event) -> None:
        super().__init__("meta")
        self.release = release

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        self.release.wait(5.0)
        return super().complete(request, model_id)


def test_a_slow_call_times_out_as_a_transport_error_and_the_late_answer_is_dropped() -> None:
    release = threading.Event()
    slow = _Slow(release)
    client, _, log = build(providers={"meta": slow}, timeout_s=0.05)
    try:
        with pytest.raises(ProviderError, match="timeout"):
            client.call(req("director", "slow"))
    finally:
        release.set()
    assert [r.status for r in log.records()] == ["error"]


def test_a_timed_out_call_is_retried_within_the_cap() -> None:
    release = threading.Event()
    slow = _Slow(release)
    client, _, log = build(providers={"meta": slow}, timeout_s=0.05, retries=1)
    try:
        with pytest.raises(ProviderError):
            client.call(req("director"))
    finally:
        release.set()
    assert [r.status for r in log.records()] == ["error", "error"]


def test_a_fast_call_passes_with_a_timeout_set() -> None:
    client, providers, _ = build(timeout_s=2.0)
    assert client.call(req("director")).text == "ok"
    assert providers["meta"].calls == 1
