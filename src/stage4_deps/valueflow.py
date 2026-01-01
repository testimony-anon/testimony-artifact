"""Exact value-flow extraction and dependency-edge inference (005 D36/D37/D39 + 005A rulings).

Looks up the real literal values in the session_bundle HAR behind the observations of augmented_oas:
- producer side: response-body leaf values / whole response-header values -> value index (low-cardinality exclusion, both-ends success gate);
- consumer side: request path segments / query / header (scheme-aware Authorization + whole values of ordinary headers) / body leaf literals;
- exact equality match + temporal order (consumer not earlier than producer) + same-entry self-echo exclusion + conservative same-session rule;
- converge into edges keyed by (producer, consumer); multiple value-flow channels become multiple evidence items (S4).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit, parse_qsl

from common.xml_valueflow import is_xml_field, is_xml_id_like_field, iter_xml_scalar_values
from common.location_link_valueflow import is_location_path_field, iter_location_path_values, parse_link_header
from common.oas_discovery import is_execution_ready
from stage2_recover.loader import LoadedBundle

from .lowcard import is_low_card

AUTH_SCHEMES = ("Token ", "Bearer ")

FROM_RESPONSE_BODY = "response_body"
FROM_RESPONSE_HEADER = "response_header"

RESPONSE_HEADER_EXCLUDE = {
    "accept-ranges",
    "cache-control",
    "connection",
    "content-encoding",
    "content-length",
    "content-type",
    "date",
    "expires",
    "keep-alive",
    "link",
    "location",
    "pragma",
    "server",
    "set-cookie",
    "strict-transport-security",
    "transfer-encoding",
    "vary",
    "traceparent",
    "tracestate",
    "x-content-type-options",
    "x-correlation-id",
    "x-frame-options",
    "x-powered-by",
    "x-request-id",
    "x-runtime",
}
RESPONSE_HEADER_PREFIX_EXCLUDE = (
    "access-control-",
    "cf-",
    "x-amzn-trace-id",
    "x-correlation-id",
    "x-envoy-",
)

REQUEST_HEADER_EXCLUDE = {
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "connection",
    "content-length",
    "content-type",
    "cookie",
    "host",
    "origin",
    "pragma",
    "referer",
    "upgrade-insecure-requests",
    "user-agent",
    "traceparent",
    "tracestate",
    "x-correlation-id",
    "x-csrf",
    "x-csrf-token",
    "x-request-id",
    "x-requested-with",
    "x-xsrf",
    "x-xsrf-token",
}
REQUEST_HEADER_PREFIX_EXCLUDE = ("sec-",)
_INT_STRING = re.compile(r"^-?\d+$")
_REDACTED_SCALAR = re.compile(r"^\[REDACTED:[0-9a-fA-F]+\]$")
_REDACTED_ORIGIN = re.compile(r"^\[REDACTED:[0-9a-fA-F]+\](?=/|$)")


def _is_success(status: int) -> bool:
    return 200 <= status < 400


def _is_redacted_scalar(value: object) -> bool:
    return isinstance(value, str) and _REDACTED_SCALAR.fullmatch(value) is not None


def _split_recorded_url(value: str):
    match = _REDACTED_ORIGIN.match(value)
    if match is not None:
        value = "http://recorded.invalid" + (value[match.end():] or "/")
    return urlsplit(value)


def _iter_leaves(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_leaves(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_leaves(v, f"{path}[{i}]")
    else:
        yield path, obj


def _parse_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _response_content_type(entry: dict) -> str | None:
    content = entry.get("response", {}).get("content", {})
    if content.get("mimeType"):
        return str(content["mimeType"])
    for h in entry.get("response", {}).get("headers", []):
        if str(h.get("name", "")).lower() == "content-type":
            return _header_value(h)
    return None


def _is_low_card_xml_value(from_field: str, value: object) -> bool:
    if not is_low_card(value):
        return False
    if isinstance(value, str) and _INT_STRING.fullmatch(value.strip()) \
            and len(value.strip()) > 2 and is_xml_id_like_field(from_field):
        return False
    return True


def _is_json_numeric_id_like_field(from_field: str, value: object) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        pass
    elif isinstance(value, str) and _INT_STRING.fullmatch(value.strip()):
        pass
    else:
        return False
    terminal = _json_field_tail(from_field)
    return terminal == "id" or terminal.endswith("id") or terminal in {"number", "index"}


def _json_field_tail(field: str) -> str:
    terminal = str(field).rsplit(".", 1)[-1]
    return terminal.split("[", 1)[0].lower()


def _json_id_body_fields_compatible(from_field: str, to_field: str) -> bool:
    source = _json_field_tail(from_field)
    target = _json_field_tail(to_field)
    if not (source == "id" or source.endswith("id") or source in {"number", "index"}):
        return False
    if not (target == "id" or target.endswith("id") or target in {"number", "index"}):
        return False
    if source in {"number", "index"} or target in {"number", "index"}:
        return source == target
    if source == "id" or source == target:
        return True
    source_stem = source[:-2]
    target_stem = target[:-2]
    return 0 < len(source_stem) <= 2 and target_stem.startswith(source_stem)


def _low_card_bypass_producer(prod: ProducerOcc, value: object, to_location: str, to_field: str) -> bool:
    if (
        prod.from_location == FROM_RESPONSE_BODY
        and is_xml_field(prod.from_field)
        and is_xml_id_like_field(prod.from_field)
    ):
        return True
    if (
        to_location in {"path", "query"}
        and prod.from_location == FROM_RESPONSE_BODY
        and _is_json_numeric_id_like_field(prod.from_field, value)
    ):
        return True
    if (
        to_location == "body"
        and prod.from_location == FROM_RESPONSE_BODY
        and _is_json_numeric_id_like_field(prod.from_field, value)
        and _is_json_numeric_id_like_field(to_field, value)
        and _json_id_body_fields_compatible(prod.from_field, to_field)
    ):
        return True
    return (
        to_location in {"path", "query"}
        and prod.from_location == FROM_RESPONSE_HEADER
        and is_location_path_field(prod.from_field)
    )


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


@dataclass(frozen=True)
class ObsRef:
    run_id: str
    entry_index: int


@dataclass
class ProducerOcc:
    op: str
    ref: ObsRef
    from_location: str
    from_field: str
    ts: float


@dataclass
class Candidate:
    producer_op: str
    consumer_op: str
    from_location: str
    from_field: str
    to_location: str
    to_field: str
    producer_ref: ObsRef
    consumer_ref: ObsRef


@dataclass
class Stage4Inputs:
    augmented_oas: dict
    bundles: dict[str, LoadedBundle]


def _canonical_params(canonical_path: str, concrete_url: str) -> list[tuple[str, str]]:
    """Align the path segments of a concrete URL with the canonical template and take the literal at each {param} position."""
    can_segs = canonical_path.strip("/").split("/")
    conc_path = _split_recorded_url(concrete_url).path.rstrip("/") or "/"
    conc_segs = conc_path.strip("/").split("/")
    out = []
    if len(can_segs) != len(conc_segs):
        return out
    for cs, vs in zip(can_segs, conc_segs):
        if cs.startswith("{") and cs.endswith("}"):
            out.append((cs[1:-1], vs))  # (to_field=param name, literal value)
    return out


def _canonical_header_name(name: str) -> str:
    return name.strip().lower()


def _header_value(header: dict) -> str | None:
    value = header.get("value")
    if value is None:
        return None
    return str(value)


def _is_response_header_noise(name: str) -> bool:
    canonical = _canonical_header_name(name)
    return canonical in RESPONSE_HEADER_EXCLUDE or any(
        canonical.startswith(prefix) for prefix in RESPONSE_HEADER_PREFIX_EXCLUDE)


def _is_request_header_noise(name: str) -> bool:
    canonical = _canonical_header_name(name)
    return canonical in REQUEST_HEADER_EXCLUDE or any(
        canonical.startswith(prefix) for prefix in REQUEST_HEADER_PREFIX_EXCLUDE)


def _is_create_location_response(entry: dict, status: int) -> bool:
    method = str(entry.get("request", {}).get("method", "")).upper()
    return status == 201 and method in {"POST", "PUT", "PATCH"}


def _filtered_counts() -> dict:
    return {"producer_nonsuccess": 0, "consumer_nonsuccess": 0, "low_card_excluded": 0,
            "same_entry_echo": 0, "cross_session": 0, "temporal_violation": 0}


def extract_candidates(inp: Stage4Inputs) -> tuple[list[Candidate], dict]:
    """Returns (candidate value-flow list, filtered diagnostic counts)."""
    filtered = _filtered_counts()

    # Collect the observations of each operation (op, canonical_path, ObsRef, status, ts, entry)
    observations: list[tuple[str, str, ObsRef, int, float, dict]] = []
    for canonical_path, item in inp.augmented_oas["paths"].items():
        for method, op in item.items():
            if not is_execution_ready(op):
                continue
            op_id = op["operationId"]
            for o in op["x-carverflow-observations"]:
                if o.get("source") == "stage2_5_probe":
                    # D65: probe observations are not UI value-flow evidence (no session run_id/entry_index): skip them,
                    # keep them out of the value-flow candidates, do not crash; x-carverflow-observations of augmented_oas
                    # already carry their existence. Only this kind is skipped; all others proceed (no other exception is swallowed).
                    continue
                ref = ObsRef(o["run_id"], o["entry_index"])
                bundle = inp.bundles.get(o["run_id"])
                if bundle is None:
                    continue
                entry = bundle.entries[o["entry_index"]]
                observations.append(
                    (op_id, canonical_path, ref, o["status"], _ts(o["timestamp"]), entry))

    # Producer value index: low-cardinality exclusion + successful observations only (both-ends success gate, S5)
    index: dict[str, list[ProducerOcc]] = defaultdict(list)
    for op_id, _cp, ref, status, ts, entry in observations:
        if not _is_success(status):
            filtered["producer_nonsuccess"] += 1
            continue
        body = _parse_json(entry["response"]["content"].get("text"))
        indexed_body_values: set[str] = set()
        if body is not None:
            for from_field, value in _iter_leaves(body):
                if is_low_card(value) and not _is_json_numeric_id_like_field(from_field, value):
                    continue
                index[str(value)].append(ProducerOcc(
                    op_id, ref, FROM_RESPONSE_BODY, from_field, ts))
                indexed_body_values.add(str(value))
        else:
            text = entry["response"]["content"].get("text")
            content_type = _response_content_type(entry)
            for from_field, value in iter_xml_scalar_values(text, content_type):
                if _is_low_card_xml_value(from_field, value):
                    continue
                index[str(value)].append(ProducerOcc(
                    op_id, ref, FROM_RESPONSE_BODY, from_field, ts))
                indexed_body_values.add(str(value))
        for h in entry["response"].get("headers", []):
            name = h.get("name", "")
            canonical = _canonical_header_name(name)
            if canonical == "location" and _is_create_location_response(entry, status):
                value = _header_value(h)
                for from_field, segment in iter_location_path_values(
                    value, entry.get("request", {}).get("url")):
                    if segment in indexed_body_values:
                        # A created entity's identifier that the same response already
                        # carries as a body scalar: the Location header echoes that
                        # scalar, it is not a second, header-only fresh source.  Only
                        # the body occurrence stays indexed; a Location segment absent
                        # from the body keeps its header source as before.
                        continue
                    index[segment].append(ProducerOcc(
                        op_id, ref, FROM_RESPONSE_HEADER, from_field, ts))
                continue
            if canonical == "link":
                # Link is parsed only as a guard/diagnostic shape in this first version;
                # pagination/resource links must not become ordinary data dependencies.
                parse_link_header(_header_value(h))
                continue
            if _is_response_header_noise(name):
                continue
            value = _header_value(h)
            if value is None or is_low_card(value):
                continue
            index[value].append(ProducerOcc(
                op_id, ref, FROM_RESPONSE_HEADER, _canonical_header_name(name), ts))

    # Consumer literal matching
    candidates: list[Candidate] = []
    for op_id, canonical_path, ref, status, ts, entry in observations:
        if not _is_success(status):
            filtered["consumer_nonsuccess"] += 1
            continue
        req = entry["request"]
        literals: list[tuple[str, str, object]] = []  # (to_location, to_field, value)
        # path segments
        for to_field, value in _canonical_params(canonical_path, req["url"]):
            literals.append(("path", to_field, value))
        # query
        for name, value in parse_qsl(_split_recorded_url(req["url"]).query):
            literals.append(("query", name, value))
        # header: Authorization keeps its old special case; ordinary request headers use whole-value exact match only.
        for h in req.get("headers", []):
            name = h.get("name", "")
            canonical = _canonical_header_name(name)
            hv = _header_value(h)
            if hv is None:
                continue
            if canonical == "authorization":
                for scheme in AUTH_SCHEMES:
                    if hv.startswith(scheme):
                        hv = hv[len(scheme):]
                        break
                literals.append(("header", "Authorization", hv))
            elif not _is_request_header_noise(name):
                literals.append(("header", canonical, hv))
        # body
        post = req.get("postData")
        body = _parse_json(post.get("text")) if post else None
        if body is not None:
            for to_field, value in _iter_leaves(body):
                literals.append(("body", to_field, value))

        for to_location, to_field, value in literals:
            if _is_redacted_scalar(value) and not _is_auth_evidence(
                to_location, to_field
            ):
                continue
            producers = index.get(str(value), [])
            if is_low_card(value):
                bypass_producers = [
                    prod for prod in producers
                    if _low_card_bypass_producer(prod, value, to_location, to_field)
                ]
                if not bypass_producers:
                    filtered["low_card_excluded"] += 1
                    continue
                producers = bypass_producers
            for prod in producers:
                if prod.ref == ref:
                    filtered["same_entry_echo"] += 1  # M3: same-entry self-echo
                    continue
                if prod.ref.run_id != ref.run_id:
                    filtered["cross_session"] += 1  # D37: no cross-session edges in V1
                    continue
                if ts < prod.ts:
                    filtered["temporal_violation"] += 1  # D37: consumer must not precede producer
                    continue
                candidates.append(Candidate(
                    producer_op=prod.op, consumer_op=op_id,
                    from_location=prod.from_location, from_field=prod.from_field,
                    to_location=to_location, to_field=to_field,
                    producer_ref=prod.ref, consumer_ref=ref))
    return candidates, filtered


def _evidence_confidence(observation_count: int, to_location: str) -> float:
    base = min(1.0, round(0.8 + 0.05 * (observation_count - 1), 4))
    if to_location == "query":
        return min(base, 0.5)  # 005A ruling 2: value flows into query filter positions are capped at medium confidence
    return base


def _is_auth_evidence(to_location: str, to_field: str) -> bool:
    return to_location == "header" and to_field.lower() == "authorization"


def converge_edges(candidates: list[Candidate]) -> list[dict]:
    """Converge by (producer, consumer) (S4); same-path edges with value flow are retained (S3 does not trigger in V1)."""
    by_pair: dict[tuple[str, str], dict[tuple[str, str, str, str], list[Candidate]]] = defaultdict(
        lambda: defaultdict(list))
    for c in candidates:
        by_pair[(c.producer_op, c.consumer_op)][
            (c.from_location, c.from_field, c.to_location, c.to_field)].append(c)

    edges = []
    for (producer, consumer), channels in by_pair.items():
        evidence = []
        for (from_location, from_field, to_location, to_field), occs in channels.items():
            refs = sorted(
                {(o.producer_ref.run_id, o.producer_ref.entry_index,
                  o.consumer_ref.run_id, o.consumer_ref.entry_index) for o in occs})
            observation_refs = [
                {"producer_ref": {"run_id": r[0], "entry_index": r[1]},
                 "consumer_ref": {"run_id": r[2], "entry_index": r[3]}} for r in refs]
            evidence.append({
                "type": "exact_value_flow",
                "detail": {"from_location": from_location, "from_field": from_field,
                           "to_location": to_location, "to_field": to_field,
                           "observation_refs": observation_refs},
                "_conf": _evidence_confidence(len(observation_refs), to_location),
                "_auth": _is_auth_evidence(to_location, to_field),
            })
        evidence.sort(key=lambda e: (e["detail"]["to_location"], e["detail"]["to_field"],
                                     e["detail"]["from_location"], e["detail"]["from_field"]))
        confidence = round(max(e["_conf"] for e in evidence), 4)
        kind = "auth" if any(e["_auth"] for e in evidence) else "data"
        clean_evidence = [{"type": e["type"], "detail": e["detail"]} for e in evidence]
        edges.append({
            "producer": producer, "consumer": consumer,
            "evidence": clean_evidence, "confidence": confidence,
            "kind": kind, "grounded": False,
        })
    edges.sort(key=lambda e: (e["producer"], e["consumer"]))
    return edges


def template_inference_edges(augmented_oas: dict) -> list[dict]:
    """Build conservative producer -> discovered-template path edges.

    Probe-discovered templates do not have HAR consumer entries, so these are
    intentionally not exact_value_flow edges.  They use schema_family evidence
    from Stage3's template inference metadata and are only produced for ready
    GET templates with explicit source_jsonpath bindings.
    """
    obs_to_op: dict[tuple[str, int], str] = {}
    for _path, item in augmented_oas.get("paths", {}).items():
        for _method, op in item.items():
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId")
            if not op_id:
                continue
            for obs in op.get("x-carverflow-observations", []) or []:
                if obs.get("source") != "stage1_session":
                    continue
                run_id = obs.get("run_id")
                entry_index = obs.get("entry_index")
                if run_id is None or entry_index is None:
                    continue
                try:
                    obs_to_op[(str(run_id), int(entry_index))] = str(op_id)
                except (TypeError, ValueError):
                    continue

    edges: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for _path, item in augmented_oas.get("paths", {}).items():
        for method, op in item.items():
            if not isinstance(op, dict) or not is_execution_ready(op):
                continue
            if str(method).upper() != "GET":
                continue
            consumer = op.get("operationId")
            inference = op.get("x-carverflow-template-inference")
            if not consumer or not isinstance(inference, dict):
                continue
            if len(set(inference.get("probe_ids") or [])) < 2:
                continue
            for binding in inference.get("param_bindings") or []:
                param = binding.get("param")
                source_field = _template_binding_source_field(binding)
                if not param or not source_field:
                    continue
                for source_entry_id in binding.get("source_entry_ids") or []:
                    producer = obs_to_op.get(_entry_id_tuple(source_entry_id))
                    if producer is None or producer == consumer:
                        continue
                    key = (producer, str(consumer), str(source_field), str(param))
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append({
                        "producer": producer,
                        "consumer": str(consumer),
                        "evidence": [{
                            "type": "schema_family",
                            "detail": {
                                "from_location": _template_edge_source_location(binding),
                                "from_field": str(source_field),
                                "to_location": "path",
                                "to_field": str(param),
                                "template_inference": {
                                    "probe_ids": sorted(set(inference.get("probe_ids") or [])),
                                    "example_values": sorted(set(binding.get("example_values") or [])),
                                    "source_entry_ids": sorted(set(binding.get("source_entry_ids") or [])),
                                },
                            },
                        }],
                        "confidence": 0.65,
                        "kind": "data",
                        "grounded": False,
                    })
    edges.sort(key=lambda e: (e["producer"], e["consumer"], e["evidence"][0]["detail"]["to_field"]))
    return edges


def scheduled_probe_material_edges(augmented_oas: dict) -> list[dict]:
    """Build producer -> probe-discovered consumer edges from fresh probe material.

    These edges come from Stage2.5 scheduled prefix/probe execution records, not
    from HAR exact matching, so they intentionally use schema_family evidence.
    """
    ready_ops: set[str] = set()
    op_to_material: list[tuple[str, list[dict]]] = []
    for _path, item in augmented_oas.get("paths", {}).items():
        for _method, op in item.items():
            if not isinstance(op, dict) or not is_execution_ready(op):
                continue
            op_id = op.get("operationId")
            if not op_id:
                continue
            ready_ops.add(str(op_id))
            material = op.get("x-carverflow-probe-material")
            if isinstance(material, list):
                op_to_material.append((str(op_id), material))

    edges: list[dict] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for consumer, material_records in op_to_material:
        for record in material_records:
            prefix_steps = [str(step) for step in record.get("prefix_steps") or []]
            probe_id = record.get("probe_id")
            explicit_producer = record.get("producer_operation_id")
            for binding in record.get("fresh_value_bindings") or []:
                producer = str(explicit_producer) if explicit_producer else None
                if producer is None:
                    try:
                        producer = prefix_steps[int(binding.get("from_step", -1))]
                    except (IndexError, TypeError, ValueError):
                        continue
                if producer not in ready_ops or producer == consumer:
                    continue
                from_location = str(binding.get("from_location") or FROM_RESPONSE_BODY)
                from_field = str(binding.get("from_field") or "")
                to_location = str(binding.get("to_location") or "")
                to_field = str(binding.get("to_field") or "")
                if not from_field or not to_location or not to_field:
                    continue
                key = (producer, consumer, from_location, from_field, to_location, to_field)
                if key in seen:
                    continue
                seen.add(key)
                kind = "auth" if _is_auth_evidence(to_location, to_field) else "data"
                edges.append({
                    "producer": producer,
                    "consumer": consumer,
                    "evidence": [{
                        "type": "schema_family",
                        "detail": {
                            "from_location": from_location,
                            "from_field": from_field,
                            "to_location": to_location,
                            "to_field": to_field,
                            "probe_material": {
                                "probe_id": probe_id,
                                "producer_probe_id": record.get("producer_probe_id"),
                                "value_basis": record.get("value_basis"),
                                "verification_status": record.get("verification_status"),
                                "source": "stage2_5_scheduled_probe_material",
                            },
                        },
                    }],
                    "confidence": 0.75,
                    "kind": kind,
                    "grounded": False,
                })
    edges.sort(key=lambda e: (e["producer"], e["consumer"], e["evidence"][0]["detail"]["to_field"]))
    return edges


def _template_binding_source_field(binding: dict) -> str | None:
    for key in ("source_jsonpath", "source_xpath", "source_field"):
        value = binding.get(key)
        if value:
            return str(value)
    return None


def _template_edge_source_location(binding: dict) -> str:
    source_location = str(binding.get("source_location") or FROM_RESPONSE_BODY)
    if source_location == "response_body_xml":
        return FROM_RESPONSE_BODY
    return source_location


def _entry_id_tuple(source_entry_id: object) -> tuple[str, int] | None:
    if not isinstance(source_entry_id, str):
        return None
    run_id, sep, index_text = source_entry_id.partition("#")
    if not sep:
        return None
    try:
        return run_id, int(index_text)
    except ValueError:
        return None
