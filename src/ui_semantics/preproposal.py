"""Deterministic pre-proposal evidence DAG over frozen observations.

This module stops at the rendered scientific input.  It has no provider,
candidate generation, target lifecycle, transport, reset, or evaluation path.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from common.oas_discovery import is_execution_ready
from stage2_recover.loader import load_bundle
from stage4_deps.assemble import build_dependency_graph
from stage4_deps.valueflow import (
    Stage4Inputs,
    converge_edges,
    extract_candidates,
    scheduled_probe_material_edges,
    template_inference_edges,
)
from stage5_synth import project_binding_plans

from .contracts import (
    PREPROPOSAL_FORBIDDEN_SOURCES,
    BindingOpportunity,
    BindingOpportunitySet,
    CompactChannelProjection,
    CompactBindingOpportunity,
    CompactTransferAssertion,
    CompactUiDiff,
    DependencyEdge,
    DependencyGraph,
    DiscoveryCandidateAudit,
    EvidenceBundle,
    EvidenceCard,
    ObservationalApiStructure,
    ObservedApiCatalog,
    ObservedOperation,
    ObservedValueFlow,
    ObservedValueFlowSet,
    NegativeRequestFact,
    PreProposalEvidencePackage,
    ProducerApplicability,
    ProposalEvidenceView,
    RecordingBundle,
    RenderedCandidateInput,
    TransferEvidenceRecord,
    FrozenBusinessProjection,
    TypedTransitionFact,
    TransitionWriteCompetition,
    UiApiTrace,
    UiDiffEvidenceRecord,
)
from .offline_pipeline import (
    SETUP_DOMAIN_MAX_REQUESTS,
    _load_page_state,
    producer_setup_domains,
    resolve_recording_bundle_paths,
)
from .current_route_s import canonical_sha256
from .current_protocols import current_executable_relation_language
from .dsl import get_path
from .route_s_capture_redaction import sensitive_field_category
from .v2_template import (
    PROPOSAL_EVIDENCE_PLACEHOLDER,
    canonical_v2_template_sha256,
    canonical_v2_template_text,
)


COMPACT_BODY_SHAPE_LIMIT = 64
COMPACT_UI_DIFF_ITEM_LIMIT = 16
MECHANICAL_NEIGHBORHOOD_ORDER_RADIUS = 16
MECHANICAL_NEIGHBORHOOD_MAX_REQUESTS = SETUP_DOMAIN_MAX_REQUESTS
CHANGE_REASON = "typed_transition_facts_and_grounded_predicate_expansion"
_SETUP_CLUE_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SETUP_CLUE_SCALAR_TYPES = (str, int, float, bool, type(None))


_UI_DIFF_URL = re.compile(r"https?://[^\s<>'\"]+", re.I)
_UI_DIFF_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
_UI_DIFF_UUID = re.compile(
    r"(?<![0-9A-F])(?:[0-9A-F]{8}-[0-9A-F]{4}-[1-5][0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12})(?![0-9A-F])",
    re.I,
)
_UI_DIFF_TIMESTAMP = re.compile(
    r"(?<!\d)\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?(?!\d)",
    re.I,
)
_UI_DIFF_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)
_UI_DIFF_DYNAMIC_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,64}(?![A-Za-z0-9_-])")


class _EvidenceAliasNormalizer:
    """Preserve business literals while assigning stable aliases to volatile identity."""

    def __init__(self) -> None:
        self._aliases: dict[tuple[str, str], str] = {}
        self._counts: Counter[str] = Counter()

    def _alias(self, kind: str, value: str) -> str:
        key = (kind, value)
        alias = self._aliases.get(key)
        if alias is None:
            self._counts[kind] += 1
            alias = f"<{kind}_{self._counts[kind]}>"
            self._aliases[key] = alias
        return alias

    def normalize_path(self, value: str) -> str:
        parts = []
        for segment in value.split("/"):
            if (
                _UI_DIFF_UUID.fullmatch(segment)
                or _is_opaque_dynamic_token(segment)
                or _is_opaque_path_segment(segment)
            ):
                parts.append(self._alias("ID", segment))
            elif segment.isdigit() and len(segment) >= 5:
                parts.append(self._alias("ID", segment))
            else:
                parts.append(segment)
        return "/".join(parts)

    def normalize_text(self, value: str) -> str:
        normalized = " ".join(value.split())
        normalized = _UI_DIFF_URL.sub(self._normalize_url, normalized)
        normalized = _UI_DIFF_EMAIL.sub(
            lambda match: self._alias("ACTOR", match.group(0)), normalized
        )
        normalized = _UI_DIFF_UUID.sub(
            lambda match: self._alias("ID", match.group(0)), normalized
        )
        normalized = _UI_DIFF_TIMESTAMP.sub(
            lambda match: self._alias("TIME", match.group(0)), normalized
        )
        normalized = _UI_DIFF_JWT.sub("<TOKEN>", normalized)
        return _UI_DIFF_DYNAMIC_TOKEN.sub(self._normalize_dynamic_token, normalized)

    def _normalize_dynamic_token(self, match: re.Match[str]) -> str:
        token = match.group(0)
        return self._alias("ID", token) if _is_opaque_dynamic_token(token) else token

    def _normalize_url(self, match: re.Match[str]) -> str:
        parsed = urlsplit(match.group(0))
        query = urlencode(
            [
                (name, self.normalize_text(value))
                for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            ]
        )
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                self.normalize_path(parsed.path),
                query,
                "",
            )
        )


def _is_opaque_dynamic_token(token: str) -> bool:
    has_alpha = any(char.isalpha() for char in token)
    has_digit = any(char.isdigit() for char in token)
    opaque_long_token = len(token) >= 20 and any(char.isupper() for char in token)
    return has_alpha and (has_digit or opaque_long_token)


def _is_opaque_path_segment(segment: str) -> bool:
    return (
        8 <= len(segment) <= 64
        and sum(char.isupper() for char in segment) >= 2
        and sum(char.islower() for char in segment) >= 2
    )


def identity_like_json_path(path: str) -> bool:
    """Return whether one JSON path carries the existing mechanical identity shape."""

    tail = re.split(r"[.\[\]]+", path)[-1].lower()
    return bool(
        tail in {"id", "uuid", "slug", "key", "code", "username"}
        or re.search(r"(?:^|[_-])(id|uuid|slug|key|code)$", tail)
        or (tail.endswith("id") and len(tail) > 2)
    )


def response_collection_paths_with_identity(
    shape: Mapping[str, Any],
) -> set[str]:
    """Project collection paths that expose an existing mechanical identity."""

    signature = tuple(sorted(
        (str(row.get("path", "")), str(row.get("type", "")))
        for row in shape.get("shape_rows", ())
        if isinstance(row, Mapping)
    ))
    scalar_types = {"boolean", "integer", "number", "null", "string"}
    result: set[str] = set()
    for collection_path, value_type in signature:
        if value_type != "array":
            continue
        member_prefix = f"{collection_path}[*]" if collection_path != "$" else "$[*]"
        if any(
            path == member_prefix and member_type in scalar_types
            for path, member_type in signature
        ):
            result.add(collection_path)
            continue
        if any(
            member_type in scalar_types
            and path.startswith(f"{member_prefix}.")
            and identity_like_json_path(path)
            for path, member_type in signature
        ):
            result.add(collection_path)
    return result


@dataclass(frozen=True)
class PreProposalArtifacts:
    catalog: ObservedApiCatalog
    discovery_audit: DiscoveryCandidateAudit
    value_flows: ObservedValueFlowSet
    dependency_graph: DependencyGraph
    binding_opportunities: BindingOpportunitySet
    package: PreProposalEvidencePackage
    view: ProposalEvidenceView
    rendered_input: RenderedCandidateInput
    raw_dependency_graph: dict[str, Any]


def build_observed_api_catalog(
    structure: ObservationalApiStructure,
    products: Mapping[str, Any],
    trace: UiApiTrace,
    *,
    catalog_id: str,
) -> ObservedApiCatalog:
    initial, probes, augmented = _validated_products(structure, products)
    request_by_observation = {
        (str(item["observation_ref"]["run_id"]), int(item["observation_ref"]["entry_index"])): item["request_ref"]
        for item in trace.trace["api_requests"]
    }
    operations: list[ObservedOperation] = []
    for canonical_path, path_item in sorted(augmented.get("paths", {}).items()):
        for method, operation in sorted(path_item.items()):
            if not is_execution_ready(operation):
                continue
            observation_refs = []
            for observation in operation.get("x-carverflow-observations", []):
                source = str(observation.get("source") or "")
                if source == "stage1_session":
                    key = (str(observation["run_id"]), int(observation["entry_index"]))
                    request_ref = request_by_observation.get(key)
                    if request_ref is None:
                        raise ValueError(f"Stage3 observation is absent from UiApiTrace: {key}")
                    observation_refs.append({
                        "source": source,
                        "run_id": key[0],
                        "entry_index": key[1],
                        "request_ref": request_ref,
                        "status": int(observation["status"]),
                        "timestamp": str(observation["timestamp"]),
                    })
                elif source == "stage2_5_probe":
                    observation_refs.append({
                        "source": source,
                        "probe_id": str(observation["probe_id"]),
                        "status": int(observation["status"]),
                        "timestamp": str(observation["timestamp"]),
                    })
                else:
                    raise ValueError(f"unknown Stage3 observation source: {source}")
            operations.append(
                ObservedOperation(
                    operation_id=str(operation["operationId"]),
                    method=str(method).upper(),
                    canonical_path=str(canonical_path),
                    readiness=str((operation.get("x-carverflow-discovery") or {}).get("execution_readiness")),
                    observation_refs=tuple(observation_refs),
                )
            )
    probe_observations_present = any(
        item.get("source") == "stage2_5_probe"
        for operation in operations
        for item in operation.observation_refs
    )
    return ObservedApiCatalog(
        catalog_id=catalog_id,
        operations=tuple(operations),
        operation_count=len(operations),
        stage2_source_sha256=canonical_sha256(initial),
        stage3_source_sha256=canonical_sha256(augmented),
        source_refs=(structure.canonical_sha256(), trace.canonical_sha256()),
        source_sha256={
            "observational_api_structure": structure.canonical_sha256(),
            "ui_api_trace": trace.canonical_sha256(),
            "discovery_candidate_records": canonical_sha256(probes.get("probes", [])),
        },
        derivation=(
            "recording_and_validated_probe_observations"
            if probe_observations_present
            else "recording_observation_only"
        ),
    )


def build_discovery_candidate_audit(
    structure: ObservationalApiStructure,
    products: Mapping[str, Any],
    *,
    audit_id: str,
) -> DiscoveryCandidateAudit:
    _initial, probes, augmented = _validated_products(structure, products)
    records = tuple(probes.get("probes", []))
    admitted_probe_ids = {
        str(observation["probe_id"])
        for path_item in augmented.get("paths", {}).values()
        for operation in path_item.values()
        for observation in operation.get("x-carverflow-observations", [])
        if observation.get("source") == "stage2_5_probe"
    }
    not_executed = sum(item.get("execution_mode") == "not_executed" for item in records)
    executed = len(records) - not_executed
    admitted = sum(str(item.get("probe_id")) in admitted_probe_ids for item in records)
    if structure.active_http_probes != executed:
        raise ValueError("Stage2.5 active probe count differs from discovery execution")
    if structure.audit_only and (executed != 0 or admitted != 0):
        raise ValueError("audit-only pre-proposal structure cannot contain executed or admitted Stage2.5 rows")
    return DiscoveryCandidateAudit(
        audit_id=audit_id,
        records=records,
        records_sha256=canonical_sha256(list(records)),
        planned_count=len(records),
        executed_count=executed,
        admitted_count=admitted,
        rejected_count=executed - admitted,
        not_executed_count=not_executed,
        kind_counts=dict(sorted(Counter(str(item.get("probe_kind") or "unknown") for item in records).items())),
        execution_scope="audit_only" if not_executed == len(records) else "executed" if not_executed == 0 else "mixed",
        source_refs=(structure.canonical_sha256(),),
        source_sha256={
            "observational_api_structure": structure.canonical_sha256(),
            "audit_only_probe_results": canonical_sha256(probes),
        },
    )


def build_observed_value_flows(
    structure: ObservationalApiStructure,
    products: Mapping[str, Any],
    recording: RecordingBundle,
    trace: UiApiTrace,
    *,
    recording_root: str | Path,
    flow_set_id: str,
) -> ObservedValueFlowSet:
    _initial, _probes, augmented = _validated_products(structure, products)
    paths = resolve_recording_bundle_paths(recording, recording_root)
    bundles = {
        item.run_id: load_bundle(paths[item.actor_id]) for item in recording.actors
    }
    actor_by_run = {item.run_id: item.actor_id for item in recording.actors}
    request_by_observation = {
        (str(item["observation_ref"]["run_id"]), int(item["observation_ref"]["entry_index"])): item["request_ref"]
        for item in trace.trace["api_requests"]
    }
    unresolved = _unresolved_stage3_observations(augmented, bundles, request_by_observation)
    if unresolved:
        raise ValueError(f"Stage3 contains unresolved recording observations: {unresolved[:3]}")
    candidates, filtered = extract_candidates(Stage4Inputs(augmented_oas=augmented, bundles=bundles))
    flows = []
    for candidate in candidates:
        producer_key = (candidate.producer_ref.run_id, candidate.producer_ref.entry_index)
        consumer_key = (candidate.consumer_ref.run_id, candidate.consumer_ref.entry_index)
        producer_entry = bundles[producer_key[0]].entries[producer_key[1]]
        consumer_entry = bundles[consumer_key[0]].entries[consumer_key[1]]
        producer_timestamp = str(producer_entry["startedDateTime"])
        consumer_timestamp = str(consumer_entry["startedDateTime"])
        if _timestamp(consumer_timestamp) < _timestamp(producer_timestamp):
            raise ValueError("Stage4 returned a temporally inverted observed value flow")
        support_refs = [
            {
                "role": "producer",
                "run_id": producer_key[0],
                "entry_index": producer_key[1],
                "request_ref": request_by_observation[producer_key],
                "location": candidate.from_location,
                "field": candidate.from_field,
            },
            {
                "role": "consumer",
                "run_id": consumer_key[0],
                "entry_index": consumer_key[1],
                "request_ref": request_by_observation[consumer_key],
                "location": candidate.to_location,
                "field": candidate.to_field,
            },
        ]
        payload = {
            "producer_operation_id": candidate.producer_op,
            "consumer_operation_id": candidate.consumer_op,
            "producer_request_ref": request_by_observation[producer_key],
            "consumer_request_ref": request_by_observation[consumer_key],
            "producer_actor_id": actor_by_run[producer_key[0]],
            "consumer_actor_id": actor_by_run[consumer_key[0]],
            "producer_session_run_id": producer_key[0],
            "consumer_session_run_id": consumer_key[0],
            "producer_entry_index": producer_key[1],
            "consumer_entry_index": consumer_key[1],
            "producer_timestamp": producer_timestamp,
            "consumer_timestamp": consumer_timestamp,
            "from_location": candidate.from_location,
            "from_field": candidate.from_field,
            "to_location": candidate.to_location,
            "to_field": candidate.to_field,
            "same_session_proof": True,
            "temporal_order_proof": "producer_not_after_consumer",
            "support_refs": support_refs,
            "evidence_semantics": "observed_candidate",
            "grounded": False,
        }
        flows.append(
            ObservedValueFlow(
                flow_id=f"vf-{canonical_sha256(payload)[:24]}",
                support_sha256=canonical_sha256(list(support_refs)),
                **payload,
            )
        )
    flows.sort(key=lambda item: item.flow_id)
    return ObservedValueFlowSet(
        flow_set_id=flow_set_id,
        flows=tuple(flows),
        occurrence_count=len(flows),
        filtered_counts=dict(sorted(filtered.items())),
        unresolved_observation_ref_count=0,
        source_refs=(structure.canonical_sha256(), recording.canonical_sha256(), trace.canonical_sha256()),
        source_sha256={
            "observational_api_structure": structure.canonical_sha256(),
            "recording_bundle": recording.canonical_sha256(),
            "ui_api_trace": trace.canonical_sha256(),
            "stage3_observed_structure": canonical_sha256(augmented),
        },
    )


def build_observed_dependency_graph(
    structure: ObservationalApiStructure,
    products: Mapping[str, Any],
    recording: RecordingBundle,
    catalog: ObservedApiCatalog,
    value_flows: ObservedValueFlowSet,
    *,
    recording_root: str | Path,
    graph_id: str,
) -> tuple[DependencyGraph, dict[str, Any]]:
    _initial, _probes, augmented = _validated_products(structure, products)
    paths = resolve_recording_bundle_paths(recording, recording_root)
    bundle_paths = [paths[item.actor_id] for item in recording.actors]
    raw_graph, _filtered = build_dependency_graph(
        augmented,
        bundle_paths,
        semantic_edge_audit=None,
        semantic_edge_audit_path=None,
        run_id=f"{graph_id}-stage4",
    )
    if any(item.get("kind") == "semantic_order" for item in raw_graph.get("edges", [])):
        raise ValueError("semantic_order is forbidden in the pre-proposal dependency graph")
    bundles = {
        item.run_id: load_bundle(paths[item.actor_id]) for item in recording.actors
    }
    candidates, _ = extract_candidates(Stage4Inputs(augmented_oas=augmented, bundles=bundles))
    exact_edges = converge_edges(candidates)
    template_edges = template_inference_edges(augmented)
    scheduled_edges = scheduled_probe_material_edges(augmented)
    if sum(
        len(evidence.get("detail", {}).get("observation_refs", []))
        for edge in exact_edges
        for evidence in edge.get("evidence", [])
    ) != value_flows.occurrence_count:
        raise ValueError("Stage4 graph evidence does not close over request-level observed flows")
    edges = []
    for raw in raw_graph.get("edges", []):
        observed_count = sum(
            len(evidence.get("detail", {}).get("observation_refs", []))
            for evidence in raw.get("evidence", [])
            if evidence.get("type") == "exact_value_flow"
        )
        raw_sha = canonical_sha256(raw)
        edges.append(
            DependencyEdge(
                edge_id=f"de-{raw_sha[:24]}",
                producer_operation_id=str(raw["producer"]),
                consumer_operation_id=str(raw["consumer"]),
                kind=str(raw["kind"]),
                deterministic_heuristic_score=float(raw.get("confidence") or 0),
                evidence_channel_count=len(raw.get("evidence", [])),
                observed_flow_count=observed_count,
                stage4_edge_sha256=raw_sha,
            )
        )
    edges.sort(key=lambda item: item.edge_id)
    graph = DependencyGraph(
        graph_id=graph_id,
        nodes=tuple(sorted(raw_graph.get("nodes", []))),
        edges=tuple(edges),
        edge_count=len(edges),
        evidence_channel_count=sum(item.evidence_channel_count for item in edges),
        observed_flow_count=sum(item.observed_flow_count for item in edges),
        semantic_order_edge_count=0,
        template_inference_edge_count=len(template_edges),
        scheduled_probe_material_edge_count=len(scheduled_edges),
        observed_api_catalog_sha256=catalog.canonical_sha256(),
        observed_value_flow_set_sha256=value_flows.canonical_sha256(),
        source_refs=(structure.canonical_sha256(), catalog.canonical_sha256(), value_flows.canonical_sha256()),
        source_sha256={
            "observational_api_structure": structure.canonical_sha256(),
            "observed_api_catalog": catalog.canonical_sha256(),
            "observed_value_flow_set": value_flows.canonical_sha256(),
            "stage4_dependency_graph": canonical_sha256(raw_graph),
        },
    )
    return graph, raw_graph


def build_binding_opportunity_set(
    products: Mapping[str, Any],
    raw_dependency_graph: Mapping[str, Any],
    graph: DependencyGraph,
    value_flows: ObservedValueFlowSet,
    *,
    opportunity_set_id: str,
) -> BindingOpportunitySet:
    augmented = products["augmented_structure"]
    plans = project_binding_plans(augmented, dict(raw_dependency_graph))
    flow_index = {_flow_lookup_key(item): item for item in value_flows.flows}
    edge_kinds = {
        (str(item["producer"]), str(item["consumer"])): str(item["kind"])
        for item in raw_dependency_graph.get("edges", [])
    }
    opportunities = []
    for plan in plans:
        if not plan.observation_refs:
            continue
        flow_ids = []
        for refs in plan.observation_refs:
            key = (
                plan.producer,
                plan.consumer,
                plan.from_location,
                plan.from_field,
                plan.to_location,
                plan.to_field,
                str(refs[0]),
                int(refs[1]),
                str(refs[2]),
                int(refs[3]),
            )
            flow = flow_index.get(key)
            if flow is None:
                raise ValueError(f"Stage5 binding projection has no request-level flow: {key}")
            flow_ids.append(flow.flow_id)
        flow_ids = sorted(set(flow_ids))
        payload = {
            "producer_operation_id": plan.producer,
            "consumer_operation_id": plan.consumer,
            "source_edge_kind": edge_kinds[(plan.producer, plan.consumer)],
            "effective_binding_kind": plan.kind,
            "from_location": plan.from_location,
            "from_field": plan.from_field,
            "to_location": plan.to_location,
            "to_field": plan.to_field,
            "value_flow_ids": flow_ids,
            "support_count": len(flow_ids),
            "witness_flow_id": min(flow_ids),
            "evidence_semantics": "observed_candidate",
            "grounded": False,
        }
        full_hash = canonical_sha256(payload)
        opportunities.append(
            BindingOpportunity(
                opportunity_id=f"bo-{full_hash[:24]}",
                full_row_sha256=full_hash,
                **payload,
            )
        )
    opportunities.sort(key=lambda item: item.opportunity_id)
    result = BindingOpportunitySet(
        opportunity_set_id=opportunity_set_id,
        opportunities=tuple(opportunities),
        opportunity_count=len(opportunities),
        support_reference_count=sum(item.support_count for item in opportunities),
        observed_value_flow_set_sha256=value_flows.canonical_sha256(),
        dependency_graph_sha256=graph.canonical_sha256(),
        source_refs=(graph.canonical_sha256(), value_flows.canonical_sha256()),
        source_sha256={
            "dependency_graph": graph.canonical_sha256(),
            "observed_value_flow_set": value_flows.canonical_sha256(),
        },
    )
    validate_binding_opportunity_closure(result, value_flows)
    return result


def validate_binding_opportunity_closure(
    opportunities: BindingOpportunitySet,
    value_flows: ObservedValueFlowSet,
) -> None:
    flows = {item.flow_id: item for item in value_flows.flows}
    if opportunities.observed_value_flow_set_sha256 != value_flows.canonical_sha256():
        raise ValueError("binding opportunities reference a different value-flow set")
    referenced = []
    for item in opportunities.opportunities:
        for flow_id in item.value_flow_ids:
            flow = flows.get(flow_id)
            if flow is None:
                raise ValueError(f"binding opportunity contains a dangling flow ID: {flow_id}")
            expected = (
                item.producer_operation_id,
                item.consumer_operation_id,
                item.from_location,
                item.from_field,
                item.to_location,
                item.to_field,
            )
            observed = (
                flow.producer_operation_id,
                flow.consumer_operation_id,
                flow.from_location,
                flow.from_field,
                flow.to_location,
                flow.to_field,
            )
            if observed != expected:
                raise ValueError("binding opportunity fields do not match referenced flow")
            referenced.append(flow_id)
    if sorted(referenced) != sorted(flows):
        raise ValueError("binding opportunities do not close exactly over observed value flows")


def build_preproposal_evidence_package(
    recording: RecordingBundle,
    trace: UiApiTrace,
    structure: ObservationalApiStructure,
    catalog: ObservedApiCatalog,
    discovery_audit: DiscoveryCandidateAudit,
    evidence: EvidenceBundle,
    applicability: ProducerApplicability,
    value_flows: ObservedValueFlowSet,
    graph: DependencyGraph,
    opportunities: BindingOpportunitySet,
    *,
    package_id: str,
    forbidden_inputs: Mapping[str, Any] | None = None,
) -> PreProposalEvidencePackage:
    _reject_forbidden_inputs(forbidden_inputs)
    validate_binding_opportunity_closure(opportunities, value_flows)
    artifact_models = {
        "recording_bundle": recording,
        "ui_api_trace": trace,
        "observational_api_structure": structure,
        "observed_api_catalog": catalog,
        "discovery_candidate_audit": discovery_audit,
        "evidence_bundle": evidence,
        "producer_applicability": applicability,
        "observed_value_flow_set": value_flows,
        "dependency_graph": graph,
        "binding_opportunity_set": opportunities,
    }
    artifact_payloads = {
        name: value.model_dump(mode="json")
        for name, value in artifact_models.items()
    }
    artifact_hashes = {
        name: canonical_sha256(value)
        for name, value in artifact_payloads.items()
    }
    counts = {
        "recording_actor_count": len(recording.actors),
        "trace_event_count": trace.event_count,
        "trace_admitted_request_count": trace.admitted_request_count,
        "observed_operation_count": catalog.operation_count,
        "discovery_planned_count": discovery_audit.planned_count,
        "discovery_executed_count": discovery_audit.executed_count,
        "discovery_admitted_count": discovery_audit.admitted_count,
        "observed_value_flow_occurrence_count": value_flows.occurrence_count,
        "dependency_edge_count": graph.edge_count,
        "dependency_evidence_channel_count": graph.evidence_channel_count,
        "binding_opportunity_count": opportunities.opportunity_count,
        "producer_universe_count": applicability.universe_count,
        "producer_available_count": applicability.available_count,
        "producer_unsupported_count": applicability.unsupported_count,
    }
    return PreProposalEvidencePackage(
        package_id=package_id,
        artifact_sha256=artifact_hashes,
        artifact_payloads=artifact_payloads,
        channel_availability={key: value.status for key, value in evidence.channels.items()},
        counts=counts,
        forbidden_sources=tuple(sorted(PREPROPOSAL_FORBIDDEN_SOURCES)),
        source_refs=tuple(artifact_hashes),
        source_sha256=artifact_hashes,
    )


def build_proposal_evidence_view(
    package: PreProposalEvidencePackage,
    recording: RecordingBundle,
    trace: UiApiTrace,
    catalog: ObservedApiCatalog,
    discovery_audit: DiscoveryCandidateAudit,
    evidence: EvidenceBundle,
    applicability: ProducerApplicability,
    value_flows: ObservedValueFlowSet,
    graph: DependencyGraph,
    opportunities: BindingOpportunitySet,
    *,
    recording_root: str | Path,
    view_id: str,
    organization: str = "association",
) -> ProposalEvidenceView:
    if organization not in {"association", "temporal", "flat"}:
        raise ValueError(f"unknown evidence organization: {organization}")
    flat = organization == "flat"
    temporal_only = organization in {"temporal", "flat"}
    expected = {
        "recording_bundle": recording.canonical_sha256(),
        "ui_api_trace": trace.canonical_sha256(),
        "observed_api_catalog": catalog.canonical_sha256(),
        "discovery_candidate_audit": discovery_audit.canonical_sha256(),
        "evidence_bundle": evidence.canonical_sha256(),
        "producer_applicability": applicability.canonical_sha256(),
        "observed_value_flow_set": value_flows.canonical_sha256(),
        "dependency_graph": graph.canonical_sha256(),
        "binding_opportunity_set": opportunities.canonical_sha256(),
    }
    if any(package.artifact_sha256[key] != value for key, value in expected.items()):
        raise ValueError("proposal evidence view inputs do not match the pre-proposal package")
    alias_normalizer = _EvidenceAliasNormalizer()
    compact_trace = _compact_trace(
        recording,
        trace,
        recording_root,
        alias_normalizer=alias_normalizer,
    )
    available_setup_domains = producer_setup_domains(
        applicability,
        trace=trace,
        value_flows=value_flows,
        graph=graph,
    )
    applicability_by_ref = {
        item.request_ref: item.model_dump(mode="json")
        for item in applicability.producers
    }
    request_setup_domains: dict[str, dict[str, Any]] = {}
    for request in compact_trace["api_requests"]:
        request_ref = str(request["request_ref"])
        if request_ref in available_setup_domains:
            domain = available_setup_domains[request_ref]
            request_setup_domains[request_ref] = {
                "status": "available",
                "target_request_ref": request_ref,
                "target_anchor": copy.deepcopy(domain["producer_anchor"]),
                "eligible_setup_action_ids": list(
                    domain["eligible_setup_action_ids"]
                ),
                "bound": copy.deepcopy(domain["bound"]),
                "profile_managed": {
                    "active": bool(domain["profile_managed_request_refs"]),
                    "request_count": len(domain["profile_managed_request_refs"]),
                },
                "reason": "automatic_anchor_available",
            }
        elif request_ref in applicability_by_ref:
            row = applicability_by_ref[request_ref]
            request_setup_domains[request_ref] = {
                "status": "unsupported",
                "target_request_ref": request_ref,
                "target_anchor": None,
                "eligible_setup_action_ids": [],
                "reason": row.get("reason_code"),
                "bound": {
                    "max_requests": SETUP_DOMAIN_MAX_REQUESTS,
                    "truncated_request_count": 0,
                },
                "profile_managed": {"active": False, "request_count": 0},
            }
        else:
            request_setup_domains[request_ref] = {
                "status": "not_applicable",
                "target_request_ref": request_ref,
                "target_anchor": None,
                "eligible_setup_action_ids": [],
                "reason": "request_not_setup_eligible",
                "bound": {
                    "max_requests": SETUP_DOMAIN_MAX_REQUESTS,
                    "truncated_request_count": 0,
                },
                "profile_managed": {"active": False, "request_count": 0},
            }
    action_order = {
        str(row["event_id"]): int(row["global_order"])
        for row in compact_trace["ui_actions"]
    }
    setup_action_catalog = tuple(sorted(
        {
            str(action_id)
            for domain in request_setup_domains.values()
            for action_id in domain["eligible_setup_action_ids"]
        },
        key=lambda ref: (action_order[ref], ref),
    ))
    setup_selection_clues = _build_setup_selection_clues(
        recording,
        trace,
        recording_root=recording_root,
        api_requests=compact_trace["api_requests"],
        ui_actions=compact_trace["ui_actions"],
        request_setup_domains=request_setup_domains,
        value_flows=None if temporal_only else value_flows,
        alias_normalizer=alias_normalizer,
    )
    transition_facts = () if temporal_only else _build_typed_transition_facts(
        recording,
        trace,
        recording_root=recording_root,
        api_requests=compact_trace["api_requests"],
        value_flows=value_flows,
        dependency_edges=tuple(
            item.model_dump(mode="json") for item in graph.edges
        ),
    )
    negative_request_facts = () if flat else _build_negative_request_facts(
        recording,
        trace,
        recording_root=recording_root,
        api_requests=compact_trace["api_requests"],
        ui_actions=compact_trace["ui_actions"],
    )

    compact_bindings = tuple(
        CompactBindingOpportunity(
            opportunity_id=item.opportunity_id,
            producer_operation_id=item.producer_operation_id,
            consumer_operation_id=item.consumer_operation_id,
            effective_binding_kind=item.effective_binding_kind,
            from_location=item.from_location,
            from_field=item.from_field,
            to_location=item.to_location,
            to_field=item.to_field,
            full_row_sha256=item.full_row_sha256,
            support_count=item.support_count,
            witness_flow_id=item.witness_flow_id,
        )
        for item in sorted(opportunities.opportunities, key=lambda item: item.opportunity_id)
    )
    observed_value_flows = tuple(
        {
            "flow_id": item.flow_id,
            "producer_operation_id": item.producer_operation_id,
            "consumer_operation_id": item.consumer_operation_id,
            "producer_request_ref": item.producer_request_ref,
            "consumer_request_ref": item.consumer_request_ref,
            "producer_actor_id": item.producer_actor_id,
            "consumer_actor_id": item.consumer_actor_id,
            "producer_session_run_id": item.producer_session_run_id,
            "consumer_session_run_id": item.consumer_session_run_id,
            "from_location": item.from_location,
            "from_field": item.from_field,
            "to_location": item.to_location,
            "to_field": item.to_field,
        }
        for item in sorted(value_flows.flows, key=lambda item: item.flow_id)
    )
    evidence_channel_summaries = {
        key: _evidence_channel_summary(key, value)
        for key, value in sorted(evidence.channels.items())
    }
    if flat and "ui_diff" in evidence_channel_summaries:
        # page-change rows are withheld from the provider in the flat baseline
        # (the view's evidence_organization field records the withholding)
        withheld = copy.deepcopy(evidence_channel_summaries["ui_diff"])
        projection = withheld.get("semantic_projection")
        if isinstance(projection, dict):
            projection["omitted_count"] = int(projection.get("total_count", 0))
            projection["visible_count"] = 0
            projection["rows"] = []
            projection["projection_sha256"] = canonical_sha256(
                {key: value for key, value in projection.items() if key != "projection_sha256"}
            )
        evidence_channel_summaries["ui_diff"] = withheld
    dependency_rows = tuple({
        "edge_id": item.edge_id,
        "producer_operation_id": item.producer_operation_id,
        "consumer_operation_id": item.consumer_operation_id,
        "kind": item.kind,
        "evidence_channel_count": item.evidence_channel_count,
        "observed_flow_count": item.observed_flow_count,
        "deterministic_heuristic_score": item.deterministic_heuristic_score,
        "score_semantics": item.score_semantics,
        "full_row_sha256": item.stage4_edge_sha256,
    } for item in graph.edges)
    evidence_cards = _build_evidence_cards(
        compact_trace["api_requests"],
        request_setup_domains,
        available_setup_domains,
        evidence_channel_summaries,
        observed_value_flows,
        dependency_rows,
        compact_bindings,
        negative_request_facts,
        organization=organization,
    )
    if temporal_only:
        # the provider-visible view carries no explicit association structure;
        # the package (and every hash of it) still records what was mined
        observed_value_flows, dependency_rows, compact_bindings = (), (), ()
    view = ProposalEvidenceView(
        view_id=view_id,
        package_sha256=package.canonical_sha256(),
        observed_api_catalog_sha256=catalog.canonical_sha256(),
        observed_value_flow_set_sha256=value_flows.canonical_sha256(),
        dependency_graph_sha256=graph.canonical_sha256(),
        binding_opportunity_set_sha256=opportunities.canonical_sha256(),
        trace_summary={
            "events": trace.event_count,
            "admitted_requests": trace.admitted_request_count,
            "automatic_bindings": trace.automatic_binding_count,
            "review_required": trace.review_required_count,
        },
        ui_actions=compact_trace["ui_actions"],
        api_requests=compact_trace["api_requests"],
        automatic_bindings=tuple(_hashed_row(item) for item in trace.trace["bindings"]),
        binding_reviews=tuple(_hashed_row(item) for item in trace.trace["binding_reviews"]),
        evidence_cards=evidence_cards,
        proposal_target_card_ids=tuple(card.card_id for card in evidence_cards),
        relation_language=current_executable_relation_language(),
        evidence_channel_summaries=evidence_channel_summaries,
        setup_action_catalog=setup_action_catalog,
        request_setup_domains=request_setup_domains,
        setup_selection_clues=setup_selection_clues,
        transition_facts=transition_facts,
        negative_request_facts=negative_request_facts,
        api_operations=tuple({
            "operation_id": item.operation_id,
            "method": item.method,
            "canonical_path": item.canonical_path,
            "readiness": item.readiness,
            "observation_count": len(item.observation_refs),
            "stage1_request_refs": tuple(
                str(observation["request_ref"])
                for observation in item.observation_refs
                if observation.get("source") == "stage1_session"
            ),
            "probe_observation_count": sum(
                observation.get("source") == "stage2_5_probe"
                for observation in item.observation_refs
            ),
            "full_row_sha256": canonical_sha256(item.model_dump(mode="json")),
        } for item in catalog.operations),
        discovery_audit_summary={
            "planned_count": discovery_audit.planned_count,
            "executed_count": discovery_audit.executed_count,
            "admitted_count": discovery_audit.admitted_count,
            "rejected_count": discovery_audit.rejected_count,
            "not_executed_count": discovery_audit.not_executed_count,
            "kind_counts": discovery_audit.kind_counts,
            "records_sha256": discovery_audit.records_sha256,
            "not_executed_semantics": "audit_plan_non_evidence",
        },
        channel_availability={key: value.status for key, value in evidence.channels.items()},
        request_setup_eligibility_summary={
            "universe": applicability.universe_count,
            "available": applicability.available_count,
            "unsupported": applicability.unsupported_count,
        },
        observed_value_flows=observed_value_flows,
        dependency_edges=dependency_rows,
        binding_opportunities=compact_bindings,
        value_flow_occurrence_count=0 if temporal_only else value_flows.occurrence_count,
        evidence_organization=organization,
        source_refs=(package.canonical_sha256(),),
        source_sha256={"preproposal_evidence_package": package.canonical_sha256(), **expected},
    )
    _reject_provider_structural_bias(view.model_dump(mode="json"))
    return view

def _build_evidence_cards(
    api_requests: tuple[dict[str, Any], ...],
    request_setup_domains: Mapping[str, Any],
    complete_setup_domains: Mapping[str, Any],
    evidence_channel_summaries: Mapping[str, Mapping[str, Any]],
    observed_value_flows: tuple[dict[str, Any], ...],
    dependency_edges: tuple[dict[str, Any], ...],
    binding_opportunities: tuple[CompactBindingOpportunity, ...],
    negative_request_facts: tuple[NegativeRequestFact, ...] = (),
    organization: str = "association",
) -> tuple[EvidenceCard, ...]:
    """Build atomic M2 cards plus protocol-neutral mechanical neighborhoods.

    ``organization="temporal"`` (RQ3 ablation) keeps the same atomic cards but
    drops every association-derived incident reference (value flows,
    dependency edges, binding opportunities) and builds each neighborhood from
    the root card and the temporal window only, never from recorded relations.
    """

    flat = organization == "flat"
    temporal_only = organization in {"temporal", "flat"}
    requests = {str(row["request_ref"]): row for row in api_requests}
    ui_diff_rows = () if flat else tuple(
        evidence_channel_summaries
        .get("ui_diff", {})
        .get("semantic_projection", {})
        .get("rows", ())
    )
    flow_by_id = {str(row["flow_id"]): row for row in observed_value_flows}

    def incident_refs(request_refs: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
        ref_set = set(request_refs)
        operation_ids = {
            str(requests[ref]["operation_id"]) for ref in request_refs
        }
        ui_diffs = tuple(sorted(
            str(row["record_id"])
            for row in ui_diff_rows
            if ref_set & set(row.get("preceding_request_refs", ()))
            or ref_set & set(row.get("following_request_refs", ()))
        ))
        flows = tuple(sorted(
            flow_id
            for flow_id, row in flow_by_id.items()
            if row["producer_request_ref"] in ref_set
            or row["consumer_request_ref"] in ref_set
        ))
        edges = tuple(sorted(
            str(row["edge_id"])
            for row in dependency_edges
            if str(row["producer_operation_id"]) in operation_ids
            or str(row["consumer_operation_id"]) in operation_ids
        ))
        bindings = tuple(sorted(
            item.opportunity_id
            for item in binding_opportunities
            if item.producer_operation_id in operation_ids
            or item.consumer_operation_id in operation_ids
        ))
        negative_facts = tuple(sorted(
            fact.fact_id
            for fact in negative_request_facts
            if {
                fact.setup_request_ref,
                fact.negative_request_ref,
                fact.projection.before_request_ref,
                fact.projection.after_request_ref,
            } <= ref_set
        ))
        if temporal_only:
            flows, edges, bindings = (), (), ()
        return {
            "ui_diff_record_ids": ui_diffs,
            "value_flow_ids": flows,
            "dependency_edge_ids": edges,
            "binding_opportunity_ids": bindings,
            "negative_request_fact_ids": negative_facts,
        }

    def make_card(
        *,
        card_kind: str,
        request_refs: tuple[str, ...],
        component_card_ids: tuple[str, ...] = (),
        root_request_ref: str | None = None,
        neighborhood_summary: dict[str, Any] | None = None,
    ) -> EvidenceCard:
        ordered_refs = tuple(sorted(
            request_refs,
            key=lambda ref: (int(requests[ref]["global_order"]), ref),
        ))
        action_ids = tuple(sorted({
            str(requests[ref]["action_event_id"])
            for ref in ordered_refs
            if requests[ref].get("action_event_id") is not None
        }))
        group_ids = tuple(sorted({
            str(requests[ref]["request_group_id"])
            for ref in ordered_refs
            if requests[ref].get("request_group_id") is not None
        }))
        incident = incident_refs(ordered_refs)
        negative_fact_ids = incident.pop("negative_request_fact_ids")
        payload = {
            "card_kind": card_kind,
            "component_card_ids": list(sorted(component_card_ids)),
            "request_refs": list(ordered_refs),
            "actor_ids": list(sorted({
                str(requests[ref]["actor_id"]) for ref in ordered_refs
            })),
            "session_run_ids": list(sorted({
                str(requests[ref]["session_run_id"]) for ref in ordered_refs
            })),
            "action_event_ids": list(action_ids),
            "request_group_ids": list(group_ids),
            "anchor_request_refs": list(
                ref for ref in ordered_refs if requests[ref].get("is_anchor")
            ),
            "setup_domain_refs": list(ordered_refs),
            **{
                key: list(value)
                for key, value in incident.items()
            },
            "root_request_ref": root_request_ref,
            "neighborhood_summary": neighborhood_summary,
            "alias_scope": "proposal_view_first_occurrence_v1",
        }
        if negative_fact_ids:
            payload["negative_request_fact_ids"] = list(negative_fact_ids)
        return EvidenceCard(
            card_id=f"evidence-card-{canonical_sha256(payload)[:24]}",
            **payload,
        )

    grouped: dict[tuple[str, str], list[str]] = {}
    unassigned: list[str] = []
    for request in sorted(
        api_requests, key=lambda row: (int(row["global_order"]), str(row["request_ref"]))
    ):
        request_ref = str(request["request_ref"])
        group_id = request.get("request_group_id")
        action_id = request.get("action_event_id")
        if group_id is None or action_id is None:
            unassigned.append(request_ref)
        elif flat:
            # no UI-action grouping: every request is its own card
            grouped.setdefault((str(group_id), str(action_id), request_ref), []).append(request_ref)
        else:
            grouped.setdefault((str(group_id), str(action_id)), []).append(request_ref)

    atomic: list[EvidenceCard] = [
        make_card(card_kind="action_episode", request_refs=tuple(refs))
        for _key, refs in sorted(grouped.items())
    ]
    atomic.extend(
        make_card(card_kind="unassigned_request", request_refs=(request_ref,))
        for request_ref in unassigned
    )
    atomic_by_request = {
        request_ref: card
        for card in atomic
        for request_ref in card.request_refs
    }
    atomic_by_id = {card.card_id: card for card in atomic}

    def card_order(card: EvidenceCard) -> tuple[int, str]:
        return min(int(requests[ref]["global_order"]) for ref in card.request_refs), card.card_id

    def close_to_atomic_cards(refs: set[str]) -> set[str]:
        return {
            atomic_by_request[ref].card_id
            for ref in refs
            if ref in atomic_by_request
        }

    requests_by_operation: dict[str, set[str]] = {}
    requests_by_action: dict[str, set[str]] = {}
    for ref, row in requests.items():
        requests_by_operation.setdefault(str(row["operation_id"]), set()).add(ref)
        action_id = row.get("action_event_id")
        if action_id is not None:
            requests_by_action.setdefault(str(action_id), set()).add(ref)

    neighborhoods: list[EvidenceCard] = []
    for root_ref, domain in (() if flat else sorted(request_setup_domains.items())):
        if domain.get("status") != "available" or root_ref not in atomic_by_request:
            continue
        root = requests[root_ref]
        root_order = int(root["global_order"])
        root_card = atomic_by_request[root_ref]
        relation_refs = set(root_card.request_refs)
        temporal_refs = {
            ref
            for ref, row in requests.items()
            if abs(int(row["global_order"]) - root_order)
            <= MECHANICAL_NEIGHBORHOOD_ORDER_RADIUS
        }
        for row in (() if temporal_only else ui_diff_rows):
            incident = {
                *(str(ref) for ref in row.get("preceding_request_refs", ())),
                *(str(ref) for ref in row.get("following_request_refs", ())),
            }
            if root_ref in incident:
                relation_refs.update(incident & set(requests))
        for row in (() if temporal_only else observed_value_flows):
            pair = {
                str(row["producer_request_ref"]),
                str(row["consumer_request_ref"]),
            }
            if root_ref in pair:
                relation_refs.update(pair & set(requests))

        root_operation = str(root["operation_id"])
        if not temporal_only:
            relation_refs.update(requests_by_operation[root_operation])
        for edge in (() if temporal_only else dependency_edges):
            producer_operation = str(edge["producer_operation_id"])
            consumer_operation = str(edge["consumer_operation_id"])
            if root_operation == producer_operation:
                relation_refs.update(requests_by_operation.get(consumer_operation, ()))
            if root_operation == consumer_operation:
                relation_refs.update(requests_by_operation.get(producer_operation, ()))

        complete_domain = complete_setup_domains.get(root_ref) or {}
        for action_id in (() if temporal_only else complete_domain.get("eligible_setup_action_ids", ())):
            relation_refs.update(requests_by_action.get(str(action_id), ()))

        relation_card_ids = close_to_atomic_cards(relation_refs)
        temporal_card_ids = close_to_atomic_cards(temporal_refs) - relation_card_ids
        ordered_card_ids = [root_card.card_id]
        ordered_card_ids.extend(
            card.card_id
            for card in sorted(
                (atomic_by_id[item] for item in relation_card_ids - {root_card.card_id}),
                key=card_order,
            )
        )
        ordered_card_ids.extend(
            card.card_id
            for card in sorted(
                (atomic_by_id[item] for item in temporal_card_ids),
                key=card_order,
            )
        )
        all_component_refs = {
            ref
            for card_id in ordered_card_ids
            for ref in atomic_by_id[card_id].request_refs
        }
        visible_card_ids: list[str] = []
        visible_refs: set[str] = set()
        for card_id in ordered_card_ids:
            card_refs = set(atomic_by_id[card_id].request_refs)
            if len(visible_refs | card_refs) > MECHANICAL_NEIGHBORHOOD_MAX_REQUESTS:
                continue
            visible_card_ids.append(card_id)
            visible_refs.update(card_refs)
        if len(visible_card_ids) < 2:
            continue
        outside_radius = {
            ref
            for ref in relation_refs
            if ref in requests
            and abs(int(requests[ref]["global_order"]) - root_order)
            > MECHANICAL_NEIGHBORHOOD_ORDER_RADIUS
        }
        summary = {
            "relation_scope": "temporal_window_only_v1" if temporal_only else "one_hop_recording_facts_v1",
            "temporal_radius": MECHANICAL_NEIGHBORHOOD_ORDER_RADIUS,
            "max_requests": MECHANICAL_NEIGHBORHOOD_MAX_REQUESTS,
            "total_request_count": len(all_component_refs),
            "visible_request_count": len(visible_refs),
            "omitted_request_count": len(all_component_refs - visible_refs),
            "outside_temporal_radius_related_request_count": len(outside_radius),
        }
        neighborhoods.append(make_card(
            card_kind="mechanical_neighborhood",
            request_refs=tuple(visible_refs),
            component_card_ids=tuple(sorted(visible_card_ids)),
            root_request_ref=root_ref,
            neighborhood_summary=summary,
        ))

    cards = {card.card_id: card for card in (*atomic, *neighborhoods)}
    return tuple(cards[key] for key in sorted(cards))


_PROVIDER_FORBIDDEN_STRUCTURE = {
    "shape_kind",
    "protocol_kind",
    "observation_opportunity_ref",
    "causal_two_arm",
    "lifecycle_workflow",
    "actor_matrix",
    "metamorphic_query",
    "control",
    "treatment",
    "workflow_plan",
    "actor_plan",
    "query_plan",
    "allowed_assertions",
    "candidate_menu",
    "producer_request_refs",
    "consumer_request_refs",
    "producer_anchor",
    "producer_applicability_summary",
}


def _reject_provider_structural_bias(value: Any) -> None:
    """Reject forbidden protocol vocabulary in keys and structural enum labels only."""

    def walk(item: Any, parent_key: str | None = None) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if str(key) in _PROVIDER_FORBIDDEN_STRUCTURE:
                    raise ValueError(f"provider-visible forbidden structural key: {key}")
                walk(child, str(key))
        elif isinstance(item, (list, tuple)):
            for child in item:
                walk(child, parent_key)
        elif (
            isinstance(item, str)
            and parent_key in {
                "artifact_type", "card_kind", "proposal_round", "source_kind",
                "association_status", "status", "kind", "role", "type",
            }
            and item in _PROVIDER_FORBIDDEN_STRUCTURE
        ):
            raise ValueError(
                f"provider-visible forbidden structural enum: {item}"
            )

    walk(value)


def render_preproposal_candidate_input(
    package: PreProposalEvidencePackage,
    view: ProposalEvidenceView,
    *,
    input_id: str,
    template: str,
    template_sha256: str,
) -> RenderedCandidateInput:
    if view.package_sha256 != package.canonical_sha256():
        raise ValueError("rendered input view does not reference the supplied package")
    if hashlib.sha256(template.encode("utf-8")).hexdigest() != template_sha256:
        raise ValueError("candidate input template hash mismatch")
    placeholder = PROPOSAL_EVIDENCE_PLACEHOLDER
    if placeholder not in template:
        raise ValueError("candidate input template lacks the canonical evidence placeholder")
    _reject_provider_structural_bias(view.model_dump(mode="json"))
    rendered = template.replace(
        placeholder,
        json.dumps(
            view.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    return RenderedCandidateInput(
        input_id=input_id,
        package_sha256=package.canonical_sha256(),
        view_sha256=view.canonical_sha256(),
        template_sha256=template_sha256,
        rendered_text=rendered,
        rendered_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        source_refs=(
            package.canonical_sha256(),
            view.canonical_sha256(),
            f"candidate-input-template:sha256:{template_sha256}",
        ),
        source_sha256={
            "preproposal_evidence_package": package.canonical_sha256(),
            "proposal_evidence_view": view.canonical_sha256(),
            "candidate_input_template": template_sha256,
        },
    )


def build_preproposal_mainline(
    recording: RecordingBundle,
    trace: UiApiTrace,
    structure: ObservationalApiStructure,
    products: Mapping[str, Any],
    evidence: EvidenceBundle,
    applicability: ProducerApplicability,
    *,
    recording_root: str | Path,
    run_id: str,
    forbidden_inputs: Mapping[str, Any] | None = None,
    organization: str = "association",
) -> PreProposalArtifacts:
    if any(value is None for value in (recording, trace, structure, products, evidence, applicability)):
        raise ValueError("pre-proposal mainline cannot fall back from a missing required trunk")
    _reject_forbidden_inputs(forbidden_inputs)
    _validated_products(structure, products)
    catalog = build_observed_api_catalog(
        structure, products, trace, catalog_id=f"{run_id}-observed-api-catalog"
    )
    discovery_audit = build_discovery_candidate_audit(
        structure, products, audit_id=f"{run_id}-discovery-audit"
    )
    value_flows = build_observed_value_flows(
        structure,
        products,
        recording,
        trace,
        recording_root=recording_root,
        flow_set_id=f"{run_id}-observed-value-flows",
    )
    graph, raw_graph = build_observed_dependency_graph(
        structure,
        products,
        recording,
        catalog,
        value_flows,
        recording_root=recording_root,
        graph_id=f"{run_id}-dependency-graph",
    )
    opportunities = build_binding_opportunity_set(
        products,
        raw_graph,
        graph,
        value_flows,
        opportunity_set_id=f"{run_id}-binding-opportunities",
    )
    package = build_preproposal_evidence_package(
        recording,
        trace,
        structure,
        catalog,
        discovery_audit,
        evidence,
        applicability,
        value_flows,
        graph,
        opportunities,
        package_id=f"{run_id}-preproposal-package",
        forbidden_inputs=forbidden_inputs,
    )
    view = build_proposal_evidence_view(
        package,
        recording,
        trace,
        catalog,
        discovery_audit,
        evidence,
        applicability,
        value_flows,
        graph,
        opportunities,
        recording_root=recording_root,
        view_id=f"{run_id}-proposal-evidence-view",
        organization=organization,
    )
    rendered = render_preproposal_candidate_input(
        package,
        view,
        input_id=f"{run_id}-rendered-candidate-input",
        template=canonical_v2_template_text(),
        template_sha256=canonical_v2_template_sha256(),
    )
    return PreProposalArtifacts(
        catalog=catalog,
        discovery_audit=discovery_audit,
        value_flows=value_flows,
        dependency_graph=graph,
        binding_opportunities=opportunities,
        package=package,
        view=view,
        rendered_input=rendered,
        raw_dependency_graph=raw_graph,
    )


def _recording_entries_by_request(
    recording: RecordingBundle,
    trace: UiApiTrace,
    recording_root: str | Path,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    paths = resolve_recording_bundle_paths(recording, recording_root)
    bundles = {
        item.run_id: load_bundle(paths[item.actor_id]) for item in recording.actors
    }
    entries: dict[str, Mapping[str, Any]] = {}
    graphql_kinds: dict[str, str] = {}
    for row in trace.trace["api_requests"]:
        request_ref = str(row["request_ref"])
        observation = row["observation_ref"]
        run_id = str(observation["run_id"])
        entry_index = int(observation["entry_index"])
        bundle = bundles.get(run_id)
        if bundle is None or entry_index < 0 or entry_index >= len(bundle.entries):
            raise ValueError(f"recording entry cannot resolve request: {request_ref}")
        entries[request_ref] = bundle.entries[entry_index]
        if row.get("graphql_operation_kind") is not None:
            graphql_kinds[request_ref] = str(row["graphql_operation_kind"])
    return entries, graphql_kinds


def _build_typed_transition_facts(
    recording: RecordingBundle,
    trace: UiApiTrace,
    *,
    recording_root: str | Path,
    api_requests: tuple[dict[str, Any], ...],
    value_flows: ObservedValueFlowSet,
    dependency_edges: tuple[Mapping[str, Any], ...] = (),
) -> tuple[TypedTransitionFact, ...]:
    """Project neutral comparable-read transitions for detail proposals only."""

    entries, graphql_kinds = _recording_entries_by_request(
        recording, trace, recording_root
    )
    request_rows = {str(row["request_ref"]): row for row in api_requests}
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in api_requests:
        request_ref = str(row["request_ref"])
        method = str(row.get("method") or "").upper()
        is_read = (
            method in _SETUP_CLUE_READ_METHODS
            or (method == "POST" and graphql_kinds.get(request_ref) == "query")
            or row.get("declared_read_semantic") is True
        )
        status = row.get("response_status")
        body = _response_json(entries[request_ref])
        if (
            not is_read
            or not isinstance(status, int)
            or not 200 <= status < 300
            or body is None
        ):
            continue
        snapshot = _selector_snapshot_sha256(row)
        groups.setdefault(
            (
                str(row["actor_id"]),
                str(row["session_run_id"]),
                str(row["operation_id"]),
                snapshot,
            ),
            [],
        ).append(
            {
                "request_ref": request_ref,
                "global_order": int(row["global_order"]),
                "body": body,
            }
        )
    for rows in groups.values():
        rows.sort(key=lambda item: (item["global_order"], item["request_ref"]))

    facts: dict[str, TypedTransitionFact] = {}

    def add_fact(payload: dict[str, Any]) -> None:
        competition = TransitionWriteCompetition.model_validate(
            _transition_write_competition(
                payload,
                request_rows=request_rows,
                entries=entries,
                value_flows=value_flows,
                dependency_edges=dependency_edges,
            ),
            strict=True,
        )
        model_payload = {**payload, "write_competition": competition}
        hash_payload = {
            **payload,
            "write_competition": competition.model_dump(mode="json"),
        }
        fact_id = f"transition-fact-{canonical_sha256(hash_payload)[:24]}"
        fact = TypedTransitionFact.model_validate(
            {"fact_id": fact_id, **model_payload}, strict=True
        )
        facts[fact.fact_id] = fact

    for (actor_id, session_run_id, operation_id, snapshot), rows in groups.items():
        for before, after in zip(rows, rows[1:]):
            before_scalars = dict(_scalar_fields(before["body"]))
            after_scalars = dict(_scalar_fields(after["body"]))
            common = {
                path: (value, after_scalars[path])
                for path, value in before_scalars.items()
                if path in after_scalars
            }
            resource_identity = {
                "kind": "resource",
                "path": "$request.selector_snapshot_sha256",
                "json_type": "string",
                "value_ref": _scalar_value_ref(snapshot),
            }
            common_payload = {
                "before_request_ref": before["request_ref"],
                "after_request_ref": after["request_ref"],
                "actor_id": actor_id,
                "session_run_id": session_run_id,
                "operation_id": operation_id,
                "selector_snapshot_sha256": snapshot,
            }
            for path, (before_value, after_value) in sorted(common.items()):
                if not _transition_scalar_path_allowed(path):
                    continue
                if type(before_value) is not type(after_value) or before_value == after_value:
                    continue
                if type(before_value) not in {bool, int, float}:
                    continue
                if isinstance(before_value, float) and not (
                    math.isfinite(before_value) and math.isfinite(after_value)
                ):
                    continue
                value_type = _json_type(before_value)
                add_fact(
                    {
                        **common_payload,
                        "observation_kind": "scalar",
                        "target_path": path,
                        "value_type": value_type,
                        "before_value": before_value,
                        "after_value": after_value,
                        "signed_delta": (
                            after_value - before_value
                            if value_type in {"integer", "number"}
                            else None
                        ),
                        "identity": resource_identity,
                    }
                )

            before_collections = _collections_by_path(before["body"])
            after_collections = _collections_by_path(after["body"])
            for path in sorted(set(before_collections) & set(after_collections)):
                before_collection = before_collections[path]
                after_collection = after_collections[path]
                if len(before_collection) != len(after_collection):
                    add_fact(
                        {
                            **common_payload,
                            "observation_kind": "collection_count",
                            "target_path": path,
                            "value_type": "integer",
                            "before_value": len(before_collection),
                            "after_value": len(after_collection),
                            "signed_delta": len(after_collection)
                            - len(before_collection),
                            "identity": {
                                "kind": "collection",
                                "collection_path": path,
                            },
                        }
                    )
                locator_witnesses = _value_flow_backed_member_locators(
                    before=before,
                    after=after,
                    collection_path=path,
                    before_collection=before_collection,
                    after_collection=after_collection,
                    entries=entries,
                    request_rows=request_rows,
                    value_flows=value_flows,
                )
                for locator in locator_witnesses:
                    identity = {
                        "kind": "collection_member",
                        "collection_path": path,
                        "member_path": locator["member_path"],
                        "json_type": locator["json_type"],
                        "value_ref": locator["value_ref"],
                    }
                    witness = locator["locator_witness"]
                    before_member = locator["before_member"]
                    after_member = locator["after_member"]
                    if before_member is not None and after_member is not None:
                        before_fields = dict(_scalar_fields(before_member))
                        after_fields = dict(_scalar_fields(after_member))
                        for member_path in sorted(set(before_fields) & set(after_fields)):
                            before_value = before_fields[member_path]
                            after_value = after_fields[member_path]
                            if (
                                not _transition_member_field_path_allowed(member_path)
                                or type(before_value) is not type(after_value)
                                or before_value == after_value
                                or type(before_value) not in {bool, int, float}
                                or (
                                    isinstance(before_value, float)
                                    and not (
                                        math.isfinite(before_value)
                                        and math.isfinite(after_value)
                                    )
                                )
                            ):
                                continue
                            value_type = _json_type(before_value)
                            add_fact(
                                {
                                    **common_payload,
                                    "observation_kind": "scalar",
                                    "target_path": member_path,
                                    "value_type": value_type,
                                    "before_value": before_value,
                                    "after_value": after_value,
                                    "signed_delta": (
                                        after_value - before_value
                                        if value_type in {"integer", "number"}
                                        else None
                                    ),
                                    "identity": identity,
                                    "locator_witness": witness,
                                }
                            )
                    was_present = before_member is not None
                    is_present = after_member is not None
                    if was_present == is_present:
                        continue
                    add_fact(
                        {
                            **common_payload,
                            "observation_kind": "collection_member",
                            "target_path": path,
                            "value_type": "boolean",
                            "before_value": was_present,
                            "after_value": is_present,
                            "signed_delta": int(is_present) - int(was_present),
                            "identity": identity,
                            "locator_witness": witness,
                        }
                    )
    return tuple(facts[ref] for ref in sorted(facts))


def _build_negative_request_facts(
    recording: RecordingBundle,
    trace: UiApiTrace,
    *,
    recording_root: str | Path,
    api_requests: tuple[dict[str, Any], ...],
    ui_actions: tuple[dict[str, Any], ...],
) -> tuple[NegativeRequestFact, ...]:
    """Freeze fully observed duplicate-input rejection windows."""

    entries, _graphql_kinds = _recording_entries_by_request(
        recording, trace, recording_root
    )
    actions = {str(row["event_id"]): row for row in ui_actions}
    action_order = {
        event_id: int(row["global_order"]) for event_id, row in actions.items()
    }
    facts: dict[str, NegativeRequestFact] = {}

    for negative in api_requests:
        negative_ref = str(negative["request_ref"])
        negative_status = negative.get("response_status")
        negative_action = negative.get("action_event_id")
        if (
            not isinstance(negative_status, int)
            or not 400 <= negative_status < 500
            or not _recorded_write_request(negative)
            or not isinstance(negative_action, str)
            or negative_action not in action_order
        ):
            continue
        negative_body = _request_json(entries[negative_ref])
        if not isinstance(negative_body, dict):
            continue
        error_paths = tuple(sorted(
            str(row["path"])
            for row in negative["response_body_shape"].get("shape_rows", ())
            if "error" in _json_path_tail(str(row.get("path") or "")).casefold()
        ))
        if not error_paths:
            continue

        sources: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for source in api_requests:
            source_ref = str(source["request_ref"])
            source_status = source.get("response_status")
            if not (
                isinstance(source_status, int)
                and 200 <= source_status < 300
                and _recorded_write_request(source)
                and source["actor_id"] == negative["actor_id"]
                and source["session_run_id"] == negative["session_run_id"]
                and source["operation_id"] == negative["operation_id"]
                and int(source["global_order"]) < int(negative["global_order"])
            ):
                continue
            source_body = _request_json(entries[source_ref])
            if not isinstance(source_body, dict):
                continue
            duplicates = [
                {
                    "source_path": source_path,
                    "target_path": target_path,
                    "value_type": _json_type(source_value),
                    "comparison": "strict_json_scalar_equal_value_not_persisted",
                }
                for source_path, source_value in _scalar_fields(source_body)
                for target_path, target_value in _scalar_fields(negative_body)
                if source_path == target_path
                and sensitive_field_category(_json_path_tail(source_path)) is None
                and _same_json_scalar(source_value, target_value)
            ]
            if len(duplicates) == 1:
                sources.append((source, duplicates[0]))
        if not sources:
            continue
        source, duplicate = max(
            sources,
            key=lambda row: (
                int(row[0]["global_order"]), str(row[0]["request_ref"])
            ),
        )
        source_action = source.get("action_event_id")
        if not isinstance(source_action, str) or source_action not in action_order:
            continue
        boundary_events = [
            event_id
            for event_id, row in actions.items()
            if row.get("actor_id") == negative["actor_id"]
            and action_order[source_action]
            < action_order[event_id]
            < action_order[negative_action]
            and _recorded_logout_action(row)
        ]
        if len(boundary_events) > 1:
            continue
        context_mode = "auth_absent" if boundary_events else "auth_preserved"
        boundary_event_id = boundary_events[0] if boundary_events else source_action

        before_rows = [
            row for row in api_requests
            if _successful_recorded_read(row)
            and row["actor_id"] == negative["actor_id"]
            and row["session_run_id"] == negative["session_run_id"]
            and int(source["global_order"])
            < int(row["global_order"])
            < int(negative["global_order"])
        ]
        after_rows = [
            row for row in api_requests
            if _successful_recorded_read(row)
            and row["actor_id"] == negative["actor_id"]
            and row["session_run_id"] == negative["session_run_id"]
            and int(row["global_order"]) > int(negative["global_order"])
        ]
        pairs: list[tuple[dict[str, Any], dict[str, Any], str, str]] = []
        for before in before_rows:
            before_ref = str(before["request_ref"])
            before_target = _recorded_request_target(entries[before_ref])
            before_response = _response_json(entries[before_ref])
            for after in after_rows:
                after_ref = str(after["request_ref"])
                after_response = _response_json(entries[after_ref])
                if not (
                    before["operation_id"] == after["operation_id"]
                    and before_target == _recorded_request_target(entries[after_ref])
                    and isinstance(before_response, dict)
                    and isinstance(after_response, dict)
                ):
                    continue
                before_shape = _compact_shape_path_types(
                    before["response_body_shape"]
                )
                after_shape = _compact_shape_path_types(
                    after["response_body_shape"]
                )
                common = [
                    path
                    for path, value_type in before_shape.items()
                    if path.count(".") == 1
                    and value_type == "object"
                    and after_shape.get(path) == value_type
                ]
                equal = [
                    path for path in common
                    if canonical_sha256(get_path(before_response, path))
                    == canonical_sha256(get_path(after_response, path))
                ]
                if len(equal) == 1:
                    pairs.append((before, after, equal[0], "object"))
        if not pairs:
            catalog_rows = []
            for before in before_rows:
                response = _response_json(entries[str(before["request_ref"])])
                shape = _compact_shape_path_types(before["response_body_shape"])
                projections = [
                    path for path, value_type in shape.items()
                    if path.count(".") == 1
                    and value_type == "object"
                    and isinstance(get_path(response, path), dict)
                ]
                if len(projections) == 1:
                    catalog_rows.append((before, projections[0]))
            if len(catalog_rows) == 1:
                observer, projection_path = catalog_rows[0]
                pairs.append((observer, observer, projection_path, "object"))
            else:
                continue
        before, after, projection_path, projection_type = min(
            pairs,
            key=lambda row: (
                int(negative["global_order"]) - int(row[0]["global_order"]),
                int(row[1]["global_order"]) - int(negative["global_order"]),
                str(row[0]["request_ref"]),
                str(row[1]["request_ref"]),
            ),
        )
        projection_payload = {
            "before_request_ref": str(before["request_ref"]),
            "after_request_ref": str(after["request_ref"]),
            "operation_id": str(before["operation_id"]),
            "resource_identity": (
                "exact_recorded_request_target_equal_value_not_persisted"
            ),
            "path": projection_path,
            "value_type": projection_type,
            "normalization": (
                "typed_canonical_json_object_keys_array_order_preserved_no_coercion"
            ),
            "excluded_paths": (),
        }
        projection_hash_payload = {**projection_payload, "excluded_paths": []}
        projection = FrozenBusinessProjection(
            projection_ref=(
                f"state-projection-{canonical_sha256(projection_hash_payload)[:24]}"
            ),
            **projection_payload,
        )
        fact_payload = {
            "actor_id": str(negative["actor_id"]),
            "session_run_id": str(negative["session_run_id"]),
            "setup_request_ref": str(source["request_ref"]),
            "negative_request_ref": negative_ref,
            "operation_id": str(negative["operation_id"]),
            "duplicate_input": duplicate,
            "rejection_detector": {
                "kind": "http_status_class",
                "expected_class": "client_error",
            },
            "response_status": negative_status,
            "error_response_paths": tuple(error_paths),
            "context_mode": context_mode,
            "session_boundary_event_id": boundary_event_id,
            "projection": projection,
        }
        fact_hash_payload = {
            **fact_payload,
            "error_response_paths": list(error_paths),
            "projection": projection.model_dump(mode="json"),
        }
        fact_hash_payload.pop("context_mode", None)
        fact = NegativeRequestFact(
            fact_id=(
                f"negative-request-fact-{canonical_sha256(fact_hash_payload)[:24]}"
            ),
            **fact_payload,
        )
        facts[fact.fact_id] = fact
    return tuple(facts[ref] for ref in sorted(facts))


def _recorded_write_request(row: Mapping[str, Any]) -> bool:
    return (
        str(row.get("method") or "").upper() not in _SETUP_CLUE_READ_METHODS
        and row.get("declared_read_semantic") is not True
    )


def _successful_recorded_read(row: Mapping[str, Any]) -> bool:
    status = row.get("response_status")
    return (
        (
            str(row.get("method") or "").upper() in _SETUP_CLUE_READ_METHODS
            or row.get("declared_read_semantic") is True
        )
        and isinstance(status, int)
        and 200 <= status < 300
    )


def _recorded_logout_action(row: Mapping[str, Any]) -> bool:
    visible = row.get("visible_element") or {}
    text = " ".join(
        str(value) for value in visible.values() if isinstance(value, str)
    )
    selector = str(row.get("selector") or "")
    return "logout" in f"{selector} {text}".casefold()


def _request_json(entry: Mapping[str, Any]) -> Any | None:
    raw = ((entry.get("request") or {}).get("postData") or {}).get("text")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _recorded_request_target(entry: Mapping[str, Any]) -> tuple[str, str]:
    parsed = urlsplit(str((entry.get("request") or {}).get("url") or ""))
    return parsed.path, parsed.query


def _compact_shape_path_types(shape: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(row["path"]): str(row["type"])
        for row in shape.get("shape_rows", ())
        if isinstance(row, Mapping)
        and isinstance(row.get("path"), str)
        and isinstance(row.get("type"), str)
    }


_TRANSITION_GENERIC_TOKENS = {
    "api",
    "count",
    "current",
    "data",
    "get",
    "item",
    "items",
    "list",
    "post",
    "put",
    "patch",
    "delete",
    "result",
    "results",
}


def _transition_semantic_tokens(value: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {
        token
        for token in re.findall(r"[a-z0-9]+", separated.casefold())
        if len(token) >= 4 and token not in _TRANSITION_GENERIC_TOKENS
    }


def _transition_tokens_related(left: set[str], right: set[str]) -> bool:
    return any(
        first == second
        or (
            min(len(first), len(second)) >= 5
            and (first.startswith(second) or second.startswith(first))
        )
        for first in left
        for second in right
    )


def _transition_path_segments(path: str) -> tuple[str, ...]:
    return tuple(
        segment
        for segment in path.strip("/").split("/")
        if segment and segment.casefold() != "api"
    )


def _transition_full_target_path(payload: Mapping[str, Any]) -> str:
    identity = payload["identity"]
    if identity["kind"] != "collection_member":
        return str(payload["target_path"])
    collection = str(identity["collection_path"])
    suffix = str(payload["target_path"])[1:]
    return f"{collection}[*]{suffix}"


def _transition_path_parent(path: str) -> str:
    normalized = re.sub(r"\[\d+\]", "[*]", path)
    return normalized.rsplit(".", 1)[0] if "." in normalized else "$"


def _transition_flow_value(flow: Any, field: str) -> Any:
    return flow.get(field) if isinstance(flow, Mapping) else getattr(flow, field)


def _transition_collection_membership_write(
    collection_base_path: str,
    write: Mapping[str, Any],
) -> bool:
    observer = _transition_path_segments(collection_base_path)
    candidate = _transition_path_segments(str(write.get("canonical_path") or ""))
    method = str(write.get("method") or "").upper()
    return (
        method == "POST" and candidate == observer
    ) or (
        method == "DELETE"
        and len(candidate) == len(observer) + 1
        and candidate[: len(observer)] == observer
    )


def _transition_collection_distinct_descendant(
    collection_base_path: str,
    write_path: str,
) -> bool:
    observer = _transition_path_segments(collection_base_path)
    candidate = _transition_path_segments(write_path)
    if candidate[: len(observer)] == observer:
        return len(candidate) > len(observer) + 1
    common = 0
    for left, right in zip(observer, candidate):
        if left != right:
            break
        common += 1
    return common >= 1 and common < min(len(observer), len(candidate))


def _transition_collection_base_path(
    observer_path: str,
    target_tokens: set[str],
) -> str:
    segments = _transition_path_segments(observer_path)
    matches = [
        index
        for index, segment in enumerate(segments)
        if _transition_tokens_related(
            target_tokens, _transition_semantic_tokens(segment)
        )
    ]
    if not matches:
        return observer_path
    return "/" + "/".join(segments[: matches[-1] + 1])


def _transition_identity_rows(member: Any) -> list[dict[str, Any]]:
    """Return stable, non-sensitive scalar identities unique within one member."""

    by_ref: dict[str, list[dict[str, Any]]] = {}
    for path, value in _scalar_fields(member):
        if (
            isinstance(value, bool)
            or type(value) not in {str, int}
            or not identity_like_json_path(path)
            or sensitive_field_category(_json_path_tail(path)) is not None
            or (isinstance(value, str) and (not value or "[REDACT" in value))
        ):
            continue
        value_ref = _scalar_value_ref(value)
        by_ref.setdefault(value_ref, []).append({
            "path": path,
            "value": value,
            "value_ref": value_ref,
            "value_type": _json_type(value),
        })
    return sorted(
        (rows[0] for rows in by_ref.values() if len(rows) == 1),
        key=lambda row: (row["path"], row["value_ref"]),
    )


def _transition_unique_changed_member(
    before_collection: list[Any],
    after_collection: list[Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Find one added or removed member using stable identity, never position."""

    if len(after_collection) > len(before_collection):
        changed, other, direction = after_collection, before_collection, "added"
    elif len(after_collection) < len(before_collection):
        changed, other, direction = before_collection, after_collection, "removed"
    else:
        return None, None
    candidates: list[dict[str, Any]] = []
    for member in changed:
        identities = [
            row
            for row in _transition_identity_rows(member)
            if _collection_identity_match_count(changed, row["path"], row["value"])
            == 1
            and _collection_identity_match_count(other, row["path"], row["value"])
            == 0
        ]
        if identities:
            candidates.append({"member": member, "identities": identities})
    if len(candidates) != 1:
        return None, direction
    return candidates[0], direction


