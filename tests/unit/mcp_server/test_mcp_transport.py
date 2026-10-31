"""The line transport maps JSON-RPC tool messages onto the boundary and never raises."""

import io
import json
from collections.abc import Mapping

import pytest

from waggle.mcp_server.boundary import CallResult
from waggle.mcp_server.schemas import SCHEMAS
from waggle.mcp_server.transport import LineServer, serve_stdio

TOKEN = "c" * 43


class FakeBoundary:
    def __init__(self, result: CallResult | None = None, *, explode: bool = False) -> None:
        self.result = result or CallResult(True, data={"accepted": True})
        self.explode = explode
        self.calls: list[tuple[str, str, str, Mapping[str, object]]] = []

    def handle(
        self, token: str, request_id: str, tool: str, args: Mapping[str, object]
    ) -> CallResult:
        if self.explode:
            raise RuntimeError("secret detail")
        self.calls.append((token, request_id, tool, args))
        return self.result


def _server(boundary: FakeBoundary | None = None) -> tuple[LineServer, FakeBoundary]:
    boundary = boundary or FakeBoundary()
    return LineServer(boundary, TOKEN, "sess"), boundary


def _call(server: LineServer, message: object) -> dict[str, object] | None:
    line = server.handle_line(message if isinstance(message, str) else json.dumps(message))
    return None if line is None else json.loads(line)


def _tools_call(msg_id: object, name: object, arguments: object) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def test_tools_list_names_every_tool_in_a_stable_order_with_strict_schemas() -> None:
    server, _ = _server()
    reply = _call(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert reply is not None
    tools = reply["result"]["tools"]  # type: ignore[index]
    assert [t["name"] for t in tools] == sorted(SCHEMAS)
    move = next(t for t in tools if t["name"] == "move_waypoint")
    schema = move["inputSchema"]
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert set(schema["required"]) == set(SCHEMAS["move_waypoint"])
    assert schema["properties"]["speed"]["type"] == "number"
    assert _call(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) is not None


def test_a_successful_call_returns_content_structured_content_and_no_error() -> None:
    server, boundary = _server()
    reply = _call(server, _tools_call(7, "get_task", {"task_id": "t1"}))
    assert reply is not None and reply["id"] == 7
    result = reply["result"]
    assert result["isError"] is False  # type: ignore[index]
    assert result["structuredContent"] == {"accepted": True}  # type: ignore[index]
    assert json.loads(result["content"][0]["text"]) == {"accepted": True}  # type: ignore[index]
    token, request_id, tool, args = boundary.calls[0]
    assert (token, tool, args) == (TOKEN, "get_task", {"task_id": "t1"})
    assert request_id == "sess:7"


def test_a_denied_call_is_a_tool_error_with_only_the_reason_code() -> None:
    server, _ = _server(FakeBoundary(CallResult(False, "out_of_bounds")))
    reply = _call(server, _tools_call(1, "move_waypoint", {}))
    assert reply is not None
    result = reply["result"]
    assert result["isError"] is True  # type: ignore[index]
    assert json.loads(result["content"][0]["text"]) == {"code": "out_of_bounds"}  # type: ignore[index]
    assert "structuredContent" not in result  # type: ignore[operator]


def test_an_unknown_tool_is_a_protocol_error_after_the_boundary_audited_it() -> None:
    server, boundary = _server(FakeBoundary(CallResult(False, "tool_not_allowed")))
    reply = _call(server, _tools_call(1, "rm_rf", {}))
    assert reply is not None and reply["error"]["code"] == -32602  # type: ignore[index]
    assert len(boundary.calls) == 1


def test_a_known_tool_the_chassis_may_not_use_is_a_tool_error_not_a_protocol_error() -> None:
    server, _ = _server(FakeBoundary(CallResult(False, "tool_not_allowed")))
    reply = _call(server, _tools_call(1, "create_purchase_order", {}))
    assert reply is not None and reply["result"]["isError"] is True  # type: ignore[index]


@pytest.mark.parametrize(
    "line", ["not json", "[]", "5", '{"jsonrpc":"2.0"}', '{"jsonrpc":"1.0","id":1,"method":"x"}']
)
def test_malformed_messages_get_an_error_reply(line: str) -> None:
    server, boundary = _server()
    reply = _call(server, line)
    assert reply is not None and reply["error"]["code"] in (-32700, -32600)  # type: ignore[index]
    assert boundary.calls == []


@pytest.mark.parametrize("bad_id", [None, True, 1.5, [], {}])
def test_an_id_that_is_not_a_string_or_integer_is_rejected(bad_id: object) -> None:
    server, boundary = _server()
    reply = _call(server, _tools_call(bad_id, "get_task", {"task_id": "t1"}))
    assert reply is not None and reply["error"]["code"] == -32600  # type: ignore[index]
    assert boundary.calls == []


@pytest.mark.parametrize(
    "params", [None, [], {"name": 5, "arguments": {}}, {"name": "get_task", "arguments": []}]
)
def test_bad_call_params_are_invalid_params(params: object) -> None:
    server, boundary = _server()
    reply = _call(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})
    assert reply is not None and reply["error"]["code"] == -32602  # type: ignore[index]
    assert boundary.calls == []


