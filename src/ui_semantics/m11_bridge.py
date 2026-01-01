"""Lossless v2 CandidateSet → M11 runtime-material bridge.

The bridge is pure and stops before any Route-S collector.  It accepts only a
fully closed ``V2ProposalRunLineage``; bare mappings and historical CandidateSet
objects are intentionally not part of this current API.
"""

from __future__ import annotations

import copy
from typing import Any

from .contracts import (
    DependencyGraph,
    ObservedValueFlowSet,
    ProducerApplicability,
    ProducerRecord,
    UiApiTrace,
    V2BoundCandidate,
    V2RuntimeReadyMaterial,
    V2RuntimeReadyMaterialSet,
)
from .dsl import lint_predicate
from .proposal_run import V2ProposalRunLineage
from .current_route_s import canonical_sha256
from .offline_pipeline import SETUP_DOMAIN_MAX_REQUESTS, producer_setup_domains
from .v2_proposer import V2ProposalCandidate


def bridge_v2_proposal_run_to_m11(
    proposal_run: V2ProposalRunLineage,
    *,
    trace: UiApiTrace,
    applicability: ProducerApplicability,
    material_set_id: str,
) -> V2RuntimeReadyMaterialSet:
    if not isinstance(proposal_run, V2ProposalRunLineage):
        raise TypeError("current M11 bridge requires a validated V2ProposalRunLineage")
    package = proposal_run.frozen_input.lineage.package
    if package.artifact_sha256["ui_api_trace"] != trace.canonical_sha256():
        raise ValueError("M11 trace does not match the frozen pre-proposal package")
    if package.artifact_sha256["producer_applicability"] != applicability.canonical_sha256():
        raise ValueError("M11 producer applicability does not match the frozen package")

    requests = {str(item["request_ref"]): item for item in trace.trace["api_requests"]}
    available = {
        item.request_ref: item
        for item in applicability.producers
        if item.applicability == "available"
    }
    candidate_set = proposal_run.candidate_set
    candidate_set_sha = candidate_set.canonical_sha256()
    candidate_template_sha = candidate_set.source_sha256.get("canonical_template")
    if candidate_template_sha is None:
        raise ValueError("M11 candidate set lacks its actual proposal template lineage")
    replay_source_sha256 = {
        key: value
        for key, value in candidate_set.source_sha256.items()
        if key.startswith(("provider_actual_", "current_validation_"))
        or key == "validation_amendment"
    }
    replay_source_refs = (
        tuple(
            ref
            for ref in candidate_set.source_refs
            if ref != candidate_set.rendered_input_ref
        )
        if replay_source_sha256
        else ()
    )
    union_sha = canonical_sha256(proposal_run.union_provenance.model_dump(mode="json"))
    bound: list[V2BoundCandidate] = []
    materials: list[V2RuntimeReadyMaterial] = []
    opportunities = {
        str(item["plan_id"]): item
        for item in proposal_run.union_provenance.constructed_execution_plans
    }
    value_flows = ObservedValueFlowSet.model_validate(
        package.artifact_payloads["observed_value_flow_set"]
    )
    graph = DependencyGraph.model_validate(
        package.artifact_payloads["dependency_graph"]
    )
    frozen_setup_domains = producer_setup_domains(
        applicability,
        trace=trace,
        value_flows=value_flows,
        graph=graph,
    )

    for record in candidate_set.candidates:
        candidate = V2ProposalCandidate.model_validate(record.payload, strict=True)
        opportunity = opportunities[candidate.observation_opportunity_ref]
        if (
            candidate.schema_version != "uisemtest-oracle-candidate-v1"
            or candidate.candidate_id != record.candidate_id
        ):
            raise ValueError("M11 normalized candidate schema or ID mismatch")
        is_query = opportunity["shape_kind"] == "metamorphic_query" or candidate.contract_kind == "read_preservation"
        is_single_state = opportunity["shape_kind"] == "single_state" or opportunity["shape_kind"] == "multi_resource" and candidate.producer is None
        producer_ref = candidate.producer.request_ref if candidate.producer is not None else None
        producer = available.get(producer_ref)
        if producer is None and not (is_query or is_single_state):
            raise ValueError(f"M11 candidate producer is unsupported: {record.candidate_id}")
        if is_query and (
            candidate.setup
            or candidate.producer.request_ref not in requests
            or requests[candidate.producer.request_ref]["actor_id"] != candidate.producer.actor
        ):
            raise ValueError("M11 query source does not match the frozen trace")
        if producer is not None and producer.actor_id != candidate.producer.actor:
            raise ValueError("M11 producer actor does not match producer applicability")
        if candidate.consumer.request_ref not in requests:
            raise ValueError("M11 observer request is absent from the trace")
        if requests[candidate.consumer.request_ref]["actor_id"] != candidate.consumer.actor:
            raise ValueError("M11 observer actor does not match the trace")

        domain = tuple(producer.eligible_setup_event_ids) if producer is not None else ()
        setup_rows = (
            resolve_selected_setup_bindings(
                tuple(candidate.setup), trace=trace, producer=producer
            )
            if producer is not None
            else []
        )
        setup_requests = [item["request_ref"] for item in setup_rows]

        source_predicate = candidate.primary_predicate.model_dump(mode="json")
        runtime_predicate = _compile_runtime_predicate(source_predicate)
        if is_query or is_single_state:
            anchor_ref = candidate.consumer.request_ref if is_single_state else producer_ref
            producer_order = int(requests[anchor_ref]["global_order"])
            complete_prior = [
                str(row["request_ref"])
                for row in proposal_run.frozen_input.lineage.view.api_requests
                if int(row["global_order"]) < producer_order
            ]
            query_truncated_count = max(
                0, len(complete_prior) - SETUP_DOMAIN_MAX_REQUESTS
            )
            domain_payload = {
                **({"target_request_ref": anchor_ref} if is_single_state else {"producer_request_ref": anchor_ref}),
                "eligible_setup_action_ids": [],
                "policy": "single_observation_bounded_prefix_v1" if is_single_state else "recorded_query_plan_no_setup_v1",
                "ordered_request_refs": complete_prior[-SETUP_DOMAIN_MAX_REQUESTS:],
                "profile_managed_request_refs": [],
                "bound": {
                    "max_requests": SETUP_DOMAIN_MAX_REQUESTS,
                    "truncated_request_count": query_truncated_count,
                },
            }
        else:
            domain_payload = copy.deepcopy(
                frozen_setup_domains.get(candidate.producer.request_ref)
            )
            if not isinstance(domain_payload, dict):
                raise ValueError("M11 frozen producer setup domain is missing")
            if domain_payload.get("eligible_setup_action_ids") != list(domain):
                raise ValueError("M11 frozen setup action domain drifted")
            domain_payload = {"status": "available", **domain_payload}
        eligible_setup_request_refs = tuple(
            str(ref)
            for ref in domain_payload.get("ordered_request_refs", [])
        )
        profile_managed_setup_refs = tuple(
            str(ref)
            for ref in domain_payload.get("profile_managed_request_refs", [])
        )
        truncation_count = int(
            domain_payload.get("bound", {}).get("truncated_request_count", 0)
        )
        domain_sha = canonical_sha256(domain_payload)
        bound_candidate = V2BoundCandidate(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_set_sha256=candidate_set_sha,
            candidate_id=record.candidate_id,
            candidate_payload_sha256=record.payload_sha256,
            input_freeze_manifest_sha256=proposal_run.frozen_input.manifest_raw_sha256,
            package_sha256=package.canonical_sha256(),
            view_sha256=proposal_run.frozen_input.lineage.view.canonical_sha256(),
            rendered_input_sha256=candidate_set.rendered_input_sha256,
            template_sha256=candidate_template_sha,
            proposal_run_plan_sha256=proposal_run.plan_sha256,
            proposal_union_provenance_sha256=union_sha,
            proposal_completion_sha256=proposal_run.completion_raw_sha256,
            raw_response_sha256=proposal_run.raw_response_sha256,
            producer_request_ref=producer_ref,
            observer_request_ref=candidate.consumer.request_ref,
            source_symbolic_predicate=source_predicate,
            source_symbolic_predicate_sha256=canonical_sha256(source_predicate),
            runtime_predicate=runtime_predicate,
            runtime_predicate_sha256=canonical_sha256(runtime_predicate),
            selected_setup_action_ids=tuple(candidate.setup),
            selected_setup_event_ids=tuple(candidate.setup),
            selected_setup_request_refs=tuple(setup_requests),
            eligible_setup_request_refs=eligible_setup_request_refs,
            profile_managed_setup_request_refs=profile_managed_setup_refs,
            setup_domain_truncated_request_count=truncation_count,
            eligible_setup_domain_ref=(
                f"single-observation:{candidate.observation_opportunity_ref}"
                if is_single_state
                else
                f"query-opportunity:{candidate.observation_opportunity_ref}"
                if is_query
                else f"producer-applicability:{producer.request_ref}"
            ),
            eligible_setup_domain_sha256=domain_sha,
            source_refs=(
                proposal_run.frozen_input.manifest_path.name,
                "proposal_run_completion.json",
                f"candidate:{record.candidate_id}",
                *replay_source_refs,
            ),
            source_sha256={
                "candidate_set": candidate_set_sha,
                "eligible_setup_domain": domain_sha,
                "proposal_run_plan": proposal_run.plan_sha256,
                "proposal_union_provenance": union_sha,
                "proposal_completion": proposal_run.completion_raw_sha256,
                **{
                    f"candidate_set_source_{key}": value
                    for key, value in replay_source_sha256.items()
                },
            },
        )
        execution_binding = {
            "schema_version": "uisemtest-v2-route-s-v5-execution-binding-v1",
            "candidate_id": record.candidate_id,
            "producer": {"request_ref": producer_ref, "actor_id": candidate.producer.actor} if candidate.producer is not None else None,
            "observer": {"request_ref": candidate.consumer.request_ref, "actor_id": candidate.consumer.actor},
            "setup": setup_rows,
            "runtime_predicate": runtime_predicate,
            "candidate": candidate.model_dump(mode="json", exclude={"rationale"}),
            "protocol_shape": {
                "shape_kind": opportunity["shape_kind"],
                **{key: copy.deepcopy(opportunity[key]) for key in ("negative_kind", "identity_topology", "repetition_kind", "repeated_plan", "required_checks") if key in opportunity},
                **({"roles": copy.deepcopy(opportunity["roles"])} if opportunity["shape_kind"] == "repeated_execution" else {}),
                **({key: copy.deepcopy(opportunity[key]) for key in ("roles", "observation_plan", "time_requirement")} if opportunity["shape_kind"] == "temporal" else {}),
                **({key: copy.deepcopy(opportunity[key]) for key in ("roles", "observation_plan", "joint_observation")} if opportunity["shape_kind"] == "multi_resource" else {}),
                **(
                    {
                        "roles": copy.deepcopy(opportunity["roles"]),
                        "observation_plan": copy.deepcopy(opportunity["observation_plan"]),
                        "sampling": copy.deepcopy(opportunity["sampling"]),
                    }
                    if opportunity["shape_kind"] == "single_state"
                    else {}
                ),
                **(
                    {
                        "read_execution_evidence": copy.deepcopy(
                            opportunity["read_execution_evidence"]
                        )
                    }
                    if "read_execution_evidence" in opportunity
                    else {}
                ),
                **(
                    {
                        "observer_catalog_selection": copy.deepcopy(
                            opportunity["observer_catalog_selection"]
                        )
                    }
                    if "observer_catalog_selection" in opportunity
                    else {}
                ),
                **(
                    {
                        "roles": copy.deepcopy(opportunity["roles"]),
                        **(
                            {"workflow_kind": opportunity["workflow_kind"]}
                            if "workflow_kind" in opportunity
                            else {}
                        ),
                        **(
                            {
                                "deferred_fresh_binding": copy.deepcopy(
                                    opportunity["deferred_fresh_binding"]
                                )
                            }
                            if "deferred_fresh_binding" in opportunity
                            else {}
                        ),
                        **(
                            {
                                "postcondition_flow": copy.deepcopy(
                                    opportunity["postcondition_flow"]
                                )
                            }
                            if "postcondition_flow" in opportunity
                            else {}
                        ),
                        "workflow_plan": copy.deepcopy(opportunity["workflow_plan"]),
                    }
                    if opportunity["shape_kind"] == "lifecycle_workflow"
                    else {
                        "roles": copy.deepcopy(opportunity["roles"]),
                        "actor_plan": copy.deepcopy(opportunity["actor_plan"]),
                    }
                    if opportunity["shape_kind"] == "actor_matrix"
                    else {
                        "roles": copy.deepcopy(opportunity["roles"]),
                        "transform_kind": opportunity["transform_kind"],
                        "query_plan": copy.deepcopy(opportunity["query_plan"]),
                        "query_scope": copy.deepcopy(opportunity["query_scope"]),
                        "query_transform": copy.deepcopy(opportunity["query_transform"]),
                    }
                    if opportunity["shape_kind"] == "metamorphic_query"
                    else {
                        "roles": copy.deepcopy(opportunity["roles"]),
                        **({"negative_request_fact_ref": opportunity["negative_request_fact_ref"]} if "negative_request_fact_ref" in opportunity else {}),
                        "projection": copy.deepcopy(opportunity["projection"]),
                        "rejection_detector": copy.deepcopy(
                            opportunity["rejection_detector"]
                        ),
                        "session_boundary": copy.deepcopy(
                            opportunity["session_boundary"]
                        ),
                        "negative_plan": copy.deepcopy(
                            opportunity["negative_plan"]
                        ),
                        **(
                            {
                                "catalog_observer_template": copy.deepcopy(
                                    opportunity["catalog_observer_template"]
                                )
                            }
                            if "catalog_observer_template" in opportunity
                            else {}
                        ),
                    }
                    if opportunity["shape_kind"] == "negative_no_effect"
                    else {}
                ),
            },
        }
        resource_plan = {
            "schema_version": "uisemtest-v2-resource-material-plan-v1",
            "status": "offline_unresolved_pending_fresh_binding",
            "setup_request_refs": setup_requests,
            "producer_request_ref": producer_ref,
            "observer_request_ref": candidate.consumer.request_ref,
            "concrete_runtime_values": "forbidden_until_fresh_live_binding",
        }
        pre_live_pins = {
            "schema_version": "uisemtest-v2-route-s-v5-pre-live-pins-v1",
            "bound_candidate_sha256": bound_candidate.canonical_sha256(),
            "execution_binding_sha256": canonical_sha256(execution_binding),
            "resource_material_plan_sha256": canonical_sha256(resource_plan),
            "scientific_input_version": "preproposal-evidence-v2",
            "live_execution_count": 0,
        }
        material = V2RuntimeReadyMaterial(
            candidate_id=record.candidate_id,
            bound_candidate_sha256=bound_candidate.canonical_sha256(),
            execution_binding=execution_binding,
            execution_binding_sha256=canonical_sha256(execution_binding),
            pre_live_pins=pre_live_pins,
            pre_live_pins_sha256=canonical_sha256(pre_live_pins),
            resource_material_plan=resource_plan,
            resource_material_plan_sha256=canonical_sha256(resource_plan),
            source_refs=(bound_candidate.canonical_sha256(),),
            source_sha256={"v2_bound_candidate": bound_candidate.canonical_sha256()},
        )
        bound.append(bound_candidate)
        materials.append(material)

    return V2RuntimeReadyMaterialSet(
        material_set_id=material_set_id,
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_set_sha256=candidate_set_sha,
        bound_candidates=tuple(bound),
        runtime_materials=tuple(materials),
        source_refs=(proposal_run.completion_raw_sha256,),
        source_sha256={
            "candidate_set": candidate_set_sha,
            "proposal_run_completion": proposal_run.completion_raw_sha256,
        },
    )


