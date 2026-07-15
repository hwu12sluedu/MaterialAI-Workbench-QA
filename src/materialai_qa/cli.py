"""Command-line entry point for reproducible release gates."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from materialai_qa.contracts import validate_document
from materialai_qa.process_control import run_portable_smoke
from materialai_qa.reporting import build_release_decision
from materialai_qa.release_asset import audit_release, extract_release


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _release_paths(product_root: Path, version: str) -> tuple[Path, Path]:
    archive = product_root / "dist" / f"MaterialAI-Workbench-Windows-x64-v{version}.zip"
    return archive, Path(str(archive) + ".sha256")


def _product_commit(product_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=product_root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MaterialAI Workbench black-box QA")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit-release")
    audit.add_argument("--zip", required=True, type=Path)
    audit.add_argument("--checksum", required=True, type=Path)
    audit.add_argument("--expected-version", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--document", required=True, type=Path)
    validate.add_argument("--schema", required=True, type=Path)

    gate = subparsers.add_parser("gate")
    gate.add_argument("--product-root", required=True, type=Path)
    gate.add_argument("--expected-version", required=True)
    gate.add_argument("--reports", type=Path, default=Path("reports"))
    gate.add_argument("--evidence", type=Path, default=Path("evidence"))
    gate.add_argument("--timeout", type=float, default=240.0)

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--reports", type=Path, default=Path("reports"))
    summarize.add_argument("--evidence", type=Path, default=Path("evidence"))
    summarize.add_argument("--mcp-diagnostics", type=Path)
    summarize.add_argument("--output-prefix", default="release_decision")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "audit-release":
            payload = audit_release(
                args.zip, args.checksum, args.expected_version
            ).to_dict()
        elif args.command == "validate":
            validate_document(args.document, args.schema)
            payload = {"status": "pass", "document": str(args.document)}
        elif args.command == "gate":
            product_root = args.product_root.resolve()
            archive, checksum = _release_paths(product_root, args.expected_version)
            release = audit_release(archive, checksum, args.expected_version)
            run_id = (
                datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                + "-"
                + uuid.uuid4().hex[:8]
            )
            run_evidence = args.evidence.resolve() / run_id
            extraction = run_evidence / "portable"
            executable = extract_release(archive, extraction)
            smoke = run_portable_smoke(
                executable,
                run_evidence / "portable-smoke",
                timeout_seconds=args.timeout,
            )
            payload = {
                "status": "pass",
                "run_id": run_id,
                "generated_at": datetime.now(UTC).isoformat(),
                "host": platform.node(),
                "python": platform.python_version(),
                "product_root": str(product_root),
                "product_commit": _product_commit(product_root),
                "release": release.to_dict(),
                "smoke": smoke.to_dict(),
            }
            _write_json(args.reports.resolve() / f"{run_id}_gate_summary.json", payload)
            _write_json(run_evidence / "gate_summary.json", payload)
        else:
            payload = build_release_decision(
                args.reports,
                args.evidence,
                args.mcp_diagnostics,
                output_prefix=args.output_prefix,
            )
    except Exception as exc:
        payload = {"status": "fail", "error": str(exc)}
        print(json.dumps(payload, indent=2, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("status") != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
