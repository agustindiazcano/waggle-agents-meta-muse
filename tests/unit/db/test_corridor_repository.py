"""Invalid provision and effect inputs fail before a database transaction."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository


@pytest.mark.parametrize("resources", [(), ("lane", "lane"), ("",)])
def test_invalid_resource_registration_does_not_connect(resources: tuple[str, ...]) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        CorridorRepository(database).register(resources)
    database.transaction.assert_not_called()


def test_empty_event_credentials_deny_without_connecting() -> None:
    database = MagicMock(spec=Database)
    result = CorridorRepository(database).record_event("event-1", "robot-0", (), 0, "move")
    assert not result.accepted and not result.replayed
    database.transaction.assert_not_called()
