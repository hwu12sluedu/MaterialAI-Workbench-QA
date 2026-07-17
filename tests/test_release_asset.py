from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from materialai_qa.release_asset import (
    ReleaseAuditError,
    audit_release,
    extract_release,
)


@pytest.mark.portable
def test_release_zip_hash_version_and_inventory(
    release_zip: Path,
    release_checksum: Path,
    expected_version: str,
) -> None:
    audit = audit_release(release_zip, release_checksum, expected_version)

    assert audit.checksum_matches is True
    assert audit.exe_version == expected_version
    assert audit.entry_count > 100
    assert audit.uncompressed_bytes < 700 * 1024 * 1024
    assert audit.forbidden_entries == ()
    assert audit.suspicious_entries == ()

    with zipfile.ZipFile(release_zip) as archive:
        entries = {name.replace("\\", "/") for name in archive.namelist()}
    assert (
        "MaterialAIWorkbench/_internal/webview/lib/" "Microsoft.Web.WebView2.Core.dll"
    ) in entries
    assert "MaterialAIWorkbench/README-START.txt" in entries


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../outside.txt", "unsafe")

    with pytest.raises(ReleaseAuditError, match="Unsafe ZIP entry"):
        extract_release(archive, tmp_path / "extract")


def test_forbidden_workspace_is_rejected_before_release(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("MaterialAIWorkbench/workspace/result.odb", b"odb")

    with pytest.raises(ReleaseAuditError, match="Forbidden release entry"):
        extract_release(archive, tmp_path / "extract")


def test_case_insensitive_duplicate_entry_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("MaterialAIWorkbench/readme.txt", "one")
        output.writestr("MaterialAIWorkbench/README.TXT", "two")

    with pytest.raises(ReleaseAuditError, match="Duplicate Windows ZIP entry"):
        extract_release(archive, tmp_path / "extract")
