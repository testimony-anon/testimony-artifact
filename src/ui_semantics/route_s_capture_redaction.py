"""Deterministic capture-boundary redaction for Route-S evidence.

This module is deliberately value-oblivious.  It classifies a field only by
its normalized key, replaces the complete value before any evidence writer can
see it, and never computes metadata from the removed value.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping


RULE_VERSION = "route-s-capture-redaction-v1"
SENTINEL_KEY = "$route_s_redacted"
_SENSITIVE = (
    ("authorization", "authorization"),
    ("setcookie", "cookie"),
    ("cookie", "cookie"),
    ("apikey", "credential"),
    ("credential", "credential"),
    ("jwt", "token"),
    ("password", "password"),
    ("secret", "secret"),
    ("session", "session"),
    ("token", "token"),
)


class CaptureRedactionError(RuntimeError):
    """The response cannot be sanitized without ambiguity."""


class SensitiveMaterialUnavailable(RuntimeError):
    """A frozen symbolic/projection dependency intersects a redacted field."""


def sanitize_capture(
    value: Any,
    *,
    sensitive_values: Iterable[str] = (),
    removed_strings: list[str] | None = None,
) -> tuple[Any, list[dict[str, str]]]:
    """Return a detached sanitized value and a value-free redaction manifest.

    ``removed_strings`` is an optional process-memory-only sink used by the
    successor's exact full-tree scan.  Its contents must never be serialized.
    """

    manifest: list[dict[str, str]] = []
    secrets = tuple(item for item in sensitive_values if isinstance(item, str) and item)
    sanitized = _sanitize(
        copy.deepcopy(value), (), manifest, secrets, removed_strings
    )
    manifest.sort(key=lambda row: (row["json_pointer"], row["category"]))
    return sanitized, manifest


def dependency_intersects_redactions(
    dependency_tokens: Iterable[str | int], manifest: Iterable[Mapping[str, str]]
) -> bool:
    wanted = tuple(dependency_tokens)
    for row in manifest:
        observed = tuple(_decode_pointer(str(row.get("json_pointer") or "")))
        if _is_prefix(wanted, observed) or _is_prefix(observed, wanted):
            return True
    return False


def reject_redacted_predicate_dependencies(
    predicate: Mapping[str, Any],
    sources: Mapping[str, Iterable[tuple[Mapping[str, Any], str]]],
    *,
    item_bindings: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Reject a dependency on sanitized material at its actual source path.

    Composite evaluation calls this for each required atomic check, binding
    ``item`` to the current response member.  Checking a complete composite
    here is suitable for dependency auditing, not three-valued evaluation:
    one unavailable member must not erase another member's counterexample.
    """

    for reference in predicate_value_refs(predicate, item_bindings=item_bindings):
        if reference["role"] == "item":
            raise ValueError("predicate_item_binding_missing")
        location = reference.get("location")
        required_channel = None
        if location is not None:
            required_channel = {
                "body": "request",
                "query": "request_query",
                "path": "request_path",
                "headers": "request_headers",
            }.get(str(location))
            if required_channel is None:
                raise ValueError("predicate_request_location_unsupported")
        for record, channel in sources.get(str(reference["role"]), ()):
            if required_channel is not None and channel != required_channel:
                continue
            rows = (record.get("redaction_manifest") or {}).get(channel) or []
            tokens = dotted_tokens(str(reference["path"]))
            if reference.get("field_presence_only") is True:
                # Sanitization preserves the exact key, but a replaced
                # ancestor conceals whether a nested target existed.
                intersects = any(
                    len(observed) < len(tokens) and _is_prefix(observed, tokens)
                    for row in rows
                    for observed in [tuple(_decode_pointer(str(row.get("json_pointer") or "")))]
                )
            elif reference.get("collection_structure_only") is True:
                intersects = _dependency_container_is_redacted(tokens, rows)
            else:
                intersects = dependency_intersects_redactions(tokens, rows)
            if intersects:
                raise SensitiveMaterialUnavailable("sensitive_material_unavailable")


