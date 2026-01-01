"""final OAS gate (004 D31, revised in 013-C): operation existence filter.

Admit iff the operation has a real recorded observation or at least one successful probe (200 ≤ status < 400):
- UI recorded observations support existing operations; non-zero 4xx/5xx recorded responses are kept as discovery_only;
- a successful probe observation proves the operation exists.

Since 013-C, cleanup/trust/material no longer decide whether an operation enters augmented_oas; they are written to
x-carverflow-discovery.execution_readiness for downstream routing. Protocol-mechanism methods (OPTIONS/HEAD/TRACE)
never spawn a business operation, even on success (D21/G3).
"""

from __future__ import annotations

PROTOCOL_METHODS = {"OPTIONS", "HEAD", "TRACE"}  # protocol mechanism, not a business operation (D21)


def is_success(status: int) -> bool:
    """D31: success is pinned to 200 ≤ status < 400; no 5xx bypass of any kind."""
    return 200 <= status < 400


def observed_http_response(status: int) -> bool:
    """Whether Stage1 saw an actual HTTP response status.

    Browser-level failures use status=0 in some fixtures and do not prove an API
    operation exists.  Real HTTP error responses such as 400/401/403 are still
    useful UI observations and must be preserved in augmented OAS.
    """
    return int(status) > 0


def probe_untrusted(probe: dict) -> bool:
    """D31 (4) + D60: a probe whose cleanup failed is untrusted, **unless** cleanup.basis=environment_reset
    (environment-level reversibility fallback, delivered by the forced end-of-batch reset in Stage 2.5). Only the trust basis
    changes, not the D31 success criterion (is_success untouched; the logic below is V1 plus one leading environment_reset pass-through)."""
    cleanup = probe.get("cleanup", {})
    if cleanup.get("basis") == "environment_reset":
        return False  # D60: environment-level reversibility → trusted admission (end-of-batch reset as cleanup fallback)
    return bool(cleanup.get("required")) and not cleanup.get("performed")


def admit(method: str, ui_observations: list[dict], probe_observations: list[dict]) -> bool:
    """Whether to admit this (method, canonical_path) operation."""
    if method.upper() in PROTOCOL_METHODS:
        return False  # G3: protocol methods never spawn an operation
    ui_observed = any(observed_http_response(o["status"]) for o in ui_observations)
    probe_success = any(is_success(p["response"]["status"]) for p in probe_observations)
    return ui_observed or probe_success
