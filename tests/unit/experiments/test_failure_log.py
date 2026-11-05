"""Tests for the synthetic failure log generator (ADR-020)."""

import ast
import json
import math
import re
from pathlib import Path

import pytest

from waggle.experiments.failure_log import (
    LOG_PARAMETERS,
    FailureCase,
    FailureMode,
    generate_failure_log,
    similar_cases,
)

ROOT = Path(__file__).resolve().parents[3]


def _collect_keys_and_numbers(data: object) -> tuple[set[str], set[float]]:
    """Recursively collect mapping keys and numeric values from a JSON structure."""
    keys: set[str] = set()
    numbers: set[float] = set()
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, str):
                keys.add(k)
            sub_k, sub_n = _collect_keys_and_numbers(v)
            keys.update(sub_k)
            numbers.update(sub_n)
    elif isinstance(data, list):
        for item in data:
            sub_k, sub_n = _collect_keys_and_numbers(item)
            keys.update(sub_k)
            numbers.update(sub_n)
    elif isinstance(data, (int, float)) and not isinstance(data, bool):
        numbers.add(float(data))
    return keys, numbers


def test_determinism_and_seed_sensitivity() -> None:
    """Assert identical seeds yield equal tuples and different seeds yield different tuples."""
    log_a1 = generate_failure_log(seed=101, count=25)
    log_a2 = generate_failure_log(seed=101, count=25)
    log_b = generate_failure_log(seed=102, count=25)

    assert log_a1 == log_a2
    assert log_a1 != log_b


def test_every_case_valid() -> None:
    """Assert all cases generated in a synthetic log satisfy specification invariants."""
    log = generate_failure_log(seed=202, count=60)
    assert len(log) == 60

    part_re = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
    case_id_re = re.compile(r"^fl-\d+$")

    for case in log:
        assert isinstance(case, FailureCase)
        assert case_id_re.fullmatch(case.case_id) is not None
        assert case.machine_class in {"conveyor", "pump", "lift"}
        assert isinstance(case.mode, FailureMode)
        assert case.onset_to_failure_ticks >= 1
        assert math.isfinite(case.peak_temperature_c) and case.peak_temperature_c >= 0.0
        assert math.isfinite(case.peak_vibration_rms) and case.peak_vibration_rms >= 0.0
        assert math.isfinite(case.peak_current_a) and case.peak_current_a >= 0.0
        assert part_re.fullmatch(case.part_number) is not None


def test_modes_all_present_for_large_enough_count() -> None:
    """Assert all failure modes and machine classes appear when count is sufficiently large."""
    log = generate_failure_log(seed=303, count=300)
    modes = {case.mode for case in log}
    classes = {case.machine_class for case in log}

    assert modes == {
        FailureMode.BEARING_WEAR,
        FailureMode.LUBRICATION_LOSS,
        FailureMode.MISALIGNMENT,
    }
    assert classes == {"conveyor", "pump", "lift"}


def test_bad_seed_and_count() -> None:
    """Assert negative seed and out-of-range counts raise ValueError without echoing input."""
    with pytest.raises(ValueError) as exc_seed_neg:
        generate_failure_log(seed=-1, count=10)
    assert "-1" not in str(exc_seed_neg.value)

    with pytest.raises(ValueError) as exc_count_zero:
        generate_failure_log(seed=1, count=0)
    assert "0" not in str(exc_count_zero.value)

    with pytest.raises(ValueError) as exc_count_high:
        generate_failure_log(seed=1, count=10001)
    assert "10001" not in str(exc_count_high.value)

    with pytest.raises(ValueError):
        generate_failure_log(seed=1, count=-5)


