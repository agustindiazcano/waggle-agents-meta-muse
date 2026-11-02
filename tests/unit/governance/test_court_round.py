"""Court round: pre-checks, concurrent round, post-checks, round record and failure paths."""

import threading
from collections.abc import Mapping, Sequence

import pytest
from llm_support import CAPS, build

from waggle.governance.court import Decision, Verdict
from waggle.governance.court_contract import ReviewRequest
from waggle.governance.court_round import (
    InMemoryRoundStore,
    PreCheckFailure,
    RoundRecord,
    RoundResult,
    check_composition,
    run_round,
)
from waggle.governance.sanitizers import UntrustedSource, sanitize
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.court_adapter import COURT_PROMPT_HASH, CourtReviewer
from waggle.llm.errors import ProviderError
from waggle.llm.providers import Entry, ScriptedProvider

ROLES = ("court_1", "court_2", "court_3")
APPROVE = '{"verdict":"approve","reason_codes":["no_issue"]}'
REJECT = '{"verdict":"reject","reason_codes":["sop_violation"]}'
UNCERTAIN = '{"verdict":"uncertain","reason_codes":["insufficient_information"]}'
DEADLINE = 5.0


def _review(excerpt: str = "Pick slowly near Z1.") -> ReviewRequest:
    return ReviewRequest(
        task="move ITEM-17 to DOCK",
        item_resolution="ITEM-17 unique, in stock",
        world_summary="Z1 occupied",
        excerpts=(sanitize(excerpt, UntrustedSource.SOP_TEXT),),
    )


def _providers(
    court_1: Entry = APPROVE, court_2: Entry = APPROVE, court_3: Entry = APPROVE
) -> dict[str, ScriptedProvider]:
    return {
        "meta": ScriptedProvider("meta", by_role={"court_1": court_1}),
        "baseten": ScriptedProvider("baseten", by_role={"court_2": court_2}),
        "modal": ScriptedProvider("modal", by_role={"court_3": court_3}),
    }


def _round(
    providers: Mapping[str, ScriptedProvider],
    *,
    fallbacks: bool = False,
    held_out: bool = False,
    caps: dict[str, str] | None = None,
    store: InMemoryRoundStore | None = None,
    pre_checks: Sequence[object] = (),
    review: ReviewRequest | None = None,
    deadline_s: float = DEADLINE,
) -> tuple[RoundResult, InMemoryRoundStore, InMemoryCallLog]:
    client, _, log = build(providers=providers, fallbacks=fallbacks, caps=caps or CAPS)
    store = store or InMemoryRoundStore()
    result = run_round(
        review or _review(),
        CourtReviewer(client),
        ROLES,
        store=store,
        call_log=log,
        task_id="t1",
        held_out=held_out,
        deadline_s=deadline_s,
        pre_checks=pre_checks,  # type: ignore[arg-type]
    )
    return result, store, log


def _total(providers: Mapping[str, ScriptedProvider]) -> int:
    return sum(p.calls for p in providers.values())


def test_unanimous_approval_executes_and_the_record_is_written_first() -> None:
    providers = _providers()
    result, store, _ = _round(providers)
    assert result.action == "execute"
    assert result.record.decision is Decision.EXECUTE
    assert [m.role for m in result.record.members] == list(ROLES)
    assert all(
        m.vote is not None and m.vote.verdict is Verdict.APPROVE for m in result.record.members
    )
    assert store.records == [result.record]
    assert result.record.prompt_hash == COURT_PROMPT_HASH
    assert result.record.prompt_version == "court-v1"
    assert result.record.review_digest == _review().digest()
    assert {m.model_id for m in result.record.members} == {
        "meta-text",
        "baseten-open",
        "modal-glimmer",
    }
    assert _total(providers) == 3


def test_one_reject_escalates_and_keeps_the_reason_codes() -> None:
    result, _, _ = _round(_providers(court_2=REJECT))
    assert result.action == "escalate"
    vote = result.record.members[1].vote
    assert vote is not None and vote.reason_codes == ("sop_violation",)


@pytest.mark.parametrize("failing", ["meta", "baseten", "modal"])
def test_a_provider_error_for_each_provider_in_turn_escalates(failing: str) -> None:
    providers = _providers()
    providers[failing] = ScriptedProvider(
        failing, by_role={r: ProviderError("down") for r in ROLES}
    )
    result, _, _ = _round(providers)
    assert result.action == "escalate"
    causes = [m.cause for m in result.record.members]
    assert causes.count("provider_error") == 1
    assert sum(m.vote is None for m in result.record.members) == 1