def test_a_missing_arguments_field_is_an_empty_object() -> None:
    server, boundary = _server()
    _call(
        server, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_task"}}
    )
    assert boundary.calls[0][3] == {}


def test_notifications_get_no_reply_and_unknown_methods_get_method_not_found() -> None:
    server, boundary = _server()
    assert _call(server, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert _call(server, {"jsonrpc": "2.0", "method": "tools/call", "params": {}}) is None
    assert boundary.calls == []
    reply = _call(server, {"jsonrpc": "2.0", "id": 1, "method": "resources/list"})
    assert reply is not None and reply["error"]["code"] == -32601  # type: ignore[index]


def test_a_boundary_exception_becomes_an_internal_error_without_detail() -> None:
    server, _ = _server(FakeBoundary(explode=True))
    line = server.handle_line(json.dumps(_tools_call(1, "get_task", {"task_id": "t1"})))
    assert line is not None
    assert json.loads(line)["error"]["code"] == -32603
    assert "secret" not in line and TOKEN not in line


def test_an_oversize_line_is_rejected_before_parsing() -> None:
    server, boundary = _server()
    reply = _call(server, "x" * 70_000)
    assert reply is not None and reply["error"]["code"] == -32600  # type: ignore[index]
    assert boundary.calls == []


def test_the_token_never_appears_in_any_reply() -> None:
    server, _ = _server()
    for message in (
        _tools_call(1, "get_task", {"task_id": "t1"}),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ):
        line = server.handle_line(json.dumps(message))
        assert line is not None and TOKEN not in line


def test_each_session_prefixes_its_own_correlation_ids() -> None:
    boundary = FakeBoundary()
    LineServer(boundary, TOKEN, "a").handle_line(json.dumps(_tools_call(1, "get_task", {})))
    LineServer(boundary, TOKEN, "b").handle_line(json.dumps(_tools_call(1, "get_task", {})))
    assert [c[1] for c in boundary.calls] == ["a:1", "b:1"]


def test_stdio_loop_writes_one_line_per_reply_and_skips_blank_lines_and_notifications() -> None:
    server, _ = _server()
    lines = [
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "",
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        "garbage",
    ]
    out = io.StringIO()
    serve_stdio(server, io.StringIO("\n".join(lines) + "\n"), out)
    replies = out.getvalue().splitlines()
    assert len(replies) == 2
    assert "tools" in json.loads(replies[0])["result"]
    assert json.loads(replies[1])["error"]["code"] == -32700
    assert all("\n" not in r for r in replies)


def test_constructor_rejects_an_empty_token_or_session() -> None:
    with pytest.raises(ValueError):
        LineServer(FakeBoundary(), "", "sess")
    with pytest.raises(ValueError):
        LineServer(FakeBoundary(), TOKEN, "bad session")
