"""Pure admission check for a physical handoff at a capacity-one zone."""

from waggle.coordination.corridors import CorridorZone, ZoneObservation, ZoneToken
from waggle.coordination.leases import check_token
from waggle.coordination.task_model import TaskCredential, TaskRecord, TaskState, worker_transition


def authorize_handoff(
    task: TaskRecord,
    credential: TaskCredential,
    zone: CorridorZone,
    token: ZoneToken,
    observation: ZoneObservation,
    now_tick: int,
) -> bool:
    """Check current task, zone and occupancy evidence without performing an effect.

    The caller must establish the trust of identity and observations and repeat this
    check inside the transaction holding the relevant rows. This is not authority
    to perform a later effect based on an unlocked snapshot.
    """
    if type(now_tick) is not int or now_tick < 0:
        return False
    if (
        credential.task_id != task.task_id
        or task.state != TaskState.EXECUTING
        or credential.worker_id != zone.lease.holder
        or token.resource_id != zone.lease.resource_id
        or observation.resource_id != zone.lease.resource_id
        or observation.observed_tick != now_tick
        or observation.occupants != (credential.worker_id,)
        or zone.fault_occupied
    ):
        return False
    if not check_token(zone.lease, credential.worker_id, token.token, now_tick):
        return False
    return worker_transition(task, credential, TaskState.DONE, now_tick) is not None
