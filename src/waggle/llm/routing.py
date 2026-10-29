"""Role routing table: role to tier, primary route and declared fallback, read from config."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from waggle.llm.budget import PROVIDERS
from waggle.llm.errors import ConfigError, UnknownRoleError

DEFAULT_ROUTES_PATH = Path(__file__).with_name("routes.toml")


class Role(StrEnum):
    """Every LLM role. Roles outside this set fail closed."""

    GUARD = "guard"
    DIRECTOR = "director"
    PLANNER = "planner"
    DIAGNOSIS = "diagnosis"
    COURT_1 = "court_1"
    COURT_2 = "court_2"
    COURT_3 = "court_3"
    ADVISOR = "advisor"
    ORGANIZER = "organizer"
    VOICE = "voice"
    VISION = "vision"


ROLES = tuple(r.value for r in Role)
TIERS = ("fast", "planning")


@dataclass(frozen=True)
class RouteSpec:
    """A provider and the environment variable that holds its model id."""

    provider: str
    model_env: str


@dataclass(frozen=True)
class RoleRoute:
    """Tier, primary route and optional declared fallback for one role."""

    role: str
    tier: str
    primary: RouteSpec
    fallback: RouteSpec | None


def _spec(raw: Mapping[str, str], where: str) -> RouteSpec:
    provider = raw.get("provider", "")
    model_env = raw.get("model_env", "")
    if provider not in PROVIDERS or not model_env:
        raise ConfigError(f"{where}: bad route {dict(raw)}")
    return RouteSpec(provider=provider, model_env=model_env)


class RoutingTable:
    """Immutable mapping from role name to route."""

    def __init__(self, routes: Mapping[str, RoleRoute]) -> None:
        self._routes = dict(routes)

    def get(self, role: str) -> RoleRoute:
        """Return the route for a role, or raise UnknownRoleError."""
        try:
            return self._routes[role]
        except KeyError:
            raise UnknownRoleError(f"unknown role {role!r}") from None


def load_routes(path: Path | None = None) -> RoutingTable:
    """Load and validate the routing table. Every declared role must be present."""
    data = tomllib.loads((path or DEFAULT_ROUTES_PATH).read_text(encoding="utf-8"))
    raw_roles = data.get("roles", {})
    missing = set(ROLES) - set(raw_roles)
    if missing:
        raise ConfigError(f"routes missing roles: {sorted(missing)}")
    routes: dict[str, RoleRoute] = {}
    for name, entry in raw_roles.items():
        tier = entry.get("tier")
        if tier not in TIERS:
            raise ConfigError(f"role {name}: bad tier {tier!r}")
        fallback = entry.get("fallback")
        routes[name] = RoleRoute(
            role=name,
            tier=tier,
            primary=_spec(entry.get("primary", {}), f"role {name} primary"),
            fallback=_spec(fallback, f"role {name} fallback") if fallback else None,
        )
    return RoutingTable(routes)


def resolve_model_id(spec: RouteSpec, environ: Mapping[str, str]) -> str:
    """Read the model id for a route from the environment. Missing or blank fails closed."""
    value = environ.get(spec.model_env, "").strip()
    if not value:
        raise ConfigError(f"{spec.model_env} is not set")
    return value
