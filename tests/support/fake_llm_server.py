"""A local fake chat-completions server for provider tests (127.0.0.1, OS-assigned port).

No real network and no real key. Responses are scripted: each request takes the next
canned response, and the last one repeats.
"""

import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass(frozen=True)
class Canned:
    """One scripted response."""

    status: int = 200
    body: bytes = b""
    content_type: str | None = "application/json"
    headers: tuple[tuple[str, str], ...] = ()
    hang_s: float = 0.0


@dataclass
class Seen:
    """What the server received."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class FakeState:
    """Script and log shared with the handler."""

    script: list[Canned]
    seen: list[Seen] = field(default_factory=list)
    release: threading.Event = field(default_factory=threading.Event)


def ok_body(
    text: str = "hello", tokens_in: int = 10, tokens_out: int = 5, *, usage: bool = True
) -> bytes:
    """A well-formed chat completion body."""
    data: dict[str, object] = {
        "id": "cmpl-1",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
    }
    if usage:
        data["usage"] = {"prompt_tokens": tokens_in, "completion_tokens": tokens_out}
    return json.dumps(data).encode("utf-8")


def _handler(state: FakeState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            state.seen.append(
                Seen("POST", self.path, {k.lower(): v for k, v in self.headers.items()}, body)
            )
            index = min(len(state.seen) - 1, len(state.script) - 1)
            canned = state.script[index]
            if canned.hang_s:
                state.release.wait(canned.hang_s)
            self.send_response(canned.status)
            if canned.content_type is not None:
                self.send_header("Content-Type", canned.content_type)
            for name, value in canned.headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(canned.body)))
            self.end_headers()
            try:
                self.wfile.write(canned.body)
            except OSError:
                return

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


@contextmanager
def fake_server(script: list[Canned]) -> Iterator[tuple[str, FakeState]]:
    """Run the server in a thread. Yields its base URL (ending in /v1) and its state."""
    state = FakeState(script=script)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", state
    finally:
        state.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def closed_port_url() -> str:
    """A loopback URL whose port has nothing listening (connection refused)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    return f"http://127.0.0.1:{port}/v1"
