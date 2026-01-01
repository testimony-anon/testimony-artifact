"""Canonical, serializable contracts for the UISemTest method pipeline.

The contracts deliberately carry data and provenance only.  Subject lifecycle,
evaluation schedules, providers, and result-specific policy do not belong here.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .current_route_s import canonical_json_bytes, canonical_sha256


SCHEMA_VERSION = "uisemtest.method.v1"
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]


class FinalSuiteStratum(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    qualification_ref: str
    tests_ref: str
    calibration_ref: str
    attempted: NonNegativeInt
    confirmed: NonNegativeInt
    generated: NonNegativeInt
    retained: NonNegativeInt

    @model_validator(mode="after")
    def _closed_counts(self) -> "FinalSuiteStratum":
        if not (
            self.retained <= self.generated <= self.confirmed <= self.attempted
        ):
            raise ValueError("final suite stratum counts do not close")
        return self


class FinalSuiteProducerPartition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    domain_business: NonNegativeInt
    available: NonNegativeInt
    unsupported: NonNegativeInt
    auth_session: NonNegativeInt
    total: NonNegativeInt
    disjoint: Literal[True]

    @model_validator(mode="after")
    def _closed_partition(self) -> "FinalSuiteProducerPartition":
        if self.domain_business != self.available + self.unsupported:
            raise ValueError("final suite business availability partition does not close")
        if self.total != self.domain_business + self.auth_session:
            raise ValueError("final suite producer partition does not close")
        return self


class FinalSuiteIndex(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["uisemtest-final-suite-index-v1"]
    artifact_type: Literal["final_suite_index"]
    producer_partition: FinalSuiteProducerPartition
    strata: dict[Literal["domain_business", "auth_session"], FinalSuiteStratum]
    total_retained_count: NonNegativeInt

    @model_validator(mode="after")
    def _closed_index(self) -> "FinalSuiteIndex":
        if set(self.strata) != {"domain_business", "auth_session"}:
            raise ValueError("final suite index requires both scientific strata")
        if self.total_retained_count != sum(
            row.retained for row in self.strata.values()
        ):
            raise ValueError("final suite retained total does not close strata")
        return self


class Contract(BaseModel):
    """Strict base contract with one canonical JSON representation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["uisemtest.method.v1"] = SCHEMA_VERSION
    source_refs: tuple[str, ...] = ()
    source_sha256: dict[str, Sha256] = Field(default_factory=dict)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))

    def canonical_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> Self:
        return cls.model_validate_json(payload)


class ActorBundleRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str
    run_id: str
    path: str
    manifest_sha256: Sha256

    @field_validator("path")
    @classmethod
    def _recording_root_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or value in {".", ".."}
            or path.is_absolute()
            or ".." in path.parts
            or PureWindowsPath(value).is_absolute()
            or "\\" in value
        ):
            raise ValueError("recording actor path must be recording-root-relative POSIX")
        return value


class RecordingBundle(Contract):
    artifact_type: Literal["recording_bundle"] = "recording_bundle"
    recording_id: str
    actors: tuple[ActorBundleRef, ...]
    workflow_id: str
    workflow_result_ref: str
    reset_epoch: str
    step_correspondence: tuple[dict[str, Any], ...]

    @model_validator(mode="after")
    def _unique_actors(self) -> "RecordingBundle":
        actor_ids = [item.actor_id for item in self.actors]
        run_ids = [item.run_id for item in self.actors]
        if not actor_ids or len(actor_ids) != len(set(actor_ids)):
            raise ValueError("recording actors must be nonempty and unique")
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("recording run IDs must be unique")
        indexes = [int(item["global_step_index"]) for item in self.step_correspondence]
        if indexes != list(range(len(indexes))):
            raise ValueError("recording step correspondence must be globally contiguous")
        return self


class UiApiTrace(Contract):
    artifact_type: Literal["ui_api_trace"] = "ui_api_trace"
    trace_id: str
    trace: dict[str, Any]
    event_count: int
    admitted_request_count: int
    automatic_binding_count: int
    review_required_count: int

    @model_validator(mode="after")
    def _counts_match(self) -> "UiApiTrace":
        expected = (
            len(self.trace.get("events", [])),
            len(self.trace.get("api_requests", [])),
            len(self.trace.get("bindings", [])),
            len(self.trace.get("binding_reviews", [])),
        )
        if expected != (
            self.event_count,
            self.admitted_request_count,
            self.automatic_binding_count,
            self.review_required_count,
        ):
            raise ValueError("trace counts do not match the embedded trace")
        events = [str(item.get("event_id")) for item in self.trace.get("events", [])]
        requests = [str(item.get("request_ref")) for item in self.trace.get("api_requests", [])]
        bindings = self.trace.get("bindings", [])
        reviews = self.trace.get("binding_reviews", [])
        if len(events) != len(set(events)) or len(requests) != len(set(requests)):
            raise ValueError("trace event and request IDs must be unique")
        if any(item.get("event_id") not in events or item.get("request_ref") not in requests for item in bindings):
            raise ValueError("trace binding contains a dangling reference")
        if any(item.get("event_id") not in events for item in reviews):
            raise ValueError("trace review contains a dangling event reference")
        groups = self.trace.get("request_groups")
        unassigned = self.trace.get("unassigned_requests")
        if not isinstance(groups, list) or not isinstance(unassigned, list):
            raise ValueError("trace must contain request_groups and unassigned_requests")
        grouped_events = [str(item.get("event_id")) for item in groups]
        if sorted(grouped_events) != sorted(events):
            raise ValueError("trace must contain exactly one request group per event")
        request_actor = {
            str(item.get("request_ref")): str(item.get("actor_id"))
            for item in self.trace.get("api_requests", [])
        }
        grouped_requests = [
            str(member.get("request_ref"))
            for group in groups
            for member in group.get("members", [])
        ]
        unassigned_requests = [str(item.get("request_ref")) for item in unassigned]
        represented = grouped_requests + unassigned_requests
        if len(represented) != len(set(represented)) or sorted(represented) != sorted(requests):
            raise ValueError("every admitted request must appear once in a group or unassigned")
        event_actor = {
            str(item.get("event_id")): str(item.get("actor_id"))
            for item in self.trace.get("events", [])
        }
        for group in groups:
            event_id = str(group.get("event_id"))
            actor_id = str(group.get("actor_id"))
            if event_actor.get(event_id) != actor_id:
                raise ValueError("request group actor must match its event actor")
            member_refs = [str(item.get("request_ref")) for item in group.get("members", [])]
            if any(request_actor.get(ref) != actor_id for ref in member_refs):
                raise ValueError("request group members must share the event actor")
            anchor = group.get("anchor_request_ref")
            if anchor is not None and str(anchor) not in member_refs:
                raise ValueError("request group anchor must be a group member")
        if any(request_actor.get(str(item.get("request_ref"))) != str(item.get("actor_id")) for item in unassigned):
            raise ValueError("unassigned request actor must match the admitted request")
        return self


class ObservationalApiStructure(Contract):
    artifact_type: Literal["observational_api_structure"] = "observational_api_structure"
    structure_id: str
    stage2_operation_count: int
    stage2_5_record_count: int
    stage3_operation_count: int
    initial_structure_sha256: Sha256
    audit_only_probe_results_sha256: Sha256
    augmented_structure_sha256: Sha256
    audit_only: bool = True
    active_http_probes: NonNegativeInt = 0

    @model_validator(mode="after")
    def _probe_execution_mode_closed(self) -> "ObservationalApiStructure":
        if self.audit_only != (self.active_http_probes == 0):
            raise ValueError("observational structure probe execution mode mismatch")
        return self


class ObservedOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str
    method: str
    canonical_path: str
    readiness: str
    observation_refs: tuple[dict[str, Any], ...]
    observation_derived: Literal[True] = True


class ObservedApiCatalog(Contract):
    artifact_type: Literal["observed_api_catalog"] = "observed_api_catalog"
    catalog_id: str
    operations: tuple[ObservedOperation, ...]
    operation_count: int
    stage2_source_sha256: Sha256
    stage3_source_sha256: Sha256
    derivation: Literal[
        "recording_observation_only",
        "recording_and_validated_probe_observations",
    ] = "recording_observation_only"
    official_or_external_spec_used: Literal[False] = False

    @model_validator(mode="after")
    def _catalog_closed(self) -> "ObservedApiCatalog":
        if self.operation_count != len(self.operations):
            raise ValueError("observed API catalog operation count mismatch")
        ids = [item.operation_id for item in self.operations]
        if len(ids) != len(set(ids)):
            raise ValueError("observed API catalog operation IDs must be unique")
        if any(not item.observation_refs for item in self.operations):
            raise ValueError("observed API catalog operations require observation references")
        return self


class DiscoveryCandidateAudit(Contract):
    artifact_type: Literal["discovery_candidate_audit"] = "discovery_candidate_audit"
    audit_id: str
    records: tuple[dict[str, Any], ...]
    records_sha256: Sha256
    planned_count: NonNegativeInt
    executed_count: NonNegativeInt
    admitted_count: NonNegativeInt
    rejected_count: NonNegativeInt
    not_executed_count: NonNegativeInt
    kind_counts: dict[str, NonNegativeInt]
    execution_scope: Literal["audit_only", "mixed", "executed"]

    @model_validator(mode="after")
    def _audit_counts_and_non_evidence(self) -> "DiscoveryCandidateAudit":
        if canonical_sha256(list(self.records)) != self.records_sha256:
            raise ValueError("discovery audit record hash mismatch")
        if self.planned_count != len(self.records):
            raise ValueError("discovery audit planned count mismatch")
        not_executed = [item for item in self.records if item.get("execution_mode") == "not_executed"]
        if len(not_executed) != self.not_executed_count:
            raise ValueError("discovery audit not-executed count mismatch")
        if self.executed_count + self.not_executed_count != self.planned_count:
            raise ValueError("discovery audit execution partition mismatch")
        if self.admitted_count + self.rejected_count != self.executed_count:
            raise ValueError("discovery audit executed partition mismatch")
        if self.admitted_count > self.executed_count or self.rejected_count > self.executed_count:
            raise ValueError("discovery audit decision count exceeds executed count")
        observed_kinds: dict[str, int] = {}
        for item in self.records:
            kind = str(item.get("probe_kind") or "unknown")
            observed_kinds[kind] = observed_kinds.get(kind, 0) + 1
        if dict(sorted(observed_kinds.items())) != dict(sorted(self.kind_counts.items())):
            raise ValueError("discovery audit kind counts mismatch")
        for item in not_executed:
            admission = item.get("admission") or {}
            if admission.get("existence_evidence") != "non_evidence":
                raise ValueError("not-executed discovery row cannot be existence evidence")
            if admission.get("admission_decision") != "not_executed":
                raise ValueError("not-executed discovery row cannot be admitted")
        expected_scope = (
            "audit_only"
            if self.not_executed_count == self.planned_count
            else "executed"
            if self.not_executed_count == 0
            else "mixed"
        )
        if self.execution_scope != expected_scope:
            raise ValueError("discovery audit execution scope mismatch")
        if self.execution_scope == "audit_only" and (
            self.executed_count != 0
            or self.admitted_count != 0
            or self.rejected_count != 0
            or self.not_executed_count != self.planned_count
        ):
            raise ValueError("audit-only discovery rows cannot be executed, admitted, or rejected")
        return self


