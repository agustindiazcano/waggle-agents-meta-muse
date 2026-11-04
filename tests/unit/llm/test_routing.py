import re
from pathlib import Path

import pytest

from waggle.llm.budget import PROVIDERS
from waggle.llm.errors import ConfigError, UnknownRoleError
from waggle.llm.routing import META_ROUTES_PATH, ROLES, Role, load_routes, resolve_model_id

ROOT = Path(__file__).resolve().parents[3]

EXPECTED_ROLES = {
    "guard",
    "director",
    "planner",
    "diagnosis",
    "court_1",
    "court_2",
    "court_3",
    "advisor",
    "organizer",
    "voice",
    "vision",
}


def test_role_set_is_exactly_the_declared_one() -> None:
    assert {r.value for r in Role} == EXPECTED_ROLES
    assert set(ROLES) == EXPECTED_ROLES


@pytest.mark.parametrize("role", sorted(EXPECTED_ROLES))
def test_every_role_resolves_to_a_configured_route(role: str) -> None:
    route = load_routes().get(role)
    assert route.tier in {"fast", "planning"}
    assert route.primary.provider in PROVIDERS
    assert route.primary.model_env
    if route.fallback is not None:
        assert route.fallback.provider in PROVIDERS
        assert route.fallback.provider != route.primary.provider


def test_unknown_role_fails_closed() -> None:
    with pytest.raises(UnknownRoleError):
        load_routes().get("root_admin")


def test_court_members_use_the_declared_providers() -> None:
    table = load_routes()
    assert table.get("court_1").primary.provider == "meta"
    assert table.get("court_2").primary.provider == "baseten"
    assert table.get("court_3").primary.provider == "modal"
    assert table.get("guard").primary.provider == "modal"


def test_fast_tier_is_baseten_advisors_and_guard() -> None:
    table = load_routes()
    assert table.get("advisor").tier == "fast"
    assert table.get("organizer").tier == "fast"
    assert table.get("advisor").primary.provider == "baseten"
    assert table.get("director").tier == "planning"
    assert table.get("planner").tier == "planning"


def test_roles_without_fallback_are_the_meta_roles() -> None:
    table = load_routes()
    for role in ("director", "planner", "diagnosis", "court_1", "voice", "vision"):
        assert table.get(role).fallback is None


def test_planning_roles_use_meta_wonder_model_env() -> None:
    table = load_routes()
    for role in ("director", "planner", "diagnosis"):
        primary = table.get(role).primary
        assert primary.provider == "meta"
        assert primary.model_env == "META_WONDER_MODEL_ID"
    for role in ("court_1", "vision"):
        primary = table.get(role).primary
        assert primary.provider == "meta"
        assert primary.model_env == "META_MODEL_ID"
    assert table.get("voice").primary.model_env == "META_VOICE_MODEL_ID"


def test_meta_only_profile_routes_every_role_to_meta() -> None:
    table = load_routes(META_ROUTES_PATH)
    for role in EXPECTED_ROLES:
        route = table.get(role)
        assert route.primary.provider == "meta"
        assert route.fallback is None
    for role in ("director", "planner", "diagnosis", "court_2"):
        assert table.get(role).primary.model_env == "META_WONDER_MODEL_ID"
    for role in ("court_1", "court_3", "guard", "advisor", "organizer", "vision"):
        assert table.get(role).primary.model_env == "META_MODEL_ID"
    assert table.get("voice").primary.model_env == "META_VOICE_MODEL_ID"


def test_model_id_comes_from_config_not_code() -> None:
    spec = load_routes().get("director").primary
    assert (
        resolve_model_id(spec, {spec.model_env: "from-the-models-list"}) == "from-the-models-list"
    )
    with pytest.raises(ConfigError):
        resolve_model_id(spec, {})
    with pytest.raises(ConfigError):
        resolve_model_id(spec, {spec.model_env: " "})


def test_routes_file_has_no_hardcoded_model_ids() -> None:
    for path in (ROOT / "src" / "waggle" / "llm" / "routes.toml", META_ROUTES_PATH):
        text = path.read_text(encoding="utf-8")
        assert "muse-spark" not in text.lower()
        assert "muse-wonder" not in text.lower()
        assert "gemini" not in text.lower()


def test_every_route_env_name_is_listed_in_env_example() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    names = set(re.findall(r"^([A-Z0-9_]+)=", example, flags=re.MULTILINE))
    table = load_routes()
    for role in EXPECTED_ROLES:
        route = table.get(role)
        assert route.primary.model_env in names, route.primary.model_env
        if route.fallback is not None:
            assert route.fallback.model_env in names, route.fallback.model_env
