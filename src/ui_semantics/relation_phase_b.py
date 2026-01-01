"""Deterministic Phase-B conversion of sealed semantic relations into API tests.

The converter is intentionally subject-neutral: it consumes request references,
certificates, bindings, projections, and predicates.  A Stage6 runtime adapter is
responsible for resolving those request references against a frozen trace.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Iterable, Mapping

from common.contracts import make_envelope, validate_artifact
from ui_semantics.dsl import SEMANTIC_TYPES, get_path, lint_predicate


BUSINESS_ASSERTION_TYPES = frozenset(SEMANTIC_TYPES)
GENERIC_ASSERTION_TYPES = frozenset(
    {"status_success", "status_class", "schema_type"}
)
CONSTRAINT_CHECKS = (
    "source_hash_closure",
    "confirmed_outcome",
    "request_binding_complete",
    "actor_session_closed",
    "fresh_value_binding_closed",
    "projection_complete",
    "predicate_lint_pass",
    "reset_isolation_closed",
    "safe_execution_closed",
)
BUSINESS_EVALUATOR = "ui_semantics.current_route_s.core.evaluate_pair"
_RETAINED_SOURCE_KEYS = (
    "candidate",
    "execution_material",
    "execution_evidence",
    "certificate",
    "normalized_candidate_sha256",
)


class RelationBlueprintError(RuntimeError):
    """A rendered relation test violates the frozen conversion rules."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _validate_current_relation_input_closure(closure: Mapping[str, Any]) -> None:
    if closure.get("schema_version") != "certified-relation-input-closure-current-v2":
        raise RelationBlueprintError("current_relation_input_closure_version_required")
    confirmed = closure.get("confirmed")
    if not isinstance(confirmed, list):
        raise RelationBlueprintError("current_relation_confirmed_rows_invalid")
    if closure.get("confirmed_count") != len(confirmed):
        raise RelationBlueprintError("current_relation_confirmed_count_drift")
    for item in confirmed:
        if not isinstance(item, Mapping):
            raise RelationBlueprintError("current_relation_confirmed_row_invalid")
        if (item.get("protocol_kind"), item.get("claim_kind")) not in {
            ("V1", "causal_confirmed"),
            ("V2", "single_state_confirmed"),
            ("V9", "joint_observation_confirmed"),
            ("V8", "temporal_observation_confirmed"),
            ("V3", "metamorphic_confirmed"),
            ("V4", "workflow_confirmed"),
            ("V5", "repeated_execution_confirmed"),
            ("V6", "negative_behavior_confirmed"),
            ("V7", "actor_relation_confirmed"),
        }:
            raise RelationBlueprintError("current_relation_protocol_not_registered")
        source = item.get("source")
        if not isinstance(source, Mapping) or set(source) != set(_RETAINED_SOURCE_KEYS):
            raise RelationBlueprintError("current_relation_source_shape_invalid")
        for key in _RETAINED_SOURCE_KEYS[:-1]:
            ref = source[key]
            if (
                not isinstance(ref, Mapping)
                or set(ref) != {"path", "sha256"}
                or not all(isinstance(ref[field], str) and ref[field] for field in ref)
            ):
                raise RelationBlueprintError("current_relation_file_ref_invalid")
        candidate_sha256 = source["normalized_candidate_sha256"]
        if (
            not isinstance(candidate_sha256, str)
            or len(candidate_sha256) != 64
            or any(character not in "0123456789abcdef" for character in candidate_sha256)
        ):
            raise RelationBlueprintError("current_relation_candidate_sha256_invalid")


def build_certified_relation_tests(
    closure: Mapping[str, Any],
    *,
    run_id: str,
    normal_runs: int = 1,
    created_at: str | None = None,
) -> dict[str, Any]:
    _validate_current_relation_input_closure(closure)
    if normal_runs < 1:
        raise ValueError("normal_runs must be positive")
    upstream = closure["upstream"]
    tests = [
        (
            _render_observation_plan_test(item, normal_runs=normal_runs)
            if item["protocol_kind"] in {"V8", "V9"}
            else _render_single_state_test(item, normal_runs=normal_runs)
            if item["protocol_kind"] == "V2"
            else
            _render_explicit_plan_test(item, normal_runs=normal_runs)
            if item["protocol_kind"] == "V5" or item["protocol_kind"] == "V6" and item["negative_kind"] == "rejection"
            else
            _render_single_arm_test(item, normal_runs=normal_runs)
            if item["protocol_kind"] in {"V3", "V4", "V6", "V7"}
            else _render_test(item, normal_runs=normal_runs)
        )
        for item in closure["confirmed"]
    ]
    metadata = make_envelope(
        "certified_relation_tests",
        "stage5",
        run_id,
        upstream_refs=[
            {
                "artifact_type": "test_execution_report",
                "run_id": str(closure["run_plan_id"]),
                "path": upstream["run_report"]["path"],
            }
        ],
    )
    if created_at is not None:
        metadata["created_at"] = created_at
    document = {
        "metadata": metadata,
        "source_input": {
            "run_report": copy.deepcopy(upstream["run_report"]),
            "confirmed_set_sha256": closure["confirmed_set_sha256"],
            "confirmed_count": closure["confirmed_count"],
        },
        "assertion_definition": {
            "business_types": sorted(BUSINESS_ASSERTION_TYPES),
            "generic_types": sorted(GENERIC_ASSERTION_TYPES),
            "reference_translation_policy": "alpha_rename_observation_refs_only_v1",
            "business_evaluator": closure["implementation_pins"]["business_evaluator"],
            "business_evaluator_source": copy.deepcopy(
                closure["implementation_pins"]["business_evaluator_source"]
            ),
            "normal_runs": normal_runs,
        },
        "tests": tests,
    }
    validate_artifact("certified_relation_tests.schema.json", document)
    validate_certified_relation_tests(document)
    return document


