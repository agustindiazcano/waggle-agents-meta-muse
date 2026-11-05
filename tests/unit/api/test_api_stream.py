"""Health endpoint and WebSocket bridge of waggle.api, through Starlette's TestClient."""

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from waggle.api import app as api_app
from waggle.api import sources
from waggle.api.config import ApiConfig
from waggle.replay import overlay_data
from waggle.replay.recorder import ReplayRecorder
from waggle.sim import frame, scenarios

COMMIT = "abc1234"


class FakeSleep:
    """Records the pacing delays and never waits."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _direct_frames(scenario_id: str, seed: int, ticks: int) -> list[str]:
    scenario = scenarios.generate(scenario_id, seed)
    sim, _ = scenarios.build_engine(scenario)
    box = scenarios.load_map(scenario.map_name)
    run = frame.RunInfo(COMMIT, seed, scenario_id, "live")
    out: list[str] = []
    for _ in range(ticks):
        sim.step()
        overlays = overlay_data.build_overlays(sim, scenario, box)
        out.append(frame.encode_frame(frame.export_frame(sim, run, overlays=overlays)))
    return out


def _record(path: Path, ticks: int = 5) -> list[str]:
    scenario = scenarios.generate("S01", 3)
    sim, _ = scenarios.build_engine(scenario)
    run = frame.RunInfo(COMMIT, 3, "S01", "replay")
    world_hash = frame.world_hash(scenarios.load_map(scenario.map_name))
    lines: list[str] = []
    with ReplayRecorder(path, run, world_hash, resimulable=True) as rec:
        for _ in range(ticks):
            sim.step()
            item = frame.export_frame(sim, run)
            rec.add(item)
            lines.append(frame.encode_frame(item))
    return lines


def _client(tmp_path: Path, sleep: FakeSleep | None = None, **kw: object) -> TestClient:
    cfg = ApiConfig(replay_dir=tmp_path, commit=COMMIT, **kw)  # type: ignore[arg-type]
    return TestClient(api_app.create_app(cfg, sleep or FakeSleep()))


def _drain(ws: object) -> tuple[list[str], int]:
    """Read text messages until the server closes. Returns the messages and the close code."""
    messages: list[str] = []
    while True:
        try:
            messages.append(ws.receive_text())  # type: ignore[attr-defined]
        except WebSocketDisconnect as closed:
            return messages, closed.code


def test_health(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json() == {"service": "api", "status": "ok"}


def test_no_write_endpoint(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/health").status_code == 405
    assert client.post("/ws/live").status_code in (404, 405)
    assert client.get("/openapi.json").status_code == 404


def test_replay_forwards_the_recorded_lines(tmp_path: Path) -> None:
    lines = _record(tmp_path / "run.jsonl")
    sleep = FakeSleep()
    with _client(tmp_path, sleep).websocket_connect("/ws/replay?name=run.jsonl") as ws:
        messages, code = _drain(ws)
    assert code == 1000
    assert json.loads(messages[0])["type"] == "header"
    assert messages[1:-1] == lines
    assert json.loads(messages[-1])["type"] == "footer"
    assert sleep.delays == [1 / 30.0] * len(messages)


def test_rate_limit_follows_the_config(tmp_path: Path) -> None:
    _record(tmp_path / "run.jsonl")
    sleep = FakeSleep()
    with _client(tmp_path, sleep, max_fps=4.0).websocket_connect("/ws/replay?name=run.jsonl") as ws:
        _drain(ws)
    assert set(sleep.delays) == {0.25}


def test_stride_skips_frames_and_ticks_stay_visible(tmp_path: Path) -> None:
    lines = _record(tmp_path / "run.jsonl", ticks=6)
    with _client(tmp_path, stride=2).websocket_connect("/ws/replay?name=run.jsonl") as ws:
        messages, _ = _drain(ws)
    sent = messages[1:-1]
    assert sent == lines[0::2]
    assert [json.loads(m)["tick"] for m in sent] == [1, 3, 5]


def test_over_cap_frame_is_dropped_with_an_error_never_truncated(tmp_path: Path) -> None:
    lines = _record(tmp_path / "run.jsonl")
    cap = min(len(line.encode("utf-8")) for line in lines) - 1
    with _client(tmp_path, max_frame_bytes=cap).websocket_connect(
        "/ws/replay?name=run.jsonl"
    ) as ws:
        messages, code = _drain(ws)
    assert code == 1000
    body = messages[1:-1]
    assert len(body) == len(lines)
    for index, text in enumerate(body):
        parsed = json.loads(text)
        assert parsed == {"type": "error", "error": "frame_too_large", "tick": index + 1}
        assert "robots" not in text


def test_frames_at_the_cap_pass(tmp_path: Path) -> None:
    lines = _record(tmp_path / "run.jsonl")
    cap = max(len(line.encode("utf-8")) for line in lines)
    with _client(tmp_path, max_frame_bytes=cap).websocket_connect(
        "/ws/replay?name=run.jsonl"
    ) as ws:
        messages, _ = _drain(ws)
    assert messages[1:-1] == lines


@pytest.mark.parametrize(
    "name",
    ["../x.jsonl", "/etc/passwd", "C:/x.jsonl", "..%2Fx.jsonl", "sub%5Cx.jsonl", "nope.jsonl", ""],
)
def test_replay_path_attacks_are_refused(tmp_path: Path, name: str) -> None:
    (tmp_path.parent / "x.jsonl").write_text("secret", encoding="utf-8")
    with _client(tmp_path).websocket_connect(f"/ws/replay?name={name}") as ws:
        messages, code = _drain(ws)
    assert code == 1008
    assert [json.loads(m)["error"] for m in messages] == ["replay_not_allowed"]
    assert "secret" not in "".join(messages)


def test_tampered_replay_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    _record(path)
    path.write_text("not json\nnot json\nnot json\n", encoding="utf-8")
    with _client(tmp_path).websocket_connect("/ws/replay?name=bad.jsonl") as ws:
        messages, code = _drain(ws)
    assert code == 1008
    assert [json.loads(m)["error"] for m in messages] == ["replay_invalid"]


def test_unknown_scenario_is_refused(tmp_path: Path) -> None:
    for query in ("scenario=S99", "scenario=../S01", "scenario=", ""):
        with _client(tmp_path).websocket_connect(f"/ws/live?{query}") as ws:
            messages, code = _drain(ws)
        assert code == 1008
        assert [json.loads(m)["error"] for m in messages] == ["unknown_scenario"]


def test_live_stream_is_the_simulator_output(tmp_path: Path) -> None:
    total = scenarios.generate("S01", 5).duration_ticks
    stride = total // 3
    with _client(tmp_path, stride=stride, live_seed=5).websocket_connect(
        "/ws/live?scenario=S01"
    ) as ws:
        messages, code = _drain(ws)
    assert code == 1000
    world = json.loads(messages[0])
    assert world["type"] == "world"
    assert world["hash"] == frame.world_hash(scenarios.load_map("A"))
    direct = _direct_frames("S01", 5, total)
    assert messages[1:] == direct[0::stride]
    assert all(json.loads(m)["run"]["source"] == "live" for m in messages[1:])


def test_two_connections_do_not_share_state(tmp_path: Path) -> None:
    total = scenarios.generate("S01", 0).duration_ticks
    client = _client(tmp_path, stride=total)
    runs = []
    for _ in range(2):
        with client.websocket_connect("/ws/live?scenario=S01") as ws:
            runs.append(_drain(ws)[0])
    assert runs[0] == runs[1]


def test_client_message_is_refused_and_does_not_change_the_run(tmp_path: Path) -> None:
    total = scenarios.generate("S01", 0).duration_ticks
    direct = _direct_frames("S01", 0, total)
    with _client(tmp_path, stride=1).websocket_connect("/ws/live?scenario=S01") as ws:
        first = ws.receive_text()
        ws.send_text(json.dumps({"scenario": "S02", "tick": 0, "speed": 99}))
        messages, code = _drain(ws)
    assert json.loads(first)["type"] == "world"
    assert code == 1008
    assert json.loads(messages[-1]) == {"type": "error", "error": "client_messages_not_allowed"}
    sent = [m for m in messages[:-1]]
    assert sent == direct[: len(sent)]


def test_closing_mid_stream_stops_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"closed": False, "made": 0}

    def endless(config: ApiConfig, scenario_id: str) -> Generator[sources.Item]:
        try:
            while True:
                state["made"] += 1
                yield sources.Item("frame", state["made"], '{"tick":1}')
        finally:
            state["closed"] = True

    monkeypatch.setattr(sources, "live_items", endless)
    with _client(tmp_path).websocket_connect("/ws/live?scenario=S01") as ws:
        ws.receive_text()
        ws.close()
    assert state["closed"] is True
