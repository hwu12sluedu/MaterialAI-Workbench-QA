from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_fixture_registry_hashes_and_provenance() -> None:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    registry = json.loads((root / "fixture_registry.json").read_text(encoding="utf-8"))

    assert registry["schema_version"] == "1.0"
    assert registry["fixtures"]
    for item in registry["fixtures"]:
        path = root / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert item["source"]
        assert item["license"]
        assert item["customer_data"] is False
