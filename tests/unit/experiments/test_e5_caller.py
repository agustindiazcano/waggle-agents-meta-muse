"""E5 caller: facts read from the rig and sim, context-change rule, advisor failure."""

from dataclasses import replace
from typing import Any

import pytest

from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e1_rig import streams_for
from waggle.experiments.e5_caller import AdvisorCaller, context_changed, extract_facts
from waggle.experiments.e5_rig import E5Rig
from waggle.governance.advisor_input import TrustedFacts
from waggle.governance.caution import CautionAction, CautionConfig, CautionEvent
from waggle.governance.caution_log import CautionLog
from waggle.llm.advisor_runtime import AdvisorResult
from waggle.llm.errors import ProviderError
from waggle.sim import robots, scenarios

SEED = 419688070
CONFIG = CautionConfig(max_window_ticks=100, h_max_ticks=50, n_max_holds=3)


def _world() -> tuple[Any, Any, Any, Any]:
    scenario = scenarios.generate("S01", SEED)
    box = scenarios.load_map(scenario.map_name)
    sim, _det = scenarios.build_engine(
        scenario, streams_for(BY_NAME["envelope_oracle"], len(scenario.robots))
    )
    fleet = robots.RobotFleet(
        [r.kind for r in scenario.robots], load_raised=[r.load_raised for r in scenario.robots]
    )
    return scenario, box, sim, fleet


def _facts(**over: Any) -> TrustedFacts:
    base = TrustedFacts(
        robot_id="robot-0",
        chassis="forklift",
        speed=0.5,
        active_reasons=("REQUEST",),
        zone="z",
        task_step=None,
        nearest_distance=5.0,
        occluded=None,
        geofences=None,
        lease_holders=None,
    )
    return replace(base, **over)


def test_state_that_is_not_exposed_is_unknown_not_a_default() -> None:
    scenario, box, sim, _fleet = _world()
    facts = extract_facts(sim, 0, "robot-0", scenario, box, None, occluded=None)
    assert facts.task_step is None
    assert facts.geofences is None
    assert facts.lease_holders is None
    assert facts.occluded is None


def test_occluded_is_taken_from_the_argument_not_fixed() -> None:
    scenario, box, sim, _fleet = _world()
    seen = {
        value: extract_facts(sim, 0, "robot-0", scenario, box, None, occluded=value).occluded
        for value in (True, False, None)
    }
    assert seen == {True: True, False: False, None: None}


def test_speed_nearest_distance_and_reason_come_from_the_state() -> None:
    scenario, box, sim, _fleet = _world()
    facts = extract_facts(sim, 0, "robot-0", scenario, box, "cpa", occluded=None)
    assert facts.active_reasons == ("cpa",)
    assert facts.speed == pytest.approx(float(sim.state.arrays["robot_speed"][0]), abs=0.01)
    assert facts.nearest_distance >= 0.0
    assert facts.chassis == scenario.robots[0].kind.value


def test_rig_reports_occlusion_unknown_before_the_first_step_and_when_the_layer_is_off() -> None:
    scenario, box, _sim, fleet = _world()
    with_occ = E5Rig(BY_NAME["envelope_occlusion_cpa_lidar_beacons"], fleet, box)
    assert with_occ.occluded(0) is None
    without = E5Rig(BY_NAME["envelope_oracle"], fleet, box)
    without.last_limits_hit[0] = ()
    assert without.occluded(0) is None
    assert len(scenario.robots) >= 1


def test_rig_reports_occlusion_from_the_limits_the_fast_layer_hit() -> None:
    _scenario, box, _sim, fleet = _world()
    rig = E5Rig(BY_NAME["envelope_occlusion_cpa_lidar_beacons"], fleet, box)
    rig.last_limits_hit[0] = ("occlusion", "cpa")
    assert rig.occluded(0) is True
    rig.last_limits_hit[0] = ("cpa",)
    assert rig.occluded(0) is False


def test_threshold_has_no_default() -> None:
    with pytest.raises(TypeError):
        context_changed(_facts(), _facts())  # type: ignore[call-arg]


