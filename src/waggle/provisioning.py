"""Load catalog, machines, zones and robot identities from a spec file (ADR-056).

Data is provisioned by this script and never by a migration. The spec is validated in full
before anything is created. A rerun is safe: existing parts, machines and active identities are
skipped and reported, existing zones are left as they are, and stock is never reset. A token is
generated per new identity, only its digest reaches the database, and the token goes to a new
file that is never overwritten. Tokens are never printed or logged.
"""

import json
import logging
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TextIO

import psycopg.errors

from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.identities import PostgresIdentityStore
from waggle.db.inventory import InventoryRepository
from waggle.db.tickets import TicketRepository
from waggle.mcp_server.allowlist import ALLOWLIST
from waggle.mcp_server.identity import generate_token, hash_token

logger = logging.getLogger("waggle.provisioning")

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_STOCK_MAX = 1_000_000
_KEYS = frozenset({"parts", "machines", "zones", "identities"})


class SpecError(ValueError):
    """The spec file is unreadable or invalid. Nothing was created."""


class TargetExists(FileExistsError):
    """The token file already exists. It is never overwritten."""


@dataclass(frozen=True)
class Spec:
    """A validated provisioning spec."""

    parts: tuple[tuple[str, int], ...]
    machines: tuple[str, ...]
    zones: tuple[str, ...]
    identities: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Provisioned:
    """What a run created. ``tokens`` maps robot id to token and is hidden from ``repr``."""

    parts: tuple[str, ...]
    machines: tuple[str, ...]
    zones: tuple[str, ...]
    skipped: tuple[str, ...]
    tokens: Mapping[str, str] = field(repr=False)


def _identifier(value: object, what: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise SpecError(f"invalid {what}")
    return value


def _unique(items: Sequence[str], what: str) -> tuple[str, ...]:
    if len(set(items)) != len(items):
        raise SpecError(f"duplicate {what}")
    return tuple(items)


def _list(body: Mapping[str, object], key: str) -> list[object]:
    value = body.get(key)
    if not isinstance(value, list):
        raise SpecError(f"{key} must be a list")
    return value


def _entry(value: object, keys: frozenset[str], what: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise SpecError(f"{what} must have exactly the fields {sorted(keys)}")
    return value


def _stock(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _STOCK_MAX:
        raise SpecError("on_hand must be an integer from 0 to 1000000")
    return value


def parse_spec(body: object) -> Spec:
    """Validate a decoded spec strictly: unknown, missing or duplicate entries are errors."""
    if not isinstance(body, dict) or set(body) != _KEYS:
        raise SpecError(f"the spec must have exactly the keys {sorted(_KEYS)}")
    parts = [
        (
            _identifier(e["part_number"], "part number"),
            _stock(e["on_hand"]),
        )
        for e in (
            _entry(item, frozenset({"part_number", "on_hand"}), "part")
            for item in _list(body, "parts")
        )
    ]
    _unique([p for p, _ in parts], "part number")
    machines = _unique(
        [_identifier(m, "machine id") for m in _list(body, "machines")], "machine id"
    )
    zones = _unique([_identifier(z, "zone id") for z in _list(body, "zones")], "zone id")
    identities = []
    for item in _list(body, "identities"):
        entry = _entry(item, frozenset({"chassis", "robot_id"}), "identity")
        chassis = entry["chassis"]
        if not isinstance(chassis, str) or chassis not in ALLOWLIST:
            raise SpecError("unknown chassis")
        identities.append((chassis, _identifier(entry["robot_id"], "robot id")))
    _unique([f"{c}/{r}" for c, r in identities], "identity")
    return Spec(tuple(parts), machines, zones, tuple(identities))


def load_spec(path: Path) -> Spec:
    """Read and validate a spec file."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SpecError(f"cannot read the spec: {type(error).__name__}") from None
    return parse_spec(body)


class _Inventory(Protocol):
    def get(self, part_number: str) -> object | None: ...
    def add_part(self, part_number: str, on_hand: int) -> None: ...


class _Machines(Protocol):
    def add_machine(self, machine_id: str) -> None: ...


class _Zones(Protocol):
    def register(self, resources: tuple[str, ...]) -> None: ...


class _Identities(Protocol):
    def register(self, token_hash: str, chassis: str, robot_id: str) -> None: ...


def provision(
    spec: Spec,
    inventory: _Inventory,
    machines: _Machines,
    zones: _Zones,
    identities: _Identities,
) -> Provisioned:
    """Create what is missing. Existing rows are skipped and named in ``skipped``."""
    created_parts, created_machines, skipped = [], [], []
    tokens: dict[str, str] = {}
    for part_number, on_hand in spec.parts:
        if inventory.get(part_number) is not None:
            skipped.append(f"part:{part_number}")
            continue
        inventory.add_part(part_number, on_hand)
        created_parts.append(part_number)
    for machine_id in spec.machines:
        try:
            machines.add_machine(machine_id)
        except psycopg.errors.UniqueViolation:
            skipped.append(f"machine:{machine_id}")
        else:
            created_machines.append(machine_id)
    if spec.zones:
        zones.register(spec.zones)
    for chassis, robot_id in spec.identities:
        token = generate_token()
        try:
            identities.register(hash_token(token), chassis, robot_id)
        except psycopg.errors.UniqueViolation:
            skipped.append(f"identity:{robot_id}")
        else:
            tokens[robot_id] = token
    return Provisioned(
        tuple(created_parts), tuple(created_machines), spec.zones, tuple(skipped), tokens
    )


def write_tokens(path: Path, tokens: Mapping[str, str]) -> None:
    """Write tokens to a new file readable by the owner only. Never overwrites."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise TargetExists(path.name) from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(dict(tokens), handle, indent=2)


def main(argv: Sequence[str], environ: Mapping[str, str], stderr: TextIO) -> int:
    """Provision the database named by DATABASE_URL. Returns 0, or 2 on any failure."""
    if len(argv) != 2:
        stderr.write("usage: provision SPEC_FILE TOKENS_OUT_FILE\n")
        return 2
    spec_path, out_path = Path(argv[0]), Path(argv[1])
    try:
        if out_path.exists():
            raise TargetExists(out_path.name)
        spec = load_spec(spec_path)
        database = Database.from_environ(environ)
        result = provision(
            spec,
            InventoryRepository(database),
            TicketRepository(database),
            CorridorRepository(database),
            PostgresIdentityStore(database),
        )
        if result.tokens:
            write_tokens(out_path, result.tokens)
    except (SpecError, TargetExists, ValueError, psycopg.Error) as error:
        stderr.write(f"provision failed: {type(error).__name__}\n")
        return 2
    stderr.write(
        f"created {len(result.parts)} parts, {len(result.machines)} machines, "
        f"{len(spec.zones)} zones, {len(result.tokens)} identities; "
        f"skipped {len(result.skipped)}\n"
    )
    return 0


def run() -> int:
    """Process entry: real environment and standard error."""
    return main(sys.argv[1:], os.environ, sys.stderr)