class ObservedValueFlow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    flow_id: str
    producer_operation_id: str
    consumer_operation_id: str
    producer_request_ref: str
    consumer_request_ref: str
    producer_actor_id: str
    consumer_actor_id: str
    producer_session_run_id: str
    consumer_session_run_id: str
    producer_entry_index: int
    consumer_entry_index: int
    producer_timestamp: str
    consumer_timestamp: str
    from_location: str
    from_field: str
    to_location: str
    to_field: str
    same_session_proof: Literal[True] = True
    temporal_order_proof: Literal["producer_not_after_consumer"] = "producer_not_after_consumer"
    support_refs: tuple[dict[str, Any], ...]
    support_sha256: Sha256
    evidence_semantics: Literal["observed_candidate"] = "observed_candidate"
    grounded: Literal[False] = False

    @model_validator(mode="after")
    def _flow_identity_and_proof(self) -> "ObservedValueFlow":
        if self.producer_session_run_id != self.consumer_session_run_id:
            raise ValueError("observed value flow must be same-session")
        if self.producer_actor_id != self.consumer_actor_id:
            raise ValueError("same-session observed value flow actor mismatch")
        if not self.support_refs or canonical_sha256(list(self.support_refs)) != self.support_sha256:
            raise ValueError("observed value flow support hash mismatch")
        identity = self.model_dump(mode="json", exclude={"flow_id", "support_sha256"})
        expected = f"vf-{canonical_sha256(identity)[:24]}"
        if self.flow_id != expected:
            raise ValueError("observed value flow ID mismatch")
        return self


class ObservedValueFlowSet(Contract):
    artifact_type: Literal["observed_value_flow_set"] = "observed_value_flow_set"
    flow_set_id: str
    flows: tuple[ObservedValueFlow, ...]
    occurrence_count: int
    filtered_counts: dict[str, int]
    unresolved_observation_ref_count: int = 0
    extraction_algorithm: Literal["stage4_exact_literal_same_session_success_temporal_v1"] = (
        "stage4_exact_literal_same_session_success_temporal_v1"
    )

    @model_validator(mode="after")
    def _flow_set_closed(self) -> "ObservedValueFlowSet":
        if self.occurrence_count != len(self.flows):
            raise ValueError("observed value-flow occurrence count mismatch")
        ids = [item.flow_id for item in self.flows]
        if len(ids) != len(set(ids)):
            raise ValueError("observed value-flow IDs must be unique")
        if self.unresolved_observation_ref_count != 0:
            raise ValueError("observed value-flow set contains unresolved observation refs")
        if any(value < 0 for value in self.filtered_counts.values()):
            raise ValueError("observed value-flow filtered counts must be nonnegative")
        return self


class DependencyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    edge_id: str
    producer_operation_id: str
    consumer_operation_id: str
    kind: Literal["data", "auth"]
    deterministic_heuristic_score: float
    score_semantics: Literal["ranking_heuristic_not_statistical_confidence"] = (
        "ranking_heuristic_not_statistical_confidence"
    )
    evidence_channel_count: int
    observed_flow_count: int
    stage4_edge_sha256: Sha256
    grounded: Literal[False] = False


class DependencyGraph(Contract):
    artifact_type: Literal["dependency_graph"] = "dependency_graph"
    graph_id: str
    nodes: tuple[str, ...]
    edges: tuple[DependencyEdge, ...]
    edge_count: int
    evidence_channel_count: int
    observed_flow_count: int
    semantic_order_edge_count: Literal[0] = 0
    template_inference_edge_count: int = 0
    scheduled_probe_material_edge_count: int = 0
    observed_api_catalog_sha256: Sha256
    observed_value_flow_set_sha256: Sha256

    @model_validator(mode="after")
    def _graph_counts(self) -> "DependencyGraph":
        if self.edge_count != len(self.edges):
            raise ValueError("dependency graph edge count mismatch")
        if self.evidence_channel_count != sum(item.evidence_channel_count for item in self.edges):
            raise ValueError("dependency graph evidence-channel count mismatch")
        if self.observed_flow_count != sum(item.observed_flow_count for item in self.edges):
            raise ValueError("dependency graph observed-flow count mismatch")
        ids = [item.edge_id for item in self.edges]
        if len(ids) != len(set(ids)):
            raise ValueError("dependency graph edge IDs must be unique")
        nodes = set(self.nodes)
        if any(item.producer_operation_id not in nodes or item.consumer_operation_id not in nodes for item in self.edges):
            raise ValueError("dependency graph edge references unknown operation")
        return self


class BindingOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    opportunity_id: str
    producer_operation_id: str
    consumer_operation_id: str
    source_edge_kind: Literal["data", "auth"]
    effective_binding_kind: Literal["data", "auth"]
    from_location: str
    from_field: str
    to_location: str
    to_field: str
    value_flow_ids: tuple[str, ...]
    support_count: int
    witness_flow_id: str
    full_row_sha256: Sha256
    evidence_semantics: Literal["observed_candidate"] = "observed_candidate"
    grounded: Literal[False] = False

    @model_validator(mode="after")
    def _opportunity_hash_and_support(self) -> "BindingOpportunity":
        if self.support_count != len(self.value_flow_ids) or not self.value_flow_ids:
            raise ValueError("binding opportunity support count mismatch")
        if self.witness_flow_id != min(self.value_flow_ids):
            raise ValueError("binding opportunity witness must be the deterministic minimum flow ID")
        payload = self.model_dump(mode="json", exclude={"opportunity_id", "full_row_sha256"})
        expected_hash = canonical_sha256(payload)
        if self.full_row_sha256 != expected_hash:
            raise ValueError("binding opportunity full-row hash mismatch")
        if self.opportunity_id != f"bo-{expected_hash[:24]}":
            raise ValueError("binding opportunity ID mismatch")
        return self


class BindingOpportunitySet(Contract):
    artifact_type: Literal["binding_opportunity_set"] = "binding_opportunity_set"
    opportunity_set_id: str
    opportunities: tuple[BindingOpportunity, ...]
    opportunity_count: int
    support_reference_count: int
    observed_value_flow_set_sha256: Sha256
    dependency_graph_sha256: Sha256
    projection_algorithm: Literal["stage5_all_evidence_backed_binding_plans_v1"] = (
        "stage5_all_evidence_backed_binding_plans_v1"
    )

    @model_validator(mode="after")
    def _opportunity_counts(self) -> "BindingOpportunitySet":
        if self.opportunity_count != len(self.opportunities):
            raise ValueError("binding opportunity count mismatch")
        if self.support_reference_count != sum(item.support_count for item in self.opportunities):
            raise ValueError("binding opportunity support-reference count mismatch")
        ids = [item.opportunity_id for item in self.opportunities]
        if len(ids) != len(set(ids)):
            raise ValueError("binding opportunity IDs must be unique")
        return self


class UiTestAssertionOrigin(BaseModel):
    """Allowlisted provenance for one assertion from a versioned UI-test selection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    candidate_id: str = Field(min_length=1)
    system: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    framework: str = Field(min_length=1)
    assertion_kind: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_file_sha256: Sha256
    start_line: int = Field(ge=1)
    assertion: str = Field(min_length=1)
    assertion_sha256: Sha256

    @field_validator(
        "candidate_id", "system", "repository", "framework", "assertion_kind", "assertion"
    )
    @classmethod
    def _nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("UI-test assertion provenance strings must be nonblank")
        return value

    @field_validator("source_path")
    @classmethod
    def _relative_normalized_source_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        windows_path = PureWindowsPath(value)
        if (
            not value.strip()
            or not path.parts
            or "\\" in value
            or path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or path.as_posix() != value
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("UI-test source_path must be a normalized relative POSIX path")
        return value

    @model_validator(mode="after")
    def _assertion_hash(self) -> "UiTestAssertionOrigin":
        observed = hashlib.sha256(self.assertion.encode("utf-8")).hexdigest()
        if observed != self.assertion_sha256:
            raise ValueError("UI-test assertion SHA-256 does not match assertion UTF-8 bytes")
        return self


class UiTestAssertionSelectionCandidate(UiTestAssertionOrigin):
    """External frozen-selection row; unapproved fields are ignored and never projected."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class UiTestAssertionSelectionManifest(BaseModel):
    """Typed input allowlist for the canonical transfer evidence channel."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    schema_version: Literal["e1-transfer-sample-v1"]
    system: str = Field(min_length=1)
    selected_count: int = Field(ge=1)
    population_count: int = Field(ge=1)
    population_sha256: Sha256
    candidates: tuple[UiTestAssertionSelectionCandidate, ...]

    @field_validator("system")
    @classmethod
    def _nonblank_system(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("UI-test selection system must be nonblank")
        return value

    @model_validator(mode="after")
    def _selection_closed(self) -> "UiTestAssertionSelectionManifest":
        if self.selected_count != len(self.candidates):
            raise ValueError("UI-test selection selected_count must equal candidates length")
        if self.selected_count > self.population_count:
            raise ValueError("UI-test selection cannot exceed its population")
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("UI-test selection candidate IDs must be unique")
        if any(item.system != self.system for item in self.candidates):
            raise ValueError("UI-test selection candidate system must match manifest system")
        return self


class UiTestAssertionPopulationCandidate(UiTestAssertionOrigin):
    """External frozen-population row; only the allowlisted origin is trusted."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class UiTestAssertionPopulationManifest(BaseModel):
    """Typed trust root for a frozen UI-test assertion population."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    schema_version: Literal["e1-transfer-population-v1"]
    system: str = Field(min_length=1)
    candidate_count: int = Field(ge=1)
    candidates: tuple[UiTestAssertionPopulationCandidate, ...]

    @field_validator("system")
    @classmethod
    def _nonblank_system(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("UI-test population system must be nonblank")
        return value

    @model_validator(mode="after")
    def _population_closed(self) -> "UiTestAssertionPopulationManifest":
        if self.candidate_count != len(self.candidates):
            raise ValueError("UI-test population candidate_count must equal candidates length")
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("UI-test population candidate IDs must be unique")
        if any(item.system != self.system for item in self.candidates):
            raise ValueError("UI-test population candidate system must match manifest system")
        return self


class TransferSourceAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    source_sha256: Sha256
    source_location: str = Field(min_length=1)
    verbatim: str = Field(min_length=1)


class TransferEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    record_id: str = Field(min_length=1)
    source_kind: Literal["ui_test_assertion"]
    selection_schema_version: Literal["e1-transfer-sample-v1"]
    selection_manifest_sha256: Sha256
    population_schema_version: Literal["e1-transfer-population-v1"]
    population_manifest_sha256: Sha256
    origin: UiTestAssertionOrigin
    source_assertion: TransferSourceAssertion
    api_observation_refs: list[dict[str, Any]]

    @model_validator(mode="after")
    def _projection_matches_origin(self) -> "TransferEvidenceRecord":
        if self.record_id != self.origin.candidate_id:
            raise ValueError("transfer record ID must match UI-test assertion candidate ID")
        expected_location = f"{self.origin.source_path}:{self.origin.start_line}"
        if (
            self.source_assertion.source_sha256 != self.origin.assertion_sha256
            or self.source_assertion.source_location != expected_location
            or self.source_assertion.verbatim != self.origin.assertion
        ):
            raise ValueError("transfer assertion projection does not match allowlisted origin")
        return self


class UiDiffEvidenceRecord(BaseModel):
    """Observation-only visible-page change derived from two frozen snapshots."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    record_id: str = Field(min_length=1)
    source_kind: Literal["ui_page_visible_text_diff"]
    diff_rule: Literal["ordered_normalized_multiset_dom_text_v1"]
    event_ref: dict[str, Any]
    before_page_state_ref: dict[str, Any]
    before_page_state_sha256: Sha256
    after_page_state_ref: dict[str, Any]
    after_page_state_sha256: Sha256
    before_page_path: str
    after_page_path: str
    producer_request_refs: list[dict[str, Any]]
    consumer_request_refs: list[dict[str, Any]]
    added_text: list[str]
    removed_text: list[str]
    diff_sha256: Sha256

    @model_validator(mode="after")
    def _diff_is_closed(self) -> "UiDiffEvidenceRecord":
        if canonical_sha256({"added": self.added_text, "removed": self.removed_text}) != self.diff_sha256:
            raise ValueError("UI-diff text projection hash mismatch")
        if not self.producer_request_refs:
            raise ValueError("UI-diff record requires a producer request")
        return self


