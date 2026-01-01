"""013-F-A conservative canonicalization for executed candidate_url probes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from oas_naming import operation_id
from stage2_recover.canonical import STABLE_WORD, STRONG_FORM_PATTERNS

from .loader import Stage25Inputs

SENSITIVE_SEGMENT_PARTS = {
    "auth",
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
REDACTED = re.compile(r"\[REDACTED:[^\]]+\]", re.IGNORECASE)


@dataclass(frozen=True)
class CanonicalizationDecision:
    canonical_path: str | None
    operation_id: str | None = None
    reason: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def upgraded(self) -> bool:
        return self.canonical_path is not None


def canonicalize_candidate_url_probe(
    record: dict,
    inp: Stage25Inputs,
    base_url: str,
) -> CanonicalizationDecision:
    """Return a conservative canonical_path upgrade for an executed candidate URL.

    This deliberately does not infer new templates from a single concrete URL.
    It either maps to an existing static path exactly, or to one unambiguous
    existing parameterized template with positive evidence for every param slot.
    """
    candidate_url = record.get("target", {}).get("candidate_url")
    normalized = _normalize_same_origin_path(candidate_url, base_url)
    if normalized is None:
        return CanonicalizationDecision(None, reason="candidate_url_not_same_origin_path")
    if _unsafe_path(normalized):
        return CanonicalizationDecision(None, reason="candidate_url_unsafe_path")

    initial_paths = set(inp.initial_oas.get("paths", {}))
    if normalized in initial_paths and "{" not in normalized and "}" not in normalized:
        return CanonicalizationDecision(
            normalized,
            operation_id("GET", normalized),
            reason="exact_static_path",
            evidence=["exact_static_path"],
        )

    matches = [
        match for template in sorted(initial_paths)
        if "{" in template or "}" in template
        for match in [_match_template(template, normalized)]
        if match is not None
    ]
    if not matches:
        return CanonicalizationDecision(None, reason="no_matching_canonical_template")
    if len(matches) > 1:
        return CanonicalizationDecision(None, reason="ambiguous_matching_canonical_template")

    template, captures = matches[0]
    response_shape = _record_response_shape(record)
    existing_shapes = _existing_response_shapes(inp, template)
    shape_compatible = bool(response_shape and response_shape in existing_shapes)
    observed_values = _observed_param_values(inp, template)

    evidence: list[str] = []
    for param, value in captures.items():
        param_evidence = _param_evidence(
            value=value,
            observed_values=observed_values.get(param, set()),
            shape_compatible=shape_compatible,
            record=record,
        )
        if not param_evidence:
            return CanonicalizationDecision(
                None,
                reason="insufficient_parameter_evidence",
                evidence=evidence,
            )
        evidence.extend(f"{param}:{item}" for item in param_evidence)

    return CanonicalizationDecision(
        template,
        operation_id("GET", template),
        reason="unambiguous_parameterized_template",
        evidence=sorted(set(evidence)),
    )


def _normalize_same_origin_path(candidate_url: object, base_url: str) -> str | None:
    if not isinstance(candidate_url, str):
        return None
    value = candidate_url.strip()
    if not value or REDACTED.search(value):
        return None
    if value.startswith("/") and not value.startswith("//"):
        parts = urlsplit(value)
        if parts.query or parts.fragment:
            return None
        return parts.path.rstrip("/") or "/"

    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    base = urlsplit(base_url)
    if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
        return None
    if parts.query or parts.fragment:
        return None
    return parts.path.rstrip("/") or "/"


def _unsafe_path(path: str) -> bool:
    if "{" in path or "}" in path:
        return True
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return True
    return any(_unsafe_segment(segment) for segment in segments)


def _unsafe_segment(segment: str) -> bool:
    if not segment or REDACTED.search(segment) or "@" in segment:
        return True
    lowered = segment.lower().replace("-", "_")
    if any(part in lowered for part in SENSITIVE_SEGMENT_PARTS):
        return True
    if lowered.startswith("bearer ") or lowered.startswith("token "):
        return True
    if segment.count(".") == 2 and len(segment) >= 24:
        return True
    if len(segment) >= 24 and re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        return not _strong_form(segment)
    return False


def _match_template(template: str, path: str) -> tuple[str, dict[str, str]] | None:
    template_segments = [segment for segment in template.split("/") if segment]
    path_segments = [segment for segment in path.split("/") if segment]
    if len(template_segments) != len(path_segments):
        return None
    captures: dict[str, str] = {}
    for template_segment, path_segment in zip(template_segments, path_segments, strict=True):
        if template_segment.startswith("{") and template_segment.endswith("}"):
            captures[template_segment[1:-1]] = path_segment
            continue
        if template_segment != path_segment:
            return None
    return template, captures


def _param_evidence(
    *,
    value: str,
    observed_values: set[str],
    shape_compatible: bool,
    record: dict,
) -> list[str]:
    evidence: list[str] = []
    if _strong_form(value):
        evidence.append("strong_form")
    if value in observed_values:
        evidence.append("observed_concrete_value")
    if len(observed_values) >= 2 and not STABLE_WORD.fullmatch(value):
        evidence.append("diverse_observed_template")
    if _fresh_material(record) and not STABLE_WORD.fullmatch(value):
        evidence.append("fresh_material")
    if evidence and shape_compatible and not STABLE_WORD.fullmatch(value):
        evidence.append("response_shape_compatible")
    return evidence


def _strong_form(value: str) -> bool:
    return any(pattern.match(value) for pattern in STRONG_FORM_PATTERNS)


def _fresh_material(record: dict) -> bool:
    material = record.get("material") or {}
    if material.get("value_basis") not in {"fresh_replay", "runtime_secret", "mixed"}:
        return False
    return bool(material.get("fresh_value_bindings") or material.get("runtime_secret_bindings"))


def _observed_param_values(inp: Stage25Inputs, template: str) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {
        segment[1:-1]: set()
        for segment in template.split("/")
        if segment.startswith("{") and segment.endswith("}")
    }
    info = inp.paths.get(template)
    if info is None:
        return values
    for url in info.concrete_urls:
        path = _normalize_observed_path(url)
        if path is None:
            continue
        match = _match_template(template, path)
        if match is None:
            continue
        for param, value in match[1].items():
            values.setdefault(param, set()).add(value)
    return values


def _normalize_observed_path(url: str) -> str | None:
    parts = urlsplit(url)
    path = parts.path if parts.scheme or parts.netloc else urlsplit(url).path
    if not path:
        return None
    return path.rstrip("/") or "/"


def _record_response_shape(record: dict) -> tuple | None:
    body = (record.get("response") or {}).get("body")
    if not isinstance(body, str) or not body.strip():
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    return _shape(parsed)


def _existing_response_shapes(inp: Stage25Inputs, template: str) -> set[tuple]:
    item = inp.initial_oas.get("paths", {}).get(template, {})
    shapes: set[tuple] = set()
    for operation in item.values():
        for observation in operation.get("x-carverflow-observations", []):
            run_id = observation.get("run_id")
            entry_index = observation.get("entry_index")
            if run_id not in inp.bundles or entry_index is None:
                continue
            try:
                entry = inp.bundles[run_id].entries[int(entry_index)]
            except (IndexError, TypeError, ValueError):
                continue
            if not 200 <= int(((entry.get("response") or {}).get("status")) or 0) < 300:
                continue
            text = (((entry.get("response") or {}).get("content") or {}).get("text"))
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            shapes.add(_shape(parsed))
    return shapes


def _shape(value) -> tuple:
    if isinstance(value, list):
        return ("array",)
    if isinstance(value, dict):
        return ("object", tuple(sorted(value.keys())))
    return ("scalar", type(value).__name__)
