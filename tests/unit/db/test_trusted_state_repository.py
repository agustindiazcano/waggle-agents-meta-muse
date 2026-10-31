"""Trusted tick and occupancy inputs fail before any database transaction opens."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.occupancy import TrustedStateRepository


@pytest.mark.parametrize("tick", [-1, True, 1.5, "3", 2**63])
def test_invalid_tick_does_not_connect(tick: object) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        TrustedStateRepository(database).advance_tick(tick)  # type: ignore[arg-type]
    database.transaction.assert_not_called()


@pytest.mark.parametrize(
    ("zone_id", "observed_tick", "occupants"),
    [
        ("", 1, ()),
        ("dock", -1, ()),
        ("dock", True, ()),
        ("dock", 1, ("a", "a")),
        ("dock", 1, ("bad id",)),
        ("dock", 1, "robot-0"),
    ],
)
def test_invalid_observation_does_not_connect(
    zone_id: str, observed_tick: int, occupants: object
) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        TrustedStateRepository(database).record(
            zone_id,
            observed_tick,
            occupants,  # type: ignore[arg-type]
        )
    database.transaction.assert_not_called()


@pytest.mark.parametrize("zone_ids", [(), ("dock", "dock"), ("",)])
def test_invalid_observe_request_does_not_connect(zone_ids: tuple[str, ...]) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        TrustedStateRepository(database).observe(zone_ids, 0)
    database.transaction.assert_not_called()
