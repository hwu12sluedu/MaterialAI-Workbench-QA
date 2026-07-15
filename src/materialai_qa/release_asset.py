"""Release ZIP integrity, version and content auditing."""

from __future__ import annotations

import hashlib
import re
import stat
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

import pefile

FORBIDDEN_SEGMENTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "build",
    "tests",
    "workspace",
}
FORBIDDEN_SUFFIXES = {".cae", ".env", ".odb", ".pyo", ".pyc", ".sim"}
SECRET_PATTERN = re.compile(rb"sk-[A-Za-z0-9_-]{20,}")
TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


class ReleaseAuditError(RuntimeError):
    """Raised when a release artifact violates a P0 gate."""


@dataclass(frozen=True)
class ReleaseAudit:
    zip_path: str
    sha256: str
    checksum_matches: bool
    expected_version: str
    exe_version: str
    entry_count: int
    compressed_bytes: int
    uncompressed_bytes: int
    forbidden_entries: tuple[str, ...]
    suspicious_entries: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_from_file(path: Path | str) -> str:
    content = Path(path).read_text(encoding="ascii", errors="strict").strip()
    token = content.split()[0].lower() if content else ""
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ReleaseAuditError(f"Invalid SHA256 file: {path}")
    return token


def _safe_entry_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or (path.parts and ":" in path.parts[0])
    ):
        raise ReleaseAuditError(f"Unsafe ZIP entry: {name}")
    return path


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _is_forbidden(path: PurePosixPath) -> bool:
    lower_parts = {part.lower() for part in path.parts}
    return bool(
        lower_parts & FORBIDDEN_SEGMENTS
        or path.suffix.lower() in FORBIDDEN_SUFFIXES
        or path.name.lower() == ".env"
    )


def _pe_product_version(executable: Path) -> str:
    image = pefile.PE(str(executable), fast_load=False)
    try:
        for group in getattr(image, "FileInfo", []) or []:
            for item in group:
                if getattr(item, "Key", b"") != b"StringFileInfo":
                    continue
                for table in getattr(item, "StringTable", []) or []:
                    for raw_key, raw_value in table.entries.items():
                        key = raw_key.decode("utf-8", errors="replace")
                        if key == "ProductVersion":
                            return raw_value.decode("utf-8", errors="replace").strip()
    finally:
        image.close()
    raise ReleaseAuditError(f"ProductVersion is missing from {executable}")


def audit_release(
    zip_path: Path | str,
    checksum_path: Path | str,
    expected_version: str,
    *,
    max_uncompressed_bytes: int = 700 * 1024 * 1024,
) -> ReleaseAudit:
    archive_path = Path(zip_path).resolve()
    checksum = sha256_file(archive_path)
    expected_checksum = checksum_from_file(checksum_path)
    if checksum != expected_checksum:
        raise ReleaseAuditError("Release ZIP SHA256 does not match its checksum file.")

    forbidden: list[str] = []
    suspicious: list[str] = []
    executable_entries: list[zipfile.ZipInfo] = []
    uncompressed = 0
    entry_count = 0
    with zipfile.ZipFile(archive_path) as archive:
        normalized_entries: set[str] = set()
        for info in archive.infolist():
            path = _safe_entry_name(info.filename)
            if _is_symlink(info):
                raise ReleaseAuditError(
                    f"Symlinks are not allowed in the Windows ZIP: {info.filename}"
                )
            normalized = str(path).casefold()
            if normalized in normalized_entries:
                raise ReleaseAuditError(f"Duplicate Windows ZIP entry: {info.filename}")
            normalized_entries.add(normalized)
            entry_count += 1
            uncompressed += int(info.file_size)
            suffix = path.suffix.lower()
            if _is_forbidden(path):
                forbidden.append(info.filename)
            if path.name.lower() == "materialaiworkbench.exe":
                executable_entries.append(info)
            if suffix in TEXT_SUFFIXES and 0 < info.file_size <= 2 * 1024 * 1024:
                payload = archive.read(info)
                if SECRET_PATTERN.search(payload):
                    suspicious.append(info.filename)

        if uncompressed > max_uncompressed_bytes:
            raise ReleaseAuditError(
                f"Uncompressed release is too large: {uncompressed / 1024 / 1024:.1f} MB"
            )
        if forbidden:
            raise ReleaseAuditError(f"Forbidden release entries: {forbidden[:10]}")
        if suspicious:
            raise ReleaseAuditError(
                f"Possible API keys in release entries: {suspicious[:10]}"
            )
        if len(executable_entries) != 1:
            raise ReleaseAuditError(
                "Release ZIP must contain exactly one MaterialAIWorkbench.exe."
            )

        with tempfile.TemporaryDirectory(prefix="materialai-version-") as temp_dir:
            executable = Path(temp_dir) / "MaterialAIWorkbench.exe"
            executable.write_bytes(archive.read(executable_entries[0]))
            exe_version = _pe_product_version(executable)

    if exe_version != expected_version:
        raise ReleaseAuditError(
            f"Executable version mismatch: expected {expected_version}, found {exe_version}."
        )
    if expected_version not in archive_path.name:
        raise ReleaseAuditError(
            "Release ZIP filename does not contain the expected version."
        )

    return ReleaseAudit(
        zip_path=str(archive_path),
        sha256=checksum,
        checksum_matches=True,
        expected_version=expected_version,
        exe_version=exe_version,
        entry_count=entry_count,
        compressed_bytes=archive_path.stat().st_size,
        uncompressed_bytes=uncompressed,
        forbidden_entries=tuple(forbidden),
        suspicious_entries=tuple(suspicious),
    )


def extract_release(zip_path: Path | str, destination: Path | str) -> Path:
    target = Path(destination).resolve()
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(Path(zip_path).resolve()) as archive:
        normalized_entries: set[str] = set()
        for info in archive.infolist():
            path = _safe_entry_name(info.filename)
            if _is_symlink(info):
                raise ReleaseAuditError(f"Symlink is not allowed: {info.filename}")
            if _is_forbidden(path):
                raise ReleaseAuditError(f"Forbidden release entry: {info.filename}")
            normalized = str(path).casefold()
            if normalized in normalized_entries:
                raise ReleaseAuditError(f"Duplicate Windows ZIP entry: {info.filename}")
            normalized_entries.add(normalized)
        archive.extractall(target)
    matches = list(target.rglob("MaterialAIWorkbench.exe"))
    if len(matches) != 1:
        raise ReleaseAuditError(
            "Extracted release does not contain exactly one executable."
        )
    return matches[0]
