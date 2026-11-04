"""E4 harness, scripted and live (COURT_DESIGN sections 8 and 10, branch 7).

Scripted mode: every reviewer is a ``ScriptedProvider``: no network, no spend, no secrets. A
run checks the harness arithmetic and the court plumbing. It is never a model result, and the
result file says so.

Live mode (``run_e4_live``): reviewers are real provider calls through the production client
built from the environment, with fallbacks disabled. Only configurations A, B and C run live:
the baseline makes no court calls and the cross-family configuration D needs a non-Muse
``court_3`` route, which is a maintainer configuration change (Vertex is secondary). A missing
cap or model id for a used route is a real error before any call, never an empty pass.

Each configuration runs on identical cases. The baseline "no court" lets the code checks
decide alone, so the court's contribution is an ablation.

A held-out run needs the explicit ``held_out_authorized`` argument and never overwrites an
existing result. Fallbacks are always off. Repeats of a case use ``-r<n>`` request ids so each is
a real call, and they are reported as repeats.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from waggle.experiments.e4_cases import SEED_SETS, EvalCase
from waggle.experiments.e4_configs import Configuration
from waggle.experiments.e4_metrics import RunRecord, Summary, VoteRecord
from waggle.experiments.e4_result import (
    LIVE_PROVIDER_MODE,
    ResultExistsError,
    build_record,
    result_path,
    write_result,
)
from waggle.governance.court_round import (
    InMemoryRoundStore,
    PreCheck,
    PreCheckFailure,
    RoundResult,
    run_round,
)
from waggle.llm.budget import PROVIDERS, BudgetGuard, parse_cap
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.client_factory import build_client
from waggle.llm.court_adapter import COURT_PROMPT_HASH, COURT_PROMPT_VERSION, CourtReviewer
from waggle.llm.errors import ConfigError
from waggle.llm.providers import Entry, Provider, ScriptedProvider, ScriptMissingError
from waggle.llm.routing import load_routes

Scripts = Mapping[str, Mapping[str, Entry]]
DEFAULT_CAP_USD: Final = 1.0
DEFAULT_DEADLINE_S: Final = 5.0
_ENV: Final = {
    "META_MODEL_ID": "scripted-meta",
    "BASETEN_MODEL_ID": "scripted-baseten",
    "MODAL_GLIMMER_MODEL_ID": "scripted-modal",
    "MODAL_SPARK_OPEN_MODEL_ID": "scripted-modal-open",
    "VERTEX_MODEL_ID": "scripted-vertex",
}


class HeldOutNotAuthorizedError(PermissionError):
    """A held-out run was requested without the explicit authorization argument."""


class LiveConfigurationError(ValueError):
    """A configuration that live mode refuses: baseline or cross-family D."""


LIVE_CONFIGURATIONS: Final = frozenset({"A_single", "B_two", "C_three"})


def _pre_checks(case: EvalCase) -> tuple[PreCheck, ...]:
    if case.code_check == "deny":
        return (lambda: PreCheckFailure("deny", "code_check"),)
    if case.code_check == "escalate":
        return (lambda: PreCheckFailure("escalate", "code_check"),)
    return ()


def _baseline_run(case: EvalCase, repeat: int) -> RunRecord:
    action = {"pass": "execute", "deny": "deny", "escalate": "escalate"}[case.code_check]
    return RunRecord(case.id, case.label, repeat, action, f"code_check_{case.code_check}", ())


def _votes(result: RoundResult) -> tuple[VoteRecord, ...]:
    return tuple(
        VoteRecord(
            m.role,
            m.vote.verdict.value if m.vote else None,
            m.cause,
            m.model_id,
            m.fallback_label,
        )
        for m in result.record.members
    )


def run_case(
    config: Configuration,
    case: EvalCase,
    scripts: Scripts,
    *,
    repeat: int,
    held_out: bool,
    cap_usd: float = DEFAULT_CAP_USD,
    deadline_s: float = DEFAULT_DEADLINE_S,
) -> RunRecord:
    """Run one case once in one configuration and return its record.

    A court configuration whose scripts miss a reviewer raises ``ScriptMissingError``: an
    absent answer is a real error, never an empty pass (AGENTS.md 11.2).
    """
    if not config.court:
        return _baseline_run(case, repeat)
    table = load_routes()
    case_scripts = scripts.get(case.id, {})
    providers: dict[str, ScriptedProvider] = {}
    for role in config.roles:
        if role not in case_scripts:
            raise ScriptMissingError(f"{case.id}: no script for {role}")
        name = table.get(role).primary.provider
        providers[role] = ScriptedProvider(name, by_role={role: case_scripts[role]})
    log = InMemoryCallLog()
    client = LlmClient(
        providers={p.name: p for p in providers.values()},
        table=table,
        guard=BudgetGuard({f"{p.upper()}_SPEND_CAP_USD": str(cap_usd) for p in PROVIDERS}, log),
        log=log,
        environ=_ENV,
        fallbacks_enabled=False,
    )
    result = run_round(
        case.review_request(),
        CourtReviewer(client),
        config.roles,
        store=InMemoryRoundStore(),
        call_log=log,
        task_id=f"{case.id}-r{repeat}",
        held_out=held_out,
        deadline_s=deadline_s,
        pre_checks=_pre_checks(case),
        repeat=repeat,
    )
    return RunRecord(
        case.id,
        case.label,
        repeat,
        result.action,
        result.record.reason,
        _votes(result),
        tuple(log.records()),
    )


def _prepare(
    config: Configuration,
    cases: Sequence[EvalCase],
    *,
    repeats: int,
    held_out: bool,
    held_out_authorized: bool,
    out_dir: Path,
) -> tuple[str, Path]:
    """Validate a run before any call and return its seed set and result path."""
    seed_set = SEED_SETS[1] if held_out else SEED_SETS[0]
    if held_out and not held_out_authorized:
        raise HeldOutNotAuthorizedError("a held-out run needs the explicit authorization argument")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    if not cases:
        raise ValueError("no cases to run")
    if any(case.split != seed_set for case in cases):
        raise ValueError(f"every case must be in the {seed_set} split")
    path = result_path(out_dir, config.name, seed_set)
    if path.exists():
        raise ResultExistsError(f"{path.name} exists and is not overwritten")
    return seed_set, path


def run_e4(
    config: Configuration,
    cases: Sequence[EvalCase],
    scripts: Scripts,
    *,
    repeats: int,
    held_out: bool,
    commit: str,
    run_date: str,
    out_dir: Path,
    held_out_authorized: bool = False,
    cap_usd: float = DEFAULT_CAP_USD,
    deadline_s: float = DEFAULT_DEADLINE_S,
) -> Path:
    """Run one configuration over every case and repeat, then write its result file.

    Refuses before any work: a held-out run without ``held_out_authorized``, cases from the wrong
    seed set, no cases, a bad repeat count, and an existing result file for the same
    configuration and seed set. Returns the path of the new file.
    """
    seed_set, path = _prepare(
        config,
        cases,
        repeats=repeats,
        held_out=held_out,
        held_out_authorized=held_out_authorized,
        out_dir=out_dir,
    )
    runs = [
        run_case(
            config,
            case,
            scripts,
            repeat=n,
            held_out=held_out,
            cap_usd=cap_usd,
            deadline_s=deadline_s,
        )
        for case in sorted(cases, key=lambda c: c.id)
        for n in range(repeats)
    ]
    record: Summary = build_record(
        config=config,
        seed_set=seed_set,
        held_out=held_out,
        commit=commit,
        run_date=run_date,
        runs=runs,
        prompt_version=COURT_PROMPT_VERSION,
        prompt_hash=COURT_PROMPT_HASH,
    )
    write_result(path, record)
    return path


def _check_live_config(config: Configuration) -> None:
    if config.name not in LIVE_CONFIGURATIONS:
        raise LiveConfigurationError(
            f"{config.name} does not run live: the baseline makes no court calls and "
            "cross-family D needs a non-Muse court_3 route (maintainer configuration)"
        )


def _check_live_environ(config: Configuration, environ: Mapping[str, str]) -> None:
    """Refuse before any call when a used route lacks its cap or model id."""
    table = load_routes()
    for role in config.roles:
        route = table.get(role).primary
        parse_cap(route.provider, environ)
        if not environ.get(route.model_env, "").strip():
            raise ConfigError(f"{route.model_env} is missing")


def run_case_live(
    config: Configuration,
    case: EvalCase,
    *,
    repeat: int,
    held_out: bool,
    environ: Mapping[str, str],
    providers: Mapping[str, Provider] | None = None,
    deadline_s: float = DEFAULT_DEADLINE_S,
) -> RunRecord:
    """Run one case once live through the production client, fallbacks disabled."""
    _check_live_config(config)
    log = InMemoryCallLog()
    client = build_client(environ, log, fallbacks_enabled=False, providers=providers)
    result = run_round(
        case.review_request(),
        CourtReviewer(client),
        config.roles,
        store=InMemoryRoundStore(),
        call_log=log,
        task_id=f"{case.id}-r{repeat}",
        held_out=held_out,
        deadline_s=deadline_s,
        pre_checks=_pre_checks(case),
        repeat=repeat,
    )
    return RunRecord(
        case.id,
        case.label,
        repeat,
        result.action,
        result.record.reason,
        _votes(result),
        tuple(log.records()),
    )


def run_e4_live(
    config: Configuration,
    cases: Sequence[EvalCase],
    *,
    repeats: int,
    held_out: bool,
    commit: str,
    run_date: str,
    out_dir: Path,
    environ: Mapping[str, str],
    providers: Mapping[str, Provider] | None = None,
    held_out_authorized: bool = False,
    deadline_s: float = DEFAULT_DEADLINE_S,
) -> Path:
    """Run one live configuration over every case and repeat, then write its result.

    Refuses before any call: a configuration live mode does not support, a held-out
    run without authorization, cases from the wrong seed set, no cases, a bad repeat
    count, an existing result file, and a missing cap or model id for a used route.
    """
    _check_live_config(config)
    seed_set, path = _prepare(
        config,
        cases,
        repeats=repeats,
        held_out=held_out,
        held_out_authorized=held_out_authorized,
        out_dir=out_dir,
    )
    _check_live_environ(config, environ)
    runs = [
        run_case_live(
            config,
            case,
            repeat=n,
            held_out=held_out,
            environ=environ,
            providers=providers,
            deadline_s=deadline_s,
        )
        for case in sorted(cases, key=lambda c: c.id)
        for n in range(repeats)
    ]
    record: Summary = build_record(
        config=config,
        seed_set=seed_set,
        held_out=held_out,
        commit=commit,
        run_date=run_date,
        runs=runs,
        prompt_version=COURT_PROMPT_VERSION,
        prompt_hash=COURT_PROMPT_HASH,
        provider_mode=LIVE_PROVIDER_MODE,
    )
    write_result(path, record)
    return path
