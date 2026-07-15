"""Public JSON contract validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def load_json(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return payload


def validate_document(document_path: Path | str, schema_path: Path | str) -> None:
    schema = load_json(schema_path)
    document = load_json(document_path)
    Draft202012Validator(schema).validate(document)
