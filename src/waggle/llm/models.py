"""Plain data types shared by the LLM layer."""

import base64
import binascii
from dataclasses import dataclass
from typing import Final, Literal

from waggle.llm.errors import InvalidAttachmentError

CallStatus = Literal["ok", "denied", "error", "cached"]

# Limits are assumptions to calibrate against the provider documentation and the cost method.
MAX_ATTACHMENTS: Final = 2
MAX_IMAGE_BYTES: Final = 2 * 1024 * 1024
MAX_AUDIO_BYTES: Final = 5 * 1024 * 1024
_MEDIA_TYPES: Final[dict[str, frozenset[str]]] = {
    "image": frozenset({"image/png", "image/jpeg"}),
    "audio": frozenset({"audio/wav", "audio/mpeg", "audio/webm"}),
}
_MAX_BYTES: Final = {"image": MAX_IMAGE_BYTES, "audio": MAX_AUDIO_BYTES}


@dataclass(frozen=True)
class Attachment:
    """One image or audio input as base64 text. Invalid or oversized data is rejected here.

    The encoded length is checked before decoding, so a huge string is never expanded.
    """

    kind: str
    media_type: str
    data_b64: str

    def __post_init__(self) -> None:
        allowed = _MEDIA_TYPES.get(self.kind)
        if allowed is None or self.media_type not in allowed:
            raise InvalidAttachmentError("kind or media type is not allowed")
        if not isinstance(self.data_b64, str) or not self.data_b64:
            raise InvalidAttachmentError("data must be a non-empty base64 string")
        if len(self.data_b64) > 4 * ((_MAX_BYTES[self.kind] + 2) // 3):
            raise InvalidAttachmentError("data exceeds the size limit")
        try:
            size = len(base64.b64decode(self.data_b64, validate=True))
        except (binascii.Error, ValueError):
            raise InvalidAttachmentError("data is not valid base64") from None
        if size == 0 or size > _MAX_BYTES[self.kind]:
            raise InvalidAttachmentError("data exceeds the size limit")

    @property
    def size_bytes(self) -> int:
        """Decoded size in bytes."""
        return len(base64.b64decode(self.data_b64, validate=True))


@dataclass(frozen=True)
class LlmRequest:
    """One request to a role. ``request_id`` is checked before any model call."""

    request_id: str
    role: str
    prompt: str
    task_id: str | None = None
    attachments: tuple[Attachment, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.attachments, tuple) or not all(
            isinstance(item, Attachment) for item in self.attachments
        ):
            raise InvalidAttachmentError("attachments must be a tuple of Attachment")
        if len(self.attachments) > MAX_ATTACHMENTS:
            raise InvalidAttachmentError("too many attachments")


@dataclass(frozen=True)
class Completion:
    """Result of a provider call."""

    text: str
    model_id: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    cost_usd: float


@dataclass(frozen=True)
class CallRecord:
    """One row of the call log (the future llm_calls table)."""

    request_id: str
    task_id: str | None
    role: str
    provider: str
    model_id: str
    status: CallStatus
    tokens_in: int
    tokens_out: int
    latency_s: float
    cost_usd: float
    fallback_label: str | None = None
