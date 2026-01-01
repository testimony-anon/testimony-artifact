"""Transactional, offline-testable M10 proposal-run boundary.

This module has no network implementation and never reads provider environment
variables.  A caller must inject one ``RenderedProposalProvider`` per frozen
call specification.  Each provider receives the rendered scientific input once
and receives no second evidence payload.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import copy
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .artifact_relocation import attested_sha256
from threading import Lock
from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .candidate_lineage import load_v2_candidate_lineage
from .contracts import (
    CandidateRecord,
    CandidateSet,
    ProposalEvidenceView,
    RenderedCandidateInput,
)
from .current_providers import RenderedProposalProvider, RenderedProposalResponse
from .current_route_s import canonical_json_bytes, canonical_sha256
from .preproposal import (
    _selector_snapshot_sha256,
    identity_like_json_path,
    response_collection_paths_with_identity,
)
from .v2_proposer import (
    READ_METHODS,
    SCIENTIFIC_INPUT_VERSION,
    V2FrozenInput,
    WRITE_METHODS,
    _parse_response,
    _reject_duplicate_keys,
    _scientific_relation_payload,
    _validate_candidate_batch,
    _query_is_filter_refinement,
    load_hardened_v2_input,
)
from .v2_template import (
    SCAN_EVIDENCE_PLACEHOLDER,
    canonical_scan_template_sha256,
    canonical_scan_template_text,
    canonical_v2_template_sha256,
    canonical_v2_template_text,
)


_SHA = r"^[0-9a-f]{64}$"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SAFE_ATOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
_SECRET_KEYS = frozenset({
    "authorization",
    "proxy_authorization",
    "api_key",
    "api-key",
    "apikey",
    "x-api-key",
    "secret",
    "client_secret",
    "password",
    "access_token",
    "refresh_token",
    "cookie",
    "set-cookie",
})
SCAN_MAX_PRIMARY_CARDS = 24
SCAN_MAX_RENDERED_UTF8_BYTES = 96 * 1024
SCAN_MAX_SINGLE_PRIMARY_RENDERED_UTF8_BYTES = 128 * 1024
DETAIL_MAX_REQUESTS = 48
DETAIL_MAX_RENDERED_UTF8_BYTES = 240 * 1024
SCAN_STRUCTURE_PATH_LIMIT = 48
SCAN_COMPACT_RELATION_ROW_LIMIT = 16
DETAIL_DERIVATION_REVISION = "m10-observed-catalog-observer-v4"
_MODEL_SNAPSHOT_SUFFIX = re.compile(
    r"^(?P<family>.+)-(?P<snapshot>\d{4}-\d{2}-\d{2})$"
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _nonblank_atom(value: str) -> str:
    if not value.strip() or not _SAFE_ATOM.fullmatch(value):
        raise ValueError("proposal metadata must be a nonblank safe atom")
    return value


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("proposal timestamps must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError("proposal timestamps require an explicit timezone")
    return parsed.astimezone(UTC)


def _provider_model_family(value: str) -> str:
    """Return the stable family for a bare model or dated model snapshot."""

    normalized = value.strip()
    match = _MODEL_SNAPSHOT_SUFFIX.fullmatch(normalized)
    if match is None:
        return normalized
    try:
        datetime.strptime(match.group("snapshot"), "%Y-%m-%d")
    except ValueError:
        return normalized
    return match.group("family")


class ProposalCallSpec(_StrictModel):
    call_id: str
    call_order: int = Field(ge=1)
    model: str
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh", "max"] | None = Field(
        default=None, exclude_if=lambda value: value is None,
    )
    temperature: float = Field(ge=0.0, le=2.0)
    retry_limit: int = Field(ge=0, le=10)
    endpoint_shape: str
    endpoint_host: str
    stratum: Literal["business"]
    proposal_round: Literal[
        "global_scan", "detail_proposal", "center_completion"
    ]
    evidence_card_ids: tuple[str, ...] = Field(min_length=1)
    detail_region_id: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    scan_soft_overflow_utf8_bytes: int | None = Field(
        default=None,
        ge=1,
        exclude_if=lambda value: value is None,
    )

    _model = field_validator("model")(_nonblank_atom)
    _endpoint_shape = field_validator("endpoint_shape")(_nonblank_atom)

    @field_validator("call_id")
    @classmethod
    def _call_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value):
            raise ValueError("proposal call_id must be a safe relative identifier")
        return value

    @field_validator("temperature")
    @classmethod
    def _finite_temperature(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("proposal temperature must be finite")
        return value

    @field_validator("endpoint_host")
    @classmethod
    def _host(cls, value: str) -> str:
        if (
            not value.strip()
            or any(token in value for token in ("/", "\\", "@", "?", "#"))
            or not re.fullmatch(r"[A-Za-z0-9.-]+(?::\d{1,5})?", value)
        ):
            raise ValueError("endpoint_host must be a sanitized host[:port], without credentials or scheme")
        return value

    @model_validator(mode="after")
    def _scope_pair(self) -> "ProposalCallSpec":
        if self.endpoint_shape == "codex_cli" and self.reasoning_effort is None:
            raise ValueError("Codex CLI call requires explicit reasoning_effort")
        if any(not ref.strip() for ref in self.evidence_card_ids):
            raise ValueError("proposal evidence-card IDs must be nonblank")
        if len(self.evidence_card_ids) != len(set(self.evidence_card_ids)):
            raise ValueError("proposal evidence-card IDs must be unique")
        if self.proposal_round in {"detail_proposal", "center_completion"} and len(
            self.evidence_card_ids
        ) != 1:
            raise ValueError("detail candidate calls require exactly one primary card")
        if self.proposal_round in {"detail_proposal", "center_completion"}:
            if self.detail_region_id is None:
                raise ValueError("detail candidate call requires detail_region_id")
        elif self.detail_region_id is not None:
            raise ValueError("only detail candidate calls may carry detail_region_id")
        if self.detail_region_id is not None and not _SAFE_ID.fullmatch(
            self.detail_region_id
        ):
            raise ValueError("detail_region_id must be a safe identifier")
        if self.scan_soft_overflow_utf8_bytes is not None:
            if self.proposal_round != "global_scan" or len(self.evidence_card_ids) != 1:
                raise ValueError(
                    "scan soft overflow requires one global-scan primary card"
                )
            if not (
                SCAN_MAX_RENDERED_UTF8_BYTES
                < self.scan_soft_overflow_utf8_bytes
                <= SCAN_MAX_SINGLE_PRIMARY_RENDERED_UTF8_BYTES
            ):
                raise ValueError("scan soft overflow bytes are outside current bounds")
        return self


class ScanDetailSelection(_StrictModel):
    refs: list[str] = Field(min_length=1)

    @field_validator("refs")
    @classmethod
    def _unique_refs(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value) or len(value) != len(set(value)):
            raise ValueError("scan selection refs must be nonblank and unique")
        return value


class ScanDecision(_StrictModel):
    primary_card_id: str
    decision: Literal["expand", "skip"]
    detail_selections: list[ScanDetailSelection]

    @model_validator(mode="after")
    def _decision_shape(self) -> "ScanDecision":
        if self.decision == "skip" and self.detail_selections:
            raise ValueError("skip decision must not contain detail selections")
        if self.decision == "expand" and not self.detail_selections:
            raise ValueError("expand decision requires detail selections")
        return self


class ScanResponse(_StrictModel):
    scientific_input_version: Literal["preproposal-evidence-v2"]
    decisions: list[ScanDecision]


class DetailRegion(_StrictModel):
    region_id: str
    region_kind: Literal["business_operation_episode", "selected_fact_region"]
    primary_card_id: str
    center_action_id: str | None = None
    center_state_change_request_refs: tuple[str, ...] = ()
    center_observation_slice: dict[str, Any] | None = None
    observer_operation_catalog: tuple[dict[str, Any], ...] = ()
    core_card_ids: tuple[str, ...] = ()
    selection_refs: tuple[str, ...]
    member_card_ids: tuple[str, ...]
    visible_request_refs: tuple[str, ...]
    visible_action_ids: tuple[str, ...]
    visible_evidence_refs: tuple[str, ...]
    split_order: int = Field(ge=1)
    split_count: int = Field(ge=1)
    boundary: dict[str, int | str]


class ProposalRunPlan(_StrictModel):
    schema_version: Literal["uisemtest-v2-proposal-run-plan-v2"] = (
        "uisemtest-v2-proposal-run-plan-v2"
    )
    scientific_input_version: Literal["preproposal-evidence-v2"] = SCIENTIFIC_INPUT_VERSION
    plan_id: str
    frozen_at: str
    input_freeze_manifest_sha256: str = Field(pattern=_SHA)
    template_sha256: str = Field(pattern=_SHA)
    scan_template_sha256: str = Field(
        default_factory=canonical_scan_template_sha256,
        pattern=_SHA,
    )
    package_sha256: str = Field(pattern=_SHA)
    view_sha256: str = Field(pattern=_SHA)
    rendered_input_sha256: str = Field(pattern=_SHA)
    rendered_text_sha256: str = Field(pattern=_SHA)
    calls: tuple[ProposalCallSpec, ...]
    actual_model_policy: Literal["exact", "consistent"]
    scan_max_primary_cards: int = Field(default=SCAN_MAX_PRIMARY_CARDS, ge=1)
    scan_max_rendered_utf8_bytes: int = Field(
        default=SCAN_MAX_RENDERED_UTF8_BYTES, ge=1
    )
    scan_max_single_primary_rendered_utf8_bytes: int = Field(
        default=SCAN_MAX_SINGLE_PRIMARY_RENDERED_UTF8_BYTES,
        ge=SCAN_MAX_RENDERED_UTF8_BYTES,
    )
    detail_max_requests: int = Field(default=DETAIL_MAX_REQUESTS, ge=1)
    detail_max_rendered_utf8_bytes: int = Field(
        default=DETAIL_MAX_RENDERED_UTF8_BYTES, ge=1
    )
    detail_derivation_revision: Literal["m10-observed-catalog-observer-v4"] = (
        DETAIL_DERIVATION_REVISION
    )

    @field_validator("plan_id")
    @classmethod
    def _plan_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value):
            raise ValueError("proposal plan_id must be a safe identifier")
        return value

    @field_validator("frozen_at")
    @classmethod
    def _frozen_at(cls, value: str) -> str:
        _timestamp(value)
        return value

    @model_validator(mode="after")
    def _ordered_calls(self) -> "ProposalRunPlan":
        if [item.call_order for item in self.calls] != list(range(1, len(self.calls) + 1)):
            raise ValueError("proposal calls must be stored in contiguous call_order")
        ids = [item.call_id for item in self.calls]
        if len(ids) != len(set(ids)):
            raise ValueError("proposal call IDs must be unique")
        if not self.calls:
            return self
        call_kinds = {item.proposal_round for item in self.calls}
        if call_kinds not in ({"global_scan"}, {"center_completion"}):
            raise ValueError(
                "current M10 plan must be one regular scan schedule or one "
                "center-completion schedule"
            )
        policies = {
            (
                item.model,
                item.reasoning_effort,
                item.temperature,
                item.retry_limit,
                item.endpoint_shape,
                item.endpoint_host,
            )
            for item in self.calls
        }
        if len(policies) != 1:
            raise ValueError("proposal calls must share one frozen provider policy")
        if call_kinds == {"global_scan"}:
            refs = [ref for item in self.calls for ref in item.evidence_card_ids]
            if len(refs) != len(set(refs)):
                raise ValueError("proposal calls must assign disjoint primary cards")
        else:
            # Distinct query pairs can share a followup card. Their frozen
            # opportunity regions, not their primary cards, must be unique.
            regions = [item.detail_region_id for item in self.calls]
            if len(regions) != len(set(regions)):
                raise ValueError("completion calls must identify unique opportunity regions")
        return self

    def scientific_sha256(self) -> str:
        """Hash call semantics while excluding administrative run ID/time."""

        return canonical_sha256({
            "schema_version": self.schema_version,
            "scientific_input_version": self.scientific_input_version,
            "input_freeze_manifest_sha256": self.input_freeze_manifest_sha256,
            "template_sha256": self.template_sha256,
            "scan_template_sha256": self.scan_template_sha256,
            "package_sha256": self.package_sha256,
            "view_sha256": self.view_sha256,
            "rendered_input_sha256": self.rendered_input_sha256,
            "rendered_text_sha256": self.rendered_text_sha256,
            "calls": [item.model_dump(mode="json") for item in self.calls],
            "scan_max_primary_cards": self.scan_max_primary_cards,
            "scan_max_rendered_utf8_bytes": self.scan_max_rendered_utf8_bytes,
            "scan_max_single_primary_rendered_utf8_bytes": (
                self.scan_max_single_primary_rendered_utf8_bytes
            ),
            "detail_max_requests": self.detail_max_requests,
            "detail_max_rendered_utf8_bytes": self.detail_max_rendered_utf8_bytes,
            "detail_derivation_revision": self.detail_derivation_revision,
        })


class ProposalCallProvenance(_StrictModel):
    schema_version: Literal["uisemtest-v2-proposal-call-provenance-v2"] = (
        "uisemtest-v2-proposal-call-provenance-v2"
    )
    call_id: str
    call_order: int
    request_config_sha256: str = Field(pattern=_SHA)
    raw_response_file_sha256: str = Field(pattern=_SHA)
    raw_response_content_sha256: str = Field(pattern=_SHA)
    canonical_response_sha256: str = Field(pattern=_SHA)
    candidate_validation_file_sha256: str = Field(pattern=_SHA)
    candidate_set_sha256: str = Field(pattern=_SHA)
    candidate_count: int = Field(ge=0)
    raw_proposed_count: int = Field(ge=0)
    valid_admitted_count: int = Field(ge=0)
    invalid_rejected_count: int = Field(ge=0)
    deduplicated_count: int = Field(ge=0)
    model: str
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh", "max"] | None = Field(
        default=None, exclude_if=lambda value: value is None,
    )
    endpoint_shape: str
    endpoint_host: str
    temperature: float
    retry_count: int = Field(ge=0)
    response_received_at: str

    @model_validator(mode="after")
    def _metadata(self) -> "ProposalCallProvenance":
        _nonblank_atom(self.model)
        _nonblank_atom(self.endpoint_shape)
        ProposalCallSpec._host(self.endpoint_host)
        _timestamp(self.response_received_at)
        if not math.isfinite(self.temperature):
            raise ValueError("proposal call temperature must be finite")
        if self.candidate_count != self.valid_admitted_count:
            raise ValueError("proposal call candidate/admission count mismatch")
        if self.raw_proposed_count != (
            self.valid_admitted_count
            + self.invalid_rejected_count
            + self.deduplicated_count
        ):
            raise ValueError("proposal call candidate partition mismatch")
        return self


class ProposalUnionProvenance(_StrictModel):
    schema_version: Literal["uisemtest-v2-proposal-union-provenance-v5"] = (
        "uisemtest-v2-proposal-union-provenance-v5"
    )
    plan_sha256: str = Field(pattern=_SHA)
    plan_scientific_sha256: str = Field(pattern=_SHA)
    input_freeze_manifest_sha256: str = Field(pattern=_SHA)
    call_ids: tuple[str, ...]
    call_provenance_sha256: dict[str, str]
    raw_response_file_sha256: dict[str, str]
    raw_proposed_count: int = Field(ge=0)
    valid_admitted_count: int = Field(ge=0)
    invalid_rejected_count: int = Field(ge=0)
    deduplicated_count: int = Field(ge=0)
    union_candidate_set_sha256: str = Field(pattern=_SHA)
    constructed_execution_plans: tuple[dict[str, Any], ...]
    resolved_calls: tuple[dict[str, Any], ...] = ()
    detail_regions: tuple[dict[str, Any], ...] = ()
    proposal_funnel: dict[str, int] = Field(default_factory=dict)
    center_completion: dict[str, Any] = Field(default_factory=dict)
    admitted_canonical_relation_core_identities: tuple[str, ...]

    @model_validator(mode="after")
    def _partition(self) -> "ProposalUnionProvenance":
        if self.raw_proposed_count != (
            self.valid_admitted_count
            + self.invalid_rejected_count
            + self.deduplicated_count
        ):
            raise ValueError("proposal union candidate partition mismatch")
        if set(self.call_ids) != set(self.call_provenance_sha256) or set(self.call_ids) != set(self.raw_response_file_sha256):
            raise ValueError("proposal union call provenance keys do not close")
        if any(not re.fullmatch(_SHA, value) for value in (*self.call_provenance_sha256.values(), *self.raw_response_file_sha256.values())):
            raise ValueError("proposal union contains a malformed call SHA-256")
        if (
            len(self.admitted_canonical_relation_core_identities)
            != self.valid_admitted_count + self.deduplicated_count
            or any(
                not re.fullmatch(_SHA, value)
                for value in self.admitted_canonical_relation_core_identities
            )
        ):
            raise ValueError("proposal union canonical relation-core occurrences do not close")
        plan_ids = [str(item.get("plan_id")) for item in self.constructed_execution_plans]
        if plan_ids != sorted(plan_ids) or len(plan_ids) != len(set(plan_ids)):
            raise ValueError("constructed execution plans must be unique and ordered")
        return self


class ProposalRunCompletion(_StrictModel):
    schema_version: Literal["uisemtest-v2-proposal-run-completion-v2"] = (
        "uisemtest-v2-proposal-run-completion-v2"
    )
    status: Literal["complete", "failed"]
    plan_file_sha256: str = Field(pattern=_SHA)
    plan_sha256: str = Field(pattern=_SHA)
    input_freeze_manifest_sha256: str = Field(pattern=_SHA)
    scheduled_call_count: int = Field(ge=0)
    completed_call_count: int = Field(ge=0)
    failed_call_id: str | None = None
    call_completion_sha256: dict[str, str]
    union_candidate_set_sha256: str | None = None
    union_provenance_sha256: str | None = None
    union_candidate_set_file_sha256: str | None = None
    union_provenance_file_sha256: str | None = None
    provider_logical_call_count: int = Field(ge=0)
    provider_concurrency_planned: int = Field(ge=1)
    provider_concurrency_actual_max: int = Field(ge=0)
    raw_proposed_count: int = Field(ge=0)
    valid_admitted_count: int = Field(ge=0)
    invalid_rejected_count: int = Field(ge=0)
    deduplicated_count: int = Field(ge=0)
    additional_evidence_payload_count: Literal[0] = 0

    @model_validator(mode="after")
    def _terminal_state(self) -> "ProposalRunCompletion":
        if self.provider_concurrency_actual_max > self.provider_concurrency_planned:
            raise ValueError("actual provider concurrency exceeds its frozen plan")
        if self.completed_call_count != len(self.call_completion_sha256):
            raise ValueError("proposal completion call count mismatch")
        if self.status == "complete":
            if self.completed_call_count != self.scheduled_call_count or self.failed_call_id is not None:
                raise ValueError("complete proposal run did not finish every scheduled call")
            if any(value is None for value in (
                self.union_candidate_set_sha256,
                self.union_provenance_sha256,
                self.union_candidate_set_file_sha256,
                self.union_provenance_file_sha256,
            )):
                raise ValueError("complete proposal run lacks union artifacts")
        elif self.failed_call_id is None or any(value is not None for value in (
            self.union_candidate_set_sha256,
            self.union_provenance_sha256,
            self.union_candidate_set_file_sha256,
            self.union_provenance_file_sha256,
        )):
            raise ValueError("failed proposal run terminal fields are inconsistent")
        if self.raw_proposed_count != (
            self.valid_admitted_count
            + self.invalid_rejected_count
            + self.deduplicated_count
        ):
            raise ValueError("proposal completion candidate partition mismatch")
        return self


@dataclass(frozen=True)
class V2ProposalRunLineage:
    frozen_input: V2FrozenInput
    plan: ProposalRunPlan
    plan_sha256: str
    candidate_set: CandidateSet
    union_provenance: ProposalUnionProvenance
    completion: ProposalRunCompletion
    run_root: Path
    completion_raw_sha256: str
    raw_response_sha256: dict[str, str]
    call_provenance_sha256: dict[str, str]


class ProposalRunExecutionError(RuntimeError):
    def __init__(self, message: str, *, run_root: Path) -> None:
        super().__init__(message)
        self.run_root = run_root


ProviderFactory = Callable[[ProposalCallSpec], RenderedProposalProvider]


@dataclass(frozen=True)
class _ProposalCallInput:
    view: Any
    rendered_input: RenderedCandidateInput


@dataclass(frozen=True)
class _DetailFactUnit:
    selected_ref: str
    request_refs: frozenset[str]
    action_ids: frozenset[str]
    evidence_refs: frozenset[str]
    card_ids: frozenset[str]
    order_key: tuple[int, int, str]


@dataclass(frozen=True)
class _BusinessOperationEpisode:
    center_card_id: str
    center_action_id: str
    center_kind: Literal["authentication", "state_change"]
    core_card_ids: tuple[str, ...]


def _catalog_request_operations(
    operations: list[dict[str, Any]],
) -> dict[str, str]:
    request_operations: dict[str, str] = {}
    for operation in operations:
        operation_id = str(operation["operation_id"])
        for observation in operation.get("observation_refs", ()):
            source = observation.get("source")
            if source == "stage2_5_probe":
                continue
            if source != "stage1_session":
                raise ValueError("catalog observation source is unsupported")
            request_ref = observation.get("request_ref")
            if not isinstance(request_ref, str) or not request_ref:
                raise ValueError(
                    "stage1 catalog observation requires a non-empty request_ref"
                )
            previous = request_operations.setdefault(request_ref, operation_id)
            if previous != operation_id:
                raise ValueError(
                    "catalog request observation maps to multiple operations"
                )
    return request_operations


def _recording_order_key(
    card: Mapping[str, Any], requests: Mapping[str, Mapping[str, Any]]
) -> tuple[int, str]:
    return (
        min(int(requests[str(ref)]["global_order"]) for ref in card["request_refs"]),
        str(card["card_id"]),
    )


def _shape_summary(shape: Mapping[str, Any]) -> dict[str, Any]:
    rows = [
        {"path": str(row.get("path")), "type": str(row.get("type"))}
        for row in shape.get("shape_rows", ())
        if row.get("path") is not None and row.get("type") is not None
    ]
    rows = list({(row["path"], row["type"]): row for row in rows}.values())

    def depth(path: str) -> int:
        return path.count(".") + path.count("[*]")

    ordered = sorted(
        rows,
        key=lambda row: (
            0 if identity_like_json_path(row["path"]) else 1,
            0 if row["type"] == "array" else 1,
            depth(row["path"]),
            row["path"],
            row["type"],
        ),
    )
    visible = ordered[:SCAN_STRUCTURE_PATH_LIMIT]
    collections = sorted(
        row["path"] for row in rows if row["type"] == "array"
    )
    identities = sorted(
        row["path"] for row in rows if identity_like_json_path(row["path"])
    )
    return {
        "nested_path_types": visible,
        "nested_path_type_count": len(rows),
        "nested_path_type_omitted_count": len(rows) - len(visible),
        "collection_paths": collections,
        "identity_candidates": identities,
    }


def _scan_request_summary(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: request.get(key)
        for key in (
            "request_ref",
            "actor_id",
            "session_run_id",
            "global_order",
            "operation_id",
            "method",
            "canonical_path",
            "request_group_id",
            "action_event_id",
            "association_status",
            "group_order",
            "is_anchor",
            "weak_roles",
            "query_parameter_names",
            "query",
            "response_status",
        )
        if key in request
    } | {
        "request_structure": _shape_summary(request.get("request_body_shape") or {}),
        "response_structure": _shape_summary(request.get("response_body_shape") or {}),
    }


def _scan_context_for_card(
    card: Mapping[str, Any],
    *,
    cards: Mapping[str, Mapping[str, Any]],
) -> tuple[set[str], set[str], set[str], set[str]]:
    card_id = str(card["card_id"])
    related_cards = {
        other_id
        for other_id, other in cards.items()
        if other_id == card_id
        or card_id in set(map(str, other.get("component_card_ids", ())))
    }
    request_refs = {
        str(ref)
        for related_id in related_cards
        for ref in cards[related_id].get("request_refs", ())
    }
    action_ids = set(map(str, card.get("action_event_ids", ())))
    evidence_refs = {
        str(ref)
        for field in (
            "ui_diff_record_ids",
            "value_flow_ids",
            "dependency_edge_ids",
            "binding_opportunity_ids",
            "negative_request_fact_ids",
        )
        for ref in card.get(field, ())
    }
    return related_cards, request_refs, action_ids, evidence_refs


def _scan_batch_payload(
    view: ProposalEvidenceView,
    card_ids: tuple[str, ...],
    *,
    batch_id: str,
) -> dict[str, Any]:
    payload = view.model_dump(mode="json")
    cards = {str(card["card_id"]): card for card in payload["evidence_cards"]}
    requests = {str(row["request_ref"]): row for row in payload["api_requests"]}
    actions = {str(row["event_id"]): row for row in payload["ui_actions"]}
    flows = {str(row["flow_id"]): row for row in payload["observed_value_flows"]}
    edges = {str(row["edge_id"]): row for row in payload["dependency_edges"]}
    bindings = {
        str(row["opportunity_id"]): row for row in payload["binding_opportunities"]
    }
    ui_rows = {
        str(row["record_id"]): row
        for row in (
            payload.get("evidence_channel_summaries", {})
            .get("ui_diff", {})
            .get("semantic_projection", {})
            .get("rows", ())
        )
    }
    primary_rows: list[dict[str, Any]] = []
    visible_requests: set[str] = set()
    visible_actions: set[str] = set()
    visible_cards: set[str] = set()
    visible_evidence: set[str] = set()
    primary_request_refs: set[str] = set()
    for card_id in card_ids:
        card = cards[card_id]
        related_cards, request_refs, action_ids, evidence_refs = _scan_context_for_card(
            card, cards=cards
        )
        setup_summaries = {
            ref: payload["request_setup_domains"][ref]
            for ref in map(str, card["request_refs"])
        }
        setup_action_ids = {
            str(action_id)
            for domain in setup_summaries.values()
            for action_id in domain.get("eligible_setup_action_ids", ())
        }
        action_ids.update(setup_action_ids)
        allowed = {
            card_id,
            *related_cards,
            *request_refs,
            *action_ids,
            *evidence_refs,
        }
        primary_rows.append({
            "primary_card_id": card_id,
            "card_kind": card["card_kind"],
            "request_refs": card["request_refs"],
            "action_event_ids": card["action_event_ids"],
            "request_group_ids": card["request_group_ids"],
            "actor_ids": card["actor_ids"],
            "session_run_ids": card["session_run_ids"],
            "request_setup_summaries": setup_summaries,
            "related_card_ids": sorted(related_cards - {card_id}),
            "related_request_refs": sorted(
                request_refs - set(map(str, card["request_refs"])),
                key=lambda ref: (int(requests[ref]["global_order"]), ref),
            ),
            "allowed_reference_ids": sorted(allowed),
        })
        visible_cards.update(related_cards)
        visible_requests.update(request_refs)
        primary_request_refs.update(map(str, card["request_refs"]))
        visible_actions.update(action_ids)
        visible_evidence.update(evidence_refs)

    compact_flows_all = [
        {
            key: row[key]
            for key in (
                "flow_id",
                "producer_request_ref",
                "consumer_request_ref",
                "producer_operation_id",
                "consumer_operation_id",
                "from_location",
                "from_field",
                "to_location",
                "to_field",
            )
        }
        for ref in sorted(visible_evidence & set(flows))
        for row in (flows[ref],)
    ]
    compact_edges_all = [
        {
            key: row[key]
            for key in (
                "edge_id",
                "producer_operation_id",
                "consumer_operation_id",
                "kind",
                "observed_flow_count",
            )
        }
        for ref in sorted(visible_evidence & set(edges))
        for row in (edges[ref],)
    ]
    compact_bindings_all = [
        {
            key: row[key]
            for key in (
                "opportunity_id",
                "producer_operation_id",
                "consumer_operation_id",
                "effective_binding_kind",
                "from_location",
                "from_field",
                "to_location",
                "to_field",
            )
        }
        for ref in sorted(visible_evidence & set(bindings))
        for row in (bindings[ref],)
    ]
    cross_batch_refs = sorted(
        visible_requests - primary_request_refs,
        key=lambda item: (int(requests[item]["global_order"]), item),
    )
    visible_ui_refs = sorted(visible_evidence & set(ui_rows))
    return {
        "phase": "global_scan",
        "batch_id": batch_id,
        "primary_cards": primary_rows,
        "request_catalog": [
            _scan_request_summary(requests[ref])
            for ref in sorted(
                primary_request_refs,
                key=lambda item: (int(requests[item]["global_order"]), item),
            )
        ],
        "cross_batch_request_catalog": [
            {
                key: requests[ref].get(key)
                for key in (
                    "request_ref",
                    "actor_id",
                    "session_run_id",
                    "global_order",
                    "operation_id",
                    "method",
                    "canonical_path",
                    "request_group_id",
                    "action_event_id",
                    "weak_roles",
                    "query_parameter_names",
                )
                if key in requests[ref]
            }
            for ref in cross_batch_refs[:SCAN_COMPACT_RELATION_ROW_LIMIT]
        ],
        "action_catalog": [
            {
                key: actions[ref].get(key)
                for key in (
                    "event_id",
                    "actor_id",
                    "global_order",
                    "action_type",
                    "selector",
                    "page_url",
                    "visible_element",
                )
            }
            for ref in sorted(
                visible_actions,
                key=lambda item: (int(actions[item]["global_order"]), item),
            )
            if ref in actions
        ],
        "ui_diff_catalog": [
            ui_rows[ref]
            for ref in visible_ui_refs[:SCAN_COMPACT_RELATION_ROW_LIMIT]
        ],
        "value_flow_catalog": compact_flows_all[:SCAN_COMPACT_RELATION_ROW_LIMIT],
        "dependency_catalog": compact_edges_all[:SCAN_COMPACT_RELATION_ROW_LIMIT],
        "binding_catalog": compact_bindings_all[:SCAN_COMPACT_RELATION_ROW_LIMIT],
        "boundary": {
            "primary_card_count": len(card_ids),
            "request_context_count": len(visible_requests),
            "cross_batch_context_request_count": len(
                visible_requests
                - {
                    str(ref)
                    for card_id in card_ids
                    for ref in cards[card_id]["request_refs"]
                }
            ),
            "cross_batch_context_catalog_visible": min(
                len(cross_batch_refs), SCAN_COMPACT_RELATION_ROW_LIMIT
            ),
            "cross_batch_context_catalog_omitted": max(
                0, len(cross_batch_refs) - SCAN_COMPACT_RELATION_ROW_LIMIT
            ),
            "ui_diff_total": len(visible_ui_refs),
            "ui_diff_catalog_omitted": max(
                0, len(visible_ui_refs) - SCAN_COMPACT_RELATION_ROW_LIMIT
            ),
            "value_flow_total": len(compact_flows_all),
            "value_flow_catalog_omitted": max(
                0, len(compact_flows_all) - SCAN_COMPACT_RELATION_ROW_LIMIT
            ),
            "dependency_total": len(compact_edges_all),
            "dependency_catalog_omitted": max(
                0, len(compact_edges_all) - SCAN_COMPACT_RELATION_ROW_LIMIT
            ),
            "binding_total": len(compact_bindings_all),
            "binding_catalog_omitted": max(
                0, len(compact_bindings_all) - SCAN_COMPACT_RELATION_ROW_LIMIT
            ),
        },
    }


def _render_scan_payload(payload: Mapping[str, Any]) -> str:
    return canonical_scan_template_text().replace(
        SCAN_EVIDENCE_PLACEHOLDER,
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def global_scan_batches(
    view: ProposalEvidenceView,
    *,
    max_primary_cards: int = SCAN_MAX_PRIMARY_CARDS,
    max_rendered_utf8_bytes: int = SCAN_MAX_RENDERED_UTF8_BYTES,
    max_single_primary_rendered_utf8_bytes: int = (
        SCAN_MAX_SINGLE_PRIMARY_RENDERED_UTF8_BYTES
    ),
) -> tuple[tuple[str, ...], ...]:
    if max_single_primary_rendered_utf8_bytes < max_rendered_utf8_bytes:
        raise ValueError("single-primary scan bound must cover the normal bound")
    payload = view.model_dump(mode="json")
    requests = {str(row["request_ref"]): row for row in payload["api_requests"]}
    atomic = sorted(
        (
            card
            for card in payload["evidence_cards"]
            if card["card_kind"] in {"action_episode", "unassigned_request"}
        ),
        key=lambda card: _recording_order_key(card, requests),
    )
    batches: list[tuple[str, ...]] = []
    current: list[str] = []
    for card in atomic:
        candidate = (*current, str(card["card_id"]))
        batch_id = f"global-scan-{len(batches) + 1:04d}"
        rendered_size = len(
            _render_scan_payload(
                _scan_batch_payload(view, candidate, batch_id=batch_id)
            ).encode("utf-8")
        )
        if current and (
            len(candidate) > max_primary_cards
            or rendered_size > max_rendered_utf8_bytes
        ):
            batches.append(tuple(current))
            current = [str(card["card_id"])]
            batch_id = f"global-scan-{len(batches) + 1:04d}"
            rendered_size = len(
                _render_scan_payload(
                    _scan_batch_payload(view, tuple(current), batch_id=batch_id)
                ).encode("utf-8")
            )
        else:
            current = list(candidate)
        if rendered_size > max_single_primary_rendered_utf8_bytes:
            raise ValueError(
                f"scan_primary_too_large:{card['card_id']}:{rendered_size}"
            )
        if rendered_size > max_rendered_utf8_bytes:
            if len(current) != 1:
                raise ValueError("scan soft overflow must contain one primary card")
            batches.append(tuple(current))
            current = []
    if current:
        batches.append(tuple(current))
    return tuple(batches)


def scan_soft_overflow_bytes(
    view: ProposalEvidenceView,
    batches: tuple[tuple[str, ...], ...],
    *,
    max_rendered_utf8_bytes: int = SCAN_MAX_RENDERED_UTF8_BYTES,
    max_single_primary_rendered_utf8_bytes: int = (
        SCAN_MAX_SINGLE_PRIMARY_RENDERED_UTF8_BYTES
    ),
) -> dict[int, int]:
    """Return zero-based batch indexes for permitted singleton soft overflows."""

    result: dict[int, int] = {}
    for index, card_ids in enumerate(batches):
        batch_id = f"global-scan-{index + 1:04d}"
        rendered_size = len(
            _render_scan_payload(
                _scan_batch_payload(view, card_ids, batch_id=batch_id)
            ).encode("utf-8")
        )
        if rendered_size <= max_rendered_utf8_bytes:
            continue
        if (
            len(card_ids) != 1
            or rendered_size > max_single_primary_rendered_utf8_bytes
        ):
            raise ValueError(
                f"scan_primary_too_large:{card_ids[0]}:{rendered_size}"
            )
        result[index] = rendered_size
    return result


def _render_payload_input(
    frozen: V2FrozenInput,
    *,
    input_id: str,
    payload: Mapping[str, Any],
    template: str,
    template_sha256: str,
    placeholder: str,
) -> RenderedCandidateInput:
    rendered_text = template.replace(
        placeholder,
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    if placeholder in rendered_text:
        raise ValueError("proposal template placeholder was not replaced")
    return RenderedCandidateInput(
        input_id=input_id,
        package_sha256=frozen.lineage.package.canonical_sha256(),
        view_sha256=frozen.lineage.view.canonical_sha256(),
        template_sha256=template_sha256,
        rendered_text=rendered_text,
        rendered_sha256=hashlib.sha256(rendered_text.encode("utf-8")).hexdigest(),
        source_refs=("preproposal_evidence_package", "proposal_evidence_view"),
        source_sha256={
            "preproposal_evidence_package": frozen.lineage.package.canonical_sha256(),
            "proposal_evidence_view": frozen.lineage.view.canonical_sha256(),
            "canonical_template": template_sha256,
        },
    )


def _parse_scan_response(content: str) -> ScanResponse:
    if not isinstance(content, str):
        raise ValueError("scan response content must be JSON text")
    try:
        payload = json.loads(
            content,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant is forbidden: {value}")
            ),
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("scan response is not strict JSON") from exc
    return ScanResponse.model_validate(payload, strict=True)


def _reference_order(view: ProposalEvidenceView) -> dict[str, tuple[int, int, str]]:
    payload = view.model_dump(mode="json")
    request_order = {
        str(row["request_ref"]): int(row["global_order"])
        for row in payload["api_requests"]
    }
    action_order = {
        str(row["event_id"]): int(row["global_order"])
        for row in payload["ui_actions"]
    }
    order: dict[str, tuple[int, int, str]] = {}
    for ref, value in request_order.items():
        order[ref] = (value, 0, ref)
    for ref, value in action_order.items():
        order[ref] = (value, 1, ref)
    for card in payload["evidence_cards"]:
        refs = [request_order[ref] for ref in card["request_refs"] if ref in request_order]
        order[str(card["card_id"])] = (min(refs, default=10**12), 2, str(card["card_id"]))
    for field, id_key, rank in (
        ("observed_value_flows", "flow_id", 3),
        ("dependency_edges", "edge_id", 4),
        ("binding_opportunities", "opportunity_id", 5),
    ):
        for row in payload[field]:
            ref = str(row[id_key])
            endpoints = [
                request_order[item]
                for item in (
                    row.get("producer_request_ref"),
                    row.get("consumer_request_ref"),
                )
                if item in request_order
            ]
            order[ref] = (min(endpoints, default=10**12), rank, ref)
    for row in (
        payload.get("evidence_channel_summaries", {})
        .get("ui_diff", {})
        .get("semantic_projection", {})
        .get("rows", ())
    ):
        ref = str(row["record_id"])
        endpoints = [
            request_order[item]
            for item in (
                *row.get("preceding_request_refs", ()),
                *row.get("following_request_refs", ()),
            )
            if item in request_order
        ]
        order[ref] = (min(endpoints, default=10**12), 6, ref)
    for row in payload.get("transition_facts", ()):
        ref = str(row["fact_id"])
        endpoints = [
            request_order[item]
            for item in (
                row.get("before_request_ref"),
                row.get("after_request_ref"),
            )
            if item in request_order
        ]
        order[ref] = (min(endpoints, default=10**12), 7, ref)
    for row in payload.get("negative_request_facts", ()):
        ref = str(row["fact_id"])
        projection = row.get("projection") or {}
        endpoints = [
            request_order[item]
            for item in (
                row.get("setup_request_ref"),
                projection.get("before_request_ref"),
                row.get("negative_request_ref"),
                projection.get("after_request_ref"),
            )
            if item in request_order
        ]
        order[ref] = (min(endpoints, default=10**12), 8, ref)
    return order


def _normalize_scan_decisions(
    response: ScanResponse,
    *,
    batch_payload: Mapping[str, Any],
    view: ProposalEvidenceView,
) -> tuple[dict[str, Any], ...]:
    primary_rows = {
        str(row["primary_card_id"]): row for row in batch_payload["primary_cards"]
    }
    decision_ids = [row.primary_card_id for row in response.decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("scan response contains duplicate primary decisions")
    if set(decision_ids) != set(primary_rows):
        raise ValueError("scan response must decide every primary card exactly once")
    normalized: list[dict[str, Any]] = []
    order = _reference_order(view)
    batch_allowed = {
        str(ref)
        for row in primary_rows.values()
        for ref in row["allowed_reference_ids"]
    }
    decisions_by_id = {row.primary_card_id: row for row in response.decisions}
    for primary_card_id in primary_rows:
        decision = decisions_by_id[primary_card_id]
        selections: set[tuple[str, ...]] = set()
        for selection in decision.detail_selections:
            if not set(selection.refs) <= batch_allowed:
                raise ValueError("scan selection references an ID outside the visible batch")
            selections.add(tuple(sorted(selection.refs, key=lambda ref: order[ref])))
        normalized.append({
            "primary_card_id": decision.primary_card_id,
            "decision": decision.decision,
            "detail_selections": [list(row) for row in sorted(selections)],
        })
    return tuple(normalized)


def _detail_indexes(view: ProposalEvidenceView) -> dict[str, Any]:
    payload = view.model_dump(mode="json")
    cards = {str(row["card_id"]): row for row in payload["evidence_cards"]}
    requests = {str(row["request_ref"]): row for row in payload["api_requests"]}
    actions = {str(row["event_id"]): row for row in payload["ui_actions"]}
    automatic_bindings = {
        str(row["binding_id"]): row for row in payload["automatic_bindings"]
    }
    ui_rows = {
        str(row["record_id"]): row
        for row in (
            payload.get("evidence_channel_summaries", {})
            .get("ui_diff", {})
            .get("semantic_projection", {})
            .get("rows", ())
        )
    }
    flows = {str(row["flow_id"]): row for row in payload["observed_value_flows"]}
    edges = {str(row["edge_id"]): row for row in payload["dependency_edges"]}
    bindings = {
        str(row["opportunity_id"]): row for row in payload["binding_opportunities"]
    }
    transitions = {
        str(row["fact_id"]): row for row in payload.get("transition_facts", ())
    }
    negative_facts = {
        str(row["fact_id"]): row
        for row in payload.get("negative_request_facts", ())
    }
    flow_order = {ref: int(row["global_order"]) for ref, row in requests.items()}
    edge_witnesses: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for flow in flows.values():
        key = (
            str(flow["producer_operation_id"]),
            str(flow["consumer_operation_id"]),
        )
        edge_witnesses.setdefault(key, []).append(flow)
    ordered_edge_witnesses = {
        key: tuple(sorted(
            rows,
            key=lambda flow: (
                flow_order.get(str(flow.get("producer_request_ref")), 10**12),
                flow_order.get(str(flow.get("consumer_request_ref")), 10**12),
                str(flow["flow_id"]),
            ),
        ))
        for key, rows in edge_witnesses.items()
    }
    return {
        "payload": payload,
        "cards": cards,
        "requests": requests,
        "actions": actions,
        "automatic_bindings": automatic_bindings,
        "ui": ui_rows,
        "flows": flows,
        "edges": edges,
        "bindings": bindings,
        "transitions": transitions,
        "negative_facts": negative_facts,
        "edge_witnesses": ordered_edge_witnesses,
    }


def _recorded_state_change_refs(
    frozen: V2FrozenInput,
) -> tuple[set[str], set[str]]:
    """Return observed business and profile-managed auth request refs.

    Producer applicability is an existing M3-M9 mechanical fact.  It is used
    only to recognize recorded state-changing actions and authentication
    boundaries; it does not label any request as a relation role.
    """

    applicability = frozen.lineage.package.artifact_payloads.get(
        "producer_applicability", {}
    )
    producers = applicability.get("producers", ())
    business = {
        str(row["request_ref"])
        for row in producers
        if isinstance(row, Mapping) and row.get("request_ref")
    }
    authentication = {
        str(ref)
        for row in producers
        if isinstance(row, Mapping)
        for ref in row.get("profile_managed_setup_request_refs", ())
        if ref
    }
    return business, authentication


def _is_graphql_transport(request: Mapping[str, Any]) -> bool:
    shape_paths = {
        str(row.get("path"))
        for row in (request.get("request_body_shape") or {}).get(
            "shape_rows", ()
        )
    }
    return "$.query" in shape_paths


def _is_recorded_state_change(
    request: Mapping[str, Any],
    *,
    business_refs: set[str],
    authentication_refs: set[str],
) -> bool:
    request_ref = str(request["request_ref"])
    if request_ref in business_refs or request_ref in authentication_refs:
        return True
    if "state_change_like" in set(map(str, request.get("weak_roles", ()))):
        return True
    if str(request.get("method", "")).upper() in READ_METHODS:
        return False
    if request.get("declared_read_semantic") is True:
        # Profile-declared read-semantic endpoint (M2 fact carried by the view
        # row); a write method with read semantics is not a recorded state change.
        return False
    # GraphQL uses POST for queries and mutations.  In the protocol-neutral M9
    # view only the existing mechanical state-change signal distinguishes them.
    return not _is_graphql_transport(request)


def _shape_signature(shape: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (str(row.get("path", "")), str(row.get("type", "")))
            for row in shape.get("shape_rows", ())
            if isinstance(row, Mapping)
        )
    )


def _recorded_post_query_evidence(
    frozen: V2FrozenInput,
) -> dict[str, dict[str, Any]]:
    """Recover repeatable POST queries from frozen, protocol-neutral facts.

    POST remains mutating by default.  A request is classified as a query only
    when the same actor/session repeatedly issued the same selector shape, the
    successful responses share a collection path, and at least one occurrence
    was recorded as background/review observation rather than being inferred
    from an HTTP path or a response value.
    """

    rows = tuple(frozen.lineage.view.api_requests)
    applicability = frozen.lineage.package.artifact_payloads.get(
        "producer_applicability", {}
    )
    anchored_producer_refs = {
        str(row["request_ref"])
        for row in applicability.get("producers", ())
        if isinstance(row, Mapping)
        and row.get("request_ref")
        and row.get("applicability") == "available"
        and row.get("anchor_event_id")
    }
    business_refs, authentication_refs = _recorded_state_change_refs(frozen)
    recorded_state_change_refs = business_refs | authentication_refs
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        if str(row.get("method", "")).upper() != "POST":
            continue
        if _is_graphql_transport(row):
            continue
        grouped.setdefault(
            (
                str(row.get("operation_id", "")),
                str(row.get("actor_id", "")),
                str(row.get("session_run_id", "")),
            ),
            [],
        ).append(row)

    evidence: dict[str, dict[str, Any]] = {}
    scalar_types = {"boolean", "integer", "number", "null", "string"}
    observation_statuses = {"review_required", "unassigned"}
    conflicting_statuses = {201, 202, 204}
    for peers in grouped.values():
        if len(peers) < 2 or any(
            row.get("response_status") in conflicting_statuses for row in peers
        ):
            continue
        if any(
            str(row.get("request_ref", "")) in recorded_state_change_refs
            or "state_change_like" in set(map(str, row.get("weak_roles", ())))
            for row in peers
        ):
            continue
        conflicting_refs = {
            str(row.get("request_ref", ""))
            for row in peers
            if str(row.get("request_ref", "")) in anchored_producer_refs
            or bool(row.get("is_anchor"))
        }
        if any(row.get("response_status") != 200 for row in peers):
            continue
        if not any(
            str(row.get("association_status", "")) in observation_statuses
            for row in peers
        ):
            continue
        for row in peers:
            if str(row.get("request_ref", "")) in conflicting_refs:
                continue
            request_shape = _shape_signature(row.get("request_body_shape") or {})
            selector_body_sha256 = (row.get("request_body_shape") or {}).get(
                "body_sha256"
            )
            if not isinstance(selector_body_sha256, str) or re.fullmatch(
                r"[0-9a-f]{64}", selector_body_sha256
            ) is None:
                continue
            selector_paths = tuple(
                path
                for path, value_type in request_shape
                if path != "$" and value_type in scalar_types
            )
            if not selector_paths:
                continue
            response_arrays = response_collection_paths_with_identity(
                row.get("response_body_shape") or {}
            )
            if not response_arrays:
                continue
            witnesses = []
            common_collection_paths: set[str] = set()
            for peer in peers:
                if (
                    peer is row
                    or str(peer.get("request_ref", "")) in conflicting_refs
                    or _shape_signature(
                    peer.get("request_body_shape") or {}
                    ) != request_shape
                ):
                    continue
                peer_arrays = response_collection_paths_with_identity(
                    peer.get("response_body_shape") or {}
                )
                shared = response_arrays & peer_arrays
                if shared:
                    witnesses.append(str(peer["request_ref"]))
                    common_collection_paths.update(shared)
            if not witnesses:
                continue
            evidence[str(row["request_ref"])] = {
                "kind": "recorded_post_query",
                "selector_paths": selector_paths,
                "selector_body_sha256": selector_body_sha256,
                "response_collection_paths": tuple(sorted(common_collection_paths)),
                "repeated_observation_request_refs": tuple(sorted(witnesses)),
            }
    return evidence


def _request_execution_attributes(
    frozen: V2FrozenInput,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Project frozen M2/M3 facts into post-proposal execution mechanics."""

    business_refs, authentication_refs = _recorded_state_change_refs(frozen)
    state_change_refs = business_refs | authentication_refs
    trace_payload = frozen.lineage.package.artifact_payloads.get(
        "ui_api_trace", {}
    )
    trace_requests = (trace_payload.get("trace") or {}).get(
        "api_requests", ()
    )
    graphql_kinds = {
        str(row["request_ref"]): str(row["graphql_operation_kind"])
        for row in trace_requests
        if isinstance(row, Mapping)
        and row.get("request_ref")
        and row.get("graphql_operation_kind") is not None
    }
    recorded_post_queries = _recorded_post_query_evidence(frozen)
    declared_read_refs = {
        str(row["request_ref"])
        for row in trace_requests
        if isinstance(row, Mapping)
        and row.get("request_ref")
        and row.get("declared_read_semantic") is True
    }
    kinds: dict[str, str] = {}
    read_evidence: dict[str, dict[str, Any]] = {}
    for request in frozen.lineage.view.api_requests:
        ref = str(request["request_ref"])
        method = str(request.get("method", "")).upper()
        if method in READ_METHODS:
            kinds[ref] = "read"
            continue
        if method not in WRITE_METHODS:
            kinds[ref] = "unknown"
            continue
        if ref in declared_read_refs:
            # Profile-declared read-semantic endpoint (M2 fact carried by the
            # trace record); it is a read for every proposer plan.
            kinds[ref] = "read"
            continue
        if ref in recorded_post_queries:
            kinds[ref] = "read"
            read_evidence[ref] = recorded_post_queries[ref]
            continue
        if not _is_graphql_transport(request):
            kinds[ref] = "write"
            continue
        recorded_graphql_kind = graphql_kinds.get(ref)
        if recorded_graphql_kind in {"query", "mutation"}:
            kinds[ref] = (
                "read" if recorded_graphql_kind == "query" else "write"
            )
            continue
        if recorded_graphql_kind is not None:
            kinds[ref] = "unknown"
            continue
        # Frozen inputs created before M2 retained the parsed operation kind
        # still carry mutation membership in M3.  Response shape distinguishes
        # their already-observed query calls without changing provider input.
        if ref in state_change_refs:
            kinds[ref] = "write"
            continue
        response_paths = {
            str(row.get("path"))
            for row in (request.get("response_body_shape") or {}).get(
                "shape_rows", ()
            )
        }
        kinds[ref] = (
            "read"
            if any(
                path == "$.data" or path.startswith("$.data.")
                for path in response_paths
            )
            else "unknown"
        )
    return kinds, read_evidence


