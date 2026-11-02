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
    "compatibility": [
        {"machine_id": "C1", "part_number": "BRG-6204"},
        {"machine_id": "CONV-1", "part_number": "SEAL-08"},
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

    def has_machine(self, machine_id: str) -> bool:
        return machine_id in self.ids


class _Compatibility:
    def __init__(self) -> None:
        self.rows: set[tuple[str, str]] = set()

    def exists(self, machine_id: str, part_number: str) -> bool:
        return (machine_id, part_number) in self.rows

    def add(self, machine_id: str, part_number: str) -> None:
        self.rows.add((machine_id, part_number))

    def count(self) -> int:
        return len(self.rows)


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
    inventory: _Inventory,
    machines: _Machines,
    zones: _Zones,
    identities: _Identities,
    compatibility: _Compatibility | None = None,
    body: object = SPEC,
) -> Provisioned:
    return provision(
        parse_spec(body),
        inventory,
        machines,
        zones,
        identities,
        compatibility if compatibility is not None else _Compatibility(),
    )


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
        lambda s: s.update(compatibility={}),
        lambda s: s["compatibility"].append(s["compatibility"][0]),
        lambda s: s["compatibility"][0].update(note="x"),
        lambda s: s["compatibility"][0].pop("part_number"),
        lambda s: s["compatibility"][0].update(machine_id="bad id"),
        lambda s: s["compatibility"][0].update(part_number=5),
        lambda s: s["compatibility"].append("C1/BRG-6204"),
    ],
)
def test_an_invalid_spec_is_rejected_before_anything_is_created(mutate: object) -> None:
    body = json.loads(json.dumps(SPEC))
    mutate(body)  # type: ignore[operator]
    with pytest.raises(SpecError):
        parse_spec(body)


def test_the_compatibility_key_is_optional_for_older_specs() -> None:
    body = {k: v for k, v in SPEC.items() if k != "compatibility"}
    assert parse_spec(body).compatibility == ()


def test_compatibility_rows_are_created_after_parts_and_machines() -> None:
    compatibility = _Compatibility()
    result = _run(_Inventory(), _Machines(), _Zones(), _Identities(), compatibility)
    assert compatibility.rows == {("C1", "BRG-6204"), ("CONV-1", "SEAL-08")}
    assert result.warnings == ()


def test_a_rerun_skips_existing_compatibility_rows_and_names_them() -> None:
    inventory, machines, zones, identities = _Inventory(), _Machines(), _Zones(), _Identities()
    compatibility = _Compatibility()
    _run(inventory, machines, zones, identities, compatibility)
    again = _run(inventory, machines, zones, identities, compatibility)
    assert {"compatibility:C1/BRG-6204", "compatibility:CONV-1/SEAL-08"} <= set(again.skipped)
    assert compatibility.rows == {("C1", "BRG-6204"), ("CONV-1", "SEAL-08")}


@pytest.mark.parametrize(
    "row",
    [
        {"machine_id": "GHOST", "part_number": "BRG-6204"},
        {"machine_id": "C1", "part_number": "GHOST-1"},
    ],
)
def test_a_row_naming_an_unknown_machine_or_part_rejects_the_spec_before_anything_is_created(
    row: dict[str, str],
) -> None:
    body = json.loads(json.dumps(SPEC))
    body["compatibility"].append(row)
    inventory, machines, zones, identities = _Inventory(), _Machines(), _Zones(), _Identities()
    compatibility = _Compatibility()
    with pytest.raises(SpecError):
        _run(inventory, machines, zones, identities, compatibility, body)
    assert inventory.parts == {} and machines.ids == set() and zones.names == set()
    assert identities.active == {} and compatibility.rows == set()


def test_a_row_may_name_a_machine_and_part_that_already_exist_in_the_database() -> None:
    inventory, machines = _Inventory(), _Machines()
    _run(inventory, machines, _Zones(), _Identities())
    body = {
        "parts": [],
        "machines": [],
        "zones": [],
        "identities": [],
        "compatibility": [{"machine_id": "C1", "part_number": "SEAL-08"}],
    }
    compatibility = _Compatibility()
    _run(inventory, machines, _Zones(), _Identities(), compatibility, body)
    assert compatibility.rows == {("C1", "SEAL-08")}


def test_parts_without_any_compatibility_row_produce_a_warning() -> None:
    body = {k: v for k, v in SPEC.items() if k != "compatibility"}
    result = _run(_Inventory(), _Machines(), _Zones(), _Identities(), body=body)
    assert len(result.warnings) == 1
    assert "compatibility" in result.warnings[0]


def test_the_warning_is_written_to_standard_error(tmp_path: Path) -> None:
    import io

    from waggle.provisioning import report

    err = io.StringIO()
    result = _run(
        _Inventory(), _Machines(), _Zones(), _Identities(), body={**SPEC, "compatibility": []}
    )
    report(result, parse_spec({**SPEC, "compatibility": []}), err)
    assert "warning" in err.getvalue()


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


class _Packages:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    def has(self, package_id: str) -> bool:
        return package_id in self.ids

    def add(self, package_id: str, source: str = "scenario") -> None:
        self.ids.add(package_id)


def test_the_packages_key_is_optional_for_older_specs() -> None:
    assert parse_spec(SPEC).packages == ()


def test_package_ids_are_validated_and_must_be_unique() -> None:
    assert parse_spec({**SPEC, "packages": ["pk-1", "pk-2"]}).packages == ("pk-1", "pk-2")
    for bad in (["pk-1", "pk-1"], ["bad id"], [3], "pk-1"):
        with pytest.raises(SpecError):
            parse_spec({**SPEC, "packages": bad})


def test_package_ids_are_registered_and_a_rerun_skips_them() -> None:
    packages = _Packages()
    spec = parse_spec({**SPEC, "packages": ["pk-1", "pk-2"]})
    args = (spec, _Inventory(), _Machines(), _Zones(), _Identities(), _Compatibility())
    first = provision(*args, packages=packages)
    assert packages.ids == {"pk-1", "pk-2"} and first.packages == ("pk-1", "pk-2")
    again = provision(*args, packages=packages)
    assert again.packages == () and "package:pk-1" in again.skipped
