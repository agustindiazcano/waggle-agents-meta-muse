"""vision-v1: a closed schema; anything else is rejected and nothing is guessed."""

import json

import pytest

from waggle.multimodal.vision_schema import (
    OBSTRUCTION_CLASSES,
    SCHEMA_VERSION,
    LabelError,
    VisionLabel,
    parse_vision_label,
)


def _raw(**overrides: object) -> str:
    payload: dict[str, object] = {
        "label_text": "PKG-7",
        "obstruction_class": "none",
        "legibility": 0.9,
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_a_valid_label_is_parsed() -> None:
    label = parse_vision_label(_raw())
    assert label == VisionLabel("PKG-7", "none", 0.9)
    assert SCHEMA_VERSION == "vision-v1"


@pytest.mark.parametrize("name", ["none", "package", "human", "vehicle", "debris", "unknown"])
def test_every_obstruction_class_is_accepted(name: str) -> None:
    assert parse_vision_label(_raw(obstruction_class=name)).obstruction_class == name
    assert name in OBSTRUCTION_CLASSES


@pytest.mark.parametrize("name", ["NONE", "obstacle", "person", "", "clear"])
def test_an_obstruction_outside_the_closed_enum_is_rejected(name: str) -> None:
    with pytest.raises(LabelError):
        parse_vision_label(_raw(obstruction_class=name))


@pytest.mark.parametrize(
    "extra", [{"package_id": "PKG-7"}, {"confidence": 1}, {"action": "pick"}, {"speed": 2.0}]
)
def test_extra_fields_are_rejected_so_a_label_cannot_name_a_package_or_action(
    extra: dict[str, object],
) -> None:
    payload = json.loads(_raw())
    payload.update(extra)
    with pytest.raises(LabelError):
        parse_vision_label(json.dumps(payload))


@pytest.mark.parametrize("missing", ["label_text", "obstruction_class", "legibility"])
def test_a_missing_field_is_rejected(missing: str) -> None:
    payload = json.loads(_raw())
    del payload[missing]
    with pytest.raises(LabelError):
        parse_vision_label(json.dumps(payload))


@pytest.mark.parametrize("legibility", [-0.01, 1.01, True, "0.9", None, float("nan")])
def test_legibility_must_be_a_real_number_from_zero_to_one(legibility: object) -> None:
    with pytest.raises(LabelError):
        parse_vision_label(_raw(legibility=legibility))


@pytest.mark.parametrize("legibility", [0, 1, 0.0, 1.0])
def test_the_bounds_of_legibility_are_allowed(legibility: float) -> None:
    assert parse_vision_label(_raw(legibility=legibility)).legibility == legibility


def test_label_text_is_bounded_by_the_package_label_cap() -> None:
    assert parse_vision_label(_raw(label_text="x" * 200)).label_text == "x" * 200
    with pytest.raises(LabelError):
        parse_vision_label(_raw(label_text="x" * 201))


@pytest.mark.parametrize("label_text", [7, None, ["PKG-7"]])
def test_label_text_must_be_text(label_text: object) -> None:
    with pytest.raises(LabelError):
        parse_vision_label(_raw(label_text=label_text))


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[]",
        "null",
        '"PKG-7"',
        '{"label_text":"PKG-7","label_text":"PKG-9","obstruction_class":"none","legibility":1}',
        "x" * 5000,
    ],
)
def test_malformed_or_hostile_text_is_rejected_with_a_typed_error(raw: str) -> None:
    with pytest.raises(LabelError):
        parse_vision_label(raw)


def test_a_non_string_is_rejected() -> None:
    with pytest.raises(LabelError):
        parse_vision_label(None)  # type: ignore[arg-type]
