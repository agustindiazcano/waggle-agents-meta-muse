"""Transcription through the voice role: a result or a typed error, never an exception."""

import base64

import pytest
from llm_support import build

from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.errors import ProviderError
from waggle.llm.models import Attachment
from waggle.llm.providers import MockProvider, ScriptedProvider
from waggle.llm.voice_adapter import transcribe


def _clip(media_type: str = "audio/wav") -> Attachment:
    return Attachment("audio", media_type, base64.b64encode(b"RIFF....").decode("ascii"))


def _client(
    entry: str | ProviderError | tuple[str | ProviderError, ...],
) -> tuple[LlmClient, ScriptedProvider, InMemoryCallLog]:
    provider = ScriptedProvider("meta", by_role={"voice": entry})
    client, _, log = build(providers={"meta": provider})
    return client, provider, log


def test_a_clip_is_sent_to_the_voice_role_and_the_text_comes_back() -> None:
    client, provider, log = _client("pick item seven")
    result = transcribe(client, _clip(), "req-1", task_id="task-1")
    assert (result.text, result.error) == ("pick item seven", None)
    assert provider.calls_by_role == {"voice": 1}
    assert provider.attachments_seen == 1
    record = log.records()[-1]
    assert (record.role, record.task_id, record.status) == ("voice", "task-1", "ok")


def test_the_text_is_stripped() -> None:
    client, _, _ = _client("  pick item 7 \n")
    assert transcribe(client, _clip(), "req-1").text == "pick item 7"


def test_an_empty_transcript_is_an_error_not_an_empty_result() -> None:
    client, _, _ = _client("   ")
    result = transcribe(client, _clip(), "req-1")
    assert (result.text, result.error) == (None, "empty")


def test_a_provider_error_is_returned_as_an_error_result() -> None:
    client, _, _ = _client(ProviderError("down"))
    result = transcribe(client, _clip(), "req-1")
    assert (result.text, result.error) == (None, "provider_error")


def test_a_call_that_would_pass_the_cap_is_returned_as_no_budget_and_makes_no_call() -> None:
    mock = MockProvider("meta", cost_usd=0.5, media_cost_usd=0.6)
    client, providers, log = build(providers={"meta": mock})
    result = transcribe(client, _clip(), "req-1")
    assert (result.text, result.error) == (None, "no_budget")
    assert providers["meta"].calls == 0
    assert log.records()[-1].status == "denied"


def test_a_repeat_of_the_request_id_returns_the_cached_text_without_a_second_call() -> None:
    client, provider, log = _client(("first", "second"))
    assert transcribe(client, _clip(), "req-1").text == "first"
    assert transcribe(client, _clip(), "req-1").text == "first"
    assert provider.calls == 1
    assert log.records()[-1].status == "cached"


@pytest.mark.parametrize("request_id", ["", "  "])
def test_an_empty_request_id_is_an_error_result(request_id: str) -> None:
    client, provider, _ = _client("x")
    result = transcribe(client, _clip(), request_id)
    assert (result.text, result.error) == (None, "bad_request")
    assert provider.calls == 0
