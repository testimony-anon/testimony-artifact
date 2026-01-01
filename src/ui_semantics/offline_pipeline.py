"""The canonical offline UISemTest method pipeline.

Every function in this module is deterministic over explicit frozen inputs.
The module implements no target lifecycle or transport; canonical local runs
may inject the bounded Stage2.5 runner after starting their shared runtime.
Subject-specific URL and session semantics enter only through callable/data
parameters.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from .artifact_relocation import attested_sha256
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from common.contracts import make_envelope
from stage2_5_probe.offline import build_audit_only_probe_results
from stage2_recover.assemble import recover_initial_oas
from stage2_recover.loader import LoadedBundle, load_bundle, load_bundles
from stage3_gate.assemble import build_augmented_oas

from .contracts import (
    ActorBundleRef,
    CalibrationReport,
    CertifiedRelationTestSuite,
    DependencyGraph,
    EvidenceBundle,
    EvidenceChannel,
    ObservationalApiStructure,
    ObservedValueFlowSet,
    ProducerApplicability,
    ProducerRecord,
    RecordingBundle,
    RouteSCertificate,
    TransferEvidenceRecord,
    UiDiffEvidenceRecord,
    UiTestAssertionPopulationManifest,
    UiTestAssertionSelectionManifest,
    UiApiTrace,
)
from .current_route_s import canonical_json_bytes, canonical_sha256
from .trace_builder import build_ui_trace_from_bundles


WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
READ_METHODS = frozenset({"GET", "HEAD"})
SETUP_DOMAIN_POLICY = "complete_bounded_global_recorded_prefix_v1"
SETUP_DOMAIN_MAX_REQUESTS = 256
UrlNormalizer = Callable[[str], str]
ActiveProbeRunner = Callable[
    [dict[str, Any], Sequence[LoadedBundle], str],
    dict[str, Any],
]
SessionEndpointMap = Mapping[str, tuple[str, str]]
# actor_id -> the exact (METHOD, path) pairs the profile declares as session
# maintenance (credential refresh). Empty/absent means the former behaviour.
SessionMaintenanceEndpointMap = Mapping[str, frozenset[tuple[str, str]]]
SCIENTIFIC_WORKFLOW_ID = "recorded-workflow"


def declared_read_semantic_endpoints(profile: Any) -> frozenset[tuple[str, str]]:
    """Project the exact read-semantic method/path pairs a typed profile declares.

    Nothing is inferred from path wording. Profiles that declare none (Conduit,
    RWA, Umami, Paperless-ngx) produce an empty set, which makes every consumer
    of the declaration a no-op for them.
    """
    endpoints = getattr(profile, "read_semantic_endpoints", None) or ()
    return frozenset(
        (str(item.method).upper(), str(item.path)) for item in endpoints
    )


def declared_session_maintenance_endpoints(
    profile: Any,
) -> dict[str, frozenset[tuple[str, str]]]:
    """Project the exact actor-scoped session-maintenance endpoints of a typed profile.

    Only exact method/path pairs that the profile declares are returned; nothing is
    inferred from path wording. Profiles that declare no session_maintenance (Conduit,
    RWA) produce an empty map, which makes the maintenance exclusion a no-op for them.
    """
    result: dict[str, frozenset[tuple[str, str]]] = {}
    from stage0_launch.profile import actor_auth

    for actor_id in ["default", *(actor.actor_id for actor in profile.actors)]:
        endpoints = actor_auth(profile, actor_id).session_maintenance
        if not endpoints:
            continue
        result[actor_id] = frozenset(
            (str(item.method).upper(), str(item.path)) for item in endpoints
        )
    return result


def declared_session_transaction_endpoints(
    profile: Any,
) -> dict[str, frozenset[tuple[str, str]]]:
    """Project the actor-scoped identity probe and session teardown a profile declares.

    These are session transactions, not business writes: the identity probe exists to
    prove who the session belongs to, and the teardown ends it. Both are taken from the
    typed profile (``auth.probe_endpoint`` and ``auth.logout_endpoint``); nothing is
    inferred from path wording. An application whose probe is a GET (Conduit, RWA) is
    unaffected, because a read method never reaches the producer universe anyway.
    """
    result: dict[str, frozenset[tuple[str, str]]] = {}
    from stage0_launch.profile import actor_auth

    for actor_id in ["default", *(actor.actor_id for actor in profile.actors)]:
        auth = actor_auth(profile, actor_id)
        endpoints = set()
        for declared in (auth.probe_endpoint, auth.logout_endpoint):
            if declared is None:
                continue
            endpoints.add(
                (
                    str(declared.method).upper(),
                    urlsplit(str(declared.path)).path or "/",
                )
            )
        if endpoints:
            result[actor_id] = frozenset(endpoints)
    return result


def sha256_file(path: Path) -> str:
    return attested_sha256(path)


def recording_bundle(
    actor_bundle_dirs: Mapping[str, str | Path],
    *,
    recording_id: str,
    recording_root: str | Path,
) -> RecordingBundle:
    root = Path(recording_root).resolve(strict=True)
    workflow_result_path = root / "recording_workflow_result.json"
    workflow_result = json.loads(workflow_result_path.read_text(encoding="utf-8"))
    from common.contracts import validate_artifact

    validate_artifact("recording_workflow_result.schema.json", workflow_result)
    if workflow_result["status"] != "completed":
        raise ValueError("M2 rejects a non-completed recording workflow")
    declared = {
        str(item["actor_id"]): str(item["manifest_ref"])
        for item in workflow_result["actor_bundles"]
    }
    if len(declared) != len(workflow_result["actor_bundles"]):
        raise ValueError("completed workflow result contains duplicate actor bundles")
    if set(declared) != set(actor_bundle_dirs):
        raise ValueError("recording actor bundles differ from completed workflow result")
    actors = []
    source_sha256: dict[str, str] = {}
    for actor_id, raw_path in sorted(actor_bundle_dirs.items()):
        path = Path(raw_path).resolve(strict=True)
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError("recording actor bundle escapes the recording root") from exc
        if relative == Path("."):
            raise ValueError("recording actor bundle must be below the recording root")
        bundle = load_bundle(path)
        manifest_path = path / "manifest.json"
        expected_manifest = (root / declared[actor_id]).resolve(strict=True)
        if expected_manifest != manifest_path:
            raise ValueError("recording actor bundle path differs from workflow result")
        manifest_sha = sha256_file(manifest_path)
        source_sha256[(relative / "manifest.json").as_posix()] = manifest_sha
        actors.append(
            ActorBundleRef(
                actor_id=actor_id,
                run_id=bundle.run_id,
                path=relative.as_posix(),
                manifest_sha256=manifest_sha,
            )
        )
    return RecordingBundle(
        recording_id=recording_id,
        actors=tuple(actors),
        # The typed workflow ID is recording provenance and may encode suite/case
        # organization.  M1 needs only an opaque workflow identity; the exact
        # recording result remains pinned below by its source hash.
        workflow_id=SCIENTIFIC_WORKFLOW_ID,
        workflow_result_ref="recording_workflow_result.json",
        reset_epoch=str(workflow_result["reset_epoch"]["record_id"]),
        step_correspondence=tuple(workflow_result["step_correspondence"]),
        source_refs=tuple(item.path for item in actors),
        source_sha256={
            **source_sha256,
            "recording_workflow_result.json": sha256_file(workflow_result_path),
        },
    )


def build_trace(
    recording: RecordingBundle,
    *,
    recording_root: str | Path,
    trace_id: str,
    url_normalizer: UrlNormalizer | None = None,
    read_semantic_endpoints: frozenset[tuple[str, str]] | None = None,
) -> UiApiTrace:
    resolved = resolve_recording_bundle_paths(recording, recording_root)
    paths = {item.actor_id: resolved[item.actor_id] for item in recording.actors}
    trace = build_ui_trace_from_bundles(
        paths,
        run_id=trace_id,
        step_correspondence=recording.step_correspondence,
        url_normalizer=url_normalizer,
        read_semantic_endpoints=read_semantic_endpoints,
    )
    relative_by_run = {item.run_id: item.path for item in recording.actors}
    for actor in trace["actors"]:
        actor["session_bundle_ref"]["path"] = relative_by_run[
            str(actor["session_bundle_ref"]["run_id"])
        ]
    for source in trace["metadata"].get("upstream_refs", []):
        source["path"] = relative_by_run[str(source["run_id"])]
    _stabilize_envelope(trace["metadata"], trace_id)
    return UiApiTrace(
        trace_id=trace_id,
        trace=trace,
        event_count=len(trace["events"]),
        admitted_request_count=len(trace["api_requests"]),
        automatic_binding_count=len(trace["bindings"]),
        review_required_count=len(trace["binding_reviews"]),
        source_refs=(recording.canonical_sha256(),),
        source_sha256={"recording_bundle": recording.canonical_sha256()},
    )


def build_observational_structure(
    recording: RecordingBundle,
    *,
    recording_root: str | Path,
    structure_id: str,
    url_normalizer: UrlNormalizer | None = None,
    active_probe_runner: ActiveProbeRunner | None = None,
) -> tuple[ObservationalApiStructure, dict[str, Any]]:
    """Build Stage2, Stage2.5, and Stage3 entirely in memory."""
    resolved = resolve_recording_bundle_paths(recording, recording_root)
    bundles = load_bundles([resolved[item.actor_id] for item in recording.actors])
    if url_normalizer is not None:
        bundles = _normalized_bundles(bundles, url_normalizer)
    initial, warnings = recover_initial_oas(bundles)
    relative_by_run = {item.run_id: item.path for item in recording.actors}
    for source in initial["x-carverflow-meta"].get("upstream_refs", []):
        run_id = str(source.get("run_id") or "")
        if run_id in relative_by_run:
            source["path"] = relative_by_run[run_id]
    _stabilize_envelope(initial["x-carverflow-meta"], f"{structure_id}-stage2")
    probe_run_id = f"{structure_id}-stage2-5"
    probes = (
        build_audit_only_probe_results(
            initial,
            bundles,
            run_id=f"{probe_run_id}-audit-only",
        )
        if active_probe_runner is None
        else active_probe_runner(initial, bundles, probe_run_id)
    )
    for source in probes["metadata"].get("upstream_refs", []):
        run_id = str(source.get("run_id") or "")
        if run_id in relative_by_run:
            source["path"] = relative_by_run[run_id]
    _stabilize_envelope(probes["metadata"], probe_run_id)
    augmented = build_augmented_oas(initial, probes)
    _stabilize_envelope(augmented["x-carverflow-meta"], f"{structure_id}-stage3")
    active_http_probes = sum(
        item.get("execution_mode") != "not_executed"
        for item in probes.get("probes", [])
    )
    contract = ObservationalApiStructure(
        structure_id=structure_id,
        stage2_operation_count=_operation_count(initial),
        stage2_5_record_count=len(probes["probes"]),
        stage3_operation_count=_operation_count(augmented),
        initial_structure_sha256=canonical_sha256(initial),
        audit_only_probe_results_sha256=canonical_sha256(probes),
        augmented_structure_sha256=canonical_sha256(augmented),
        source_refs=tuple(item.path for item in recording.actors),
        source_sha256={"recording_bundle": recording.canonical_sha256()},
        audit_only=active_http_probes == 0,
        active_http_probes=active_http_probes,
    )
    return contract, {
        "initial_structure": initial,
        "audit_only_probe_results": probes,
        "augmented_structure": augmented,
        "warnings": warnings,
    }


def build_evidence_bundle(
    trace: UiApiTrace,
    recording: RecordingBundle,
    *,
    recording_root: str | Path,
    evidence_id: str,
    enabled_channels: Iterable[str] | None = None,
    transfer_selection_bytes: bytes | None = None,
    transfer_population_bytes: bytes | None = None,
) -> tuple[EvidenceBundle, dict[str, dict[str, Any]]]:
    enabled = (
        {"semantic", "ui-diff", "transfer"}
        if enabled_channels is None
        else set(enabled_channels)
    )
    unknown = enabled - {"semantic", "ui-diff", "transfer"}
    if unknown or "semantic" not in enabled:
        raise ValueError("enabled channels must include semantic and may include ui-diff/transfer")
    if (transfer_selection_bytes is None) != (transfer_population_bytes is None):
        raise ValueError("transfer selection and population raw bytes must be supplied together")
    if (
        transfer_selection_bytes is not None or transfer_population_bytes is not None
    ) and "transfer" not in enabled:
        raise ValueError("transfer selection/population supplied while the transfer channel is disabled")
    raw = trace.trace
    refs = _refs(raw)
    semantic_records = [
        {
            "record_id": "semantic-window-all",
            "ui_trace_ref": {
                "artifact_type": "ui_trace",
                "run_id": raw["metadata"]["run_id"],
                "path": "ui_trace.json",
            },
            "event_refs": [refs["event"][item["event_id"]] for item in raw["events"]],
            "request_refs": [refs["request"][item["request_ref"]] for item in raw["api_requests"]],
        }
    ]
    ui_diff_records = (
        _ui_diff_records(raw, recording, recording_root, refs)
        if "ui-diff" in enabled
        else []
    )
    (
        transfer_records,
        transfer_selection_ref,
        transfer_selection_sha256,
        transfer_population_ref,
        transfer_population_sha256,
    ) = (
        _transfer_records(
            raw,
            refs,
            transfer_selection_bytes,
            transfer_population_bytes,
        )
        if "transfer" in enabled
        else ([], None, None, None, None)
    )
    documents = {"semantic": _evidence_document(raw, "semantic_edges", semantic_records)}
    if "ui-diff" in enabled:
        documents["ui_diff"] = _evidence_document(raw, "ui_diff_assertions", ui_diff_records)
    if transfer_records:
        documents["transfer"] = _evidence_document(
            raw, "ui_assertion_transfer", transfer_records
        )
    channels = {
        "semantic": EvidenceChannel(
            status="available",
            reason="primary_observation_channel",
            records=tuple(semantic_records),
            artifact_sha256=canonical_sha256(documents["semantic"]),
        ),
        "ui_diff": (
            EvidenceChannel(
                status="available",
                reason="deterministic_write_then_read_windows",
                records=tuple(ui_diff_records),
                artifact_sha256=canonical_sha256(documents["ui_diff"]),
            )
            if ui_diff_records
            else EvidenceChannel(
                status="unavailable",
                reason=(
                    "no_deterministic_write_then_read_window"
                    if "ui-diff" in enabled
                    else "channel_not_requested"
                ),
            )
        ),
        "transfer": (
            EvidenceChannel(
                status="available",
                reason="independent_frozen_selection_supplied",
                records=tuple(transfer_records),
                artifact_sha256=canonical_sha256(documents["transfer"]),
            )
            if transfer_records
            else EvidenceChannel(
                status="unavailable",
                reason=(
                    "independent_frozen_selection_not_supplied"
                    if "transfer" in enabled
                    else "channel_not_requested"
                ),
            )
        ),
    }
    source_refs = [trace.canonical_sha256(), recording.canonical_sha256()]
    source_sha256 = {
        "ui_api_trace": trace.canonical_sha256(),
        "recording_bundle": recording.canonical_sha256(),
    }
    if transfer_selection_ref is not None and transfer_selection_sha256 is not None:
        source_refs.append(transfer_selection_ref)
        source_sha256["ui_test_assertion_selection_manifest"] = transfer_selection_sha256
    if transfer_population_ref is not None and transfer_population_sha256 is not None:
        source_refs.append(transfer_population_ref)
        source_sha256["ui_test_assertion_population_manifest"] = transfer_population_sha256
    return EvidenceBundle(
        evidence_id=evidence_id,
        trace_sha256=trace.canonical_sha256(),
        channels=channels,
        transfer_selection_ref=transfer_selection_ref,
        transfer_selection_sha256=transfer_selection_sha256,
        transfer_population_ref=transfer_population_ref,
        transfer_population_sha256=transfer_population_sha256,
        source_refs=tuple(source_refs),
        source_sha256=source_sha256,
    ), documents


def producer_applicability(
    trace: UiApiTrace,
    recording: RecordingBundle,
    *,
    recording_root: str | Path,
    applicability_id: str,
    session_endpoints: SessionEndpointMap | None = None,
    session_maintenance_endpoints: SessionMaintenanceEndpointMap | None = None,
    session_transaction_endpoints: SessionMaintenanceEndpointMap | None = None,
    read_semantic_endpoints: frozenset[tuple[str, str]] | None = None,
) -> ProducerApplicability:
    raw = trace.trace
    bundles = _bundles(recording, recording_root)
    session_endpoints = session_endpoints or {}
    session_maintenance_endpoints = session_maintenance_endpoints or {}
    session_transaction_endpoints = session_transaction_endpoints or {}
    read_semantic_endpoints = read_semantic_endpoints or frozenset()
    event_order = {item["event_id"]: item["global_order"] for item in raw["events"]}
    request_to_event = {item["request_ref"]: item["event_id"] for item in raw["bindings"]}
    event_to_request = {item["event_id"]: item["request_ref"] for item in raw["bindings"]}
    ambiguous_refs = {
        ref
        for review in raw["binding_reviews"]
        for ref in review.get("candidate_request_refs", [])
    }
    requests = {item["request_ref"]: item for item in raw["api_requests"]}
    records: list[ProducerRecord] = []
    for request in raw["api_requests"]:
        entry = _entry_for(request, bundles)
        eligible, _classification = _classify_producer(
            request,
            entry,
            session_endpoints,
            session_maintenance_endpoints,
            session_transaction_endpoints,
            read_semantic_endpoints,
        )
        if not eligible:
            continue
        request_ref = request["request_ref"]
        anchor_event = request_to_event.get(request_ref)
        if anchor_event is not None:
            producer_order = int(request["global_order"])
            bounded_refs, truncated_count = _bounded_setup_request_refs(
                raw["api_requests"], producer_order=producer_order
            )
            bounded_ref_set = set(bounded_refs)
            profile_managed_refs = tuple(
                str(item["request_ref"])
                for item in raw["api_requests"]
                if str(item["request_ref"]) in bounded_ref_set
                if session_endpoints.get(str(item["actor_id"]))
                == (str(item["method"]).upper(), str(item["canonical_path"]))
            )
            prior_bound_events = [
                str(event["event_id"])
                for event in raw["events"]
                if int(event["global_order"]) < int(event_order[anchor_event])
                and str(event["event_id"]) in event_to_request
            ]
            effective = []
            for event_id in prior_bound_events:
                bound_ref = event_to_request[event_id]
                if bound_ref not in bounded_ref_set:
                    continue
                bound = requests[bound_ref]
                endpoint = (bound["method"].upper(), bound["canonical_path"])
                if session_endpoints.get(bound["actor_id"]) != endpoint:
                    effective.append(event_id)
            records.append(
                ProducerRecord(
                    request_ref=request_ref,
                    actor_id=request["actor_id"],
                    method=request["method"],
                    canonical_path=request["canonical_path"],
                    request_started_at=entry.get("startedDateTime"),
                    anchor_status="automatic",
                    applicability="available",
                    reason_code="automatic_anchor_available",
                    anchor_event_id=anchor_event,
                    eligible_setup_event_ids=tuple(effective),
                    setup_domain_request_refs=bounded_refs,
                    profile_managed_setup_request_refs=profile_managed_refs,
                    setup_domain_truncated_request_count=truncated_count,
                )
            )
        else:
            ambiguous = request_ref in ambiguous_refs
            records.append(
                ProducerRecord(
                    request_ref=request_ref,
                    actor_id=request["actor_id"],
                    method=request["method"],
                    canonical_path=request["canonical_path"],
                    request_started_at=entry.get("startedDateTime"),
                    anchor_status="ambiguous" if ambiguous else "missing",
                    applicability="unsupported",
                    reason_code="ambiguous_anchor" if ambiguous else "missing_anchor",
                )
            )
    available = sum(item.applicability == "available" for item in records)
    return ProducerApplicability(
        applicability_id=applicability_id,
        producers=tuple(records),
        universe_count=len(records),
        available_count=available,
        unsupported_count=len(records) - available,
        source_refs=(trace.canonical_sha256(), recording.canonical_sha256()),
        source_sha256={
            "ui_api_trace": trace.canonical_sha256(),
            "recording_bundle": recording.canonical_sha256(),
        },
    )


def observed_response_statuses(
    trace: UiApiTrace,
    recording: RecordingBundle,
    *,
    recording_root: str | Path,
) -> dict[str, int | None]:
    """Resolve every admitted request, with HAR 0 denoting no HTTP response."""

    bundles = _bundles(recording, recording_root)
    statuses: dict[str, int | None] = {}
    for request in trace.trace["api_requests"]:
        request_ref = str(request["request_ref"])
        status = _entry_for(request, bundles).get("response", {}).get("status")
        if type(status) is int and status == 0:
            statuses[request_ref] = None
            continue
        if (
            not isinstance(status, int)
            or isinstance(status, bool)
            or not 100 <= status <= 599
        ):
            raise ValueError(
                f"recorded response status is missing or invalid: {request_ref}"
            )
        statuses[request_ref] = status
    if len(statuses) != len(trace.trace["api_requests"]):
        raise ValueError("recorded response status request refs are not unique")
    return statuses


def _bounded_setup_request_refs(
    requests: Sequence[Mapping[str, Any]],
    *,
    producer_order: int,
) -> tuple[tuple[str, ...], int]:
    """Keep the latest bounded prefix without changing its recorded order."""

    complete_prior = [
        item for item in requests if int(item["global_order"]) < producer_order
    ]
    truncated_count = max(0, len(complete_prior) - SETUP_DOMAIN_MAX_REQUESTS)
    retained = complete_prior[-SETUP_DOMAIN_MAX_REQUESTS:]
    return tuple(str(item["request_ref"]) for item in retained), truncated_count


def producer_setup_domains(
    applicability: ProducerApplicability,
    *,
    trace: UiApiTrace,
    value_flows: ObservedValueFlowSet,
    graph: DependencyGraph,
) -> dict[str, Any]:
    """Project each available producer's complete bounded recorded prefix."""
    raw = trace.trace
    request_by_ref = {
        str(item["request_ref"]): item for item in raw["api_requests"]
    }
    event_by_id = {str(item["event_id"]): item for item in raw["events"]}
    group_by_request: dict[str, dict[str, Any]] = {}
    for group in raw["request_groups"]:
        for member in group["members"]:
            group_by_request[str(member["request_ref"])] = {
                "group_id": str(group["group_id"]),
                "event_id": str(group["event_id"]),
                "association_status": str(group["status"]),
                "anchor_request_ref": group.get("anchor_request_ref"),
                "group_order": int(member["group_order"]),
                "weak_roles": list(member["weak_roles"]),
            }
    unassigned_by_request = {
        str(item["request_ref"]): item for item in raw["unassigned_requests"]
    }
    flows_by_request: dict[str, list[Any]] = {}
    for flow in value_flows.flows:
        flows_by_request.setdefault(flow.producer_request_ref, []).append(flow)
        flows_by_request.setdefault(flow.consumer_request_ref, []).append(flow)
    edges_by_operations: dict[tuple[str, str], list[str]] = {}
    for edge in graph.edges:
        edges_by_operations.setdefault(
            (edge.producer_operation_id, edge.consumer_operation_id), []
        ).append(edge.edge_id)

    domains = {}
    for item in applicability.producers:
        if item.applicability != "available":
            continue
        scope = set(item.setup_domain_request_refs) | {item.request_ref}
        ordered_request_refs = []
        associated_event_ids: set[str] = set()
        domain_flow_refs: set[str] = set()
        domain_dependency_refs: set[str] = set()
        for request_ref in item.setup_domain_request_refs:
            request = request_by_ref[request_ref]
            group = group_by_request.get(request_ref)
            if group is None and request_ref not in unassigned_by_request:
                raise ValueError("setup domain request is absent from the M2 partition")
            if group is not None:
                associated_event_ids.add(str(group["event_id"]))
            incident_flows = [
                flow
                for flow in flows_by_request.get(request_ref, [])
                if flow.producer_request_ref in scope
                and flow.consumer_request_ref in scope
            ]
            domain_flow_refs.update(flow.flow_id for flow in incident_flows)
            domain_dependency_refs.update(
                edge_id
                for flow in incident_flows
                for edge_id in edges_by_operations.get(
                    (
                        flow.producer_operation_id,
                        flow.consumer_operation_id,
                    ),
                    [],
                )
            )
            ordered_request_refs.append(request_ref)
        associated_action_ids = [
            event_id
            for event_id in sorted(
                associated_event_ids,
                key=lambda ref: int(event_by_id[ref]["global_order"]),
            )
        ]
        domains[item.request_ref] = {
            "producer": {
                "actor": item.actor_id,
                "request_ref": item.request_ref,
            },
            "producer_anchor": {
                "policy": "automated_binding_anchor",
                "action_id": item.anchor_event_id,
                "request_started_at": item.request_started_at,
            },
            "setup_domain_policy": SETUP_DOMAIN_POLICY,
            "bound": {
                "max_requests": SETUP_DOMAIN_MAX_REQUESTS,
                "truncated_request_count": item.setup_domain_truncated_request_count,
            },
            "eligible_setup_action_ids": list(item.eligible_setup_event_ids),
            "profile_managed_request_refs": list(
                item.profile_managed_setup_request_refs
            ),
            "associated_action_ids": associated_action_ids,
            "ordered_request_refs": ordered_request_refs,
            "value_flow_refs": sorted(domain_flow_refs),
            "dependency_edge_refs": sorted(domain_dependency_refs),
        }
    return domains


