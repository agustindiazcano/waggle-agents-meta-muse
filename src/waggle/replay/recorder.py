"""Write a replay file from frames produced by ``waggle.sim.frame.export_frame``.

Frames are held in memory and the file is written once, in exclusive-create mode, when the
recorder closes cleanly: an existing file is never overwritten and a failed run leaves no file.
The commit is read from the run metadata the caller passes.
"""

from pathlib import Path
from types import TracebackType

from waggle.replay import replay_format
from waggle.sim import frame, params


class ReplayRecorder:
    """Collects frames of one run and writes the JSON Lines file on a clean close."""

    def __init__(self, path: Path, run: frame.RunInfo, world_hash: str, resimulable: bool) -> None:
        self._path = path
        self._run = run
        self._world_hash = world_hash
        self._resimulable = resimulable
        self._lines: list[str] = []
        self._last_tick = -1
        self._final_hash = ""

    def add(self, item: frame.JsonObject) -> None:
        """Validate one frame and keep it. Ticks must increase and the run must match."""
        text = frame.encode_frame(item)
        parsed = frame.parse_frame(text)
        run = parsed["run"]
        if (run["commit"], run["seed"], run["scenario_id"]) != (
            self._run.commit,
            self._run.seed,
            self._run.scenario_id,
        ):
            raise ValueError("frame run metadata does not match the recorder run")
        if parsed["tick"] <= self._last_tick:
            raise ValueError("frame tick must be greater than the previous tick")
        self._last_tick = parsed["tick"]
        self._final_hash = parsed["state_hash"]
        self._lines.append(text)

    def close(self) -> None:
        """Write the file. Raises ValueError with no frames and FileExistsError if it exists."""
        if not self._lines:
            raise ValueError("no frames recorded")
        header = {
            "type": "header",
            "schema_version": frame.SCHEMA_VERSION,
            "commit": self._run.commit,
            "seed": self._run.seed,
            "scenario_id": self._run.scenario_id,
            "dt": params.DT,
            "world_hash": self._world_hash,
            "frame_count": len(self._lines),
            "resimulable": self._resimulable,
        }
        footer = {
            "type": "footer",
            "final_state_hash": self._final_hash,
            "frames_digest": replay_format.digest_lines(self._lines),
        }
        rows = [frame.encode_frame(header), *self._lines, frame.encode_frame(footer)]
        with self._path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(rows) + "\n")

    def __enter__(self) -> "ReplayRecorder":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self.close()
