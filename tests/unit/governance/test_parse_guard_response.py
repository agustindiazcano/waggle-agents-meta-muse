"""The guard response parser is public so output structure can be scored on its own."""

import pytest

from waggle.governance.classifier import parse_guard_response
from waggle.governance.guard import GuardLabel


def test_a_valid_response_parses() -> None:
    assert parse_guard_response('{"label":"benign","reason_code":"ok_text"}') == (
        GuardLabel.BENIGN,
        "ok_text",
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"label":"injection","label":"benign","reason_code":"x"}',
        '{"label":"benign"}',
        '{"label":"benign","reason_code":"x","extra":1}',
        '{"label":"maybe","reason_code":"x"}',
        '{"label":"benign","reason_code":"Bad Code"}',
        "not json",
        "[]",
        "x" * 2000,
        5,
    ],
)
def test_a_malformed_response_raises_value_error(raw: object) -> None:
    with pytest.raises(ValueError):
        parse_guard_response(raw)  # type: ignore[arg-type]
