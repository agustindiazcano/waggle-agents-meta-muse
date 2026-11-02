"""JSON Lines replay recorder and strict reader."""

import json
from pathlib import Path
from typing import Any

import pytest

from waggle.replay import recorder, replay_format
from waggle.sim import frame, scenarios

RUN = frame.RunInfo(commit="abc1234", seed=7, scenario_id="S01", source="replay")


def record(path: Path, ticks: int = 5, resimulable: bool = True) -> None:
    scenario = scenarios.generate("S01", 7)
    sim, _ = scenarios.build_engine(scenario)
    box = scenarios.load_map(scenario.map_name)
    with recorder.ReplayRecorder(path, RUN, frame.world_hash(box), resimulable) as rec:
        for _ in range(ticks):
            sim.step()
            rec.add(frame.export_frame(sim, RUN))


def lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_file_has_header_frames_and_footer(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    record(path)
    rows = lines(path)
    assert len(rows) == 7
    header = json.loads(rows[0])
    assert header == {
        "type": "header",
        "schema_version": frame.SCHEMA_VERSION,
        "commit": "abc1234",
        "seed": 7,
        "scenario_id": "S01",
        "dt": 0.025,
        "world_hash": header["world_hash"],
        "frame_count": 5,
        "resimulable": True,
    }
    last_frame = json.loads(rows[-2])
    footer = json.loads(rows[-1])
    assert footer["type"] == "footer"
    assert footer["final_state_hash"] == last_frame["state_hash"]
    assert [json.loads(r)["tick"] for r in rows[1:-1]] == [1, 2, 3, 4, 5]


def test_same_run_gives_byte_identical_files(tmp_path: Path) -> None:
    record(tmp_path / "a.jsonl")
    record(tmp_path / "b.jsonl")
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()


def test_reader_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    record(path)
    replay = replay_format.read_replay(path)
    assert replay.header["frame_count"] == 5
    assert len(replay.frames) == 5
    assert replay.footer["final_state_hash"] == replay.frames[-1]["state_hash"]


def test_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    record(path)
    with pytest.raises(FileExistsError):
        record(path)


def test_nothing_is_written_when_the_block_fails(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    with (
        pytest.raises(RuntimeError),
        recorder.ReplayRecorder(path, RUN, "0" * 64, False),
    ):
        raise RuntimeError("run failed")
    assert not path.exists()


def test_recorder_refuses_bad_frames(tmp_path: Path) -> None:
    scenario = scenarios.generate("S01", 7)
    sim, _ = scenarios.build_engine(scenario)
    sim.step()
    good = frame.export_frame(sim, RUN)
    rec = recorder.ReplayRecorder(tmp_path / "x.jsonl", RUN, "0" * 64, False)
    rec.add(good)
    with pytest.raises(ValueError, match="tick"):
        rec.add(good)
    other = frame.RunInfo("zzz", 7, "S01", "replay")
    sim.step()
    with pytest.raises(ValueError, match="run"):
        rec.add(frame.export_frame(sim, other))
    with pytest.raises(frame.FrameError):
        rec.add({**good, "tick": 99, "extra": 1})
    with pytest.raises(ValueError, match="no frames"):
        recorder.ReplayRecorder(tmp_path / "y.jsonl", RUN, "0" * 64, False).close()


def rewrite(path: Path, edit: Any) -> Path:
    rows = [json.loads(r) for r in lines(path)]
    edit(rows)
    out = path.with_name("edited.jsonl")
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return out


@pytest.mark.parametrize("field", ["commit", "seed", "scenario_id", "schema_version", "dt"])
def test_reader_refuses_a_header_missing_a_field(tmp_path: Path, field: str) -> None:
    path = tmp_path / "run.jsonl"
    record(path)
    edited = rewrite(path, lambda rows: rows[0].pop(field))
    with pytest.raises(replay_format.ReplayError, match="header"):
        replay_format.read_replay(edited)


def test_reader_refuses_unknown_version_unknown_field_and_count_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    record(path)
    with pytest.raises(replay_format.ReplayError, match="schema version"):
        replay_format.read_replay(rewrite(path, lambda rows: rows[0].update(schema_version=2)))
    with pytest.raises(replay_format.ReplayError, match="header"):
        replay_format.read_replay(rewrite(path, lambda rows: rows[0].update(extra=1)))
    with pytest.raises(replay_format.ReplayError, match="frame_count"):
        replay_format.read_replay(rewrite(path, lambda rows: rows.pop(2)))
    with pytest.raises(replay_format.ReplayError, match="footer"):
        replay_format.read_replay(rewrite(path, lambda rows: rows.pop()))
    with pytest.raises(replay_format.ReplayError, match="schema version"):
        replay_format.read_replay(rewrite(path, lambda rows: rows[2].update(schema_version=9)))
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(replay_format.ReplayError):
        replay_format.read_replay(empty)
