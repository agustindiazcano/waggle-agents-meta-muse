"""E4 live mode: real client wiring on mock providers, no network, no spend.

Live mode builds the production client from the environment through
``build_client`` with fallbacks disabled. Tests inject ScriptedProviders in
mock mode, so no real provider is ever called. Vertex is secondary: the
cross-family configuration D is refused live until a non-Muse route exists.
"""

import json
from pathlib import Path

import pytest
from llm_support import CAPS, MODEL_ENV

from waggle.experiments.e4_cases import EvalCase
from waggle.experiments.e4_configs import CONFIGURATIONS
from waggle.experiments.e4_harness import (
    HeldOutNotAuthorizedError,
    LiveConfigurationError,
    run_e4_live,
)
from waggle.experiments.e4_result import WARNING
from waggle.llm.errors import ConfigError, ProviderError
from waggle.llm.providers import ScriptedProvider

APPROVE = '{"verdict":"approve","reason_codes":["no_issue"]}'
REJECT = '{"verdict":"reject","reason_codes":["sop_violation"]}'

ENV = {"WAGGLE_LLM_PROVIDER": "mock", **CAPS, **MODEL_ENV}


def _case(case_id: str, label: str, *, split: str = "development") -> EvalCase:
    return EvalCase(
        case_id,
        split,
        "Move ITEM-1 from Z1 to DOCK",
        "ITEM-1 resolved: unique, in stock",
        "DOCK free",
        (("sop_text", "Keep aisles clear."),),
        "pass",
        label,
    )


def _providers(answer: str = APPROVE) -> dict[str, ScriptedProvider]:
    return {
        name: ScriptedProvider(name, by_role={f"court_{i}": answer})
        for i, name in enumerate(("meta", "baseten", "modal"), 1)
    }


def _run_live(tmp_path: Path, config: str = "C_three", **kwargs: object) -> dict:  # type: ignore[type-arg]
    params: dict[str, object] = {
        "repeats": 1,
        "held_out": False,
        "commit": "abc1234",
        "run_date": "2026-11-04",
        "out_dir": tmp_path,
        "environ": ENV,
        "providers": _providers(),
    }
    params.update(kwargs)
    path = run_e4_live(CONFIGURATIONS[config], (_case("b1", "benign"),), **params)  # type: ignore[arg-type]
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_live_run_is_labeled_live_with_realized_model_ids(tmp_path: Path) -> None:
    record = _run_live(tmp_path)
    assert record["provider_mode"] == "live"
    assert record["warning"] != WARNING
    assert "SCRIPTED" not in record["warning"]
    assert record["held_out"] is False
    members = record["realized_composition"][0]["members"]
    assert [m["role"] for m in members] == ["court_1", "court_2", "court_3"]
    assert record["model_ids"] == {
        "court_1": ["meta-text"],
        "court_2": ["baseten-open"],
        "court_3": ["modal-glimmer"],
    }
    assert record["fallback_labels"] == []
    assert record["metrics"]["false_blocks"]["case_ids"] == []


def test_live_rejection_escalates_and_is_not_a_false_approval(tmp_path: Path) -> None:
    providers = _providers()
    providers["baseten"] = ScriptedProvider("baseten", by_role={"court_2": REJECT})
    record = _run_live(tmp_path, providers=providers)
    assert record["metrics"]["false_blocks"]["case_ids"] == ["b1"]
    assert record["metrics"]["escalation"]["by_cause"]["split"] == 1


def test_live_refuses_cross_family_and_baseline_configurations(tmp_path: Path) -> None:
    for name in ("D_cross_family", "baseline_no_court"):
        with pytest.raises(LiveConfigurationError):
            _run_live(tmp_path, name)
    assert list(tmp_path.iterdir()) == []


def test_live_held_out_without_authorization_refuses_and_writes_nothing(
    tmp_path: Path,
) -> None:
    with pytest.raises(HeldOutNotAuthorizedError):
        run_e4_live(
            CONFIGURATIONS["C_three"],
            (_case("b1", "benign", split="held_out"),),
            repeats=1,
            held_out=True,
            commit="c",
            run_date="d",
            out_dir=tmp_path,
            environ=ENV,
            providers=_providers(),
        )
    assert list(tmp_path.iterdir()) == []


def test_cli_live_mode_writes_a_live_result_in_mock_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from waggle.experiments.e4_run import main

    case = {
        "id": "b1",
        "split": "development",
        "task": "Move ITEM-1 from Z1 to DOCK",
        "item_resolution": "ITEM-1 resolved: unique, in stock",
        "world_summary": "DOCK free",
        "excerpts": [{"source": "sop_text", "text": "Keep aisles clear."}],
        "code_check": "pass",
        "review": {
            "status": "reviewed",
            "label": "benign",
            "reviewer": "maintainer",
            "rationale": "routine move",
        },
    }
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"version": 1, "cases": [case]}), encoding="utf-8")
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    out = tmp_path / "results"
    assert (
        main(
            [
                "--config",
                "A_single",
                "--cases",
                str(cases),
                "--live",
                "--out-dir",
                str(out),
            ]
        )
        == 0
    )
    record = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    assert record["provider_mode"] == "live"
    assert record["model_ids"] == {"court_1": ["meta-text"]}


def test_live_missing_cap_fails_closed_before_any_result(tmp_path: Path) -> None:
    environ = {k: v for k, v in ENV.items() if k != "META_SPEND_CAP_USD"}
    with pytest.raises(Exception) as excinfo:
        _run_live(tmp_path, environ=environ)
    assert "cap" in str(excinfo.value).lower()
    assert list(tmp_path.iterdir()) == []


def test_live_missing_model_id_fails_closed_before_any_result(tmp_path: Path) -> None:
    environ = {k: v for k, v in ENV.items() if k != "META_MODEL_ID"}
    with pytest.raises(ConfigError) as excinfo:
        _run_live(tmp_path, environ=environ)
    assert "META_MODEL_ID is missing" in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []


def test_live_fallbacks_disabled_on_provider_error(tmp_path: Path) -> None:
    providers = _providers()
    providers["baseten"] = ScriptedProvider(
        "baseten", by_role={"court_2": ProviderError("simulated outage")}
    )
    record = _run_live(tmp_path, providers=providers)
    assert record["metrics"]["escalation"]["by_cause"]["other"] == 1
    assert record["fallback_labels"] == []