def _compile_runtime_predicate(symbolic: dict[str, Any]) -> dict[str, Any]:
    result = lint_predicate(symbolic, assertion=False, improved=False)
    if result.verdict != "pass" or result.predicate is None:
        raise ValueError(f"M11 symbolic predicate cannot compile into the approved DSL: {result.reason}")
    return result.predicate


def resolve_selected_setup_bindings(
    selected_action_ids: tuple[str, ...],
    *,
    trace: UiApiTrace,
    producer: ProducerRecord,
) -> list[dict[str, str]]:
    """Map each selected action to exactly one automatic request, losslessly."""

    domain = tuple(producer.eligible_setup_event_ids)
    positions = {event_id: index for index, event_id in enumerate(domain)}
    if len(selected_action_ids) != len(set(selected_action_ids)):
        raise ValueError("M11 setup action IDs must be unique")
    if any(event_id not in positions for event_id in selected_action_ids):
        raise ValueError("M11 selected setup escapes the eligible producer domain")
    if [positions[event_id] for event_id in selected_action_ids] != sorted(
        positions[event_id] for event_id in selected_action_ids
    ):
        raise ValueError("M11 selected setup does not preserve the frozen domain order")
    events = {str(item["event_id"]): item for item in trace.trace["events"]}
    requests = {str(item["request_ref"]): item for item in trace.trace["api_requests"]}
    bindings: dict[str, list[dict[str, Any]]] = {}
    for item in trace.trace["bindings"]:
        bindings.setdefault(str(item["event_id"]), []).append(item)
    review_events = {str(item["event_id"]) for item in trace.trace["binding_reviews"]}
    rows: list[dict[str, str]] = []
    for selected in selected_action_ids:
        if selected in review_events:
            raise ValueError("M11 setup selection is review-only or ambiguous")
        event = events.get(selected)
        matches = bindings.get(selected, [])
        if event is None or len(matches) != 1:
            raise ValueError("M11 setup selection requires exactly one automatic binding")
        request_ref = str(matches[0]["request_ref"])
        request = requests.get(request_ref)
        if request is None or request["actor_id"] != event["actor_id"]:
            raise ValueError("M11 setup event/request actor binding is inconsistent")
        rows.append({
            "selected_action_id": selected,
            "event_id": str(event["event_id"]),
            "recording_action_id": str(event["action_ref"]["action_id"]),
            "request_ref": request_ref,
            "actor_id": str(event["actor_id"]),
        })
    request_refs = [item["request_ref"] for item in rows]
    if len(request_refs) != len(set(request_refs)):
        raise ValueError("M11 setup actions cannot collapse onto a duplicate request")
    return rows
