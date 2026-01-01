"""Historical compatibility Route-S v3 pre-live closure.

This version preserves the pure v1/v2 evaluators, but requires a separately
frozen and externally pinned candidate-local binding before evaluating any
live evidence.  It also makes partial-chain slot state monotonic across
write-through records.  The module owns no target lifecycle.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping, Sequence

from . import route_s as v1
from . import route_s_v2 as v2


def bind_pre_live_pins(payload: Mapping[str, Any], artifact_ref: str) -> dict[str, Any]:
    if not artifact_ref:
        raise v1.RouteSInvariantError("pre_live_binding_pins_ref_empty")
    return {
        "artifact_ref": artifact_ref,
        "artifact_sha256": v1.canonical_sha256(payload),
        "payload": deepcopy(dict(payload)),
    }


def build_route_s_certificate_v3(
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
    """Build a non-qualifying envelope only after trusted pre-live pin checks."""
    _validate_pre_live_pins(
        evidence,
        execution_binding,
        pre_live_binding_pins,
        pre_live_binding_pins_bytes,
        expected_pre_live_binding_pins_ref,
        expected_pre_live_binding_pins_sha256,
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
        "schema_version": "ui-semantics-route-s-certificate-envelope-v2",
        "status": "rendered_awaiting_post_render_scan_and_final_seal",
        "execution_evidence_sha256": exact_evidence_sha,
        "pre_live_binding_pins": deepcopy(dict(pre_live_binding_pins)),
        "v1_envelope": inner,
        "qualifying_seal_required": True,
        "live_result_eligible": False,
    }


def validate_partial_chain_v3(
    records: Sequence[Mapping[str, Any]],
    *,
    artifact_hashes: Mapping[str, str],
    slot_artifact_refs: Mapping[str, Sequence[str]],
) -> None:
    """Validate v2 ownership plus immutable cross-record closed-slot states."""
    v2.validate_partial_chain_v2(
        records,
        artifact_hashes=artifact_hashes,
        slot_artifact_refs=slot_artifact_refs,
    )
    previous_states: Mapping[str, str] | None = None
    previous_boundary = -1
    historical_not_executed = False
    for record in records:
        states = record["protocol_slot_states"]
        closed = record["last_closed_slot"]
        boundary = -1 if closed == "none" else v1.PROTOCOL_SLOTS.index(closed)
        if boundary < previous_boundary:
            raise v1.RouteSInvariantError("partial_closed_boundary_regressed")
        if previous_states is not None:
            for slot in v1.PROTOCOL_SLOTS[: previous_boundary + 1]:
                if states[slot] != previous_states[slot]:
                    raise v1.RouteSInvariantError("partial_closed_slot_state_changed")
        newly_closed = states[previous_boundary + 1: boundary + 1] if isinstance(states, list) else [
            states[slot] for slot in v1.PROTOCOL_SLOTS[previous_boundary + 1: boundary + 1]
        ]
        if historical_not_executed and any(state != "not_executed" for state in newly_closed):
            raise v1.RouteSInvariantError("partial_slot_revived_after_historical_not_executed")
        if any(state == "not_executed" for state in states.values()):
            historical_not_executed = True
        previous_states = states
        previous_boundary = boundary


def _validate_pre_live_pins(
    evidence: Mapping[str, Any],
    execution_binding: Mapping[str, Any],
    pins: Mapping[str, Any],
    pins_bytes: bytes,
    expected_ref: str,
    expected_sha256: str,
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
) -> None:
    ref = pins.get("artifact_ref")
    digest = pins.get("artifact_sha256")
    if ref != expected_ref or digest != expected_sha256:
        raise v1.RouteSInvariantError("pre_live_binding_pins_not_frozen")
    if hashlib.sha256(pins_bytes).hexdigest() != digest or artifact_hashes.get(ref) != digest:
        raise v1.RouteSInvariantError("pre_live_binding_pins_hash_mismatch")
    if artifact_bytes.get(ref) != pins_bytes:
        raise v1.RouteSInvariantError("pre_live_binding_pins_artifact_bytes_mismatch")
    try:
        parsed = json.loads(pins_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("pre_live_binding_pins_invalid") from error
    if v1.canonical_json_bytes(parsed) != v1.canonical_json_bytes(pins.get("payload")):
        raise v1.RouteSInvariantError("pre_live_binding_pins_payload_mismatch")
    payload = pins["payload"]
    if payload.get("candidate_id") != evidence["candidate"].get("candidate_id"):
        raise v1.RouteSInvariantError("pre_live_binding_candidate_mismatch")
    if (
        payload.get("execution_binding_ref") != execution_binding.get("artifact_ref")
        or payload.get("execution_binding_sha256") != execution_binding.get("artifact_sha256")
    ):
        raise v1.RouteSInvariantError("execution_binding_not_pre_live_pinned")
    binding_ref = execution_binding["artifact_ref"]
    binding_digest = execution_binding["artifact_sha256"]
    binding_bytes = artifact_bytes.get(binding_ref)
    if binding_bytes is None or hashlib.sha256(binding_bytes).hexdigest() != binding_digest or artifact_hashes.get(binding_ref) != binding_digest:
        raise v1.RouteSInvariantError("execution_binding_inventory_mismatch")
    classification = execution_binding["payload"]["sensitive_classification"]
    class_ref = classification["artifact_ref"]
    class_digest = classification["artifact_sha256"]
    if (
        payload.get("sensitive_classification_ref") != class_ref
        or payload.get("sensitive_classification_sha256") != class_digest
    ):
        raise v1.RouteSInvariantError("sensitive_classification_not_pre_live_pinned")
    class_bytes = artifact_bytes.get(class_ref)
    if class_bytes is None or hashlib.sha256(class_bytes).hexdigest() != class_digest or artifact_hashes.get(class_ref) != class_digest:
        raise v1.RouteSInvariantError("sensitive_classification_inventory_mismatch")


__all__ = [
    "bind_pre_live_pins",
    "build_route_s_certificate_v3",
    "validate_partial_chain_v3",
]
