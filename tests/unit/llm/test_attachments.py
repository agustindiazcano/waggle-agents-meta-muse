"""Image and audio attachments on an LLM request: strict limits, nothing invalid gets through."""

import base64

import pytest

from waggle.llm.errors import InvalidAttachmentError, LlmError
from waggle.llm.models import (
    MAX_ATTACHMENTS,
    MAX_AUDIO_BYTES,
    MAX_IMAGE_BYTES,
    Attachment,
    LlmRequest,
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_a_valid_audio_attachment_is_kept_as_given() -> None:
    attachment = Attachment("audio", "audio/wav", _b64(b"RIFFdata"))
    request = LlmRequest("r1", "voice", "transcribe", attachments=(attachment,))
    assert request.attachments == (attachment,)
    assert attachment.size_bytes == len(b"RIFFdata")


def test_a_request_has_no_attachments_by_default() -> None:
    assert LlmRequest("r1", "guard", "text").attachments == ()


@pytest.mark.parametrize(
    ("kind", "media_type"),
    [
        ("audio", "image/png"),
        ("image", "audio/wav"),
        ("video", "video/mp4"),
        ("audio", "audio/x-unknown"),
        ("image", "image/svg+xml"),
        ("image", ""),
    ],
)
def test_a_kind_or_media_type_outside_the_allowed_list_is_rejected(
    kind: str, media_type: str
) -> None:
    with pytest.raises(InvalidAttachmentError):
        Attachment(kind, media_type, _b64(b"x"))


@pytest.mark.parametrize("data", ["", "not base64!!", "QQ", "QUJD\nREVG", "QUJD=REVG", " QUJD"])
def test_base64_must_be_strictly_valid_and_non_empty(data: str) -> None:
    with pytest.raises(InvalidAttachmentError):
        Attachment("image", "image/png", data)


def test_a_non_string_payload_is_rejected() -> None:
    with pytest.raises(InvalidAttachmentError):
        Attachment("image", "image/png", b"abc")  # type: ignore[arg-type]


def test_size_limits_are_per_kind_and_bounded() -> None:
    assert Attachment("image", "image/png", _b64(b"x" * MAX_IMAGE_BYTES)).size_bytes
    with pytest.raises(InvalidAttachmentError):
        Attachment("image", "image/png", _b64(b"x" * (MAX_IMAGE_BYTES + 1)))
    assert Attachment("audio", "audio/wav", _b64(b"x" * MAX_AUDIO_BYTES)).size_bytes
    with pytest.raises(InvalidAttachmentError):
        Attachment("audio", "audio/wav", _b64(b"x" * (MAX_AUDIO_BYTES + 1)))


def test_the_encoded_text_is_checked_before_it_is_decoded() -> None:
    huge = "A" * (4 * (MAX_AUDIO_BYTES + MAX_IMAGE_BYTES))
    with pytest.raises(InvalidAttachmentError):
        Attachment("audio", "audio/wav", huge)


def test_too_many_attachments_are_rejected() -> None:
    one = Attachment("image", "image/png", _b64(b"x"))
    assert LlmRequest("r", "vision", "p", attachments=(one,) * MAX_ATTACHMENTS)
    with pytest.raises(InvalidAttachmentError):
        LlmRequest("r", "vision", "p", attachments=(one,) * (MAX_ATTACHMENTS + 1))


def test_attachments_must_be_a_tuple_of_attachments() -> None:
    with pytest.raises(InvalidAttachmentError):
        LlmRequest("r", "vision", "p", attachments=["x"])  # type: ignore[arg-type]


def test_the_error_is_a_typed_llm_error() -> None:
    assert issubclass(InvalidAttachmentError, LlmError)
    assert issubclass(InvalidAttachmentError, ValueError)
