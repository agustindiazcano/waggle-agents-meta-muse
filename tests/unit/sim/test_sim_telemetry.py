"""waggle.sim.telemetry: Gaussian noise per channel and a per-machine bias (design T2)."""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from waggle.sim import machines, telemetry
from waggle.sim.params import DT

PARAMS = machines.load_params()
NOISE = telemetry.load_noise()
HEALTHY = dataclasses.replace(
    PARAMS, wear=dataclasses.replace(PARAMS.wear, healthy_probability=1.0)
)
STRIDE = machines.STRIDE_TICKS


def _engine(seed: int = 1, count: int = 3) -> telemetry.TelemetryEngine:
    return telemetry.build_engine(seed, count, PARAMS, NOISE)


def test_noise_parameters_load_and_are_positive() -> None:
    for field in dataclasses.fields(NOISE):
        value = getattr(NOISE, field.name)
        assert np.isfinite(value) and value >= 0.0


def test_negative_or_non_finite_noise_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(machines.default_params_path().read_text(encoding="utf-8"))
    raw["telemetry"]["vibration_sigma"] = -0.1
    bad = tmp_path / "neg.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(machines.DegradationError, match="vibration_sigma"):
        telemetry.load_noise(bad)
    raw["telemetry"]["vibration_sigma"] = float("inf")
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(machines.DegradationError, match="vibration_sigma"):
        telemetry.load_noise(bad)


def test_one_sample_per_machine_with_tick_and_id() -> None:
    eng = _engine()
    eng.engine.run(STRIDE)
    samples = telemetry.read(eng)
    assert [s.machine_id for s in samples] == [0, 1, 2]
    assert {s.tick for s in samples} == {STRIDE}


def test_same_seed_gives_identical_samples_and_hashes() -> None:
    a, b = _engine(4), _engine(4)
    for _ in range(20):
        a.engine.run(STRIDE)
        b.engine.run(STRIDE)
        assert telemetry.read(a) == telemetry.read(b)
        assert a.engine.state_hash() == b.engine.state_hash()


def test_different_seeds_give_different_samples() -> None:
    a, b = _engine(1), _engine(2)
    a.engine.run(STRIDE)
    b.engine.run(STRIDE)
    assert telemetry.read(a) != telemetry.read(b)


def test_reading_advances_the_telemetry_stream_and_is_part_of_the_hash() -> None:
    eng = _engine()
    eng.engine.run(STRIDE)
    before = eng.engine.state_hash()
    telemetry.read(eng)
    assert eng.engine.state_hash() != before


def test_a_forked_engine_reads_the_same_samples() -> None:
    eng = _engine(6)
    eng.engine.run(5 * STRIDE)
    twin = telemetry.TelemetryEngine(eng.engine.fork(), eng.params, eng.noise)
    for _ in range(5):
        eng.engine.run(STRIDE)
        twin.engine.run(STRIDE)
        assert telemetry.read(eng) == telemetry.read(twin)


def test_zero_noise_returns_truth_plus_a_constant_bias() -> None:
    quiet = dataclasses.replace(NOISE, temperature_sigma_c=0.0, vibration_sigma=0.0)
    quiet = dataclasses.replace(quiet, current_sigma_a=0.0, load_sigma=0.0)
    eng = telemetry.build_engine(3, 2, PARAMS, quiet)
    eng.engine.run(STRIDE)
    first = telemetry.read(eng)
    truth = machines.observables(eng.engine.state.arrays, PARAMS)
    bias = np.asarray(eng.engine.state.arrays["machine_bias"], dtype=np.float64)
    for i, sample in enumerate(first):
        assert sample.temperature == pytest.approx(truth.temperature[i] + bias[i, 0])
        assert sample.vibration == pytest.approx(truth.vibration[i] + bias[i, 1])
        assert sample.current == pytest.approx(truth.current[i] + bias[i, 2])
        assert sample.load == pytest.approx(truth.load[i])


def test_machines_have_different_biases_and_noise_has_the_declared_scale() -> None:
    eng = telemetry.build_engine(8, 4, HEALTHY, NOISE)
    eng.engine.run(STRIDE)
    bias = np.asarray(eng.engine.state.arrays["machine_bias"], dtype=np.float64)
    assert len({tuple(row) for row in bias.tolist()}) == 4
    truth = machines.observables(eng.engine.state.arrays, HEALTHY)
    residuals = []
    for _ in range(400):
        residuals.append(telemetry.read(eng)[0].temperature - truth.temperature[0] - bias[0, 0])
    assert np.std(residuals) == pytest.approx(NOISE.temperature_sigma_c, rel=0.2)
    assert abs(np.mean(residuals)) < 0.15


def test_no_machines_gives_no_samples() -> None:
    eng = telemetry.build_engine(1, 0, PARAMS, NOISE)
    eng.engine.run(10)
    assert telemetry.read(eng) == []


def test_non_finite_truth_fails_closed() -> None:
    eng = _engine()
    eng.engine.run(STRIDE)
    eng.engine.state.arrays["machine_t_bearing"][1] = np.nan
    with pytest.raises(ValueError, match="finite"):
        telemetry.read(eng)


def test_telemetry_carries_no_hidden_state() -> None:
    names = {f.name for f in dataclasses.fields(telemetry.TelemetrySample)}
    assert names == {"machine_id", "tick", "temperature", "vibration", "current", "load"}


def test_a_planted_bearing_failure_is_visible_in_the_samples() -> None:
    wear = dataclasses.replace(
        PARAMS.wear, healthy_probability=0.0, onset_min_s=300.0, onset_max_s=300.0
    )
    eng = telemetry.build_engine(
        5, 1, dataclasses.replace(PARAMS, wear=wear), NOISE, modes=[machines.BEARING]
    )
    eng.engine.run(round(200.0 / DT))
    early = telemetry.read(eng)[0]
    eng.engine.run(round(900.0 / DT))
    late = telemetry.read(eng)[0]
    assert late.temperature > early.temperature + 5.0