def materialize_semantic(
    trace: UiApiTrace,
    recording: RecordingBundle,
    recording_root: str | Path,
    semantic_document: Mapping[str, Any],
) -> dict[str, Any]:
    raw = trace.trace
    bundles = _bundles(recording, recording_root)
    event_ids = {item["event_id"] for item in raw["events"]}
    material = {"channel": semantic_document["channel"], "records": []}
    for record in semantic_document["records"]:
        rendered = {"record_id": record["record_id"], "typed_record": record, "observations": {}}
        for ref in _walk_refs(record):
            if ref["artifact_type"] == "ui_trace" and ref["record_id"] in event_ids:
                event = next(item for item in raw["events"] if item["event_id"] == ref["record_id"])
                observation = _semantic_event_observation(event, bundles)
                canonical_event = copy.deepcopy(observation["event"])
                canonical_event.pop("action_ref", None)
                canonical_action = copy.deepcopy(observation["action"])
                canonical_action["action_id"] = event["event_id"]
                observation = {"event": canonical_event, "action": canonical_action}
            else:
                observation = _resolve_ref(ref, raw, bundles)
            rendered["observations"][_observation_key(ref)] = observation
        material["records"].append(rendered)
    return material


def replay_route_s_certificates(candidate_result_paths: Iterable[Path]) -> tuple[RouteSCertificate, ...]:
    certificates = []
    for path in sorted(candidate_result_paths, key=lambda item: item.as_posix()):
        result = json.loads(path.read_text(encoding="utf-8"))
        certificates.append(
            RouteSCertificate(
                candidate_id=result["candidate_id"],
                outcome=result["outcome"],
                certificate_ref=result["certificate_ref"],
                certificate_sha256=result["certificate_sha256"],
                source_refs=(str(path),),
                source_sha256={str(path): sha256_file(path)},
            )
        )
    ids = [item.candidate_id for item in certificates]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Route-S certificate replay requires a unique nonempty candidate set")
    return tuple(certificates)


