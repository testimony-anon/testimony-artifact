"""Current, offline-only validators for the current Route-S contract chain.

The validators are deliberately independent of subject runners.  They validate
the published JSON Schema DAG and then close cross-artifact facts that JSON
Schema alone cannot express.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .core import canonical_sha256, _semantic_request_matches_transport


CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
ACTIVE_CHAIN_V5 = (
    "route_s_execution_evidence_v4.schema.json",
    "route_s_execution_evidence_v5.schema.json",
    "route_s_certificate_v4.schema.json",
    "route_s_execution_binding_v2.schema.json",
    "route_s_pre_live_binding_pins_v2.schema.json",
    "route_s_certificate_envelope_v5.schema.json",
)

ROUTE_S_CLOSURE_CHAIN_V5 = (
    *ACTIVE_CHAIN_V5,
    "route_s_partial_certificate_v2.schema.json",
    "route_s_scan_report_v1.schema.json",
    "route_s_final_seal_v1.schema.json",
    "route_s_artifact_manifest_v1.schema.json",
)

CURRENT_ROUTE_S_CONTRACTS = (
    "test_suite.schema.json",
    "current_route_s_execution_material_v1.schema.json",
    "current_route_s_evaluation_v1.schema.json",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def load_registry(
    names: Iterable[str] = ACTIVE_CHAIN_V5,
) -> tuple[dict[str, dict[str, Any]], Registry]:
    documents: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for name in names:
        value = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(value)
        registry = registry.with_resource(value["$id"], Resource.from_contents(value))
        documents[name] = value
    return documents, registry


def validate_instance(
    schema_name: str,
    instance: Mapping[str, Any],
    *,
    names: Iterable[str] = ACTIVE_CHAIN_V5,
) -> None:
    documents, registry = load_registry(names)
    Draft202012Validator(
        documents[schema_name],
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(instance)


def validate_hash_closed_artifact(artifact: Mapping[str, Any]) -> None:
    payload = artifact.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("artifact_payload_not_object")
    digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    if digest != artifact.get("artifact_sha256"):
        raise ValueError("artifact_hash_payload_mismatch")


def validate_current_route_s_material(material: Mapping[str, Any]) -> None:
    validate_instance(
        "current_route_s_execution_material_v1.schema.json",
        material,
        names=CURRENT_ROUTE_S_CONTRACTS,
    )


def validate_current_route_s_evaluation(document: Mapping[str, Any]) -> None:
    validate_instance(
        "current_route_s_evaluation_v1.schema.json",
        document,
        names=("current_route_s_evaluation_v1.schema.json",),
    )


def validate_execution_binding_v2(binding: Mapping[str, Any]) -> None:
    validate_instance("route_s_execution_binding_v2.schema.json", binding)
    validate_hash_closed_artifact(binding)


def validate_pre_live_binding_pins_v2(pins: Mapping[str, Any]) -> None:
    validate_instance("route_s_pre_live_binding_pins_v2.schema.json", pins)
    validate_hash_closed_artifact(pins)


def validate_execution_evidence_v5(evidence: Mapping[str, Any]) -> None:
    validate_instance("route_s_execution_evidence_v5.schema.json", evidence)


def validate_partial_certificate_v2(record: Mapping[str, Any]) -> None:
    validate_instance(
        "route_s_partial_certificate_v2.schema.json",
        record,
        names=("route_s_partial_certificate_v2.schema.json",),
    )


def validate_scan_report_v1(report: Mapping[str, Any]) -> None:
    validate_instance(
        "route_s_scan_report_v1.schema.json",
        report,
        names=("route_s_scan_report_v1.schema.json",),
    )


def validate_final_seal_v1(seal: Mapping[str, Any]) -> None:
    validate_instance(
        "route_s_final_seal_v1.schema.json",
        seal,
        names=("route_s_final_seal_v1.schema.json",),
    )


def validate_artifact_manifest_v1(manifest: Mapping[str, Any]) -> None:
    validate_instance(
        "route_s_artifact_manifest_v1.schema.json",
        manifest,
        names=("route_s_artifact_manifest_v1.schema.json",),
    )


def validate_outer_envelope_v5(
    envelope: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any] | None = None,
) -> None:
    validate_instance("route_s_certificate_envelope_v5.schema.json", envelope)
    validate_hash_closed_artifact(envelope["execution_binding"])
    validate_hash_closed_artifact(envelope["pre_live_binding_pins"])
    hashes = {
        envelope["execution_evidence_sha256"],
        envelope["route_s_certificate"]["execution_evidence_sha256"],
    }
    if len(hashes) != 1:
        raise ValueError("dual_view_envelope_execution_evidence_sha256_mismatch")
    pins_payload = envelope["pre_live_binding_pins"]["payload"]
    binding = envelope["execution_binding"]
    if (
        pins_payload.get("execution_binding_ref") != binding.get("artifact_ref")
        or pins_payload.get("execution_binding_sha256")
        != binding.get("artifact_sha256")
    ):
        raise ValueError("pre_live_pins_execution_binding_crosslink_mismatch")
    for key, row in envelope["request_binding_attestation"].items():
        if row.get("slot") != key:
            raise ValueError("request_binding_attestation_key_slot_mismatch")
    if evidence is not None:
        _validate_outer_against_evidence(envelope, evidence)


def _validate_outer_against_evidence(
    envelope: Mapping[str, Any], evidence: Mapping[str, Any]
) -> None:
    if canonical_sha256(evidence) != envelope["execution_evidence_sha256"]:
        raise ValueError("outer_execution_evidence_object_hash_mismatch")
    protocol = evidence["protocol"]
    expected_slots = {
        slot
        for slot in ("Oc1", "Oc2", "Ot0", "P", "Ot1")
        if protocol[slot].get("state") == "executed"
        and protocol[slot].get("status") == "pass"
    }
    rows = envelope["request_binding_attestation"]
    if set(rows) != expected_slots:
        raise ValueError("request_binding_attestation_executed_pass_closure_mismatch")
    for slot in expected_slots:
        record = protocol[slot]
        row = rows[slot]
        request = record["transport_request"] if slot == "P" else record["request"]
        reset_slot = "Rc" if record["arm"] == "control" else "Rt"
        checks = (
            row["request_ref"] == record["request_ref"],
            row["actor_id"] == record["actor_id"],
            row["arm"] == record["arm"],
            row["reset_epoch"] == protocol[reset_slot]["reset_epoch"],
            row["actual_method"] == request["method"],
            row["actual_path"] == request["path"],
            row["request_shape_sha256"]
            == record["transport_request_shape_sha256"],
            row["binding_event_count"] == len(record["binding_events"]),
            row["source_ids"]
            == sorted(
                {
                    event["source_id"]
                    for event in record["binding_events"]
                    if event.get("event") == "consumer_value_rebound"
                }
            ),
            row["binding_scope_ids"]
            == sorted(
                {
                    event["binding_scope_id"]
                    for event in record["binding_events"]
                    if event.get("event") == "consumer_value_rebound"
                }
            ),
        )
        if not all(checks):
            raise ValueError(f"request_binding_attestation_evidence_mismatch:{slot}")
    dual = envelope["producer_dual_view_attestation"]
    producer = protocol["P"]
    if "P" in expected_slots:
        if dual.get("state") != "validated":
            raise ValueError("producer_dual_view_validated_row_missing")
        if not _semantic_request_matches_transport(
            producer.get("request"),
            producer.get("transport_request", {}).get("body"),
            producer.get("binding_events") or [],
        ):
            raise ValueError("producer_dual_view_alias_equivalence_mismatch")
        if (
            dual["business_request_sha256"]
            != canonical_sha256(producer["request"])
            or dual["transport_body_sha256"]
            != canonical_sha256(producer["transport_request"]["body"])
            or dual["transport_request_sha256"]
            != canonical_sha256(producer["transport_request"])
        ):
            raise ValueError("producer_dual_view_recomputed_hash_mismatch")
    elif dual.get("state") != "not_evaluated":
        raise ValueError("producer_dual_view_not_evaluated_state_mismatch")
    counts = envelope["redaction_attestation"]["slot_counts"]
    for slot in ("Oc1", "Oc2", "Ot0", "P", "Ot1"):
        manifest = protocol[slot].get("redaction_manifest") or {}
        expected_counts = {
            name: len(manifest.get(name, []))
            for name in (
                "request",
                "request_query",
                "request_headers",
                "response",
                "response_headers",
            )
        }
        if counts[slot] != expected_counts:
            raise ValueError(f"redaction_attestation_count_mismatch:{slot}")


__all__ = [
    "ACTIVE_CHAIN_V5",
    "validate_execution_binding_v2",
    "validate_execution_evidence_v5",
    "validate_outer_envelope_v5",
    "validate_pre_live_binding_pins_v2",
]
