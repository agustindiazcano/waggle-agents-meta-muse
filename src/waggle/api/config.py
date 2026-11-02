"""Configuration of waggle.api, read from environment variables.

| Variable | Meaning | Default |
| --- | --- | --- |
| WAGGLE_API_HOST | bind address | 127.0.0.1 |
| WAGGLE_API_PORT | bind port | 8000 |
| WAGGLE_REPLAY_DIR | the only directory replay files are read from | replays |
| WAGGLE_API_MAX_FPS | most frames sent per second | 30 |
| WAGGLE_API_STRIDE | send every Nth simulator tick | 1 |
| WAGGLE_API_MAX_FRAME_BYTES | frame size cap, at most the contract cap | 262144 |
| WAGGLE_API_LIVE_SEED | seed of live runs (clients cannot choose it) | 0 |
| WAGGLE_COMMIT | commit recorded in live frames | unknown |

A missing or invalid value fails closed with ConfigError.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from waggle.sim import frame

MAX_FPS_LIMIT = 240.0


class ConfigError(ValueError):
    """A configuration value is invalid."""


@dataclass(frozen=True)
class ApiConfig:
    """Validated settings of the API process."""

    host: str = "127.0.0.1"
    port: int = 8000
    replay_dir: Path = Path("replays")
    max_fps: float = 30.0
    stride: int = 1
    max_frame_bytes: int = frame.MAX_FRAME_BYTES
    live_seed: int = 0
    commit: str = "unknown"


def _number(env: Mapping[str, str], name: str, default: str) -> float:
    try:
        value = float(env.get(name, default))
    except ValueError as error:
        raise ConfigError(f"{name} must be a number") from error
    if not math.isfinite(value):
        raise ConfigError(f"{name} must be finite")
    return value


def _integer(env: Mapping[str, str], name: str, default: str, low: int, high: int) -> int:
    try:
        value = int(env.get(name, default))
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer") from error
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


def from_env(env: Mapping[str, str]) -> ApiConfig:
    """Build the configuration from environment-like mapping. Raises ConfigError."""
    fps = _number(env, "WAGGLE_API_MAX_FPS", "30")
    if not 0 < fps <= MAX_FPS_LIMIT:
        raise ConfigError(f"WAGGLE_API_MAX_FPS must be above 0 and at most {MAX_FPS_LIMIT:g}")
    commit = env.get("WAGGLE_COMMIT", "unknown")
    if not commit or len(commit) > frame.MAX_STRING:
        raise ConfigError("WAGGLE_COMMIT is empty or too long")
    return ApiConfig(
        host=env.get("WAGGLE_API_HOST", "127.0.0.1"),
        port=_integer(env, "WAGGLE_API_PORT", "8000", 1, 65535),
        replay_dir=Path(env.get("WAGGLE_REPLAY_DIR", "replays")),
        max_fps=fps,
        stride=_integer(env, "WAGGLE_API_STRIDE", "1", 1, 10_000),
        max_frame_bytes=_integer(
            env, "WAGGLE_API_MAX_FRAME_BYTES", str(frame.MAX_FRAME_BYTES), 1, frame.MAX_FRAME_BYTES
        ),
        live_seed=_integer(env, "WAGGLE_API_LIVE_SEED", "0", 0, 2**31 - 1),
        commit=commit,
    )