def _request_execution_kinds(frozen: V2FrozenInput) -> dict[str, str]:
    return _request_execution_attributes(frozen)[0]


def _business_operation_episodes(
    frozen: V2FrozenInput,
    indexes: Mapping[str, Any],
) -> dict[str, _BusinessOperationEpisode]:
    """Build one actor-bounded, globally ordered episode for each write-like action."""

    cards = indexes["cards"]
    requests = indexes["requests"]
    business_refs, authentication_refs = _recorded_state_change_refs(frozen)
    atomic = sorted(
        (
            card
            for card in cards.values()
            if card["card_kind"] in {"action_episode", "unassigned_request"}
        ),
        key=lambda card: _recording_order_key(card, requests),
    )
    action_cards = [card for card in atomic if card["card_kind"] == "action_episode"]
    centers: list[tuple[Mapping[str, Any], tuple[int, str], str, str]] = []
    for card in action_cards:
        state_refs = {
            str(ref)
            for ref in card["request_refs"]
            if _is_recorded_state_change(
                requests[str(ref)],
                business_refs=business_refs,
                authentication_refs=authentication_refs,
            )
        }
        if not state_refs:
            continue
        authentication_only = (
            bool(state_refs & authentication_refs)
            and not bool(state_refs & business_refs)
            and state_refs <= authentication_refs
        )
        actor_ids = tuple(map(str, card["actor_ids"]))
        if len(actor_ids) != 1:
            raise ValueError("business-operation episode center must have one actor")
        centers.append((
            card,
            _recording_order_key(card, requests),
            "authentication" if authentication_only else "state_change",
            actor_ids[0],
        ))

    episodes: dict[str, _BusinessOperationEpisode] = {}
    for center, center_key, center_kind, center_actor in centers:
        non_auth_keys = [
            key
            for _, key, kind, actor in centers
            if kind == "state_change" and actor == center_actor
        ]
        previous = max((key for key in non_auth_keys if key < center_key), default=None)
        following = min((key for key in non_auth_keys if key > center_key), default=None)
        core = tuple(
            str(card["card_id"])
            for card in atomic
            if (previous is None or _recording_order_key(card, requests) > previous)
            and (following is None or _recording_order_key(card, requests) < following)
        )
        center_card_id = str(center["card_id"])
        if center_card_id not in core:
            raise ValueError("business-operation episode omitted its center action")
        center_actions = tuple(map(str, center["action_event_ids"]))
        if len(center_actions) != 1:
            raise ValueError("business-operation episode center must be one UI action")
        episodes[center_card_id] = _BusinessOperationEpisode(
            center_card_id=center_card_id,
            center_action_id=center_actions[0],
            center_kind=center_kind,
            core_card_ids=core,
        )
    return episodes


