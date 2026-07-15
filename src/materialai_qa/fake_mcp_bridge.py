"""Fault-injectable JSON-over-TCP bridge compatible with the public MCP protocol."""

from __future__ import annotations

import json
import socket
import socketserver
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeMcpBehavior:
    mode: str = "normal"
    delay_seconds: float = 0.0
    jobs: list[dict[str, Any]] = field(
        default_factory=lambda: [{"name": "qa_job", "status": "COMPLETED"}]
    )


class _FakeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], behavior: FakeMcpBehavior):
        super().__init__(address, _FakeHandler)
        self.behavior = behavior
        self.requests: list[dict[str, Any]] = []


class _FakeHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        chunks: list[bytes] = []
        while True:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            marker = chunk.find(b"\n")
            if marker >= 0:
                chunks.append(chunk[:marker])
                break
            chunks.append(chunk)
        server = self.server
        assert isinstance(server, _FakeServer)
        behavior = server.behavior
        if behavior.mode == "invalid_json":
            self.request.sendall(b"not-json\n")
            return
        request = json.loads(b"".join(chunks).decode("utf-8"))
        server.requests.append(request)
        if behavior.delay_seconds:
            time.sleep(behavior.delay_seconds)
        if behavior.mode == "timeout":
            time.sleep(5)
            return
        response_id = (
            str(uuid.uuid4()) if behavior.mode == "mismatched_id" else request.get("id")
        )
        if behavior.mode == "error":
            response = {
                "id": response_id,
                "ok": False,
                "error": {"type": "RuntimeError", "message": "fake kernel error"},
            }
        else:
            response = {
                "id": response_id,
                "ok": True,
                "result": _result_for(request, behavior),
            }
        self.request.sendall(
            json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )


def _result_for(request: dict[str, Any], behavior: FakeMcpBehavior) -> dict[str, Any]:
    method = request.get("method")
    if method == "ping":
        return {
            "abaqus_version": "2023-QA",
            "models": ["Model-1"],
            "viewports": ["Viewport: 1"],
            "bridge": {"version": "5.0.3-qa", "transport": "socket"},
        }
    if method == "execute":
        code = (request.get("params") or {}).get("code")
        if not isinstance(code, str) or not code.strip():
            return {
                "ok": False,
                "error_type": "ValueError",
                "core_error": "params.code must be a non-empty string",
            }
        return {
            "ok": True,
            "stdout": "",
            "return_value": {
                "models": {"Model-1": {}},
                "jobs": behavior.jobs,
                "received_unicode": "中文" in code,
            },
        }
    if method == "stop":
        return {"success": True, "message": "stop requested"}
    return {"method": method}


class FakeMcpBridge:
    def __init__(self, behavior: FakeMcpBehavior | None = None):
        self.behavior = behavior or FakeMcpBehavior()
        self._server = _FakeServer(("127.0.0.1", 0), self.behavior)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def requests(self) -> list[dict[str, Any]]:
        return list(self._server.requests)

    def __enter__(self) -> "FakeMcpBridge":
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=3)


def bridge_request(
    host: str,
    port: int,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    payload = {"id": str(uuid.uuid4()), "method": method, "params": params or {}}
    with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
        connection.settimeout(timeout_seconds)
        connection.sendall(
            json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                raise RuntimeError("socket closed before a complete response")
            marker = chunk.find(b"\n")
            if marker >= 0:
                chunks.append(chunk[:marker])
                break
            chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))