def certified_suite_contract(
    suite: Mapping[str, Any],
    *,
    suite_id: str,
    source_ref: str,
    source_sha256: str,
) -> CertifiedRelationTestSuite:
    value = copy.deepcopy(dict(suite))
    assertions = [row for test in value.get("tests", []) for row in test.get("assertions", [])]
    return CertifiedRelationTestSuite(
        suite_id=suite_id,
        suite=value,
        test_count=len(value.get("tests", [])),
        business_assertion_count=sum(row.get("assertion_class") == "business" for row in assertions),
        generic_assertion_count=sum(row.get("assertion_class") == "generic" for row in assertions),
        source_refs=(source_ref,),
        source_sha256={source_ref: source_sha256},
    )


def calibration_contract(
    *,
    calibration_id: str,
    test_pass_count: int,
    test_total_count: int,
    business_pass_count: int,
    business_total_count: int,
    generic_pass_count: int,
    generic_total_count: int,
    source_ref: str,
    source_sha256: str,
) -> CalibrationReport:
    return CalibrationReport(
        calibration_id=calibration_id,
        test_pass_count=test_pass_count,
        test_total_count=test_total_count,
        business_pass_count=business_pass_count,
        business_total_count=business_total_count,
        generic_pass_count=generic_pass_count,
        generic_total_count=generic_total_count,
        source_refs=(source_ref,),
        source_sha256={source_ref: source_sha256},
    )


