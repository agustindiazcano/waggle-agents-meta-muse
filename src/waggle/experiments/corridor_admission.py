"""Simulator corridor admission and an explicit S03 variant, without persistence.

The original E1 scenario remains unchanged. This adapter runs after the driver and before
control and dynamics. Axis-aligned capacity-one zones use conservative footprint bounding
boxes; unknown poses deny every admission. All reservation state lives in simulator arrays.
"""

import math
from dataclasses import replace

import numpy as np

from waggle.coordination.corridors import (
    CorridorRequest,
    CorridorState,
    CorridorZone,
    ZoneObservation,
    ZoneToken,
    release_corridor,
    request_corridor,
)
from waggle.coordination.leases import LeaseState
from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e1_rig import ControlRig, streams_for
from waggle.experiments.s03_routes import plan_s03_routes
from waggle.sim import detector, engine, scenarios, scripted, state, world
from waggle.sim.params import RobotKind
from waggle.sim.robots import RobotFleet, footprint_corners


class CorridorAdmission:
    """Hold each robot until its complete route is granted, in stable robot order."""

    def __init__(
        self,
        fleet: RobotFleet,
        zones: tuple[world.Zone, ...],
        requests: tuple[CorridorRequest, ...],
        route_lengths: tuple[int, ...],
        lease_ticks: int,
    ) -> None:
        if len(requests) != fleet.count or len(route_lengths) != fleet.count:
            raise ValueError("one request and route length per robot is required")
        if type(lease_ticks) is not int or lease_ticks <= 0:
            raise ValueError("lease_ticks must be a positive integer")
        if tuple(r.holder for r in requests) != tuple(f"robot-{i}" for i in range(fleet.count)):
            raise ValueError("holders must match stable fleet indices")
        self.fleet = fleet
        self.zones = tuple(sorted(zones, key=lambda z: z.id))
        self.requests = requests
        self.route_lengths = route_lengths
        self.lease_ticks = lease_ticks
        self.bounds: list[tuple[float, float, float, float]] = []
        for zone in self.zones:
            xs, ys = zip(*zone.polygon.points, strict=True)
            bounds = (min(xs), min(ys), max(xs), max(ys))
            corners = {(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])}
            if zone.capacity != 1 or set(zone.polygon.points) != corners:
                raise ValueError("admission requires rectangular capacity-one zones")
            self.bounds.append(bounds)
        known = {z.id for z in self.zones}
        if len(known) != len(self.zones) or any(not set(r.resource_ids) <= known for r in requests):
            raise ValueError("duplicate or unknown corridor resource")

    def initial_arrays(self) -> dict[str, state.Array]:
        """Lease counters, owners, expiry and fault latches for snapshot and fork."""
        count = len(self.zones)
        return {
            "admission_owner": np.full(count, -1, dtype=np.int64),
            "admission_token": np.zeros(count, dtype=np.int64),
            "admission_expiry": np.zeros(count, dtype=np.int64),
            "admission_fault": np.zeros(count, dtype=np.int64),
            "admission_tick": np.zeros(count, dtype=np.int64),
        }

    def occupancy(self, sim: state.SimState) -> tuple[ZoneObservation, ...]:
        """Current trusted occupancy, conservatively including touching footprints."""
        poses = np.asarray(sim.arrays["robot_pose"], dtype=np.float64)
        if not np.all(np.isfinite(poses)):
            return tuple(ZoneObservation(z.id, sim.tick, None) for z in self.zones)
        footprints = [footprint_corners(p, *poses[i]) for i, p in enumerate(self.fleet.params)]
        observations: list[ZoneObservation] = []
        for zone, (x0, y0, x1, y1) in zip(self.zones, self.bounds, strict=True):
            occupants = tuple(
                f"robot-{i}"
                for i, points in enumerate(footprints)
                if points[:, 0].max() >= x0
                and points[:, 0].min() <= x1
                and points[:, 1].max() >= y0
                and points[:, 1].min() <= y1
            )
            observations.append(ZoneObservation(zone.id, sim.tick, occupants))
        return tuple(observations)

    def _read(self, sim: state.SimState) -> CorridorState:
        zones: list[CorridorZone] = []
        for j, zone in enumerate(self.zones):
            owner = int(sim.arrays["admission_owner"][j])
            request = self.requests[owner] if owner >= 0 else None
            lease = LeaseState(
                resource_id=zone.id,
                holder=request.holder if request else None,
                token=int(sim.arrays["admission_token"][j]),
                expires_tick=int(sim.arrays["admission_expiry"][j]) if request else None,
                observed_tick=int(sim.arrays["admission_tick"][j]),
            )
            zones.append(
                CorridorZone(
                    lease,
                    request.direction_for(zone.id) if request else None,
                    bool(sim.arrays["admission_fault"][j]),
                )
            )
        return CorridorState(tuple(zones))

    def _write(self, sim: state.SimState, current: CorridorState) -> None:
        holders = {r.holder: i for i, r in enumerate(self.requests)}
        for j, zone in enumerate(current.zones):
            sim.arrays["admission_owner"][j] = (
                holders[zone.lease.holder] if zone.lease.holder is not None else -1
            )
            sim.arrays["admission_token"][j] = zone.lease.token
            sim.arrays["admission_expiry"][j] = zone.lease.expires_tick or 0
            sim.arrays["admission_fault"][j] = int(zone.fault_occupied)
            sim.arrays["admission_tick"][j] = zone.lease.observed_tick

    def step(self, sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        """Reserve atomically, release only after parking, and deny motion on failure."""
        observations = self.occupancy(sim)
        current = self._read(sim)
        for i, request in enumerate(self.requests):
            done = int(sim.arrays["script_wp"][i]) >= self.route_lengths[i]
            if done:
                tokens = tuple(
                    ZoneToken(z.lease.resource_id, z.lease.token)
                    for z in current.zones
                    if z.lease.holder == request.holder
                )
                if tokens:
                    result = release_corridor(
                        current, request.holder, tokens, sim.tick, observations
                    )
                    current = result.state
                allowed = False
            else:
                result = request_corridor(
                    current, request, sim.tick, observations, self.lease_ticks
                )
                current, allowed = result.state, result.granted
            if not allowed:
                # Cancel queued motion as well as today's request. Dynamics still brake at
                # the declared deceleration; occupied expiry never clears a physical robot.
                sim.arrays["robot_pending"][i] = 0.0
                sim.arrays["robot_active"][i] = 0.0
        self._write(sim, current)


def build_s03_admission(
    seed: int, *, lease_ticks: int = 4000, admission_enabled: bool = True
) -> tuple[engine.Engine, CorridorAdmission, detector.Detector]:
    """Build the S03 admission variant with exterior staging and one-shot parking routes.

    This is a simulator integration fixture, implemented, not evaluated by E2. The fixed
    4000-tick lease is a test assumption, not automatic renewal or a persistence guarantee.
    """
    if type(admission_enabled) is not bool:
        raise ValueError("admission_enabled must be a boolean")
    original = scenarios.generate("S03", seed)
    box = scenarios.load_map(original.map_name)
    planned = plan_s03_routes(box)
    requests: list[CorridorRequest] = []
    for route in planned:
        request = route.plan.corridor_request
        if request is None:
            raise ValueError("S03 route must reserve its capacity-one corridor")
        requests.append(request)
    variant = replace(
        original,
        robots=(
            scenarios.RobotSpec(RobotKind.CARRIER, (3.0, 2.0, math.pi / 2), planned[0].waypoints),
            scenarios.RobotSpec(RobotKind.CARRIER, (9.0, 22.0, -math.pi), planned[1].waypoints),
        ),
        duration_ticks=3200,
    )
    config = BY_NAME["envelope_oracle"]
    sim, det = scenarios.build_engine(variant, streams_for(config, 2))
    fleet = RobotFleet([r.kind for r in variant.robots])
    driver = scripted.WaypointDriver(fleet, [r.route for r in variant.robots], loop=False)
    admission = CorridorAdmission(
        fleet,
        (box.zone("lane_1"),),
        tuple(requests),
        tuple(len(route.waypoints) for route in planned),
        lease_ticks,
    )
    sim.state.arrays.update(admission.initial_arrays())
    rig = ControlRig(config, fleet, box)
    sim.systems[0] = driver.system()
    sim.systems[1:1] = ([admission.step] if admission_enabled else []) + [rig.system()]
    return sim, admission, det
