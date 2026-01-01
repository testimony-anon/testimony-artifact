"""Constraint-input proposal checks; baselines and variants stay attributable."""

from __future__ import annotations

from typing import Any, Iterable


def classify_constraint_result(
    *,
    ui_declared_accepts: bool,
    backend_outcome: str,
    comparable: bool = True,
) -> dict[str, str | None]:
    """Classify UI/backend agreement without labeling divergence as a defect."""
    if backend_outcome not in {"accepted", "rejected"} or not comparable:
        return {"classification": "unable", "divergence_direction": None}
    backend_accepts = backend_outcome == "accepted"
    if ui_declared_accepts == backend_accepts:
        return {"classification": "comparable_consistent", "divergence_direction": None}
    direction = "backend_looser_than_ui" if backend_accepts else "backend_stricter_than_ui"
    return {"classification": "comparable_divergent", "divergence_direction": direction}


def validate_constraint_cases(cases: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for case in cases:
        case_id = str(case.get("case_id") or "")
        assignments = case.get("assignments")
        baseline = case.get("valid_baseline")
        if not case_id or not isinstance(assignments, list):
            result.append({"case_id": case_id, "verdict": "rejected_malformed", "reason": "missing case_id or assignments"})
        elif not isinstance(baseline, dict) or not baseline.get("accepted", False):
            result.append({"case_id": case_id, "verdict": "unable", "reason": "valid baseline was not accepted"})
        elif len(assignments) != 1:
            result.append({"case_id": case_id, "verdict": "rejected_malformed", "reason": "variant must change exactly one field"})
        else:
            result.append({"case_id": case_id, "verdict": "ready", "reason": None})
    return result
