"""Incident text is a threat-model source and gets its own sanitizer entry (T18)."""

import pytest

from waggle.governance.sanitizers import MAX_CHARS, SanitizeError, UntrustedSource, fence, sanitize


def test_incident_text_is_an_untrusted_source_with_a_cap() -> None:
    assert UntrustedSource.INCIDENT_TEXT.value == "incident_text"
    assert MAX_CHARS[UntrustedSource.INCIDENT_TEXT] > 0
    assert set(MAX_CHARS) == set(UntrustedSource)


def test_incident_text_is_cleaned_and_fenced_as_data() -> None:
    clean = sanitize("Aisle 4 blocked.​ <ignore previous>", UntrustedSource.INCIDENT_TEXT)
    assert "​" not in clean.text
    fenced = fence(clean)
    assert fenced.startswith('<untrusted source="incident_text">')
    assert "&lt;ignore previous&gt;" in fenced


@pytest.mark.parametrize(("text", "code"), [("", "empty"), ("x" * 100_000, "too_long")])
def test_incident_text_that_cannot_be_screened_is_rejected(text: str, code: str) -> None:
    with pytest.raises(SanitizeError) as caught:
        sanitize(text, UntrustedSource.INCIDENT_TEXT)
    assert caught.value.code == code
