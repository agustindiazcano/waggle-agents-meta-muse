"""Token authentication for the MCP boundary (ADR-032, interface only, no database)."""

import hashlib
import hmac
import logging
from unittest import mock

import pytest

from waggle.mcp_server.identity import (
    AuthError,
    Identity,
    IdentityRecord,
    authenticate,
    generate_token,
    hash_token,
)

TOKEN = "t" * 43


class FakeStore:
    """Looks up by digest, like the table will."""

    def __init__(self, *records: IdentityRecord) -> None:
        self.records = {r.token_hash: r for r in records}
        self.lookups: list[str] = []

    def lookup(self, token_hash: str) -> IdentityRecord | None:
        self.lookups.append(token_hash)
        return self.records.get(token_hash)


def record(
    token: str = TOKEN, chassis: str = "carrier", robot_id: str = "r-1", revoked: bool = False
) -> IdentityRecord:
    return IdentityRecord(hash_token(token), chassis, robot_id, revoked)


def code_of(token: object, store: object) -> str:
    with pytest.raises(AuthError) as err:
        authenticate(token, store)  # type: ignore[arg-type]
    return err.value.code


def test_hash_is_sha256_hex_of_the_utf8_token() -> None:
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


def test_valid_token_yields_the_identity_from_the_record() -> None:
    out = authenticate(TOKEN, FakeStore(record(chassis="forklift", robot_id="r-7")))
    assert out == Identity("forklift", "r-7")


def test_store_is_queried_with_the_digest_never_the_token() -> None:
    store = FakeStore(record())
    authenticate(TOKEN, store)
    assert store.lookups == [hash_token(TOKEN)]
    assert TOKEN not in store.lookups[0]


def test_digests_are_compared_in_constant_time() -> None:
    with mock.patch("hmac.compare_digest", wraps=hmac.compare_digest) as spy:
        authenticate(TOKEN, FakeStore(record()))
    assert spy.call_count >= 1


def test_unknown_token_is_denied() -> None:
    assert code_of("u" * 43, FakeStore(record())) == "unknown_token"


def test_revoked_token_is_denied() -> None:
    assert code_of(TOKEN, FakeStore(record(revoked=True))) == "revoked"


@pytest.mark.parametrize("bad", [None, 5, b"abc", "", "   ", "a b", "a\n", "x" * 257, "é" * 8])
def test_malformed_tokens_are_denied_without_a_lookup(bad: object) -> None:
    store = FakeStore(record())
    assert code_of(bad, store) == "bad_token"
    assert store.lookups == []


def test_token_length_boundary() -> None:
    assert code_of("x" * 256, FakeStore()) == "unknown_token"
    assert code_of("x" * 257, FakeStore()) == "bad_token"


def test_record_whose_digest_does_not_match_is_denied() -> None:
    class Lying:
        def lookup(self, token_hash: str) -> IdentityRecord | None:
            return record(token="another-token-value")

    assert code_of(TOKEN, Lying()) == "unknown_token"


def test_record_with_unknown_chassis_is_denied() -> None:
    assert code_of(TOKEN, FakeStore(record(chassis="ghost"))) == "bad_record"


def test_record_with_unsafe_robot_id_is_denied() -> None:
    assert code_of(TOKEN, FakeStore(record(robot_id="r 1;drop"))) == "bad_record"
    assert code_of(TOKEN, FakeStore(record(robot_id=""))) == "bad_record"


def test_store_failure_fails_closed_and_is_logged_without_the_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Broken:
        def lookup(self, token_hash: str) -> IdentityRecord | None:
            raise RuntimeError("connection refused")

    with caplog.at_level(logging.ERROR):
        assert code_of(TOKEN, Broken()) == "store_error"
    assert caplog.records
    assert TOKEN not in caplog.text
    assert hash_token(TOKEN) not in caplog.text


def test_error_messages_never_contain_the_token() -> None:
    with pytest.raises(AuthError) as err:
        authenticate(TOKEN, FakeStore())
    assert TOKEN not in str(err.value)
    assert TOKEN not in repr(err.value)


def test_generated_tokens_are_long_unique_and_accepted_by_the_format_check() -> None:
    tokens = {generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 43 for t in tokens)
    token = next(iter(tokens))
    assert authenticate(token, FakeStore(record(token=token))).chassis == "carrier"


def test_identity_and_record_are_immutable() -> None:
    with pytest.raises(AttributeError):
        Identity("carrier", "r-1").chassis = "forklift"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        record().revoked = False  # type: ignore[misc]
