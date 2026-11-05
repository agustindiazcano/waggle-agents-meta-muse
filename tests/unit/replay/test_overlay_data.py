"""Real overlay geometry built from simulator state for viewer frames."""

from waggle.api import sources
from waggle.api.config import ApiConfig
from waggle.replay import overlay_data
from waggle.sim import frame, scenarios


def _built(ticks: int = 5):  # type: ignore[no-untyped-def]
    scenario = scenarios.generate("S01", 7)
    sim, _det = scenarios.build_engine(scenario)
    sim.run(ticks)
    world = scenarios.load_map(scenario.map_name)
    before = sim.state_hash()
    overlays = overlay_data.build_overlays(sim, scenario, world)
    return sim, scenario, overlays, before


def test_build_overlays_derives_envelopes_from_robot_poses() -> None:
    sim, scenario, overlays, before = _built()
    assert sim.state_hash() == before
    assert len(overlays.envelopes) == len(scenario.robots)
    first = overlays.envelopes[0]
    assert first.robot_id == "robot_0"
    assert len(first.polygon) >= 4
    assert first.margin_m >= 0.0


def test_build_overlays_ghost_paths_start_at_current_pose() -> None:
    sim, _scenario, overlays, before = _built()
    assert overlays.ghost_paths, "a forked rollout must produce at least one ghost path"
    ghost = overlays.ghost_paths[0]
    assert ghost.robot_id == "robot_0"
    assert ghost.k == 1
    assert ghost.snapshot_hash == before
    assert ghost.horizon_s > 0.0
    assert len(ghost.points) >= 2
    pose = sim.state.arrays["robot_pose"][0]
    assert ghost.points[0] == (float(pose[0]), float(pose[1]))


def test_build_overlays_lidar_shadows_use_sampled_stride() -> None:
    _sim, _scenario, overlays, _before = _built()
    assert overlays.lidar_shadows, "racks on map A must cast sampled lidar shadows"
    for shadow in overlays.lidar_shadows:
        assert shadow.sample_stride == overlay_data.SHADOW_SAMPLE_STRIDE
        assert len(shadow.polygon) >= 3


def test_live_items_carry_real_overlays() -> None:
    items = list(sources.live_items(ApiConfig(commit="abc1234", live_seed=7), "S01"))
    frames = [item for item in items if item.kind == "frame"]
    assert frames and frames[0].text is not None
    parsed = frame.parse_frame(frames[0].text)
    assert parsed["overlays"]["envelopes"], "live frames must carry envelopes"
    assert parsed["overlays"]["ghost_paths"], "live frames must carry ghost paths"


def test_generated_replay_frames_carry_real_overlays(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from waggle.replay import generate, replay_format, verify

    path = tmp_path / "run.jsonl"
    assert generate.generate(path, "S01", 7, 3, "abc1234") == 3
    replay = replay_format.read_replay(path)
    for item in replay.frames:
        assert item["overlays"]["envelopes"]
        assert item["overlays"]["ghost_paths"]
    problems, _note = verify.verify_file(str(path), digest_only=False)
    assert problems == []