def predicate_value_refs(
    value: Any,
    *,
    item_bindings: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[Mapping[str, Any]]:
    """Return semantic references, preserving location and member projection.

    A complete forall exposes wildcard member dependencies for audits.  Its
    atomic runtime checks instead receive an exact member binding.  Frozen
    hypothesis values are JSON data and are never traversed as references.
    """

    return [
        _bind_item_reference(reference, item_bindings or {})
        for reference in _predicate_value_refs(value)
    ]


def _predicate_value_refs(value: Any) -> list[Mapping[str, Any]]:
    family = value.get("family") if isinstance(value, Mapping) else None
    if family == "forall":
        collection = value.get("collection")
        if not isinstance(collection, Mapping):
            return []
        bindings = {
            "item": {
                "role": collection["role"],
                "path": f'{collection["path"]}[*]',
            }
        }
        refs = [{**dict(collection), "collection_structure_only": True}]
        for field in ("item_guard", "body"):
            refs.extend(predicate_value_refs(value.get(field), item_bindings=bindings))
        return refs
    if family == "P01" and isinstance(value.get("target"), Mapping) and value["target"].get("role") in {"observation", "item"}:
        return [{**dict(value["target"]), "field_presence_only": True}]
    if family == "P21":
        target = value.get("target")
        return [{**dict(target), "collection_structure_only": True}] if isinstance(target, Mapping) else []
    if family == "P11":
        target = value.get("collection") or value.get("target")
        reference = {**dict(target)} if isinstance(target, Mapping) else None
        if reference is not None and value.get("projection") != "length":
            reference["collection_structure_only"] = True
        return ([reference] if reference is not None else []) + predicate_value_refs(value.get("right"))
    if family == "P19":
        collection = value["collection"]
        refs = [{**dict(collection), "collection_structure_only": True}, value["output"]]
        bindings = {"item": {"role": collection["role"], "path": collection["path"] + "[*]"}}
        for key in ("item", "factor"):
            refs.extend(predicate_value_refs(value.get(key), item_bindings=bindings))
        return refs
    if family == "P13" and value.get("identity") is None:
        return [value["collection"], *predicate_value_refs(value.get("member"))]
    if family == "P15" and value.get("scope") == "actual_response":
        collection = value["collection"]
        return [{**dict(collection), "collection_structure_only": True}] + [
            {"role": collection["role"], "path": collection["path"] + "[*]" + ("" if path == "$" else path.removeprefix("$"))}
            for path in value["identity"]["paths"]
        ]
    if family == "P12":
        return [
            {
                **dict(value[field]),
                "collection_structure_only": True,
            }
            for field in ("before", "after")
            if isinstance(value.get(field), Mapping)
        ]
    if family in {"P01", "P13", "P14"}:
        collection_fields = {
            "P01": ("target",),
            "P13": ("collection",),
            "P14": ("before", "after"),
        }[family]
        identity = value.get("identity")
        pairs = identity.get("field_pairs") if isinstance(identity, Mapping) else None
        member = value.get("member")
        member_ref = member.get("ref") if isinstance(member, Mapping) else None
        if not isinstance(pairs, list) or not isinstance(member_ref, Mapping):
            # P01 also admits a scalar/boolean target with no member locator.
            # That form reads the target value itself and must retain the
            # ordinary dependency walk.
            if family == "P01":
                target = value.get("target")
                return [target] if isinstance(target, Mapping) else []
            return []
        refs: list[Mapping[str, Any]] = []
        for field in collection_fields:
            collection = value.get(field)
            if not isinstance(collection, Mapping):
                continue
            for pair in pairs:
                if not isinstance(pair, Mapping):
                    continue
                item_path = pair.get("collection_item_path")
                if not isinstance(item_path, str):
                    continue
                suffix = "" if item_path == "$" else item_path.removeprefix("$")
                refs.append({
                    "role": collection["role"],
                    "path": f'{collection["path"]}[*]{suffix}',
                })
        for pair in pairs:
            if not isinstance(pair, Mapping):
                continue
            member_path = pair.get("member_path")
            if not isinstance(member_path, str):
                continue
            suffix = "" if member_path == "$" else member_path.removeprefix("$")
            refs.append({
                "role": member_ref["role"],
                "path": f'{member_ref["path"]}{suffix}',
            })
        return refs
    if isinstance(value, Mapping) and value.get("family") in {"P16", "P17"}:
        identity = value.get("identity")
        paths = identity.get("paths") if isinstance(identity, Mapping) else None
        sides = ("before", "after") if family == "P16" else ("left", "right")
        if value.get("comparison_basis") == "full_json_value":
            return [value[side] for side in sides]
        if value.get("comparison_basis") == "frozen_projection":
            paths = value["projection"]
        if not isinstance(paths, list) or not all(
            isinstance(path, str) for path in paths
        ):
            return []
        refs: list[Mapping[str, Any]] = []
        for side in sides:
            collection = value.get(side)
            if not isinstance(collection, Mapping):
                continue
            role = collection.get("role")
            collection_path = collection.get("path")
            if not isinstance(role, str) or not isinstance(collection_path, str):
                continue
            for identity_path in [*paths, *([value["key"]] if family == "P16" and side == "after" else [])]:
                suffix = "" if identity_path == "$" else identity_path.removeprefix("$")
                refs.append({
                    "role": role,
                    "path": f"{collection_path}[*]{suffix}",
                })
        return refs
    refs: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if isinstance(value.get("source"), str) and value.get("source") in {"hypothesis", "transition_fact"}:
            return []
        if (
            value.get("source") == "collection_member"
            and isinstance(value.get("role"), str)
        ):
            suffix = "" if value["field_path"] == "$" else str(
                value["field_path"]
            ).removeprefix("$")
            refs.append({
                "role": value["role"],
                "path": f'{value["collection_path"]}[*]{suffix}',
            })
            refs.extend(predicate_value_refs(value.get("member")))
        elif isinstance(value.get("role"), str) and isinstance(value.get("path"), str):
            refs.append(value)
        else:
            for child in value.values():
                refs.extend(predicate_value_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(predicate_value_refs(child))
    return refs


def _bind_item_reference(
    reference: Mapping[str, Any],
    item_bindings: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    binding = item_bindings.get(str(reference.get("role") or ""))
    if binding is None:
        return reference
    path = str(reference["path"])
    suffix = "" if path == "$" else path.removeprefix("$")
    return {
        **dict(reference),
        "role": binding["role"],
        "path": f'{binding["path"]}{suffix}',
    }


def _dependency_container_is_redacted(
    dependency_tokens: tuple[str | int, ...],
    manifest: Iterable[Mapping[str, str]],
) -> bool:
    """A collection's length is sensitive only if the container is obscured.

    Redacted descendants do not affect cardinality.  A redaction at the exact
    collection path or at one of its ancestors still blocks evaluation.
    """

    for row in manifest:
        observed = tuple(_decode_pointer(str(row.get("json_pointer") or "")))
        if _is_prefix(observed, dependency_tokens):
            return True
    return False


def dotted_tokens(path: str) -> tuple[str | int, ...]:
    """Parse the frozen dotted/indexed path subset without evaluating a value."""

    tokens: list[str | int] = []
    root_indices = re.match(r"^\$((?:\[(?:\d+|\*)\])+)(?:\.|$)", path)
    if root_indices is not None:
        tokens.extend(
            value if value == "*" else int(value)
            for value in re.findall(r"\[(\d+|\*)\]", root_indices.group(1))
        )
        path = path[root_indices.end():]
    if path.startswith("$."):
        path = path[2:]
    if not path or path == "$":
        return tuple(tokens)
    for segment in path.split("."):
        match = re.fullmatch(r"([^\[\]]+)((?:\[(?:\d+|\*)\])*)", segment)
        if match is None or not match.group(1):
            raise CaptureRedactionError("unsupported_dependency_path")
        head = match.group(1)
        tokens.append(int(head) if head.isdigit() else head)
        tokens.extend(
            value if value == "*" else int(value)
            for value in re.findall(r"\[(\d+|\*)\]", match.group(2))
        )
    return tuple(tokens)


def typed_redaction_sentinel_attested(
    value: Any,
    *,
    typed_path: str,
    original_json_type: str,
    manifest: Iterable[Mapping[str, str]],
) -> bool:
    """Match one sanitized typed value to its exact capture manifest row."""

    if not isinstance(value, Mapping) or set(value) != {SENTINEL_KEY}:
        return False
    sentinel = value[SENTINEL_KEY]
    if not isinstance(sentinel, Mapping) or set(sentinel) != {
        "category",
        "original_json_type",
        "rule",
    }:
        return False
    category = sentinel.get("category")
    if (
        not isinstance(category, str)
        or not category
        or sentinel.get("original_json_type") != original_json_type
        or sentinel.get("rule") != RULE_VERSION
    ):
        return False
    try:
        tokens = () if typed_path == "$" else dotted_tokens(typed_path)
    except CaptureRedactionError:
        return False
    if "*" in tokens:
        return False
    pointer = _pointer(tokens)
    rows = [
        row
        for row in manifest
        if isinstance(row, Mapping) and row.get("json_pointer") == pointer
    ]
    if len(rows) != 1:
        return False
    return dict(rows[0]) == {
        "json_pointer": pointer,
        "category": category,
        "original_json_type": original_json_type,
        "rule": RULE_VERSION,
        "replacement_kind": "typed_sentinel",
    }


def _sanitize(
    value: Any,
    path: tuple[str | int, ...],
    manifest: list[dict[str, str]],
    sensitive_values: tuple[str, ...],
    removed_strings: list[str] | None,
) -> Any:
    if isinstance(value, dict):
        if SENTINEL_KEY in value:
            raise CaptureRedactionError("reserved_redaction_sentinel_in_input")
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            category = sensitive_field_category(key_text)
            child_path = (*path, key_text)
            if category is None:
                result[key_text] = _sanitize(
                    child, child_path, manifest, sensitive_values, removed_strings
                )
                continue
            _remember_strings(child, removed_strings)
            manifest.append(
                {
                    "json_pointer": _pointer(child_path),
                    "category": category,
                    "original_json_type": _json_type(child),
                    "rule": RULE_VERSION,
                    "replacement_kind": "typed_sentinel",
                }
            )
            result[key_text] = {
                SENTINEL_KEY: {
                    "category": category,
                    "original_json_type": _json_type(child),
                    "rule": RULE_VERSION,
                }
            }
        return result
    if isinstance(value, list):
        return [
            _sanitize(
                child,
                (*path, index),
                manifest,
                sensitive_values,
                removed_strings,
            )
            for index, child in enumerate(value)
        ]
    if isinstance(value, str) and any(secret in value for secret in sensitive_values):
        _remember_strings(value, removed_strings)
        manifest.append(
            {
                "json_pointer": _pointer(path),
                "category": "session",
                "original_json_type": "string",
                "rule": RULE_VERSION,
                "replacement_kind": "typed_sentinel",
            }
        )
        return {
            SENTINEL_KEY: {
                "category": "session",
                "original_json_type": "string",
                "rule": RULE_VERSION,
            }
        }
    return value


def _remember_strings(value: Any, sink: list[str] | None) -> None:
    """Keep removed strings in volatile memory for exact leak scans only."""

    if sink is None:
        return
    if isinstance(value, str):
        if value and value not in sink:
            sink.append(value)
        return
    if isinstance(value, dict):
        for child in value.values():
            _remember_strings(child, sink)
        return
    if isinstance(value, list):
        for child in value:
            _remember_strings(child, sink)


def sensitive_field_category(key: str) -> str | None:
    """Classify a sensitive field name using the shared capture rule."""

    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    for marker, category in _SENSITIVE:
        if marker in normalized:
            return category
    return None


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise CaptureRedactionError("non_json_capture_value")


def _pointer(path: tuple[str | int, ...]) -> str:
    return "".join("/" + str(item).replace("~", "~0").replace("/", "~1") for item in path)


def _decode_pointer(pointer: str) -> list[str | int]:
    if not pointer:
        return []
    if not pointer.startswith("/"):
        raise CaptureRedactionError("invalid_redaction_pointer")
    result: list[str | int] = []
    for item in pointer[1:].split("/"):
        decoded = item.replace("~1", "/").replace("~0", "~")
        # JSON Pointer does not encode whether a numeric component addressed an
        # object key or an array index.  Prefix comparison treats both textual
        # forms identically so neither representation can bypass intersection.
        result.append(int(decoded) if decoded.isdigit() else decoded)
    return result


def _is_prefix(left: tuple[Any, ...], right: tuple[Any, ...]) -> bool:
    return len(left) <= len(right) and all(
        expected == "*" or observed == "*" or expected == observed
        for expected, observed in zip(left, right)
    )


__all__ = [
    "CaptureRedactionError",
    "RULE_VERSION",
    "SENTINEL_KEY",
    "SensitiveMaterialUnavailable",
    "dependency_intersects_redactions",
    "typed_redaction_sentinel_attested",
    "dotted_tokens",
    "predicate_value_refs",
    "sanitize_capture",
    "sensitive_field_category",
]
