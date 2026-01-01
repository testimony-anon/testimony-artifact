"""Shared fail-closed ACTIVE gate for provider/live-capable entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal


def require_active_authorization(
    *,
    repo_root: str | Path,
    entrypoint: str,
    capability: Literal["provider", "live"],
) -> None:
    active_path = Path(repo_root).resolve() / "docs/ACTIVE-EXECUTION.json"
    value = json.loads(active_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("ACTIVE execution lock is not a JSON object")
    allowed = value.get("allowed_entrypoints")
    if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
        raise RuntimeError("ACTIVE allowed_entrypoints is malformed")
    if value.get("target_running") is not False:
        raise RuntimeError("ACTIVE target state is not a closed pre-entry state")
    if value.get("live_allowed") is not True or entrypoint not in allowed:
        raise RuntimeError(
            f"ACTIVE blocks {capability} entrypoint {entrypoint}; explicit exact authorization is required"
        )
