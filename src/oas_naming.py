"""Shared OpenAPI naming helpers."""

from __future__ import annotations

import re

_VALID_OPERATION_METHODS = {
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "trace",
}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_UNDERSCORES = re.compile(r"_+")


def operation_id(method: str, path: str) -> str:
    """Return a schema-safe deterministic operationId for an HTTP method/path."""
    method_part = str(method or "").lower()
    if method_part not in _VALID_OPERATION_METHODS:
        method_part = _sanitize_part(method_part) or "get"
    parts = [_sanitize_part(segment.strip("{}")) for segment in str(path or "").split("/")]
    suffix = "_".join(part for part in parts if part) or "root"
    return f"{method_part}_{suffix}"


def path_parameter_name(raw: str | None, fallback: str = "var1") -> str:
    """Return an OpenAPI-safe path parameter name."""
    name = _sanitize_part(str(raw or ""))
    return name or fallback


def _sanitize_part(value: str) -> str:
    lowered = str(value or "").lower()
    replaced = _NON_ALNUM.sub("_", lowered)
    collapsed = _UNDERSCORES.sub("_", replaced)
    return collapsed.strip("_")
