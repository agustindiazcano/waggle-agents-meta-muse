"""The legacy initialize flow and the per-request modern flow, as read from the specification."""

import json
from collections.abc import Mapping

import pytest

from waggle import __version__
from waggle.mcp_server.boundary import CallResult
from waggle.mcp_server.transport import LineServer

TOKEN = "c" * 43
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
INFO_KEY = "io.modelcontextprotocol/serverInfo"


class FakeBoundary:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def handle(
        self, token: str, request_id: str, tool: str, args: Mapping[str, object]
    ) -> CallResult:
        self.calls.append((request_id, args))
        return CallResult(True, data={"accepted": True})


def _server() -> tuple[LineServer, FakeBoundary]:
    boundary = FakeBoundary()
    return LineServer(boundary, TOKEN, "sess"), boundary


def _send(server: LineServer, message: dict[str, object]) -> dict[str, object] | None:
    line = server.handle_line(json.dumps(message))
    return None if line is None else json.loads(line)


def _initialize(version: object = "2025-11-25") -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": version,
            "capabilities": {"roots": {}},
            "clientInfo": {"name": "client", "version": "1"},
        },
    }


def _modern(method: str, msg_id: object = "m1", **extra: object) -> dict[str, object]:
    meta = {VERSION_KEY: "2026-07-28", CAPS_KEY: {}, **extra}
    return {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": {"_meta": meta}}


def _with_params(message: dict[str, object], **params: object) -> dict[str, object]:
    merged = {**message["params"], **params}  # type: ignore[dict-item]
    return {**message, "params": merged}


def _with_meta(message: dict[str, object], **meta: object) -> dict[str, object]:
    params = dict(message["params"])  # type: ignore[call-overload]
    params["_meta"] = {**params["_meta"], **meta}
    return {**message, "params": params}


# ---- legacy initialize ----


def test_initialize_answers_with_the_requested_version_when_supported() -> None:
    server, _ = _server()
    reply = _send(server, _initialize("2025-11-25"))
    assert reply is not None
    result = reply["result"]
    assert result["protocolVersion"] == "2025-11-25"  # type: ignore[index]
    assert result["serverInfo"] == {"name": "waggle-hive", "version": __version__}  # type: ignore[index]
    assert "tools" in result["capabilities"]  # type: ignore[index]


def test_initialize_answers_with_its_own_version_when_the_requested_one_is_unsupported() -> None:
    server, _ = _server()
    reply = _send(server, _initialize("1900-01-01"))
    assert reply is not None and reply["result"]["protocolVersion"] == "2025-11-25"  # type: ignore[index]


@pytest.mark.parametrize(
    "params",
    [
        None,
        [],
        {"capabilities": {}, "clientInfo": {}},
        {"protocolVersion": 5, "capabilities": {}, "clientInfo": {}},
        {"protocolVersion": "2025-11-25", "clientInfo": {}},
        {"protocolVersion": "2025-11-25", "capabilities": {}},
    ],
)
def test_initialize_with_bad_params_is_invalid_params(params: object) -> None:
    server, _ = _server()
    reply = _send(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params})
    assert reply is not None and reply["error"]["code"] == -32602  # type: ignore[index]


