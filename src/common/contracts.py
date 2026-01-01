"""Contract schema loading and validation (contract rule: every artifact must pass its schema before being written and after being read by a consumer)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema.validators import validator_for
from referencing import Registry, Resource

from . import SCHEMA_VERSION, TOOL_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"


class ContractValidationError(Exception):
    """The artifact does not conform to its contract schema. A validation failure is a stage failure (contract rule)."""

    def __init__(self, schema_name: str, errors: list[Any]):
        self.schema_name = schema_name
        self.errors = errors
        details = "; ".join(
            f"{e.json_path}: {e.message}" for e in errors[:10]
        )
        super().__init__(f"contract validation failed [{schema_name}]: {details}")


def _retrieve(uri: str) -> Resource:
    path = CONTRACTS_DIR / uri.split("#")[0]
    return Resource.from_contents(json.loads(path.read_text()))


_REGISTRY = Registry(retrieve=_retrieve)


def load_schema(schema_name: str) -> dict:
    return json.loads((CONTRACTS_DIR / schema_name).read_text())


def validate_artifact(schema_name: str, instance: Any) -> None:
    """Validate one artifact instance against its contract schema; raise ContractValidationError if it is invalid."""
    schema = load_schema(schema_name)
    validator = validator_for(schema)(schema, registry=_REGISTRY)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.json_path)
    if errors:
        raise ContractValidationError(schema_name, errors)


def make_envelope(
    artifact_type: str,
    stage: str,
    run_id: str,
    upstream_refs: list[dict] | None = None,
    fixture_id: str | None = None,
) -> dict:
    """Build the D6 metadata envelope (carried in the same shape at the top level of every artifact)."""
    envelope = {
        "artifact_type": artifact_type,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "stage": stage,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "tool_version": TOOL_VERSION,
        "upstream_refs": upstream_refs or [],
    }
    if fixture_id is not None:
        envelope["fixture_id"] = fixture_id
    return envelope
