"""Migration entry points require a valid expected revision before opening a connection."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.schema import migrate


@pytest.mark.parametrize("revision", [-1, True, 1.5, "0"])
def test_invalid_expected_revision_does_not_connect(revision: object) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError, match="revision"):
        migrate(database, expected_revision=revision)  # type: ignore[arg-type]
    database.transaction.assert_not_called()


@pytest.mark.parametrize("target", [-1, True, 0, 99])
def test_invalid_target_revision_does_not_connect(target: int) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError, match="revision"):
        migrate(database, expected_revision=0, target_revision=target)
    database.transaction.assert_not_called()
