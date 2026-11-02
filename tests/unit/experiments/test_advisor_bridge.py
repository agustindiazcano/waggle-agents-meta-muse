"""The harness bridge from recorded cautions to fast-layer limits, and replay (ADR-064).

The bridge sits in waggle.experiments because waggle.control must not import governance.
"""

import math

import numpy as np

from waggle.control.types import Limit, Reason
from waggle.experiments.advisor_bridge import AdvisorBridge, fast_layer_limits
from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e1_rig import ControlRig, streams_for
from waggle.governance.caution import CautionAction, CautionConfig, CautionEvent
from waggle.governance.caution_limits import SpeedLimit
from waggle.governance.caution_log import CautionLog
from waggle.sim import engine, robots, scenarios, scripted
from waggle.sim.params import ROBOT_PARAMS, RobotKind

CFG = CautionConfig(max_window_ticks=400, h_max_ticks=200, n_max_holds=3)
CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]


def _event(
    action: CautionAction, cap: float | None, issue: int, window: int, request: str
) -> CautionEvent:
    return CautionEvent(
        "run", "carrier-0", issue, issue, issue + window, action, cap, None, request, "accepted"
    )


def _log(*events: CautionEvent) -> CautionLog:
    log = CautionLog(CFG)
    for event in events:
        log.submit(event, owner_robot="carrier-0", task_id="t1")
    return log


def test_speed_limits_become_advisor_limits() -> None:
    got = fast_layer_limits((SpeedLimit(0.5, "advisor", "a"), SpeedLimit(0.0, "advisor", "b")))
    assert got == (Limit(0.5, Reason.ADVISOR), Limit(0.0, Reason.ADVISOR))
    assert fast_layer_limits(()) == ()


def test_the_bridge_reads_the_active_cautions_of_one_robot() -> None:
    log = _log(
        _event(CautionAction.SLOW, 0.6, 10, 50, "a"), _event(CautionAction.HOLD, 0.0, 20, 5, "b")
    )
    bridge = AdvisorBridge(log, ["carrier-0", "carrier-1"])
    assert bridge(0, 5, 2.0) == ()
    assert bridge(0, 22, 2.0) == (Limit(0.6, Reason.ADVISOR), Limit(0.0, Reason.ADVISOR))
    assert bridge(0, 30, 2.0) == (Limit(0.6, Reason.ADVISOR),)
    assert bridge(1, 22, 2.0) == ()


def test_a_cap_above_the_class_maximum_is_lowered_to_it() -> None:
    log = _log(_event(CautionAction.SLOW, 5.0, 0, 50, "a"))
    assert AdvisorBridge(log, ["carrier-0"])(0, 1, 2.0) == (Limit(2.0, Reason.ADVISOR),)


def test_a_bad_class_maximum_fails_closed() -> None:
    log = _log(_event(CautionAction.SLOW, 0.5, 0, 50, "a"))
    assert AdvisorBridge(log, ["carrier-0"])(0, 1, math.nan) == (Limit(0.0, Reason.ADVISOR),)


def test_an_unknown_robot_index_has_no_limits() -> None:
    log = _log(_event(CautionAction.HOLD, 0.0, 0, 50, "a"))
    assert AdvisorBridge(log, ["carrier-0"])(3, 1, 2.0) == ()


def _run(bridge: AdvisorBridge | None, ticks: int = 400) -> tuple[engine.Engine, float]:
    config = BY_NAME["envelope_oracle"]
    fleet = robots.RobotFleet([RobotKind.CARRIER])
    driver = scripted.WaypointDriver(fleet, [[(35.0, 2.5)]], loop=False)
    rig = ControlRig(config, fleet, scenarios.load_map("A"), advisor=bridge)
    arrays = {
        **fleet.initial_arrays(np.array([[3.0, 2.5, 0.0]])),
        **driver.initial_arrays(),
        "human_pos": np.zeros((0, 2)),
    }
    sim = engine.Engine(
        7, arrays, [driver.system(), rig.system(), fleet.system()], streams_for(config, 1)
    )
    sim.run(ticks)
    return sim, rig.tally.limited_speed


def test_a_hold_stops_the_robot_and_two_identical_runs_have_equal_hashes() -> None:
    hold = _log(_event(CautionAction.HOLD, 0.0, 100, 200, "h1"))
    free_sim, _ = _run(None)
    first, _ = _run(AdvisorBridge(hold, ["carrier-0"]))
    second, _ = _run(AdvisorBridge(hold, ["carrier-0"]))
    assert first.state_hash() == second.state_hash()
    assert first.state_hash() != free_sim.state_hash()
    x_free = float(np.asarray(free_sim.state.arrays["robot_pose"])[0, 0])
    x_hold = float(np.asarray(first.state.arrays["robot_pose"])[0, 0])
    assert x_hold < x_free
    # During the hold the robot is at rest: sample a run that ends inside the window.
    inside, _ = _run(AdvisorBridge(hold, ["carrier-0"]), ticks=250)
    assert abs(float(np.asarray(inside.state.arrays["robot_speed"])[0])) < 1e-6


def test_a_replay_from_the_serialized_log_gives_the_same_hash() -> None:
    log = _log(
        _event(CautionAction.SLOW, 0.5, 40, 300, "s1"),
        _event(CautionAction.HOLD, 0.0, 150, 60, "h1"),
    )
    live, _ = _run(AdvisorBridge(log, ["carrier-0"]))
    replayed = CautionLog.from_jsonl(log.to_jsonl(), CFG)
    again, _ = _run(AdvisorBridge(replayed, ["carrier-0"]))
    assert live.state_hash() == again.state_hash()


def test_an_empty_log_gives_the_same_hash_as_no_advisor() -> None:
    none_sim, _ = _run(None)
    empty_sim, _ = _run(AdvisorBridge(CautionLog(CFG), ["carrier-0"]))
    assert none_sim.state_hash() == empty_sim.state_hash()


def test_the_advisor_never_raises_the_speed_of_a_run() -> None:
    slow = _log(_event(CautionAction.SLOW, 0.4, 0, 400, "s1"))
    _, free = _run(None)
    _, limited = _run(AdvisorBridge(slow, ["carrier-0"]))
    assert limited <= free + 1e-9
    assert limited < free
