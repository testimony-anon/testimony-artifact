"""Frozen GraphAmp oracle used to verify the approved Python DSL subset."""

from __future__ import annotations

from typing import Any


SUPPORTED_GRAPHAMP_TEMPLATES = {
    "status_all_2xx",
    "schema_basic_object",
    "cross_node_equal",
    "selected_entity_present",
    "field_matches_source",
    "quantity_matches_request",
}


def evaluate_supported_outcome(spec: dict[str, Any], js_outcome: dict[str, Any]) -> dict[str, Any]:
    """Re-evaluate a frozen normal outcome without importing GraphAmp JS."""
    template = spec.get("template")
    if template not in SUPPORTED_GRAPHAMP_TEMPLATES:
        return {
            "assertion_id": spec.get("id"),
            "template": template,
            "verdict": "unsupported_by_approved_dsl",
            "calibration": "dropped",
        }
    detail = js_outcome.get("detail") or {}
    if template == "status_all_2xx":
        statuses = list((detail.get("statuses") or {}).values())
        passed = bool(statuses) and all(isinstance(status, int) and 200 <= status < 300 for status in statuses)
        grounded = passed
    elif template == "schema_basic_object":
        passed = bool(detail.get("target")) and detail.get("missing") == []
        grounded = passed
    elif template == "cross_node_equal":
        left, right = detail.get("left"), detail.get("right")
        passed = _values_equal(left, right, spec.get("options") or {})
        grounded = left is not None and right is not None
    elif template == "selected_entity_present":
        passed = detail.get("matched") is not None
        grounded = detail.get("expected") is not None and passed
    elif template == "field_matches_source":
        expected, actual = detail.get("expected"), detail.get("actual")
        passed = _values_equal(actual, expected, spec.get("options") or {})
        grounded = expected is not None and actual is not None
    else:
        expected, actual = detail.get("expected"), detail.get("actual")
        try:
            passed = float(actual) == float(expected)
        except (TypeError, ValueError):
            passed = False
        grounded = expected is not None and actual is not None and detail.get("matchedEntity") is not None
    return {
        "assertion_id": spec["id"],
        "template": template,
        "verdict": "passed" if passed else "failed",
        "calibration": "kept" if passed and grounded else "dropped",
    }


def _values_equal(left: Any, right: Any, options: dict[str, Any]) -> bool:
    if options.get("numeric"):
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            return False
    if options.get("caseInsensitive") and isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    return left == right
