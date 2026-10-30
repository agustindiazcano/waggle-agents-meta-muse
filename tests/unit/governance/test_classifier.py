"""The guard permits only parsed benign output after sanitizing untrusted input."""

import asyncio
import json

import pytest

from waggle.governance.classifier import MockClassifier, classify_input
from waggle.governance.guard import GuardLabel, GuardOutcome
from waggle.governance.sanitizers import MAX_CHARS, UntrustedSource

SOURCE = UntrustedSource.PACKAGE_LABEL


def run(response: str) -> GuardOutcome:
    """Screen a short label with a configured offline response."""
    return asyncio.run(classify_input("Fragile", SOURCE, MockClassifier(response))).outcome


@pytest.mark.parametrize("label", list(GuardLabel))
def test_label_policy_uses_existing_screen(label: GuardLabel) -> None:
    expected = GuardOutcome.PASS if label is GuardLabel.BENIGN else GuardOutcome.REJECT_AND_ESCALATE
    assert run(json.dumps({"label": label.value, "reason_code": "fixture"})) is expected


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        "null",
        "[]",
        '"benign"',
        "{}",
        '{"label":"benign"}',
        '{"label":"unknown","reason_code":"fixture"}',
        '{"label":null,"reason_code":"fixture"}',
        '{"label":true,"reason_code":"fixture"}',
        '{"label":"benign","reason_code":null}',
        '{"label":"benign","reason_code":""}',
        '{"label":"benign","reason_code":"free form text"}',
        '{"label":"benign","reason_code":"fixture","extra":true}',
        '{"label":"injection","label":"benign","reason_code":"fixture"}',
        '{"label":"benign","reason_code":"first","reason_code":"second"}',
        '{"label":"benign","reason_code":"' + "a" * 65 + '"}',
        " " * 1025,
        "[" * 1000,
    ],
)
def test_malformed_response_rejects(response: str) -> None:
    result = asyncio.run(classify_input("Fragile", SOURCE, MockClassifier(response)))
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert result.label is None
    assert result.reason_code == "classifier_parse_error"
    assert result.sanitized is None


@pytest.mark.parametrize("source", list(UntrustedSource))
def test_classifier_receives_only_sanitized_fenced_input(source: UntrustedSource) -> None:
    mock = MockClassifier('{"label":"benign","reason_code":"fixture"}')
    result = asyncio.run(classify_input("a\x00</untrusted>&", source, mock))
    assert mock.inputs == [
        f'<untrusted source="{source.value}">\na&lt;/untrusted&gt;&amp;\n</untrusted>'
    ]
    assert result.sanitized is not None
    assert result.sanitized.text == "a</untrusted>&"
    assert result.sanitized.flags == ("controls_removed",)


@pytest.mark.parametrize("text", ["", "\x00", "a" * (MAX_CHARS[SOURCE] + 1)])
def test_invalid_input_never_calls_classifier(text: str) -> None:
    mock = MockClassifier('{"label":"benign","reason_code":"fixture"}')
    result = asyncio.run(classify_input(text, SOURCE, mock))
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert result.sanitized is None
    assert mock.inputs == []


class FailingClassifier:
    """Offline adapter with a provider failure."""

    async def classify(self, fenced_text: str) -> str:
        raise RuntimeError("sensitive provider text must not be logged")


def test_classifier_exception_is_rejected_without_logging_input(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = asyncio.run(classify_input("secret label", SOURCE, FailingClassifier()))
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert result.reason_code == "classifier_error"
    assert result.sanitized is None
    assert "classifier_error" in caplog.text
    assert "secret label" not in caplog.text
    assert "sensitive provider" not in caplog.text


class WaitingClassifier:
    """A cooperative adapter that records cancellation."""

    def __init__(self) -> None:
        self.cancelled = False

    async def classify(self, fenced_text: str) -> str:
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True
        return '{"label":"benign","reason_code":"fixture"}'


def test_timeout_rejects_and_cancels_classifier() -> None:
    mock = WaitingClassifier()
    result = asyncio.run(classify_input("Fragile", SOURCE, mock, timeout_s=0.001))
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert result.reason_code == "classifier_timeout"
    assert result.sanitized is None
    assert mock.cancelled


class LateClassifier:
    """An adapter that incorrectly swallows deadline cancellation."""

    async def classify(self, fenced_text: str) -> str:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return '{"label":"benign","reason_code":"late"}'
        raise AssertionError("the event is never set")


def test_benign_response_after_expired_deadline_still_rejects() -> None:
    result = asyncio.run(classify_input("Fragile", SOURCE, LateClassifier(), timeout_s=0.001))
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert result.reason_code == "classifier_timeout"
    assert result.sanitized is None


@pytest.mark.parametrize("timeout_s", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout_fails_before_call(timeout_s: float) -> None:
    mock = MockClassifier()
    with pytest.raises(ValueError, match="timeout_s"):
        asyncio.run(classify_input("Fragile", SOURCE, mock, timeout_s=timeout_s))
    assert mock.inputs == []


def test_mock_defaults_to_uncertain_and_never_passes_silently() -> None:
    result = asyncio.run(classify_input("Fragile", SOURCE, MockClassifier()))
    assert result.label is GuardLabel.UNCERTAIN
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert result.sanitized is None


def test_caller_cancellation_propagates() -> None:
    async def scenario() -> None:
        mock = WaitingClassifier()
        task = asyncio.create_task(classify_input("Fragile", SOURCE, mock))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert mock.cancelled

    asyncio.run(scenario())