def _transition_request_scalar_locations(
    entry: Mapping[str, Any], value: Any
) -> list[tuple[str, str]]:
    """Locate one strict scalar in a write path, query, or JSON body."""

    request = entry.get("request") or {}
    found: list[tuple[str, str]] = []
    raw_text = (request.get("postData") or {}).get("text")
    if isinstance(raw_text, str) and raw_text:
        try:
            body = json.loads(raw_text)
        except json.JSONDecodeError:
            body = None
        if body is not None:
            found.extend(
                ("body", path)
                for path, observed in _scalar_fields(body)
                if _same_json_scalar(observed, value)
                and sensitive_field_category(_json_path_tail(path)) is None
            )
    if isinstance(value, str):
        found.extend(
            ("query", f"$.{row['name']}")
            for row in request.get("queryString", ())
            if isinstance(row, Mapping)
            and isinstance(row.get("name"), str)
            and str(row.get("value") or "") == value
            and sensitive_field_category(str(row["name"])) is None
        )
        found.extend(
            ("path", f"segment[{index}]")
            for index, segment in enumerate(
                unquote(item)
                for item in urlsplit(str(request.get("url") or "")).path.split("/")
                if item
            )
            if segment == value and sensitive_field_category(segment) is None
        )
    return sorted(set(found))


