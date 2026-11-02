"""voice-intent-v1: a closed schema; anything else is rejected and nothing is guessed."""

import json

import pytest

from waggle.multimodal.voice_intent import (
    CONSEQUENTIAL,
    SCHEMA_VERSION,
    IntentError,
    VoiceIntent,
    parse_voice_intent,
)


def _raw(**overrides: object) -> str:
    payload: dict[str, object] = {
        "intent": "pick_item",
        "item_ids": ["ITEM-7"],
        "zone_ids": [],
        "confidence": 0.9,
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_a_valid_intent_is_parsed() -> None:
    intent = parse_voice_intent(_raw())
    assert intent == VoiceIntent("pick_item", ("ITEM-7",), (), 0.9)
    assert SCHEMA_VERSION == "voice-intent-v1"


@pytest.mark.parametrize(
    "name", ["pick_item", "deliver_item", "report_obstruction", "status_query", "cancel_last"]
)
def test_every_enum_value_is_accepted(name: str) -> None:
    assert parse_voice_intent(_raw(intent=name)).intent == name


def test_pick_and_deliver_are_consequential_and_the_rest_are_not() -> None:
    assert frozenset({"pick_item", "deliver_item"}) == CONSEQUENTIAL


@pytest.mark.parametrize("name", ["PICK_ITEM", "pick", "open_door", "", "grant_admin"])
def test_an_intent_outside_the_closed_enum_is_rejected(name: str) -> None:
    with pytest.raises(IntentError):
        parse_voice_intent(_raw(intent=name))


@pytest.mark.parametrize(
    "extra", [{"operator_id": "admin"}, {"chassis": "forklift"}, {"speed": 3.0}, {"zone": "z"}]
)
def test_extra_fields_are_rejected_so_audio_cannot_set_identity_or_limits(
    extra: dict[str, object],
) -> None:
    payload = json.loads(_raw())
    payload.update(extra)
    with pytest.raises(IntentError):
        parse_voice_intent(json.dumps(payload))


@pytest.mark.parametrize("missing", ["intent", "item_ids", "zone_ids", "confidence"])
def test_a_missing_field_is_rejected(missing: str) -> None:
    payload = json.loads(_raw())
    del payload[missing]
    with pytest.raises(IntentError):
        parse_voice_intent(json.dumps(payload))


@pytest.mark.parametrize("confidence", [-0.01, 1.01, True, "0.9", None, float("nan")])
def test_confidence_must_be_a_real_number_from_zero_to_one(confidence: object) -> None:
    with pytest.raises(IntentError):
        parse_voice_intent(_raw(confidence=confidence))


@pytest.mark.parametrize("confidence", [0, 1, 0.0, 1.0])
def test_the_bounds_of_confidence_are_allowed(confidence: float) -> None:
    assert parse_voice_intent(_raw(confidence=confidence)).confidence == confidence


@pytest.mark.parametrize(
    "item_ids",
    ["ITEM-7", [7], [None], ["ITEM-7", "ITEM-7"], ["x" * 65], [""], ["ITEM-1"] * 6, ["a b"]],
)
def test_item_ids_must_be_a_short_list_of_distinct_plain_strings(item_ids: object) -> None:
    with pytest.raises(IntentError):
        parse_voice_intent(_raw(item_ids=item_ids))


def test_zone_ids_follow_the_same_rule() -> None:
    assert parse_voice_intent(_raw(zone_ids=["dock-1"])).zone_ids == ("dock-1",)
    with pytest.raises(IntentError):
        parse_voice_intent(_raw(zone_ids=[1]))


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[]",
        "null",
        '"pick_item"',
        '{"intent":"pick_item","intent":"status_query","item_ids":[],"zone_ids":[],"confidence":1}',
        "x" * 5000,
        "[" * 10000,
    ],
)
def test_malformed_or_hostile_text_is_rejected_with_a_typed_error(raw: str) -> None:
    with pytest.raises(IntentError):
        parse_voice_intent(raw)


def test_a_non_string_is_rejected() -> None:
    with pytest.raises(IntentError):
        parse_voice_intent(None)  # type: ignore[arg-type]
