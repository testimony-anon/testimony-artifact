"""Request/response schema inference (003 D24; deterministic, recursive).

- Merging several observations: a field present in all = required, present in some = optional;
- every property keeps x-carverflow-counts: {n_present, n_total} (003A ruling 2; convention in contracts/README);
- types are unioned: number and integer are distinct, null is a separate type (not downgraded to string);
- nested objects and array elements are recursed into; empty array → items: {}; heterogeneous element types are unioned;
- redaction placeholders are treated as strings (equality interpretation belongs to Stage 4).
"""

from __future__ import annotations

import re

_INT_FORM = re.compile(r"^-?\d+$")


def _json_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def infer_schema(values: list) -> dict:
    """Infer a schema from several observed values at the same position (values has at least 1 element)."""
    types = sorted({_json_type(v) for v in values})
    schema: dict = {"type": types[0] if len(types) == 1 else types}

    objects = [v for v in values if isinstance(v, dict)]
    if objects:
        n_total = len(objects)
        keys = sorted({k for obj in objects for k in obj})
        properties: dict = {}
        required: list[str] = []
        for key in keys:
            present = [obj[key] for obj in objects if key in obj]
            prop = infer_schema(present)
            prop["x-carverflow-counts"] = {
                "n_present": len(present),
                "n_total": n_total,
            }
            properties[key] = prop
            if len(present) == n_total:
                required.append(key)
        schema["properties"] = properties
        if required:
            schema["required"] = required

    arrays = [v for v in values if isinstance(v, list)]
    if arrays:
        elements = [item for arr in arrays for item in arr]
        schema["items"] = infer_schema(elements) if elements else {}

    return schema


def infer_query_parameters(query_lists: list[list[dict]]) -> list[dict]:
    """Query parameter induction (D24): present in all = required; type inferred from the value form (003A detail 4)."""
    n_total = len(query_lists)
    by_name: dict[str, list[str]] = {}
    for ql in query_lists:
        seen = {}
        for pair in ql:
            seen.setdefault(pair["name"], pair["value"])
        for name, value in seen.items():
            by_name.setdefault(name, []).append(value)

    parameters = []
    for name in sorted(by_name):
        values = by_name[name]
        types = sorted({"integer" if _INT_FORM.match(v) else "string" for v in values})
        parameters.append(
            {
                "name": name,
                "in": "query",
                "required": len(values) == n_total,
                "schema": {"type": types[0] if len(types) == 1 else types},
                "x-carverflow-counts": {"n_present": len(values), "n_total": n_total},
            }
        )
    return parameters