class EvidenceChannel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["available", "unavailable"]
    reason: str
    records: tuple[dict[str, Any], ...] = ()
    artifact_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def _availability_is_explicit(self) -> "EvidenceChannel":
        if not self.reason.strip():
            raise ValueError("evidence channel reason must be nonempty")
        if self.status == "available" and not self.records:
            raise ValueError("available evidence channel must contain records")
        if self.status == "available" and self.artifact_sha256 is None:
            raise ValueError("available evidence channel requires an artifact hash")
        if self.status == "unavailable" and self.records:
            raise ValueError("unavailable evidence channel cannot contain records")
        if self.status == "unavailable" and self.artifact_sha256 is not None:
            raise ValueError("unavailable evidence channel cannot carry an artifact hash")
        return self


class EvidenceBundle(Contract):
    artifact_type: Literal["evidence_bundle"] = "evidence_bundle"
    evidence_id: str
    trace_sha256: Sha256
    channels: dict[Literal["semantic", "ui_diff", "transfer"], EvidenceChannel]
    transfer_selection_ref: str | None = None
    transfer_selection_sha256: Sha256 | None = None
    transfer_population_ref: str | None = None
    transfer_population_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def _channel_contract(self) -> "EvidenceBundle":
        if set(self.channels) != {"semantic", "ui_diff", "transfer"}:
            raise ValueError("evidence bundle must declare all three channel states")
        if self.channels["semantic"].status != "available":
            raise ValueError("semantic is the required primary evidence channel")
        if (self.transfer_selection_ref is None) != (self.transfer_selection_sha256 is None):
            raise ValueError("transfer selection ref/hash must be supplied together")
        if (self.transfer_population_ref is None) != (self.transfer_population_sha256 is None):
            raise ValueError("transfer population ref/hash must be supplied together")
        if (self.transfer_selection_ref is None) != (self.transfer_population_ref is None):
            raise ValueError("transfer selection and population sources must be supplied together")
        transfer = self.channels["transfer"]
        ui_diff = self.channels["ui_diff"]
        if ui_diff.status == "available":
            typed_flags = [item.get("source_kind") == "ui_page_visible_text_diff" for item in ui_diff.records]
            if any(typed_flags) and not all(typed_flags):
                raise ValueError("UI-diff evidence cannot mix historical and typed current rows")
            if all(typed_flags):
                typed_ui_diff = tuple(
                    UiDiffEvidenceRecord.model_validate(item, strict=True)
                    for item in ui_diff.records
                )
                ids = [item.record_id for item in typed_ui_diff]
                if len(ids) != len(set(ids)):
                    raise ValueError("UI-diff evidence record IDs must be unique")
        selection_source_hash = self.source_sha256.get("ui_test_assertion_selection_manifest")
        population_source_hash = self.source_sha256.get("ui_test_assertion_population_manifest")
        if transfer.status == "available":
            if any(value is None for value in (
                self.transfer_selection_ref,
                self.transfer_selection_sha256,
                self.transfer_population_ref,
                self.transfer_population_sha256,
            )):
                raise ValueError("available transfer evidence requires typed selection and population sources")
            if self.transfer_selection_ref not in self.source_refs or self.transfer_population_ref not in self.source_refs:
                raise ValueError("transfer selection/population reference is absent from EvidenceBundle sources")
            if selection_source_hash != self.transfer_selection_sha256:
                raise ValueError("transfer selection source hash does not close")
            if population_source_hash != self.transfer_population_sha256:
                raise ValueError("transfer population source hash does not close")
            validated = tuple(TransferEvidenceRecord.model_validate(item) for item in transfer.records)
            ids = [item.record_id for item in validated]
            if len(ids) != len(set(ids)):
                raise ValueError("transfer evidence record IDs must be unique")
            if any(item.selection_manifest_sha256 != self.transfer_selection_sha256 for item in validated):
                raise ValueError("transfer evidence rows do not share the frozen selection hash")
            if any(item.population_manifest_sha256 != self.transfer_population_sha256 for item in validated):
                raise ValueError("transfer evidence rows do not share the frozen population hash")
        elif (
            self.transfer_selection_ref is not None
            or self.transfer_selection_sha256 is not None
            or self.transfer_population_ref is not None
            or self.transfer_population_sha256 is not None
            or selection_source_hash is not None
            or population_source_hash is not None
        ):
            raise ValueError("unavailable transfer evidence cannot claim selection/population sources")
        return self


PREPROPOSAL_REQUIRED_ARTIFACTS = frozenset({
    "recording_bundle",
    "ui_api_trace",
    "observational_api_structure",
    "observed_api_catalog",
    "discovery_candidate_audit",
    "evidence_bundle",
    "producer_applicability",
    "observed_value_flow_set",
    "dependency_graph",
    "binding_opportunity_set",
})
PREPROPOSAL_FORBIDDEN_SOURCES = frozenset({
    "author_labels",
    "old_proposals",
    "old_outcomes",
    "old_certificates",
    "external_spec",
    "backend_source",
    "semantic_edge_audit",
})


class PreProposalEvidencePackage(Contract):
    artifact_type: Literal["preproposal_evidence_package"] = "preproposal_evidence_package"
    package_id: str
    scientific_input_version: Literal["preproposal-evidence-v2"] = "preproposal-evidence-v2"
    artifact_sha256: dict[str, Sha256]
    artifact_payloads: dict[str, dict[str, Any]]
    channel_availability: dict[Literal["semantic", "ui_diff", "transfer"], Literal["available", "unavailable"]]
    counts: dict[str, int]
    forbidden_sources: tuple[str, ...]
    new_candidate_count: Literal[0] = 0
    new_provider_call_count: Literal[0] = 0
    new_route_s_result_count: Literal[0] = 0
    new_test_result_count: Literal[0] = 0

    @model_validator(mode="after")
    def _package_closed(self) -> "PreProposalEvidencePackage":
        if set(self.artifact_sha256) != PREPROPOSAL_REQUIRED_ARTIFACTS:
            raise ValueError("pre-proposal package required trunk is incomplete")
        if set(self.artifact_payloads) != PREPROPOSAL_REQUIRED_ARTIFACTS:
            raise ValueError("pre-proposal package payload trunk is incomplete")
        for name, payload in self.artifact_payloads.items():
            if canonical_sha256(payload) != self.artifact_sha256[name]:
                raise ValueError(f"pre-proposal package artifact hash mismatch: {name}")
        if set(self.channel_availability) != {"semantic", "ui_diff", "transfer"}:
            raise ValueError("pre-proposal package must declare all evidence channels")
        if self.channel_availability["semantic"] != "available":
            raise ValueError("pre-proposal package requires semantic evidence")
        if set(self.forbidden_sources) != PREPROPOSAL_FORBIDDEN_SOURCES:
            raise ValueError("pre-proposal package forbidden-source declaration mismatch")
        if any(value < 0 for value in self.counts.values()):
            raise ValueError("pre-proposal package counts must be nonnegative")
        return self


class CompactBindingOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    opportunity_id: str
    producer_operation_id: str
    consumer_operation_id: str
    effective_binding_kind: Literal["data", "auth"]
    from_location: str
    from_field: str
    to_location: str
    to_field: str
    full_row_sha256: Sha256
    support_count: int
    witness_flow_id: str


class CompactTransferAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    record_id: str
    source_kind: Literal["ui_test_assertion"]
    assertion_kind: str
    origin_ref: str
    assertion_sha256: Sha256
    subject_kind: str
    predicate_operator: str
    symbolic_intent: str
    api_observation_ref_count: NonNegativeInt
    full_row_sha256: Sha256
    projection_sha256: Sha256

    @model_validator(mode="after")
    def _projection_hash(self) -> "CompactTransferAssertion":
        payload = self.model_dump(mode="json", exclude={"projection_sha256"})
        if canonical_sha256(payload) != self.projection_sha256:
            raise ValueError("compact transfer projection hash mismatch")
        return self


