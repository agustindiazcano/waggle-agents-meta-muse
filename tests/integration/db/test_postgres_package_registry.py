"""Cloud-only checks of the package id registry (revision 12)."""

import psycopg.errors
import pytest
from postgres_support import isolated_database

from waggle.db.connection import Database
from waggle.db.packages import PackageRegistry
from waggle.db.schema import current_revision, migrate
from waggle.experiments.sim_motion import packages_match
from waggle.sim import scenarios

pytestmark = pytest.mark.heavy


def test_revision_twelve_upgrade_adds_an_empty_registry() -> None:
    with isolated_database() as db:
        assert migrate(db, expected_revision=0, target_revision=11) == 11
        assert migrate(db, expected_revision=11, target_revision=12) == 12
        assert current_revision(db) == 12
        assert PackageRegistry(db).count() == 0


def test_a_registered_id_is_found_and_an_unregistered_one_is_not(database: Database) -> None:
    registry = PackageRegistry(database)
    registry.add("pk-1", source="scenario-S01")
    assert registry.has("pk-1") and not registry.has("pk-2")
    assert registry.count() == 1


def test_a_duplicate_id_is_refused_and_the_database_checks_the_id_text(
    database: Database,
) -> None:
    registry = PackageRegistry(database)
    registry.add("pk-1")
    with pytest.raises(psycopg.errors.UniqueViolation):
        registry.add("pk-1")
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction() as connection:
        connection.execute("INSERT INTO packages (package_id) VALUES ('bad id')")


def test_registry_ids_match_the_simulator_package_ids(database: Database) -> None:
    registry = PackageRegistry(database)
    scenario = scenarios.with_packages(scenarios.generate("S01", 3), 2)
    model = scenarios.package_model(scenario)
    for package_id in model.package_ids:
        registry.add(package_id)
    assert registry.ids() == tuple(sorted(model.package_ids))
    assert packages_match(registry, model) is True
    registry.add("pk-extra")
    assert packages_match(registry, model) is False
