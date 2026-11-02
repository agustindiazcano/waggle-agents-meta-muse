"""build_client wires providers, routes, budget guard and call log from the environment."""

import pytest

from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client_factory import build_client
from waggle.llm.errors import ConfigError, InvalidCapError
from waggle.llm.models import LlmRequest
from waggle.llm.provider_config import MODE_VAR

MODEL_IDS = {
    "META_MODEL_ID": "m-meta",
    "BASETEN_MODEL_ID": "m-baseten",
    "MODAL_GLIMMER_MODEL_ID": "m-modal",
    "MODAL_SPARK_OPEN_MODEL_ID": "m-modal-open",
    "VERTEX_MODEL_ID": "m-vertex",
}
CAPS = {f"{p}_SPEND_CAP_USD": "1.0" for p in ("META", "BASETEN", "MODAL", "VERTEX")}


def _env(mode: str = "mock", **extra: str) -> dict[str, str]:
    return {MODE_VAR: mode, **MODEL_IDS, **CAPS, **extra}


def test_in_mock_mode_a_call_is_served_and_logged_without_network() -> None:
    log = InMemoryCallLog()
    client = build_client(_env(), log, fallbacks_enabled=False)
    client.call(LlmRequest("r-1", "guard", "hello", task_id="t-1"))
    rows = log.records()
    assert [(r.request_id, r.status) for r in rows] == [("r-1", "ok")]


def test_a_repeated_request_id_is_served_from_the_cache_and_labeled() -> None:
    log = InMemoryCallLog()
    client = build_client(_env(), log, fallbacks_enabled=False)
    client.call(LlmRequest("r-1", "guard", "hello"))
    client.call(LlmRequest("r-1", "guard", "hello"))
    assert [r.status for r in log.records()] == ["ok", "cached"]


def test_a_missing_cap_fails_closed_before_any_call() -> None:
    environ = _env()
    del environ["MODAL_SPEND_CAP_USD"]
    client = build_client(environ, InMemoryCallLog(), fallbacks_enabled=False)
    with pytest.raises(InvalidCapError):
        client.call(LlmRequest("r-1", "guard", "hello"))


@pytest.mark.parametrize("mode", ["", "real"])
def test_an_unset_or_unknown_mode_fails_closed(mode: str) -> None:
    with pytest.raises(ConfigError):
        build_client(_env(mode), InMemoryCallLog(), fallbacks_enabled=False)


def test_http_mode_without_keys_fails_closed_when_the_client_is_built() -> None:
    with pytest.raises(ConfigError):
        build_client(_env("http"), InMemoryCallLog(), fallbacks_enabled=False)


def test_the_client_does_not_retry_on_top_of_the_http_provider() -> None:
    client = build_client(_env(), InMemoryCallLog(), fallbacks_enabled=False)
    assert client.max_retries == 0
