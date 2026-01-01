"""Conservative Stage3 template inference for concrete probe paths.

Successful exploratory probes may execute concrete instance URLs.  Stage 3 must
not let those concrete URLs become final OAS paths unless they can be mapped to
an existing template or generalized from multiple compatible successful probes.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from common.xml_valueflow import iter_xml_scalar_values
from oas_naming import path_parameter_name

_RESPONSE_EXTENSION_RULES = {
    "response_key_path_extension",
    "response_value_path_extension",
}
_CANDIDATE_URL_RULES = {
    "response_url_like_candidate",
    "location_header_candidate",
    "header_url_like_candidate",
    "link_header_candidate",
    "xml_url_like_candidate",
    "intermediate_path_segment",
    "bipartite_missing_edge",
}
_XML_EXTENSION_RULES = {
    "xml_value_path_extension",
}
_ALL_TEMPLATE_RULES = _RESPONSE_EXTENSION_RULES | _CANDIDATE_URL_RULES | _XML_EXTENSION_RULES
_RESERVED_STATIC_SEGMENTS = {
    "api",
    "rest",
    "v1",
    "v2",
    "v3",
    "graphql",
}
_SENSITIVE_SEGMENT_PARTS = {
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
    "cookie",
    "sessionid",
}
_REDACTED = re.compile(r"\[REDACTED:[^\]]+\]", re.IGNORECASE)


@dataclass(frozen=True)
class ProbePathResolution:
    canonical_path: str
    reason: str
    param_bindings: tuple[dict, ...] = ()
    probe_ids: tuple[str, ...] = ()
    example_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ConcreteProbe:
    probe: dict
    method: str
    path: str
    segments: tuple[str, ...]
    source_kind: str
    source_location: str | None
    source_jsonpath: str | None
    source_xpath: str | None
    source_field: str | None
    source_entry_id: str | None
    source_value: str | None
    shape: tuple


def resolve_probe_template_paths(
    initial_oas: dict,
    probes: list[dict],
) -> dict[str, ProbePathResolution]:
    """Return template paths for concrete probe candidates.

    Path-extension or candidate_url probes may execute a concrete instance URL
    such as /items/abc. This helper either maps the probe to an existing
    parameterized template, infers a new template from multiple compatible
    successful probes, or leaves it unresolved so Stage3 keeps the probe only in
    probe_results.
    """
    initial_paths = set(initial_oas.get("paths", {}))
    initial_static_segments = _initial_static_segments(initial_paths)
    base_url = _base_url(initial_oas)
    resolutions: dict[str, ProbePathResolution] = {}
    unresolved: list[_ConcreteProbe] = []

    for probe in probes:
        concrete = _concrete_probe(probe, initial_paths, base_url)
        if concrete is None:
            continue
        existing = None
        if _allow_existing_template_resolution(concrete):
            existing = _unique_existing_template(concrete.path, initial_paths, initial_static_segments)
        if existing is not None:
            resolutions[probe["probe_id"]] = ProbePathResolution(
                canonical_path=existing,
                reason="existing_parameterized_template",
                param_bindings=_param_bindings_for_template(existing, concrete, [concrete]),
                probe_ids=(probe["probe_id"],),
                example_values=tuple(_template_values(existing, concrete.path)),
            )
            continue
        if _ambiguous_existing_template(concrete.path, initial_paths):
            continue
        unresolved.append(concrete)

    resolutions.update(_infer_new_templates(initial_static_segments, unresolved))
    return resolutions


def _allow_existing_template_resolution(concrete: _ConcreteProbe) -> bool:
    target = concrete.probe.get("target") if isinstance(concrete.probe, dict) else {}
    if (
        concrete.source_kind == "response_url_like_candidate"
        and isinstance(target, dict)
        and "canonical_path" not in target
    ):
        return False
    return True


def resolve_response_probe_paths(
    initial_oas: dict,
    probes: list[dict],
) -> dict[str, ProbePathResolution]:
    """Backward-compatible wrapper for the original response-only name."""
    return resolve_probe_template_paths(initial_oas, probes)


def template_gated_probe(probe: dict, initial_oas: dict) -> bool:
    """Whether Stage3 must route this probe through the template gate."""
    return _concrete_probe(probe, set(initial_oas.get("paths", {})), _base_url(initial_oas)) is not None


def response_derived_concrete_probe(probe: dict, initial_paths: set[str]) -> bool:
    """Whether Stage3 must gate this response-derived canonical_path probe.

    Kept for existing callers/tests.  New code should use template_gated_probe
    or resolve_probe_template_paths.
    """
    if probe.get("probe_kind") != "response":
        return False
    basis = probe.get("construction_basis", {}).get("generation_basis")
    if not isinstance(basis, dict):
        return False
    if basis.get("generation_rule") not in _RESPONSE_EXTENSION_RULES:
        return False
    canonical_path = probe.get("target", {}).get("canonical_path")
    if not isinstance(canonical_path, str) or not canonical_path.startswith("/"):
        return False
    if "{" in canonical_path or "}" in canonical_path:
        return False
    return canonical_path not in initial_paths


def _concrete_probe(probe: dict, initial_paths: set[str], base_url: str | None) -> _ConcreteProbe | None:
    if probe.get("execution_mode") == "not_executed":
        return None
    response = probe.get("response")
    if not isinstance(response, dict) or not (200 <= int(response.get("status", 0)) < 400):
        return None
    target = probe.get("target") or {}
    method = str(target.get("method", "")).upper()
    if method != "GET":
        return None
    basis = probe.get("construction_basis", {}).get("generation_basis")
    if not isinstance(basis, dict):
        return None
    generation_rule = basis.get("generation_rule")
    if generation_rule not in _ALL_TEMPLATE_RULES:
        return None
    path = _candidate_path(target, base_url)
    if path is None or path in initial_paths:
        return None
    if "{" in path or "}" in path:
        return None
    if _unsafe_path(path):
        return None
    shape = _response_shape(probe)
    if shape is None:
        return None
    source_jsonpath = basis.get("source_jsonpath")
    source_xpath = basis.get("source_xpath")
    source_field = basis.get("source_field")
    source_entry_id = basis.get("source_entry_id")
    source_value = basis.get("source_value") or _source_value_from_path(path, source_jsonpath)
    return _ConcreteProbe(
        probe=probe,
        method=method,
        path=path,
        segments=tuple(_segments(path)),
        source_kind=str(generation_rule),
        source_location=str(basis.get("source_location")) if basis.get("source_location") else None,
        source_jsonpath=str(source_jsonpath) if source_jsonpath else None,
        source_xpath=str(source_xpath) if source_xpath else None,
        source_field=str(source_field) if source_field else None,
        source_entry_id=str(source_entry_id) if source_entry_id else None,
        source_value=str(source_value) if source_value else None,
        shape=shape,
    )


def _candidate_path(target: dict, base_url: str | None) -> str | None:
    canonical_path = target.get("canonical_path")
    if isinstance(canonical_path, str) and canonical_path.startswith("/"):
        return canonical_path.rstrip("/") or "/"
    candidate_url = target.get("candidate_url")
    return _normalize_same_origin_path(candidate_url, base_url)


def _normalize_same_origin_path(candidate_url: object, base_url: str | None) -> str | None:
    if not isinstance(candidate_url, str):
        return None
    value = candidate_url.strip()
    if not value or _REDACTED.search(value):
        return None
    if value.startswith("/") and not value.startswith("//"):
        parts = urlsplit(value)
        if parts.query or parts.fragment:
            return None
        return parts.path.rstrip("/") or "/"
    if not base_url:
        return None
    parts = urlsplit(value)
    base = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
        return None
    if parts.query or parts.fragment:
        return None
    return parts.path.rstrip("/") or "/"


def _base_url(initial_oas: dict) -> str | None:
    servers = initial_oas.get("servers") or []
    if not servers:
        return None
    url = servers[0].get("url") if isinstance(servers[0], dict) else None
    return str(url) if url else None


def _unique_existing_template(path: str, initial_paths: set[str], initial_static_segments: set[str]) -> str | None:
    matches = [
        template
        for template in sorted(initial_paths)
        if "{" in template
        and "}" in template
        and _match_template(template, path)
        and _existing_template_values_safe(template, path, initial_static_segments)
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _ambiguous_existing_template(path: str, initial_paths: set[str]) -> bool:
    matches = [
        template
        for template in sorted(initial_paths)
        if "{" in template
        and "}" in template
        and _match_template(template, path)
    ]
    return len(matches) > 1


def _match_template(template: str, path: str) -> bool:
    template_segments = _segments(template)
    path_segments = _segments(path)
    if len(template_segments) != len(path_segments):
        return False
    for template_segment, path_segment in zip(template_segments, path_segments, strict=True):
        if template_segment.startswith("{") and template_segment.endswith("}"):
            if not path_segment:
                return False
            continue
        if template_segment != path_segment:
            return False
    return True


def _existing_template_values_safe(template: str, path: str, initial_static_segments: set[str]) -> bool:
    template_segments = _segments(template)
    path_segments = _segments(path)
    for template_segment, path_segment in zip(template_segments, path_segments, strict=True):
        if not (template_segment.startswith("{") and template_segment.endswith("}")):
            continue
        if _stable_or_unsafe_diff_value(path_segment, initial_static_segments):
            return False
        if not _dynamic_segment_hint(path_segment):
            return False
    return True


def _dynamic_segment_hint(value: str) -> bool:
    if any(ch.isdigit() for ch in value):
        return True
    return any(ch in value for ch in ("-", "_", ".", "~"))


def _infer_new_templates(
    initial_static_segments: set[str],
    probes: list[_ConcreteProbe],
) -> dict[str, ProbePathResolution]:
    groups: dict[tuple[str, int], list[_ConcreteProbe]] = defaultdict(list)
    for probe in probes:
        groups[(probe.method, len(probe.segments))].append(probe)

    resolutions: dict[str, ProbePathResolution] = {}
    for (_method, _length), members in sorted(groups.items()):
        for cluster in _cluster_compatible_paths(members, initial_static_segments):
            template, bindings = _template_for_cluster(cluster)
            if template is None:
                continue
            probe_ids = tuple(sorted(member.probe["probe_id"] for member in cluster))
            examples = tuple(sorted({value for member in cluster for value in _diff_values(template, member.path)}))
            for member in cluster:
                resolutions[member.probe["probe_id"]] = ProbePathResolution(
                    canonical_path=template,
                    reason="multi_probe_compatible_template",
                    param_bindings=tuple(bindings),
                    probe_ids=probe_ids,
                    example_values=examples,
                )
    return resolutions


def _cluster_compatible_paths(
    members: list[_ConcreteProbe],
    initial_static_segments: set[str],
) -> list[list[_ConcreteProbe]]:
    by_signature: dict[tuple[str | None, ...], list[_ConcreteProbe]] = defaultdict(list)
    for member in members:
        for signature in _signatures(member.segments):
            by_signature[signature].append(member)

    clusters: list[list[_ConcreteProbe]] = []
    seen_keys: set[tuple[str, ...]] = set()
    for signature, group in sorted(by_signature.items(), key=lambda item: (_signature_sort_key(item[0]), [m.path for m in item[1]])):
        diff_positions = [index for index, segment in enumerate(signature) if segment is None]
        if not diff_positions:
            continue
        for compatible_group in _shape_compatible_groups(group):
            unique_paths = {member.path for member in compatible_group}
            if len(unique_paths) < 2:
                continue
            if not _diff_positions_safe(compatible_group, diff_positions, initial_static_segments):
                continue
            key = tuple(sorted(unique_paths))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            clusters.append(sorted(compatible_group, key=lambda member: member.path))
    return clusters


def _shape_compatible_groups(members: list[_ConcreteProbe]) -> list[list[_ConcreteProbe]]:
    groups: list[list[_ConcreteProbe]] = []
    for member in sorted(members, key=lambda item: item.path):
        for group in groups:
            if all(_shape_compatible(member.shape, existing.shape) for existing in group):
                group.append(member)
                break
        else:
            groups.append([member])
    return groups


def _signature_sort_key(signature: tuple[str | None, ...]) -> tuple:
    return tuple("" if part is None else f"~{part}" for part in signature)


def _signatures(segments: tuple[str, ...]) -> list[tuple[str | None, ...]]:
    count = len(segments)
    # Require at least one static segment.  This avoids generalizing unrelated
    # roots such as /users/a and /groups/b into /{var1}/{var2}.
    out: list[tuple[str | None, ...]] = []
    for mask in range(1, (1 << count) - 1):
        signature = tuple(None if mask & (1 << index) else segments[index] for index in range(count))
        if any(part is not None for part in signature) and any(part is None for part in signature):
            out.append(signature)
    out.sort(key=lambda sig: (sum(part is None for part in sig), _signature_sort_key(sig)))
    return out


def _diff_positions_safe(
    members: list[_ConcreteProbe],
    diff_positions: list[int],
    initial_static_segments: set[str],
) -> bool:
    for position in diff_positions:
        values = {member.segments[position] for member in members}
        if len(values) < 2:
            return False
        if all(_stable_or_unsafe_diff_value(value, initial_static_segments) for value in values):
            return False
    return True


def _stable_or_unsafe_diff_value(value: str, initial_static_segments: set[str]) -> bool:
    lowered = value.lower()
    return (
        lowered in _RESERVED_STATIC_SEGMENTS
        or lowered in initial_static_segments
        or _unsafe_segment(value)
    )


def _template_for_cluster(cluster: list[_ConcreteProbe]) -> tuple[str | None, list[dict]]:
    segments = [member.segments for member in cluster]
    template_parts: list[str] = []
    param_positions: list[int] = []
    for index in range(len(segments[0])):
        values = {parts[index] for parts in segments}
        if len(values) == 1:
            template_parts.append(next(iter(values)))
        else:
            param_positions.append(index)
            template_parts.append("")
    if not param_positions:
        return None, []

    names = _param_names_for_positions(cluster, param_positions)
    bindings: list[dict] = []
    for position, name in zip(param_positions, names, strict=True):
        template_parts[position] = f"{{{name}}}"
        sources = _sources_for_position(cluster, position)
        source_locations = sorted({
            member.source_location or "response_body"
            for member in cluster
            if _segment_matches_source(member, position)
        })
        bindings.append({
            "param": name,
            "position": position,
            "source_location": source_locations[0] if len(source_locations) == 1 else "response_body",
            **_source_binding_fields(sources),
            "source_entry_ids": sorted({
                member.source_entry_id for member in cluster if member.source_entry_id
            }),
            "example_values": sorted({member.segments[position] for member in cluster}),
        })
    return "/" + "/".join(template_parts), bindings


def _param_names_for_positions(cluster: list[_ConcreteProbe], positions: list[int]) -> list[str]:
    if len(positions) == 1:
        position = positions[0]
        leaves = {
            _source_leaf(member)
            for member in cluster
            if _segment_matches_source(member, position)
        }
        leaves = {leaf for leaf in leaves if leaf and not _generic_link_leaf(leaf, cluster)}
        if len(leaves) == 1:
            return [path_parameter_name(next(iter(leaves)), fallback="var1")]
        if position == len(cluster[0].segments) - 1:
            return ["id"]
    return [f"var{index}" for index in range(1, len(positions) + 1)]


def _sources_for_position(cluster: list[_ConcreteProbe], position: int) -> dict[str, list[str]]:
    sources: dict[str, set[str]] = defaultdict(set)
    for member in cluster:
        if not _segment_matches_source(member, position):
            continue
        if member.source_jsonpath:
            normalized = _normalize_jsonpath_indices(member.source_jsonpath)
            if normalized:
                sources["source_jsonpath"].add(normalized)
        if member.source_xpath:
            normalized = _normalize_xpath_indices(member.source_xpath)
            if normalized:
                sources["source_xpath"].add(normalized)
        if member.source_field:
            sources["source_field"].add(member.source_field)
    return {key: sorted(values) for key, values in sources.items() if values}


def _source_binding_fields(sources: dict[str, list[str]]) -> dict:
    out: dict[str, str] = {}
    for field in ("source_jsonpath", "source_xpath", "source_field"):
        values = sources.get(field) or []
        if len(values) == 1:
            out[field] = values[0]
    return out


def _segment_matches_source(member: _ConcreteProbe, position: int) -> bool:
    return member.segments[position] in _source_segment_values(member)


def _source_segment_values(member: _ConcreteProbe) -> set[str]:
    values: set[str] = set()
    if member.source_value:
        values.add(member.source_value)
        values.update(_segments(member.source_value))
        normalized = _normalize_same_origin_path(member.source_value, None)
        if normalized:
            values.update(_segments(normalized))
    if member.source_jsonpath and not values:
        values.add(member.segments[-1])
    return values


def _source_leaf(member: _ConcreteProbe) -> str:
    if member.source_jsonpath:
        return _jsonpath_leaf(member.source_jsonpath)
    if member.source_xpath:
        leaf = _xpath_leaf(member.source_xpath)
        return "" if _generic_source_leaf(leaf) else leaf
    if member.source_field:
        if (member.source_location or "").lower() == "response_header":
            return ""
        return str(member.source_field).split(";", 1)[0].strip()
    return ""


def _generic_link_leaf(leaf: str, cluster: list[_ConcreteProbe]) -> bool:
    lowered = leaf.lower().replace("-", "_")
    if lowered in {"href", "link", "location", "self", "uri", "path", "resource"}:
        return True
    return lowered in {"location", "link"} and any(
        (member.source_location or "").lower() == "response_header" for member in cluster
    )


def _generic_source_leaf(leaf: str) -> bool:
    return leaf.lower().replace("-", "_") in {
        "href",
        "link",
        "location",
        "self",
        "url",
        "uri",
        "path",
        "resource",
    }


def _normalize_jsonpath_indices(path: str | None) -> str | None:
    if not path:
        return None
    return re.sub(r"\[\d+\]", "[*]", path)


def _normalize_xpath_indices(path: str | None) -> str | None:
    if not path:
        return None
    return re.sub(r"\[\d+\]", "[*]", path)


def _xpath_leaf(path: str) -> str:
    if not path:
        return ""
    tail = path.rstrip("/").rsplit("/", 1)[-1]
    if tail.startswith("@"):
        tail = tail[1:]
    if "[" in tail:
        tail = tail.split("[", 1)[0]
    return tail.strip()


def _param_bindings_for_template(template: str, concrete: _ConcreteProbe, members: list[_ConcreteProbe]) -> tuple[dict, ...]:
    template_segments = _segments(template)
    bindings = []
    for index, segment in enumerate(template_segments):
        if not (segment.startswith("{") and segment.endswith("}")):
            continue
        sources = _sources_for_position(members, index)
        bindings.append({
            "param": segment[1:-1],
            "position": index,
            "source_location": concrete.source_location or "response_body",
            **(_source_binding_fields(sources) or _fallback_source_binding(concrete)),
            "source_entry_ids": sorted({
                member.source_entry_id for member in members if member.source_entry_id
            }),
            "example_values": sorted({member.segments[index] for member in members}),
        })
    return tuple(bindings)


def _fallback_source_binding(concrete: _ConcreteProbe) -> dict:
    if concrete.source_jsonpath:
        return {"source_jsonpath": concrete.source_jsonpath}
    if concrete.source_xpath:
        return {"source_xpath": concrete.source_xpath}
    if concrete.source_field:
        return {"source_field": concrete.source_field}
    return {}


def _template_values(template: str, path: str) -> list[str]:
    values: list[str] = []
    for template_segment, path_segment in zip(_segments(template), _segments(path), strict=False):
        if template_segment.startswith("{") and template_segment.endswith("}"):
            values.append(path_segment)
    return values


def _diff_values(template: str, path: str) -> list[str]:
    return _template_values(template, path)


def _segments(path: str) -> list[str]:
    return [segment for segment in str(path or "").split("/") if segment]


def _jsonpath_leaf(path: str) -> str:
    if not path:
        return ""
    tail = path.rsplit(".", 1)[-1]
    if "[" in tail:
        tail = tail.split("[", 1)[0]
    return tail.strip("$[]'\"")


def _source_value_from_path(path: str, source_jsonpath: object) -> str | None:
    if not source_jsonpath:
        return None
    leaf = _jsonpath_leaf(str(source_jsonpath))
    if not leaf:
        return None
    segments = _segments(path)
    return segments[-1] if segments else None


def _response_shape(probe: dict) -> tuple | None:
    body = (probe.get("response") or {}).get("body")
    if isinstance(body, str):
        if not body.strip():
            return None
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return _xml_shape(body, probe)
    return _shape(body)


def _shape(value: Any) -> tuple | None:
    if isinstance(value, dict):
        return (
            "object",
            tuple((str(key), _shape(value[key])) for key in sorted(value)),
        )
    if isinstance(value, list):
        return ("array", tuple(sorted({_shape(item) for item in value}, key=repr)))
    if value is None:
        return ("scalar", "null")
    if isinstance(value, bool):
        return ("scalar", "bool")
    if isinstance(value, int) and not isinstance(value, bool):
        return ("scalar", "int")
    if isinstance(value, float):
        return ("scalar", "float")
    if isinstance(value, str):
        return ("scalar", "str")
    return None


def _xml_shape(body: str, probe: dict) -> tuple | None:
    fields = []
    for field, value in iter_xml_scalar_values(body, _response_content_type(probe)):
        fields.append((_normalize_xpath_indices(field) or field, ("scalar", _scalar_type(value))))
    if not fields:
        return None
    return ("xml", tuple(sorted(fields)))


def _response_content_type(probe: dict) -> str | None:
    headers = (probe.get("response") or {}).get("headers") or {}
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == "content-type":
                return str(value)
    return None


def _scalar_type(value: object) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if value is None:
        return "null"
    return "str"


def _shape_compatible(a: tuple | None, b: tuple | None) -> bool:
    if a is None or b is None:
        return False
    if a == b:
        return True
    if not a or not b or a[0] != b[0]:
        return False
    kind = a[0]
    if kind == "object":
        a_fields = dict(a[1])
        b_fields = dict(b[1])
        common = sorted(set(a_fields) & set(b_fields))
        if not common:
            return False
        return all(_shape_compatible(a_fields[key], b_fields[key]) for key in common)
    if kind == "array":
        a_items = list(a[1])
        b_items = list(b[1])
        if not a_items or not b_items:
            return True
        return any(_shape_compatible(left, right) for left in a_items for right in b_items)
    if kind == "scalar":
        return a[1] == b[1]
    if kind == "xml":
        a_fields = dict(a[1])
        b_fields = dict(b[1])
        common = sorted(set(a_fields) & set(b_fields))
        if not common:
            return False
        return all(a_fields[key] == b_fields[key] for key in common)
    return False


def _initial_static_segments(initial_paths: set[str]) -> set[str]:
    out: set[str] = set()
    for path in initial_paths:
        for segment in _segments(path):
            if segment.startswith("{") and segment.endswith("}"):
                continue
            out.add(segment.lower())
    return out | _RESERVED_STATIC_SEGMENTS


def _unsafe_path(path: str) -> bool:
    parts = _segments(path)
    if not parts:
        return True
    return any(_unsafe_segment(part) for part in parts)


def _unsafe_segment(segment: str) -> bool:
    if not segment or _REDACTED.search(segment) or "@" in segment:
        return True
    lowered = segment.lower().replace("-", "_")
    if any(part in lowered for part in _SENSITIVE_SEGMENT_PARTS):
        return True
    if lowered.startswith("bearer ") or lowered.startswith("token "):
        return True
    if segment.count(".") == 2 and len(segment) >= 24:
        return True
    return False
