"""The guard role behind the classifier contract, over scripted providers (no network)."""

import asyncio
import json

import pytest
from llm_support import build

from waggle.governance.classifier import classify_input
from waggle.governance.guard import GuardLabel, GuardOutcome
from waggle.governance.sanitizers import UntrustedSource
from waggle.llm.errors import ProviderError
from waggle.llm.guard_adapter import GUARD_PROMPT_VERSION, LlmGuardClassifier
from waggle.llm.models import Completion, LlmRequest


class ScriptedProvider:
    name = "modal"

    def __init__(self, text: str = "", error: bool = False) -> None:
        self.text = text
        self.error = error
        self.requests: list[LlmRequest] = []

    def estimate_cost(self, request: LlmRequest) -> float:
        return 0.01

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        self.requests.append(request)
        if self.error:
            raise ProviderError("modal: outage")
        return Completion(self.text, model_id, 10, 5, 0.0, 0.01)


def _classifier(provider: ScriptedProvider) -> LlmGuardClassifier:
    client, providers, _ = build()
    providers["modal"] = provider  # type: ignore[assignment]
    return LlmGuardClassifier(client)


def _verdict(label: str, code: str = "fixture") -> str:
    return json.dumps({"label": label, "reason_code": code})


def test_the_request_uses_the_guard_role_and_carries_the_fenced_text_and_version() -> None:
    provider = ScriptedProvider(_verdict("benign"))
    fenced = '<untrusted source="package_label">\nPKG-1\n</untrusted>'
    asyncio.run(_classifier(provider).classify(fenced))
    request = provider.requests[0]
    assert request.role == "guard"
    assert "PKG-1" in request.prompt
    assert GUARD_PROMPT_VERSION in request.prompt
    assert request.request_id.startswith("guard-")


def test_the_same_input_reuses_the_request_id_so_the_cache_serves_it() -> None:
    provider = ScriptedProvider(_verdict("benign"))
    classifier = _classifier(provider)
    asyncio.run(classifier.classify("same"))
    asyncio.run(classifier.classify("same"))
    asyncio.run(classifier.classify("other"))
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    ("label", "outcome"),
    [
        ("benign", GuardOutcome.PASS),
        ("injection", GuardOutcome.REJECT_AND_ESCALATE),
        ("uncertain", GuardOutcome.REJECT_AND_ESCALATE),
    ],
)
def test_end_to_end_screening_follows_the_label(label: str, outcome: GuardOutcome) -> None:
    classifier = _classifier(ScriptedProvider(_verdict(label)))
    result = asyncio.run(classify_input("PKG-17", UntrustedSource.PACKAGE_LABEL, classifier))
    assert result.outcome is outcome
    assert result.label is GuardLabel(label)


@pytest.mark.parametrize("provider", [ScriptedProvider(error=True), ScriptedProvider("not json")])
def test_an_outage_or_a_bad_response_rejects_and_escalates(provider: ScriptedProvider) -> None:
    result = asyncio.run(
        classify_input("PKG-17", UntrustedSource.PACKAGE_LABEL, _classifier(provider))
    )
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert result.sanitized is None


def test_an_exhausted_budget_rejects_without_a_model_call() -> None:
    client, providers, _ = build(caps={"MODAL_SPEND_CAP_USD": "0.001"})
    provider = ScriptedProvider(_verdict("benign"))
    providers["modal"] = provider  # type: ignore[assignment]
    result = asyncio.run(
        classify_input("PKG-17", UntrustedSource.PACKAGE_LABEL, LlmGuardClassifier(client))
    )
    assert result.outcome is GuardOutcome.REJECT_AND_ESCALATE
    assert provider.requests == []
