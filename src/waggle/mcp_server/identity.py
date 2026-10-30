"""Chassis token authentication (ADR-032). Interface only: the store is a protocol, so this
module holds no database code.

The server keeps only ``sha256(token)``. ``chassis`` and ``robot_id`` come from the matched
record and never from the request. Every failure denies; no message carries the token or its
digest.
"""

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Literal, Protocol

from waggle.mcp_server.allowlist import ALLOWLIST

logger = logging.getLogger("waggle.mcp_server")

AuthCode = Literal["bad_token", "unknown_token", "revoked", "bad_record", "store_error"]

_TOKEN = re.compile(r"[\x21-\x7e]+")
_TOKEN_MAX = 256
_ROBOT_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class AuthError(Exception):
    """Authentication failed. ``code`` is the audit reason code."""

    def __init__(self, code: AuthCode) -> None:
        super().__init__(code)
        self.code: AuthCode = code


@dataclass(frozen=True)
class Identity:
    """The authenticated caller."""

    chassis: str
    robot_id: str


@dataclass(frozen=True)
class IdentityRecord:
    """One stored identity: the token digest, who it belongs to and whether it was revoked."""

    token_hash: str
    chassis: str
    robot_id: str
    revoked: bool


class IdentityStore(Protocol):
    """Finds a record by token digest. A miss returns None; a failure raises."""

    def lookup(self, token_hash: str) -> IdentityRecord | None:
        """Return the record for ``token_hash`` or None."""
        ...


def hash_token(token: str) -> str:
    """Hex SHA-256 of the token. A fast hash is enough: tokens are long and random."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """A new random token (256 bits). Provision it outside the repository, store only its hash."""
    return secrets.token_urlsafe(32)


def authenticate(token: str, store: IdentityStore) -> Identity:
    """Return the identity for ``token`` or raise AuthError."""
    if not isinstance(token, str) or len(token) > _TOKEN_MAX or _TOKEN.fullmatch(token) is None:
        raise AuthError("bad_token")
    digest = hash_token(token)
    try:
        found = store.lookup(digest)
    except Exception as err:
        logger.error("identity store failed: %s", type(err).__name__)
        raise AuthError("store_error") from err
    if found is None or not hmac.compare_digest(
        found.token_hash.encode("utf-8"), digest.encode("utf-8")
    ):
        raise AuthError("unknown_token")
    if found.revoked:
        raise AuthError("revoked")
    if found.chassis not in ALLOWLIST or _ROBOT_ID.fullmatch(found.robot_id) is None:
        raise AuthError("bad_record")
    return Identity(found.chassis, found.robot_id)
