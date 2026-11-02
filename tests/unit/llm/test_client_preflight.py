"""LlmClient.preflight: one all-or-nothing budget check for several requests, no call made."""

import pytest
from llm_support import build, req

from waggle.llm.errors import BudgetExceededError, InvalidCapError, UnknownRoleError


def test_requests_that_fit_pass_and_nothing_is_called_or_logged() -> None:
    client, providers, log = build(cost=0.3)
    client.preflight([req("court_1", "a"), req("court_2", "b"), req("court_3", "c")])
    assert all(p.calls == 0 for p in providers.values())
    assert log.records() == []


def test_one_provider_over_cap_denies_the_whole_set() -> None:
    client, providers, _ = build(cost=0.4)
    client.call(req("court_2", "spent"))
    client.call(req("court_2", "spent2"))
    with pytest.raises(BudgetExceededError):
        client.preflight([req("court_1", "a"), req("court_2", "b")])
    assert providers["meta"].calls == 0


def test_estimates_add_up_per_provider() -> None:
    client, _, _ = build(cost=0.4)
    with pytest.raises(BudgetExceededError):
        client.preflight([req("director", "a"), req("planner", "b"), req("diagnosis", "c")])


def test_a_missing_cap_and_an_unknown_role_fail_closed() -> None:
    client, _, _ = build(caps={})
    with pytest.raises(InvalidCapError):
        client.preflight([req("court_1")])
    client2, _, _ = build()
    with pytest.raises(UnknownRoleError):
        client2.preflight([req("root_admin")])


def test_an_already_cached_request_costs_nothing() -> None:
    client, _, _ = build(cost=0.6)
    client.call(req("court_1", "same"))
    client.preflight([req("court_1", "same")])
