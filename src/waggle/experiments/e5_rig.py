"""E1 control rig that also counts widening ticks and the minimum separation (E5).

``E5Rig._step`` repeats ``ControlRig._step`` and adds two measures: a second ``control_step``
with no advisor limits, to count ticks where the advisor would have raised the speed (expected
0 by construction), and the smallest gap to a human or another robot. ``test_e5_rig.py`` checks
that, with no advisor, it gives the same run as the E1 rig.
"""

import math
import time
from typing import Any

import numpy as np

from waggle.control.step import ControlInputs, control_step
from waggle.control.types import ControlRequest, Reason
from waggle.experiments.advisor_bridge import AdvisorBridge
from waggle.experiments.e1_config import E1Config
from waggle.experiments.e1_rig import ControlRig
from waggle.sim import detector, robots, sensors, world
from waggle.sim.params import HUMAN_RADIUS
from waggle.sim.robots import footprint_corners


class E5Rig(ControlRig):
    """Extended rig tracking widening violations and minimum separation across the run."""

    def __init__(
        self,
        config: E1Config,
        fleet: robots.RobotFleet,
        box: world.World,
        advisor: AdvisorBridge | None = None,
    ) -> None:
        super().__init__(config, fleet, box, advisor=advisor)
        self.widening_ticks = 0
        self.min_separation_m = math.inf
        self.last_reasons: list[str | None] = [None] * fleet.count
        self.last_limits_hit: list[tuple[str, ...] | None] = [None] * fleet.count

    def occluded(self, robot_index: int) -> bool | None:
        """Whether the occlusion limit was hit at the robot's last step, from the fast layer.

        None (unknown) before the first step, and when the run has no occlusion layer: the
        absence of a limit then says nothing about occlusion.
        """
        hit = self.last_limits_hit[robot_index]
        if hit is None or not self.config.occlusion:
            return None
        return Reason.OCCLUSION.value in hit

    def _step(self, sim: Any, rngs: dict[str, np.random.Generator]) -> None:
        tick = sim.tick
        poses = np.asarray(sim.arrays["robot_pose"], dtype=np.float64)
        speeds = np.asarray(sim.arrays["robot_speed"], dtype=np.float64)
        active = np.asarray(sim.arrays["robot_active"], dtype=np.float64)
        pending = np.asarray(sim.arrays["robot_pending"], dtype=np.float64)
        humans = np.asarray(sim.arrays["human_pos"], dtype=np.float64).reshape(-1, 2)
        self.history.append(humans.copy())
        discs = np.column_stack([humans, np.full(len(humans), HUMAN_RADIUS)])
        refresh = sensors.lidar_due(tick)
        commands = np.zeros((self.fleet.count, 2))

        # Update minimum separation across all robots and humans
        for i in range(self.fleet.count):
            fp_i = footprint_corners(self.params[i], *poses[i])
            for h in humans:
                gap_h = float(detector.point_polygon_distance(h, fp_i)) - HUMAN_RADIUS
                self.min_separation_m = min(self.min_separation_m, gap_h)
            for j in range(i + 1, self.fleet.count):
                gap_r = float(
                    detector.polygon_distance(fp_i, footprint_corners(self.params[j], *poses[j]))
                )
                self.min_separation_m = min(self.min_separation_m, gap_r)

        for i in range(self.fleet.count):
            if refresh:
                self.scans[i] = self._scan(i, tick, poses, discs, rngs)
            slot = (tick + int(self.fleet.delay[i])) % self.fleet.ring
            requested = pending[i, slot]
            odometry = None
            if f"robots/{i}" in rngs:
                odometry = sensors.odometry(
                    tick,
                    i,
                    poses[i],
                    float(speeds[i]),
                    self._yaw_rate(i, float(speeds[i]), float(active[i, 1])),
                    self.noise,
                    rngs[f"robots/{i}"],
                )
            beacons = (
                sensors.beacon_reports(
                    tick,
                    i,
                    poses[i, :2],
                    list(self.history),
                    self.beacon_config,
                    rngs[f"beacons/{i}"],
                )
                if self.config.beacons
                else ()
            )
            inputs = ControlInputs(
                request=ControlRequest(float(requested[0]), float(requested[1])),
                params=self.params[i],
                tick=tick,
                odometry=odometry,
                scan=self.scans[i],
                beacons=beacons,
                mode=self.config.mode,
                use_occlusion=self.config.occlusion,
                use_cpa=self.config.cpa,
                map_segments=self.static,
            )
            caution = (
                self.advisor(i, tick, self.params[i].max_speed) if self.advisor is not None else ()
            )

            # Widening check against C0 baseline for the exact same state and inputs
            if caution:
                _, out_c0 = control_step(self.states[i], inputs, advisor_limits=())
                _, out_test = control_step(self.states[i], inputs, advisor_limits=caution)
                if abs(out_test.speed) > abs(out_c0.speed) + 1e-9:
                    self.widening_ticks += 1

            started = time.perf_counter_ns()
            self.states[i], out = control_step(self.states[i], inputs, advisor_limits=caution)
            self.tally.latency_us.append((time.perf_counter_ns() - started) / 1000.0)
            self.tally.control_calls += 1
            commands[i] = (out.speed, out.turn)
            self.last_reasons[i] = out.reason.value
            self.last_limits_hit[i] = tuple(r.value for r in out.limits_hit)
            self.tally.requested_speed += abs(float(requested[0]))
            self.tally.limited_speed += abs(out.speed)
            self._count_stop(
                i, float(requested[0]), out.speed, out.reason.value, humans, poses[i, :2]
            )
        self.fleet.issue(sim, commands)
