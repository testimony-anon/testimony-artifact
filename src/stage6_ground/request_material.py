"""Fail-closed matching for recorded input request material."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .resource_rebinding import scalar_sha256


def input_action_matches_target_path(
    action: Mapping[str, Any],
    event: Mapping[str, Any],
    target_path: str,
) -> bool:
    """Return whether recorded UI metadata names the target JSON field exactly."""

    field = _terminal_field(target_path)
    if field is None:
        return False
    values = (
        action.get("selector"),
        action.get("workflow_step_id"),
        action.get("scenario_step_id"),
        action.get("element_accessibility"),
        event.get("workflow_step_id"),
        event.get("scenario_step_id"),
    )
    return any(field in _tokens(value) for value in values)


def resolve_environment_request_material(
    environment: Mapping[str, str],
    *,
    actor_id: str,
    target_path: str,
    expected_sha256: str | None = None,
) -> tuple[str, str] | None:
    """Resolve one actor- and field-labelled runtime value without persisting it."""

    field = _terminal_field(target_path)
    if field is None:
        return None
    normalized_actor = re.sub(r"[^A-Za-z0-9]", "", actor_id).lower()
    candidates: list[tuple[str, str]] = []
    for name, value in environment.items():
        name_tokens = _tokens(name)
        normalized_name = re.sub(r"[^A-Za-z0-9]", "", name).lower()
        if field not in name_tokens:
            continue
        if normalized_actor and normalized_actor not in normalized_name:
            continue
        if expected_sha256 is not None and scalar_sha256(value) != expected_sha256:
            continue
        candidates.append((name, value))
    return candidates[0] if len(candidates) == 1 else None


def _terminal_field(target_path: str) -> str | None:
    match = re.search(r"\.([A-Za-z_][A-Za-z0-9_]*)$", target_path)
    return match.group(1).lower() if match is not None else None


def _tokens(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        text = " ".join(f"{key} {item}" for key, item in value.items())
    elif isinstance(value, str):
        text = value
    else:
        return set()
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)}


__all__ = [
    "input_action_matches_target_path",
    "resolve_environment_request_material",
]
