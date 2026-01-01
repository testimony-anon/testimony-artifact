"""Schema-driven structural projection for regression comparisons."""

from __future__ import annotations

import copy
from typing import Any

from common.contracts import load_schema


_MISSING = object()


def structural_projection(document: Any, schema_name: str) -> Any:
    """Keep only fields declared structural by the artifact contract."""
    root = load_schema(schema_name)
    projected = _project(document, root, root)
    return None if projected is _MISSING else projected


def _project(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> Any:
    if "$ref" in schema:
        target, target_root = _resolve_ref(schema["$ref"], root)
        return _project(value, target, target_root)
    if isinstance(value, dict):
        projected = {}
        properties = schema.get("properties", {})
        for key, child in properties.items():
            if key not in value:
                continue
            item = _project(value[key], child, root)
            if item is not _MISSING:
                projected[key] = item
        if projected:
            return projected
        if schema.get("x-volatility") == "structural":
            return copy.deepcopy(value)
        return _MISSING
    if isinstance(value, list):
        item_schema = schema.get("items", {})
        items = [_project(item, item_schema, root) for item in value]
        retained = [item for item in items if item is not _MISSING]
        if retained or (not value and schema.get("x-volatility") == "structural"):
            return retained
        return _MISSING
    if schema.get("x-volatility") == "structural":
        return copy.deepcopy(value)
    return _MISSING


def _resolve_ref(reference: str, root: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_name, _, fragment = reference.partition("#")
    target_root = load_schema(schema_name) if schema_name else root
    target: Any = target_root
    if fragment:
        for token in fragment.removeprefix("/").split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
    return target, target_root
