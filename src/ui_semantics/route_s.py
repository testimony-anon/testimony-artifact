"""Historical compatibility Route-S scientific gate and certificate evaluator.

This module is deliberately pure and opt-in.  It owns no transport, target,
reset, browser, provider, or filesystem lifecycle.  A live harness may only
hand it already write-through execution evidence after a separately approved
gate.  The legacy :class:`DeterministicTwoArmVerifier` is not imported or
called here.
"""

from __future__ import annotations

import hashlib
import json
import math
import posixpath
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from .dsl import get_path, lint_predicate


PROTOCOL_SLOTS = (
    "Rc", "Sc", "Oc1", "settle_c", "Oc2",
    "Rt", "St", "Ot0", "P", "settle_t", "Ot1",
)
OBSERVATION_SLOTS = ("Oc1", "Oc2", "Ot0", "Ot1")
OBSERVER_DOMAINS = frozenset({"cookie", "token", "cache", "last_seen"})
SUPPORTED_PREDICATES = frozenset({"numeric_delta", "count_delta", "item_appears", "field_equals"})
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
    *,
    transform_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Mechanically derive the sole projection before any observation exists."""
    lint = lint_predicate(
        predicate,
        assertion=False,
        improved=True,
        enum_evidence=transform_evidence or {},
    )
    if lint.verdict != "pass" or lint.predicate is None:
        raise RouteSUnsupported(lint.reason or "predicate_lint_failed")
    kind = lint.predicate["type"]
    if kind not in SUPPORTED_PREDICATES:
        raise RouteSUnsupported("predicate_type_unsupported")
    field = "collection_path" if kind == "item_appears" else "target_path"
    path = lint.predicate.get(field)
    if not isinstance(path, str):
        raise RouteSUnsupported("projection_path_unavailable")
    for ref in _symbolic_refs(lint.predicate):
        if ref.startswith("setup."):
            raise RouteSUnsupported("setup_symbolic_operand_is_not_uniquely_defined")
    return {
        "predicate_type": kind,
        "body_path": path,
        "derived_from_field": field,
        "canonicalization": CANONICALIZATION,
        "materialized_before_observation": True,
        "result_adaptive_selection": False,
    }


def bind_projection_plan(payload: Mapping[str, Any], artifact_ref: str) -> dict[str, Any]:
    """Bind a separately written canonical payload; the hash is not self-referential."""
    if not artifact_ref:
        raise RouteSInvariantError("projection_plan_artifact_ref_empty")
    value = deepcopy(dict(payload))
    value.update({"artifact_ref": artifact_ref, "artifact_sha256": canonical_sha256(payload)})
    return value


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
) -> dict[str, Any]:
    """Recompute all Route-S gates and return a sanitized final certificate.

    The caller must schema-validate the evidence before this function and the
    returned certificate after it.  No gate or outcome supplied by a caller is
    trusted.
    """
    candidate = evidence["candidate"]
    protocol = evidence["protocol"]
    pins = evidence["pins"]
    if pins != dict(expected_pins):
        raise RouteSInvariantError("pins_not_exactly_frozen")
    _verify_evidence_artifacts(evidence, artifact_hashes)

    malformed_reasons: list[str] = []
    predicate: dict[str, Any] | None = None
    plan = evidence["projection_plan"]
    if candidate.get("predicate_type") == "unsupported" or plan.get("state") == "not_projectable":
        malformed_reasons.append(plan.get("reason_code", "predicate_unsupported"))
    else:
        lint = lint_predicate(
            candidate.get("effect_predicate"),
            assertion=False,
            improved=True,
            enum_evidence=candidate.get("transform_evidence") or {},
        )
        if lint.verdict != "pass" or lint.predicate is None:
            malformed_reasons.append(lint.reason or "predicate_lint_failed")
        else:
            predicate = lint.predicate
            if predicate["type"] != candidate.get("predicate_type"):
                malformed_reasons.append("candidate_predicate_type_mismatch")
            try:
                derived = derive_projection_plan_payload(
                    predicate,
                    transform_evidence=candidate.get("transform_evidence") or {},
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
            )
        except RouteSUnavailable as error:
            infra_reasons.append(str(error))

    evaluator_hash = pins["predicate_evaluator_sha256"]
    equivalence_hash = pins["equivalence_sha256"]
    gates = {
        "observer_pure": _gate(observer_pure_value is not None, observer_pure_value, _reason(observer_reasons, "observer_not_computed"), pins["observer_request_policy_sha256"], []),
        "stable_control": _gate(False, None, "not_computed", equivalence_hash, []),
        "baseline_equivalent": _gate(False, None, "not_computed", equivalence_hash, []),
        "supplemental_baseline": _gate(False, None, "not_computed", equivalence_hash, []),
        "control_effect_absent": _gate(False, None, "not_computed", evaluator_hash, []),
        "treatment_effect_present": _gate(False, None, "not_computed", evaluator_hash, []),
        "isolated": _gate(False, None, "not_computed", pins["session_materializer_sha256"], []),
    }

    projected = all("normalized_projection" in projection_records[slot] for slot in OBSERVATION_SLOTS)
    if projected:
        gates["stable_control"] = _equivalence_gate(projection_records["Oc1"], projection_records["Oc2"], equivalence_hash, "stable_control")
        gates["baseline_equivalent"] = _equivalence_gate(projection_records["Oc1"], projection_records["Ot0"], equivalence_hash, "baseline_equivalent")
        gates["supplemental_baseline"] = _equivalence_gate(projection_records["Oc2"], projection_records["Ot0"], equivalence_hash, "supplemental_baseline")
        try:
            phi_c, phi_c_operands, phi_c_reason = _evaluate_pair(predicate, protocol["Oc1"], protocol["Oc2"], protocol["P"])
            phi_t, phi_t_operands, phi_t_reason = _evaluate_pair(predicate, protocol["Ot0"], protocol["Ot1"], protocol["P"])
            gates["control_effect_absent"] = _gate(True, not phi_c, phi_c_reason, evaluator_hash, phi_c_operands)
            gates["treatment_effect_present"] = _gate(True, phi_t, phi_t_reason, evaluator_hash, phi_t_operands)
        except (RouteSUnavailable, RouteSUnsupported, TypeError, ValueError) as error:
            infra_reasons.append(f"predicate_operands_unavailable:{error}")

    isolated, isolation_reasons, isolation_operands, detected_reuse = _evaluate_isolation(evidence)
    gates["isolated"] = _gate(True, isolated, _reason(isolation_reasons, "isolated"), pins["session_materializer_sha256"], isolation_operands)
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
    sanitized_protocol = {slot: _sanitize_slot(slot, protocol[slot]) for slot in PROTOCOL_SLOTS}
    certificate = {
        "schema_version": "ui-semantics-route-s-certificate-v4",
        "certificate_status": "final",
        "execution_evidence_sha256": execution_evidence_sha256,
        "candidate": deepcopy(candidate),
        "projection_plan": deepcopy(plan),
        "protocol": sanitized_protocol,
        "observation_projections": projection_records,
        "gates": gates,
        "sessions": deepcopy(evidence.get("sessions", [])),
        "cross_arm_reuse_refs": deepcopy(evidence.get("cross_arm_reuse_refs", [])),
        "pins": deepcopy(pins),
        "run_attestation": deepcopy(evidence["run_attestation"]),
        "outcome": outcome,
        "outcome_precedence_version": "route-s-outcome-precedence-v5",
        "fail_closed_reasons": sorted(set(fail_reasons)),
        "completeness": {
            "required_fields_complete": True,
            "schema_validated": True,
            "artifact_hashes_verified": True,
            "secret_values_present": False,
        },
    }
    if outcome == "confirmed" and not _confirmed_complete(certificate):
        raise RouteSInvariantError("confirmed_certificate_incomplete")
    return certificate


def _project_all_observations(
    protocol: Mapping[str, Any],
    plan: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
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
        )
        all_pure = all_pure and pure
        reasons.extend(f"{slot}:{reason}" for reason in domain_reasons)
        records[slot] = {
            "raw_ref": observation["raw_ref"],
            "raw_sha256": observation["raw_sha256"],
            "observed_at": observation["finished_at"],
            "normalized_projection": deepcopy(value),
            "projection_sha256": canonical_sha256(value),
            "observer_domain_results": domain_results,
        }
    return records, all_pure, reasons


def _evaluate_observer_domains(
    domains: Any,
    artifact_hashes: Mapping[str, str],
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
        cap_ok = isinstance(ref, str) and artifact_hashes.get(ref) == item.get("capability_sha256")
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


def _evaluate_pair(
    predicate: Mapping[str, Any] | None,
    before_observation: Mapping[str, Any],
    after_observation: Mapping[str, Any],
    producer: Mapping[str, Any],
) -> tuple[bool, list[dict[str, Any]], str]:
    if predicate is None:
        raise RouteSUnsupported("predicate_unavailable")
    if any(record.get("state") != "executed" or record.get("status") != "pass" for record in (before_observation, after_observation, producer)):
        raise RouteSUnavailable("pair_protocol_slot_not_successful")
    kind = predicate["type"]
    path = predicate.get("collection_path") if kind == "item_appears" else predicate.get("target_path", "")
    before = _path_or_missing(before_observation.get("response", {}).get("body", _MISSING), path)
    after = _path_or_missing(after_observation.get("response", {}).get("body", _MISSING), path)
    if before is _MISSING or after is _MISSING:
        raise RouteSUnavailable("predicate_target_path_missing")
    operands = [
        _operand("before", before_observation["raw_ref"], "pair_before", before),
        _operand("after", after_observation["raw_ref"], "pair_after", after),
    ]
    if kind == "numeric_delta":
        source = _resolve_symbolic(predicate["value_ref"], producer, after_observation)
        expected = _apply_transform(source, predicate.get("value_transform"))
        if isinstance(before, bool) or isinstance(after, bool) or isinstance(expected, bool):
            raise RouteSUnavailable("numeric_operand_boolean")
        actual = float(after) - float(before)
        target = float(expected) * predicate["multiplier"]
        operands.extend([_operand("producer_value", producer["raw_ref"], "transform", expected), _operand("delta", after_observation["raw_ref"], "after_minus_before", actual), _operand("expected_delta", producer["raw_ref"], "value_times_multiplier", target)])
        result = math.isclose(actual, target, rel_tol=0, abs_tol=1e-9)
    elif kind == "count_delta":
        actual = len(_collection(before, predicate))
        after_count = len(_collection(after, predicate))
        delta = after_count - actual
        operands.extend([_operand("before_count", before_observation["raw_ref"], "collection_count", actual), _operand("after_count", after_observation["raw_ref"], "collection_count", after_count), _operand("expected_delta", "predicate", "equals", predicate["equals"])])
        result = delta == predicate["equals"]
    elif kind == "item_appears":
        expected = {field: _resolve_symbolic(ref, producer, after_observation) for field, ref in sorted(predicate["match_fields"].items())}
        before_count = _match_count(_collection(before, predicate), expected)
        after_count = _match_count(_collection(after, predicate), expected)
        operands.extend([_operand("expected_item", producer["raw_ref"], "match_fields", expected), _operand("before_matches", before_observation["raw_ref"], "match_count", before_count), _operand("after_matches", after_observation["raw_ref"], "match_count", after_count)])
        result = after_count - before_count == 1
    elif kind == "field_equals":
        expected = _apply_transform(_resolve_symbolic(predicate["value_ref"], producer, after_observation), predicate.get("value_transform"))
        transition = _transition_matches(before, after, predicate.get("value_transform"))
        operands.extend([_operand("expected", producer["raw_ref"], "transform", expected), _operand("transition", after_observation["raw_ref"], "before_after_transition", transition)])
        result = after == expected and before != after and transition
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
    value = canonical_json_bytes(left["normalized_projection"]) == canonical_json_bytes(right["normalized_projection"])
    operands = [
        _operand(f"{name}_left", left["raw_ref"], "canonical_equivalence", left["normalized_projection"]),
        _operand(f"{name}_right", right["raw_ref"], "canonical_equivalence", right["normalized_projection"]),
    ]
    return _gate(True, value, "equivalent" if value else "not_equivalent", evaluator_hash, operands)


def _gate(computed: bool, value: bool | None, reason: str, evaluator_hash: str, operands: list[dict[str, Any]]) -> dict[str, Any]:
    return {"computed": computed, "value": value if computed else None, "reason_code": reason, "evaluator_sha256": evaluator_hash, "operands": operands}


def _operand(name: str, raw_ref: str, operator: str, value: Any) -> dict[str, Any]:
    return {"name": name, "raw_ref": raw_ref, "operator": operator, "normalization_rule": CANONICALIZATION, "normalized_value": deepcopy(value), "normalized_value_sha256": canonical_sha256(value)}


def _sanitize_slot(slot: str, record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("state") == "not_executed":
        return {key: deepcopy(record[key]) for key in ("slot", "state", "reason_code")}
    common = {key: deepcopy(record[key]) for key in ("slot", "state", "raw_ref", "raw_sha256", "started_at", "finished_at", "status", "arm")}
    if record.get("status") == "failed":
        common.update({key: deepcopy(record[key]) for key in ("error_ref", "error_sha256", "reason_code")})
        return common
    if slot in {"Rc", "Rt"}:
        common["reset_epoch"] = record["reset_epoch"]
    elif slot in {"Sc", "St"}:
        common["provenance_refs"] = deepcopy(record["provenance_refs"])
    elif slot in OBSERVATION_SLOTS:
        common.update({"actor_id": record["actor_id"], "request_sha256": canonical_sha256(record["request"]), "response_sha256": canonical_sha256(record["response"])})
    elif slot == "P":
        common.update({"actor_id": record["actor_id"], "action_ref": record["action_ref"], "request_ref": record["request_ref"], "request_sha256": canonical_sha256(record["request"]), "response_sha256": canonical_sha256(record["response"])})
    else:
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
    if isinstance(predicate.get("value_ref"), str):
        yield predicate["value_ref"]
    for value in (predicate.get("match_fields") or {}).values():
        if isinstance(value, str):
            yield value


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


__all__ = [
    "CANONICALIZATION", "OBSERVER_DOMAINS", "OUTCOME_PRECEDENCE", "PROTOCOL_SLOTS",
    "RouteSInvariantError", "RouteSUnavailable", "RouteSUnsupported",
    "bind_projection_plan", "build_route_s_certificate", "canonical_json_bytes",
    "canonical_sha256", "derive_projection_plan_payload", "validate_artifact_manifest",
    "validate_final_seal", "validate_partial_chain", "validate_scan_report",
]
