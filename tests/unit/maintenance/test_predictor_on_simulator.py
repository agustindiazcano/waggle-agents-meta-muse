"""The predictor against the simulator's telemetry: planted, blind and healthy machines.

The truth (failure tick) comes from simulator state and goes to the scorer only. The predictor
sees ``Reading`` objects built from numbers. Tests may import both sides; the packages may not
import each other.
"""

import dataclasses
from collections.abc import Callable

import pytest

from waggle.maintenance.predictor import Assessment, Predictor, Reading, load_params
from waggle.maintenance.scoring import MachineScore, Outcome, score
from waggle.sim import machines, telemetry
from waggle.sim.params import DT

SIM = machines.load_params()
NOISE = telemetry.load_noise()
PRED = load_params()
STRIDE = machines.STRIDE_TICKS
HORIZON_S = 3200
ONSET_S = 400.0


def _with(
    healthy: float = 0.0, effects: machines.EffectsParams | None = None
) -> machines.DegradationParams:
    wear = dataclasses.replace(
        SIM.wear, healthy_probability=healthy, onset_min_s=ONSET_S, onset_max_s=ONSET_S
    )
    return dataclasses.replace(SIM, wear=wear, effects=effects or SIM.effects)


def _as_reading(sample: telemetry.TelemetrySample) -> Reading:
    return Reading(
        sample.machine_id,
        sample.tick,
        sample.temperature,
        sample.vibration,
        sample.current,
        sample.load,
    )


def run_machine(
    seed: int,
    params: machines.DegradationParams,
    mode: int,
    decide: Callable[[Assessment], bool] = lambda a: a.flag,
) -> MachineScore:
    """Run one machine to its failure or the horizon and score the first alert."""
    eng = telemetry.build_engine(seed, 1, params, NOISE, modes=[mode])
    predictor = Predictor(PRED)
    first_alert: int | None = None
    fail: int | None = None
    for _ in range(int(HORIZON_S / (STRIDE * DT))):
        eng.engine.run(STRIDE)
        sample = telemetry.read(eng)[0]
        if first_alert is None and decide(predictor.update(_as_reading(sample))):
            first_alert = sample.tick
        failed = int(eng.engine.state.arrays["machine_fail_tick"][0])  # truth, scorer only
        if failed >= 0:
            fail = failed
            break
    onset = int(eng.engine.state.arrays["machine_onset_tick"][0])
    return score(fail, first_alert, onset_tick=None if onset < 0 else onset)


@pytest.mark.parametrize("mode", [machines.BEARING, machines.LUBE, machines.OFFSET])
def test_a_planted_failure_is_detected_before_it_happens(mode: int) -> None:
    result = run_machine(21, _with(), mode)
    assert result.outcome is Outcome.DETECTED
    assert result.lead_ticks is not None and result.lead_ticks > 0
    assert result.detection_delay_ticks is not None and result.detection_delay_ticks >= 0


def test_a_blind_predictor_is_reported_as_missed_not_detected() -> None:
    result = run_machine(21, _with(), machines.BEARING, decide=lambda a: False)
    assert result.outcome is Outcome.MISSED
    assert result.lead_ticks is None


def test_a_failure_with_no_telemetry_signature_is_missed() -> None:
    silent = dataclasses.replace(
        SIM.effects,
        friction_heat_wear_w=0.0,
        friction_heat_lube_w=0.0,
        friction_heat_offset_w=0.0,
        vibration_wear_gain=0.0,
        vibration_lube_gain=0.0,
        vibration_offset_gain=0.0,
        current_offset_gain_a=0.0,
    )
    result = run_machine(21, _with(effects=silent), machines.BEARING)
    assert result.outcome is Outcome.MISSED


def test_healthy_machines_are_quiet_or_counted_as_false_alarms() -> None:
    outcomes = [
        run_machine(seed, _with(healthy=1.0), machines.BEARING).outcome for seed in range(4)
    ]
    assert all(o in (Outcome.QUIET, Outcome.FALSE_ALARM) for o in outcomes)
    assert outcomes.count(Outcome.FALSE_ALARM) == 0, "false alarms on healthy machines: counted"


def test_same_seed_gives_the_same_score() -> None:
    a = run_machine(33, _with(), machines.LUBE)
    b = run_machine(33, _with(), machines.LUBE)
    assert a == b
