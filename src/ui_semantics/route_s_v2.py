"""Historical compatibility Route-S v2 closure around the preserved evaluator.

The v2 layer adds candidate-local execution binding, exact evidence/artifact
bytes, strict typed operands, settle symmetry, scoped closure and referenced
sensitive-path rejection.  It remains pure and owns no live lifecycle.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import Any, Mapping, Sequence

from . import route_s as v1
from .dsl import get_path


OBSERVATIONS = ("Oc1", "Oc2", "Ot0", "Ot1")


def request_shape_sha256(request: Mapping[str, Any]) -> str:
    """Hash method/path plus a typed value-free request shape."""
    return v1.canonical_sha256(_shape(dict(request)))


def bind_execution_payload(payload: Mapping[str, Any], artifact_ref: str) -> dict[str, Any]:
    if not artifact_ref:
        raise v1.RouteSInvariantError("execution_binding_ref_empty")
    return {
        "artifact_ref": artifact_ref,
        "artifact_sha256": v1.canonical_sha256(payload),
        "payload": deepcopy(dict(payload)),
    }


def build_route_s_certificate_v2(
    evidence: Mapping[str, Any],
    *,
    execution_evidence_bytes: bytes,
    execution_binding: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
    expected_pins: Mapping[str, str],
) -> dict[str, Any]:
    """Validate all v2 bindings and return a non-qualifying rendered envelope."""
    exact_evidence_sha = hashlib.sha256(execution_evidence_bytes).hexdigest()
    try:
        parsed_evidence = json.loads(execution_evidence_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("execution_evidence_bytes_invalid") from error
    if v1.canonical_json_bytes(parsed_evidence) != v1.canonical_json_bytes(evidence):
        raise v1.RouteSInvariantError("execution_evidence_bytes_object_mismatch")

    payload = _validate_binding_artifact(execution_binding, artifact_bytes)
    _validate_candidate_local_binding(evidence, payload, artifact_hashes, artifact_bytes)
    _validate_projection_artifact(evidence, artifact_bytes)
    _validate_settle(evidence, artifact_hashes, artifact_bytes)
    _validate_sensitive_paths(evidence, payload, artifact_hashes, artifact_bytes)
    _validate_strict_typed_operands(evidence)

    inner = v1.build_route_s_certificate(
        evidence,
        execution_evidence_sha256=exact_evidence_sha,
        artifact_hashes=artifact_hashes,
        expected_pins=expected_pins,
    )
    if inner["execution_evidence_sha256"] != exact_evidence_sha:
        raise v1.RouteSInvariantError("inner_certificate_evidence_hash_mismatch")
    _reject_python_equality_coercion(evidence, inner)
    return {
        "schema_version": "ui-semantics-route-s-certificate-envelope-v1",
        "status": "rendered_awaiting_post_render_scan_and_final_seal",
        "execution_evidence_sha256": exact_evidence_sha,
        "execution_binding": deepcopy(dict(execution_binding)),
        "route_s_certificate": inner,
        "qualifying_seal_required": True,
        "live_result_eligible": False,
    }


def validate_partial_chain_v2(
    records: Sequence[Mapping[str, Any]],
    *,
    artifact_hashes: Mapping[str, str],
    slot_artifact_refs: Mapping[str, Sequence[str]],
) -> None:
    v1.validate_partial_chain(records, artifact_hashes=artifact_hashes)
    for record in records:
        states = record["protocol_slot_states"]
        closed = record["last_closed_slot"]
        if closed == "none":
            continue
        boundary = v1.PROTOCOL_SLOTS.index(closed)
        prefix = [states[slot] for slot in v1.PROTOCOL_SLOTS[: boundary + 1]]
        if "not_executed" in prefix:
            first = prefix.index("not_executed")
            if any(state != "not_executed" for state in prefix[first:]):
                raise v1.RouteSInvariantError("partial_slot_revived_after_not_executed")
        ref = record["last_closed_artifact_ref"]
        if ref not in set(slot_artifact_refs.get(closed, ())):
            raise v1.RouteSInvariantError("partial_last_artifact_not_owned_by_closed_slot")


def validate_final_seal_v2(
    seal: Mapping[str, Any],
    *,
    pre_scan: Mapping[str, Any],
    post_scan: Mapping[str, Any],
    required_pre_scope: Mapping[str, str],
    required_post_scope: Mapping[str, str],
    execution_evidence_bytes: bytes,
    certificate_bytes: bytes,
) -> None:
    v1.validate_scan_report(pre_scan, required_phase="pre_render", required_scope=required_pre_scope)
    v1.validate_scan_report(post_scan, required_phase="post_render", required_scope=required_post_scope)
    v1.validate_final_seal(
        seal,
        pre_scan=pre_scan,
        post_scan=post_scan,
        execution_evidence_bytes=execution_evidence_bytes,
        certificate_bytes=certificate_bytes,
    )


def _validate_binding_artifact(binding: Mapping[str, Any], artifact_bytes: Mapping[str, bytes]) -> Mapping[str, Any]:
    ref = binding.get("artifact_ref")
    raw = artifact_bytes.get(ref)
    if raw is None or hashlib.sha256(raw).hexdigest() != binding.get("artifact_sha256"):
        raise v1.RouteSInvariantError("execution_binding_artifact_hash_mismatch")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("execution_binding_artifact_invalid") from error
    if v1.canonical_json_bytes(parsed) != v1.canonical_json_bytes(binding.get("payload")):
        raise v1.RouteSInvariantError("execution_binding_payload_mismatch")
    return binding["payload"]


def _validate_candidate_local_binding(
    evidence: Mapping[str, Any],
    payload: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
) -> None:
    candidate = evidence["candidate"]
    protocol = evidence["protocol"]
    pins = evidence["pins"]
    if payload.get("candidate_id") != candidate.get("candidate_id"):
        raise v1.RouteSInvariantError("execution_binding_candidate_mismatch")
    for slot in OBSERVATIONS:
        expected = payload["observations"][slot]
        actual = protocol[slot]
        if expected["actor_id"] != candidate["consumer"]["actor_id"]:
            raise v1.RouteSInvariantError(f"{slot}_observer_actor_binding_mismatch")
        _validate_policy_binding(expected, pins, artifact_hashes, artifact_bytes, slot)
        if actual.get("state") == "executed" and actual.get("status") == "pass":
            if actual.get("actor_id") != expected["actor_id"]:
                raise v1.RouteSInvariantError(f"{slot}_observer_actor_binding_mismatch")
            _validate_request_binding(actual.get("request"), expected, pins, artifact_hashes, artifact_bytes, slot)
    expected_p = payload["producer"]
    actual_p = protocol["P"]
    if expected_p["actor_id"] != candidate["producer"]["actor_id"]:
        raise v1.RouteSInvariantError("producer_actor_binding_mismatch")
    if expected_p["request_ref"] != candidate["producer"]["request_ref"]:
        raise v1.RouteSInvariantError("producer_action_request_binding_mismatch")
    _validate_policy_binding(expected_p, pins, artifact_hashes, artifact_bytes, "P")
    if actual_p.get("state") == "executed" and actual_p.get("status") == "pass":
        if actual_p.get("actor_id") != expected_p["actor_id"]:
            raise v1.RouteSInvariantError("producer_actor_binding_mismatch")
        if actual_p.get("request_ref") != expected_p["request_ref"] or actual_p.get("action_ref") != expected_p["action_ref"]:
            raise v1.RouteSInvariantError("producer_action_request_binding_mismatch")
        _validate_request_binding(actual_p.get("request"), expected_p, pins, artifact_hashes, artifact_bytes, "P")

    frozen_setup = [(item["actor_id"], item["request_ref"]) for item in candidate.get("setup", [])]
    for arm, setup_slot in (("control", "Sc"), ("treatment", "St")):
        records = payload["setup"][arm]
        observed_setup = [(item["actor_id"], item["request_ref"]) for item in records]
        if observed_setup != frozen_setup:
            raise v1.RouteSInvariantError(f"{arm}_setup_binding_not_exact")
        setup_protocol = protocol[setup_slot]
        if setup_protocol.get("state") != "executed" or setup_protocol.get("status") != "pass":
            continue
        execution_refs = setup_protocol.get("provenance_refs")
        if not isinstance(execution_refs, list) or len(execution_refs) != len(records):
            raise v1.RouteSInvariantError(f"{arm}_setup_provenance_mismatch")
        for record, ref in zip(records, execution_refs):
            raw = artifact_bytes.get(ref)
            digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
            if raw is None or artifact_hashes.get(ref) != digest:
                raise v1.RouteSInvariantError(f"{arm}_setup_execution_hash_mismatch")
            try:
                actual = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise v1.RouteSInvariantError(f"{arm}_setup_execution_invalid") from error
            expected_actual = {"actor_id": record["actor_id"], "request_ref": record["request_ref"], "status": "pass"}
            if actual != expected_actual:
                raise v1.RouteSInvariantError(f"{arm}_setup_execution_binding_mismatch")


def _validate_request_binding(
    request: Any,
    expected: Mapping[str, Any],
    pins: Mapping[str, str],
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
    slot: str,
) -> None:
    if not isinstance(request, dict):
        raise v1.RouteSInvariantError(f"{slot}_request_not_object")
    if request.get("method") != expected["method"] or request.get("path") != expected["path"]:
        raise v1.RouteSInvariantError(f"{slot}_method_path_binding_mismatch")
    if request_shape_sha256(request) != expected["request_shape_sha256"]:
        raise v1.RouteSInvariantError(f"{slot}_request_shape_binding_mismatch")
    _validate_policy_binding(expected, pins, artifact_hashes, artifact_bytes, slot)


def _validate_policy_binding(expected, pins, artifact_hashes, artifact_bytes, slot):
    ref = expected["observer_policy_ref"]
    digest = expected["observer_policy_sha256"]
    raw = artifact_bytes.get(ref)
    if raw is None or hashlib.sha256(raw).hexdigest() != digest or artifact_hashes.get(ref) != digest or pins["observer_request_policy_sha256"] != digest:
        raise v1.RouteSInvariantError(f"{slot}_observer_policy_binding_mismatch")


def _validate_projection_artifact(evidence: Mapping[str, Any], artifact_bytes: Mapping[str, bytes]) -> None:
    plan = evidence["projection_plan"]
    if plan.get("state") == "not_projectable":
        return
    raw = artifact_bytes.get(plan["artifact_ref"])
    if raw is None or hashlib.sha256(raw).hexdigest() != plan["artifact_sha256"]:
        raise v1.RouteSInvariantError("projection_plan_artifact_bytes_mismatch")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("projection_plan_artifact_invalid") from error
    derived = v1.derive_projection_plan_payload(evidence["candidate"]["effect_predicate"], transform_evidence=evidence["candidate"].get("transform_evidence") or {})
    if v1.canonical_json_bytes(parsed) != v1.canonical_json_bytes(derived):
        raise v1.RouteSInvariantError("projection_plan_artifact_not_derived_payload")


def _validate_settle(
    evidence: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
) -> None:
    control = evidence["protocol"]["settle_c"]
    treatment = evidence["protocol"]["settle_t"]
    if control.get("status") != "pass" or treatment.get("status") != "pass":
        return
    if (control.get("policy_ref"), control.get("policy_sha256")) != (treatment.get("policy_ref"), treatment.get("policy_sha256")):
        raise v1.RouteSInvariantError("settle_policy_not_symmetric")
    ref, digest = control["policy_ref"], control["policy_sha256"]
    raw = artifact_bytes.get(ref)
    if raw is None or hashlib.sha256(raw).hexdigest() != digest or artifact_hashes.get(ref) != digest or evidence["pins"]["settle_policy_sha256"] != digest:
        raise v1.RouteSInvariantError("settle_policy_artifact_or_pin_mismatch")


def _validate_sensitive_paths(
    evidence: Mapping[str, Any],
    payload: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
) -> None:
    classification = payload["sensitive_classification"]
    ref, digest = classification["artifact_ref"], classification["artifact_sha256"]
    raw = artifact_bytes.get(ref)
    if raw is None or hashlib.sha256(raw).hexdigest() != digest or artifact_hashes.get(ref) != digest:
        raise v1.RouteSInvariantError("sensitive_classification_artifact_mismatch")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("sensitive_classification_artifact_invalid") from error
    expected = {
        "forbidden_source_refs": classification["forbidden_source_refs"],
        "forbidden_projection_paths": classification["forbidden_projection_paths"],
    }
    if parsed != expected:
        raise v1.RouteSInvariantError("sensitive_classification_payload_mismatch")
    predicate = evidence["candidate"]["effect_predicate"]
    refs = []
    if isinstance(predicate.get("value_ref"), str):
        refs.append(predicate["value_ref"])
    refs.extend((predicate.get("match_fields") or {}).values())
    path = predicate.get("collection_path") if predicate.get("type") == "item_appears" else predicate.get("target_path")
    if any(ref in set(classification["forbidden_source_refs"]) for ref in refs) or path in set(classification["forbidden_projection_paths"]):
        raise v1.RouteSInvariantError("predicate_references_frozen_sensitive_material")


def _validate_strict_typed_operands(evidence: Mapping[str, Any]) -> None:
    predicate = evidence["candidate"]["effect_predicate"]
    if predicate.get("type") != "numeric_delta":
        return
    path = predicate["target_path"]
    records = evidence["protocol"]
    if any(records[slot].get("state") != "executed" or records[slot].get("status") != "pass" for slot in (*OBSERVATIONS, "P")):
        return
    for slot in OBSERVATIONS:
        value = _path(records[slot]["response"]["body"], path)
        if not _json_number(value):
            raise v1.RouteSInvariantError("numeric_target_requires_finite_json_number")
    source = _symbolic_value(predicate["value_ref"], records["P"], records["Ot1"])
    if not _json_number(source):
        raise v1.RouteSInvariantError("numeric_source_requires_finite_json_number")


def _reject_python_equality_coercion(evidence: Mapping[str, Any], envelope_inner: Mapping[str, Any]) -> None:
    predicate = evidence["candidate"]["effect_predicate"]
    kind = predicate.get("type")
    records = evidence["protocol"]
    if any(records[slot].get("state") != "executed" or records[slot].get("status") != "pass" for slot in (*OBSERVATIONS, "P")):
        return
    gates = envelope_inner.get("gates", {})
    if not all(
        isinstance(gates.get(name), Mapping) and gates[name].get("computed") is True
        for name in ("control_effect_absent", "treatment_effect_present")
    ):
        return
    if kind == "field_equals":
        path = predicate["target_path"]
        expected = _symbolic_value(predicate["value_ref"], records["P"], records["Ot1"])
        for slot in OBSERVATIONS:
            value = _path(records[slot]["response"]["body"], path)
            if value == expected and v1.canonical_json_bytes(value) != v1.canonical_json_bytes(expected):
                raise v1.RouteSInvariantError("field_equals_python_coercion_forbidden")
    elif kind == "item_appears":
        expected = {field: _symbolic_value(ref, records["P"], records["Ot1"]) for field, ref in predicate["match_fields"].items()}
        for slot in OBSERVATIONS:
            collection = _path(records[slot]["response"]["body"], predicate["collection_path"])
            values = collection if isinstance(collection, list) else [collection]
            for item in values:
                if not isinstance(item, dict):
                    continue
                for field, target in expected.items():
                    actual = _path(item, field)
                    if actual == target and v1.canonical_json_bytes(actual) != v1.canonical_json_bytes(target):
                        raise v1.RouteSInvariantError("item_appears_python_coercion_forbidden")


def _symbolic_value(ref: str, producer: Mapping[str, Any], consumer: Mapping[str, Any]) -> Any:
    root, side, *path = ref.split(".")
    if root == "producer":
        value = producer.get(side)
    elif root == "consumer":
        value = consumer.get("response", {}).get("body") if side == "response" else consumer.get(side)
    else:
        raise v1.RouteSInvariantError("setup_symbolic_value_unsupported")
    return _path(value, ".".join(path))


def _path(value: Any, path: str) -> Any:
    try:
        return get_path(value, path)
    except (KeyError, TypeError, ValueError) as error:
        raise v1.RouteSInvariantError("typed_operand_path_missing") from error


def _json_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and (not isinstance(value, float) or math.isfinite(value))


def _shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise v1.RouteSInvariantError("non_finite_request_shape")
        return "number"
    if isinstance(value, str):
        return "string"
    raise v1.RouteSInvariantError("non_json_request_shape")


__all__ = [
    "bind_execution_payload", "build_route_s_certificate_v2", "request_shape_sha256",
    "validate_final_seal_v2", "validate_partial_chain_v2",
]
