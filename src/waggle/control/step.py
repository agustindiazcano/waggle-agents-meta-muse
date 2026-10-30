"""One control step: scan and odometry to tracks, then the limited command (ADR-026, ADR-027).

Pure function with explicit state. It reads no clock. Bad input or an exception stops the robot
with a reason, and the state is left as it was.
"""

import logging
import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from waggle.control import cpa, occlusion, perception, tracking
from waggle.control.arbiter import arbitrate
from waggle.control.limiter import EnvelopeMode, limit_command
from waggle.control.params import (
    DEFAULT_CONTROL_PARAMS,
    DEFAULT_CPA_PARAMS,
    DEFAULT_OCCLUSION_PARAMS,
    DEFAULT_PERCEPTION_PARAMS,
    ControlParams,
    CpaParams,
    OcclusionParams,
    PerceptionParams,
)
from waggle.control.tracking import Detection, TrackState
from waggle.control.types import ControlOutput, ControlRequest, Limit, Reason
from waggle.sim.observations import BeaconReport, LidarScan, RobotOdometry
from waggle.sim.params import DT, HUMAN_RADIUS, RobotParams

logger = logging.getLogger(__name__)

Points = NDArray[np.float64]


def _no_points() -> Points:
    return np.empty((0, 2), dtype=np.float64)


@dataclass(frozen=True)
class ControlInputs:
    """Everything one robot needs for one tick. Beacon positions are in the world frame."""

    request: ControlRequest
    params: RobotParams
    tick: int
    odometry: RobotOdometry | None
    scan: LidarScan | None
    beacons: tuple[BeaconReport, ...] = ()
    mode: EnvelopeMode = EnvelopeMode.SWEPT
    use_occlusion: bool = False
    use_cpa: bool = False


@dataclass(frozen=True)
class ControlState:
    """Tracks and the structure points of the last scan, in the world frame."""

    tracks: TrackState = field(default_factory=TrackState)
    structure_world: Points = field(default_factory=_no_points, compare=False)
    scan_tick: int | None = None


def _to_world(points: Points, odom: RobotOdometry) -> Points:
    c, s = math.cos(odom.theta), math.sin(odom.theta)
    return np.column_stack(
        [odom.x + c * points[:, 0] - s * points[:, 1], odom.y + s * points[:, 0] + c * points[:, 1]]
    )


def _to_robot(points: Points, odom: RobotOdometry) -> Points:
    c, s = math.cos(odom.theta), math.sin(odom.theta)
    dx, dy = points[:, 0] - odom.x, points[:, 1] - odom.y
    return np.column_stack([c * dx + s * dy, -s * dx + c * dy])


def _cluster_detection(world: Points, tick: int) -> Detection:
    centre = world.mean(axis=0)
    radius = float(np.max(np.hypot(world[:, 0] - centre[0], world[:, 1] - centre[1])))
    return Detection(float(centre[0]), float(centre[1]), radius, 0.0, tick)


def _beacon_detection(
    beacon: BeaconReport, human_clusters: list[Points], pp: PerceptionParams
) -> Detection | None:
    """A detection for a beacon, or None when a visible cluster already accounts for it."""
    reach = pp.beacon_sigma + HUMAN_RADIUS + pp.human_speed_bound * beacon.delay_ticks * DT
    here = np.array([beacon.x, beacon.y])
    for world in human_clusters:
        if float(np.min(np.hypot(world[:, 0] - here[0], world[:, 1] - here[1]))) <= reach:
            return None
    return Detection(
        beacon.x, beacon.y, HUMAN_RADIUS, pp.beacon_sigma, beacon.tick - beacon.delay_ticks
    )


def _perceive(state: ControlState, inputs: ControlInputs, pp: PerceptionParams) -> ControlState:
    scan, odom = inputs.scan, inputs.odometry
    assert scan is not None and odom is not None
    new_scan = scan.tick != state.scan_tick
    if not new_scan and not inputs.beacons:
        return state
    detections: list[Detection] = []
    human_clusters: list[Points] = []
    structure = state.structure_world
    if new_scan:
        others: list[Points] = []
        for cluster in perception.clusters_from_scan(scan, pp):
            world = _to_world(cluster.points, odom)
            if perception.is_human_candidate(cluster, pp):
                human_clusters.append(world)
                detections.append(_cluster_detection(world, scan.tick))
            else:
                others.append(world)
        structure = np.vstack(others) if others else _no_points()
    for beacon in inputs.beacons:
        detection = _beacon_detection(beacon, human_clusters, pp)
        if detection is not None:
            detections.append(detection)
    tracks = tracking.update_tracks(state.tracks, detections, inputs.tick, pp)
    return ControlState(tracks, structure, scan.tick if new_scan else state.scan_tick)


def _stop(inputs: ControlInputs, reason: Reason) -> ControlOutput:
    return arbitrate(inputs.request, inputs.params, [Limit(0.0, reason)])


def control_step(
    state: ControlState,
    inputs: ControlInputs,
    cp: ControlParams = DEFAULT_CONTROL_PARAMS,
    pp: PerceptionParams = DEFAULT_PERCEPTION_PARAMS,
    op: OcclusionParams = DEFAULT_OCCLUSION_PARAMS,
    cpap: CpaParams = DEFAULT_CPA_PARAMS,
) -> tuple[ControlState, ControlOutput]:
    """Limit one motion command. Missing or stale input gives a stop with its reason."""
    reason = perception.check_inputs(inputs.scan, inputs.odometry, inputs.tick, pp)
    if reason is not None:
        return state, _stop(inputs, reason)
    odom = inputs.odometry
    assert odom is not None
    try:
        new_state = _perceive(state, inputs, pp)
        human = _to_robot(tracking.track_points(new_state.tracks, inputs.tick, pp), odom)
        structure = _to_robot(new_state.structure_world, odom)
        extra: list[Limit] = []
        scan = inputs.scan
        assert scan is not None
        if inputs.use_occlusion:
            boundaries = occlusion.boundary_points(scan, pp, op)
            extra.append(
                occlusion.occlusion_limit(inputs.request, inputs.params, boundaries, cp, op)
            )
        if inputs.use_cpa:
            extra.append(
                cpa.cpa_limit(
                    inputs.request,
                    inputs.params,
                    odom,
                    new_state.tracks.tracks,
                    inputs.tick,
                    cp,
                    pp,
                    cpap,
                )
            )
        output = limit_command(
            inputs.request, inputs.params, human, structure, odom.speed, cp, inputs.mode, extra
        )
    except Exception:
        logger.exception("control step failed, stopping the robot")
        return state, _stop(inputs, Reason.INPUT_MISSING)
    return new_state, output
