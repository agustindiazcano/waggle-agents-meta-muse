"""E5 wiring: client factory and call log in the harness, replay from a file (mock mode only)."""

from pathlib import Path
from typing import Any

import pytest
from db_fakes import FakeDatabase

from waggle.db.llm_calls import PostgresCallLog
from waggle.experiments import e5_advisors
from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e5_advisors import E5Runner, RunSpec
from waggle.governance.advisor_input import AdvisorInputLimits
from waggle.governance.caution import CautionConfig, CautionRejected
from waggle.governance.caution_file import write_caution_log
from waggle.governance.caution_log import CautionLog
from waggle.governance.classifier import MockClassifier
from waggle.llm import client_factory
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.errors import ConfigError
from waggle.llm.provider_config import MODE_VAR

SEED = 419688070
TICKS = 25
SLOW = '{"action":"slow","speed_cap":0.2,"duration_ticks":50,"code":null}'
CONFIG = CautionConfig(max_window_ticks=100, h_max_ticks=50, n_max_holds=3)
LIMITS = AdvisorInputLimits(
    max_prompt_chars=2000, min_interval_ticks=5, max_calls_per_task=10, max_messages=5
)
ENV = {
    MODE_VAR: "mock",
    "META_MODEL_ID": "m1",
    "META_VOICE_MODEL_ID": "m2",
    "BASETEN_MODEL_ID": "m3",
    "MODAL_GLIMMER_MODEL_ID": "m4",
    "MODAL_SPARK_OPEN_MODEL_ID": "m5",
    "VERTEX_MODEL_ID": "m6",
    **{f"{p}_SPEND_CAP_USD": "10.0" for p in ("META", "BASETEN", "MODAL", "VERTEX")},
}


def _runner(**extra: Any) -> E5Runner:
    return E5Runner(
        caution_config=CONFIG,
        input_limits=LIMITS,
        timeout_s=2.0,
        rate_limit_ticks=5,
        max_response_chars=1024,
        near_threshold_m=3.0,
        classifier=MockClassifier(response='{"label":"benign","reason_code":"ok"}'),
        base_config=BY_NAME["envelope_oracle"],
        **extra,
    )


def _spec(config: str = "C1", **over: Any) -> RunSpec:
    args: dict[str, Any] = {"ticks": TICKS, "provider_script": {"advisor": SLOW}}
    args.update(over)
    return RunSpec(config, "S01", SEED, **args)


def test_injected_in_memory_log_receives_every_advisor_call_without_fallback() -> None:
    log = InMemoryCallLog()
    record = _runner(client_environ=ENV, call_log=log).run_one(_spec())
    rows = log.records()
    assert record["advisor_calls"] > 0
    assert len(rows) == record["advisor_calls"]
    assert {r.role for r in rows} == {"advisor"}
    assert all(r.fallback_label is None for r in rows)


def test_injected_postgres_log_writes_one_insert_per_call() -> None:
    database = FakeDatabase(lambda _sql, _params: None)
    log = PostgresCallLog(database, "mock")  # type: ignore[arg-type]
    record = _runner(client_environ=ENV, call_log=log).run_one(_spec())
    assert record["advisor_calls"] > 0
    assert len(database.writes()) == record["advisor_calls"]
    assert all("llm_calls" in sql for sql in database.writes())


def test_fallbacks_are_disabled_in_the_factory_call(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    original = client_factory.build_client

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(dict(kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(e5_advisors, "build_client", spy)
    _runner(client_environ=ENV, call_log=InMemoryCallLog()).run_one(_spec())
    assert seen
    assert all(call["fallbacks_enabled"] is False for call in seen)


def test_http_mode_is_refused_before_any_call() -> None:
    log = InMemoryCallLog()
    with pytest.raises(ConfigError):
        _runner(client_environ={**ENV, MODE_VAR: "http"}, call_log=log)
    with pytest.raises(ConfigError):
        _runner(client_environ={k: v for k, v in ENV.items() if k != MODE_VAR}, call_log=log)
    assert log.records() == []


def test_a_call_log_without_an_environment_is_refused() -> None:
    with pytest.raises(ValueError, match="client_environ"):
        _runner(call_log=InMemoryCallLog())


def test_a_missing_cap_in_the_injected_environment_denies_the_call_and_adds_no_caution() -> None:
    env = {k: v for k, v in ENV.items() if not k.endswith("_SPEND_CAP_USD")}
    record = _runner(client_environ=env, call_log=InMemoryCallLog()).run_one(_spec())
    assert record["cautions_issued"] == 0


def test_c1_replay_runs_from_a_file_and_matches_the_recorded_run(tmp_path: Path) -> None:
    runner = _runner()
    recorded = runner.run_one(_spec())
    log = CautionLog.from_jsonl(recorded["caution_log_jsonl"], CONFIG)
    assert log.events
    target = tmp_path / "c1.jsonl"
    write_caution_log(target, log)
    replay = runner.run_one(_spec("C1_REPLAY", replay_path=target, provider_script=None))
    assert replay["event_log_digest"] == recorded["event_log_digest"]
    assert replay["final_hash"] == recorded["final_hash"]
    assert replay["widening_ticks"] == 0


def test_replay_from_a_file_with_a_bad_line_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "bad.jsonl"
    target.write_text('{"action":"slow"}\n', encoding="utf-8")
    with pytest.raises(CautionRejected):
        _runner().run_one(_spec("C1_REPLAY", replay_path=target, provider_script=None))


def test_replay_needs_exactly_one_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="replay"):
        _runner().run_one(_spec("C1_REPLAY", provider_script=None))
    both = _spec("C1_REPLAY", replay_path=tmp_path / "x.jsonl", replay_log="", provider_script=None)
    with pytest.raises(ValueError, match="replay"):
        _runner().run_one(both)
