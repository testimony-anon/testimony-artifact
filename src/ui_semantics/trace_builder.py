"""Build the typed ui_trace sidecar from neutral recorded traces."""

from __future__ import annotations

import gzip
from pathlib import Path
from datetime import datetime
import json
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

from common.contracts import make_envelope, validate_artifact
from common.request_admission import (
    EXCLUDED_RESPONSE_MIME_TYPES as _EXCLUDED_RESPONSE_MIME_TYPES,
)
from common.request_admission import response_media_type, response_mime_is_admitted
from oas_naming import operation_id
from stage2_recover.loader import load_bundle

from .binder import (
    BindingDecision,
    bind_actions,
    graphql_operation_kind,
    request_is_mutating,
)


OperationResolver = Callable[[str, str, dict[str, Any]], str]
UrlNormalizer = Callable[[str], str]
REQUEST_RESOURCE_TYPES = frozenset({"document", "fetch", "xhr"})
# Framework payloads that arrive as fetch/xhr but carry no API surface (Next.js RSC
# prefetches). The list lives in common.request_admission because the Stage2/Stage3
# recovery path must apply exactly the same criterion; re-exported here for callers
# that already read it from this module.
EXCLUDED_RESPONSE_MIME_TYPES = _EXCLUDED_RESPONSE_MIME_TYPES


def resource_type_is_admitted(value: Any) -> bool:
    """Admit request-bearing browser resources, excluding static assets by default."""
    return _normalized_resource_type(value) in REQUEST_RESOURCE_TYPES


def entry_is_admitted(entry: Mapping[str, Any]) -> bool:
    """Full admission predicate: request-bearing resource type and an admitted MIME."""
    return resource_type_is_admitted(
        entry.get("_resource_type")
    ) and response_mime_is_admitted(entry)


