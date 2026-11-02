"""The FastAPI app of waggle.api: a health endpoint and two read-only WebSocket streams.

Security and scope: there is no authentication yet (none is designed), so the process binds to
127.0.0.1 by default and must not be exposed on a network as it is. The app has no write
endpoint. A client picks only an allowlisted scenario id (live) or a replay file name under the
configured replay directory (replay); live runs use the configured seed. The bridge computes
nothing: it forwards what the simulator produced. A browser page on any origin can still open
a socket to localhost and read frames, which are simulator data and nothing else.
"""

import asyncio
import logging

from fastapi import FastAPI, WebSocket

from waggle.api import bridge, paths, sources
from waggle.api.bridge import Sleep
from waggle.api.config import ApiConfig
from waggle.replay import replay_format

log = logging.getLogger("waggle.api")


def create_app(config: ApiConfig, sleep: Sleep = asyncio.sleep) -> FastAPI:
    """Build the app. ``sleep`` paces the stream and is replaced by a fake in tests."""
    app = FastAPI(title="Waggle Hive API", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness probe."""
        return {"service": "api", "status": "ok"}

    @app.websocket("/ws/live")
    async def live(ws: WebSocket, scenario: str = "") -> None:
        """Stream a scenario run: a world message, then one frame per sent tick."""
        try:
            scenario_id = paths.check_scenario(scenario)
        except paths.Rejected:
            await bridge.reject(ws, "unknown_scenario")
            return
        await bridge.stream(ws, sources.live_items(config, scenario_id), config, sleep)

    @app.websocket("/ws/replay")
    async def replay(ws: WebSocket, name: str = "") -> None:
        """Stream a recorded replay file: header, frames as recorded, footer."""
        try:
            path = paths.resolve_replay(config.replay_dir, name)
        except paths.Rejected:
            await bridge.reject(ws, "replay_not_allowed")
            return
        try:
            items = sources.replay_items(path)
        except replay_format.ReplayError:
            log.warning("replay file refused by the strict reader")
            await bridge.reject(ws, "replay_invalid")
            return
        await bridge.stream(ws, items, config, sleep)

    return app
