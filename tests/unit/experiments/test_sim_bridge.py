"""The simulator bridge publishes the tick and conservative occupancy to a trusted writer."""

import pytest

from waggle.experiments.corridor_admission import build_s03_admission
from waggle.experiments.sim_bridge import SimTrustedBridge


class FakeWriter:
    def __init__(self, *, regress: bool = False, stale: bool = False) -> None:
        self.regress = regress
        self.stale = stale
        self.calls: list[tuple[object, ...]] = []

    def advance_tick(self, tick: int) -> None:
        if self.regress:
            raise ValueError("tick cannot move backwards")
        self.calls.append(("tick", tick))

    def record(self, zone_id: str, observed_tick: int, occupants: tuple[str, ...] | None) -> bool:
        self.calls.append(("record", zone_id, observed_tick, occupants))
        return not self.stale


def test_publish_writes_the_tick_before_each_zone_observation() -> None:
    sim, admission, _ = build_s03_admission(7)
    sim.run(5)
    writer = FakeWriter()
    written = SimTrustedBridge(writer, admission).publish(sim.state)
    zone_ids = [z.id for z in admission.zones]
    assert writer.calls[0] == ("tick", sim.state.tick)
    assert [c[1] for c in writer.calls[1:]] == zone_ids
    assert all(c[2] == sim.state.tick for c in writer.calls[1:])
    assert written == len(zone_ids)


def test_published_occupants_match_the_simulator_derivation() -> None:
    sim, admission, _ = build_s03_admission(7)
    sim.state.arrays["robot_pose"][0] = [3.0, 4.6, 0.0]
    writer = FakeWriter()
    SimTrustedBridge(writer, admission).publish(sim.state)
    expected = admission.occupancy(sim.state)
    assert [c[3] for c in writer.calls[1:]] == [o.occupants for o in expected]
    assert writer.calls[1][3] == ("robot-0",)


def test_an_unknown_pose_is_published_as_unknown_not_clear() -> None:
    sim, admission, _ = build_s03_admission(7)
    sim.state.arrays["robot_pose"][1, 0] = float("nan")
    writer = FakeWriter()
    SimTrustedBridge(writer, admission).publish(sim.state)
    assert writer.calls[1][3] is None


def test_a_tick_regression_stops_before_any_observation() -> None:
    sim, admission, _ = build_s03_admission(7)
    writer = FakeWriter(regress=True)
    with pytest.raises(ValueError, match="backwards"):
        SimTrustedBridge(writer, admission).publish(sim.state)
    assert writer.calls == []


def test_stale_observations_are_not_counted_as_written() -> None:
    sim, admission, _ = build_s03_admission(7)
    assert SimTrustedBridge(FakeWriter(stale=True), admission).publish(sim.state) == 0


def test_publishing_every_step_tracks_the_simulator_tick() -> None:
    sim, admission, _ = build_s03_admission(7)
    writer = FakeWriter()
    bridge = SimTrustedBridge(writer, admission)
    for _ in range(10):
        sim.step()
        bridge.publish(sim.state)
    ticks = [c[1] for c in writer.calls if c[0] == "tick"]
    assert ticks == list(range(sim.state.tick - 9, sim.state.tick + 1))
