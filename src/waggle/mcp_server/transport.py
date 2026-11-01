"""Newline-delimited JSON-RPC transport for the MCP boundary (ADR-045, ADR-046).

Stdio framing: one message per line, nothing but protocol messages on stdout. Two protocol
flows, both read from the current specification:

- Legacy (revision 2025-11-25): ``initialize`` must come first. Other requests before it are
  refused; ``ping`` is always answered.
- Modern (revision 2026-07-28): no handshake. Every request carries ``_meta`` with the
  protocol version and client capabilities; ``server/discover`` reports what this server
  supports. A request is modern when its ``_meta`` has the protocol version key.

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

from waggle import __version__
from waggle.mcp_server.boundary import CallResult
from waggle.mcp_server.schemas import SCHEMAS

logger = logging.getLogger("waggle.mcp_server")

LEGACY_VERSION = "2025-11-25"
MODERN_VERSIONS = ("2026-07-28",)
_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
_SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"
_SERVER_INFO = {"name": "waggle-hive", "version": __version__}
_CAPABILITIES: dict[str, object] = {"tools": {}}

_LINE_MAX = 65_536
_SESSION = re.compile(r"[A-Za-z0-9_.-]{1,32}")
_STR_ID_MAX = 64

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_UNSUPPORTED_VERSION = -32022

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


def _error(msg_id: object, code: int, message: str, data: object = None) -> str:
    error: dict[str, object] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return _dump({"jsonrpc": "2.0", "id": msg_id, "error": error})


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
        self._initialized = False

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
        method: str = message["method"]
        params = message.get("params")
        if method == "ping":
            return _dump({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        meta = params.get("_meta") if isinstance(params, dict) else None
        modern = isinstance(meta, dict) and _VERSION_KEY in meta
        if modern:
            problem = self._check_meta(msg_id, meta)
            if problem is not None:
                return problem
        elif method == "initialize":
            return self._initialize(msg_id, params)
        elif not self._initialized:
            return _error(msg_id, _INVALID_REQUEST, "server not initialized")
        return self._dispatch(msg_id, method, params, modern)

    @staticmethod
    def _check_meta(msg_id: object, meta: object) -> str | None:
        if not isinstance(meta, dict):
            return _error(msg_id, _INVALID_PARAMS, "invalid params")
        version = meta.get(_VERSION_KEY)
        if not isinstance(version, str) or not isinstance(meta.get(_CAPABILITIES_KEY), dict):
            return _error(msg_id, _INVALID_PARAMS, "invalid params")
        if version not in MODERN_VERSIONS:
            return _error(
                msg_id,
                _UNSUPPORTED_VERSION,
                "Unsupported protocol version",
                {"supported": list(MODERN_VERSIONS), "requested": version},
            )
        return None

    def _initialize(self, msg_id: object, params: object) -> str:
        if (
            not isinstance(params, dict)
            or not isinstance(params.get("protocolVersion"), str)
            or not isinstance(params.get("capabilities"), dict)
            or not isinstance(params.get("clientInfo"), dict)
        ):
            return _error(msg_id, _INVALID_PARAMS, "invalid params")
        self._initialized = True
        result: dict[str, object] = {
            "protocolVersion": LEGACY_VERSION,
            "capabilities": _CAPABILITIES,
            "serverInfo": _SERVER_INFO,
        }
        return _dump({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _dispatch(self, msg_id: object, method: str, params: object, modern: bool) -> str:
        if method == "server/discover" and modern:
            result: dict[str, object] = {
                "supportedVersions": list(MODERN_VERSIONS),
                "capabilities": _CAPABILITIES,
            }
        elif method == "tools/list":
            result = {"tools": _tool_definitions()}
        elif method == "tools/call":
            called = self._call(msg_id, params)
            if isinstance(called, str):
                return called
            result = called
        else:
            return _error(msg_id, _METHOD_NOT_FOUND, "method not found")
        if modern:
            result["resultType"] = "complete"
            result["_meta"] = {_SERVER_INFO_KEY: _SERVER_INFO}
        return _dump({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _call(self, msg_id: object, params: object) -> dict[str, object] | str:
        """The tool result payload, or an error line."""
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
            return {
                "content": [{"type": "text", "text": _dump(data)}],
                "structuredContent": data,
                "isError": False,
            }
        return {
            "content": [{"type": "text", "text": _dump({"code": result.code})}],
            "isError": True,
        }


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
