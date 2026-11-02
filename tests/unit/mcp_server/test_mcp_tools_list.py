"""tools/list shows only what the authenticated chassis may call (ADR-063).

The listing and the call path read one allowlist, so the two cannot drift.
"""

import json
from collections.abc import Mapping

import pytest

from waggle.db.mcp_audit import AuditIntent, IntentOutcome, RateLimit, ResultRecord
from waggle.mcp_server.allowlist import ALLOWLIST, TOOLS, allowed_tools, is_allowed
from waggle.mcp_server.boundary import Boundary
from waggle.mcp_server.bounds import MapExtent
from waggle.mcp_server.identity import Identity, IdentityRecord, hash_token
from waggle.mcp_server.schemas import SCHEMAS
from waggle.mcp_server.transport import LineServer

TOKEN = "c" * 43
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
INIT = {
    "jsonrpc": "2.0",
    "id": "i",
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
}


class Store:
    def __init__(self, chassis: str, *, revoked: bool = False, fail: bool = False) -> None:
        self.record = IdentityRecord(hash_token(TOKEN), chassis, "robot-0", revoked)
        self.fail = fail

    def lookup(self, token_hash: str) -> IdentityRecord | None:
        if self.fail:
            raise RuntimeError("db down")
        return self.record if token_hash == self.record.token_hash else None


class Audit:
    def begin(self, intent: AuditIntent, limit: RateLimit) -> IntentOutcome:
        return IntentOutcome(True)

    def deny(self, intent: AuditIntent, reason: str) -> IntentOutcome:
        return IntentOutcome(False, reason=reason)

    def complete(self, correlation_id: str, outcome: str, latency_ms: int) -> ResultRecord:
        return ResultRecord(True)


class Forwarder:
    def forward(
        self, identity: Identity, tool: str, args: Mapping[str, object], timeout_s: float
    ) -> Mapping[str, object]:
        return {"accepted": True}


def _boundary(store: Store) -> Boundary:
    extent = MapExtent(0.0, 0.0, 100.0, 50.0)
    return Boundary(store, Audit(), Forwarder(), extent, RateLimit(10, 60), 2.5)


def _server(store: Store, *, handshake: bool = True) -> LineServer:
    server = LineServer(_boundary(store), TOKEN, "sess")
    if handshake:
        server.handle_line(json.dumps(INIT))
    return server


def _listed(server: LineServer, params: object = None) -> list[str]:
    message: dict[str, object] = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    if params is not None:
        message["params"] = params
    reply = json.loads(server.handle_line(json.dumps(message)) or "null")
    return [tool["name"] for tool in reply["result"]["tools"]]


def test_allowed_tools_is_the_function_behind_is_allowed() -> None:
    for chassis in [*ALLOWLIST, "unknown", ""]:
        for tool in [*TOOLS, "nope"]:
            assert (tool in allowed_tools(chassis)) == is_allowed(chassis, tool)


def test_allowed_tools_of_an_unknown_chassis_is_empty() -> None:
    assert allowed_tools("nobody") == frozenset()


@pytest.mark.parametrize("chassis", sorted(ALLOWLIST))
def test_listed_tools_equal_the_allowed_tools_in_sorted_order(chassis: str) -> None:
    assert _listed(_server(Store(chassis))) == sorted(ALLOWLIST[chassis])


def test_every_tool_a_chassis_can_call_is_listed_and_no_other() -> None:
    for chassis in ALLOWLIST:
        listed = set(_listed(_server(Store(chassis))))
        for tool in SCHEMAS:
            assert (tool in listed) == is_allowed(chassis, tool)


def test_chassis_lists_differ() -> None:
    assert _listed(_server(Store("carrier"))) != _listed(_server(Store("maintenance")))


def test_a_listed_tool_has_the_unchanged_input_schema() -> None:
    server = _server(Store("parts_runner"))
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    tools = json.loads(server.handle_line(json.dumps(message)) or "")["result"]["tools"]
    move = next(t for t in tools if t["name"] == "move_waypoint")
    assert move["inputSchema"]["additionalProperties"] is False
    assert set(move["inputSchema"]["required"]) == set(SCHEMAS["move_waypoint"])


def test_an_unlisted_tool_is_still_denied_when_the_client_names_it() -> None:
    server = _server(Store("parts_runner"))
    assert "pick_package" not in _listed(server)
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "pick_package", "arguments": {}},
    }
    result = json.loads(server.handle_line(json.dumps(call)) or "")["result"]
    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"]) == {"code": "tool_not_allowed"}


@pytest.mark.parametrize("fault", ["unknown", "revoked", "store_down"])
def test_unauthenticated_or_unknown_chassis_lists_nothing(fault: str) -> None:
    store = {
        "unknown": Store("carrier"),
        "revoked": Store("carrier", revoked=True),
        "store_down": Store("carrier", fail=True),
    }[fault]
    if fault == "unknown":
        store.record = IdentityRecord(hash_token("d" * 43), "carrier", "robot-0", False)
    assert _listed(_server(store)) == []


def test_boundary_allowed_tools_fails_closed_on_a_bad_token() -> None:
    boundary = _boundary(Store("carrier"))
    assert boundary.allowed_tools("") == frozenset()
    assert boundary.allowed_tools("x" * 300) == frozenset()
    assert boundary.allowed_tools(TOKEN) == ALLOWLIST["carrier"]


def test_legacy_client_cannot_list_before_initialize() -> None:
    server = _server(Store("carrier"), handshake=False)
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    reply = json.loads(server.handle_line(json.dumps(message)) or "")
    assert "result" not in reply and reply["error"]["code"] == -32600


@pytest.mark.parametrize(
    "params",
    [
        {"chassis": "maintenance"},
        {"robot_id": "maintenance-0", "_meta": {"chassis": "maintenance"}},
        {"arguments": {"chassis": "maintenance"}, "name": "reserve_part"},
    ],
)
def test_extra_parameters_cannot_select_another_chassis(params: object) -> None:
    server = _server(Store("carrier"))
    assert _listed(server, params) == sorted(ALLOWLIST["carrier"])


def test_modern_request_is_filtered_by_the_token_chassis() -> None:
    server = _server(Store("parts_runner"), handshake=False)
    meta = {VERSION_KEY: "2026-07-28", CAPS_KEY: {}, "chassis": "maintenance"}
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}}
    reply = json.loads(server.handle_line(json.dumps(message)) or "")
    names = [tool["name"] for tool in reply["result"]["tools"]]
    assert names == sorted(ALLOWLIST["parts_runner"])
    assert reply["result"]["resultType"] == "complete"
