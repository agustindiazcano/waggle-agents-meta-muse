"""ScriptedProvider: configured text per request id and per role, errors, call counts."""

import pytest
from llm_support import req

from waggle.llm.errors import ProviderError
from waggle.llm.providers import ScriptedProvider, ScriptMissingError


def test_returns_the_text_scripted_for_the_role() -> None:
    provider = ScriptedProvider("meta", by_role={"court_1": "A"})
    result = provider.complete(req("court_1"), "m-1")
    assert result.text == "A"
    assert result.model_id == "m-1"
    assert provider.calls == 1
    assert provider.calls_by_role == {"court_1": 1}


def test_a_request_id_entry_wins_over_the_role_entry() -> None:
    provider = ScriptedProvider("meta", by_role={"court_1": "A"}, by_request={"x": "B"})
    assert provider.complete(req("court_1", "x"), "m").text == "B"
    assert provider.complete(req("court_1", "y"), "m").text == "A"
    assert provider.request_ids == ["x", "y"]


def test_a_scripted_error_is_raised_and_still_counted() -> None:
    provider = ScriptedProvider("meta", by_role={"court_1": ProviderError("down")})
    with pytest.raises(ProviderError, match="down"):
        provider.complete(req("court_1"), "m")
    assert provider.calls == 1


def test_a_tuple_is_consumed_in_order_and_running_out_is_a_real_error() -> None:
    provider = ScriptedProvider("meta", by_role={"r": (ProviderError("once"), "then ok")})
    with pytest.raises(ProviderError):
        provider.complete(req("r"), "m")
    assert provider.complete(req("r"), "m").text == "then ok"
    with pytest.raises(ScriptMissingError):
        provider.complete(req("r"), "m")


def test_a_role_without_a_script_is_a_real_error_not_a_provider_error() -> None:
    provider = ScriptedProvider("meta", by_role={})
    with pytest.raises(ScriptMissingError) as info:
        provider.complete(req("court_9"), "m")
    assert not isinstance(info.value, ProviderError)
    assert provider.calls == 0


def test_cost_is_fixed_and_the_estimate_matches() -> None:
    provider = ScriptedProvider("meta", by_role={"r": "t"}, cost_usd=0.05)
    assert provider.estimate_cost(req("r")) == 0.05
    assert provider.complete(req("r"), "m").cost_usd == 0.05
