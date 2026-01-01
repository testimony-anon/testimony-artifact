"""013-D response-derived deterministic probe candidate planner.

This module records APICARV-style response probes as auditable not_executed
candidates. It is intentionally not wired into the legacy Stage 2.5 pipeline
yet.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from common.location_link_valueflow import parse_link_header
from common.xml_valueflow import iter_xml_scalar_values
from oas_naming import operation_id

from .loader import Stage25Inputs

SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]+$")
SIMPLE_JSONPATH_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REDACTED = re.compile(r"\[REDACTED:[^\]]+\]", re.IGNORECASE)
UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
MAX_SEGMENT_LENGTH = 64
SENSITIVE_NAME_PARTS = {
    "authorization",
    "bearer",
    "credential",
    "email",
    "jwt",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
}
_URL_HEADER_NOISE = {
    "accept-ranges",
    "access-control-allow-headers",
    "access-control-allow-methods",
    "access-control-allow-origin",
    "cache-control",
    "connection",
    "content-encoding",
    "content-language",
    "content-length",
    "content-type",
    "date",
    "etag",
    "expires",
    "pragma",
    "server",
    "vary",
    "via",
    "x-content-type-options",
    "x-frame-options",
    "x-powered-by",
}
_XML_RESOURCE_FIELD_PARTS = {
    "href",
    "id",
    "link",
    "location",
    "path",
    "resource",
    "self",
    "slug",
    "uri",
    "url",
}


@dataclass(frozen=True)
class ResponseJsonToken:
    source_jsonpath: str
    source_part: str
    token: str
    raw_value: Any


@dataclass
class ResponseProbePlanResult:
    not_executed: list[dict] = field(default_factory=list)

    @property
    def probes(self) -> list[dict]:
        return list(self.not_executed)


def extract_response_json_tokens(entry: dict) -> list[ResponseJsonToken]:
    """Extract auditable key/value tokens from a HAR entry response body."""
    text = (((entry.get("response") or {}).get("content") or {}).get("text"))
    if not isinstance(text, str) or not text.strip():
        return []
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return []

    tokens: list[ResponseJsonToken] = []
    _walk_json(body, "$", tokens)
    return tokens


def plan_response_probe_candidates(inp: Stage25Inputs) -> ResponseProbePlanResult:
    """Generate response-derived candidates without scheduling or execution."""
    records: dict[tuple[str, str, str], dict] = {}
    for source_entry_id, canonical_path in _observed_entries(inp.initial_oas):
        entry = _entry_for_ref(inp, source_entry_id)
        if entry is None:
            continue
        request_url = ((entry.get("request") or {}).get("url")) or ""
        if not _is_2xx(entry):
            continue
        for token in extract_response_json_tokens(entry):
            for record in _records_for_token(
                token=token,
                source_entry_id=source_entry_id,
                base_canonical_path=canonical_path,
                request_url=request_url,
            ):
                _add_record(records, record)
        for record in _records_for_headers(
            entry=entry,
            source_entry_id=source_entry_id,
            request_url=request_url,
        ):
            _add_record(records, record)
        for record in _records_for_xml(
            entry=entry,
            source_entry_id=source_entry_id,
            base_canonical_path=canonical_path,
            request_url=request_url,
        ):
            _add_record(records, record)

    return ResponseProbePlanResult(
        not_executed=[records[key] for key in sorted(records, key=lambda k: (k[2], k[1], k[0]))]
    )


def _add_record(records: dict[tuple[str, str, str], dict], record: dict) -> None:
    basis = record["construction_basis"]["generation_basis"]
    key = (
        record["target"]["method"],
        basis["generation_rule"],
        basis["derived_candidate"],
    )
    existing = records.get(key)
    if existing is None or _record_sort_key(record) < _record_sort_key(existing):
        records[key] = record


def _walk_json(value: Any, path: str, out: list[ResponseJsonToken]) -> None:
    if isinstance(value, dict):
        for key in sorted(value):
            child_path = _jsonpath_child(path, key)
            if key:
                out.append(ResponseJsonToken(
                    source_jsonpath=child_path,
                    source_part="key",
                    token=str(key),
                    raw_value=key,
                ))
            _walk_json(value[key], child_path, out)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_json(item, f"{path}[{index}]", out)
        return
    if value is None:
        return
    if isinstance(value, bool):
        token = "true" if value else "false"
    elif isinstance(value, (int, float, str)):
        token = str(value)
    else:
        return
    if token:
        out.append(ResponseJsonToken(
            source_jsonpath=path,
            source_part="value",
            token=token,
            raw_value=value,
        ))


def _records_for_token(
    token: ResponseJsonToken,
    source_entry_id: str,
    base_canonical_path: str,
    request_url: str,
) -> list[dict]:
    if _sensitive_path(token.source_jsonpath):
        return []
    if token.source_part == "value":
        url_candidate = _url_like_candidate(token.raw_value, request_url)
        if url_candidate:
            return [_not_executed_response_record(
                generation_rule="response_url_like_candidate",
                source_entry_id=source_entry_id,
                source_jsonpath=token.source_jsonpath,
                source_value=str(token.raw_value),
                source_part="value",
                derived_candidate=f"GET {url_candidate}",
                target={"method": "GET", "candidate_url": url_candidate},
                not_executed_reason="response_url_like_candidate_not_scheduled",
                reason="response value is a deterministic URL-like candidate",
            )]
    if not _safe_path_segment(token.token, token.source_jsonpath):
        return []

    candidate_path = _join_path(base_canonical_path, token.token)
    generation_rule = (
        "response_key_path_extension"
        if token.source_part == "key"
        else "response_value_path_extension"
    )
    return [_not_executed_response_record(
        generation_rule=generation_rule,
        source_entry_id=source_entry_id,
        source_jsonpath=token.source_jsonpath,
        source_value=str(token.raw_value),
        source_part=token.source_part,
        derived_candidate=f"GET {candidate_path}",
        target={
            "method": "GET",
            "canonical_path": candidate_path,
            "operation_id": operation_id("GET", candidate_path),
        },
        not_executed_reason="response_path_extension_not_scheduled",
        reason=f"response {token.source_part} deterministically extends observed path",
    )]


def _records_for_headers(entry: dict, source_entry_id: str, request_url: str) -> list[dict]:
    records: list[dict] = []
    for name, value in _response_headers(entry):
        canonical_name = name.lower()
        if _sensitive_name(canonical_name):
            continue
        if canonical_name == "location":
            candidate = _url_like_candidate(value, request_url)
            if candidate:
                records.append(_url_candidate_record(
                    generation_rule="location_header_candidate",
                    source_entry_id=source_entry_id,
                    source_location="response_header",
                    source_field="Location",
                    source_value=value,
                    derived_candidate=f"GET {candidate}",
                    candidate_url=candidate,
                    not_executed_reason="location_header_candidate_not_scheduled",
                    reason="Location response header points to a same-origin resource candidate",
                ))
            continue
        if canonical_name == "link":
            for link in parse_link_header(value):
                candidate = _url_like_candidate(link.get("url"), request_url)
                if not candidate:
                    continue
                rel = link.get("rel") or "unknown"
                if _sensitive_name(rel):
                    continue
                records.append(_url_candidate_record(
                    generation_rule="link_header_candidate",
                    source_entry_id=source_entry_id,
                    source_location="response_header",
                    source_field=f"Link;rel={rel}",
                    source_value=link.get("url", ""),
                    derived_candidate=f"GET {candidate}",
                    candidate_url=candidate,
                    not_executed_reason="link_header_candidate_not_scheduled",
                    reason="structured Link response header points to a same-origin resource candidate",
                ))
            continue
        if canonical_name in _URL_HEADER_NOISE:
            continue
        candidate = _url_like_candidate(value, request_url)
        if candidate:
            records.append(_url_candidate_record(
                generation_rule="header_url_like_candidate",
                source_entry_id=source_entry_id,
                source_location="response_header",
                source_field=name,
                source_value=value,
                derived_candidate=f"GET {candidate}",
                candidate_url=candidate,
                not_executed_reason="header_url_like_candidate_not_scheduled",
                reason="response header value is a deterministic URL-like candidate",
            ))
    return records


def _records_for_xml(
    entry: dict,
    source_entry_id: str,
    base_canonical_path: str,
    request_url: str,
) -> list[dict]:
    text = (((entry.get("response") or {}).get("content") or {}).get("text"))
    content_type = _response_content_type(entry)
    records: list[dict] = []
    for source_xpath, value in iter_xml_scalar_values(text, content_type):
        if _sensitive_path(source_xpath):
            continue
        url_candidate = _url_like_candidate(value, request_url)
        if url_candidate:
            records.append(_url_candidate_record(
                generation_rule="xml_url_like_candidate",
                source_entry_id=source_entry_id,
                source_location="response_body_xml",
                source_xpath=source_xpath,
                source_value=value,
                derived_candidate=f"GET {url_candidate}",
                candidate_url=url_candidate,
                not_executed_reason="xml_url_like_candidate_not_scheduled",
                reason="XML response scalar is a deterministic URL-like candidate",
            ))
            continue
        if not _xml_resource_field(source_xpath):
            continue
        if not _safe_path_segment(value, source_xpath):
            continue
        candidate_path = _join_path(base_canonical_path, value)
        records.append(_not_executed_response_record(
            generation_rule="xml_value_path_extension",
            source_entry_id=source_entry_id,
            source_location="response_body_xml",
            source_xpath=source_xpath,
            source_value=value,
            source_part="value",
            derived_candidate=f"GET {candidate_path}",
            target={
                "method": "GET",
                "canonical_path": candidate_path,
                "operation_id": operation_id("GET", candidate_path),
            },
            not_executed_reason="xml_value_path_extension_not_scheduled",
            reason="XML response scalar deterministically extends observed path",
        ))
    return records


def _url_candidate_record(
    *,
    generation_rule: str,
    source_entry_id: str,
    source_location: str,
    source_field: str | None = None,
    source_xpath: str | None = None,
    source_value: str | None = None,
    derived_candidate: str,
    candidate_url: str,
    not_executed_reason: str,
    reason: str,
) -> dict:
    return _not_executed_response_record(
        generation_rule=generation_rule,
        source_entry_id=source_entry_id,
        source_location=source_location,
        source_field=source_field,
        source_xpath=source_xpath,
        source_value=source_value,
        source_part="value",
        derived_candidate=derived_candidate,
        target={"method": "GET", "candidate_url": candidate_url},
        not_executed_reason=not_executed_reason,
        reason=reason,
    )


def _not_executed_response_record(
    generation_rule: str,
    source_entry_id: str,
    *,
    source_jsonpath: str | None = None,
    source_location: str = "response_body",
    source_field: str | None = None,
    source_xpath: str | None = None,
    source_value: str | None = None,
    source_part: str,
    derived_candidate: str,
    target: dict,
    not_executed_reason: str,
    reason: str,
) -> dict:
    basis = {
        "generation_rule": generation_rule,
        "source_entry_id": source_entry_id,
        "source_location": source_location,
        "source_part": source_part,
        "derived_candidate": derived_candidate,
        "reason": reason,
    }
    if source_jsonpath:
        basis["source_jsonpath"] = source_jsonpath
    if source_field:
        basis["source_field"] = source_field
    if source_xpath:
        basis["source_xpath"] = source_xpath
    if source_value:
        basis["source_value"] = source_value
    material_field = source_jsonpath or source_xpath or source_field or source_entry_id
    return {
        "probe_id": _probe_id(generation_rule, source_part, derived_candidate, source_entry_id),
        "probe_kind": "response",
        "execution_mode": "not_executed",
        "not_executed_reason": not_executed_reason,
        "target": target,
        "construction_basis": {
            "strategy": "scheduled_discovery",
            "generation_basis": basis,
        },
        "schedule": {
            "schedule_kind": "not_scheduled",
            "checkpoint_type": "none",
            "insertion_policy": "not_scheduled",
            "suffix_policy": "not_applicable",
        },
        "material": {
            "value_basis": "recorded_literal",
            "literal_assumptions": [{
                "location": "path",
                "field": material_field,
                "reason": "response-derived candidate is recorded as audit only; no fresh anchor yet",
            }],
            "material_sufficiency": "insufficient",
        },
        "admission": {
            "existence_evidence": "non_evidence",
            "admission_decision": "not_executed",
        },
    }


def _observed_entries(initial_oas: dict) -> list[tuple[str, str]]:
    refs: set[tuple[str, int, str]] = set()
    for canonical_path, item in initial_oas.get("paths", {}).items():
        for operation in item.values():
            for obs in operation.get("x-carverflow-observations", []):
                if "run_id" not in obs or "entry_index" not in obs:
                    continue
                refs.add((str(obs["run_id"]), int(obs["entry_index"]), canonical_path))
    return [(f"{run_id}#{entry_index}", path) for run_id, entry_index, path in sorted(refs)]


def _entry_for_ref(inp: Stage25Inputs, source_entry_id: str) -> dict | None:
    run_id, _, index_text = source_entry_id.partition("#")
    if not run_id or not index_text:
        return None
    bundle = inp.bundles.get(run_id)
    if bundle is None:
        return None
    try:
        index = int(index_text)
    except ValueError:
        return None
    if index < 0 or index >= len(bundle.entries):
        return None
    return bundle.entries[index]


def _is_2xx(entry: dict) -> bool:
    try:
        status = int((entry.get("response") or {}).get("status", 0))
    except (TypeError, ValueError):
        return False
    return 200 <= status < 300


def _response_headers(entry: dict) -> list[tuple[str, str]]:
    headers = (entry.get("response") or {}).get("headers") or []
    out: list[tuple[str, str]] = []
    if isinstance(headers, dict):
        iterable = headers.items()
    else:
        iterable = (
            (item.get("name"), item.get("value"))
            for item in headers
            if isinstance(item, dict)
        )
    for name, value in iterable:
        if name is None or value is None:
            continue
        text = str(value).strip()
        if text:
            out.append((str(name).strip(), text))
    return out


def _response_content_type(entry: dict) -> str | None:
    content = ((entry.get("response") or {}).get("content") or {})
    mime = content.get("mimeType")
    if mime:
        return str(mime)
    for name, value in _response_headers(entry):
        if name.lower() == "content-type":
            return value
    return None


def _url_like_candidate(raw_value: Any, request_url: str) -> str | None:
    if not isinstance(raw_value, str):
        return None
    value = raw_value.strip()
    if not value or REDACTED.search(value):
        return None
    if _sensitive_value(value):
        return None
    if value.startswith("/") and not value.startswith("//"):
        parts = urlsplit(value)
        if parts.query or parts.fragment:
            return None
        path = parts.path.rstrip("/") or "/"
        return path if _safe_candidate_path(path) else None
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    if parts.query or parts.fragment:
        return None
    request_parts = urlsplit(request_url)
    if request_parts.scheme and request_parts.netloc and (
        parts.scheme,
        parts.netloc,
    ) != (
        request_parts.scheme,
        request_parts.netloc,
        ):
        return None
    if not _safe_candidate_path(parts.path.rstrip("/") or "/"):
        return None
    return value


def _safe_candidate_path(path: str) -> bool:
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if not segments:
        return False
    return all(_safe_path_segment(segment, path) for segment in segments)


def _safe_path_segment(token: str, source_jsonpath: str) -> bool:
    if not token or len(token) > MAX_SEGMENT_LENGTH:
        return False
    if REDACTED.search(token):
        return False
    if _sensitive_name(token) or _sensitive_value_for_path_segment(token, source_jsonpath) or _sensitive_path(source_jsonpath):
        return False
    if not SAFE_SEGMENT.fullmatch(token):
        return False
    return True


def _sensitive_path(source_jsonpath: str) -> bool:
    parts = re.split(r"[^A-Za-z0-9_]+", source_jsonpath)
    return any(_sensitive_name(part) for part in parts if part)


def _sensitive_name(token: str) -> bool:
    lowered = token.lower().replace("-", "_")
    return any(part in lowered for part in SENSITIVE_NAME_PARTS)


def _sensitive_value(token: str) -> bool:
    lowered = token.lower()
    return "@" in token or lowered.startswith("bearer ") or lowered.startswith("token ") or _looks_like_long_secret(token)


def _sensitive_value_for_path_segment(token: str, source_jsonpath: str) -> bool:
    lowered = token.lower()
    if "@" in token or lowered.startswith("bearer ") or lowered.startswith("token "):
        return True
    if _looks_like_long_secret(token) and not _identity_like_source_path(source_jsonpath):
        return True
    return False


def _identity_like_source_path(source_jsonpath: str) -> bool:
    tail = re.split(r"[^A-Za-z0-9_]+", str(source_jsonpath or "").rstrip("]"))[-1].lower()
    return tail in {"id", "slug", "uuid", "href", "url", "uri", "link", "self", "resource", "location", "path"} or tail.endswith("id")


def _looks_like_long_secret(token: str) -> bool:
    if UUID_SEGMENT.fullmatch(token):
        return False
    if token.count(".") == 2 and len(token) >= 24:
        return True
    return len(token) >= 32 and bool(re.fullmatch(r"[A-Za-z0-9_-]+", token))


def _join_path(base_path: str, segment: str) -> str:
    if base_path == "/":
        return f"/{segment}"
    return f"{base_path.rstrip('/')}/{segment}"


def _jsonpath_child(parent: str, key: str) -> str:
    if SIMPLE_JSONPATH_KEY.fullmatch(key):
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"


def _xml_resource_field(source_xpath: str) -> bool:
    terminal = str(source_xpath).rstrip("/").rsplit("/", 1)[-1]
    if terminal.startswith("@"):
        terminal = terminal[1:]
    if "[" in terminal:
        terminal = terminal.split("[", 1)[0]
    lowered = terminal.lower().replace("-", "_")
    return any(part == lowered or lowered.endswith(f"_{part}") for part in _XML_RESOURCE_FIELD_PARTS)


def _probe_id(generation_rule: str, source_part: str, derived_candidate: str, source_entry_id: str) -> str:
    digest = hashlib.sha1(
        f"{generation_rule}|{source_part}|{derived_candidate}|{source_entry_id}".encode("utf-8")
    ).hexdigest()[:12]
    return f"pr-013d-response-{digest}"


def _record_sort_key(record: dict) -> tuple:
    basis = record["construction_basis"]["generation_basis"]
    return (
        basis["derived_candidate"],
        basis["generation_rule"],
        basis["source_part"],
        basis.get("source_entry_id", ""),
        basis.get("source_jsonpath", ""),
    )
