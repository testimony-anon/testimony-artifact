"""Binding value path extraction/insertion (Stage 6 replay: resolving the from_field/to_field of a binding).

Supports the JSONPath subset that occurs in Stage 4/5 artifacts: $.a, $.a.b, $.a[0], $.a[0].b.
- extract_value: read the value at from_field from the producer response body (in the style of apicarver extract_value_from_sample_or_response).
- set_body_value: write the value into the to_field position of the consumer request body (creating intermediate objects level by level when needed).
Purely deterministic, no network.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(\[(\d+)\])?")


def _parse(path: str) -> list:
    """'$.articles[0].slug' -> ['articles', 0, 'slug']; '$.tags[0]' -> ['tags', 0]."""
    p = path.strip()
    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:]
    out: list = []
    for seg in p.split("."):
        if not seg:
            continue
        m = _TOKEN.fullmatch(seg)
        if not m:
            raise ValueError(f"cannot parse path segment: {seg!r} (from {path!r})")
        out.append(m.group(1))
        if m.group(3) is not None:
            out.append(int(m.group(3)))
    return out


def extract_value(body: Any, from_field: str) -> Any | None:
    """Read the value at from_field from the response body; any missing level / type mismatch / index out of range → None (producer_value_missing)."""
    if body is None:
        return None
    cur = body
    for key in _parse(from_field):
        if isinstance(key, int):
            if not isinstance(cur, list) or key >= len(cur):
                return None
            cur = cur[key]
        else:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
    return cur


class BodyPathError(Exception):
    """set_body_value target missing (array absent / index out of range, target type mismatch) → routed by replay to bind_fail (D61)."""


def set_body_value(body: dict, to_field: str, value: Any) -> None:
    """Write value into body at the to_field (JSONPath) position, supporting array indices symmetrically with extract_value (D61).

    Object segments: missing intermediate dicts are created level by level (existing behaviour). Array index segments: the target must already be a list and the index in range —
    **arrays are never created silently nor extended automatically** (missing → BodyPathError(array_index_out_of_range), routed to bind_fail,
    consistent with "never fabricate").
    """
    keys = _parse(to_field)
    if not keys:
        raise ValueError(f"empty body path: {to_field!r}")
    cur = body
    for i, key in enumerate(keys[:-1]):
        if isinstance(key, int):
            if not isinstance(cur, list) or key >= len(cur):
                raise BodyPathError(f"array_index_out_of_range: {to_field!r} segment [{key}]")
            cur = cur[key]
            continue
        if not isinstance(cur, dict):
            raise BodyPathError(f"target_not_object: {to_field!r} segment {key!r}")
        nxt = cur.get(key)
        if nxt is None:
            if isinstance(keys[i + 1], int):
                # the next segment is an array index → do not create the array (conservative, bind_fail)
                raise BodyPathError(f"array_index_out_of_range: {to_field!r} array segment {key!r} does not exist")
            nxt = {}
            cur[key] = nxt
        cur = nxt
    last = keys[-1]
    if isinstance(last, int):
        if not isinstance(cur, list) or last >= len(cur):
            raise BodyPathError(f"array_index_out_of_range: {to_field!r} segment [{last}]")
        cur[last] = value
    else:
        if not isinstance(cur, dict):
            raise BodyPathError(f"target_not_object: {to_field!r}")
        cur[last] = value
