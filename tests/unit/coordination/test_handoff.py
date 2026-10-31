"""Physical handoff admission must deny stale authority or untrusted occupancy."""

from dataclasses import replace

import pytest

from waggle.coordination.corridors import CorridorZone, Direction, ZoneObservation, ZoneToken
from waggle.coordination.handoff import authorize_handoff
from waggle.coordination.leases import LeaseState
from waggle.coordination.task_model import TaskCredential, TaskRecord, TaskState


def test_current_matching_credentials_and_occupancy_allow_handoff() -> None:
    task = TaskRecord("delivery", TaskState.EXECUTING, 1, 1, "robot", 10, 0)
    zone = CorridorZone(LeaseState("dock", 2, "robot", 10, 0), Direction.FORWARD)
    assert authorize_handoff(
        task,
        TaskCredential("delivery", "robot", 1),
        zone,
        ZoneToken("dock", 2),
        ZoneObservation("dock", 1, ("robot",)),
        1,
    )


@pytest.mark.parametrize(
    "failure",
    [
        "task_token",
        "zone_token",
        "other_occupant",
        "stale",
        "unknown",
        "wrong_zone",
        "fault",
        "expired",
    ],
)
def test_missing_or_stale_authority_and_occupancy_deny_handoff(failure: str) -> None:
    task = TaskRecord("delivery", TaskState.EXECUTING, 1, 1, "robot", 10, 0)
    credential = TaskCredential("delivery", "robot", 2 if failure == "task_token" else 1)
    zone = CorridorZone(
        LeaseState("dock", 2, "robot", 10, 0), Direction.FORWARD, failure == "fault"
    )
    token = ZoneToken(
        "other" if failure == "wrong_zone" else "dock", 3 if failure == "zone_token" else 2
    )
    observation = ZoneObservation(
        "dock",
        0 if failure == "stale" else 1,
        None
        if failure == "unknown"
        else (("intruder",) if failure == "other_occupant" else ("robot",)),
    )
    if failure == "expired":
        task = replace(task, expires_tick=1)
    assert not authorize_handoff(task, credential, zone, token, observation, 1)


@pytest.mark.parametrize("tick", [True, -1, 10])
def test_invalid_or_expired_tick_denies(tick: int) -> None:
    task = TaskRecord("delivery", TaskState.EXECUTING, 1, 1, "robot", 10, 0)
    zone = CorridorZone(LeaseState("dock", 2, "robot", 10, 0), Direction.FORWARD)
    assert not authorize_handoff(
        task,
        TaskCredential("delivery", "robot", 1),
        zone,
        ZoneToken("dock", 2),
        ZoneObservation("dock", 1, ("robot",)),
        tick,
    )


def test_zone_expiry_denies_even_if_task_is_live() -> None:
    task = TaskRecord("delivery", TaskState.EXECUTING, 1, 1, "robot", 10, 0)
    zone = CorridorZone(LeaseState("dock", 2, "robot", 1, 0), Direction.FORWARD)
    assert not authorize_handoff(
        task,
        TaskCredential("delivery", "robot", 1),
        zone,
        ZoneToken("dock", 2),
        ZoneObservation("dock", 1, ("robot",)),
        1,
    )


def test_out_of_range_tick_denies() -> None:
    task = TaskRecord("delivery", TaskState.EXECUTING, 1, 1, "robot", 10, 0)
    zone = CorridorZone(LeaseState("dock", 2, "robot", 10, 0), Direction.FORWARD)
    assert not authorize_handoff(
        task,
        TaskCredential("delivery", "robot", 1),
        zone,
        ZoneToken("dock", 2),
        ZoneObservation("dock", 1, ("robot",)),
        2**63,
    )