def test_an_invalid_answer_is_a_parse_failure_and_escalates() -> None:
    result, _, _ = _round(_providers(court_3=UNCERTAIN))
    assert result.action == "escalate"
    assert result.record.members[2].vote is None
    assert result.record.members[2].cause == "parse_error"


def test_budget_denied_for_one_role_means_no_provider_call_at_all() -> None:
    providers = _providers()
    caps = {
        "META_SPEND_CAP_USD": "1.0",
        "BASETEN_SPEND_CAP_USD": "1.0",
        "MODAL_SPEND_CAP_USD": "0.0",
        "VERTEX_SPEND_CAP_USD": "1.0",
    }
    result, store, _ = _round(providers, caps=caps)
    assert result.action == "escalate"
    assert result.record.reason == "budget"
    assert result.record.members == ()
    assert _total(providers) == 0
    assert store.records == [result.record]


def test_a_missing_cap_fails_closed_before_any_call() -> None:
    providers = _providers()
    caps = {"META_SPEND_CAP_USD": "1.0"}
    result, _, _ = _round(providers, caps=caps)
    assert result.action == "escalate"
    assert result.record.reason == "budget"
    assert _total(providers) == 0


def test_a_failed_pre_check_makes_zero_calls_and_denies_or_escalates() -> None:
    providers = _providers()
    result, store, _ = _round(
        providers, pre_checks=[lambda: PreCheckFailure("deny", "item_out_of_stock")]
    )
    assert result.action == "deny"
    assert result.record.reason == "item_out_of_stock"
    assert _total(providers) == 0
    assert store.records == [result.record]
    result2, _, _ = _round(
        providers,
        pre_checks=[lambda: None, lambda: PreCheckFailure("escalate", "excerpt_not_screened")],
    )
    assert result2.action == "escalate"
    assert _total(providers) == 0


def test_passing_pre_checks_let_the_round_run() -> None:
    result, _, _ = _round(_providers(), pre_checks=[lambda: None])
    assert result.action == "execute"


def test_the_same_request_twice_is_one_provider_call_per_reviewer() -> None:
    providers = _providers()
    client, _, log = build(providers=providers)
    reviewer = CourtReviewer(client)
    for _ in range(2):
        run_round(
            _review(),
            reviewer,
            ROLES,
            store=InMemoryRoundStore(),
            call_log=log,
            task_id="t1",
            held_out=False,
            deadline_s=DEADLINE,
        )
    assert _total(providers) == 3
    assert [r.status for r in log.records()][-3:] == ["cached"] * 3


def test_a_reject_is_never_retried_even_if_the_script_would_approve_next() -> None:
    providers = _providers(court_2=(REJECT, APPROVE))
    result, _, _ = _round(providers)
    assert result.action == "escalate"
    assert providers["baseten"].calls == 1


def test_an_invalid_answer_is_never_asked_again() -> None:
    providers = _providers(court_3=(UNCERTAIN, APPROVE))
    result, _, _ = _round(providers)
    assert result.action == "escalate"
    assert providers["modal"].calls == 1


def test_a_fallback_in_a_held_out_round_is_a_failure_not_a_vote() -> None:
    providers = _providers(court_2=ProviderError("down"))
    providers["modal"] = ScriptedProvider("modal", by_role={"court_3": APPROVE, "court_2": APPROVE})
    result, _, _ = _round(providers, fallbacks=True, held_out=True)
    assert result.action == "escalate"
    member = result.record.members[1]
    assert member.vote is None
    assert member.cause == "fallback_in_held_out"
    assert member.fallback_label == "fallback:baseten->modal:error"


def test_a_fallback_outside_held_out_counts_and_is_labeled() -> None:
    providers = _providers(court_2=ProviderError("down"))
    providers["modal"] = ScriptedProvider("modal", by_role={"court_3": APPROVE, "court_2": APPROVE})
    result, _, _ = _round(providers, fallbacks=True, held_out=False)
    assert result.action == "execute"
    assert result.record.members[1].fallback_label == "fallback:baseten->modal:error"
    assert result.record.members[0].fallback_label is None


def test_a_record_write_failure_escalates_instead_of_executing() -> None:
    class Broken:
        def write(self, record: RoundRecord) -> None:
            raise OSError("disk full")

    client, _, log = build(providers=_providers())
    result = run_round(
        _review(),
        CourtReviewer(client),
        ROLES,
        store=Broken(),
        call_log=log,
        task_id="t1",
        held_out=False,
        deadline_s=DEADLINE,
    )
    assert result.action == "escalate"
    assert result.record.reason == "record_write_failed"


