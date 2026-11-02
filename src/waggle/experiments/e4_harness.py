"""E4 harness on the scripted provider (COURT_DESIGN sections 8 and 10, branch 7).

Every reviewer is a ``ScriptedProvider``: no network, no spend, no secrets, no live mode. A run
checks the harness arithmetic and the court plumbing. It is never a model result, and the result
file says so. Each configuration runs on identical cases. The baseline "no court" lets the code
checks decide alone, so the court's contribution is an ablation.

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
from waggle.llm.budget import PROVIDERS, BudgetGuard
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.court_adapter import COURT_PROMPT_HASH, COURT_PROMPT_VERSION, CourtReviewer
from waggle.llm.providers import Entry, ScriptedProvider, ScriptMissingError
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
    pre_checks: tuple[PreCheck, ...] = ()
    if case.code_check == "deny":
        pre_checks = (lambda: PreCheckFailure("deny", "code_check"),)
    elif case.code_check == "escalate":
        pre_checks = (lambda: PreCheckFailure("escalate", "code_check"),)
    result = run_round(
        case.review_request(),
        CourtReviewer(client),
        config.roles,
        store=InMemoryRoundStore(),
        call_log=log,
        task_id=f"{case.id}-r{repeat}",
        held_out=held_out,
        deadline_s=deadline_s,
        pre_checks=pre_checks,
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
