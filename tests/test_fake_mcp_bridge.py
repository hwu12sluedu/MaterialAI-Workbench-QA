from __future__ import annotations

import json
import socket

import pytest

from materialai_qa.fake_mcp_bridge import (
    FakeMcpBehavior,
    FakeMcpBridge,
    bridge_request,
)


def test_fake_bridge_ping_and_unicode_execute() -> None:
    with FakeMcpBridge() as bridge:
        ping = bridge_request(bridge.host, bridge.port, "ping")
        execute = bridge_request(
            bridge.host,
            bridge.port,
            "execute",
            {"code": "result = {'label': '中文'}"},
        )

    assert ping["ok"] is True
    assert ping["result"]["bridge"]["version"] == "5.0.3-qa"
    assert execute["result"]["return_value"]["received_unicode"] is True
    assert [item["method"] for item in bridge.requests] == ["ping", "execute"]


def test_fake_bridge_mismatched_id_fault() -> None:
    with FakeMcpBridge(FakeMcpBehavior(mode="mismatched_id")) as bridge:
        response = bridge_request(bridge.host, bridge.port, "ping")

    assert response["ok"] is True
    assert response["id"] != bridge.requests[0]["id"]


def test_fake_bridge_invalid_json_fault() -> None:
    with FakeMcpBridge(FakeMcpBehavior(mode="invalid_json")) as bridge:
        with pytest.raises(json.JSONDecodeError):
            bridge_request(bridge.host, bridge.port, "ping")


def test_fake_bridge_kernel_error_fault() -> None:
    with FakeMcpBridge(FakeMcpBehavior(mode="error")) as bridge:
        response = bridge_request(bridge.host, bridge.port, "execute", {"code": "x=1"})

    assert response["ok"] is False
    assert response["error"]["message"] == "fake kernel error"


def test_fake_bridge_timeout_fault() -> None:
    behavior = FakeMcpBehavior(mode="timeout")
    with FakeMcpBridge(behavior) as bridge:
        with pytest.raises(socket.timeout):
            bridge_request(
                bridge.host,
                bridge.port,
                "ping",
                timeout_seconds=0.1,
            )
