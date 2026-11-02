"""Configuration and request checks of waggle.api."""

from pathlib import Path

import pytest

from waggle.api import config, paths
from waggle.sim import frame


def test_defaults_bind_to_localhost() -> None:
    cfg = config.from_env({})
    assert cfg.host == "127.0.0.1"
    assert cfg.max_frame_bytes == frame.MAX_FRAME_BYTES
    assert cfg.stride == 1


def test_env_overrides() -> None:
    cfg = config.from_env(
        {
            "WAGGLE_API_HOST": "0.0.0.0",
            "WAGGLE_API_PORT": "9000",
            "WAGGLE_API_MAX_FPS": "10",
            "WAGGLE_API_STRIDE": "4",
            "WAGGLE_REPLAY_DIR": "somewhere",
        }
    )
    assert (cfg.host, cfg.port, cfg.max_fps, cfg.stride) == ("0.0.0.0", 9000, 10.0, 4)
    assert cfg.replay_dir == Path("somewhere")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("WAGGLE_API_PORT", "0"),
        ("WAGGLE_API_PORT", "x"),
        ("WAGGLE_API_MAX_FPS", "0"),
        ("WAGGLE_API_MAX_FPS", "nan"),
        ("WAGGLE_API_STRIDE", "0"),
        ("WAGGLE_API_MAX_FRAME_BYTES", "0"),
        ("WAGGLE_API_MAX_FRAME_BYTES", str(frame.MAX_FRAME_BYTES + 1)),
        ("WAGGLE_API_LIVE_SEED", "-1"),
    ],
)
def test_invalid_config_is_refused(name: str, value: str) -> None:
    with pytest.raises(config.ConfigError):
        config.from_env({name: value})


def test_scenario_allowlist() -> None:
    assert paths.check_scenario("S01") == "S01"
    for bad in ("S99", "s01", "../S01", "", "S01 "):
        with pytest.raises(paths.Rejected):
            paths.check_scenario(bad)


def test_replay_path_inside_directory(tmp_path: Path) -> None:
    (tmp_path / "run.jsonl").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.jsonl").write_text("x", encoding="utf-8")
    assert paths.resolve_replay(tmp_path, "run.jsonl") == (tmp_path / "run.jsonl").resolve()
    assert paths.resolve_replay(tmp_path, "sub/deep.jsonl").name == "deep.jsonl"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../outside.jsonl",
        "sub/../../outside.jsonl",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "C:\\Windows\\win.ini",
        "\\\\host\\share\\x.jsonl",
        "sub\\deep.jsonl",
        "run.txt",
        "missing.jsonl",
        "run\x00.jsonl",
        "a" * 300 + ".jsonl",
        "sub",
    ],
)
def test_replay_path_rejected(tmp_path: Path, name: str) -> None:
    (tmp_path / "run.jsonl").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    with pytest.raises(paths.Rejected):
        paths.resolve_replay(tmp_path, name)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.jsonl").write_text("x", encoding="utf-8")
    base = tmp_path / "replays"
    base.mkdir()
    try:
        (base / "link.jsonl").symlink_to(outside / "secret.jsonl")
    except OSError:
        pytest.skip("symlinks are not available")
    with pytest.raises(paths.Rejected):
        paths.resolve_replay(base, "link.jsonl")
