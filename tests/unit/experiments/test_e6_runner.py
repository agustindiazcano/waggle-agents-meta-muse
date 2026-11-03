"""E6 runner on the mock: configurations, scorer, intervals and the result document.

The telemetry comes from the simulator's machine model (ground truth stays in the scorer). No
model is called and no held-out seed is read. Every case maps to a rule of design section 7 or 8
of docs/PREDICTIVE_MAINTENANCE_DESIGN.md.
"""

import dataclasses
import json
import math
from pathlib import Path

import pytest

from waggle.experiments import e6_runner as e6
from waggle.maintenance.loop import AlertPolicy
from waggle.maintenance.predictor import Assessment
from waggle.sim import machines, telemetry

ROOT = Path(__file__).resolve().parents[3]
SIM = machines.load_params()
PLANTED = dataclasses.replace(
    SIM,
    wear=dataclasses.replace(
        SIM.wear, healthy_probability=0.0, onset_min_s=400.0, onset_max_s=400.0
    ),
)
HEALTHY = dataclasses.replace(SIM, wear=dataclasses.replace(SIM.wear, healthy_probability=1.0))


def _blind() -> "e6.Assessor":
    def assess(sample: telemetry.TelemetrySample) -> Assessment:
        return Assessment(sample.machine_id, sample.tick, True, True, False, (), None)

    return assess


@pytest.fixture(scope="module")
def planted() -> e6.Trace:
    return e6.build_trace(21, PLANTED, mode=machines.BEARING)


@pytest.fixture(scope="module")
def healthy() -> e6.Trace:
    return e6.build_trace(21, HEALTHY, mode=machines.BEARING)


def test_the_seeds_are_the_development_seeds_only() -> None:
    raw = json.loads((ROOT / "data" / "seeds.json").read_text(encoding="utf-8"))
    dev = {s for seeds in raw["dev"].values() for s in seeds}
    held = {s for seeds in raw["heldout"].values() for s in seeds}
    assert set(e6.dev_seeds()) <= dev
    assert not set(e6.dev_seeds()) & held
    assert e6.dev_seeds() == sorted(set(e6.dev_seeds()))


def test_the_runner_has_no_held_out_path() -> None:
    source = (ROOT / "src" / "waggle" / "experiments" / "e6_runner.py").read_text(encoding="utf-8")
    assert "heldout" not in source
    assert (
        "seed_set" not in e6.run_config.__code__.co_varnames[: e6.run_config.__code__.co_argcount]
    )


def test_the_predictor_and_simulator_parameters_do_not_overlap() -> None:
    e6.check_parameter_separation()