class CompactUiDiff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    record_id: str
    event_id: str
    preceding_request_refs: list[str]
    following_request_refs: list[str]
    before_page_path: str
    after_page_path: str
    added_sanitized_text: list[str]
    removed_sanitized_text: list[str]
    added_total_count: NonNegativeInt
    removed_total_count: NonNegativeInt
    added_omitted_count: NonNegativeInt
    removed_omitted_count: NonNegativeInt

    @model_validator(mode="after")
    def _projection_partition(self) -> "CompactUiDiff":
        if len(self.added_sanitized_text) + self.added_omitted_count != self.added_total_count:
            raise ValueError("compact UI-diff added partition mismatch")
        if len(self.removed_sanitized_text) + self.removed_omitted_count != self.removed_total_count:
            raise ValueError("compact UI-diff removed partition mismatch")
        return self


class EvidenceCard(BaseModel):
    """One protocol-neutral context rooted only in recorded facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    card_id: str
    card_kind: Literal["action_episode", "unassigned_request", "mechanical_neighborhood"]
    component_card_ids: tuple[str, ...]
    request_refs: tuple[str, ...]
    actor_ids: tuple[str, ...]
    session_run_ids: tuple[str, ...]
    action_event_ids: tuple[str, ...]
    request_group_ids: tuple[str, ...]
    anchor_request_refs: tuple[str, ...]
    setup_domain_refs: tuple[str, ...]
    ui_diff_record_ids: tuple[str, ...]
    value_flow_ids: tuple[str, ...]
    dependency_edge_ids: tuple[str, ...]
    binding_opportunity_ids: tuple[str, ...]
    negative_request_fact_ids: tuple[str, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    root_request_ref: str | None = None
    neighborhood_summary: dict[str, Any] | None = None
    alias_scope: Literal["proposal_view_first_occurrence_v1"]

    @model_validator(mode="after")
    def _closed_card(self) -> "EvidenceCard":
        unique_fields = (
            self.component_card_ids,
            self.request_refs,
            self.actor_ids,
            self.session_run_ids,
            self.action_event_ids,
            self.request_group_ids,
            self.anchor_request_refs,
            self.setup_domain_refs,
            self.ui_diff_record_ids,
            self.value_flow_ids,
            self.dependency_edge_ids,
            self.binding_opportunity_ids,
            self.negative_request_fact_ids,
        )
        if any(len(value) != len(set(value)) for value in unique_fields):
            raise ValueError("evidence card references must be unique")
        if not self.request_refs or not self.actor_ids or not self.session_run_ids:
            raise ValueError("evidence card requires request, actor, and session refs")
        if not set(self.anchor_request_refs) <= set(self.request_refs):
            raise ValueError("evidence card anchor refs are outside its requests")
        if not set(self.setup_domain_refs) <= set(self.request_refs):
            raise ValueError("evidence card setup refs are outside its requests")
        if self.card_kind == "action_episode" and (
            len(self.action_event_ids) != 1
            or len(self.request_group_ids) != 1
            or self.component_card_ids
            or self.root_request_ref is not None
            or self.neighborhood_summary is not None
        ):
            raise ValueError("action episode card must close one request group")
        if self.card_kind == "unassigned_request" and (
            len(self.request_refs) != 1
            or self.action_event_ids
            or self.request_group_ids
            or self.component_card_ids
            or self.root_request_ref is not None
            or self.neighborhood_summary is not None
        ):
            raise ValueError("unassigned card must close one request")
        if self.card_kind == "mechanical_neighborhood":
            if len(self.component_card_ids) < 2:
                raise ValueError("mechanical neighborhood requires at least two atomic cards")
            if self.root_request_ref not in self.request_refs:
                raise ValueError("mechanical neighborhood root must remain visible")
            summary = self.neighborhood_summary
            if not isinstance(summary, dict):
                raise ValueError("mechanical neighborhood requires a boundary summary")
            required = {
                "relation_scope",
                "temporal_radius",
                "max_requests",
                "total_request_count",
                "visible_request_count",
                "omitted_request_count",
                "outside_temporal_radius_related_request_count",
            }
            if set(summary) != required:
                raise ValueError("mechanical neighborhood summary keys mismatch")
            if summary["relation_scope"] not in {
                "one_hop_recording_facts_v1",   # full evidence organization
                "temporal_window_only_v1",      # RQ3 ablation: no association expansion
            }:
                raise ValueError("mechanical neighborhood relation scope mismatch")
            counts = tuple(
                summary[key]
                for key in required - {"relation_scope"}
            )
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("mechanical neighborhood boundary values must be nonnegative integers")
            if summary["visible_request_count"] != len(self.request_refs):
                raise ValueError("mechanical neighborhood visible count mismatch")
            if summary["total_request_count"] != (
                summary["visible_request_count"] + summary["omitted_request_count"]
            ):
                raise ValueError("mechanical neighborhood partition mismatch")
        payload = self.model_dump(mode="json", exclude={"card_id"})
        if self.card_id != f"evidence-card-{canonical_sha256(payload)[:24]}":
            raise ValueError("evidence card ID mismatch")
        return self


class CompactChannelProjection(BaseModel):
    """The current provider-visible semantic projection for one evidence channel."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    revision: Literal["aux-semantic-projection-v1"]
    channel: Literal["transfer", "ui_diff"]
    source_records_sha256: Sha256
    total_count: NonNegativeInt
    visible_count: NonNegativeInt
    omitted_count: NonNegativeInt
    ordering_rule: Literal["record_id_asc_all_v1"]
    rows: list[dict[str, Any]]
    projection_sha256: Sha256

    @model_validator(mode="after")
    def _closed_projection(self) -> "CompactChannelProjection":
        if self.visible_count != len(self.rows):
            raise ValueError("compact channel visible count mismatch")
        if self.visible_count + self.omitted_count != self.total_count:
            raise ValueError("compact channel partition mismatch")
        ids: list[str] = []
        for row in self.rows:
            typed = (
                CompactTransferAssertion.model_validate(row, strict=True)
                if self.channel == "transfer"
                else CompactUiDiff.model_validate(row, strict=True)
            )
            ids.append(typed.record_id)
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("compact channel rows must be unique and ordered by record_id")
        payload = self.model_dump(mode="json", exclude={"projection_sha256"})
        if canonical_sha256(payload) != self.projection_sha256:
            raise ValueError("compact channel projection hash mismatch")
        return self


class TransitionLocatorWitness(BaseModel):
    """One exact M6 witness that makes a collection-member locator executable."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    flow_id: str = Field(pattern=r"^vf-[0-9a-f]{24}$")
    request_ref: str = Field(min_length=1)
    to_location: Literal["path", "query", "body"]
    to_field: str = Field(min_length=1)
    operand_role: Literal["producer_request", "producer_response"]
    operand_path: str = Field(pattern=r"^\$")


class TransitionMemberIdentityStateEvidence(BaseModel):
    """Value-free identity and state evidence for one collection transition."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    value_ref: str = Field(pattern=r"^scalar-sha256:[0-9a-f]{64}$")
    value_type: Literal["string", "integer"]
    member_path: str = Field(pattern=r"^\$")
    request_location: Literal["path", "query", "body"]
    request_path: str = Field(min_length=1)
    response_identity_path: str = Field(pattern=r"^\$")
    response_state_path: str = Field(pattern=r"^\$")
    response_state_value: bool
    transition_direction: Literal["added", "removed"]
    flow_ids: tuple[str, ...] = ()


class TransitionWriteAssessment(BaseModel):
    """One compact, neutral relevance assessment for an in-window write."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    request_ref: str = Field(min_length=1)
    global_order: int = Field(ge=0)
    operation_id: str = Field(min_length=1)
    canonical_path: str = Field(min_length=1)
    classification: Literal[
        "target_relevant", "potentially_relevant", "target_irrelevant"
    ]
    reason_code: Literal[
        "collection_membership_write",
        "member_identity_and_state_evidence",
        "target_field_resource_flow",
        "target_field_graphql_operation",
        "distinct_collection_descendant",
        "explicit_other_field_write",
        "disjoint_target_resource",
        "target_relation_unproven",
    ]
    provenance_refs: tuple[str, ...] = ()
    member_identity_state_evidence: TransitionMemberIdentityStateEvidence | None = None

    @model_validator(mode="after")
    def _identity_state_evidence_matches_reason(self) -> "TransitionWriteAssessment":
        has_evidence = self.member_identity_state_evidence is not None
        if (self.reason_code == "member_identity_and_state_evidence") != has_evidence:
            raise ValueError("transition member identity/state evidence mismatch")
        if has_evidence and self.classification != "target_relevant":
            raise ValueError("transition member identity/state evidence must be relevant")
        return self


class TransitionWriteCompetition(BaseModel):
    """Compact M9 provenance for exact single-write transition grounding."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    revision: Literal["target-resource-field-competition-v2"]
    interval_state_change_request_count: int = Field(ge=0)
    target_relevant_request_refs: tuple[str, ...]
    potentially_relevant_request_refs: tuple[str, ...]
    target_irrelevant_request_count: int = Field(ge=0)
    assessments: tuple[TransitionWriteAssessment, ...]
    grounding_status: Literal["unique_target_relevant", "ambiguous"]
    groundable_effect_source_request_ref: str | None
    reason_code: Literal[
        "unique_target_relevant_write",
        "no_target_relevant_write",
        "multiple_target_relevant_writes",
        "potential_competitor_present",
        "unique_target_write_lacks_locator_operand",
    ]

    @model_validator(mode="after")
    def _competition_is_closed(self) -> "TransitionWriteCompetition":
        refs = [row.request_ref for row in self.assessments]
        if (
            len(refs) != len(set(refs))
            or list(self.assessments) != sorted(
                self.assessments,
                key=lambda row: (row.global_order, row.request_ref),
            )
        ):
            raise ValueError("transition write assessments must be unique and ordered")
        relevant = tuple(
            row.request_ref
            for row in self.assessments
            if row.classification == "target_relevant"
        )
        possible = tuple(
            row.request_ref
            for row in self.assessments
            if row.classification == "potentially_relevant"
        )
        irrelevant_count = sum(
            row.classification == "target_irrelevant" for row in self.assessments
        )
        if (
            self.interval_state_change_request_count != len(self.assessments)
            or self.target_relevant_request_refs != relevant
            or self.potentially_relevant_request_refs != possible
            or self.target_irrelevant_request_count != irrelevant_count
        ):
            raise ValueError("transition write competition counts do not close")
        uniquely_groundable = (
            len(relevant) == 1
            and not possible
            and self.groundable_effect_source_request_ref == relevant[0]
        )
        if (self.grounding_status == "unique_target_relevant") != uniquely_groundable:
            raise ValueError("transition write grounding status mismatch")
        if self.grounding_status == "ambiguous" and (
            self.groundable_effect_source_request_ref is not None
        ):
            raise ValueError("ambiguous transition cannot name an effect source")
        return self


