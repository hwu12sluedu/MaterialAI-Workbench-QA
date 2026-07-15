from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

from materialai_qa.process_control import terminate_process_tree
from materialai_qa.release_asset import extract_release


@pytest.fixture(scope="session")
def product_root() -> Path:
    configured = os.environ.get("MATERIALAI_QA_PRODUCT_ROOT")
    return Path(
        configured or Path(__file__).resolve().parents[2] / "pyLabFEA"
    ).resolve()


@pytest.fixture(scope="session")
def expected_version() -> str:
    return os.environ.get("MATERIALAI_QA_EXPECTED_VERSION", "0.3.0.dev0")


@pytest.fixture(scope="session")
def release_zip(product_root: Path, expected_version: str) -> Path:
    path = (
        product_root
        / "dist"
        / f"MaterialAI-Workbench-Windows-x64-v{expected_version}.zip"
    )
    if not path.is_file():
        pytest.skip(f"Portable release ZIP is unavailable: {path}")
    return path


@pytest.fixture(scope="session")
def release_checksum(release_zip: Path) -> Path:
    path = Path(str(release_zip) + ".sha256")
    if not path.is_file():
        pytest.fail(f"Release checksum is unavailable: {path}")
    return path


@pytest.fixture(scope="session")
def extracted_executable(
    release_zip: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    root = tmp_path_factory.mktemp("portable-release")
    return extract_release(release_zip, root)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="session")
def frozen_app_url(
    extracted_executable: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> str:
    root = tmp_path_factory.mktemp("frozen-ui")
    local_app_data = root / "localappdata"
    temp_dir = root / "temp"
    local_app_data.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "LOCALAPPDATA": str(local_app_data),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
        }
    )
    log_path = root / "frozen_ui_server.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(extracted_executable), "--serve", "--port", str(port)],
            cwd=extracted_executable.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
        )
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Frozen UI server exited with code {process.returncode}; "
                        f"see {log_path}"
                    )
                try:
                    response = requests.get(url, timeout=1)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError(f"Frozen UI server did not become ready: {log_path}")
            yield url
        finally:
            terminate_process_tree(process.pid)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        assert probe.connect_ex(("127.0.0.1", port)) != 0
