"""Mock and scripted providers price attachments, and the budget guard sees that price."""

import base64

import pytest
from llm_support import build

from waggle.llm.errors import BudgetExceededError
from waggle.llm.models import Attachment, LlmRequest
from waggle.llm.providers import MockProvider, ScriptedProvider


def _audio() -> Attachment:
    return Attachment("audio", "audio/wav", base64.b64encode(b"RIFF").decode("ascii"))


def _image() -> Attachment:
    return Attachment("image", "image/png", base64.b64encode(b"PNG").decode("ascii"))


def _voice(rid: str, *attachments: Attachment) -> LlmRequest:
    return LlmRequest(rid, "voice", "transcribe", attachments=attachments)


def test_a_text_call_costs_the_base_cost_in_both_providers() -> None:
    request = LlmRequest("r", "voice", "hello")
    assert MockProvider("meta", cost_usd=0.1, media_cost_usd=0.3).estimate_cost(request) == 0.1
    scripted = ScriptedProvider("meta", by_role={"voice": "x"}, cost_usd=0.1, media_cost_usd=0.3)
    assert scripted.estimate_cost(request) == 0.1


def test_each_attachment_adds_the_media_cost_to_the_estimate() -> None:
    mock = MockProvider("meta", cost_usd=0.1, media_cost_usd=0.3)
    assert mock.estimate_cost(_voice("r", _audio())) == pytest.approx(0.4)
    assert mock.estimate_cost(_voice("r", _audio(), _image())) == pytest.approx(0.7)
    scripted = ScriptedProvider("meta", by_role={"voice": "x"}, cost_usd=0.1, media_cost_usd=0.3)
    assert scripted.estimate_cost(_voice("r", _audio())) == pytest.approx(0.4)


def test_the_completion_costs_what_was_estimated() -> None:
    mock = MockProvider("meta", cost_usd=0.1, media_cost_usd=0.3)
    assert mock.complete(_voice("r", _audio()), "m").cost_usd == pytest.approx(0.4)
    scripted = ScriptedProvider(
        "meta", by_role={"voice": "heard"}, cost_usd=0.1, media_cost_usd=0.3
    )
    result = scripted.complete(_voice("r", _audio(), _image()), "m")
    assert result.text == "heard"
    assert result.cost_usd == pytest.approx(0.7)


def test_the_providers_count_the_attachments_they_received() -> None:
    mock = MockProvider("meta")
    mock.complete(_voice("a", _audio()), "m")
    assert mock.attachments_seen == 1
    scripted = ScriptedProvider("meta", by_role={"voice": "x"})
    scripted.complete(_voice("b", _audio(), _image()), "m")
    assert scripted.attachments_seen == 2


def test_the_media_cost_defaults_to_zero_so_existing_callers_are_unchanged() -> None:
    assert MockProvider("meta", cost_usd=0.1).estimate_cost(_voice("r", _audio())) == 0.1


def test_the_budget_guard_denies_a_call_whose_attachments_pass_the_cap() -> None:
    mock = MockProvider("meta", cost_usd=0.4, media_cost_usd=0.4)
    client, providers, log = build(providers={"meta": mock})
    with pytest.raises(BudgetExceededError):
        client.call(_voice("r1", _audio(), _image()))
    assert providers["meta"].calls == 0
    assert [r.status for r in log.records()] == ["denied"]


def test_a_call_with_attachments_inside_the_cap_is_logged_with_the_media_cost() -> None:
    mock = MockProvider("meta", cost_usd=0.2, media_cost_usd=0.3)
    client, providers, log = build(providers={"meta": mock})
    result = client.call(_voice("r1", _audio()))
    assert result.cost_usd == pytest.approx(0.5)
    assert providers["meta"].calls == 1
    assert log.records()[-1].cost_usd == pytest.approx(0.5)


def test_the_cap_counts_the_media_cost_of_earlier_calls() -> None:
    mock = MockProvider("meta", cost_usd=0.1, media_cost_usd=0.4)
    client, providers, _ = build(providers={"meta": mock})
    client.call(_voice("r1", _audio()))
    client.call(_voice("r2", _audio()))
    with pytest.raises(BudgetExceededError):
        client.call(_voice("r3", _audio()))
    assert providers["meta"].calls == 2
