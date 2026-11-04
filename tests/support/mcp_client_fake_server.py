"""Fake-backed MCP server process for the real-client test.

Runs the production LineServer over stdio with a dispatcher that stands in for
the database-backed boundary: one allowed tool, every other tool denied. This
exercises the transport and handshake against a real client without a database.
Run as: python -m mcp_client_fake_server (with src and tests/support on the path).
"""

import sys
from collections.abc import Mapping

from waggle.mcp_server.boundary import CallResult
from waggle.mcp_server.transport import LineServer, serve_stdio

TOKEN = "c" * 43
ALLOWED_TOOL = "get_task"


class FakeDispatcher:
    """One allowed tool; every other known or unknown tool is denied by code."""

    def handle(
        self, token: str, request_id: str, tool: str, args: Mapping[str, object]
    ) -> CallResult:
        """Accept the allowed tool and deny the rest, recording nothing."""
        if tool != ALLOWED_TOOL:
            return CallResult(False, "tool_not_allowed")
        task_id = args.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return CallResult(False, "invalid_arguments")
        return CallResult(True, data={"task_id": task_id, "status": "accepted"})

    def allowed_tools(self, token: str) -> frozenset[str]:
        """The single tool this fake chassis may call."""
        return frozenset({ALLOWED_TOOL})


def main() -> int:
    """Serve stdio until end of input. Stdout carries protocol messages only."""
    serve_stdio(LineServer(FakeDispatcher(), TOKEN, "sdkclient"), sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
