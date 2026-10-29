import pytest
from llm_support import build, req

from waggle.llm.errors import (
    BudgetExceededError,
    ProviderError,
    TaskCapExceededError,
    UnknownRoleError,
)
from waggle.llm.task_caps import TaskCaps

# One role whose primary route is each provider (vertex only appears as a fallback).
ROLE_FOR = {"meta": "director", "baseten": "court_2", "modal": "court_3"}


@pytest.mark.parametrize(("provider", "role"), sorted(ROLE_FOR.items()))
def test_call_goes_to_the_primary_provider_and_is_logged(provider: str, role: str) -> None:
    client, providers, log = build()
    result = client.call(req(role))
    assert providers[provider].calls == 1
    record = log.records()[-1]
    assert record.provider == provider
    assert record.status == "ok"
    assert record.cost_usd == result.cost_usd == 0.4
    assert record.tokens_in > 0
    assert record.latency_s >= 0
    assert record.fallback_label is None
    assert record.model_id == result.model_id


@pytest.mark.parametrize(("provider", "role"), sorted(ROLE_FOR.items()))
def test_over_cap_makes_no_call_and_logs_denial(provider: str, role: str) -> None:
    client, providers, log = build()
    client.call(req(role, "a"))
    client.call(req(role, "b"))
    with pytest.raises(BudgetExceededError):
        client.call(req(role, "c"))
    assert providers[provider].calls == 2
    assert [r.status for r in log.records()][-1] == "denied"


def test_exhausting_meta_never_routes_to_another_provider() -> None:
    client, providers, _ = build(fallbacks=True)
    client.call(req("director", "a"))
    client.call(req("director", "b"))
    with pytest.raises(BudgetExceededError):
        client.call(req("director", "c"))
    assert providers["baseten"].calls == providers["modal"].calls == providers["vertex"].calls == 0


def test_exhausted_provider_with_declared_fallback_uses_it_and_labels_it() -> None:
    client, providers, log = build(fallbacks=True)
    client.call(req("court_2", "a"))
    client.call(req("court_2", "b"))
    client.call(req("court_2", "c"))
    assert providers["baseten"].calls == 2
    assert providers["modal"].calls == 1
    last = log.records()[-1]
    assert last.status == "ok"
    assert last.provider == "modal"
    assert last.model_id == "modal-open"
    assert last.fallback_label == "fallback:baseten->modal:budget"


def test_fallbacks_disabled_means_the_call_fails() -> None:
    client, providers, _ = build(fallbacks=False)
    client.call(req("court_2", "a"))
    client.call(req("court_2", "b"))
    with pytest.raises(BudgetExceededError):
        client.call(req("court_2", "c"))
    assert providers["modal"].calls == 0


def test_provider_outage_uses_declared_fallback_only_when_enabled() -> None:
    client, providers, log = build(failing=("baseten",), fallbacks=True)
    client.call(req("advisor"))
    assert providers["modal"].calls == 1
    assert log.records()[-1].fallback_label == "fallback:baseten->modal:error"
    client2, providers2, _ = build(failing=("baseten",), fallbacks=False)
    with pytest.raises(ProviderError):
        client2.call(req("advisor"))
    assert providers2["modal"].calls == 0


def test_fallback_also_failing_raises() -> None:
    client, _, _ = build(failing=("modal", "vertex"), fallbacks=True)
    with pytest.raises(ProviderError):
        client.call(req("court_3"))


def test_unknown_role_fails_closed_without_any_call() -> None:
    client, providers, _ = build()
    with pytest.raises(UnknownRoleError):
        client.call(req("root_admin"))
    assert all(p.calls == 0 for p in providers.values())


def test_repeated_request_id_returns_cached_result_without_cost() -> None:
    client, providers, log = build()
    first = client.call(req("director", "same"))
    second = client.call(req("director", "same"))
    assert first == second
    assert providers["meta"].calls == 1
    assert log.records()[-1].status == "cached"
    assert log.records()[-1].cost_usd == 0.0


def test_task_call_cap_raises_typed_error() -> None:
    client, providers, _ = build(task_caps=TaskCaps(max_calls=2, max_cost_usd=10.0), cost=0.01)
    client.call(req("director", "a", task_id="t1"))
    client.call(req("director", "b", task_id="t1"))
    with pytest.raises(TaskCapExceededError):
        client.call(req("director", "c", task_id="t1"))
    assert providers["meta"].calls == 2
    client.call(req("director", "d", task_id="t2"))


def test_task_cost_cap_raises_typed_error() -> None:
    client, providers, _ = build(task_caps=TaskCaps(max_calls=10, max_cost_usd=0.5), cost=0.3)
    client.call(req("director", "a", task_id="t1"))
    with pytest.raises(TaskCapExceededError):
        client.call(req("director", "b", task_id="t1"))
    assert providers["meta"].calls == 1
