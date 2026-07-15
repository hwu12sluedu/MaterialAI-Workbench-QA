from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from materialai_qa.contracts import validate_document


@pytest.mark.abaqus_real
def test_real_abaqus_diagnostics_and_plate_hole_gate(
    product_root: Path,
) -> None:
    if os.environ.get("MATERIALAI_QA_RUN_ABAQUS_REAL") != "1":
        pytest.skip("Real Abaqus gate requires MATERIALAI_QA_RUN_ABAQUS_REAL=1.")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    evidence_base = Path(
        os.environ.get(
            "MATERIALAI_QA_EVIDENCE_ROOT",
            Path.cwd() / "evidence" / "abaqus_real",
        )
    ).resolve()
    output_root = evidence_base / run_id / "acceptance"
    output_root.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "conda",
            "run",
            "-n",
            "pylabfea",
            "materialai-plate-hole",
            "--name",
            f"qa_{run_id.lower()}",
            "--output-root",
            str(output_root),
            "--backend",
            "batch",
            "--execute",
            "--submit-job",
            "--archive-case",
            "--mesh-size",
            "4.0",
            "--cpus",
            "2",
            "--timeout",
            "3600",
        ],
        cwd=product_root,
        capture_output=True,
        text=True,
        timeout=4200,
        check=False,
    )
    (output_root.parent / "command_stdout.log").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (output_root.parent / "command_stderr.log").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    manifests = sorted(output_root.glob("*/acceptance_manifest.json"))
    assert len(manifests) == 1
    manifest_path = manifests[0]
    schema = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "acceptance_manifest.schema.json"
    )
    validate_document(manifest_path, schema)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "archived"
    for stage in (
        "prepare",
        "diagnostics",
        "build",
        "solve",
        "postprocess",
        "engineering_validation",
        "archive",
    ):
        assert payload["stages"][stage]["status"] == "pass"

    for artifact in ("cae", "inp", "odb", "sta", "result_json", "feature_csv"):
        path = Path(payload["artifacts"][artifact])
        assert path.is_file(), f"Missing {artifact}: {path}"
        assert path.stat().st_size > 0

    results = payload["results"]
    assert 0.315 <= float(results["max_displacement_mm"]) <= 0.438
    assert float(results["reaction_force_n"]) > 1.0
    assert 0.5 <= float(results["stress_concentration_ratio"]) <= 8.0

    compact_summary = {
        "status": "pass",
        "run_id": run_id,
        "manifest": str(manifest_path),
        "abaqus_status": payload["status"],
        "case_id": payload.get("case_id"),
        "results": results,
    }
    reports = Path.cwd() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{run_id}_abaqus_real.json").write_text(
        json.dumps(compact_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
