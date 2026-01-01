"""Historical compatibility Route-S v4 candidate-and-projection closure.

The pre-live pins accepted here are expected to be bound by a higher-level
execution freeze.  This pure module checks those pins before evaluating any
evidence and owns no live target lifecycle.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Mapping

from . import route_s as v1
from . import route_s_v2 as v2
from . import route_s_v3 as v3


def bind_pre_live_pins_v2(payload: Mapping[str, Any], artifact_ref: str) -> dict[str, Any]:
    if not artifact_ref:
        raise v1.RouteSInvariantError("pre_live_binding_pins_ref_empty")
    return {
        "artifact_ref": artifact_ref,
        "artifact_sha256": v1.canonical_sha256(payload),
        "payload": deepcopy(dict(payload)),
    }


def build_route_s_certificate_v4(
    evidence: Mapping[str, Any],
    *,
    execution_evidence_bytes: bytes,
    execution_binding: Mapping[str, Any],
    pre_live_binding_pins: Mapping[str, Any],
    pre_live_binding_pins_bytes: bytes,
    expected_pre_live_binding_pins_ref: str,
    expected_pre_live_binding_pins_sha256: str,
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
    expected_pins: Mapping[str, str],
) -> dict[str, Any]:
    v3._validate_pre_live_pins(
        evidence,
        execution_binding,
        pre_live_binding_pins,
        pre_live_binding_pins_bytes,
        expected_pre_live_binding_pins_ref,
        expected_pre_live_binding_pins_sha256,
        artifact_hashes,
        artifact_bytes,
    )
    _validate_candidate_and_projection_anchor(
        evidence,
        pre_live_binding_pins["payload"],
        artifact_hashes,
        artifact_bytes,
    )
    inner = v2.build_route_s_certificate_v2(
        evidence,
        execution_evidence_bytes=execution_evidence_bytes,
        execution_binding=execution_binding,
        artifact_hashes=artifact_hashes,
        artifact_bytes=artifact_bytes,
        expected_pins=expected_pins,
    )
    exact_evidence_sha = hashlib.sha256(execution_evidence_bytes).hexdigest()
    return {
        "schema_version": "ui-semantics-route-s-certificate-envelope-v3",
        "status": "rendered_awaiting_post_render_scan_and_final_seal",
        "execution_evidence_sha256": exact_evidence_sha,
        "pre_live_binding_pins": deepcopy(dict(pre_live_binding_pins)),
        "v1_envelope": inner,
        "qualifying_seal_required": True,
        "live_result_eligible": False,
    }


def _validate_candidate_and_projection_anchor(
    evidence: Mapping[str, Any],
    payload: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
) -> None:
    candidate = evidence["candidate"]
    exact = {
        "candidate_id": candidate.get("candidate_id"),
        "candidate_identity": candidate.get("candidate_identity"),
        "normalized_candidate_sha256": candidate.get("normalized_candidate_sha256"),
        "canonical_candidate_payload_sha256": v1.canonical_sha256(candidate),
    }
    for key, value in exact.items():
        if payload.get(key) != value:
            raise v1.RouteSInvariantError(f"{key}_not_pre_live_pinned")
    plan = evidence["projection_plan"]
    ref, digest = plan.get("artifact_ref"), plan.get("artifact_sha256")
    if payload.get("projection_plan_ref") != ref or payload.get("projection_plan_sha256") != digest:
        raise v1.RouteSInvariantError("projection_plan_not_pre_live_pinned")
    raw = artifact_bytes.get(ref)
    if raw is None or hashlib.sha256(raw).hexdigest() != digest or artifact_hashes.get(ref) != digest:
        raise v1.RouteSInvariantError("projection_plan_inventory_mismatch")


__all__ = ["bind_pre_live_pins_v2", "build_route_s_certificate_v4"]
