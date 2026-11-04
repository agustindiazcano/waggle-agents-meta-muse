"""Capture scenes retain simulator state and deterministic denial evidence."""

from pathlib import Path

import pytest

from waggle.experiments.demo_capture import scene_frames, write_scene
from waggle.replay.replay_format import read_replay
from waggle.sim.frame import parse_frame, world_hash
from waggle.sim.scenarios import load_map


def test_injection_records_actual_schema_denial_and_unknown_motion_mode(tmp_path: Path) -> None:
    path = tmp_path / "injection.jsonl"
    write_scene(path, "injection", "test", ticks=3)
    replay = read_replay(path)
    assert replay.header["world_hash"] == world_hash(load_map("A"))
    assert replay.header["resimulable"] is False
    assert replay.frames[0]["events"] == [
        {"kind": "denial", "text": "MCP schema rejected injected override field; no model call"}
    ]
    assert replay.frames[0]["robots"] == []
    with pytest.raises(FileExistsError):
        write_scene(path, "injection", "test", ticks=3)


def test_human_frames_are_deterministic_and_modes_come_from_controller() -> None:
    first = list(scene_frames("human-crossing", "test", ticks=4))
    assert first == list(scene_frames("human-crossing", "test", ticks=4))
    assert first[0]["humans"]
    assert first[0]["run"]["source"] == "replay"
    assert all(r["mode"] in (None, "stopped") for f in first for r in f["robots"])


def test_unknown_scene_and_invalid_ticks_fail_explicitly() -> None:
    with pytest.raises(ValueError):
        list(scene_frames("invented", "test", ticks=1))
    with pytest.raises(ValueError):
        list(scene_frames("injection", "test", ticks=0))


def test_generated_frame_remains_strict_version_one() -> None:
    from waggle.sim.frame import encode_frame

    for item in scene_frames("overheating", "test", ticks=2):
        assert parse_frame(encode_frame(item)) == item
        assert item["machines"][0]["temperature"] > 0


def test_crossing_records_motion_then_actual_rest_after_the_stop_command() -> None:
    recorded = list(scene_frames("human-crossing", "test", ticks=700))
    assert recorded[0]["robots"][0]["active"]["speed"] > 0
    stop = next(i for i, item in enumerate(recorded) if item["events"])
    assert recorded[stop]["events"][0]["kind"] == "stop"
    assert any(
        item["robots"][0]["active"]["speed"] == 0 and item["robots"][0]["mode"] == "stopped"
        for item in recorded[stop:]
    )
    assert recorded[0]["humans"] != recorded[-1]["humans"]
