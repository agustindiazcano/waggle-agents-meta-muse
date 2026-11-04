"""``replay-verify FILE``: check a replay file and exit nonzero on any problem.

Checks, in order: the file parses under the strict reader; the digest of the frame lines
matches the footer; the final state hash matches the last frame; ticks increase and every frame
carries the run metadata of the header. When the header says the file can be re-run
(``resimulable``), the scenario is rebuilt from the seed, the world hash is compared, and every
recorded frame is compared with the frame the simulator exports at that tick. A tamper that
also repairs the digest and the hashes is caught only by that re-run. A file that cannot be
re-run gets the digest checks only, and the report says so. ``--digest-only`` skips the re-run.
"""

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from waggle.replay import overlay_data, replay_format
from waggle.sim import frame, scenarios

USAGE = "usage: replay-verify [--digest-only] FILE"


def _structure(replay: replay_format.Replay) -> list[str]:
    problems: list[str] = []
    header, footer = replay.header, replay.footer
    if replay_format.digest_lines(replay.lines) != footer["frames_digest"]:
        problems.append("frame digest does not match the footer")
    if replay.frames[-1]["state_hash"] != footer["final_state_hash"]:
        problems.append("final state hash does not match the last frame")
    expected = (header["commit"], header["seed"], header["scenario_id"])
    previous = -1
    for item in replay.frames:
        run = item["run"]
        if (run["commit"], run["seed"], run["scenario_id"]) != expected:
            problems.append(f"tick {item['tick']}: run metadata differs from the header")
        if item["tick"] <= previous:
            problems.append(f"tick {item['tick']}: ticks do not increase")
        if item["dt"] != header["dt"]:
            problems.append(f"tick {item['tick']}: dt differs from the header")
        previous = item["tick"]
    return problems


def _rerun(replay: replay_format.Replay) -> list[str]:
    header = replay.header
    try:
        scenario = scenarios.generate(header["scenario_id"], header["seed"])
    except ValueError as error:
        return [f"cannot rebuild the scenario: {error}"]
    sim, _ = scenarios.build_engine(scenario)
    box = scenarios.load_map(scenario.map_name)
    if frame.world_hash(box) != header["world_hash"]:
        return ["world hash does not match the scenario map"]
    problems: list[str] = []
    for recorded in replay.frames:
        while sim.state.tick < recorded["tick"]:
            sim.step()
        if sim.state.tick != recorded["tick"]:
            return [f"tick {recorded['tick']}: earlier than the simulator position"]
        run = recorded["run"]
        info = frame.RunInfo(run["commit"], run["seed"], run["scenario_id"], run["source"])
        overlays = (
            overlay_data.build_overlays(sim, scenario, box) if recorded.get("overlays") else None
        )
        again = frame.export_frame(sim, info, overlays=overlays)
        if frame.encode_frame(again) != frame.encode_frame(recorded):
            problems.append(f"tick {recorded['tick']}: frame differs from the re-run")
            break
    return problems


def verify_file(path: str, digest_only: bool) -> tuple[list[str], str]:
    """Problems found in the file and a note on how far the check went."""
    try:
        replay = replay_format.read_replay(Path(path))
    except replay_format.ReplayError as error:
        return [f"refused: {error}"], ""
    problems = _structure(replay)
    if problems:
        return problems, ""
    if digest_only or not replay.header["resimulable"]:
        return [], "digest checks only, not re-run"
    return _rerun(replay), "re-run from the seed"


def main(argv: Sequence[str], stderr: TextIO) -> int:
    """Run the command. Returns 0 only for a file that passes every check."""
    digest_only = "--digest-only" in argv
    paths = [a for a in argv if a != "--digest-only"]
    if len(paths) != 1:
        print(USAGE, file=stderr)
        return 2
    problems, note = verify_file(paths[0], digest_only)
    if problems:
        for problem in problems:
            print(f"replay-verify: {problem}", file=stderr)
        return 1
    print(f"replay-verify: ok ({note})", file=stderr)
    return 0


def run() -> int:
    """Process entry: real arguments and standard error."""
    return main(sys.argv[1:], sys.stderr)
