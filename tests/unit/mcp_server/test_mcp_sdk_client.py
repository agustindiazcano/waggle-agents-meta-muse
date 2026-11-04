"""The official MCP Python SDK client against the real line transport, fake-backed.

The server subprocess runs the production LineServer with a fake dispatcher at
the boundary seam (tests/support/mcp_client_fake_server.py). No database and no
paid call. This is a client interop check, not a conformance claim.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[3]
ALLOWED_TOOL = "get_task"
DENIED_TOOL = "move_waypoint"


def _server_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT / "tests" / "support")])
    return env


async def _exercise_client() -> dict[str, object]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_client_fake_server"],
        env=_server_env(),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        tools = await session.list_tools()
        allowed = await session.call_tool(ALLOWED_TOOL, {"task_id": "t1"})
        denied = await session.call_tool(DENIED_TOOL, {"x": 1.0, "y": 2.0, "speed": 0.5})
        return {
            "server_name": init.server_info.name,
            "protocol": init.protocol_version,
            "tools": sorted(tool.name for tool in tools.tools),
            "allowed_is_error": allowed.is_error,
            "allowed_payload": json.loads(allowed.content[0].text),  # type: ignore[union-attr]
            "denied_is_error": denied.is_error,
            "denied_payload": json.loads(denied.content[0].text),  # type: ignore[union-attr]
        }


def test_official_sdk_client_completes_handshake_list_and_calls() -> None:
    result = asyncio.run(_exercise_client())
    assert result["server_name"] == "waggle-hive"
    assert result["tools"] == [ALLOWED_TOOL]
    assert result["allowed_is_error"] is False
    assert result["allowed_payload"] == {"task_id": "t1", "status": "accepted"}
    assert result["denied_is_error"] is True
    assert result["denied_payload"] == {"code": "tool_not_allowed"}


def test_server_process_exits_2_and_names_the_missing_setting_without_its_value() -> None:
    env = _server_env()
    for name in (
        "WAGGLE_MCP_TOKEN",
        "WAGGLE_MCP_EXTENT",
        "WAGGLE_MCP_RATE_MAX_CALLS",
        "WAGGLE_MCP_RATE_WINDOW_S",
        "WAGGLE_MCP_TIMEOUT_S",
        "DATABASE_URL",
    ):
        env.pop(name, None)
    proc = subprocess.run(
        [sys.executable, "-m", "waggle.mcp_server"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert (
        "WAGGLE_MCP_TOKEN is required" in proc.stderr or "DATABASE_URL is required" in proc.stderr
    )
