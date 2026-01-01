"""Single physical implementation of the current Route-S scientific core."""

from __future__ import annotations

import collections
import copy
import hashlib
import json
import math
import posixpath
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote

from ..dsl import get_path, lint_predicate
from ..route_s_capture_redaction import (
    SENTINEL_KEY,
    SensitiveMaterialUnavailable,
    dotted_tokens,
    predicate_value_refs,
    reject_redacted_predicate_dependencies,
)


PROTOCOL_SLOTS = (
    "Rc", "Sc", "Oc1", "settle_c", "Oc2",
    "Rt", "St", "Ot0", "P", "settle_t", "Ot1",
)

OBSERVATION_SLOTS = ("Oc1", "Oc2", "Ot0", "Ot1")

OBSERVER_DOMAINS = frozenset({"cookie", "token", "cache", "last_seen"})

SUPPORTED_PREDICATES = frozenset({"P01", "P02", "P03", "P04", "P06", "P07", "P08", "P16", "P19", "P09", "P10", "P11", "P12", "P13", "P14", "P15", "P17", "P18", "P20", "P21", "forall"})

OUTCOME_PRECEDENCE = (
    "malformed_or_unsupported",
    "infrastructure_failed",
    "setup_failed",
    "arm_isolation_failed",
    "observer_mutating_or_uncertain",
    "control_unstable",
    "baseline_mismatch",
    "effect_absent",
    "confirmed",
)

CANONICALIZATION = "typed_canonical_json_object_keys_array_order_preserved_no_coercion"

class RouteSInvariantError(ValueError):
    """A run-level evidence, certificate, or closure invariant failed."""

class RouteSUnsupported(ValueError):
    """The frozen predicate cannot be projected without inventing semantics."""

class RouteSUnavailable(ValueError):
    """A runtime operand or observation is absent; this is not semantic false."""

_MISSING = object()

def canonical_json_bytes(value: Any) -> bytes:
    """Return finite, typed canonical JSON bytes without list reordering."""
    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

def derive_projection_plan_payload(
    predicate: Mapping[str, Any],
) -> dict[str, Any]:
    """Mechanically derive the sole projection before any observation exists."""
    lint = lint_predicate(
        predicate,
        assertion=False,
    )
    if lint.verdict != "pass" or lint.predicate is None:
        raise RouteSUnsupported(lint.reason or "predicate_lint_failed")
    family = lint.predicate["family"]
    if family in {"repeat_equal", "repeat_rejected", "repeat_delta"}:
        inner = lint.predicate["delta" if family == "repeat_delta" else "projection"]
        projection = derive_projection_plan_payload(inner)
        projection["predicate_family"] = family
        return projection
    if family not in SUPPORTED_PREDICATES:
        raise RouteSUnsupported("predicate_type_unsupported")
    field = {
        "P01": "target",
        "P02": "left",
        "P03": "target",
        "P08": "output",
        "P19": "output",
        "P16": "after",
        "P09": "target",
        "P10": "target",
        "forall": "collection",
        "P04": "after",
        "P06": "after",
        "P07": "after",
        "P11": "collection" if lint.predicate.get("collection") is not None else "target",
        "P12": "after",
        "P13": "collection",
        "P14": "after",
        "P15": "collection",
        "P17": "left",
        "P18": "source",
        "P20": "left",
        "P21": "target",
    }[family]
    target = lint.predicate["terms"][0]["after"] if family == "P08" and lint.predicate.get("operator") == "linear_delta" else lint.predicate[field]
    path = (
        target.get("collection_path")
        if target.get("source") == "collection_member"
        else target.get("path")
    )
    if not isinstance(path, str):
        raise RouteSUnsupported("projection_path_unavailable")
    if target.get("role") == "observation":
        # Missing tested fields are predicate counterexamples, not missing
        # projection material. V2 retains the actual response body as evidence.
        path = "$"
    for ref in _symbolic_refs(lint.predicate):
        if ref.startswith("setup."):
            raise RouteSUnsupported("setup_symbolic_operand_is_not_uniquely_defined")
    return {
        "predicate_family": family,
        "body_path": path,
        "derived_from_field": field,
        "canonicalization": CANONICALIZATION,
        "materialized_before_observation": True,
        "result_adaptive_selection": False,
    }

def validate_partial_chain(
    records: Sequence[Mapping[str, Any]],
    *,
    artifact_hashes: Mapping[str, str],
) -> None:
    """Validate sequence, hash-chain, slot prefix and last-artifact write-through."""
    if not records:
        raise RouteSInvariantError("partial_chain_empty")
    previous_hash = None
    for index, record in enumerate(records):
        if record.get("record_sequence") != index:
            raise RouteSInvariantError("partial_sequence_non_contiguous")
        if record.get("previous_record_sha256") != previous_hash:
            raise RouteSInvariantError("partial_previous_hash_mismatch")
        _validate_partial_prefix(record)
        closed = record.get("last_closed_slot")
        ref = record.get("last_closed_artifact_ref")
        digest = record.get("last_closed_artifact_sha256")
        if closed == "none":
            if index != 0 or ref is not None or digest is not None:
                raise RouteSInvariantError("partial_initial_record_invalid")
        else:
            if not isinstance(ref, str) or artifact_hashes.get(ref) != digest:
                raise RouteSInvariantError("partial_last_artifact_hash_mismatch")
        previous_hash = canonical_sha256(record)

def validate_scan_report(
    report: Mapping[str, Any],
    *,
    required_phase: str,
    required_scope: Mapping[str, str],
) -> None:
    """Validate phase inventory and redacted finding accounting."""
    if report.get("phase") != required_phase:
        raise RouteSInvariantError("scan_phase_mismatch")
    refs = report.get("scope_refs")
    hashes = report.get("scope_hashes")
    if not isinstance(refs, list) or len(refs) != len(set(refs)):
        raise RouteSInvariantError("scan_scope_refs_not_unique")
    if set(refs) != set(required_scope) or hashes != dict(required_scope):
        raise RouteSInvariantError("scan_scope_inventory_mismatch")
    findings = report.get("finding_records")
    if not isinstance(findings, list) or report.get("findings_count") != len(findings):
        raise RouteSInvariantError("scan_findings_count_mismatch")
    for finding in findings:
        if set(finding) != {"reason_code", "artifact_ref", "artifact_sha256"}:
            raise RouteSInvariantError("scan_finding_contains_unredacted_or_unknown_fields")
        if required_scope.get(finding["artifact_ref"]) != finding["artifact_sha256"]:
            raise RouteSInvariantError("scan_finding_artifact_mismatch")
    if report.get("provider_calls") != 0 or report.get("no_feedback") is not True:
        raise RouteSInvariantError("scan_attestation_boundary_failed")
    if report.get("status") == "pass" and findings:
        raise RouteSInvariantError("passing_scan_has_findings")
    if report.get("status") == "fail" and not findings:
        raise RouteSInvariantError("failing_scan_has_no_findings")

