from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from materialai_qa.process_control import run_bounded, run_portable_smoke
from materialai_qa.release_asset import extract_release


@pytest.mark.portable
def test_frozen_client_runs_from_chinese_and_space_path(
    release_zip: Path,
    tmp_path: Path,
) -> None:
    executable = extract_release(release_zip, tmp_path / "中文 客户端")

    result = run_portable_smoke(executable, tmp_path / "中文 用户数据")

    assert result.returncode == 0


@pytest.mark.portable
def test_frozen_client_core_smoke_does_not_require_external_network(
    extracted_executable: Path,
    tmp_path: Path,
) -> None:
    result = run_portable_smoke(
        extracted_executable,
        tmp_path / "offline",
        environment_overrides={
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
        },
    )

    assert result.returncode == 0


@pytest.mark.portable
def test_frozen_client_reports_occupied_port_without_hanging(
    extracted_executable: Path,
    tmp_path: Path,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = int(occupied.getsockname()[1])
        sandbox = tmp_path / "occupied-port"
        local_app_data = sandbox / "localappdata"
        temp_dir = sandbox / "temp"
        local_app_data.mkdir(parents=True)
        temp_dir.mkdir(parents=True)
        environment = os.environ.copy()
        environment.update(
            {
                "LOCALAPPDATA": str(local_app_data),
                "TEMP": str(temp_dir),
                "TMP": str(temp_dir),
            }
        )
        result = run_bounded(
            [
                str(extracted_executable),
                "--smoke-test",
                "--port",
                str(port),
                "--startup-timeout",
                "10",
            ],
            cwd=extracted_executable.parent,
            log_path=sandbox / "process.log",
            timeout_seconds=30,
            env=environment,
        )

    desktop_log = local_app_data / "MaterialAIWorkbench" / "logs" / "desktop.log"
    content = desktop_log.read_text(encoding="utf-8", errors="replace")
    assert result.timed_out is False
    assert result.returncode == 1
    assert f"端口 {port} 已被占用" in content