def _transition_collection_path(
    payload: Mapping[str, Any], before_body: Any, after_body: Any
) -> str | None:
    identity = payload["identity"]
    if payload["observation_kind"] in {"collection_count", "collection_member"}:
        return str(identity["collection_path"])
    if not (
        str(payload["value_type"]) == "integer"
        and isinstance(before_body, Mapping)
        and isinstance(after_body, Mapping)
    ):
        return None
    target_tokens = _transition_semantic_tokens(str(payload["target_path"]))
    before_collections = _collections_by_path(before_body)
    after_collections = _collections_by_path(after_body)
    candidates = [
        path
        for path, collection in before_collections.items()
        if path in after_collections
        and _transition_tokens_related(
            target_tokens, _transition_semantic_tokens(path)
        )
        and len(collection) == payload["before_value"]
        and len(after_collections[path]) == payload["after_value"]
    ]
    return candidates[0] if len(candidates) == 1 else None


def _transition_identity_flow_groups(
    *,
    value: Any,
    request_ref: str,
    request_location: str,
    before_order: int,
    write_order: int,
    request_rows: Mapping[str, Mapping[str, Any]],
    entries: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet,
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    groups: dict[tuple[str, str], list[str]] = {}
    for flow in value_flows.flows:
        if (
            str(_transition_flow_value(flow, "consumer_request_ref")) != request_ref
            or _transition_flow_value(flow, "from_location") != "response_body"
            or str(_transition_flow_value(flow, "to_location")) != request_location
        ):
            continue
        producer_ref = str(_transition_flow_value(flow, "producer_request_ref"))
        producer = request_rows.get(producer_ref)
        if producer is not None and not (
            before_order <= int(producer["global_order"]) < write_order
        ):
            continue
        source_body = _response_json(entries.get(producer_ref, {}))
        if source_body is None:
            continue
        source_path = str(_transition_flow_value(flow, "from_field"))
        try:
            observed = _concrete_json_path_value(source_body, source_path)
        except (KeyError, TypeError, ValueError):
            continue
        if not _same_json_scalar(observed, value):
            continue
        key = (producer_ref, re.sub(r"\[\d+\]", "[*]", source_path))
        groups.setdefault(key, []).append(
            str(_transition_flow_value(flow, "flow_id"))
        )
    ordered_groups = tuple(sorted(groups))
    flow_ids = tuple(sorted({item for rows in groups.values() for item in rows}))
    return ordered_groups, flow_ids


def _transition_member_identity_state_evidence(
    payload: Mapping[str, Any],
    *,
    write: Mapping[str, Any],
    entry: Mapping[str, Any],
    before_body: Any,
    after_body: Any,
    before_order: int,
    request_rows: Mapping[str, Mapping[str, Any]],
    entries: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet,
) -> tuple[str, dict[str, Any] | None, tuple[str, ...]]:
    """Close a cross-endpoint collection change with identity and state facts."""

    collection_path = _transition_collection_path(payload, before_body, after_body)
    if collection_path is None:
        return "none", None, ()
    before_collections = _collections_by_path(before_body)
    after_collections = _collections_by_path(after_body)
    if collection_path not in before_collections or collection_path not in after_collections:
        return "none", None, ()
    changed, direction = _transition_unique_changed_member(
        before_collections[collection_path], after_collections[collection_path]
    )
    if direction is None:
        return "none", None, ()

    response = _response_json(entry)
    if response is None:
        return "none", None, ()
    operation_tokens = _transition_semantic_tokens(
        f"{write.get('operation_id') or ''} {write.get('canonical_path') or ''}"
    )
    expected_state = direction == "added"
    state_rows = [
        (path, value)
        for path, value in _scalar_fields(response)
        if type(value) is bool
        and value is expected_state
        and _transition_tokens_related(
            operation_tokens, _transition_semantic_tokens(path)
        )
    ]
    if not state_rows:
        return "none", None, ()
    if changed is None:
        return "ambiguous", None, ()

    candidates: list[dict[str, Any]] = []
    ambiguous = False
    request_ref = str(write["request_ref"])
    write_order = int(write["global_order"])
    response_scalars = list(_scalar_fields(response))
    for identity in changed["identities"]:
        response_value_paths = sorted({
            path
            for path, observed in response_scalars
            if _same_json_scalar(observed, identity["value"])
            and sensitive_field_category(_json_path_tail(path)) is None
        })
        request_locations = _transition_request_scalar_locations(
            entry, identity["value"]
        )
        if (
            len(response_value_paths) != 1
            or not identity_like_json_path(response_value_paths[0])
            or len(request_locations) != 1
        ):
            if response_value_paths and request_locations:
                ambiguous = True
            continue
        response_identity_path = response_value_paths[0]
        matching_states = sorted({
            path
            for path, _value in state_rows
            if _transition_path_parent(path)
            == _transition_path_parent(response_identity_path)
        })
        if len(matching_states) != 1:
            if matching_states:
                ambiguous = True
            continue
        request_location, request_path = request_locations[0]
        flow_groups, flow_ids = _transition_identity_flow_groups(
            value=identity["value"],
            request_ref=request_ref,
            request_location=request_location,
            before_order=before_order,
            write_order=write_order,
            request_rows=request_rows,
            entries=entries,
            value_flows=value_flows,
        )
        if len(flow_groups) > 1:
            ambiguous = True
            continue
        candidates.append({
            "value_ref": identity["value_ref"],
            "value_type": identity["value_type"],
            "member_path": identity["path"],
            "request_location": request_location,
            "request_path": request_path,
            "response_identity_path": response_identity_path,
            "response_state_path": matching_states[0],
            "response_state_value": expected_state,
            "transition_direction": direction,
            "flow_ids": flow_ids,
        })
    unique = {
        canonical_sha256({**row, "flow_ids": list(row["flow_ids"])}): row
        for row in candidates
    }
    if ambiguous or len(unique) > 1:
        return "ambiguous", None, ()
    if len(unique) != 1:
        return "none", None, ()
    evidence = next(iter(unique.values()))
    return "unique", evidence, tuple(evidence["flow_ids"])


def _transition_write_competition(
    payload: Mapping[str, Any],
    *,
    request_rows: Mapping[str, Mapping[str, Any]],
    entries: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet,
    dependency_edges: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Classify compact in-window writes without assigning transition cause."""

    before_ref = str(payload["before_request_ref"])
    after_ref = str(payload["after_request_ref"])
    before = request_rows[before_ref]
    after = request_rows[after_ref]
    before_order = int(before["global_order"])
    after_order = int(after["global_order"])
    target_tokens = _transition_semantic_tokens(str(payload["target_path"]))
    full_target_parent = _transition_path_parent(
        _transition_full_target_path(payload)
    )
    observer_path = str(before.get("canonical_path") or "")
    observation_kind = str(payload["observation_kind"])
    identity_kind = str(payload["identity"]["kind"])
    assessments: list[dict[str, Any]] = []
    before_body = _response_json(entries[before_ref])
    after_body = _response_json(entries[after_ref])
    mirrored_collection_count = False
    if (
        str(payload["value_type"]) == "integer"
        and isinstance(before_body, Mapping)
        and isinstance(after_body, Mapping)
        and "count" in _json_path_tail(
            str(payload["target_path"])
        ).casefold()
    ):
        before_collections = _collections_by_path(before_body)
        after_collections = _collections_by_path(after_body)
        mirrored_collection_count = any(
            path in after_collections
            and _transition_tokens_related(
                target_tokens, _transition_semantic_tokens(path)
            )
            and len(collection) == payload["before_value"]
            and len(after_collections[path]) == payload["after_value"]
            for path, collection in before_collections.items()
        )
    collection_semantics = observation_kind in {
        "collection_count", "collection_member"
    } or mirrored_collection_count
    collection_base_path = _transition_collection_base_path(
        observer_path, target_tokens
    )

    for write in sorted(
        (
            row
            for row in request_rows.values()
            if before_order < int(row["global_order"]) < after_order
            and "state_change_like" in set(map(str, row.get("weak_roles", ())))
        ),
        key=lambda row: (int(row["global_order"]), str(row["request_ref"])),
    ):
        request_ref = str(write["request_ref"])
        operation_id = str(write["operation_id"])
        write_path = str(write.get("canonical_path") or "")
        write_tokens = _transition_semantic_tokens(
            f"{operation_id} {write_path}"
        )
        body_tokens = _transition_semantic_tokens(
            " ".join(
                str(row.get("path") or "")
                for row in (write.get("request_body_shape") or {}).get(
                    "shape_rows", ()
                )
            )
        )
        token_match = _transition_tokens_related(target_tokens, write_tokens)
        explicit_body = bool(body_tokens)
        body_match = _transition_tokens_related(target_tokens, body_tokens)
        write_segments = _transition_path_segments(write_path)
        observer_segments = _transition_path_segments(observer_path)
        same_path_scope = bool(
            observer_segments
            and write_segments
            and (
                write_segments[: len(observer_segments)] == observer_segments
                or observer_segments[: len(write_segments)] == write_segments
            )
        )
        identity_state_status, member_identity_state_evidence, identity_state_flow_ids = (
            _transition_member_identity_state_evidence(
                payload,
                write=write,
                entry=entries.get(request_ref, {}),
                before_body=before_body,
                after_body=after_body,
                before_order=before_order,
                request_rows=request_rows,
                entries=entries,
                value_flows=value_flows,
            )
            if collection_semantics
            else ("none", None, ())
        )

        target_resource_flow_ids: list[str] = []
        exact_locator_flow_ids: list[str] = []
        logical_locator_flow_groups: dict[
            tuple[str, str, str], list[str]
        ] = {}
        locator_witness = payload.get("locator_witness")
        locator_witness_flow_id = (
            str(locator_witness.get("flow_id") or "")
            if isinstance(locator_witness, Mapping)
            else ""
        )
        for flow in value_flows.flows:
            producer_ref = str(_transition_flow_value(flow, "producer_request_ref"))
            consumer_ref = str(_transition_flow_value(flow, "consumer_request_ref"))
            if consumer_ref != request_ref:
                continue
            if _transition_flow_value(flow, "from_location") != "response_body":
                continue
            observed_source_path = str(_transition_flow_value(flow, "from_field"))
            source_path = re.sub(
                r"\[\d+\]", "[*]", observed_source_path
            )
            if (
                producer_ref == before_ref
                and _transition_path_parent(source_path) == full_target_parent
            ):
                target_resource_flow_ids.append(
                    str(_transition_flow_value(flow, "flow_id"))
                )
            if identity_kind == "collection_member":
                identity_path = (
                    f"{payload['identity']['collection_path']}[*]"
                    f"{str(payload['identity']['member_path'])[1:]}"
                )
                if (
                    source_path == identity_path
                    and _transition_flow_value(flow, "to_location")
                    in {"path", "query", "body"}
                ):
                    source_body = _response_json(entries.get(producer_ref, {}))
                    if source_body is None:
                        continue
                    try:
                        source_value = _concrete_json_path_value(
                            source_body, observed_source_path
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
                    source_value_ref = _scalar_value_ref(source_value)
                    flow_id = str(_transition_flow_value(flow, "flow_id"))
                    producer = request_rows.get(producer_ref)
                    if producer_ref == before_ref or producer is None or (
                        before_order
                        <= int(producer["global_order"])
                        < int(write["global_order"])
                    ):
                        logical_locator_flow_groups.setdefault(
                            (producer_ref, source_path, source_value_ref), []
                        ).append(flow_id)
                    if (
                        producer_ref == before_ref
                        and source_value_ref
                        == str(payload["identity"].get("value_ref") or "")
                    ):
                        exact_locator_flow_ids.append(flow_id)

        dependency_refs = sorted(
            str(edge["edge_id"])
            for edge in dependency_edges
            if {
                str(edge["producer_operation_id"]),
                str(edge["consumer_operation_id"]),
            }
            == {str(payload["operation_id"]), operation_id}
        )
        provenance = sorted(
            set(target_resource_flow_ids)
            | set(exact_locator_flow_ids)
            | set(identity_state_flow_ids)
            | set(dependency_refs)
        )

        classification = "potentially_relevant"
        reason_code = "target_relation_unproven"
        if collection_semantics:
            logical_locator_witness = (
                len(logical_locator_flow_groups) == 1
                and len(exact_locator_flow_ids) >= 1
                and locator_witness_flow_id in exact_locator_flow_ids
            )
            if (
                observation_kind == "collection_member"
                and isinstance(locator_witness, Mapping)
                and str(locator_witness.get("request_ref") or "") == request_ref
                and locator_witness_flow_id
                and logical_locator_witness
            ):
                classification = "target_relevant"
                reason_code = "target_field_resource_flow"
            elif identity_state_status == "unique":
                classification = "target_relevant"
                reason_code = "member_identity_and_state_evidence"
            elif identity_state_status == "ambiguous":
                classification = "potentially_relevant"
                reason_code = "target_relation_unproven"
            elif _transition_collection_membership_write(
                collection_base_path, write
            ):
                classification = "target_relevant"
                reason_code = "collection_membership_write"
            elif (
                write_path == "/graphql"
                and observer_path == "/graphql"
                and token_match
            ):
                classification = "target_relevant"
                reason_code = "target_field_graphql_operation"
            elif target_tokens and (
                _transition_collection_distinct_descendant(
                    collection_base_path, write_path
                )
                or (not token_match and not provenance)
            ):
                classification = "target_irrelevant"
                reason_code = (
                    "distinct_collection_descendant"
                    if same_path_scope
                    or _transition_collection_distinct_descendant(
                        collection_base_path, write_path
                    )
                    else "disjoint_target_resource"
                )
        else:
            resource_proven = bool(target_resource_flow_ids) or same_path_scope
            if token_match and resource_proven:
                classification = "target_relevant"
                reason_code = (
                    "target_field_resource_flow"
                    if target_resource_flow_ids
                    else "target_field_graphql_operation"
                )
            elif target_tokens and resource_proven and (
                (explicit_body and not body_match)
                or (
                    exact_locator_flow_ids
                    and not token_match
                    and len(write_segments) > len(observer_segments) + 1
                )
            ):
                classification = "target_irrelevant"
                reason_code = "explicit_other_field_write"
            elif (
                target_tokens
                and not resource_proven
                and not token_match
            ):
                classification = "target_irrelevant"
                reason_code = "disjoint_target_resource"

        assessments.append(
            {
                "request_ref": request_ref,
                "global_order": int(write["global_order"]),
                "operation_id": operation_id,
                "canonical_path": write_path,
                "classification": classification,
                "reason_code": reason_code,
                "provenance_refs": tuple(provenance),
                "member_identity_state_evidence": (
                    member_identity_state_evidence
                    if reason_code == "member_identity_and_state_evidence"
                    else None
                ),
            }
        )

    relevant = tuple(
        row["request_ref"]
        for row in assessments
        if row["classification"] == "target_relevant"
    )
    possible = tuple(
        row["request_ref"]
        for row in assessments
        if row["classification"] == "potentially_relevant"
    )
    groundable_ref: str | None = None
    reason = "no_target_relevant_write"
    if len(relevant) > 1:
        reason = "multiple_target_relevant_writes"
    elif possible:
        reason = "potential_competitor_present"
    elif len(relevant) == 1:
        witness = payload.get("locator_witness")
        if witness is not None and witness["request_ref"] != relevant[0]:
            reason = "unique_target_write_lacks_locator_operand"
        else:
            reason = "unique_target_relevant_write"
            groundable_ref = relevant[0]
    return {
        "revision": "target-resource-field-competition-v2",
        "interval_state_change_request_count": len(assessments),
        "target_relevant_request_refs": relevant,
        "potentially_relevant_request_refs": possible,
        "target_irrelevant_request_count": sum(
            row["classification"] == "target_irrelevant" for row in assessments
        ),
        "assessments": tuple(assessments),
        "grounding_status": (
            "unique_target_relevant" if groundable_ref is not None else "ambiguous"
        ),
        "groundable_effect_source_request_ref": groundable_ref,
        "reason_code": reason,
    }


def _transition_scalar_path_allowed(path: str) -> bool:
    tail = _json_path_tail(path)
    folded = tail.casefold().replace("-", "_")
    return (
        "[*]" not in path
        and sensitive_field_category(tail) is None
        and not identity_like_json_path(path)
        and not any(
            token in folded
            for token in ("time", "date", "created", "updated", "expires")
        )
    )


def _transition_member_field_path_allowed(path: str) -> bool:
    return _transition_scalar_path_allowed(path)


def _value_flow_backed_member_locators(
    *,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    collection_path: str,
    before_collection: list[Any],
    after_collection: list[Any],
    entries: Mapping[str, Mapping[str, Any]],
    request_rows: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet,
) -> tuple[dict[str, Any], ...]:
    """Return per-write member locators proven by one exact M6 value flow.

    The concrete recorded array index is used only to recover the witnessed
    scalar from the frozen response.  The emitted identity is member-relative
    and is accepted only when it uniquely selects the same typed value on each
    available collection side.
    """

    before_ref = str(before["request_ref"])
    before_order = int(before["global_order"])
    after_order = int(after["global_order"])
    by_request: dict[str, list[dict[str, Any]]] = {}
    for flow in value_flows.flows:
        consumer_ref = str(flow.consumer_request_ref)
        consumer = request_rows.get(consumer_ref)
        if (
            flow.producer_request_ref != before_ref
            or flow.from_location != "response_body"
            or flow.to_location not in {"path", "query", "body"}
            or consumer is None
            or not before_order < int(consumer["global_order"]) < after_order
            or "state_change_like"
            not in set(map(str, consumer.get("weak_roles", ())))
        ):
            continue
        member_path = _member_relative_path(
            str(flow.from_field), collection_path
        )
        if member_path is None or sensitive_field_category(
            _json_path_tail(member_path)
        ) is not None:
            continue
        try:
            value = _concrete_json_path_value(before["body"], str(flow.from_field))
        except (KeyError, TypeError, ValueError):
            continue
        if (
            isinstance(value, bool)
            or type(value) not in {str, int}
            or (isinstance(value, str) and (not value or "[REDACT" in value))
        ):
            continue
        before_matches = _members_matching_locator(
            before_collection, member_path, value
        )
        after_matches = _members_matching_locator(
            after_collection, member_path, value
        )
        if len(before_matches) != 1 or len(after_matches) > 1:
            continue
        operand = _unique_locator_operand(
            entries[consumer_ref],
            value=value,
            to_location=str(flow.to_location),
            to_field=str(flow.to_field),
        )
        if operand is None:
            continue
        by_request.setdefault(consumer_ref, []).append(
            {
                "flow_id": str(flow.flow_id),
                "request_ref": consumer_ref,
                "to_location": str(flow.to_location),
                "to_field": str(flow.to_field),
                "member_path": member_path,
                "json_type": _json_type(value),
                "value_ref": _scalar_value_ref(value),
                "before_member": before_matches[0],
                "after_member": after_matches[0] if after_matches else None,
                **operand,
            }
        )

    result: list[dict[str, Any]] = []
    for request_ref, rows in sorted(by_request.items()):
        identities = {
            (row["member_path"], row["json_type"], row["value_ref"])
            for row in rows
        }
        if len(rows) != 1 or len(identities) != 1:
            continue
        row = rows[0]
        result.append(
            {
                "member_path": row["member_path"],
                "json_type": row["json_type"],
                "value_ref": row["value_ref"],
                "before_member": row["before_member"],
                "after_member": row["after_member"],
                "locator_witness": {
                    "flow_id": row["flow_id"],
                    "request_ref": request_ref,
                    "to_location": row["to_location"],
                    "to_field": row["to_field"],
                    "operand_role": row["operand_role"],
                    "operand_path": row["operand_path"],
                },
            }
        )
    return tuple(result)


def _member_relative_path(observed_path: str, collection_path: str) -> str | None:
    wildcard = re.sub(r"\[\d+\]", "[*]", observed_path)
    prefix = f"{collection_path}[*]" if collection_path != "$" else "$[*]"
    if not wildcard.startswith(prefix):
        return None
    suffix = wildcard[len(prefix) :]
    if not suffix or "[*]" in suffix:
        return None
    return f"${suffix}"


def _concrete_json_path_value(value: Any, path: str) -> Any:
    if not path.startswith("$"):
        raise ValueError("JSON path must be rooted")
    current = value
    position = 1
    token = re.compile(r"\.([^\.\[]+)|\[(\d+)\]")
    while position < len(path):
        match = token.match(path, position)
        if match is None:
            raise ValueError("unsupported concrete JSON path")
        name, index = match.groups()
        if name is not None and isinstance(current, Mapping) and name in current:
            current = current[name]
        elif index is not None and isinstance(current, list) and int(index) < len(current):
            current = current[int(index)]
        else:
            raise KeyError(path)
        position = match.end()
    return current


def _members_matching_locator(
    collection: list[Any], member_path: str, value: Any
) -> list[Any]:
    matches: list[Any] = []
    for member in collection:
        observed = dict(_scalar_fields(member)).get(member_path, object())
        if _same_json_scalar(observed, value):
            matches.append(member)
    return matches


def _unique_locator_operand(
    entry: Mapping[str, Any],
    *,
    value: Any,
    to_location: str,
    to_field: str,
) -> dict[str, str] | None:
    candidates: list[tuple[str, str]] = []
    request = entry.get("request") or {}
    if to_location == "body":
        raw_text = (request.get("postData") or {}).get("text")
        if isinstance(raw_text, str) and raw_text:
            try:
                body = json.loads(raw_text)
            except json.JSONDecodeError:
                body = None
            if body is not None:
                for path, observed in _scalar_fields(body):
                    if path == to_field and _same_json_scalar(observed, value):
                        candidates.append(("producer_request", path))
    response = _response_json(entry)
    if response is not None:
        for path, observed in _scalar_fields(response):
            if (
                _same_json_scalar(observed, value)
                and sensitive_field_category(_json_path_tail(path)) is None
            ):
                candidates.append(("producer_response", path))
    unique = sorted(set(candidates))
    if len(unique) != 1:
        return None
    return {"operand_role": unique[0][0], "operand_path": unique[0][1]}


def _build_setup_selection_clues(
    recording: RecordingBundle,
    trace: UiApiTrace,
    *,
    recording_root: str | Path,
    api_requests: tuple[dict[str, Any], ...],
    ui_actions: tuple[dict[str, Any], ...],
    request_setup_domains: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet | None = None,
    alias_normalizer: _EvidenceAliasNormalizer,
) -> dict[str, dict[str, Any]]:
    """Project neutral resource-appearance or locator-lineage setup facts.

    The projection never names a cause.  A comparable collection transition
    remains the strongest observation.  When no such read pair exists, one
    exact M6 value-flow identity may expose the same bounded setup domain
    without inventing an absent observation or a causal label.
    """

    entries, graphql_kinds = _recording_entries_by_request(
        recording, trace, recording_root
    )

    request_rows = {str(row["request_ref"]): row for row in api_requests}
    action_rows = {str(row["event_id"]): row for row in ui_actions}
    read_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for request_ref, row in request_rows.items():
        method = str(row.get("method") or "").upper()
        is_read = (
            method in _SETUP_CLUE_READ_METHODS
            or (method == "POST" and graphql_kinds.get(request_ref) == "query")
            or row.get("declared_read_semantic") is True
        )
        status = row.get("response_status")
        if not is_read or not isinstance(status, int) or not 200 <= status < 300:
            continue
        body = _response_json(entries[request_ref])
        if body is None:
            continue
        snapshot = _selector_snapshot_sha256(row)
        key = (
            str(row["actor_id"]),
            str(row["session_run_id"]),
            str(row["operation_id"]),
            snapshot,
        )
        read_groups.setdefault(key, []).append({
            "request_ref": request_ref,
            "global_order": int(row["global_order"]),
            "body": body,
        })
    for rows in read_groups.values():
        rows.sort(key=lambda row: (row["global_order"], row["request_ref"]))

    state_changes_by_action: dict[str, list[Mapping[str, Any]]] = {}
    for row in request_rows.values():
        action_id = row.get("action_event_id")
        if (
            action_id is not None
            and "state_change_like" in set(map(str, row.get("weak_roles", ())))
        ):
            state_changes_by_action.setdefault(str(action_id), []).append(row)
    for rows in state_changes_by_action.values():
        rows.sort(key=lambda row: (int(row["global_order"]), str(row["request_ref"])))

    clues: dict[str, dict[str, Any]] = {}
    for target_ref, domain in request_setup_domains.items():
        if domain.get("status") != "available" or target_ref not in entries:
            continue
        target = request_rows[target_ref]
        locators = _request_locator_scalars(entries[target_ref])
        flow_locators = _flow_backed_target_locators(
            target_ref,
            entries=entries,
            value_flows=value_flows,
        )
        by_value_ref = {
            str(row["value_ref"]): row for row in [*locators, *flow_locators]
        }
        locators = sorted(
            by_value_ref.values(),
            key=lambda row: (row["value_ref"], row["request_paths"]),
        )
        if not locators:
            continue
        transitions_by_locator: dict[str, list[dict[str, Any]]] = {}
        for locator in locators:
            for key, rows in read_groups.items():
                actor_id, session_run_id, operation_id, snapshot = key
                if (
                    actor_id != target["actor_id"]
                    or session_run_id != target["session_run_id"]
                ):
                    continue
                eligible_rows = [
                    row for row in rows
                    if row["global_order"] < int(target["global_order"])
                ]
                for previous, first_seen in zip(eligible_rows, eligible_rows[1:]):
                    match = _unique_collection_member_match(
                        first_seen["body"], locator["_value"]
                    )
                    if match is None:
                        continue
                    previous_collections = _collections_by_path(previous["body"])
                    previous_collection = previous_collections.get(match["collection_path"])
                    if previous_collection is None:
                        continue
                    if _collection_identity_match_count(
                        previous_collection,
                        match["collection_item_path"],
                        locator["_value"],
                    ) != 0:
                        continue
                    transitions_by_locator.setdefault(locator["value_ref"], []).append({
                        "locator": locator,
                        "actor_id": actor_id,
                        "session_run_id": session_run_id,
                        "operation_id": operation_id,
                        "selector_snapshot_sha256": snapshot,
                        "previous": previous,
                        "first_seen": first_seen,
                        **match,
                    })
        if len(transitions_by_locator) != 1:
            lineage = _recorded_locator_lineage_clue(
                target_ref=target_ref,
                target=target,
                locators=flow_locators,
                domain=domain,
                action_rows=action_rows,
                state_changes_by_action=state_changes_by_action,
                entries=entries,
                request_rows=request_rows,
                alias_normalizer=alias_normalizer,
            )
            if lineage is not None:
                clues[target_ref] = lineage
            continue
        transitions = next(iter(transitions_by_locator.values()))
        latest_order = max(row["first_seen"]["global_order"] for row in transitions)
        latest = [
            row for row in transitions
            if row["first_seen"]["global_order"] == latest_order
        ]
        unique_latest = {
            (
                row["collection_path"],
                row["collection_item_path"],
                row["previous"]["request_ref"],
                row["first_seen"]["request_ref"],
            ): row
            for row in latest
        }
        if len(unique_latest) != 1:
            continue
        transition = next(iter(unique_latest.values()))
        previous_order = int(transition["previous"]["global_order"])
        first_seen_order = int(transition["first_seen"]["global_order"])
        eligible_action_ids = set(map(str, domain["eligible_setup_action_ids"]))
        candidate_actions: list[dict[str, Any]] = []
        for action_id in eligible_action_ids:
            action = action_rows.get(action_id)
            if action is None:
                continue
            state_changes = [
                row for row in state_changes_by_action.get(action_id, ())
                if previous_order < int(row["global_order"]) < first_seen_order
            ]
            if not state_changes:
                continue
            candidate_actions.append({
                "setup_action_id": action_id,
                "global_order": int(action["global_order"]),
                "actor_id": str(action["actor_id"]),
                "ui_action": {
                    "action_type": str(action.get("action_type") or ""),
                    "selector": str(action.get("selector") or ""),
                    "visible_element": copy.deepcopy(action.get("visible_element") or {}),
                },
                "state_change_requests": [
                    {
                        "request_ref": str(row["request_ref"]),
                        "global_order": int(row["global_order"]),
                        "method": str(row["method"]),
                        "operation_id": str(row["operation_id"]),
                        "response_status": row.get("response_status"),
                        "request_group_id": row.get("request_group_id"),
                        "weak_roles": list(map(str, row.get("weak_roles", ()))),
                        "resource_identity_overlaps": _resource_identity_overlaps(
                            transition["member"], entries[str(row["request_ref"])]
                        ),
                    }
                    for row in state_changes
                ],
            })
        candidate_actions.sort(key=lambda row: (row["global_order"], row["setup_action_id"]))
        locator = transition["locator"]
        clues[target_ref] = {
            "observation_kind": "absent_to_present",
            "target_request_ref": target_ref,
            "target_locator": {
                "value_ref": locator["value_ref"],
                "json_type": locator["json_type"],
                "request_paths": locator["request_paths"],
                "collection_item_path": transition["collection_item_path"],
            },
            "resource_observation": {
                "actor_id": transition["actor_id"],
                "session_run_id": transition["session_run_id"],
                "operation_id": transition["operation_id"],
                "collection_path": transition["collection_path"],
                "selector_snapshot_sha256": transition["selector_snapshot_sha256"],
                "previous_read_ref": transition["previous"]["request_ref"],
                "previous_observed_contains_member": False,
                "first_seen_read_ref": transition["first_seen"]["request_ref"],
                "first_observed_contains_member": True,
                "member_fields": _member_field_projection(
                    transition["member"], alias_normalizer
                ),
            },
            "candidate_setup_actions": candidate_actions,
            "bound": copy.deepcopy(domain["bound"]),
        }
    return dict(sorted(clues.items()))


def _flow_backed_target_locators(
    target_ref: str,
    *,
    entries: Mapping[str, Mapping[str, Any]],
    value_flows: ObservedValueFlowSet | None,
) -> list[dict[str, Any]]:
    """Recover one target scalar only from exact recorded M6 flows."""

    if value_flows is None:
        return []
    found: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for flow in value_flows.flows:
        if (
            flow.consumer_request_ref != target_ref
            or flow.from_location != "response_body"
            or flow.to_location not in {"path", "query", "body"}
            or sensitive_field_category(_json_path_tail(flow.from_field))
            is not None
            or sensitive_field_category(_json_path_tail(flow.to_field))
            is not None
        ):
            continue
        source_body = _response_json(entries[str(flow.producer_request_ref)])
        if source_body is None:
            continue
        try:
            value = _concrete_json_path_value(source_body, str(flow.from_field))
        except (KeyError, TypeError, ValueError):
            continue
        if (
            isinstance(value, bool)
            or type(value) not in {str, int}
            or (isinstance(value, str) and (not value or "[REDACT" in value))
        ):
            continue
        value_ref = _scalar_value_ref(value)
        row = found.setdefault(
            value_ref,
            {
                "_value": value,
                "value_ref": value_ref,
                "json_type": _json_type(value),
                "request_paths": [],
                "locator_flows": [],
            },
        )
        if not _same_json_scalar(row["_value"], value):
            ambiguous.add(value_ref)
            continue
        row["request_paths"].append(
            f"{flow.to_location}:{flow.to_field}"
        )
        row["locator_flows"].append(
            {
                "flow_id": str(flow.flow_id),
                "source_request_ref": str(flow.producer_request_ref),
                "source_operation_id": str(flow.producer_operation_id),
                "source_response_path": re.sub(
                    r"\[\d+\]", "[*]", str(flow.from_field)
                ),
                "target_location": str(flow.to_location),
                "target_field": str(flow.to_field),
            }
        )
    result = []
    for value_ref, row in sorted(found.items()):
        if value_ref in ambiguous:
            continue
        row["request_paths"] = sorted(set(row["request_paths"]))
        row["locator_flows"] = sorted(
            {canonical_sha256(item): item for item in row["locator_flows"]}.values(),
            key=lambda item: (
                item["source_request_ref"],
                item["source_response_path"],
                item["flow_id"],
            ),
        )
        result.append(row)
    return result


def _recorded_locator_lineage_clue(
    *,
    target_ref: str,
    target: Mapping[str, Any],
    locators: list[dict[str, Any]],
    domain: Mapping[str, Any],
    action_rows: Mapping[str, Mapping[str, Any]],
    state_changes_by_action: Mapping[str, list[Mapping[str, Any]]],
    entries: Mapping[str, Mapping[str, Any]],
    request_rows: Mapping[str, Mapping[str, Any]],
    alias_normalizer: _EvidenceAliasNormalizer,
) -> dict[str, Any] | None:
    """Expose one exact request locator lineage without claiming causality."""

    by_value_ref = {str(row["value_ref"]): row for row in locators}
    if len(by_value_ref) != 1:
        return None
    locator = next(iter(by_value_ref.values()))
    flows = locator.get("locator_flows") or []
    source_paths = sorted({str(row["source_response_path"]) for row in flows})
    if not flows or not source_paths:
        return None
    member_path = source_paths[0]
    member = {"locator": locator["_value"]}
    projected_member = _member_field_projection(
        member, alias_normalizer
    )[0]
    projected_member["path"] = member_path
    projected_member.pop("visible_literal", None)

    target_order = int(target["global_order"])
    eligible_action_ids = set(map(str, domain["eligible_setup_action_ids"]))
    candidate_actions: list[dict[str, Any]] = []
    for action_id in eligible_action_ids:
        action = action_rows.get(action_id)
        if action is None:
            continue
        state_changes = [
            row
            for row in state_changes_by_action.get(action_id, ())
            if int(row["global_order"]) < target_order
        ]
        if not state_changes:
            continue
        candidate_actions.append(
            {
                "setup_action_id": action_id,
                "global_order": int(action["global_order"]),
                "actor_id": str(action["actor_id"]),
                "ui_action": {
                    "action_type": str(action.get("action_type") or ""),
                    "selector": str(action.get("selector") or ""),
                    "visible_element": copy.deepcopy(
                        action.get("visible_element") or {}
                    ),
                },
                "state_change_requests": [
                    {
                        "request_ref": str(row["request_ref"]),
                        "global_order": int(row["global_order"]),
                        "method": str(row["method"]),
                        "operation_id": str(row["operation_id"]),
                        "response_status": row.get("response_status"),
                        "request_group_id": row.get("request_group_id"),
                        "weak_roles": list(map(str, row.get("weak_roles", ()))),
                        "resource_identity_overlaps": _flow_locator_overlaps(
                            value=locator["_value"],
                            value_ref=locator["value_ref"],
                            member_path=member_path,
                            entry=entries[str(row["request_ref"])],
                        ),
                    }
                    for row in state_changes
                ],
            }
        )
    candidate_actions.sort(
        key=lambda row: (row["global_order"], row["setup_action_id"])
    )
    if not candidate_actions or not any(
        request["resource_identity_overlaps"]
        for action in candidate_actions
        for request in action["state_change_requests"]
    ):
        return None
    return {
        "observation_kind": "recorded_locator_lineage",
        "target_request_ref": target_ref,
        "target_locator": {
            "value_ref": locator["value_ref"],
            "json_type": locator["json_type"],
            "request_paths": locator["request_paths"],
            "collection_item_path": member_path,
        },
        "resource_observation": {
            "actor_id": str(target["actor_id"]),
            "session_run_id": str(target["session_run_id"]),
            "source_request_refs": sorted(
                {str(row["source_request_ref"]) for row in flows}
            ),
            "locator_flows": flows,
            "member_fields": [projected_member],
        },
        "candidate_setup_actions": candidate_actions,
        "bound": copy.deepcopy(domain["bound"]),
    }


def _flow_locator_overlaps(
    *,
    value: Any,
    value_ref: str,
    member_path: str,
    entry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project unique exact equalities for one flow-proven locator."""

    found: list[tuple[str, str]] = []
    request = entry.get("request") or {}
    raw_text = (request.get("postData") or {}).get("text")
    if isinstance(raw_text, str) and raw_text:
        try:
            body = json.loads(raw_text)
        except json.JSONDecodeError:
            body = None
        if body is not None:
            found.extend(
                ("request_body", path)
                for path, observed in _scalar_fields(body)
                if _same_json_scalar(observed, value)
                and sensitive_field_category(_json_path_tail(path)) is None
            )
    query: dict[str, str] = {}
    duplicate_names: set[str] = set()
    for row in request.get("queryString", ()):
        name = row.get("name")
        if not isinstance(name, str):
            continue
        if name in query:
            duplicate_names.add(name)
        query[name] = str(row.get("value") or "")
    found.extend(
        ("request_query", f"$.{name}")
        for name, observed in query.items()
        if name not in duplicate_names
        and _same_json_scalar(observed, value)
        and sensitive_field_category(name) is None
    )
    path_matches = [
        path
        for path, observed in _request_path_identity_sources(entry)
        if _same_json_scalar(observed, value)
    ]
    if len(path_matches) == 1:
        found.append(("request_path", path_matches[0]))
    response = _response_json(entry)
    if response is not None:
        found.extend(
            ("response_body", path)
            for path, observed in _scalar_fields(response)
            if _same_json_scalar(observed, value)
            and sensitive_field_category(_json_path_tail(path)) is None
        )
    unique = sorted(set(found))
    if len(unique) != len(found):
        return []
    return [
        {
            "member_path": member_path,
            "observed_path": f"{source_kind}:{path}",
            "value_ref": value_ref,
        }
        for source_kind, path in unique
    ]


def _request_locator_scalars(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    request = entry.get("request") or {}
    found: dict[tuple[str, str], dict[str, Any]] = {}

    def add(value: Any, source: str) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (str, int))
            or (isinstance(value, str) and (not value or "[REDACTED" in value))
        ):
            return
        json_type = _json_type(value)
        value_ref = _scalar_value_ref(value)
        key = (json_type, value_ref)
        row = found.setdefault(key, {
            "_value": value,
            "value_ref": value_ref,
            "json_type": json_type,
            "request_paths": [],
        })
        row["request_paths"].append(source)

    post_data = request.get("postData") or {}
    raw_text = post_data.get("text")
    if isinstance(raw_text, str) and raw_text:
        try:
            body = json.loads(raw_text)
        except json.JSONDecodeError:
            body = None
        if body is not None:
            for path, value in _scalar_fields(body):
                tail = _json_path_tail(path)
                if identity_like_json_path(path) and sensitive_field_category(tail) is None:
                    add(value, f"request_body:{path}")
    for row in request.get("queryString", ()):
        name = row.get("name")
        if (
            isinstance(name, str)
            and identity_like_json_path(f"$.{name}")
            and sensitive_field_category(name) is None
        ):
            add(str(row.get("value") or ""), f"query:$.{name}")
    for source, segment in _request_path_identity_sources(entry):
        add(segment, f"path:{source}")
    for row in found.values():
        row["request_paths"] = sorted(set(row["request_paths"]))
    return sorted(found.values(), key=lambda row: (row["value_ref"], row["request_paths"]))


def _response_json(entry: Mapping[str, Any]) -> Any | None:
    content = (entry.get("response") or {}).get("content") or {}
    if content.get("encoding") is not None:
        return None
    text = content.get("text")
    if not isinstance(text, str) or not text:
        return None
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return None
    return body if isinstance(body, (dict, list)) else None


def _resource_identity_overlaps(
    member: Any,
    entry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return unique observed identity equalities without assigning causality."""

    member_by_ref: dict[str, list[tuple[str, str]]] = {}
    for path, value in _scalar_fields(member):
        tail = _json_path_tail(path)
        if (
            not identity_like_json_path(path)
            or sensitive_field_category(tail) is not None
            or (isinstance(value, str) and "[REDACT" in value)
        ):
            continue
        member_by_ref.setdefault(_scalar_value_ref(value), []).append(
            (path, _json_type(value))
        )
    unique_member = {
        value_ref: rows[0]
        for value_ref, rows in member_by_ref.items()
        if len(rows) == 1
    }

    source_rows: dict[tuple[str, str], list[tuple[str, str]]] = {}
    request = entry.get("request") or {}
    post_data = request.get("postData") or {}
    raw_text = post_data.get("text")
    if isinstance(raw_text, str) and raw_text:
        try:
            request_body = json.loads(raw_text)
        except json.JSONDecodeError:
            request_body = None
        if request_body is not None:
            _collect_identity_overlap_sources(source_rows, "request_body", request_body)

    query: dict[str, Any] = {}
    duplicate_query_names: set[str] = set()
    for query_row in request.get("queryString", ()):
        name = query_row.get("name")
        if not isinstance(name, str):
            continue
        if name in query:
            duplicate_query_names.add(name)
        query[name] = str(query_row.get("value") or "")
    for name in duplicate_query_names:
        query.pop(name, None)
    if query:
        _collect_identity_overlap_sources(source_rows, "request_query", query)

    for path, scalar in _request_path_identity_sources(entry):
        source_rows.setdefault(
            ("request_path", _scalar_value_ref(scalar)), []
        ).append((path, _json_type(scalar)))

    response_body = _response_json(entry)
    if response_body is not None:
        _collect_identity_overlap_sources(source_rows, "response_body", response_body)

    overlaps: list[dict[str, Any]] = []
    for (source_kind, value_ref), rows in source_rows.items():
        if len(rows) != 1 or value_ref not in unique_member:
            continue
        source_path, json_type = rows[0]
        member_path, member_type = unique_member[value_ref]
        if json_type != member_type:
            continue
        overlaps.append({
            "member_path": member_path,
            "observed_path": f"{source_kind}:{source_path}",
            "value_ref": value_ref,
        })
    return sorted(
        overlaps,
        key=lambda row: (row["member_path"], row["observed_path"]),
    )


def _collect_identity_overlap_sources(
    found: dict[tuple[str, str], list[tuple[str, str]]],
    source_kind: str,
    value: Any,
) -> None:
    for path, scalar in _scalar_fields(value):
        tail = _json_path_tail(path)
        if (
            not identity_like_json_path(path)
            or sensitive_field_category(tail) is not None
            or (isinstance(scalar, str) and "[REDACT" in scalar)
        ):
            continue
        found.setdefault((source_kind, _scalar_value_ref(scalar)), []).append(
            (path, _json_type(scalar))
        )


def _request_path_identity_sources(
    entry: Mapping[str, Any],
) -> list[tuple[str, str]]:
    """Return non-sensitive URL segments that are mechanically dynamic."""

    request = entry.get("request") or {}
    raw_segments = [
        segment
        for segment in urlsplit(str(request.get("url") or "")).path.split("/")
        if segment
    ]
    decoded = [unquote(segment) for segment in raw_segments]
    result: list[tuple[str, str]] = []
    for index, segment in enumerate(decoded):
        previous = decoded[index - 1] if index else ""
        if (
            sensitive_field_category(segment) is not None
            or sensitive_field_category(previous) is not None
            or "[REDACT" in segment
        ):
            continue
        if not (
            _UI_DIFF_UUID.fullmatch(segment)
            or _is_opaque_path_segment(segment)
            or (len(segment) >= 8 and _is_opaque_dynamic_token(segment))
            or segment.isdigit()
        ):
            continue
        result.append((f"segment[{index}]", segment))
    return result


def _selector_snapshot_sha256(request: Mapping[str, Any]) -> str:
    shape = request.get("request_body_shape") or {}
    return canonical_sha256({
        "query": request.get("query") or {},
        "body_kind": shape.get("body_kind"),
        "body_sha256": shape.get("body_sha256"),
    })


def _collections_by_path(value: Any) -> dict[str, list[Any]]:
    found: dict[str, list[list[Any]]] = {}

    def walk(item: Any, path: str) -> None:
        if isinstance(item, list):
            found.setdefault(path, []).append(item)
            for child in item:
                if isinstance(child, (dict, list)):
                    walk(child, f"{path}[*]")
        elif isinstance(item, dict):
            for key, child in item.items():
                if isinstance(child, (dict, list)):
                    walk(child, f"{path}.{key}")

    walk(value, "$")
    return {
        path: rows[0]
        for path, rows in found.items()
        if len(rows) == 1
    }


def _unique_collection_member_match(body: Any, value: Any) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for collection_path, collection in _collections_by_path(body).items():
        for member in collection:
            member_matches = []
            if not isinstance(member, (dict, list)):
                if _same_json_scalar(member, value):
                    member_matches.append("$")
            else:
                member_matches.extend(
                    path for path, observed in _scalar_fields(member)
                    if identity_like_json_path(path)
                    and _same_json_scalar(observed, value)
                )
            if len(member_matches) == 1:
                matches.append({
                    "collection_path": collection_path,
                    "collection_item_path": member_matches[0],
                    "member": member,
                })
            elif len(member_matches) > 1:
                return None
    return matches[0] if len(matches) == 1 else None


def _collection_identity_match_count(
    collection: list[Any], path: str, value: Any
) -> int:
    return sum(
        _same_json_scalar(observed, value)
        for member in collection
        for observed_path, observed in _scalar_fields(member)
        if observed_path == path
    )


def _scalar_fields(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_scalar_fields(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for child in value:
            rows.extend(_scalar_fields(child, f"{path}[*]"))
    elif isinstance(value, _SETUP_CLUE_SCALAR_TYPES):
        rows.append((path, value))
    return rows


def _same_json_scalar(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _scalar_value_ref(value: Any) -> str:
    return f"scalar-sha256:{canonical_sha256({'json_type': _json_type(value), 'value': value})}"


def _json_path_tail(path: str) -> str:
    return re.split(r"[.\[\]]+", path)[-1]


def _member_field_projection(
    member: Any, normalizer: _EvidenceAliasNormalizer
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, value in sorted(_scalar_fields(member), key=lambda row: row[0]):
        tail = _json_path_tail(path)
        if sensitive_field_category(tail) is not None:
            continue
        if isinstance(value, str) and "[REDACTED" in value:
            continue
        row: dict[str, Any] = {
            "path": path,
            "json_type": _json_type(value),
            "value_ref": _scalar_value_ref(value),
        }
        if isinstance(value, bool):
            row["visible_literal"] = value
        elif (
            isinstance(value, str)
            and not identity_like_json_path(path)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", value)
        ):
            row["visible_literal"] = value
        if isinstance(value, str):
            normalized = normalizer.normalize_text(value)
            if normalized != value and normalized.startswith("<"):
                row["stable_alias"] = normalized
        rows.append(row)
    return rows


def _compact_trace(
    recording: RecordingBundle,
    trace: UiApiTrace,
    recording_root: str | Path,
    *,
    alias_normalizer: _EvidenceAliasNormalizer,
) -> dict[str, tuple[dict[str, Any], ...]]:
    paths = resolve_recording_bundle_paths(recording, recording_root)
    bundles = {
        item.run_id: load_bundle(paths[item.actor_id]) for item in recording.actors
    }
    action_by_ref = {
        (bundle.run_id, str(action["action_id"])): action
        for bundle in bundles.values()
        for action in bundle.actions
    }
    ui_actions = []
    for event in trace.trace["events"]:
        ref = event["action_ref"]
        action = action_by_ref.get((str(ref["run_id"]), str(ref["action_id"])))
        if action is None:
            raise ValueError(f"proposal view cannot resolve UI action: {event['event_id']}")
        accessibility = action.get("element_accessibility") or {}
        ui_actions.append(_hashed_row({
            "event_id": str(event["event_id"]),
            "actor_id": str(event["actor_id"]),
            "global_order": int(event["global_order"]),
            "timestamp": str(action.get("timestamp") or ""),
            "action_type": str(action.get("action_type") or ""),
            "selector": str(action.get("selector") or ""),
            "page_url": str(action.get("page_url") or ""),
            "visible_element": {
                key: accessibility.get(key)
                for key in ("role", "name", "tag", "text", "input_type")
            },
            "dom_declarations": _recorded_dom_declarations(
                recording, recording_root, bundles[str(ref["run_id"])],
                str(ref["action_id"]), alias_normalizer,
            ),
        }))

    automatic_by_request: dict[str, list[str]] = {}
    for binding in trace.trace["bindings"]:
        automatic_by_request.setdefault(str(binding["request_ref"]), []).append(str(binding["event_id"]))
    review_by_request: dict[str, list[str]] = {}
    for review in trace.trace["binding_reviews"]:
        for request_ref in review.get("candidate_request_refs", []):
            review_by_request.setdefault(str(request_ref), []).append(str(review["event_id"]))

    group_by_request: dict[str, dict[str, Any]] = {}
    for group in trace.trace["request_groups"]:
        for member in group["members"]:
            group_by_request[str(member["request_ref"])] = {
                "request_group_id": str(group["group_id"]),
                "action_event_id": str(group["event_id"]),
                "association_status": str(group["status"]),
                "group_order": int(member["group_order"]),
                "is_anchor": group.get("anchor_request_ref")
                == member["request_ref"],
                "weak_roles": list(member["weak_roles"]),
            }
    unassigned_by_request = {
        str(item["request_ref"]): item
        for item in trace.trace["unassigned_requests"]
    }

    api_requests = []
    for request in trace.trace["api_requests"]:
        observation = request["observation_ref"]
        run_id = str(observation["run_id"])
        entry_index = int(observation["entry_index"])
        bundle = bundles.get(run_id)
        if bundle is None or entry_index < 0 or entry_index >= len(bundle.entries):
            raise ValueError(f"proposal view cannot resolve API request: {request['request_ref']}")
        entry = bundle.entries[entry_index]
        raw_request = entry.get("request") or {}
        raw_response = entry.get("response") or {}
        response_content = raw_response.get("content") or {}
        post_data = raw_request.get("postData") or {}
        request_ref = str(request["request_ref"])
        association = group_by_request.get(request_ref)
        if association is None:
            unassigned = unassigned_by_request.get(request_ref)
            if unassigned is None:
                raise ValueError("proposal view request is absent from the M2 partition")
            association = {
                "request_group_id": None,
                "action_event_id": None,
                "association_status": str(unassigned["status"]),
                "group_order": None,
                "is_anchor": False,
                "weak_roles": list(unassigned["weak_roles"]),
            }
        query = _query_projection(
            raw_request.get("queryString", []), alias_normalizer
        )
        api_requests.append(_hashed_row({
            "request_ref": request_ref,
            "actor_id": str(request["actor_id"]),
            "session_run_id": run_id,
            "session_ref": bundle.manifest.get("session", {}).get("auth_context", {}).get("session_ref", run_id),
            "identity_relations": copy.deepcopy(bundle.manifest.get("session", {}).get("auth_context", {}).get("identity_relations", [])),
            "global_order": int(request["global_order"]),
            "operation_id": str(request["operation_id"]),
            "method": str(request["method"]),
            "canonical_path": str(request["canonical_path"]),
            "body_encoding": str(request.get("body_encoding") or "none"),
            **(
                {"declared_read_semantic": True}
                if request.get("declared_read_semantic") is True
                else {}
            ),
            "response_status": (
                None if type(raw_response.get("status")) is int and raw_response["status"] == 0
                else raw_response.get("status")
            ),
            "request_mime_type": post_data.get("mimeType"),
            "response_mime_type": response_content.get("mimeType"),
            "query_parameter_names": sorted({
                str(item.get("name"))
                for item in raw_request.get("queryString", [])
                if item.get("name") is not None
            }),
            "request_header_names": sorted({
                str(item["name"]) for item in raw_request.get("headers", [])
                if isinstance(item, Mapping) and isinstance(item.get("name"), str)
                and sensitive_field_category(item["name"]) is None
            }),
            **({"query": query} if query else {}),
            "parameter_evidence": _request_parameter_evidence(
                raw_request,
                source_ref={
                    "artifact_type": "session_bundle", "run_id": run_id,
                    "path": str(bundle.manifest["members"]["har"]),
                    "record_id": request_ref,
                    "value_path": f"$.log.entries[{entry_index}].request",
                },
                normalizer=alias_normalizer,
            ),
            "request_body_shape": _body_shape_projection(post_data.get("text")),
            "response_body_shape": _body_shape_projection(response_content.get("text")),
            "automatic_event_ids": sorted(automatic_by_request.get(request_ref, [])),
            "review_event_ids": sorted(review_by_request.get(request_ref, [])),
            **association,
        }))
    return {
        "ui_actions": tuple(ui_actions),
        "api_requests": tuple(api_requests),
    }


def _literal_evidence(value: str, normalizer: _EvidenceAliasNormalizer) -> dict[str, Any]:
    """Keep exact business text, but never promote a dynamic alias to a literal."""
    normalized = normalizer.normalize_text(value)
    if re.search(r"<(?:ID|ACTOR|TIME)_[0-9]+>|<TOKEN>|<REDACTED>|\[REDACTED", normalized, re.IGNORECASE):
        return {"literal_available": False, "sanitized_text": normalized}
    return {"literal_available": True, "value": value}


class _FormDeclarationParser(HTMLParser):
    """Read recorded attributes only; this does not execute browser validation."""

    _ATTRIBUTES = frozenset({
        "required", "type", "min", "max", "minlength", "maxlength", "pattern",
        "multiple", "disabled", "readonly",
    })
    _SKIPPED = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self, normalizer: _EvidenceAliasNormalizer) -> None:
        super().__init__(convert_charrefs=True)
        self.normalizer = normalizer
        self.rows: list[dict[str, Any]] = []
        self._skip: list[str] = []
        self._select: dict[str, Any] | None = None
        self._option: dict[str, Any] | None = None
        self._option_text: list[str] = []
        self._disabled_group = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip:
            if tag in self._SKIPPED:
                self._skip.append(tag)
            return
        if tag in self._SKIPPED:
            self._skip.append(tag)
            return
        attributes = dict(attrs)
        if tag == "optgroup":
            self._disabled_group = "disabled" in attributes
        if tag == "option" and self._select is not None:
            self._finish_option()
            self._option = {
                "disabled": "disabled" in attributes or self._disabled_group,
                "selected": "selected" in attributes,
                "value_source": "value_attribute" if "value" in attributes else "text_content",
            }
            if "value" in attributes:
                self._option.update(_literal_evidence(attributes["value"] or "", self.normalizer))
            self._select["options"].append(self._option)
        if tag not in {"input", "textarea", "select"}:
            return
        row = {
            "element_index": len(self.rows), "tag": tag,
            "attributes": {key: value for key, value in attrs if key in self._ATTRIBUTES},
            "element": {
                key: self.normalizer.normalize_text(attributes[key] or "")
                for key in ("id", "name") if key in attributes
            },
        }
        if tag == "select":
            row["options"] = []
            self._select = row
        elif tag == "input" and str(attributes.get("type") or "").lower() == "radio":
            row["option"] = {
                "value_source": "value_attribute" if "value" in attributes else "html_default_on",
                **_literal_evidence(attributes.get("value") or ("" if "value" in attributes else "on"), self.normalizer),
            }
        self.rows.append(row)

    def handle_data(self, data: str) -> None:
        if not self._skip and self._option is not None:
            self._option_text.append(data)

    def _finish_option(self) -> None:
        if self._option is not None:
            # HTML option text strips and collapses ASCII whitespace only.
            label = re.sub(r"[\t\n\f\r ]+", " ", "".join(self._option_text)).strip(" ")
            self._option["label"] = self.normalizer.normalize_text(label)
            if self._option["value_source"] == "text_content":
                self._option.update(_literal_evidence(label, self.normalizer))
        self._option = None
        self._option_text = []

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
            return
        if tag in {"option", "select"}:
            self._finish_option()
        if tag == "select":
            self._select = None
        elif tag == "optgroup":
            self._disabled_group = False

    def close(self) -> None:
        super().close()
        self._finish_option()


def _recorded_dom_declarations(
    recording: RecordingBundle, recording_root: str | Path, bundle: Any,
    action_id: str, normalizer: _EvidenceAliasNormalizer,
) -> list[dict[str, Any]]:
    result = []
    for snapshot in bundle.manifest["members"].get("page_state", ()):
        record_id = str(snapshot["action_id"])
        if record_id not in {action_id, f"before:{action_id}"}:
            continue
        source_ref = {
            "artifact_type": "session_bundle", "run_id": bundle.run_id,
            "path": str(snapshot["file"]), "record_id": record_id,
            "value_path": "$.dom_html",
        }
        state, digest = _load_page_state(recording, recording_root, source_ref)
        parser = _FormDeclarationParser(normalizer)
        parser.feed(state["dom_html"])
        parser.close()
        if parser.rows:
            result.append({
                "source_ref": source_ref, "page_state_sha256": digest,
                "snapshot": "before" if record_id.startswith("before:") else "after",
                "captured_at": str(state.get("captured_at") or snapshot["timestamp"]),
                "semantics": "recorded_html_declarations_not_api_constraints",
                "elements": parser.rows,
            })
    return result


@dataclass(frozen=True)
class _RecordedNumber:
    lexical: str
    value_type: str


def _request_parameter_evidence(
    request: Mapping[str, Any], *, source_ref: Mapping[str, Any],
    normalizer: _EvidenceAliasNormalizer,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    unsupported: list[dict[str, str]] = []

    def add(location: str, path: str, value: Any, **extra: Any) -> None:
        row = {"location": location, "path": path, **extra}
        if isinstance(value, _RecordedNumber):
            row.update(value_type=value.value_type, lexical=value.lexical, literal_available=True)
        else:
            row["value_type"] = _json_type(value)
            row.update(_literal_evidence(value, normalizer) if isinstance(value, str) else {"value": value, "literal_available": True})
        rows.append(row)

    for location, values in (("query", request.get("queryString", ())), ("headers", request.get("headers", ()))):
        names = [str(row.get("name") or "") for row in values]
        counts = Counter(name.lower() if location == "headers" else name for name in names)
        seen: Counter[str] = Counter()
        for row, name in zip(values, names):
            if not name or sensitive_field_category(name) is not None:
                continue
            key = name.lower() if location == "headers" else name
            if "." in key:
                unsupported.append({"location": location, "reason_code": "request_parameter_path_unsupported"})
                continue
            seen[key] += 1
            add(location, f"$.{key}", str(row.get("value") or ""), occurrence_index=seen[key] - 1, occurrence_count=counts[key])
    parsed = urlsplit(str(request.get("url") or ""))
    add("path", "$", unquote(parsed.path))
    text = (request.get("postData") or {}).get("text")
    if isinstance(text, str) and text:
        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            if len({key for key, _ in items}) != len(items):
                raise ValueError("duplicate_json_object_keys")
            return dict(items)

        def invalid_constant(_value: str) -> None:
            raise ValueError("non_finite_json_number")

        try:
            body = json.loads(text, parse_int=lambda value: _RecordedNumber(value, "integer"), parse_float=lambda value: _RecordedNumber(value, "number"), parse_constant=invalid_constant, object_pairs_hook=pairs)
        except ValueError as exc:
            unsupported.append({"location": "body", "reason_code": str(exc) if not isinstance(exc, json.JSONDecodeError) else "request_body_not_json"})
        else:
            def visit(value: Any, path: str) -> None:
                if isinstance(value, dict):
                    rows.append({"location": "body", "path": path, "value_type": "object", "property_count": len(value), "literal_available": True})
                    for key, item in value.items():
                        if not key or any(char in key for char in ".*[]"):
                            unsupported.append({"location": "body", "reason_code": "request_parameter_path_unsupported"})
                        elif sensitive_field_category(key) is None and key != "$route_s_redacted":
                            visit(item, f"{path}.{key}")
                        else:
                            unsupported.append({"location": "body", "reason_code": "request_parameter_sensitive"})
                elif isinstance(value, list):
                    rows.append({"location": "body", "path": path, "value_type": "array", "length": len(value), "literal_available": True})
                    for index, item in enumerate(value):
                        visit(item, f"{path}.{index}")
                else:
                    add("body", path, value)
            visit(body, "$")
    return {"source_ref": dict(source_ref), "semantics": "recorded_request_parameters_rebind_at_execution", "parameters": rows, "unsupported": unsupported}


def _hashed_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    row["full_row_sha256"] = canonical_sha256(row)
    return row


def _query_projection(
    rows: Any, normalizer: _EvidenceAliasNormalizer
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows if isinstance(rows, list) else []:
        name = row.get("name")
        if not isinstance(name, str) or not name:
            continue
        if sensitive_field_category(name) is not None:
            value = "<REDACTED>"
        else:
            literal = _literal_evidence(str(row.get("value") or ""), normalizer)
            value = literal.get("value", literal.get("sanitized_text"))
        if name not in result:
            result[name] = value
        elif not isinstance(result[name], list):
            result[name] = [result[name], value]
        else:
            result[name].append(value)
    return result


def _evidence_channel_summary(channel_name: str, channel: Any) -> dict[str, Any]:
    records = list(channel.records)
    first = records[0] if records else None
    summary = {
        "status": channel.status,
        "reason": channel.reason,
        "record_count": len(records),
        "records_sha256": canonical_sha256(records),
        "artifact_sha256": channel.artifact_sha256,
        "deterministic_witness_record_id": (
            str(first.get("record_id"))
            if isinstance(first, Mapping) and first.get("record_id") is not None
            else None
        ),
        "deterministic_witness_sha256": canonical_sha256(first) if first is not None else None,
    }
    if channel_name in {"transfer", "ui_diff"}:
        summary["semantic_projection"] = _compact_aux_channel_projection(
            channel_name,
            channel.status,
            records,
            summary["records_sha256"],
        )
    return summary


def _compact_aux_channel_projection(
    channel_name: str,
    status: str,
    records: list[dict[str, Any]],
    records_sha256: str,
) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: str(item.get("record_id") or ""))
    if len({str(item.get("record_id") or "") for item in ordered}) != len(ordered):
        raise ValueError(f"{channel_name} evidence record IDs must be unique")
    if status == "unavailable" and ordered:
        raise ValueError(f"unavailable {channel_name} evidence cannot be projected")
    visible = ordered
    if channel_name == "transfer":
        rows = [_compact_transfer_row(item).model_dump(mode="json") for item in visible]
    else:
        normalizer = _EvidenceAliasNormalizer()
        rows = [
            _compact_ui_diff_row(item, normalizer).model_dump(mode="json")
            for item in visible
        ]
    payload = {
        "revision": "aux-semantic-projection-v1",
        "channel": channel_name,
        "source_records_sha256": records_sha256,
        "total_count": len(ordered),
        "visible_count": len(rows),
        "omitted_count": 0,
        "ordering_rule": "record_id_asc_all_v1",
        "rows": rows,
    }
    return CompactChannelProjection(
        **payload,
        projection_sha256=canonical_sha256(payload),
    ).model_dump(mode="json")


def _compact_transfer_row(raw: Mapping[str, Any]) -> CompactTransferAssertion:
    record = TransferEvidenceRecord.model_validate(raw, strict=True)
    subject_kind, predicate_operator = _symbolic_ui_assertion_intent(
        record.origin.assertion,
        record.origin.assertion_kind,
    )
    payload = {
        "record_id": record.record_id,
        "source_kind": record.source_kind,
        "assertion_kind": record.origin.assertion_kind,
        "origin_ref": f"{record.origin.source_path}:{record.origin.start_line}",
        "assertion_sha256": record.origin.assertion_sha256,
        "subject_kind": subject_kind,
        "predicate_operator": predicate_operator,
        "symbolic_intent": f"{subject_kind}:{predicate_operator}",
        "api_observation_ref_count": len(record.api_observation_refs),
        "full_row_sha256": canonical_sha256(raw),
    }
    return CompactTransferAssertion(
        **payload,
        projection_sha256=canonical_sha256(payload),
    )


def _symbolic_ui_assertion_intent(assertion: str, assertion_kind: str) -> tuple[str, str]:
    compact = " ".join(assertion.split())
    if "cy.location(" in compact:
        subject = "page_location"
    elif "cy.getBySel(" in compact:
        subject = "test_selector_element"
    elif "cy.get(" in compact:
        subject = "selector_element"
    elif "cy.contains(" in compact:
        subject = "visible_text_match"
    elif "expect(" in compact:
        subject = "ui_expression"
    else:
        subject = "ui_assertion"
    match = re.search(r"\.should\(\s*['\"]([^'\"]+)['\"]", compact)
    if match:
        operator = match.group(1)
    elif "cy.contains(" in compact:
        operator = "contains"
    else:
        operator = assertion_kind
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", operator):
        operator = assertion_kind
    return subject, operator


def _compact_ui_diff_row(
    raw: Mapping[str, Any],
    normalizer: _EvidenceAliasNormalizer,
) -> CompactUiDiff:
    record = UiDiffEvidenceRecord.model_validate(raw, strict=True)
    added = [
        normalizer.normalize_text(item)
        for item in record.added_text[:COMPACT_UI_DIFF_ITEM_LIMIT]
    ]
    removed = [
        normalizer.normalize_text(item)
        for item in record.removed_text[:COMPACT_UI_DIFF_ITEM_LIMIT]
    ]
    event_id = str(record.event_ref.get("record_id") or "")
    preceding_refs = [str(item.get("record_id") or "") for item in record.producer_request_refs]
    following_refs = [str(item.get("record_id") or "") for item in record.consumer_request_refs]
    if not event_id or any(not item for item in (*preceding_refs, *following_refs)):
        raise ValueError("typed UI-diff projection contains an unresolved observation reference")
    payload = {
        "record_id": record.record_id,
        "event_id": event_id,
        "preceding_request_refs": preceding_refs,
        "following_request_refs": following_refs,
        "before_page_path": normalizer.normalize_path(record.before_page_path),
        "after_page_path": normalizer.normalize_path(record.after_page_path),
        "added_sanitized_text": added,
        "removed_sanitized_text": removed,
        "added_total_count": len(record.added_text),
        "removed_total_count": len(record.removed_text),
        "added_omitted_count": len(record.added_text) - len(added),
        "removed_omitted_count": len(record.removed_text) - len(removed),
    }
    return CompactUiDiff(**payload)


def _body_shape_projection(raw_text: Any) -> dict[str, Any]:
    if not isinstance(raw_text, str) or not raw_text:
        return {
            "body_kind": "absent",
            "body_sha256": None,
            "shape_total_count": 0,
            "shape_visible_count": 0,
            "shape_omitted_count": 0,
            "shape_rows": [],
            "compact_rule": "sorted_unique_json_shape_paths_prefix_64_v1",
        }
    try:
        body = json.loads(raw_text)
        body_kind = "json"
        body_sha = canonical_sha256(body)
    except json.JSONDecodeError:
        body = raw_text
        body_kind = "text"
        body_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    rows: set[tuple[str, str]] = set()
    _walk_shape(body, "$", rows)
    ordered = [{"path": path, "type": kind} for path, kind in sorted(rows)]
    visible = ordered[:COMPACT_BODY_SHAPE_LIMIT]
    return {
        "body_kind": body_kind,
        "body_sha256": body_sha,
        "shape_total_count": len(ordered),
        "shape_visible_count": len(visible),
        "shape_omitted_count": len(ordered) - len(visible),
        "shape_rows": visible,
        "compact_rule": "sorted_unique_json_shape_paths_prefix_64_v1",
    }


def _walk_shape(value: Any, path: str, rows: set[tuple[str, str]]) -> None:
    kind = _json_type(value)
    rows.add((path, kind))
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_shape(child, f"{path}.{key}", rows)
    elif isinstance(value, list):
        for child in value:
            _walk_shape(child, f"{path}[*]", rows)


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
    if isinstance(value, dict):
        return "object"
    raise ValueError(f"non-JSON body value in frozen recording: {type(value).__name__}")


def _validated_products(
    structure: ObservationalApiStructure,
    products: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    required = {"initial_structure", "audit_only_probe_results", "augmented_structure"}
    if not required <= set(products):
        raise ValueError(f"observation-derived Stage2/2.5/3 products missing: {sorted(required - set(products))}")
    initial = products["initial_structure"]
    probes = products["audit_only_probe_results"]
    augmented = products["augmented_structure"]
    observed = (
        canonical_sha256(initial),
        canonical_sha256(probes),
        canonical_sha256(augmented),
    )
    expected = (
        structure.initial_structure_sha256,
        structure.audit_only_probe_results_sha256,
        structure.augmented_structure_sha256,
    )
    if observed != expected:
        raise ValueError("observation-derived Stage2/2.5/3 product hash mismatch")
    if structure.audit_only and structure.active_http_probes == 0:
        admitted_probe_observations = [
            observation
            for path_item in augmented.get("paths", {}).values()
            if isinstance(path_item, Mapping)
            for operation in path_item.values()
            if isinstance(operation, Mapping)
            for observation in operation.get("x-carverflow-observations", [])
            if observation.get("source") == "stage2_5_probe"
        ]
        if admitted_probe_observations:
            raise ValueError(
                "audit-only pre-proposal structure cannot admit Stage2.5 probe observations"
            )
    return initial, probes, augmented


def _reject_forbidden_inputs(forbidden_inputs: Mapping[str, Any] | None) -> None:
    supplied = set(forbidden_inputs or {})
    forbidden = PREPROPOSAL_FORBIDDEN_SOURCES | {
        "provider_response",
        "candidate_set",
        "route_s_verdict",
        "final_reference_labels",
        "binder_labels",
    }
    if supplied & forbidden:
        raise ValueError(f"forbidden pre-proposal input supplied: {sorted(supplied & forbidden)}")


def _unresolved_stage3_observations(
    augmented: Mapping[str, Any],
    bundles: Mapping[str, Any],
    request_by_observation: Mapping[tuple[str, int], str],
) -> list[tuple[str, int]]:
    unresolved = []
    for path_item in augmented.get("paths", {}).values():
        for operation in path_item.values():
            if not is_execution_ready(operation):
                continue
            for observation in operation.get("x-carverflow-observations", []):
                if observation.get("source") == "stage2_5_probe":
                    continue
                key = (str(observation.get("run_id")), int(observation.get("entry_index", -1)))
                bundle = bundles.get(key[0])
                if bundle is None or key[1] < 0 or key[1] >= len(bundle.entries) or key not in request_by_observation:
                    unresolved.append(key)
    return sorted(set(unresolved))


def _flow_lookup_key(flow: ObservedValueFlow) -> tuple[Any, ...]:
    return (
        flow.producer_operation_id,
        flow.consumer_operation_id,
        flow.from_location,
        flow.from_field,
        flow.to_location,
        flow.to_field,
        flow.producer_session_run_id,
        flow.producer_entry_index,
        flow.consumer_session_run_id,
        flow.consumer_entry_index,
    )


def _timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
