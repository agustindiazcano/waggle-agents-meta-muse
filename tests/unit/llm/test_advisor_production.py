"""Production advisor assembly wires the production client to the Postgres call log."""

from typing import cast

import pytest
from db_fakes import FakeDatabase
from llm_support import CAPS, MODEL_ENV

from waggle.db.connection import Database
from waggle.db.llm_calls import PostgresCallLog
from waggle.governance.advisor_input import AdvisorInputLimits, TrustedFacts
from waggle.governance.caution import CautionAction, CautionConfig
from waggle.llm.advisor_production import build_production_advisors
from waggle.llm.errors import ConfigError, ProviderError
from waggle.llm.providers import ScriptedProvider

CONFIG = CautionConfig(max_window_ticks=20, h_max_ticks=10, n_max_holds=3)
LIMITS = AdvisorInputLimits(
    max_prompt_chars=2000, min_interval_ticks=5, max_calls_per_task=10, max_messages=5
)
FACTS = TrustedFacts(
    robot_id="R1",
    chassis="forklift",
    speed=1.0,
    active_reasons=("OCCLUSION",),
    zone="Z1",
    task_step="travel",
    nearest_distance=4.2,
    occluded=False,
    geofences=("G1",),
    lease_holders=(("corr_1", "R2"),),
)
SLOW = '{"action":"slow","speed_cap":0.5,"duration_ticks":5,"code":null}'
ENV = {"WAGGLE_LLM_PROVIDER": "mock", **MODEL_ENV, **CAPS}


def _database() -> FakeDatabase:
    return FakeDatabase(lambda _sql, _params: None)


def _build(database: FakeDatabase, provider: ScriptedProvider, **over: object):  # type: ignore[no-untyped-def]
    kwargs: dict[str, object] = {
        "caution_config": CONFIG,
        "input_limits": LIMITS,
        "timeout_s": 2.0,
        "max_response_chars": 1024,
        "rate_limit_ticks": 5,
        "fallbacks_enabled": False,
        "providers": {"baseten": provider},
    }
    kwargs.update(over)
    return build_production_advisors(cast(Database, database), ENV, **kwargs)  # type: ignore[arg-type]


def test_build_makes_no_call_and_writes_nothing() -> None:
    database = _database()
    service = _build(database, ScriptedProvider("baseten", by_role={"advisor": SLOW}))
    assert isinstance(service.call_log, PostgresCallLog)
    assert database.log == []
    assert service.caution_log.events == ()


def test_advise_records_caution_and_one_postgres_call_log_row() -> None:
    database = _database()
    provider = ScriptedProvider("baseten", by_role={"advisor": SLOW})
    service = _build(database, provider)
    result = service.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "accepted"
    assert result.limits[0].speed_cap == 0.5
    assert len(service.caution_log.events) == 1
    assert service.caution_log.events[0].action == CautionAction.SLOW
    assert provider.calls == 1
    writes = database.writes()
    assert len(writes) == 1
    assert writes[0].startswith("INSERT INTO llm_calls")


def test_provider_error_adds_no_caution() -> None:
    database = _database()
    provider = ScriptedProvider(
        "baseten", by_role={"advisor": ProviderError("offline")}, cost_usd=0.01
    )
    service = _build(database, provider)
    result = service.advise(
        FACTS, tick=10, current_cap=1.5, class_max=2.0, run_id="run-1", task_id="task-1"
    )
    assert result.status == "error"
    assert service.caution_log.events == ()
    assert result.limits == ()


def test_missing_mode_fails_closed_before_any_write() -> None:
    database = _database()
    with pytest.raises(ConfigError):
        build_production_advisors(
            cast(Database, database),
            {**MODEL_ENV, **CAPS},
            caution_config=CONFIG,
            input_limits=LIMITS,
            timeout_s=2.0,
            max_response_chars=1024,
            rate_limit_ticks=5,
            fallbacks_enabled=False,
            providers={"baseten": ScriptedProvider("baseten", by_role={"advisor": SLOW})},
        )
    assert database.log == []


def test_provider_override_is_refused_in_http_mode() -> None:
    database = _database()
    with pytest.raises(ConfigError):
        build_production_advisors(
            cast(Database, database),
            {"WAGGLE_LLM_PROVIDER": "http", **MODEL_ENV, **CAPS},
            caution_config=CONFIG,
            input_limits=LIMITS,
            timeout_s=2.0,
            max_response_chars=1024,
            rate_limit_ticks=5,
            fallbacks_enabled=False,
            providers={"baseten": ScriptedProvider("baseten", by_role={"advisor": SLOW})},
        )
    assert database.log == []
