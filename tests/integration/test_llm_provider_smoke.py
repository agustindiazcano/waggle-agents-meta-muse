"""One cloud-only smoke test per route. Never run locally (AGENTS.md section 3).

Each test makes one call of about one cent. It fails, and does not skip, when the mode,
key, cap, model id or verified price is missing.
"""

import os

import pytest
from llm_smoke_support import SMOKE_COST_LIMIT_USD, SMOKE_PROMPT, smoke_provider

from waggle.llm.models import LlmRequest


@pytest.mark.llm
@pytest.mark.parametrize("route", ["meta", "baseten", "modal"])
def test_route_answers_one_cheap_call(route: str) -> None:
    provider, model_id = smoke_provider(route, os.environ)
    request = LlmRequest(request_id=f"smoke-{route}", role="smoke", prompt=SMOKE_PROMPT)
    assert provider.estimate_cost(request) < SMOKE_COST_LIMIT_USD
    result = provider.complete(request, model_id)
    assert result.text.strip()
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert 0 < result.cost_usd < SMOKE_COST_LIMIT_USD


@pytest.mark.llm
def test_meta_wonder_answers_one_cheap_call() -> None:
    provider, _ = smoke_provider("meta", os.environ)
    wonder_id = os.environ.get("META_WONDER_MODEL_ID", "").strip()
    assert wonder_id, "META_WONDER_MODEL_ID is not set"
    request = LlmRequest(request_id="smoke-meta-wonder", role="planner", prompt=SMOKE_PROMPT)
    assert provider.estimate_cost(request) < SMOKE_COST_LIMIT_USD
    result = provider.complete(request, wonder_id)
    assert result.text.strip()
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert 0 < result.cost_usd < SMOKE_COST_LIMIT_USD
