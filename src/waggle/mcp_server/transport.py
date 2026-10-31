"""Newline-delimited JSON-RPC transport for the MCP boundary (ADR-045).

Covers what was checked against the current MCP specification: stdio framing (one message per
line, nothing but protocol messages on stdout), ``tools/list``, ``tools/call`` with ``isError``
results, and ``-32602`` for an unknown tool. It does not implement a handshake (``initialize``
or ``server/discover``), so it must not be described as a conformant MCP server.

The token is bound when the server is built, one chassis per process. Correlation ids are the
JSON-RPC id prefixed with a per-process session name, so they are unique across sessions and a
repeat inside one session is a replay. Argument values, tokens and exception text never reach a
reply.
"""

import json
import logging
import re
from collections.abc import Mapping
from typing import Protocol, TextIO

from waggle.mcp_server.boundary import CallResult
from waggle.mcp_server.schemas import SCHEMAS

logger = logging.getLogger("waggle.mcp_server")

_LINE_MAX = 65_536
_SESSION = re.compile(r"[A-Za-z0-9_.-]{1,32}")
_STR_ID_MAX = 64

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

_KIND_TYPE = {
    "id": "string",
    "text": "string",
    "token": "integer",
    "quantity": "integer",
    "x": "number",
    "y": "number",
    "speed": "number",
}


class Dispatcher(Protocol):
    """The boundary, as the transport sees it."""

    def handle(
        self, token: str, request_id: str, tool: str, args: Mapping[str, object]
    ) -> CallResult:
        """Run one call and return a typed result."""
        ...


def _reject_constant(value: str) -> object:
    raise ValueError("non-finite number")


def _dump(message: Mapping[str, object]) -> str:
    return json.dumps(message, separators=(",", ":"), allow_nan=False)


def _error(msg_id: object, code: int, message: str) -> str:
    return _dump({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def _tool_definitions() -> list[dict[str, object]]:
    """Advisory input schemas. The boundary enforces the real bounds per chassis."""
    return [
        {
            "name": name,
            "description": f"Waggle tool {name}. Arguments are validated and bounded server side.",
            "inputSchema": {
                "type": "object",
                "properties": {field: {"type": _KIND_TYPE[kind]} for field, kind in schema.items()},
                "required": sorted(schema),
                "additionalProperties": False,
            },
        }
        for name, schema in sorted(SCHEMAS.items())
    ]


class LineServer:
    """Turns one input line into at most one output line. Never raises."""

    def __init__(self, dispatcher: Dispatcher, token: str, session: str) -> None:
        if not isinstance(token, str) or not token:
            raise ValueError("a token is required")
        if not isinstance(session, str) or _SESSION.fullmatch(session) is None:
            raise ValueError("invalid session name")
        self._dispatcher = dispatcher
        self._token = token
        self._session = session

    def handle_line(self, line: str) -> str | None:
        """Return the reply line, or None for a notification."""
        try:
            return self._handle(line)
        except Exception as err:
            logger.error("transport failure: %s", type(err).__name__)
            return _error(None, _INTERNAL_ERROR, "internal error")

    def _handle(self, line: str) -> str | None:
        if len(line) > _LINE_MAX:
            return _error(None, _INVALID_REQUEST, "message too large")
        try:
            message = json.loads(line, parse_constant=_reject_constant)
        except ValueError:
            return _error(None, _PARSE_ERROR, "parse error")
        if (
            not isinstance(message, dict)
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
        ):
            return _error(None, _INVALID_REQUEST, "invalid request")
        if "id" not in message:
            return None
        msg_id = message["id"]
        if not (type(msg_id) is int or (isinstance(msg_id, str) and len(msg_id) <= _STR_ID_MAX)):
            return _error(None, _INVALID_REQUEST, "invalid id")
        method = message["method"]
        if method == "tools/list":
            return _dump({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _tool_definitions()}})
        if method == "tools/call":
            return self._call(msg_id, message.get("params"))
        return _error(msg_id, _METHOD_NOT_FOUND, "method not found")

    def _call(self, msg_id: object, params: object) -> str:
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error(msg_id, _INVALID_PARAMS, "invalid params")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error(msg_id, _INVALID_PARAMS, "invalid params")
        name: str = params["name"]
        result = self._dispatcher.handle(self._token, f"{self._session}:{msg_id}", name, arguments)
        if result.code == "tool_not_allowed" and name not in SCHEMAS:
            return _error(msg_id, _INVALID_PARAMS, "unknown tool")
        if result.ok:
            data = dict(result.data or {})
            payload: dict[str, object] = {
                "content": [{"type": "text", "text": _dump(data)}],
                "structuredContent": data,
                "isError": False,
            }
        else:
            payload = {
                "content": [{"type": "text", "text": _dump({"code": result.code})}],
                "isError": True,
            }
        return _dump({"jsonrpc": "2.0", "id": msg_id, "result": payload})


def serve_stdio(server: LineServer, source: TextIO, sink: TextIO) -> None:
    """Read lines until end of input, writing one reply line per request. Blank lines skip."""
    for raw in source:
        line = raw.strip()
        if not line:
            continue
        reply = server.handle_line(line)
        if reply is not None:
            sink.write(reply + "\n")
            sink.flush()
