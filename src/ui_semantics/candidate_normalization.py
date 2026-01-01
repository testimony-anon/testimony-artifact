"""Shared deterministic candidate normalization used by the current bridge."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .dsl import get_path, lint_predicate


@dataclass(frozen=True)
class CandidateDecision:
    verdict: str
    rejection_class: str | None
    reason: str | None
    candidate: dict[str, Any] | None
    verification: dict[str, Any] | None = None


def prepare_semantic_candidate(
    candidate: Any,
    *,
    trace: dict[str, Any],
    improved: bool,
    enum_evidence: dict[str, Any] | None = None,
) -> CandidateDecision:
    if not isinstance(candidate, dict):
        return _reject("candidate must be an object")
    value = copy.deepcopy(candidate)
    try:
        producer = _endpoint(value, "producer", trace)
        consumer = _endpoint(value, "consumer", trace)
        _validate_setup_order(value.get("setup"), producer, trace)
        setup = _setup(value.get("setup"), trace)
        if improved:
            setup = _complete_setup(setup, producer, consumer, trace)
        evidence = dict(enum_evidence or {})
        if improved:
            derived = derive_trace_enum_evidence(value, trace=trace)
            if derived:
                supplied = evidence.get("enum_map")
                if supplied is not None and supplied != derived["enum_map"]:
                    raise ValueError("supplied enum mapping conflicts with trace evidence")
                evidence.update(derived)
        predicate = _formal_predicate(value.get("effect_predicate"), consumer, improved, evidence)
    except (KeyError, TypeError, ValueError) as error:
        return _reject(str(error))
    lint = lint_predicate(predicate, assertion=False, improved=improved, enum_evidence=evidence)
    if lint.verdict != "pass":
        return _reject(lint.reason or "predicate lint failed")
    return CandidateDecision(
        verdict="ready",
        rejection_class=None,
        reason=None,
        candidate={"producer": producer, "consumer": consumer, "setup": setup, "effect_predicate": lint.predicate},
    )


def derive_trace_enum_evidence(candidate: dict[str, Any], *, trace: dict[str, Any]) -> dict[str, Any]:
    predicate = candidate.get("effect_predicate")
    if not isinstance(predicate, dict) or predicate.get("type") != "field_equals":
        return {}
    producer = candidate.get("producer") or {}
    consumer = candidate.get("consumer") or {}
    requests = {item["id"]: item for item in trace.get("api_requests", [])}
    producer_record = requests.get(producer.get("request_ref"))
    consumer_record = requests.get(consumer.get("request_ref"))
    if not producer_record or not consumer_record:
        return {}
    value_ref = predicate.get("value_ref")
    if not isinstance(value_ref, str) or not value_ref.startswith("producer."):
        return {}
    try:
        _, side, path = value_ref.split(".", 2)
        source_root = producer_record.get("request_body") if side == "request" else producer_record.get("response_body")
        source = get_path(source_root, path)
        target = get_path(consumer_record.get("response_body"), predicate.get("target_path", ""))
    except (KeyError, TypeError, ValueError):
        return {}
    if source == target or isinstance(source, (dict, list)) or isinstance(target, (dict, list)):
        return {}
    mapping = {str(source): target}
    evidence_ref = (
        f"ui_trace:{producer['request_ref']}:{value_ref}->"
        f"{consumer['request_ref']}:response.{predicate.get('target_path', '')}"
    )
    return {"enum_map": mapping, "evidence_ref": evidence_ref, evidence_ref: mapping}


def _endpoint(candidate: dict[str, Any], side: str, trace: dict[str, Any]) -> dict[str, str]:
    endpoint = candidate.get(side)
    if not isinstance(endpoint, dict):
        raise ValueError(f"missing {side}")
    actor_id = endpoint.get("actor_id", endpoint.get("actor"))
    request_ref = endpoint.get("request_ref")
    requests = {item["id"]: item for item in trace.get("api_requests", [])}
    if request_ref not in requests or requests[request_ref].get("actor") != actor_id:
        raise ValueError(f"invalid {side} request/actor")
    return {"actor_id": actor_id, "request_ref": request_ref}


def _setup(raw: Any, trace: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise ValueError("setup must be a list")
    actions = {item["id"]: item for item in trace.get("actions", [])}
    result = []
    for item in raw:
        if isinstance(item, dict) and {"actor_id", "request_ref"} <= item.keys():
            result.append({"actor_id": item["actor_id"], "request_ref": item["request_ref"]})
            continue
        action = actions.get(item)
        if not action:
            raise ValueError(f"unknown setup action: {item}")
        request_ref = (action.get("binding_v0") or {}).get("primary_request_id")
        if request_ref:
            result.append({"actor_id": action["actor"], "request_ref": request_ref})
    return result


def _validate_setup_order(raw: Any, producer: dict[str, str], trace: dict[str, Any]) -> None:
    if not isinstance(raw, list):
        raise ValueError("setup must be a list")
    actions = trace.get("actions", [])
    action_index = {item["id"]: index for index, item in enumerate(actions)}
    request_index = {
        request_ref: index
        for index, action in enumerate(actions)
        if (request_ref := (action.get("binding_v0") or {}).get("primary_request_id"))
    }
    producer_index = request_index.get(producer["request_ref"])
    if producer_index is None:
        return
    for item in raw:
        setup_index = action_index.get(item) if isinstance(item, str) else (
            request_index.get(item.get("request_ref")) if isinstance(item, dict) else None
        )
        if setup_index is not None and setup_index >= producer_index:
            raise ValueError("setup contains an action that is not before the producer")


def _complete_setup(
    setup: list[dict[str, str]],
    producer: dict[str, str],
    consumer: dict[str, str],
    trace: dict[str, Any],
) -> list[dict[str, str]]:
    requests = {item["id"]: item for item in trace.get("api_requests", [])}
    actions = trace.get("actions", [])
    request_to_action = {
        (item.get("binding_v0") or {}).get("primary_request_id"): item
        for item in actions
        if (item.get("binding_v0") or {}).get("primary_request_id")
    }
    producer_action = request_to_action.get(producer["request_ref"])
    producer_index = actions.index(producer_action) if producer_action in actions else len(actions)
    material = [requests.get(producer["request_ref"], {}), requests.get(consumer["request_ref"], {})]
    material.extend(requests.get(item["request_ref"], {}) for item in setup)
    result = list(setup)
    present = {item["request_ref"] for item in result}
    for request_ref, action in request_to_action.items():
        if actions.index(action) >= producer_index or request_ref in present:
            continue
        request = requests.get(request_ref, {})
        if str(request.get("method", "")).upper() not in {"POST", "PUT", "PATCH"}:
            continue
        produced = [
            value
            for _, value in _scalar_leaves(request.get("response_body"))
            if isinstance(value, str) and len(value) >= 4
        ]
        if any(_contains_scalar(record, value) for record in material for value in produced):
            result.append({"actor_id": action["actor"], "request_ref": request_ref})
            present.add(request_ref)
    order = {item["id"]: index for index, item in enumerate(actions)}
    return sorted(result, key=lambda item: order.get(request_to_action.get(item["request_ref"], {}).get("id"), len(order)))


def _formal_predicate(raw: Any, consumer: dict[str, str], improved: bool, enum_evidence: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("missing effect_predicate")
    predicate = copy.deepcopy(raw)
    before = f"{consumer['request_ref']}:before"
    after = f"{consumer['request_ref']}:after"
    if predicate.get("type") in {"numeric_delta", "count_delta", "item_appears"}:
        predicate.setdefault("before_ref", before)
        predicate.setdefault("after_ref", after)
    if predicate.get("type") == "item_appears" and "target_path" in predicate:
        target_path = predicate.pop("target_path")
        if target_path != predicate.get("collection_path"):
            raise ValueError("item_appears target_path conflicts with collection_path")
    if predicate.get("type") == "field_equals":
        predicate.setdefault("response_ref", after)
    direction = predicate.pop("direction", 1)
    if predicate.get("type") == "numeric_delta" and isinstance(predicate.get("multiplier", 1), (int, float)):
        predicate["multiplier"] = predicate.get("multiplier", 1) * direction
    if improved and predicate.get("type") == "field_equals" and "value_transform" not in predicate:
        mapping = enum_evidence.get("enum_map")
        evidence_ref = enum_evidence.get("evidence_ref")
        if isinstance(mapping, dict) and mapping and isinstance(evidence_ref, str):
            predicate["value_transform"] = {"type": "enum_map", "mapping": mapping, "evidence_ref": evidence_ref}
    if improved and "value_transform" not in predicate and enum_evidence.get("null_mode"):
        predicate["value_transform"] = {"type": "null_transition", "mode": enum_evidence["null_mode"]}
    return predicate


def _reject(reason: str) -> CandidateDecision:
    return CandidateDecision("rejected", "rejected_malformed", reason, None)


def _scalar_leaves(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        return [pair for key, item in value.items() for pair in _scalar_leaves(item, f"{prefix}.{key}".strip("."))]
    if isinstance(value, list):
        return [pair for index, item in enumerate(value) for pair in _scalar_leaves(item, f"{prefix}.{index}".strip("."))]
    return [(prefix, value)]


def _contains_scalar(value: Any, needle: Any) -> bool:
    return any(item == needle for _, item in _scalar_leaves(value))