def test_a_late_answer_is_discarded_at_the_round_deadline() -> None:
    release = threading.Event()

    class Slow(ScriptedProvider):
        def complete(self, request, model_id):  # type: ignore[no-untyped-def]
            release.wait(5.0)
            return super().complete(request, model_id)

    providers = _providers()
    providers["baseten"] = Slow("baseten", by_role={"court_2": APPROVE})
    try:
        result, _, _ = _round(providers, deadline_s=0.2)
    finally:
        release.set()
    assert result.action == "escalate"
    assert result.record.members[1].vote is None
    assert result.record.members[1].cause == "timeout"


def test_members_run_concurrently() -> None:
    barrier = threading.Barrier(3, timeout=3.0)

    class Meet(ScriptedProvider):
        def complete(self, request, model_id):  # type: ignore[no-untyped-def]
            barrier.wait()
            return super().complete(request, model_id)

    providers = {
        "meta": Meet("meta", by_role={"court_1": APPROVE}),
        "baseten": Meet("baseten", by_role={"court_2": APPROVE}),
        "modal": Meet("modal", by_role={"court_3": APPROVE}),
    }
    result, _, _ = _round(providers)
    assert result.action == "execute"


def test_an_unexpected_exception_never_yields_execute() -> None:
    providers = _providers()
    providers["meta"] = ScriptedProvider("meta", by_role={})
    with pytest.raises(Exception, match="no script"):
        _round(providers)


def test_composition_checks_catch_duplicates_and_wrong_counts() -> None:
    from waggle.governance.court_round import MemberResult

    def member(role: str, rid: str) -> MemberResult:
        return MemberResult(role, rid, None, None, "", None)

    ok = [member("court_1", "a"), member("court_2", "b"), member("court_3", "c")]
    assert check_composition(ok, ROLES) is None
    assert check_composition(ok[:2], ROLES) == "composition"
    dup_id = [member("court_1", "a"), member("court_2", "a"), member("court_3", "c")]
    assert check_composition(dup_id, ROLES) == "composition"
    dup_role = [member("court_1", "a"), member("court_1", "b"), member("court_3", "c")]
    assert check_composition(dup_role, ROLES) == "composition"
    assert check_composition([], ()) == "composition"
    assert check_composition(ok, ("court_1", "court_1", "court_3")) == "composition"


def test_a_forged_duplicate_request_id_escalates_a_unanimous_round() -> None:
    class Forging(CourtReviewer):
        def request_id(self, role, review, repeat=None):  # type: ignore[no-untyped-def]
            return "same-id"

    client, _, log = build(providers=_providers())
    result = run_round(
        _review(),
        Forging(client),
        ROLES,
        store=InMemoryRoundStore(),
        call_log=log,
        task_id="t1",
        held_out=False,
        deadline_s=DEADLINE,
    )
    assert result.action == "escalate"
    assert result.record.reason == "composition"


def test_an_empty_or_repeated_composition_escalates_without_calls() -> None:
    providers = _providers()
    client, _, log = build(providers=providers)
    for roles in ((), ("court_1", "court_1")):
        result = run_round(
            _review(),
            CourtReviewer(client),
            roles,
            store=InMemoryRoundStore(),
            call_log=log,
            task_id="t1",
            held_out=False,
            deadline_s=DEADLINE,
        )
        assert result.action == "escalate"
        assert result.record.reason == "composition"
    assert _total(providers) == 0


def test_a_single_reviewer_configuration_uses_the_same_function() -> None:
    providers = _providers()
    client, _, log = build(providers=providers)
    result = run_round(
        _review(),
        CourtReviewer(client),
        ("court_1",),
        store=InMemoryRoundStore(),
        call_log=log,
        task_id="t1",
        held_out=False,
        deadline_s=DEADLINE,
    )
    assert result.action == "execute"
    assert _total(providers) == 1


def test_an_invalid_deadline_is_refused() -> None:
    client, _, log = build(providers=_providers())
    with pytest.raises(ValueError):
        run_round(
            _review(),
            CourtReviewer(client),
            ROLES,
            store=InMemoryRoundStore(),
            call_log=log,
            task_id="t1",
            held_out=False,
            deadline_s=0.0,
        )