def test_context_change_rules() -> None:
    near = 3.0
    assert context_changed(_facts(), None, near_threshold_m=near)
    assert not context_changed(_facts(), _facts(), near_threshold_m=near)
    assert context_changed(_facts(zone="y"), _facts(), near_threshold_m=near)
    assert context_changed(_facts(active_reasons=("cpa",)), _facts(), near_threshold_m=near)
    assert context_changed(_facts(nearest_distance=2.9), _facts(), near_threshold_m=near)
    assert not context_changed(
        _facts(nearest_distance=2.9), _facts(nearest_distance=0.5), near_threshold_m=near
    )


def test_the_threshold_argument_is_used() -> None:
    a, b = _facts(nearest_distance=4.0), _facts(nearest_distance=6.0)
    assert not context_changed(a, b, near_threshold_m=3.0)
    assert context_changed(a, b, near_threshold_m=5.0)


class _Advisor:
    def __init__(self, log: CautionLog, *, fail: bool = False) -> None:
        self.ticks: list[tuple[str, int]] = []
        self.log = log
        self.fail = fail

    def advise(self, facts: TrustedFacts, *, tick: int, **_kw: Any) -> AdvisorResult:
        self.ticks.append((facts.robot_id, tick))
        if self.fail:
            raise ProviderError("down")
        return AdvisorResult(status="accepted", limits=())


def _caller(advisor: _Advisor, **over: Any) -> AdvisorCaller:
    args: dict[str, Any] = {
        "robot_ids": ("robot-0", "robot-1"),
        "run_id": "run-x",
        "near_threshold_m": 3.0,
        "trigger_ticks": None,
    }
    args.update(over)
    return AdvisorCaller(advisor, **args)


def test_the_advisor_is_called_at_tick_zero_and_only_when_the_context_changed() -> None:
    scenario, box, sim, fleet = _world()
    rig = E5Rig(BY_NAME["envelope_oracle"], fleet, box)
    advisor = _Advisor(CautionLog(CONFIG))
    caller = _caller(advisor, robot_ids=tuple(f"robot-{i}" for i in range(len(scenario.robots))))
    for tick in range(3):
        caller.step(sim=sim, tick=tick, rig=rig, scenario=scenario, box=box, fleet=fleet)
    assert {t for _, t in advisor.ticks} == {0}
    assert caller.advisor_calls == len(scenario.robots)


def test_trigger_ticks_override_the_context_rule() -> None:
    scenario, box, sim, fleet = _world()
    rig = E5Rig(BY_NAME["envelope_oracle"], fleet, box)
    advisor = _Advisor(CautionLog(CONFIG))
    ids = tuple(f"robot-{i}" for i in range(len(scenario.robots)))
    caller = _caller(advisor, robot_ids=ids, trigger_ticks=(1,))
    for tick in range(3):
        caller.step(sim=sim, tick=tick, rig=rig, scenario=scenario, box=box, fleet=fleet)
    assert {t for _, t in advisor.ticks} == {1}


def test_an_advisor_failure_is_counted_and_the_limits_in_force_are_kept() -> None:
    scenario, box, sim, fleet = _world()
    rig = E5Rig(BY_NAME["envelope_oracle"], fleet, box)
    log = CautionLog(CONFIG)
    log.submit(
        CautionEvent(
            run_id="run-x",
            robot_id="robot-0",
            issue_tick=0,
            effective_tick=0,
            expiry_tick=50,
            action=CautionAction.SLOW,
            speed_cap=0.2,
            code=None,
            call_request_id="seed-1",
            validator_verdict="accepted",
        ),
        owner_robot="robot-0",
        task_id="t",
    )
    advisor = _Advisor(log, fail=True)
    ids = tuple(f"robot-{i}" for i in range(len(scenario.robots)))
    caller = _caller(advisor, robot_ids=ids)
    caller.step(sim=sim, tick=0, rig=rig, scenario=scenario, box=box, fleet=fleet)
    assert len(log.events) == 1
    assert caller.failures == len(scenario.robots)
    assert caller.rejected.get("advisor_error", 0) == len(scenario.robots)
