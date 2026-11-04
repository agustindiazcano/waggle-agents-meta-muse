"""E8 reports use production control timing and explicit call-log provenance."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from waggle.control.step import control_step
from waggle.experiments.e8_run import load_calls, main, measure_control


def test_control_measurement_counts_actual_production_calls() -> None:
    with patch("waggle.experiments.e1_rig.control_step", wraps=control_step) as measured:
        result = measure_control(ticks=2, warmup_ticks=1)
    robot_count = result["robots"]
    latency = result["latency_s"]
    scope = result["scope"]
    assert isinstance(robot_count, int)
    assert isinstance(latency, dict)
    assert isinstance(scope, str)
    assert result["configuration"] == "envelope_occlusion_cpa_lidar_beacons"
    assert result["scenario"] == "S01"
    assert result["control_calls"] == robot_count * 2
    assert measured.call_count == robot_count * 3
    assert latency["count"] == result["control_calls"]
    assert latency["min"] >= 0
    assert "control_step" in scope


@pytest.mark.parametrize("ticks,warmup", [(0, 1), (1, -1), (True, 1), (100001, 0)])
def test_control_measurement_rejects_invalid_sizes(ticks: int, warmup: int) -> None:
    with pytest.raises(ValueError):
        measure_control(ticks=ticks, warmup_ticks=warmup)


def _export(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "source": "llm_calls",
                "mode": "http",
                "commit": "abc123",
                "prompt_versions": {"advisor": "v1"},
                "records": [
                    {
                        "request_id": "a",
                        "task_id": "t",
                        "role": "advisor",
                        "provider": "meta",
                        "model_id": "model",
                        "status": "ok",
                        "tokens_in": 2,
                        "tokens_out": 3,
                        "latency_s": 0.25,
                        "cost_usd": 0.01,
                        "fallback_label": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_load_export_preserves_source_metadata(tmp_path: Path) -> None:
    path = tmp_path / "calls.json"
    _export(path)
    records, metadata = load_calls(path)
    assert records[0].latency_s == 0.25
    assert metadata["mode"] == "http"
    assert metadata["commit"] == "abc123"


@pytest.mark.parametrize("change", ["empty", "extra", "mode", "source", "prompts", "role"])
def test_load_export_rejects_invalid_input(tmp_path: Path, change: str) -> None:
    path = tmp_path / "calls.json"
    _export(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    if change == "empty":
        document["records"] = []
    elif change == "extra":
        document["records"][0]["prompt"] = "untrusted content"
    elif change == "mode":
        document["mode"] = "unknown"
    elif change == "source":
        document["source"] = "synthetic"
    elif change == "role":
        document["prompt_versions"] = {"other": "v1"}
    else:
        document["prompt_versions"] = {}
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        load_calls(path)


def test_calls_cli_writes_report_and_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "calls.json"
    output = tmp_path / "report.json"
    _export(source)
    args = ["calls", "--input", str(source), "--output", str(output)]
    assert main(args) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["experiment"] == "e8"
    assert report["source"]["mode"] == "http"
    assert report["extrapolation"] is None
    with pytest.raises(FileExistsError):
        main(args)


def test_extrapolation_requires_single_realized_route(tmp_path: Path) -> None:
    source = tmp_path / "calls.json"
    _export(source)
    document = json.loads(source.read_text(encoding="utf-8"))
    second = dict(document["records"][0], model_id="other", request_id="b")
    document["records"].append(second)
    source.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="one provider, model and role"):
        main(
            [
                "calls",
                "--input",
                str(source),
                "--output",
                str(tmp_path / "out.json"),
                "--fleet-size",
                "10",
            ]
        )


def test_calls_cli_extrapolates_known_constant_latency_burst(tmp_path: Path) -> None:
    source = tmp_path / "calls.json"
    output = tmp_path / "out.json"
    _export(source)
    assert (
        main(
            [
                "calls",
                "--input",
                str(source),
                "--output",
                str(output),
                "--fleet-size",
                "5",
                "--calls-per-robot",
                "2",
                "--concurrency",
                "3",
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["extrapolation"]["elapsed_s"] == 1.0
    assert report["extrapolation"]["total_calls"] == 10
    assert report["extrapolation"]["failed_calls"] == 0


def test_fast_cli_writes_only_control_measurement(tmp_path: Path) -> None:
    output = tmp_path / "control.json"
    assert (
        main(
            [
                "fast",
                "--ticks",
                "1",
                "--warmup-ticks",
                "0",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["llm_calls"] is None
    assert report["extrapolation"] is None
    assert report["model_ids"] == []


def test_extrapolation_does_not_treat_unmeasured_error_latency_as_zero(tmp_path: Path) -> None:
    source = tmp_path / "calls.json"
    output = tmp_path / "out.json"
    _export(source)
    document = json.loads(source.read_text(encoding="utf-8"))
    document["records"].append(
        dict(
            document["records"][0],
            request_id="failed",
            status="error",
            latency_s=0.0,
            cost_usd=0.0,
            tokens_in=0,
            tokens_out=0,
        )
    )
    source.write_text(json.dumps(document), encoding="utf-8")
    assert (
        main(
            [
                "calls",
                "--input",
                str(source),
                "--output",
                str(output),
                "--fleet-size",
                "2",
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["extrapolation"]["inputs"]["latencies_s"] == [0.25]
    assert report["extrapolation"]["inputs"]["failure_rate"] == 0.5
