"""action↔API attribution (003 D22 + 002A derived-event rule + 003A ruling 1).

Intervals are [action i, action i+1); derived navigate/submit events open no new interval; the causal constraint
(request start ≥ action start) is guaranteed by the interval construction; a request is attributed to exactly one
action (asserted explicitly). The executable boundary of the three orphan classes is given in D22.
"""

from __future__ import annotations

import re
from datetime import datetime

from .api_filter import ApiObservation
from .loader import LoadedBundle

# 003A ruling 1: independently named strict-attribution-window constant. Initial value equals the 002A settle window (800ms),
# but its semantics are independent and may evolve separately; do not reference the 002A settle constant directly.
STRICT_ATTRIBUTION_WINDOW_MS = 800

DERIVED_WINDOW_MS = 1000  # 002A ruling 1: causal window for derived events
PRIMARY_TYPES = {"click", "input"}
DERIVED_CANDIDATE_TYPES = {"submit", "navigate"}
REDACTED_PATTERN = re.compile(r"\[REDACTED:[0-9a-f]{8}\]")


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _interval_boundaries(actions: list[dict]) -> list[tuple[str, float]]:
    """Non-derived actions open intervals; navigate/submit events judged derived by 002A join the preceding primary action's interval."""
    boundaries: list[tuple[str, float]] = []
    last_primary_ts: float | None = None
    for action in actions:
        ts = _ts(action["timestamp"])
        atype = action["action_type"]
        derived = (
            atype in DERIVED_CANDIDATE_TYPES
            and last_primary_ts is not None
            and 0 <= (ts - last_primary_ts) * 1000.0 <= DERIVED_WINDOW_MS
        )
        if not derived:
            boundaries.append((action["action_id"], ts))
        if atype in PRIMARY_TYPES:
            last_primary_ts = ts
    return boundaries


def _is_stage0_auth(obs: ApiObservation) -> bool:
    """D22 executable boundary: login (a POST whose postData contains a redaction placeholder) or probe (script initiator without a source URL)."""
    if obs.method == "POST" and obs.request_body_text and REDACTED_PATTERN.search(
        obs.request_body_text
    ):
        return True
    initiator = obs.initiator
    has_source = bool(initiator.get("url")) or any(
        frame.get("url")
        for frame in initiator.get("stack", {}).get("callFrames", [])
    )
    return initiator.get("type") == "script" and not has_source


def join_bundle(bundle: LoadedBundle, observations: list[ApiObservation]) -> None:
    """Fill in, in place, each observation's attribution (action_id or orphan_class, exactly one) and confidence tier."""
    boundaries = _interval_boundaries(bundle.actions)
    first_action_ts = boundaries[0][1] if boundaries else float("inf")

    for obs in observations:
        assert obs.action_id is None and obs.orphan_class is None, "a request is attributed only once (D22)"
        if obs.started_ts < first_action_ts:
            obs.orphan_class = "stage0_auth" if _is_stage0_auth(obs) else "initial_load"
            continue
        owner: tuple[str, float] | None = None
        for i, (action_id, action_ts) in enumerate(boundaries):
            next_ts = boundaries[i + 1][1] if i + 1 < len(boundaries) else float("inf")
            if action_ts <= obs.started_ts < next_ts:
                owner = (action_id, action_ts)
                break
        if owner is None:
            obs.orphan_class = "unmatched"
            continue
        # The causal constraint is guaranteed by the left-closed interval construction: obs.started_ts >= action_ts
        obs.action_id = owner[0]
        elapsed_ms = (obs.started_ts - owner[1]) * 1000.0
        obs.confidence_tier = (
            "strict_interval" if elapsed_ms <= STRICT_ATTRIBUTION_WINDOW_MS else "tail"
        )