def _operation_edge_witnesses(
    edge: Mapping[str, Any], indexes: Mapping[str, Any]
) -> tuple[Mapping[str, Any], ...]:
    producer_operation = str(edge["producer_operation_id"])
    consumer_operation = str(edge["consumer_operation_id"])
    return tuple(indexes["edge_witnesses"].get(
        (producer_operation, consumer_operation), ()
    ))


def _complete_request_groups(
    *,
    request_refs: set[str],
    action_ids: set[str],
    indexes: Mapping[str, Any],
) -> tuple[set[str], set[str]]:
    """Close only explicitly selected actions and endpoint request groups."""

    requests = indexes["requests"]
    unknown_requests = request_refs - set(requests)
    unknown_actions = action_ids - set(indexes["actions"])
    if unknown_requests or unknown_actions:
        raise ValueError("detail fact contains an unknown request or action reference")
    groups = {
        requests[ref].get("request_group_id")
        for ref in request_refs
        if requests[ref].get("request_group_id") is not None
    }
    completed = {
        ref
        for ref, row in requests.items()
        if ref in request_refs
        or row.get("request_group_id") in groups
        or row.get("action_event_id") in action_ids
    }
    completed_actions = set(action_ids)
    completed_actions.update(
        str(requests[ref]["action_event_id"])
        for ref in completed
        if requests[ref].get("action_event_id") in indexes["actions"]
    )
    return completed, completed_actions


