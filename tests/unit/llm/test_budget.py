import logging

import pytest

from waggle.llm.budget import PROVIDERS, BudgetGuard, cap_env_name, parse_cap
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.errors import BudgetExceededError, InvalidCapError
from waggle.llm.models import CallRecord


def _ok(provider: str, cost: float) -> CallRecord:
    return CallRecord(
        request_id="r",
        task_id=None,
        role="director",
        provider=provider,
        model_id="m",
        status="ok",
        tokens_in=1,
        tokens_out=1,
        latency_s=0.0,
        cost_usd=cost,
    )


@pytest.mark.parametrize("provider", PROVIDERS)
def test_cap_env_name(provider: str) -> None:
    assert cap_env_name(provider) == f"{provider.upper()}_SPEND_CAP_USD"


def test_provider_names_are_the_four_declared() -> None:
    assert set(PROVIDERS) == {"meta", "baseten", "modal", "vertex"}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_valid_cap_is_read_from_env(provider: str) -> None:
    assert parse_cap(provider, {cap_env_name(provider): "12.5"}) == 12.5


@pytest.mark.parametrize("raw", [None, "", "  ", "abc", "-1", "nan", "inf", "-inf"])
def test_missing_or_invalid_cap_fails_closed(raw: str | None) -> None:
    environ = {} if raw is None else {"META_SPEND_CAP_USD": raw}
    with pytest.raises(InvalidCapError):
        parse_cap("meta", environ)


def test_unknown_provider_name_is_rejected() -> None:
    with pytest.raises(InvalidCapError):
        parse_cap("openai", {"OPENAI_SPEND_CAP_USD": "5"})


@pytest.mark.parametrize("provider", PROVIDERS)
def test_call_within_cap_is_allowed_and_over_cap_is_denied(
    provider: str, caplog: pytest.LogCaptureFixture
) -> None:
    log = InMemoryCallLog()
    guard = BudgetGuard({cap_env_name(provider): "1.0"}, log)
    guard.check(provider, 0.4, request_id="a", role="director")
    log.record(_ok(provider, 0.4))
    guard.check(provider, 0.4, request_id="b", role="director")
    log.record(_ok(provider, 0.4))
    with (
        caplog.at_level(logging.WARNING, logger="waggle.llm"),
        pytest.raises(BudgetExceededError) as info,
    ):
        guard.check(provider, 0.4, request_id="c", role="director")
    assert info.value.provider == provider
    denied = [r for r in log.records() if r.status == "denied"]
    assert len(denied) == 1
    assert denied[0].request_id == "c"
    assert any("denied" in rec.message for rec in caplog.records)


def test_exact_cap_is_allowed() -> None:
    log = InMemoryCallLog()
    guard = BudgetGuard({"META_SPEND_CAP_USD": "1.0"}, log)
    guard.check("meta", 1.0, request_id="a", role="director")


def test_missing_cap_blocks_the_call() -> None:
    guard = BudgetGuard({}, InMemoryCallLog())
    with pytest.raises(InvalidCapError):
        guard.check("meta", 0.0, request_id="a", role="director")


def test_spent_counts_only_successful_calls() -> None:
    log = InMemoryCallLog()
    guard = BudgetGuard({"META_SPEND_CAP_USD": "10"}, log)
    log.record(_ok("meta", 2.0))
    log.record(_ok("baseten", 5.0))
    assert guard.spent("meta") == 2.0
    assert guard.remaining("meta") == 8.0
