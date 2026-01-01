"""Subject-neutral M11b materialization for the current Route-S boundary.

M11a owns candidate lineage, setup selection and predicate compilation.  This
module is the separate boundary that binds those facts to the published Route-S
execution-binding and pre-live-pins contracts.  It never executes a target and
never selects or records a scientific outcome.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Any, Callable, Mapping, Sequence

from stage6_ground.resource_rebinding import (
    ResourceRebindingError,
    RecordedSetupRequest,
    ResourceBindingSource,
    ResourceBindingUse,
    SetupBindingPlan,
    build_setup_binding_plan,
    extract_typed_value,
    scalar_sha256,
    typed_value_is_missing,
)

from .contracts import (
    ObservedValueFlowSet,
    UiApiTrace,
    V2BoundCandidate,
    V2RuntimeReadyMaterialSet,
)
from .current_candidate_failure import CandidateLocalFailure
from .current_route_s import (
    RouteSUnsupported,
    bind_execution_payload,
    bind_pre_live_pins_v2,
    canonical_json_bytes,
    canonical_sha256,
    derive_projection_plan_payload,
    request_shape_sha256,
    validate_current_route_s_material,
    validate_execution_binding_v2,
    validate_pre_live_binding_pins_v2,
)


_REDACTED_RUNTIME_MATERIAL = re.compile(r"^\[REDACTED:[^\]\r\n]+\]$")


@dataclass(frozen=True)
class RouteSPreLiveMaterializedCandidate:
    candidate_id: str
    bound_candidate_sha256: str
    candidate: dict[str, Any]
    execution_binding: dict[str, Any]
    execution_binding_bytes: bytes
    pre_live_binding_pins: dict[str, Any]
    pre_live_binding_pins_bytes: bytes
    projection_plan: dict[str, Any]
    observer_policy: dict[str, Any]
    settle_policy: dict[str, Any]
    sensitive_classification: dict[str, Any]
    resource_binding_plans: dict[str, dict[str, Any]]
    scientific_pins: dict[str, str]
    artifact_bytes: dict[str, bytes]
    artifact_hashes: dict[str, str]
    artifact_inventory: tuple[dict[str, Any], ...]
    execution_material: dict[str, Any]
    execution_material_bytes: bytes
    output_level: str


@dataclass(frozen=True)
class RouteSM11bMaterializationResult:
    materials: tuple[RouteSPreLiveMaterializedCandidate, ...]
    ineligible: tuple[dict[str, str], ...]


def materialize_current_route_s_inputs(
    material_set: V2RuntimeReadyMaterialSet,
    *,
    trace: UiApiTrace,
    value_flows: ObservedValueFlowSet,
    binding_plan: Mapping[str, Any],
    scientific_pins: Mapping[str, str],
    output_level: str,
    recording_trace: Mapping[str, Any] | None = None,
    recording_material_aliases: tuple[dict[str, Any], ...] = (),
    authenticated_actor_identity_paths: Mapping[str, str] | None = None,
    observed_catalog_requests: Mapping[str, Mapping[str, Any]] | None = None,
    observed_catalog_operations: Mapping[str, Mapping[str, Any]] | None = None,
) -> RouteSM11bMaterializationResult:
    """Turn the validated M11a set into exact official M11b artifacts."""

    if not isinstance(material_set, V2RuntimeReadyMaterialSet):
        raise TypeError("M11b requires the current validated M11a material set")
    if not isinstance(value_flows, ObservedValueFlowSet):
        raise TypeError("M11b requires the current observed value-flow set")
    if value_flows.source_sha256.get("ui_api_trace") != trace.canonical_sha256():
        raise ValueError("M11b value-flow set does not close over the current trace")
    _validate_binding_plan_boundary(binding_plan)
    if output_level not in {"paper", "debug", "forensic"}:
        raise ValueError(f"unknown current output level: {output_level!r}")
    required_pin_keys = {
        "verifier_sha256",
        "partial_schema_sha256",
        "certificate_schema_sha256",
        "execution_evidence_schema_sha256",
        "projector_sha256",
        "equivalence_sha256",
        "predicate_evaluator_sha256",
        "predicate_linter_sha256",
        "observer_request_policy_sha256",
        "reset_driver_sha256",
        "session_materializer_sha256",
        "settle_policy_sha256",
        "profile_sha256",
        "renderer_sha256",
        "subject_pin_sha256",
    }
    if output_level == "forensic" and (set(scientific_pins) != required_pin_keys or any(
        not _is_sha(value) for value in scientific_pins.values()
    )):
        raise ValueError("M11b scientific pin set is not exact")

    bound_by_id = {item.candidate_id: item for item in material_set.bound_candidates}
    runtime_by_id = {item.candidate_id: item for item in material_set.runtime_materials}
    if set(bound_by_id) != set(runtime_by_id):
        raise ValueError("M11a bound/runtime candidate partition mismatch")
    requests = {
        str(item["request_ref"]): item for item in trace.trace["api_requests"]
    }
    recorded_post_read_refs: set[str] = set()
    for runtime_material in runtime_by_id.values():
        protocol_shape = runtime_material.execution_binding.get("protocol_shape") or {}
        evidence = protocol_shape.get("read_execution_evidence") or {}
        if not isinstance(evidence, Mapping):
            raise ValueError("M11b read execution evidence shape invalid")
        for request_ref, row in evidence.items():
            request = requests.get(str(request_ref))
            repeated_refs = (
                row.get("repeated_observation_request_refs", ())
                if isinstance(row, Mapping)
                else ()
            )
            if (
                request is None
                or not isinstance(row, Mapping)
                or row.get("kind") != "recorded_post_query"
                or str(request.get("method", "")).upper() != "POST"
                or not isinstance(repeated_refs, (list, tuple))
                or not repeated_refs
                or any(
                    peer_ref not in requests
                    or requests[peer_ref].get("operation_id")
                    != request.get("operation_id")
                    or requests[peer_ref].get("actor_id")
                    != request.get("actor_id")
                    or requests[peer_ref].get("session_run_id")
                    != request.get("session_run_id")
                    for peer_ref in repeated_refs
                )
            ):
                raise ValueError("M11b read execution evidence does not bind trace")
            recorded_post_read_refs.add(str(request_ref))
    requests = {
        request_ref: {
            **request,
            **(
                {"mechanical_read_kind": "recorded_post_query"}
                if request_ref in recorded_post_read_refs
                else {}
            ),
        }
        for request_ref, request in requests.items()
    }
    request_order = {
        str(item["request_ref"]): index
        for index, item in enumerate(trace.trace["api_requests"])
    }
    recording_plan = (
        _recording_prerequisite_plan(
            recording_trace,
            request_bindings=binding_plan["request_bindings"],
            requests=requests,
        )
        if recording_trace is not None
        else None
    )
    events = {str(item["event_id"]): item for item in trace.trace["events"]}
    request_to_events: dict[str, list[str]] = {}
    for row in trace.trace["bindings"]:
        request_to_events.setdefault(str(row["request_ref"]), []).append(
            str(row["event_id"])
        )

    result: list[RouteSPreLiveMaterializedCandidate] = []
    ineligible: list[dict[str, str]] = []
    for candidate_id in sorted(bound_by_id):
        bound = bound_by_id[candidate_id]
        runtime_material = runtime_by_id[candidate_id]
        if runtime_material.bound_candidate_sha256 != bound.canonical_sha256():
            raise ValueError("M11a runtime material does not bind its candidate")
        prefix = f"M11b/{candidate_id}"
        bound_ref = f"{prefix}/m11a_bound_candidate.json"
        selected_setup_rows = [
            {"actor_id": str(row["actor_id"]), "request_ref": str(row["request_ref"])}
            for row in runtime_material.execution_binding["setup"]
        ]
        if [row["request_ref"] for row in selected_setup_rows] != list(
            bound.selected_setup_request_refs
        ):
            raise ValueError("M11b selected setup order drifted from M11a")
        protocol_shape = copy.deepcopy(
            runtime_material.execution_binding.get("protocol_shape")
            or {"shape_kind": "causal_two_arm"}
        )
        shape_kind = protocol_shape["shape_kind"]
        _validate_observer_catalog_selection(
            protocol_shape=protocol_shape,
            bound=bound,
            execution_binding=runtime_material.execution_binding,
            requests=requests,
            observed_catalog_requests=observed_catalog_requests,
            observed_catalog_operations=observed_catalog_operations,
        )
        is_v4 = shape_kind == "lifecycle_workflow"
        is_create_capture_v4 = (
            is_v4 and protocol_shape.get("workflow_kind") == "create_capture_read"
        )
        is_postcondition_v4 = (
            is_v4 and protocol_shape.get("workflow_kind") == "postcondition_read"
        )
        is_no_before_v4 = is_create_capture_v4 or is_postcondition_v4
        is_v7 = shape_kind == "actor_matrix"
        is_v3 = shape_kind == "metamorphic_query"
        is_v6 = shape_kind == "negative_no_effect"
        is_v5 = shape_kind == "repeated_execution"
        negative_standalone = is_v6 and protocol_shape["negative_kind"] == "rejection"
        is_v2 = shape_kind == "single_state"
        is_v9 = shape_kind == "multi_resource"
        is_v8 = shape_kind == "temporal"
        producer_free = is_v2 or is_v9 and bound.producer_request_ref is None
        is_single_arm = is_v2 or is_v3 or is_v4 or is_v5 or is_v6 or is_v7 or is_v9 or is_v8
        if is_v9 or is_v8:
            prerequisite_consumer_refs = {row["request_ref"] for row in protocol_shape["observation_plan"]}
        else:
            prerequisite_consumer_refs = set()
        prerequisite_consumer_refs = (
            {
                str(protocol_shape["roles"]["before"]["request_ref"]),
            }
            if (is_v4 and not is_no_before_v4) or is_v5 or (is_v6 and not negative_standalone)
            else prerequisite_consumer_refs
        )
        if is_v8 and "before" in protocol_shape["roles"]:
            prerequisite_consumer_refs.add(protocol_shape["roles"]["before"]["request_ref"])
        if is_v4 and protocol_shape.get("workflow_kind") == "inverse_restoration":
            prerequisite_consumer_refs.add(str(protocol_shape["roles"]["inverse"]["request_ref"]))
        try:
            session_continuity = (
                _resolve_postcondition_session_continuity(
                    protocol_shape=protocol_shape,
                    producer_ref=bound.producer_request_ref,
                    observer_ref=bound.observer_request_ref,
                    producer_actor=str(
                        runtime_material.execution_binding["producer"]["actor_id"]
                    ),
                    observer_actor=str(
                        runtime_material.execution_binding["observer"]["actor_id"]
                    ),
                    requests=requests,
                    value_flows=value_flows,
                )
                if is_postcondition_v4
                else None
            )
            if session_continuity is not None:
                protocol_shape["postcondition_flow"][
                    "session_continuity"
                ] = session_continuity
            deferred_workflow_binding = (
                _resolve_deferred_workflow_binding(
                    protocol_shape=protocol_shape,
                    producer_ref=bound.producer_request_ref,
                    observer_ref=bound.observer_request_ref,
                    producer_actor=str(
                        runtime_material.execution_binding["producer"]["actor_id"]
                    ),
                    observer_actor=str(
                        runtime_material.execution_binding["observer"]["actor_id"]
                    ),
                    recording_plan=recording_plan,
                    path_binding_targets=(
                        binding_plan.get("path_binding_targets") or {}
                    ),
                )
                if is_create_capture_v4
                else None
            )
            prerequisite_plan = _candidate_prerequisite_plan(
                producer_ref=bound.producer_request_ref,
                observer_ref=bound.observer_request_ref,
                request_order=request_order,
                path_binding_targets=binding_plan.get("path_binding_targets") or {},
                additional_consumer_refs=prerequisite_consumer_refs,
                selected_setup_refs=set(bound.selected_setup_request_refs),
                eligible_domain_refs=set(bound.eligible_setup_request_refs),
                profile_managed_refs=set(
                    bound.profile_managed_setup_request_refs
                ),
                recording_plan=recording_plan,
                deferred_observer_source_ref=(
                    bound.producer_request_ref
                    if deferred_workflow_binding is not None
                    else None
                ),
            )
            producer_lookup_rows = (
                _producer_lookup_setup_rows(
                    producer_ref=bound.producer_request_ref,
                    request_order=request_order,
                    requests=requests,
                    value_flows=value_flows,
                    path_binding_targets=(
                        binding_plan.get("path_binding_targets") or {}
                    ),
                    profile_managed_refs=set(
                        bound.profile_managed_setup_request_refs
                    ),
                    authenticated_actor_identity_path=(
                        authenticated_actor_identity_paths or {}
                    ).get(str(requests[bound.producer_request_ref]["actor_id"])),
                )
                if not producer_free and not selected_setup_rows and prerequisite_plan is None
                else []
            )
            initial_setup_by_ref = {
                str(row["request_ref"]): copy.deepcopy(row)
                for row in (*selected_setup_rows, *producer_lookup_rows)
            }
            if producer_free:
                initial_setup_by_ref.update({
                    ref: {"request_ref": ref, "actor_id": str(requests[ref]["actor_id"])}
                    for ref in bound.eligible_setup_request_refs
                    if ref not in bound.profile_managed_setup_request_refs
                })
            setup_rows, setup_closure_provenance, closure_only_request_refs = _expand_setup_request_chain(
                [
                    initial_setup_by_ref[request_ref]
                    for request_ref in sorted(
                        initial_setup_by_ref,
                        key=request_order.__getitem__,
                    )
                ],
                trace=trace,
                value_flows=value_flows,
                eligible_domain_refs=set(bound.eligible_setup_request_refs),
                recording_plan=recording_plan,
                recording_trace=recording_trace,
                binding_plan=binding_plan,
                ordinary_setup_refs=set(initial_setup_by_ref).union(
                    source.creator_request_ref
                    for source in prerequisite_plan.sources
                ) if prerequisite_plan is not None else set(initial_setup_by_ref),
                strict_identity_field_pairs=_strict_identity_field_pairs(
                    bound.runtime_predicate
                ),
            )
        except CandidateLocalFailure as error:
            ineligible.append(
                error.record(candidate_id, status="materialization_ineligible")
            )
            continue
        setup_by_ref = {
            str(row["request_ref"]): copy.deepcopy(row) for row in setup_rows
        }
        if prerequisite_plan is not None:
            for source in prerequisite_plan.sources:
                setup_by_ref.setdefault(
                    source.creator_request_ref,
                    {
                        "actor_id": str(
                            requests[source.creator_request_ref]["actor_id"]
                        ),
                        "request_ref": source.creator_request_ref,
                    },
                )
        executed_refs = {
            bound.observer_request_ref,
            *setup_by_ref,
        }
        if bound.producer_request_ref is not None:
            executed_refs.add(bound.producer_request_ref)
        roles = protocol_shape.get("roles")
        if isinstance(roles, Mapping):
            executed_refs.update(
                str(role["request_ref"])
                for role in roles.values()
                if isinstance(role, Mapping)
                and isinstance(role.get("request_ref"), str)
            )
        query_plan = protocol_shape.get("query_plan")
        if isinstance(query_plan, list):
            executed_refs.update(
                str(step["request_ref"])
                for step in query_plan
                if isinstance(step, Mapping)
                and isinstance(step.get("request_ref"), str)
            )
        profile_setup_rows = _authenticated_profile_setup_rows(
            consumers={
                request_ref: str(requests[request_ref]["actor_id"])
                for request_ref in executed_refs
            },
            binding_plan=binding_plan,
            requests=requests,
            recording_trace=recording_trace,
            authenticated_actor_identity_paths=(
                authenticated_actor_identity_paths or {}
            ),
        )
        profile_setup_refs = {
            str(row["request_ref"]) for row in profile_setup_rows
        }
        for row in profile_setup_rows:
            setup_by_ref.setdefault(str(row["request_ref"]), row)
        setup_rows = _ordered_setup_rows(
            setup_by_ref=setup_by_ref,
            request_order=request_order,
            technical_profile_refs=profile_setup_refs,
        )
        materialized_execution_binding = copy.deepcopy(
            runtime_material.execution_binding
        )
        materialized_execution_binding["setup"] = copy.deepcopy(setup_rows)
        candidate = _route_s_candidate(
            bound,
            materialized_execution_binding,
            source_ref=bound_ref,
        )
        if is_v3:
            transform_kind = protocol_shape.get("transform_kind")
            predicate = candidate["primary_predicate"]
            from .current_protocols import current_shape_supports_relation
            valid_transform = current_shape_supports_relation(
                "metamorphic_query", candidate["contract_kind"], predicate["family"],
                predicate.get("operator"), transform_kind=transform_kind,
            )
            if not valid_transform:
                raise ValueError("metamorphic_query_transform_contract_mismatch")
        if output_level != "forensic":
            candidate.pop("source_hashes", None)
        try:
            projection_payload = derive_projection_plan_payload(
                candidate["primary_predicate"],
            )
        except RouteSUnsupported as error:
            ineligible.append(
                CandidateLocalFailure(
                    "M11b", "contract", str(error)
                ).record(candidate_id, status="materialization_ineligible")
            )
            continue
        observer_policy = copy.deepcopy(dict(binding_plan["observer_policy"]))
        settle_policy = copy.deepcopy(dict(binding_plan["settle_policy"]))
        classification_payload = copy.deepcopy(
            dict(binding_plan["sensitive_classification"])
        )
        if output_level == "forensic" and not is_single_arm:
            projection_ref = f"{prefix}/projection_plan.payload.json"
            projection_bytes = canonical_json_bytes(projection_payload)
            projection = {
                **copy.deepcopy(projection_payload),
                "artifact_ref": projection_ref,
                "artifact_sha256": hashlib.sha256(projection_bytes).hexdigest(),
            }
            observer_policy_ref = f"{prefix}/observer_policy.json"
            observer_policy_bytes = canonical_json_bytes(observer_policy)
            observer_policy_sha = hashlib.sha256(observer_policy_bytes).hexdigest()
            if scientific_pins["observer_request_policy_sha256"] != observer_policy_sha:
                raise ValueError("M11b observer policy does not match the scientific pin")
            settle_policy_ref = f"{prefix}/settle_policy.json"
            settle_policy_bytes = canonical_json_bytes(settle_policy)
            settle_policy_sha = hashlib.sha256(settle_policy_bytes).hexdigest()
            if scientific_pins["settle_policy_sha256"] != settle_policy_sha:
                raise ValueError("M11b settle policy does not match the scientific pin")
            classification_ref = f"{prefix}/sensitive_classification.json"
            classification_bytes = canonical_json_bytes(classification_payload)
            classification_sha = hashlib.sha256(classification_bytes).hexdigest()
            classification = {
                "artifact_ref": classification_ref,
                "artifact_sha256": classification_sha,
                **classification_payload,
            }
        else:
            projection = copy.deepcopy(projection_payload)
            classification = copy.deepcopy(classification_payload)

        try:
            producer_request = _bound_request(
                bound.producer_request_ref,
                requests=requests,
                binding_plan=binding_plan,
            ) if bound.producer_request_ref is not None else None
            observer_request = _bound_request(
                bound.observer_request_ref,
                requests=requests,
                binding_plan=binding_plan,
            )
            if (
                observer_policy.get("request_method_policy") == "read_only"
                and not _request_is_read_only(
                    bound.observer_request_ref,
                    bound_request=observer_request,
                    requests=requests,
                )
            ):
                raise CandidateLocalFailure(
                    "M11b", "contract", "observer_request_not_read_only"
                )
            if producer_free:
                producer_events = []
            elif is_v3 or is_v4 and protocol_shape.get("workflow_kind") == "read_preservation":
                # V3's candidate producer is the source query, not a write.
                # Bind its recorded action only when the trace has one exact
                # association; a query without a UI action remains executable.
                producer_events = request_to_events.get(
                    bound.producer_request_ref, []
                )
                if len(producer_events) > 1 or any(
                    event_id not in events for event_id in producer_events
                ):
                    raise CandidateLocalFailure(
                        "M11b", "binding", "query_source_action_binding_ambiguous"
                    )
            else:
                producer_events = request_to_events.get(bound.producer_request_ref, [])
                if len(producer_events) != 1 or producer_events[0] not in events:
                    raise CandidateLocalFailure(
                        "M11b", "binding", "producer_action_binding_not_unique"
                    )
            for row in setup_rows:
                _bound_request(
                    row["request_ref"],
                    requests=requests,
                    binding_plan=binding_plan,
                )
        except CandidateLocalFailure as error:
            ineligible.append(
                error.record(candidate_id, status="materialization_ineligible")
            )
            continue
        producer_action_ref = producer_events[0] if producer_events else None
        before_role = (
            "source_query"
            if is_v3
            else
            "before"
            if (is_v4 and not is_no_before_v4) or is_v5 or (is_v6 and not negative_standalone)
            else next(
                role for role in protocol_shape.get("roles", {})
                if role.startswith("actor_before:")
            )
            if is_v7
            else None
        )
        before_ref = (
            str(protocol_shape["roles"][before_role]["request_ref"])
            if before_role is not None
            else bound.observer_request_ref
        )
        before_request = _bound_request(
            before_ref, requests=requests, binding_plan=binding_plan
        )
        from .dsl import is_workflow_effect_predicate
        if is_v4 and is_workflow_effect_predicate(candidate["primary_predicate"]):
            # M10 has canonical operations; M11 additionally has the actual
            # recorded selector and physical path for this same-object slice.
            selectors = lambda request: {key: request.get(key) for key in ("actor_id", "method", "path", "query", "body")}
            if canonical_json_bytes(selectors(before_request)) != canonical_json_bytes(selectors(observer_request)):
                ineligible.append(CandidateLocalFailure("M11b", "binding", "workflow_observer_object_selector_mismatch").record(candidate_id, status="materialization_ineligible"))
                continue
        if is_v9 and candidate["primary_predicate"].get("operator") == "linear_delta":
            selectors = lambda request: {key: request.get(key) for key in ("actor_id", "method", "path", "query", "body")}
            if any(selectors(_bound_request(protocol_shape["roles"][term["before"]["role"]]["request_ref"], requests=requests, binding_plan=binding_plan)) != selectors(_bound_request(protocol_shape["roles"][term["after"]["role"]]["request_ref"], requests=requests, binding_plan=binding_plan)) for term in candidate["primary_predicate"]["terms"]):
                ineligible.append(CandidateLocalFailure("M11b", "binding", "joint_resource_checkpoint_selector_mismatch").record(candidate_id, status="materialization_ineligible"))
                continue
        observations = {
            slot: {
                "actor_id": observer_request["actor_id"],
                "method": observer_request["method"],
                "path": observer_request["path"],
                **_graphql_operation_binding(
                    bound.observer_request_ref, requests=requests
                ),
                "request_shape_sha256": request_shape_sha256(
                    _transport_shape(observer_request)
                ),
                **(
                    {
                        "observer_policy_ref": observer_policy_ref,
                        "observer_policy_sha256": observer_policy_sha,
                    }
                    if output_level == "forensic" and not is_single_arm
                    else {}
                ),
            }
            for slot in ("Oc1", "Oc2", "Ot0", "Ot1")
        }
        if is_v2:
            observations = {
                "observation": {
                    "actor_id": observer_request["actor_id"],
                    "method": observer_request["method"],
                    "path": observer_request["path"],
                    **_graphql_operation_binding(bound.observer_request_ref, requests=requests),
                    "request_ref": bound.observer_request_ref,
                    "request_shape_sha256": request_shape_sha256(_transport_shape(observer_request)),
                }
            }
        elif is_v3 or is_v9 or is_v8:
            observations = {
                step["role"]: {
                    "actor_id": step["actor"] if is_v8 or is_v9 else protocol_shape["roles"][step["role"]]["actor"],
                    "method": _bound_request(
                        step["request_ref"], requests=requests, binding_plan=binding_plan
                    )["method"],
                    "path": _bound_request(
                        step["request_ref"], requests=requests, binding_plan=binding_plan
                    )["path"],
                    **_graphql_operation_binding(
                        step["request_ref"], requests=requests
                    ),
                    "request_ref": step["request_ref"],
                    "request_shape_sha256": request_shape_sha256(
                        _transport_shape(_bound_request(
                            step["request_ref"], requests=requests, binding_plan=binding_plan
                        ))
                    ),
                }
                for step in protocol_shape["observation_plan" if is_v9 or is_v8 else "query_plan"]
            }
        elif is_v4:
            observations = {
                **(
                    {
                        "workflow_before": {
                            "actor_id": before_request["actor_id"],
                            "method": before_request["method"],
                            "path": before_request["path"],
                            **_graphql_operation_binding(
                                before_ref, requests=requests
                            ),
                            "request_ref": before_ref,
                            "request_shape_sha256": request_shape_sha256(
                                _transport_shape(before_request)
                            ),
                        }
                    }
                    if not is_no_before_v4
                    else {}
                ),
                "workflow_after": {
                    "actor_id": observer_request["actor_id"],
                    "method": observer_request["method"],
                    "path": observer_request["path"],
                    **_graphql_operation_binding(
                        bound.observer_request_ref, requests=requests
                    ),
                    "request_ref": bound.observer_request_ref,
                    "request_shape_sha256": request_shape_sha256(
                        _transport_shape(observer_request)
                    ),
                },
            }
        elif is_v5:
            observations = {}
            for step in protocol_shape["repeated_plan"]:
                if step["kind"] != "observe":
                    continue
                request = before_request if step["role"] == "before" else observer_request
                ref = before_ref if step["role"] == "before" else bound.observer_request_ref
                observations[step["step_id"]] = {"actor_id": request["actor_id"], "method": request["method"], "path": request["path"], "request_ref": ref,
                    "request_shape_sha256": request_shape_sha256(_transport_shape(request)), **_graphql_operation_binding(ref, requests=requests)}
        elif is_v6:
            observations = {
                "negative_before": {
                    "actor_id": before_request["actor_id"],
                    "method": before_request["method"],
                    "path": before_request["path"],
                    **_graphql_operation_binding(before_ref, requests=requests),
                    "request_ref": before_ref,
                    "request_shape_sha256": request_shape_sha256(
                        _transport_shape(before_request)
                    ),
                },
                "negative_after": {
                    "actor_id": observer_request["actor_id"],
                    "method": observer_request["method"],
                    "path": observer_request["path"],
                    **_graphql_operation_binding(
                        bound.observer_request_ref, requests=requests
                    ),
                    "request_ref": bound.observer_request_ref,
                    "request_shape_sha256": request_shape_sha256(
                        _transport_shape(observer_request)
                    ),
                },
            }
        elif is_v7:
            observations = {
                "actor_before": {
                    "actor_id": before_request["actor_id"],
                    "method": before_request["method"],
                    "path": before_request["path"],
                    **_graphql_operation_binding(
                        before_ref, requests=requests
                    ),
                    "request_ref": before_ref,
                    "request_shape_sha256": request_shape_sha256(
                        _transport_shape(before_request)
                    ),
                },
                "actor_after": {
                    "actor_id": observer_request["actor_id"],
                    "method": observer_request["method"],
                    "path": observer_request["path"],
                    **_graphql_operation_binding(
                        bound.observer_request_ref, requests=requests
                    ),
                    "request_ref": bound.observer_request_ref,
                    "request_shape_sha256": request_shape_sha256(
                        _transport_shape(observer_request)
                    ),
                },
            }
        binding_payload = {
            "schema_version": "ui-semantics-route-s-execution-binding-payload-v2",
            "candidate_id": candidate_id,
            "observations": observations,
            "producer": {
                "actor_id": producer_request["actor_id"],
                "method": producer_request["method"],
                "path": producer_request["path"],
                "request_shape_sha256": request_shape_sha256(
                    _transport_shape(producer_request)
                ),
                **(
                    {
                        "observer_policy_ref": observer_policy_ref,
                        "observer_policy_sha256": observer_policy_sha,
                    }
                    if output_level == "forensic" and not is_single_arm
                    else {}
                ),
                **(
                    {"action_ref": producer_action_ref}
                    if producer_action_ref is not None
                    else {}
                ),
                "request_ref": bound.producer_request_ref,
            } if producer_request is not None else None,
            "setup": (
                {(
                    "temporal" if is_v8
                    else "multi_resource" if is_v9
                    else "single_state" if is_v2
                    else "metamorphic_query" if is_v3
                    else "workflow" if is_v4
                    else "negative_no_effect" if is_v6
                    else "actor_matrix"
                ): copy.deepcopy(setup_rows)}
                if is_single_arm
                else {
                    "control": copy.deepcopy(setup_rows),
                    "treatment": copy.deepcopy(setup_rows),
                }
            ),
            "sensitive_classification": classification,
        }
        if is_v8 and "before" in protocol_shape["roles"]:
            before = _bound_request(protocol_shape["roles"]["before"]["request_ref"], requests=requests, binding_plan=binding_plan)
            binding_payload["observations"]["workflow_before"] = {"actor_id": before["actor_id"], "method": before["method"], "path": before["path"], "request_ref": protocol_shape["roles"]["before"]["request_ref"], "request_shape_sha256": request_shape_sha256(_transport_shape(before))}
        if is_v5:
            epochs = ("repeat_once", "repeat_twice") if protocol_shape["repetition_kind"] == "repeat_equal" else ("repeat_twice",)
            binding_payload["setup"] = {epoch: copy.deepcopy(setup_rows) for epoch in epochs}
        if is_v4 and protocol_shape.get("workflow_kind") == "inverse_restoration":
            inverse_ref = str(protocol_shape["roles"]["inverse"]["request_ref"])
            inverse = _bound_request(inverse_ref, requests=requests, binding_plan=binding_plan)
            binding_payload["inverse"] = {"actor_id": inverse["actor_id"], "method": inverse["method"], "path": inverse["path"], "request_ref": inverse_ref,
                "request_shape_sha256": request_shape_sha256(_transport_shape(inverse))}
            binding_payload["observations"]["workflow_intermediate"] = copy.deepcopy(observations["workflow_before"])
        if output_level == "forensic" and not is_single_arm:
            binding_ref = f"{prefix}/execution_binding.payload.json"
            execution_binding = bind_execution_payload(binding_payload, binding_ref)
            execution_binding_bytes = canonical_json_bytes(binding_payload)
            validate_execution_binding_v2(execution_binding)
            pins_payload = {
                "schema_version": "ui-semantics-route-s-pre-live-binding-pins-payload-v2",
                "candidate_id": candidate_id,
                "candidate_identity": candidate["candidate_identity"],
                "normalized_candidate_sha256": candidate["normalized_candidate_sha256"],
                "canonical_candidate_payload_sha256": canonical_sha256(candidate),
                "execution_binding_ref": execution_binding["artifact_ref"],
                "execution_binding_sha256": execution_binding["artifact_sha256"],
                "sensitive_classification_ref": classification_ref,
                "sensitive_classification_sha256": classification_sha,
                "projection_plan_ref": projection_ref,
                "projection_plan_sha256": projection["artifact_sha256"],
            }
            pins_ref = f"{prefix}/pre_live_binding_pins.payload.json"
            pre_live_pins = bind_pre_live_pins_v2(pins_payload, pins_ref)
            pre_live_pins_bytes = canonical_json_bytes(pins_payload)
            validate_pre_live_binding_pins_v2(pre_live_pins)
            scientific_pins_ref = f"{prefix}/scientific_pins.json"
            scientific_pins_bytes = canonical_json_bytes(dict(scientific_pins))
        else:
            binding_payload = copy.deepcopy(binding_payload)
            binding_payload.pop("schema_version", None)
            execution_binding = {"payload": binding_payload}
            execution_binding_bytes = canonical_json_bytes(binding_payload)
            pre_live_pins = {}
            pre_live_pins_bytes = b""

        try:
            arms = (
                ("temporal",) if is_v8
                else ("multi_resource",) if is_v9
                else ("single_state",) if is_v2
                else ("metamorphic_query",) if is_v3
                else ("workflow",) if is_v4
                else (("repeat_once", "repeat_twice") if protocol_shape["repetition_kind"] == "repeat_equal" else ("repeat_twice",)) if is_v5
                else ("negative_no_effect",) if is_v6
                else ("actor_matrix",) if is_v7
                else ("control", "treatment")
            )
            resource_plans = {
                arm: _resource_binding_plan(
                    candidate_id=candidate_id,
                    arm=arm,
                    candidate=candidate,
                    binding_plan=binding_plan,
                    value_flows=value_flows,
                    trace=trace,
                    prerequisite_plan=prerequisite_plan,
                    recording_plan=recording_plan,
                    setup_closure_provenance=setup_closure_provenance,
                    closure_only_request_refs=closure_only_request_refs,
                    capture_producer_identity_in_control=bool(
                        producer_lookup_rows
                    ),
                    workflow_before=(
                        {
                            "request_ref": before_ref,
                            "actor_id": before_request["actor_id"],
                        }
                        if (is_v4 and not is_no_before_v4) or is_v5 or (is_v6 and not negative_standalone)
                        else None
                    ),
                    deferred_workflow_binding=deferred_workflow_binding,
                    recording_trace=recording_trace,
                    authenticated_actor_identity_paths=(
                        authenticated_actor_identity_paths or {}
                    ),
                    runtime_source_refs=(
                        {
                            str(step["request_ref"]): str(
                                protocol_shape["roles"][step["role"]]["actor"]
                            )
                            for step in protocol_shape["query_plan"]
                        }
                        if is_v3
                        else {}
                    ),
                )
                for arm in arms
            }
            request_material_bindings = _candidate_request_material_bindings(
                candidate=candidate,
                protocol_shape=protocol_shape,
                request_bindings=binding_plan["request_bindings"],
                available_bindings=binding_plan.get("request_material_bindings", ()),
                resource_plans=resource_plans,
            )
            projection_identity = _recorded_projection_member_identity(
                candidate,
                recording_trace=recording_trace,
            )
            if projection_identity is not None:
                _close_projection_identity_sources(
                    candidate=candidate,
                    resource_plans=resource_plans,
                    recorded_identity=projection_identity,
                    recording_material_aliases=recording_material_aliases,
                )
            _require_runtime_request_material(
                candidate=candidate,
                protocol_shape=protocol_shape,
                request_bindings=binding_plan["request_bindings"],
                resource_plans=resource_plans,
                request_material_bindings=request_material_bindings,
            )
        except CandidateLocalFailure as error:
            ineligible.append(
                error.record(candidate_id, status="materialization_ineligible")
            )
            continue
        execution_material = {
            "schema_version": "uisemtest-current-route-s-execution-material-v1",
            "document_kind": "execution_material",
            "candidate_id": candidate_id,
            "bound_candidate_sha256": bound.canonical_sha256(),
            "candidate_sha256": canonical_sha256(
                {key: value for key, value in candidate.items() if key != "source_hashes"}
            ),
            "execution_binding": copy.deepcopy(binding_payload),
            "projection_plan": copy.deepcopy(projection_payload),
            "observer_policy": copy.deepcopy(observer_policy),
            "settle_policy": copy.deepcopy(settle_policy),
            "sensitive_classification": copy.deepcopy(classification_payload),
            "resource_binding_plans": copy.deepcopy(resource_plans),
            **(
                {
                    "request_material_bindings": copy.deepcopy(
                        list(request_material_bindings)
                    )
                }
                if request_material_bindings
                else {}
            ),
            "protocol_shape": protocol_shape,
        }
        execution_material_bytes = canonical_json_bytes(execution_material)
        if output_level != "forensic" or is_single_arm:
            candidate_ref = f"{prefix}/candidate.json"
            material_ref = f"{prefix}/execution_material.json"
            artifacts = {
                candidate_ref: canonical_json_bytes(candidate),
                material_ref: execution_material_bytes,
            }
            hashes = {
                ref: hashlib.sha256(payload).hexdigest()
                for ref, payload in artifacts.items()
            }
            result.append(
                RouteSPreLiveMaterializedCandidate(
                    candidate_id=candidate_id,
                    bound_candidate_sha256=bound.canonical_sha256(),
                    candidate=candidate,
                    execution_binding={"payload": binding_payload},
                    execution_binding_bytes=canonical_json_bytes(binding_payload),
                    pre_live_binding_pins={},
                    pre_live_binding_pins_bytes=b"",
                    projection_plan=projection_payload,
                    observer_policy=observer_policy,
                    settle_policy=settle_policy,
                    sensitive_classification=classification_payload,
                    resource_binding_plans=resource_plans,
                    scientific_pins={},
                    artifact_bytes=artifacts,
                    artifact_hashes=hashes,
                    artifact_inventory=(),
                    execution_material=execution_material,
                    execution_material_bytes=execution_material_bytes,
                    output_level=output_level,
                )
            )
            continue
        artifacts = {
            f"{prefix}/candidate.json": canonical_json_bytes(candidate),
            f"{prefix}/execution_material.json": execution_material_bytes,
            bound_ref: bound.canonical_bytes(),
            projection_ref: projection_bytes,
            observer_policy_ref: observer_policy_bytes,
            settle_policy_ref: settle_policy_bytes,
            classification_ref: classification_bytes,
            binding_ref: execution_binding_bytes,
            pins_ref: pre_live_pins_bytes,
            scientific_pins_ref: scientific_pins_bytes,
        }
        for arm, plan in resource_plans.items():
            artifacts[f"{prefix}/resource_binding_plan.{arm}.json"] = canonical_json_bytes(
                plan
            )
        hashes = {ref: hashlib.sha256(payload).hexdigest() for ref, payload in artifacts.items()}
        inventory = tuple(
            {
                "artifact_ref": ref,
                "artifact_sha256": hashes[ref],
                "bytes": len(artifacts[ref]),
            }
            for ref in sorted(artifacts)
        )
        result.append(
            RouteSPreLiveMaterializedCandidate(
                candidate_id=candidate_id,
                bound_candidate_sha256=bound.canonical_sha256(),
                candidate=candidate,
                execution_binding=execution_binding,
                execution_binding_bytes=execution_binding_bytes,
                pre_live_binding_pins=pre_live_pins,
                pre_live_binding_pins_bytes=pre_live_pins_bytes,
                projection_plan=projection,
                observer_policy=observer_policy,
                settle_policy=settle_policy,
                sensitive_classification=classification_payload,
                resource_binding_plans=resource_plans,
                scientific_pins=dict(scientific_pins),
                artifact_bytes=artifacts,
                artifact_hashes=hashes,
                artifact_inventory=inventory,
                execution_material=execution_material,
                execution_material_bytes=execution_material_bytes,
                output_level=output_level,
            )
        )
    return RouteSM11bMaterializationResult(
        materials=tuple(result),
        ineligible=tuple(ineligible),
    )


def validate_and_persist_current_route_s_material(
    material: RouteSPreLiveMaterializedCandidate,
    *,
    run_root: Path,
    output_level: str,
) -> RouteSPreLiveMaterializedCandidate:
    """Validate M11b contracts and persist the selected review-level boundary."""

    root = run_root.resolve()
    prefix = f"M11b/{material.candidate_id}"
    if output_level not in {"paper", "debug", "forensic"}:
        raise ValueError(f"unknown current output level: {output_level!r}")
    candidate_root = (root / prefix).resolve()
    if not candidate_root.is_relative_to(root / "M11b"):
        raise ValueError("M11b candidate output path escapes the stage root")
    if candidate_root.exists():
        raise CandidateLocalFailure(
            "M11b", "writer", "candidate_artifact_collision"
        )

    validate_current_route_s_material(material.execution_material)
    is_single_arm = material.execution_material.get("protocol_shape", {}).get(
        "shape_kind"
    ) in {
        "lifecycle_workflow", "actor_matrix", "metamorphic_query",
        "negative_no_effect", "single_state", "repeated_execution", "multi_resource", "temporal",
    }
    if output_level != "forensic" or is_single_arm:
        candidate_ref = f"{prefix}/candidate.json"
        material_ref = f"{prefix}/execution_material.json"
        expected = {
            candidate_ref: canonical_json_bytes(material.candidate),
            material_ref: material.execution_material_bytes,
        }
        if expected != material.artifact_bytes:
            raise ValueError("M11b compact artifact set drifted")
        for ref, payload in expected.items():
            _write_exact(root / ref, payload)
        return material

    computed_hashes = {
        ref: hashlib.sha256(payload).hexdigest()
        for ref, payload in material.artifact_bytes.items()
    }
    if computed_hashes != material.artifact_hashes:
        raise ValueError("M11b in-memory artifact hashes drifted")
    expected_inventory = tuple(
        {
            "artifact_ref": ref,
            "artifact_sha256": computed_hashes[ref],
            "bytes": len(material.artifact_bytes[ref]),
        }
        for ref in sorted(material.artifact_bytes)
    )
    if expected_inventory != material.artifact_inventory:
        raise ValueError("M11b in-memory artifact inventory drifted")
    validate_execution_binding_v2(material.execution_binding)
    validate_pre_live_binding_pins_v2(material.pre_live_binding_pins)
    _validate_wrapper_payload_file(material.execution_binding, material.artifact_bytes)
    _validate_wrapper_payload_file(
        material.pre_live_binding_pins,
        material.artifact_bytes,
    )

    binding_wrapper_ref = f"{prefix}/execution_binding.wrapper.json"
    binding_wrapper_bytes = canonical_json_bytes(material.execution_binding)
    pins_wrapper_ref = f"{prefix}/pre_live_binding_pins.wrapper.json"
    pins_wrapper_bytes = canonical_json_bytes(material.pre_live_binding_pins)
    complete_inventory = [*material.artifact_inventory]
    for ref, payload in (
        (binding_wrapper_ref, binding_wrapper_bytes),
        (pins_wrapper_ref, pins_wrapper_bytes),
    ):
        complete_inventory.append(
            {
                "artifact_ref": ref,
                "artifact_sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    complete_inventory.sort(key=lambda row: str(row["artifact_ref"]))
    scientific_pins_ref = f"{prefix}/scientific_pins.json"
    manifest = {
        "schema_version": "uisemtest-m11b-material-manifest-v1",
        "candidate_id": material.candidate_id,
        "bound_candidate_sha256": material.bound_candidate_sha256,
        "execution_binding": {
            "path": binding_wrapper_ref,
            "sha256": hashlib.sha256(binding_wrapper_bytes).hexdigest(),
        },
        "pre_live_binding_pins": {
            "path": pins_wrapper_ref,
            "sha256": hashlib.sha256(pins_wrapper_bytes).hexdigest(),
        },
        "scientific_pins": {
            "path": scientific_pins_ref,
            "sha256": material.artifact_hashes[scientific_pins_ref],
        },
        "projection_plan": {
            "path": material.projection_plan["artifact_ref"],
            "sha256": material.projection_plan["artifact_sha256"],
        },
        "resource_binding_plans": {
            arm: {
                "path": f"{prefix}/resource_binding_plan.{arm}.json",
                "sha256": material.artifact_hashes[
                    f"{prefix}/resource_binding_plan.{arm}.json"
                ],
            }
            for arm in ("control", "treatment")
        },
        "artifact_inventory": complete_inventory,
        "persistence_boundary": "write_reload_validate_before_route_s",
        "adapter_scientific_decision_fields": 0,
        "live_execution_count": 0,
    }
    manifest_ref = f"{prefix}/material_manifest.json"
    manifest_bytes = canonical_json_bytes(manifest)
    enriched_artifacts = {
        **material.artifact_bytes,
        binding_wrapper_ref: binding_wrapper_bytes,
        pins_wrapper_ref: pins_wrapper_bytes,
        manifest_ref: manifest_bytes,
    }
    for ref, payload in sorted(material.artifact_bytes.items()):
        _write_exact(root / ref, payload)

    _write_exact(root / binding_wrapper_ref, binding_wrapper_bytes)
    _write_exact(root / pins_wrapper_ref, pins_wrapper_bytes)
    manifest_path = root / manifest_ref
    _write_exact(manifest_path, manifest_bytes)

    loaded_manifest = _read_object(manifest_path)
    if loaded_manifest != manifest:
        raise ValueError("M11b material manifest write/reload drift")
    loaded_artifacts: dict[str, bytes] = {}
    loaded_hashes: dict[str, str] = {}
    for row in loaded_manifest["artifact_inventory"]:
        ref = str(row["artifact_ref"])
        path = root / ref
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if len(payload) != row["bytes"] or digest != row["artifact_sha256"]:
            raise ValueError("M11b artifact inventory reload mismatch")
        loaded_artifacts[ref] = payload
        loaded_hashes[ref] = digest
    manifest_ref = manifest_path.relative_to(root).as_posix()
    manifest_payload = manifest_path.read_bytes()
    loaded_artifacts[manifest_ref] = manifest_payload
    loaded_hashes[manifest_ref] = hashlib.sha256(manifest_payload).hexdigest()

    execution_binding = _read_object(root / binding_wrapper_ref)
    pre_live_pins = _read_object(root / pins_wrapper_ref)
    validate_execution_binding_v2(execution_binding)
    validate_pre_live_binding_pins_v2(pre_live_pins)
    _validate_wrapper_payload_file(execution_binding, loaded_artifacts)
    _validate_wrapper_payload_file(pre_live_pins, loaded_artifacts)
    scientific_pins = _read_object(root / scientific_pins_ref)
    if scientific_pins != material.scientific_pins:
        raise ValueError("M11b scientific pins changed across persistence")

    projection_payload = _read_object(root / material.projection_plan["artifact_ref"])
    projection = {
        **projection_payload,
        "artifact_ref": material.projection_plan["artifact_ref"],
        "artifact_sha256": material.projection_plan["artifact_sha256"],
    }
    resource_plans = {
        arm: _read_object(root / f"{prefix}/resource_binding_plan.{arm}.json")
        for arm in ("control", "treatment")
    }
    observer_ref = next(
        ref for ref in loaded_artifacts if ref.endswith("/observer_policy.json")
    )
    settle_ref = next(
        ref for ref in loaded_artifacts if ref.endswith("/settle_policy.json")
    )
    classification_ref = next(
        ref
        for ref in loaded_artifacts
        if ref.endswith("/sensitive_classification.json")
    )
    return replace(
        material,
        execution_binding=execution_binding,
        execution_binding_bytes=loaded_artifacts[
            execution_binding["artifact_ref"]
        ],
        pre_live_binding_pins=pre_live_pins,
        pre_live_binding_pins_bytes=loaded_artifacts[
            pre_live_pins["artifact_ref"]
        ],
        projection_plan=projection,
        observer_policy=_read_object(root / observer_ref),
        settle_policy=_read_object(root / settle_ref),
        sensitive_classification=_read_object(root / classification_ref),
        resource_binding_plans=resource_plans,
        scientific_pins=scientific_pins,
        artifact_bytes=loaded_artifacts,
        artifact_hashes=loaded_hashes,
        artifact_inventory=tuple(loaded_manifest["artifact_inventory"]),
    )


def _validate_wrapper_payload_file(
    wrapper: Mapping[str, Any],
    artifacts: Mapping[str, bytes],
) -> None:
    ref = str(wrapper["artifact_ref"])
    payload = artifacts.get(ref)
    if payload is None or hashlib.sha256(payload).hexdigest() != wrapper[
        "artifact_sha256"
    ]:
        raise ValueError("M11b wrapper payload file hash mismatch")
    if json.loads(payload) != wrapper["payload"]:
        raise ValueError("M11b wrapper payload file content mismatch")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"M11b persisted artifact is not an object: {path}")
    return value


def _write_exact(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"M11b refuses to overwrite: {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _fresh_flow_target(
    flow: Any,
    *,
    binding_plan: Mapping[str, Any],
    strict: bool,
) -> tuple[str, str, str] | None:
    def reject(stage: str, reason: str) -> None:
        if strict:
            raise CandidateLocalFailure("M11b", stage, reason)

    if flow.from_location != "response_body":
        reject("contract", "fresh_source_not_response_body_scalar")
        return None
    location = _target_location(str(flow.to_location))
    policy = binding_plan["fresh_materialization_policy"]
    if location not in policy["allowed_target_locations"]:
        reject("contract", "fresh_target_location_not_admitted")
        return None
    if _session_managed_binding_material(
        location=location,
        target_field=str(flow.to_field),
        source_field=str(flow.from_field),
    ):
        return None
    consumer_ref = str(flow.consumer_request_ref)
    template = binding_plan["request_bindings"].get(consumer_ref)
    if not isinstance(template, Mapping):
        reject("binding", "fresh_consumer_request_binding_missing")
        return None
    path_targets = binding_plan.get("path_binding_targets") or {}
    target_path = str(path_targets.get(consumer_ref, {}).get(flow.to_field, ""))
    if location != "path":
        target_path = _typed_path(str(flow.to_field), location=location)
    if location == "path":
        if not (
            target_path.startswith("$.segments[") and target_path.endswith("]")
        ):
            reject("binding", "path_flow_target_segment_unresolved")
            return None
        if not _path_target_is_variable(
            consumer_ref, target_path, path_binding_targets=path_targets
        ):
            return None
    scalar_type = _json_scalar_type(_binding_template_value(template, location, target_path))
    if scalar_type not in policy["allowed_scalar_types"]:
        reject("contract", "fresh_scalar_type_not_admitted")
        return None
    return location, target_path, scalar_type


def _flow_provenance_key(flow: Any) -> tuple[str, str, str, str, str]:
    return tuple(
        str(value)
        for value in (
            flow.consumer_request_ref, flow.producer_request_ref,
            flow.from_field, flow.to_location, flow.to_field,
        )
    )

def _expand_setup_request_chain(
    selected_setup: list[dict[str, str]],
    *,
    trace: UiApiTrace,
    value_flows: ObservedValueFlowSet,
    eligible_domain_refs: set[str],
    recording_plan: SetupBindingPlan | None,
    recording_trace: Mapping[str, Any] | None,
    binding_plan: Mapping[str, Any] | None = None,
    ordinary_setup_refs: set[str] | None = None,
    strict_identity_field_pairs: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[list[dict[str, str]], Mapping[Any, Any], frozenset[str]]:
    """Close setup inputs and indexed-member creators inside the frozen domain."""

    if not selected_setup:
        return [], {}, frozenset()
    requests = {
        str(row["request_ref"]): row for row in trace.trace["api_requests"]
    }
    order = {
        str(row["request_ref"]): index
        for index, row in enumerate(trace.trace["api_requests"])
    }
    selected_refs = [str(row["request_ref"]) for row in selected_setup]
    if len(selected_refs) != len(set(selected_refs)):
        raise CandidateLocalFailure(
            "M11b", "contract", "selected_setup_request_refs_not_unique"
        )
    for row in selected_setup:
        request = requests.get(str(row["request_ref"]))
        if request is None or request.get("actor_id") != row.get("actor_id"):
            raise CandidateLocalFailure(
                "M11b", "binding", "selected_setup_request_actor_missing"
            )

    ordinary_refs = set(ordinary_setup_refs or selected_refs)
    preclosed_refs = ordinary_refs - set(selected_refs)
    required, scoped_refs = set(), set()
    provenance: dict[Any, Any] = {}
    visiting: set[str] = set()
    def closure_target(flow: Any) -> tuple[str, str, str] | None:
        target = (
            _fresh_flow_target(flow, binding_plan=binding_plan, strict=False)
            if binding_plan is not None else None
        )
        indexed_match = _INDEXED_MEMBER_PATH.fullmatch(str(flow.from_field))
        strict_identity_locator = (
            indexed_match is not None
            and any(
                collection_item_path == "$" + indexed_match.group("field")
                for collection_item_path, _member_path
                in strict_identity_field_pairs
            )
        )
        if target and (
            target[0] != "path"
            and _request_is_read_only(
                str(flow.producer_request_ref),
                bound_request=binding_plan["request_bindings"].get(
                    str(flow.producer_request_ref), {}
                ),
                requests=requests,
            )
            and not strict_identity_locator
        ):
            target = None
        return target

    def include(request_ref: str) -> None:
        if request_ref in required:
            return
        if request_ref in visiting:
            raise CandidateLocalFailure(
                "M11b", "binding", "setup_dependency_cycle"
            )
        visiting.add(request_ref)
        closure_only = request_ref not in ordinary_refs
        consumer = requests[request_ref]
        by_target: dict[tuple[str, str], list[Any]] = {}
        for flow in value_flows.flows:
            if (
                flow.consumer_request_ref != request_ref
                or flow.consumer_actor_id != consumer["actor_id"]
                or flow.to_location not in {"path", "query", "header", "body"}
            ):
                continue
            producer = requests.get(flow.producer_request_ref)
            if (
                producer is None
                or producer.get("actor_id") != consumer["actor_id"]
                or order[flow.producer_request_ref] >= order[request_ref]
            ):
                continue
            by_target.setdefault((flow.to_location, flow.to_field), []).append(flow)
        for rows in by_target.values():
            latest_order = max(order[row.producer_request_ref] for row in rows)
            latest_refs = {
                row.producer_request_ref
                for row in rows
                if order[row.producer_request_ref] == latest_order
            }
            if len(latest_refs) != 1:
                raise CandidateLocalFailure(
                    "M11b", "binding", "setup_dependency_producer_ambiguous"
                )
            source_ref = next(iter(latest_refs))
            if request_ref in scoped_refs:
                scoped_refs.add(source_ref)
            for flow in rows:
                if flow.producer_request_ref != source_ref:
                    continue
                target = closure_target(flow)
                if closure_only and target is None:
                    continue
                creator = _indexed_member_creator_source(
                    flow,
                    target=target,
                    requests=requests,
                    request_order=order,
                    eligible_domain_refs=eligible_domain_refs,
                    recording_plan=recording_plan,
                    recording_trace=recording_trace,
                    binding_plan=binding_plan,
                    strict_identity_field_pairs=strict_identity_field_pairs,
                ) if target is not None else None
                if target is not None:
                    key = _flow_provenance_key(flow)
                    value = (*target, creator)
                    if key in provenance and provenance[key] != value:
                        raise CandidateLocalFailure(
                            "M11b", "binding", "setup_closure_edge_ambiguous"
                        )
                    provenance[key] = value
                if creator is not None:
                    scoped_refs.update({request_ref, source_ref, creator.creator_request_ref})
                    if creator.creator_request_ref not in preclosed_refs:
                        include(creator.creator_request_ref)
            include(source_ref)
        visiting.remove(request_ref)
        required.add(request_ref)

    for request_ref in selected_refs:
        include(request_ref)
    closure_only_refs = frozenset(scoped_refs - ordinary_refs)
    for flow in value_flows.flows:
        if (
            str(flow.producer_request_ref) not in closure_only_refs
            or str(flow.consumer_request_ref) not in required
        ):
            continue
        target = closure_target(flow)
        if target is None:
            continue
        provenance.setdefault(_flow_provenance_key(flow), (*target, None))
    return (
        [
            {"actor_id": str(requests[ref]["actor_id"]), "request_ref": ref}
            for ref in sorted(required, key=order.__getitem__)
        ],
        dict(sorted(provenance.items())),
        closure_only_refs,
    )


def _indexed_member_creator_source(
    flow: Any,
    *,
    target: tuple[str, str, str],
    requests: Mapping[str, Mapping[str, Any]],
    request_order: Mapping[str, int],
    eligible_domain_refs: set[str],
    recording_plan: SetupBindingPlan | None,
    recording_trace: Mapping[str, Any] | None,
    binding_plan: Mapping[str, Any],
    strict_identity_field_pairs: frozenset[tuple[str, str]],
) -> Any | None:
    """Resolve one stable locator to one earlier state-changing creator.

    Field names are not identity evidence.  The recorded indexed member must
    instead be unique and the same typed scalar must either flow into a proven
    variable path or match one field of the candidate's strict identity tuple.
    Only a unique, successful, earlier state-changing response in the bounded
    setup domain may replace the order-unstable collection read.
    """

    source_ref = str(flow.producer_request_ref)
    source = requests.get(source_ref)
    indexed_path = _INDEXED_MEMBER_PATH.fullmatch(str(flow.from_field))
    if (
        source is None
        or source_ref not in eligible_domain_refs
        or flow.from_location != "response_body"
        or indexed_path is None
        or not _request_is_read_only(
            source_ref,
            bound_request=source,
            requests=requests,
        )
    ):
        return None
    recorded_source = _recorded_request_facts(recording_trace).get(source_ref)
    if recorded_source is None:
        return None
    value = extract_typed_value(
        recorded_source.get("response_body"), str(flow.from_field)
    )
    if typed_value_is_missing(value) or not isinstance(
        value, (str, int, float, bool)
    ):
        return None
    scalar_type = _json_scalar_type(value)
    if os.environ.get("UISEMTEST_M11B_DEBUG"):
        print(
            "[m11b-debug] indexed-member creator lookup",
            {"flow": f"{flow.producer_request_ref} {flow.from_field} -> {flow.consumer_request_ref} {flow.to_location}:{flow.to_field}",
             "target": target, "identity_field": bool(_identity_field_name(str(flow.from_field))),
             "recording_plan_sources": [
                 (src.creator_request_ref, src.response_path, src.recorded_value_sha256[:8])
                 for src in (recording_plan.sources if recording_plan is not None else ())
                 if src.recorded_value_sha256 == scalar_sha256(value)
             ],
             "value_sha": scalar_sha256(value)[:8],
             "domain_size": len(eligible_domain_refs),
             "binding_plan": binding_plan is not None},
            file=sys.stderr, flush=True,
        )
    if _identity_field_name(str(flow.from_field)):
        matches = {
            (
                candidate.creator_request_ref,
                candidate.response_path,
                candidate.scalar_type,
                candidate.recorded_value_sha256,
            ): candidate
            for candidate in (recording_plan.sources if recording_plan is not None else ())
            if candidate.creator_request_ref in eligible_domain_refs
            and candidate.creator_request_ref in request_order
            and request_order[candidate.creator_request_ref]
            < request_order[source_ref]
            and candidate.scalar_type == scalar_type
            and candidate.recorded_value_sha256 == scalar_sha256(value)
            and _identity_field_name(candidate.response_path)
        }
        if (
            not matches
            and binding_plan is not None
            and not isinstance(value, bool)
            and not _is_redacted_runtime_material(value)
        ):
            # The recording plan only carries same-session value flows, so a
            # resource created by another actor never appears in it and an
            # identity read from an order-unstable collection would keep
            # pointing at the lookup.  The bounded rule used for non-identity
            # locators applies unchanged: one unique, successful, earlier
            # state-changing response in the frozen setup domain that carries
            # the exact scalar at an identity-named path.
            matches = _domain_indexed_member_creator_matches(
                value,
                scalar_type=scalar_type,
                source_ref=source_ref,
                requests=requests,
                request_order=request_order,
                eligible_domain_refs=eligible_domain_refs,
                recording_trace=recording_trace,
                binding_plan=binding_plan,
                locator_evidence=lambda response_path: bool(
                    _identity_field_name(response_path)
                ),
            )
        return _unique_indexed_member_creator(matches)
    if isinstance(value, bool) or _is_redacted_runtime_material(value):
        return None
    if scalar_type != target[2]:
        return None
    collection = extract_typed_value(
        recorded_source.get("response_body"), indexed_path.group("collection")
    )
    member_path = "$" + indexed_path.group("field")
    recorded_member_matches = [
        member
        for member in collection
        if isinstance(member, Mapping)
        and (
            member_value := extract_typed_value(member, member_path)
        ) is not None
        and not typed_value_is_missing(member_value)
        and type(member_value) is type(value)
        and member_value == value
    ] if isinstance(collection, list) else []
    if len(recorded_member_matches) != 1:
        if len(recorded_member_matches) > 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "setup_indexed_member_locator_ambiguous"
            )
        return None

    def locator_evidence(response_path: str) -> bool:
        if target[0] == "path":
            return True
        return any(
            collection_item_path == member_path
            and response_path.endswith(member_identity_path.removeprefix("$"))
            for collection_item_path, member_identity_path
            in strict_identity_field_pairs
        )

    matches: dict[tuple[str, str, str, str], ResourceBindingSource] = {
        (
            candidate.creator_request_ref,
            candidate.response_path,
            candidate.scalar_type,
            candidate.recorded_value_sha256,
        ): candidate
        for candidate in (recording_plan.sources if recording_plan is not None else ())
        if candidate.creator_request_ref in eligible_domain_refs
        and candidate.creator_request_ref in request_order
        and request_order[candidate.creator_request_ref] < request_order[source_ref]
        and not _request_is_read_only(
            candidate.creator_request_ref,
            bound_request=binding_plan["request_bindings"].get(
                candidate.creator_request_ref, {}
            ),
            requests=requests,
        )
        and candidate.scalar_type == _json_scalar_type(value)
        and candidate.recorded_value_sha256 == scalar_sha256(value)
        and locator_evidence(candidate.response_path)
    }
    for key, source_row in _domain_indexed_member_creator_matches(
        value,
        scalar_type=scalar_type,
        source_ref=source_ref,
        requests=requests,
        request_order=request_order,
        eligible_domain_refs=eligible_domain_refs,
        recording_trace=recording_trace,
        binding_plan=binding_plan,
        locator_evidence=locator_evidence,
    ).items():
        matches.setdefault(key, source_row)
    return _unique_indexed_member_creator(matches)


_COLLECTION_ID_LIKE_SEGMENT = re.compile(r"^(\d+|[0-9a-fA-F-]{8,}|\{[^}]*\})$")


def _collection_path_segments(path: Any) -> list[str]:
    return [segment for segment in str(path or "").split("?", 1)[0].split("/") if segment]


def _consumer_collection_before_value(path: Any, value: Any) -> str | None:
    """The collection segment that precedes ``value`` in a consumer path.

    A concrete path locates the value by equality of one segment; a canonical
    path locates it by its single placeholder segment.  Any other shape (value
    absent, repeated, several placeholders, or preceded by an id-like segment)
    yields ``None`` and leaves the caller's behaviour untouched.
    """

    segments = _collection_path_segments(path)
    hits = [index for index, segment in enumerate(segments) if segment == str(value)]
    if len(hits) != 1:
        hits = [
            index
            for index, segment in enumerate(segments)
            if segment.startswith("{") and segment.endswith("}")
        ]
        if len(hits) != 1:
            return None
    index = hits[0]
    if index < 1 or _COLLECTION_ID_LIKE_SEGMENT.match(segments[index - 1]):
        return None
    return segments[index - 1]


def _creator_collection_segment(path: Any) -> str | None:
    """The last non-id segment of a creator path (``/api/v1/projects/{id}/tasks`` -> ``tasks``)."""

    segments = [
        segment
        for segment in _collection_path_segments(path)
        if not _COLLECTION_ID_LIKE_SEGMENT.match(segment)
    ]
    return segments[-1] if segments else None


def _request_path_candidates(
    request_ref: str,
    *,
    requests: Mapping[str, Mapping[str, Any]],
    binding_plan: Mapping[str, Any],
) -> list[Any]:
    template = binding_plan.get("request_bindings", {}).get(request_ref)
    request = requests.get(request_ref)
    return [
        value
        for value in (
            template.get("path") if isinstance(template, Mapping) else None,
            request.get("canonical_path") if isinstance(request, Mapping) else None,
        )
        if value
    ]


def _collection_compatible_creator_matches(
    matches: dict[tuple[str, str, str, str], ResourceBindingSource],
    *,
    consumer_ref: str,
    value: Any,
    requests: Mapping[str, Mapping[str, Any]],
    binding_plan: Mapping[str, Any],
) -> dict[tuple[str, str, str, str], ResourceBindingSource]:
    """Disambiguate creators of one scalar by the consumer's path collection.

    Integer identifiers (Vikunja, Paperless-ngx) recur across unrelated write
    responses, so the exact-scalar match alone names several creators.  When
    the value sits in the consumer's path right after a collection segment
    (``/api/v1/projects/3``), only creators whose own path ends in that
    collection (``PUT /api/v1/projects``, ``PUT /api/v1/projects/{id}/tasks``
    for ``/api/v1/tasks/5``) are kept -- and only if exactly one creator
    remains.  Unique matches, values outside the path and unresolved cases
    return ``matches`` unchanged, so slug/UUID subjects are unaffected.
    """

    creator_refs = {key[0] for key in matches}
    if len(creator_refs) < 2:
        return matches
    collection = next(
        (
            found
            for found in (
                _consumer_collection_before_value(path, value)
                for path in _request_path_candidates(
                    consumer_ref, requests=requests, binding_plan=binding_plan
                )
            )
            if found
        ),
        None,
    )
    if collection is None:
        return matches
    compatible = {
        creator_ref
        for creator_ref in creator_refs
        if any(
            _creator_collection_segment(path) == collection
            for path in _request_path_candidates(
                creator_ref, requests=requests, binding_plan=binding_plan
            )
        )
    }
    if len(compatible) != 1:
        return matches
    return {key: row for key, row in matches.items() if key[0] in compatible}


def _domain_indexed_member_creator_matches(
    value: Any,
    *,
    scalar_type: str,
    source_ref: str,
    requests: Mapping[str, Mapping[str, Any]],
    request_order: Mapping[str, int],
    eligible_domain_refs: set[str],
    recording_trace: Mapping[str, Any] | None,
    binding_plan: Mapping[str, Any],
    locator_evidence: Callable[[str], bool],
) -> dict[tuple[str, str, str, str], ResourceBindingSource]:
    """Earlier state-changing domain responses that carry the exact scalar.

    Every actor's requests in the bounded setup domain are eligible; the
    caller decides whether the creator set is unique.
    """

    matches: dict[tuple[str, str, str, str], ResourceBindingSource] = {}
    recorded_requests = _recorded_request_facts(recording_trace)
    for candidate_ref in sorted(
        eligible_domain_refs,
        key=lambda request_ref: request_order.get(request_ref, len(request_order)),
    ):
        if (
            candidate_ref not in request_order
            or request_order[candidate_ref] >= request_order[source_ref]
            or _request_is_read_only(
                candidate_ref,
                bound_request=binding_plan["request_bindings"].get(
                    candidate_ref, {}
                ),
                requests=requests,
            )
        ):
            continue
        recorded_candidate = recorded_requests.get(candidate_ref)
        request_template = binding_plan["request_bindings"].get(candidate_ref)
        if (
            not isinstance(recorded_candidate, Mapping)
            or not isinstance(request_template, Mapping)
            or not 200 <= int(recorded_candidate.get("response_status", 0)) < 400
        ):
            continue
        request_hashes = _request_template_scalar_hashes(request_template)
        if os.environ.get("UISEMTEST_M11B_DEBUG"):
            print("[m11b-debug] domain candidate", candidate_ref, "status", recorded_candidate.get("response_status"),
                  "scalars", [(p, str(v)[:12]) for p, v in _recorded_scalar_paths(recorded_candidate.get("response_body")) if v == value][:3],
                  file=sys.stderr, flush=True)
        for response_path, candidate_value in _recorded_scalar_paths(
            recorded_candidate.get("response_body")
        ):
            if (
                not isinstance(candidate_value, (str, int, float))
                or isinstance(candidate_value, bool)
                or _is_redacted_runtime_material(candidate_value)
                or type(candidate_value) is not type(value)
                or candidate_value != value
                or scalar_sha256(candidate_value) in request_hashes
                or _session_managed_binding_material(
                    location="body",
                    target_field=response_path,
                    source_field=response_path,
                )
                or _authenticated_profile_field_is_forbidden(response_path)
                or not locator_evidence(response_path)
            ):
                continue
            source_row = ResourceBindingSource(
                source_id=canonical_sha256({
                    "creator_request_ref": candidate_ref,
                    "response_path": response_path,
                    "scalar_type": scalar_type,
                    "recorded_value_sha256": scalar_sha256(value),
                }),
                actor_id=str(requests[candidate_ref]["actor_id"]),
                creator_request_ref=candidate_ref,
                response_path=response_path,
                scalar_type=scalar_type,
                recorded_value_sha256=scalar_sha256(value),
            )
            matches.setdefault(
                (
                    candidate_ref,
                    response_path,
                    scalar_type,
                    scalar_sha256(value),
                ),
                source_row,
            )
    return _collection_compatible_creator_matches(
        matches,
        consumer_ref=source_ref,
        value=value,
        requests=requests,
        binding_plan=binding_plan,
    )


def _own_identity_response_path(paths: "Iterable[str]") -> str | None:
    """The one response path that is the entity's own identity among echoes of the same value.

    A created entity's identifier is echoed by nested back-references in the
    same response (Vikunja: ``$.id`` and ``$.views[i].project_id`` all carry the
    new project's id).  Among the given paths the own identity is the unique
    shallowest path whose terminal field is exactly ``id``; when no such path
    exists, or when it is not unique at that depth, ``None`` is returned and the
    caller keeps its ambiguity verdict.
    """

    candidates = [
        (path.count("."), path)
        for path in {str(path) for path in paths}
        if path.rsplit(".", 1)[-1].casefold() == "id"
    ]
    if not candidates:
        return None
    depth = min(depth for depth, _ in candidates)
    shallowest = [path for candidate_depth, path in candidates if candidate_depth == depth]
    return shallowest[0] if len(shallowest) == 1 else None


def _own_identity_source_key(
    keys: "Iterable[tuple[str, str, str]]",
) -> tuple[str, str, str] | None:
    """Collapse the source keys of one creator response to its own identity field."""

    keys = list(keys)
    producers = {key[0] for key in keys}
    scalar_types = {key[2] for key in keys}
    if len(keys) < 2 or len(producers) != 1 or len(scalar_types) != 1:
        return None
    own_path = _own_identity_response_path(key[1] for key in keys)
    if own_path is None:
        return None
    return next(key for key in keys if key[1] == own_path)


def _unique_indexed_member_creator(
    matches: Mapping[tuple[str, str, str, str], ResourceBindingSource],
) -> ResourceBindingSource | None:
    creator_refs = {key[0] for key in matches}
    if not matches:
        return None
    if len(creator_refs) != 1:
        raise CandidateLocalFailure(
            "M11b", "binding", "setup_indexed_member_creator_ambiguous"
        )
    rows = [row for key, row in matches.items() if key[0] in creator_refs]
    if len(rows) != 1:
        own_key = _own_identity_source_key(
            (key[0], key[1], key[2]) for key in matches
        )
        if own_key is None:
            raise CandidateLocalFailure(
                "M11b", "binding", "setup_indexed_member_creator_ambiguous"
            )
        rows = [
            row
            for key, row in matches.items()
            if (key[0], key[1], key[2]) == own_key
        ]
        if len(rows) != 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "setup_indexed_member_creator_ambiguous"
            )
    return rows[0]


def _request_template_scalar_hashes(request: Mapping[str, Any]) -> set[str]:
    """Return typed scalar hashes already present in one creator request."""

    values: list[Any] = []
    values.extend((request.get("query") or {}).values())
    values.extend(
        value for _path, value in _recorded_scalar_paths(request.get("body"))
    )
    values.extend(
        segment for segment in str(request.get("path") or "").split("/")
        if segment
    )
    return {
        scalar_sha256(value)
        for value in values
        if isinstance(value, (str, int, float, bool))
    }


def _strict_identity_field_pairs(
    predicate: Mapping[str, Any],
) -> frozenset[tuple[str, str]]:
    identity = predicate.get("identity")
    rows = identity.get("field_pairs") if isinstance(identity, Mapping) else None
    if (
        not isinstance(identity, Mapping)
        or identity.get("semantics") != "strict-tuple"
        or not isinstance(rows, Sequence)
        or isinstance(rows, (str, bytes))
    ):
        return frozenset()
    member = predicate.get("member")
    ref = member.get("ref") if isinstance(member, Mapping) else None
    member_root = str(ref.get("path") or "") if isinstance(ref, Mapping) else ""

    def absolute_member_path(relative: str) -> str:
        if member_root == "$":
            return relative
        if relative == "$":
            return member_root
        if member_root.startswith("$.") and relative.startswith("$."):
            return member_root + relative.removeprefix("$")
        return ""

    pairs = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        collection_path = str(row.get("collection_item_path") or "")
        member_path = str(row.get("member_path") or "")
        absolute_path = absolute_member_path(member_path)
        if collection_path.startswith("$.") and absolute_path.startswith("$."):
            pairs.add((collection_path, absolute_path))
    return frozenset(pairs)


def _route_s_candidate(
    bound: V2BoundCandidate,
    m11a_execution_binding: Mapping[str, Any],
    *,
    source_ref: str,
) -> dict[str, Any]:
    setup = [
        {"actor_id": str(row["actor_id"]), "request_ref": str(row["request_ref"])}
        for row in m11a_execution_binding["setup"]
    ]
    normalized = m11a_execution_binding["candidate"]
    return {
        "schema_version": str(normalized["schema_version"]),
        "candidate_id": bound.candidate_id,
        "candidate_identity": f"{bound.candidate_set_id}:{bound.candidate_id}",
        "normalized_candidate_sha256": bound.canonical_sha256(),
        "source_hashes": {source_ref: bound.canonical_sha256()},
        "producer": {
            "actor_id": str(m11a_execution_binding["producer"]["actor_id"]),
            "request_ref": bound.producer_request_ref,
        } if bound.producer_request_ref is not None else None,
        "consumer": {
            "actor_id": str(m11a_execution_binding["observer"]["actor_id"]),
            "request_ref": bound.observer_request_ref,
        },
        "setup": setup,
        "contract_kind": str(normalized["contract_kind"]),
        "observation_opportunity_ref": str(normalized["observation_opportunity_ref"]),
        "primary_predicate": copy.deepcopy(bound.runtime_predicate),
        "evidence_refs": copy.deepcopy(normalized["evidence_refs"]),
        "predicate_family": str(bound.runtime_predicate["family"]),
    }


def _bound_request(
    request_ref: str,
    *,
    requests: Mapping[str, Mapping[str, Any]],
    binding_plan: Mapping[str, Any],
) -> dict[str, Any]:
    observed = requests.get(request_ref)
    planned = binding_plan["request_bindings"].get(request_ref)
    if observed is None or not isinstance(planned, Mapping):
        raise CandidateLocalFailure("M11b", "binding", "request_binding_missing")
    value = copy.deepcopy(dict(planned))
    if (
        value.get("actor_id") != observed.get("actor_id")
        or str(value.get("method") or "").upper()
        != str(observed.get("method") or "").upper()
        or value.get("path") != observed.get("canonical_path")
    ):
        raise CandidateLocalFailure(
            "M11b", "contract", "request_binding_trace_drift"
        )
    if set(value) - {"actor_id", "method", "path", "body", "query", "headers"}:
        raise CandidateLocalFailure(
            "M11b", "contract", "request_binding_fields_unsupported"
        )
    value["method"] = str(value["method"]).upper()
    value.setdefault("body", None)
    value.setdefault("query", {})
    value.setdefault("headers", {})
    if not isinstance(value["query"], dict):
        raise CandidateLocalFailure(
            "M11b", "contract", "request_query_template_invalid"
        )
    if not isinstance(value["headers"], dict) or not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in value["headers"].items()
    ):
        raise CandidateLocalFailure(
            "M11b", "contract", "request_header_template_invalid"
        )
    return value


def _request_is_read_only(
    request_ref: str,
    *,
    bound_request: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Use the already recovered GraphQL operation kind behind POST."""

    observed = requests.get(request_ref)
    method = str(
        bound_request.get("method")
        or (
            observed.get("method")
            if isinstance(observed, Mapping)
            else ""
        )
    ).upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return True
    if method != "POST":
        return False
    return (
        isinstance(observed, Mapping)
        and (
            observed.get("graphql_operation_kind") == "query"
            or observed.get("mechanical_read_kind") == "recorded_post_query"
            or observed.get("declared_read_semantic") is True
        )
    )


def _validate_observer_catalog_selection(
    *,
    protocol_shape: Mapping[str, Any],
    bound: V2BoundCandidate,
    execution_binding: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
    observed_catalog_requests: Mapping[str, Mapping[str, Any]] | None,
    observed_catalog_operations: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    selection = protocol_shape.get("observer_catalog_selection")
    if selection is None:
        return
    if not isinstance(selection, Mapping) or protocol_shape.get(
        "shape_kind"
    ) != "causal_two_arm":
        raise ValueError("M11b observer catalog selection shape invalid")
    request_ref = str(selection.get("request_ref") or "")
    request = requests.get(request_ref)
    observed = (
        observed_catalog_requests.get(request_ref)
        if observed_catalog_requests is not None
        else None
    )
    observed_operation = (
        observed_catalog_operations.get(str(selection.get("operation_id") or ""))
        if observed_catalog_operations is not None
        else None
    )
    observer = execution_binding.get("observer") or {}
    session_run_id = (
        request.get("session_run_id")
        if isinstance(request, Mapping)
        else None
    ) or (
        (request.get("observation_ref") or {}).get("run_id")
        if isinstance(request, Mapping)
        else None
    )
    if (
        not isinstance(request, Mapping)
        or not isinstance(observed, Mapping)
        or not isinstance(observed_operation, Mapping)
        or (
            request_ref != bound.observer_request_ref
            or request_ref != observer.get("request_ref")
            or selection.get("source") != "observed_api_catalog"
            or selection.get("actor_id") != request.get("actor_id")
            or selection.get("actor_id") != observer.get("actor_id")
            or selection.get("session_run_id") != session_run_id
            or selection.get("operation_id") != request.get("operation_id")
            or selection.get("method") != str(request.get("method") or "").upper()
            or selection.get("canonical_path") != request.get("canonical_path")
            or any(
                observed.get(key) != selection.get(selection_key)
                for key, selection_key in (
                    ("actor_id", "actor_id"),
                    ("session_run_id", "session_run_id"),
                    ("operation_id", "operation_id"),
                    ("canonical_path", "canonical_path"),
                )
            )
            or str(observed.get("method") or "").upper()
            != selection.get("method")
            or selection.get("catalog_operation_sha256")
            != observed_operation.get("full_row_sha256")
            or selection.get("operation_id")
            != observed_operation.get("operation_id")
            or selection.get("method")
            != str(observed_operation.get("method") or "").upper()
            or selection.get("canonical_path")
            != observed_operation.get("canonical_path")
            or request_ref
            not in set(map(str, observed_operation.get("stage1_request_refs", ())))
            or not _request_is_read_only(
                request_ref,
                bound_request={"method": request.get("method")},
                requests=requests,
            )
        )
    ):
        raise ValueError("M11b observer catalog selection does not bind trace")
    response_shape = dict(observed.get("response_body_shape") or {})
    request_shape = observed.get("request_body_shape") or {}
    selector_sha = canonical_sha256({
        "query": observed.get("query") or {},
        "body_kind": request_shape.get("body_kind"),
        "body_sha256": request_shape.get("body_sha256"),
    })
    template_payload = {
        "actor_id": str(observed["actor_id"]),
        "session_run_id": str(observed["session_run_id"]),
        "operation_id": str(observed["operation_id"]),
        "method": str(observed["method"]).upper(),
        "canonical_path": str(observed["canonical_path"]),
        "selector_snapshot_sha256": selector_sha,
        "response_body_shape_sha256": canonical_sha256(response_shape),
    }
    if (
        selection.get("selector_snapshot_sha256") != selector_sha
        or selection.get("response_body_shape_sha256")
        != template_payload["response_body_shape_sha256"]
        or selection.get("template_sha256") != canonical_sha256(template_payload)
    ):
        raise ValueError("M11b observer catalog selection provenance drifted")


def _graphql_operation_binding(
    request_ref: str,
    *,
    requests: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    observed = requests.get(request_ref)
    kind = (
        observed.get("graphql_operation_kind")
        if isinstance(observed, Mapping)
        else None
    )
    return (
        {"graphql_operation_kind": str(kind)}
        if kind in {"query", "mutation", "unknown"}
        else {}
    )


def _transport_shape(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "method": request["method"],
        "path": request["path"],
        "body": copy.deepcopy(request.get("body")),
    }


def _recording_prerequisite_plan(
    recording_trace: Mapping[str, Any],
    *,
    request_bindings: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
) -> SetupBindingPlan:
    rows = recording_trace.get("api_requests")
    if not isinstance(rows, list):
        raise ValueError("M11b recording trace requires api_requests")
    records = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("M11b recording trace request is not an object")
        request_ref = str(row["id"])
        request = request_bindings.get(request_ref)
        observed = requests.get(request_ref)
        if not isinstance(request, Mapping) or not isinstance(observed, Mapping):
            raise ValueError("M11b recording request binding is missing")
        records.append(
            RecordedSetupRequest(
                request_ref=request_ref,
                actor_id=str(row["actor"]),
                order=int(row["started_at_ms"]),
                # Resource rebuilding needs the mechanical operation kind, not
                # the transport verb.  A GraphQL query carried by POST observes
                # state and therefore cannot become a fresh-resource creator.
                method=(
                    "GET"
                    if _request_is_read_only(
                        request_ref,
                        bound_request=request,
                        requests=requests,
                    )
                    else str(row["method"])
                ),
                request=_recorded_request_shape(request),
                response_status=int(row["response_status"]),
                response_body=copy.deepcopy(row.get("response_body")),
            )
        )
    return build_setup_binding_plan(records)


def _recorded_request_shape(request: Mapping[str, Any]) -> dict[str, Any]:
    body = request.get("body")
    return {
        "url": str(request["path"]),
        "queryString": [
            {"name": str(name), "value": copy.deepcopy(value)}
            for name, value in sorted((request.get("query") or {}).items())
        ],
        "headers": [
            {"name": str(name), "value": str(value)}
            for name, value in sorted((request.get("headers") or {}).items())
        ],
        "postData": (
            {
                "mimeType": "application/json",
                "text": json.dumps(
                    body,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
            if body is not None
            else None
        ),
    }


def _candidate_prerequisite_plan(
    *,
    producer_ref: str | None,
    observer_ref: str,
    request_order: Mapping[str, int],
    path_binding_targets: Mapping[str, Mapping[str, str]],
    additional_consumer_refs: set[str] | None = None,
    selected_setup_refs: set[str] | None = None,
    eligible_domain_refs: set[str] | None = None,
    profile_managed_refs: set[str] | None = None,
    deferred_observer_source_ref: str | None = None,
    recording_plan: SetupBindingPlan | None,
) -> SetupBindingPlan | None:
    """Close exact recorded setup dependencies inside the frozen prefix."""

    if recording_plan is None:
        return None
    domain_refs = set(eligible_domain_refs or ())
    if not domain_refs:
        return None
    sources = {source.source_id: source for source in recording_plan.sources}
    producer_order = request_order[producer_ref if producer_ref is not None else observer_ref]
    for use in recording_plan.uses:
        source = sources.get(use.source_id)
        if (
            source is not None
            and use.consumer_request_ref == observer_ref
            and use.location == "path"
            and _path_use_targets_variable(
                use, path_binding_targets=path_binding_targets
            )
            and request_order[source.creator_request_ref] >= producer_order
        ):
            if source.creator_request_ref == deferred_observer_source_ref:
                continue
            reason = (
                "observer_identity_available_only_after_treatment_producer"
                if source.creator_request_ref == producer_ref
                else "observer_identity_source_not_prior_to_treatment_producer"
            )
            raise CandidateLocalFailure("M11b", "binding", reason)
    profile_managed = set(profile_managed_refs or ())
    consumer_refs = {observer_ref, *(selected_setup_refs or set())}
    if producer_ref is not None:
        consumer_refs.add(producer_ref)
    consumer_refs.update(additional_consumer_refs or set())
    selected_source_ids: set[str] = set()
    selected_use_keys: set[tuple[str, str, str, str]] = set()
    changed = True
    while changed:
        changed = False
        for use in recording_plan.uses:
            source = sources.get(use.source_id)
            if (
                source is None
                or use.consumer_request_ref not in consumer_refs
                or source.creator_request_ref not in domain_refs
                or source.creator_request_ref in profile_managed
                or use.consumer_request_ref not in request_order
                or source.creator_request_ref not in request_order
                or request_order[source.creator_request_ref]
                >= request_order[use.consumer_request_ref]
                or (
                    use.location == "path"
                    and not _path_use_targets_variable(
                        use, path_binding_targets=path_binding_targets
                    )
                )
            ):
                continue
            key = (
                use.source_id,
                use.consumer_request_ref,
                use.location,
                use.target_path,
            )
            if key not in selected_use_keys:
                selected_use_keys.add(key)
                selected_source_ids.add(use.source_id)
                changed = True
            if source.creator_request_ref not in consumer_refs:
                consumer_refs.add(source.creator_request_ref)
                changed = True
    selected_uses = tuple(
        use
        for use in recording_plan.uses
        if (
            use.source_id,
            use.consumer_request_ref,
            use.location,
            use.target_path,
        )
        in selected_use_keys
    )
    if not selected_uses:
        return None
    selected_sources = sorted(
        (sources[source_id] for source_id in selected_source_ids),
        key=lambda source: request_order[source.creator_request_ref],
    )
    return SetupBindingPlan(
        setup_request_refs=tuple(
            source.creator_request_ref for source in selected_sources
        ),
        sources=tuple(selected_sources),
        uses=selected_uses,
        issues=(),
    )


def _resolve_deferred_workflow_binding(
    *,
    protocol_shape: Mapping[str, Any],
    producer_ref: str,
    observer_ref: str,
    producer_actor: str,
    observer_actor: str,
    recording_plan: SetupBindingPlan | None,
    path_binding_targets: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Resolve one recorded producer-response identity to one observer target."""

    declared = protocol_shape.get("deferred_fresh_binding")
    if not isinstance(declared, Mapping) or recording_plan is None:
        raise CandidateLocalFailure(
            "M11b", "binding", "deferred_fresh_identity_missing"
        )
    if (
        declared.get("source_request_ref") != producer_ref
        or declared.get("target_request_ref") != observer_ref
        or declared.get("target_actor") != observer_actor
    ):
        raise CandidateLocalFailure(
            "M11b", "binding", "deferred_fresh_identity_scope_mismatch"
        )
    location = str(declared.get("target_location") or "")
    target_field = str(declared.get("target_field") or "")
    if location not in {"path", "query", "body"} or not target_field:
        raise CandidateLocalFailure(
            "M11b", "binding", "deferred_fresh_target_invalid"
        )
    target_path = (
        str(path_binding_targets.get(observer_ref, {}).get(target_field, ""))
        if location == "path"
        else _typed_path(target_field, location=location)
    )
    if not target_path:
        raise CandidateLocalFailure(
            "M11b", "binding", "deferred_fresh_target_missing"
        )
    sources = {source.source_id: source for source in recording_plan.sources}
    matches: dict[tuple[str, str, str], tuple[Any, Any]] = {}
    for use in recording_plan.uses:
        source = sources.get(use.source_id)
        if (
            source is None
            or source.creator_request_ref != producer_ref
            or source.actor_id != producer_actor
            or use.consumer_request_ref != observer_ref
            or use.actor_id != observer_actor
            or use.location != location
            or use.target_path != target_path
            or use.scalar_type != source.scalar_type
        ):
            continue
        matches[(source.response_path, use.target_path, source.scalar_type)] = (
            source,
            use,
        )
    if not matches:
        raise CandidateLocalFailure(
            "M11b", "binding", "deferred_fresh_identity_missing"
        )
    if len(matches) != 1:
        raise CandidateLocalFailure(
            "M11b", "binding", "deferred_fresh_identity_ambiguous"
        )
    source, use = next(iter(matches.values()))
    return {
        "source": {
            "source_id": source.source_id,
            "actor_id": source.actor_id,
            "creator_request_ref": source.creator_request_ref,
            "response_path": source.response_path,
            "scalar_type": source.scalar_type,
            "capture_timing": "producer_response",
        },
        "use": {
            "source_id": use.source_id,
            "consumer_request_ref": use.consumer_request_ref,
            "location": use.location,
            "target_path": use.target_path,
            "actor_id": use.actor_id,
            "scalar_type": use.scalar_type,
        },
    }


def _resolve_postcondition_session_continuity(
    *,
    protocol_shape: Mapping[str, Any],
    producer_ref: str,
    observer_ref: str,
    producer_actor: str,
    observer_actor: str,
    requests: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet,
) -> dict[str, Any] | None:
    """Close one observed auth-token flow as arm-local session continuity.

    The fresh token remains in memory and is not a business identity source.
    Non-session witnesses require no runtime session update here.
    """

    declared = protocol_shape.get("postcondition_flow")
    if not isinstance(declared, Mapping):
        raise CandidateLocalFailure(
            "M11b", "contract", "postcondition_flow_missing"
        )
    witness_id = str(declared.get("witness_flow_id") or "")
    matches = [
        flow for flow in value_flows.flows if flow.flow_id == witness_id
    ]
    if len(matches) != 1:
        raise CandidateLocalFailure(
            "M11b", "binding", "postcondition_flow_witness_not_unique"
        )
    flow = matches[0]
    producer = requests.get(producer_ref)
    observer = requests.get(observer_ref)
    if (
        producer is None
        or observer is None
        or declared.get("producer_request_ref") != producer_ref
        or declared.get("after_request_ref") != observer_ref
        or flow.producer_request_ref != producer_ref
        or flow.consumer_request_ref != observer_ref
        or flow.producer_actor_id != producer_actor
        or flow.consumer_actor_id != observer_actor
        or producer_actor != observer_actor
        or flow.producer_operation_id != producer.get("operation_id")
        or flow.consumer_operation_id != observer.get("operation_id")
    ):
        raise CandidateLocalFailure(
            "M11b", "binding", "postcondition_flow_scope_mismatch"
        )
    target_location = _target_location(str(flow.to_location))
    if not _session_managed_binding_material(
        location=target_location,
        target_field=str(flow.to_field),
        source_field=str(flow.from_field),
    ):
        return None
    if (
        flow.from_location != "response_body"
        or target_location != "header"
        or re.sub(r"[^a-z0-9]", "", str(flow.to_field).casefold())
        != "authorization"
    ):
        raise CandidateLocalFailure(
            "M11b", "contract", "postcondition_session_flow_unsupported"
        )
    return {
        "kind": "api_token",
        "actor_id": producer_actor,
        "producer_request_ref": producer_ref,
        "after_request_ref": observer_ref,
        "response_path": str(flow.from_field),
        "target_header": "Authorization",
        "witness_flow_id": witness_id,
    }


def classify_recording_setup_signal(
    *,
    producer_ref: str,
    request_order: Mapping[str, int],
    requests: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet,
    path_binding_targets: Mapping[str, Mapping[str, str]],
    recording_plan: SetupBindingPlan,
    eligible_domain_refs: set[str],
) -> dict[str, Any]:
    """Classify one producer-only T10 signal without predicting live behavior."""

    sources = {source.source_id: source for source in recording_plan.sources}
    variable_targets = set(path_binding_targets.get(producer_ref, {}).values())
    closable_uses = [
        use
        for use in recording_plan.uses
        if use.consumer_request_ref == producer_ref
        and use.source_id in sources
        and sources[use.source_id].creator_request_ref in eligible_domain_refs
        and (use.location != "path" or use.target_path in variable_targets)
    ]
    covered_variable_targets = {
        use.target_path for use in closable_uses if use.location == "path"
    }
    if closable_uses and variable_targets <= covered_variable_targets:
        return {
            "request_ref": producer_ref,
            "failure_stage": "M11b",
            "failure_kind": "dependency_auto_closed",
            "reason_code": "recorded_dependency_closure_available",
            "creator_request_refs": sorted(
                {
                    sources[use.source_id].creator_request_ref
                    for use in closable_uses
                },
                key=request_order.__getitem__,
            ),
        }
    try:
        lookup_rows = _producer_lookup_setup_rows(
            producer_ref=producer_ref,
            request_order=request_order,
            requests=requests,
            value_flows=value_flows,
            path_binding_targets=path_binding_targets,
        )
    except CandidateLocalFailure as error:
        return {
            "request_ref": producer_ref,
            "failure_stage": "M11b",
            "failure_kind": "creator_identity_ambiguous",
            "reason_code": error.reason_code,
            "creator_request_refs": [],
        }
    if lookup_rows:
        return {
            "request_ref": producer_ref,
            "failure_stage": "M11b",
            "failure_kind": "dependency_auto_closed",
            "reason_code": "recorded_lookup_closure_available",
            "creator_request_refs": [row["request_ref"] for row in lookup_rows],
        }
    if variable_targets:
        return {
            "request_ref": producer_ref,
            "failure_stage": "M11b",
            "failure_kind": "setup_domain_missing",
            "reason_code": "variable_path_creator_absent_from_domain",
            "creator_request_refs": [],
        }
    return {
        "request_ref": producer_ref,
        "failure_stage": "M11b",
        "failure_kind": "binding_not_required",
        "reason_code": "no_evidence_supported_variable_target",
        "creator_request_refs": [],
    }


def _producer_lookup_setup_rows(
    *,
    producer_ref: str,
    request_order: Mapping[str, int],
    requests: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet,
    path_binding_targets: Mapping[str, Mapping[str, str]],
    profile_managed_refs: set[str] | None = None,
    authenticated_actor_identity_path: str | None = None,
) -> list[dict[str, str]]:
    """Add the nearest observed lookup that supplies a producer path identity."""

    producer = requests.get(producer_ref)
    if producer is None:
        raise CandidateLocalFailure(
            "M11b", "binding", "producer_request_missing_from_trace"
        )
    producer_actor = str(producer["actor_id"])
    producer_session = _request_session_id(producer)
    producer_order = request_order[producer_ref]
    flows_by_target: dict[str, list[Any]] = {}
    for flow in value_flows.flows:
        if (
            flow.consumer_request_ref != producer_ref
            or flow.consumer_actor_id != producer_actor
            or flow.from_location != "response_body"
            or flow.to_location != "path"
        ):
            continue
        lookup = requests.get(flow.producer_request_ref)
        if (
            lookup is None
            or str(lookup["actor_id"]) != producer_actor
            or (
                producer_session is not None
                and _request_session_id(lookup) != producer_session
            )
            or str(lookup["method"]).upper() not in {"GET", "HEAD"}
            or request_order[flow.producer_request_ref] >= producer_order
        ):
            continue
        target_path = str(
            path_binding_targets.get(producer_ref, {}).get(flow.to_field, "")
        )
        if not target_path:
            continue
        if not _path_target_is_variable(
            producer_ref,
            target_path,
            path_binding_targets=path_binding_targets,
        ):
            continue
        flows_by_target.setdefault(target_path, []).append(flow)

    lookup_refs: set[str] = set()
    managed_refs = profile_managed_refs or set()
    for target_path, rows in flows_by_target.items():
        exact_actor_identity_rows = [
            row
            for row in rows
            if authenticated_actor_identity_path is not None
            and (
                str(row.from_field) == authenticated_actor_identity_path
                or (
                    str(row.from_field).startswith(
                        authenticated_actor_identity_path + "."
                    )
                    and _identity_field_name(
                        str(row.from_field).rsplit(".", 1)[-1]
                    )
                )
            )
        ]
        if exact_actor_identity_rows:
            identity_sources = {
                (
                    str(requests[row.producer_request_ref]["operation_id"]),
                    str(row.from_field),
                )
                for row in exact_actor_identity_rows
            }
            if len(identity_sources) != 1:
                raise CandidateLocalFailure(
                    "M11b", "binding", "producer_lookup_source_ambiguous"
                )
            operation_id, source_path = next(iter(identity_sources))
            equivalent = [
                row
                for row in exact_actor_identity_rows
                if (
                    str(requests[row.producer_request_ref]["operation_id"]),
                    str(row.from_field),
                ) == (operation_id, source_path)
            ]
            lookup_refs.add(max(
                (row.producer_request_ref for row in equivalent),
                key=request_order.__getitem__,
            ))
            continue
        authenticated_paths = {
            str(flow.from_field)
            for flow in value_flows.flows
            if (
                flow.consumer_request_ref == producer_ref
                and flow.producer_request_ref in managed_refs
                and flow.consumer_actor_id == producer_actor
                and flow.producer_actor_id == producer_actor
                and flow.from_location == "response_body"
                and flow.to_location == "path"
                and str(
                    path_binding_targets.get(producer_ref, {}).get(
                        flow.to_field, ""
                    )
                ) == target_path
                and (
                    producer_session is None
                    or flow.producer_session_run_id == producer_session
                )
            )
        }
        if authenticated_paths:
            actor_identity_rows = [
                row for row in rows
                if str(row.from_field) in authenticated_paths
            ]
            identity_sources = {
                (
                    str(requests[row.producer_request_ref]["operation_id"]),
                    str(row.from_field),
                )
                for row in actor_identity_rows
            }
            if len(identity_sources) != 1:
                raise CandidateLocalFailure(
                    "M11b", "binding", "producer_lookup_source_ambiguous"
                )
            operation_id, source_path = next(iter(identity_sources))
            equivalent = [
                row for row in actor_identity_rows
                if (
                    str(requests[row.producer_request_ref]["operation_id"]),
                    str(row.from_field),
                ) == (operation_id, source_path)
            ]
            lookup_refs.add(max(
                (row.producer_request_ref for row in equivalent),
                key=request_order.__getitem__,
            ))
            continue
        latest_order = max(request_order[row.producer_request_ref] for row in rows)
        latest = [
            row
            for row in rows
            if request_order[row.producer_request_ref] == latest_order
        ]
        minimum_depth = min(_observed_path_depth(row.from_field) for row in latest)
        latest = [
            row
            for row in latest
            if _observed_path_depth(row.from_field) == minimum_depth
        ]
        source_keys = {
            (row.producer_request_ref, row.from_field) for row in latest
        }
        if len(source_keys) != 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "producer_lookup_source_ambiguous"
            )
        lookup_refs.add(next(iter(source_keys))[0])

    return [
        {
            "actor_id": str(requests[request_ref]["actor_id"]),
            "request_ref": request_ref,
        }
        for request_ref in sorted(lookup_refs, key=request_order.__getitem__)
    ]


def _request_session_id(request: Mapping[str, Any]) -> str | None:
    session = request.get("session_run_id")
    if isinstance(session, str) and session:
        return session
    observation = request.get("observation_ref")
    if isinstance(observation, Mapping):
        run_id = observation.get("run_id")
        if isinstance(run_id, str) and run_id:
            return run_id
    return None


def _fresh_identity_equivalence_witnesses(
    rows: Sequence[tuple[Any, str, str, str]],
    *,
    actor_id: str,
    consumer_ref: str,
    target_value: Any,
    requests: Mapping[str, Mapping[str, Any]],
    setup_refs: Mapping[str, str],
    recording_trace: Mapping[str, Any] | None,
) -> tuple[str, ...] | None:
    """Admit provisional same-identity sources for exact fresh verification."""

    consumer = requests.get(consumer_ref)
    consumer_session = (
        _request_session_id(consumer) if isinstance(consumer, Mapping) else None
    )
    recorded = _recorded_request_facts(recording_trace)
    unique: dict[tuple[str, str, str], tuple[Any, str, str, str]] = {
        (
            str(row[0].producer_request_ref),
            str(row[0].from_field),
            str(row[3]),
        ): row
        for row in rows
    }
    if len(unique) < 2 or consumer_session is None:
        return None
    paths = {key[1] for key in unique}
    scalar_types = {key[2] for key in unique}
    if (
        len(paths) != 1
        or len(scalar_types) != 1
        or not _identity_field_name(next(iter(paths)).rsplit(".", 1)[-1])
    ):
        return None
    witnesses: list[str] = []
    for (request_ref, response_path, scalar_type), row in unique.items():
        request = requests.get(request_ref)
        record = recorded.get(request_ref)
        value = (
            extract_typed_value(record.get("response_body"), response_path)
            if isinstance(record, Mapping)
            else None
        )
        if (
            request_ref not in setup_refs
            or setup_refs.get(request_ref) != actor_id
            or not isinstance(request, Mapping)
            or str(row[0].producer_actor_id) != actor_id
            or _request_session_id(request) != consumer_session
            or _request_is_read_only(
                request_ref,
                bound_request=request,
                requests=requests,
            )
            or not isinstance(record, Mapping)
            or type(value) is not type(target_value)
            or value != target_value
            or _json_scalar_type(value) != scalar_type
        ):
            return None
        witnesses.append(request_ref)
    return tuple(sorted(witnesses))


def _recorded_request_facts(
    recording_trace: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(recording_trace, Mapping):
        return {}
    rows = recording_trace.get("api_requests")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }


def _authenticated_profile_scalar_witnesses(
    *,
    requests: Mapping[str, Mapping[str, Any]],
    recording_trace: Mapping[str, Any] | None,
    authenticated_actor_identity_paths: Mapping[str, str],
) -> dict[tuple[str, str], tuple[Any, tuple[str, ...]]]:
    """Return stable recorded profile scalars and equivalent probe requests.

    The profile contributes only its declared authenticated response root.  A
    field is usable when every read-only observation for one actor/session has
    the same typed value.  Repeated equivalent probes are collapsed; a changed
    value or multiple sessions remain unavailable rather than being ordered.
    """

    recorded = _recorded_request_facts(recording_trace)
    by_field: dict[tuple[str, str], list[tuple[Any, str, str | None]]] = {}
    for request_ref, row in recorded.items():
        request = requests.get(request_ref)
        actor_id = str(row.get("actor") or "")
        probe_path = authenticated_actor_identity_paths.get(actor_id)
        if (
            not probe_path
            or not isinstance(request, Mapping)
            or not _request_is_read_only(
                request_ref,
                bound_request=request,
                requests=requests,
            )
        ):
            continue
        root = extract_typed_value(row.get("response_body"), probe_path)
        if not isinstance(root, Mapping):
            continue
        for path, value in _recorded_scalar_paths(root, path=probe_path):
            if isinstance(value, (str, int, float, bool)) and value is not None:
                by_field.setdefault((actor_id, path), []).append(
                    (value, request_ref, _request_session_id(request))
                )

    result: dict[tuple[str, str], tuple[Any, tuple[str, ...]]] = {}
    for key, rows in by_field.items():
        values = {(type(value), _binding_scalar_key(value)) for value, _, _ in rows}
        sessions = {session for _, _, session in rows}
        if len(values) != 1 or len(sessions) != 1 or None in sessions:
            continue
        result[key] = (
            copy.deepcopy(rows[0][0]),
            tuple(sorted({request_ref for _, request_ref, _ in rows})),
        )
    return result


def _authenticated_identity_flow_source(
    rows: list[tuple[Any, str, str, str]],
    *,
    actor_id: str,
    consumer_ref: str,
    target_value: Any,
    requests: Mapping[str, Mapping[str, Any]],
    binding_plan: Mapping[str, Any],
    recording_trace: Mapping[str, Any] | None,
    authenticated_actor_identity_paths: Mapping[str, str],
) -> tuple[Any, str, str, str] | None:
    """Collapse identity passthrough observations to one fresh write source."""

    consumer = requests.get(consumer_ref)
    consumer_session = (
        _request_session_id(consumer) if isinstance(consumer, Mapping) else None
    )
    if consumer_session is None:
        return None
    witnesses = _authenticated_profile_scalar_witnesses(
        requests=requests,
        recording_trace=recording_trace,
        authenticated_actor_identity_paths=authenticated_actor_identity_paths,
    )
    matching_profile_paths = {
        path
        for (profile_actor, path), (value, _request_refs) in witnesses.items()
        if profile_actor == actor_id
        and _identity_field_name(path.rsplit(".", 1)[-1])
        and type(value) is type(target_value)
        and value == target_value
    }
    if len(matching_profile_paths) != 1:
        return None

    recorded = _recorded_request_facts(recording_trace)
    proven_rows = []
    for row in rows:
        flow = row[0]
        source_ref = str(flow.producer_request_ref)
        source_request = requests.get(source_ref)
        source_record = recorded.get(source_ref)
        if (
            not isinstance(source_request, Mapping)
            or not isinstance(source_record, Mapping)
            or str(flow.producer_actor_id) != actor_id
            or _request_session_id(source_request) != consumer_session
            or not _identity_field_name(
                str(flow.from_field).rsplit(".", 1)[-1]
            )
        ):
            continue
        value = extract_typed_value(
            source_record.get("response_body"), str(flow.from_field)
        )
        if (
            typed_value_is_missing(value)
            or type(value) is not type(target_value)
            or value != target_value
        ):
            continue
        proven_rows.append(row)
    if len(proven_rows) != len(rows):
        return None
    source_keys = {
        (
            str(row[0].producer_request_ref),
            str(row[0].from_field),
            row[3],
        )
        for row in proven_rows
    }
    state_changing = {
        key
        for key in source_keys
        if not _request_is_read_only(
            key[0],
            bound_request=binding_plan["request_bindings"].get(key[0], {}),
            requests=requests,
        )
    }
    if len(state_changing) > 1:
        raise CandidateLocalFailure(
            "M11b", "binding", "observed_fresh_source_ambiguous"
        )
    if len(state_changing) == 1:
        chosen = next(iter(state_changing))
    elif len(source_keys) == 1:
        chosen = next(iter(source_keys))
    else:
        return None
    return next(
        row
        for row in proven_rows
        if (
            str(row[0].producer_request_ref),
            str(row[0].from_field),
            row[3],
        ) == chosen
    )


def _resource_binding_plan(
    *,
    candidate_id: str,
    arm: str,
    candidate: Mapping[str, Any],
    binding_plan: Mapping[str, Any],
    value_flows: ObservedValueFlowSet,
    trace: UiApiTrace,
    prerequisite_plan: SetupBindingPlan | None = None,
    recording_plan: SetupBindingPlan | None = None,
    setup_closure_provenance: Mapping[Any, Any] | None = None,
    closure_only_request_refs: frozenset[str] = frozenset(),
    capture_producer_identity_in_control: bool = False,
    workflow_before: Mapping[str, str] | None = None,
    deferred_workflow_binding: Mapping[str, Any] | None = None,
    recording_trace: Mapping[str, Any] | None = None,
    authenticated_actor_identity_paths: Mapping[str, str] | None = None,
    runtime_source_refs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    setup_refs = {
        str(item["request_ref"]): str(item["actor_id"])
        for item in candidate["setup"]
    }
    runtime_sources = dict(runtime_source_refs or {})
    source_actors = {**setup_refs, **runtime_sources}
    consumers = {
        **setup_refs,
        str(candidate["consumer"]["request_ref"]): str(candidate["consumer"]["actor_id"]),
    }
    if workflow_before is not None:
        consumers[str(workflow_before["request_ref"])] = str(
            workflow_before["actor_id"]
        )
    producer_ref = str(candidate["producer"]["request_ref"]) if candidate["producer"] is not None else None
    if producer_ref is not None and (arm != "control" or capture_producer_identity_in_control):
        consumers[producer_ref] = str(candidate["producer"]["actor_id"])
    policy = binding_plan["fresh_materialization_policy"]
    allowed_locations = set(policy["allowed_target_locations"])
    allowed_types = set(policy["allowed_scalar_types"])
    request_order = {
        str(row["request_ref"]): index
        for index, row in enumerate(trace.trace["api_requests"])
    }
    requests = {
        str(row["request_ref"]): row for row in trace.trace["api_requests"]
    }
    sources_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    uses: list[dict[str, Any]] = []
    flows_by_target: dict[
        tuple[str, str, str, str],
        list[tuple[Any, str, str, str]],
    ] = {}
    cited_flow_ids = {
        str(ref)
        for ref in candidate.get("evidence_refs", [])
        if isinstance(ref, str) and ref.startswith("vf-")
    }
    cited_sources_by_consumer_value: dict[
        tuple[str, str, str], set[tuple[str, str, str]]
    ] = {}
    closure_provenance = setup_closure_provenance or {}
    for flow in value_flows.flows:
        creator_ref = flow.producer_request_ref
        consumer_ref = flow.consumer_request_ref
        if creator_ref not in source_actors or consumer_ref not in consumers:
            continue
        if flow.producer_actor_id != source_actors[creator_ref]:
            raise CandidateLocalFailure(
                "M11b", "binding", "fresh_source_actor_drift"
            )
        if flow.consumer_actor_id != consumers[consumer_ref]:
            raise CandidateLocalFailure(
                "M11b", "binding", "fresh_consumer_actor_drift"
            )
        if request_order[creator_ref] >= request_order[consumer_ref]:
            continue
        target = _fresh_flow_target(flow, binding_plan=binding_plan, strict=True)
        if target is None:
            continue
        location, target_path, scalar_type = target
        request_template = binding_plan["request_bindings"][consumer_ref]
        closure = closure_provenance.get(_flow_provenance_key(flow))
        if creator_ref in closure_only_request_refs and closure is None:
            continue
        target_key = (consumer_ref, consumers[consumer_ref], location, target_path)
        flows_by_target.setdefault(target_key, []).append(
            (flow, location, target_path, scalar_type)
        )
        if flow.flow_id in cited_flow_ids:
            cited_sources_by_consumer_value.setdefault(
                (
                    consumer_ref,
                    scalar_type,
                    _binding_scalar_key(
                        _binding_template_value(
                            request_template, location, target_path
                        )
                    ),
                ),
                set(),
            ).add((creator_ref, flow.from_field, scalar_type))

    path_anchored_lookup_sources = {
        (flow.producer_request_ref, flow.from_field, scalar_type)
        for rows in flows_by_target.values()
        for flow, location, _target_path, scalar_type in rows
        if _request_is_read_only(
            flow.producer_request_ref,
            bound_request=binding_plan["request_bindings"].get(
                flow.producer_request_ref, {}
            ),
            requests=requests,
        )
        and location == "path"
    }
    selected_rows: list[tuple[Any, str, str, str]] = []
    evidence_selected_source_keys: set[tuple[str, str, str]] = set()
    identity_equivalence_by_source_key: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for target_key, rows in sorted(flows_by_target.items()):
        consumer_ref, actor_id, location, target_path = target_key
        request_template = binding_plan["request_bindings"][consumer_ref]
        actor_probe_path = (authenticated_actor_identity_paths or {}).get(
            actor_id
        )
        consumer_session = _request_session_id(requests[consumer_ref])
        profile_identity_rows = [
            row
            for row in rows
            if actor_probe_path is not None
            and consumer_session is not None
            and str(row[0].producer_actor_id) == actor_id
            and _request_session_id(requests[row[0].producer_request_ref])
            == consumer_session
            and (
                str(row[0].from_field) == actor_probe_path
                or (
                    str(row[0].from_field).startswith(actor_probe_path + ".")
                    and _identity_field_name(
                        str(row[0].from_field).rsplit(".", 1)[-1]
                    )
                )
            )
        ]
        if profile_identity_rows:
            identity_sources = {
                (
                    str(requests[row[0].producer_request_ref]["operation_id"]),
                    str(row[0].from_field),
                    row[3],
                )
                for row in profile_identity_rows
            }
            if len(identity_sources) != 1:
                raise CandidateLocalFailure(
                    "M11b", "binding", "observed_fresh_source_ambiguous"
                )
            operation_id, source_path, scalar_type = next(
                iter(identity_sources)
            )
            equivalent = [
                row
                for row in profile_identity_rows
                if (
                    str(requests[row[0].producer_request_ref]["operation_id"]),
                    str(row[0].from_field),
                    row[3],
                ) == (operation_id, source_path, scalar_type)
            ]
            selected_rows.append(max(
                equivalent,
                key=lambda row: request_order[row[0].producer_request_ref],
            ))
            continue
        authenticated_identity_row = _authenticated_identity_flow_source(
            rows,
            actor_id=actor_id,
            consumer_ref=consumer_ref,
            target_value=_binding_template_value(
                request_template, location, target_path
            ),
            requests=requests,
            binding_plan=binding_plan,
            recording_trace=recording_trace,
            authenticated_actor_identity_paths=(
                authenticated_actor_identity_paths or {}
            ),
        )
        if authenticated_identity_row is not None:
            selected_rows.append(authenticated_identity_row)
            continue
        ungrounded_graphql_creator_rows = [
            row
            for row in rows
            if not _request_is_read_only(
                row[0].producer_request_ref,
                bound_request=binding_plan["request_bindings"].get(
                    row[0].producer_request_ref, {}
                ),
                requests=requests,
            )
            and not _graphql_creator_flow_matches_target(
                row[0], target_path=target_path, requests=requests
            )
            and row[0].flow_id not in cited_flow_ids
        ]
        state_changing_source_keys = {
            (row[0].producer_request_ref, row[0].from_field, row[3])
            for row in rows
            if not _request_is_read_only(
                row[0].producer_request_ref,
                bound_request=binding_plan["request_bindings"].get(
                    row[0].producer_request_ref, {}
                ),
                requests=requests,
            )
            and (
                _graphql_creator_flow_matches_target(
                    row[0], target_path=target_path, requests=requests
                )
                or row[0].flow_id in cited_flow_ids
            )
        }
        if len(state_changing_source_keys) > 1:
            own_identity_key = _own_identity_source_key(
                (str(key[0]), str(key[1]), key[2])
                for key in state_changing_source_keys
            )
            if own_identity_key is not None:
                state_changing_source_keys = {
                    key
                    for key in state_changing_source_keys
                    if (str(key[0]), str(key[1]), key[2]) == own_identity_key
                }
        if len(state_changing_source_keys) > 1:
            witnesses = _fresh_identity_equivalence_witnesses(
                rows,
                actor_id=actor_id,
                consumer_ref=consumer_ref,
                target_value=_binding_template_value(
                    request_template, location, target_path
                ),
                requests=requests,
                setup_refs=setup_refs,
                recording_trace=recording_trace,
            )
            if witnesses is None:
                raise CandidateLocalFailure(
                    "M11b", "binding", "observed_fresh_source_ambiguous"
                )
            selected = max(
                rows,
                key=lambda row: request_order[row[0].producer_request_ref],
            )
            selected_key = (
                str(selected[0].producer_request_ref),
                str(selected[0].from_field),
                selected[3],
            )
            identity_equivalence_by_source_key[selected_key] = witnesses
            selected_rows.append(selected)
            continue
        if len(state_changing_source_keys) == 1:
            source_key = next(iter(state_changing_source_keys))
            selected_rows.append(
                next(
                    row
                    for row in rows
                    if (row[0].producer_request_ref, row[0].from_field, row[3])
                    == source_key
                )
            )
            continue
        cited = [row for row in rows if row[0].flow_id in cited_flow_ids]
        if not cited:
            exemplar = rows[0]
            anchored_keys = cited_sources_by_consumer_value.get(
                (
                    consumer_ref,
                    exemplar[3],
                    _binding_scalar_key(
                        _binding_template_value(
                            request_template, location, target_path
                        )
                    ),
                ),
                set(),
            )
            if len(anchored_keys) == 1:
                cited = [
                    row
                    for row in rows
                    if (
                        row[0].producer_request_ref,
                        row[0].from_field,
                        row[3],
                    ) in anchored_keys
                ]
        if cited:
            source_keys = {
                (row[0].producer_request_ref, row[0].from_field, row[3])
                for row in cited
            }
            if len(source_keys) != 1:
                raise CandidateLocalFailure(
                    "M11b", "binding", "observed_fresh_source_ambiguous"
                )
            evidence_selected_source_keys.update(source_keys)
            selected_rows.append(cited[0])
            continue
        if ungrounded_graphql_creator_rows and len(
            {
                (row[0].producer_request_ref, row[0].from_field, row[3])
                for row in rows
            }
        ) > 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "observed_fresh_source_ambiguous"
            )
        latest_order = max(request_order[row[0].producer_request_ref] for row in rows)
        latest = [
            row
            for row in rows
            if request_order[row[0].producer_request_ref] == latest_order
        ]
        if _request_is_read_only(
            latest[0][0].producer_request_ref,
            bound_request=binding_plan["request_bindings"].get(
                latest[0][0].producer_request_ref, {}
            ),
            requests=requests,
        ):
            latest = [
                row
                for row in latest
                if (row[0].producer_request_ref, row[0].from_field, row[3])
                in path_anchored_lookup_sources
            ]
            if not latest:
                continue
            minimum_depth = min(_observed_path_depth(row[0].from_field) for row in latest)
            latest = [
                row
                for row in latest
                if _observed_path_depth(row[0].from_field) == minimum_depth
            ]
        source_keys = {
            (
                row[0].producer_request_ref,
                row[0].from_field,
                row[3],
            )
            for row in latest
        }
        if len(source_keys) != 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "observed_fresh_source_ambiguous"
            )
        selected_rows.append(latest[0])

    for flow, location, target_path, scalar_type in selected_rows:
        creator_ref = flow.producer_request_ref
        consumer_ref = flow.consumer_request_ref
        source_key = (creator_ref, flow.from_field, scalar_type)
        if (
            _request_is_read_only(
                creator_ref,
                bound_request=binding_plan["request_bindings"].get(creator_ref, {}),
                requests=requests,
            )
            and source_key not in path_anchored_lookup_sources
            and not (
                creator_ref in runtime_sources
                and source_key in evidence_selected_source_keys
            )
        ):
            continue
        closure = closure_provenance.get(_flow_provenance_key(flow))
        indexed_creator = closure[3] if closure is not None else None
        if (
            closure is not None
            and indexed_creator is None
        ):
            target_hash = scalar_sha256(_binding_template_value(binding_plan["request_bindings"][consumer_ref], location, target_path))
            upstream = {
                value[3].source_id: value[3]
                for key, value in closure_provenance.items()
                if key[0] == creator_ref
                and value[3] is not None
                and value[3].creator_request_ref not in closure_only_request_refs
                and value[3].recorded_value_sha256 == target_hash
            }
            indexed_creator = next(iter(upstream.values())) if len(upstream) == 1 else None
        if indexed_creator is not None:
            replacement_key = (
                indexed_creator.creator_request_ref,
                indexed_creator.response_path,
                indexed_creator.scalar_type,
            )
            if source_key in evidence_selected_source_keys:
                evidence_selected_source_keys.add(replacement_key)
            source_key = replacement_key
        source = sources_by_key.get(source_key)
        if source is None:
            source_id = (
                indexed_creator.source_id
                if indexed_creator is not None
                else canonical_sha256(
                    {
                        "creator_request_ref": creator_ref,
                        "response_path": flow.from_field,
                        "scalar_type": scalar_type,
                        "observed_value_flow_set_sha256": value_flows.canonical_sha256(),
                    }
                )
            )
            source = {
                "source_id": source_id,
                "actor_id": (
                    indexed_creator.actor_id
                    if indexed_creator is not None
                    else source_actors[creator_ref]
                ),
                "creator_request_ref": (
                    indexed_creator.creator_request_ref
                    if indexed_creator is not None
                    else creator_ref
                ),
                "response_path": (
                    indexed_creator.response_path
                    if indexed_creator is not None
                    else flow.from_field
                ),
                "scalar_type": scalar_type,
                "recorded_value_sha256": (
                    indexed_creator.recorded_value_sha256
                    if indexed_creator is not None
                    else scalar_sha256(
                        _binding_template_value(
                            binding_plan["request_bindings"][consumer_ref],
                            location,
                            target_path,
                        )
                    )
                ),
                **(
                    {"transport_encoding": "url_path_segment_string"}
                    if _recorded_numeric_path_transport(
                        recording_trace=recording_trace,
                        creator_request_ref=creator_ref,
                        response_path=str(flow.from_field),
                        target_location=location,
                        target_scalar_type=scalar_type,
                    )
                    else {}
                ),
                **(
                    {
                        "identity_equivalence_request_refs": copy.deepcopy(
                            list(identity_equivalence_by_source_key[source_key])
                        )
                    }
                    if source_key in identity_equivalence_by_source_key
                    else {}
                ),
            }
            sources_by_key[source_key] = source
        uses.append(
            {
                "source_id": source["source_id"],
                "consumer_request_ref": consumer_ref,
                "location": location,
                "target_path": target_path,
                "actor_id": consumers[consumer_ref],
                "scalar_type": scalar_type,
            }
        )
    identity_sources, identity_uses = _authenticated_actor_identity_bindings(
        candidate=candidate,
        setup_refs=setup_refs,
        consumers=consumers,
        binding_plan=binding_plan,
        value_flows=value_flows,
        cited_flow_ids=cited_flow_ids,
        recording_trace=recording_trace,
        request_facts=requests,
        authenticated_actor_identity_paths=(
            authenticated_actor_identity_paths or {}
        ),
        paired_before=workflow_before,
        allowed_locations=allowed_locations,
        allowed_types=allowed_types,
        existing_uses=uses,
    )
    for source_key, source in identity_sources:
        previous = sources_by_key.get(source_key)
        if previous is not None and previous != source:
            raise CandidateLocalFailure(
                "M11b", "binding", "authenticated_actor_identity_source_conflict"
            )
        sources_by_key[source_key] = source
        evidence_selected_source_keys.add(source_key)
    uses.extend(identity_uses)
    profile_sources, profile_uses = _redacted_authenticated_identity_bindings(
        consumers=consumers,
        binding_plan=binding_plan,
        requests=requests,
        recording_trace=recording_trace,
        authenticated_actor_identity_paths=(
            authenticated_actor_identity_paths or {}
        ),
        allowed_locations=allowed_locations,
        allowed_types=allowed_types,
        existing_uses=uses,
    )
    for source_key, source in profile_sources:
        previous = sources_by_key.get(source_key)
        if previous is not None and previous != source:
            raise CandidateLocalFailure(
                "M11b", "binding", "authenticated_actor_identity_source_conflict"
            )
        sources_by_key[source_key] = source
        evidence_selected_source_keys.add(source_key)
    uses.extend(profile_uses)
    if prerequisite_plan is not None:
        admitted_consumers = {
            str(candidate["consumer"]["request_ref"]),
            *(str(ref) for ref in setup_refs),
        }
        if workflow_before is not None:
            admitted_consumers.add(str(workflow_before["request_ref"]))
        if arm in {
            "treatment", "workflow", "actor_matrix", "metamorphic_query",
            "negative_no_effect", "repeat_once", "repeat_twice",
        }:
            admitted_consumers.add(str(candidate["producer"]["request_ref"]))
        prerequisite_uses = [
            row
            for row in prerequisite_plan.uses
            if row.consumer_request_ref in admitted_consumers
            and (
                row.location != "path"
                or _path_use_targets_variable(
                    row,
                    path_binding_targets=(
                        binding_plan.get("path_binding_targets") or {}
                    ),
                )
            )
        ]
        if any(
            row.actor_id != consumers.get(row.consumer_request_ref)
            for row in prerequisite_uses
        ):
            raise CandidateLocalFailure(
                "M11b", "binding", "prerequisite_consumer_actor_drift"
            )
        prerequisite_source_ids = {row.source_id for row in prerequisite_uses}
        prerequisite_source_id_map: dict[str, str] = {}
        for row in prerequisite_plan.sources:
            if row.source_id not in prerequisite_source_ids:
                continue
            if setup_refs.get(row.creator_request_ref) != row.actor_id:
                raise CandidateLocalFailure(
                    "M11b", "binding", "prerequisite_source_actor_drift"
                )
            value = {
                "source_id": row.source_id,
                "actor_id": row.actor_id,
                "creator_request_ref": row.creator_request_ref,
                "response_path": row.response_path,
                "scalar_type": row.scalar_type,
                "recorded_value_sha256": row.recorded_value_sha256,
            }
            previous = sources_by_key.get(
                (row.creator_request_ref, row.response_path, row.scalar_type)
            )
            if previous is not None:
                if any(
                    previous[key] != value[key]
                    for key in (
                        "actor_id",
                        "creator_request_ref",
                        "response_path",
                        "scalar_type",
                    )
                ):
                    raise CandidateLocalFailure(
                        "M11b",
                        "binding",
                        "prerequisite_source_observed_flow_conflict",
                    )
                effective_source_id = str(previous["source_id"])
            else:
                sources_by_key[
                    (row.creator_request_ref, row.response_path, row.scalar_type)
                ] = value
                effective_source_id = row.source_id
            prerequisite_source_id_map[row.source_id] = effective_source_id
        uses.extend(
            {
                "source_id": prerequisite_source_id_map[row.source_id],
                "consumer_request_ref": row.consumer_request_ref,
                "location": row.location,
                "target_path": row.target_path,
                "actor_id": row.actor_id,
                "scalar_type": row.scalar_type,
            }
            for row in prerequisite_uses
        )

    uses = list(
        {
            (
                str(row["source_id"]),
                str(row["consumer_request_ref"]),
                str(row["location"]),
                str(row["target_path"]),
                str(row["actor_id"]),
                str(row["scalar_type"]),
            ): row
            for row in uses
        }.values()
    )
    if closure_only_request_refs:
        source_by_id = {
            str(source["source_id"]): source for source in sources_by_key.values()
        }
        allowed_closure_uses = {
            (source_ref, key[0], value[0], value[1])
            for key, value in closure_provenance.items()
            for source_ref in (
                key[1], getattr(value[3], "creator_request_ref", None)
            )
            if source_ref is not None
        }
        uses = [
            row
            for row in uses
            if (
                str(source_by_id[str(row["source_id"])]["creator_request_ref"])
                not in closure_only_request_refs
                or (
                    str(source_by_id[str(row["source_id"])]["creator_request_ref"]),
                    str(row["consumer_request_ref"]),
                    str(row["location"]),
                    str(row["target_path"]),
                ) in allowed_closure_uses
            )
        ]
    evidence_selected_source_ids = {
        str(source["source_id"])
        for key, source in sources_by_key.items()
        if key in evidence_selected_source_keys
    }
    uses = _resolve_binding_target_sources(
        uses,
        sources=tuple(sources_by_key.values()),
        requests=requests,
        evidence_selected_source_ids=evidence_selected_source_ids,
    )
    uses.sort(
        key=lambda row: (
            str(row["consumer_request_ref"]),
            str(row["location"]),
            str(row["target_path"]),
            str(row["source_id"]),
        )
    )
    recorded_hashes_by_source: dict[str, set[str]] = {}
    for use in uses:
        recorded_hashes_by_source.setdefault(str(use["source_id"]), set()).add(
            scalar_sha256(
                _binding_template_value(
                    binding_plan["request_bindings"][
                        str(use["consumer_request_ref"])
                    ],
                    str(use["location"]),
                    str(use["target_path"]),
                )
            )
        )
    if any(len(values) != 1 for values in recorded_hashes_by_source.values()):
        raise CandidateLocalFailure(
            "M11b", "binding", "fresh_source_recorded_value_ambiguous"
        )
    for source in sources_by_key.values():
        values = recorded_hashes_by_source.get(str(source["source_id"]))
        if values:
            source["recorded_value_sha256"] = next(iter(values))
    used_source_ids = {str(row["source_id"]) for row in uses}
    sources = sorted(
        (
            row
            for row in sources_by_key.values()
            if str(row["source_id"]) in used_source_ids
        ),
        key=lambda row: str(row["source_id"]),
    )
    if deferred_workflow_binding is not None:
        deferred_source = copy.deepcopy(
            dict(deferred_workflow_binding["source"])
        )
        deferred_use = copy.deepcopy(dict(deferred_workflow_binding["use"]))
        source_id = str(deferred_source["source_id"])
        if any(str(row["source_id"]) == source_id for row in sources):
            raise CandidateLocalFailure(
                "M11b", "binding", "deferred_fresh_source_collides"
            )
        if any(
            (
                str(row["consumer_request_ref"]),
                str(row["location"]),
                str(row["target_path"]),
            )
            == (
                str(deferred_use["consumer_request_ref"]),
                str(deferred_use["location"]),
                str(deferred_use["target_path"]),
            )
            for row in uses
        ):
            raise CandidateLocalFailure(
                "M11b", "binding", "deferred_fresh_target_collides"
            )
        sources.append(deferred_source)
        uses.append(deferred_use)
        sources.sort(key=lambda row: str(row["source_id"]))
        uses.sort(
            key=lambda row: (
                str(row["consumer_request_ref"]),
                str(row["location"]),
                str(row["target_path"]),
                str(row["source_id"]),
            )
        )
    _close_workflow_before_member_binding(
        candidate=candidate,
        workflow_before=workflow_before,
        sources=sources,
        uses=uses,
        value_flows=value_flows,
        binding_plan=binding_plan,
        requests=requests,
        request_order=request_order,
        recording_trace=recording_trace,
        excluded_proof_source_refs=closure_only_request_refs,
    )
    return {
        "schema_version": "uisemtest-resource-binding-plan-v1",
        "candidate_id": candidate_id,
        "arm": arm,
        "sources": sources,
        "uses": uses,
        "concrete_values_present": False,
        "derivation": {
            "source": "current_observed_value_flow_set",
            "selection": "evidence_anchored_or_nearest_lookup_plus_unique_creator_v3",
            "observed_value_flow_set_sha256": value_flows.canonical_sha256(),
        },
    }


def _recorded_numeric_path_transport(
    *,
    recording_trace: Mapping[str, Any] | None,
    creator_request_ref: str,
    response_path: str,
    target_location: str,
    target_scalar_type: str,
) -> bool:
    """Prove that a numeric JSON identity was recorded in a URL path segment."""

    if (
        target_location != "path"
        or target_scalar_type != "string"
        or not isinstance(recording_trace, Mapping)
        or not isinstance(recording_trace.get("api_requests"), list)
    ):
        return False
    rows = [
        row
        for row in recording_trace["api_requests"]
        if isinstance(row, Mapping)
        and str(row.get("id") or "") == creator_request_ref
    ]
    if len(rows) != 1:
        return False
    value = extract_typed_value(rows[0].get("response_body"), response_path)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


_INDEXED_MEMBER_PATH = re.compile(
    r"^(?P<collection>\$.*)\[(?P<index>\d+)](?P<field>\.[^.\[]+)$"
)


def _close_workflow_before_member_binding(
    *,
    candidate: Mapping[str, Any],
    workflow_before: Mapping[str, str] | None,
    sources: list[dict[str, Any]],
    uses: list[dict[str, Any]],
    value_flows: ObservedValueFlowSet,
    binding_plan: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
    request_order: Mapping[str, int],
    recording_trace: Mapping[str, Any] | None,
    excluded_proof_source_refs: frozenset[str] = frozenset(),
) -> None:
    """Bind one fresh collection member selected by recorded and fresh identity."""

    if workflow_before is None or not isinstance(recording_trace, Mapping):
        return
    before_ref = str(workflow_before["request_ref"])
    producer_ref = str(candidate["producer"]["request_ref"])
    after_ref = str(candidate["consumer"]["request_ref"])
    if (
        requests[before_ref].get("actor_id") != requests[after_ref].get("actor_id")
        or _request_session_id(requests[before_ref]) != _request_session_id(requests[after_ref])
        or requests[before_ref].get("operation_id") != requests[after_ref].get("operation_id")
        or not request_order[before_ref] < request_order[producer_ref] < request_order[after_ref]
    ):
        return
    predicate = candidate.get("primary_predicate")
    identity_pairs = _strict_identity_field_pairs(predicate)
    if not identity_pairs:
        return
    candidate_rows = [
        flow for flow in value_flows.flows
        if flow.producer_request_ref == before_ref
        and flow.consumer_request_ref == producer_ref
        and flow.from_location == "response_body"
    ]
    source_paths = {
        flow.from_field for flow in candidate_rows
        if (match := _INDEXED_MEMBER_PATH.fullmatch(flow.from_field)) is not None
        and (
            "$" + match.group("field"),
            _typed_path(
                flow.to_field,
                location=_target_location(flow.to_location),
            ),
        ) in identity_pairs
    }
    if len(source_paths) > 1:
        raise CandidateLocalFailure(
            "M11b", "binding", "workflow_member_source_ambiguous"
        )
    if not source_paths:
        return
    response_path = next(iter(source_paths))
    rows = [flow for flow in candidate_rows if flow.from_field == response_path]
    match = _INDEXED_MEMBER_PATH.fullmatch(response_path)
    if match is None:
        return
    recorded_rows = {
        str(row.get("id") or ""): row
        for row in recording_trace.get("api_requests", ())
        if isinstance(row, Mapping)
    }
    recorded = recorded_rows.get(before_ref)
    collection = (
        extract_typed_value(recorded.get("response_body"), match.group("collection"))
        if isinstance(recorded, Mapping) else None
    )
    index = int(match.group("index"))
    if not isinstance(collection, list) or index >= len(collection) or not isinstance(collection[index], Mapping):
        return
    member = collection[index]
    target_path = "$" + match.group("field")
    member_rows = [
        (path, value, _json_scalar_type(value))
        for path, value in _recorded_scalar_paths(member)
        if _identity_field_name(path)
        and not _session_managed_binding_material(
            location="body", target_field=path, source_field=path
        )
        and isinstance(value, (str, int)) and not isinstance(value, bool)
    ]
    proofs = []
    for path, value, scalar_type in member_rows:
        if path == target_path:
            continue
        matches = [
            source for source in sources
            if source["scalar_type"] == scalar_type
            and source["creator_request_ref"] not in excluded_proof_source_refs
            and source.get("recorded_value_sha256") == scalar_sha256(value)
            and request_order.get(str(source["creator_request_ref"]), 10**12)
            < request_order[before_ref]
        ]
        if len(matches) == 1:
            proofs.append({
                "member_path": path,
                "source_id": str(matches[0]["source_id"]),
                "scalar_type": scalar_type,
            })
    if not proofs:
        return
    shape = [
        {"member_path": path, "scalar_type": scalar_type}
        for path, _value, scalar_type in sorted(member_rows)
    ]
    recorded_value = extract_typed_value(member, target_path)
    recorded_matches = [
        candidate_index for candidate_index, candidate_member in enumerate(collection)
        if isinstance(candidate_member, Mapping)
        and extract_typed_value(candidate_member, target_path) == recorded_value
    ]
    if not recorded_matches:
        raise CandidateLocalFailure(
            "M11b", "binding", "workflow_member_identity_missing"
        )
    if recorded_matches != [index]:
        raise CandidateLocalFailure(
            "M11b", "binding", "workflow_member_identity_ambiguous"
        )
    target_uses = []
    template = binding_plan["request_bindings"][producer_ref]
    for flow in rows:
        location = _target_location(flow.to_location)
        target = (
            str((binding_plan.get("path_binding_targets") or {}).get(producer_ref, {}).get(flow.to_field, ""))
            if location == "path" else _typed_path(flow.to_field, location=location)
        )
        if target:
            target_uses.append((location, target))
    if not target_uses:
        return
    scalar_type = _json_scalar_type(recorded_value)
    source_id = canonical_sha256({
        "creator_request_ref": before_ref,
        "response_path": response_path,
        "recorded_value_sha256": scalar_sha256(recorded_value),
        "collection_identity": proofs,
    })
    sources.append({
        "source_id": source_id,
        "actor_id": str(workflow_before["actor_id"]),
        "creator_request_ref": before_ref,
        "response_path": response_path,
        "scalar_type": scalar_type,
        "recorded_value_sha256": scalar_sha256(recorded_value),
        "collection_identity": proofs,
        "collection_identity_shape": shape,
    })
    existing = {(row["consumer_request_ref"], row["location"], row["target_path"]) for row in uses}
    for location, target in sorted(set(target_uses)):
        if (producer_ref, location, target) not in existing:
            uses.append({
                "source_id": source_id,
                "consumer_request_ref": producer_ref,
                "location": location,
                "target_path": target,
                "actor_id": str(candidate["producer"]["actor_id"]),
                "scalar_type": scalar_type,
            })
    sources.sort(key=lambda row: str(row["source_id"]))
    uses.sort(key=lambda row: (
        str(row["consumer_request_ref"]), str(row["location"]),
        str(row["target_path"]), str(row["source_id"]),
    ))


_SESSION_MATERIAL_NAMES = frozenset({
    "authorization",
    "cookie",
    "setcookie",
    "session",
    "token",
    "accesstoken",
    "refreshtoken",
})
_AUTHENTICATED_PROFILE_FORBIDDEN_FIELDS = _SESSION_MATERIAL_NAMES | frozenset({
    "credential",
    "credentials",
    "password",
    "passphrase",
    "secret",
})


def _session_managed_binding_material(
    *, location: str, target_field: str, source_field: str
) -> bool:
    """Keep authentication/session material outside ordinary fresh binding."""

    def names(value: str) -> set[str]:
        return {
            re.sub(r"[^a-z0-9]", "", token.casefold())
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", value)
        }

    target_names = names(target_field)
    source_names = names(source_field)
    if location == "header" and target_names & {
        "authorization", "cookie", "setcookie"
    }:
        return True
    return bool((target_names | source_names) & _SESSION_MATERIAL_NAMES)


def _recorded_scalar_paths(
    value: Any, *, path: str = "$"
) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            result.extend(_recorded_scalar_paths(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(
                _recorded_scalar_paths(child, path=f"{path}[{index}]")
            )
    else:
        result.append((path, value))
    return result


def _recorded_scalar_members(
    value: Any, *, path: str = "$"
) -> list[tuple[str, Any, Mapping[str, Any]]]:
    result: list[tuple[str, Any, Mapping[str, Any]]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if isinstance(child, (Mapping, list)):
                result.extend(_recorded_scalar_members(child, path=child_path))
            else:
                result.append((child_path, child, value))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(
                _recorded_scalar_members(child, path=f"{path}[{index}]")
            )
    return result


def _authenticated_profile_field_is_forbidden(path: str) -> bool:
    terminal = re.sub(
        r"[^a-z0-9]", "", _terminal_binding_name(path).casefold()
    )
    return terminal in _AUTHENTICATED_PROFILE_FORBIDDEN_FIELDS


def _redacted_authenticated_identity_bindings(
    *,
    consumers: Mapping[str, str],
    binding_plan: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
    recording_trace: Mapping[str, Any] | None,
    authenticated_actor_identity_paths: Mapping[str, str],
    allowed_locations: set[str],
    allowed_types: set[str],
    existing_uses: list[dict[str, Any]],
) -> tuple[list[tuple[tuple[str, str, str], dict[str, Any]]], list[dict[str, Any]]]:
    """Bind a redacted request scalar to one authenticated profile field.

    The redacted alias is first observed in an earlier response from the same
    actor/session as the request.  Its containing object must carry identity
    scalars that select exactly one authenticated actor, and the same object
    field must exist uniquely below that actor's declared profile root.  The
    fresh value is therefore delayed to the runtime profile probe; neither the
    recorded nor fresh scalar is persisted in this plan.
    """

    recorded = _recorded_request_facts(recording_trace)
    if not recorded:
        return [], []
    profile = _authenticated_profile_scalar_witnesses(
        requests=requests,
        recording_trace=recording_trace,
        authenticated_actor_identity_paths=authenticated_actor_identity_paths,
    )
    request_order = {
        request_ref: index for index, request_ref in enumerate(requests)
    }
    covered = {
        (
            str(use["consumer_request_ref"]),
            str(use["location"]),
            str(use["target_path"]),
        )
        for use in existing_uses
    }
    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    uses: list[dict[str, Any]] = []
    for consumer_ref, consumer_actor in sorted(consumers.items()):
        request = binding_plan["request_bindings"].get(consumer_ref)
        consumer_fact = requests.get(consumer_ref)
        if not isinstance(request, Mapping) or not isinstance(
            consumer_fact, Mapping
        ):
            continue
        if not _request_is_read_only(
            consumer_ref,
            bound_request=request,
            requests=requests,
        ):
            continue
        consumer_session = _request_session_id(consumer_fact)
        if consumer_session is None:
            continue
        for location, target_path in sorted(
            _redacted_runtime_material_locations(request)
        ):
            target_key = (consumer_ref, location, target_path)
            if target_key in covered:
                continue
            if location not in allowed_locations or _session_managed_binding_material(
                location=location,
                target_field=target_path,
                source_field=target_path,
            ):
                continue
            target_value = _binding_template_value(
                request, location, target_path
            )
            scalar_type = _json_scalar_type(target_value)
            if scalar_type not in allowed_types:
                continue
            proofs: set[tuple[str, str, str, tuple[str, ...]]] = set()
            for observed_ref, observed in recorded.items():
                observed_fact = requests.get(observed_ref)
                if (
                    not isinstance(observed_fact, Mapping)
                    or str(observed.get("actor") or "") != consumer_actor
                    or _request_session_id(observed_fact) != consumer_session
                    or request_order.get(observed_ref, 10**12)
                    >= request_order.get(consumer_ref, -1)
                    or not _request_is_read_only(
                        observed_ref,
                        bound_request=binding_plan["request_bindings"].get(
                            observed_ref, {}
                        ),
                        requests=requests,
                    )
                ):
                    continue
                for alias_path, value, member in _recorded_scalar_members(
                    observed.get("response_body")
                ):
                    if type(value) is not type(target_value) or value != target_value:
                        continue
                    field_name = _terminal_binding_name(alias_path)
                    if _authenticated_profile_field_is_forbidden(field_name):
                        continue
                    matching_actors: set[str] = set()
                    for profile_actor, probe_root in (
                        authenticated_actor_identity_paths.items()
                    ):
                        identity_matches = [
                            key
                            for key, sibling in member.items()
                            if _identity_field_name(str(key))
                            and (witness := profile.get(
                                (profile_actor, f"{probe_root}.{key}")
                            )) is not None
                            and type(witness[0]) is type(sibling)
                            and witness[0] == sibling
                        ]
                        if identity_matches:
                            matching_actors.add(profile_actor)
                    if len(matching_actors) != 1:
                        continue
                    profile_actor = next(iter(matching_actors))
                    probe_root = authenticated_actor_identity_paths[profile_actor]
                    field_rows = [
                        (path, witness)
                        for (actor, path), witness in profile.items()
                        if actor == profile_actor
                        and _terminal_binding_name(path) == field_name
                        and type(witness[0]) is type(target_value)
                        and not _authenticated_profile_field_is_forbidden(path)
                    ]
                    if len(field_rows) != 1:
                        continue
                    profile_path, (_recorded_value, probe_refs) = field_rows[0]
                    proofs.add(
                        (profile_actor, profile_path, scalar_type, probe_refs)
                    )
            if len(proofs) != 1:
                continue
            profile_actor, response_path, scalar_type, probe_refs = next(
                iter(proofs)
            )
            equivalent_probe_shapes = {
                (
                    str(requests[ref].get("method") or ""),
                    str(requests[ref].get("canonical_path") or ""),
                    str(requests[ref].get("operation_id") or ""),
                    _request_session_id(requests[ref]),
                )
                for ref in probe_refs
            }
            if len(equivalent_probe_shapes) != 1:
                continue
            creator_ref = min(probe_refs, key=request_order.__getitem__)
            source_key = (creator_ref, response_path, scalar_type)
            source_id = canonical_sha256({
                "creator_request_ref": creator_ref,
                "response_path": response_path,
                "scalar_type": scalar_type,
                "authenticated_actor": profile_actor,
                "recorded_alias_sha256": scalar_sha256(target_value),
            })
            sources[source_key] = {
                "source_id": source_id,
                "actor_id": profile_actor,
                "creator_request_ref": creator_ref,
                "response_path": response_path,
                "scalar_type": scalar_type,
                "recorded_value_sha256": scalar_sha256(target_value),
            }
            uses.append({
                "source_id": source_id,
                "consumer_request_ref": consumer_ref,
                "location": location,
                "target_path": target_path,
                "actor_id": consumer_actor,
                "scalar_type": scalar_type,
            })
            covered.add(target_key)
    return list(sources.items()), uses


def _authenticated_profile_setup_rows(
    *,
    consumers: Mapping[str, str],
    binding_plan: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
    recording_trace: Mapping[str, Any] | None,
    authenticated_actor_identity_paths: Mapping[str, str],
) -> list[dict[str, str]]:
    """Close authenticated profile reads as technical setup dependencies."""

    policy = binding_plan["fresh_materialization_policy"]
    sources, _uses = _redacted_authenticated_identity_bindings(
        consumers=consumers,
        binding_plan=binding_plan,
        requests=requests,
        recording_trace=recording_trace,
        authenticated_actor_identity_paths=authenticated_actor_identity_paths,
        allowed_locations=set(policy["allowed_target_locations"]),
        allowed_types=set(policy["allowed_scalar_types"]),
        existing_uses=[],
    )
    return [
        {
            "actor_id": str(source["actor_id"]),
            "request_ref": str(source["creator_request_ref"]),
        }
        for _source_key, source in sources
    ]


def _ordered_setup_rows(
    *,
    setup_by_ref: Mapping[str, Mapping[str, Any]],
    request_order: Mapping[str, int],
    technical_profile_refs: set[str],
) -> list[dict[str, Any]]:
    """Run authenticated profile reads before setup consumers.

    These rows are technical fresh-session identity probes added by M11b, not
    recorded business prerequisites.  All other setup rows retain their
    recorded relative order.
    """

    return [
        copy.deepcopy(dict(setup_by_ref[request_ref]))
        for request_ref in sorted(
            setup_by_ref,
            key=lambda request_ref: (
                request_ref not in technical_profile_refs,
                request_order[request_ref],
            ),
        )
    ]


def _authenticated_actor_identity_bindings(
    *,
    candidate: Mapping[str, Any],
    setup_refs: Mapping[str, str],
    consumers: Mapping[str, str],
    binding_plan: Mapping[str, Any],
    value_flows: ObservedValueFlowSet,
    cited_flow_ids: set[str],
    recording_trace: Mapping[str, Any] | None,
    request_facts: Mapping[str, Mapping[str, Any]] | None = None,
    authenticated_actor_identity_paths: Mapping[str, str],
    paired_before: Mapping[str, str] | None = None,
    allowed_locations: set[str],
    allowed_types: set[str],
    existing_uses: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[tuple[tuple[str, str, str], dict[str, Any]]], list[dict[str, Any]]]:
    """Bind one recorded logical actor identity to its fresh setup response.

    The profile contributes only its authenticated probe scalar or object
    root.  Admission additionally requires a cited recorded flow into the
    physical target, a matching producer-response witness for that actor, and
    exactly one earlier selected setup response carrying the same typed actor
    identity.  Values themselves never enter the materialized plan.
    """

    if not isinstance(recording_trace, Mapping):
        return [], []
    rows = recording_trace.get("api_requests")
    if not isinstance(rows, list):
        return [], []
    recorded = {
        str(row.get("id")): row for row in rows if isinstance(row, Mapping)
    }
    producer = candidate.get("producer")
    if not isinstance(producer, Mapping):
        return [], []
    producer_ref = str(producer.get("request_ref") or "")
    producer_actor = str(producer.get("actor_id") or "")
    probe_path = authenticated_actor_identity_paths.get(producer_actor)
    producer_row = recorded.get(producer_ref)
    if not probe_path or not isinstance(producer_row, Mapping):
        return [], []
    declared_identity_name = _terminal_binding_name(str(probe_path))
    probe_names = re.findall(r"[A-Za-z_][A-Za-z0-9_-]*", str(probe_path))
    identity_source_names = {declared_identity_name}
    if len(probe_names) >= 2:
        identity_source_names.add(
            _terminal_binding_name("".join(probe_names[-2:]))
        )
    probe_is_object = any(
        isinstance(
            extract_typed_value(
                (recorded.get(request_ref) or {}).get("response_body"),
                str(probe_path),
            ),
            Mapping,
        )
        for request_ref, actor_id in setup_refs.items()
        if actor_id == producer_actor
    )

    source_rows: list[tuple[tuple[str, str, str], dict[str, Any]]] = []
    uses: list[dict[str, Any]] = []
    seen_targets = {
        (
            str(use.get("consumer_request_ref") or ""),
            str(use.get("location") or ""),
            str(use.get("target_path") or ""),
        )
        for use in existing_uses
    }
    for flow in value_flows.flows:
        if (
            flow.flow_id not in cited_flow_ids
            or flow.consumer_request_ref not in consumers
            or flow.from_location != "response_body"
        ):
            continue
        flow_source_name = _terminal_binding_name(str(flow.from_field))
        if probe_is_object:
            probe_root_name = _terminal_binding_name(str(probe_path))
            if str(flow.from_field).startswith(str(probe_path) + "."):
                identity_name = flow_source_name
            elif (
                flow_source_name.startswith(probe_root_name)
                and len(flow_source_name) > len(probe_root_name)
            ):
                identity_name = flow_source_name[len(probe_root_name):]
            else:
                continue
            if not _identity_field_name(identity_name):
                continue
        else:
            if flow_source_name not in identity_source_names:
                continue
            identity_name = declared_identity_name
        producer_identity_values = _recorded_named_scalars(
            producer_row.get("response_body"), terminal_name=identity_name
        )
        if not producer_identity_values:
            continue
        location = _target_location(str(flow.to_location))
        if location not in {"path", "query", "body"} or location not in allowed_locations:
            continue
        consumer_ref = str(flow.consumer_request_ref)
        template = binding_plan["request_bindings"].get(consumer_ref)
        if not isinstance(template, Mapping):
            raise CandidateLocalFailure(
                "M11b", "binding", "fresh_consumer_request_binding_missing"
            )
        if location == "path":
            target_path = str(
                (binding_plan.get("path_binding_targets") or {})
                .get(consumer_ref, {})
                .get(str(flow.to_field), "")
            )
            if not target_path:
                raise CandidateLocalFailure(
                    "M11b", "binding", "authenticated_actor_identity_target_missing"
                )
        else:
            target_path = _typed_path(str(flow.to_field), location=location)
        target_key = (consumer_ref, location, target_path)
        if target_key in seen_targets:
            continue
        target_value = _binding_template_value(template, location, target_path)
        scalar_type = _json_scalar_type(target_value)
        if scalar_type not in allowed_types:
            raise CandidateLocalFailure(
                "M11b", "contract", "fresh_scalar_type_not_admitted"
            )
        producer_matches = [
            path
            for path, value in producer_identity_values
            if type(value) is type(target_value) and value == target_value
        ]
        if not producer_matches:
            continue
        if len(producer_matches) != 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "authenticated_actor_identity_witness_ambiguous"
            )
        producer_session = _request_session_id(producer_row)
        setup_matches = [
            (request_ref, path)
            for request_ref, actor_id in setup_refs.items()
            if actor_id == producer_actor
            and (
                producer_session is None
                or _request_session_id(recorded.get(request_ref) or {})
                == producer_session
            )
            for path, value in _recorded_named_scalars(
                (recorded.get(request_ref) or {}).get("response_body"),
                terminal_name=identity_name,
            )
            if type(value) is type(target_value) and value == target_value
        ]
        if not setup_matches:
            raise CandidateLocalFailure(
                "M11b", "binding", "authenticated_actor_identity_source_missing"
            )
        exact_setup_matches = {
            row
            for row in setup_matches
            if (
                row[1].startswith(str(probe_path) + ".")
                and _terminal_binding_name(row[1]) == identity_name
                if probe_is_object
                else row[1] == probe_path
            )
        }
        eligible_setup_matches = (
            exact_setup_matches
            if probe_is_object
            else exact_setup_matches or set(setup_matches)
        )
        if not eligible_setup_matches:
            raise CandidateLocalFailure(
                "M11b", "binding", "authenticated_actor_identity_source_missing"
            )
        if len(eligible_setup_matches) != 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "authenticated_actor_identity_source_ambiguous"
            )
        creator_ref, response_path = next(iter(eligible_setup_matches))
        source_key = (creator_ref, response_path, scalar_type)
        source_id = canonical_sha256({
            "creator_request_ref": creator_ref,
            "response_path": response_path,
            "scalar_type": scalar_type,
            "authenticated_actor": producer_actor,
            "recorded_value_sha256": scalar_sha256(target_value),
        })
        source = {
            "source_id": source_id,
            "actor_id": producer_actor,
            "creator_request_ref": creator_ref,
            "response_path": response_path,
            "scalar_type": scalar_type,
            "recorded_value_sha256": scalar_sha256(target_value),
        }
        seen_targets.add(target_key)
        source_rows.append((source_key, source))
        uses.append({
            "source_id": source_id,
            "consumer_request_ref": consumer_ref,
            "location": location,
            "target_path": target_path,
            "actor_id": consumers[consumer_ref],
            "scalar_type": scalar_type,
        })
        if paired_before is not None and consumer_ref == str(
            candidate.get("consumer", {}).get("request_ref") or ""
        ):
            before_ref = str(paired_before.get("request_ref") or "")
            before_actor = str(paired_before.get("actor_id") or "")
            before_row = (request_facts or {}).get(before_ref)
            after_row = (request_facts or {}).get(consumer_ref)
            before_template = binding_plan["request_bindings"].get(before_ref)
            if (
                not before_ref
                or before_ref == consumer_ref
                or not isinstance(before_row, Mapping)
                or not isinstance(after_row, Mapping)
                or not isinstance(before_template, Mapping)
                or before_actor != consumers.get(consumer_ref)
                or str(before_row.get("actor_id") or "") != before_actor
                or str(after_row.get("actor_id") or "") != before_actor
                or not str(before_row.get("operation_id") or "")
                or before_row.get("operation_id") != after_row.get("operation_id")
                or _request_session_id(before_row) is None
                or _request_session_id(before_row) != _request_session_id(after_row)
                or str(before_row.get("method") or "")
                != str(after_row.get("method") or "")
            ):
                raise CandidateLocalFailure(
                    "M11b", "binding", "authenticated_actor_identity_pair_mismatch"
                )
            if location == "path":
                before_path_targets = (
                    binding_plan.get("path_binding_targets") or {}
                ).get(before_ref, {})
                if len([
                    name
                    for name, path in before_path_targets.items()
                    if str(path) == target_path
                ]) != 1:
                    raise CandidateLocalFailure(
                        "M11b",
                        "binding",
                        "authenticated_actor_identity_pair_target_ambiguous",
                    )
            before_value = _binding_template_value(
                before_template, location, target_path
            )
            if (
                _json_scalar_type(before_value) != scalar_type
                or type(before_value) is not type(target_value)
                or before_value != target_value
            ):
                raise CandidateLocalFailure(
                    "M11b", "binding", "authenticated_actor_identity_pair_mismatch"
                )
            before_target_key = (before_ref, location, target_path)
            if before_target_key in seen_targets:
                raise CandidateLocalFailure(
                    "M11b", "binding", "authenticated_actor_identity_target_ambiguous"
                )
            seen_targets.add(before_target_key)
            uses.append({
                "source_id": source_id,
                "consumer_request_ref": before_ref,
                "location": location,
                "target_path": target_path,
                "actor_id": before_actor,
                "scalar_type": scalar_type,
            })
    unique_sources = {
        (key, canonical_sha256(source)): (key, source)
        for key, source in source_rows
    }
    return list(unique_sources.values()), uses


def _recorded_named_scalars(
    value: Any, *, terminal_name: str, path: str = "$"
) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if isinstance(child, (Mapping, list)):
                result.extend(
                    _recorded_named_scalars(
                        child, terminal_name=terminal_name, path=child_path
                    )
                )
            elif _terminal_binding_name(str(key)) == terminal_name:
                result.append((child_path, child))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(
                _recorded_named_scalars(
                    child,
                    terminal_name=terminal_name,
                    path=f"{path}[{index}]",
                )
            )
    return result


_CONCRETE_OBJECT_MEMBER_PATH = re.compile(
    r"^\$\.(?P<collection>[^.\[\]]+)\.(?P<member>[^.\[\]]+)\.(?P<field>.+)$"
)


def _recorded_projection_member_identity(
    candidate: Mapping[str, Any],
    *,
    recording_trace: Mapping[str, Any] | None,
) -> str | None:
    """Return one concrete object-member identity proven by the recorded body.

    A dotted path is treated as a dynamic collection member only when its
    recorded object has exactly one identity-named scalar whose value equals
    the object key.  Shape alone and ordinary equal-valued fields are not
    sufficient.
    """

    if recording_trace is None:
        return None
    predicate = candidate.get("primary_predicate")
    if not isinstance(predicate, Mapping):
        return None
    left = predicate.get("left")
    if not isinstance(left, Mapping) or left.get("role") != "after":
        return None
    path = str(left.get("path") or "")
    match = _CONCRETE_OBJECT_MEMBER_PATH.fullmatch(path)
    if match is None:
        return None
    request_ref = str(candidate.get("consumer", {}).get("request_ref") or "")
    requests = recording_trace.get("api_requests")
    if not isinstance(requests, list):
        return None
    rows = [row for row in requests if str(row.get("id") or "") == request_ref]
    if len(rows) != 1:
        return None
    body = rows[0].get("response_body")
    collection = extract_typed_value(body, f"$.{match.group('collection')}")
    member = match.group("member")
    if not isinstance(collection, Mapping) or member not in collection:
        return None
    item = collection[member]
    if not isinstance(item, Mapping):
        return None
    identities = [
        value
        for key, value in item.items()
        if _identity_field_name(str(key))
        and isinstance(value, (str, int))
        and type(value) is type(member)
        and value == member
    ]
    return member if len(identities) == 1 else None


def _identity_field_name(value: str) -> bool:
    terminal = value.rsplit(".", 1)[-1]
    folded = terminal.casefold().replace("-", "_")
    return (
        folded == "id"
        or folded.endswith("_id")
        or re.search(r"[A-Za-z0-9]Id$", terminal) is not None
    )


def _close_projection_identity_sources(
    *,
    candidate: Mapping[str, Any],
    resource_plans: dict[str, dict[str, Any]],
    recorded_identity: str,
    recording_material_aliases: tuple[dict[str, Any], ...],
) -> None:
    """Close fresh projection identity without choosing a runtime member.

    A recording reset alias is sufficient by itself.  Otherwise exactly one
    setup response identity source must already be present in the mechanically
    recovered binding plans; that source is copied to every arm solely for
    response-key normalization.  Producer-only sources cannot supply a V1
    control arm and therefore remain fail-closed.
    """

    actor_id = str(candidate.get("consumer", {}).get("actor_id") or "")
    matching_aliases = {
        (type(row.get("runtime_value")), row.get("runtime_value"))
        for row in recording_material_aliases
        if (row.get("actor_id") in {None, actor_id})
        and type(row.get("runtime_value")) is type(recorded_identity)
        and row.get("runtime_value") == recorded_identity
        and row.get("normalize_response") is True
    }
    if len(matching_aliases) == 1:
        return
    setup_refs = {
        str(row.get("request_ref") or "") for row in candidate.get("setup", ())
    }
    digest = scalar_sha256(recorded_identity)
    sources = {
        (
            str(source.get("creator_request_ref") or ""),
            str(source.get("response_path") or ""),
            str(source.get("scalar_type") or ""),
            str(source.get("recorded_value_sha256") or ""),
        ): copy.deepcopy(source)
        for plan in resource_plans.values()
        for source in plan.get("sources", ())
        if str(source.get("creator_request_ref") or "") in setup_refs
        and _identity_field_name(
            str(source.get("response_path") or "").rsplit(".", 1)[-1]
        )
        and str(source.get("recorded_value_sha256") or "") == digest
    }
    if len(sources) != 1:
        raise CandidateLocalFailure(
            "M11b", "binding", "predicate_identity_runtime_value_unavailable"
        )
    source = next(iter(sources.values()))
    source["normalization_only"] = True
    for plan in resource_plans.values():
        existing = [
            row
            for row in plan.get("sources", ())
            if str(row.get("source_id")) == str(source["source_id"])
        ]
        if len(existing) > 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "predicate_identity_source_ambiguous"
            )
        if not existing:
            plan["sources"].append(copy.deepcopy(source))
            plan["sources"].sort(key=lambda row: str(row["source_id"]))


def _require_runtime_request_material(
    *,
    candidate: Mapping[str, Any],
    protocol_shape: Mapping[str, Any],
    request_bindings: Mapping[str, Any],
    resource_plans: Mapping[str, Mapping[str, Any]],
    request_material_bindings: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Reject unresolved recorded material before it becomes an M12 failure."""

    covered = {
        (
            str(use["consumer_request_ref"]),
            str(use["location"]),
            str(use["target_path"]),
        )
        for plan in resource_plans.values()
        for use in plan.get("uses", ())
    }
    covered.update(
        (
            str(binding["request_ref"]),
            str(binding["location"]),
            str(binding["target_path"]),
        )
        for binding in request_material_bindings
    )
    refs = {
        str(candidate["consumer"]["request_ref"]),
        *(str(row["request_ref"]) for row in candidate.get("setup", ())),
        *_request_refs_in(protocol_shape),
    }
    if candidate["producer"] is not None:
        refs.add(str(candidate["producer"]["request_ref"]))
    for request_ref in sorted(refs):
        request = request_bindings.get(request_ref)
        if not isinstance(request, Mapping):
            continue
        missing = {
            (request_ref, location, path)
            for location, path in _redacted_runtime_material_locations(request)
            if (request_ref, location, path) not in covered
        }
        if missing:
            raise CandidateLocalFailure(
                "M11b", "binding", "runtime_value_unavailable"
            )


def _candidate_request_material_bindings(
    *,
    candidate: Mapping[str, Any],
    protocol_shape: Mapping[str, Any],
    request_bindings: Mapping[str, Any],
    available_bindings: Sequence[Mapping[str, Any]],
    resource_plans: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    refs = {
        str(candidate["consumer"]["request_ref"]),
        *(str(row["request_ref"]) for row in candidate.get("setup", ())),
        *_request_refs_in(protocol_shape),
    }
    if candidate["producer"] is not None:
        refs.add(str(candidate["producer"]["request_ref"]))
    resource_covered = {
        (
            str(use["consumer_request_ref"]),
            str(use["location"]),
            str(use["target_path"]),
        )
        for plan in resource_plans.values()
        for use in plan.get("uses", ())
    }
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in available_bindings:
        if not isinstance(raw, Mapping):
            continue
        request_ref = str(raw.get("request_ref") or "")
        location = str(raw.get("location") or "")
        target_path = str(raw.get("target_path") or "")
        key = (request_ref, location, target_path)
        request = request_bindings.get(request_ref)
        if (
            request_ref not in refs
            or key in resource_covered
            or location != "body"
            or not isinstance(request, Mapping)
            or (location, target_path)
            not in _redacted_runtime_material_locations(request)
        ):
            continue
        marker = _binding_template_value(request, location, target_path)
        if (
            not isinstance(marker, str)
            or hashlib.sha256(marker.encode()).hexdigest()
            != str(raw.get("redaction_token_sha256") or "")
            or key in selected
        ):
            continue
        selected[key] = copy.deepcopy(dict(raw))
    return tuple(selected[key] for key in sorted(selected))


def _request_refs_in(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        refs = (
            {str(value["request_ref"])}
            if isinstance(value.get("request_ref"), str)
            else set()
        )
        for child in value.values():
            refs.update(_request_refs_in(child))
        return refs
    if isinstance(value, (list, tuple)):
        refs: set[str] = set()
        for child in value:
            refs.update(_request_refs_in(child))
        return refs
    return set()


def _redacted_runtime_material_locations(
    request: Mapping[str, Any],
) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for index, segment in enumerate(str(request.get("path") or "").strip("/").split("/")):
        if _is_redacted_runtime_material(segment):
            result.add(("path", f"$.segments[{index}]"))
    for key, value in (request.get("query") or {}).items():
        if _is_redacted_runtime_material(value):
            result.add(("query", f"$.{key}"))
    for key, value in (request.get("headers") or {}).items():
        if _is_redacted_runtime_material(value):
            result.add(("header", f"$.{key}"))
    result.update(
        ("body", path)
        for path in _redacted_json_paths(request.get("body"))
    )
    return result


def _redacted_json_paths(value: Any, path: str = "$") -> set[str]:
    if _is_redacted_runtime_material(value):
        return {path}
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            result.update(_redacted_json_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.update(_redacted_json_paths(child, f"{path}[{index}]"))
    return result


def _is_redacted_runtime_material(value: Any) -> bool:
    return (
        isinstance(value, str)
        and _REDACTED_RUNTIME_MATERIAL.fullmatch(value) is not None
    )


def _binding_scalar_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _resolve_binding_target_sources(
    uses: list[dict[str, Any]],
    *,
    sources: tuple[dict[str, Any], ...],
    requests: Mapping[str, Mapping[str, Any]],
    evidence_selected_source_ids: set[str],
) -> list[dict[str, Any]]:
    """Keep one proven source for each physical request target."""

    source_by_id = {str(row["source_id"]): row for row in sources}
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for use in uses:
        grouped.setdefault(
            (
                str(use["consumer_request_ref"]),
                str(use["location"]),
                str(use["target_path"]),
            ),
            [],
        ).append(use)

    # A read-side indexed scalar may be the recorded witness of the same
    # resource created earlier in the dependency chain.  A shared physical
    # target proves that equivalence only when both sources carry the same
    # recorded typed scalar and exactly one source is state-changing.  Reuse
    # that fresh creator for every use of the order-unstable read source.
    source_signatures = {
        source_id: (
            str(row.get("scalar_type") or ""),
            str(row.get("recorded_value_sha256") or ""),
        )
        for source_id, row in source_by_id.items()
    }
    equivalent: dict[str, set[str]] = {
        source_id: set() for source_id in source_by_id
    }

    def link(left: str, right: str) -> None:
        if (
            left != right
            and source_signatures[left] == source_signatures[right]
            and source_signatures[left][1]
        ):
            equivalent[left].add(right)
            equivalent[right].add(left)

    for rows in grouped.values():
        source_ids = sorted({str(row["source_id"]) for row in rows})
        for index, left in enumerate(source_ids):
            for right in source_ids[index + 1:]:
                link(left, right)

    uses_by_consumer: dict[str, set[str]] = {}
    for use in uses:
        uses_by_consumer.setdefault(
            str(use["consumer_request_ref"]), set()
        ).add(str(use["source_id"]))
    for source_id, source in source_by_id.items():
        creator_ref = str(source["creator_request_ref"])
        if (
            not _request_is_read_only(
                creator_ref,
                bound_request=requests[creator_ref],
                requests=requests,
            )
            or not _identity_field_name(
                str(source.get("response_path") or "").rsplit(".", 1)[-1]
            )
        ):
            continue
        for dependency_source_id in uses_by_consumer.get(creator_ref, set()):
            link(source_id, dependency_source_id)

    source_aliases: dict[str, str] = {}
    remaining = set(equivalent)
    while remaining:
        start = remaining.pop()
        component = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for peer in equivalent[current] - component:
                component.add(peer)
                remaining.discard(peer)
                frontier.append(peer)
        if not any(
            re.search(
                r"\[\d+\]", str(source_by_id[source_id].get("response_path") or "")
            )
            for source_id in component
        ):
            continue
        state_changing = {
            source_id
            for source_id in component
            if not _request_is_read_only(
                str(source_by_id[source_id]["creator_request_ref"]),
                bound_request=requests[
                    str(source_by_id[source_id]["creator_request_ref"])
                ],
                requests=requests,
            )
        }
        if len(state_changing) > 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "observed_fresh_source_ambiguous"
            )
        if len(state_changing) == 1:
            winner = next(iter(state_changing))
            source_aliases.update(
                (source_id, winner)
                for source_id in component
                if source_id != winner
            )

    if source_aliases:
        uses = [
            {
                **row,
                "source_id": source_aliases.get(
                    str(row["source_id"]), str(row["source_id"])
                ),
            }
            for row in uses
        ]
        grouped = {}
        for use in uses:
            grouped.setdefault(
                (
                    str(use["consumer_request_ref"]),
                    str(use["location"]),
                    str(use["target_path"]),
                ),
                [],
            ).append(use)

    resolved: list[dict[str, Any]] = []
    for rows in grouped.values():
        source_ids = {str(row["source_id"]) for row in rows}
        if len(source_ids) == 1:
            resolved.append(rows[0])
            continue
        state_changing = {
            source_id
            for source_id in source_ids
            if not _request_is_read_only(
                str(source_by_id[source_id]["creator_request_ref"]),
                bound_request=requests[
                    str(source_by_id[source_id]["creator_request_ref"])
                ],
                requests=requests,
            )
        }
        if len(state_changing) > 1:
            raise CandidateLocalFailure(
                "M11b", "binding", "observed_fresh_source_ambiguous"
            )
        if len(state_changing) == 1:
            chosen = next(iter(state_changing))
        else:
            evidence_selected = source_ids & evidence_selected_source_ids
            if len(evidence_selected) != 1:
                raise CandidateLocalFailure(
                    "M11b", "binding", "observed_fresh_source_ambiguous"
                )
            chosen = next(iter(evidence_selected))
        resolved.append(
            next(row for row in rows if str(row["source_id"]) == chosen)
        )
    return resolved


def _graphql_creator_flow_matches_target(
    flow: Any,
    *,
    target_path: str,
    requests: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Prevent an unrelated GraphQL mutation value from winning by HTTP method.

    REST creators retain the existing behavior.  A GraphQL mutation is a
    creator for an uncited technical binding only when the recorded source and
    target name the same terminal identity field.
    """

    request = requests.get(str(flow.producer_request_ref))
    if (
        not isinstance(request, Mapping)
        or request.get("graphql_operation_kind") != "mutation"
    ):
        return True
    return _terminal_binding_name(str(flow.from_field)) == _terminal_binding_name(
        target_path
    )


def _terminal_binding_name(path: str) -> str:
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_-]*", path)
    return re.sub(r"[-_]", "", names[-1]).lower() if names else ""


def _observed_path_depth(path: str) -> int:
    """Rank observed scalar paths structurally without naming subject fields."""

    return path.count(".") + path.count("[")


def _path_use_targets_variable(
    use: ResourceBindingUse,
    *,
    path_binding_targets: Mapping[str, Mapping[str, str]],
) -> bool:
    return _path_target_is_variable(
        str(use.consumer_request_ref),
        str(use.target_path),
        path_binding_targets=path_binding_targets,
    )


def _path_target_is_variable(
    request_ref: str,
    target_path: str,
    *,
    path_binding_targets: Mapping[str, Mapping[str, str]],
) -> bool:
    prefix = "$.segments["
    if not target_path.startswith(prefix) or not target_path.endswith("]"):
        raise CandidateLocalFailure(
            "M11b", "binding", "path_binding_target_invalid"
        )
    try:
        int(target_path[len(prefix) : -1])
    except ValueError as exc:
        raise CandidateLocalFailure(
            "M11b", "binding", "path_binding_target_invalid"
        ) from exc
    return target_path in set(path_binding_targets.get(request_ref, {}).values())


def _validate_binding_plan_boundary(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != "uisemtest-current-subject-adapter-v1":
        raise ValueError("unsupported M11b current subject adapter")
    required = {
        "request_bindings",
        "fresh_materialization_policy",
        "observer_policy",
        "settle_policy",
        "sensitive_classification",
    }
    if not required <= set(value):
        raise ValueError("M11b fixture binding plan is incomplete")
    request_material = value.get("request_material_bindings", ())
    if not isinstance(request_material, (list, tuple)) or any(
        not isinstance(row, Mapping) for row in request_material
    ):
        raise ValueError("M11b request material bindings are invalid")
    classification = value["sensitive_classification"]
    if set(classification) != {"forbidden_source_refs", "forbidden_projection_paths"}:
        raise ValueError("sensitive classification payload shape mismatch")
    for key in ("forbidden_source_refs", "forbidden_projection_paths"):
        rows = classification[key]
        if not isinstance(rows, list) or len(rows) != len(set(rows)):
            raise ValueError("sensitive classification rows must be unique")


def _target_location(value: str) -> str:
    aliases = {
        "request_body": "body",
        "body": "body",
        "query": "query",
        "request_query": "query",
        "header": "header",
        "request_header": "header",
        "path": "path",
        "request_path": "path",
    }
    try:
        return aliases[value]
    except KeyError as exc:
        raise CandidateLocalFailure(
            "M11b", "contract", "observed_target_location_unsupported"
        ) from exc


def _typed_path(value: str, *, location: str) -> str:
    if value.startswith("$"):
        return value
    if not value or any(token in value for token in ("[", "]", "\\")):
        raise CandidateLocalFailure(
            "M11b", "binding", "observed_target_path_invalid"
        )
    if location == "path" and value.isdigit():
        return f"$.segments[{value}]"
    return f"$.{value}"


def _binding_template_value(
    request: Mapping[str, Any], location: str, path: str
) -> Any:
    if location == "body":
        root = request.get("body")
    elif location == "query":
        root = request.get("query") or {}
    elif location == "header":
        root = request.get("headers") or {}
        header_name = path.removeprefix("$.")
        if path.startswith("$.") and header_name in root:
            return root[header_name]
    elif location == "path":
        segments = str(request.get("path") or "").strip("/").split("/")
        if not path.startswith("$.segments[") or not path.endswith("]"):
            raise CandidateLocalFailure(
                "M11b", "binding", "path_binding_target_invalid"
            )
        try:
            return segments[int(path[len("$.segments[") : -1])]
        except (ValueError, IndexError) as exc:
            raise CandidateLocalFailure(
                "M11b", "binding", "path_binding_target_missing"
            ) from exc
    else:
        raise CandidateLocalFailure(
            "M11b", "contract", "binding_target_location_unsupported"
        )
    try:
        value = extract_typed_value(root, path)
    except (KeyError, TypeError, ValueError, IndexError, ResourceRebindingError) as exc:
        raise CandidateLocalFailure(
            "M11b", "binding", "binding_target_missing"
        ) from exc
    if typed_value_is_missing(value):
        raise CandidateLocalFailure(
            "M11b", "binding", "binding_target_missing"
        )
    return value


def _json_scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    raise CandidateLocalFailure(
        "M11b", "contract", "fresh_value_not_json_scalar"
    )


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


__all__ = [
    "RouteSPreLiveMaterializedCandidate",
    "RouteSM11bMaterializationResult",
    "materialize_current_route_s_inputs",
    "validate_and_persist_current_route_s_material",
]
