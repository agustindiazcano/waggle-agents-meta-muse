"""Shared builders for llm tests: a client wired with mock providers."""

from collections.abc import Mapping

from waggle.llm.budget import PROVIDERS, BudgetGuard
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.models import LlmRequest
from waggle.llm.providers import MockProvider
from waggle.llm.routing import load_routes
from waggle.llm.task_caps import TaskCaps

MODEL_ENV = {
    "META_MODEL_ID": "meta-text",
    "META_VOICE_MODEL_ID": "meta-voice",
    "BASETEN_MODEL_ID": "baseten-open",
    "MODAL_GLIMMER_MODEL_ID": "modal-glimmer",
    "MODAL_SPARK_OPEN_MODEL_ID": "modal-open",
    "VERTEX_MODEL_ID": "vertex-model",
}
CAPS = {f"{p.upper()}_SPEND_CAP_USD": "1.0" for p in PROVIDERS}


def build(
    *,
    caps: Mapping[str, str] = CAPS,
    cost: float = 0.4,
    failing: tuple[str, ...] = (),
    fallbacks: bool = False,
    task_caps: TaskCaps | None = None,
) -> tuple[LlmClient, dict[str, MockProvider], InMemoryCallLog]:
    """Return a client, its mock providers and the in-memory call log."""
    log = InMemoryCallLog()
    providers = {p: MockProvider(p, cost_usd=cost, fail=p in failing) for p in PROVIDERS}
    client = LlmClient(
        providers=providers,
        table=load_routes(),
        guard=BudgetGuard(caps, log),
        log=log,
        environ=MODEL_ENV,
        fallbacks_enabled=fallbacks,
        task_caps=task_caps,
    )
    return client, providers, log


def req(role: str, rid: str = "r1", task_id: str | None = None) -> LlmRequest:
    """Build a request for a role."""
    return LlmRequest(request_id=rid, role=role, prompt="hello", task_id=task_id)
