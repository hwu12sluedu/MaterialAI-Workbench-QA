from __future__ import annotations

import sys
from pathlib import Path

import pytest

from materialai_qa.process_control import run_bounded, run_portable_smoke


def test_bounded_process_records_success(tmp_path: Path) -> None:
    result = run_bounded(
        [sys.executable, "-c", "print('qa-ok')"],
        cwd=tmp_path,
        log_path=tmp_path / "success.log",
        timeout_seconds=10,
    )

    assert result.returncode == 0
    assert result.timed_out is False
    assert "qa-ok" in (tmp_path / "success.log").read_text(encoding="utf-8")


def test_bounded_process_kills_timeout(tmp_path: Path) -> None:
    result = run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        log_path=tmp_path / "timeout.log",
        timeout_seconds=1,
    )

    assert result.timed_out is True
    assert result.returncode == -1


@pytest.mark.portable
def test_frozen_client_smoke_and_cleanup(
    extracted_executable: Path,
    tmp_path: Path,
) -> None:
    result = run_portable_smoke(extracted_executable, tmp_path / "smoke")

    assert result.returncode == 0
    assert result.backend_port is not None
    assert result.desktop_log is not None


@pytest.mark.portable
def test_frozen_client_preserves_existing_user_workspace(
    extracted_executable: Path,
    tmp_path: Path,
) -> None:
    sandbox = tmp_path / "upgrade"
    marker = (
        sandbox
        / "localappdata"
        / "MaterialAIWorkbench"
        / "workspace"
        / "user-case.keep"
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("keep", encoding="ascii")

    run_portable_smoke(extracted_executable, sandbox)

    assert marker.read_text(encoding="ascii") == "keep"
