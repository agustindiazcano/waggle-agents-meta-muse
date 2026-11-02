"""Checks of what a client may ask for: an allowlisted scenario id or a replay file name.

A replay name is a relative path with forward slashes under the configured replay directory.
Absolute paths, drive letters, backslashes, parent references and links that leave the
directory are rejected. Error text never echoes the client input.
"""

from pathlib import Path, PurePosixPath

from waggle.sim import scenarios

MAX_NAME = 200
REPLAY_SUFFIX = ".jsonl"


class Rejected(ValueError):
    """A client request names something outside the allowlist."""


def check_scenario(scenario_id: str) -> str:
    """The scenario id when it is one of the generated scenarios, else Rejected."""
    if scenario_id not in scenarios.SCENARIO_IDS:
        raise Rejected("unknown scenario")
    return scenario_id


def _clean_parts(name: str) -> tuple[str, ...]:
    if not name or len(name) > MAX_NAME:
        raise Rejected("invalid replay name")
    if any(ch in name for ch in ("\x00", "\\", ":")) or name.startswith("/"):
        raise Rejected("invalid replay name")
    parts = PurePosixPath(name).parts
    if not parts or any(part in ("..", ".", "") for part in parts):
        raise Rejected("invalid replay name")
    if not parts[-1].endswith(REPLAY_SUFFIX):
        raise Rejected("invalid replay name")
    return parts


def resolve_replay(base: Path, name: str) -> Path:
    """The real path of a replay file under ``base``. Raises Rejected on any problem."""
    parts = _clean_parts(name)
    root = base.resolve()
    try:
        target = root.joinpath(*parts).resolve(strict=True)
    except (OSError, ValueError) as error:
        raise Rejected("replay not found") from error
    if not target.is_relative_to(root) or not target.is_file():
        raise Rejected("replay not found")
    return target
