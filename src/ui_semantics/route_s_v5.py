"""Historical compatibility Route-S v5 dual-view closure.

Scientific projection, predicates, five admission gates, outcome precedence,
observer purity and isolation remain owned by the preserved v1-v4 modules.
This layer only separates producer business/transport request views and admits
path changes that are already proven by arm-local resource-binding events.
"""

from __future__ import annotations

import copy
import collections
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import unquote

from . import route_s as v1
from . import route_s_v2 as v2
from . import route_s_v3 as v3
from . import route_s_v4 as v4
from .route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    dependency_intersects_redactions,
    dotted_tokens,
)


OBSERVATIONS = ("Oc1", "Oc2", "Ot0", "Ot1")
CANONICALIZATION = "typed_canonical_json_object_keys_array_order_preserved_no_coercion"


def build_route_s_certificate_v5(
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
    exact_evidence_sha = hashlib.sha256(execution_evidence_bytes).hexdigest()
    try:
        parsed = json.loads(execution_evidence_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("execution_evidence_bytes_invalid") from error
    if v1.canonical_json_bytes(parsed) != v1.canonical_json_bytes(evidence):
        raise v1.RouteSInvariantError("execution_evidence_bytes_object_mismatch")
    if evidence.get("schema_version") != "ui-semantics-route-s-execution-evidence-v5":
        raise v1.RouteSInvariantError("dual_view_evidence_schema_version_invalid")

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
    v4._validate_candidate_and_projection_anchor(
        evidence, pre_live_binding_pins["payload"], artifact_hashes, artifact_bytes
    )
    payload = v2._validate_binding_artifact(execution_binding, artifact_bytes)
    binding_attestation = _validate_dual_view_binding(evidence, payload, artifact_bytes)
    _reject_redacted_dependencies(evidence)

    binding_evidence = copy.deepcopy(dict(evidence))
    binding_evidence["schema_version"] = "ui-semantics-route-s-execution-evidence-v4"
    producer_record = binding_evidence["protocol"]["P"]
    if producer_record.get("state") == "executed" and producer_record.get("status") == "pass":
        producer_record["request"] = copy.deepcopy(producer_record["transport_request"])
    adjusted_payload = copy.deepcopy(dict(payload))
    for slot, attestation in binding_attestation["request_bindings"].items():
        if slot == "P":
            target_binding = adjusted_payload["producer"]
            actual_request = binding_evidence["protocol"]["P"]["request"]
        else:
            target_binding = adjusted_payload["observations"][slot]
            actual_request = binding_evidence["protocol"][slot]["request"]
        if attestation["path_rebound"]:
            target_binding["path"] = attestation["actual_path"]
        target_binding["request_shape_sha256"] = v2.request_shape_sha256(actual_request)
    v2._validate_candidate_local_binding(
        binding_evidence, adjusted_payload, artifact_hashes, artifact_bytes
    )
    v2._validate_projection_artifact(evidence, artifact_bytes)
    v2._validate_settle(evidence, artifact_hashes, artifact_bytes)
    v2._validate_sensitive_paths(evidence, payload, artifact_hashes, artifact_bytes)
    v2._validate_strict_typed_operands(evidence)

    scientific_evidence = copy.deepcopy(dict(evidence))
    scientific_evidence["schema_version"] = "ui-semantics-route-s-execution-evidence-v4"
    scientific_evidence["protocol"]["P"].pop("transport_request", None)
    scientific_evidence["protocol"]["P"].pop("transport_status", None)
    scientific_evidence["protocol"]["P"].pop("transport_request_shape_sha256", None)
    scientific_evidence["protocol"]["P"].pop("transport_metadata", None)
    scientific_evidence["protocol"]["P"].pop("binding_events", None)
    scientific_evidence["protocol"]["P"].pop("redaction_manifest", None)
    for slot in OBSERVATIONS:
        scientific_evidence["protocol"][slot].pop("binding_events", None)
        scientific_evidence["protocol"][slot].pop("transport_request_shape_sha256", None)
        scientific_evidence["protocol"][slot].pop("transport_metadata", None)
        scientific_evidence["protocol"][slot].pop("redaction_manifest", None)
    inner = v1.build_route_s_certificate(
        scientific_evidence,
        execution_evidence_sha256=exact_evidence_sha,
        artifact_hashes=artifact_hashes,
        expected_pins=expected_pins,
    )
    v2._reject_python_equality_coercion(scientific_evidence, inner)
    dual = binding_attestation["producer_dual_view"]
    return {
        "schema_version": "ui-semantics-route-s-certificate-envelope-v5",
        "status": "rendered_awaiting_post_render_scan_and_final_seal",
        "execution_evidence_sha256": exact_evidence_sha,
        "pre_live_binding_pins": copy.deepcopy(dict(pre_live_binding_pins)),
        "execution_binding": copy.deepcopy(dict(execution_binding)),
        "route_s_certificate": inner,
        "producer_dual_view_attestation": dual,
        "request_binding_attestation": binding_attestation["request_bindings"],
        "redaction_attestation": _redaction_attestation(evidence),
        "qualifying_seal_required": True,
        "live_result_eligible": False,
    }


def _validate_dual_view_binding(
    evidence: Mapping[str, Any],
    payload: Mapping[str, Any],
    artifact_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    protocol = evidence["protocol"]
    producer = protocol["P"]
    rows: dict[str, Any] = {}
    for slot in OBSERVATIONS:
        actual = protocol[slot]
        if actual.get("state") == "executed" and actual.get("status") == "pass":
            if actual.get("request_ref") != evidence["candidate"]["consumer"]["request_ref"]:
                raise v1.RouteSInvariantError(f"{slot}_observer_request_ref_mismatch")
            rows[slot] = _request_binding_attestation(
                slot,
                actual.get("request"),
                payload["observations"][slot],
                actual,
                evidence,
                artifact_bytes,
            )
    if producer.get("state") != "executed" or producer.get("status") != "pass":
        dual = {
            "state": "not_evaluated",
            "reason_code": "producer_not_executed_pass",
        }
    else:
        transport = producer.get("transport_request")
        if not isinstance(transport, dict) or set(transport) != {"method", "path", "body"}:
            raise v1.RouteSInvariantError("producer_transport_request_invalid")
        if v1.canonical_json_bytes(transport.get("body")) != v1.canonical_json_bytes(
            producer.get("request")
        ):
            raise v1.RouteSInvariantError("producer_dual_view_body_mismatch")
        rows["P"] = _request_binding_attestation(
            "P", transport, payload["producer"], producer, evidence, artifact_bytes
        )
        dual = {
            "state": "validated",
            "business_request_sha256": v1.canonical_sha256(producer.get("request")),
            "transport_request_sha256": v1.canonical_sha256(transport),
            "transport_body_sha256": v1.canonical_sha256(transport.get("body")),
            "cross_view_equality": True,
            "left_operand": "/protocol/P/request",
            "right_operand": "/protocol/P/transport_request/body",
            "canonicalization": CANONICALIZATION,
            "derivation_rule": "business_request_from_same_final_outgoing_transport_body_after_binding",
        }
    return {
        "producer_dual_view": dual,
        "request_bindings": rows,
    }


def _request_binding_attestation(
    slot: str,
    actual: Any,
    expected: Mapping[str, Any],
    record: Mapping[str, Any],
    evidence: Mapping[str, Any],
    artifact_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    if not isinstance(actual, dict) or set(actual) != {"method", "path", "body"}:
        raise v1.RouteSInvariantError(f"{slot}_transport_request_invalid")
    if actual["method"] != expected["method"]:
        raise v1.RouteSInvariantError(f"{slot}_method_binding_mismatch")
    expected_actor = (
        evidence["candidate"]["producer"]["actor_id"]
        if slot == "P"
        else evidence["candidate"]["consumer"]["actor_id"]
    )
    expected_request_ref = (
        evidence["candidate"]["producer"]["request_ref"]
        if slot == "P"
        else evidence["candidate"]["consumer"]["request_ref"]
    )
    if record.get("actor_id") != expected_actor:
        raise v1.RouteSInvariantError(f"{slot}_request_actor_mismatch")
    if record.get("request_ref") != expected_request_ref:
        raise v1.RouteSInvariantError(f"{slot}_request_ref_mismatch")
    shape_digest = _redaction_aware_request_shape_sha256(actual)
    if record.get("transport_request_shape_sha256") != shape_digest:
        raise v1.RouteSInvariantError(f"{slot}_captured_request_shape_attestation_mismatch")
    if shape_digest != expected["request_shape_sha256"] and not _empty_object_no_body_shape_compatible(
        actual, expected["request_shape_sha256"]
    ):
        raise v1.RouteSInvariantError(f"{slot}_request_shape_binding_mismatch")
    changed = actual["path"] != expected["path"]
    events = record.get("binding_events") or []
    source_ids, scope_ids = _validate_fresh_binding_events(
        slot, actual, record, evidence, artifact_bytes
    )
    if changed:
        _validate_proven_path_change(expected["path"], actual["path"], events, record)
    return {
        "slot": slot,
        "actor_id": expected_actor,
        "arm": record.get("arm"),
        "reset_epoch": _arm_reset_epoch(evidence, str(record.get("arm"))),
        "request_ref": record.get("request_ref") or None,
        "expected_method": expected["method"],
        "actual_method": actual["method"],
        "expected_path": expected["path"],
        "actual_path": actual["path"],
        "request_shape_sha256": shape_digest,
        "path_rebound": changed,
        "binding_event_count": len(events),
        "source_ids": source_ids,
        "binding_scope_ids": scope_ids,
        "binding_rule": "exact_or_existing_arm_local_typed_resource_event",
    }


def _validate_fresh_binding_events(
    slot: str,
    actual: Mapping[str, Any],
    record: Mapping[str, Any],
    evidence: Mapping[str, Any],
    artifact_bytes: Mapping[str, bytes],
) -> tuple[list[str], list[str]]:
    events = record.get("binding_events") or []
    if not isinstance(events, list):
        raise v1.RouteSInvariantError(f"{slot}_binding_events_invalid")
    arm = str(record.get("arm"))
    epoch = _arm_reset_epoch(evidence, arm)
    actor = str(record.get("actor_id"))
    request_ref = str(record.get("request_ref"))
    candidate_id = str(evidence["candidate"]["candidate_id"])
    plan = _arm_resource_plan(evidence, arm, artifact_bytes)
    plan_uses = plan["uses"]
    plan_sources = plan["sources"]
    expected_uses = [
        row
        for row in plan_uses
        if row.get("consumer_request_ref") == request_ref
        and row.get("actor_id") == actor
    ]
    expected_keys = collections.Counter(
        (
            str(row.get("source_id")),
            str(row.get("consumer_request_ref")),
            str(row.get("location")),
            str(row.get("target_path")),
            str(row.get("actor_id")),
            str(row.get("scalar_type")),
        )
        for row in expected_uses
    )
    actual_keys = collections.Counter(
        (
            str(row.get("source_id")),
            str(row.get("consumer_request_ref")),
            str(row.get("target_location")),
            str(row.get("target_typed_path")),
            str(row.get("actor_id")),
            str(row.get("scalar_type")),
        )
        for row in events
        if isinstance(row, dict) and row.get("event") == "consumer_value_rebound"
    )
    if actual_keys != expected_keys or len(events) != sum(expected_keys.values()):
        raise v1.RouteSInvariantError(f"{slot}_binding_event_plan_closure_mismatch")
    if not events:
        return [], []
    setup_refs = {
        (str(item["actor_id"]), str(item["request_ref"]))
        for item in evidence["candidate"].get("setup", [])
    }
    creator_events = _arm_creator_events(evidence, arm, artifact_bytes)
    source_ids: set[str] = set()
    scope_ids: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("event") != "consumer_value_rebound":
            raise v1.RouteSInvariantError(f"{slot}_unexpected_binding_event")
        expected_scope = _binding_scope_id(candidate_id, arm, actor, epoch)
        creator_actor = str(event.get("creator_actor_id") or "")
        creator_scope = _binding_scope_id(candidate_id, arm, creator_actor, epoch)
        source_matches = [
            row
            for row in plan_sources
            if row.get("source_id") == event.get("source_id")
            and row.get("actor_id") == creator_actor
            and row.get("creator_request_ref") == event.get("creator_request_ref")
            and row.get("response_path") == event.get("source_typed_path")
            and row.get("scalar_type") == event.get("scalar_type")
        ]
        checks = (
            event.get("candidate_id") == candidate_id,
            event.get("arm") == arm,
            event.get("reset_epoch") == epoch,
            event.get("actor_id") == actor,
            bool(creator_actor),
            event.get("consumer_request_ref") == request_ref,
            event.get("binding_scope_id") == expected_scope,
            (creator_actor, str(event.get("creator_request_ref"))) in setup_refs,
            isinstance(event.get("source_id"), str) and bool(event.get("source_id")),
            len(source_matches) == 1,
        )
        if not all(checks):
            raise v1.RouteSInvariantError(f"{slot}_binding_scope_mismatch")
        creator_matches = [
            row
            for row in creator_events
            if row.get("source_id") == event.get("source_id")
            and row.get("creator_request_ref") == event.get("creator_request_ref")
            and row.get("source_typed_path") == event.get("source_typed_path")
            and row.get("actor_id") == creator_actor
            and row.get("creator_actor_id") == creator_actor
            and row.get("candidate_id") == candidate_id
            and row.get("arm") == arm
            and row.get("reset_epoch") == epoch
            and row.get("binding_scope_id") == creator_scope
            and row.get("scalar_type") == event.get("scalar_type")
            and row.get("value_sha256") == event.get("value_sha256")
        ]
        if len(creator_matches) != 1:
            raise v1.RouteSInvariantError(f"{slot}_creator_event_closure_invalid")
        target_value = _binding_target_value(actual, record, event)
        if _scalar_sha256(target_value) != event.get("value_sha256"):
            raise v1.RouteSInvariantError(f"{slot}_final_transport_binding_value_mismatch")
        source_ids.add(str(event["source_id"]))
        scope_ids.add(str(event["binding_scope_id"]))
    return sorted(source_ids), sorted(scope_ids)


def _arm_resource_plan_uses(
    evidence: Mapping[str, Any], arm: str, artifact_bytes: Mapping[str, bytes]
) -> list[dict[str, Any]]:
    """Load the exact per-arm plan sealed in the reset raw artifact."""

    return _arm_resource_plan(evidence, arm, artifact_bytes)["uses"]


def _arm_resource_plan(
    evidence: Mapping[str, Any], arm: str, artifact_bytes: Mapping[str, bytes]
) -> dict[str, list[dict[str, Any]]]:
    """Load and minimally validate the exact per-arm resource plan."""

    slot = {"control": "Rc", "treatment": "Rt"}.get(arm)
    record = evidence["protocol"].get(slot or "", {})
    raw = artifact_bytes.get(str(record.get("raw_ref") or ""))
    if raw is None:
        raise v1.RouteSInvariantError("resource_binding_reset_raw_missing")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("resource_binding_reset_raw_invalid") from error
    reset_ref = value.get("reset_ref") if isinstance(value, dict) else None
    plan = reset_ref.get("resource_binding_plan") if isinstance(reset_ref, dict) else None
    uses = plan.get("uses") if isinstance(plan, dict) else None
    sources = plan.get("sources", []) if isinstance(plan, dict) else None
    if not isinstance(uses, list) or not all(isinstance(row, dict) for row in uses):
        raise v1.RouteSInvariantError("resource_binding_plan_uses_missing")
    if not isinstance(sources, list) or not all(isinstance(row, dict) for row in sources):
        raise v1.RouteSInvariantError("resource_binding_plan_sources_missing")
    return {"uses": uses, "sources": sources}


def _arm_reset_epoch(evidence: Mapping[str, Any], arm: str) -> str:
    slot = {"control": "Rc", "treatment": "Rt"}.get(arm)
    value = evidence["protocol"].get(slot or "", {}).get("reset_epoch")
    if not isinstance(value, str) or not value:
        raise v1.RouteSInvariantError("binding_reset_epoch_missing")
    return value


def _arm_creator_events(
    evidence: Mapping[str, Any], arm: str, artifact_bytes: Mapping[str, bytes]
) -> list[dict[str, Any]]:
    slot = {"control": "Sc", "treatment": "St"}.get(arm)
    record = evidence["protocol"].get(slot or "", {})
    raw = artifact_bytes.get(str(record.get("raw_ref") or ""))
    if raw is None:
        raise v1.RouteSInvariantError("setup_binding_raw_missing")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise v1.RouteSInvariantError("setup_binding_raw_invalid") from error
    rows = value.get("setup") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        raise v1.RouteSInvariantError("setup_binding_rows_missing")
    return [
        event
        for row in rows
        if isinstance(row, dict)
        for event in (row.get("binding_events") or [])
        if isinstance(event, dict) and event.get("event") == "creator_value_captured"
    ]


def _binding_target_value(
    actual: Mapping[str, Any], record: Mapping[str, Any], event: Mapping[str, Any]
) -> Any:
    location = event.get("target_location")
    typed_path = str(event.get("target_typed_path") or "")
    if location == "path":
        match = re.fullmatch(r"\$\.segments\[(\d+)\]", typed_path)
        if match is None:
            raise v1.RouteSInvariantError("binding_path_target_invalid")
        parts = str(actual["path"]).split("/")
        index = int(match.group(1)) + (1 if str(actual["path"]).startswith("/") else 0)
        if index >= len(parts):
            raise v1.RouteSInvariantError("binding_path_target_missing")
        return unquote(parts[index])
    metadata = record.get("transport_metadata")
    if not isinstance(metadata, dict):
        raise v1.RouteSInvariantError("binding_transport_metadata_missing")
    if location == "body":
        root = actual.get("body")
    elif location == "query":
        root = metadata.get("query")
    elif location == "header":
        root = metadata.get("request_headers")
    else:
        raise v1.RouteSInvariantError("binding_target_location_invalid")
    return _typed_path_value(root, typed_path)


def _typed_path_value(value: Any, path: str) -> Any:
    tokens = dotted_tokens(path[2:] if path.startswith("$.") else path)
    current = value
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                raise v1.RouteSInvariantError("binding_target_path_missing")
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                raise v1.RouteSInvariantError("binding_target_path_missing")
            current = current[token]
    return current


def _scalar_sha256(value: Any) -> str:
    if value is None:
        kind = "null"
    elif isinstance(value, bool):
        kind = "boolean"
    elif isinstance(value, int):
        kind = "integer"
    elif isinstance(value, float):
        kind = "number"
    elif isinstance(value, str):
        kind = "string"
    else:
        raise v1.RouteSInvariantError("binding_target_not_scalar")
    return hashlib.sha256(
        json.dumps(
            {"type": kind, "value": value},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _redaction_aware_request_shape_sha256(request: Mapping[str, Any]) -> str:
    return v2.request_shape_sha256(_restore_redacted_types(copy.deepcopy(dict(request))))


def _empty_object_no_body_shape_compatible(
    actual: Mapping[str, Any], expected_sha256: str
) -> bool:
    """Bridge the frozen trace's ``{}`` encoding to an absent outgoing body."""

    if set(actual) != {"method", "path", "body"} or actual.get("body") is not None:
        return False
    frozen_encoding = copy.deepcopy(dict(actual))
    frozen_encoding["body"] = {}
    return v2.request_shape_sha256(frozen_encoding) == expected_sha256


def _restore_redacted_types(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$route_s_redacted"}:
            sentinel = value["$route_s_redacted"]
            if not isinstance(sentinel, dict):
                raise v1.RouteSInvariantError("redaction_sentinel_invalid")
            kind = sentinel.get("original_json_type")
            examples = {
                "null": None,
                "boolean": False,
                "string": "",
                "integer": 0,
                "number": 0.0,
                "array": [],
                "object": {},
            }
            if kind not in examples:
                raise v1.RouteSInvariantError("redaction_original_type_invalid")
            return examples[kind]
        return {key: _restore_redacted_types(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_restore_redacted_types(child) for child in value]
    return value


def _binding_scope_id(candidate_id: str, arm: str, actor_id: str, reset_epoch: str) -> str:
    value = f"{candidate_id}|{arm}|{actor_id}|{reset_epoch}|route-s-binding-scope-v1"
    return hashlib.sha256(value.encode()).hexdigest()


def _validate_proven_path_change(
    expected: str, actual: str, events: Any, record: Mapping[str, Any]
) -> None:
    if not isinstance(events, list):
        raise v1.RouteSInvariantError("path_binding_events_invalid")
    expected_parts = expected.split("/")
    actual_parts = actual.split("/")
    if len(expected_parts) != len(actual_parts):
        raise v1.RouteSInvariantError("path_binding_segment_count_changed")
    changed = {
        index
        for index, pair in enumerate(zip(expected_parts, actual_parts))
        if unquote(pair[0]) != unquote(pair[1])
    }
    allowed: set[int] = set()
    request_ref = record.get("request_ref")
    for event in events:
        if (
            isinstance(event, dict)
            and event.get("event") == "consumer_value_rebound"
            and event.get("consumer_request_ref") == request_ref
            and event.get("target_location") == "path"
        ):
            match = re.fullmatch(r"\$\.segments\[(\d+)\]", str(event.get("target_typed_path")))
            if match is not None:
                allowed.add(int(match.group(1)) + (1 if expected.startswith("/") else 0))
    if not changed or not changed.issubset(allowed):
        raise v1.RouteSInvariantError("path_change_not_proven_by_frozen_binding_events")


def _reject_redacted_dependencies(evidence: Mapping[str, Any]) -> None:
    candidate = evidence["candidate"]
    predicate = candidate["effect_predicate"]
    symbolic = []
    if isinstance(predicate.get("value_ref"), str):
        symbolic.append(predicate["value_ref"])
    symbolic.extend(
        value for value in (predicate.get("match_fields") or {}).values() if isinstance(value, str)
    )
    producer = evidence["protocol"]["P"]
    manifest = producer.get("redaction_manifest") or {}
    for ref in symbolic:
        if ref.startswith("producer.request."):
            rows = manifest.get("request", [])
            tokens = dotted_tokens(ref.removeprefix("producer.request."))
        elif ref.startswith("producer.response."):
            rows = manifest.get("response", [])
            tokens = dotted_tokens(ref.removeprefix("producer.response."))
        elif ref.startswith("consumer.request."):
            rows = []
            tokens = ()
            for slot in OBSERVATIONS:
                slot_manifest = evidence["protocol"][slot].get("redaction_manifest") or {}
                if dependency_intersects_redactions(
                    dotted_tokens(ref.removeprefix("consumer.request.")),
                    slot_manifest.get("request", []),
                ):
                    raise SensitiveMaterialUnavailable("sensitive_material_unavailable")
            continue
        elif ref.startswith("consumer.response."):
            rows = []
            tokens = ()
            for slot in OBSERVATIONS:
                slot_manifest = evidence["protocol"][slot].get("redaction_manifest") or {}
                if dependency_intersects_redactions(
                    dotted_tokens(ref.removeprefix("consumer.response.")),
                    slot_manifest.get("response", []),
                ):
                    raise SensitiveMaterialUnavailable("sensitive_material_unavailable")
            continue
        else:
            continue
        if dependency_intersects_redactions(tokens, rows):
            raise SensitiveMaterialUnavailable("sensitive_material_unavailable")
    target = predicate.get("target_path") or predicate.get("collection_path")
    if isinstance(target, str):
        tokens = dotted_tokens(target)
        for slot in OBSERVATIONS:
            rows = (evidence["protocol"][slot].get("redaction_manifest") or {}).get(
                "response", []
            )
            if dependency_intersects_redactions(tokens, rows):
                raise SensitiveMaterialUnavailable("sensitive_material_unavailable")


def _redaction_attestation(evidence: Mapping[str, Any]) -> dict[str, Any]:
    counts = {}
    for slot in (*OBSERVATIONS, "P"):
        manifest = evidence["protocol"][slot].get("redaction_manifest") or {}
        counts[slot] = {
            name: len(manifest.get(name, []))
            for name in (
                "request",
                "request_query",
                "request_headers",
                "response",
                "response_headers",
            )
        }
    return {
        "rule": "route-s-capture-redaction-v1",
        "capture_before_write": True,
        "original_values_persisted": False,
        "original_value_lengths_persisted": False,
        "original_value_hashes_or_hmacs_persisted": False,
        "observer_secret_state_derivation": "in_memory_equality_ordinal_then_public_label_hash_no_secret_input",
        "slot_counts": counts,
    }


__all__ = ["build_route_s_certificate_v5"]