def _transition_is_center_local(
    row: Mapping[str, Any],
    *,
    center_state_change_request_refs: tuple[str, ...],
    requests: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Return whether a transition interval explicitly contains this center."""

    before_ref = str(row["before_request_ref"])
    after_ref = str(row["after_request_ref"])
    before_order = int(requests[before_ref]["global_order"])
    after_order = int(requests[after_ref]["global_order"])
    center_refs = set(center_state_change_request_refs)
    if not any(
        before_order < int(requests[ref]["global_order"]) < after_order
        for ref in center_refs
    ):
        return False
    competition = row.get("write_competition") or {}
    competition_refs = {
        str(item["request_ref"])
        for item in competition.get("assessments", ())
        if isinstance(item, Mapping) and item.get("request_ref")
    }
    groundable = competition.get("groundable_effect_source_request_ref")
    if groundable:
        competition_refs.add(str(groundable))
    return bool(center_refs & competition_refs)


def _read_comparison_key(
    ref: str,
    *,
    requests: Mapping[str, Mapping[str, Any]],
    catalog_operations: Mapping[str, str],
) -> tuple[str, str, str, str] | None:
    operation_id = catalog_operations.get(ref)
    if operation_id is None:
        return None
    row = requests[ref]
    return (
        str(row["actor_id"]),
        str(row["session_run_id"]),
        operation_id,
        _selector_snapshot_sha256(row),
    )


def _nearest_comparable_pre_state_refs(
    post_ref: str,
    *,
    center_order: int,
    requests: Mapping[str, Mapping[str, Any]],
    execution_kinds: Mapping[str, str],
    catalog_operations: Mapping[str, str],
) -> tuple[tuple[str, str, str, str] | None, tuple[str, ...]]:
    """Retain the complete nearest request group, or no guessed pre-state."""

    key = _read_comparison_key(
        post_ref,
        requests=requests,
        catalog_operations=catalog_operations,
    )
    candidates = sorted(
        (
            ref
            for ref in requests
            if execution_kinds.get(ref) == "read"
            and int(requests[ref]["global_order"]) < center_order
            and key is not None
            and _read_comparison_key(
                ref,
                requests=requests,
                catalog_operations=catalog_operations,
            )
            == key
        ),
        key=lambda ref: (int(requests[ref]["global_order"]), ref),
    )
    if not candidates:
        return key, ()
    latest = candidates[-1]
    latest_group = requests[latest].get("request_group_id")
    nearest = tuple(
        ref
        for ref in candidates
        if (
            requests[ref].get("request_group_id") == latest_group
            if latest_group is not None
            else ref == latest
        )
    )
    return key, nearest


def _center_observation_slice(
    frozen: V2FrozenInput,
    *,
    episode: _BusinessOperationEpisode,
    core_request_refs: set[str],
    center_state_change_request_refs: tuple[str, ...],
    indexes: Mapping[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    """Pair local post-state reads with their nearest comparable pre-state reads."""

    requests = indexes["requests"]
    execution_kinds = _request_execution_kinds(frozen)
    catalog = frozen.lineage.package.artifact_payloads.get(
        "observed_api_catalog", {}
    )
    catalog_operations = _catalog_request_operations(
        list(catalog.get("operations", ()))
    )
    center_orders = [
        int(requests[ref]["global_order"])
        for ref in center_state_change_request_refs
    ]
    center_order_min = min(center_orders)
    center_order_max = max(center_orders)
    business_refs, authentication_refs = _recorded_state_change_refs(frozen)

    def changes_state(ref: str) -> bool:
        return _is_recorded_state_change(
            requests[ref],
            business_refs=business_refs,
            authentication_refs=authentication_refs,
        )

    immediate_ui_diff_refs = sorted(
        ref
        for ref, row in indexes["ui"].items()
        if row.get("event_id") == episode.center_action_id
    )
    transition_fact_refs = sorted(
        ref
        for ref, row in indexes["transitions"].items()
        if _transition_is_center_local(
            row,
            center_state_change_request_refs=center_state_change_request_refs,
            requests=requests,
        )
    )
    directly_linked_post_refs = {
        str(ref)
        for diff_ref in immediate_ui_diff_refs
        for ref in indexes["ui"][diff_ref].get("following_request_refs", ())
        if ref in requests
    } | {
        str(indexes["transitions"][ref]["after_request_ref"])
        for ref in transition_fact_refs
    }
    next_state_change_order = min(
        (
            int(requests[ref]["global_order"])
            for ref in requests
            if changes_state(ref)
            and int(requests[ref]["global_order"]) > center_order_max
        ),
        default=None,
    )
    candidate_post_refs = sorted(
        (
            ref
            for ref in core_request_refs
            if execution_kinds.get(ref) == "read"
            and int(requests[ref]["global_order"]) > center_order_max
        ),
        key=lambda ref: (int(requests[ref]["global_order"]), ref),
    )
    pre_state_refs: set[str] = set()
    post_refs: list[str] = []
    required_request_refs: set[str] = set()
    competing_refs: set[str] = set()
    observations: list[dict[str, Any]] = []
    for post_ref in candidate_post_refs:
        key, nearest = _nearest_comparable_pre_state_refs(
            post_ref,
            center_order=center_order_min,
            requests=requests,
            execution_kinds=execution_kinds,
            catalog_operations=catalog_operations,
        )
        nearest_refs = list(nearest)
        status = (
            "none"
            if not nearest_refs
            else "unique"
            if len(nearest_refs) == 1
            else "multiple"
        )
        post_order = int(requests[post_ref]["global_order"])
        if not (
            next_state_change_order is None
            or post_order < next_state_change_order
            or nearest_refs
            or post_ref in directly_linked_post_refs
        ):
            continue
        post_refs.append(post_ref)
        required_request_refs.add(post_ref)
        pre_state_refs.update(nearest_refs)
        required_request_refs.update(nearest_refs)
        interval_start = (
            min(int(requests[ref]["global_order"]) for ref in nearest_refs)
            if nearest_refs
            else center_order_min
        )
        intervening_refs = sorted(
            (
                ref
                for ref in requests
                if changes_state(ref)
                and interval_start
                < int(requests[ref]["global_order"])
                < int(requests[post_ref]["global_order"])
            ),
            key=lambda ref: (int(requests[ref]["global_order"]), ref),
        )
        required_request_refs.update(intervening_refs)
        competing_refs.update(
            set(intervening_refs) - set(center_state_change_request_refs)
        )
        observations.append({
            "post_state_request_ref": post_ref,
            "comparable_pre_state_status": status,
            "nearest_pre_state_request_refs": nearest_refs,
            "intervening_state_change_request_refs": intervening_refs,
            "comparison_identity": (
                None
                if key is None
                else {
                    "actor_id": key[0],
                    "session_run_id": key[1],
                    "catalog_operation_id": key[2],
                    "selector_snapshot_sha256": key[3],
                }
            ),
        })

    center_ref_set = set(center_state_change_request_refs)
    transition_competing_refs = {
        str(item["request_ref"])
        for ref in transition_fact_refs
        for item in (
            indexes["transitions"][ref]
            .get("write_competition", {})
            .get("assessments", ())
        )
        if isinstance(item, Mapping)
        and item.get("request_ref") in requests
        and str(item["request_ref"]) not in center_ref_set
    }
    competing_refs.update(transition_competing_refs)
    required_request_refs.update(transition_competing_refs)
    ordered_competing_refs = sorted(
        competing_refs,
        key=lambda ref: (int(requests[ref]["global_order"]), ref),
    )
    observation_slice = {
        "comparison_rule": (
            "same_actor_session_catalog_operation_and_selector_nearest_"
            "request_group_v1"
        ),
        "center_action_id": episode.center_action_id,
        "center_state_change_request_refs": list(
            center_state_change_request_refs
        ),
        "immediate_ui_diff_refs": immediate_ui_diff_refs,
        "pre_state_request_refs": sorted(
            pre_state_refs,
            key=lambda ref: (int(requests[ref]["global_order"]), ref),
        ),
        "post_state_request_refs": post_refs,
        "post_state_observations": observations,
        "center_interval_transition_fact_refs": transition_fact_refs,
        "competing_state_change_request_refs": ordered_competing_refs,
    }
    return observation_slice, required_request_refs


def _observer_operation_catalog(
    frozen: V2FrozenInput,
    *,
    center_state_change_request_refs: tuple[str, ...],
    observation_slice: Mapping[str, Any],
    indexes: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Project neutral M5 reads that can supply a fresh M12 observation.

    The model sees operation identities and response shapes, never a URL,
    selector value, body value, or concrete request reference.  Concrete
    templates remain internal so M10 can require an exact observed source.
    """

    requests = indexes["requests"]
    execution_kinds = _request_execution_kinds(frozen)
    center_actor_sessions = {
        (
            str(requests[ref]["actor_id"]),
            str(requests[ref]["session_run_id"]),
        )
        for ref in center_state_change_request_refs
    }
    explicit_pairs = {
        (
            str(identity["catalog_operation_id"]),
            str(identity["actor_id"]),
            str(identity["session_run_id"]),
        )
        for observation in observation_slice.get("post_state_observations", ())
        if observation.get("comparable_pre_state_status") == "unique"
        and isinstance(observation.get("comparison_identity"), Mapping)
        for identity in (observation["comparison_identity"],)
    }
    if explicit_pairs:
        return ()
    operations: list[dict[str, Any]] = []
    for operation in frozen.lineage.view.api_operations:
        operation_id = str(operation["operation_id"])
        method = str(operation["method"]).upper()
        canonical_path = str(operation["canonical_path"])
        templates: dict[str, dict[str, Any]] = {}
        for request_ref in operation.get("stage1_request_refs", ()):
            request = requests.get(str(request_ref))
            if not isinstance(request, Mapping):
                raise ValueError("catalog observer request is absent from M9 trace")
            actor_session = (
                str(request["actor_id"]),
                str(request["session_run_id"]),
            )
            if (
                actor_session not in center_actor_sessions
                or execution_kinds.get(str(request_ref)) != "read"
                or str(request.get("operation_id")) != operation_id
                or str(request.get("method", "")).upper() != method
                or str(request.get("canonical_path")) != canonical_path
            ):
                continue
            response_shape = copy.deepcopy(
                dict(request.get("response_body_shape") or {})
            )
            selector_sha = _selector_snapshot_sha256(request)
            template_payload = {
                "actor_id": actor_session[0],
                "session_run_id": actor_session[1],
                "operation_id": operation_id,
                "method": method,
                "canonical_path": canonical_path,
                "selector_snapshot_sha256": selector_sha,
                "response_body_shape_sha256": canonical_sha256(response_shape),
            }
            template_sha = canonical_sha256(template_payload)
            candidate = {
                **template_payload,
                "template_sha256": template_sha,
                "request_ref": str(request_ref),
                "global_order": int(request["global_order"]),
                "response_body_shape": response_shape,
            }
            previous = templates.get(template_sha)
            if previous is None or (
                candidate["global_order"], candidate["request_ref"]
            ) < (previous["global_order"], previous["request_ref"]):
                templates[template_sha] = candidate
        if not templates:
            continue
        operations.append({
            "operation_id": operation_id,
            "method": method,
            "canonical_path": canonical_path,
            "readiness": str(operation["readiness"]),
            "catalog_operation_sha256": str(operation["full_row_sha256"]),
            "templates": tuple(
                sorted(
                    templates.values(),
                    key=lambda row: (
                        row["actor_id"],
                        row["session_run_id"],
                        row["template_sha256"],
                        row["request_ref"],
                    ),
                )
            ),
        })
    return tuple(sorted(operations, key=lambda row: row["operation_id"]))


def _binding_witness(
    binding: Mapping[str, Any], indexes: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    witness_id = binding.get("witness_flow_id")
    if witness_id is None:
        return None
    return indexes["flows"].get(str(witness_id))


def _fact_unit(
    *,
    selected_ref: str,
    request_refs: set[str],
    action_ids: set[str],
    display_action_ids: set[str] | None = None,
    evidence_refs: set[str],
    card_ids: set[str],
    indexes: Mapping[str, Any],
    order_suffix: str,
) -> _DetailFactUnit:
    completed_requests, completed_actions = _complete_request_groups(
        request_refs=request_refs,
        action_ids=action_ids,
        indexes=indexes,
    )
    completed_actions.update(display_action_ids or ())
    request_order = {
        ref: int(row["global_order"]) for ref, row in indexes["requests"].items()
    }
    return _DetailFactUnit(
        selected_ref=selected_ref,
        request_refs=frozenset(completed_requests),
        action_ids=frozenset(completed_actions),
        evidence_refs=frozenset(evidence_refs),
        card_ids=frozenset(card_ids),
        order_key=(
            min((request_order[ref] for ref in completed_requests), default=10**12),
            len(completed_requests),
            order_suffix,
        ),
    )


def _root_detail_fact(
    primary_card_id: str, indexes: Mapping[str, Any]
) -> _DetailFactUnit:
    card = indexes["cards"].get(primary_card_id)
    if card is None or card["card_kind"] not in {
        "action_episode", "unassigned_request"
    }:
        raise ValueError("detail root must be one atomic M9 card")
    return _fact_unit(
        selected_ref=primary_card_id,
        request_refs=set(map(str, card["request_refs"])),
        action_ids=set(map(str, card["action_event_ids"])),
        evidence_refs=set(),
        card_ids={primary_card_id},
        indexes=indexes,
        order_suffix=primary_card_id,
    )


def _selected_detail_fact_units(
    ref: str, indexes: Mapping[str, Any]
) -> tuple[_DetailFactUnit, ...]:
    cards = indexes["cards"]
    requests = indexes["requests"]
    actions = indexes["actions"]
    if ref in cards:
        card = cards[ref]
        if card["card_kind"] == "mechanical_neighborhood":
            units: list[_DetailFactUnit] = []
            for component_id in card["component_card_ids"]:
                component = cards[str(component_id)]
                if component["card_kind"] == "mechanical_neighborhood":
                    raise ValueError("mechanical neighborhood components must be atomic")
                units.append(_fact_unit(
                    selected_ref=ref,
                    request_refs=set(map(str, component["request_refs"])),
                    action_ids=set(map(str, component["action_event_ids"])),
                    evidence_refs={ref, str(component_id)},
                    card_ids={str(component_id)},
                    indexes=indexes,
                    order_suffix=str(component_id),
                ))
            return tuple(sorted(units, key=lambda unit: unit.order_key))
        return (_fact_unit(
            selected_ref=ref,
            request_refs=set(map(str, card["request_refs"])),
            action_ids=set(map(str, card["action_event_ids"])),
            evidence_refs={ref},
            card_ids={ref},
            indexes=indexes,
            order_suffix=ref,
        ),)
    if ref in requests:
        return (_fact_unit(
            selected_ref=ref,
            request_refs={ref},
            action_ids=set(),
            evidence_refs=set(),
            card_ids=set(),
            indexes=indexes,
            order_suffix=ref,
        ),)
    if ref in actions:
        return (_fact_unit(
            selected_ref=ref,
            request_refs=set(),
            action_ids={ref},
            evidence_refs=set(),
            card_ids=set(),
            indexes=indexes,
            order_suffix=ref,
        ),)
    if ref in indexes["ui"]:
        row = indexes["ui"][ref]
        endpoints = {
            *map(str, row.get("preceding_request_refs", ())),
            *map(str, row.get("following_request_refs", ())),
        } & set(requests)
        action_ids = (
            {str(row["event_id"])} if row.get("event_id") in actions else set()
        )
        return (_fact_unit(
            selected_ref=ref,
            request_refs=endpoints,
            action_ids=set(),
            display_action_ids=action_ids,
            evidence_refs={ref},
            card_ids=set(),
            indexes=indexes,
            order_suffix=ref,
        ),)
    if ref in indexes["flows"]:
        row = indexes["flows"][ref]
        endpoints = {
            str(row[key])
            for key in ("producer_request_ref", "consumer_request_ref")
            if row.get(key) in requests
        }
        return (_fact_unit(
            selected_ref=ref,
            request_refs=endpoints,
            action_ids=set(),
            evidence_refs={ref},
            card_ids=set(),
            indexes=indexes,
            order_suffix=ref,
        ),)
    if ref in indexes["edges"]:
        witnesses = _operation_edge_witnesses(indexes["edges"][ref], indexes)
        if not witnesses:
            raise ValueError(f"dependency edge has no recorded value-flow witness:{ref}")
        return tuple(
            _fact_unit(
                selected_ref=ref,
                request_refs={
                    str(witness[key])
                    for key in ("producer_request_ref", "consumer_request_ref")
                    if witness.get(key) in requests
                },
                action_ids=set(),
                evidence_refs={ref, str(witness["flow_id"])},
                card_ids=set(),
                indexes=indexes,
                order_suffix=str(witness["flow_id"]),
            )
            for witness in witnesses
        )
    if ref in indexes["bindings"]:
        witness = _binding_witness(indexes["bindings"][ref], indexes)
        if witness is None:
            raise ValueError(f"binding opportunity has no recorded witness:{ref}")
        return (_fact_unit(
            selected_ref=ref,
            request_refs={
                str(witness[key])
                for key in ("producer_request_ref", "consumer_request_ref")
                if witness.get(key) in requests
            },
            action_ids=set(),
            evidence_refs={ref, str(witness["flow_id"])},
            card_ids=set(),
            indexes=indexes,
            order_suffix=str(witness["flow_id"]),
        ),)
    if ref in indexes["negative_facts"]:
        row = indexes["negative_facts"][ref]
        projection = row["projection"]
        endpoints = {
            str(row["setup_request_ref"]),
            str(row["negative_request_ref"]),
            str(projection["before_request_ref"]),
            str(projection["after_request_ref"]),
        }
        return (_fact_unit(
            selected_ref=ref,
            request_refs=endpoints,
            action_ids={str(row["session_boundary_event_id"])},
            evidence_refs={ref},
            card_ids=set(),
            indexes=indexes,
            order_suffix=ref,
        ),)
    raise ValueError(f"detail selection references an unknown fact:{ref}")


def _business_episode_region(
    frozen: V2FrozenInput,
    *,
    episode: _BusinessOperationEpisode,
    selected_refs: tuple[str, ...],
    region_id: str,
    indexes: Mapping[str, Any],
    reference_order: Mapping[str, tuple[int, int, str]],
) -> DetailRegion:
    """Close one contiguous UI-operation episode plus direct recorded facts."""

    cards = indexes["cards"]
    requests = indexes["requests"]
    actions = indexes["actions"]
    payload = indexes["payload"]
    core_cards = [cards[ref] for ref in episode.core_card_ids]
    center_card = cards[episode.center_card_id]
    core_request_refs = {
        str(ref) for card in core_cards for ref in card["request_refs"]
    }
    business_refs, authentication_refs = _recorded_state_change_refs(frozen)
    center_state_change_request_refs = tuple(
        sorted(
            (
                str(ref)
                for ref in center_card["request_refs"]
                if _is_recorded_state_change(
                    requests[str(ref)],
                    business_refs=business_refs,
                    authentication_refs=authentication_refs,
                )
            ),
            key=lambda ref: (int(requests[ref]["global_order"]), ref),
        )
    )
    if not center_state_change_request_refs:
        raise ValueError("business-operation episode center lacks a state change")
    observation_slice, slice_request_refs = _center_observation_slice(
        frozen,
        episode=episode,
        core_request_refs=core_request_refs,
        center_state_change_request_refs=center_state_change_request_refs,
        indexes=indexes,
    )
    observer_operation_catalog = _observer_operation_catalog(
        frozen,
        center_state_change_request_refs=center_state_change_request_refs,
        observation_slice=observation_slice,
        indexes=indexes,
    )
    checkpoint_request_refs = set(
        map(str, observation_slice["pre_state_request_refs"])
    )
    first_business_order = min(
        (
            int(requests[ref]["global_order"])
            for ref in business_refs
            if ref in requests
        ),
        default=None,
    )
    include_authentication_refs = (
        first_business_order is not None
        and min(
            int(requests[ref]["global_order"])
            for ref in center_state_change_request_refs
        )
        == first_business_order
    )
    request_refs = set(map(str, center_card["request_refs"])) | slice_request_refs
    if include_authentication_refs:
        request_refs.update(authentication_refs & set(requests))
    action_ids = {episode.center_action_id}
    card_ids = {episode.center_card_id}
    evidence_refs: set[str] = set()
    for ref in selected_refs:
        for unit in _selected_detail_fact_units(ref, indexes):
            request_refs.update(unit.request_refs)
            action_ids.update(unit.action_ids)
            evidence_refs.update(unit.evidence_refs)
            card_ids.update(unit.card_ids)

    # Keep every cumulative transition whose recorded interval explicitly
    # contains this center, together with all competing writes.  Competition
    # provenance, rather than temporal proximity, still controls grounding.
    for ref in observation_slice["center_interval_transition_fact_refs"]:
        row = indexes["transitions"][ref]
        competition = row.get("write_competition") or {}
        witness = row.get("locator_witness")
        request_refs.update(
            {
                str(row["before_request_ref"]),
                str(row["after_request_ref"]),
            }
        )
        request_refs.update(
            str(item["request_ref"])
            for item in competition.get("assessments", ())
            if isinstance(item, Mapping)
            and item.get("request_ref") in requests
        )
        evidence_refs.add(ref)
        if witness:
            evidence_refs.add(str(witness["flow_id"]))
    for ref, row in indexes["negative_facts"].items():
        projection = row["projection"]
        required_requests = {
            str(row["setup_request_ref"]),
            str(row["negative_request_ref"]),
            str(projection["before_request_ref"]),
            str(projection["after_request_ref"]),
        }
        if str(row["negative_request_ref"]) not in set(
            center_state_change_request_refs
        ):
            continue
        request_refs.update(required_requests)
        action_ids.add(str(row["session_boundary_event_id"]))
        evidence_refs.add(ref)

    for ref, row in indexes["ui"].items():
        endpoints = {
            *map(str, row.get("preceding_request_refs", ())),
            *map(str, row.get("following_request_refs", ())),
        }
        endpoint_groups = {
            str(requests[endpoint]["request_group_id"])
            for endpoint in endpoints
            if endpoint in requests
        }
        endpoint_group_refs = {
            candidate_ref
            for candidate_ref, candidate in requests.items()
            if str(candidate["request_group_id"]) in endpoint_groups
        }
        endpoint_group_has_hidden_state_change = any(
            endpoint not in request_refs
            and endpoint in endpoint_group_refs
            and endpoint not in authentication_refs
            and _is_recorded_state_change(
                requests[endpoint],
                business_refs=business_refs,
                authentication_refs=authentication_refs,
            )
            for endpoint in endpoint_group_refs
        )
        if (
            row.get("event_id") != episode.center_action_id
            and endpoint_group_has_hidden_state_change
        ):
            continue
        if row.get("event_id") in action_ids or endpoints & request_refs:
            evidence_refs.add(ref)
            if not endpoint_group_has_hidden_state_change:
                request_refs.update(endpoints & set(requests))

    flow_ids = {ref for ref in evidence_refs if ref in indexes["flows"]}
    flow_ids.update(
        ref
        for ref, row in indexes["flows"].items()
        if {
            str(row["producer_request_ref"]),
            str(row["consumer_request_ref"]),
        } <= request_refs
    )
    binding_ids = {ref for ref in evidence_refs if ref in indexes["bindings"]}
    binding_ids.update(
        ref for ref, row in indexes["bindings"].items()
        if str(row.get("witness_flow_id")) in flow_ids
    )
    for ref in binding_ids:
        witness = _binding_witness(indexes["bindings"][ref], indexes)
        if witness is not None:
            flow_ids.add(str(witness["flow_id"]))
    for ref in flow_ids:
        flow = indexes["flows"][ref]
        request_refs.update(
            str(flow[key])
            for key in ("producer_request_ref", "consumer_request_ref")
            if flow.get(key) in requests
        )
    evidence_refs.update(flow_ids)
    evidence_refs.update(binding_ids)
    flow_pairs = {
        (str(indexes["flows"][ref]["producer_operation_id"]),
         str(indexes["flows"][ref]["consumer_operation_id"]))
        for ref in flow_ids
    }
    evidence_refs.update(
        ref for ref, row in indexes["edges"].items()
        if (str(row["producer_operation_id"]), str(row["consumer_operation_id"]))
        in flow_pairs
    )

    request_refs, action_ids = _complete_request_groups(
        request_refs=request_refs, action_ids=action_ids, indexes=indexes
    )
    for card_id, card in cards.items():
        if card["card_kind"] in {"action_episode", "unassigned_request"} and (
            set(map(str, card["request_refs"])) & request_refs
            or set(map(str, card["action_event_ids"])) & action_ids
        ):
            card_ids.add(card_id)
    evidence_refs.update(
        ref for ref, row in indexes["automatic_bindings"].items()
        if str(row.get("request_ref")) in request_refs
        and str(row.get("event_id")) in action_ids
    )
    for request_ref in request_refs:
        domain = payload["request_setup_domains"].get(request_ref, {})
        action_ids.update(map(str, domain.get("eligible_setup_action_ids", ())))
    center_transition_refs = set(
        observation_slice["center_interval_transition_fact_refs"]
    )
    for ref, row in indexes["transitions"].items():
        if ref not in center_transition_refs:
            continue
        witness = row.get("locator_witness")
        required_requests = {
            str(row["before_request_ref"]),
            str(row["after_request_ref"]),
            *((str(witness["request_ref"]),) if witness else ()),
        }
        if not required_requests <= request_refs:
            continue
        evidence_refs.add(ref)
        if witness:
            evidence_refs.add(str(witness["flow_id"]))
    for ref, row in indexes["negative_facts"].items():
        projection = row["projection"]
        required_requests = {
            str(row["setup_request_ref"]),
            str(row["negative_request_ref"]),
            str(projection["before_request_ref"]),
            str(projection["after_request_ref"]),
        }
        if required_requests <= request_refs:
            action_ids.add(str(row["session_boundary_event_id"]))
            evidence_refs.add(ref)
    visible_evidence = evidence_refs | request_refs | action_ids | card_ids
    request_order = {
        ref: (int(row["global_order"]), ref) for ref, row in requests.items()
    }
    action_order = {
        ref: (int(row["global_order"]), ref) for ref, row in actions.items()
    }
    visible_core_card_ids = tuple(
        card_id
        for card_id in episode.core_card_ids
        if (
            set(map(str, cards[card_id]["request_refs"])) & request_refs
            or set(map(str, cards[card_id]["action_event_ids"])) & action_ids
        )
    )
    if episode.center_card_id not in visible_core_card_ids:
        raise ValueError("business-operation slice omitted its center card")
    return DetailRegion(
        region_id=region_id,
        region_kind="business_operation_episode",
        primary_card_id=episode.center_card_id,
        center_action_id=episode.center_action_id,
        center_state_change_request_refs=center_state_change_request_refs,
        center_observation_slice=observation_slice,
        observer_operation_catalog=observer_operation_catalog,
        core_card_ids=visible_core_card_ids,
        selection_refs=tuple(sorted(set(selected_refs), key=lambda ref: reference_order[ref])),
        member_card_ids=tuple(sorted(card_ids)),
        visible_request_refs=tuple(sorted(request_refs, key=lambda ref: request_order[ref])),
        visible_action_ids=tuple(sorted(action_ids, key=lambda ref: action_order[ref])),
        visible_evidence_refs=tuple(sorted(visible_evidence)),
        split_order=1,
        split_count=1,
        boundary={
            "derivation_revision": DETAIL_DERIVATION_REVISION,
            "episode_center_kind": episode.center_kind,
            "episode_candidate_card_count": len(episode.core_card_ids),
            "episode_core_card_count": len(visible_core_card_ids),
            "episode_core_request_count": len(core_request_refs),
            "pre_state_checkpoint_request_count": len(checkpoint_request_refs),
            "post_state_observation_count": len(
                observation_slice["post_state_observations"]
            ),
            "post_state_without_comparable_pre_count": sum(
                row["comparable_pre_state_status"] == "none"
                for row in observation_slice["post_state_observations"]
            ),
            "post_state_with_multiple_comparable_pre_count": sum(
                row["comparable_pre_state_status"] == "multiple"
                for row in observation_slice["post_state_observations"]
            ),
            "visible_request_count": len(request_refs),
            "visible_action_count": len(action_ids),
            "direct_evidence_count": len(evidence_refs),
            "legacy_per_call_budget_enforced": "false",
        },
    )


def _compact_provider_shape(shape: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: shape[key]
        for key in ("body_kind", "shape_rows", "shape_total_count",
                    "shape_visible_count", "shape_omitted_count")
        if key in shape
    }


def _provider_observer_operation_catalog(
    operations: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for operation in operations:
        templates = tuple(operation.get("templates", ()))
        shapes = {
            str(template["response_body_shape_sha256"]): _compact_provider_shape(
                template["response_body_shape"]
            )
            for template in templates
        }
        actor_sessions = sorted({
            (str(template["actor_id"]), str(template["session_run_id"]))
            for template in templates
        })
        result.append({
            "operation_id": str(operation["operation_id"]),
            "method": str(operation["method"]),
            "canonical_path": str(operation["canonical_path"]),
            "readiness": str(operation["readiness"]),
            "observed_actor_sessions": [
                {"actor_id": actor, "session_run_id": session}
                for actor, session in actor_sessions
            ],
            "observed_request_template_count": len(templates),
            "response_shapes": [
                {"shape_sha256": shape_sha, **shapes[shape_sha]}
                for shape_sha in sorted(shapes)
            ],
        })
    return result


def _business_episode_payload(
    view: ProposalEvidenceView,
    region: DetailRegion,
    *,
    payload: Mapping[str, Any],
    indexes: Mapping[str, Any],
) -> dict[str, Any]:
    """Render a compact, role-neutral, globally ordered operation timeline."""

    if region.center_action_id is None or not region.core_card_ids:
        raise ValueError("business-operation episode lacks its center or core")
    if region.center_observation_slice is None:
        raise ValueError("business-operation episode lacks its observation slice")
    request_ids = set(region.visible_request_refs)
    action_ids = set(region.visible_action_ids)
    card_ids = set(region.member_card_ids)
    shapes: dict[str, dict[str, Any]] = {}
    compact_requests: list[dict[str, Any]] = []
    for ref in region.visible_request_refs:
        row = indexes["requests"][ref]
        compact = {
            key: value for key, value in row.items()
            if key not in {"full_row_sha256", "request_body_shape", "response_body_shape"}
        }
        for source_key, target_key in (
            ("request_body_shape", "request_shape_ref"),
            ("response_body_shape", "response_shape_ref"),
        ):
            shape = _compact_provider_shape(row.get(source_key) or {})
            shape_ref = f"shape-{canonical_sha256(shape)[:24]}"
            shapes.setdefault(shape_ref, shape)
            compact[target_key] = shape_ref
        compact_requests.append(compact)

    def card_entry(card_id: str) -> dict[str, Any]:
        card = indexes["cards"][card_id]
        refs = [str(ref) for ref in card["request_refs"] if ref in request_ids]
        orders = [int(indexes["requests"][ref]["global_order"]) for ref in refs]
        return {
            "card_id": card_id,
            "card_kind": card["card_kind"],
            "action_ids": [str(ref) for ref in card["action_event_ids"] if ref in action_ids],
            "request_group_ids": list(card["request_group_ids"]),
            "request_refs": refs,
            "actor_ids": list(card["actor_ids"]),
            "session_run_ids": list(card["session_run_ids"]),
            "request_order_min": min(orders, default=-1),
            "request_order_max": max(orders, default=-1),
        }

    core_entries = [card_entry(ref) for ref in region.core_card_ids]
    linked_entries = [
        card_entry(ref)
        for ref in sorted(card_ids - set(region.core_card_ids))
    ]
    all_entries = core_entries + linked_entries
    center = next(row for row in core_entries if region.center_action_id in row["action_ids"])
    center_key = (center["request_order_min"], center["card_id"])
    prior = [
        row for row in all_entries
        if (row["request_order_min"], row["card_id"]) < center_key
    ]
    following = [
        row for row in all_entries
        if (row["request_order_min"], row["card_id"]) > center_key
    ]
    prior.sort(key=lambda row: (row["request_order_min"], row["card_id"]))
    following.sort(key=lambda row: (row["request_order_min"], row["card_id"]))
    timeline_action_ids = {
        str(ref)
        for card_id in region.member_card_ids
        for ref in indexes["cards"][card_id]["action_event_ids"]
    }
    compact_actions = [
        {key: value for key, value in indexes["actions"][ref].items() if key != "full_row_sha256"}
        for ref in region.visible_action_ids if ref in timeline_action_ids
    ]
    compact_flows = [
        {"flow_id": ref, "from_request_ref": row["producer_request_ref"],
         "from_location": row["from_location"], "from_field": row["from_field"],
         "to_request_ref": row["consumer_request_ref"], "to_location": row["to_location"],
         "to_field": row["to_field"]}
        for ref in region.visible_evidence_refs if ref in indexes["flows"]
        for row in (indexes["flows"][ref],)
    ]
    compact_edges = [
        {"edge_id": ref, "from_operation_id": row["producer_operation_id"],
         "to_operation_id": row["consumer_operation_id"], "kind": row["kind"],
         "observed_flow_count": row["observed_flow_count"]}
        for ref in region.visible_evidence_refs if ref in indexes["edges"]
        for row in (indexes["edges"][ref],)
    ]
    compact_bindings = [
        {"opportunity_id": ref, "from_operation_id": row["producer_operation_id"],
         "from_location": row["from_location"], "from_field": row["from_field"],
         "to_operation_id": row["consumer_operation_id"], "to_location": row["to_location"],
         "to_field": row["to_field"], "witness_flow_id": row["witness_flow_id"]}
        for ref in region.visible_evidence_refs if ref in indexes["bindings"]
        for row in (indexes["bindings"][ref],)
    ]
    action_links = [
        {key: value for key, value in indexes["automatic_bindings"][ref].items()
         if key != "full_row_sha256"}
        for ref in region.visible_evidence_refs if ref in indexes["automatic_bindings"]
    ]
    return {
        "phase": "detail_proposal",
        "detail_view_kind": "bounded_cross_actor_business_operation_episode",
        "detail_region_id": region.region_id,
        "primary_card_id": region.primary_card_id,
        "center_action_id": region.center_action_id,
        "center_state_change_request_refs": list(
            region.center_state_change_request_refs
        ),
        "center_observation_slice": region.center_observation_slice,
        "observer_operation_catalog": _provider_observer_operation_catalog(
            region.observer_operation_catalog
        ),
        "selected_fact_refs": list(region.selection_refs),
        "visible_request_refs": list(region.visible_request_refs),
        "visible_action_ids": list(region.visible_action_ids),
        "visible_evidence_refs": list(region.visible_evidence_refs),
        "recorded_timeline": {
            "prior_recorded_facts": prior,
            "center_ui_action": center,
            "following_recorded_facts": following,
            "direct_linked_facts": {
                "ui_diff_refs": [
                    ref for ref in region.visible_evidence_refs
                    if ref in indexes["ui"]
                ],
                "value_flow_refs": [
                    ref for ref in region.visible_evidence_refs
                    if ref in indexes["flows"]
                ],
                "dependency_edge_refs": [
                    ref for ref in region.visible_evidence_refs
                    if ref in indexes["edges"]
                ],
                "binding_opportunity_refs": [
                    ref for ref in region.visible_evidence_refs
                    if ref in indexes["bindings"]
                ],
                "negative_request_fact_refs": [
                    ref for ref in region.visible_evidence_refs
                    if ref in indexes["negative_facts"]
                ],
            },
        },
        "ui_actions": compact_actions,
        "api_requests": compact_requests,
        "shape_catalog": [{"shape_ref": ref, **shapes[ref]} for ref in sorted(shapes)],
        "recorded_action_request_links": action_links,
        "ui_diff": {"rows": [indexes["ui"][ref] for ref in region.visible_evidence_refs if ref in indexes["ui"]]},
        "observed_value_flows": compact_flows,
        "dependency_edges": compact_edges,
        "binding_opportunities": compact_bindings,
        "setup_action_catalog": [ref for ref in payload["setup_action_catalog"] if ref in action_ids],
        "request_setup_domains": {ref: payload["request_setup_domains"][ref] for ref in region.visible_request_refs},
        "setup_selection_clues": {
            ref: payload["setup_selection_clues"][ref]
            for ref in region.visible_request_refs
            if ref in payload["setup_selection_clues"]
        },
        "transition_facts": [
            indexes["transitions"][ref]
            for ref in region.visible_evidence_refs
            if ref in indexes["transitions"]
        ],
        "negative_request_facts": [
            indexes["negative_facts"][ref]
            for ref in region.visible_evidence_refs
            if ref in indexes["negative_facts"]
        ],
        "relation_language": payload["relation_language"],
        "boundary": region.boundary,
    }


def _detail_payload(
    view: ProposalEvidenceView,
    region: DetailRegion,
    *,
    view_payload: Mapping[str, Any] | None = None,
    indexes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = view_payload or view.model_dump(mode="json")
    indexes = indexes or _detail_indexes(view)
    if region.region_kind == "business_operation_episode":
        return _business_episode_payload(
            view,
            region,
            payload=payload,
            indexes=indexes,
        )
    action_ids = set(region.visible_action_ids)
    card_ids = set(region.member_card_ids)
    request_ids = set(region.visible_request_refs)
    evidence_ids = set(region.visible_evidence_refs)
    ui_projection = (
        payload.get("evidence_channel_summaries", {})
        .get("ui_diff", {})
        .get("semantic_projection", {})
    )

    def project_card(row: Mapping[str, Any]) -> dict[str, Any]:
        projected = dict(row)
        projected["component_card_ids"] = [
            ref for ref in row["component_card_ids"] if ref in card_ids
        ]
        projected["request_refs"] = [
            ref for ref in row["request_refs"] if ref in request_ids
        ]
        projected["action_event_ids"] = [
            ref for ref in row["action_event_ids"] if ref in action_ids
        ]
        projected["anchor_request_refs"] = [
            ref for ref in row["anchor_request_refs"] if ref in request_ids
        ]
        projected["setup_domain_refs"] = [
            ref for ref in row["setup_domain_refs"] if ref in request_ids
        ]
        for field in (
            "ui_diff_record_ids",
            "value_flow_ids",
            "dependency_edge_ids",
            "binding_opportunity_ids",
            "negative_request_fact_ids",
        ):
            projected[field] = [
                ref for ref in row.get(field, ()) if ref in evidence_ids
            ]
        if projected.get("root_request_ref") not in request_ids:
            projected["root_request_ref"] = None
        return projected

    return {
        "phase": "detail_proposal",
        "detail_region_id": region.region_id,
        "primary_card_id": region.primary_card_id,
        "selection_refs": list(region.selection_refs),
        "selected_card_summaries": [
            {
                "card_id": row["card_id"],
                "card_kind": row["card_kind"],
                "component_card_ids": [
                    ref for ref in row["component_card_ids"] if ref in card_ids
                ],
                "request_count": len(
                    set(map(str, row["request_refs"]))
                    & set(region.visible_request_refs)
                ),
            }
            for row in payload["evidence_cards"]
            if str(row["card_id"]) in set(region.selection_refs)
        ],
        "visible_request_refs": list(region.visible_request_refs),
        "visible_action_ids": list(region.visible_action_ids),
        "visible_evidence_refs": list(region.visible_evidence_refs),
        "api_requests": [
            indexes["requests"][ref] for ref in region.visible_request_refs
        ],
        "ui_actions": [
            row for row in payload["ui_actions"] if str(row["event_id"]) in action_ids
        ],
        "evidence_cards": [
            project_card(row)
            for row in payload["evidence_cards"]
            if str(row["card_id"]) in card_ids
        ],
        "ui_diff": {
            **{key: value for key, value in ui_projection.items() if key != "rows"},
            "rows": [
                indexes["ui"][ref]
                for ref in region.visible_evidence_refs
                if ref in indexes["ui"]
            ],
        },
        "observed_value_flows": [
            indexes["flows"][ref]
            for ref in region.visible_evidence_refs
            if ref in indexes["flows"]
        ],
        "dependency_edges": [
            indexes["edges"][ref]
            for ref in region.visible_evidence_refs
            if ref in indexes["edges"]
        ],
        "binding_opportunities": [
            indexes["bindings"][ref]
            for ref in region.visible_evidence_refs
            if ref in indexes["bindings"]
        ],
        "setup_action_catalog": [
            action_id for action_id in payload["setup_action_catalog"]
            if action_id in action_ids
        ],
        "request_setup_domains": {
            ref: payload["request_setup_domains"][ref] for ref in region.visible_request_refs
        },
        "setup_selection_clues": {
            ref: payload["setup_selection_clues"][ref]
            for ref in region.visible_request_refs
            if ref in payload["setup_selection_clues"]
        },
        "transition_facts": [
            indexes["transitions"][ref]
            for ref in region.visible_evidence_refs
            if ref in indexes["transitions"]
        ],
        "negative_request_facts": [
            indexes["negative_facts"][ref]
            for ref in region.visible_evidence_refs
            if ref in indexes["negative_facts"]
        ],
        "relation_language": payload["relation_language"],
        "boundary": region.boundary,
    }


def derive_detail_regions(
    frozen: V2FrozenInput,
    *,
    normalized_decisions: tuple[dict[str, Any], ...],
    first_call_order: int,
    detail_max_requests: int,
    detail_max_rendered_utf8_bytes: int,
    call_prototype: ProposalCallSpec,
) -> tuple[tuple[DetailRegion, ProposalCallSpec], ...]:
    view = frozen.lineage.view
    view_payload = view.model_dump(mode="json")
    indexes = _detail_indexes(view)
    request_order = {
        str(row["request_ref"]): (int(row["global_order"]), str(row["request_ref"]))
        for row in view_payload["api_requests"]
    }
    reference_order = _reference_order(view)
    operation_episodes = _business_operation_episodes(frozen, indexes)
    results: list[tuple[DetailRegion, ProposalCallSpec]] = []

    def make_region(
        *,
        primary_card_id: str,
        root: _DetailFactUnit,
        units: tuple[_DetailFactUnit, ...],
        all_direct_requests: set[str],
        original_selection_count: int,
        region_id: str,
        split_order: int,
        split_count: int,
    ) -> DetailRegion:
        chunk_requests = set(root.request_refs)
        chunk_actions = set(root.action_ids)
        chunk_actions.update(
            str(indexes["requests"][ref]["action_event_id"])
            for ref in chunk_requests
            if ref in indexes["requests"]
            and indexes["requests"][ref].get("action_event_id") in indexes["actions"]
        )
        chunk_evidence: set[str] = set()
        chunk_cards = set(root.card_ids)
        selection_refs: set[str] = set()
        for unit in units:
            selection_refs.add(unit.selected_ref)
            chunk_requests.update(unit.request_refs)
            chunk_actions.update(unit.action_ids)
            chunk_evidence.update(unit.evidence_refs)
            chunk_cards.update(unit.card_ids)
        for request_ref in chunk_requests:
            domain = view_payload["request_setup_domains"].get(request_ref, {})
            chunk_actions.update(map(str, domain.get("eligible_setup_action_ids", ())))
        for ref, row in indexes["transitions"].items():
            witness = row.get("locator_witness")
            required_requests = {
                str(row["before_request_ref"]),
                str(row["after_request_ref"]),
                *((str(witness["request_ref"]),) if witness else ()),
            }
            if not required_requests <= chunk_requests:
                continue
            chunk_evidence.add(ref)
            if witness:
                chunk_evidence.add(str(witness["flow_id"]))
        for ref, row in indexes["negative_facts"].items():
            projection = row["projection"]
            required_requests = {
                str(row["setup_request_ref"]),
                str(row["negative_request_ref"]),
                str(projection["before_request_ref"]),
                str(projection["after_request_ref"]),
            }
            if required_requests <= chunk_requests:
                chunk_actions.add(str(row["session_boundary_event_id"]))
                chunk_evidence.add(ref)
        ordered_selections = tuple(sorted(
            selection_refs, key=lambda ref: reference_order[ref]
        ))
        return DetailRegion(
            region_id=region_id,
            region_kind="selected_fact_region",
            primary_card_id=primary_card_id,
            center_action_id=None,
            center_state_change_request_refs=(),
            core_card_ids=(),
            selection_refs=ordered_selections,
            member_card_ids=tuple(sorted(chunk_cards)),
            visible_request_refs=tuple(
                sorted(chunk_requests, key=lambda ref: request_order[ref])
            ),
            visible_action_ids=tuple(sorted(chunk_actions)),
            visible_evidence_refs=tuple(
                sorted(chunk_evidence | chunk_cards | chunk_requests | chunk_actions)
            ),
            split_order=split_order,
            split_count=split_count,
            boundary={
                "max_requests": detail_max_requests,
                "visible_request_count": len(chunk_requests),
                "total_request_count": len(all_direct_requests),
                "omitted_request_count": len(all_direct_requests - chunk_requests),
                "selection_ref_count": len(ordered_selections),
                "original_selection_ref_count": original_selection_count,
                "derivation_revision": DETAIL_DERIVATION_REVISION,
            },
        )

    def rendered_size(region: DetailRegion) -> int:
        return len(
            _render_detail_input(
                frozen,
                region,
                view_payload=view_payload,
                indexes=indexes,
            ).rendered_text.encode("utf-8")
        )

    for decision in normalized_decisions:
        primary_card_id = str(decision["primary_card_id"])
        if primary_card_id in operation_episodes:
            region = _business_episode_region(
                frozen,
                episode=operation_episodes[primary_card_id],
                selected_refs=(),
                region_id=f"detail-{len(results) + 1:04d}",
                indexes=indexes,
                reference_order=reference_order,
            )
            results.append((region, ProposalCallSpec(
                call_id=region.region_id,
                call_order=first_call_order + len(results),
                model=call_prototype.model,
                reasoning_effort=call_prototype.reasoning_effort,
                temperature=call_prototype.temperature,
                retry_limit=call_prototype.retry_limit,
                endpoint_shape=call_prototype.endpoint_shape,
                endpoint_host=call_prototype.endpoint_host,
                stratum="business",
                proposal_round="detail_proposal",
                evidence_card_ids=(primary_card_id,),
                detail_region_id=region.region_id,
            )))
            continue
        if decision["decision"] == "skip":
            continue
        root = _root_detail_fact(primary_card_id, indexes)
        unique_selections = {
            tuple(sorted(map(str, refs), key=lambda ref: reference_order[ref]))
            for refs in decision["detail_selections"]
        }
        for selection_refs in sorted(
            unique_selections,
            key=lambda refs: tuple(reference_order[ref] for ref in refs),
        ):
            units: list[_DetailFactUnit] = []
            for ref in selection_refs:
                units.extend(_selected_detail_fact_units(ref, indexes))
            units.sort(key=lambda unit: unit.order_key)
            if not units:
                raise ValueError("expanded detail selection contains no fact units")
            all_direct_requests = set(root.request_refs)
            for unit in units:
                all_direct_requests.update(unit.request_refs)

            region_parts: list[tuple[_DetailFactUnit, ...]] = []
            current: list[_DetailFactUnit] = []
            current_requests = set(root.request_refs)
            for unit in units:
                indivisible_requests = set(root.request_refs) | set(unit.request_refs)
                if len(indivisible_requests) > detail_max_requests:
                    raise ValueError(
                        f"detail_region_too_large:{primary_card_id}:{unit.selected_ref}"
                    )
                if len(current_requests | set(unit.request_refs)) <= detail_max_requests:
                    current.append(unit)
                    current_requests.update(unit.request_refs)
                    continue
                if current:
                    region_parts.append(tuple(current))
                current = [unit]
                current_requests = indivisible_requests
            if current:
                region_parts.append(tuple(current))

            byte_bounded_parts: list[tuple[_DetailFactUnit, ...]] = []
            pending = list(region_parts)
            while pending:
                part = pending.pop(0)
                provisional = make_region(
                    primary_card_id=primary_card_id,
                    root=root,
                    units=part,
                    all_direct_requests=all_direct_requests,
                    original_selection_count=len(selection_refs),
                    region_id="detail-size-probe",
                    split_order=1,
                    split_count=max(1, len(units)),
                )
                if rendered_size(provisional) <= detail_max_rendered_utf8_bytes:
                    byte_bounded_parts.append(part)
                    continue
                if len(part) == 1:
                    raise ValueError(
                        f"detail_region_too_large:{primary_card_id}:{part[0].selected_ref}"
                    )
                middle = len(part) // 2
                pending[0:0] = [part[:middle], part[middle:]]
            region_parts = byte_bounded_parts

            regions_for_selection = tuple(
                make_region(
                    primary_card_id=primary_card_id,
                    root=root,
                    units=part,
                    all_direct_requests=all_direct_requests,
                    original_selection_count=len(selection_refs),
                    region_id=f"detail-{len(results) + index:04d}",
                    split_order=index,
                    split_count=len(region_parts),
                )
                for index, part in enumerate(region_parts, start=1)
            )
            covered_selection_refs = {
                ref for region in regions_for_selection for ref in region.selection_refs
            }
            if covered_selection_refs != set(selection_refs):
                raise ValueError("detail region split omitted a selected fact")
            required_actions = set(root.action_ids)
            required_evidence: set[str] = set()
            for unit in units:
                required_actions.update(unit.action_ids)
                required_evidence.update(unit.evidence_refs)
            visible_requests = {
                ref for region in regions_for_selection for ref in region.visible_request_refs
            }
            visible_actions = {
                ref for region in regions_for_selection for ref in region.visible_action_ids
            }
            visible_evidence = {
                ref for region in regions_for_selection for ref in region.visible_evidence_refs
            }
            if all_direct_requests != visible_requests:
                raise ValueError("detail region split omitted or added a direct request")
            if not required_actions <= visible_actions:
                raise ValueError("detail region split omitted a selected action")
            if not required_evidence <= visible_evidence:
                raise ValueError("detail region split omitted selected direct evidence")
            if any(
                len(region.visible_request_refs) > detail_max_requests
                or rendered_size(region) > detail_max_rendered_utf8_bytes
                for region in regions_for_selection
            ):
                raise ValueError("detail region final rendering exceeds a frozen bound")
            for region in regions_for_selection:
                call_order = first_call_order + len(results)
                results.append((region, ProposalCallSpec(
                    call_id=region.region_id,
                    call_order=call_order,
                    model=call_prototype.model,
                    reasoning_effort=call_prototype.reasoning_effort,
                    temperature=call_prototype.temperature,
                    retry_limit=call_prototype.retry_limit,
                    endpoint_shape=call_prototype.endpoint_shape,
                    endpoint_host=call_prototype.endpoint_host,
                    stratum="business",
                    proposal_round="detail_proposal",
                    evidence_card_ids=(primary_card_id,),
                    detail_region_id=region.region_id,
                )))
    return tuple(results)


def _render_detail_input(
    frozen: V2FrozenInput,
    region: DetailRegion,
    *,
    view_payload: Mapping[str, Any] | None = None,
    indexes: Mapping[str, Any] | None = None,
) -> RenderedCandidateInput:
    return _render_payload_input(
        frozen,
        input_id=f"{frozen.lineage.rendered_input.input_id}-{region.region_id}",
        payload=_detail_payload(
            frozen.lineage.view,
            region,
            view_payload=view_payload,
            indexes=indexes,
        ),
        template=canonical_v2_template_text(),
        template_sha256=canonical_v2_template_sha256(),
        placeholder="{{PROPOSAL_EVIDENCE_VIEW_JSON}}",
    )


def _state_change_center_regions(
    frozen: V2FrozenInput,
) -> tuple[DetailRegion, ...]:
    """Rebuild every write-center region without using provider selections."""

    indexes = _detail_indexes(frozen.lineage.view)
    episodes = _business_operation_episodes(frozen, indexes)
    reference_order = _reference_order(frozen.lineage.view)
    centers = sorted(
        (
            episode
            for episode in episodes.values()
            if episode.center_kind == "state_change"
        ),
        key=lambda episode: _recording_order_key(
            indexes["cards"][episode.center_card_id], indexes["requests"]
        ),
    )
    return tuple(
        _business_episode_region(
            frozen,
            episode=episode,
            selected_refs=(),
            region_id=f"center-completion-{index:04d}",
            indexes=indexes,
            reference_order=reference_order,
        )
        for index, episode in enumerate(centers, start=1)
    )


def _query_relation_opportunity_regions(
    frozen: V2FrozenInput,
) -> tuple[DetailRegion, ...]:
    """Build bounded regions for unique, observed query refinements.

    Query-only workflows have no business producer, so they cannot be write
    centers.  This projection is deliberately narrower than "all GETs": it
    requires two successful, same-actor/session/operation observations with a
    strict selector refinement and one shared identity-bearing response
    collection.  The provider still has to ground and propose P17.
    """
    view = frozen.lineage.view
    indexes = _detail_indexes(view)
    execution_kinds = _request_execution_kinds(frozen)
    requests = indexes["requests"]
    cards = indexes["cards"]
    card_for_request = {
        str(ref): str(card["card_id"])
        for card in cards.values()
        for ref in card.get("request_refs", ())
        if str(ref) in requests
    }
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for row in requests.values():
        if execution_kinds.get(str(row["request_ref"])) != "read":
            continue
        status = row.get("response_status")
        if not isinstance(status, int) or not 200 <= status < 300:
            continue
        query = row.get("query") or {}
        if not isinstance(query, Mapping):
            continue
        groups.setdefault((
            str(row.get("actor_id")), str(row.get("session_run_id")),
            str(row.get("operation_id")), str(row.get("canonical_path")),
        ), []).append(row)

    regions: list[DetailRegion] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for rows in groups.values():
        rows = sorted(rows, key=lambda row: (int(row["global_order"]), str(row["request_ref"])))
        for source in rows:
            source_query = source.get("query") or {}
            source_arrays = response_collection_paths_with_identity(
                source.get("response_body_shape") or {}
            )
            for followup in rows:
                if int(followup["global_order"]) <= int(source["global_order"]):
                    continue
                follow_query = followup.get("query") or {}
                if not _query_is_filter_refinement(source_query, follow_query):
                    continue
                shared_arrays = source_arrays & response_collection_paths_with_identity(
                    followup.get("response_body_shape") or {}
                )
                # Nested arrays are members of the enclosing collection, not
                # competing query result roots.  Retain the shortest observed
                # identity-bearing collection path; multiple roots remain
                # ambiguous and do not schedule completion.
                shared_arrays = {
                    path for path in shared_arrays
                    if not any(
                        path != other
                        and (path.startswith(other + ".") or path.startswith(other + "[*]."))
                        for other in shared_arrays
                    )
                }
                if len(shared_arrays) != 1:
                    continue
                source_ref = str(source["request_ref"])
                follow_ref = str(followup["request_ref"])
                source_order = int(source["global_order"])
                follow_order = int(followup["global_order"])
                if any(
                    source_order < int(row["global_order"]) < follow_order
                    and execution_kinds.get(str(row["request_ref"])) == "write"
                    for row in requests.values()
                ):
                    continue
                source_card = card_for_request.get(source_ref)
                follow_card = card_for_request.get(follow_ref)
                if source_card is None or follow_card is None or source_card == follow_card:
                    continue
                pair_key = (source_ref, follow_ref, next(iter(shared_arrays)))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                selected_cards = (source_card, follow_card)
                request_refs: set[str] = set()
                action_ids: set[str] = set()
                for card_id in selected_cards:
                    card = cards[card_id]
                    request_refs.update(map(str, card.get("request_refs", ())))
                    action_ids.update(map(str, card.get("action_event_ids", ())))
                request_refs, action_ids = _complete_request_groups(
                    request_refs=request_refs, action_ids=action_ids, indexes=indexes
                )
                visible = request_refs | action_ids | set(selected_cards)
                order = {ref: (int(row["global_order"]), ref) for ref, row in requests.items()}
                regions.append(DetailRegion(
                    region_id=f"query-completion-{len(regions) + 1:04d}",
                    region_kind="selected_fact_region",
                    primary_card_id=follow_card,
                    selection_refs=selected_cards,
                    member_card_ids=selected_cards,
                    visible_request_refs=tuple(sorted(request_refs, key=lambda ref: order[ref])),
                    visible_action_ids=tuple(sorted(action_ids)),
                    visible_evidence_refs=tuple(sorted(visible)),
                    split_order=1,
                    split_count=1,
                    boundary={
                        "derivation_revision": DETAIL_DERIVATION_REVISION,
                        "query_relation_kind": "strict_selector_refinement",
                        "source_request_ref": source_ref,
                        "followup_request_ref": follow_ref,
                    },
                ))
    return tuple(regions)


def _opportunity_completion_regions(
    frozen: V2FrozenInput,
) -> tuple[DetailRegion, ...]:
    return (*_state_change_center_regions(frozen), *_query_relation_opportunity_regions(frozen))


def _centered_candidate_count(
    payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    region: DetailRegion,
) -> int:
    center_refs = set(region.center_state_change_request_refs)
    return sum(
        isinstance(payload.get("producer"), Mapping)
        and payload["producer"].get("request_ref") in center_refs
        for payload in payloads
    )


def _completion_candidate_count(
    payloads: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    region: DetailRegion,
) -> int:
    if region.boundary.get("query_relation_kind"):
        source_ref = region.boundary.get("source_request_ref")
        followup_ref = region.boundary.get("followup_request_ref")
        return sum(
            isinstance(payload.get("producer"), Mapping)
            and isinstance(payload.get("consumer"), Mapping)
            and payload["producer"].get("request_ref") == source_ref
            and payload["consumer"].get("request_ref") == followup_ref
            for payload in payloads
        )
    return _centered_candidate_count(payloads, region)


def _provider_token_usage(lineage: V2ProposalRunLineage | None) -> dict[str, int]:
    """Aggregate provider-reported token fields without estimating missing usage."""

    if lineage is None:
        return {}
    totals: dict[str, int] = {}
    for call_id in lineage.union_provenance.call_ids:
        raw = _read_json(
            lineage.run_root / "calls" / call_id / "provider_response_envelope.json"
        )
        usage = raw.get("raw_envelope", {}).get("usage", {})
        if not isinstance(usage, Mapping):
            continue
        for name, value in usage.items():
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                totals[str(name)] = totals.get(str(name), 0) + value
    return dict(sorted(totals.items()))


def _render_center_completion_input(
    frozen: V2FrozenInput,
    region: DetailRegion,
) -> RenderedCandidateInput:
    payload = _detail_payload(frozen.lineage.view, region)
    payload["phase"] = "center_completion"
    payload["center_completion_pass"] = {
        "trigger": "zero_admitted_centered_relations_after_complete_regular_rounds",
        "opportunity_kind": (
            "query_relation"
            if region.boundary.get("query_relation_kind")
            else "state_change"
        ),
        "center_action_id": region.center_action_id,
        "center_state_change_request_refs": list(
            region.center_state_change_request_refs
        ),
        "logical_call_limit": 1,
        "legal_relation_language": copy.deepcopy(payload["relation_language"]),
    }
    if region.boundary.get("query_relation_kind"):
        payload["center_completion_pass"]["query_pair"] = {
            "source_request_ref": region.boundary["source_request_ref"],
            "followup_request_ref": region.boundary["followup_request_ref"],
        }
    return _render_payload_input(
        frozen,
        input_id=f"{frozen.lineage.rendered_input.input_id}-{region.region_id}",
        payload=payload,
        template=canonical_v2_template_text(),
        template_sha256=canonical_v2_template_sha256(),
        placeholder="{{PROPOSAL_EVIDENCE_VIEW_JSON}}",
    )


def _completion_regions_for_plan(
    frozen: V2FrozenInput,
    plan: ProposalRunPlan,
) -> tuple[tuple[DetailRegion, ProposalCallSpec], ...]:
    available = {
        region.region_id: region for region in _opportunity_completion_regions(frozen)
    }
    derived: list[tuple[DetailRegion, ProposalCallSpec]] = []
    for spec in plan.calls:
        if spec.proposal_round != "center_completion":
            raise ValueError("completion plan contains a non-completion call")
        region = available.get(str(spec.detail_region_id))
        if region is None or spec.evidence_card_ids != (region.primary_card_id,):
            raise ValueError("completion call does not identify a frozen write center")
        derived.append((region, spec))
    return tuple(derived)


def _proposal_call_input(
    frozen: V2FrozenInput,
    spec: ProposalCallSpec,
) -> _ProposalCallInput:
    """Project one deterministic global-scan call from the frozen view."""

    lineage = frozen.lineage
    if spec.proposal_round == "global_scan":
        payload = _scan_batch_payload(
            lineage.view,
            spec.evidence_card_ids,
            batch_id=spec.call_id,
        )
        return _ProposalCallInput(
            view=payload,
            rendered_input=_render_payload_input(
                frozen,
                input_id=f"{lineage.rendered_input.input_id}-{spec.call_id}",
                payload=payload,
                template=canonical_scan_template_text(),
                template_sha256=canonical_scan_template_sha256(),
                placeholder=SCAN_EVIDENCE_PLACEHOLDER,
            ),
        )
    if spec.proposal_round == "detail_proposal":
        raise ValueError("detail proposal input requires its derived detail region")
    raise ValueError("proposal call is not a current global-scan input")


def largest_proposal_call_prompt(
    frozen: V2FrozenInput,
    calls: tuple[ProposalCallSpec, ...],
) -> str:
    """Return the largest actual per-call prompt for one consolidated preflight."""

    return max(
        (_proposal_call_input(frozen, spec).rendered_input.rendered_text for spec in calls),
        key=len,
    )


def build_proposal_run_plan(
    frozen: V2FrozenInput,
    *,
    plan_id: str,
    frozen_at: str,
    calls: tuple[ProposalCallSpec, ...],
    actual_model_policy: Literal["exact", "consistent"],
) -> ProposalRunPlan:
    lineage = frozen.lineage
    return ProposalRunPlan(
        plan_id=plan_id,
        frozen_at=frozen_at,
        input_freeze_manifest_sha256=frozen.manifest_raw_sha256,
        template_sha256=canonical_v2_template_sha256(),
        package_sha256=lineage.package.canonical_sha256(),
        view_sha256=lineage.view.canonical_sha256(),
        rendered_input_sha256=lineage.rendered_input.canonical_sha256(),
        rendered_text_sha256=lineage.rendered_input.rendered_sha256,
        calls=calls,
        actual_model_policy=actual_model_policy,
    )


def _prepare_dynamic_call_artifacts(
    *,
    spec: ProposalCallSpec,
    rendered: RenderedCandidateInput,
    call_root: Path,
    response_delivery_kind: Literal["provider", "sealed_response_replay"],
) -> None:
    call_root.mkdir(parents=True)
    _atomic_write(call_root / "rendered_candidate_input.json", rendered.canonical_bytes())
    request_config = _request_config_payload(
        spec=spec,
        rendered=rendered,
        response_delivery_kind=response_delivery_kind,
    )
    request_path = call_root / "request_config.json"
    _atomic_json(request_path, request_config)


def _persist_dynamic_response(
    *,
    response: RenderedProposalResponse,
    call_root: Path,
    filename: str = "provider_response_envelope.json",
) -> None:
    raw_payload = {
        "schema_version": "uisemtest-v2-raw-response-v1",
        "content": response.content,
        "raw_envelope": response.raw_envelope,
        "model": response.model,
        "endpoint_shape": response.endpoint_shape,
        "endpoint_host": response.endpoint_host,
        "temperature": response.temperature,
        "retry_count": response.retry_count,
        "response_received_at": response.response_received_at,
    }
    if response.reasoning_effort is not None:
        raw_payload["reasoning_effort"] = response.reasoning_effort
    _reject_secret_material(raw_payload)
    raw_path = call_root / filename
    _atomic_json(raw_path, raw_payload)


def _transport_dynamic_response(
    *,
    spec: ProposalCallSpec,
    rendered: RenderedCandidateInput,
    provider_factory: ProviderFactory,
    call_root: Path,
) -> RenderedProposalResponse:
    provider = provider_factory(spec)
    response = provider.propose_rendered(rendered_prompt=rendered.rendered_text)
    try:
        json.loads(response.content)
    except ValueError as exc:
        # A syntactically broken JSON body is a sampling defect of the provider,
        # not a deterministic input error: keep the rejected envelope for audit
        # and surface it as a transport failure so the frozen per-call retry
        # budget can re-sample it. No content repair is attempted.
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        _persist_dynamic_response(
            response=response,
            call_root=call_root,
            filename=f"provider_response_envelope.malformed-{stamp}.json",
        )
        raise ValueError(
            "provider content is not strict JSON; envelope kept and call marked for retry"
        ) from exc
    try:
        _parse_stage_response(spec, response.content)
    except ValueError as exc:
        # pydantic's ValidationError is a ValueError.  A well-formed JSON body
        # that violates the frozen response schema (missing or extra fields, a
        # stale scientific_input_version literal) is the same class of sampling
        # defect as broken JSON: keep the rejected envelope for audit and let
        # the frozen per-call retry budget re-sample the call.  No content
        # repair or salvage is attempted, and the budget stays bounded.
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        _persist_dynamic_response(
            response=response,
            call_root=call_root,
            filename=f"provider_response_envelope.schema_rejected-{stamp}.json",
        )
        raise ValueError(
            "provider content violates the frozen response schema; envelope kept "
            f"and call marked for retry: {_compact_error_text(exc)}"
        ) from exc
    _persist_dynamic_response(response=response, call_root=call_root)
    return response


def _parse_stage_response(spec: ProposalCallSpec, content: str) -> Any:
    """Parse one provider body with the strict schema of its proposal round."""

    if spec.proposal_round == "global_scan":
        return _parse_scan_response(content)
    return _parse_response(content)


def _compact_error_text(exc: BaseException, *, limit: int = 600) -> str:
    lines = (line.strip() for line in str(exc).splitlines())
    text = " | ".join(
        line for line in lines
        if line and not line.startswith("For further information")
    )
    return f"{type(exc).__name__}: {text[:limit]}"


def _process_dynamic_call_artifacts(
    *,
    frozen: V2FrozenInput,
    plan: ProposalRunPlan,
    spec: ProposalCallSpec,
    rendered: RenderedCandidateInput,
    call_root: Path,
    response_delivery_kind: Literal["provider", "sealed_response_replay"],
    region: DetailRegion | None,
    response: RenderedProposalResponse,
    reused_response: bool,
) -> tuple[
    datetime,
    ProposalCallProvenance,
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    tuple[dict[str, Any], ...],
]:
    _validate_response_metadata(
        response,
        spec,
        plan,
        allow_historical_timestamp=(
            response_delivery_kind == "sealed_response_replay" or reused_response
        ),
    )
    received_at = _timestamp(response.response_received_at)
    request_path = call_root / "request_config.json"
    raw_path = call_root / "provider_response_envelope.json"

    validation_path = call_root / "candidate_validation_report.json"
    payloads: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    normalized_scan: tuple[dict[str, Any], ...] = ()
    if spec.proposal_round == "global_scan":
        parsed_scan = _parse_scan_response(response.content)
        scan_payload = _scan_batch_payload(
            frozen.lineage.view,
            spec.evidence_card_ids,
            batch_id=spec.call_id,
        )
        normalized_scan = _normalize_scan_decisions(
            parsed_scan,
            batch_payload=scan_payload,
            view=frozen.lineage.view,
        )
        report = {
            "schema_version": "uisemtest-v2-candidate-validation-report-v1",
            "status": "complete",
            "scientific_input_version": SCIENTIFIC_INPUT_VERSION,
            "raw_proposed_count": 0,
            "valid_admitted_count": 0,
            "invalid_rejected_count": 0,
            "deduplicated_count": 0,
            "candidates": [],
            "scan_decisions": list(normalized_scan),
        }
        canonical_response_sha256 = canonical_sha256(
            parsed_scan.model_dump(mode="json")
        )
    else:
        if region is None or spec.proposal_round not in {
            "detail_proposal", "center_completion"
        }:
            raise ValueError("dynamic candidate call lacks a detail region")
        parsed = _parse_response(response.content)
        execution_kinds, execution_evidence = _request_execution_attributes(frozen)
        batch = _validate_candidate_batch(
            parsed,
            frozen.lineage.view,
            detail_region_id=region.region_id,
            visible_request_refs=set(region.visible_request_refs),
            visible_action_ids=set(region.visible_action_ids),
            visible_evidence_refs=set(region.visible_evidence_refs),
            request_execution_kinds=execution_kinds,
            request_execution_evidence=execution_evidence,
            observer_operation_catalog=region.observer_operation_catalog,
            required_effect_source_request_refs=(
                set(region.center_state_change_request_refs)
                if spec.proposal_round == "center_completion"
                else None
            ),
            required_query_pair=(
                (
                    str(region.boundary["source_request_ref"]),
                    str(region.boundary["followup_request_ref"]),
                )
                if region.boundary.get("query_relation_kind")
                else None
            ),
        )
        report = batch.report
        payloads.extend(batch.payloads)
        plans.extend(batch.constructed_execution_plans)
        canonical_response_sha256 = canonical_sha256(parsed.model_dump(mode="json"))
    _atomic_json(validation_path, report)
    candidate_set = _candidate_set(
        payloads,
        frozen=frozen,
        seed_label=canonical_response_sha256,
        rendered_ref="rendered_candidate_input.json",
        actual_rendered_input=rendered,
    )
    candidate_path = call_root / "candidate_set.json"
    _atomic_write(candidate_path, candidate_set.canonical_bytes())
    load_v2_candidate_lineage(
        candidate_set_path=candidate_path,
        package_path=frozen.artifact_paths["package"],
        view_path=frozen.artifact_paths["view"],
        rendered_input_path=call_root / "rendered_candidate_input.json",
    )
    provenance = ProposalCallProvenance(
        call_id=spec.call_id,
        call_order=spec.call_order,
        request_config_sha256=_sha256_file(request_path),
        raw_response_file_sha256=_sha256_file(raw_path),
        raw_response_content_sha256=hashlib.sha256(response.content.encode("utf-8")).hexdigest(),
        canonical_response_sha256=canonical_response_sha256,
        candidate_validation_file_sha256=_sha256_file(validation_path),
        candidate_set_sha256=candidate_set.canonical_sha256(),
        candidate_count=len(payloads),
        raw_proposed_count=report["raw_proposed_count"],
        valid_admitted_count=report["valid_admitted_count"],
        invalid_rejected_count=report["invalid_rejected_count"],
        deduplicated_count=report["deduplicated_count"],
        model=response.model,
        reasoning_effort=response.reasoning_effort,
        endpoint_shape=response.endpoint_shape,
        endpoint_host=response.endpoint_host,
        temperature=response.temperature,
        retry_count=response.retry_count,
        response_received_at=response.response_received_at,
    )
    provenance_path = call_root / "call_provenance.json"
    _atomic_write(
        provenance_path,
        canonical_json_bytes(provenance.model_dump(mode="json")),
    )
    completion = {
        "schema_version": "uisemtest-v2-proposal-call-completion-v2",
        "status": "complete",
        "call_id": spec.call_id,
        "request_config_file_sha256": _sha256_file(request_path),
        "raw_response_file_sha256": _sha256_file(raw_path),
        "candidate_validation_file_sha256": _sha256_file(validation_path),
        "candidate_set_sha256": candidate_set.canonical_sha256(),
        "candidate_set_file_sha256": _sha256_file(candidate_path),
        "call_provenance_sha256": canonical_sha256(provenance.model_dump(mode="json")),
        "call_provenance_file_sha256": _sha256_file(provenance_path),
        "parse_admission_status": "admitted",
        "raw_proposed_count": report["raw_proposed_count"],
        "valid_admitted_count": report["valid_admitted_count"],
        "invalid_rejected_count": report["invalid_rejected_count"],
        "deduplicated_count": report["deduplicated_count"],
    }
    completion_path = call_root / "call_completion.json"
    _atomic_json(completion_path, completion)
    return received_at, provenance, completion, payloads, plans, normalized_scan


def _request_config_payload(
    *,
    spec: ProposalCallSpec,
    rendered: RenderedCandidateInput,
    response_delivery_kind: Literal["provider", "sealed_response_replay"],
) -> dict[str, Any]:
    return {
        "schema_version": "uisemtest-v2-sanitized-request-config-v1",
        "call": spec.model_dump(mode="json"),
        "delivery_kind": response_delivery_kind,
        "rendered_text_sha256": rendered.rendered_sha256,
        "scientific_payload_field": "rendered_prompt",
        "additional_evidence_payload_count": 0,
    }


@dataclass(frozen=True)
class _IncompleteProposalRecovery:
    root: Path
    completed_call_ids: tuple[str, ...]
    reusable_call_ids: tuple[str, ...]
    failed_call_ids: tuple[str, ...]
    missing_call_ids: tuple[str, ...]
    prior_attempt_counts: dict[str, int]
    prior_recovery_invocation_count: int
    call_failures: dict[str, dict[str, str]]
    source_resolved_calls: tuple[ProposalCallSpec, ...]
    failure_file_sha256: str

    @classmethod
    def load(
        cls,
        *,
        source_root: Path,
        frozen: V2FrozenInput,
        plan: ProposalRunPlan,
    ) -> "_IncompleteProposalRecovery":
        root = source_root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("incomplete M10 recovery source must be a directory")
        if (root / "proposal_run_completion.json").exists() or (root / "union").exists():
            raise ValueError("incomplete M10 recovery source is already complete")
        source_plan = _read_json(root / "proposal_run_plan.json")
        current_plan = plan.model_dump(mode="json")
        input_hash_fields = {
            "input_freeze_manifest_sha256",
            "package_sha256",
            "view_sha256",
            "rendered_input_sha256",
            "rendered_text_sha256",
        }
        source_call_plan = {
            key: value for key, value in source_plan.items() if key not in input_hash_fields
        }
        current_call_plan = {
            key: value for key, value in current_plan.items() if key not in input_hash_fields
        }
        if source_call_plan != current_call_plan:
            changed = sorted(
                key
                for key in set(source_call_plan) | set(current_call_plan)
                if source_call_plan.get(key) != current_call_plan.get(key)
            )
            raise ValueError(
                "incomplete M10 call plan differs from the current call plan: "
                + ", ".join(changed)
            )
        snapshot = root / "input_snapshot/rendered_candidate_input.json"
        source_rendered = RenderedCandidateInput.model_validate_json(
            snapshot.read_bytes(), strict=True
        )
        if (
            source_rendered.scientific_input_version
            != frozen.lineage.rendered_input.scientific_input_version
            or source_rendered.template_sha256 != plan.template_sha256
        ):
            raise ValueError("incomplete M10 input contract differs from current M9")
        failure_path = root / "proposal_run_failure.json"
        failure = _read_json(failure_path)
        if failure.get("status") != "incomplete":
            raise ValueError("M10 recovery source lacks an incomplete failure record")
        scheduled_rows = failure.get("scheduled_calls")
        if not isinstance(scheduled_rows, list) or not scheduled_rows:
            raise ValueError("M10 recovery lacks its frozen complete call schedule")
        source_resolved_calls = tuple(
            ProposalCallSpec.model_validate(
                {
                    **row,
                    **(
                        {"evidence_card_ids": tuple(row["evidence_card_ids"])}
                        if isinstance(row, dict) and "evidence_card_ids" in row
                        else {}
                    ),
                },
                strict=True,
            )
            for row in scheduled_rows
        )
        scheduled_ids = tuple(spec.call_id for spec in source_resolved_calls)
        if failure.get("scheduled_call_count") != len(source_resolved_calls):
            raise ValueError("M10 recovery scheduled-call count is invalid")

        state_names = (
            "completed_call_ids",
            "reusable_call_ids",
            "failed_call_ids",
            "missing_call_ids",
        )
        state_lists: dict[str, tuple[str, ...]] = {}
        for name in state_names:
            value = failure.get(name)
            if (
                not isinstance(value, list)
                or any(not isinstance(item, str) for item in value)
                or len(value) != len(set(value))
            ):
                raise ValueError(f"M10 recovery {name} is invalid")
            state_lists[name] = tuple(value)
        state_sets = [set(state_lists[name]) for name in state_names]
        if (
            any(
                left & right
                for index, left in enumerate(state_sets)
                for right in state_sets[index + 1:]
            )
            or set().union(*state_sets) != set(scheduled_ids)
            or any(
                state_lists[name]
                != tuple(
                    call_id
                    for call_id in scheduled_ids
                    if call_id in state_sets[index]
                )
                for index, name in enumerate(state_names)
            )
        ):
            raise ValueError("M10 recovery call-state partition differs from its schedule")

        attempts_value = failure.get("call_attempt_counts")
        if not isinstance(attempts_value, dict) or set(attempts_value) != set(
            scheduled_ids
        ):
            raise ValueError("M10 recovery attempt counts do not close its schedule")
        prior_attempt_counts: dict[str, int] = {}
        specs_by_id = {spec.call_id: spec for spec in source_resolved_calls}
        for call_id, value in attempts_value.items():
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                or value > specs_by_id[call_id].retry_limit + 1
            ):
                raise ValueError("M10 recovery contains an invalid attempt count")
            prior_attempt_counts[call_id] = value

        failures_value = failure.get("call_failures")
        noncompleted = set(scheduled_ids) - state_sets[0]
        if not isinstance(failures_value, dict) or set(failures_value) != noncompleted:
            raise ValueError("M10 recovery failure details do not close noncompleted calls")
        call_failures: dict[str, dict[str, str]] = {}
        for call_id, row in failures_value.items():
            if (
                not isinstance(row, dict)
                or set(row) != {"category", "reason"}
                or any(not isinstance(row[key], str) or not row[key] for key in row)
            ):
                raise ValueError("M10 recovery failure detail is invalid")
            call_failures[call_id] = dict(row)

        completed_set = state_sets[0]
        reusable_set = state_sets[1]
        failed_set = state_sets[2]
        missing_set = state_sets[3]
        response_ids = {
            path.parent.name
            for path in root.glob("calls/*/provider_response_envelope.json")
        }
        completion_ids = {
            path.parent.name for path in root.glob("calls/*/call_completion.json")
        }
        if response_ids != completed_set | reusable_set or completion_ids != completed_set:
            raise ValueError("M10 recovery completed-call artifacts are not closed")
        call_dir_ids = {
            path.name for path in (root / "calls").iterdir() if path.is_dir()
        }
        required_call_dirs = completed_set | reusable_set | failed_set
        if not required_call_dirs <= call_dir_ids or not call_dir_ids <= set(scheduled_ids):
            raise ValueError("M10 recovery call directories do not close its schedule")
        if any(prior_attempt_counts[call_id] < 1 for call_id in failed_set):
            raise ValueError("M10 failed calls lack a proven transport attempt")
        if any(prior_attempt_counts[call_id] != 0 for call_id in missing_set):
            raise ValueError("M10 missing calls unexpectedly consumed transport")
        recovery_invocations = failure.get("recovery_logical_invocation_count", 0)
        if (
            not isinstance(recovery_invocations, int)
            or isinstance(recovery_invocations, bool)
            or recovery_invocations < 0
        ):
            raise ValueError("M10 recovery invocation count is invalid")
        return cls(
            root=root,
            completed_call_ids=state_lists["completed_call_ids"],
            reusable_call_ids=state_lists["reusable_call_ids"],
            failed_call_ids=state_lists["failed_call_ids"],
            missing_call_ids=state_lists["missing_call_ids"],
            prior_attempt_counts=prior_attempt_counts,
            prior_recovery_invocation_count=recovery_invocations,
            call_failures=call_failures,
            source_resolved_calls=source_resolved_calls,
            failure_file_sha256=_sha256_file(failure_path),
        )

    def validate_resolved_calls(self, specs: tuple[ProposalCallSpec, ...]) -> None:
        source_has_details = any(
            spec.proposal_round == "detail_proposal"
            for spec in self.source_resolved_calls
        )
        only_scan_calls = all(spec.proposal_round == "global_scan" for spec in specs)
        if source_has_details and only_scan_calls:
            matches = specs == self.source_resolved_calls[: len(specs)]
        elif source_has_details:
            matches = specs == self.source_resolved_calls
        else:
            matches = (
                specs[: len(self.source_resolved_calls)]
                == self.source_resolved_calls
            )
        if not matches:
            raise ValueError("M10 recovery call tree differs from its frozen schedule")

    def prior_attempt_count(self, spec: ProposalCallSpec) -> int:
        if spec.call_id not in self.prior_attempt_counts:
            raise ValueError("M10 recovery call is outside the frozen schedule")
        return self.prior_attempt_counts[spec.call_id]

    def requires_transport(self, spec: ProposalCallSpec) -> bool:
        return spec.call_id in set(self.failed_call_ids) | set(self.missing_call_ids)

    def validate_transport_budget(self, spec: ProposalCallSpec) -> None:
        if not self.requires_transport(spec):
            raise ValueError("M10 recovery attempted transport for a reusable call")
        if self.prior_attempt_count(spec) >= spec.retry_limit + 1:
            raise ValueError(
                f"M10 call exhausted its frozen retry limit: {spec.call_id}"
            )

    def _validate_call_input(
        self,
        *,
        spec: ProposalCallSpec,
        rendered: RenderedCandidateInput,
        response_delivery_kind: Literal["provider", "sealed_response_replay"],
    ) -> Path:
        call_root = self.root / "calls" / spec.call_id
        expected_request = _request_config_payload(
            spec=spec,
            rendered=rendered,
            response_delivery_kind=response_delivery_kind,
        )
        source_request = _read_json(call_root / "request_config.json")
        comparable_source_request = {
            key: value for key, value in source_request.items() if key != "delivery_kind"
        }
        comparable_expected_request = {
            key: value for key, value in expected_request.items() if key != "delivery_kind"
        }
        try:
            source_rendered = RenderedCandidateInput.model_validate_json(
                (call_root / "rendered_candidate_input.json").read_bytes(), strict=True
            )
        except ValueError as exc:
            raise ValueError(
                f"M10 recovery prompt/spec differs for frozen call {spec.call_id}"
            ) from exc
        if (
            source_rendered.rendered_text != rendered.rendered_text
            or source_rendered.rendered_sha256 != rendered.rendered_sha256
            or source_rendered.scientific_input_version
            != rendered.scientific_input_version
            or source_rendered.template_sha256 != rendered.template_sha256
            or comparable_source_request != comparable_expected_request
        ):
            raise ValueError(
                f"M10 recovery prompt/spec differs for frozen call {spec.call_id}"
            )
        return call_root

    def reused_response(
        self,
        *,
        spec: ProposalCallSpec,
        rendered: RenderedCandidateInput,
        response_delivery_kind: Literal["provider", "sealed_response_replay"],
    ) -> RenderedProposalResponse:
        if spec.call_id not in set(self.completed_call_ids) | set(self.reusable_call_ids):
            raise ValueError("M10 recovery attempted to reuse an uncompleted call")
        call_root = self._validate_call_input(
            spec=spec,
            rendered=rendered,
            response_delivery_kind=response_delivery_kind,
        )
        response_path = call_root / "provider_response_envelope.json"
        return load_sealed_rendered_proposal_response(
            response_path,
            expected_file_sha256=_sha256_file(response_path),
        )

    def validate_transport_input(
        self,
        *,
        spec: ProposalCallSpec,
        rendered: RenderedCandidateInput,
        response_delivery_kind: Literal["provider", "sealed_response_replay"],
    ) -> None:
        if not self.requires_transport(spec):
            raise ValueError("M10 recovery transport-call identity drift")
        if (
            spec.call_id in self.missing_call_ids
            and not (self.root / "calls" / spec.call_id).is_dir()
        ):
            return
        self._validate_call_input(
            spec=spec,
            rendered=rendered,
            response_delivery_kind=response_delivery_kind,
        )


@dataclass(frozen=True)
class _PreparedStageCall:
    spec: ProposalCallSpec
    rendered: RenderedCandidateInput
    region: DetailRegion | None
    call_root: Path
    reused_response: RenderedProposalResponse | None
    prior_attempt_count: int


@dataclass(frozen=True)
class _ProviderStageResult:
    provenances: tuple[ProposalCallProvenance, ...]
    payloads: tuple[dict[str, Any], ...]
    plans: tuple[dict[str, Any], ...]
    scan_decisions: tuple[dict[str, Any], ...]
    actual_model_family: str | None
    reused_call_ids: tuple[str, ...]
    attempt_counts: dict[str, int]
    call_failures: dict[str, dict[str, str]]
    first_error: Exception | None
    actual_max_concurrency: int


def _execute_provider_stage(
    *,
    frozen: V2FrozenInput,
    plan: ProposalRunPlan,
    provider_factory: ProviderFactory,
    staging: Path,
    response_delivery_kind: Literal["provider", "sealed_response_replay"],
    calls: tuple[
        tuple[ProposalCallSpec, RenderedCandidateInput, DetailRegion | None], ...
    ],
    recovery: _IncompleteProposalRecovery | None,
    provider_concurrency: int,
    actual_model_family: str | None,
) -> _ProviderStageResult:
    """Transport one complete stage concurrently, then process by call order."""

    prepared: list[_PreparedStageCall] = []
    reused_call_ids: list[str] = []
    attempt_counts: dict[str, int] = {}
    source_ids = (
        {spec.call_id for spec in recovery.source_resolved_calls}
        if recovery is not None
        else set()
    )
    for spec, rendered, region in calls:
        call_root = staging / "calls" / spec.call_id
        _prepare_dynamic_call_artifacts(
            spec=spec,
            rendered=rendered,
            call_root=call_root,
            response_delivery_kind=response_delivery_kind,
        )
        reused_response = None
        prior_attempt_count = 0
        if recovery is not None and spec.call_id in source_ids:
            prior_attempt_count = recovery.prior_attempt_count(spec)
            if spec.call_id in set(recovery.completed_call_ids) | set(
                recovery.reusable_call_ids
            ):
                reused_response = recovery.reused_response(
                    spec=spec,
                    rendered=rendered,
                    response_delivery_kind=response_delivery_kind,
                )
                marker = getattr(provider_factory, "mark_reused_call", None)
                if marker is None:
                    raise ValueError("current provider cannot register a reused M10 call")
                marker(spec)
                reused_call_ids.append(spec.call_id)
                _persist_dynamic_response(response=reused_response, call_root=call_root)
        attempt_counts[spec.call_id] = prior_attempt_count
        prepared.append(_PreparedStageCall(
            spec=spec,
            rendered=rendered,
            region=region,
            call_root=call_root,
            reused_response=reused_response,
            prior_attempt_count=prior_attempt_count,
        ))

    preflight = getattr(provider_factory, "preflight", None)
    for row in prepared:
        if preflight is not None:
            preflight(row.rendered.rendered_text)
        if (
            recovery is None
            or row.spec.call_id not in source_ids
            or row.reused_response is not None
        ):
            continue
        recovery.validate_transport_input(
            spec=row.spec,
            rendered=row.rendered,
            response_delivery_kind=response_delivery_kind,
        )
        recovery.validate_transport_budget(row.spec)
        if row.prior_attempt_count:
            resume = getattr(provider_factory, "resume_failed_call", None)
            if resume is None:
                raise ValueError("current provider cannot resume a failed M10 call")
            resume(row.spec, prior_attempt_count=row.prior_attempt_count)

    responses: dict[str, RenderedProposalResponse] = {
        row.spec.call_id: row.reused_response
        for row in prepared
        if row.reused_response is not None
    }
    transport_rows = [row for row in prepared if row.reused_response is None]
    transport_failures: dict[str, Exception] = {}
    not_dispatched: list[_PreparedStageCall] = []
    attempts_for = getattr(provider_factory, "transport_attempts_for", None)

    if transport_rows:
        iterator = iter(transport_rows)
        in_flight: dict[Future[RenderedProposalResponse], _PreparedStageCall] = {}
        stopped = False
        active_transports = 0
        actual_max_concurrency = 0
        activity_lock = Lock()

        def transport(row: _PreparedStageCall) -> RenderedProposalResponse:
            nonlocal active_transports, actual_max_concurrency
            with activity_lock:
                active_transports += 1
                actual_max_concurrency = max(
                    actual_max_concurrency, active_transports
                )
            try:
                return _transport_dynamic_response(
                    spec=row.spec,
                    rendered=row.rendered,
                    provider_factory=provider_factory,
                    call_root=row.call_root,
                )
            finally:
                with activity_lock:
                    active_transports -= 1

        with ThreadPoolExecutor(
            max_workers=min(provider_concurrency, len(transport_rows)),
            thread_name_prefix="uisemtest-m10-provider",
        ) as executor:
            def submit_available() -> None:
                while not stopped and len(in_flight) < provider_concurrency:
                    try:
                        row = next(iterator)
                    except StopIteration:
                        return
                    future = executor.submit(transport, row)
                    in_flight[future] = row

            submit_available()
            while in_flight:
                done, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
                failed_now = False
                for future in sorted(
                    done, key=lambda item: in_flight[item].spec.call_order
                ):
                    row = in_flight.pop(future)
                    try:
                        responses[row.spec.call_id] = future.result()
                    except Exception as exc:
                        transport_failures[row.spec.call_id] = exc
                        failed_now = True
                    observed_attempts = (
                        attempts_for(row.spec.call_id)
                        if attempts_for is not None
                        else row.prior_attempt_count + 1
                    )
                    attempt_counts[row.spec.call_id] = max(
                        row.prior_attempt_count, observed_attempts
                    )
                if failed_now:
                    stopped = True
                submit_available()
            not_dispatched.extend(iterator)
    else:
        actual_max_concurrency = 0

    call_failures: dict[str, dict[str, str]] = {
        call_id: {
            "category": (
                f"{next(row.spec.proposal_round for row in prepared if row.spec.call_id == call_id)}"
                "_transport_failed"
            ),
            "reason": f"{type(exc).__name__}: {exc}",
        }
        for call_id, exc in transport_failures.items()
    }
    for row in not_dispatched:
        call_failures[row.spec.call_id] = {
            "category": f"{row.spec.proposal_round}_not_dispatched",
            "reason": "not dispatched after an earlier transport failure in the same stage",
        }

    provenances: list[ProposalCallProvenance] = []
    payloads: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    scan_decisions: list[dict[str, Any]] = []
    processing_errors: dict[str, Exception] = {}
    model_family = actual_model_family
    for row in prepared:
        response = responses.get(row.spec.call_id)
        if response is None:
            continue
        try:
            _validate_response_metadata(
                response,
                row.spec,
                plan,
                allow_historical_timestamp=(
                    response_delivery_kind == "sealed_response_replay"
                    or row.reused_response is not None
                ),
            )
            observed_family = (
                response.model
                if plan.actual_model_policy == "exact"
                else _provider_model_family(response.model)
            )
            if model_family is None:
                model_family = observed_family
            elif observed_family != model_family:
                raise ValueError(
                    "provider actual model changed within the frozen proposal run"
                )
            _, provenance, _, found_payloads, found_plans, decisions = (
                _process_dynamic_call_artifacts(
                    frozen=frozen,
                    plan=plan,
                    spec=row.spec,
                    rendered=row.rendered,
                    call_root=row.call_root,
                    response_delivery_kind=response_delivery_kind,
                    region=row.region,
                    response=response,
                    reused_response=row.reused_response is not None,
                )
            )
            provenances.append(provenance)
            payloads.extend(found_payloads)
            plans.extend(found_plans)
            scan_decisions.extend(decisions)
        except Exception as exc:
            processing_errors[row.spec.call_id] = exc
            call_failures[row.spec.call_id] = {
                "category": f"{row.spec.proposal_round}_response_processing_failed",
                "reason": f"{type(exc).__name__}: {exc}",
            }

    error_ids = set(transport_failures) | set(processing_errors)
    first_error = next(
        (
            transport_failures.get(row.spec.call_id)
            or processing_errors.get(row.spec.call_id)
            for row in prepared
            if row.spec.call_id in error_ids
        ),
        None,
    )
    return _ProviderStageResult(
        provenances=tuple(provenances),
        payloads=tuple(payloads),
        plans=tuple(plans),
        scan_decisions=tuple(scan_decisions),
        actual_model_family=model_family,
        reused_call_ids=tuple(reused_call_ids),
        attempt_counts=attempt_counts,
        call_failures=call_failures,
        first_error=first_error,
        actual_max_concurrency=actual_max_concurrency,
    )


def _execute_dynamic_v2_proposal_run(
    *,
    frozen: V2FrozenInput,
    plan: ProposalRunPlan,
    provider_factory: ProviderFactory,
    output_root: Path,
    response_delivery_kind: Literal["provider", "sealed_response_replay"],
    incomplete_run_root: Path | None,
    provider_concurrency: int,
) -> V2ProposalRunLineage:
    if (
        not isinstance(provider_concurrency, int)
        or isinstance(provider_concurrency, bool)
        or provider_concurrency < 1
    ):
        raise ValueError("provider concurrency must be a positive integer")
    target = output_root.resolve()
    if target.exists():
        raise ValueError(
            "proposal output root must be new and separate from the input trust root"
        )
    if target == frozen.manifest_path.parent or frozen.manifest_path.parent in target.parents:
        raise ValueError("proposal output root cannot be inside the input trust root")
    recovery = (
        _IncompleteProposalRecovery.load(
            source_root=incomplete_run_root,
            frozen=frozen,
            plan=plan,
        )
        if incomplete_run_root is not None
        else None
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    completed: dict[str, str] = {}
    provenance_hashes: dict[str, str] = {}
    raw_hashes: dict[str, str] = {}
    all_payloads: list[dict[str, Any]] = []
    all_plans: list[dict[str, Any]] = []
    normalized_decisions: list[dict[str, Any]] = []
    reused_call_ids: set[str] = set()
    actual_model_seen: str | None = None
    attempt_counts: dict[str, int] = {}
    call_failures: dict[str, dict[str, str]] = {}
    actual_max_concurrency = 0
    resolved_schedule: tuple[ProposalCallSpec, ...] = plan.calls
    try:
        plan_path = staging / "proposal_run_plan.json"
        _atomic_write(plan_path, canonical_json_bytes(plan.model_dump(mode="json")))
        snapshot = staging / "input_snapshot"
        snapshot.mkdir()
        _copy_exact(
            frozen.artifact_paths["rendered"],
            snapshot / "rendered_candidate_input.json",
        )
        if recovery is not None:
            recovery.validate_resolved_calls(plan.calls)
            _atomic_json(
                staging / "proposal_run_recovery.json",
                {
                    "status": "resumed",
                    "source_failure_file_sha256": recovery.failure_file_sha256,
                    "reused_call_ids": [
                        *recovery.completed_call_ids,
                        *recovery.reusable_call_ids,
                    ],
                    "transport_call_ids": [
                        *recovery.failed_call_ids,
                        *recovery.missing_call_ids,
                    ],
                    "prior_call_attempt_counts": recovery.prior_attempt_counts,
                    "prior_call_failures": recovery.call_failures,
                    "recovery_logical_invocation_count": (
                        recovery.prior_recovery_invocation_count + 1
                    ),
                    "provider_concurrency_planned": provider_concurrency,
                },
            )
        completion_mode = bool(
            plan.calls and plan.calls[0].proposal_round == "center_completion"
        )
        if completion_mode:
            derived = _completion_regions_for_plan(frozen, plan)
        else:
            scan_calls = tuple(
                (
                    spec,
                    _proposal_call_input(frozen, spec).rendered_input,
                    None,
                )
                for spec in plan.calls
            )
            scan_result = _execute_provider_stage(
                frozen=frozen,
                plan=plan,
                provider_factory=provider_factory,
                staging=staging,
                response_delivery_kind=response_delivery_kind,
                calls=scan_calls,
                recovery=recovery,
                provider_concurrency=provider_concurrency,
                actual_model_family=actual_model_seen,
            )
            actual_model_seen = scan_result.actual_model_family
            actual_max_concurrency = max(
                actual_max_concurrency, scan_result.actual_max_concurrency
            )
            attempt_counts.update(scan_result.attempt_counts)
            call_failures.update(scan_result.call_failures)
            reused_call_ids.update(scan_result.reused_call_ids)
            for provenance in scan_result.provenances:
                completed[provenance.call_id] = _sha256_file(
                    staging / "calls" / provenance.call_id / "call_completion.json"
                )
                provenance_hashes[provenance.call_id] = canonical_sha256(
                    provenance.model_dump(mode="json")
                )
                raw_hashes[provenance.call_id] = provenance.raw_response_file_sha256
            normalized_decisions.extend(scan_result.scan_decisions)
            if scan_result.first_error is not None:
                raise scan_result.first_error

            derived = (
                derive_detail_regions(
                    frozen,
                    normalized_decisions=tuple(normalized_decisions),
                    first_call_order=len(plan.calls) + 1,
                    detail_max_requests=plan.detail_max_requests,
                    detail_max_rendered_utf8_bytes=plan.detail_max_rendered_utf8_bytes,
                    call_prototype=plan.calls[0],
                )
                if plan.calls
                else ()
            )
        detail_specs = tuple(spec for _, spec in derived)
        resolved_schedule = (
            detail_specs if completion_mode else (*plan.calls, *detail_specs)
        )
        register = getattr(provider_factory, "register_calls", None)
        if register is not None:
            register(detail_specs)
        if recovery is not None:
            recovery.validate_resolved_calls(resolved_schedule)
        detail_calls = tuple(
            (
                spec,
                (
                    _render_center_completion_input(frozen, region)
                    if completion_mode
                    else _render_detail_input(frozen, region)
                ),
                region,
            )
            for region, spec in derived
        )
        if completion_mode and detail_calls:
            preflight = getattr(provider_factory, "preflight", None)
            if preflight is not None:
                preflight(max(
                    (rendered.rendered_text for _, rendered, _ in detail_calls),
                    key=len,
                ))
        detail_result = _execute_provider_stage(
            frozen=frozen,
            plan=plan,
            provider_factory=provider_factory,
            staging=staging,
            response_delivery_kind=response_delivery_kind,
            calls=detail_calls,
            recovery=recovery,
            provider_concurrency=provider_concurrency,
            actual_model_family=actual_model_seen,
        )
        actual_model_seen = detail_result.actual_model_family
        actual_max_concurrency = max(
            actual_max_concurrency, detail_result.actual_max_concurrency
        )
        attempt_counts.update(detail_result.attempt_counts)
        call_failures.update(detail_result.call_failures)
        reused_call_ids.update(detail_result.reused_call_ids)
        for provenance in detail_result.provenances:
            completed[provenance.call_id] = _sha256_file(
                staging / "calls" / provenance.call_id / "call_completion.json"
            )
            provenance_hashes[provenance.call_id] = canonical_sha256(
                provenance.model_dump(mode="json")
            )
            raw_hashes[provenance.call_id] = provenance.raw_response_file_sha256
        all_payloads.extend(detail_result.payloads)
        all_plans.extend(detail_result.plans)
        if detail_result.first_error is not None:
            raise detail_result.first_error

        union_payloads = _deduplicate_payloads(all_payloads)
        within_call_dedup = sum(
            _read_json(staging / "calls" / spec.call_id / "candidate_validation_report.json")[
                "deduplicated_count"
            ]
            for _, spec in derived
        )
        invalid_count = sum(
            _read_json(staging / "calls" / spec.call_id / "candidate_validation_report.json")[
                "invalid_rejected_count"
            ]
            for _, spec in derived
        )
        raw_count = sum(
            _read_json(staging / "calls" / spec.call_id / "candidate_validation_report.json")[
                "raw_proposed_count"
            ]
            for _, spec in derived
        )
        admitted_core_identities = tuple(
            str(row["canonical_relation_core_identity"])
            for _, spec in derived
            for row in _read_json(
                staging / "calls" / spec.call_id / "candidate_validation_report.json"
            )["candidates"]
            if row["disposition"] in {"admitted", "deduplicated"}
        )
        dedup_count = within_call_dedup + len(all_payloads) - len(union_payloads)
        plans_by_id = {str(row["plan_id"]): row for row in all_plans}
        union_plan_ids = {
            str(payload["observation_opportunity_ref"]) for payload in union_payloads
        }
        union_plans = tuple(plans_by_id[key] for key in sorted(union_plan_ids))
        union_root = staging / "union"
        union_root.mkdir()
        _copy_exact(
            frozen.artifact_paths["rendered"],
            union_root / "rendered_candidate_input.json",
        )
        union = _candidate_set(
            union_payloads,
            frozen=frozen,
            seed_label=canonical_sha256(union_payloads),
            rendered_ref="rendered_candidate_input.json",
        )
        union_path = union_root / "candidate_set.json"
        _atomic_write(union_path, union.canonical_bytes())
        funnel = {
            "m9_atomic_card_universe": sum(
                card.card_kind in {"action_episode", "unassigned_request"}
                for card in frozen.lineage.view.evidence_cards
            ),
            "scan_primary_covered": len(normalized_decisions),
            "selected_roots": len({
                row["primary_card_id"]
                for row in normalized_decisions
                if row["decision"] == "expand"
            }),
            "mandatory_episode_roots": len({
                region.primary_card_id
                for region, _ in derived
                if region.region_kind == "business_operation_episode"
            }),
            "detail_roots": len({
                region.primary_card_id for region, _ in derived
            }),
            "constructed_detail_regions": len(derived),
            "detail_calls_completed": len(derived),
            "raw_candidates": raw_count,
            "admitted_candidates": len(all_payloads),
            "deduplicated_candidates": len(union_payloads),
            "center_completion_calls": (
                len(derived) if completion_mode else 0
            ),
        }
        resolved_specs = resolved_schedule
        union_provenance = ProposalUnionProvenance(
            plan_sha256=canonical_sha256(plan.model_dump(mode="json")),
            plan_scientific_sha256=plan.scientific_sha256(),
            input_freeze_manifest_sha256=frozen.manifest_raw_sha256,
            call_ids=tuple(spec.call_id for spec in resolved_specs),
            call_provenance_sha256=provenance_hashes,
            raw_response_file_sha256=raw_hashes,
            raw_proposed_count=raw_count,
            valid_admitted_count=len(union_payloads),
            invalid_rejected_count=invalid_count,
            deduplicated_count=dedup_count,
            union_candidate_set_sha256=union.canonical_sha256(),
            constructed_execution_plans=union_plans,
            resolved_calls=tuple(spec.model_dump(mode="json") for spec in resolved_specs),
            detail_regions=tuple(region.model_dump(mode="json") for region, _ in derived),
            proposal_funnel=funnel,
            center_completion=(
                {
                    "mode": "bounded-center-completion",
                    "scheduled_center_count": len(derived),
                    "logical_call_limit_per_center": 1,
                }
                if completion_mode
                else {}
            ),
            admitted_canonical_relation_core_identities=admitted_core_identities,
        )
        provenance_path = union_root / "union_provenance.json"
        _atomic_write(
            provenance_path,
            canonical_json_bytes(union_provenance.model_dump(mode="json")),
        )
        _atomic_json(
            staging / "evidence_card_coverage_ledger.json",
            {"schema_version": "uisemtest-v2-evidence-card-coverage-ledger-v2", **funnel},
        )
        completion = ProposalRunCompletion(
            status="complete",
            plan_file_sha256=_sha256_file(plan_path),
            plan_sha256=canonical_sha256(plan.model_dump(mode="json")),
            input_freeze_manifest_sha256=frozen.manifest_raw_sha256,
            scheduled_call_count=len(resolved_specs),
            completed_call_count=len(completed),
            call_completion_sha256=completed,
            union_candidate_set_sha256=union.canonical_sha256(),
            union_provenance_sha256=canonical_sha256(
                union_provenance.model_dump(mode="json")
            ),
            union_candidate_set_file_sha256=_sha256_file(union_path),
            union_provenance_file_sha256=_sha256_file(provenance_path),
            provider_logical_call_count=(
                0
                if response_delivery_kind == "sealed_response_replay"
                else int(
                    getattr(
                        provider_factory,
                        "logical_call_count",
                        len(resolved_specs) - len(reused_call_ids),
                    )
                )
            ),
            provider_concurrency_planned=provider_concurrency,
            provider_concurrency_actual_max=actual_max_concurrency,
            raw_proposed_count=raw_count,
            valid_admitted_count=len(union_payloads),
            invalid_rejected_count=invalid_count,
            deduplicated_count=dedup_count,
        )
        completion_path = staging / "proposal_run_completion.json"
        _atomic_write(
            completion_path,
            canonical_json_bytes(completion.model_dump(mode="json")),
        )
        os.replace(staging, target)
        return _load_dynamic_v2_proposal_run_lineage(
            run_root=target,
            frozen=frozen,
            completion_sha256=_sha256_file(target / "proposal_run_completion.json"),
        )
    except Exception as error:
        raw_responses = sorted(
            staging.glob("calls/*/provider_response_envelope.json")
        )
        if raw_responses or any(attempt_counts.values()):
            scheduled_ids = tuple(spec.call_id for spec in resolved_schedule)
            for call_id in scheduled_ids:
                attempt_counts.setdefault(
                    call_id,
                    (
                        recovery.prior_attempt_counts.get(call_id, 0)
                        if recovery is not None
                        else 0
                    ),
                )
            completed_ids = tuple(
                call_id
                for call_id in scheduled_ids
                if (staging / "calls" / call_id / "call_completion.json").is_file()
            )
            reusable_ids = tuple(
                call_id
                for call_id in scheduled_ids
                if call_id not in completed_ids
                and (staging / "calls" / call_id / "provider_response_envelope.json").is_file()
            )
            failed_ids = tuple(
                call_id
                for call_id in scheduled_ids
                if call_id not in completed_ids
                and call_id not in reusable_ids
                and attempt_counts[call_id] > 0
            )
            missing_ids = tuple(
                call_id
                for call_id in scheduled_ids
                if call_id not in completed_ids
                and call_id not in reusable_ids
                and call_id not in failed_ids
            )
            for call_id in (*reusable_ids, *failed_ids, *missing_ids):
                call_failures.setdefault(
                    call_id,
                    {
                        "category": "proposal_run_processing_failed",
                        "reason": f"{type(error).__name__}: {error}",
                    },
                )
            failure = {
                "status": "incomplete",
                "completed_call_ids": list(completed_ids),
                "reusable_call_ids": list(reusable_ids),
                "failed_call_ids": list(failed_ids),
                "missing_call_ids": list(missing_ids),
                "call_attempt_counts": {
                    call_id: attempt_counts[call_id] for call_id in scheduled_ids
                },
                "call_failures": {
                    call_id: call_failures[call_id]
                    for call_id in scheduled_ids
                    if call_id not in completed_ids
                },
                "run_failure": {
                    "category": "proposal_run_incomplete",
                    "reason": f"{type(error).__name__}: {error}",
                },
                "scheduled_call_count": len(resolved_schedule),
                "scheduled_calls": [
                    spec.model_dump(mode="json") for spec in resolved_schedule
                ],
                "provider_concurrency_planned": provider_concurrency,
                "provider_concurrency_actual_max": actual_max_concurrency,
                "recovery_logical_invocation_count": (
                    recovery.prior_recovery_invocation_count + 1
                    if recovery is not None
                    else 0
                ),
            }
            if recovery is not None:
                failure["source_failure_file_sha256"] = recovery.failure_file_sha256
            _atomic_json(staging / "proposal_run_failure.json", failure)
            os.replace(staging, target)
        elif staging.exists():
            shutil.rmtree(staging)
        raise


def execute_v2_proposal_run(
    *,
    input_freeze_manifest_path: str | Path,
    expected_manifest_sha256: str,
    plan: ProposalRunPlan,
    provider_factory: ProviderFactory,
    output_root: str | Path,
    response_delivery_kind: Literal["provider", "sealed_response_replay"] = "provider",
    incomplete_run_root: str | Path | None = None,
    provider_concurrency: int = 1,
) -> V2ProposalRunLineage:
    """Execute the sole current two-stage M10 path and seal one lineage."""

    frozen = load_hardened_v2_input(
        input_freeze_manifest_path=input_freeze_manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
        require_current_revision=True,
    )
    _validate_plan_against_input(plan, frozen)
    return _execute_dynamic_v2_proposal_run(
        frozen=frozen,
        plan=plan,
        provider_factory=provider_factory,
        output_root=Path(output_root),
        response_delivery_kind=response_delivery_kind,
        incomplete_run_root=(
            Path(incomplete_run_root) if incomplete_run_root is not None else None
        ),
        provider_concurrency=provider_concurrency,
    )


def union_v2_proposal_rounds(
    *,
    frozen: V2FrozenInput,
    rounds: tuple[V2ProposalRunLineage, ...],
    output_root: str | Path,
    provider_factory: ProviderFactory | None = None,
    response_delivery_kind: Literal[
        "provider", "sealed_response_replay"
    ] = "provider",
    provider_concurrency: int = 12,
    incomplete_completion_root: str | Path | None = None,
) -> V2ProposalRunLineage:
    """Seal the canonical cross-round union and its bounded center completion."""

    if not rounds:
        raise ValueError("proposal round union requires at least one complete round")
    target = Path(output_root).resolve()
    if target.exists():
        raise ValueError("proposal round union output root must be fresh")
    package_sha = frozen.lineage.package.canonical_sha256()
    view_sha = frozen.lineage.view.canonical_sha256()
    rendered_sha = frozen.lineage.rendered_input.canonical_sha256()
    for round_lineage in rounds:
        if round_lineage.completion.status != "complete":
            raise ValueError("proposal round union received an incomplete round")
        lineage = round_lineage.frozen_input.lineage
        if (
            lineage.package.canonical_sha256() != package_sha
            or lineage.view.canonical_sha256() != view_sha
            or lineage.rendered_input.canonical_sha256() != rendered_sha
        ):
            raise ValueError("proposal round scientific inputs differ")

    regular_payloads = [
        {
            key: copy.deepcopy(value)
            for key, value in record.payload.items()
            if key not in {"schema_version", "candidate_id"}
        }
        for round_lineage in rounds
        for record in round_lineage.candidate_set.candidates
    ]
    center_regions = _opportunity_completion_regions(frozen)
    regular_center_counts = {
        region.region_id: _completion_candidate_count(regular_payloads, region)
        for region in center_regions
    }
    missing_regions = tuple(
        region
        for region in center_regions
        if regular_center_counts[region.region_id] == 0
    )
    completion_lineage: V2ProposalRunLineage | None = None
    completion_payloads: list[dict[str, Any]] = []
    if missing_regions:
        if provider_factory is None:
            raise ValueError(
                "complete-round union with uncovered opportunities requires the "
                "current completion provider"
            )
        prototype = next(
            (spec for spec in rounds[0].plan.calls if spec.proposal_round == "global_scan"),
            None,
        )
        if prototype is None:
            raise ValueError("center completion lacks a frozen provider policy")
        completion_calls = tuple(
            ProposalCallSpec(
                call_id=region.region_id,
                call_order=index,
                model=prototype.model,
                reasoning_effort=prototype.reasoning_effort,
                temperature=prototype.temperature,
                retry_limit=3,
                endpoint_shape=prototype.endpoint_shape,
                endpoint_host=prototype.endpoint_host,
                stratum="business",
                proposal_round="center_completion",
                evidence_card_ids=(region.primary_card_id,),
                detail_region_id=region.region_id,
            )
            for index, region in enumerate(missing_regions, start=1)
        )
        completion_plan = build_proposal_run_plan(
            frozen,
            plan_id=(
                "m10-center-completion-"
                + canonical_sha256(
                    [region.primary_card_id for region in missing_regions]
                )[:16]
            ),
            frozen_at=rounds[0].plan.frozen_at,
            calls=completion_calls,
            actual_model_policy=rounds[0].plan.actual_model_policy,
        )
        _validate_plan_against_input(completion_plan, frozen)
        completion_lineage = _execute_dynamic_v2_proposal_run(
            frozen=frozen,
            plan=completion_plan,
            provider_factory=provider_factory,
            output_root=target / "center_completion",
            response_delivery_kind=response_delivery_kind,
            incomplete_run_root=(
                Path(incomplete_completion_root)
                if incomplete_completion_root is not None
                else None
            ),
            provider_concurrency=provider_concurrency,
        )
        completion_payloads = [
            {
                key: copy.deepcopy(value)
                for key, value in record.payload.items()
                if key not in {"schema_version", "candidate_id"}
            }
            for record in completion_lineage.candidate_set.candidates
        ]
    union_payloads = _deduplicate_payloads([
        *regular_payloads, *completion_payloads
    ])
    round_candidate_hashes = {
        f"round_{index:04d}_candidate_set": round_lineage.candidate_set.canonical_sha256()
        for index, round_lineage in enumerate(rounds, start=1)
    }
    source_identity = {
        "mode": "union-with-bounded-center-completion",
        "round_candidate_sets": round_candidate_hashes,
        "center_completion_candidate_set": (
            completion_lineage.candidate_set.canonical_sha256()
            if completion_lineage is not None
            else None
        ),
    }
    candidate_set = _candidate_set(
        union_payloads,
        frozen=frozen,
        seed_label=canonical_sha256(source_identity),
        rendered_ref="../../M01_09/rendered_candidate_input.json",
    )
    candidate_set = candidate_set.model_copy(
        update={
            "source_refs": (
                candidate_set.rendered_input_ref,
                *tuple(
                    f"round:{index:04d}:{round_lineage.completion_raw_sha256}"
                    for index, round_lineage in enumerate(rounds, start=1)
                ),
                *(
                    (f"center-completion:{completion_lineage.completion_raw_sha256}",)
                    if completion_lineage is not None
                    else ()
                ),
            ),
            "source_sha256": {
                **candidate_set.source_sha256,
                **round_candidate_hashes,
                **(
                    {
                        "center_completion_candidate_set": (
                            completion_lineage.candidate_set.canonical_sha256()
                        )
                    }
                    if completion_lineage is not None
                    else {}
                ),
                "round_union_identity": canonical_sha256(
                    [_scientific_relation_payload(payload) for payload in union_payloads]
                ),
            },
        }
    )

    plans: dict[str, dict[str, Any]] = {}
    for round_lineage in rounds:
        for plan in round_lineage.union_provenance.constructed_execution_plans:
            plan_id = str(plan["plan_id"])
            existing = plans.get(plan_id)
            if existing is not None and existing != plan:
                raise ValueError("proposal rounds disagree on an execution plan")
            plans[plan_id] = copy.deepcopy(plan)
    if completion_lineage is not None:
        for plan in completion_lineage.union_provenance.constructed_execution_plans:
            plan_id = str(plan["plan_id"])
            existing = plans.get(plan_id)
            if existing is not None and existing != plan:
                raise ValueError("completion pass disagrees on an execution plan")
            plans[plan_id] = copy.deepcopy(plan)

    call_ids: list[str] = []
    call_provenance: dict[str, str] = {}
    raw_responses: dict[str, str] = {}
    call_completions: dict[str, str] = {}
    resolved_calls: list[dict[str, Any]] = []
    detail_regions: list[dict[str, Any]] = []
    for index, round_lineage in enumerate(rounds, start=1):
        prefix = f"round-{index:04d}"
        for call_id in round_lineage.union_provenance.call_ids:
            union_call_id = f"{prefix}:{call_id}"
            call_ids.append(union_call_id)
            call_provenance[union_call_id] = (
                round_lineage.call_provenance_sha256[call_id]
            )
            raw_responses[union_call_id] = round_lineage.raw_response_sha256[call_id]
            call_completions[union_call_id] = (
                round_lineage.completion.call_completion_sha256[call_id]
            )
        resolved_calls.extend(
            {"sample_round": index, **copy.deepcopy(spec)}
            for spec in round_lineage.union_provenance.resolved_calls
        )
        detail_regions.extend(
            {"sample_round": index, **copy.deepcopy(region)}
            for region in round_lineage.union_provenance.detail_regions
        )

    if completion_lineage is not None:
        for call_id in completion_lineage.union_provenance.call_ids:
            union_call_id = f"center-completion:{call_id}"
            call_ids.append(union_call_id)
            call_provenance[union_call_id] = (
                completion_lineage.call_provenance_sha256[call_id]
            )
            raw_responses[union_call_id] = (
                completion_lineage.raw_response_sha256[call_id]
            )
            call_completions[union_call_id] = (
                completion_lineage.completion.call_completion_sha256[call_id]
            )
        resolved_calls.extend(
            {"sample_round": "center_completion", **copy.deepcopy(spec)}
            for spec in completion_lineage.union_provenance.resolved_calls
        )
        detail_regions.extend(
            {"sample_round": "center_completion", **copy.deepcopy(region)}
            for region in completion_lineage.union_provenance.detail_regions
        )

    raw_count = sum(row.union_provenance.raw_proposed_count for row in rounds) + (
        completion_lineage.union_provenance.raw_proposed_count
        if completion_lineage is not None
        else 0
    )
    invalid_count = sum(
        row.union_provenance.invalid_rejected_count for row in rounds
    ) + (
        completion_lineage.union_provenance.invalid_rejected_count
        if completion_lineage is not None
        else 0
    )
    deduplicated_count = raw_count - invalid_count - len(union_payloads)
    center_statuses = []
    for region in center_regions:
        regular_count = regular_center_counts[region.region_id]
        completion_count = _completion_candidate_count(
            completion_payloads, region
        )
        center_statuses.append({
            "center_action_id": region.center_action_id,
            "primary_card_id": region.primary_card_id,
            "center_state_change_request_refs": list(
                region.center_state_change_request_refs
            ),
            "regular_admitted_centered_relation_count": regular_count,
            "completion_admitted_centered_relation_count": completion_count,
            "completion_call_id": (
                region.region_id if region in missing_regions else None
            ),
            "status": (
                "covered"
                if regular_count or completion_count
                else "completion-pass-empty/rejected"
            ),
        })
    completion_status = (
        "covered"
        if all(row["status"] == "covered" for row in center_statuses)
        else "completion-pass-empty/rejected"
    )
    center_completion_summary = {
        "trigger_round_count": len(rounds),
        "observed_regular_round_count": len(rounds),
        "triggered": bool(missing_regions),
        "logical_call_limit_per_missing_center": 1,
        "regularly_uncovered_center_count": len(missing_regions),
        "scheduled_completion_call_count": len(missing_regions),
        "provider_logical_call_count": (
            completion_lineage.completion.provider_logical_call_count
            if completion_lineage is not None
            else 0
        ),
        "provider_token_usage": _provider_token_usage(completion_lineage),
        "raw_proposed_count": (
            completion_lineage.union_provenance.raw_proposed_count
            if completion_lineage is not None
            else 0
        ),
        "valid_admitted_count": (
            completion_lineage.union_provenance.valid_admitted_count
            if completion_lineage is not None
            else 0
        ),
        "invalid_rejected_count": (
            completion_lineage.union_provenance.invalid_rejected_count
            if completion_lineage is not None
            else 0
        ),
        "completion_run_sha256": (
            completion_lineage.completion_raw_sha256
            if completion_lineage is not None
            else None
        ),
        "status": completion_status,
        "centers": center_statuses,
    }
    plan_summary = {
        "schema_version": "uisemtest-m10-proposal-round-union-plan-v2",
        "mode": "union",
        "round_count": len(rounds),
        "round_plan_sha256": [row.plan_sha256 for row in rounds],
        "round_completion_sha256": [row.completion_raw_sha256 for row in rounds],
        "center_completion": center_completion_summary,
    }
    plan_sha = canonical_sha256(plan_summary)
    provenance = ProposalUnionProvenance(
        plan_sha256=plan_sha,
        plan_scientific_sha256=canonical_sha256(
            [row.plan.scientific_sha256() for row in rounds]
        ),
        input_freeze_manifest_sha256=frozen.manifest_raw_sha256,
        call_ids=tuple(call_ids),
        call_provenance_sha256=call_provenance,
        raw_response_file_sha256=raw_responses,
        raw_proposed_count=raw_count,
        valid_admitted_count=len(union_payloads),
        invalid_rejected_count=invalid_count,
        deduplicated_count=deduplicated_count,
        union_candidate_set_sha256=candidate_set.canonical_sha256(),
        constructed_execution_plans=tuple(plans[key] for key in sorted(plans)),
        resolved_calls=tuple(resolved_calls),
        detail_regions=tuple(detail_regions),
        proposal_funnel={
            "sample_rounds": len(rounds),
            "raw_candidates": raw_count,
            "admitted_candidates": sum(
                row.union_provenance.valid_admitted_count for row in rounds
            ),
            "deduplicated_candidates": len(union_payloads),
            "regular_provider_logical_calls": sum(
                row.completion.provider_logical_call_count for row in rounds
            ),
            "center_completion_provider_logical_calls": center_completion_summary[
                "provider_logical_call_count"
            ],
            "center_completion_calls": center_completion_summary[
                "scheduled_completion_call_count"
            ],
        },
        center_completion=center_completion_summary,
        admitted_canonical_relation_core_identities=tuple(
            identity
            for round_lineage in rounds
            for identity in round_lineage.union_provenance.admitted_canonical_relation_core_identities
        ) + (
            completion_lineage.union_provenance.admitted_canonical_relation_core_identities
            if completion_lineage is not None
            else ()
        ),
    )

    union_root = target / "union"
    union_root.mkdir(parents=True)
    plan_path = target / "proposal_round_union_plan.json"
    candidate_path = union_root / "candidate_set.json"
    provenance_path = union_root / "union_provenance.json"
    _atomic_json(plan_path, plan_summary)
    _atomic_write(candidate_path, candidate_set.canonical_bytes())
    _atomic_json(provenance_path, provenance.model_dump(mode="json"))
    completion = ProposalRunCompletion(
        status="complete",
        plan_file_sha256=_sha256_file(plan_path),
        plan_sha256=plan_sha,
        input_freeze_manifest_sha256=frozen.manifest_raw_sha256,
        scheduled_call_count=len(call_ids),
        completed_call_count=len(call_ids),
        call_completion_sha256=call_completions,
        union_candidate_set_sha256=candidate_set.canonical_sha256(),
        union_provenance_sha256=canonical_sha256(provenance.model_dump(mode="json")),
        union_candidate_set_file_sha256=_sha256_file(candidate_path),
        union_provenance_file_sha256=_sha256_file(provenance_path),
        provider_logical_call_count=sum(
            row.completion.provider_logical_call_count for row in rounds
        ) + center_completion_summary["provider_logical_call_count"],
        provider_concurrency_planned=max(
            (
                *(row.completion.provider_concurrency_planned for row in rounds),
                *(
                    (completion_lineage.completion.provider_concurrency_planned,)
                    if completion_lineage is not None
                    else ()
                ),
            )
        ),
        provider_concurrency_actual_max=max(
            (
                *(row.completion.provider_concurrency_actual_max for row in rounds),
                *(
                    (completion_lineage.completion.provider_concurrency_actual_max,)
                    if completion_lineage is not None
                    else ()
                ),
            )
        ),
        raw_proposed_count=raw_count,
        valid_admitted_count=len(union_payloads),
        invalid_rejected_count=invalid_count,
        deduplicated_count=deduplicated_count,
    )
    completion_path = target / "proposal_run_completion.json"
    _atomic_json(completion_path, completion.model_dump(mode="json"))
    return V2ProposalRunLineage(
        frozen_input=frozen,
        plan=rounds[0].plan,
        plan_sha256=plan_sha,
        candidate_set=candidate_set,
        union_provenance=provenance,
        completion=completion,
        run_root=target,
        completion_raw_sha256=_sha256_file(completion_path),
        raw_response_sha256=raw_responses,
        call_provenance_sha256=call_provenance,
    )


def _load_dynamic_v2_proposal_run_lineage(
    *,
    run_root: Path,
    frozen: V2FrozenInput,
    completion_sha256: str,
) -> V2ProposalRunLineage:
    root = run_root.resolve(strict=True)
    completion_path = root / "proposal_run_completion.json"
    if _sha256_file(completion_path) != completion_sha256:
        raise ValueError("proposal run completion raw SHA-256 mismatch")
    completion = ProposalRunCompletion.model_validate_json(
        completion_path.read_bytes(), strict=True
    )
    if completion.status != "complete":
        raise ValueError("M11 accepts only a complete proposal run")
    plan_path = root / "proposal_run_plan.json"
    if _sha256_file(plan_path) != completion.plan_file_sha256:
        raise ValueError("proposal run plan raw SHA-256 mismatch")
    plan = ProposalRunPlan.model_validate_json(plan_path.read_bytes(), strict=True)
    _validate_plan_against_input(plan, frozen)
    plan_sha = canonical_sha256(plan.model_dump(mode="json"))
    if plan_sha != completion.plan_sha256:
        raise ValueError("proposal run plan canonical SHA-256 mismatch")
    union_provenance_path = root / "union" / "union_provenance.json"
    if _sha256_file(union_provenance_path) != completion.union_provenance_file_sha256:
        raise ValueError("proposal union provenance raw-file SHA-256 mismatch")
    union_provenance = ProposalUnionProvenance.model_validate_json(
        union_provenance_path.read_bytes(), strict=True
    )
    if canonical_sha256(
        union_provenance.model_dump(mode="json")
    ) != completion.union_provenance_sha256:
        raise ValueError("proposal terminal/union provenance SHA-256 mismatch")
    resolved_specs = tuple(
        ProposalCallSpec.model_validate(
            {
                **row,
                **(
                    {"evidence_card_ids": tuple(row["evidence_card_ids"])}
                    if "evidence_card_ids" in row
                    else {}
                ),
            },
            strict=True,
        )
        for row in union_provenance.resolved_calls
    )
    completion_mode = bool(
        plan.calls and plan.calls[0].proposal_round == "center_completion"
    )
    if resolved_specs[: len(plan.calls)] != plan.calls:
        raise ValueError("dynamic proposal lineage changed the frozen calls")

    normalized_decisions: list[dict[str, Any]] = []
    call_provenance_hashes: dict[str, str] = {}
    raw_response_hashes: dict[str, str] = {}
    all_payloads: list[dict[str, Any]] = []
    all_plans: list[dict[str, Any]] = []
    admitted_core_identities: list[str] = []
    raw_count = 0
    invalid_count = 0
    within_dedup = 0
    actual_models: set[str] = set()
    if completion_mode:
        derived = _completion_regions_for_plan(frozen, plan)
    else:
        for spec in plan.calls:
            rendered = _proposal_call_input(frozen, spec).rendered_input
            call_root = root / "calls" / spec.call_id
            stored_rendered = RenderedCandidateInput.model_validate_json(
                (call_root / "rendered_candidate_input.json").read_bytes(), strict=True
            )
            if stored_rendered != rendered:
                raise ValueError("scan rendered input does not reconstruct")
            raw_path = call_root / "provider_response_envelope.json"
            raw = _read_json(raw_path)
            _reject_secret_material(raw)
            response = _response_from_raw(raw)
            _validate_response_metadata(
                response, spec, plan, allow_historical_timestamp=True
            )
            actual_models.add(
                response.model
                if plan.actual_model_policy == "exact"
                else _provider_model_family(response.model)
            )
            parsed = _parse_scan_response(response.content)
            normalized = _normalize_scan_decisions(
                parsed,
                batch_payload=_scan_batch_payload(
                    frozen.lineage.view,
                    spec.evidence_card_ids,
                    batch_id=spec.call_id,
                ),
                view=frozen.lineage.view,
            )
            report = _read_json(call_root / "candidate_validation_report.json")
            if report.get("scan_decisions") != list(normalized):
                raise ValueError("scan decisions do not reconstruct")
            normalized_decisions.extend(normalized)

        derived = (
            derive_detail_regions(
                frozen,
                normalized_decisions=tuple(normalized_decisions),
                first_call_order=len(plan.calls) + 1,
                detail_max_requests=plan.detail_max_requests,
                detail_max_rendered_utf8_bytes=plan.detail_max_rendered_utf8_bytes,
                call_prototype=plan.calls[0],
            )
            if plan.calls
            else ()
        )
    expected_regions = tuple(region for region, _ in derived)
    expected_detail_specs = tuple(spec for _, spec in derived)
    observed_detail_specs = (
        resolved_specs if completion_mode else resolved_specs[len(plan.calls):]
    )
    if observed_detail_specs != expected_detail_specs:
        raise ValueError("dynamic detail call schedule does not reconstruct")
    if tuple(
        region.model_dump(mode="json") for region in expected_regions
    ) != union_provenance.detail_regions:
        raise ValueError("dynamic detail regions do not reconstruct")

    region_by_call = {spec.call_id: region for region, spec in derived}
    for spec in resolved_specs:
        call_root = root / "calls" / spec.call_id
        completion_path = call_root / "call_completion.json"
        if _sha256_file(completion_path) != completion.call_completion_sha256.get(spec.call_id):
            raise ValueError("proposal call completion raw SHA-256 mismatch")
        provenance_path = call_root / "call_provenance.json"
        provenance = ProposalCallProvenance.model_validate_json(
            provenance_path.read_bytes(), strict=True
        )
        provenance_sha = canonical_sha256(provenance.model_dump(mode="json"))
        if provenance_sha != union_provenance.call_provenance_sha256.get(spec.call_id):
            raise ValueError("proposal call provenance closure mismatch")
        raw_path = call_root / "provider_response_envelope.json"
        if _sha256_file(raw_path) != union_provenance.raw_response_file_sha256.get(spec.call_id):
            raise ValueError("proposal raw-response closure mismatch")
        call_provenance_hashes[spec.call_id] = provenance_sha
        raw_response_hashes[spec.call_id] = _sha256_file(raw_path)
        response = _response_from_raw(_read_json(raw_path))
        _validate_response_metadata(
            response, spec, plan, allow_historical_timestamp=True
        )
        if (
            provenance.model != response.model
            or provenance.reasoning_effort != response.reasoning_effort
        ):
            raise ValueError("proposal provenance model configuration differs from raw response")
        actual_models.add(
            response.model
            if plan.actual_model_policy == "exact"
            else _provider_model_family(response.model)
        )
        if spec.proposal_round == "global_scan":
            continue
        region = region_by_call[spec.call_id]
        rendered = (
            _render_center_completion_input(frozen, region)
            if completion_mode
            else _render_detail_input(frozen, region)
        )
        stored_rendered = RenderedCandidateInput.model_validate_json(
            (call_root / "rendered_candidate_input.json").read_bytes(), strict=True
        )
        if stored_rendered != rendered:
            raise ValueError("detail rendered input does not reconstruct")
        parsed = _parse_response(response.content)
        execution_kinds, execution_evidence = _request_execution_attributes(frozen)
        batch = _validate_candidate_batch(
            parsed,
            frozen.lineage.view,
            detail_region_id=region.region_id,
            visible_request_refs=set(region.visible_request_refs),
            visible_action_ids=set(region.visible_action_ids),
            visible_evidence_refs=set(region.visible_evidence_refs),
            request_execution_kinds=execution_kinds,
            request_execution_evidence=execution_evidence,
            observer_operation_catalog=region.observer_operation_catalog,
            required_effect_source_request_refs=(
                set(region.center_state_change_request_refs)
                if completion_mode
                else None
            ),
            required_query_pair=(
                (
                    str(region.boundary["source_request_ref"]),
                    str(region.boundary["followup_request_ref"]),
                )
                if region.boundary.get("query_relation_kind")
                else None
            ),
        )
        if _read_json(call_root / "candidate_validation_report.json") != batch.report:
            raise ValueError("detail candidate validation does not reconstruct")
        raw_count += batch.report["raw_proposed_count"]
        invalid_count += batch.report["invalid_rejected_count"]
        within_dedup += batch.report["deduplicated_count"]
        admitted_core_identities.extend(
            str(row["canonical_relation_core_identity"])
            for row in batch.report["candidates"]
            if row["disposition"] in {"admitted", "deduplicated"}
        )
        all_payloads.extend(batch.payloads)
        all_plans.extend(batch.constructed_execution_plans)

    if len(actual_models) != (1 if resolved_specs else 0):
        raise ValueError("proposal run contains inconsistent provider actual models")
    union_path = root / "union" / "candidate_set.json"
    if _sha256_file(union_path) != completion.union_candidate_set_file_sha256:
        raise ValueError("proposal union CandidateSet raw-file SHA-256 mismatch")
    union_lineage = load_v2_candidate_lineage(
        candidate_set_path=union_path,
        package_path=frozen.artifact_paths["package"],
        view_path=frozen.artifact_paths["view"],
        rendered_input_path=root / "union" / "rendered_candidate_input.json",
    )
    expected_payloads = _deduplicate_payloads(all_payloads)
    observed_payloads = [
        {
            key: value for key, value in record.payload.items()
            if key not in {"schema_version", "candidate_id"}
        }
        for record in union_lineage.candidate_set.candidates
    ]
    if observed_payloads != expected_payloads:
        raise ValueError("dynamic proposal union does not reconstruct")
    expected_plans_by_id = {str(row["plan_id"]): row for row in all_plans}
    expected_plan_ids = {
        str(row["observation_opportunity_ref"]) for row in expected_payloads
    }
    expected_plans = tuple(
        expected_plans_by_id[plan_id] for plan_id in sorted(expected_plan_ids)
    )
    if union_provenance.constructed_execution_plans != expected_plans:
        raise ValueError("dynamic constructed execution plans do not reconstruct")
    dedup_count = within_dedup + len(all_payloads) - len(expected_payloads)
    if (
        union_provenance.raw_proposed_count,
        union_provenance.valid_admitted_count,
        union_provenance.invalid_rejected_count,
        union_provenance.deduplicated_count,
    ) != (raw_count, len(expected_payloads), invalid_count, dedup_count):
        raise ValueError("dynamic proposal counts do not reconstruct")
    if tuple(admitted_core_identities) != (
        union_provenance.admitted_canonical_relation_core_identities
    ):
        raise ValueError("dynamic proposal canonical relation-core occurrences do not reconstruct")
    if set(completion.call_completion_sha256) != {
        spec.call_id for spec in resolved_specs
    }:
        raise ValueError("dynamic completion does not close every resolved call")
    return V2ProposalRunLineage(
        frozen_input=frozen,
        plan=plan,
        plan_sha256=plan_sha,
        candidate_set=union_lineage.candidate_set,
        union_provenance=union_provenance,
        completion=completion,
        run_root=root,
        completion_raw_sha256=completion_sha256,
        raw_response_sha256=raw_response_hashes,
        call_provenance_sha256=call_provenance_hashes,
    )


def _union_first_round_plan(frozen: V2FrozenInput) -> ProposalRunPlan:
    """Reconstruct the frozen scan plan referenced by a round union."""

    schedule_ref = frozen.manifest.sources.get("proposal_schedule")
    if not isinstance(schedule_ref, dict) or set(schedule_ref) != {"path", "sha256"}:
        raise ValueError("proposal round union lacks its frozen proposal schedule")
    relative = Path(str(schedule_ref["path"]))
    expected_sha = schedule_ref["sha256"]
    source_root = frozen.manifest_path.parent.parent.resolve(strict=True)
    if (
        relative.is_absolute()
        or relative == Path(".")
        or ".." in relative.parts
        or not isinstance(expected_sha, str)
        or not re.fullmatch(_SHA, expected_sha)
    ):
        raise ValueError("proposal round union has an invalid proposal schedule ref")
    schedule_path = (source_root / relative).resolve(strict=True)
    if (
        not schedule_path.is_file()
        or not schedule_path.is_relative_to(source_root)
        or schedule_path.is_symlink()
        or _sha256_file(schedule_path) != expected_sha
    ):
        raise ValueError("proposal round union proposal schedule differs from its pin")
    schedule = _read_json(schedule_path)
    if not isinstance(schedule, dict) or set(schedule) not in (
        {
            "schema_version", "plan_id", "frozen_at", "normal_runs",
            "provider", "policy",
        },
        {
            "schema_version", "plan_id", "frozen_at", "normal_runs",
            "provider", "policy", "responses",
        },
    ):
        raise ValueError("proposal round union proposal schedule shape mismatch")
    if (
        schedule.get("schema_version") != "uisemtest-current-provider-config-v1"
        or schedule.get("frozen_at") != frozen.manifest.frozen_at
        or schedule.get("normal_runs") != 1
        or isinstance(schedule.get("normal_runs"), bool)
    ):
        raise ValueError("proposal round union proposal schedule is not current")
    policy = schedule.get("policy")
    policy_fields = {
        "model", "temperature", "retry_limit", "endpoint_shape",
        "endpoint_host", "actual_model_policy",
    }
    if not isinstance(policy, dict) or set(policy) not in (
        policy_fields, policy_fields | {"reasoning_effort"}
    ):
        raise ValueError("proposal round union policy shape mismatch")
    temperature = policy["temperature"]
    retry_limit = policy["retry_limit"]
    actual_model_policy = policy["actual_model_policy"]
    if (
        not isinstance(temperature, (int, float))
        or isinstance(temperature, bool)
        or not math.isfinite(float(temperature))
        or not isinstance(retry_limit, int)
        or isinstance(retry_limit, bool)
        or actual_model_policy not in {"exact", "consistent"}
    ):
        raise ValueError("proposal round union policy values are invalid")
    batches = global_scan_batches(frozen.lineage.view)
    soft_overflows = scan_soft_overflow_bytes(frozen.lineage.view, batches)
    calls = tuple(
        ProposalCallSpec(
            call_id=f"global-scan-{index:04d}",
            call_order=index,
            model=policy["model"],
            reasoning_effort=policy.get("reasoning_effort"),
            temperature=float(temperature),
            retry_limit=retry_limit,
            endpoint_shape=policy["endpoint_shape"],
            endpoint_host=policy["endpoint_host"],
            stratum="business",
            proposal_round="global_scan",
            evidence_card_ids=card_ids,
            scan_soft_overflow_utf8_bytes=soft_overflows.get(index - 1),
        )
        for index, card_ids in enumerate(batches, start=1)
    )
    plan = build_proposal_run_plan(
        frozen,
        plan_id=schedule["plan_id"],
        frozen_at=schedule["frozen_at"],
        calls=calls,
        actual_model_policy=actual_model_policy,
    )
    _validate_plan_against_input(plan, frozen)
    return plan


def _load_union_v2_proposal_run_lineage(
    *,
    run_root: Path,
    frozen: V2FrozenInput,
    completion_sha256: str,
) -> V2ProposalRunLineage:
    """Load the sole current N-round M10 union without replaying provider calls."""

    root = run_root.resolve(strict=True)
    completion_path = root / "proposal_run_completion.json"
    if _sha256_file(completion_path) != completion_sha256:
        raise ValueError("proposal run completion raw SHA-256 mismatch")
    completion = ProposalRunCompletion.model_validate_json(
        completion_path.read_bytes(), strict=True
    )
    if completion.status != "complete":
        raise ValueError("M11 accepts only a complete proposal run")

    plan_path = root / "proposal_round_union_plan.json"
    if _sha256_file(plan_path) != completion.plan_file_sha256:
        raise ValueError("proposal round union plan raw SHA-256 mismatch")
    plan_summary = _read_json(plan_path)
    if not isinstance(plan_summary, dict) or set(plan_summary) != {
        "schema_version", "mode", "round_count", "round_plan_sha256",
        "round_completion_sha256", "center_completion",
    }:
        raise ValueError("proposal round union plan shape mismatch")
    round_count = plan_summary.get("round_count")
    round_plan_hashes = plan_summary.get("round_plan_sha256")
    round_completion_hashes = plan_summary.get("round_completion_sha256")
    center_completion_summary = plan_summary.get("center_completion")
    if (
        plan_summary.get("schema_version")
        != "uisemtest-m10-proposal-round-union-plan-v2"
        or plan_summary.get("mode") != "union"
        or not isinstance(round_count, int)
        or isinstance(round_count, bool)
        or round_count < 1
        or not isinstance(round_plan_hashes, list)
        or not isinstance(round_completion_hashes, list)
        or len(round_plan_hashes) != round_count
        or len(round_completion_hashes) != round_count
        or any(not isinstance(value, str) or not re.fullmatch(_SHA, value) for value in (
            *round_plan_hashes, *round_completion_hashes
        ))
        or not isinstance(center_completion_summary, dict)
    ):
        raise ValueError("proposal round union plan values are invalid")
    plan_sha = canonical_sha256(plan_summary)
    if plan_sha != completion.plan_sha256:
        raise ValueError("proposal round union plan canonical SHA-256 mismatch")

    provenance_path = root / "union" / "union_provenance.json"
    if _sha256_file(provenance_path) != completion.union_provenance_file_sha256:
        raise ValueError("proposal union provenance raw-file SHA-256 mismatch")
    provenance = ProposalUnionProvenance.model_validate_json(
        provenance_path.read_bytes(), strict=True
    )
    if canonical_sha256(
        provenance.model_dump(mode="json")
    ) != completion.union_provenance_sha256:
        raise ValueError("proposal terminal/union provenance SHA-256 mismatch")
    if (
        provenance.plan_sha256 != plan_sha
        or provenance.input_freeze_manifest_sha256 != frozen.manifest_raw_sha256
        or completion.input_freeze_manifest_sha256 != frozen.manifest_raw_sha256
    ):
        raise ValueError("proposal round union does not close its plan and M9 input")

    plan = _union_first_round_plan(frozen)
    if canonical_sha256(plan.model_dump(mode="json")) != round_plan_hashes[0]:
        raise ValueError("proposal round union first plan does not reconstruct")
    if provenance.plan_scientific_sha256 != canonical_sha256(
        [plan.scientific_sha256()] * round_count
    ):
        raise ValueError("proposal round union scientific plan does not reconstruct")

    completion_run_sha = center_completion_summary.get("completion_run_sha256")
    if completion_run_sha is not None and (
        not isinstance(completion_run_sha, str)
        or not re.fullmatch(_SHA, completion_run_sha)
    ):
        raise ValueError("center completion run SHA-256 is invalid")
    completion_lineage = (
        _load_dynamic_v2_proposal_run_lineage(
            run_root=root / "center_completion",
            frozen=frozen,
            completion_sha256=completion_run_sha,
        )
        if completion_run_sha is not None
        else None
    )
    if (root / "center_completion").exists() != (completion_lineage is not None):
        raise ValueError("center completion artifacts differ from the union plan")
    if provenance.center_completion != center_completion_summary:
        raise ValueError("center completion summary differs from union provenance")

    specs_by_round: dict[int, list[ProposalCallSpec]] = {
        index: [] for index in range(1, round_count + 1)
    }
    completion_specs: list[ProposalCallSpec] = []
    observed_round_order: list[int] = []
    for raw_spec in provenance.resolved_calls:
        row = copy.deepcopy(raw_spec)
        sample_round = row.pop("sample_round", None)
        if sample_round == "center_completion":
            completion_specs.append(
                ProposalCallSpec.model_validate_json(
                    canonical_json_bytes(row), strict=True
                )
            )
            continue
        if sample_round not in specs_by_round:
            raise ValueError("proposal union call has an invalid sample round")
        observed_round_order.append(sample_round)
        specs_by_round[sample_round].append(
            ProposalCallSpec.model_validate_json(
                canonical_json_bytes(row), strict=True
            )
        )
    if observed_round_order != sorted(observed_round_order):
        raise ValueError("proposal union calls are not grouped by sample round")
    for sample_round, specs in specs_by_round.items():
        if [spec.call_order for spec in specs] != list(range(1, len(specs) + 1)):
            raise ValueError("proposal union round calls are not contiguous")
        if tuple(specs[: len(plan.calls)]) != plan.calls:
            raise ValueError("proposal union round changed the frozen scan calls")
        if any(spec.proposal_round != "detail_proposal" for spec in specs[len(plan.calls):]):
            raise ValueError("proposal union contains a non-detail dynamic call")

    regions_by_round: dict[int, list[DetailRegion]] = {
        index: [] for index in range(1, round_count + 1)
    }
    completion_regions: list[DetailRegion] = []
    observed_region_round_order: list[int] = []
    for raw_region in provenance.detail_regions:
        row = copy.deepcopy(raw_region)
        sample_round = row.pop("sample_round", None)
        if sample_round == "center_completion":
            completion_regions.append(
                DetailRegion.model_validate_json(
                    canonical_json_bytes(row), strict=True
                )
            )
            continue
        if sample_round not in regions_by_round:
            raise ValueError("proposal union detail region has an invalid sample round")
        observed_region_round_order.append(sample_round)
        regions_by_round[sample_round].append(
            DetailRegion.model_validate_json(canonical_json_bytes(row), strict=True)
        )
    if observed_region_round_order != sorted(observed_region_round_order):
        raise ValueError("proposal union regions are not grouped by sample round")
    expected_call_ids: list[str] = []
    for sample_round in range(1, round_count + 1):
        specs = specs_by_round[sample_round]
        detail_specs = specs[len(plan.calls):]
        regions = regions_by_round[sample_round]
        if tuple(spec.detail_region_id for spec in detail_specs) != tuple(
            region.region_id for region in regions
        ):
            raise ValueError("proposal union detail calls and regions differ")
        expected_call_ids.extend(
            f"round-{sample_round:04d}:{spec.call_id}" for spec in specs
        )
    if completion_lineage is None:
        if completion_specs or completion_regions:
            raise ValueError("unexecuted center completion has call artifacts")
    else:
        expected_completion_specs = tuple(
            ProposalCallSpec.model_validate_json(
                canonical_json_bytes(spec), strict=True
            )
            for spec in completion_lineage.union_provenance.resolved_calls
        )
        expected_completion_regions = tuple(
            DetailRegion.model_validate_json(
                canonical_json_bytes(region), strict=True
            )
            for region in completion_lineage.union_provenance.detail_regions
        )
        if (
            tuple(completion_specs) != expected_completion_specs
            or tuple(completion_regions) != expected_completion_regions
        ):
            raise ValueError("center completion call tree does not reconstruct")
        expected_call_ids.extend(
            f"center-completion:{spec.call_id}"
            for spec in expected_completion_specs
        )
    if tuple(expected_call_ids) != provenance.call_ids or set(expected_call_ids) != set(
        completion.call_completion_sha256
    ):
        raise ValueError("proposal round union call closure mismatch")

    candidate_path = root / "union" / "candidate_set.json"
    if _sha256_file(candidate_path) != completion.union_candidate_set_file_sha256:
        raise ValueError("proposal union CandidateSet raw-file SHA-256 mismatch")
    candidate_set = CandidateSet.model_validate_json(
        candidate_path.read_bytes(), strict=True
    )
    expected_rendered_ref = Path(os.path.relpath(
        frozen.artifact_paths["rendered"], candidate_path.parent
    )).as_posix()
    if (
        candidate_set.rendered_input_ref != expected_rendered_ref
        or candidate_set.preproposal_evidence_package_sha256
        != frozen.lineage.package.canonical_sha256()
        or candidate_set.proposal_evidence_view_sha256
        != frozen.lineage.view.canonical_sha256()
        or candidate_set.rendered_input_sha256
        != frozen.lineage.rendered_input.canonical_sha256()
    ):
        raise ValueError("proposal union CandidateSet input lineage does not close")
    if (
        candidate_set.canonical_sha256() != completion.union_candidate_set_sha256
        or candidate_set.canonical_sha256() != provenance.union_candidate_set_sha256
    ):
        raise ValueError("proposal union CandidateSet closure mismatch")
    expected_source_refs = (
        candidate_set.rendered_input_ref,
        *tuple(
            f"round:{index:04d}:{digest}"
            for index, digest in enumerate(round_completion_hashes, start=1)
        ),
        *(
            (f"center-completion:{completion_run_sha}",)
            if completion_run_sha is not None
            else ()
        ),
    )
    if candidate_set.source_refs != expected_source_refs:
        raise ValueError("proposal union CandidateSet round sources differ from its plan")
    if completion_lineage is not None and candidate_set.source_sha256.get(
        "center_completion_candidate_set"
    ) != completion_lineage.candidate_set.canonical_sha256():
        raise ValueError("proposal union completion candidate source differs")
    union_payloads = [
        {
            key: value for key, value in record.payload.items()
            if key not in {"schema_version", "candidate_id"}
        }
        for record in candidate_set.candidates
    ]
    if candidate_set.source_sha256.get("round_union_identity") != canonical_sha256(
        [_scientific_relation_payload(payload) for payload in union_payloads]
    ):
        raise ValueError("proposal union CandidateSet identity does not reconstruct")
    if (
        completion.scheduled_call_count != len(expected_call_ids)
        or completion.completed_call_count != len(expected_call_ids)
        or completion.call_completion_sha256.keys()
        != provenance.call_provenance_sha256.keys()
        or completion.call_completion_sha256.keys()
        != provenance.raw_response_file_sha256.keys()
        or (
            completion.raw_proposed_count,
            completion.valid_admitted_count,
            completion.invalid_rejected_count,
            completion.deduplicated_count,
        )
        != (
            provenance.raw_proposed_count,
            provenance.valid_admitted_count,
            provenance.invalid_rejected_count,
            provenance.deduplicated_count,
        )
        or completion.valid_admitted_count != len(candidate_set.candidates)
        or center_completion_summary.get("provider_logical_call_count") != (
            completion_lineage.completion.provider_logical_call_count
            if completion_lineage is not None
            else 0
        )
        or center_completion_summary.get("scheduled_completion_call_count") != (
            completion_lineage.completion.scheduled_call_count
            if completion_lineage is not None
            else 0
        )
        or center_completion_summary.get("provider_token_usage")
        != _provider_token_usage(completion_lineage)
    ):
        raise ValueError("proposal round union terminal counts do not close")
    return V2ProposalRunLineage(
        frozen_input=frozen,
        plan=plan,
        plan_sha256=plan_sha,
        candidate_set=candidate_set,
        union_provenance=provenance,
        completion=completion,
        run_root=root,
        completion_raw_sha256=completion_sha256,
        raw_response_sha256=dict(provenance.raw_response_file_sha256),
        call_provenance_sha256=dict(provenance.call_provenance_sha256),
    )


def load_v2_proposal_run_lineage(
    *,
    run_root: str | Path,
    input_freeze_manifest_path: str | Path,
    expected_input_manifest_sha256: str,
    expected_completion_sha256: str,
) -> V2ProposalRunLineage:
    """Load and reconstruct the sole current two-stage M10 lineage."""

    root = Path(run_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("proposal run root is not a directory")
    frozen = load_hardened_v2_input(
        input_freeze_manifest_path=input_freeze_manifest_path,
        expected_manifest_sha256=expected_input_manifest_sha256,
        require_current_revision=True,
    )
    dynamic_plan = root / "proposal_run_plan.json"
    union_plan = root / "proposal_round_union_plan.json"
    if dynamic_plan.is_file() == union_plan.is_file():
        raise ValueError("proposal run must contain exactly one current plan kind")
    loader = (
        _load_dynamic_v2_proposal_run_lineage
        if dynamic_plan.is_file()
        else _load_union_v2_proposal_run_lineage
    )
    return loader(
        run_root=root,
        frozen=frozen,
        completion_sha256=expected_completion_sha256,
    )


def _validate_plan_against_input(plan: ProposalRunPlan, frozen: V2FrozenInput) -> None:
    lineage = frozen.lineage
    expected = (
        frozen.manifest_raw_sha256,
        canonical_v2_template_sha256(),
        lineage.package.canonical_sha256(),
        lineage.view.canonical_sha256(),
        lineage.rendered_input.canonical_sha256(),
        lineage.rendered_input.rendered_sha256,
    )
    observed = (
        plan.input_freeze_manifest_sha256,
        plan.template_sha256,
        plan.package_sha256,
        plan.view_sha256,
        plan.rendered_input_sha256,
        plan.rendered_text_sha256,
    )
    if observed != expected:
        raise ValueError("proposal run plan does not close over the current frozen input")
    if plan.scan_template_sha256 != canonical_scan_template_sha256():
        raise ValueError("proposal run plan does not bind the current scan template")
    available = {card.card_id for card in lineage.view.evidence_cards}
    completion_mode = bool(
        plan.calls and plan.calls[0].proposal_round == "center_completion"
    )
    if completion_mode:
        _completion_regions_for_plan(frozen, plan)
        if any(spec.retry_limit != 3 for spec in plan.calls):
            raise ValueError("center-completion transport retry_limit must remain 3")
        return
    expected_batches = global_scan_batches(
        lineage.view,
        max_primary_cards=plan.scan_max_primary_cards,
        max_rendered_utf8_bytes=plan.scan_max_rendered_utf8_bytes,
        max_single_primary_rendered_utf8_bytes=(
            plan.scan_max_single_primary_rendered_utf8_bytes
        ),
    )
    observed_batches = tuple(spec.evidence_card_ids for spec in plan.calls)
    if observed_batches != expected_batches:
        raise ValueError("proposal scan schedule does not close the M9 atomic universe")
    expected_soft_overflows = scan_soft_overflow_bytes(
        lineage.view,
        expected_batches,
        max_rendered_utf8_bytes=plan.scan_max_rendered_utf8_bytes,
        max_single_primary_rendered_utf8_bytes=(
            plan.scan_max_single_primary_rendered_utf8_bytes
        ),
    )
    for index, spec in enumerate(plan.calls):
        if spec.scan_soft_overflow_utf8_bytes != expected_soft_overflows.get(index):
            raise ValueError("proposal scan soft-overflow record differs from rendered input")
    for spec in plan.calls:
        unavailable = set(spec.evidence_card_ids) - available
        if unavailable:
            raise ValueError(
                "proposal call evidence-card scope is outside the frozen view: "
                + ", ".join(sorted(unavailable))
            )


def _validate_response_metadata(
    response: RenderedProposalResponse,
    spec: ProposalCallSpec,
    plan: ProposalRunPlan,
    *,
    allow_historical_timestamp: bool = False,
) -> None:
    if not isinstance(response, RenderedProposalResponse):
        raise ValueError("rendered provider returned an untyped response")
    if response.raw_envelope is None or not isinstance(response.raw_envelope, dict):
        raise ValueError("current rendered provider response requires an exact raw envelope")
    if not isinstance(response.model, str) or not response.model.strip():
        raise ValueError("provider response lacks its actual model")
    if (
        (plan.actual_model_policy == "exact" and response.model != spec.model)
        or (
            plan.actual_model_policy == "consistent"
            and _provider_model_family(response.model)
            != _provider_model_family(spec.model)
        )
        or response.endpoint_shape != spec.endpoint_shape
        or response.endpoint_host != spec.endpoint_host
        or response.temperature != spec.temperature
        or response.reasoning_effort != spec.reasoning_effort
        or response.retry_count < 0
        or response.retry_count > spec.retry_limit
    ):
        raise ValueError("provider response metadata does not match the frozen call spec")
    if (
        not allow_historical_timestamp
        and _timestamp(response.response_received_at) < _timestamp(plan.frozen_at)
    ):
        raise ValueError("provider response timestamp predates the frozen run plan")
    _reject_secret_material(response.raw_envelope)


def _candidate_set(
    payloads: list[dict[str, Any]],
    *,
    frozen: V2FrozenInput,
    seed_label: str,
    rendered_ref: str,
    actual_rendered_input: RenderedCandidateInput | None = None,
    evidence_view: ProposalEvidenceView | None = None,
) -> CandidateSet:
    records = tuple(
        CandidateRecord(
            candidate_id=candidate_id,
            scientific_input_version=SCIENTIFIC_INPUT_VERSION,
            payload=normalized,
            payload_sha256=canonical_sha256(normalized),
        )
        for index, payload in enumerate(payloads, start=1)
        for candidate_id in (f"v2-candidate-{index:04d}",)
        for normalized in ({
            "schema_version": "uisemtest-oracle-candidate-v1",
            "candidate_id": candidate_id,
            **payload,
        },)
    )
    lineage = frozen.lineage
    view = evidence_view or lineage.view
    rendered_input = actual_rendered_input or lineage.rendered_input
    seed = canonical_sha256({
        "package": lineage.package.canonical_sha256(),
        "view": view.canonical_sha256(),
        "rendered": rendered_input.canonical_sha256(),
        "response": seed_label,
    })
    source_refs = [rendered_ref]
    source_sha256 = {
        "preproposal_evidence_package": lineage.package.canonical_sha256(),
        "proposal_evidence_view": view.canonical_sha256(),
        "rendered_candidate_input": rendered_input.canonical_sha256(),
        "canonical_template": rendered_input.template_sha256,
        "canonical_candidate_payload_sequence": canonical_sha256(payloads),
    }
    return CandidateSet(
        candidate_set_id=f"v2-candidate-set-{seed[:24]}",
        scientific_input_version=SCIENTIFIC_INPUT_VERSION,
        candidates=records,
        preproposal_evidence_package_sha256=lineage.package.canonical_sha256(),
        proposal_evidence_view_sha256=view.canonical_sha256(),
        rendered_input_ref=rendered_ref,
        rendered_input_sha256=rendered_input.canonical_sha256(),
        source_refs=tuple(dict.fromkeys(source_refs)),
        source_sha256=source_sha256,
    )


def _deduplicate_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for payload in payloads:
        digest = canonical_sha256(_scientific_relation_payload(payload))
        if digest not in seen:
            seen.add(digest)
            result.append(payload)
    return result


def load_sealed_rendered_proposal_response(
    path: str | Path, *, expected_file_sha256: str
) -> RenderedProposalResponse:
    """Load one already-persisted response through the current raw-envelope parser."""

    source = Path(path).resolve(strict=True)
    if not source.is_file() or _sha256_file(source) != expected_file_sha256:
        raise ValueError("sealed provider response file SHA-256 mismatch")
    raw = _read_json(source)
    _reject_secret_material(raw)
    return _response_from_raw(raw)


def _response_from_raw(raw: dict[str, Any]) -> RenderedProposalResponse:
    fields = {
        "schema_version", "content", "raw_envelope", "model", "endpoint_shape",
        "endpoint_host", "temperature", "retry_count", "response_received_at",
    }
    if set(raw) not in (fields, fields | {"reasoning_effort"}) or raw.get("schema_version") != "uisemtest-v2-raw-response-v1":
        raise ValueError("proposal raw response envelope shape mismatch")
    return RenderedProposalResponse(
        content=raw["content"],
        raw_envelope=raw["raw_envelope"],
        model=raw["model"],
        reasoning_effort=raw.get("reasoning_effort"),
        endpoint_shape=raw["endpoint_shape"],
        endpoint_host=raw["endpoint_host"],
        temperature=raw["temperature"],
        retry_count=raw["retry_count"],
        response_received_at=raw["response_received_at"],
    )


def _reject_secret_material(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _SECRET_KEYS:
                raise ValueError("proposal artifacts cannot persist credential-bearing fields")
            _reject_secret_material(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_material(child)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _copy_exact(source: Path, target: Path) -> None:
    _atomic_write(target, source.read_bytes())


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value
