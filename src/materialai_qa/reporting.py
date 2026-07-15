"""Release-decision aggregation without importing product source code."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

REQUIRED_SUITES = {
    "unit": "unit-junit.xml",
    "source_mock": "source-mock-junit.xml",
    "release_audit": "release-audit-junit.xml",
    "portable_lifecycle": "portable-lifecycle-junit.xml",
    "portable_boundaries": "portable-boundaries-junit.xml",
    "ui": "ui-junit.xml",
    "abaqus_real": "abaqus-real-junit.xml",
}
SECRET_PATTERN = re.compile(rb"sk-[A-Za-z0-9_-]{20,}")


@dataclass(frozen=True)
class SuiteResult:
    key: str
    path: str
    tests: int
    failures: int
    errors: int
    skipped: int
    time_seconds: float
    status: str


def parse_junit(path: Path | str, key: str) -> SuiteResult:
    report_path = Path(path).resolve()
    root = ElementTree.parse(report_path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(item.get("tests", "0")) for item in suites)
    failures = sum(int(item.get("failures", "0")) for item in suites)
    errors = sum(int(item.get("errors", "0")) for item in suites)
    skipped = sum(int(item.get("skipped", "0")) for item in suites)
    elapsed = sum(float(item.get("time", "0")) for item in suites)
    return SuiteResult(
        key=key,
        path=str(report_path),
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        time_seconds=elapsed,
        status="pass" if tests > 0 and failures == 0 and errors == 0 else "fail",
    )


def build_release_decision(
    reports_root: Path | str,
    evidence_root: Path | str,
    mcp_diagnostics: Path | str | None,
    *,
    output_prefix: str = "release_decision",
) -> dict[str, object]:
    reports = Path(reports_root).resolve()
    evidence = Path(evidence_root).resolve()
    reports.mkdir(parents=True, exist_ok=True)
    suites: list[SuiteResult] = []
    missing: list[str] = []
    for key, filename in REQUIRED_SUITES.items():
        path = reports / filename
        if not path.is_file():
            missing.append(key)
            continue
        suites.append(parse_junit(path, key))

    mcp_payload: dict[str, object] = {}
    mcp_status = "blocked"
    mcp_note = "No live Abaqus MCP diagnostics were supplied."
    diagnostics_path = Path(mcp_diagnostics).resolve() if mcp_diagnostics else None
    if diagnostics_path and diagnostics_path.is_file():
        mcp_payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        if mcp_payload.get("mcp_ready") is True:
            mcp_status = "pass"
            mcp_note = "Live Abaqus model and Job context is readable."
        else:
            checks = mcp_payload.get("checks") or []
            live = next(
                (item for item in checks if item.get("key") == "live_context"),
                {},
            )
            mcp_note = str(live.get("message") or "Live MCP context is not ready.")

    suite_pass = not missing and all(item.status == "pass" for item in suites)
    status = "pass" if suite_pass and mcp_status == "pass" else "blocked"
    payload: dict[str, object] = {
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "required_suites": list(REQUIRED_SUITES),
        "missing_suites": missing,
        "suites": [asdict(item) for item in suites],
        "mcp_live": {
            "status": mcp_status,
            "note": mcp_note,
            "diagnostics": str(diagnostics_path) if diagnostics_path else None,
        },
    }
    json_path = reports / f"{output_prefix}.json"
    markdown_path = reports / f"{output_prefix}.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    bundle_path = reports / f"{output_prefix}_evidence.zip"
    _bundle_evidence(
        bundle_path,
        reports,
        evidence,
        diagnostics_path,
        exclude={bundle_path},
    )
    payload["evidence_bundle"] = str(bundle_path)
    payload["evidence_bundle_sha256"] = hashlib.sha256(
        bundle_path.read_bytes()
    ).hexdigest()
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload


def _bundle_evidence(
    destination: Path,
    reports: Path,
    evidence: Path,
    diagnostics: Path | None,
    *,
    exclude: set[Path],
) -> None:
    candidates = [
        path
        for path in reports.iterdir()
        if path.is_file() and path.suffix.lower() in {".html", ".json", ".md", ".xml"}
    ]
    candidates.extend((evidence / "ui").glob("*.png"))
    candidates.extend(evidence.glob("*/gate_summary.json"))
    candidates.extend(evidence.glob("abaqus_real/*/gate_summary.json"))
    if diagnostics and diagnostics.is_file():
        candidates.append(diagnostics)

    seen: set[Path] = set()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in candidates:
            resolved = path.resolve()
            if resolved in exclude or resolved in seen or not resolved.is_file():
                continue
            payload = resolved.read_bytes()
            if SECRET_PATTERN.search(payload):
                raise RuntimeError(f"Evidence contains a possible API key: {resolved}")
            seen.add(resolved)
            if resolved.is_relative_to(reports):
                name = Path("reports") / resolved.relative_to(reports)
            elif resolved.is_relative_to(evidence):
                name = Path("evidence") / resolved.relative_to(evidence)
            else:
                name = Path("diagnostics") / resolved.name
            archive.writestr(name.as_posix(), payload)


def _markdown(payload: dict[str, object]) -> str:
    rows = []
    for suite in payload["suites"]:
        rows.append(
            "| {key} | {status} | {tests} | {failures} | {errors} | {skipped} |".format(
                **suite
            )
        )
    missing = ", ".join(payload["missing_suites"]) or "无"
    mcp = payload["mcp_live"]
    return "\n".join(
        [
            "# MaterialAI Workbench 发布判定",
            "",
            f"- 总体状态：`{payload['status']}`",
            f"- 缺失测试套件：{missing}",
            f"- 实时 Abaqus MCP：`{mcp['status']}` - {mcp['note']}",
            "",
            "| 套件 | 状态 | tests | failures | errors | skipped |",
            "|---|---:|---:|---:|---:|---:|",
            *rows,
            "",
            "只有全部自动化套件通过且实时 MCP 上下文可读取时，状态才为 `pass`。",
            "",
        ]
    )
