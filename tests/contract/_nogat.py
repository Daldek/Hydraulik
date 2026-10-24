"""Access to the vendored Nogat schemas (``schemas/nogat``) for contract tests."""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas" / "nogat"
NAMES = ("result-1", "error-1", "commands-1")


def load(name: str) -> dict[str, Any]:
    """Return the vendored schema file ``<name>.schema.json``."""
    document: dict[str, Any] = json.loads(
        (SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    return document


def validator(name: str) -> Draft202012Validator:
    """Return a validator of ``<name>`` that resolves ``$ref`` between the schemas."""
    registry: Registry[Any] = Registry()
    for item in NAMES:
        schema = load(item)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(load(name), registry=registry)