def partition_counts(certificates: Iterable[RouteSCertificate]) -> dict[str, int]:
    return dict(sorted(Counter(item.outcome for item in certificates).items()))


def _stabilize_envelope(envelope: dict[str, Any], run_id: str) -> None:
    envelope["run_id"] = run_id
    envelope["created_at"] = "1970-01-01T00:00:00.000+00:00"


def _operation_count(document: Mapping[str, Any]) -> int:
    methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    return sum(key in methods for item in document.get("paths", {}).values() for key in item)


def _refs(trace: Mapping[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    run_id = trace["metadata"]["run_id"]
    return {
        "event": {
            item["event_id"]: {"artifact_type": "ui_trace", "run_id": run_id, "record_id": item["event_id"]}
            for item in trace["events"]
        },
        "request": {
            item["request_ref"]: {"artifact_type": "ui_trace", "run_id": run_id, "record_id": item["request_ref"]}
            for item in trace["api_requests"]
        },
    }


def _evidence_document(trace: Mapping[str, Any], channel: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = make_envelope(
            "ui_semantics_evidence",
            "stage2",
            f"{trace['metadata']['run_id']}-{channel}-evidence",
        )
    _stabilize_envelope(metadata, f"{trace['metadata']['run_id']}-{channel}-evidence")
    return {
        "metadata": metadata,
        "channel": channel,
        "records": records,
    }


def _ui_diff_records(
    trace: Mapping[str, Any],
    recording: RecordingBundle,
    recording_root: str | Path,
    refs: Mapping[str, Mapping[str, dict[str, str]]],
) -> list[dict[str, Any]]:
    ordered = trace["api_requests"]
    indexes = {item["request_ref"]: index for index, item in enumerate(ordered)}
    requests = {item["request_ref"]: item for item in ordered}
    events = {item["event_id"]: item for item in trace["events"]}
    records = []
    for binding in trace["bindings"]:
        producer = requests[binding["request_ref"]]
        if (
            producer["method"] not in WRITE_METHODS
            or producer.get("declared_read_semantic") is True
        ):
            continue
        later_reads = _ui_diff_observer_requests(
            producer,
            ordered[indexes[producer["request_ref"]] + 1 :],
        )
        page_state_refs = _page_state_refs(
            recording, recording_root, events[binding["event_id"]]
        )
        if page_state_refs is None:
            continue
        before, after = page_state_refs
        before_state, before_sha = _load_page_state(recording, recording_root, before)
        after_state, after_sha = _load_page_state(recording, recording_root, after)
        added, removed = _ordered_visible_text_diff(
            _visible_dom_text(str(before_state.get("dom_html") or "")),
            _visible_dom_text(str(after_state.get("dom_html") or "")),
        )
        record = UiDiffEvidenceRecord(
            record_id=f"ui-diff-{len(records) + 1:04d}",
            source_kind="ui_page_visible_text_diff",
            diff_rule="ordered_normalized_multiset_dom_text_v1",
            event_ref=refs["event"][binding["event_id"]],
            before_page_state_ref=before,
            before_page_state_sha256=before_sha,
            after_page_state_ref=after,
            after_page_state_sha256=after_sha,
            before_page_path=_page_path(before_state.get("url")),
            after_page_path=_page_path(after_state.get("url")),
            producer_request_refs=[refs["request"][producer["request_ref"]]],
            consumer_request_refs=[refs["request"][item["request_ref"]] for item in later_reads],
            added_text=added,
            removed_text=removed,
            diff_sha256=canonical_sha256({"added": added, "removed": removed}),
        )
        records.append(record.model_dump(mode="python"))
    return records


def _ui_diff_observer_requests(
    producer: Mapping[str, Any],
    later: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Link recorded observer facts without a fixed request-distance gate."""

    reads = [
        row
        for row in later
        if row.get("method") in READ_METHODS
        or row.get("graphql_operation_kind") == "query"
        or row.get("declared_read_semantic") is True
        or "read_like" in set(map(str, row.get("weak_roles", ())))
    ]
    producer_group = producer.get("request_group_id")
    grouped = [
        row
        for row in reads
        if producer_group is not None
        and row.get("request_group_id") == producer_group
        and row.get("actor_id") == producer.get("actor_id")
        and row.get("session_run_id") == producer.get("session_run_id")
    ]
    if grouped:
        return grouped
    comparable = [
        row
        for row in reads
        if row.get("actor_id") == producer.get("actor_id")
        and row.get("session_run_id") == producer.get("session_run_id")
        and (
            row.get("operation_id") == producer.get("operation_id")
            or row.get("canonical_path") == producer.get("canonical_path")
        )
    ]
    if not comparable:
        return []
    nearest = comparable[0]
    nearest_group = nearest.get("request_group_id")
    if nearest_group is None:
        return [nearest]
    return [
        row
        for row in reads
        if row.get("actor_id") == producer.get("actor_id")
        and row.get("session_run_id") == producer.get("session_run_id")
        if row.get("request_group_id") == nearest_group
    ]


def _transfer_records(
    trace: Mapping[str, Any],
    refs: Mapping[str, Mapping[str, dict[str, str]]],
    selection_bytes: bytes | None,
    population_bytes: bytes | None,
) -> tuple[
    list[dict[str, Any]],
    str | None,
    str | None,
    str | None,
    str | None,
]:
    if selection_bytes is None and population_bytes is None:
        return [], None, None, None, None
    if not isinstance(selection_bytes, bytes) or not isinstance(population_bytes, bytes):
        raise ValueError(
            "canonical transfer evidence requires raw bytes of versioned UI-test selection and population manifests"
        )
    selection = UiTestAssertionSelectionManifest.model_validate_json(selection_bytes)
    population = UiTestAssertionPopulationManifest.model_validate_json(population_bytes)
    selection_sha256 = hashlib.sha256(selection_bytes).hexdigest()
    population_sha256 = hashlib.sha256(population_bytes).hexdigest()
    if selection.population_sha256 != population_sha256:
        raise ValueError("UI-test selection population SHA-256 does not match supplied population bytes")
    if selection.population_count != population.candidate_count:
        raise ValueError("UI-test selection population_count does not match supplied population")
    if selection.system != population.system:
        raise ValueError("UI-test selection and population systems do not match")
    population_by_id = {item.candidate_id: item for item in population.candidates}
    for selected in selection.candidates:
        member = population_by_id.get(selected.candidate_id)
        if member is None or selected.model_dump(mode="python") != member.model_dump(mode="python"):
            raise ValueError(
                "UI-test selection candidate is not an exact allowlisted-origin member of the frozen population"
            )
    selection_ref = f"ui-test-assertion-selection:sha256:{selection_sha256}"
    population_ref = f"ui-test-assertion-population:sha256:{population_sha256}"
    api_refs = [refs["request"][item["request_ref"]] for item in trace["api_requests"]]
    records = []
    for item in selection.candidates:
        record = TransferEvidenceRecord(
            record_id=item.candidate_id,
            source_kind="ui_test_assertion",
            selection_schema_version=selection.schema_version,
            selection_manifest_sha256=selection_sha256,
            population_schema_version=population.schema_version,
            population_manifest_sha256=population_sha256,
            origin=item.model_dump(mode="python"),
            source_assertion={
                "source_sha256": item.assertion_sha256,
                "source_location": f"{item.source_path}:{item.start_line}",
                "verbatim": item.assertion,
            },
            api_observation_refs=api_refs,
        )
        records.append(record.model_dump(mode="python"))
    if len({item["record_id"] for item in records}) != len(records):
        raise ValueError("transfer record IDs must be unique")
    return records, selection_ref, selection_sha256, population_ref, population_sha256


def resolve_recording_bundle_paths(
    recording: RecordingBundle,
    recording_root: str | Path,
) -> dict[str, Path]:
    root = Path(recording_root).resolve(strict=True)
    result: dict[str, Path] = {}
    for actor in recording.actors:
        relative = Path(actor.path)
        if relative.is_absolute() or relative == Path(".") or ".." in relative.parts:
            raise ValueError("recording actor path must be recording-root-relative")
        path = (root / relative).resolve(strict=True)
        if not path.is_dir() or not path.is_relative_to(root):
            raise ValueError("recording actor path escapes the recording root")
        result[actor.actor_id] = path
    return result


def _bundles(
    recording: RecordingBundle,
    recording_root: str | Path,
) -> dict[str, LoadedBundle]:
    paths = resolve_recording_bundle_paths(recording, recording_root)
    return {
        item.run_id: load_bundle(paths[item.actor_id])
        for item in recording.actors
    }


def _normalized_bundles(
    bundles: Sequence[LoadedBundle],
    normalizer: UrlNormalizer,
) -> list[LoadedBundle]:
    normalized = []
    for bundle in bundles:
        entries = copy.deepcopy(bundle.entries)
        for entry in entries:
            request = entry.get("request") or {}
            if isinstance(request.get("url"), str):
                request["url"] = normalizer(request["url"])
        normalized.append(
            LoadedBundle(
                bundle_dir=bundle.bundle_dir,
                run_id=bundle.run_id,
                manifest=bundle.manifest,
                entries=entries,
                actions=bundle.actions,
                decisions=bundle.decisions,
                request_material_shapes=bundle.request_material_shapes,
            )
        )
    return normalized


def _entry_for(request: Mapping[str, Any], bundles: Mapping[str, LoadedBundle]) -> dict[str, Any]:
    observation = request["observation_ref"]
    return bundles[observation["run_id"]].entries[observation["entry_index"]]


def _classify_producer(
    request: Mapping[str, Any],
    entry: Mapping[str, Any],
    session_endpoints: SessionEndpointMap,
    session_maintenance_endpoints: SessionMaintenanceEndpointMap | None = None,
    session_transaction_endpoints: SessionMaintenanceEndpointMap | None = None,
    read_semantic_endpoints: frozenset[tuple[str, str]] | None = None,
) -> tuple[bool, str]:
    method = str(request["method"]).upper()
    endpoint = (method, str(request["canonical_path"]))
    if method not in WRITE_METHODS:
        return False, "read_method"
    if endpoint in (read_semantic_endpoints or frozenset()):
        return False, "profile_read_semantic_endpoint"
    if session_endpoints.get(str(request["actor_id"])) == endpoint:
        return False, "profile_session_initialization"
    if endpoint in (session_maintenance_endpoints or {}).get(
        str(request["actor_id"]), frozenset()
    ):
        return False, "profile_session_maintenance"
    if endpoint in (session_transaction_endpoints or {}).get(
        str(request["actor_id"]), frozenset()
    ):
        return False, "profile_session_transaction"
    graphql = _graphql_operation(_json_body(entry.get("request", {}).get("postData")))
    if graphql == "query":
        return False, "graphql_query_over_post"
    if graphql == "unknown":
        return False, "graphql_operation_unknown"
    return True, "state_changing_method"


def _graphql_operation(body: Any) -> str | None:
    # Local import avoids the trace_builder -> binder import cycle while keeping
    # one query-document/operationName parser for M2 binding and M3 recovery.
    from .binder import graphql_operation_kind

    return graphql_operation_kind(body)


def _json_body(post_data: Any) -> Any:
    if not isinstance(post_data, Mapping):
        return None
    text = str(post_data.get("text") or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _json_response(content: Any) -> Any:
    if not isinstance(content, Mapping):
        return None
    text = content.get("text")
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _page_state_refs(
    recording: RecordingBundle,
    recording_root: str | Path,
    event: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    actor = next(item for item in recording.actors if item.run_id == event["action_ref"]["run_id"])
    bundle = load_bundle(
        resolve_recording_bundle_paths(recording, recording_root)[actor.actor_id]
    )
    states = bundle.manifest["members"].get("page_state")
    if not isinstance(states, list) or not states:
        return None
    action_id = event["action_ref"]["action_id"]
    index = next((i for i, item in enumerate(states) if item["action_id"] == action_id), None)
    if index is None:
        return None
    before_action_id = f"before:{action_id}"
    before_index = next(
        (
            i
            for i, item in enumerate(states)
            if item["action_id"] == before_action_id
        ),
        None,
    )
    if before_index is None or before_index + 1 != index:
        return None

    def ref(item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "artifact_type": "session_bundle",
            "run_id": bundle.run_id,
            "path": str(item["file"]),
            "record_id": item["action_id"],
            "value_path": "$.dom_html",
        }

    return ref(states[before_index]), ref(states[index])


_UI_DIFF_VOLATILE_RULES = (
    re.compile(r"^[\s\u200b]*$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?$"),
    re.compile(r"^(?:a|an|\d+)\s+(?:second|minute|hour|day|week|month|year)s?\s+ago$", re.I),
    re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?$", re.I),
)


class _VisibleTextParser(HTMLParser):
    _SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.items: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._SKIP_TAGS or self._skip_depth:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        normalized = re.sub(r"\s+", " ", data).strip()
        if normalized and not any(rule.fullmatch(normalized) for rule in _UI_DIFF_VOLATILE_RULES):
            self.items.append(normalized)


def _visible_dom_text(dom_html: str) -> list[str]:
    parser = _VisibleTextParser()
    parser.feed(dom_html)
    parser.close()
    return parser.items


def _ordered_visible_text_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    before_counts = Counter(before)
    after_counts = Counter(after)
    added_budget = after_counts - before_counts
    removed_budget = before_counts - after_counts
    added: list[str] = []
    removed: list[str] = []
    for item in after:
        if added_budget[item] > 0:
            added.append(item)
            added_budget[item] -= 1
    for item in before:
        if removed_budget[item] > 0:
            removed.append(item)
            removed_budget[item] -= 1
    return added, removed


def _load_page_state(
    recording: RecordingBundle,
    recording_root: str | Path,
    ref: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    actor = next((item for item in recording.actors if item.run_id == ref.get("run_id")), None)
    if actor is None:
        raise ValueError("UI-diff page-state reference has an unknown recording run")
    root = resolve_recording_bundle_paths(recording, recording_root)[actor.actor_id]
    relative = Path(str(ref.get("path") or ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("UI-diff page-state reference must stay inside the recording bundle")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("UI-diff page-state reference escapes the recording bundle") from exc
    raw = path.read_bytes()
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        state = json.load(stream)
    if not isinstance(state, dict) or not isinstance(state.get("dom_html"), str):
        raise ValueError("UI-diff page-state snapshot lacks DOM HTML")
    if str(state.get("action_id") or "") != str(ref.get("record_id") or ""):
        raise ValueError("UI-diff page-state record identity mismatch")
    return state, hashlib.sha256(raw).hexdigest()


def _page_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "unavailable"
    split = urlsplit(value)
    return split.path or "/"


def _walk_refs(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if {"artifact_type", "run_id", "record_id"} <= value.keys():
            yield value
        for child in value.values():
            yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)


def _observation_key(ref: Mapping[str, Any]) -> str:
    return f"{ref['artifact_type']}:{ref['run_id']}:{ref['record_id']}:{ref.get('value_path', '')}"


def _semantic_event_observation(event: Mapping[str, Any], bundles: Mapping[str, LoadedBundle]) -> dict[str, Any]:
    ref = event["action_ref"]
    action = next(item for item in bundles[ref["run_id"]].actions if item["action_id"] == ref["action_id"])
    return {"event": copy.deepcopy(dict(event)), "action": copy.deepcopy(action)}


def _resolve_ref(ref: Mapping[str, Any], trace: Mapping[str, Any], bundles: Mapping[str, LoadedBundle]) -> Any:
    record_id = ref["record_id"]
    request = next(item for item in trace["api_requests"] if item["request_ref"] == record_id)
    entry = _entry_for(request, bundles)
    return {
        "request_record": request,
        "har_entry": {
            "request": {
                key: entry["request"].get(key)
                for key in ("method", "url", "queryString", "postData")
                if entry["request"].get(key) is not None
            },
            "response": {
                "status": entry["response"].get("status"),
                "content": (entry["response"].get("content") or {}).get("text"),
            },
        },
    }


def _epoch_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
