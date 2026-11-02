"""Cloud-only: the provisioning script against PostgreSQL (ADR-056)."""

from pathlib import Path

import pytest

from waggle.db.compatibility import CompatibilityRepository
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.identities import PostgresIdentityStore
from waggle.db.inventory import InventoryRepository, PartStock
from waggle.db.tickets import TicketRepository
from waggle.mcp_server.identity import hash_token
from waggle.provisioning import SpecError, load_spec, parse_spec, provision

pytestmark = pytest.mark.heavy

ROOT = Path(__file__).resolve().parents[3]


def _run(database: Database) -> dict[str, str]:
    result = provision(
        load_spec(ROOT / "data" / "provision" / "example.json"),
        InventoryRepository(database),
        TicketRepository(database),
        CorridorRepository(database),
        PostgresIdentityStore(database),
        CompatibilityRepository(database),
    )
    return dict(result.tokens)


def test_the_example_spec_provisions_a_fresh_database_and_a_rerun_changes_nothing(
    database: Database,
) -> None:
    tokens = _run(database)
    assert set(tokens) == {"C1", "C2", "MAINT-1"}
    inventory = InventoryRepository(database)
    assert inventory.get("BRG-6204") == PartStock("BRG-6204", 10, 0)
    record = PostgresIdentityStore(database).lookup(hash_token(tokens["C1"]))
    assert record is not None and (record.chassis, record.robot_id) == ("carrier", "C1")
    assert {z.lease.resource_id for z in CorridorRepository(database).snapshot().zones} == {
        "Z1",
        "Z2",
    }
    compatibility = CompatibilityRepository(database)
    assert compatibility.exists("C1", "BRG-6204")
    assert not compatibility.exists("C1", "SEAL-08")
    assert _run(database) == {}
    assert compatibility.count() == 2
    assert inventory.get("BRG-6204") == PartStock("BRG-6204", 10, 0)


def test_a_spec_with_a_row_for_an_unknown_machine_creates_nothing(database: Database) -> None:
    spec = parse_spec(
        {
            "parts": [{"part_number": "P-1", "on_hand": 1}],
            "machines": ["M-1"],
            "zones": [],
            "identities": [],
            "compatibility": [{"machine_id": "GHOST", "part_number": "P-1"}],
        }
    )
    with pytest.raises(SpecError):
        provision(
            spec,
            InventoryRepository(database),
            TicketRepository(database),
            CorridorRepository(database),
            PostgresIdentityStore(database),
            CompatibilityRepository(database),
        )
    assert InventoryRepository(database).get("P-1") is None
    assert not TicketRepository(database).has_machine("M-1")
