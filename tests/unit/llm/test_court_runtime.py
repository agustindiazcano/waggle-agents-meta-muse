"""Court composition keeps deterministic checks and a required record store."""

from llm_support import CAPS, MODEL_ENV

from waggle.governance.court_contract import ReviewRequest
from waggle.governance.court_round import InMemoryRoundStore, PreCheckFailure, RoundRecord
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.court_runtime import CourtRuntime
from waggle.llm.providers import ScriptedProvider

APPROVE = '{"verdict":"approve","reason_codes":["no_issue"]}'
REVIEW = ReviewRequest("Move ITEM-1", "ITEM-1 resolved", "Zone clear", ())


def _runtime(store: InMemoryRoundStore) -> tuple[CourtRuntime, InMemoryCallLog]:
    providers = {
        name: ScriptedProvider(name, by_role={f"court_{i}": APPROVE})
        for i, name in enumerate(("meta", "baseten", "modal"), 1)
    }
    log = InMemoryCallLog()
    runtime = CourtRuntime.from_environment(
        {"WAGGLE_LLM_PROVIDER": "mock", **CAPS, **MODEL_ENV},
        log,
        store,
        fallbacks_enabled=False,
        providers=providers,
    )
    return runtime, log


def test_three_routed_approvals_return_a_recorded_proposal() -> None:
    store = InMemoryRoundStore()
    runtime, log = _runtime(store)
    result = runtime.review(REVIEW, task_id="task-1", deadline_s=5.0)
    assert result.action == "execute"
    assert len(result.record.members) == 3
    assert {r.provider for r in log.records()} == {"meta", "baseten", "modal"}
    assert all(r.task_id == "task-1" for r in log.records())


def test_code_denial_makes_no_provider_call() -> None:
    runtime, log = _runtime(InMemoryRoundStore())
    result = runtime.review(
        REVIEW,
        task_id="task-1",
        deadline_s=5.0,
        pre_checks=(lambda: PreCheckFailure("deny", "blocked"),),
    )
    assert result.action == "deny"
    assert log.records() == []


class FailedStore(InMemoryRoundStore):
    """Persistence outage must withhold an approved proposal."""

    def write(self, record: RoundRecord) -> None:
        raise OSError("simulated record outage")


def test_record_write_failure_escalates_even_after_three_approvals() -> None:
    runtime, _ = _runtime(FailedStore())
    result = runtime.review(REVIEW, task_id="task-1", deadline_s=5.0)
    assert result.action == "escalate"
