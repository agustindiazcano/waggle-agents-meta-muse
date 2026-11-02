"""waggle.maintenance.predictor: load-corrected CUSUM and a one-node thermal estimate."""

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

from waggle.maintenance.predictor import (
    Assessment,
    Predictor,
    PredictorError,
    PredictorParams,
    Reading,
    default_params_path,
    load_params,
)

PARAMS = load_params()
ALPHA = 0.97
SAMPLES = 1500


def _series(
    seed: int,
    fault_from: int | None = None,
    vib_slope: float = 0.02,
    heat_slope: float = 0.02,
    samples: int = SAMPLES,
) -> list[Reading]:
    """A synthetic machine: first-order temperature, vibration and current linear in load.

    Written here on purpose, without the simulator. A fault ramps vibration and heat input.
    """
    rng = np.random.default_rng(seed)
    temp, readings = 40.0, []
    for k in range(samples):
        load = 0.5 + 0.2 * math.sin(k / 37.0) + 0.1 * math.sin(k / 11.0)
        ramp = 0.0 if fault_from is None or k < fault_from else float(k - fault_from)
        temp = ALPHA * temp + (1 - ALPHA) * (30.0 + 40.0 * load) + heat_slope * ramp**1.2 * 0.05
        readings.append(
            Reading(
                machine_id=1,
                tick=k * 40,
                temperature=temp + float(rng.normal(0, 0.3)),
                vibration=1.0 + 0.9 * load + vib_slope * ramp + float(rng.normal(0, 0.1)),
                current=2.0 + 5.0 * load + float(rng.normal(0, 0.15)),
                load=load + float(rng.normal(0, 0.02)),
            )
        )
    return readings


def _run(readings: list[Reading], params: PredictorParams = PARAMS) -> list[Assessment]:
    predictor = Predictor(params)
    return [predictor.update(r) for r in readings]


def test_reading_has_no_fault_state_field() -> None:
    names = {f.name for f in dataclasses.fields(Reading)}
    assert names == {"machine_id", "tick", "temperature", "vibration", "current", "load"}


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_reading_rejects_non_finite_values(bad: float) -> None:
    for field in ("temperature", "vibration", "current", "load"):
        values = dict(machine_id=1, tick=0, temperature=1.0, vibration=1.0, current=1.0, load=0.5)
        values[field] = bad
        with pytest.raises(ValueError, match=field):
            Reading(**values)  # type: ignore[arg-type]  # dict of mixed values in a test


def test_parameter_file_loads_and_rejects_bad_values(tmp_path: Path) -> None:
    raw = json.loads(default_params_path().read_text(encoding="utf-8"))
    for section, key, value in (
        ("cusum", "threshold", float("nan")),
        ("cusum", "threshold", -1.0),
        ("baseline", "warmup_samples", 3),
        ("baseline", "alpha_min", 1.2),
        ("estimate", "intercept_memory", 1.0),
    ):
        broken = json.loads(json.dumps(raw))
        broken[section][key] = value
        path = tmp_path / "p.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(PredictorError, match=key):
            load_params(path)


def test_unknown_parameter_key_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(default_params_path().read_text(encoding="utf-8"))
    raw["cusum"]["extra"] = 1.0
    path = tmp_path / "p.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PredictorError, match="extra"):
        load_params(path)


def test_no_flag_and_not_warm_during_the_baseline_window() -> None:
    out = _run(_series(1, samples=PARAMS.warmup_samples - 1))
    assert not any(a.flag for a in out)
    assert not any(a.warm for a in out)


def test_healthy_machines_raise_no_flag_over_many_seeds() -> None:
    flagged = [seed for seed in range(8) if any(a.flag for a in _run(_series(seed)))]
    assert flagged == []


def test_planted_fault_is_flagged_after_it_starts_and_not_before() -> None:
    start = 600
    out = _run(_series(3, fault_from=start))
    first = next(i for i, a in enumerate(out) if a.flag)
    assert first > start
    assert first < start + 300
    assert "vibration" in out[first].flagged or "temperature" in out[first].flagged


def test_time_to_limit_shrinks_as_a_planted_fault_grows() -> None:
    out = _run(_series(3, fault_from=600, heat_slope=0.6))
    values = [a.time_to_limit_ticks for a in out if a.time_to_limit_ticks is not None]
    assert values, "a growing heat input must give a finite estimate at some point"
    assert min(values) < max(values)


def test_no_time_to_limit_for_a_healthy_machine() -> None:
    out = _run(_series(2))
    assert all(a.time_to_limit_ticks is None for a in out)


def test_same_input_gives_the_same_assessments() -> None:
    readings = _series(5, fault_from=500)
    assert _run(readings) == _run(readings)


def test_machines_are_tracked_independently() -> None:
    sick = _series(5, fault_from=400)
    well = [dataclasses.replace(r, machine_id=2) for r in _series(6)]
    predictor = Predictor(PARAMS)
    flags: dict[int, bool] = {1: False, 2: False}
    for r_sick, r_well in zip(sick, well, strict=True):
        for reading in (r_sick, r_well):
            if predictor.update(reading).flag:
                flags[reading.machine_id] = True
    assert flags == {1: True, 2: False}


def test_a_gap_is_unscorable_and_does_not_flag() -> None:
    readings = _series(7)
    predictor = Predictor(PARAMS)
    out = [predictor.update(r) for r in readings[:300]]
    skipped = predictor.update(readings[310])
    assert not skipped.scorable
    assert not skipped.flag
    assert out[-1].scorable


def test_a_repeated_or_earlier_tick_is_rejected() -> None:
    readings = _series(7, samples=5)
    predictor = Predictor(PARAMS)
    predictor.update(readings[2])
    with pytest.raises(PredictorError, match="tick"):
        predictor.update(readings[2])
    with pytest.raises(PredictorError, match="tick"):
        predictor.update(readings[1])


def test_blind_channel_fault_is_not_flagged() -> None:
    """A fault the three channels do not show must stay unflagged: the predictor is blind."""
    out = _run(_series(3, fault_from=600, vib_slope=0.0, heat_slope=0.0))
    assert not any(a.flag for a in out)


def test_the_baseline_window_grows_until_the_load_has_varied() -> None:
    flat_start = [dataclasses.replace(r, load=0.5) for r in _series(2, samples=200)]
    varied = _series(2, samples=500)[200:]
    out = _run(flat_start + varied)
    first_warm = next(i for i, a in enumerate(out) if a.warm)
    assert first_warm >= PARAMS.warmup_samples
    assert first_warm > 199, "a flat load must not complete the baseline"


def test_a_machine_whose_load_never_varies_is_unfit_and_never_scorable() -> None:
    flat = [
        dataclasses.replace(r, load=0.5) for r in _series(2, samples=PARAMS.max_warmup_samples + 50)
    ]
    out = _run(flat)
    assert not any(a.warm for a in out)
    assert not out[-1].scorable
    assert not any(a.flag for a in out)
