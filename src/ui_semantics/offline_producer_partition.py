"""Typed offline partition of business and authentication/session producers."""

from __future__ import annotations

from typing import Any, Mapping

from stage0_launch.profile import (
    AppProfile,
    actor_session_initialization_endpoint,
)

from .auth_session_stratum import _resolve_auth_session_binding
from .contracts import ProducerApplicability, UiApiTrace
from .offline_pipeline import (
    WRITE_METHODS,
    declared_session_transaction_endpoints,
)


def declared_session_endpoints(
    trace: UiApiTrace,
    profile: AppProfile,
) -> dict[str, tuple[str, str]]:
    """Project exact actor-scoped session endpoints declared by the typed profile."""
    actor_ids = sorted(
        {
            str(request["actor_id"])
            for request in trace.trace.get("api_requests", [])
        }
    )
    endpoints: dict[str, tuple[str, str]] = {}
    for actor_id in actor_ids:
        endpoint = actor_session_initialization_endpoint(profile, actor_id)
        if endpoint is not None:
            endpoints[actor_id] = endpoint
    return endpoints


def _session_transaction_rows(
    trace: UiApiTrace,
    profile: AppProfile,
) -> list[dict[str, str]]:
    """Recorded writes that hit a declared identity probe or session teardown."""
    declared = declared_session_transaction_endpoints(profile)
    if not declared:
        return []
    rows = []
    for request in trace.trace.get("api_requests", []):
        actor_id = str(request["actor_id"])
        method = str(request["method"]).upper()
        canonical_path = str(request["canonical_path"])
        if method not in WRITE_METHODS:
            continue
        if (method, canonical_path) not in declared.get(actor_id, frozenset()):
            continue
        rows.append(
            {
                "request_ref": str(request["request_ref"]),
                "actor_id": actor_id,
                "method": method,
                "canonical_path": canonical_path,
            }
        )
    rows.sort(key=lambda item: item["request_ref"])
    return rows


def partition_offline_producers(
    trace: UiApiTrace,
    profile: AppProfile,
    business: ProducerApplicability,
    *,
    response_status_by_request: Mapping[str, int | None],
) -> dict[str, Any]:
    """Build a small JSON-ready business/auth-session partition without reclassification."""
    requests = trace.trace.get("api_requests", [])
    request_index = {
        str(request["request_ref"]): request
        for request in requests
    }
    if len(request_index) != len(requests):
        raise ValueError("trace request refs must be unique")
    if set(response_status_by_request) != set(request_index) or any(
        status is not None and (
            not isinstance(status, int)
            or isinstance(status, bool)
            or not 100 <= status <= 599
        )
        for status in response_status_by_request.values()
    ):
        raise ValueError("auth-session partition requires every frozen HAR status")

    business_refs = [item.request_ref for item in business.producers]
    available_refs = [
        item.request_ref
        for item in business.producers
        if item.applicability == "available"
    ]
    unsupported_refs = [
        item.request_ref
        for item in business.producers
        if item.applicability == "unsupported"
    ]
    if (
        len(business_refs) != len(set(business_refs))
        or set(available_refs) & set(unsupported_refs)
        or set(business_refs) != set(available_refs) | set(unsupported_refs)
    ):
        raise ValueError("business producer availability partition does not close")
    for item in business.producers:
        request = request_index.get(item.request_ref)
        if request is None:
            raise ValueError("business producer is absent from the supplied trace")
        trace_identity = (
            str(request["actor_id"]),
            str(request["method"]).upper(),
            str(request["canonical_path"]),
        )
        producer_identity = (
            item.actor_id,
            item.method.upper(),
            item.canonical_path,
        )
        if trace_identity != producer_identity:
            raise ValueError("business producer identity differs from the supplied trace")

    endpoints = declared_session_endpoints(trace, profile)
    endpoint_requests: dict[str, list[dict[str, str]]] = {}
    for request in requests:
        actor_id = str(request["actor_id"])
        method = str(request["method"]).upper()
        canonical_path = str(request["canonical_path"])
        if endpoints.get(actor_id) != (method, canonical_path):
            continue
        status = response_status_by_request[str(request["request_ref"])]
        if status is None or not 200 <= status < 300:
            continue
        endpoint_requests.setdefault(actor_id, []).append(
            {
                "request_ref": str(request["request_ref"]),
                "actor_id": actor_id,
                "method": method,
                "canonical_path": canonical_path,
            }
        )
    bindings: dict[str, list[dict[str, Any]]] = {}
    for binding in trace.trace["bindings"]:
        bindings.setdefault(str(binding["request_ref"]), []).append(binding)
    reviews = trace.trace["binding_reviews"]
    events = {
        str(event["event_id"]): event for event in trace.trace["events"]
    }
    auth_session = []
    for actor_id, candidates in sorted(endpoint_requests.items()):
        candidates.sort(key=lambda item: item["request_ref"])
        grounded = []
        for candidate in candidates:
            request_ref = candidate["request_ref"]
            has_confirmed_binding = any(
                row.get("status") == "confirmed"
                for row in bindings.get(request_ref, [])
            )
            has_review_binding = any(
                request_ref
                in {
                    str(item)
                    for item in review.get("candidate_request_refs", [])
                }
                for review in reviews
            )
            if not has_confirmed_binding and not has_review_binding:
                continue
            _resolve_auth_session_binding(
                request_ref=request_ref,
                actor_id=actor_id,
                endpoint=endpoints[actor_id],
                bindings=bindings,
                reviews=reviews,
                events=events,
                requests=request_index,
            )
            grounded.append(candidate)
        if len(grounded) > 1:
            raise ValueError(
                "auth-session grounded producer is not unique per actor"
            )
        if grounded:
            auth_session.append(grounded[0])
    auth_session.sort(key=lambda item: item["request_ref"])

    auth_refs = [item["request_ref"] for item in auth_session]
    overlap = sorted(set(business_refs) & set(auth_refs))
    if overlap:
        raise ValueError(
            "business and auth_session producer strata overlap: " + ", ".join(overlap)
        )
    business_count = len(business_refs)
    auth_session_count = len(auth_session)
    # Writes to a profile-declared identity probe or session teardown are session
    # transactions, not business producers, and unlike the login they are neither
    # unique per actor nor replayed as session material. They are reported beside the
    # auth/session stratum. The key is omitted when there are none, so a subject whose
    # probe is a GET and that declares no logout (Conduit, RWA) keeps its former
    # artifact byte for byte.
    transactions = _session_transaction_rows(trace, profile)
    return {
        "business_producer_refs": business_refs,
        "business_available_producer_refs": available_refs,
        "business_unsupported_producer_refs": unsupported_refs,
        "auth_session_producers": auth_session,
        **({"auth_session_transactions": transactions} if transactions else {}),
        "summary": {
            "business": business_count,
            "business_available": len(available_refs),
            "business_unsupported": len(unsupported_refs),
            "auth_session": auth_session_count,
            "total": business_count + auth_session_count,
            "disjoint": True,
        },
    }
