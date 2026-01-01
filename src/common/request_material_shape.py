"""Cross-member closure for typed request-material shape descriptors."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from common.contracts import ContractValidationError, validate_artifact


_REDACTION_MARKER = re.compile(r"\[REDACTED(?::[^\]\r\n]+)?\]")
_SOURCE_ORDER = {
    "explicit_registered_secret": 0,
    "authorization": 1,
    "cookie": 2,
    "jwt": 3,
    "sensitive_key": 4,
}
_MATCH_ORDER = {
    "not_applicable": 0,
    "exact_token": 0,
    "separator_delimited_token": 1,
    "substring_only": 2,
}


class RequestMaterialShapeError(ValueError):
    """Descriptor/HAR closure is invalid without exposing request material."""


def load_request_material_shapes(
    bundle_dir: Path,
    manifest: dict[str, Any],
    entries: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Load and close the optional descriptor member against redacted HAR bytes."""

    member = manifest["members"].get("request_material_shapes")
    default_path = bundle_dir / "request_material_shapes.jsonl"
    if member is None:
        if default_path.exists():
            raise RequestMaterialShapeError(
                "request-material descriptor exists but is not indexed by manifest"
            )
        return {}

    path = bundle_dir / member
    if not path.is_file():
        raise RequestMaterialShapeError("request-material descriptor member is missing")

    descriptors: dict[int, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            descriptor = json.loads(line)
            validate_artifact(
                "session_bundle_request_material_shape.schema.json", descriptor
            )
        except (json.JSONDecodeError, ContractValidationError, TypeError):
            raise RequestMaterialShapeError(
                f"request-material descriptor line {line_number} is invalid"
            ) from None
        entry_index = descriptor["entry_index"]
        if entry_index in descriptors:
            raise RequestMaterialShapeError("request-material entry index is duplicated")
        if entry_index >= len(entries):
            raise RequestMaterialShapeError("request-material entry index is out of range")
        _validate_descriptor(descriptor, entries[entry_index])
        descriptors[entry_index] = descriptor

    described_indexes = set(descriptors)
    redacted_indexes = {
        index
        for index, entry in enumerate(entries)
        if _structured_redacted_paths(entry["request"])
    }
    if described_indexes != redacted_indexes:
        raise RequestMaterialShapeError(
            "request-material descriptors do not close over structured redactions"
        )
    return descriptors


def _validate_descriptor(descriptor: dict[str, Any], entry: dict[str, Any]) -> None:
    request = entry["request"]
    post = request.get("postData") or {}
    text = post.get("text")
    mime = str(post.get("mimeType") or "")
    if request.get("method") != descriptor["method"] or mime != descriptor["mime_type"]:
        raise RequestMaterialShapeError("request-material method or MIME does not match HAR")
    if "json" not in mime.lower() or not isinstance(text, str):
        raise RequestMaterialShapeError("request-material entry is not a JSON request")
    try:
        body = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise RequestMaterialShapeError("request-material JSON body is not parseable") from None
    root_kind = "object" if isinstance(body, dict) else "array" if isinstance(body, list) else None
    if root_kind is None or descriptor["root_kind"] != root_kind:
        raise RequestMaterialShapeError("request-material JSON root kind does not match")
    encoded = text.encode()
    if descriptor["redacted_body_bytes"] != len(encoded):
        raise RequestMaterialShapeError("request-material body byte count does not match")
    if descriptor["redacted_body_sha256"] != hashlib.sha256(encoded).hexdigest():
        raise RequestMaterialShapeError("request-material body hash does not match")

    redacted_paths = _redacted_scalar_paths(body)
    descriptor_paths: set[tuple[tuple[str, Any], ...]] = set()
    for node in descriptor["redactions"]:
        path = _path_key(node["path"])
        if path in descriptor_paths:
            raise RequestMaterialShapeError("request-material typed path is duplicated")
        descriptor_paths.add(path)
        scalar = _resolve_path(body, node["path"])
        markers = _ordered_unique(_REDACTION_MARKER.findall(scalar) if isinstance(scalar, str) else [])
        if not markers:
            raise RequestMaterialShapeError(
                "request-material typed path does not point to a redacted scalar"
            )
        expected_form = "whole_scalar" if len(markers) == 1 and scalar == markers[0] else "string_substitution"
        if node["redaction_form"] != expected_form:
            raise RequestMaterialShapeError("request-material redaction form does not match")
        if node["original_scalar_type"] != "string" and expected_form != "whole_scalar":
            raise RequestMaterialShapeError(
                "non-string request material cannot use string substitution"
            )
        placeholders = node["placeholders"]
        if len(placeholders) != len(markers):
            raise RequestMaterialShapeError("request-material placeholder count does not match")
        actual_hashes = [placeholder["placeholder_sha256"] for placeholder in placeholders]
        expected_hashes = {hashlib.sha256(marker.encode()).hexdigest() for marker in markers}
        if len(set(actual_hashes)) != len(actual_hashes) or set(actual_hashes) != expected_hashes:
            raise RequestMaterialShapeError("request-material placeholder hashes do not close")
        for placeholder in placeholders:
            _validate_basis_order(placeholder["classification_bases"])
    if descriptor_paths != redacted_paths:
        raise RequestMaterialShapeError(
            "request-material typed paths do not close over redacted scalars"
        )


def _structured_redacted_paths(request: dict[str, Any]) -> set[tuple[tuple[str, Any], ...]]:
    post = request.get("postData") or {}
    mime = str(post.get("mimeType") or "")
    text = post.get("text")
    if "json" not in mime.lower() or not isinstance(text, str) or not text:
        return set()
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return set()
    if not isinstance(body, (dict, list)):
        return set()
    return _redacted_scalar_paths(body)


def _redacted_scalar_paths(value: Any) -> set[tuple[tuple[str, Any], ...]]:
    paths: set[tuple[tuple[str, Any], ...]] = set()

    def visit(current: Any, path: tuple[tuple[str, Any], ...]) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                visit(child, (*path, ("object_key", key)))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                visit(child, (*path, ("array_index", index)))
        elif isinstance(current, str) and _REDACTION_MARKER.search(current):
            paths.add(path)

    visit(value, ())
    return paths


def _path_key(path: list[dict[str, Any]]) -> tuple[tuple[str, Any], ...]:
    return tuple(
        (segment["kind"], segment.get("key", segment.get("index")))
        for segment in path
    )


def _resolve_path(value: Any, path: list[dict[str, Any]]) -> Any:
    current = value
    for segment in path:
        if segment["kind"] == "object_key":
            key = segment["key"]
            if not isinstance(current, dict) or key not in current:
                raise RequestMaterialShapeError("request-material typed path is unresolved")
            current = current[key]
        else:
            index = segment["index"]
            if not isinstance(current, list) or index >= len(current):
                raise RequestMaterialShapeError("request-material typed path is unresolved")
            current = current[index]
    return current


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _validate_basis_order(bases: list[dict[str, str]]) -> None:
    keys = [
        (_SOURCE_ORDER[item["source_class"]], _MATCH_ORDER[item["sensitive_key_match"]])
        for item in bases
    ]
    if len({(item["source_class"], item["sensitive_key_match"]) for item in bases}) != len(bases):
        raise RequestMaterialShapeError("request-material classification basis is duplicated")
    if keys != sorted(keys):
        raise RequestMaterialShapeError("request-material classification bases are out of order")
