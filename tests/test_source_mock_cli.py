from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

from materialai_qa.contracts import validate_document
from materialai_qa.fake_mcp_bridge import FakeMcpBehavior, FakeMcpBridge


def _diagnostics_command() -> list[str]:
    configured = os.environ.get("MATERIALAI_QA_DIAGNOSTICS_COMMAND")
    if configured:
        return shlex.split(configured, posix=os.name != "nt")
    return ["conda", "run", "-n", "pylabfea", "materialai-diagnostics"]


def _diagnostics(
    bridge: FakeMcpBridge,
    output_root: Path,
    product_root: Path,
    *,
    timeout_seconds: float = 2.0,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object], Path]:
    fake_commands = output_root.parent / "fake-abaqus"
    fake_commands.mkdir(parents=True, exist_ok=True)
    abaqus_bat = fake_commands / "abaqus.bat"
    smapython = fake_commands / "SMAPython.exe"
    abaqus_bat.touch()
    smapython.touch()
    completed = subprocess.run(
        [
            *_diagnostics_command(),
            "--abaqus-bat",
            str(abaqus_bat),
            "--smapython",
            str(smapython),
            "--workspace-root",
            str(product_root / "workspace"),
            "--output-root",
            str(output_root),
            "--host",
            bridge.host,
            "--port",
            str(bridge.port),
            "--timeout",
            str(timeout_seconds),
        ],
        cwd=product_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    documents = sorted(output_root.glob("*/diagnostics.json"))
    assert documents, completed.stdout + completed.stderr
    document = documents[-1]
    payload = json.loads(document.read_text(encoding="utf-8"))
    return completed, payload, document


def _check(payload: dict[str, object], key: str) -> dict[str, object]:
    checks = payload.get("checks") or []
    return next(item for item in checks if item.get("key") == key)


@pytest.mark.source_mock
def test_product_cli_reads_fake_mcp_live_context(
    tmp_path: Path,
    product_root: Path,
) -> None:
    with FakeMcpBridge() as bridge:
        completed, payload, document = _diagnostics(
            bridge,
            tmp_path / "normal",
            product_root,
        )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert payload["mcp_ready"] is True
    assert _check(payload, "mcp_bridge")["status"] == "pass"
    assert _check(payload, "live_context")["status"] == "pass"
    assert [request["method"] for request in bridge.requests] == [
        "ping",
        "execute",
        "execute",
    ]
    schema = (
        Path(__file__).resolve().parents[1] / "contracts" / "diagnostics.schema.json"
    )
    validate_document(document, schema)


@pytest.mark.source_mock
@pytest.mark.parametrize(
    ("mode", "error_fragment"),
    [
        ("mismatched_id", "mismatched response id"),
        ("invalid_json", "Expecting value"),
        ("error", "fake kernel error"),
    ],
)
def test_product_cli_degrades_cleanly_on_bad_mcp_responses(
    mode: str,
    error_fragment: str,
    tmp_path: Path,
    product_root: Path,
) -> None:
    with FakeMcpBridge(FakeMcpBehavior(mode=mode)) as bridge:
        completed, payload, _ = _diagnostics(
            bridge,
            tmp_path / mode,
            product_root,
        )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert payload["batch_ready"] is True
    assert payload["mcp_ready"] is False
    bridge_check = _check(payload, "mcp_bridge")
    assert bridge_check["status"] == "warn"
    assert error_fragment.lower() in str(bridge_check["evidence"]).lower()


@pytest.mark.source_mock
def test_product_cli_bounds_fake_mcp_timeout(
    tmp_path: Path,
    product_root: Path,
) -> None:
    with FakeMcpBridge(FakeMcpBehavior(mode="timeout")) as bridge:
        completed, payload, _ = _diagnostics(
            bridge,
            tmp_path / "timeout",
            product_root,
            timeout_seconds=0.2,
        )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert payload["batch_ready"] is True
    assert payload["mcp_ready"] is False
    assert _check(payload, "mcp_bridge")["status"] == "warn"
