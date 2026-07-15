"""Bounded process execution and frozen-client lifecycle assertions."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import psutil


class ProcessGateError(RuntimeError):
    """Raised when a process violates timeout or cleanup gates."""


@dataclass(frozen=True)
class ProcessResult:
    command: tuple[str, ...]
    returncode: int
    duration_seconds: float
    timed_out: bool
    log_path: str
    desktop_log: str | None = None
    backend_port: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def terminate_process_tree(pid: int, *, timeout_seconds: float = 8.0) -> None:
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    processes = parent.children(recursive=True) + [parent]
    for process in processes:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=timeout_seconds)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=3)


def run_bounded(
    command: Sequence[str],
    *,
    cwd: Path | str,
    log_path: Path | str,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    output_path = Path(log_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with output_path.open("wb") as output:
        process = subprocess.Popen(
            [str(item) for item in command],
            cwd=str(Path(cwd).resolve()),
            env=dict(env or os.environ),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
        )
        try:
            returncode = process.wait(timeout=max(1.0, float(timeout_seconds)))
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_process_tree(process.pid)
            returncode = -1
    return ProcessResult(
        command=tuple(str(item) for item in command),
        returncode=int(returncode),
        duration_seconds=time.monotonic() - started,
        timed_out=timed_out,
        log_path=str(output_path),
    )


def _processes_for_executable(executable: Path) -> list[int]:
    target = os.path.normcase(str(executable.resolve()))
    matches: list[int] = []
    for process in psutil.process_iter(["pid", "exe"]):
        try:
            value = process.info.get("exe")
            if value and os.path.normcase(str(Path(value).resolve())) == target:
                matches.append(int(process.info["pid"]))
        except (OSError, psutil.Error):
            continue
    return matches


def _port_is_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", int(port))) != 0


def _wait_for_cleanup(executable: Path, before: set[int], port: int | None) -> set[int]:
    deadline = time.monotonic() + 8.0
    residual: set[int] = set()
    while time.monotonic() < deadline:
        residual = set(_processes_for_executable(executable)) - before
        port_closed = port is None or _port_is_closed(port)
        if not residual and port_closed:
            return set()
        time.sleep(0.25)
    return residual


def run_portable_smoke(
    executable: Path | str,
    sandbox_root: Path | str,
    *,
    timeout_seconds: float = 240.0,
    environment_overrides: Mapping[str, str] | None = None,
) -> ProcessResult:
    exe = Path(executable).resolve()
    root = Path(sandbox_root).resolve()
    local_app_data = root / "localappdata"
    temp_dir = root / "temp"
    local_app_data.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    log_path = root / "frozen_process.log"
    environment = os.environ.copy()
    environment.update(
        {
            "LOCALAPPDATA": str(local_app_data),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
        }
    )
    environment.update(dict(environment_overrides or {}))
    before = set(_processes_for_executable(exe))
    result = run_bounded(
        [str(exe), "--smoke-test", "--startup-timeout", "180"],
        cwd=exe.parent,
        log_path=log_path,
        timeout_seconds=timeout_seconds,
        env=environment,
    )
    desktop_log = local_app_data / "MaterialAIWorkbench" / "logs" / "desktop.log"
    content = (
        desktop_log.read_text(encoding="utf-8", errors="replace")
        if desktop_log.is_file()
        else ""
    )
    match = re.findall(r"Backend is healthy at http://127\.0\.0\.1:(\d+)", content)
    backend_port = int(match[-1]) if match else None
    if result.timed_out:
        raise ProcessGateError(
            f"Frozen client timed out after {timeout_seconds:g} seconds."
        )
    if result.returncode != 0:
        raise ProcessGateError(f"Frozen client exited with code {result.returncode}.")
    if "Desktop smoke test passed" not in content:
        raise ProcessGateError(
            "Desktop log does not contain the smoke-test success marker."
        )
    residual = _wait_for_cleanup(exe, before, backend_port)
    if residual:
        for pid in residual:
            terminate_process_tree(pid)
        raise ProcessGateError(
            f"Frozen client left residual processes: {sorted(residual)}"
        )
    if backend_port is None or not _port_is_closed(backend_port):
        raise ProcessGateError(
            "Frozen client backend port was not released after exit."
        )
    return ProcessResult(
        command=result.command,
        returncode=result.returncode,
        duration_seconds=result.duration_seconds,
        timed_out=False,
        log_path=result.log_path,
        desktop_log=str(desktop_log),
        backend_port=backend_port,
    )
