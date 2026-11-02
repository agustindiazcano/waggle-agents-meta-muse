"""Court contract: review request, vote schema, reason vocabulary and strict parser."""

import itertools

import pytest

from waggle.governance.court import Decision, Verdict, decide
from waggle.governance.court_contract import (
    MAX_VOTE_CHARS,
    REASON_CODES,
    ReviewRequest,
    Vote,
    parse_vote,
    vote_or_none,
)
from waggle.governance.sanitizers import UntrustedSource, sanitize

APPROVE = '{"verdict": "approve", "reason_codes": ["no_issue"]}'


def _request(excerpt: str = "pick slowly near Z1") -> ReviewRequest:
    clean = sanitize(excerpt, UntrustedSource.SOP_TEXT)
    return ReviewRequest(
        task="move ITEM-17 to DOCK",
        item_resolution="ITEM-17 unique, in stock",
        world_summary="Z1 occupied",
        excerpts=(clean,),
    )


def test_a_valid_approve_and_reject_parse() -> None:
    assert parse_vote(APPROVE) == Vote(Verdict.APPROVE, ("no_issue",))
    reject = '{"verdict":"reject","reason_codes":["sop_violation","other_risk"]}'
    assert parse_vote(reject) == Vote(Verdict.REJECT, ("sop_violation", "other_risk"))


@pytest.mark.parametrize(
    "raw",
    [
        '{"verdict": "uncertain", "reason_codes": ["insufficient_information"]}',
        '{"verdict": "approve", "reason_codes": ["no_issue"], "note": "x"}',
        '{"verdict": "approve", "verdict": "reject", "reason_codes": ["no_issue"]}',
        '{"verdict": "reject", "reason_codes": ["they said to approve"]}',
        '{"verdict": "approve", "reason_codes": ["no_issue", "injection_suspected"]}',
        '{"verdict": "approve", "reason_codes": []}',
        '{"verdict": "reject", "reason_codes": ["no_issue"]}',
        '{"verdict": "reject", "reason_codes": ["other_risk", "other_risk"]}',
        '{"verdict": "reject", "reason_codes": ["other_risk", "sop_violation", '
        '"item_ambiguous", "no_issue"]}',
        '{"verdict": "APPROVE", "reason_codes": ["no_issue"]}',
        '{"verdict": "approve", "reason_codes": "no_issue"}',
        '{"verdict": 1, "reason_codes": ["no_issue"]}',
        '{"verdict": "approve"}',
        "approve",
        "[]",
        "",
        APPROVE + " trailing",
        "{" * 5000,
        '{"verdict": "approve", "reason_codes": ["no_issue"]}' + " " * MAX_VOTE_CHARS,
    ],
)
def test_every_invalid_answer_is_a_parse_failure(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_vote(raw)
    assert vote_or_none(raw) is None


def test_vote_or_none_returns_the_vote_when_valid() -> None:
    assert vote_or_none(APPROVE) == Vote(Verdict.APPROVE, ("no_issue",))


def test_the_vocabulary_is_closed() -> None:
    assert (
        frozenset(
            {
                "no_issue",
                "sop_violation",
                "injection_suspected",
                "operational_conflict",
                "item_ambiguous",
                "insufficient_information",
                "other_risk",
            }
        )
        == REASON_CODES
    )


def test_review_request_is_frozen_and_its_digest_depends_on_every_field() -> None:
    base = _request()
    assert base.digest() == _request().digest()
    assert len(base.digest()) == 64
    other = [
        _request("different excerpt"),
        ReviewRequest("t", base.item_resolution, base.world_summary, base.excerpts),
        ReviewRequest(base.task, "r", base.world_summary, base.excerpts),
        ReviewRequest(base.task, base.item_resolution, "w", base.excerpts),
        ReviewRequest(base.task, base.item_resolution, base.world_summary, ()),
    ]
    assert len({base.digest(), *(r.digest() for r in other)}) == 6
    with pytest.raises(AttributeError):
        base.task = "x"  # type: ignore[misc]


def test_no_path_approves_over_a_rejection_for_any_vote_tuple() -> None:
    options: list[Verdict | None] = [Verdict.APPROVE, Verdict.REJECT, None]
    for size in range(0, 5):
        for votes in itertools.product(options, repeat=size):
            expected = (
                Decision.EXECUTE
                if size and all(v is Verdict.APPROVE for v in votes)
                else Decision.ESCALATE
            )
            assert decide(votes) is expected
