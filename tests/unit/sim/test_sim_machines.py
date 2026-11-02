"""waggle.sim.machines: two-node thermal model with power-law wear and a stochastic rate."""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from waggle.sim import engine, machines
from waggle.sim.params import DT

PARAMS = machines.load_params()
STRIDE_TICKS = machines.STRIDE_TICKS
FORCED_ONSET = dataclasses.replace(PARAMS.wear, healthy_probability=0.0, onset_min_s=300.0)
FORCED_ONSET = dataclasses.replace(FORCED_ONSET, onset_max_s=300.0)
PLANTED = dataclasses.replace(PARAMS, wear=FORCED_ONSET)


def _run(
    seed: int,
    n: int,
    seconds: int,
    params: machines.DegradationParams = PARAMS,
    modes: list[int] | None = None,
) -> engine.Engine:
    eng = machines.build_engine(seed, n, params, modes=modes)
    eng.run(int(seconds / DT))
    return eng


def test_default_parameter_file_loads_and_is_finite() -> None:
    for section in (PARAMS.thermal, PARAMS.wear, PARAMS.load, PARAMS.effects):
        for field in dataclasses.fields(section):
            assert np.isfinite(getattr(section, field.name))


def test_non_finite_or_missing_parameters_are_rejected(tmp_path: Path) -> None:
    raw = json.loads(machines.default_params_path().read_text(encoding="utf-8"))
    raw["thermal"]["ambient_c"] = float("nan")
    bad = tmp_path / "nan.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(machines.DegradationError, match="ambient_c"):
        machines.load_params(bad)
    del raw["thermal"]["ambient_c"]
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(machines.DegradationError, match="ambient_c"):
        machines.load_params(bad)


def test_unknown_parameter_keys_are_rejected(tmp_path: Path) -> None:
    raw = json.loads(machines.default_params_path().read_text(encoding="utf-8"))
    raw["wear"]["surprise"] = 1.0
    bad = tmp_path / "extra.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(machines.DegradationError, match="surprise"):
        machines.load_params(bad)


def test_inverted_ranges_are_rejected() -> None:
    wear = dataclasses.replace(PARAMS.wear, onset_min_s=900.0, onset_max_s=100.0)
    with pytest.raises(machines.DegradationError, match="onset"):
        machines.validate(dataclasses.replace(PARAMS, wear=wear))


def test_no_machines_means_no_arrays_and_no_streams() -> None:
    assert machines.initial_arrays(7, 0, PARAMS) == {}
    eng = machines.build_engine(7, 0, PARAMS)
    eng.run(100)
    assert eng.state.arrays == {}
    assert eng.rngs == {}


def test_negative_machine_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="count"):
        machines.initial_arrays(7, -1, PARAMS)


def test_same_seed_gives_equal_state_hashes_at_every_stride() -> None:
    a = machines.build_engine(3, 4, PARAMS)
    b = machines.build_engine(3, 4, PARAMS)
    for _ in range(30):
        a.run(STRIDE_TICKS)
        b.run(STRIDE_TICKS)
        assert a.state_hash() == b.state_hash()


def test_different_seeds_differ() -> None:
    assert _run(1, 3, 600).state_hash() != _run(2, 3, 600).state_hash()


def test_fork_continues_exactly_like_the_original() -> None:
    eng = _run(5, 3, 500)
    twin = eng.fork()
    eng.run(2000)
    twin.run(2000)
    assert eng.state_hash() == twin.state_hash()


def test_state_stays_finite_and_bounded() -> None:
    eng = _run(9, 6, 2400, PLANTED)
    arrays = eng.state.arrays
    for name in ("machine_wear", "machine_lube"):
        values = np.asarray(arrays[name], dtype=np.float64)
        assert np.all((values >= 0.0) & (values <= 1.0))
    for name, array in arrays.items():
        if np.issubdtype(array.dtype, np.floating):
            assert np.all(np.isfinite(array)), name


def test_healthy_machines_never_fail_and_stay_near_their_start() -> None:
    healthy = dataclasses.replace(PARAMS.wear, healthy_probability=1.0)
    eng = _run(4, 5, 3000, dataclasses.replace(PARAMS, wear=healthy))
    arrays = eng.state.arrays
    assert np.all(arrays["machine_onset_tick"] == -1)
    assert np.all(arrays["machine_fail_tick"] == -1)
    assert np.all(arrays["machine_wear"] == 0.0)
    assert np.all(arrays["machine_lube"] == 1.0)
    assert np.all(np.asarray(arrays["machine_t_bearing"], dtype=np.float64) < 60.0)


@pytest.mark.parametrize("mode", [machines.BEARING, machines.LUBE, machines.OFFSET])
def test_every_mode_fails_after_its_onset_and_not_before(mode: int) -> None:
    eng = _run(11, 1, 3000, PLANTED, modes=[mode])
    arrays = eng.state.arrays
    onset = int(arrays["machine_onset_tick"][0])
    fail = int(arrays["machine_fail_tick"][0])
    assert onset == round(300.0 / DT)
    assert fail > onset, "the machine must fail, and only after the onset"


def test_bearing_wear_accelerates_after_onset() -> None:
    eng = machines.build_engine(2, 1, PLANTED, modes=[machines.BEARING])
    wear: list[float] = []
    for _ in range(1500):
        eng.run(STRIDE_TICKS)
        wear.append(float(eng.state.arrays["machine_wear"][0]))
        if wear[-1] >= 1.0:
            break
    inc = np.diff(np.array(wear))
    started = int(np.argmax(inc > 0))
    grown = inc[started:]
    half = len(grown) // 2
    assert half > 10
    assert grown[half:].sum() > 3.0 * grown[:half].sum()


def test_failing_machine_runs_hotter_and_shakes_more() -> None:
    healthy = dataclasses.replace(PARAMS.wear, healthy_probability=1.0)
    base = machines.observables(
        _run(
            6, 1, 1100, dataclasses.replace(PARAMS, wear=healthy), modes=[machines.BEARING]
        ).state.arrays,
        PARAMS,
    )
    bad = machines.observables(
        _run(6, 1, 1100, PLANTED, modes=[machines.BEARING]).state.arrays, PARAMS
    )
    assert bad.temperature[0] > base.temperature[0] + 5.0
    assert bad.vibration[0] > base.vibration[0] + 1.0


def test_load_follows_the_task_count_and_stays_in_range() -> None:
    eng = machines.build_engine(8, 1, PARAMS)
    eng.run(STRIDE_TICKS)
    low = float(eng.state.arrays["machine_load"][0])
    eng.state.arrays["machine_tasks"][0] = 100
    eng.run(STRIDE_TICKS)
    high = float(eng.state.arrays["machine_load"][0])
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0
    assert high > low


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="mode"):
        machines.initial_arrays(1, 2, PARAMS, modes=[0, 9])
    with pytest.raises(ValueError, match="modes"):
        machines.initial_arrays(1, 2, PARAMS, modes=[0])


def test_new_subsystems_do_not_move_existing_stream_indexes() -> None:
    from waggle.sim import streams

    assert streams.SUBSYSTEMS[:5] == ("robots", "humans", "lidar", "beacons", "scenario")
    for name in ("degradation", "wear", "telemetry", "sensorbias"):
        assert len(streams.make_streams(1, name, 2)) == 2