def request_admission_counts(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic counts for an evaluation-side admission report."""
    counts: dict[str, dict[str, int]] = {}
    mime_excluded: dict[str, int] = {}
    total = admitted = 0
    for entry in entries:
        resource_type = _normalized_resource_type(entry.get("_resource_type"))
        bucket = counts.setdefault(resource_type, {"total": 0, "admitted": 0, "excluded": 0})
        bucket["total"] += 1
        total += 1
        if not resource_type_is_admitted(resource_type):
            bucket["excluded"] += 1
        elif not response_mime_is_admitted(entry):
            bucket["excluded"] += 1
            mime = _normalized_response_mime(entry)
            mime_excluded[mime] = mime_excluded.get(mime, 0) + 1
        else:
            bucket["admitted"] += 1
            admitted += 1
    return {
        "admitted_resource_types": sorted(REQUEST_RESOURCE_TYPES),
        "excluded_response_mime_types": sorted(EXCLUDED_RESPONSE_MIME_TYPES),
        "total": total,
        "admitted": admitted,
        "excluded": total - admitted,
        "excluded_by_response_mime": sum(mime_excluded.values()),
        "by_resource_type": {key: counts[key] for key in sorted(counts)},
        "by_excluded_response_mime": {key: mime_excluded[key] for key in sorted(mime_excluded)},
    }


def build_ui_trace(
    trace: dict[str, Any],
    *,
    actor_bundle_refs: Mapping[str, Mapping[str, str]],
    run_id: str,
    operation_resolver: OperationResolver | None = None,
    url_normalizer: UrlNormalizer | None = None,
) -> dict[str, Any]:
    """Construct a credential-free ui_trace and validate it before returning."""
    actions = sorted(
        trace.get("actions", []),
        key=lambda item: (int(item["global_step_index"]), item["id"]),
    )
    requests = sorted(trace.get("api_requests", []), key=lambda item: (item["started_at_ms"], item["id"]))
    decisions = bind_actions(actions, requests)
    resolver = operation_resolver or _default_operation_resolver
    normalize_url = url_normalizer or (lambda value: value)

    actors = []
    for actor_id in sorted(trace.get("actors", {})):
        bundle = actor_bundle_refs.get(actor_id)
        if bundle is None:
            raise ValueError(f"actor lacks a session bundle reference: {actor_id}")
        actors.append(
            {
                "actor_id": actor_id,
                "session_bundle_ref": {
                    "artifact_type": "session_bundle",
                    "run_id": bundle["run_id"],
                    "path": bundle["path"],
                },
            }
        )

    events = [
        {
            "event_id": str(action["id"]),
            "actor_id": str(action["actor"]),
            "action_ref": {
                "run_id": actor_bundle_refs[str(action["actor"])]["run_id"],
                "action_id": str(action.get("source_action_id") or action["id"]),
            },
            "global_order": int(action["global_step_index"]),
            "scenario_step_id": str(action["scenario_step_id"]),
            "workflow_step_id": str(action["workflow_step_id"]),
            "global_step_index": int(action["global_step_index"]),
            "binding_material_source_step_ids": list(
                action.get("binding_material_source_step_ids") or []
            ),
        }
        for index, action in enumerate(actions)
    ]
    api_requests = [
        _request_record(request, index, actor_bundle_refs, resolver, normalize_url)
        for index, request in enumerate(requests)
    ]
    bindings = [_confirmed_binding(item, index) for index, item in enumerate(decisions) if item.status == "confirmed"]
    reviews = [_binding_review(item, index) for index, item in enumerate(decisions) if item.status == "review_required"]
    request_groups, unassigned_requests = _request_group_records(
        actions,
        requests,
        api_requests,
        decisions,
    )

    document = {
        "metadata": make_envelope(
            "ui_trace",
            "stage2",
            run_id,
            upstream_refs=[
                {"artifact_type": "session_bundle", "run_id": actor["session_bundle_ref"]["run_id"], "path": actor["session_bundle_ref"]["path"]}
                for actor in actors
            ],
        ),
        "actors": actors,
        "events": events,
        "api_requests": api_requests,
        "bindings": bindings,
        "binding_reviews": reviews,
        "request_groups": request_groups,
        "unassigned_requests": unassigned_requests,
    }
    validate_artifact("ui_trace.schema.json", document)
    return document


def build_ui_trace_from_bundles(
    actor_bundle_dirs: Mapping[str, str | Path],
    *,
    run_id: str,
    step_correspondence: Iterable[Mapping[str, Any]],
    after_url_resolution_report: dict[str, Any] | None = None,
    url_normalizer: UrlNormalizer | None = None,
    read_semantic_endpoints: frozenset[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Aggregate contracted single-actor bundles without introducing a second trace format."""
    if not actor_bundle_dirs:
        raise ValueError("at least one actor session bundle is required")
    normalize_url = url_normalizer or (lambda value: value)
    declared_read_semantic = read_semantic_endpoints or frozenset()
    correspondence = list(step_correspondence)
    if [int(item["global_step_index"]) for item in correspondence] != list(range(len(correspondence))):
        raise ValueError("workflow step correspondence is not globally contiguous")
    by_actor_action = {
        (str(item["actor_id"]), str(item["action_id"])): item
        for item in correspondence
    }
    if len(by_actor_action) != len(correspondence):
        raise ValueError("workflow step correspondence contains duplicate actor/action refs")
    actions = []
    requests = []
    refs = {}
    after_url_resolutions = []
    for actor_id, bundle_dir in sorted(actor_bundle_dirs.items()):
        bundle = load_bundle(bundle_dir)
        refs[actor_id] = {"run_id": bundle.run_id, "path": str(bundle.bundle_dir)}
        page_state_urls = _load_page_state_urls(bundle.bundle_dir, bundle.manifest)
        actor_actions = sorted(bundle.actions, key=lambda item: int(item["global_step_index"]))
        if len(bundle.decisions) != len(actor_actions):
            raise ValueError(f"actor action/decision count mismatch: {actor_id}")
        decision_by_action = {
            str(item["action_id"]): item for item in bundle.decisions
        }
        if len(decision_by_action) != len(bundle.decisions):
            raise ValueError(f"actor decisions contain duplicate action IDs: {actor_id}")
        for index, action in enumerate(actor_actions):
            action_id = str(action["action_id"])
            recorded_decision = decision_by_action.get(action_id)
            if recorded_decision is None:
                raise ValueError(f"deterministic decision missing for action: {actor_id}/{action_id}")
            row = by_actor_action.get((actor_id, action_id))
            if row is None:
                raise ValueError(f"workflow correspondence missing actor action: {actor_id}/{action_id}")
            if str(action["workflow_step_id"]) != str(row["workflow_step_id"]):
                raise ValueError("workflow step ID differs between bundle and result")
            if str(action["scenario_step_id"]) != str(row["scenario_step_id"]):
                raise ValueError("scenario step ID differs between bundle and result")
            if int(action["global_step_index"]) != int(row["global_step_index"]):
                raise ValueError("global step index differs between bundle and result")
            material_refs = list(
                action.get("binding_material_source_step_ids") or []
            )
            if material_refs != list(
                row.get("binding_material_source_step_ids") or []
            ):
                raise ValueError(
                    "binding material refs differ between bundle and result"
                )
            decision_detail = recorded_decision.get("detail") or {}
            if (
                str(decision_detail.get("actor_id")) != actor_id
                or str(decision_detail.get("scenario_step_id"))
                != str(row["scenario_step_id"])
                or str(decision_detail.get("workflow_step_id")) != str(row["workflow_step_id"])
                or int(decision_detail.get("global_step_index", -1)) != int(row["global_step_index"])
                or list(
                    decision_detail.get("binding_material_source_step_ids") or []
                )
                != material_refs
            ):
                raise ValueError("deterministic decision differs from workflow correspondence")
            started = _epoch_ms(str(row["started_at"]))
            finished = _epoch_ms(str(row["ended_at"]))
            if action_id in page_state_urls:
                after_url = page_state_urls[action_id]
                resolution_source = "page_state_snapshot"
            elif index + 1 < len(actor_actions):
                after_url = actor_actions[index + 1]["page_url"]
                resolution_source = "fallback_next_action"
            else:
                after_url = action["page_url"]
                resolution_source = "fallback_current_action"
            after_url_resolutions.append(
                {
                    "actor_id": actor_id,
                    "action_id": action_id,
                    "source": resolution_source,
                    "after_url": after_url,
                }
            )
            actions.append(
                {
                    "id": f"{bundle.run_id}:{action['action_id']}",
                    "source_action_id": action["action_id"],
                    "actor": actor_id,
                    "started_at_ms": started,
                    "finished_at_ms": max(started, finished),
                    "scenario_step_id": str(row["scenario_step_id"]),
                    "workflow_step_id": str(row["workflow_step_id"]),
                    "global_step_index": int(row["global_step_index"]),
                    "action_type": action["action_type"],
                    "key": action.get("key"),
                    "selector": action.get("selector"),
                    "element_accessibility": action.get("element_accessibility"),
                    "after": {"url": after_url},
                    "input_values": (
                        {action["selector"]: action["value"]}
                        if action.get("value") and action.get("selector")
                        else {}
                    ),
                    "binding_material_source_step_ids": material_refs,
                }
            )
        for entry_index, entry in enumerate(bundle.entries):
            if not entry_is_admitted(entry):
                continue
            request = entry["request"]
            normalized_request_url = normalize_url(request["url"])
            split = urlsplit(normalized_request_url)
            if split.scheme not in {"http", "https"} or not (split.path or "/").startswith("/"):
                continue
            requests.append(
                {
                    "id": f"{bundle.run_id}:request:{entry_index}",
                    "actor": actor_id,
                    "started_at_ms": _epoch_ms(entry["startedDateTime"]),
                    "method": request["method"],
                    "path": request["url"],
                    "request_body": _har_body(request),
                    "resource_type": entry.get("_resource_type"),
                    "background": str(entry.get("_initiator", {}).get("type") or "").lower() == "script",
                    "_entry_index": entry_index,
                    # Only a profile-declared read-semantic method/path pair carries
                    # the flag; every other request record is unchanged.
                    **(
                        {"declared_read_semantic": True}
                        if (str(request["method"]).upper(), split.path or "/")
                        in declared_read_semantic
                        else {}
                    ),
                }
            )

    if len(actions) != len(correspondence):
        raise ValueError("workflow correspondence contains actions absent from actor bundles")
    entry_index_by_ref = {item["id"]: item.pop("_entry_index") for item in requests}

    def resolver(method: str, path: str, request: dict[str, Any]) -> str:
        del request
        return operation_id(method, path)

    document = build_ui_trace(
        {"actors": {actor_id: {} for actor_id in actor_bundle_dirs}, "actions": actions, "api_requests": requests},
        actor_bundle_refs=refs,
        run_id=run_id,
        operation_resolver=resolver,
        url_normalizer=normalize_url,
    )
    for record in document["api_requests"]:
        record["observation_ref"]["entry_index"] = entry_index_by_ref[record["request_ref"]]
    validate_artifact("ui_trace.schema.json", document)
    if after_url_resolution_report is not None:
        counts: dict[str, int] = {}
        for item in after_url_resolutions:
            counts[item["source"]] = counts.get(item["source"], 0) + 1
        after_url_resolution_report.clear()
        after_url_resolution_report.update(
            {
                "schema_version": "ui-trace-after-url-resolution-v1",
                "counts": {key: counts[key] for key in sorted(counts)},
                "resolutions": after_url_resolutions,
            }
        )
    return document


def _load_page_state_urls(bundle_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    """Load authoritative post-action URLs; an indexed corrupt snapshot is never a fallback."""
    urls: dict[str, str] = {}
    for item in manifest["members"]["page_state"]:
        action_id = str(item["action_id"])
        if action_id in urls:
            raise ValueError(f"duplicate page_state action_id: {action_id}")
        snapshot_path = bundle_dir / item["file"]
        try:
            with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
                snapshot = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid page_state snapshot for {action_id}: {snapshot_path}") from exc
        if snapshot.get("action_id") != action_id:
            raise ValueError(
                f"page_state action_id mismatch: manifest={action_id}, "
                f"snapshot={snapshot.get('action_id')}"
            )
        url = snapshot.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError(f"page_state snapshot lacks URL: {action_id}")
        urls[action_id] = url
    return urls


def _request_record(
    request: dict[str, Any],
    entry_index: int,
    actor_bundle_refs: Mapping[str, Mapping[str, str]],
    resolver: OperationResolver,
    url_normalizer: UrlNormalizer,
) -> dict[str, Any]:
    actor_id = str(request["actor"])
    path = urlsplit(url_normalizer(str(request.get("path") or "/"))).path or "/"
    method = str(request.get("method") or "GET").upper()
    record = {
        "request_ref": str(request["id"]),
        "actor_id": actor_id,
        "observation_ref": {
            "run_id": actor_bundle_refs[actor_id]["run_id"],
            "entry_index": entry_index,
        },
        "operation_id": resolver(method, path, request),
        "method": method,
        "canonical_path": path,
        "body_encoding": _body_encoding(request),
        "global_order": entry_index,
    }
    graphql_kind = graphql_operation_kind(request.get("request_body"))
    if graphql_kind is not None:
        record["graphql_operation_kind"] = graphql_kind
    if request.get("declared_read_semantic") is True:
        record["declared_read_semantic"] = True
    return record


def _default_operation_resolver(method: str, path: str, _request: dict[str, Any]) -> str:
    return operation_id(method, path)


def _body_encoding(request: dict[str, Any]) -> str:
    content_type = str(request.get("request_content_type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        return "form_urlencoded"
    if "multipart/form-data" in content_type:
        return "multipart"
    if request.get("request_body") is None:
        return "none"
    return "json"


def load_trace(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _epoch_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _normalized_resource_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "unknown"


def _normalized_response_mime(entry: Mapping[str, Any]) -> str:
    """Canonical lowercase response media type; the shared cross-stage implementation."""
    return response_media_type(entry)


def _har_body(request: dict[str, Any]) -> Any:
    post = request.get("postData") or {}
    text = post.get("text")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {item["name"]: item.get("value") for item in post.get("params", [])}


def _confirmed_binding(decision: BindingDecision, index: int) -> dict[str, Any]:
    assert decision.request_ref is not None
    return {
        "binding_id": f"binding-{index:04d}",
        "event_id": decision.event_id,
        "request_ref": decision.request_ref,
        "status": "confirmed",
        "deterministic_evidence": list(decision.evidence),
    }


def _binding_review(decision: BindingDecision, index: int) -> dict[str, Any]:
    return {
        "review_id": f"binding-review-{index:04d}",
        "event_id": decision.event_id,
        "candidate_request_refs": list(decision.candidate_request_refs),
        "status": "review_required",
        "reason": decision.reason,
        "deterministic_evidence": list(decision.evidence),
    }


def _request_group_records(
    actions: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    api_requests: list[dict[str, Any]],
    decisions: list[BindingDecision],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Materialize every action window without turning weak request roles into filters."""
    request_by_ref = {str(item["id"]): item for item in requests}
    api_by_ref = {str(item["request_ref"]): item for item in api_requests}
    grouped_refs: set[str] = set()
    groups = []
    for group_order, (action, decision) in enumerate(zip(actions, decisions, strict=True)):
        refs = [
            str(request["id"])
            for request in requests
            if str(request["actor"]) == str(action["actor"])
            and int(action["started_at_ms"])
            <= int(request.get("started_at_ms", -1))
            <= int(action["finished_at_ms"])
        ]
        duplicate_refs = sorted(grouped_refs.intersection(refs))
        if duplicate_refs:
            raise ValueError(
                "workflow action windows overlap for admitted requests: "
                + ", ".join(duplicate_refs)
            )
        grouped_refs.update(refs)
        repeated_operations = _repeated_operations(refs, api_by_ref)
        review_refs = set(decision.candidate_request_refs)
        members = []
        for member_order, request_ref in enumerate(refs):
            request = request_by_ref[request_ref]
            api_request = api_by_ref[request_ref]
            members.append(
                {
                    "request_ref": request_ref,
                    "global_order": api_request["global_order"],
                    "group_order": member_order,
                    "weak_roles": _weak_request_roles(
                        request,
                        api_request,
                        anchor_request_ref=decision.request_ref,
                        review_candidate=(
                            decision.status == "review_required"
                            and request_ref in review_refs
                        ),
                        repeated_operations=repeated_operations,
                    ),
                }
            )
        groups.append(
            {
                "group_id": f"request-group-{group_order:04d}",
                "event_id": decision.event_id,
                "actor_id": str(action["actor"]),
                "status": (
                    "anchored"
                    if decision.status == "confirmed"
                    else "review_required"
                    if decision.status == "review_required"
                    else "unanchored"
                    if refs
                    else "no_request"
                ),
                "anchor_request_ref": decision.request_ref,
                "members": members,
                "deterministic_evidence": list(decision.evidence),
                "reason": decision.reason,
            }
        )

    unassigned = []
    for request, api_request in zip(requests, api_requests, strict=True):
        request_ref = str(request["id"])
        if request_ref in grouped_refs:
            continue
        unassigned.append(
            {
                "request_ref": request_ref,
                "actor_id": str(request["actor"]),
                "global_order": api_request["global_order"],
                "weak_roles": _weak_request_roles(
                    request,
                    api_request,
                    anchor_request_ref=None,
                    review_candidate=False,
                    repeated_operations=set(),
                ),
                "status": "unassigned",
                "reason": "outside_action_window",
            }
        )
    return groups, unassigned


def _repeated_operations(
    request_refs: list[str],
    api_by_ref: Mapping[str, dict[str, Any]],
) -> set[tuple[str, str]]:
    counts: dict[tuple[str, str], int] = {}
    for request_ref in request_refs:
        request = api_by_ref[request_ref]
        key = (str(request["method"]), str(request["canonical_path"]))
        counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count > 1}


def _weak_request_roles(
    request: dict[str, Any],
    api_request: dict[str, Any],
    *,
    anchor_request_ref: str | None,
    review_candidate: bool,
    repeated_operations: set[tuple[str, str]],
) -> list[str]:
    roles = []
    request_ref = str(request["id"])
    if request_ref == anchor_request_ref:
        roles.append("anchor")
    if request_is_mutating(request):
        roles.append("state_change_like")
    if (
        str(api_request["method"]) in {"GET", "HEAD"}
        or api_request.get("declared_read_semantic") is True
    ):
        roles.append("read_like")
    operation = (str(api_request["method"]), str(api_request["canonical_path"]))
    if operation in repeated_operations:
        roles.append("repeated_operation_like")
    if bool(request.get("background", False)):
        roles.append("background_initiated")
    if review_candidate:
        roles.append("review_candidate")
    return roles or ["unknown"]
