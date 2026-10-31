"""Cloud-only: the simulator bridge feeds the real trusted store, and a release reads it."""

import pytest

from waggle.coordination.corridors import CorridorRequest, Direction
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.occupancy import TrustedStateRepository
from waggle.experiments.corridor_admission import build_s03_admission
from waggle.experiments.sim_bridge import SimTrustedBridge

pytestmark = pytest.mark.heavy


def test_stored_observations_equal_the_simulator_derivation_every_step(
    database: Database,
) -> None:
    sim, admission, _ = build_s03_admission(7)
    zone_ids = tuple(z.id for z in admission.zones)
    CorridorRepository(database).register(zone_ids)
    state = TrustedStateRepository(database)
    bridge = SimTrustedBridge(state, admission)
    for _ in range(30):
        sim.step()
        bridge.publish(sim.state)
        assert state.now_tick() == sim.state.tick
        assert state.observe(zone_ids, sim.state.tick) == admission.occupancy(sim.state)


def test_a_zone_with_a_robot_in_it_cannot_be_released_from_published_state(
    database: Database,
) -> None:
    sim, admission, _ = build_s03_admission(7)
    zone_ids = tuple(z.id for z in admission.zones)
    corridors = CorridorRepository(database)
    corridors.register(zone_ids)
    state = TrustedStateRepository(database)
    bridge = SimTrustedBridge(state, admission)
    sim.run(1)
    bridge.publish(sim.state)
    granted = corridors.reserve(
        CorridorRequest("robot-0", (zone_ids[0],), Direction.FORWARD),
        sim.state.tick,
        state.observe((zone_ids[0],), sim.state.tick),
    )
    assert granted.granted
    sim.state.arrays["robot_pose"][0] = [3.0, 4.6, 0.0]
    bridge.publish(sim.state)
    refused = corridors.release(
        "robot-0", granted.tokens, sim.state.tick, state.observe((zone_ids[0],), sim.state.tick)
    )
    assert not refused.granted
