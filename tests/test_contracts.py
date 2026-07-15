from __future__ import annotations

from pathlib import Path

import pytest

from materialai_qa.contracts import validate_document


def _latest(root: Path, pattern: str) -> Path:
    matches = sorted(
        root.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True
    )
    if not matches:
        pytest.skip(f"No contract document matches {pattern}")
    return matches[0]


def test_latest_diagnostics_matches_pinned_contract(product_root: Path) -> None:
    document = _latest(product_root / "workspace" / "diagnostics", "*/diagnostics.json")
    schema = (
        Path(__file__).resolve().parents[1] / "contracts" / "diagnostics.schema.json"
    )

    validate_document(document, schema)


def test_latest_acceptance_manifest_matches_pinned_contract(product_root: Path) -> None:
    document = _latest(
        product_root / "workspace" / "acceptance_runs", "*/acceptance_manifest.json"
    )
    schema = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "acceptance_manifest.schema.json"
    )

    validate_document(document, schema)