def test_failure_case_refuses_invalid_fields() -> None:
    """Assert FailureCase rejects non-finite, negative, bad class, bad part, and zero ticks."""
    bad_marker = "ILLEGAL_PROBE_999"

    # NaN checks
    with pytest.raises(ValueError) as exc:
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, float("nan"), 1.0, 2.0, "P1")
    assert "nan" not in str(exc.value).lower()

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, 20.0, float("nan"), 2.0, "P1")

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, 20.0, 1.0, float("nan"), "P1")

    # Infinite checks
    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, float("inf"), 1.0, 2.0, "P1")

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, 20.0, float("-inf"), 2.0, "P1")

    # Negative checks
    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, -0.01, 1.0, 2.0, "P1")

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, 20.0, -1.0, 2.0, "P1")

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, 20.0, 1.0, -0.5, "P1")

    # Zero or negative ticks
    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 0, 20.0, 1.0, 2.0, "P1")

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, -5, 20.0, 1.0, 2.0, "P1")

    # Bad machine class
    with pytest.raises(ValueError) as exc_cls:
        FailureCase(
            "fl-001",
            bad_marker,
            FailureMode.BEARING_WEAR,
            10,
            20.0,
            1.0,
            2.0,
            "P1",
        )
    assert bad_marker not in str(exc_cls.value)

    # Bad part number
    with pytest.raises(ValueError) as exc_part:
        FailureCase(
            "fl-001",
            "pump",
            FailureMode.BEARING_WEAR,
            10,
            20.0,
            1.0,
            2.0,
            bad_marker + "@illegal",
        )
    assert bad_marker not in str(exc_part.value)

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, 20.0, 1.0, 2.0, "")

    with pytest.raises(ValueError):
        FailureCase("fl-001", "pump", FailureMode.BEARING_WEAR, 10, 20.0, 1.0, 2.0, "A" * 65)

    # Bad case_id
    with pytest.raises(ValueError) as exc_cid:
        FailureCase(
            bad_marker + "@illegal",
            "pump",
            FailureMode.BEARING_WEAR,
            10,
            20.0,
            1.0,
            2.0,
            "P1",
        )
    assert bad_marker not in str(exc_cid.value)

    # Bad mode
    with pytest.raises(ValueError) as exc_mode:
        FailureCase(
            "fl-001",
            "pump",
            bad_marker,  # type: ignore[arg-type]
            10,
            20.0,
            1.0,
            2.0,
            "P1",
        )
    assert bad_marker not in str(exc_mode.value)


def test_similar_cases_ordering_and_tie_break() -> None:
    """Assert similar_cases sorts by normalized distance and breaks ties by case_id."""
    case_a = FailureCase(
        case_id="fl-00001",
        machine_class="pump",
        mode=FailureMode.BEARING_WEAR,
        onset_to_failure_ticks=50,
        peak_temperature_c=10.0,
        peak_vibration_rms=1.0,
        peak_current_a=2.0,
        part_number="PART-01",
    )
    case_b = FailureCase(
        case_id="fl-00002",
        machine_class="pump",
        mode=FailureMode.BEARING_WEAR,
        onset_to_failure_ticks=60,
        peak_temperature_c=20.0,
        peak_vibration_rms=2.0,
        peak_current_a=4.0,
        part_number="PART-01",
    )
    case_c = FailureCase(
        case_id="fl-00003",
        machine_class="conveyor",
        mode=FailureMode.BEARING_WEAR,
        onset_to_failure_ticks=70,
        peak_temperature_c=30.0,
        peak_vibration_rms=3.0,
        peak_current_a=6.0,
        part_number="PART-02",
    )
    log = (case_c, case_a, case_b)

    # Closest to (10.5, 1.05, 2.05) is case_a, then case_b
    nearest = similar_cases(
        log=log,
        mode=FailureMode.BEARING_WEAR,
        temperature_c=10.5,
        vibration_rms=1.05,
        current_a=2.05,
        k=2,
    )
    assert nearest == (case_a, case_b)

    # Tie break check: identical peaks, different case_id
    tie_early = FailureCase(
        case_id="fl-00010",
        machine_class="pump",
        mode=FailureMode.LUBRICATION_LOSS,
        onset_to_failure_ticks=40,
        peak_temperature_c=15.0,
        peak_vibration_rms=1.5,
        peak_current_a=3.0,
        part_number="PART-01",
    )
    tie_late = FailureCase(
        case_id="fl-00020",
        machine_class="pump",
        mode=FailureMode.LUBRICATION_LOSS,
        onset_to_failure_ticks=40,
        peak_temperature_c=15.0,
        peak_vibration_rms=1.5,
        peak_current_a=3.0,
        part_number="PART-01",
    )
    tie_log = (tie_late, tie_early)
    tie_result_k1 = similar_cases(
        log=tie_log,
        mode=FailureMode.LUBRICATION_LOSS,
        temperature_c=15.0,
        vibration_rms=1.5,
        current_a=3.0,
        k=1,
    )
    assert tie_result_k1 == (tie_early,)

    tie_result_k2 = similar_cases(
        log=tie_log,
        mode=FailureMode.LUBRICATION_LOSS,
        temperature_c=15.0,
        vibration_rms=1.5,
        current_a=3.0,
        k=2,
    )
    assert tie_result_k2 == (tie_early, tie_late)


