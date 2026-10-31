"""The S03 development seed has a window where robot-0 is alone in the corridor zone.

The cloud handoff scenario depends on this fact. This test keeps it checkable without a
database, so a simulator change shows up here first.
"""

from waggle.experiments.corridor_admission import build_s03_admission


def test_robot_0_is_alone_in_the_zone_early_and_not_at_the_start() -> None:
    sim, admission, _ = build_s03_admission(7)
    assert admission.occupancy(sim.state)[0].occupants == ()
    alone = None
    for _ in range(200):
        sim.step()
        if admission.occupancy(sim.state)[0].occupants == ("robot-0",):
            alone = sim.state.tick
            break
    assert alone is not None and alone > 1
