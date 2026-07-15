from __future__ import annotations

import json
from pathlib import Path

from materialai_qa.reporting import REQUIRED_SUITES, build_release_decision


def _write_junit(path: Path, failures: int = 0) -> None:
    path.write_text(
        f'<testsuite tests="1" failures="{failures}" errors="0" skipped="0" time="0.1">'
        '<testcase name="gate" time="0.1"/></testsuite>',
        encoding="utf-8",
    )


def test_release_decision_requires_live_mcp_and_all_suites(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    evidence = tmp_path / "evidence"
    reports.mkdir()
    evidence.mkdir()
    for filename in REQUIRED_SUITES.values():
        _write_junit(reports / filename)
    diagnostics = tmp_path / "diagnostics.json"
    diagnostics.write_text(
        json.dumps({"mcp_ready": True, "checks": []}),
        encoding="utf-8",
    )

    payload = build_release_decision(reports, evidence, diagnostics)

    assert payload["status"] == "pass"
    assert Path(payload["evidence_bundle"]).is_file()


def test_release_decision_is_blocked_by_failed_suite(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    evidence = tmp_path / "evidence"
    reports.mkdir()
    evidence.mkdir()
    for index, filename in enumerate(REQUIRED_SUITES.values()):
        _write_junit(reports / filename, failures=1 if index == 0 else 0)

    payload = build_release_decision(reports, evidence, None)

    assert payload["status"] == "blocked"
