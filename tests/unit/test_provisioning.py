"""Provisioning of catalog, machines, zones and identities from a spec file (ADR-056)."""

import json
from pathlib import Path

import psycopg.errors
import pytest

from waggle.mcp_server.identity import hash_token
from waggle.provisioning import (
    Provisioned,
    SpecError,
    TargetExists,
    load_spec,
    parse_spec,
    provision,
    write_tokens,
)

SPEC = {
    "parts": [{"part_number": "BRG-6204", "on_hand": 3}, {"part_number": "SEAL-08", "on_hand": 0}],
    "machines": ["C1", "CONV-1"],
    "zones": ["Z1", "Z2"],
    "identities": [
        {"chassis": "carrier", "robot_id": "C1"},
        {"chassis": "tech_repair", "robot_id": "TECH-1"},
    ],
}


class _Inventory:
    def __init__(self) -> None:
        self.parts: dict[str, int] = {}

    def get(self, part_number: str) -> object | None:
        return self.parts.get(part_number)

    def add_part(self, part_number: str, on_hand: int) -> None:
        self.parts[part_number] = on_hand


class _Machines:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    def add_machine(self, machine_id: str) -> None:
        if machine_id in self.ids:
            raise psycopg.errors.UniqueViolation("duplicate")
        self.ids.add(machine_id)


class _Zones:
    def __init__(self) -> None:
        self.names: set[str] = set()

    def register(self, resources: tuple[str, ...]) -> None:
        self.names.update(resources)


class _Identities:
    def __init__(self) -> None:
        self.active: dict[tuple[str, str], str] = {}

    def register(self, token_hash: str, chassis: str, robot_id: str) -> None:
        if (chassis, robot_id) in self.active:
            raise psycopg.errors.UniqueViolation("duplicate")
        self.active[(chassis, robot_id)] = token_hash


def _write(path: Path, body: object) -> Path:
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _run(
    inventory: _Inventory, machines: _Machines, zones: _Zones, identities: _Identities
) -> Provisioned:
    return provision(parse_spec(SPEC), inventory, machines, zones, identities)


def test_everything_in_the_spec_is_created() -> None:
    inventory, machines, zones, identities = _Inventory(), _Machines(), _Zones(), _Identities()
    result = _run(inventory, machines, zones, identities)
    assert inventory.parts == {"BRG-6204": 3, "SEAL-08": 0}
    assert machines.ids == {"C1", "CONV-1"}
    assert zones.names == {"Z1", "Z2"}
    assert set(identities.active) == {("carrier", "C1"), ("tech_repair", "TECH-1")}
    assert (len(result.parts), len(result.machines), len(result.zones)) == (2, 2, 2)
    assert set(result.tokens) == {"C1", "TECH-1"}


def test_only_the_digest_of_each_token_is_stored() -> None:
    identities = _Identities()
    result = _run(_Inventory(), _Machines(), _Zones(), identities)
    assert identities.active[("carrier", "C1")] == hash_token(result.tokens["C1"])
    assert len(result.tokens["C1"]) == 43


def test_a_second_run_creates_nothing_and_reports_what_it_skipped() -> None:
    inventory, machines, zones, identities = _Inventory(), _Machines(), _Zones(), _Identities()
    _run(inventory, machines, zones, identities)
    inventory.parts["BRG-6204"] = 99  # stock changed since: a rerun must not reset it
    again = _run(inventory, machines, zones, identities)
    assert inventory.parts["BRG-6204"] == 99
    assert again.tokens == {}
    assert set(again.skipped) == {
        "part:BRG-6204",
        "part:SEAL-08",
        "machine:C1",
        "machine:CONV-1",
        "identity:C1",
        "identity:TECH-1",
    }


def test_the_result_never_contains_a_token_in_its_text() -> None:
    result = _run(_Inventory(), _Machines(), _Zones(), _Identities())
    text = repr(result)
    assert all(token not in text for token in result.tokens.values())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(extra=1),
        lambda s: s.pop("zones"),
        lambda s: s["parts"][0].update(on_hand=-1),
        lambda s: s["parts"][0].update(on_hand=True),
        lambda s: s["parts"][0].update(note="x"),
        lambda s: s["parts"].append(s["parts"][0]),
        lambda s: s["machines"].append("bad id"),
        lambda s: s["zones"].append(""),
        lambda s: s["identities"][0].update(chassis="submarine"),
        lambda s: s["identities"][0].update(robot_id="a b"),
        lambda s: s["identities"].append(s["identities"][0]),
    ],
)
def test_an_invalid_spec_is_rejected_before_anything_is_created(mutate: object) -> None:
    body = json.loads(json.dumps(SPEC))
    mutate(body)  # type: ignore[operator]
    with pytest.raises(SpecError):
        parse_spec(body)


def test_load_spec_rejects_text_that_is_not_json(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(SpecError):
        load_spec(path)
    with pytest.raises(SpecError):
        load_spec(tmp_path / "missing.json")


def test_tokens_are_written_to_a_new_file_and_never_overwritten(tmp_path: Path) -> None:
    out = tmp_path / "tokens.json"
    write_tokens(out, {"C1": "t" * 43})
    assert json.loads(out.read_text(encoding="utf-8")) == {"C1": "t" * 43}
    with pytest.raises(TargetExists):
        write_tokens(out, {"C1": "u" * 43})
    assert json.loads(out.read_text(encoding="utf-8")) == {"C1": "t" * 43}


def _main(spec: Path, out: Path, environ: dict[str, str]) -> tuple[int, str]:
    import io

    from waggle.provisioning import main

    err = io.StringIO()
    return main([str(spec), str(out)], environ, err), err.getvalue()


def test_main_without_a_database_url_fails_closed_and_writes_no_token(tmp_path: Path) -> None:
    spec = _write(tmp_path / "spec.json", SPEC)
    code, message = _main(spec, tmp_path / "tokens.json", {})
    assert code == 2
    assert "provision failed" in message
    assert not (tmp_path / "tokens.json").exists()


def test_main_refuses_an_existing_token_file_before_touching_the_database(tmp_path: Path) -> None:
    spec = _write(tmp_path / "spec.json", SPEC)
    (tmp_path / "tokens.json").write_text("{}", encoding="utf-8")
    code, message = _main(spec, tmp_path / "tokens.json", {"DATABASE_URL": "postgresql://x/y"})
    assert (code, message) == (2, "provision failed: TargetExists\n")


def test_main_rejects_an_invalid_spec(tmp_path: Path) -> None:
    spec = _write(tmp_path / "spec.json", {"parts": []})
    code, message = _main(spec, tmp_path / "tokens.json", {"DATABASE_URL": "postgresql://x/y"})
    assert (code, message) == (2, "provision failed: SpecError\n")
