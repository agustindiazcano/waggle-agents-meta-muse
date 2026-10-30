"""waggle.experiments: Wilson intervals, latency summary and the eight configurations."""

import math

import pytest

from waggle.control.limiter import EnvelopeMode
from waggle.experiments import e1_stats
from waggle.experiments.e1_config import BY_NAME, CONFIGS, Sensing


def test_wilson_matches_the_figures_quoted_in_the_experiment_protocol() -> None:
    # EXPERIMENTS.md: zero collisions in 216 runs gives an upper bound of about 1.7%,
    # and in 100 runs about 3.7%
    assert e1_stats.wilson(0, 216)[1] == pytest.approx(0.0175, abs=0.0005)
    assert e1_stats.wilson(0, 100)[1] == pytest.approx(0.0370, abs=0.0005)
    assert e1_stats.wilson(0, 100)[0] == 0.0


def test_wilson_known_value_for_half() -> None:
    low, high = e1_stats.wilson(50, 100)
    assert low == pytest.approx(0.4038, abs=0.001)
    assert high == pytest.approx(0.5962, abs=0.001)


def test_wilson_is_the_whole_range_without_trials_and_rejects_bad_counts() -> None:
    assert e1_stats.wilson(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        e1_stats.wilson(5, 3)
    with pytest.raises(ValueError):
        e1_stats.wilson(-1, 3)


def test_wilson_stays_inside_zero_and_one_and_contains_the_estimate() -> None:
    for total in (1, 5, 90, 216):
        for hits in range(0, total + 1, max(total // 7, 1)):
            low, high = e1_stats.wilson(hits, total)
            assert 0.0 <= low <= hits / total <= high <= 1.0


def test_latency_summary_percentiles() -> None:
    summary = e1_stats.latency_summary(list(range(1, 101)))
    assert summary["n"] == 100
    assert summary["median_us"] == pytest.approx(50.5)
    assert summary["p99_us"] == pytest.approx(99.01)
    assert summary["max_us"] == 100.0
    assert e1_stats.latency_summary([])["n"] == 0


def test_there_are_eight_configurations_in_the_order_of_adr_028() -> None:
    assert [c.name for c in CONFIGS] == [
        "no_control",
        "radial_lidar",
        "envelope_oracle",
        "envelope_lidar",
        "envelope_lidar_beacons",
        "envelope_occlusion_lidar",
        "envelope_occlusion_cpa_lidar",
        "envelope_occlusion_cpa_lidar_beacons",
    ]
    assert len(BY_NAME) == 8


def test_each_configuration_differs_from_its_neighbour_in_the_declared_block() -> None:
    by = BY_NAME
    assert not by["no_control"].controlled
    assert by["radial_lidar"].mode is EnvelopeMode.RADIAL
    assert by["envelope_lidar"].mode is EnvelopeMode.SWEPT
    assert by["envelope_oracle"].sensing is Sensing.ORACLE
    assert by["envelope_lidar_beacons"].beacons and not by["envelope_lidar"].beacons
    assert by["envelope_occlusion_lidar"].occlusion and not by["envelope_occlusion_lidar"].cpa
    assert by["envelope_occlusion_cpa_lidar"].cpa
    last = by["envelope_occlusion_cpa_lidar_beacons"]
    assert last.beacons and last.occlusion and last.cpa
    assert not any(c.cpa and not c.occlusion for c in CONFIGS)


def test_only_the_beacon_configurations_use_beacons() -> None:
    names = {c.name for c in CONFIGS if c.beacons}
    assert names == {"envelope_lidar_beacons", "envelope_occlusion_cpa_lidar_beacons"}
    assert math.isfinite(len(names))