def test_overlapping_parameters_are_refused(tmp_path: Path) -> None:
    sim = tmp_path / "sim.json"
    pred = tmp_path / "pred.json"
    sim.write_text(json.dumps({"a": {"shared_name": 1.25}}), encoding="utf-8")
    pred.write_text(json.dumps({"b": {"shared_name": 9.0}}), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        e6.check_parameter_separation(sim, pred)
    pred.write_text(json.dumps({"b": {"other": 1.25}}), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        e6.check_parameter_separation(sim, pred)


def test_an_unknown_configuration_raises(planted: e6.Trace) -> None:
    with pytest.raises(ValueError, match="configuration"):
        e6.run_trace("Z9", planted)


@pytest.mark.parametrize("config", ["B0", "B1", "C1"])
def test_a_planted_failure_gets_one_ticket_before_it_happens(
    config: str, planted: e6.Trace
) -> None:
    record = e6.run_trace(config, planted)
    assert planted.failure_tick is not None
    assert record["outcome"] == "detected"
    assert record["ticket_id"] is not None
    assert record["first_alert_tick"] < planted.failure_tick
    assert record["lead_ticks"] > 0
    assert record["duplicates"] == 0
    assert record["tickets_created"] == 1


def test_the_threshold_baselines_alert_no_earlier_than_the_predictor(planted: e6.Trace) -> None:
    ticks = {c: e6.run_trace(c, planted)["first_alert_tick"] for c in ("B0", "B1", "C1")}
    assert ticks["B1"] <= ticks["B0"]
    assert ticks["C1"] <= ticks["B0"]


def test_the_estimate_gate_can_only_delay_the_alert(planted: e6.Trace) -> None:
    """On the simulator the machines fail well below the predictor's temperature limit, so the
    estimate never fires and C2 stays quiet. This pins that finding: C2 is never earlier than C1.
    """
    c1 = e6.run_trace("C1", planted)["first_alert_tick"]
    c2 = e6.run_trace("C2", planted)["first_alert_tick"]
    assert c2 is None or c2 >= c1


def test_a_blind_predictor_is_counted_as_missed(planted: e6.Trace) -> None:
    record = e6.run_trace("C2", planted, _blind)
    assert record["outcome"] == "missed"
    assert record["ticket_id"] is None
    assert record["lead_ticks"] is None


def test_a_healthy_machine_stays_quiet_or_is_counted(healthy: e6.Trace) -> None:
    record = e6.run_trace("C2", healthy)
    assert healthy.failure_tick is None
    assert record["outcome"] in {"quiet", "false_alarm"}
    assert record["outcome"] == ("false_alarm" if record["ticket_id"] else "quiet")


def test_nan_telemetry_is_held_and_never_counts_as_a_pass(healthy: e6.Trace) -> None:
    bad = dataclasses.replace(healthy.samples[100], temperature=math.nan)
    samples = (*healthy.samples[:100], bad, *healthy.samples[101:])
    record = e6.run_trace("C2", dataclasses.replace(healthy, samples=samples))
    assert record["held_readings"] == 1
    assert record["unscorable_ticks"] == [bad.tick]


def test_a_nan_in_a_failing_trace_does_not_hide_the_failure(planted: e6.Trace) -> None:
    bad = dataclasses.replace(planted.samples[-2], vibration=math.nan)
    samples = (*planted.samples[:-2], bad, *planted.samples[-1:])
    record = e6.run_trace("C2", dataclasses.replace(planted, samples=samples), _blind)
    assert record["held_readings"] == 1
    assert record["outcome"] == "missed"


def test_the_backend_is_idempotent_by_key() -> None:
    backend = e6.InMemoryBackend({"P-1": 2})
    args: dict[str, object] = {"machine_id": "m", "idempotency_key": "k", "summary": "s"}
    first = backend("open_ticket", args)
    assert backend("open_ticket", args) == first
    reserve: dict[str, object] = {
        "part_number": "P-1",
        "quantity": 2,
        "idempotency_key": "r",
        "ticket_id": "tkt-1",
    }
    assert backend("reserve_part", reserve) == backend("reserve_part", reserve)
    assert backend.created == {"tickets": 1, "reservations": 1, "orders": 0}
    assert backend.stock["P-1"] == 0


def test_a_backend_that_is_not_idempotent_shows_up_as_duplicates() -> None:
    backend = e6.InMemoryBackend({}, idempotent=False)
    args: dict[str, object] = {"machine_id": "m", "idempotency_key": "k", "summary": "s"}
    backend("open_ticket", args)
    backend("open_ticket", args)
    assert backend.duplicates() == 1


def test_without_the_sheet_the_ticket_opens_but_no_part_is_chosen(planted: e6.Trace) -> None:
    record = e6.run_trace("C3", planted, policy=AlertPolicy(5, 20000, use_estimate=False))
    assert record["ticket_id"] is not None
    assert record["part_number"] is None
    assert record["dispatched"] is False
    assert record["phase"] == "escalated"
    assert record["wrong_part"] is False


def test_the_scorer_marks_a_wrong_part_from_the_truth_table() -> None:
    assert e6.TRUE_PART[machines.BEARING] == "PART-BRG-01"
    assert e6.is_wrong_part(machines.BEARING, "PART-LUB-01") is True
    assert e6.is_wrong_part(machines.BEARING, "PART-BRG-01") is False
    assert e6.is_wrong_part(machines.BEARING, None) is False


def test_runs_are_deterministic(planted: e6.Trace) -> None:
    assert e6.run_trace("C2", planted) == e6.run_trace("C2", planted)
    other = e6.build_trace(22, PLANTED, mode=machines.BEARING)
    assert other.samples != planted.samples


def test_the_assembled_document_has_counts_intervals_and_the_required_fields() -> None:
    records = e6.run_config("C2", e6.dev_seeds()[:3])
    doc = e6.assemble("C2", records)
    assert set(doc) >= e6.REQUIRED_RESULT_FIELDS
    assert doc["seed_set"] == "dev"
    assert doc["model_ids"] == [] and doc["prompt_versions"] == []
    assert len(doc["per_seed_outcomes"]) == 3
    detected = doc["proportions"]["detected"]
    assert set(detected) >= {"hits", "total", "wilson95_low", "wilson95_high"}
    assert 0.0 <= detected["wilson95_low"] <= detected["wilson95_high"] <= 1.0
    assert detected["small_sample"] is True
    assert "downtime" in doc["not_measured"]
    assert isinstance(doc["failing_seeds"], list)


def test_every_configuration_assembles_over_one_seed() -> None:
    for config in e6.CONFIGS:
        doc = e6.assemble(config, e6.run_config(config, e6.dev_seeds()[:1]))
        assert doc["configuration_id"] == config


def test_the_result_file_is_validated_before_writing(tmp_path: Path) -> None:
    doc = e6.assemble("B0", e6.run_config("B0", e6.dev_seeds()[:1]))
    target = tmp_path / "out" / "e6.json"
    broken = {k: v for k, v in doc.items() if k != "commit"}
    with pytest.raises(e6.ResultValidationError):
        e6.write_result_file(target, broken)
    assert not target.exists()
    with pytest.raises(e6.ResultValidationError):
        e6.write_result_file(target, {**doc, "seed_set": "heldout"})
    assert not target.exists()
    e6.write_result_file(target, doc)
    assert json.loads(target.read_text(encoding="utf-8"))["configuration_id"] == "B0"


def test_a_seed_outside_the_development_list_is_refused() -> None:
    with pytest.raises(ValueError, match="development"):
        e6.run_config("B0", [123456789])
