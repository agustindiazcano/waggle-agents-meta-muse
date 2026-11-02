"""replay-verify: recompute the hashes and fail on a tampered or incomplete file."""

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from waggle.replay import recorder, replay_format, verify
from waggle.sim import frame, scenarios

RUN = frame.RunInfo(commit="abc1234", seed=7, scenario_id="S01", source="replay")


def record(path: Path, ticks: int = 6, resimulable: bool = True) -> Path:
    scenario = scenarios.generate("S01", 7)
    sim, _ = scenarios.build_engine(scenario)
    box = scenarios.load_map(scenario.map_name)
    with recorder.ReplayRecorder(path, RUN, frame.world_hash(box), resimulable) as rec:
        for _ in range(ticks):
            sim.step()
            rec.add(frame.export_frame(sim, RUN))
    return path


def edit(path: Path, change: Callable[[list[dict[str, object]]], object]) -> Path:
    rows = [json.loads(r) for r in path.read_text(encoding="utf-8").splitlines()]
    change(rows)
    out = path.with_name("tampered.jsonl")
    out.write_text("\n".join(frame.encode_frame(r) for r in rows) + "\n", encoding="utf-8")
    return out


def run_main(*argv: str) -> tuple[int, str]:
    err = io.StringIO()
    return verify.main(list(argv), err), err.getvalue()


def refresh_digest(rows: list[dict[str, object]]) -> None:
    lines = [frame.encode_frame(r) for r in rows[1:-1]]
    rows[-1]["frames_digest"] = replay_format.digest_lines(lines)


def test_a_clean_file_passes(tmp_path: Path) -> None:
    code, err = run_main(str(record(tmp_path / "run.jsonl")))
    assert code == 0, err
    assert "ok" in err


def test_a_changed_position_fails(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")

    def change(rows: list[dict[str, object]]) -> None:
        robots = rows[3]["robots"]
        assert isinstance(robots, list)
        robots[0]["x"] += 1.0

    code, err = run_main(str(edit(path, change)))
    assert code != 0
    assert "digest" in err


def test_a_tamper_that_fixes_the_digest_is_caught_by_the_rerun(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")

    def change(rows: list[dict[str, object]]) -> None:
        robots = rows[3]["robots"]
        assert isinstance(robots, list)
        robots[0]["x"] += 1.0
        refresh_digest(rows)

    code, err = run_main(str(edit(path, change)))
    assert code != 0
    assert "tick 3" in err


def test_a_changed_state_hash_fails_even_with_a_fixed_digest(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")

    def change(rows: list[dict[str, object]]) -> None:
        rows[2]["state_hash"] = "0" * 64
        refresh_digest(rows)

    code, _ = run_main(str(edit(path, change)))
    assert code != 0


def test_a_changed_final_hash_fails(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")
    code, err = run_main(str(edit(path, lambda rows: rows[-1].update(final_state_hash="1" * 64))))
    assert code != 0
    assert "final" in err


def test_a_dropped_frame_fails(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")
    code, _ = run_main(str(edit(path, lambda rows: rows.pop(2))))
    assert code != 0


@pytest.mark.parametrize("field", ["commit", "seed", "scenario_id", "schema_version"])
def test_a_header_missing_a_field_is_refused(tmp_path: Path, field: str) -> None:
    path = record(tmp_path / "run.jsonl")
    code, err = run_main(str(edit(path, lambda rows: rows[0].pop(field))))
    assert code != 0
    assert "header" in err


def test_a_changed_commit_in_the_header_is_caught(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")
    code, _ = run_main(str(edit(path, lambda rows: rows[0].update(commit="other"))))
    assert code != 0


def test_a_different_world_hash_fails(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")
    code, err = run_main(str(edit(path, lambda rows: rows[0].update(world_hash="2" * 64))))
    assert code != 0
    assert "world" in err


def test_a_file_that_cannot_be_rerun_gets_the_digest_check_only(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl", resimulable=False)
    code, err = run_main(str(path))
    assert code == 0, err
    assert "not re-run" in err

    def change(rows: list[dict[str, object]]) -> None:
        robots = rows[3]["robots"]
        assert isinstance(robots, list)
        robots[0]["x"] += 1.0

    code, _ = run_main(str(edit(path, change)))
    assert code != 0


def test_digest_only_flag_skips_the_rerun(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")

    def change(rows: list[dict[str, object]]) -> None:
        robots = rows[3]["robots"]
        assert isinstance(robots, list)
        robots[0]["x"] += 1.0
        refresh_digest(rows)

    code, err = run_main("--digest-only", str(edit(path, change)))
    assert code == 0
    assert "not re-run" in err


def test_unknown_scenario_and_usage_errors_fail(tmp_path: Path) -> None:
    path = record(tmp_path / "run.jsonl")
    code, _ = run_main(str(edit(path, lambda rows: rows[0].update(scenario_id="S99"))))
    assert code != 0
    assert run_main()[0] != 0
    assert run_main(str(tmp_path / "missing.jsonl"))[0] != 0
    assert run_main("a", "b")[0] != 0


def test_run_reads_argv_and_exits_with_the_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["replay-verify"])
    assert verify.run() != 0
