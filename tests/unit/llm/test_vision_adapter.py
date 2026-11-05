"""Label reading through the vision role: a result or a typed error, never an exception."""

import base64

import pytest
from llm_support import build

from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.errors import ProviderError
from waggle.llm.models import Attachment
from waggle.llm.providers import MockProvider, ScriptedProvider
from waggle.llm.vision_adapter import VISION_PROMPT_VERSION, read_label

_RAW = '{"label_text":"PKG-7","obstruction_class":"none","legibility":0.9}'


def _image(media_type: str = "image/png") -> Attachment:
    return Attachment("image", media_type, base64.b64encode(b"PNGDATA").decode("ascii"))


def _audio() -> Attachment:
    return Attachment("audio", "audio/wav", base64.b64encode(b"RIFF....").decode("ascii"))


def _client(
    entry: str | ProviderError | tuple[str | ProviderError, ...],
) -> tuple[LlmClient, ScriptedProvider, InMemoryCallLog]:
    provider = ScriptedProvider("meta", by_role={"vision": entry})
    client, _, log = build(providers={"meta": provider})
    return client, provider, log


def test_prompt_version_is_vision_v1() -> None:
    assert VISION_PROMPT_VERSION == "vision-v1"


def test_an_image_is_sent_to_the_vision_role_and_the_raw_text_comes_back() -> None:
    client, provider, log = _client(_RAW)
    result = read_label(client, _image(), "req-1", task_id="task-1")
    assert (result.text, result.error) == (_RAW, None)
    assert provider.calls_by_role == {"vision": 1}
    assert provider.attachments_seen == 1
    record = log.records()[-1]
    assert (record.role, record.task_id, record.status) == ("vision", "task-1", "ok")


def test_the_text_is_stripped() -> None:
    client, _, _ = _client(f"  {_RAW} \n")
    assert read_label(client, _image(), "req-1").text == _RAW


def test_an_empty_reply_is_an_error_not_an_empty_result() -> None:
    client, _, _ = _client("   ")
    result = read_label(client, _image(), "req-1")
    assert (result.text, result.error) == (None, "empty")


def test_a_provider_error_is_returned_as_an_error_result() -> None:
    client, _, _ = _client(ProviderError("down"))
    result = read_label(client, _image(), "req-1")
    assert (result.text, result.error) == (None, "provider_error")


def test_a_call_that_would_pass_the_cap_is_no_budget_and_makes_no_call() -> None:
    mock = MockProvider("meta", cost_usd=0.5, media_cost_usd=0.6)
    client, providers, log = build(providers={"meta": mock})
    result = read_label(client, _image(), "req-1")
    assert (result.text, result.error) == (None, "no_budget")
    assert providers["meta"].calls == 0
    assert log.records()[-1].status == "denied"


def test_a_non_image_attachment_is_a_bad_request_and_makes_no_call() -> None:
    client, provider, _ = _client(_RAW)
    result = read_label(client, _audio(), "req-1")
    assert (result.text, result.error) == (None, "bad_request")
    assert provider.calls == 0


@pytest.mark.parametrize("request_id", ["", "  "])
def test_a_blank_request_id_is_a_bad_request_and_makes_no_call(request_id: str) -> None:
    client, provider, _ = _client(_RAW)
    result = read_label(client, _image(), request_id)
    assert (result.text, result.error) == (None, "bad_request")
    assert provider.calls == 0


def test_a_repeat_of_the_request_id_returns_the_cached_text_without_a_second_call() -> None:
    client, provider, log = _client((_RAW, "second"))
    assert read_label(client, _image(), "req-1").text == _RAW
    assert read_label(client, _image(), "req-1").text == _RAW
    assert provider.calls == 1
    assert log.records()[-1].status == "cached"
