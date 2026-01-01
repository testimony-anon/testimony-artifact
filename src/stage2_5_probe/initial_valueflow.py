"""Stage2.5-local initial value-flow for scheduled discovery.

This module intentionally stays separate from the Stage4 dependency graph. It
only uses recorded session evidence to build fresh-value replay prefixes for
scheduled discovery candidates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from oas_naming import operation_id as make_operation_id

from .loader import Stage25Inputs

FROM_RESPONSE_BODY = "response_body"
AUTHORIZATION_HEADER = "Authorization"
_AUTH_SCHEMES = ("token", "bearer")


@dataclass(frozen=True)
class RecordedOperation:
    run_id: str
    entry_index: int
    ref: str
    operation_id: str
    method: str
    canonical_path: str
    entry: dict


@dataclass(frozen=True)
class InitialValueFlow:
    producer: RecordedOperation
    consumer: RecordedOperation
    from_location: str
    from_field: str
    to_location: str
    to_field: str
    value: str


@dataclass(frozen=True)
class InitialValueFlowKey:
    consumer_ref: str
    to_location: str
    to_field: str
    value: str


@dataclass
class InitialValueFlowSelection:
    usable_flows: list[InitialValueFlow]
    ambiguous_flows: list[InitialValueFlow]
    ambiguous_keys: set[InitialValueFlowKey]

    def is_ambiguous(self, consumer_ref: str, to_location: str, to_field: str, value: str) -> bool:
        return InitialValueFlowKey(consumer_ref, to_location, to_field, value) in self.ambiguous_keys

    def ambiguous_for_consumer(self, consumer_ref: str) -> list[InitialValueFlowKey]:
        return sorted(
            (key for key in self.ambiguous_keys if key.consumer_ref == consumer_ref),
            key=lambda key: (key.to_location, key.to_field, key.value),
        )


def recorded_operations(inp: Stage25Inputs) -> list[RecordedOperation]:
    """Return recorded operations in deterministic session order."""
    out: list[RecordedOperation] = []
    for canonical_path, item in inp.initial_oas.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if not isinstance(op, dict):
                continue
            operation_id = str(op.get("operationId") or make_operation_id(method, canonical_path))
            for obs in op.get("x-carverflow-observations", []):
                if "run_id" not in obs or "entry_index" not in obs:
                    continue
                run_id = str(obs["run_id"])
                entry_index = int(obs["entry_index"])
                bundle = inp.bundles.get(run_id)
                if bundle is None or entry_index >= len(bundle.entries):
                    continue
                out.append(RecordedOperation(
                    run_id=run_id,
                    entry_index=entry_index,
                    ref=f"{run_id}#{entry_index}",
                    operation_id=operation_id,
                    method=method.upper(),
                    canonical_path=canonical_path,
                    entry=bundle.entries[entry_index],
                ))
    return sorted(out, key=lambda op: (op.run_id, op.entry_index, op.operation_id))


def infer_initial_value_flows(inp: Stage25Inputs) -> list[InitialValueFlow]:
    """Infer exact recorded response-body -> later request value flows."""
    operations = recorded_operations(inp)
    producers_by_value: dict[str, list[tuple[RecordedOperation, str]]] = {}
    for op in operations:
        for jsonpath, value in response_body_leaves(op.entry):
            producers_by_value.setdefault(value, []).append((op, jsonpath))

    flows: list[InitialValueFlow] = []
    for consumer in operations:
        for to_location, to_field, value in request_literals(consumer):
            for producer, from_field in producers_by_value.get(value, []):
                if producer.run_id != consumer.run_id:
                    continue
                if producer.entry_index >= consumer.entry_index:
                    continue
                flows.append(InitialValueFlow(
                    producer=producer,
                    consumer=consumer,
                    from_location=FROM_RESPONSE_BODY,
                    from_field=from_field,
                    to_location=to_location,
                    to_field=to_field,
                    value=value,
                ))

    return sorted(
        flows,
        key=lambda flow: (
            flow.consumer.run_id,
            flow.consumer.entry_index,
            flow.consumer.operation_id,
            flow.to_location,
            flow.to_field,
            flow.producer.entry_index,
            flow.from_field,
        ),
    )


def select_initial_value_flows_for_scheduled_planning(inp: Stage25Inputs) -> InitialValueFlowSelection:
    """Return only unambiguous A0 flows for scheduled discovery planning.

    Raw A0 inference intentionally reports every exact match. Scheduled planning
    needs a stricter view: one recorded request slot/value must map to exactly
    one producer ref/from_field before it may become a fresh binding.
    """
    groups: dict[InitialValueFlowKey, list[InitialValueFlow]] = {}
    for flow in infer_initial_value_flows(inp):
        key = InitialValueFlowKey(
            consumer_ref=flow.consumer.ref,
            to_location=flow.to_location,
            to_field=flow.to_field,
            value=flow.value,
        )
        groups.setdefault(key, []).append(flow)

    usable: list[InitialValueFlow] = []
    ambiguous: list[InitialValueFlow] = []
    ambiguous_keys: set[InitialValueFlowKey] = set()
    for key in sorted(groups, key=lambda item: (item.consumer_ref, item.to_location, item.to_field, item.value)):
        flows = sorted(groups[key], key=_flow_sort_key)
        sources = {
            (flow.producer.ref, flow.from_location, flow.from_field)
            for flow in flows
        }
        if len(sources) == 1:
            usable.append(flows[0])
        elif key.to_location == "header" and key.to_field == AUTHORIZATION_HEADER:
            auth_flow = _select_authorization_producer(flows)
            if auth_flow is not None:
                usable.append(auth_flow)
            else:
                ambiguous_keys.add(key)
                ambiguous.extend(flows)
        else:
            ambiguous_keys.add(key)
            ambiguous.extend(flows)

    return InitialValueFlowSelection(
        usable_flows=usable,
        ambiguous_flows=ambiguous,
        ambiguous_keys=ambiguous_keys,
    )


def response_body_leaves(entry: dict) -> list[tuple[str, str]]:
    body = _response_json(entry)
    return [
        (jsonpath, text)
        for jsonpath, _key, value in _json_leaves(body)
        if (text := _scalar_text(value)) is not None
    ]


def request_literals(op: RecordedOperation) -> list[tuple[str, str, str]]:
    """Return scalar literals in recorded request path/query/body/Auth header."""
    out: list[tuple[str, str, str]] = []
    request = op.entry.get("request", {})
    for field, value in canonical_path_values(op.canonical_path, request.get("url", "")):
        out.append(("path", field, value))
    parts = urlsplit(request.get("url", ""))
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if value:
            out.append(("query", key, value))
    auth_value = _authorization_value(request)
    if auth_value:
        out.append(("header", AUTHORIZATION_HEADER, auth_value))
    for jsonpath, _key, value in _json_leaves(_request_json(op.entry)):
        text = _scalar_text(value)
        if text is not None:
            out.append(("body", jsonpath, text))
    return out


def literal_parameters(op: RecordedOperation, step: int) -> list[dict]:
    """Return inline replay parameters for recorded request literals.

    These are used as coarse request material; later bindings may overwrite them
    with fresh values.
    """
    return [
        {
            "to_step": step,
            "to_location": to_location,
            "to_field": to_field,
            "value": value,
        }
        for to_location, to_field, value in request_literals(op)
    ]


def canonical_path_values(canonical_path: str, concrete_url: str) -> list[tuple[str, str]]:
    c_segments = [seg for seg in canonical_path.strip("/").split("/") if seg]
    u_segments = [unquote(seg) for seg in urlsplit(concrete_url).path.strip("/").split("/") if seg]
    if len(c_segments) != len(u_segments):
        return []
    out = []
    for c_seg, u_seg in zip(c_segments, u_segments, strict=True):
        if c_seg.startswith("{") and c_seg.endswith("}") and len(c_seg) > 2:
            out.append((c_seg[1:-1], u_seg))
    return out


def _request_json(entry: dict) -> Any | None:
    text = entry.get("request", {}).get("postData", {}).get("text")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _response_json(entry: dict) -> Any | None:
    text = entry.get("response", {}).get("content", {}).get("text")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _authorization_value(request: dict) -> str | None:
    for name, value in _headers(request):
        if name.lower() != "authorization":
            continue
        text = value.strip()
        if not text:
            continue
        parts = text.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in _AUTH_SCHEMES:
            return parts[1].strip() or None
        return text
    return None


def _select_authorization_producer(flows: list[InitialValueFlow]) -> InitialValueFlow | None:
    """Select a trusted login-token source for repeated auth echoes.

    Auth tokens are often echoed by later authenticated endpoints. Treating the
    same token placeholder as an ordinary business value makes scheduled prefix
    replay unnecessarily ambiguous. We only collapse that ambiguity when a
    producer looks like the original unauthenticated login/token response.
    """
    trusted = [
        flow for flow in flows
        if _auth_producer_trust_score(flow) is not None
    ]
    if not trusted:
        return None
    return sorted(
        trusted,
        key=lambda flow: (
            _auth_producer_trust_score(flow),
            flow.producer.entry_index,
            flow.producer.operation_id,
            flow.from_field,
        ),
    )[0]


def _auth_producer_trust_score(flow: InitialValueFlow) -> int | None:
    if flow.from_location != FROM_RESPONSE_BODY:
        return None
    if not _token_field(flow.from_field):
        return None
    if _authorization_value(flow.producer.entry.get("request", {})):
        return None
    if _login_like_operation(flow.producer):
        return 0
    return None


def _token_field(field: str) -> bool:
    tail = field.rsplit(".", 1)[-1]
    if "[" in tail:
        tail = tail.split("[", 1)[0]
    return tail.strip("$").lower() in {"token", "auth_token", "access_token", "jwt"}


def _login_like_operation(op: RecordedOperation) -> bool:
    haystack = " ".join([
        op.operation_id,
        op.canonical_path,
        urlsplit(op.entry.get("request", {}).get("url", "")).path,
    ]).lower()
    markers = (
        "login",
        "log_in",
        "signin",
        "sign_in",
        "session",
        "sessions",
        "token",
    )
    return any(marker in haystack for marker in markers)


def _headers(request: dict) -> list[tuple[str, str]]:
    headers = request.get("headers", [])
    if isinstance(headers, dict):
        return [(str(k), str(v)) for k, v in headers.items()]
    out = []
    if isinstance(headers, list):
        for header in headers:
            if not isinstance(header, dict):
                continue
            name = header.get("name")
            value = header.get("value")
            if name is None or value is None:
                continue
            out.append((str(name), str(value)))
    return out


def _json_leaves(value: Any, path: str = "$") -> list[tuple[str, str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, str, Any]] = []
        for key, child in value.items():
            child_path = f"$.{key}" if path == "$" else f"{path}.{key}"
            out.extend(_json_leaves(child, child_path))
        return out
    if isinstance(value, list):
        out: list[tuple[str, str, Any]] = []
        for i, child in enumerate(value):
            out.extend(_json_leaves(child, f"{path}[{i}]"))
        return out
    return [(path, _leaf_key(path), value)]


def _leaf_key(path: str) -> str:
    tail = path.rsplit(".", 1)[-1]
    if "[" in tail:
        tail = tail.split("[", 1)[0]
    return tail.strip("$")


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value)
        return text if text else None
    return None


def _flow_sort_key(flow: InitialValueFlow) -> tuple:
    return (
        flow.consumer.run_id,
        flow.consumer.entry_index,
        flow.consumer.operation_id,
        flow.to_location,
        flow.to_field,
        flow.value,
        flow.producer.entry_index,
        flow.producer.operation_id,
        flow.from_field,
    )