def validate_certified_relation_tests(document: Mapping[str, Any]) -> None:
    validate_artifact("certified_relation_tests.schema.json", document)
    tests = document["tests"]
    if len(tests) != document["source_input"]["confirmed_count"]:
        raise RelationBlueprintError("test_count_does_not_match_confirmed_input")
    _require_unique((item["test_id"] for item in tests), "test_id")
    _require_unique((item["candidate_id"] for item in tests), "candidate_id")
    assertion_ids: list[str] = []
    for test in tests:
        if (test["protocol_kind"], test["claim_kind"]) not in {
            ("V1", "causal_confirmed"),
            ("V2", "single_state_confirmed"),
            ("V9", "joint_observation_confirmed"),
            ("V8", "temporal_observation_confirmed"),
            ("V3", "metamorphic_confirmed"),
            ("V4", "workflow_confirmed"),
            ("V5", "repeated_execution_confirmed"),
            ("V6", "negative_behavior_confirmed"),
            ("V7", "actor_relation_confirmed"),
        }:
            raise RelationBlueprintError("current_test_protocol_not_registered")
        if test["eligible"] is not (test["constraint"]["status"] == "complete"):
            raise RelationBlueprintError("eligibility_constraint_mismatch")
        blueprint = test["blueprint"]
        if test["protocol_kind"] == "V2":
            if (
                blueprint["producer"] is not None
                or "before_observer" in blueprint
                or len(blueprint.get("observation_plan", [])) != 1
                or blueprint["observation_plan"][0].get("role") != "observation"
                or any(blueprint["observation_plan"][0].get(key) != value for key, value in blueprint["observer"].items())
                or blueprint["producer_binding_requirement"]["events"]
                or blueprint["observer_binding_requirement"]["before"]["events"]
            ):
                raise RelationBlueprintError("single_state_blueprint_invalid")
        elif test["protocol_kind"] in {"V8", "V9"}:
            if len(blueprint["observation_plan"]) < (1 if test["protocol_kind"] == "V8" else 2):
                raise RelationBlueprintError("joint_observation_plan_unclosed")
            previous = []
            for step in blueprint["observation_plan"]:
                _validate_binding_requirement(step["binding_requirement"], endpoint=step["endpoint"], setup=blueprint["setup"], runtime_creators=previous)
                previous.append(step["endpoint"])
        elif blueprint["producer"] is None:
            raise RelationBlueprintError("action_protocol_producer_missing")
        retained_refs = [
            test["source"][key]
            for key in _RETAINED_SOURCE_KEYS
            if key != "normalized_candidate_sha256"
        ]
        if {
            canonical_sha256(ref) for ref in blueprint["provenance_refs"]
        } != {canonical_sha256(ref) for ref in retained_refs}:
            raise RelationBlueprintError("retained_provenance_ref_set_drift")
        before_observer = blueprint.get("before_observer")
        query_plan = (
            blueprint["query_plan"] if test["protocol_kind"] == "V3" else []
        )
        _validate_binding_requirement(
            blueprint["producer_binding_requirement"],
            endpoint=blueprint["producer"] or blueprint["observer"],
            setup=blueprint["setup"],
            runtime_creators=(
                _strictly_preceding_query_endpoints(
                    query_plan, blueprint["producer"]
                )
                if query_plan
                else (before_observer,)
                if isinstance(before_observer, Mapping)
                else ()
            ),
        )
        before_requirement = blueprint["observer_binding_requirement"]["before"]
        after_requirement = blueprint["observer_binding_requirement"]["after"]
        create_capture_read = (
            test["protocol_kind"] == "V4"
            and blueprint.get("workflow_kind") == "create_capture_read"
        )
        _validate_binding_requirement(
            before_requirement,
            endpoint=before_observer or blueprint["observer"],
            setup=blueprint["setup"],
            runtime_creators=(
                _strictly_preceding_query_endpoints(
                    query_plan, before_observer or blueprint["observer"]
                )
                if query_plan
                else ()
            ),
        )
        _validate_binding_requirement(
            after_requirement,
            endpoint=blueprint["observer"],
            setup=blueprint["setup"],
            runtime_creators=(
                _strictly_preceding_query_endpoints(
                    query_plan, blueprint["observer"]
                )
                if query_plan
                else (blueprint["producer"],)
                if create_capture_read
                else ()
            ),
        )
        if test["protocol_kind"] == "V3":
            query_requirements = blueprint["query_binding_requirements"]
            _validate_query_binding_requirements(
                query_plan,
                query_requirements,
                setup=blueprint["setup"],
            )
        if (
            test["protocol_kind"] == "V1"
            and canonical_sha256(before_requirement) != canonical_sha256(after_requirement)
        ):
            raise RelationBlueprintError("observer_before_after_binding_requirement_drift")
        checks = test["constraint"]["checks"]
        if tuple(sorted(checks)) != tuple(sorted(CONSTRAINT_CHECKS)):
            raise RelationBlueprintError("constraint_check_set_drift")
        if test["constraint"]["status"] == "complete" and not all(checks.values()):
            raise RelationBlueprintError("complete_constraint_contains_false_check")
        business_count = 0
        generic_types: list[str] = []
        for assertion in test["assertions"]:
            assertion_ids.append(assertion["assertion_id"])
            if assertion["predicate_type"] != assertion["predicate"].get("family", assertion["predicate"].get("type")):
                raise RelationBlueprintError("assertion_predicate_type_mismatch")
            definition = {key: copy.deepcopy(value) for key, value in assertion.items() if key != "definition_sha256"}
            if canonical_sha256(definition) != assertion["definition_sha256"]:
                raise RelationBlueprintError("assertion_definition_sha256_mismatch")
            if canonical_sha256(assertion["predicate"]) != assertion["rendered_predicate_sha256"]:
                raise RelationBlueprintError("rendered_predicate_sha256_mismatch")
            kind = assertion["predicate_type"]
            expected_class = "business" if kind in BUSINESS_ASSERTION_TYPES else "generic"
            if assertion["assertion_class"] != expected_class:
                raise RelationBlueprintError("assertion_class_mismatch")
            lint = lint_predicate(assertion["predicate"], assertion=True)
            if lint.verdict != "pass":
                raise RelationBlueprintError("rendered_predicate_lint_failed")
            if not {
                canonical_sha256(ref) for ref in assertion["evidence_refs"]
            } <= {canonical_sha256(ref) for ref in retained_refs}:
                raise RelationBlueprintError("assertion_evidence_ref_not_retained")
            if expected_class == "business":
                business_count += 1
                _validate_alpha_translation(assertion)
            else:
                generic_types.append(kind)
        if business_count < 1:
            raise RelationBlueprintError("test_has_no_business_assertion")
        expected_generic_types = (
            ["status_success"] * (len(blueprint["observation_plan"]) + int(blueprint["producer"] is not None))
            if test["protocol_kind"] in {"V8", "V9"} else
            sorted(assertion["predicate_type"] for assertion in _explicit_generic_assertions(test["candidate_id"], blueprint["execution_steps"], test["assertions"][0]["source_predicate_sha256"], test["source"], test["protocol_kind"], blueprint.get("repetition_kind")))
            if test["protocol_kind"] == "V5"
            else ["status_class"] if test["protocol_kind"] == "V6" and blueprint["negative_kind"] == "rejection"
            else ["status_class", "status_success"] if _point_rejection_observation(test["assertions"][0]["predicate"])
            else ["schema_type", "status_success", "status_success", "status_success", "status_success"] if blueprint.get("workflow_kind") == "inverse_restoration"
            else
            ["schema_type", "status_success"]
            if test["protocol_kind"] == "V2"
            else
            ["schema_type", "status_class", "status_success", "status_success"]
            if test["protocol_kind"] == "V6"
            else ["schema_type", "status_success", "status_success"]
        )
        expected_generic_types = list(expected_generic_types)
        projection_schema = blueprint.get("projection_schema") or {}
        if (
            projection_schema.get("status") == "unaddressed_in_recorded_observation"
            and "schema_type" in expected_generic_types
        ):
            # The renderer pins no JSON type for a projection path the recorded
            # body does not address (see _render_single_state_test and
            # _render_single_arm_test); the blueprint records that decision.
            expected_generic_types.remove("schema_type")
        if sorted(generic_types) != expected_generic_types:
            raise RelationBlueprintError("generic_assertion_definition_drift")
    _require_unique(assertion_ids, "assertion_id")


def _validate_binding_requirement(
    requirement: Mapping[str, Any],
    *,
    endpoint: Mapping[str, Any],
    setup: Iterable[Mapping[str, Any]],
    runtime_creators: Iterable[Mapping[str, Any]] = (),
) -> None:
    events = requirement["events"]
    if requirement["event_count"] != len(events):
        raise RelationBlueprintError("binding_requirement_event_count_drift")
    if set(requirement["source_ids"]) != {event["source_id"] for event in events}:
        raise RelationBlueprintError("binding_requirement_source_set_drift")
    if requirement["scope_derivation"] != "candidate_arm_actor_reset_epoch_v1":
        raise RelationBlueprintError("binding_requirement_scope_derivation_drift")
    setup_refs = {
        (row["actor_id"], row["request_ref"])
        for row in (*setup, *runtime_creators)
    }
    for event in events:
        if (
            event["actor_id"] != endpoint["actor_id"]
            or event["consumer_request_ref"] != endpoint["request_ref"]
        ):
            raise RelationBlueprintError("binding_requirement_endpoint_drift")
        if (event["creator_actor_id"], event["creator_request_ref"]) not in setup_refs:
            raise RelationBlueprintError("binding_requirement_creator_not_in_setup")


def _validate_query_binding_requirements(
    query_plan: list[Mapping[str, Any]],
    query_requirements: Mapping[str, Mapping[str, Any]],
    *,
    setup: Iterable[Mapping[str, Any]],
) -> None:
    if set(query_requirements) != {row["role"] for row in query_plan}:
        raise RelationBlueprintError("query_binding_requirement_roles_drift")
    for query_index, endpoint in enumerate(query_plan):
        _validate_binding_requirement(
            query_requirements[endpoint["role"]],
            endpoint=endpoint,
            setup=setup,
            runtime_creators=tuple(query_plan[:query_index]),
        )


