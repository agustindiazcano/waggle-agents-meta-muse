"""Where the bridge gets its messages: a recorded replay file or a running scenario.

Both sources yield messages the simulator side already produced. Nothing is computed, changed
or invented here: a replay line is forwarded as it was recorded, and a live frame is the
output of ``export_frame``. A frame the simulator refuses to export (over the contract cap) is
reported as an item with no text, so the bridge can tell the client it was dropped.
"""

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from waggle.api.config import ApiConfig
from waggle.replay import overlay_data, replay_format
from waggle.sim import frame, scenarios


@dataclass(frozen=True)
class Item:
    """One outgoing message. ``kind`` is meta (header, world, footer) or frame.

    ``text`` is None when the frame could not be exported; ``tick`` is None for meta items.
    """

    kind: str
    tick: int | None
    text: str | None


def replay_items(path: Path) -> Generator[Item]:
    """The header, every recorded frame line and the footer of a replay file, unchanged.

    The file is read and validated when this is called: ReplayError is raised here, before
    any message is sent.
    """
    replay = replay_format.read_replay(path)
    return _replay_gen(replay)


def _replay_gen(replay: replay_format.Replay) -> Generator[Item]:
    yield Item("meta", None, frame.encode_frame(replay.header))
    for parsed, line in zip(replay.frames, replay.lines, strict=True):
        yield Item("frame", int(parsed["tick"]), line)
    yield Item("meta", None, frame.encode_frame(replay.footer))


def live_items(config: ApiConfig, scenario_id: str) -> Generator[Item]:
    """The world message, then one frame per tick of a scenario run with no control."""
    scenario = scenarios.generate(scenario_id, config.live_seed)
    return _live_gen(config, scenario)


def _live_gen(config: ApiConfig, scenario: scenarios.Scenario) -> Generator[Item]:
    sim, _detector = scenarios.build_engine(scenario)
    box = scenarios.load_map(scenario.map_name)
    world = frame.export_world(box)
    yield Item("meta", None, frame.encode_frame({"type": "world", **world}))
    run = frame.RunInfo(config.commit, config.live_seed, scenario.id, "live")
    for _ in range(scenario.duration_ticks):
        sim.step()
        tick = sim.state.tick
        try:
            text = frame.encode_frame(
                frame.export_frame(
                    sim, run, overlays=overlay_data.build_overlays(sim, scenario, box)
                )
            )
        except frame.FrameTooLarge:
            text = None
        yield Item("frame", tick, text)