class TypedTransitionFact(BaseModel):
    """One neutral, strictly typed before/after observation for M10 detail."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    fact_id: str = Field(pattern=r"^transition-fact-[0-9a-f]{24}$")
    observation_kind: Literal["scalar", "collection_count", "collection_member"]
    before_request_ref: str = Field(min_length=1)
    after_request_ref: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    session_run_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    selector_snapshot_sha256: Sha256
    target_path: str = Field(pattern=r"^\$")
    value_type: Literal["boolean", "integer", "number"]
    before_value: bool | int | float
    after_value: bool | int | float
    signed_delta: int | float | None
    identity: dict[str, Any]
    locator_witness: TransitionLocatorWitness | None = None
    write_competition: TransitionWriteCompetition

    @model_validator(mode="after")
    def _transition_is_closed(self) -> "TypedTransitionFact":
        expected_type = {
            bool: "boolean",
            int: "integer",
            float: "number",
        }
        if (
            expected_type.get(type(self.before_value)) != self.value_type
            or expected_type.get(type(self.after_value)) != self.value_type
        ):
            raise ValueError("transition values must have one exact JSON type")
        if any(
            isinstance(value, float) and not math.isfinite(value)
            for value in (self.before_value, self.after_value, self.signed_delta)
        ):
            raise ValueError("transition values must be finite")
        if self.before_value == self.after_value:
            raise ValueError("transition fact must record a change")
        expected_delta: int | float | None = None
        if self.value_type in {"integer", "number"}:
            expected_delta = self.after_value - self.before_value
        elif self.observation_kind == "collection_member":
            expected_delta = int(self.after_value) - int(self.before_value)
        if type(self.signed_delta) is not type(expected_delta) or self.signed_delta != expected_delta:
            raise ValueError("transition signed delta mismatch")
        identity_keys = {
            "resource": {"kind", "path", "json_type", "value_ref"},
            "collection": {"kind", "collection_path"},
            "collection_member": {
                "kind",
                "collection_path",
                "member_path",
                "json_type",
                "value_ref",
            },
        }
        kind = self.identity.get("kind")
        if kind not in identity_keys or set(self.identity) != identity_keys[kind]:
            raise ValueError("transition identity is not a closed mechanical identity")
        if (kind == "collection_member") != (self.locator_witness is not None):
            raise ValueError(
                "collection-member transition identity requires one executable locator witness"
            )
        if "value_ref" in self.identity and not str(
            self.identity["value_ref"]
        ).startswith("scalar-sha256:"):
            raise ValueError("transition identity lacks a stable value ref")
        payload = self.model_dump(mode="json", exclude={"fact_id"})
        if self.locator_witness is None:
            payload.pop("locator_witness")
        expected_id = f"transition-fact-{canonical_sha256(payload)[:24]}"
        if self.fact_id != expected_id:
            raise ValueError("transition fact ID mismatch")
        return self


class FrozenBusinessProjection(BaseModel):
    """One result-independent business projection frozen from recorded reads."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    projection_ref: str = Field(pattern=r"^state-projection-[0-9a-f]{24}$")
    before_request_ref: str = Field(min_length=1)
    after_request_ref: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    resource_identity: Literal[
        "exact_recorded_request_target_equal_value_not_persisted"
    ]
    path: str = Field(pattern=r"^\$")
    value_type: Literal[
        "object", "array", "string", "number", "integer", "boolean", "null"
    ]
    normalization: Literal[
        "typed_canonical_json_object_keys_array_order_preserved_no_coercion"
    ]
    excluded_paths: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _projection_id_is_content_addressed(self) -> "FrozenBusinessProjection":
        if self.excluded_paths:
            raise ValueError("current P20 does not permit adaptive excluded paths")
        payload = self.model_dump(mode="json", exclude={"projection_ref"})
        expected = f"state-projection-{canonical_sha256(payload)[:24]}"
        if self.projection_ref != expected:
            raise ValueError("state projection ID mismatch")
        return self


