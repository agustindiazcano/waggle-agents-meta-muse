"""Provider plan, model tiers and court composition are recorded and consistent."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
NOTICE = "Built with Muse Spark Open"


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _adr(number: int) -> str:
    decisions = _read("docs/DECISIONS.md")
    match = re.search(rf"^## ADR-{number:03d}:.*?(?=^## ADR-|\Z)", decisions, re.S | re.M)
    assert match is not None, f"ADR-{number:03d} not found"
    return match.group(0)


def _tracked_text() -> dict[str, str]:
    git = shutil.which("git")
    assert git is not None
    out = subprocess.run(
        [git, "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, timeout=30
    ).stdout.decode("utf-8")
    texts: dict[str, str] = {}
    for name in out.split("\0"):
        path = ROOT / name
        if not name or name == "uv.lock" or path.resolve() == THIS_FILE or not path.is_file():
            continue
        try:
            texts[name] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return texts


@pytest.mark.parametrize("number", [15, 16, 17])
def test_new_adrs_exist_and_are_proposed(number: int) -> None:
    assert "Status: proposed" in _adr(number)


def test_adr_015_provider_plan() -> None:
    adr = _adr(15)
    for needle in (
        "Partner credits first",
        "10 percent",
        "40 percent",
        "personal card",
        "/v1/models",
        "contributor",
        "synthetic",
        "META_USE_CONTRIBUTOR_TIER",
        "Muse Glimmer",
        "Apache 2.0",
        "Vertex",
        "configuration D",
        "Fallbacks",
        "disabled in held-out",
    ):
        assert needle in adr, needle


def test_adr_016_tiers_and_planner() -> None:
    adr = _adr(16)
    for needle in (
        "Reflex tier",
        "Fast LLM tier",
        "Planning LLM tier",
        "Fleet planner",
        "deterministic validator",
        "deterministic assigner",
        "never per tick",
    ):
        assert needle in adr, needle


def test_adr_017_court_and_guard() -> None:
    adr = _adr(17)
    for needle in (
        "Muse Spark, Muse Spark Open 1026, Muse Glimmer",
        "not three independent families",
        "A single Muse Spark",
        "non-Muse member",
        "talked into",
        "first screen",
        "not the boundary",
        "uncertain",
        "Fail closed",
        "escalation, never to approval",
    ):
        assert needle in adr, needle


def test_superseded_adrs_keep_their_text() -> None:
    adr7 = _adr(7)
    assert "Superseded by ADR-015" in adr7
    assert "Gemini via its API" in adr7
    adr6 = _adr(6)
    assert "Superseded by ADR-017" in adr6
    assert "three families" in adr6


def test_prompt_guard_and_gemini_are_gone_outside_superseded_text() -> None:
    offenders: list[str] = []
    for name, text in _tracked_text().items():
        lowered = text.lower()
        if "prompt guard" in lowered or "prompt_guard" in lowered or "llama" in lowered:
            offenders.append(name)
    assert not offenders, offenders


def test_env_example_names() -> None:
    names = set(re.findall(r"^([A-Z0-9_]+)=", _read(".env.example"), flags=re.MULTILINE))
    required = {
        "META_MODEL_ID",
        "META_USE_CONTRIBUTOR_TIER",
        "MODAL_GLIMMER_MODEL_ID",
        "MODAL_ENDPOINT_URL",
        "META_SPEND_CAP_USD",
        "BASETEN_SPEND_CAP_USD",
        "MODAL_SPEND_CAP_USD",
        "VERTEX_SPEND_CAP_USD",
        "VERTEX_PROJECT_ID",
        "VERTEX_LOCATION",
        "VERTEX_MODEL_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
    }
    assert required <= names
    forbidden = {"GEMINI_API_KEY", "GEMINI_SPEND_CAP_USD", "MODAL_THIRD_FAMILY_MODEL_ID"}
    assert not (forbidden & names)
    assert not [n for n in names if n.startswith("PROMPT_GUARD")]


def test_license_notice_in_readme_and_web_footer() -> None:
    assert NOTICE in _read("README.md")
    html = _read("web/index.html")
    assert NOTICE in html
    assert "<footer" in html


def test_architecture_has_planner_tiers_and_llm_guard() -> None:
    arch = _read("docs/ARCHITECTURE.md")
    assert "## Model tiers and roles" in arch
    assert "| Tier |" in arch
    assert "PLANNER" in arch
    assert "Fleet planner" in arch
    assert "Guard classifier" in arch


def test_experiments_e3_e4_e5() -> None:
    exp = _read("docs/EXPERIMENTS.md")
    assert "Muse Glimmer" in exp
    configs = (
        "A: single Muse Spark",
        "B: two Muse members",
        "C: three Muse members with identical prompts",
        "D: three Muse members with role-specialized checklists",
        "E: two Muse members plus a non-Muse member on Vertex",
    )
    for config in configs:
        assert config in exp, config
    assert "fleet planner" in exp
    assert "label policy is fixed before the run" in exp


def test_plan_phases_reflect_the_decisions() -> None:
    plan = _read("PLAN.md")
    assert "Fleet planner" in plan
    assert "Muse Glimmer" in plan
    assert "Vertex" in plan


def test_pending_has_provider_items() -> None:
    pending = _read("PENDING.md")
    for needle in (
        "Muse Glimmer availability",
        "price per hour",
        "model list",
        "Muse Model License",
        "HTTP client dependency",
        "attribution card",
        "Baseten rate limit",
        "Muse Spark Open versus Muse Spark",
    ):
        assert needle in pending, needle


def test_submission_mentions_attribution_card() -> None:
    assert NOTICE in _read("SUBMISSION.md")
