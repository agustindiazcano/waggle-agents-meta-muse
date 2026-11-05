"""E10 harness on the scripted provider (EXPERIMENTS.md E10).

Every planner call is a ``ScriptedProvider`` through the production ``CrisisRuntime``:
no network, no spend. The deterministic baseline disables the planner layer and lets
code propose the same safe recovery moves, so the planner contribution is an ablation
on identical templates and seeds. A missing script is a real error, never a pass.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from waggle.experiments.e10_caller import CrisisCaller
from waggle.experiments.e10_cases import (
    CONTEXT,
    CrisisTemplate,
    template_belief,
    template_config,
    template_static,
)
from waggle.experiments.e10_configs import Configuration
from waggle.experiments.e10_result import (
    ResultExistsError,
    RunRecord,
    build_record,
    result_path,
    write_result,
)
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.crisis_adapter import PLANNER_PROMPT_VERSION
from waggle.llm.crisis_runtime import CrisisRuntime
from waggle.llm.providers import ScriptedProvider, ScriptMissingError
from waggle.validation.crisis_loop import CrisisResult, PlanProposer, run_crisis_loop

Scripts = Mapping[str, tuple[str, ...]]
_ENV: Final = {
    "WAGGLE_LLM_PROVIDER": "mock",
    "META_MODEL_ID": "scripted-meta",
    "META_WONDER_MODEL_ID": "scripted-meta-wonder",
    "META_VOICE_MODEL_ID": "scripted-meta-voice",
    "BASETEN_MODEL_ID": "scripted-baseten",
    "MODAL_GLIMMER_MODEL_ID": "scripted-modal",
    "MODAL_SPARK_OPEN_MODEL_ID": "scripted-modal-open",
    "VERTEX_MODEL_ID": "scripted-vertex",
    "META_SPEND_CAP_USD": "1.0",
    "BASETEN_SPEND_CAP_USD": "1.0",
    "MODAL_SPEND_CAP_USD": "1.0",
    "VERTEX_SPEND_CAP_USD": "1.0",
}


class _BaselineProposer:
    """Code proposer of the deterministic baseline: one safe plan, no model."""

    def __init__(self, raw: str) -> None:
        self._raw = raw

    def propose(self, feedback: str | None) -> str:
        return self._raw


def _record(template: CrisisTemplate, result: CrisisResult, calls: int, cost: float) -> RunRecord:
    return RunRecord(
        template_id=template.id,
        seed=template.seed,
        status=result.status,
        rounds=result.rounds,
        calls=calls,
        cost_usd=cost,
        counterexamples=sum(r.counterexamples for r in result.history),
        outcomes=tuple(r.outcome for r in result.history),
    )


def run_template(config: Configuration, template: CrisisTemplate, scripts: Scripts) -> RunRecord:
    """Run one template in one configuration and return its record."""
    if not config.uses_llm:
        proposer: PlanProposer = _BaselineProposer(template.baseline_raw)
        result = run_crisis_loop(
            proposer,
            mission_id=template.mission_id,
            context=CONTEXT,
            static=template_static(template),
            config=template_config(template),
            belief=template_belief(template),
            k=2,
            max_attempts=1000,
            variant_timeout_s=60.0,
            max_rounds=config.max_rounds,
        )
        return _record(template, result, 0, 0.0)
    if template.id not in scripts:
        raise ScriptMissingError(f"{template.id}: no script for planner")
    provider = ScriptedProvider("meta", by_role={"planner": tuple(scripts[template.id])})
    log = InMemoryCallLog()
    runtime = CrisisRuntime.from_environment(
        _ENV, log, fallbacks_enabled=False, providers={"meta": provider}
    )
    result = CrisisCaller(runtime).replan(template, max_rounds=config.max_rounds)
    cost = round(sum(r.cost_usd for r in log.records()), 6)
    return _record(template, result, provider.calls, cost)


def run_e10(
    config: Configuration,
    templates: Sequence[CrisisTemplate],
    scripts: Scripts,
    *,
    commit: str,
    run_date: str,
    out_dir: Path,
    seed_set: str = "development",
) -> Path:
    """Run one configuration over every template, then write its result file.

    Refuses a held-out seed set (this harness is development only), no templates,
    and an existing result file for the same configuration.
    """
    if seed_set != "development":
        raise ValueError("the E10 harness runs development seeds only")
    if not templates:
        raise ValueError("no templates to run")
    path = result_path(out_dir, config.name, seed_set)
    if path.exists():
        raise ResultExistsError(f"{path.name} exists and is not overwritten")
    runs = [run_template(config, t, scripts) for t in sorted(templates, key=lambda t: t.id)]
    record = build_record(
        config=config,
        seed_set=seed_set,
        commit=commit,
        run_date=run_date,
        runs=runs,
        prompt_version=PLANNER_PROMPT_VERSION,
    )
    write_result(path, record)
    return path
