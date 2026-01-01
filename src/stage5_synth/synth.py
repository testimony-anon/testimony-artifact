"""Stage 5 sequence/skill synthesis.

The output contract stays deliberately small: each artifact still contains only
steps, bindings, parameters, and status.  The strategy below improves the
selection layer without adding semantic labels or system-specific rules: it
scores real dependency-graph evidence, enumerates bounded candidate chains, then
greedily selects candidates that maximize operation and binding coverage.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Iterable

from common.oas_discovery import is_execution_ready

FROM_RESPONSE_BODY = "response_body"
AUTH_FROM_FIELD = "$.user.token"

MAX_STEPS = 10
MAX_SELECTED_FACTOR = 2
SEARCH_QUERY_NAMES = {"q", "query", "search", "keyword", "term"}
DENY_DYNAMIC_HEADER_BINDING = {
    "accept",
    "accept-encoding",
    "accept-language",
    "connection",
    "content-length",
    "content-type",
    "cookie",
    "host",
    "origin",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "set-cookie",
    "user-agent",
}


@dataclass(frozen=True)
class OpMeta:
    operation_id: str
    method: str
    path: str
    segments: tuple[str, ...]
    path_params: tuple[str, ...]
    is_read: bool
    is_write: bool
    is_collection_create: bool
    is_instance_or_child: bool
    is_auth_like: bool
    is_register_like: bool


@dataclass(frozen=True)
class BindingPlan:
    producer: str
    from_location: str
    from_field: str
    consumer: str
    to_location: str
    to_field: str
    observation_refs: tuple
    kind: str
    score: float


@dataclass(frozen=True)
class OrderPlan:
    producer: str
    consumer: str
    semantic_edge_id: str
    audit_ref: tuple[str, str, str]


@dataclass(frozen=True)
class Candidate:
    steps: tuple[str, ...]
    bindings: tuple[BindingPlan, ...]
    orders: tuple[OrderPlan, ...]
    score: float
    reason: str


def _operation_entries(augmented_oas: dict) -> dict[str, dict]:
    ops: dict[str, dict] = {}
    for path, path_item in (augmented_oas.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if not isinstance(op, dict) or not is_execution_ready(op):
                continue
            operation_id = op.get("operationId")
            if not operation_id:
                continue
            ops[operation_id] = {**op, "__method": method.lower(), "__path": path}
    return ops


def _op_metadata(ops: dict[str, dict]) -> dict[str, OpMeta]:
    return {operation_id: _one_meta(operation_id, op) for operation_id, op in ops.items()}


def _one_meta(operation_id: str, op: dict) -> OpMeta:
    method = str(op.get("__method") or "").upper()
    path = str(op.get("__path") or "")
    segments = tuple(segment for segment in path.strip("/").split("/") if segment)
    path_params = tuple(_strip_braces(segment) for segment in segments if _is_param(segment))
    search_text = f"{operation_id} {path}".lower()
    is_read = method in {"GET", "HEAD", "OPTIONS"}
    is_write = method in {"POST", "PUT", "PATCH", "DELETE"}
    is_collection_create = method == "POST" and not path_params
    is_instance_or_child = bool(path_params)
    is_auth_like = bool(re.search(r"(?:^|[_/\-])(login|auth|token|session|signin|sign_in)(?:$|[_/\-])", search_text))
    is_register_like = method == "POST" and bool(
        re.search(r"(?:^|[_/\-])(register|signup|sign_up|users?)(?:$|[_/\-])", search_text)
    )
    return OpMeta(
        operation_id=operation_id,
        method=method,
        path=path,
        segments=segments,
        path_params=path_params,
        is_read=is_read,
        is_write=is_write,
        is_collection_create=is_collection_create,
        is_instance_or_child=is_instance_or_child,
        is_auth_like=is_auth_like,
        is_register_like=is_register_like,
    )


def _is_param(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _strip_braces(segment: str) -> str:
    return segment[1:-1] if _is_param(segment) else segment


def _base_segments(meta: OpMeta) -> tuple[str, ...]:
    out: list[str] = []
    for segment in meta.segments:
        if _is_param(segment):
            break
        out.append(segment.lower())
    return tuple(out)


def _same_resource_family(left: OpMeta, right: OpMeta) -> bool:
    left_base = _base_segments(left)
    right_base = _base_segments(right)
    return bool(left_base and right_base and (left_base == right_base))


def _same_canonical_path(left: OpMeta, right: OpMeta) -> bool:
    return left.path == right.path


def _schema_required_leaves(schema: dict, prefix: str = "$") -> list[str]:
    """Return JSONPath leaves along required object properties."""
    out = []
    if not isinstance(schema, dict):
        return out
    if schema.get("type") == "object" or "properties" in schema:
        required = schema.get("required", [])
        props = schema.get("properties", {})
        for name in required:
            sub = props.get(name, {})
            child = f"{prefix}.{name}"
            if isinstance(sub, dict) and ("properties" in sub or sub.get("type") == "object"):
                out.extend(_schema_required_leaves(sub, child))
            else:
                out.append(child)
    return out


def _request_inputs(op: dict) -> list[tuple[str, str]]:
    """Replay-relevant request inputs.

    Required inputs are always kept.  A small class of optional search query
    parameters is also kept when observed, because omitting them changes the
    response shape and breaks downstream value bindings such as product search
    -> add-to-basket ProductId.
    """
    inputs: list[tuple[str, str]] = []
    for p in op.get("parameters", []):
        if p["in"] == "path":
            inputs.append(("path", p["name"]))
        elif p["in"] == "query" and (p.get("required") or _replay_relevant_optional_query(p)):
            inputs.append(("query", p["name"]))
        elif p["in"] == "header" and p.get("required") and p["name"].lower() != "authorization":
            inputs.append(("header", p["name"]))
    body = op.get("requestBody")
    if body:
        for media in body.get("content", {}).values():
            for leaf in _schema_required_leaves(media.get("schema", {})):
                inputs.append(("body", leaf))
            break
    return inputs


def _replay_relevant_optional_query(param: dict) -> bool:
    name = str(param.get("name") or "").lower()
    if name not in SEARCH_QUERY_NAMES:
        return False
    counts = param.get("x-carverflow-counts")
    if not isinstance(counts, dict):
        return True
    return int(counts.get("n_present") or 0) > 0


def _dependency_slots(op: dict, meta: OpMeta) -> list[tuple[str, str]]:
    """Slots that Stage 5 may fill from dependency graph evidence.

    Most collection-create POST body fields stay as parameters/materials: blindly
    binding old response values into a create body creates brittle replay and can
    turn recorded literals into false fresh grounding.  Reference-like body
    fields are different: values such as BasketId, ProductId, ownerId, roomid, or
    slug commonly bind a write request to an already selected resource/context,
    so they can safely consume dependency-graph evidence.
    """
    slots: list[tuple[str, str]] = []
    for location, field in _request_inputs(op):
        if location == "body" and meta.is_collection_create and not _body_slot_dependency_allowed(field):
            continue
        if location == "body" and meta.method == "POST":
            if not _body_slot_dependency_allowed(field):
                continue
        slots.append((location, field))
    return slots


def _dependency_slots_for_graph(
    operation_id: str,
    op: dict,
    meta: OpMeta,
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
) -> list[tuple[str, str]]:
    slots = set(_dependency_slots(op, meta))
    for consumer, location, field in data_by_slot:
        if consumer != operation_id:
            continue
        if location == "header" and _dynamic_capability_header_allowed(field):
            slots.add((location, field))
    return sorted(slots)


def _observation_refs(detail: dict) -> tuple:
    refs = []
    for ref in detail.get("observation_refs", []) or []:
        refs.append((
            ref.get("producer_ref", {}).get("run_id"),
            ref.get("producer_ref", {}).get("entry_index"),
            ref.get("consumer_ref", {}).get("run_id"),
            ref.get("consumer_ref", {}).get("entry_index"),
        ))
    return tuple(refs)


def _binding_plans(dep_graph: dict, metas: dict[str, OpMeta]) -> list[BindingPlan]:
    plans: list[BindingPlan] = []
    ready = set(metas)
    for edge in dep_graph.get("edges") or []:
        producer = edge.get("producer")
        consumer = edge.get("consumer")
        edge_kind = edge.get("kind")
        if producer not in ready or consumer not in ready:
            continue
        if edge_kind not in {"data", "auth"}:
            continue
        for evidence in edge.get("evidence") or []:
            detail = evidence.get("detail") or {}
            to_location = detail.get("to_location")
            to_field = detail.get("to_field")
            if not to_location or not to_field:
                continue
            kind = "auth" if to_location == "header" and str(to_field).lower() == "authorization" else "data"
            score = _edge_score(edge, evidence, detail, metas[producer], metas[consumer], kind)
            plans.append(BindingPlan(
                producer=producer,
                from_location=detail.get("from_location", FROM_RESPONSE_BODY),
                from_field=detail.get("from_field", AUTH_FROM_FIELD if kind == "auth" else ""),
                consumer=consumer,
                to_location=to_location,
                to_field=to_field,
                observation_refs=_observation_refs(detail),
                kind=kind,
                score=score,
            ))
    return plans


def project_binding_plans(observed_structure: dict, dependency_graph: dict) -> tuple[BindingPlan, ...]:
    """Project every evidence-backed binding opportunity without selecting a sequence.

    This is the public, side-effect-free Stage5 projection boundary for the
    pre-proposal pipeline.  It intentionally does not call candidate
    enumeration, ranking, sequence selection, or materialization.
    """
    operations = _operation_entries(observed_structure)
    plans = _binding_plans(dependency_graph, _op_metadata(operations))
    return tuple(sorted(plans, key=lambda item: (
        item.producer,
        item.consumer,
        item.kind,
        item.from_location,
        item.from_field,
        item.to_location,
        item.to_field,
        item.observation_refs,
    )))


def _order_plans(dep_graph: dict, metas: dict[str, OpMeta]) -> list[OrderPlan]:
    plans: list[OrderPlan] = []
    ready = set(metas)
    for edge in dep_graph.get("edges") or []:
        if edge.get("kind") != "semantic_order":
            continue
        producer = edge.get("producer")
        consumer = edge.get("consumer")
        if producer not in ready or consumer not in ready:
            continue
        semantic_evidence = [
            evidence
            for evidence in edge.get("evidence") or []
            if evidence.get("type") == "business_semantic"
        ]
        if not semantic_evidence:
            raise ValueError(f"semantic_order {producer}->{consumer} has no audit reference")
        for evidence in semantic_evidence:
            detail = evidence["detail"]
            audit_ref = detail["audit_ref"]
            plans.append(
                OrderPlan(
                    producer=producer,
                    consumer=consumer,
                    semantic_edge_id=detail["semantic_edge_id"],
                    audit_ref=(audit_ref["run_id"], audit_ref["path"], audit_ref["record_id"]),
                )
            )
    plans.sort(key=_order_key)
    _validate_order_acyclic(plans)
    return plans


def _order_key(plan: OrderPlan) -> tuple[str, str, str]:
    return (plan.producer, plan.consumer, plan.semantic_edge_id)


def _validate_order_acyclic(plans: list[OrderPlan]) -> None:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for plan in plans:
        adjacency[plan.producer].append(plan.consumer)
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycle = visiting[visiting.index(node) :] + [node]
            raise ValueError(f"semantic_order cycle: {' -> '.join(cycle)}")
        if node in visited:
            return
        visiting.append(node)
        for consumer in sorted(adjacency.get(node, [])):
            visit(consumer)
        visiting.pop()
        visited.add(node)

    for node in sorted(adjacency):
        visit(node)


def _edge_score(edge: dict, evidence: dict, detail: dict, producer: OpMeta, consumer: OpMeta, kind: str) -> float:
    confidence = float(edge.get("confidence") or 0)
    score = confidence * 100
    if evidence.get("type") == "exact_value_flow":
        score += 35
    score += min(len(detail.get("observation_refs") or []), 10) * 3
    to_location = str(detail.get("to_location") or "")
    to_field = str(detail.get("to_field") or "")
    from_field = str(detail.get("from_field") or "")
    if kind == "auth":
        if to_location == "header" and to_field.lower() == "authorization":
            score += 120
        if producer.is_auth_like:
            score += 100
        if producer.is_register_like:
            score -= 80
        if re.search(r"(token|session|jwt|auth)", from_field, re.I):
            score += 20
        return score

    if to_location in {"path", "query"}:
        score += 40
    if to_location == "header" and _dynamic_capability_header_allowed(to_field):
        score += 80
        if re.search(r"(token|session|csrf|api[-_]?key|apikey)", f"{from_field} {to_field}", re.I):
            score += 35
    if _looks_identifier_field(from_field) and to_location in {"path", "query", "body"}:
        score += 35
    score += _resource_identity_alignment_score(from_field, to_location, to_field, producer, consumer)
    if producer.is_collection_create and consumer.is_instance_or_child and _same_resource_family(producer, consumer):
        score += 110
    elif _same_resource_family(producer, consumer):
        score += 25
    if producer.method == "DELETE":
        score -= 50
    if _is_list_index_field(from_field):
        score += 75 if producer.is_write else -25
    if consumer.method == "DELETE" and producer.is_collection_create and _same_resource_family(producer, consumer):
        score += 25
    return score


def _resource_identity_alignment_score(
    from_field: str,
    to_location: str,
    to_field: str,
    producer: OpMeta,
    consumer: OpMeta,
) -> float:
    if to_location not in {"path", "query", "body"}:
        return 0
    source_stem = _identifier_stem(from_field)
    if not source_stem:
        return 0
    target_stem = _identifier_stem(to_field)
    consumer_resource = _last_resource_token(_base_segments(consumer))
    producer_resources = set(_resource_tokens(producer))

    if to_location == "body" and target_stem:
        if source_stem == target_stem:
            return 120 if target_stem in producer_resources else 75
        if source_stem == "id":
            return 100 if target_stem in producer_resources else -120
        if len(source_stem) <= 2 and target_stem.startswith(source_stem):
            return 80
        return -100

    if consumer_resource:
        if source_stem == consumer_resource:
            return 100
        if source_stem == "id":
            return 60 if consumer_resource in producer_resources else -80
        if len(source_stem) <= 2 and consumer_resource.startswith(source_stem):
            return 70
        if source_stem in producer_resources and source_stem != consumer_resource:
            return -90
    return 0


def _body_slot_dependency_allowed(field: str) -> bool:
    return _looks_identifier_field(field)


def _dynamic_capability_header_allowed(field: str) -> bool:
    name = str(field or "").strip().lower()
    if not name or name == "authorization" or name in DENY_DYNAMIC_HEADER_BINDING:
        return False
    if name.startswith("sec-"):
        return False
    if name.startswith("x-"):
        return True
    return bool(re.search(r"(token|session|csrf|api[-_]?key|apikey)", name))


def _looks_identifier_field(field: str) -> bool:
    tail = _field_tail(field)
    tail_l = tail.lower()
    if tail_l in {"id", "slug", "uuid", "username", "code", "key"}:
        return True
    if tail_l in {"valid", "invalid", "paid", "unpaid"}:
        return False
    if re.search(r"(?:^|[_\-.])[a-z0-9]*(id|slug|uuid|username|code|key)(?:$|[_\-.])", tail_l):
        return True
    if re.search(r"[A-Z][A-Za-z0-9]*(Id|Slug|UUID|Code|Key)$", tail):
        return True
    return bool(tail_l.endswith("id") and len(tail_l) > 2)


def _identifier_stem(field: str) -> str | None:
    tail = _field_tail(field)
    tail_l = tail.lower()
    if tail_l in {"id", "slug", "uuid", "username", "code", "key"}:
        return tail_l
    for suffix in ("uuid", "slug", "username", "code", "key", "id"):
        if tail_l.endswith(suffix) and len(tail_l) > len(suffix):
            return _resource_token(tail_l[: -len(suffix)])
    if re.search(r"(Id|Slug|UUID|Code|Key)$", tail):
        stem = re.sub(r"(Id|Slug|UUID|Code|Key)$", "", tail)
        return _resource_token(stem)
    return None


def _field_tail(field: str) -> str:
    field = str(field or "")
    if field.startswith("$."):
        field = field[2:]
    field = re.sub(r"\[\d+\]", "", field)
    parts = re.split(r"[./]", field)
    return (parts[-1] if parts else field).strip("{}[]")


def _resource_token(segment: str) -> str:
    token = str(segment or "").lower()
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def _resource_tokens(meta: OpMeta) -> tuple[str, ...]:
    tokens = [_resource_token(segment) for segment in meta.segments if not _is_param(segment)]
    while tokens and (tokens[0] in {"api", "rest"} or re.fullmatch(r"v\d+", tokens[0])):
        tokens.pop(0)
    if tokens and tokens[-1] in {"search", "list", "index", "all"}:
        tokens.pop()
    return tuple(tokens)


def _last_resource_token(segments: tuple[str, ...]) -> str | None:
    tokens = [_resource_token(segment) for segment in segments if not _is_param(segment)]
    while tokens and (tokens[0] in {"api", "rest"} or re.fullmatch(r"v\d+", tokens[0])):
        tokens.pop(0)
    if tokens and tokens[-1] in {"search", "list", "index", "all"}:
        tokens.pop()
    return tokens[-1] if tokens else None


def _is_list_index_field(field: str) -> bool:
    return bool(re.search(r"\[\d+\]", field))


def _source_rank(plan: BindingPlan) -> tuple:
    return (
        -plan.score,
        plan.producer,
        plan.from_location,
        _field_depth(plan.from_field),
        plan.from_field,
        plan.observation_refs,
    )


def _field_depth(from_field: str) -> int:
    if not from_field:
        return 0
    if from_field.startswith("$."):
        body_path = from_field[2:]
        if not body_path:
            return 0
        return body_path.count(".") + body_path.count("[") + 1
    if from_field.startswith("xml:"):
        return len([part for part in from_field[4:].split("/") if part])
    if from_field.startswith("location."):
        return 1
    return 1


def _index_plans(plans: Iterable[BindingPlan]) -> tuple[dict, dict]:
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]] = defaultdict(list)
    auth_by_consumer: dict[str, list[BindingPlan]] = defaultdict(list)
    for plan in plans:
        if plan.kind == "auth":
            if plan.to_location == "header" and plan.to_field.lower() == "authorization":
                auth_by_consumer[plan.consumer].append(plan)
        elif plan.kind == "data":
            data_by_slot[(plan.consumer, plan.to_location, plan.to_field)].append(plan)
    for values in data_by_slot.values():
        values.sort(key=_source_rank)
    for values in auth_by_consumer.values():
        values.sort(key=_source_rank)
    return data_by_slot, auth_by_consumer


def _index_orders(plans: Iterable[OrderPlan]) -> dict[str, list[OrderPlan]]:
    by_consumer: dict[str, list[OrderPlan]] = defaultdict(list)
    for plan in plans:
        by_consumer[plan.consumer].append(plan)
    for values in by_consumer.values():
        values.sort(key=_order_key)
    return by_consumer


def _best_auth(consumer: str, auth_by_consumer: dict[str, list[BindingPlan]], excluded: set[str] | None = None) -> BindingPlan | None:
    excluded = excluded or set()
    for plan in auth_by_consumer.get(consumer, []):
        if plan.producer not in excluded and plan.producer != consumer:
            return plan
    return None


def _best_data(
    consumer: str,
    slot: tuple[str, str],
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
    *,
    allowed_producers: set[str] | None = None,
    excluded: set[str] | None = None,
) -> BindingPlan | None:
    excluded = excluded or set()
    candidates = data_by_slot.get((consumer, slot[0], slot[1]), [])
    for plan in candidates:
        if plan.producer == consumer or plan.producer in excluded:
            continue
        if allowed_producers is not None and plan.producer not in allowed_producers:
            continue
        return plan
    return None


def _dependency_order(
    target: str,
    ops: dict[str, dict],
    metas: dict[str, OpMeta],
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
    auth_by_consumer: dict[str, list[BindingPlan]],
    order_by_consumer: dict[str, list[OrderPlan]],
) -> tuple[str, ...]:
    order: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(operation_id: str) -> None:
        if operation_id in visited or operation_id not in ops:
            return
        if operation_id in visiting:
            return
        visiting.add(operation_id)
        for plan in order_by_consumer.get(operation_id, []):
            visit(plan.producer)
        meta = metas[operation_id]
        for slot in _dependency_slots_for_graph(operation_id, ops[operation_id], meta, data_by_slot):
            plan = _best_data(operation_id, slot, data_by_slot, excluded=visiting)
            if plan is not None:
                visit(plan.producer)
        auth = _best_auth(operation_id, auth_by_consumer, excluded=visiting)
        if auth is not None:
            visit(auth.producer)
        visiting.remove(operation_id)
        visited.add(operation_id)
        order.append(operation_id)

    visit(target)
    return tuple(order)


def _orders_for_steps(steps: tuple[str, ...], order_plans: list[OrderPlan]) -> tuple[OrderPlan, ...]:
    position = {operation_id: index for index, operation_id in enumerate(steps)}
    return tuple(
        plan
        for plan in order_plans
        if plan.producer in position
        and plan.consumer in position
        and position[plan.producer] < position[plan.consumer]
    )


def _bindings_for_steps(
    steps: tuple[str, ...],
    ops: dict[str, dict],
    metas: dict[str, OpMeta],
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
    auth_by_consumer: dict[str, list[BindingPlan]],
) -> tuple[BindingPlan, ...]:
    available: set[str] = set()
    bindings: list[BindingPlan] = []
    seen: set[tuple] = set()
    for operation_id in steps:
        meta = metas[operation_id]
        for slot in _dependency_slots_for_graph(operation_id, ops[operation_id], meta, data_by_slot):
            plan = _best_data(operation_id, slot, data_by_slot, allowed_producers=available)
            if plan is not None:
                key = (plan.producer, plan.consumer, plan.to_location, plan.to_field, plan.from_location, plan.from_field)
                if key not in seen:
                    bindings.append(plan)
                    seen.add(key)
        auth = _best_auth(operation_id, auth_by_consumer)
        if auth is not None and auth.producer in available:
            key = (auth.producer, auth.consumer, auth.to_location, auth.to_field, auth.from_location, auth.from_field)
            if key not in seen:
                bindings.append(auth)
                seen.add(key)
        available.add(operation_id)
    return tuple(sorted(bindings, key=lambda p: (
        steps.index(p.consumer),
        p.to_location,
        p.to_field,
        steps.index(p.producer),
        p.from_location,
        p.from_field,
    )))


def _build_candidate(
    steps: Iterable[str],
    reason: str,
    ops: dict[str, dict],
    metas: dict[str, OpMeta],
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
    auth_by_consumer: dict[str, list[BindingPlan]],
    order_plans: list[OrderPlan],
) -> Candidate | None:
    deduped: list[str] = []
    seen = set()
    for step in steps:
        if step not in ops or step in seen:
            continue
        deduped.append(step)
        seen.add(step)
    if not deduped or len(deduped) > MAX_STEPS:
        return None
    step_tuple = tuple(deduped)
    bindings = _bindings_for_steps(step_tuple, ops, metas, data_by_slot, auth_by_consumer)
    orders = _orders_for_steps(step_tuple, order_plans)
    score = _candidate_score(step_tuple, bindings, orders, metas, reason)
    return Candidate(step_tuple, bindings, orders, score, reason)


def _candidate_score(
    steps: tuple[str, ...],
    bindings: tuple[BindingPlan, ...],
    orders: tuple[OrderPlan, ...],
    metas: dict[str, OpMeta],
    reason: str,
) -> float:
    covered = set(steps)
    write_count = sum(1 for op in covered if metas[op].is_write)
    read_count = sum(1 for op in covered if metas[op].is_read)
    path_bindings = sum(1 for b in bindings if b.kind == "data" and b.to_location in {"path", "query"})
    auth_bindings = sum(1 for b in bindings if b.kind == "auth")
    score = len(covered) * 25 + write_count * 16 + read_count * 8
    score += len(bindings) * 7 + path_bindings * 10 + auth_bindings * 8
    score += len(orders) * 30
    if any(metas[op].is_collection_create for op in covered) and any(metas[op].is_instance_or_child for op in covered):
        score += 45
    if len(steps) > 1:
        score += 20
    if reason.startswith("write_read") or reason.startswith("child") or reason.startswith("action"):
        score += 35
    if len(steps) == 1 and metas[steps[0]].is_collection_create:
        score -= 40
    score -= max(0, len(steps) - 6) * 4
    return score


def _can_bind_required_inputs(
    steps: tuple[str, ...],
    target: str,
    ops: dict[str, dict],
    metas: dict[str, OpMeta],
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
) -> bool:
    available = set(steps)
    for slot in _dependency_slots_for_graph(target, ops[target], metas[target], data_by_slot):
        if slot[0] in {"path", "query"} and _best_data(target, slot, data_by_slot, allowed_producers=available) is None:
            return False
    return True


def _has_direct_data_flow(
    producer: str,
    consumer: str,
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
) -> bool:
    for (slot_consumer, _location, _field), plans in data_by_slot.items():
        if slot_consumer != consumer:
            continue
        if any(plan.producer == producer for plan in plans):
            return True
    return False


def _uses_direct_data_flow(candidate: Candidate, producer: str, consumer: str) -> bool:
    return any(
        binding.producer == producer
        and binding.consumer == consumer
        and binding.kind == "data"
        for binding in candidate.bindings
    )


def _enumerate_candidates(
    ops: dict[str, dict],
    metas: dict[str, OpMeta],
    data_by_slot: dict[tuple[str, str, str], list[BindingPlan]],
    auth_by_consumer: dict[str, list[BindingPlan]],
    order_plans: list[OrderPlan],
    order_by_consumer: dict[str, list[OrderPlan]],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for target in sorted(ops):
        order = _dependency_order(target, ops, metas, data_by_slot, auth_by_consumer, order_by_consumer)
        candidate = _build_candidate(
            order,
            f"target:{target}",
            ops,
            metas,
            data_by_slot,
            auth_by_consumer,
            order_plans,
        )
        if candidate is not None:
            candidates.append(candidate)

    for base in list(candidates):
        last = base.steps[-1]
        last_meta = metas[last]
        if not last_meta.is_write or last_meta.method == "DELETE":
            continue
        for follow in sorted(ops):
            if follow in base.steps:
                continue
            follow_meta = metas[follow]
            if last_meta.method in {"PUT", "PATCH"} and not _has_direct_data_flow(last, follow, data_by_slot):
                continue
            if not _same_resource_family(last_meta, follow_meta):
                continue
            if follow_meta.method == "DELETE" and not _same_canonical_path(last_meta, follow_meta):
                continue
            if not (follow_meta.is_read or follow_meta.method == "DELETE" or _same_canonical_path(last_meta, follow_meta)):
                continue
            if not _can_bind_required_inputs(base.steps, follow, ops, metas, data_by_slot):
                continue
            reason = "write_read_follow"
            if follow_meta.method == "DELETE" or _same_canonical_path(last_meta, follow_meta):
                reason = "action_or_lifecycle_follow"
            if len(_base_segments(follow_meta)) > len(_base_segments(last_meta)) or len(follow_meta.segments) > len(last_meta.segments):
                reason = "child_write_read_follow"
            candidate = _build_candidate(
                base.steps + (follow,),
                reason,
                ops,
                metas,
                data_by_slot,
                auth_by_consumer,
                order_plans,
            )
            if candidate is not None:
                if last_meta.method in {"PUT", "PATCH"} and not _uses_direct_data_flow(candidate, last, follow):
                    continue
                candidates.append(candidate)
    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    by_key: dict[tuple, Candidate] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        existing = by_key.get(key)
        if existing is None or _candidate_sort_key(candidate) < _candidate_sort_key(existing):
            by_key[key] = candidate
    return sorted(by_key.values(), key=_candidate_sort_key)


def _candidate_key(candidate: Candidate) -> tuple:
    return (
        candidate.steps,
        tuple(sorted(
            (b.producer, b.consumer, b.from_location, b.from_field, b.to_location, b.to_field)
            for b in candidate.bindings
        )),
        tuple(_order_key(order) for order in candidate.orders),
    )


def _candidate_sort_key(candidate: Candidate) -> tuple:
    return (-candidate.score, candidate.steps, tuple((b.consumer, b.to_location, b.to_field, b.producer, b.from_field) for b in candidate.bindings))


def _binding_key(binding: BindingPlan) -> tuple:
    return (
        binding.producer,
        binding.consumer,
        binding.kind,
        binding.from_location,
        binding.from_field,
        binding.to_location,
        binding.to_field,
    )


def _select_candidates(candidates: list[Candidate], metas: dict[str, OpMeta]) -> list[Candidate]:
    if not candidates:
        return []
    limit = min(30, max(12, len(metas) * MAX_SELECTED_FACTOR))
    selected: list[Candidate] = []
    covered_ops: set[str] = set()
    covered_edges: set[tuple] = set()
    covered_orders: set[tuple[str, str, str]] = set()
    remaining = list(candidates)

    while remaining and len(selected) < limit:
        best_index = -1
        best_rank = None
        for index, candidate in enumerate(remaining):
            new_ops = set(candidate.steps) - covered_ops
            new_edges = {_binding_key(b) for b in candidate.bindings} - covered_edges
            new_orders = {_order_key(order) for order in candidate.orders} - covered_orders
            if not new_ops and not new_edges and not new_orders:
                continue
            rank = (
                -(len(new_ops) * 100
                  + sum(45 for op in new_ops if metas[op].is_write)
                  + sum(15 for op in new_ops if metas[op].is_read)
                  + len(new_edges) * 30
                  + len(new_orders) * 60
                  + int(candidate.score)),
                len(candidate.steps),
                candidate.steps,
            )
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_index = index
        if best_index < 0:
            break
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        covered_ops.update(chosen.steps)
        covered_edges.update(_binding_key(b) for b in chosen.bindings)
        covered_orders.update(_order_key(order) for order in chosen.orders)

    # If any operation is still uncovered, keep its strongest target candidate.
    for operation_id in sorted(set(metas) - covered_ops):
        fallback = next((c for c in candidates if c.steps[-1] == operation_id), None)
        if fallback is None or len(selected) >= limit:
            continue
        selected.append(fallback)
        covered_ops.update(fallback.steps)
        covered_edges.update(_binding_key(b) for b in fallback.bindings)
        covered_orders.update(_order_key(order) for order in fallback.orders)

    for operation_id, meta in sorted(metas.items()):
        if meta.method not in {"PUT", "PATCH"}:
            continue
        if any(candidate.steps[-1] == operation_id for candidate in selected):
            continue
        fallback = next((c for c in candidates if c.steps[-1] == operation_id), None)
        if fallback is None or len(selected) >= limit:
            continue
        selected.append(fallback)
        covered_ops.update(fallback.steps)
        covered_edges.update(_binding_key(b) for b in fallback.bindings)
        covered_orders.update(_order_key(order) for order in fallback.orders)

    selected = _drop_redundant_unsafe_standalone_deletes(selected, metas)
    return _dedupe_candidates(selected)


def _drop_redundant_unsafe_standalone_deletes(candidates: list[Candidate], metas: dict[str, OpMeta]) -> list[Candidate]:
    out: list[Candidate] = []
    for candidate in candidates:
        if not _unsafe_standalone_delete(candidate, metas):
            out.append(candidate)
            continue
        delete_meta = metas[candidate.steps[0]]
        redundant = any(
            other is not candidate
            and _has_bound_delete_in_same_resource_family(other, delete_meta, metas)
            for other in candidates
        )
        if not redundant:
            out.append(candidate)
    return out


def _unsafe_standalone_delete(candidate: Candidate, metas: dict[str, OpMeta]) -> bool:
    if len(candidate.steps) != 1:
        return False
    op_id = candidate.steps[0]
    meta = metas.get(op_id)
    if meta is None or meta.method != "DELETE":
        return False
    return not any(
        binding.consumer == op_id
        and binding.kind == "data"
        and binding.to_location in {"path", "query"}
        for binding in candidate.bindings
    )


def _has_bound_delete_in_same_resource_family(candidate: Candidate, delete_meta: OpMeta, metas: dict[str, OpMeta]) -> bool:
    for op_id in candidate.steps:
        meta = metas.get(op_id)
        if meta is None or meta.method != "DELETE" or not _same_resource_family(meta, delete_meta):
            continue
        if any(
            binding.consumer == op_id
            and binding.kind == "data"
            and binding.to_location in {"path", "query"}
            for binding in candidate.bindings
        ):
            return True
    return False


def _sequence_binding_record(binding: BindingPlan, step_index: dict[str, int]) -> dict:
    return {
        "from_step": step_index[binding.producer],
        "from_location": binding.from_location,
        "from_field": binding.from_field,
        "to_step": step_index[binding.consumer],
        "to_location": binding.to_location,
        "to_field": binding.to_field,
    }


def _parameters_for_steps(steps: tuple[str, ...], bindings: tuple[BindingPlan, ...], ops: dict[str, dict]) -> list[dict]:
    step_index = {op_id: index for index, op_id in enumerate(steps)}
    covered = {
        (step_index[b.consumer], b.to_location, b.to_field)
        for b in bindings
        if b.consumer in step_index
    }
    parameters: list[dict] = []
    for op_id in steps:
        to_step = step_index[op_id]
        for to_location, to_field in _request_inputs(ops[op_id]):
            if (to_step, to_location, to_field) in covered:
                continue
            parameters.append({
                "name": f"p{to_step}_{to_location}_{to_field.replace('$.', '').replace('.', '_').replace('[', '_').replace(']', '')}",
                "to_step": to_step,
                "to_location": to_location,
                "to_field": to_field,
                "required": True,
            })
    return sorted(parameters, key=lambda x: (x["to_step"], x["to_location"], x["to_field"], x["name"]))


def _materialize(candidate: Candidate, seq: int, ops: dict[str, dict]) -> tuple[dict, dict]:
    step_index = {op_id: index for index, op_id in enumerate(candidate.steps)}
    bindings = [
        _sequence_binding_record(binding, step_index)
        for binding in candidate.bindings
        if binding.producer in step_index and binding.consumer in step_index
    ]
    bindings.sort(key=lambda x: (
        x["to_step"],
        x["to_location"],
        x["to_field"],
        x["from_step"],
        x["from_location"],
        x["from_field"],
    ))
    parameters = _parameters_for_steps(candidate.steps, candidate.bindings, ops)
    sequence = {
        "sequence_id": f"seq_{seq:04d}",
        "steps": list(candidate.steps),
        "bindings": bindings,
        "status": "candidate",
    }
    skill = {
        "skill_id": f"skill_{seq:04d}",
        "steps": list(candidate.steps),
        "bindings": bindings,
        "parameters": parameters,
        "status": "candidate",
    }
    return sequence, skill


def synthesize(augmented_oas: dict, dep_graph: dict) -> tuple[list[dict], list[dict]]:
    """Build candidate test sequences from real dependency graph evidence."""
    ops = _operation_entries(augmented_oas)
    if not ops:
        return [], []
    metas = _op_metadata(ops)
    binding_plans = _binding_plans(dep_graph, metas)
    order_plans = _order_plans(dep_graph, metas)
    data_by_slot, auth_by_consumer = _index_plans(binding_plans)
    order_by_consumer = _index_orders(order_plans)
    candidates = _enumerate_candidates(
        ops,
        metas,
        data_by_slot,
        auth_by_consumer,
        order_plans,
        order_by_consumer,
    )
    selected = _select_candidates(candidates, metas)
    sequences: list[dict] = []
    skills: list[dict] = []
    for seq, candidate in enumerate(selected, start=1):
        sequence, skill = _materialize(candidate, seq, ops)
        sequences.append(sequence)
        skills.append(skill)
    return sequences, skills