def validate_artifact_manifest(
    manifest: Mapping[str, Any],
    *,
    exact_artifacts: Mapping[str, bytes],
) -> None:
    """Validate relative unique inventory and canonical aggregate, manifest-last."""
    if manifest.get("generated_last") is not True:
        raise RouteSInvariantError("manifest_not_generated_last")
    records = manifest.get("files")
    if not isinstance(records, list):
        raise RouteSInvariantError("manifest_files_invalid")
    observed: dict[str, dict[str, Any]] = {}
    for record in records:
        path = record.get("relative_path")
        if not _safe_relative_path(path) or path in observed:
            raise RouteSInvariantError("manifest_path_invalid_or_duplicate")
        observed[path] = dict(record)
    if set(observed) != set(exact_artifacts):
        raise RouteSInvariantError("manifest_inventory_not_exact")
    expected_records = []
    for path in sorted(exact_artifacts):
        payload = exact_artifacts[path]
        expected = {"relative_path": path, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        if observed[path] != expected:
            raise RouteSInvariantError("manifest_file_record_mismatch")
        expected_records.append(expected)
    if manifest.get("aggregate_sha256") != canonical_sha256(expected_records):
        raise RouteSInvariantError("manifest_aggregate_mismatch")

def validate_final_seal(
    seal: Mapping[str, Any],
    *,
    pre_scan: Mapping[str, Any],
    post_scan: Mapping[str, Any],
    execution_evidence_bytes: bytes,
    certificate_bytes: bytes,
) -> None:
    """Verify the acyclic pre/post scan and final evidence/certificate closure."""
    if pre_scan.get("phase") != "pre_render" or post_scan.get("phase") != "post_render":
        raise RouteSInvariantError("final_seal_scan_phase_mismatch")
    if any(scan.get("status") != "pass" or scan.get("findings_count") != 0 for scan in (pre_scan, post_scan)):
        raise RouteSInvariantError("final_seal_requires_clean_scans")
    expected = {
        "pre_render_scan_sha256": canonical_sha256(pre_scan),
        "post_render_scan_sha256": canonical_sha256(post_scan),
        "execution_evidence_sha256": hashlib.sha256(execution_evidence_bytes).hexdigest(),
        "certificate_sha256": hashlib.sha256(certificate_bytes).hexdigest(),
    }
    if any(seal.get(key) != value for key, value in expected.items()):
        raise RouteSInvariantError("final_seal_hash_mismatch")
    if seal.get("status") != "pass" or seal.get("provider_calls") != 0:
        raise RouteSInvariantError("final_seal_boundary_failed")

def build_route_s_certificate(
    evidence: Mapping[str, Any],
    *,
    execution_evidence_sha256: str,
    artifact_hashes: Mapping[str, str],
    expected_pins: Mapping[str, str],
    verify_forensic_artifacts: bool = True,
) -> dict[str, Any]:
    """Recompute all Route-S gates and return a sanitized final certificate.

    The caller must schema-validate the evidence before this function and the
    returned certificate after it.  No gate or outcome supplied by a caller is
    trusted.
    """
    candidate = evidence["candidate"]
    protocol = evidence["protocol"]
    pins = evidence.get("pins", {})
    if verify_forensic_artifacts:
        if pins != dict(expected_pins):
            raise RouteSInvariantError("pins_not_exactly_frozen")
        _verify_evidence_artifacts(evidence, artifact_hashes)

    malformed_reasons: list[str] = []
    predicate: dict[str, Any] | None = None
    plan = evidence["projection_plan"]
    if candidate.get("predicate_family") == "unsupported" or plan.get("state") == "not_projectable":
        malformed_reasons.append(plan.get("reason_code", "predicate_unsupported"))
    else:
        lint = lint_predicate(
            candidate.get("primary_predicate"),
            assertion=False,
        )
        if lint.verdict != "pass" or lint.predicate is None:
            malformed_reasons.append(lint.reason or "predicate_lint_failed")
        else:
            predicate = lint.predicate
            if predicate["family"] != candidate.get("predicate_family"):
                malformed_reasons.append("candidate_predicate_type_mismatch")
            try:
                derived = derive_projection_plan_payload(
                    predicate,
                )
                for key, value in derived.items():
                    if plan.get(key) != value:
                        malformed_reasons.append("projection_plan_not_mechanically_derived")
                        break
            except RouteSUnsupported as error:
                malformed_reasons.append(str(error))

    infra_reasons = _protocol_infrastructure_reasons(protocol)
    setup_reasons = _protocol_setup_reasons(protocol)
    projection_records: dict[str, dict[str, Any]] = {
        slot: {"state": "not_projected", "reason_code": "observation_not_available"}
        for slot in OBSERVATION_SLOTS
    }
    observer_pure_value: bool | None = None
    observer_reasons: list[str] = []
    if predicate is not None and not malformed_reasons and not infra_reasons and not setup_reasons:
        try:
            projection_records, observer_pure_value, observer_reasons = _project_all_observations(
                protocol,
                plan,
                artifact_hashes,
                require_capability_hashes=verify_forensic_artifacts,
                exact_numeric=predicate["family"] == "P06",
            )
        except RouteSUnavailable as error:
            infra_reasons.append(str(error))

    evaluator_hash = pins.get("predicate_evaluator_sha256", "")
    equivalence_hash = pins.get("equivalence_sha256", "")
    gates = {
        "observer_pure": _gate(observer_pure_value is not None, observer_pure_value, _reason(observer_reasons, "observer_not_computed"), pins.get("observer_request_policy_sha256", ""), []),
        "stable_control": _gate(False, None, "not_computed", equivalence_hash, []),
        "baseline_equivalent": _gate(False, None, "not_computed", equivalence_hash, []),
        "supplemental_baseline": _gate(False, None, "not_computed", equivalence_hash, []),
        "control_effect_absent": _gate(False, None, "not_computed", evaluator_hash, []),
        "treatment_effect_present": _gate(False, None, "not_computed", evaluator_hash, []),
        "isolated": _gate(False, None, "not_computed", pins.get("session_materializer_sha256", ""), []),
    }

    projected = all("normalized_projection" in projection_records[slot] for slot in OBSERVATION_SLOTS)
    if projected:
        gates["stable_control"] = _equivalence_gate(projection_records["Oc1"], projection_records["Oc2"], equivalence_hash, "stable_control")
        gates["baseline_equivalent"] = _equivalence_gate(projection_records["Oc1"], projection_records["Ot0"], equivalence_hash, "baseline_equivalent")
        gates["supplemental_baseline"] = _equivalence_gate(projection_records["Oc2"], projection_records["Ot0"], equivalence_hash, "supplemental_baseline")
        if any(gates[name].get("reason_code") == "numeric_precision_source_missing" for name in ("stable_control", "baseline_equivalent", "supplemental_baseline")):
            malformed_reasons.append("numeric_precision_source_missing")
        try:
            phi_c, phi_c_operands, phi_c_reason = evaluate_pair(predicate, protocol["Oc1"], protocol["Oc2"], protocol["P"])
            phi_t, phi_t_operands, phi_t_reason = evaluate_pair(predicate, protocol["Ot0"], protocol["Ot1"], protocol["P"])
            gates["control_effect_absent"] = _gate(True, not phi_c, phi_c_reason, evaluator_hash, phi_c_operands)
            gates["treatment_effect_present"] = _gate(True, phi_t, phi_t_reason, evaluator_hash, phi_t_operands)
        except (RouteSUnavailable, RouteSUnsupported, TypeError, ValueError) as error:
            malformed_reasons.append(f"predicate_operands_unavailable:{error}")

    isolated, isolation_reasons, isolation_operands, detected_reuse = _evaluate_isolation(evidence)
    gates["isolated"] = _gate(True, isolated, _reason(isolation_reasons, "isolated"), pins.get("session_materializer_sha256", ""), isolation_operands)
    if sorted(evidence.get("cross_arm_reuse_refs", [])) != sorted(detected_reuse):
        raise RouteSInvariantError("cross_arm_reuse_refs_not_recomputed")

    outcome, fail_reasons = _select_outcome(
        malformed_reasons=malformed_reasons,
        infrastructure_reasons=infra_reasons,
        setup_reasons=setup_reasons,
        isolation_reasons=isolation_reasons,
        observer_reasons=observer_reasons,
        gates=gates,
    )
    sanitized_protocol = {
        slot: _sanitize_slot(
            slot,
            protocol[slot],
            include_forensic_refs=verify_forensic_artifacts,
        )
        for slot in PROTOCOL_SLOTS
    }
    certificate = {
        "schema_version": (
            "ui-semantics-route-s-certificate-v4"
            if verify_forensic_artifacts
            else "uisemtest-current-route-s-certificate-inner-v1"
        ),
        "certificate_status": "final",
        "execution_evidence_sha256": execution_evidence_sha256,
        "candidate": deepcopy(candidate),
        "projection_plan": deepcopy(plan),
        "protocol": sanitized_protocol,
        "observation_projections": projection_records,
        "gates": gates,
        "sessions": deepcopy(evidence.get("sessions", [])),
        "cross_arm_reuse_refs": deepcopy(evidence.get("cross_arm_reuse_refs", [])),
        **(
            {
                "pins": deepcopy(pins),
                "run_attestation": deepcopy(evidence["run_attestation"]),
            }
            if verify_forensic_artifacts
            else {}
        ),
        "outcome": outcome,
        "outcome_precedence_version": "route-s-outcome-precedence-v5",
        "fail_closed_reasons": sorted(set(fail_reasons)),
        "completeness": {
            "required_fields_complete": True,
            "schema_validated": True,
            **(
                {"artifact_hashes_verified": True}
                if verify_forensic_artifacts
                else {"execution_material_validated": True}
            ),
            "secret_values_present": False,
        },
    }
    if outcome == "confirmed" and not _confirmed_complete(certificate):
        raise RouteSInvariantError("confirmed_certificate_incomplete")
    return certificate


def build_current_route_s_certificate(
    evidence: Mapping[str, Any],
    *,
    execution_material: Mapping[str, Any],
    execution_evidence_sha256: str,
) -> dict[str, Any]:
    """Validate plain runtime facts, then invoke the one scientific evaluator."""

    scientific_evidence, attestations = prepare_route_s_scientific_input(
        evidence,
        execution_material,
    )

    certificate = build_route_s_certificate(
        scientific_evidence,
        execution_evidence_sha256=execution_evidence_sha256,
        artifact_hashes={},
        expected_pins={},
        verify_forensic_artifacts=False,
    )
    _reject_python_equality_coercion(scientific_evidence, certificate)
    return {
        "schema_version": "uisemtest-current-route-s-certificate-v1",
        "document_kind": "certificate",
        "execution_evidence_sha256": execution_evidence_sha256,
        "execution_binding": {
            "payload": _plain_execution_binding(execution_material["execution_binding"])
        },
        "producer_dual_view_attestation": attestations["producer_dual_view"],
        "request_binding_attestation": attestations["request_bindings"],
        "route_s_certificate": certificate,
    }


def prepare_route_s_scientific_input(
    evidence: Mapping[str, Any],
    execution_material: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate all scientific inputs without artifact refs, pins, or file I/O."""

    candidate = evidence["candidate"]
    if candidate.get("schema_version") != "uisemtest-oracle-candidate-v1":
        raise RouteSInvariantError("normalized_candidate_schema_version_invalid")
    plain_candidate = {
        key: deepcopy(value)
        for key, value in candidate.items()
        if key != "source_hashes"
    }
    if execution_material.get("candidate_id") != candidate.get("candidate_id"):
        raise RouteSInvariantError("execution_material_candidate_mismatch")
    if execution_material.get("bound_candidate_sha256") != candidate.get(
        "normalized_candidate_sha256"
    ):
        raise RouteSInvariantError("execution_material_bound_candidate_mismatch")
    if execution_material.get("candidate_sha256") != canonical_sha256(
        plain_candidate
    ):
        raise RouteSInvariantError("execution_material_candidate_content_mismatch")

    derived_projection = derive_projection_plan_payload(
        candidate["primary_predicate"],
    )
    material_projection = execution_material.get("projection_plan")
    if material_projection != derived_projection:
        raise RouteSInvariantError("execution_material_projection_not_derived")
    if any(
        evidence["projection_plan"].get(key) != value
        for key, value in derived_projection.items()
    ):
        raise RouteSInvariantError("execution_evidence_projection_material_drift")

    binding = _plain_execution_binding(execution_material["execution_binding"])
    if binding.get("sensitive_classification") != execution_material.get(
        "sensitive_classification"
    ):
        raise RouteSInvariantError("sensitive_classification_material_drift")
    observer_policy = execution_material.get("observer_policy")
    if (
        not isinstance(observer_policy, Mapping)
        or observer_policy.get("request_method_policy") != "read_only"
    ):
        raise RouteSInvariantError("observer_policy_not_read_only")
    read_evidence = (
        execution_material.get("protocol_shape", {}).get(
            "read_execution_evidence", {}
        )
    )
    mechanically_read = candidate["consumer"]["request_ref"] in read_evidence
    if any(
        not _observer_binding_is_read_only(
            row, mechanically_read=mechanically_read
        )
        for row in binding.get("observations", {}).values()
    ):
        raise RouteSInvariantError("observer_binding_not_read_only")
    resource_plans = execution_material.get("resource_binding_plans")
    if not isinstance(resource_plans, Mapping):
        raise RouteSInvariantError("execution_material_resource_plans_missing")
    for arm in ("control", "treatment"):
        plan = resource_plans.get(arm)
        if (
            not isinstance(plan, Mapping)
            or plan.get("candidate_id") != candidate.get("candidate_id")
            or plan.get("arm") != arm
            or not isinstance(plan.get("sources"), list)
            or not isinstance(plan.get("uses"), list)
        ):
            raise RouteSInvariantError(f"{arm}_resource_binding_plan_invalid")
    _validate_plain_candidate_binding(evidence, binding)
    attestations = _validate_plain_dual_view_binding(
        evidence,
        binding,
        resource_plans,
    )
    _validate_plain_settle(evidence, execution_material["settle_policy"])
    _validate_plain_sensitive_paths(
        evidence,
        execution_material["sensitive_classification"],
    )
    _reject_redacted_dependencies(evidence)

    scientific_evidence = copy.deepcopy(dict(evidence))
    scientific_evidence["schema_version"] = (
        "ui-semantics-route-s-execution-evidence-v4"
    )
    producer = scientific_evidence["protocol"]["P"]
    for key in (
        "transport_request",
        "transport_status",
        "transport_request_shape_sha256",
        "transport_metadata",
        "binding_events",
        "redaction_manifest",
    ):
        producer.pop(key, None)
    for slot in OBSERVATIONS:
        for key in (
            "binding_events",
            "transport_request_shape_sha256",
            "transport_metadata",
            "redaction_manifest",
        ):
            scientific_evidence["protocol"][slot].pop(key, None)
    for slot in ("Sc", "St"):
        scientific_evidence["protocol"][slot].pop("setup_executions", None)
    return scientific_evidence, attestations


def _plain_execution_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    binding = copy.deepcopy(dict(value))
    binding.pop("schema_version", None)
    for row in [
        binding.get("producer", {}),
        *(binding.get("observations") or {}).values(),
    ]:
        row.pop("observer_policy_ref", None)
        row.pop("observer_policy_sha256", None)
    classification = binding.get("sensitive_classification")
    if isinstance(classification, dict):
        classification.pop("artifact_ref", None)
        classification.pop("artifact_sha256", None)
    return binding


def _observer_binding_is_read_only(
    value: Mapping[str, Any], *, mechanically_read: bool = False
) -> bool:
    method = str(value.get("method") or "").upper()
    return method in {"GET", "HEAD", "OPTIONS"} or (
        method == "POST"
        and (
            value.get("graphql_operation_kind") == "query"
            or mechanically_read
        )
    )


def _validate_plain_candidate_binding(
    evidence: Mapping[str, Any], binding: Mapping[str, Any]
) -> None:
    candidate = evidence["candidate"]
    if binding.get("candidate_id") != candidate.get("candidate_id"):
        raise RouteSInvariantError("execution_binding_candidate_mismatch")
    producer = binding.get("producer") or {}
    if (
        producer.get("actor_id") != candidate["producer"]["actor_id"]
        or producer.get("request_ref") != candidate["producer"]["request_ref"]
    ):
        raise RouteSInvariantError("producer_action_request_binding_mismatch")
    observations = binding.get("observations") or {}
    if set(observations) != set(OBSERVATIONS):
        raise RouteSInvariantError("observer_binding_slots_not_exact")
    for slot in OBSERVATIONS:
        if observations[slot].get("actor_id") != candidate["consumer"]["actor_id"]:
            raise RouteSInvariantError(f"{slot}_observer_actor_binding_mismatch")
    frozen_setup = [
        (row["actor_id"], row["request_ref"])
        for row in candidate.get("setup", [])
    ]
    setup = binding.get("setup") or {}
    for arm in ("control", "treatment"):
        if [
            (row.get("actor_id"), row.get("request_ref"))
            for row in setup.get(arm, [])
        ] != frozen_setup:
            raise RouteSInvariantError(f"{arm}_setup_binding_not_exact")


def _validate_plain_settle(
    evidence: Mapping[str, Any], settle_policy: Mapping[str, Any]
) -> None:
    control = evidence["protocol"]["settle_c"]
    treatment = evidence["protocol"]["settle_t"]
    if control.get("status") != "pass" or treatment.get("status") != "pass":
        return
    if control.get("policy") != settle_policy or treatment.get("policy") != settle_policy:
        raise RouteSInvariantError("settle_policy_not_symmetric")


def _validate_plain_sensitive_paths(
    evidence: Mapping[str, Any], classification: Mapping[str, Any]
) -> None:
    forbidden_refs = classification.get("forbidden_source_refs")
    forbidden_paths = classification.get("forbidden_projection_paths")
    if not isinstance(forbidden_refs, list) or not isinstance(forbidden_paths, list):
        raise RouteSInvariantError("sensitive_classification_invalid")
    predicate = evidence["candidate"]["primary_predicate"]
    refs = [f"{ref['role']}:{ref['path']}" for ref in _value_refs(predicate)]
    path = derive_projection_plan_payload(predicate)["body_path"]
    if any(ref in set(forbidden_refs) for ref in refs) or path in set(
        forbidden_paths
    ):
        raise RouteSInvariantError("predicate_references_frozen_sensitive_material")


def _validate_plain_dual_view_binding(
    evidence: Mapping[str, Any],
    binding: Mapping[str, Any],
    resource_plans: Mapping[str, Any],
) -> dict[str, Any]:
    protocol = evidence["protocol"]
    candidate = evidence["candidate"]
    rows: dict[str, Any] = {}
    for arm, slot in (("control", "Sc"), ("treatment", "St")):
        setup_record = protocol[slot]
        if setup_record.get("state") != "executed" or setup_record.get("status") != "pass":
            continue
        expected_setup = [
            (row["actor_id"], row["request_ref"])
            for row in candidate.get("setup", [])
        ]
        actual_setup = [
            (row.get("actor_id"), row.get("request_ref"))
            for row in setup_record.get("setup_executions", [])
        ]
        if actual_setup != expected_setup:
            raise RouteSInvariantError(f"{arm}_setup_execution_not_exact")

    for slot in OBSERVATIONS:
        record = protocol[slot]
        if record.get("state") == "executed" and record.get("status") == "pass":
            rows[slot] = _plain_request_binding_attestation(
                slot,
                record.get("request"),
                binding["observations"][slot],
                record,
                evidence,
                resource_plans,
            )
    producer = protocol["P"]
    if producer.get("state") != "executed" or producer.get("status") != "pass":
        dual = {
            "state": "not_evaluated",
            "reason_code": "producer_not_executed_pass",
        }
    else:
        transport = producer.get("transport_request")
        if not isinstance(transport, dict) or set(transport) != {
            "method",
            "path",
            "body",
        }:
            raise RouteSInvariantError("producer_transport_request_invalid")
        rows["P"] = _plain_request_binding_attestation(
            "P",
            transport,
            binding["producer"],
            producer,
            evidence,
            resource_plans,
        )
        if not _semantic_request_matches_transport(
            producer.get("request"),
            transport.get("body"),
            producer.get("binding_events") or [],
        ):
            raise RouteSInvariantError("producer_dual_view_body_mismatch")
        dual = {
            "state": "validated",
            "business_request_sha256": canonical_sha256(producer.get("request")),
            "transport_request_sha256": canonical_sha256(transport),
            "transport_body_sha256": canonical_sha256(transport.get("body")),
            "cross_view_equality": True,
            "left_operand": "/protocol/P/request",
            "right_operand": "/protocol/P/transport_request/body",
            "canonicalization": (
                f"{CANONICALIZATION}+proven_arm_local_resource_aliases"
            ),
            "derivation_rule": (
                "business_request_from_same_final_outgoing_transport_body_after_binding"
            ),
        }
    return {"producer_dual_view": dual, "request_bindings": rows}


def _plain_request_binding_attestation(
    slot: str,
    actual: Any,
    expected: Mapping[str, Any],
    record: Mapping[str, Any],
    evidence: Mapping[str, Any],
    resource_plans: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(actual, dict) or set(actual) != {"method", "path", "body"}:
        raise RouteSInvariantError(f"{slot}_transport_request_invalid")
    candidate = evidence["candidate"]
    endpoint = candidate["producer"] if slot == "P" else candidate["consumer"]
    if record.get("actor_id") != endpoint["actor_id"]:
        raise RouteSInvariantError(f"{slot}_request_actor_mismatch")
    if record.get("request_ref") != endpoint["request_ref"]:
        raise RouteSInvariantError(f"{slot}_request_ref_mismatch")
    if slot == "P" and record.get("action_ref") != expected.get("action_ref"):
        raise RouteSInvariantError("producer_action_request_binding_mismatch")
    if actual["method"] != expected.get("method"):
        raise RouteSInvariantError(f"{slot}_method_binding_mismatch")
    shape_digest = _redaction_aware_request_shape_sha256(actual)
    if record.get("transport_request_shape_sha256") != shape_digest:
        raise RouteSInvariantError(
            f"{slot}_captured_request_shape_attestation_mismatch"
        )
    if shape_digest != expected.get("request_shape_sha256") and not empty_object_no_body_shape_compatible(
        actual, str(expected.get("request_shape_sha256") or "")
    ):
        raise RouteSInvariantError(f"{slot}_request_shape_binding_mismatch")
    arm = str(record.get("arm"))
    plan = resource_plans.get(arm)
    if not isinstance(plan, Mapping):
        raise RouteSInvariantError(f"{slot}_resource_binding_plan_missing")
    source_ids, scope_ids = _validate_plain_fresh_binding_events(
        slot,
        actual,
        record,
        evidence,
        plan,
    )
    changed = actual["path"] != expected.get("path")
    if changed:
        validate_proven_path_change(
            str(expected.get("path") or ""),
            actual["path"],
            record.get("binding_events") or [],
            record,
        )
    return {
        "slot": slot,
        "actor_id": endpoint["actor_id"],
        "arm": arm,
        "reset_epoch": _arm_reset_epoch(evidence, arm),
        "request_ref": endpoint["request_ref"],
        "expected_method": expected["method"],
        "actual_method": actual["method"],
        "expected_path": expected["path"],
        "actual_path": actual["path"],
        "request_shape_sha256": shape_digest,
        "path_rebound": changed,
        "binding_event_count": len(record.get("binding_events") or []),
        "source_ids": source_ids,
        "binding_scope_ids": scope_ids,
        "binding_rule": "exact_or_existing_arm_local_typed_resource_event",
    }


def _validate_plain_fresh_binding_events(
    slot: str,
    actual: Mapping[str, Any],
    record: Mapping[str, Any],
    evidence: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    events = record.get("binding_events") or []
    sources = plan.get("sources")
    uses = plan.get("uses")
    if (
        not isinstance(events, list)
        or not isinstance(sources, list)
        or not isinstance(uses, list)
    ):
        raise RouteSInvariantError(f"{slot}_binding_events_or_plan_invalid")
    arm = str(record.get("arm"))
    actor = str(record.get("actor_id"))
    request_ref = str(record.get("request_ref"))
    epoch = _arm_reset_epoch(evidence, arm)
    candidate_id = str(evidence["candidate"]["candidate_id"])
    expected_uses = [
        row
        for row in uses
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
        raise RouteSInvariantError(f"{slot}_binding_event_plan_closure_mismatch")
    if not events:
        return [], []
    physical_request = record.get("physical_transport_request")
    if physical_request is None:
        binding_request = actual
        binding_record = record
    else:
        if not isinstance(physical_request, dict) or set(physical_request) != {
            "method",
            "path",
            "body",
        }:
            raise RouteSInvariantError(
                f"{slot}_physical_transport_request_invalid"
            )
        physical_metadata = record.get("physical_transport_metadata")
        if not isinstance(physical_metadata, dict):
            raise RouteSInvariantError(
                f"{slot}_physical_transport_metadata_invalid"
            )
        binding_request = physical_request
        binding_record = {
            **record,
            "transport_metadata": physical_metadata,
        }
    setup_refs = {
        (str(row["actor_id"]), str(row["request_ref"]))
        for row in evidence["candidate"].get("setup", [])
    }
    setup_slot = "Sc" if arm == "control" else "St"
    creator_events = [
        event
        for row in evidence["protocol"][setup_slot].get("setup_executions", [])
        for event in row.get("binding_events", [])
        if isinstance(event, dict)
        and event.get("event")
        in {
            "creator_value_captured",
            "creator_value_recovered_from_reset_alias",
        }
    ]
    seen_sources: set[str] = set()
    seen_scopes: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("event") != "consumer_value_rebound":
            raise RouteSInvariantError(f"{slot}_unexpected_binding_event")
        creator_actor = str(event.get("creator_actor_id") or "")
        expected_scope = binding_scope_id(candidate_id, arm, actor, epoch)
        creator_scope = binding_scope_id(candidate_id, arm, creator_actor, epoch)
        source_matches = [
            row
            for row in sources
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
            event.get("consumer_request_ref") == request_ref,
            event.get("binding_scope_id") == expected_scope,
            (creator_actor, str(event.get("creator_request_ref"))) in setup_refs,
            len(source_matches) == 1,
        )
        if not all(checks):
            raise RouteSInvariantError(f"{slot}_binding_scope_mismatch")
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
            raise RouteSInvariantError(f"{slot}_creator_event_closure_invalid")
        target_value = _binding_target_value(
            binding_request, binding_record, event
        )
        if _binding_target_is_exact_redaction(
            target_value, record=record, event=event
        ):
            target_sha = event.get("value_sha256")
        else:
            target_sha = _scalar_sha256(target_value)
        if target_sha != event.get("value_sha256"):
            raise RouteSInvariantError(
                f"{slot}_final_transport_binding_value_mismatch"
            )
        seen_sources.add(str(event["source_id"]))
        seen_scopes.add(str(event["binding_scope_id"]))
    return sorted(seen_sources), sorted(seen_scopes)

def _project_all_observations(
    protocol: Mapping[str, Any],
    plan: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    *,
    require_capability_hashes: bool = True,
    exact_numeric: bool = False,
) -> tuple[dict[str, dict[str, Any]], bool, list[str]]:
    records: dict[str, dict[str, Any]] = {}
    all_pure = True
    reasons: list[str] = []
    for slot in OBSERVATION_SLOTS:
        observation = protocol[slot]
        if observation.get("state") != "executed" or observation.get("status") != "pass":
            raise RouteSUnavailable(f"{slot}_observation_not_successful")
        body = observation.get("response", {}).get("body", _MISSING)
        value = _path_or_missing(body, plan["body_path"])
        if value is _MISSING:
            raise RouteSUnavailable(f"{slot}_projection_path_missing")
        domain_results, pure, domain_reasons = _evaluate_observer_domains(
            observation.get("observer_domains"),
            artifact_hashes,
            require_capability_hashes=require_capability_hashes,
        )
        all_pure = all_pure and pure
        reasons.extend(f"{slot}:{reason}" for reason in domain_reasons)
        records[slot] = {
            "raw_ref": observation["raw_ref"],
            **(
                {"raw_sha256": observation["raw_sha256"]}
                if require_capability_hashes
                else {}
            ),
            "observed_at": observation["finished_at"],
            "normalized_projection": deepcopy(value),
            "projection_sha256": canonical_sha256(value),
            "observer_domain_results": domain_results,
        }
        if exact_numeric:
            from ..dsl import NumericObservation
            records[slot] = NumericObservation(records[slot])
            records[slot].exact_numeric = True
            lexical_body = getattr(observation.get("response"), "numeric_body", _MISSING)
            if lexical_body is not _MISSING:
                records[slot].numeric_body = _path_or_missing(lexical_body, plan["body_path"])
    return records, all_pure, reasons

def _evaluate_observer_domains(
    domains: Any,
    artifact_hashes: Mapping[str, str],
    *,
    require_capability_hashes: bool = True,
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    if not isinstance(domains, list) or len(domains) != 4:
        return [], False, ["observer_domain_count_invalid"]
    names = [item.get("domain") for item in domains if isinstance(item, dict)]
    if len(names) != 4 or set(names) != OBSERVER_DOMAINS or len(names) != len(set(names)):
        results = [
            {
                "domain": item.get("domain"), "disposition": item.get("disposition"),
                "value": False, "reason_code": "observer_domain_set_not_exact",
                "before_sha256": item.get("before_sha256"),
                "after_sha256": item.get("after_sha256"),
                "capability_ref": item.get("capability_ref"),
                "capability_sha256": item.get("capability_sha256"),
            }
            for item in domains
        ]
        return results, False, ["observer_domain_set_not_exact"]
    results = []
    reasons = []
    for item in sorted(domains, key=lambda value: value["domain"]):
        ref = item.get("capability_ref")
        cap_ok = (
            isinstance(ref, str)
            and artifact_hashes.get(ref) == item.get("capability_sha256")
            if require_capability_hashes
            else True
        )
        empty = item.get("mutation_events") == [] and item.get("uncertain_fields") == []
        disposition = item.get("disposition")
        if disposition == "proven_unchanged":
            value = bool(item.get("before_sha256") and item.get("before_sha256") == item.get("after_sha256") and empty and cap_ok)
        elif disposition == "not_applicable":
            value = bool(item.get("before_sha256") is None and item.get("after_sha256") is None and empty and cap_ok and item.get("reason_code"))
        else:
            value = False
        reason = "observer_domain_pure" if value else "observer_domain_mutating_or_uncertain"
        if not value:
            reasons.append(f"{item['domain']}:{reason}")
        results.append({
            "domain": item["domain"], "disposition": disposition, "value": value,
            "reason_code": reason, "before_sha256": item.get("before_sha256"),
            "after_sha256": item.get("after_sha256"), "capability_ref": ref,
            "capability_sha256": item.get("capability_sha256"),
        })
    return results, not reasons, reasons

def evaluate_pair(
    predicate: Mapping[str, Any] | None,
    before_observation: Mapping[str, Any],
    after_observation: Mapping[str, Any],
    producer: Mapping[str, Any],
) -> tuple[bool, list[dict[str, Any]], str]:
    if predicate is None:
        raise RouteSUnsupported("predicate_unavailable")
    if any(record.get("state") != "executed" or record.get("status") != "pass" for record in (before_observation, after_observation, producer)):
        raise RouteSUnavailable("pair_protocol_slot_not_successful")
    family = predicate["family"]
    path = derive_projection_plan_payload(predicate)["body_path"]
    before = _path_or_missing(before_observation.get("response", {}).get("body", _MISSING), path)
    after = _path_or_missing(after_observation.get("response", {}).get("body", _MISSING), path)
    if before is _MISSING or after is _MISSING:
        raise RouteSUnavailable("predicate_target_path_missing")
    operands = [
        _operand("before", before_observation["raw_ref"], "pair_before", before),
        _operand("after", after_observation["raw_ref"], "pair_after", after),
    ]
    if family == "P04":
        before, after = _transition_pair_values(
            predicate,
            before,
            after,
            before_observation,
            after_observation,
            producer,
        )
        operands[:2] = [
            _operand("before", before_observation["raw_ref"], "pair_before", before),
            _operand("after", after_observation["raw_ref"], "pair_after", after),
        ]
        expected_before = predicate["from_value"]["value"]
        expected_after = predicate["to_value"]["value"]
        if not all(
            type(value) is bool
            for value in (before, after, expected_before, expected_after)
        ):
            raise RouteSUnavailable("boolean_transition_requires_boolean")
        operands.extend([
            _operand("expected_before", "predicate", "transition_fact", expected_before),
            _operand("expected_after", "predicate", "transition_fact", expected_after),
        ])
        result = (
            before is expected_before
            and after is expected_after
            and before is not after
        )
    elif family == "P06":
        from ..dsl import (copy_numeric_sources, evaluate_numeric_delta,
                           request_numeric_observation)
        result, observed = evaluate_numeric_delta(predicate, {
            "before": before_observation["response"],
            "after": after_observation["response"],
            "producer_request": request_numeric_observation(producer, producer.get("request")),
            "producer_response": copy_numeric_sources(producer, {"body": producer.get("response")}),
        })
        # Never persist original decimal text or a rounded arithmetic operand.
        operands = [_operand("exact_numeric_comparison", after_observation["raw_ref"],
                             "exact_after_minus_before", observed)]
    elif family == "P12":
        actual = len(_collection(before, predicate))
        after_count = len(_collection(after, predicate))
        delta = after_count - actual
        operands.extend([_operand("before_count", before_observation["raw_ref"], "collection_count", actual), _operand("after_count", after_observation["raw_ref"], "collection_count", after_count), _operand("expected_delta", "predicate", "delta", predicate["delta"])])
        result = delta == predicate["delta"]
    elif family in {"P01", "P14"}:
        member = predicate.get("member")
        if member is None:
            if not isinstance(before, bool) or not isinstance(after, bool):
                raise RouteSUnavailable("presence_target_requires_boolean")
            before_count, after_count = int(before), int(after)
        else:
            expected = _resolve_canonical_ref(member["ref"], before_observation, after_observation, producer)
            identity = predicate["identity"]
            before_count = _strict_identity_count(_collection(before, predicate), expected, identity)
            after_count = _strict_identity_count(_collection(after, predicate), expected, identity)
            operands.append(_operand("expected_item", producer["raw_ref"], "strict_identity", expected))
        operator = predicate["operator"]
        if family == "P14" and operator == "removed" and before_count == 0:
            raise RouteSUnavailable("p14_removed_baseline_missing")
        expected_transition = (0, 1) if operator in {"exists", "added"} else (1, 0)
        operands.extend([_operand("before_matches", before_observation["raw_ref"], "match_count", before_count), _operand("after_matches", after_observation["raw_ref"], "match_count", after_count)])
        result = (before_count, after_count) == expected_transition
    elif family == "P02":
        expected = _expected_operand_value(predicate["right"], before_observation, after_observation, producer)
        operands.append(_operand("expected", producer["raw_ref"], "strict_equality", expected))
        left = predicate["left"]
        if left.get("source") == "collection_member":
            member = _resolve_canonical_ref(
                left["member"]["ref"],
                before_observation,
                after_observation,
                producer,
            )
            before_value = _located_member_field_or_missing(before, member, left)
            after_value = _located_member_field_or_missing(after, member, left)
            before_true = before_value is not _MISSING and _strict_equal(
                before_value, expected
            )
            after_true = after_value is not _MISSING and _strict_equal(
                after_value, expected
            )
            operands.extend([
                _operand(
                    "before_identity_match",
                    before_observation["raw_ref"],
                    "strict_identity",
                    before_value is not _MISSING,
                ),
                _operand(
                    "after_identity_match",
                    after_observation["raw_ref"],
                    "strict_identity",
                    after_value is not _MISSING,
                ),
            ])
            result = after_true and not before_true
        else:
            result = _strict_equal(after, expected) and not _strict_equal(before, after)
    else:
        raise RouteSUnsupported("predicate_type_unsupported")
    return result, operands, "predicate_pair_true" if result else "predicate_pair_false"

def _evaluate_isolation(evidence: Mapping[str, Any]) -> tuple[bool, list[str], list[dict[str, Any]], list[str]]:
    candidate = evidence["candidate"]
    actors = {candidate["producer"]["actor_id"], candidate["consumer"]["actor_id"]}
    actors.update(item["actor_id"] for item in candidate.get("setup", []))
    sessions = evidence.get("sessions", [])
    reasons: list[str] = []
    operands: list[dict[str, Any]] = []
    resets = {"control": evidence["protocol"]["Rc"], "treatment": evidence["protocol"]["Rt"]}
    epochs: dict[str, str] = {}
    for arm, reset in resets.items():
        if reset.get("state") == "executed" and reset.get("status") == "pass" and reset.get("reset_epoch"):
            epochs[arm] = reset["reset_epoch"]
            operands.append(_operand(f"{arm}_reset_epoch", reset["raw_ref"], "epoch", reset["reset_epoch"]))
        else:
            reasons.append(f"{arm}_reset_epoch_unavailable")
    if len(epochs) == 2 and epochs["control"] == epochs["treatment"]:
        reasons.append("reset_epoch_reused")
    by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for session in sessions:
        by_key.setdefault((session.get("arm"), session.get("actor_id")), []).append(session)
        if session.get("secret_values_present") is not False:
            reasons.append("session_secret_value_present")
    expected_keys = {(arm, actor) for arm in ("control", "treatment") for actor in actors}
    if set(by_key) != expected_keys or any(len(items) != 1 for items in by_key.values()):
        reasons.append("session_actor_arm_coverage_not_exact")
    for (arm, _actor), items in by_key.items():
        for item in items:
            if epochs.get(arm) != item.get("reset_epoch"):
                reasons.append("session_reset_epoch_mismatch")
    detected: list[str] = []
    fields = ("materialization_id", "ownership_domain_sha256", "jar_ownership_sha256", "mutation_domain_sha256")
    for field in fields:
        control_values = {item.get(field) for item in sessions if item.get("arm") == "control"}
        treatment_values = {item.get(field) for item in sessions if item.get("arm") == "treatment"}
        for value in sorted(control_values & treatment_values):
            if value:
                detected.append(f"{field}:{value}")
        if len([item.get(field) for item in sessions]) != len({item.get(field) for item in sessions}):
            reasons.append(f"{field}_not_unique")
    if detected:
        reasons.append("cross_arm_session_domain_reuse")
    operands.append(_operand("session_ownership_summary", "sessions", "exact_actor_arm_and_domain_isolation", [{key: item.get(key) for key in ("arm", "actor_id", "reset_epoch", "materialization_id", "ownership_domain_sha256", "jar_ownership_sha256", "mutation_domain_sha256")} for item in sessions]))
    return not reasons, sorted(set(reasons)), operands, sorted(detected)

def _select_outcome(
    *,
    malformed_reasons: Sequence[str],
    infrastructure_reasons: Sequence[str],
    setup_reasons: Sequence[str],
    isolation_reasons: Sequence[str],
    observer_reasons: Sequence[str],
    gates: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[str]]:
    buckets = {
        "malformed_or_unsupported": list(malformed_reasons),
        "infrastructure_failed": list(infrastructure_reasons),
        "setup_failed": list(setup_reasons),
        "arm_isolation_failed": list(isolation_reasons),
        "observer_mutating_or_uncertain": list(observer_reasons),
        "control_unstable": [],
        "baseline_mismatch": [],
        "effect_absent": [],
    }
    stable = gates["stable_control"]
    control_absent = gates["control_effect_absent"]
    baseline = gates["baseline_equivalent"]
    treatment = gates["treatment_effect_present"]
    if stable.get("computed") and stable.get("value") is False:
        buckets["control_unstable"].append("control_projection_unstable")
    if control_absent.get("computed") and control_absent.get("value") is False:
        buckets["control_unstable"].append("control_effect_present")
    if baseline.get("computed") and baseline.get("value") is False:
        buckets["baseline_mismatch"].append("control_treatment_baseline_mismatch")
    if treatment.get("computed") and treatment.get("value") is False:
        buckets["effect_absent"].append("treatment_effect_absent")
    for outcome in OUTCOME_PRECEDENCE[:-1]:
        if buckets[outcome]:
            return outcome, buckets[outcome]
    required = ("observer_pure", "stable_control", "baseline_equivalent", "control_effect_absent", "treatment_effect_present", "isolated")
    if not all(gates[name].get("computed") and gates[name].get("value") is True for name in required):
        return "infrastructure_failed", ["required_scientific_gate_not_computed"]
    return "confirmed", []

def _equivalence_gate(left: Mapping[str, Any], right: Mapping[str, Any], evaluator_hash: str, name: str) -> dict[str, Any]:
    if getattr(left, "exact_numeric", False) or getattr(right, "exact_numeric", False):
        from ..dsl import exact_numeric_projection, PredicateNotEvaluable
        try:
            value = exact_numeric_projection(left["normalized_projection"], getattr(left, "numeric_body", None)) == exact_numeric_projection(right["normalized_projection"], getattr(right, "numeric_body", None))
        except PredicateNotEvaluable as error:
            return _gate(False, None, error.reason_code, evaluator_hash, [])
        return _gate(True, value, "equivalent" if value else "not_equivalent", evaluator_hash,
                     [_operand(name, left["raw_ref"], "exact_typed_projection_equivalence", {"numeric_mode": "exact", "values_equal": value})])
    value = canonical_json_bytes(left["normalized_projection"]) == canonical_json_bytes(right["normalized_projection"])
    operands = [
        _operand(f"{name}_left", left["raw_ref"], "canonical_equivalence", left["normalized_projection"]),
        _operand(f"{name}_right", right["raw_ref"], "canonical_equivalence", right["normalized_projection"]),
    ]
    return _gate(True, value, "equivalent" if value else "not_equivalent", evaluator_hash, operands)

def _gate(computed: bool, value: bool | None, reason: str, evaluator_hash: str, operands: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "computed": computed,
        "value": value if computed else None,
        "reason_code": reason,
        **({"evaluator_sha256": evaluator_hash} if evaluator_hash else {}),
        "operands": operands,
    }

def _operand(name: str, raw_ref: str, operator: str, value: Any) -> dict[str, Any]:
    return {"name": name, "raw_ref": raw_ref, "operator": operator, "normalization_rule": CANONICALIZATION, "normalized_value": deepcopy(value), "normalized_value_sha256": canonical_sha256(value)}

def _sanitize_slot(
    slot: str,
    record: Mapping[str, Any],
    *,
    include_forensic_refs: bool = True,
) -> dict[str, Any]:
    if record.get("state") == "not_executed":
        return {key: deepcopy(record[key]) for key in ("slot", "state", "reason_code")}
    keys = ["slot", "state", "raw_ref", "started_at", "finished_at", "status", "arm"]
    if include_forensic_refs:
        keys.append("raw_sha256")
    common = {key: deepcopy(record[key]) for key in keys}
    if record.get("status") == "failed":
        failure_keys = ["reason_code"]
        if include_forensic_refs:
            failure_keys.extend(("error_ref", "error_sha256"))
        common.update({key: deepcopy(record[key]) for key in failure_keys})
        if slot in {"settle_c", "settle_t"}:
            common.update(
                {
                    "policy": deepcopy(record["policy"]),
                    "elapsed_ns": record["elapsed_ns"],
                    "poll_count": record["poll_count"],
                    "consecutive_identical": record["consecutive_identical"],
                    "projection_sha256": record["projection_sha256"],
                }
            )
            if include_forensic_refs:
                common.update(
                    {
                        "policy_ref": record["policy_ref"],
                        "policy_sha256": record["policy_sha256"],
                    }
                )
        return common
    if slot in {"Rc", "Rt"}:
        common["reset_epoch"] = record["reset_epoch"]
    elif slot in {"Sc", "St"}:
        if include_forensic_refs:
            common["provenance_refs"] = deepcopy(record["provenance_refs"])
    elif slot in OBSERVATION_SLOTS:
        common.update({"actor_id": record["actor_id"], "request_sha256": canonical_sha256(record["request"]), "response_sha256": canonical_sha256(record["response"])})
    elif slot == "P":
        common.update({"actor_id": record["actor_id"], "action_ref": record["action_ref"], "request_ref": record["request_ref"], "request_sha256": canonical_sha256(record["request"]), "response_sha256": canonical_sha256(record["response"])})
    else:
        common.update(
            {
                "policy": deepcopy(record["policy"]),
                "elapsed_ns": record["elapsed_ns"],
                "poll_count": record["poll_count"],
                "consecutive_identical": record["consecutive_identical"],
                "projection_sha256": record["projection_sha256"],
            }
        )
        if include_forensic_refs:
            common.update({"policy_ref": record["policy_ref"], "policy_sha256": record["policy_sha256"]})
    return common

def _verify_evidence_artifacts(evidence: Mapping[str, Any], artifact_hashes: Mapping[str, str]) -> None:
    expected: list[tuple[str, str]] = []
    candidate = evidence["candidate"]
    expected.extend((ref, digest) for ref, digest in candidate.get("source_hashes", {}).items())
    plan = evidence["projection_plan"]
    if plan.get("artifact_ref"):
        expected.append((plan["artifact_ref"], plan["artifact_sha256"]))
    for slot in PROTOCOL_SLOTS:
        record = evidence["protocol"][slot]
        if record.get("state") == "executed":
            expected.append((record["raw_ref"], record["raw_sha256"]))
            if record.get("status") == "failed":
                expected.append((record["error_ref"], record["error_sha256"]))
        if slot in OBSERVATION_SLOTS and record.get("status") == "pass":
            expected.extend((domain["capability_ref"], domain["capability_sha256"]) for domain in record["observer_domains"])
    attestation = evidence["run_attestation"]
    expected.extend([(attestation["pre_render_scan_ref"], attestation["pre_render_scan_sha256"]), (attestation["no_feedback_ref"], attestation["no_feedback_sha256"])])
    for ref, digest in expected:
        if artifact_hashes.get(ref) != digest:
            raise RouteSInvariantError(f"artifact_hash_mismatch:{ref}")
    if attestation.get("provider_calls") != 0 or attestation.get("no_feedback") is not True or attestation.get("pre_render_scan_status") != "pass" or attestation.get("pre_render_findings") != 0:
        raise RouteSInvariantError("run_attestation_not_qualifying")

def _protocol_infrastructure_reasons(protocol: Mapping[str, Any]) -> list[str]:
    reasons = []
    for slot in ("Rc", "Oc1", "settle_c", "Oc2", "Rt", "Ot0", "P", "settle_t", "Ot1"):
        record = protocol[slot]
        if record.get("state") == "executed" and record.get("status") != "pass":
            reasons.append(f"{slot}_infrastructure_not_successful")
        elif record.get("state") == "not_executed" and record.get("reason_code") not in {"prior_failure", "setup_failed"}:
            reasons.append(f"{slot}_infrastructure_not_successful")
    return reasons

def _protocol_setup_reasons(protocol: Mapping[str, Any]) -> list[str]:
    return [f"{slot}_setup_not_successful" for slot in ("Sc", "St") if protocol[slot].get("state") != "executed" or protocol[slot].get("status") != "pass"]

def _confirmed_complete(certificate: Mapping[str, Any]) -> bool:
    if certificate["outcome"] != "confirmed" or certificate["fail_closed_reasons"]:
        return False
    if any(certificate["protocol"][slot].get("status") != "pass" for slot in PROTOCOL_SLOTS):
        return False
    if any("normalized_projection" not in certificate["observation_projections"][slot] for slot in OBSERVATION_SLOTS):
        return False
    required_gates = ("observer_pure", "stable_control", "baseline_equivalent", "control_effect_absent", "treatment_effect_present", "isolated")
    return all(certificate["gates"][name].get("computed") and certificate["gates"][name].get("value") is True for name in required_gates)

def _validate_partial_prefix(record: Mapping[str, Any]) -> None:
    states = record.get("protocol_slot_states")
    if not isinstance(states, dict) or set(states) != set(PROTOCOL_SLOTS):
        raise RouteSInvariantError("partial_slot_set_invalid")
    closed = record.get("last_closed_slot")
    boundary = -1 if closed == "none" else PROTOCOL_SLOTS.index(closed)
    for index, slot in enumerate(PROTOCOL_SLOTS):
        state = states[slot]
        if index <= boundary and state not in {"executed", "not_executed"}:
            raise RouteSInvariantError("partial_closed_prefix_has_pending_slot")
        if index > boundary and state != "pending":
            raise RouteSInvariantError("partial_future_slot_not_pending")

def _resolve_symbolic(ref: str, producer: Mapping[str, Any], consumer: Mapping[str, Any]) -> Any:
    parts = ref.split(".")
    if len(parts) < 2:
        raise RouteSUnsupported("symbolic_reference_invalid")
    root, side, *path = parts
    if root == "setup":
        raise RouteSUnsupported("setup_symbolic_operand_is_not_uniquely_defined")
    if root == "producer":
        record = producer
        value = record.get(side, _MISSING)
    elif root == "consumer":
        record = consumer
        if side == "response":
            value = record.get("response", {}).get("body", _MISSING)
        else:
            value = record.get(side, _MISSING)
    else:
        raise RouteSUnsupported("symbolic_reference_root_invalid")
    value = _path_or_missing(value, ".".join(path))
    if value is _MISSING:
        raise RouteSUnavailable(f"symbolic_operand_missing:{ref}")
    return value

def _symbolic_refs(predicate: Mapping[str, Any]) -> Iterable[str]:
    for ref in _value_refs(predicate):
        yield f"{ref['role']}:{ref['path']}"


def _value_refs(predicate: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    family = predicate.get("family")
    for field in {
        "P01": ("target",),
        "P02": ("left",),
        "P04": ("before", "after"),
        "P06": ("before", "after"),
        "P07": ("before", "after"),
        "P20": ("left", "right"),
        "P12": ("before", "after"),
        "P13": ("collection",),
        "P14": ("before", "after"),
        "P15": ("collection",),
        "P17": ("left", "right"),
        "P18": ("source", "partitions", "expected_remainder"),
    }.get(family, ()):
        value = predicate.get(field)
        if isinstance(value, Mapping):
            if value.get("source") == "collection_member":
                suffix = "" if value["field_path"] == "$" else str(
                    value["field_path"]
                ).removeprefix("$")
                yield {
                    "role": value["role"],
                    "path": f'{value["collection_path"]}[*]{suffix}',
                }
                yield value["member"]["ref"]
            else:
                yield value
        elif isinstance(value, list):
            yield from (item for item in value if isinstance(item, Mapping))
    for field in ("member", "right", "delta"):
        operand = predicate.get(field)
        if isinstance(operand, Mapping) and isinstance(operand.get("ref"), Mapping):
            yield operand["ref"]


def _expected_operand_value(
    operand: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    producer: Mapping[str, Any],
) -> Any:
    """Resolve a comparison operand: a frozen hypothesis literal or a canonical ref."""

    if operand.get("source") == "hypothesis":
        value = operand["value"]
        if _json_value_type(value) != operand.get("value_type"):
            raise RouteSUnavailable("hypothesis_value_type_mismatch")
        return value
    return _resolve_canonical_ref(operand["ref"], before, after, producer)


def _json_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _resolve_canonical_ref(
    ref: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    producer: Mapping[str, Any],
) -> Any:
    role = ref["role"]
    if role == "before":
        root = before.get("response", {}).get("body", _MISSING)
    elif role == "after":
        root = after.get("response", {}).get("body", _MISSING)
    elif role == "producer_request":
        root = producer.get("request", _MISSING)
    elif role == "producer_response":
        root = producer.get("response", _MISSING)
    else:
        raise RouteSUnsupported("value_ref_role_unsupported")
    value = _path_or_missing(root, str(ref["path"]))
    if value is _MISSING:
        raise RouteSUnavailable("predicate_value_ref_path_missing")
    return value


def _strict_equal(left: Any, right: Any) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def _strict_identity_count(
    values: Sequence[Any], member: Any, identity: Mapping[str, Any]
) -> int:
    return len(_strict_identity_matches(values, member, identity))


def _strict_identity_member(
    values: Sequence[Any],
    member: Any,
    identity: Mapping[str, Any],
    *,
    excluded_collection_paths: frozenset[str] = frozenset(),
) -> Any:
    matches = _strict_identity_matches(
        values,
        member,
        identity,
        excluded_collection_paths=excluded_collection_paths,
    )
    return matches[0] if matches else _MISSING


def _strict_identity_matches(
    values: Sequence[Any],
    member: Any,
    identity: Mapping[str, Any],
    *,
    excluded_collection_paths: frozenset[str] = frozenset(),
) -> list[Any]:
    field_pairs = identity["field_pairs"]
    try:
        expected = tuple(
            get_path(member, pair["member_path"])
            for pair in field_pairs
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RouteSUnavailable("predicate_member_identity_path_missing") from error
    matches = []
    for item in values:
        try:
            actual = tuple(
                get_path(item, pair["collection_item_path"])
                for pair in field_pairs
            )
        except (KeyError, TypeError, ValueError):
            continue
        if all(_strict_equal(left, right) for left, right in zip(actual, expected)):
            matches.append(item)
    if len(matches) > 1:
        refined = _refine_identity_matches(
            matches,
            member,
            field_pairs=field_pairs,
            excluded_collection_paths=excluded_collection_paths,
        )
        if refined is not None:
            return [refined]
        raise RouteSUnavailable("predicate_identity_ambiguous")
    return matches


_NON_BUSINESS_IDENTITY_NAMES = frozenset({
    "accesstoken",
    "authorization",
    "cookie",
    "password",
    "refreshtoken",
    "session",
    "sessionid",
    "token",
})


def _named_scalar_paths(
    value: Any, *, path: str = "$"
) -> dict[str, list[tuple[str, Any]]]:
    result: dict[str, list[tuple[str, Any]]] = {}
    if not isinstance(value, Mapping):
        return result
    for key, child in value.items():
        child_path = f"{path}.{key}"
        if isinstance(child, Mapping):
            nested = _named_scalar_paths(child, path=child_path)
            for name, rows in nested.items():
                result.setdefault(name, []).extend(rows)
        elif isinstance(child, (str, int, float, bool)) and child is not None:
            name = re.sub(r"[-_]", "", str(key)).casefold()
            result.setdefault(name, []).append((child_path, child))
    return result


def _refine_identity_matches(
    matches: Sequence[Any],
    member: Any,
    *,
    field_pairs: Sequence[Mapping[str, Any]],
    excluded_collection_paths: frozenset[str],
) -> Any | None:
    """Disambiguate with unique producer scalars visible on collection items.

    The frozen locator remains the first gate.  Refinement is admitted only
    when a uniquely named producer scalar has the same uniquely named path in
    every matched collection object and independently selects the same single
    member.  The predicate's measured field is excluded so selection cannot
    make the asserted equality true by construction.
    """

    member_paths = _named_scalar_paths(member)
    item_paths = [_named_scalar_paths(item) for item in matches]
    existing_paths = {
        str(pair["collection_item_path"]) for pair in field_pairs
    }
    uniquely_selected: dict[int, list[tuple[str, str]]] = {}
    for name, member_rows in member_paths.items():
        if name in _NON_BUSINESS_IDENTITY_NAMES or len(member_rows) != 1:
            continue
        per_item = [rows.get(name, []) for rows in item_paths]
        if any(len(rows) != 1 for rows in per_item):
            continue
        collection_paths = {str(rows[0][0]) for rows in per_item}
        if len(collection_paths) != 1:
            continue
        collection_path = next(iter(collection_paths))
        if (
            collection_path in existing_paths
            or collection_path in excluded_collection_paths
        ):
            continue
        member_path, expected = member_rows[0]
        selected = [
            index
            for index, rows in enumerate(per_item)
            if type(rows[0][1]) is type(expected)
            and _strict_equal(rows[0][1], expected)
        ]
        if len(selected) == 1:
            uniquely_selected.setdefault(selected[0], []).append(
                (member_path, collection_path)
            )
    if len(uniquely_selected) != 1:
        return None
    return matches[next(iter(uniquely_selected))]


def _located_member_field_or_missing(
    collection: Any, member: Any, ref: Mapping[str, Any]
) -> Any:
    item = _strict_identity_member(
        _collection(collection, ref),
        member,
        ref["identity"],
        excluded_collection_paths=frozenset({str(ref["field_path"])}),
    )
    if item is _MISSING:
        return _MISSING
    value = _path_or_missing(item, str(ref["field_path"]))
    if value is _MISSING:
        raise RouteSUnavailable("located_member_field_missing")
    return value


def _transition_pair_values(
    predicate: Mapping[str, Any],
    before_value: Any,
    after_value: Any,
    before_observation: Mapping[str, Any],
    after_observation: Mapping[str, Any],
    producer: Mapping[str, Any],
) -> tuple[Any, Any]:
    before_ref = predicate["before"]
    after_ref = predicate["after"]
    before_located = before_ref.get("source") == "collection_member"
    after_located = after_ref.get("source") == "collection_member"
    if before_located != after_located:
        raise RouteSUnsupported("transition_reference_shape_mismatch")
    if not before_located:
        return before_value, after_value
    member = _resolve_canonical_ref(
        before_ref["member"]["ref"],
        before_observation,
        after_observation,
        producer,
    )
    before_field = _located_member_field_or_missing(
        before_value, member, before_ref
    )
    after_field = _located_member_field_or_missing(after_value, member, after_ref)
    if before_field is _MISSING or after_field is _MISSING:
        raise RouteSUnavailable("located_transition_member_missing")
    return before_field, after_field

def _path_or_missing(value: Any, path: str) -> Any:
    if value is _MISSING:
        return _MISSING
    try:
        return get_path(value, path)
    except (KeyError, TypeError, ValueError):
        return _MISSING

def _apply_transform(value: Any, transform: Mapping[str, Any] | None) -> Any:
    if not transform or transform.get("type") in {"identity", "null_transition"}:
        return value
    if transform["type"] in {"number_multiply", "unit_scale"}:
        if isinstance(value, bool):
            raise RouteSUnavailable("transform_numeric_operand_boolean")
        return float(value) * transform["factor"]
    if transform["type"] == "enum_map":
        return transform["mapping"].get(str(value), value)
    raise RouteSUnsupported("transform_type_unsupported")

def _transition_matches(before: Any, after: Any, transform: Mapping[str, Any] | None) -> bool:
    if not transform or transform.get("type") != "null_transition":
        return True
    if transform.get("mode") == "null_to_value":
        return before is None and after is not None
    if transform.get("mode") == "value_to_null":
        return before is not None and after is None
    raise RouteSUnsupported("null_transition_mode_unsupported")

def _collection(value: Any, predicate: Mapping[str, Any]) -> list[Any]:
    transform = predicate.get("value_transform") or {}
    if value is None and transform.get("type") == "null_transition" and transform.get("mode") == "null_as_empty_collection":
        return []
    if value is None:
        raise RouteSUnavailable("collection_is_null_without_frozen_transition")
    return value if isinstance(value, list) else [value]

def _match_count(items: Sequence[Any], expected: Mapping[str, Any]) -> int:
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            if all(get_path(item, field) == value for field, value in expected.items()):
                count += 1
        except (KeyError, TypeError, ValueError):
            continue
    return count

def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RouteSInvariantError("non_finite_json_number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise RouteSInvariantError("non_string_json_object_key")
        for item in value.values():
            _validate_json_value(item)
        return
    raise RouteSInvariantError(f"non_json_value:{type(value).__name__}")

def _safe_relative_path(path: Any) -> bool:
    return isinstance(path, str) and bool(path) and not path.startswith("/") and "\\" not in path and posixpath.normpath(path) == path and not path.startswith("../") and "/../" not in path

def _reason(reasons: Sequence[str], default: str) -> str:
    return ";".join(sorted(set(reasons))) if reasons else default

OBSERVATIONS = ("Oc1", "Oc2", "Ot0", "Ot1")

def request_shape_sha256(request: Mapping[str, Any]) -> str:
    """Hash method/path plus a typed value-free request shape."""
    return canonical_sha256(_shape(dict(request)))

def bind_execution_payload(payload: Mapping[str, Any], artifact_ref: str) -> dict[str, Any]:
    if not artifact_ref:
        raise RouteSInvariantError("execution_binding_ref_empty")
    return {
        "artifact_ref": artifact_ref,
        "artifact_sha256": canonical_sha256(payload),
        "payload": deepcopy(dict(payload)),
    }

def validate_partial_chain_v2(
    records: Sequence[Mapping[str, Any]],
    *,
    artifact_hashes: Mapping[str, str],
    slot_artifact_refs: Mapping[str, Sequence[str]],
) -> None:
    validate_partial_chain(records, artifact_hashes=artifact_hashes)
    for record in records:
        states = record["protocol_slot_states"]
        closed = record["last_closed_slot"]
        if closed == "none":
            continue
        boundary = PROTOCOL_SLOTS.index(closed)
        prefix = [states[slot] for slot in PROTOCOL_SLOTS[: boundary + 1]]
        if "not_executed" in prefix:
            first = prefix.index("not_executed")
            if any(state != "not_executed" for state in prefix[first:]):
                raise RouteSInvariantError("partial_slot_revived_after_not_executed")
        ref = record["last_closed_artifact_ref"]
        if ref not in set(slot_artifact_refs.get(closed, ())):
            raise RouteSInvariantError("partial_last_artifact_not_owned_by_closed_slot")

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
    validate_scan_report(pre_scan, required_phase="pre_render", required_scope=required_pre_scope)
    validate_scan_report(post_scan, required_phase="post_render", required_scope=required_post_scope)
    validate_final_seal(
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
        raise RouteSInvariantError("execution_binding_artifact_hash_mismatch")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteSInvariantError("execution_binding_artifact_invalid") from error
    if canonical_json_bytes(parsed) != canonical_json_bytes(binding.get("payload")):
        raise RouteSInvariantError("execution_binding_payload_mismatch")
    return binding["payload"]

def _reject_python_equality_coercion(evidence: Mapping[str, Any], envelope_inner: Mapping[str, Any]) -> None:
    predicate = evidence["candidate"]["primary_predicate"]
    kind = predicate.get("family")
    records = evidence["protocol"]
    if any(records[slot].get("state") != "executed" or records[slot].get("status") != "pass" for slot in (*OBSERVATIONS, "P")):
        return
    gates = envelope_inner.get("gates", {})
    if not all(
        isinstance(gates.get(name), Mapping) and gates[name].get("computed") is True
        for name in ("control_effect_absent", "treatment_effect_present")
    ):
        return
    if kind == "P02":
        left = predicate["left"]
        expected = _expected_operand_value(
            predicate["right"], records["Ot0"], records["Ot1"], records["P"]
        )
        for slot in OBSERVATIONS:
            if left.get("source") == "collection_member":
                member = _resolve_canonical_ref(
                    left["member"]["ref"],
                    records["Ot0"],
                    records["Ot1"],
                    records["P"],
                )
                collection = _path(
                    records[slot]["response"]["body"],
                    left["collection_path"],
                )
                value = _located_member_field_or_missing(collection, member, left)
                if value is _MISSING:
                    continue
            else:
                value = _path(records[slot]["response"]["body"], left["path"])
            if value == expected and canonical_json_bytes(value) != canonical_json_bytes(expected):
                raise RouteSInvariantError("P02_python_coercion_forbidden")
    elif kind in {"P01", "P14"} and predicate.get("member") is not None:
        expected = _resolve_canonical_ref(
            predicate["member"]["ref"], records["Ot0"], records["Ot1"], records["P"]
        )
        identity_pairs = predicate["identity"]["field_pairs"]
        for slot in OBSERVATIONS:
            collection = _path(records[slot]["response"]["body"], derive_projection_plan_payload(predicate)["body_path"])
            values = collection if isinstance(collection, list) else [collection]
            for item in values:
                if not isinstance(item, dict):
                    continue
                for pair in identity_pairs:
                    target = _path(expected, pair["member_path"])
                    actual = _path(item, pair["collection_item_path"])
                    if actual == target and canonical_json_bytes(actual) != canonical_json_bytes(target):
                        raise RouteSInvariantError("P14_python_coercion_forbidden")

def _symbolic_value(ref: str, producer: Mapping[str, Any], consumer: Mapping[str, Any]) -> Any:
    root, side, *path = ref.split(".")
    if root == "producer":
        value = producer.get(side)
    elif root == "consumer":
        value = consumer.get("response", {}).get("body") if side == "response" else consumer.get(side)
    else:
        raise RouteSInvariantError("setup_symbolic_value_unsupported")
    return _path(value, ".".join(path))

def _path(value: Any, path: str) -> Any:
    try:
        return get_path(value, path)
    except (KeyError, TypeError, ValueError) as error:
        raise RouteSInvariantError("typed_operand_path_missing") from error

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
            raise RouteSInvariantError("non_finite_request_shape")
        return "number"
    if isinstance(value, str):
        return "string"
    raise RouteSInvariantError("non_json_request_shape")

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
        raise RouteSInvariantError("pre_live_binding_pins_not_frozen")
    if hashlib.sha256(pins_bytes).hexdigest() != digest or artifact_hashes.get(ref) != digest:
        raise RouteSInvariantError("pre_live_binding_pins_hash_mismatch")
    if artifact_bytes.get(ref) != pins_bytes:
        raise RouteSInvariantError("pre_live_binding_pins_artifact_bytes_mismatch")
    try:
        parsed = json.loads(pins_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteSInvariantError("pre_live_binding_pins_invalid") from error
    if canonical_json_bytes(parsed) != canonical_json_bytes(pins.get("payload")):
        raise RouteSInvariantError("pre_live_binding_pins_payload_mismatch")
    payload = pins["payload"]
    if payload.get("candidate_id") != evidence["candidate"].get("candidate_id"):
        raise RouteSInvariantError("pre_live_binding_candidate_mismatch")
    if (
        payload.get("execution_binding_ref") != execution_binding.get("artifact_ref")
        or payload.get("execution_binding_sha256") != execution_binding.get("artifact_sha256")
    ):
        raise RouteSInvariantError("execution_binding_not_pre_live_pinned")
    binding_ref = execution_binding["artifact_ref"]
    binding_digest = execution_binding["artifact_sha256"]
    binding_bytes = artifact_bytes.get(binding_ref)
    if binding_bytes is None or hashlib.sha256(binding_bytes).hexdigest() != binding_digest or artifact_hashes.get(binding_ref) != binding_digest:
        raise RouteSInvariantError("execution_binding_inventory_mismatch")
    classification = execution_binding["payload"]["sensitive_classification"]
    class_ref = classification["artifact_ref"]
    class_digest = classification["artifact_sha256"]
    if (
        payload.get("sensitive_classification_ref") != class_ref
        or payload.get("sensitive_classification_sha256") != class_digest
    ):
        raise RouteSInvariantError("sensitive_classification_not_pre_live_pinned")
    class_bytes = artifact_bytes.get(class_ref)
    if class_bytes is None or hashlib.sha256(class_bytes).hexdigest() != class_digest or artifact_hashes.get(class_ref) != class_digest:
        raise RouteSInvariantError("sensitive_classification_inventory_mismatch")

def bind_pre_live_pins_v2(payload: Mapping[str, Any], artifact_ref: str) -> dict[str, Any]:
    if not artifact_ref:
        raise RouteSInvariantError("pre_live_binding_pins_ref_empty")
    return {
        "artifact_ref": artifact_ref,
        "artifact_sha256": canonical_sha256(payload),
        "payload": deepcopy(dict(payload)),
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
        "canonical_candidate_payload_sha256": canonical_sha256(candidate),
    }
    for key, value in exact.items():
        if payload.get(key) != value:
            raise RouteSInvariantError(f"{key}_not_pre_live_pinned")
    plan = evidence["projection_plan"]
    ref, digest = plan.get("artifact_ref"), plan.get("artifact_sha256")
    if payload.get("projection_plan_ref") != ref or payload.get("projection_plan_sha256") != digest:
        raise RouteSInvariantError("projection_plan_not_pre_live_pinned")
    raw = artifact_bytes.get(ref)
    if raw is None or hashlib.sha256(raw).hexdigest() != digest or artifact_hashes.get(ref) != digest:
        raise RouteSInvariantError("projection_plan_inventory_mismatch")

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
    execution_material: Mapping[str, Any],
) -> dict[str, Any]:
    exact_evidence_sha = hashlib.sha256(execution_evidence_bytes).hexdigest()
    try:
        parsed = json.loads(execution_evidence_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteSInvariantError("execution_evidence_bytes_invalid") from error
    if canonical_json_bytes(parsed) != canonical_json_bytes(evidence):
        raise RouteSInvariantError("execution_evidence_bytes_object_mismatch")
    if evidence.get("schema_version") != "ui-semantics-route-s-execution-evidence-v5":
        raise RouteSInvariantError("dual_view_evidence_schema_version_invalid")

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
    _validate_candidate_and_projection_anchor(
        evidence, pre_live_binding_pins["payload"], artifact_hashes, artifact_bytes
    )
    payload = _validate_binding_artifact(execution_binding, artifact_bytes)
    if _plain_execution_binding(payload) != _plain_execution_binding(
        execution_material["execution_binding"]
    ):
        raise RouteSInvariantError("forensic_execution_binding_material_drift")
    _validate_forensic_material_attestations(
        evidence,
        payload,
        execution_material,
        artifact_hashes,
        artifact_bytes,
    )
    scientific_evidence, binding_attestation = prepare_route_s_scientific_input(
        evidence,
        execution_material,
    )
    inner = build_route_s_certificate(
        scientific_evidence,
        execution_evidence_sha256=exact_evidence_sha,
        artifact_hashes=artifact_hashes,
        expected_pins=expected_pins,
    )
    _reject_python_equality_coercion(scientific_evidence, inner)
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


def _validate_forensic_material_attestations(
    evidence: Mapping[str, Any],
    binding_payload: Mapping[str, Any],
    execution_material: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
    artifact_bytes: Mapping[str, bytes],
) -> None:
    def require_json_artifact(ref: Any, digest: Any, expected: Any) -> None:
        raw = artifact_bytes.get(str(ref))
        if (
            raw is None
            or hashlib.sha256(raw).hexdigest() != digest
            or artifact_hashes.get(str(ref)) != digest
        ):
            raise RouteSInvariantError("forensic_material_artifact_hash_mismatch")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RouteSInvariantError("forensic_material_artifact_invalid") from error
        if canonical_json_bytes(value) != canonical_json_bytes(expected):
            raise RouteSInvariantError("forensic_material_artifact_content_mismatch")

    plan = evidence["projection_plan"]
    require_json_artifact(
        plan.get("artifact_ref"),
        plan.get("artifact_sha256"),
        execution_material["projection_plan"],
    )
    producer = binding_payload["producer"]
    require_json_artifact(
        producer.get("observer_policy_ref"),
        producer.get("observer_policy_sha256"),
        execution_material["observer_policy"],
    )
    settle = evidence["protocol"]["settle_c"]
    settle_ref = settle.get("policy_ref")
    settle_digest = settle.get("policy_sha256")
    if settle.get("state") == "not_executed":
        settle_digest = evidence["pins"].get("settle_policy_sha256")
        expected_bytes = canonical_json_bytes(execution_material["settle_policy"])
        matching_refs = [
            ref
            for ref, digest in artifact_hashes.items()
            if digest == settle_digest and artifact_bytes.get(ref) == expected_bytes
        ]
        if len(matching_refs) != 1:
            raise RouteSInvariantError("forensic_material_artifact_hash_mismatch")
        settle_ref = matching_refs[0]
    require_json_artifact(
        settle_ref,
        settle_digest,
        execution_material["settle_policy"],
    )
    classification = binding_payload["sensitive_classification"]
    require_json_artifact(
        classification.get("artifact_ref"),
        classification.get("artifact_sha256"),
        execution_material["sensitive_classification"],
    )

def _arm_reset_epoch(evidence: Mapping[str, Any], arm: str) -> str:
    slot = {"control": "Rc", "treatment": "Rt"}.get(arm)
    value = evidence["protocol"].get(slot or "", {}).get("reset_epoch")
    if not isinstance(value, str) or not value:
        raise RouteSInvariantError("binding_reset_epoch_missing")
    return value

def _binding_target_value(
    actual: Mapping[str, Any], record: Mapping[str, Any], event: Mapping[str, Any]
) -> Any:
    location = event.get("target_location")
    typed_path = str(event.get("target_typed_path") or "")
    if location == "path":
        match = re.fullmatch(r"\$\.segments\[(\d+)\]", typed_path)
        if match is None:
            raise RouteSInvariantError("binding_path_target_invalid")
        parts = str(actual["path"]).split("/")
        index = int(match.group(1)) + (1 if str(actual["path"]).startswith("/") else 0)
        if index >= len(parts):
            raise RouteSInvariantError("binding_path_target_missing")
        return unquote(parts[index])
    metadata = record.get("transport_metadata")
    if not isinstance(metadata, dict):
        raise RouteSInvariantError("binding_transport_metadata_missing")
    if location == "body":
        root = actual.get("body")
    elif location == "query":
        root = metadata.get("query")
    elif location == "header":
        root = metadata.get("request_headers")
    else:
        raise RouteSInvariantError("binding_target_location_invalid")
    return _typed_path_value(root, typed_path)


def _binding_target_is_exact_redaction(
    value: Any,
    *,
    record: Mapping[str, Any],
    event: Mapping[str, Any],
) -> bool:
    """Accept a value-free capture only at the exact rebound scalar path."""

    sentinel = value.get(SENTINEL_KEY) if isinstance(value, Mapping) else None
    if not isinstance(sentinel, Mapping):
        return False
    channel = {
        "body": "request",
        "query": "request_query",
        "header": "request_headers",
    }.get(str(event.get("target_location") or ""))
    if channel is None:
        return False
    tokens = dotted_tokens(str(event.get("target_typed_path") or ""))
    pointer = "".join(
        "/" + str(token).replace("~", "~0").replace("/", "~1")
        for token in tokens
    )
    rows = (record.get("redaction_manifest") or {}).get(channel) or []
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("json_pointer") == pointer
        and row.get("replacement_kind") == "typed_sentinel"
        and row.get("original_json_type") == event.get("scalar_type")
    ]
    return len(matches) == 1 and all(
        sentinel.get(key) == matches[0].get(key)
        for key in ("category", "original_json_type", "rule")
    )

def _typed_path_value(value: Any, path: str) -> Any:
    tokens = dotted_tokens(path[2:] if path.startswith("$.") else path)
    current = value
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                raise RouteSInvariantError("binding_target_path_missing")
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                raise RouteSInvariantError("binding_target_path_missing")
            current = current[token]
    return current


def _semantic_request_matches_transport(
    semantic: Any,
    transport: Any,
    events: Sequence[Mapping[str, Any]],
) -> bool:
    if canonical_json_bytes(semantic) == canonical_json_bytes(transport):
        return True
    paths = sorted(
        {
            str(event.get("target_typed_path"))
            for event in events
            if event.get("event") == "consumer_value_rebound"
            and event.get("target_location") == "body"
        }
    )
    if not paths:
        return False
    allowed = {
        dotted_tokens(path[2:] if path.startswith("$.") else path)
        for path in paths
    }

    def masked(value: Any, at: tuple[str | int, ...] = ()) -> Any:
        if at in allowed:
            return {"$uisemtest_proven_alias": True}
        if isinstance(value, dict):
            return {
                key: masked(child, at + (key,))
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [
                masked(child, at + (index,))
                for index, child in enumerate(value)
            ]
        return copy.deepcopy(value)

    return canonical_json_bytes(masked(semantic)) == canonical_json_bytes(
        masked(transport)
    )


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
        raise RouteSInvariantError("binding_target_not_scalar")
    return hashlib.sha256(
        json.dumps(
            {"type": kind, "value": value},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

def _redaction_aware_request_shape_sha256(request: Mapping[str, Any]) -> str:
    return request_shape_sha256(_restore_redacted_types(copy.deepcopy(dict(request))))

def empty_object_no_body_shape_compatible(
    actual: Mapping[str, Any], expected_sha256: str
) -> bool:
    """Bridge the frozen trace's ``{}`` encoding to an absent outgoing body."""

    if set(actual) != {"method", "path", "body"} or actual.get("body") is not None:
        return False
    frozen_encoding = copy.deepcopy(dict(actual))
    frozen_encoding["body"] = {}
    return request_shape_sha256(frozen_encoding) == expected_sha256

def _restore_redacted_types(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$route_s_redacted"}:
            sentinel = value["$route_s_redacted"]
            if not isinstance(sentinel, dict):
                raise RouteSInvariantError("redaction_sentinel_invalid")
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
                raise RouteSInvariantError("redaction_original_type_invalid")
            return examples[kind]
        return {key: _restore_redacted_types(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_restore_redacted_types(child) for child in value]
    return value

def binding_scope_id(candidate_id: str, arm: str, actor_id: str, reset_epoch: str) -> str:
    value = f"{candidate_id}|{arm}|{actor_id}|{reset_epoch}|route-s-binding-scope-v1"
    return hashlib.sha256(value.encode()).hexdigest()

def validate_proven_path_change(
    expected: str, actual: str, events: Any, record: Mapping[str, Any]
) -> None:
    if not isinstance(events, list):
        raise RouteSInvariantError("path_binding_events_invalid")
    expected_parts = expected.split("/")
    actual_parts = actual.split("/")
    if len(expected_parts) != len(actual_parts):
        raise RouteSInvariantError("path_binding_segment_count_changed")
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
        raise RouteSInvariantError("path_change_not_proven_by_frozen_binding_events")

def _reject_redacted_dependencies(evidence: Mapping[str, Any]) -> None:
    predicate = evidence["candidate"]["primary_predicate"]
    producer = evidence["protocol"]["P"]
    before = tuple(
        (evidence["protocol"][slot], "response") for slot in ("Oc1", "Ot0")
    )
    after = tuple(
        (evidence["protocol"][slot], "response") for slot in ("Oc2", "Ot1")
    )
    sources: dict[str, tuple[tuple[Mapping[str, Any], str], ...]] = {
        "before": before,
        "after": after,
        "producer_request": ((producer, "request"),),
        "producer_response": ((producer, "response"),),
    }
    for reference in predicate_value_refs(predicate):
        role = str(reference.get("role") or "")
        if role.startswith("actor_before:"):
            sources[role] = before
        elif role.startswith("actor_after:"):
            sources[role] = after
    reject_redacted_predicate_dependencies(
        predicate,
        sources,
    )

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

__all__ = [
    "PROTOCOL_SLOTS",
    "RouteSInvariantError",
    "RouteSUnsupported",
    "RouteSUnavailable",
    "bind_execution_payload",
    "bind_pre_live_pins_v2",
    "binding_scope_id",
    "build_route_s_certificate",
    "build_route_s_certificate_v5",
    "canonical_json_bytes",
    "canonical_sha256",
    "derive_projection_plan_payload",
    "empty_object_no_body_shape_compatible",
    "evaluate_pair",
    "request_shape_sha256",
    "validate_artifact_manifest",
    "validate_final_seal_v2",
    "validate_partial_chain_v2",
    "validate_proven_path_change",
]
