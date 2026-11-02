"""The bridge: forwards messages to one WebSocket client, one JSON message per frame.

It enforces the send rate (at most ``max_fps`` messages per second, via an injected sleep so
no wall clock is read), the stride over simulator ticks (skipped ticks stay visible because
every frame carries its ``tick``) and the frame size cap. An over-cap frame is dropped and
reported with an error message, never truncated. Any message from the client is refused and
ends the stream: a client cannot change the run. The stream always ends with a close frame.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Generator

from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from waggle.api.config import ApiConfig
from waggle.api.sources import Item
from waggle.sim import frame

Sleep = Callable[[float], Awaitable[None]]

CLOSE_NORMAL = 1000
CLOSE_POLICY = 1008
CLOSE_INTERNAL = 1011


def error_text(code: str, tick: int | None = None) -> str:
    """An error message. The code is a fixed word; client input is never echoed."""
    body: frame.JsonObject = {"type": "error", "error": code}
    if tick is not None:
        body["tick"] = tick
    return frame.encode_frame(body)


async def reject(ws: WebSocket, code: str) -> None:
    """Accept, tell the client why the request is refused, and close with a policy code."""
    await ws.accept()
    await ws.send_text(error_text(code))
    await ws.close(code=CLOSE_POLICY)


async def _watch(ws: WebSocket, verdict: list[str]) -> None:
    """Record how the client side ended: it spoke (refused) or it went away."""
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                verdict.append("gone")
                return
            verdict.append("spoke")
            return
    except (WebSocketDisconnect, RuntimeError):
        verdict.append("gone")


def _next(items: Generator[Item]) -> Item | None:
    return next(items, None)


async def stream(ws: WebSocket, items: Generator[Item], config: ApiConfig, sleep: Sleep) -> None:
    """Accept the connection and forward the items until the source ends or the client leaves."""
    await ws.accept()
    verdict: list[str] = []
    watcher = asyncio.create_task(_watch(ws, verdict))
    delay = 1.0 / config.max_fps
    frames_seen = 0
    closed = False
    try:
        while True:
            await asyncio.sleep(0)
            if verdict:
                break
            item = await run_in_threadpool(_next, items)
            if item is None:
                break
            if item.kind == "frame":
                frames_seen += 1
                if (frames_seen - 1) % config.stride != 0:
                    continue
            if item.text is None or len(item.text.encode("utf-8")) > config.max_frame_bytes:
                await ws.send_text(error_text("frame_too_large", item.tick))
            else:
                await ws.send_text(item.text)
            await sleep(delay)
        if verdict == ["spoke"]:
            await ws.send_text(error_text("client_messages_not_allowed"))
            await ws.close(code=CLOSE_POLICY)
            closed = True
        elif not verdict:
            await ws.close(code=CLOSE_NORMAL)
            closed = True
    except (WebSocketDisconnect, RuntimeError):
        closed = True
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher
        items.close()
        if not closed and not verdict:
            with contextlib.suppress(RuntimeError):
                await ws.close(code=CLOSE_INTERNAL)
