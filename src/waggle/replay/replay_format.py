"""Replay file format: one header line, one frame per line, one footer line (JSON Lines).

The header carries ``schema_version``, ``commit``, ``seed``, ``scenario_id``, ``dt``, the world
hash, the frame count and whether the file can be checked by re-running the simulator. The
footer carries the final state hash and a digest of the frame lines. The reader is strict: an
unknown version, an unknown field, a missing field or a count mismatch is refused.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from waggle.sim import frame

HEADER_FIELDS = {
    "type",
    "schema_version",
    "commit",
    "seed",
    "scenario_id",
    "dt",
    "world_hash",
    "frame_count",
    "resimulable",
}
FOOTER_FIELDS = {"type", "final_state_hash", "frames_digest"}
MAX_LINE_BYTES = frame.MAX_FRAME_BYTES


class ReplayError(ValueError):
    """A replay file is malformed, tampered with or of an unknown version."""


@dataclass(frozen=True)
class Replay:
    """A parsed replay: header, frames in order, footer and the raw frame lines."""

    header: dict[str, Any]
    frames: tuple[frame.JsonObject, ...]
    footer: dict[str, Any]
    lines: tuple[str, ...]


def digest_lines(lines: list[str] | tuple[str, ...]) -> str:
    """SHA-256 over the frame lines, each followed by a newline."""
    sha = hashlib.sha256()
    for line in lines:
        sha.update(line.encode("utf-8") + b"\n")
    return sha.hexdigest()


def _line(text: str, what: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ReplayError(f"{what} is not valid JSON") from error
    if not isinstance(data, dict):
        raise ReplayError(f"{what} must be an object")
    return data


def _exact(data: dict[str, Any], fields: set[str], what: str) -> None:
    if set(data) != fields:
        wrong = sorted(set(data) ^ fields)
        raise ReplayError(f"{what} has missing or unknown fields: {wrong}")


def _check_header(header: dict[str, Any]) -> None:
    _exact(header, HEADER_FIELDS, "header")
    if header["type"] != "header":
        raise ReplayError("first line is not a header")
    if header["schema_version"] != frame.SCHEMA_VERSION:
        raise ReplayError("unsupported schema version")
    checks = (
        isinstance(header["commit"], str) and 0 < len(header["commit"]) <= frame.MAX_STRING,
        type(header["seed"]) is int and header["seed"] >= 0,
        isinstance(header["scenario_id"], str) and 0 < len(header["scenario_id"]) <= 64,
        isinstance(header["dt"], float) and header["dt"] > 0,
        isinstance(header["world_hash"], str) and len(header["world_hash"]) == 64,
        type(header["frame_count"]) is int and header["frame_count"] > 0,
        type(header["resimulable"]) is bool,
    )
    if not all(checks):
        raise ReplayError("header has a field of the wrong type or range")


def _check_footer(footer: dict[str, Any]) -> None:
    _exact(footer, FOOTER_FIELDS, "footer")
    if footer["type"] != "footer":
        raise ReplayError("last line is not a footer")
    for key in ("final_state_hash", "frames_digest"):
        if not isinstance(footer[key], str) or len(footer[key]) != 64:
            raise ReplayError(f"footer {key} must be a SHA-256 hex digest")


def read_replay(path: Path) -> Replay:
    """Read and validate a replay file. Raises ReplayError on any problem."""
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReplayError(f"cannot read the replay file: {type(error).__name__}") from error
    if len(rows) < 3:
        raise ReplayError("a replay needs a header, a frame and a footer")
    if any(len(row.encode("utf-8")) > MAX_LINE_BYTES for row in rows):
        raise ReplayError("a line is over the size cap")
    header = _line(rows[0], "header")
    _check_header(header)
    footer = _line(rows[-1], "footer")
    _check_footer(footer)
    frame_lines = tuple(rows[1:-1])
    if len(frame_lines) != header["frame_count"]:
        raise ReplayError("frame_count does not match the number of frame lines")
    try:
        frames = tuple(frame.parse_frame(row) for row in frame_lines)
    except frame.FrameError as error:
        raise ReplayError(str(error)) from error
    return Replay(header, frames, footer, frame_lines)