class NegativeRequestFact(BaseModel):
    """Neutral recorded evidence for one rejected request and state window."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    fact_id: str = Field(pattern=r"^negative-request-fact-[0-9a-f]{24}$")
    actor_id: str = Field(min_length=1)
    session_run_id: str = Field(min_length=1)
    setup_request_ref: str = Field(min_length=1)
    negative_request_ref: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    duplicate_input: dict[str, Any]
    rejection_detector: dict[str, str]
    response_status: int = Field(ge=400, le=499)
    error_response_paths: tuple[str, ...]
    context_mode: Literal["auth_absent", "auth_preserved"] = "auth_absent"
    session_boundary_event_id: str = Field(min_length=1)
    projection: FrozenBusinessProjection

    @model_validator(mode="after")
    def _negative_fact_is_closed(self) -> "NegativeRequestFact":
        if set(self.duplicate_input) != {
            "source_path", "target_path", "value_type", "comparison"
        }:
            raise ValueError("negative duplicate-input witness keys mismatch")
        if (
            self.duplicate_input["source_path"]
            != self.duplicate_input["target_path"]
            or self.duplicate_input["value_type"] not in {
                "string", "integer", "number", "boolean", "null"
            }
            or self.duplicate_input["comparison"]
            != "strict_json_scalar_equal_value_not_persisted"
        ):
            raise ValueError("negative duplicate-input witness is not exact")
        if self.rejection_detector != {
            "kind": "http_status_class",
            "expected_class": "client_error",
        }:
            raise ValueError("negative rejection detector must be client-error class")
        if not self.error_response_paths or len(self.error_response_paths) != len(
            set(self.error_response_paths)
        ):
            raise ValueError("negative fact requires unique error-response evidence")
        if self.context_mode not in {"auth_absent", "auth_preserved"}:
            raise ValueError("negative context mode is unsupported")
        payload = self.model_dump(
            mode="json", exclude={"fact_id", "context_mode"}
        )
        expected = f"negative-request-fact-{canonical_sha256(payload)[:24]}"
        if self.fact_id != expected:
            raise ValueError("negative request fact ID mismatch")
        return self


class ProposalEvidenceView(Contract):
    artifact_type: Literal["proposal_evidence_view"] = "proposal_evidence_view"
    view_id: str
    scientific_input_version: Literal["preproposal-evidence-v2"] = "preproposal-evidence-v2"
    package_sha256: Sha256
    observed_api_catalog_sha256: Sha256
    observed_value_flow_set_sha256: Sha256
    dependency_graph_sha256: Sha256
    binding_opportunity_set_sha256: Sha256
    trace_summary: dict[str, int]
    ui_actions: tuple[dict[str, Any], ...]
    api_requests: tuple[dict[str, Any], ...]
    automatic_bindings: tuple[dict[str, Any], ...]
    binding_reviews: tuple[dict[str, Any], ...]
    evidence_cards: tuple[EvidenceCard, ...]
    proposal_target_card_ids: tuple[str, ...]
    relation_language: tuple[dict[str, Any], ...]
    evidence_channel_summaries: dict[str, dict[str, Any]]
    setup_action_catalog: tuple[str, ...]
    request_setup_domains: dict[str, dict[str, Any]]
    setup_selection_clues: dict[str, dict[str, Any]]
    transition_facts: tuple[TypedTransitionFact, ...] = ()
    negative_request_facts: tuple[NegativeRequestFact, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    api_operations: tuple[dict[str, Any], ...]
    discovery_audit_summary: dict[str, Any]
    channel_availability: dict[str, str]
    request_setup_eligibility_summary: dict[str, int]
    observed_value_flows: tuple[dict[str, Any], ...]
    dependency_edges: tuple[dict[str, Any], ...]
    binding_opportunities: tuple[CompactBindingOpportunity, ...]
    value_flow_occurrence_count: int
    # RQ3 ablation switch: "association" is the full evidence organization;
    # "temporal" removes every explicit association structure (value flows,
    # dependency edges, binding opportunities, transition facts, flow-backed
    # setup clues) and builds neighborhoods from the temporal window only;
    # "flat" additionally drops the UI-action grouping (one card per request),
    # every neighborhood, the page-change rows and the negative request facts,
    # leaving the normalized requests in recording order.
    # Serialized only when it differs from the default so that every
    # association view keeps its historical canonical hash.
    evidence_organization: Literal["association", "temporal", "flat"] = Field(
        default="association", exclude_if=lambda value: value == "association"
    )

    @model_validator(mode="after")
    def _view_counts(self) -> "ProposalEvidenceView":
        if set(self.channel_availability) != {"semantic", "ui_diff", "transfer"}:
            raise ValueError("proposal view must declare all evidence channels")
        expected_trace_counts = {
            "events": len(self.ui_actions),
            "admitted_requests": len(self.api_requests),
            "automatic_bindings": len(self.automatic_bindings),
            "review_required": len(self.binding_reviews),
        }
        if self.trace_summary != expected_trace_counts:
            raise ValueError("proposal view trace summary mismatch")
        if set(self.evidence_channel_summaries) != {"semantic", "ui_diff", "transfer"}:
            raise ValueError("proposal view evidence summaries must cover all channels")
        for channel in ("transfer", "ui_diff"):
            summary = self.evidence_channel_summaries[channel]
            projection = summary.get("semantic_projection")
            if projection is not None:
                typed = CompactChannelProjection.model_validate(projection, strict=True)
                if typed.channel != channel:
                    raise ValueError("compact channel projection is attached to the wrong channel")
                if typed.total_count != summary.get("record_count"):
                    raise ValueError("compact channel total does not match evidence summary")
                if typed.source_records_sha256 != summary.get("records_sha256"):
                    raise ValueError("compact channel source record hash does not close")

        request_by_ref = {
            str(item.get("request_ref")): item for item in self.api_requests
        }
        request_refs = set(request_by_ref)
        value_flow_by_id = {
            str(item.get("flow_id")): item for item in self.observed_value_flows
        }
        value_flow_ids = set(value_flow_by_id)
        dependency_edge_ids = {
            str(item.get("edge_id")) for item in self.dependency_edges
        }
        transition_ids = [item.fact_id for item in self.transition_facts]
        if transition_ids != sorted(transition_ids) or len(transition_ids) != len(
            set(transition_ids)
        ):
            raise ValueError("transition facts must be unique and ordered")
        for fact in self.transition_facts:
            before = request_by_ref.get(fact.before_request_ref)
            after = request_by_ref.get(fact.after_request_ref)
            if before is None or after is None:
                raise ValueError("transition fact references an unknown request")
            if not (
                before["actor_id"] == after["actor_id"] == fact.actor_id
                and before["session_run_id"]
                == after["session_run_id"]
                == fact.session_run_id
                and before["operation_id"]
                == after["operation_id"]
                == fact.operation_id
                and int(before["global_order"]) < int(after["global_order"])
            ):
                raise ValueError("transition fact is not one ordered comparable read pair")
            witness = fact.locator_witness
            if witness is not None:
                target = request_by_ref.get(witness.request_ref)
                if (
                    target is None
                    or witness.flow_id not in value_flow_ids
                    or not int(before["global_order"])
                    < int(target["global_order"])
                    < int(after["global_order"])
                ):
                    raise ValueError(
                        "transition locator witness is not one observed in-window flow"
                    )
            competition = fact.write_competition
            for assessment in competition.assessments:
                write = request_by_ref.get(assessment.request_ref)
                if (
                    write is None
                    or not int(before["global_order"])
                    < int(write["global_order"])
                    < int(after["global_order"])
                    or int(write["global_order"]) != assessment.global_order
                    or write["operation_id"] != assessment.operation_id
                    or write["canonical_path"] != assessment.canonical_path
                    or "state_change_like"
                    not in set(map(str, write.get("weak_roles", ())))
                    or not set(assessment.provenance_refs)
                    <= value_flow_ids | dependency_edge_ids
                ):
                    raise ValueError(
                        "transition write competition references invalid provenance"
                    )
            groundable = competition.groundable_effect_source_request_ref
            if witness is not None and groundable is not None and (
                witness.request_ref != groundable
            ):
                raise ValueError(
                    "located transition groundable write must own the locator operand"
                )
        negative_ids = [item.fact_id for item in self.negative_request_facts]
        if negative_ids != sorted(negative_ids) or len(negative_ids) != len(
            set(negative_ids)
        ):
            raise ValueError("negative request facts must be unique and ordered")
        known_action_ids = {
            str(item.get("event_id")) for item in self.ui_actions
        }
        for fact in self.negative_request_facts:
            setup = request_by_ref.get(fact.setup_request_ref)
            negative = request_by_ref.get(fact.negative_request_ref)
            before = request_by_ref.get(fact.projection.before_request_ref)
            after = request_by_ref.get(fact.projection.after_request_ref)
            if any(item is None for item in (setup, negative, before, after)):
                raise ValueError("negative request fact references an unknown request")
            assert setup is not None and negative is not None
            assert before is not None and after is not None
            if not (
                setup["actor_id"] == negative["actor_id"] == fact.actor_id
                and setup["session_run_id"]
                == negative["session_run_id"]
                == fact.session_run_id
                and setup["operation_id"]
                == negative["operation_id"]
                == fact.operation_id
                and int(setup["global_order"])
                < int(before["global_order"])
                < int(negative["global_order"])
                and (
                    int(negative["global_order"]) < int(after["global_order"])
                    or (
                        fact.projection.before_request_ref == fact.projection.after_request_ref
                        and before.get("method") in {"GET", "HEAD", "OPTIONS"}
                        and type(before.get("response_status")) is int
                        and 200 <= before["response_status"] < 300
                    )
                )
                and before["actor_id"] == after["actor_id"] == fact.actor_id
                and before["session_run_id"]
                == after["session_run_id"]
                == fact.session_run_id
                and before["operation_id"]
                == after["operation_id"]
                == fact.projection.operation_id
                and fact.session_boundary_event_id in known_action_ids
            ):
                raise ValueError("negative request fact order or scope mismatch")
        if set(self.request_setup_domains) != request_refs:
            raise ValueError("every admitted request requires one setup-domain status")
        action_order = {
            str(item.get("event_id")): int(item.get("global_order"))
            for item in self.ui_actions
        }
        if (
            len(self.setup_action_catalog) != len(set(self.setup_action_catalog))
            or not set(self.setup_action_catalog) <= set(action_order)
            or list(self.setup_action_catalog) != sorted(
                self.setup_action_catalog,
                key=lambda ref: (action_order[ref], ref),
            )
        ):
            raise ValueError("setup action catalog must be unique, recorded-order, and observed")
        allowed_setup_actions = set(self.setup_action_catalog)
        for request_ref, domain in self.request_setup_domains.items():
            if domain.get("target_request_ref") != request_ref:
                raise ValueError("setup eligibility target request mismatch")
            if set(domain) - {
                "status",
                "target_request_ref",
                "target_anchor",
                "eligible_setup_action_ids",
                "bound",
                "profile_managed",
                "reason",
            }:
                raise ValueError("provider setup eligibility contains noncompact fields")
            selected = domain.get("eligible_setup_action_ids") or []
            if len(selected) != len(set(selected)) or not set(selected) <= allowed_setup_actions:
                raise ValueError("request setup actions must reference the compact catalog")
            bound = domain.get("bound") or {}
            if set(bound) != {"max_requests", "truncated_request_count"}:
                raise ValueError("request setup bound mismatch")
            profile_managed = domain.get("profile_managed") or {}
            if set(profile_managed) != {"active", "request_count"}:
                raise ValueError("request profile-managed summary mismatch")
        for request_ref, clue in self.setup_selection_clues.items():
            if request_ref not in request_refs:
                raise ValueError("setup-selection clue references an unknown target request")
            if set(clue) != {
                "observation_kind",
                "target_request_ref",
                "target_locator",
                "resource_observation",
                "candidate_setup_actions",
                "bound",
            }:
                raise ValueError("setup-selection clue keys mismatch")
            if clue["target_request_ref"] != request_ref:
                raise ValueError("setup-selection clue target mismatch")
            domain = self.request_setup_domains[request_ref]
            if domain.get("status") != "available":
                raise ValueError("setup-selection clue target is not setup-eligible")
            locator = clue["target_locator"]
            if set(locator) != {
                "value_ref",
                "json_type",
                "request_paths",
                "collection_item_path",
            }:
                raise ValueError("setup-selection locator keys mismatch")
            if not str(locator["value_ref"]).startswith("scalar-sha256:"):
                raise ValueError("setup-selection locator lacks a stable value ref")
            if (
                not locator["request_paths"]
                or len(locator["request_paths"]) != len(set(locator["request_paths"]))
            ):
                raise ValueError("setup-selection locator paths must be nonempty and unique")
            observation = clue["resource_observation"]
            if clue["observation_kind"] == "absent_to_present":
                if set(observation) != {
                    "actor_id",
                    "session_run_id",
                    "operation_id",
                    "collection_path",
                    "selector_snapshot_sha256",
                    "previous_read_ref",
                    "previous_observed_contains_member",
                    "first_seen_read_ref",
                    "first_observed_contains_member",
                    "member_fields",
                }:
                    raise ValueError(
                        "setup-selection resource observation keys mismatch"
                    )
                previous_ref = str(observation["previous_read_ref"])
                first_seen_ref = str(observation["first_seen_read_ref"])
                if (
                    previous_ref not in request_refs
                    or first_seen_ref not in request_refs
                ):
                    raise ValueError(
                        "setup-selection observation references an unknown request"
                    )
                previous = request_by_ref[previous_ref]
                first_seen = request_by_ref[first_seen_ref]
                if not (
                    observation["previous_observed_contains_member"] is False
                    and observation["first_observed_contains_member"] is True
                    and previous["actor_id"]
                    == first_seen["actor_id"]
                    == observation["actor_id"]
                    and previous["session_run_id"]
                    == first_seen["session_run_id"]
                    == observation["session_run_id"]
                    and previous["operation_id"]
                    == first_seen["operation_id"]
                    == observation["operation_id"]
                    and int(previous["global_order"])
                    < int(first_seen["global_order"])
                    < int(request_by_ref[request_ref]["global_order"])
                ):
                    raise ValueError(
                        "setup-selection observation is not one comparable absent-to-present transition"
                    )
            elif clue["observation_kind"] == "recorded_locator_lineage":
                if set(observation) != {
                    "actor_id",
                    "session_run_id",
                    "source_request_refs",
                    "locator_flows",
                    "member_fields",
                }:
                    raise ValueError(
                        "setup-selection locator-lineage observation keys mismatch"
                    )
                target = request_by_ref[request_ref]
                if not (
                    observation["actor_id"] == target["actor_id"]
                    and observation["session_run_id"]
                    == target["session_run_id"]
                ):
                    raise ValueError(
                        "setup-selection locator lineage target mismatch"
                    )
                source_refs = list(map(str, observation["source_request_refs"]))
                if (
                    not source_refs
                    or source_refs != sorted(set(source_refs))
                    or not set(source_refs) <= request_refs
                ):
                    raise ValueError(
                        "setup-selection locator lineage sources are invalid"
                    )
                expected_sources: set[str] = set()
                flow_keys: list[tuple[str, str, str]] = []
                for projected in observation["locator_flows"]:
                    if set(projected) != {
                        "flow_id",
                        "source_request_ref",
                        "source_operation_id",
                        "source_response_path",
                        "target_location",
                        "target_field",
                    }:
                        raise ValueError(
                            "setup-selection locator flow keys mismatch"
                        )
                    flow = value_flow_by_id.get(str(projected["flow_id"]))
                    if not (
                        flow
                        and flow.get("consumer_request_ref") == request_ref
                        and flow.get("producer_request_ref")
                        == projected["source_request_ref"]
                        and flow.get("producer_operation_id")
                        == projected["source_operation_id"]
                        and re.sub(r"\[\d+\]", "[*]", str(flow.get("from_field")))
                        == projected["source_response_path"]
                        and flow.get("to_location") == projected["target_location"]
                        and flow.get("to_field") == projected["target_field"]
                    ):
                        raise ValueError(
                            "setup-selection locator flow is not an exact M6 fact"
                        )
                    expected_sources.add(str(projected["source_request_ref"]))
                    flow_keys.append(
                        (
                            str(projected["source_request_ref"]),
                            str(projected["source_response_path"]),
                            str(projected["flow_id"]),
                        )
                    )
                if (
                    source_refs != sorted(expected_sources)
                    or flow_keys != sorted(set(flow_keys))
                ):
                    raise ValueError(
                        "setup-selection locator flows are not unique and ordered"
                    )
            else:
                raise ValueError("unknown setup-selection observation kind")
            member_fields = observation["member_fields"]
            if not member_fields or any(
                not {"path", "json_type", "value_ref"} <= set(row)
                or set(row) - {"path", "json_type", "value_ref", "stable_alias", "visible_literal"}
                or not str(row.get("value_ref", "")).startswith("scalar-sha256:")
                for row in member_fields
            ):
                raise ValueError("setup-selection member projection is invalid")
            actions = clue["candidate_setup_actions"]
            action_ids = [str(row.get("setup_action_id")) for row in actions]
            if (
                len(action_ids) != len(set(action_ids))
                or not set(action_ids) <= set(domain.get("eligible_setup_action_ids") or ())
                or action_ids != sorted(action_ids, key=lambda ref: (action_order[ref], ref))
            ):
                raise ValueError("setup-selection candidate actions are outside the ordered setup domain")
            for row in actions:
                if set(row) != {
                    "setup_action_id",
                    "global_order",
                    "actor_id",
                    "ui_action",
                    "state_change_requests",
                }:
                    raise ValueError("setup-selection action keys mismatch")
                if set(row["ui_action"]) != {
                    "action_type",
                    "selector",
                    "visible_element",
                }:
                    raise ValueError("setup-selection UI action keys mismatch")
                if int(row["global_order"]) != action_order[row["setup_action_id"]]:
                    raise ValueError("setup-selection action order mismatch")
                if not row["state_change_requests"]:
                    raise ValueError("setup-selection action lacks a state-change request")
                for request in row["state_change_requests"]:
                    if set(request) != {
                        "request_ref",
                        "global_order",
                        "method",
                        "operation_id",
                        "response_status",
                        "request_group_id",
                        "weak_roles",
                        "resource_identity_overlaps",
                    }:
                        raise ValueError("setup-selection request fact keys mismatch")
                    request_row = request_by_ref.get(str(request["request_ref"]))
                    if (
                        request_row is None
                        or request_row.get("action_event_id") != row["setup_action_id"]
                        or "state_change_like" not in request["weak_roles"]
                    ):
                        raise ValueError("setup-selection request is not a recorded state-change fact")
                    member_rows_by_ref: dict[str, list[dict[str, Any]]] = {}
                    for member in member_fields:
                        member_rows_by_ref.setdefault(
                            str(member["value_ref"]), []
                        ).append(member)
                    overlap_keys = []
                    for overlap in request["resource_identity_overlaps"]:
                        if set(overlap) != {
                            "member_path",
                            "observed_path",
                            "value_ref",
                        }:
                            raise ValueError(
                                "setup-selection identity-overlap keys mismatch"
                            )
                        value_ref = str(overlap["value_ref"])
                        matching_members = member_rows_by_ref.get(value_ref, [])
                        member = (
                            matching_members[0]
                            if len(matching_members) == 1
                            else None
                        )
                        observed_path = str(overlap["observed_path"])
                        observed_path_closed = (
                            observed_path.startswith(
                                ("request_body:$", "request_query:$", "response_body:$")
                            )
                            or re.fullmatch(
                                r"request_path:segment\[[0-9]+\]", observed_path
                            )
                            is not None
                        )
                        if (
                            member is None
                            or member["path"] != overlap["member_path"]
                            or not observed_path_closed
                        ):
                            raise ValueError(
                                "setup-selection identity overlap is not closed"
                            )
                        overlap_keys.append((
                            overlap["member_path"], overlap["observed_path"]
                        ))
                    if (
                        overlap_keys != sorted(overlap_keys)
                        or len(overlap_keys) != len(set(overlap_keys))
                    ):
                        raise ValueError(
                            "setup-selection identity overlaps must be unique and ordered"
                        )
            if clue["bound"] != domain["bound"]:
                raise ValueError("setup-selection clue must reuse the setup-domain bound")
        flow_ids = {str(item.get("flow_id")) for item in self.observed_value_flows}
        if len(flow_ids) != len(self.observed_value_flows):
            raise ValueError("observed value-flow IDs must be unique")
        if len(self.observed_value_flows) != self.value_flow_occurrence_count:
            raise ValueError("proposal view value-flow count mismatch")
        edge_ids = {str(item.get("edge_id")) for item in self.dependency_edges}
        binding_ids = {item.opportunity_id for item in self.binding_opportunities}
        ui_diff_ids = {
            str(item.get("record_id"))
            for item in (
                self.evidence_channel_summaries
                .get("ui_diff", {})
                .get("semantic_projection", {})
                .get("rows", ())
            )
        }
        action_ids = {str(item.get("event_id")) for item in self.ui_actions}
        group_ids = {
            str(item.get("request_group_id"))
            for item in self.api_requests
            if item.get("request_group_id") is not None
        }

        card_ids = [item.card_id for item in self.evidence_cards]
        if card_ids != sorted(card_ids) or len(card_ids) != len(set(card_ids)):
            raise ValueError("evidence cards must be unique and ordered by card ID")
        if (
            list(self.proposal_target_card_ids) != sorted(self.proposal_target_card_ids)
            or len(self.proposal_target_card_ids) != len(set(self.proposal_target_card_ids))
            or not set(self.proposal_target_card_ids) <= set(card_ids)
        ):
            raise ValueError("proposal target cards must be unique, ordered, and present")
        atomic_membership = {request_ref: 0 for request_ref in request_refs}
        for card in self.evidence_cards:
            if not set(card.request_refs) <= request_refs:
                raise ValueError("evidence card references an unknown request")
            if not set(card.action_event_ids) <= action_ids:
                raise ValueError("evidence card references an unknown action")
            if not set(card.request_group_ids) <= group_ids:
                raise ValueError("evidence card references an unknown request group")
            if not set(card.setup_domain_refs) <= request_refs:
                raise ValueError("evidence card references an unknown setup domain")
            if not set(card.ui_diff_record_ids) <= ui_diff_ids:
                raise ValueError("evidence card references an unavailable UI diff")
            if not set(card.value_flow_ids) <= flow_ids:
                raise ValueError("evidence card references an unknown value flow")
            if not set(card.dependency_edge_ids) <= edge_ids:
                raise ValueError("evidence card references an unknown dependency edge")
            if not set(card.binding_opportunity_ids) <= binding_ids:
                raise ValueError("evidence card references an unknown binding opportunity")
            if not set(card.negative_request_fact_ids) <= set(negative_ids):
                raise ValueError("evidence card references an unknown negative fact")
            if card.card_kind in {"action_episode", "unassigned_request"}:
                for request_ref in card.request_refs:
                    atomic_membership[request_ref] += 1
            elif not set(card.component_card_ids) < set(card_ids):
                raise ValueError("mechanical neighborhood references unknown atomic cards")
            if {
                str(request_by_ref[ref]["actor_id"]) for ref in card.request_refs
            } != set(card.actor_ids):
                raise ValueError("evidence card actor closure mismatch")
            if {
                str(request_by_ref[ref]["session_run_id"]) for ref in card.request_refs
            } != set(card.session_run_ids):
                raise ValueError("evidence card session closure mismatch")
        if any(count != 1 for count in atomic_membership.values()):
            raise ValueError("each admitted request requires exactly one atomic fact card")

        language = {
            (
                str(item.get("contract_kind")),
                str(item.get("predicate_family")),
                item.get("operator"),
            )
            for item in self.relation_language
        }
        if len(language) != len(self.relation_language):
            raise ValueError("current relation language contains duplicates")
        for collection in (
            self.ui_actions,
            self.api_requests,
            self.automatic_bindings,
            self.binding_reviews,
        ):
            for item in collection:
                row = dict(item)
                observed_hash = row.pop("full_row_sha256", None)
                if observed_hash != canonical_sha256(row):
                    raise ValueError("proposal view compact row hash mismatch")
        return self
class RenderedCandidateInput(Contract):
    artifact_type: Literal["rendered_candidate_input"] = "rendered_candidate_input"
    input_id: str
    scientific_input_version: Literal["preproposal-evidence-v2"] = "preproposal-evidence-v2"
    package_sha256: Sha256
    view_sha256: Sha256
    template_sha256: Sha256
    rendered_text: str
    rendered_sha256: Sha256

    @model_validator(mode="after")
    def _rendered_hash(self) -> "RenderedCandidateInput":
        import hashlib

        if hashlib.sha256(self.rendered_text.encode("utf-8")).hexdigest() != self.rendered_sha256:
            raise ValueError("rendered candidate input hash mismatch")
        return self


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    scientific_input_version: Literal["legacy-v1", "preproposal-evidence-v2"] = "legacy-v1"
    payload: dict[str, Any]
    payload_sha256: Sha256

    @model_validator(mode="after")
    def _payload_hash(self) -> "CandidateRecord":
        if canonical_sha256(self.payload) != self.payload_sha256:
            raise ValueError("candidate payload hash mismatch")
        if (
            self.scientific_input_version == "preproposal-evidence-v2"
            and (
                self.payload.get("schema_version")
                != "uisemtest-oracle-candidate-v1"
                or self.payload.get("candidate_id") != self.candidate_id
            )
        ):
            raise ValueError("current candidate payload schema or ID mismatch")
        return self


class CandidateSet(Contract):
    artifact_type: Literal["candidate_set"] = "candidate_set"
    candidate_set_id: str
    scientific_input_version: Literal["legacy-v1", "preproposal-evidence-v2"] = "legacy-v1"
    candidates: tuple[CandidateRecord, ...]
    preproposal_evidence_package_sha256: Sha256 | None = None
    proposal_evidence_view_sha256: Sha256 | None = None
    rendered_input_ref: str | None = None
    rendered_input_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def _unique_candidates(self) -> "CandidateSet":
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate IDs must be unique")
        if (self.rendered_input_ref is None) != (self.rendered_input_sha256 is None):
            raise ValueError("candidate set rendered input ref/hash must be supplied together")
        versions = {item.scientific_input_version for item in self.candidates}
        if versions and versions != {self.scientific_input_version}:
            raise ValueError("candidate set cannot mix scientific input versions")
        lineage = (
            self.preproposal_evidence_package_sha256,
            self.proposal_evidence_view_sha256,
            self.rendered_input_ref,
            self.rendered_input_sha256,
        )
        if self.scientific_input_version == "preproposal-evidence-v2" and any(value is None for value in lineage):
            raise ValueError("v2 candidate set requires package, view, and rendered input lineage")
        if self.scientific_input_version == "legacy-v1" and any(
            value is not None for value in lineage[:2]
        ):
            raise ValueError("legacy candidate set cannot claim v2 package or view lineage")
        return self


class ProducerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_ref: str
    actor_id: str
    method: str
    canonical_path: str
    request_started_at: str | None = None
    anchor_status: Literal["automatic", "ambiguous", "missing"]
    applicability: Literal["available", "unsupported"]
    reason_code: str
    anchor_event_id: str | None = None
    eligible_setup_event_ids: tuple[str, ...] = ()
    setup_domain_request_refs: tuple[str, ...] = ()
    profile_managed_setup_request_refs: tuple[str, ...] = ()
    setup_domain_truncated_request_count: int = 0

    @model_validator(mode="after")
    def _approved_mapping(self) -> "ProducerRecord":
        if (self.anchor_status == "automatic") != (self.applicability == "available"):
            raise ValueError("only automatic anchors are available")
        if self.applicability == "available" and not self.anchor_event_id:
            raise ValueError("available producer requires an automatic anchor event")
        if self.applicability == "unsupported" and self.anchor_event_id is not None:
            raise ValueError("unsupported producer cannot carry an anchor event")
        if self.applicability == "unsupported" and self.eligible_setup_event_ids:
            raise ValueError("unsupported producer cannot expose a setup domain")
        if self.applicability == "unsupported" and (
            self.setup_domain_request_refs
            or self.profile_managed_setup_request_refs
            or self.setup_domain_truncated_request_count
        ):
            raise ValueError("unsupported producer cannot expose setup request facts")
        if len(self.setup_domain_request_refs) != len(
            set(self.setup_domain_request_refs)
        ):
            raise ValueError("setup domain request refs must be unique")
        if not set(self.profile_managed_setup_request_refs) <= set(
            self.setup_domain_request_refs
        ):
            raise ValueError("profile-managed setup refs must belong to the domain")
        if self.setup_domain_truncated_request_count < 0:
            raise ValueError("setup domain truncation count must be nonnegative")
        expected_reason = {
            "automatic": "automatic_anchor_available",
            "ambiguous": "ambiguous_anchor",
            "missing": "missing_anchor",
        }[self.anchor_status]
        if self.reason_code != expected_reason:
            raise ValueError("producer reason code does not match anchor status")
        return self


class ProducerApplicability(Contract):
    artifact_type: Literal["producer_applicability"] = "producer_applicability"
    applicability_id: str
    producers: tuple[ProducerRecord, ...]
    universe_count: int
    available_count: int
    unsupported_count: int

    @model_validator(mode="after")
    def _partition(self) -> "ProducerApplicability":
        if len(self.producers) != self.universe_count:
            raise ValueError("producer universe count mismatch")
        if self.available_count + self.unsupported_count != self.universe_count:
            raise ValueError("producer applicability partition mismatch")
        if sum(item.applicability == "available" for item in self.producers) != self.available_count:
            raise ValueError("available producer count mismatch")
        if sum(item.applicability == "unsupported" for item in self.producers) != self.unsupported_count:
            raise ValueError("unsupported producer count mismatch")
        refs = [item.request_ref for item in self.producers]
        if len(refs) != len(set(refs)):
            raise ValueError("producer request refs must be unique")
        return self


class BoundCandidate(Contract):
    artifact_type: Literal["bound_candidate"] = "bound_candidate"
    candidate_id: str
    normalized_candidate: dict[str, Any]
    normalized_candidate_sha256: Sha256
    producer_request_ref: str
    consumer_request_ref: str
    setup_event_ids: tuple[str, ...]
    binding_payload: dict[str, Any]
    binding_payload_sha256: Sha256

    @model_validator(mode="after")
    def _bound_hashes(self) -> "BoundCandidate":
        if canonical_sha256(self.normalized_candidate) != self.normalized_candidate_sha256:
            raise ValueError("normalized candidate hash mismatch")
        if canonical_sha256(self.binding_payload) != self.binding_payload_sha256:
            raise ValueError("binding payload hash mismatch")
        return self


class V2BoundCandidate(Contract):
    """Lossless M10→M11 binding over one fully validated v2 candidate."""

    artifact_type: Literal["v2_bound_candidate"] = "v2_bound_candidate"
    scientific_input_version: Literal["preproposal-evidence-v2"] = "preproposal-evidence-v2"
    candidate_set_id: str
    candidate_set_sha256: Sha256
    candidate_id: str
    candidate_payload_sha256: Sha256
    input_freeze_manifest_sha256: Sha256
    package_sha256: Sha256
    view_sha256: Sha256
    rendered_input_sha256: Sha256
    template_sha256: Sha256
    proposal_run_plan_sha256: Sha256
    proposal_union_provenance_sha256: Sha256
    proposal_completion_sha256: Sha256
    raw_response_sha256: dict[str, Sha256]
    producer_request_ref: str | None
    observer_request_ref: str
    source_symbolic_predicate: dict[str, Any]
    source_symbolic_predicate_sha256: Sha256
    runtime_predicate: dict[str, Any]
    runtime_predicate_sha256: Sha256
    selected_setup_action_ids: tuple[str, ...]
    selected_setup_event_ids: tuple[str, ...]
    selected_setup_request_refs: tuple[str, ...]
    eligible_setup_request_refs: tuple[str, ...]
    profile_managed_setup_request_refs: tuple[str, ...]
    setup_domain_truncated_request_count: int
    eligible_setup_domain_ref: str
    eligible_setup_domain_sha256: Sha256

    @model_validator(mode="after")
    def _bound_v2_hashes(self) -> "V2BoundCandidate":
        if canonical_sha256(self.source_symbolic_predicate) != self.source_symbolic_predicate_sha256:
            raise ValueError("v2 source symbolic predicate hash mismatch")
        if canonical_sha256(self.runtime_predicate) != self.runtime_predicate_sha256:
            raise ValueError("v2 runtime predicate hash mismatch")
        lengths = {
            len(self.selected_setup_action_ids),
            len(self.selected_setup_event_ids),
            len(self.selected_setup_request_refs),
        }
        if len(lengths) != 1:
            raise ValueError("v2 selected setup action/event/request tuples must be lossless")
        if len(self.eligible_setup_request_refs) != len(
            set(self.eligible_setup_request_refs)
        ):
            raise ValueError("v2 eligible setup request refs must be unique")
        if not set(self.selected_setup_request_refs) <= set(
            self.eligible_setup_request_refs
        ):
            raise ValueError("v2 selected setup requests must belong to the domain")
        if not set(self.profile_managed_setup_request_refs) <= set(
            self.eligible_setup_request_refs
        ):
            raise ValueError("v2 profile-managed setup requests must belong to the domain")
        if self.setup_domain_truncated_request_count < 0:
            raise ValueError("v2 setup domain truncation count must be nonnegative")
        return self


class V2RuntimeReadyMaterial(Contract):
    artifact_type: Literal["v2_runtime_ready_material"] = "v2_runtime_ready_material"
    scientific_input_version: Literal["preproposal-evidence-v2"] = "preproposal-evidence-v2"
    candidate_id: str
    bound_candidate_sha256: Sha256
    execution_binding: dict[str, Any]
    execution_binding_sha256: Sha256
    pre_live_pins: dict[str, Any]
    pre_live_pins_sha256: Sha256
    resource_material_plan: dict[str, Any]
    resource_material_plan_sha256: Sha256
    route_s_contract_version: Literal["v5"] = "v5"
    live_execution_count: Literal[0] = 0

    @model_validator(mode="after")
    def _runtime_material_hashes(self) -> "V2RuntimeReadyMaterial":
        for value, expected, label in (
            (self.execution_binding, self.execution_binding_sha256, "execution binding"),
            (self.pre_live_pins, self.pre_live_pins_sha256, "pre-live pins"),
            (self.resource_material_plan, self.resource_material_plan_sha256, "resource/material plan"),
        ):
            if canonical_sha256(value) != expected:
                raise ValueError(f"v2 {label} hash mismatch")
        return self


class V2RuntimeReadyMaterialSet(Contract):
    artifact_type: Literal["v2_runtime_ready_material_set"] = "v2_runtime_ready_material_set"
    scientific_input_version: Literal["preproposal-evidence-v2"] = "preproposal-evidence-v2"
    material_set_id: str
    candidate_set_id: str
    candidate_set_sha256: Sha256
    bound_candidates: tuple[V2BoundCandidate, ...]
    runtime_materials: tuple[V2RuntimeReadyMaterial, ...]
    live_execution_count: Literal[0] = 0

    @model_validator(mode="after")
    def _material_set_closed(self) -> "V2RuntimeReadyMaterialSet":
        bound_ids = [item.candidate_id for item in self.bound_candidates]
        material_ids = [item.candidate_id for item in self.runtime_materials]
        if bound_ids != material_ids or len(bound_ids) != len(set(bound_ids)):
            raise ValueError("v2 runtime-ready material IDs do not close over bound candidates")
        if any(
            material.bound_candidate_sha256 != bound.canonical_sha256()
            for bound, material in zip(self.bound_candidates, self.runtime_materials, strict=True)
        ):
            raise ValueError("v2 runtime material does not reference its bound candidate")
        return self


class RouteSCertificate(Contract):
    artifact_type: Literal["route_s_certificate"] = "route_s_certificate"
    candidate_id: str
    outcome: Literal[
        "confirmed",
        "baseline_mismatch",
        "effect_absent",
        "malformed_or_unsupported",
        "infrastructure_failed",
        "setup_failed",
        "arm_isolation_failed",
        "observer_mutating_or_uncertain",
        "control_unstable",
    ]
    certificate_ref: str
    certificate_sha256: Sha256


class CertifiedRelationTestSuite(Contract):
    artifact_type: Literal["certified_relation_test_suite"] = "certified_relation_test_suite"
    suite_id: str
    suite: dict[str, Any]
    test_count: int
    business_assertion_count: int
    generic_assertion_count: int

    @model_validator(mode="after")
    def _suite_counts(self) -> "CertifiedRelationTestSuite":
        tests = self.suite.get("tests", [])
        assertions = [row for test in tests for row in test.get("assertions", [])]
        if self.test_count != len(tests):
            raise ValueError("certified suite test count mismatch")
        if self.business_assertion_count != sum(row.get("assertion_class") == "business" for row in assertions):
            raise ValueError("certified suite business assertion count mismatch")
        if self.generic_assertion_count != sum(row.get("assertion_class") == "generic" for row in assertions):
            raise ValueError("certified suite generic assertion count mismatch")
        for key, values in (
            ("test_id", [item.get("test_id") for item in tests]),
            ("candidate_id", [item.get("candidate_id") for item in tests]),
            ("assertion_id", [item.get("assertion_id") for item in assertions]),
        ):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError(f"certified suite {key} values must be nonempty and unique")
        return self


class CalibrationReport(Contract):
    artifact_type: Literal["calibration_report"] = "calibration_report"
    calibration_id: str
    test_pass_count: int
    test_total_count: int
    business_pass_count: int
    business_total_count: int
    generic_pass_count: int
    generic_total_count: int
    environment_failure_count: int = 0

    @model_validator(mode="after")
    def _denominators(self) -> "CalibrationReport":
        pairs = (
            (self.test_pass_count, self.test_total_count),
            (self.business_pass_count, self.business_total_count),
            (self.generic_pass_count, self.generic_total_count),
        )
        if any(total < 0 or passed < 0 or passed > total for passed, total in pairs):
            raise ValueError("calibration pass counts must be within denominators")
        if self.environment_failure_count < 0:
            raise ValueError("calibration environment failure count must be nonnegative")
        return self