def test_a_legacy_request_before_initialize_is_refused_and_forwards_nothing() -> None:
    server, boundary = _server()
    for method, params in (("tools/list", {}), ("tools/call", {"name": "get_task"})):
        reply = _send(server, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        assert reply is not None and reply["error"]["code"] == -32600  # type: ignore[index]
    assert boundary.calls == []


def test_tools_work_after_initialize_and_the_initialized_notification_is_silent() -> None:
    server, boundary = _server()
    _send(server, _initialize())
    assert _send(server, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    reply = _send(
        server,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_task", "arguments": {"task_id": "t1"}},
        },
    )
    assert reply is not None and reply["result"]["isError"] is False  # type: ignore[index]
    assert "resultType" not in reply["result"]  # type: ignore[operator]
    assert boundary.calls[0][0] == "sess:2"


def test_ping_gets_an_empty_result_even_before_initialize() -> None:
    server, _ = _server()
    reply = _send(server, {"jsonrpc": "2.0", "id": "p", "method": "ping"})
    assert reply == {"jsonrpc": "2.0", "id": "p", "result": {}}


# ---- modern per-request flow ----


def test_server_discover_reports_versions_capabilities_and_server_info() -> None:
    server, _ = _server()
    reply = _send(server, _modern("server/discover", "discover-1"))
    assert reply is not None and reply["id"] == "discover-1"
    result = reply["result"]
    assert result["resultType"] == "complete"  # type: ignore[index]
    assert result["supportedVersions"] == ["2026-07-28"]  # type: ignore[index]
    assert "tools" in result["capabilities"]  # type: ignore[index]
    assert result["_meta"][INFO_KEY] == {"name": "waggle-hive", "version": __version__}  # type: ignore[index]


def test_modern_requests_need_no_prior_handshake_and_carry_a_result_type() -> None:
    server, boundary = _server()
    listed = _send(server, _modern("tools/list"))
    assert listed is not None and listed["result"]["resultType"] == "complete"  # type: ignore[index]
    call = _with_params(_modern("tools/call", 9), name="get_task", arguments={"task_id": "t1"})
    reply = _send(server, call)
    assert reply is not None and reply["result"]["resultType"] == "complete"  # type: ignore[index]
    assert reply["result"]["isError"] is False  # type: ignore[index]
    assert boundary.calls[0][1] == {"task_id": "t1"}


def test_modern_arguments_exclude_the_meta_field() -> None:
    server, boundary = _server()
    call = _with_params(
        _modern("tools/call", 3, progressToken="abc"), name="get_task", arguments={"task_id": "t1"}
    )
    _send(server, call)
    assert boundary.calls[0][1] == {"task_id": "t1"}


def test_an_unsupported_modern_version_is_error_32022_with_the_supported_list() -> None:
    server, boundary = _server()
    reply = _send(server, _with_meta(_modern("tools/list"), **{VERSION_KEY: "1900-01-01"}))
    assert reply is not None
    error = reply["error"]
    assert error["code"] == -32022 and error["message"] == "Unsupported protocol version"  # type: ignore[index]
    assert error["data"] == {"supported": ["2026-07-28"], "requested": "1900-01-01"}  # type: ignore[index]
    assert boundary.calls == []


def test_a_modern_request_missing_client_capabilities_is_invalid_params() -> None:
    server, boundary = _server()
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"_meta": {VERSION_KEY: "2026-07-28"}, "name": "get_task", "arguments": {}},
    }
    reply = _send(server, message)
    assert reply is not None and reply["error"]["code"] == -32602  # type: ignore[index]
    assert boundary.calls == []


def test_a_non_string_modern_version_or_non_object_capabilities_is_invalid_params() -> None:
    server, _ = _server()
    for override in ({VERSION_KEY: 5}, {CAPS_KEY: "x"}):
        reply = _send(server, _with_meta(_modern("tools/list"), **override))
        assert reply is not None and reply["error"]["code"] == -32602  # type: ignore[index]


def test_unknown_methods_stay_method_not_found_in_both_flows() -> None:
    server, _ = _server()
    modern = _send(server, _modern("resources/list"))
    assert modern is not None and modern["error"]["code"] == -32601  # type: ignore[index]
    _send(server, _initialize())
    legacy = _send(server, {"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    assert legacy is not None and legacy["error"]["code"] == -32601  # type: ignore[index]


def test_replies_never_contain_the_token() -> None:
    server, _ = _server()
    for message in (_initialize(), _modern("server/discover"), _modern("tools/list")):
        line = server.handle_line(json.dumps(message))
        assert line is not None and TOKEN not in line