def test_similar_cases_k_bounds_and_empty_mode() -> None:
    """Assert similar_cases validates k boundaries and handles absent modes cleanly."""
    case = FailureCase(
        case_id="fl-00001",
        machine_class="conveyor",
        mode=FailureMode.BEARING_WEAR,
        onset_to_failure_ticks=50,
        peak_temperature_c=10.0,
        peak_vibration_rms=1.0,
        peak_current_a=2.0,
        part_number="PART-01",
    )
    log = (case,)

    # k bounds [1, 50]
    with pytest.raises(ValueError):
        similar_cases(log, FailureMode.BEARING_WEAR, 10.0, 1.0, 2.0, k=0)

    with pytest.raises(ValueError):
        similar_cases(log, FailureMode.BEARING_WEAR, 10.0, 1.0, 2.0, k=51)

    # Non-finite or negative query values
    with pytest.raises(ValueError):
        similar_cases(log, FailureMode.BEARING_WEAR, float("nan"), 1.0, 2.0, k=1)

    with pytest.raises(ValueError):
        similar_cases(log, FailureMode.BEARING_WEAR, 10.0, float("inf"), 2.0, k=1)

    with pytest.raises(ValueError):
        similar_cases(log, FailureMode.BEARING_WEAR, -1.0, 1.0, 2.0, k=1)

    # Empty result when requested mode is absent
    empty_res = similar_cases(
        log=log,
        mode=FailureMode.MISALIGNMENT,
        temperature_c=10.0,
        vibration_rms=1.0,
        current_a=2.0,
        k=5,
    )
    assert empty_res == ()

    # Empty log input
    empty_log_res = similar_cases(
        log=(),
        mode=FailureMode.BEARING_WEAR,
        temperature_c=10.0,
        vibration_rms=1.0,
        current_a=2.0,
        k=1,
    )
    assert empty_log_res == ()


def test_an_unknown_mode_is_an_error_and_not_an_empty_result() -> None:
    """Assert a mistyped mode raises, so it cannot pass as 'no similar case'."""
    log = generate_failure_log(seed=7, count=20)
    with pytest.raises(ValueError) as exc:
        similar_cases(log, "BEARING_WEARR", 50.0, 5.0, 5.0, k=3)
    assert "BEARING_WEARR" not in str(exc.value)
    assert similar_cases(log, "BEARING_WEAR", 50.0, 5.0, 5.0, k=3) != ()


def test_ast_import_contract() -> None:
    """Assert failure_log module does not import from forbidden subsystems."""
    source_file = ROOT / "src" / "waggle" / "experiments" / "failure_log.py"
    with open(source_file, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(source_file))

    forbidden_prefixes = (
        "waggle.sim",
        "waggle.llm",
        "waggle.governance",
        "waggle.mcp_server",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    assert not alias.name.startswith(prefix), f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in forbidden_prefixes:
                assert not module.startswith(prefix), f"Forbidden import from: {module}"


def test_no_overlap_with_sim_and_predictor_data() -> None:
    """Assert LOG_ mapping keys and numeric values do not overlap with sim or predictor data."""
    degradation_file = ROOT / "data" / "sim" / "degradation.json"
    predictor_file = ROOT / "data" / "maintenance" / "predictor.json"

    with open(degradation_file, encoding="utf-8") as f:
        deg_data = json.load(f)
    with open(predictor_file, encoding="utf-8") as f:
        pred_data = json.load(f)

    deg_keys, deg_numbers = _collect_keys_and_numbers(deg_data)
    pred_keys, pred_numbers = _collect_keys_and_numbers(pred_data)
    forbidden_keys = deg_keys | pred_keys
    forbidden_numbers = deg_numbers | pred_numbers

    for key, val in LOG_PARAMETERS.items():
        assert key not in forbidden_keys, f"Overlap in parameter key: {key}"
        assert float(val) not in forbidden_numbers, f"Overlap in numeric value: {val}"