def _strictly_preceding_query_endpoints(
    query_plan: list[Mapping[str, Any]],
    endpoint: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    matches = [
        index
        for index, row in enumerate(query_plan)
        if row["actor_id"] == endpoint["actor_id"]
        and row["request_ref"] == endpoint["request_ref"]
    ]
    if len(matches) != 1:
        raise RelationBlueprintError("query_binding_requirement_endpoint_drift")
    return tuple(query_plan[:matches[0]])


def generic_baseline_overlap(
    primary: Mapping[str, Any], generic: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Associate same-field checks without claiming equivalent verdicts.

    Presence permits other types, and missing fields fail P01/P21 while the
    generic type check is inconclusive. These links cannot justify deduplication.
    """
    target = primary.get("target") or {}
    if target.get("role") != "observation":
        return []
    return [
        {
            "generic_assertion_ids": [str(row["assertion_id"])],
            "overlap_kind": "same_field_partial_overlap",
            "full_verdict_equivalent": False,
            "usable_for_net_increment_deduplication": False,
        }
        for row in generic
        if row["predicate"].get("type") == "schema_type"
        and row["predicate"].get("response_ref") == "observation"
        and row["predicate"].get("target_path") == target.get("path")
        and (
            primary["family"] == "P01"
            and primary.get("operator") == "present"
            or primary["family"] == "P21"
            and primary.get("expected_type") == row["predicate"].get("expected_type")
        )
    ]


def assertion_layer_summary(tests: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Report semantic layers independently from the existing assertion container."""
    rows = list(tests)
    overlap = []
    classifications = []
    for test in rows:
        primary = next(
            row["predicate"]
            for row in test["assertions"]
            if row["assertion_class"] == "business"
        )
        classifications.append({"candidate_id": test["candidate_id"], **classify_assertion_layer(test["protocol_kind"], primary)})
        associations = generic_baseline_overlap(
            primary,
            (row for row in test["assertions"] if row["assertion_class"] == "generic"),
        )
        overlap.extend(
            {"candidate_id": test["candidate_id"], **association}
            for association in associations
        )
    return {
        "generic_baseline_assertion_count": sum(
            row["assertion_class"] == "generic"
            for test in rows
            for row in test["assertions"]
        ),
        "basic_constraint_candidate_ids": [
            row["candidate_id"] for row in classifications if row["assertion_layer"] == "basic_constraint"
        ],
        "business_relation_candidate_ids": [
            row["candidate_id"] for row in classifications if row["assertion_layer"] == "business_relation"
        ],
        "classification_basis": classifications,
        "generic_baseline_overlap": overlap,
    }


def classify_assertion_layer(protocol_kind: str, primary: Mapping[str, Any]) -> dict[str, Any]:
    """Classify the frozen complete proposition without consulting its rationale."""
    parameters: list[dict[str, Any]] = []
    if protocol_kind == "V2" and primary.get("family") == "forall":
        body = primary.get("body") or {}
        target = body.get("left") or body.get("target") or {}
        if target.get("role") == "item" and body.get("family") in {"P02", "P03", "P09", "P11"}:
            for key in ("right", "lower", "upper", "domain"):
                operand = body.get(key)
                if isinstance(operand, Mapping) and operand.get("source") == "request":
                    reference = operand.get("ref") or {}
                    if reference.get("role") == "observation_request":
                        parameters.append({"operand": key, **copy.deepcopy(reference)})
    if primary.get("family") in {"P08", "P19"}:
        return {"assertion_layer": "business_relation", "basis": "field_arithmetic_or_aggregate_summary", "claim_source": "frozen_candidate_hypothesis", "request_parameters": parameters}
    if parameters:
        return {
            "assertion_layer": "business_relation",
            "basis": "forall_body_compares_member_with_actual_request_parameter",
            "claim_source": "frozen_candidate_hypothesis",
            "request_parameters": parameters,
        }
    return {
        "assertion_layer": "basic_constraint" if protocol_kind == "V2" else "business_relation",
        "basis": "single_response_constraint" if protocol_kind == "V2" else "action_or_query_relation",
        "claim_source": "frozen_candidate_hypothesis",
        "request_parameters": [],
    }


def summarize_generation(document: Mapping[str, Any], closure: Mapping[str, Any]) -> dict[str, Any]:
    from .dsl import is_workflow_effect_predicate
    tests = document["tests"]
    assertions = [assertion for test in tests for assertion in test["assertions"]]
    business = [item for item in assertions if item["assertion_class"] == "business"]
    generic = [item for item in assertions if item["assertion_class"] == "generic"]
    eligible = [item for item in tests if item["eligible"]]
    dropped = [item for item in tests if not item["eligible"] and item["constraint"]["reason"]]
    return {
        "schema_version": "certified-relation-generation-report-v1",
        **({"assertion_layers": assertion_layer_summary(tests)} if any(test["protocol_kind"] == "V2" or test["protocol_kind"] == "V4" and any(row["assertion_class"] == "business" and is_workflow_effect_predicate(row["predicate"]) for row in test["assertions"]) for test in tests) else {}),
        "status": "PASS" if len(eligible) + len(dropped) == len(tests) else "STOP",
        "candidate_denominator": {
            "confirmed_input": closure["confirmed_count"],
            "blueprint_generated": len(tests),
            "constraint_complete": sum(item["constraint"]["status"] == "complete" for item in tests),
            "stage6_test_generated": len(tests),
            "executable_eligible": len(eligible),
            "conversion_dropped": len(dropped),
            "conversion_inconclusive": len(tests) - len(eligible) - len(dropped),
        },
        "test_denominator": {
            "test_case_count": len(tests),
            "eligible_test_count": len(eligible),
            "tests_with_business_assertion": sum(
                any(assertion["assertion_class"] == "business" for assertion in item["assertions"])
                for item in tests
            ),
        },
        "assertion_definition_denominator": {
            "total": len(assertions),
            "business": len(business),
            "generic_status_schema": len(generic),
            "generic_status": sum(item["predicate_type"] == "status_success" for item in generic),
            "generic_schema": sum(item["predicate_type"] == "schema_type" for item in generic),
        },
        "predicate_distribution": dict(sorted(Counter(item["predicate_type"] for item in business).items())),
        "dropped_reasons": dict(sorted(Counter(item["constraint"]["reason"] for item in dropped).items())),
        "inconclusive_reasons": {},
        "provider_llm_calls": 0,
    }


def _render_test(item: Mapping[str, Any], *, normal_runs: int) -> dict[str, Any]:
    candidate_id = item["candidate_id"]
    candidate = copy.deepcopy(item["candidate"])
    binding = copy.deepcopy(item["binding"])
    inner = item["certificate_inner"]
    source_predicate = copy.deepcopy(candidate["primary_predicate"])
    lint = lint_predicate(
        source_predicate,
        assertion=False,
    )
    rendered_predicate, translation = _render_business_predicate(lint.predicate or source_predicate)
    source_hash = canonical_sha256(source_predicate)
    source_refs = item["source"]
    certificate_ref = copy.deepcopy(source_refs["certificate"])
    candidate_ref = copy.deepcopy(source_refs["candidate"])
    material_ref = copy.deepcopy(source_refs["execution_material"])
    projection_ref = material_ref
    binding_ref = material_ref
    observer_policy = item["observer_policy"]
    assertions = [
        _assertion(
            assertion_id=f"{candidate_id}-business-01",
            assertion_class="business",
            assertion_source="semantic_relation",
            predicate=rendered_predicate,
            source_predicate_sha256=source_hash,
            reference_translation=translation,
            evidence_refs=[certificate_ref, candidate_ref, projection_ref],
        ),
        _assertion(
            assertion_id=f"{candidate_id}-generic-producer-status",
            assertion_class="generic",
            assertion_source="protocol_derived",
            predicate={"type": "status_success", "response_ref": "producer"},
            source_predicate_sha256=canonical_sha256(
                {"derivation": "producer_transport_status", "candidate": source_hash}
            ),
            reference_translation={},
            evidence_refs=[certificate_ref, binding_ref],
        ),
        _assertion(
            assertion_id=f"{candidate_id}-generic-observer-status",
            assertion_class="generic",
            assertion_source="protocol_derived",
            predicate={"type": "status_success", "response_ref": "after"},
            source_predicate_sha256=canonical_sha256(
                {"derivation": "post_observer_transport_status", "candidate": source_hash}
            ),
            reference_translation={},
            evidence_refs=[certificate_ref, binding_ref],
        ),
        _assertion(
            assertion_id=f"{candidate_id}-generic-projection-schema",
            assertion_class="generic",
            assertion_source="protocol_derived",
            predicate={
                "type": "schema_type",
                "response_ref": "after",
                "target_path": str(item["projection"]["body_path"]),
                "expected_type": _json_type(
                    inner["observation_projections"]["Ot1"]["normalized_projection"]
                ),
            },
            source_predicate_sha256=canonical_sha256(
                {
                    "derivation": "sealed_projection_json_type",
                    "projection_sha256": projection_ref["sha256"],
                }
            ),
            reference_translation={},
            evidence_refs=[certificate_ref, projection_ref],
        ),
    ]

    setup = copy.deepcopy(candidate.get("setup") or [])
    producer = {
        **copy.deepcopy(candidate["producer"]),
        "method": binding["producer"]["method"],
        "path": binding["producer"]["path"],
        "request_shape_sha256": binding["producer"]["request_shape_sha256"],
    }
    observer_binding = binding["observations"]["Ot0"]
    observer = {
        **copy.deepcopy(candidate["consumer"]),
        "method": observer_binding["method"],
        "path": observer_binding["path"],
        "request_shape_sha256": observer_binding["request_shape_sha256"],
    }
    actors = sorted(
        {
            producer["actor_id"],
            observer["actor_id"],
            *(row["actor_id"] for row in setup),
        }
    )
    sessions = {
        row["actor_id"]
        for row in inner.get("sessions", [])
        if row.get("arm") == "treatment" and row.get("secret_values_present") is False
    }
    request_attestation = inner.get("gates", {}).get("isolated") or {}
    binding_attestation = item["certificate_inner"].get("gates", {}).get("treatment_effect_present") or {}
    producer_binding_attestation = item["request_binding_attestation"].get("P") or {}
    observer_before_attestation = item["request_binding_attestation"].get("Ot0") or {}
    observer_after_attestation = item["request_binding_attestation"].get("Ot1") or {}
    runtime_binding_requirements = item["runtime_binding_requirements"]
    checks = {
        "source_hash_closure": True,
        "confirmed_outcome": item["outcome"] == "confirmed" and inner.get("outcome") == "confirmed",
        "request_binding_complete": all(
            isinstance(row.get(key), str) and bool(row[key])
            for row in (producer, observer)
            for key in ("actor_id", "request_ref", "method", "path", "request_shape_sha256")
        ),
        "actor_session_closed": set(actors).issubset(sessions),
        "fresh_value_binding_closed": _fresh_value_binding_closed(
            request_attestation=request_attestation,
            runtime_binding_requirements=runtime_binding_requirements,
            attestations={
                "P": producer_binding_attestation,
                "Ot0": observer_before_attestation,
                "Ot1": observer_after_attestation,
            },
        ),
        "projection_complete": bool(item["projection"].get("body_path")) and bool(item["projection"].get("predicate_family")),
        "predicate_lint_pass": lint.verdict == "pass",
        "reset_isolation_closed": request_attestation.get("value") is True,
        "safe_execution_closed": (
            binding_attestation.get("computed") is True
            and inner.get("completeness", {}).get("secret_values_present") is False
        ),
    }
    status = "complete" if all(checks.values()) else "incomplete"
    reason = None if status == "complete" else "constraint_checks_incomplete"
    return {
        "test_id": "relation-test-" + canonical_sha256(
            {
                "candidate_id": candidate_id,
                "normalized_candidate_sha256": source_refs[
                    "normalized_candidate_sha256"
                ],
            }
        )[:20],
        "candidate_id": candidate_id,
        "protocol_kind": item["protocol_kind"],
        "claim_kind": item["claim_kind"],
        "source": {
            key: copy.deepcopy(source_refs[key])
            for key in _RETAINED_SOURCE_KEYS
        },
        "blueprint": {
            "actors": actors,
            "setup": setup,
            "producer": producer,
            "observer": observer,
            "producer_binding_requirement": {
                "event_count": producer_binding_attestation.get("binding_event_count"),
                "source_ids": sorted(producer_binding_attestation.get("source_ids") or []),
                "scope_derivation": "candidate_arm_actor_reset_epoch_v1",
                "rule": producer_binding_attestation.get("binding_rule"),
                "events": copy.deepcopy(runtime_binding_requirements["P"]),
            },
            "observer_binding_requirement": {
                "before": {
                    "event_count": observer_before_attestation.get("binding_event_count"),
                    "source_ids": sorted(observer_before_attestation.get("source_ids") or []),
                    "scope_derivation": "candidate_arm_actor_reset_epoch_v1",
                    "rule": observer_before_attestation.get("binding_rule"),
                    "events": copy.deepcopy(runtime_binding_requirements["Ot0"]),
                },
                "after": {
                    "event_count": observer_after_attestation.get("binding_event_count"),
                    "source_ids": sorted(observer_after_attestation.get("source_ids") or []),
                    "scope_derivation": "candidate_arm_actor_reset_epoch_v1",
                    "rule": observer_after_attestation.get("binding_rule"),
                    "events": copy.deepcopy(runtime_binding_requirements["Ot1"]),
                },
            },
            "settle_policy": copy.deepcopy(item["settle_policy"]),
            "observer_purity_policy": {
                "domains": sorted(observer_policy["purity_domains_exact_set"]),
            },
            "provenance_refs": [
                copy.deepcopy(source_refs[key])
                for key in _RETAINED_SOURCE_KEYS
                if key != "normalized_candidate_sha256"
            ],
        },
        "constraint": {"status": status, "checks": checks, "reason": reason},
        "assertions": assertions,
        "normal_runs": normal_runs,
        "eligible": status == "complete",
        "eligibility_reason": reason,
    }


def _render_observation_plan_test(item: Mapping[str, Any], *, normal_runs: int) -> dict[str, Any]:
    candidate_id = item["candidate_id"]
    temporal = item["protocol_kind"] == "V8"
    predicate = copy.deepcopy(item["candidate"]["primary_predicate"])
    source = copy.deepcopy(item["source"])
    refs = [copy.deepcopy(source[key]) for key in _RETAINED_SOURCE_KEYS if key != "normalized_candidate_sha256"]
    fields = ("actor_id", "request_ref", "method", "path", "request_shape_sha256")
    plan = [{**copy.deepcopy(step), "endpoint": {key: item["binding"]["observations"][step["role"]][key] for key in fields},
             "binding_requirement": _binding_requirement(item["runtime_binding_requirements"][step["role"]])} for step in item["protocol_plan"]]
    producer = {key: item["binding"]["producer"][key] for key in fields} if item["binding"].get("producer") is not None else None
    setup = copy.deepcopy(item["candidate"].get("setup") or [])
    actors = sorted({step["actor"] for step in plan} | {row["actor_id"] for row in setup} | ({producer["actor_id"]} if producer else set()))
    source_hash = canonical_sha256(predicate)
    assertions = [_assertion(assertion_id=f"{candidate_id}-business-01", assertion_class="business", assertion_source="semantic_relation", predicate=predicate,
        source_predicate_sha256=source_hash, reference_translation={}, evidence_refs=refs)]
    for role in [step["role"] for step in plan] + (["producer"] if producer else []):
        assertions.append(_assertion(assertion_id=f"{candidate_id}-generic-{role}", assertion_class="generic", assertion_source="protocol_derived",
            predicate={"type": "status_success", "response_ref": role}, source_predicate_sha256=canonical_sha256({"derivation": role, "candidate": source_hash}), reference_translation={}, evidence_refs=refs))
    checks = dict.fromkeys(("source_hash_closure", "confirmed_outcome", "request_binding_complete", "actor_session_closed", "fresh_value_binding_closed", "projection_complete", "predicate_lint_pass", "reset_isolation_closed", "safe_execution_closed"), True)
    checks["predicate_lint_pass"] = lint_predicate(predicate, assertion=False).verdict == "pass"
    checks["safe_execution_closed"] = all(item["certificate_inner"]["qualification_gates"].values())
    eligible = all(checks.values())
    return {"test_id": "relation-test-" + canonical_sha256({"candidate_id": candidate_id, "normalized_candidate_sha256": source["normalized_candidate_sha256"]})[:20],
        "candidate_id": candidate_id, "protocol_kind": item["protocol_kind"], "claim_kind": item["claim_kind"], "source": source,
        "blueprint": {"actors": actors, "setup": setup, "producer": producer, "observer": plan[-1]["endpoint"],
            "observation_plan": plan,
            **({"time_requirement": copy.deepcopy(item["time_requirement"]), "identity_topology": copy.deepcopy(item["identity_topology"])} if temporal else {"joint_observation": copy.deepcopy(item["joint_observation"])}),
            **({"before_observer": {key: item["binding"]["observations"]["workflow_before"][key] for key in fields}} if temporal and "workflow_before" in item["binding"]["observations"] else {}),
            "producer_binding_requirement": _binding_requirement(item["runtime_binding_requirements"].get("P", [])),
            "observer_binding_requirement": {"before": _binding_requirement(item["runtime_binding_requirements"].get("before", [])), "after": plan[-1]["binding_requirement"]},
            "settle_policy": copy.deepcopy(item["settle_policy"]), "observer_purity_policy": {"domains": sorted(item["observer_policy"]["purity_domains_exact_set"])}, "provenance_refs": refs},
        "constraint": {"status": "complete" if eligible else "incomplete", "checks": checks, "reason": None if eligible else "constraint_checks_incomplete"},
        "assertions": assertions, "normal_runs": normal_runs, "eligible": eligible, "eligibility_reason": None if eligible else "constraint_checks_incomplete"}


def _render_single_state_test(
    item: Mapping[str, Any], *, normal_runs: int
) -> dict[str, Any]:
    candidate_id = str(item["candidate_id"])
    predicate = copy.deepcopy(item["candidate"]["primary_predicate"])
    lint = lint_predicate(predicate, assertion=False)
    source = copy.deepcopy(item["source"])
    binding = item["binding"]["observations"]["observation"]
    endpoint = {
        key: copy.deepcopy(binding[key])
        for key in ("actor_id", "request_ref", "method", "path", "request_shape_sha256")
    }
    setup = copy.deepcopy(item["candidate"].get("setup") or [])
    actors = sorted({endpoint["actor_id"], *(row["actor_id"] for row in setup)})
    events = copy.deepcopy(item["runtime_binding_requirements"]["observation"])
    requirement = {
        "event_count": len(events),
        "source_ids": sorted({row["source_id"] for row in events}),
        "scope_derivation": "candidate_arm_actor_reset_epoch_v1",
        "rule": "observed_fresh_value_flow_exact_target_v1",
        "events": events,
    }
    unused = {
        "event_count": 0,
        "source_ids": [],
        "scope_derivation": "candidate_arm_actor_reset_epoch_v1",
        "rule": "single_state_not_applicable",
        "events": [],
    }
    protocol = item["protocol_evidence"]["protocol"]
    observations = protocol["observations"]
    gates = item["certificate_inner"]["qualification_gates"]
    complete = (
        len(observations) == 1
        and all(
            row.get("state") == "executed" and row.get("status") == "pass"
            for row in [protocol["reset"], protocol["setup"], *observations]
        )
        and all(gates.values())
    )
    checks = {
        "source_hash_closure": True,
        "confirmed_outcome": item["outcome"] == "validated",
        "request_binding_complete": item["candidate"].get("producer") is None
        and all(isinstance(value, str) and bool(value) for value in endpoint.values()),
        "actor_session_closed": set(actors).issubset(
            {
                row["actor_id"]
                for row in item["protocol_evidence"]["sessions"]
                if row.get("arm") == "single_state"
                and row.get("secret_values_present") is False
            }
        ),
        "fresh_value_binding_closed": complete,
        "projection_complete": bool(item["projection"].get("body_path")),
        "predicate_lint_pass": lint.verdict == "pass",
        "reset_isolation_closed": protocol["reset"].get("state") == "executed",
        "safe_execution_closed": complete,
    }
    refs = [
        copy.deepcopy(source[key])
        for key in _RETAINED_SOURCE_KEYS
        if key != "normalized_candidate_sha256"
    ]
    source_hash = canonical_sha256(predicate)
    generic_path = (
        "$"
        if predicate["family"] == "P01" and predicate["operator"] == "absent"
        else (predicate.get("output") or predicate.get("target") or predicate.get("collection") or predicate["left"])["path"]
    )
    assertions = [
        _assertion(
            assertion_id=f"{candidate_id}-business-01",
            assertion_class="business",
            assertion_source="semantic_relation",
            predicate=predicate,
            source_predicate_sha256=source_hash,
            reference_translation={},
            evidence_refs=refs,
        )
    ]
    # The protocol-derived response-schema assertion pins the JSON type the
    # recorded observation actually carries at the business predicate's path.
    # A predicate whose path is not addressed at the observation body (for
    # example a P02 left operand read from the producer response) has no
    # recorded type to pin: derive no schema assertion for it instead of
    # letting the missing path abort the whole relation closure.
    try:
        observed_generic_type: str | None = _json_type(
            get_path(observations[0]["response"]["body"], generic_path)
        )
    except KeyError:
        observed_generic_type = None
    for suffix, generic in (
        ("observer-status", {"type": "status_success", "response_ref": "observation"}),
        *(
            (
                (
                    "response-schema",
                    {
                        "type": "schema_type",
                        "response_ref": "observation",
                        "target_path": generic_path,
                        "expected_type": observed_generic_type,
                    },
                ),
            )
            if observed_generic_type is not None
            else ()
        ),
    ):
        assertions.append(
            _assertion(
                assertion_id=f"{candidate_id}-generic-{suffix}",
                assertion_class="generic",
                assertion_source="protocol_derived",
                predicate=generic,
                source_predicate_sha256=canonical_sha256(
                    {"derivation": suffix, "candidate": source_hash}
                ),
                reference_translation={},
                evidence_refs=refs,
            )
        )
    eligible = all(checks.values())
    reason = None if eligible else "constraint_checks_incomplete"
    return {
        "test_id": "relation-test-"
        + canonical_sha256(
            {
                "candidate_id": candidate_id,
                "normalized_candidate_sha256": source["normalized_candidate_sha256"],
            }
        )[:20],
        "candidate_id": candidate_id,
        "protocol_kind": "V2",
        "claim_kind": "single_state_confirmed",
        "source": source,
        "blueprint": {
            "actors": actors,
            "setup": setup,
            "producer": None,
            "observer": endpoint,
            "observation_plan": [
                {**copy.deepcopy(item["protocol_plan"][0]), **endpoint}
            ],
            "sampling": copy.deepcopy(item["sampling"]),
            "producer_binding_requirement": copy.deepcopy(unused),
            "observer_binding_requirement": {
                "before": copy.deepcopy(unused),
                "after": requirement,
            },
            "settle_policy": copy.deepcopy(item["settle_policy"]),
            "observer_purity_policy": {
                "domains": sorted(item["observer_policy"]["purity_domains_exact_set"])
            },
            "projection_schema": {
                "target_path": generic_path,
                "status": (
                    "pinned"
                    if observed_generic_type is not None
                    else "unaddressed_in_recorded_observation"
                ),
            },
            "provenance_refs": refs,
        },
        "constraint": {
            "status": "complete" if eligible else "incomplete",
            "checks": checks,
            "reason": reason,
        },
        "assertions": assertions,
        "normal_runs": normal_runs,
        "eligible": eligible,
        "eligibility_reason": reason,
    }


def _binding_requirement(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {"event_count": len(events), "source_ids": sorted({row["source_id"] for row in events}),
            "scope_derivation": "candidate_arm_actor_reset_epoch_v1", "rule": "observed_fresh_value_flow_exact_target_v1", "events": copy.deepcopy(events)}


def _point_rejection_observation(predicate: Mapping[str, Any]) -> bool:
    if predicate.get("family") == "P01":
        return bool(predicate.get("absent_statuses"))
    if predicate.get("family") == "P02":
        return any(isinstance(predicate.get(key), Mapping)
                   and predicate[key].get("ref", predicate[key]).get("role") == "after_status" for key in ("left", "right"))
    return False


def _explicit_generic_assertions(candidate_id, steps, source_hash, sources, protocol, repetition_kind):
    assertions = []
    for step in steps:
        rejecting = protocol == "V6" or repetition_kind == "repeat_rejected" and step["step_id"] == "B_action2"
        predicate = {"type": "status_class", "response_ref": step["step_id"], "expected_class": "success_or_client_error"} if rejecting else {"type": "status_success", "response_ref": step["step_id"]}
        assertions.append(_assertion(assertion_id=f"{candidate_id}-generic-{step['step_id']}-status", assertion_class="generic", assertion_source="protocol_derived",
            predicate=predicate, source_predicate_sha256=canonical_sha256({"derivation": "actual_step_transport_status", "step_id": step["step_id"], "candidate": source_hash}),
            reference_translation={}, evidence_refs=[sources["certificate"], sources["execution_material"]]))
    return assertions


def _render_explicit_plan_test(item: Mapping[str, Any], *, normal_runs: int) -> dict[str, Any]:
    """Compile only the registered repeated and standalone rejection plans."""
    candidate, binding, sources = item["candidate"], item["binding"], item["source"]
    candidate_id, protocol = item["candidate_id"], item["protocol_kind"]
    primary = copy.deepcopy(candidate["primary_predicate"])
    rendered, translation = _render_business_predicate(primary)
    source_hash = canonical_sha256(primary)
    producer = {**candidate["producer"], **binding["producer"]}
    setup = copy.deepcopy(candidate["setup"])
    steps = []
    if protocol == "V5":
        for step in item["protocol_plan"]:
            endpoint = producer if step["kind"] == "request" else binding["observations"][step["step_id"]]
            steps.append({**copy.deepcopy(step), "endpoint": copy.deepcopy(endpoint), "binding_requirement": _binding_requirement(item["runtime_binding_requirements"][step["step_id"]])})
        before = next(row["endpoint"] for row in steps if row["step_id"] == "B0")
        observer = steps[-1]["endpoint"]
        epochs = ["repeat_once", "repeat_twice"] if item["repetition_kind"] == "repeat_equal" else ["repeat_twice"]
        producer_requirement = next(row["binding_requirement"] for row in steps if row["step_id"] == "B_action1")
        before_requirement = next(row["binding_requirement"] for row in steps if row["step_id"] == "B0")
        after_requirement = steps[-1]["binding_requirement"]
        extra = {"repetition_kind": item["repetition_kind"], "required_checks": copy.deepcopy(item["required_checks"]), "reset_epochs": epochs, "execution_steps": steps, "repeated_plan": copy.deepcopy(item["protocol_plan"]), "before_observer": before}
    else:
        observer, before = producer, None
        epochs = ["negative_no_effect"]
        producer_requirement = _binding_requirement(item["runtime_binding_requirements"]["P"])
        before_requirement = after_requirement = _binding_requirement([])
        steps = [{"step_id": "producer", "kind": "request", "endpoint": producer, "binding_requirement": producer_requirement}]
        extra = {"negative_kind": "rejection", "negative_plan": copy.deepcopy(item["protocol_plan"]), "rejection_detector": copy.deepcopy(item["rejection_detector"]), "session_boundary": copy.deepcopy(item["session_boundary"])}
    actors = sorted({row["endpoint"]["actor_id"] for row in steps} | {row["actor_id"] for row in setup})
    if item.get("identity_topology") is not None:
        actors = sorted(set(actors) | {item["identity_topology"][key] for key in ("left_actor_id", "right_actor_id")})
    evidence = item["protocol_evidence"]
    records = evidence["protocol"]
    required_records = ([row["step_id"] for row in steps] + [f"{prefix}_{suffix}" for prefix in (["A", "B"] if len(epochs) == 2 else ["B"]) for suffix in ("reset", "setup", "prepare")] if protocol == "V5" else ["reset", "setup", "session_boundary", "producer"])
    complete = all(records.get(key, {}).get("state") == "executed" and records.get(key, {}).get("status") == "pass" for key in required_records)
    session_actors = {row["actor_id"] for row in evidence["sessions"] if row.get("arm") in epochs and row.get("secret_values_present") is False}
    checks = {"source_hash_closure": True, "confirmed_outcome": item["outcome"] == "validated", "request_binding_complete": all(all(row["endpoint"].get(key) for key in ("actor_id", "request_ref", "method", "path", "request_shape_sha256")) for row in steps), "actor_session_closed": set(actors) <= session_actors,
        "fresh_value_binding_closed": complete, "projection_complete": bool(item["projection"].get("body_path")), "predicate_lint_pass": lint_predicate(primary, assertion=False).verdict == "pass", "reset_isolation_closed": complete, "safe_execution_closed": complete}
    assertions = [_assertion(assertion_id=f"{candidate_id}-business-01", assertion_class="business", assertion_source="semantic_relation", predicate=rendered,
        source_predicate_sha256=source_hash, reference_translation=translation, evidence_refs=[sources["certificate"], sources["candidate"], sources["execution_material"]]),
        *_explicit_generic_assertions(candidate_id, steps, source_hash, sources, protocol, item.get("repetition_kind"))]
    eligible = all(checks.values())
    return {"test_id": "relation-test-" + canonical_sha256({"candidate_id": candidate_id, "normalized_candidate_sha256": sources["normalized_candidate_sha256"]})[:20],
        "candidate_id": candidate_id, "protocol_kind": protocol, "claim_kind": item["claim_kind"], "source": {key: copy.deepcopy(sources[key]) for key in _RETAINED_SOURCE_KEYS},
        "blueprint": {"actors": actors, "setup": setup, "producer": producer, "observer": copy.deepcopy(observer), **extra,
            **({"identity_topology": copy.deepcopy(item["identity_topology"])} if "identity_topology" in item else {}),
            "producer_binding_requirement": producer_requirement, "observer_binding_requirement": {"before": before_requirement, "after": after_requirement},
            "settle_policy": copy.deepcopy(item["settle_policy"]), "observer_purity_policy": {"domains": sorted(item["observer_policy"]["purity_domains_exact_set"])},
            "provenance_refs": [copy.deepcopy(sources[key]) for key in _RETAINED_SOURCE_KEYS if key != "normalized_candidate_sha256"]},
        "constraint": {"status": "complete" if eligible else "incomplete", "checks": checks, "reason": None if eligible else "constraint_checks_incomplete"},
        "assertions": assertions, "normal_runs": normal_runs, "eligible": eligible, "eligibility_reason": None if eligible else "constraint_checks_incomplete"}


def _render_single_arm_test(item: Mapping[str, Any], *, normal_runs: int) -> dict[str, Any]:
    candidate_id = str(item["candidate_id"])
    candidate = copy.deepcopy(item["candidate"])
    binding = copy.deepcopy(item["binding"])
    source_predicate = copy.deepcopy(candidate["primary_predicate"])
    lint = lint_predicate(source_predicate, assertion=False)
    rendered_predicate, translation = _render_business_predicate(
        lint.predicate or source_predicate
    )
    source_hash = canonical_sha256(source_predicate)
    source_refs = item["source"]
    certificate_ref = copy.deepcopy(source_refs["certificate"])
    candidate_ref = copy.deepcopy(source_refs["candidate"])
    material_ref = copy.deepcopy(source_refs["execution_material"])
    evidence = item["protocol_evidence"]
    protocol = evidence["protocol"]
    requirements = item["runtime_binding_requirements"]
    create_capture_read = (
        item["protocol_kind"] == "V4"
        and any(
            step.get("step_id") == "capture_fresh_identity"
            for step in item["protocol_plan"]
        )
    )
    no_before_workflow = (
        item["protocol_kind"] == "V4"
        and not any(
            step.get("step_id") == "before"
            for step in item["protocol_plan"]
        )
    )
    workflow_kind = item.get("workflow_kind") or (
        "create_capture_read"
        if create_capture_read
        else "postcondition_read"
        if no_before_workflow
        else "before_write_after"
    )

    raw_query_plan = item["protocol_plan"] if item["protocol_kind"] == "V3" else None
    query_plan = (
        [
            {
                **copy.deepcopy(step),
                **{
                    key: copy.deepcopy(
                        binding["observations"][step["role"]][key]
                    )
                    for key in (
                        "actor_id",
                        "request_ref",
                        "method",
                        "path",
                        "request_shape_sha256",
                    )
                },
            }
            for step in raw_query_plan
        ]
        if raw_query_plan is not None
        else None
    )
    source_role = query_plan[0]["role"] if query_plan else None
    after_role = query_plan[-1]["role"] if query_plan else None
    producer_binding = (
        binding["observations"][source_role]
        if source_role is not None else binding["producer"]
    )
    producer = {
        **copy.deepcopy(candidate["producer"]),
        **{
            key: copy.deepcopy(producer_binding[key])
            for key in ("method", "path", "request_shape_sha256")
        },
    }
    before_slot, after_slot = (
        (source_role, after_role)
        if item["protocol_kind"] == "V3"
        else
        ("workflow_before", "workflow_after")
        if item["protocol_kind"] == "V4"
        else ("negative_before", "negative_after")
        if item["protocol_kind"] == "V6"
        else ("actor_before", "actor_after")
    )
    before_binding = (
        None if no_before_workflow else binding["observations"][before_slot]
    )
    after_binding = binding["observations"][after_slot]
    before_observer = (
        None
        if before_binding is None
        else {
            "actor_id": before_binding["actor_id"],
            "request_ref": before_binding["request_ref"],
            "method": before_binding["method"],
            "path": before_binding["path"],
            "request_shape_sha256": before_binding["request_shape_sha256"],
        }
    )
    observer = {
        **copy.deepcopy(candidate["consumer"]),
        **{
            key: copy.deepcopy(after_binding[key])
            for key in ("method", "path", "request_shape_sha256")
        },
    }
    setup = copy.deepcopy(candidate.get("setup") or [])
    actors = sorted(
        {
            producer["actor_id"],
            observer["actor_id"],
            *( [before_observer["actor_id"]] if before_observer else [] ),
            *(row["actor_id"] for row in setup),
        }
    )
    sessions = {
        row["actor_id"]
        for row in evidence["sessions"]
        if row.get("arm") == (
            "metamorphic_query" if item["protocol_kind"] == "V3"
            else "workflow" if item["protocol_kind"] == "V4"
            else "negative_no_effect" if item["protocol_kind"] == "V6"
            else "actor_matrix"
        )
        and row.get("secret_values_present") is False
    }

    def requirement(slot: str) -> dict[str, Any]:
        events = copy.deepcopy(requirements[slot])
        return {
            "event_count": len(events),
            "source_ids": sorted({row["source_id"] for row in events}),
            "scope_derivation": "candidate_arm_actor_reset_epoch_v1",
            "rule": "observed_fresh_value_flow_exact_target_v1",
            "events": events,
        }

    def no_before_requirement() -> dict[str, Any]:
        return {
            "event_count": 0,
            "source_ids": [],
            "scope_derivation": "candidate_arm_actor_reset_epoch_v1",
            "rule": f"not_applicable_{workflow_kind}_has_no_before_v1",
            "events": [],
        }

    after_body = (
        protocol["queries"][-1]["response"]["body"]
        if item["protocol_kind"] == "V3"
        else protocol["after"]["response"]["body"]
    )
    # The projection-schema assertion pins the JSON type observed at the
    # projection path of the recorded after-state; a path the recorded body
    # does not address has no type to pin, so no such assertion is derived.
    try:
        projection_type: str | None = _json_type(
            get_path(after_body, str(item["projection"]["body_path"]))
        )
    except KeyError:
        projection_type = None
    assertions = [
        _assertion(
            assertion_id=f"{candidate_id}-business-01",
            assertion_class="business",
            assertion_source="semantic_relation",
            predicate=rendered_predicate,
            source_predicate_sha256=source_hash,
            reference_translation=translation,
            evidence_refs=[certificate_ref, candidate_ref, material_ref],
        ),
        _assertion(
            assertion_id=f"{candidate_id}-generic-producer-status",
            assertion_class="generic",
            assertion_source="protocol_derived",
            predicate=(
                {
                    "type": "status_class",
                    "response_ref": "producer",
                    "expected_class": "success_or_client_error",
                }
                if item["protocol_kind"] == "V6"
                else {"type": "status_success", "response_ref": "producer"}
            ),
            source_predicate_sha256=canonical_sha256(
                {"derivation": "producer_transport_status", "candidate": source_hash}
            ),
            reference_translation={},
            evidence_refs=[certificate_ref, material_ref],
        ),
        *(
            [
                _assertion(
                    assertion_id=f"{candidate_id}-generic-before-status",
                    assertion_class="generic",
                    assertion_source="protocol_derived",
                    predicate={
                        "type": "status_success",
                        "response_ref": "before",
                    },
                    source_predicate_sha256=canonical_sha256(
                        {
                            "derivation": "pre_observer_transport_status",
                            "candidate": source_hash,
                        }
                    ),
                    reference_translation={},
                    evidence_refs=[certificate_ref, material_ref],
                )
            ]
            if item["protocol_kind"] == "V6"
            else []
        ),
        _assertion(
            assertion_id=f"{candidate_id}-generic-observer-status",
            assertion_class="generic",
            assertion_source="protocol_derived",
            predicate=({"type": "status_class", "response_ref": "after", "expected_class": "success_or_client_error"}
                       if _point_rejection_observation(rendered_predicate) else {"type": "status_success", "response_ref": "after"}),
            source_predicate_sha256=canonical_sha256(
                {"derivation": "post_observer_transport_status", "candidate": source_hash}
            ),
            reference_translation={},
            evidence_refs=[certificate_ref, material_ref],
        ),
        *([] if _point_rejection_observation(rendered_predicate) or projection_type is None else [_assertion(
            assertion_id=f"{candidate_id}-generic-projection-schema",
            assertion_class="generic",
            assertion_source="protocol_derived",
            predicate={
                "type": "schema_type",
                "response_ref": "after",
                "target_path": str(item["projection"]["body_path"]),
                "expected_type": projection_type,
            },
            source_predicate_sha256=canonical_sha256(
                {"derivation": "single_arm_projection_json_type", "candidate": source_hash}
            ),
            reference_translation={},
            evidence_refs=[certificate_ref, material_ref],
        )]),
    ]
    if workflow_kind == "inverse_restoration":
        assertions.extend(_explicit_generic_assertions(candidate_id, [{"step_id": "inverse"}, {"step_id": "workflow_intermediate"}], source_hash, item["source"], "V4", None))
    all_steps_pass = (
        protocol["reset"].get("state") == "executed"
        and protocol["setup"].get("state") == "executed"
        and len(protocol["queries"]) == len(query_plan)
        and all(row.get("state") == "executed" and row.get("status") == "pass" for row in protocol["queries"])
        if item["protocol_kind"] == "V3"
        else all(
            protocol[step].get("state") == "executed"
            and protocol[step].get("status") == "pass"
            for step in (
                (
                    "reset", "setup", "session_boundary", "before", "producer",
                    "rejection_gate", "settle", "after",
                )
                if item["protocol_kind"] == "V6"
                else
                ("reset", "setup", "producer", "settle", "after")
                if no_before_workflow
                else ("reset", "setup", "before", "producer", "settle", "after")
            )
        )
    )
    if item["protocol_kind"] == "V6":
        all_steps_pass = (
            all_steps_pass and protocol["rejection_gate"].get("rejected") is True
        )
    checks = {
        "source_hash_closure": True,
        "confirmed_outcome": item["outcome"] == "validated",
        "request_binding_complete": all(
            isinstance(row.get(key), str) and bool(row[key])
            for row in (
                (producer, observer)
                if no_before_workflow
                else (producer, before_observer, observer)
            )
            for key in ("actor_id", "request_ref", "method", "path", "request_shape_sha256")
        ),
        "actor_session_closed": set(actors).issubset(sessions),
        "fresh_value_binding_closed": all_steps_pass,
        "projection_complete": bool(item["projection"].get("body_path")),
        "predicate_lint_pass": lint.verdict == "pass",
        "reset_isolation_closed": protocol["reset"].get("state") == "executed",
        "safe_execution_closed": all_steps_pass,
    }
    status = "complete" if all(checks.values()) else "incomplete"
    reason = None if status == "complete" else "constraint_checks_incomplete"
    return {
        "test_id": "relation-test-" + canonical_sha256(
            {
                "candidate_id": candidate_id,
                "normalized_candidate_sha256": source_refs[
                    "normalized_candidate_sha256"
                ],
            }
        )[:20],
        "candidate_id": candidate_id,
        "protocol_kind": item["protocol_kind"],
        "claim_kind": item["claim_kind"],
        "source": {
            key: copy.deepcopy(source_refs[key]) for key in _RETAINED_SOURCE_KEYS
        },
        "blueprint": {
            "actors": actors,
            "setup": setup,
            **{key: copy.deepcopy(item[key]) for key in ("workflow_kind", "negative_kind", "identity_topology") if key in item},
            **({key: copy.deepcopy(item[key]) for key in ("query_scope", "query_transform")} if item["protocol_kind"] == "V3" else {}),
            "producer": producer,
            "observer": observer,
            **({"inverse": copy.deepcopy(binding["inverse"]), "intermediate_observer": copy.deepcopy(binding["observations"]["workflow_intermediate"]),
                "inverse_binding_requirement": _binding_requirement(item["inverse"]), "intermediate_binding_requirement": _binding_requirement(item["intermediate"])} if item.get("workflow_kind") == "inverse_restoration" else {}),
            **(
                {"workflow_kind": workflow_kind}
                if no_before_workflow
                else {"before_observer": before_observer}
            ),
            **(
                {
                    "session_boundary": copy.deepcopy(item["session_boundary"]),
                    "rejection_detector": copy.deepcopy(
                        item["rejection_detector"]
                    ),
                }
                if item["protocol_kind"] == "V6"
                else {}
            ),
            **{
                (
                    "query_plan" if item["protocol_kind"] == "V3"
                    else "workflow_plan" if item["protocol_kind"] == "V4"
                    else "negative_plan" if item["protocol_kind"] == "V6"
                    else "actor_plan"
                ):
                copy.deepcopy(
                    query_plan
                    if item["protocol_kind"] == "V3"
                    else item["protocol_plan"]
                )
            },
            "producer_binding_requirement": requirement(
                source_role if item["protocol_kind"] == "V3" else "P"
            ),
            "observer_binding_requirement": {
                "before": (
                    no_before_requirement()
                    if no_before_workflow
                    else requirement(
                        source_role if item["protocol_kind"] == "V3" else "before"
                    )
                ),
                "after": requirement(
                    after_role if item["protocol_kind"] == "V3" else "after"
                ),
            },
            **(
                {
                    "query_binding_requirements": {
                        step["role"]: requirement(step["role"])
                        for step in query_plan
                    }
                }
                if item["protocol_kind"] == "V3"
                else {}
            ),
            "settle_policy": copy.deepcopy(item["settle_policy"]),
            "observer_purity_policy": {
                "domains": sorted(
                    item["observer_policy"]["purity_domains_exact_set"]
                ),
            },
            "projection_schema": {
                "target_path": str(item["projection"]["body_path"]),
                "status": (
                    "pinned"
                    if projection_type is not None
                    else "unaddressed_in_recorded_observation"
                ),
            },
            "provenance_refs": [
                copy.deepcopy(source_refs[key])
                for key in _RETAINED_SOURCE_KEYS
                if key != "normalized_candidate_sha256"
            ],
        },
        "constraint": {"status": status, "checks": checks, "reason": reason},
        "assertions": assertions,
        "normal_runs": normal_runs,
        "eligible": status == "complete",
        "eligibility_reason": reason,
    }


def _fresh_value_binding_closed(
    *,
    request_attestation: Mapping[str, Any],
    runtime_binding_requirements: Mapping[str, list[Mapping[str, Any]]],
    attestations: Mapping[str, Mapping[str, Any]],
) -> bool:
    return request_attestation.get("value") is True and all(
        attestation.get("arm") == "treatment"
        and isinstance(attestation.get("binding_event_count"), int)
        and len(runtime_binding_requirements[slot])
        == attestation["binding_event_count"]
        and {event["source_id"] for event in runtime_binding_requirements[slot]}
        == set(attestation.get("source_ids") or [])
        for slot, attestation in attestations.items()
    )


def _assertion(
    *,
    assertion_id: str,
    assertion_class: str,
    assertion_source: str,
    predicate: Mapping[str, Any],
    source_predicate_sha256: str,
    reference_translation: Mapping[str, str],
    evidence_refs: list[dict[str, str]],
) -> dict[str, Any]:
    value = {
        "assertion_id": assertion_id,
        "assertion_class": assertion_class,
        "assertion_source": assertion_source,
        "predicate": copy.deepcopy(predicate),
        "predicate_type": predicate.get("family", predicate.get("type")),
        "source_predicate_sha256": source_predicate_sha256,
        "rendered_predicate_sha256": canonical_sha256(predicate),
        "reference_translation": dict(reference_translation),
        "evidence_refs": copy.deepcopy(evidence_refs),
    }
    value["definition_sha256"] = canonical_sha256(value)
    return value


def _render_business_predicate(predicate: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    return copy.deepcopy(predicate), {}


def _validate_alpha_translation(assertion: Mapping[str, Any]) -> None:
    predicate = copy.deepcopy(assertion["predicate"])
    if assertion["reference_translation"]:
        raise RelationBlueprintError("canonical_business_predicate_must_not_be_alpha_translated")
    if canonical_sha256(predicate) != assertion["source_predicate_sha256"]:
        raise RelationBlueprintError("business_predicate_changed_beyond_alpha_rename")


def _json_type(value: Any) -> str:
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


def _require_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise RelationBlueprintError(f"duplicate_{label}:{value}")
        seen.add(value)


__all__ = [
    "BUSINESS_ASSERTION_TYPES",
    "GENERIC_ASSERTION_TYPES",
    "RelationBlueprintError",
    "build_certified_relation_tests",
    "canonical_bytes",
    "canonical_sha256",
    "summarize_generation",
    "validate_certified_relation_tests",
]
