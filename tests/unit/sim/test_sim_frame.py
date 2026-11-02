"""Frame export: the versioned snapshot contract of docs/MULTIMODAL_AND_VIEWER_DESIGN.md."""

import json
from typing import Any

import numpy as np
import pytest

from waggle.sim import frame, scenarios

RUN = frame.RunInfo(commit="abc1234", seed=7, scenario_id="S01", source="replay")
TOP_FIELDS = {
    "schema_version",
    "tick",
    "dt",
    "sim_time",
    "state_hash",
    "run",
    "robots",
    "humans",
    "zones",
    "machines",
    "overlays",
    "events",
}


def make(seed: int = 7, scenario_id: str = "S01") -> Any:
    scenario = scenarios.generate(scenario_id, seed)
    sim, _ = scenarios.build_engine(scenario)
    return sim


def frames(seed: int, ticks: int) -> list[dict[str, Any]]:
    sim = make(seed)
    out = []
    for _ in range(ticks):
        sim.step()
        out.append(frame.export_frame(sim, RUN))
    return out


def test_frame_has_exactly_the_listed_fields() -> None:
    sim = make()
    sim.run(5)
    out = frame.export_frame(sim, RUN)
    assert set(out) == TOP_FIELDS
    assert out["schema_version"] == frame.SCHEMA_VERSION
    assert out["tick"] == 5
    assert out["state_hash"] == sim.state_hash()
    assert out["overlays"] == {}
    assert out["run"] == {
        "commit": "abc1234",
        "seed": 7,
        "scenario_id": "S01",
        "source": "replay",
    }
    assert set(out["robots"][0]) == {"id", "x", "y", "heading", "active", "speed_limit", "mode"}
    assert set(out["humans"][0]) == {"id", "x", "y", "heading"}


def test_same_seed_gives_byte_identical_frames() -> None:
    first = [frame.encode_frame(f) for f in frames(7, 30)]
    second = [frame.encode_frame(f) for f in frames(7, 30)]
    assert first == second
    assert first != [frame.encode_frame(f) for f in frames(8, 30)]


def test_values_are_copied_from_the_state_and_rounded() -> None:
    sim = make()
    sim.run(3)
    out = frame.export_frame(sim, RUN)
    pose = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)
    assert out["robots"][0]["x"] == round(float(pose[0, 0]), frame.DECIMALS)
    assert out["robots"][0]["id"] == "robot_0"
    assert out["sim_time"] == round(3 * out["dt"], frame.DECIMALS)


def test_export_does_not_change_the_state() -> None:
    sim = make()
    sim.run(4)
    before = sim.state_hash()
    frame.export_frame(sim, RUN)
    assert sim.state_hash() == before


def test_control_and_view_inputs_are_passed_through_when_given() -> None:
    sim = make()
    out = frame.export_frame(
        sim,
        RUN,
        speed_limits=[1.5] * len(sim.state.arrays["robot_pose"]),
        modes=["reduced"] * len(sim.state.arrays["robot_pose"]),
        zones=[frame.ZoneView("lane_1", "lane_1", None, 3)],
        machines=[frame.MachineView("m1", "running", 41.5, 0)],
        events=[frame.FrameEvent("stop", "robot_0")],
    )
    assert out["robots"][0]["speed_limit"] == 1.5
    assert out["robots"][0]["mode"] == "reduced"
    assert out["zones"] == [{"id": "lane_1", "polygon_id": "lane_1", "occupant": None, "token": 3}]
    assert out["machines"][0]["temperature"] == 41.5
    assert out["events"] == [{"kind": "stop", "text": "robot_0"}]


def test_missing_control_data_is_null_not_invented() -> None:
    out = frame.export_frame(make(), RUN)
    assert out["robots"][0]["speed_limit"] is None
    assert out["robots"][0]["mode"] is None


def test_bad_inputs_are_refused() -> None:
    sim = make()
    with pytest.raises(ValueError, match="mode"):
        frame.export_frame(sim, RUN, modes=["fast"] * len(sim.state.arrays["robot_pose"]))
    with pytest.raises(ValueError, match="one value per robot"):
        frame.export_frame(sim, RUN, speed_limits=[1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="event kind"):
        frame.export_frame(sim, RUN, events=[frame.FrameEvent("boom", "x")])
    with pytest.raises(ValueError, match="too long"):
        frame.export_frame(sim, frame.RunInfo("c" * 200, 1, "S03", "replay"))
    with pytest.raises(ValueError, match="source"):
        frame.export_frame(sim, frame.RunInfo("c", 1, "S03", "other"))
    with pytest.raises(ValueError, match="schema version"):
        frame.export_frame(sim, RUN, schema_version=2)


def test_oversize_frame_is_refused_not_truncated() -> None:
    sim = make()
    with pytest.raises(frame.FrameTooLarge):
        frame.export_frame(sim, RUN, max_bytes=100)
    out = frame.export_frame(sim, RUN)
    assert len(frame.encode_frame(out)) <= frame.MAX_FRAME_BYTES


def test_parse_frame_round_trips_and_rejects_unknown_input() -> None:
    sim = make()
    out = frame.export_frame(sim, RUN)
    assert frame.parse_frame(frame.encode_frame(out)) == out
    bad_version = {**out, "schema_version": 99}
    with pytest.raises(frame.FrameError, match="schema version"):
        frame.parse_frame(frame.encode_frame(bad_version))
    with pytest.raises(frame.FrameError, match="unknown field"):
        frame.parse_frame(frame.encode_frame({**out, "extra": 1}))
    nested = json.loads(frame.encode_frame(out))
    nested["robots"][0]["secret"] = 1
    with pytest.raises(frame.FrameError, match="unknown field"):
        frame.parse_frame(json.dumps(nested))
    missing = {k: v for k, v in out.items() if k != "tick"}
    with pytest.raises(frame.FrameError, match="missing field"):
        frame.parse_frame(frame.encode_frame(missing))
    with pytest.raises(frame.FrameError, match="overlays"):
        frame.parse_frame(frame.encode_frame({**out, "overlays": {"envelopes": []}}))
    with pytest.raises(frame.FrameError, match="too large"):
        frame.parse_frame(frame.encode_frame(out), max_bytes=50)
    with pytest.raises(frame.FrameError):
        frame.parse_frame("not json")


def test_world_message_has_its_own_version_and_a_stable_hash() -> None:
    box = scenarios.load_map("A")
    first, second = frame.export_world(box), frame.export_world(scenarios.load_map("A"))
    assert first == second
    assert first["schema_version"] == frame.WORLD_SCHEMA_VERSION
    assert first["hash"] == frame.world_hash(box)
    assert frame.world_hash(scenarios.load_map("B")) != first["hash"]
