"""013-D path-graph deterministic probe candidate planner.

This planner records APICARV-style intermediate and bipartite candidates as
auditable not_executed records. It is intentionally not wired into the legacy
Stage 2.5 pipeline yet.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from oas_naming import operation_id

from .loader import Stage25Inputs

MAX_CANDIDATES_PER_KIND = 100
MAX_PATH_DEPTH = 8
MAX_BIPARTITE_SUFFIX_LEN = 2
VERSION_SEGMENT = re.compile(r"^v\d+(?:\.\d+)?$", re.IGNORECASE)
SENSITIVE_SEGMENT_PARTS = {
    "auth",
    "authorization",
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


@dataclass
class PathGraphProbePlanResult:
    not_executed: list[dict] = field(default_factory=list)

    @property
    def probes(self) -> list[dict]:
        return list(self.not_executed)


def plan_path_graph_probe_candidates(inp: Stage25Inputs) -> PathGraphProbePlanResult:
    """Generate intermediate and bipartite path graph candidates.

    Intermediate candidates use canonical path prefixes. Bipartite candidates
    use concrete observed literal paths so canonical parameterization does not
    erase sibling facts.
    """
    intermediate = _intermediate_records(inp)
    bipartite = _bipartite_records(inp)
    return PathGraphProbePlanResult(not_executed=[*intermediate, *bipartite])


def _intermediate_records(inp: Stage25Inputs) -> list[dict]:
    observed = set(inp.paths) or set(inp.initial_oas.get("paths", {}))
    records: dict[tuple[str, str, str, str], dict] = {}
    for source_path in sorted(observed):
        segments = _split_path(source_path)
        for prefix_len in range(1, len(segments)):
            candidate_segments = segments[:prefix_len]
            candidate_path = _join_segments(candidate_segments)
            if candidate_path in observed:
                continue
            if not _valid_path(candidate_segments, allow_parameters=True):
                continue
            record = _intermediate_record(
                candidate_path,
                source_path,
                _first_observation_ref(inp.initial_oas, source_path),
            )
            key = _dedup_key(record)
            existing = records.get(key)
            if existing is None or _record_sort_key(record) < _record_sort_key(existing):
                records[key] = record
    return _sorted_limited(records.values())


def _bipartite_records(inp: Stage25Inputs) -> list[dict]:
    observed = _observed_concrete_paths(inp)
    records: dict[tuple[str, str, str, str], dict] = {}
    by_segments = {path: _split_path(path) for path in observed}
    for source_edge in sorted(observed):
        edge_segments = by_segments[source_edge]
        if not _valid_path(edge_segments, allow_parameters=False):
            continue
        for suffix_len in range(1, MAX_BIPARTITE_SUFFIX_LEN + 1):
            sibling_index = len(edge_segments) - suffix_len - 1
            if sibling_index <= 0:
                continue
            parent = edge_segments[:sibling_index]
            x_segment = edge_segments[sibling_index]
            suffix = edge_segments[sibling_index + 1:]
            source_base = _join_segments([*parent, x_segment])
            if source_base not in observed:
                continue
            if not _safe_literal_segments([x_segment, *suffix]):
                continue
            for sibling_base in sorted(observed):
                sibling_segments = by_segments[sibling_base]
                if len(sibling_segments) != len(parent) + 1:
                    continue
                if sibling_segments[:len(parent)] != parent:
                    continue
                y_segment = sibling_segments[-1]
                if y_segment == x_segment:
                    continue
                if not _safe_literal_segments([y_segment]):
                    continue
                candidate_segments = [*parent, y_segment, *suffix]
                candidate_path = _join_segments(candidate_segments)
                if candidate_path in observed:
                    continue
                if not _valid_path(candidate_segments, allow_parameters=False):
                    continue
                record = _bipartite_record(
                    candidate_path=candidate_path,
                    source_edge=source_edge,
                    source_base=source_base,
                    sibling_base=sibling_base,
                )
                key = _dedup_key(record)
                existing = records.get(key)
                if existing is None or _record_sort_key(record) < _record_sort_key(existing):
                    records[key] = record
    return _sorted_limited(records.values())


def _intermediate_record(
    candidate_path: str,
    source_path: str,
    source_entry_id: str | None,
) -> dict:
    generation_basis = {
        "generation_rule": "intermediate_path_segment",
        "source_location": "path_graph",
        "source_part": "path_segment",
        "derived_candidate": f"GET {candidate_path}",
        "reason": f"prefix of {source_path}",
    }
    if source_entry_id is not None:
        generation_basis["source_entry_id"] = source_entry_id
    return {
        "probe_id": _probe_id("intermediate", generation_basis["derived_candidate"]),
        "probe_kind": "intermediate",
        "execution_mode": "not_executed",
        "not_executed_reason": "intermediate_candidate_not_scheduled",
        "target": {
            "method": "GET",
            "canonical_path": candidate_path,
            "operation_id": operation_id("GET", candidate_path),
        },
        "construction_basis": {
            "strategy": "scheduled_discovery",
            "generation_basis": generation_basis,
        },
        "schedule": _not_scheduled_record(),
        "material": {
            "value_basis": "not_applicable",
            "material_sufficiency": "not_applicable",
        },
        "admission": _not_executed_admission(),
    }


def _first_observation_ref(initial_oas: dict, canonical_path: str) -> str | None:
    refs = []
    for operation in initial_oas.get("paths", {}).get(canonical_path, {}).values():
        for observation in operation.get("x-carverflow-observations", []):
            if "run_id" in observation and "entry_index" in observation:
                refs.append(
                    (str(observation["run_id"]), int(observation["entry_index"]))
                )
    if not refs:
        return None
    run_id, entry_index = sorted(refs)[0]
    return f"{run_id}#{entry_index}"


def _bipartite_record(
    candidate_path: str,
    source_edge: str,
    source_base: str,
    sibling_base: str,
) -> dict:
    generation_basis = {
        "generation_rule": "bipartite_missing_edge",
        "source_location": "path_graph",
        "source_part": "graph_edge",
        "derived_candidate": f"GET {candidate_path}",
        "reason": (
            f"source edge {source_edge}; source base {source_base}; "
            f"sibling base {sibling_base}"
        ),
    }
    return {
        "probe_id": _probe_id("bipartite", generation_basis["derived_candidate"]),
        "probe_kind": "bipartite",
        "execution_mode": "not_executed",
        "not_executed_reason": "bipartite_candidate_not_scheduled",
        "target": {
            "method": "GET",
            "candidate_url": candidate_path,
        },
        "construction_basis": {
            "strategy": "scheduled_discovery",
            "generation_basis": generation_basis,
        },
        "schedule": _not_scheduled_record(),
        "material": {
            "value_basis": "recorded_literal",
            "literal_assumptions": [{
                "location": "path",
                "field": candidate_path,
                "reason": "bipartite candidate reuses observed concrete sibling literal",
            }],
            "material_sufficiency": "insufficient",
        },
        "admission": _not_executed_admission(),
    }


def _not_scheduled_record() -> dict:
    return {
        "schedule_kind": "not_scheduled",
        "checkpoint_type": "none",
        "insertion_policy": "not_scheduled",
        "suffix_policy": "not_applicable",
    }


def _not_executed_admission() -> dict:
    return {
        "existence_evidence": "non_evidence",
        "admission_decision": "not_executed",
    }


def _observed_concrete_paths(inp: Stage25Inputs) -> set[str]:
    paths: set[str] = set()
    for info in inp.paths.values():
        for url in info.concrete_urls:
            path = _normalize_url_path(url)
            if path is not None:
                paths.add(path)
    return paths


def _normalize_url_path(url: str) -> str | None:
    if not url:
        return None
    path = urlsplit(url).path.rstrip("/") or "/"
    if "{" in path or "}" in path:
        return None
    return path


def _split_path(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _join_segments(segments: list[str]) -> str:
    return "/" + "/".join(segments) if segments else "/"


def _valid_path(segments: list[str], *, allow_parameters: bool) -> bool:
    if not segments or len(segments) > MAX_PATH_DEPTH:
        return False
    if _is_generic_root(segments):
        return False
    if _has_sensitive_segment(segments):
        return False
    if not allow_parameters and any("{" in segment or "}" in segment for segment in segments):
        return False
    return True


def _is_generic_root(segments: list[str]) -> bool:
    lowered = [segment.lower() for segment in segments]
    if len(lowered) == 1:
        return lowered[0] == "api" or bool(VERSION_SEGMENT.fullmatch(lowered[0]))
    if len(lowered) == 2:
        return lowered[0] == "api" and bool(VERSION_SEGMENT.fullmatch(lowered[1]))
    return False


def _has_sensitive_segment(segments: list[str]) -> bool:
    return any(not _safe_literal_segment(segment, allow_parameter=True) for segment in segments)


def _safe_literal_segments(segments: list[str]) -> bool:
    return all(_safe_literal_segment(segment, allow_parameter=False) for segment in segments)


def _safe_literal_segment(segment: str, *, allow_parameter: bool) -> bool:
    if not segment:
        return False
    if not allow_parameter and ("{" in segment or "}" in segment):
        return False
    lowered = segment.lower().replace("-", "_")
    return not any(part in lowered for part in SENSITIVE_SEGMENT_PARTS)


def _probe_id(probe_kind: str, derived_candidate: str) -> str:
    digest = hashlib.sha1(f"{probe_kind}|{derived_candidate}".encode("utf-8")).hexdigest()[:12]
    return f"pr-013d-path-{digest}"


def _dedup_key(record: dict) -> tuple[str, str, str, str]:
    target = record["target"]
    basis = record["construction_basis"]["generation_basis"]
    return (
        record["probe_kind"],
        target["method"],
        target.get("canonical_path") or target.get("candidate_url") or "",
        basis["generation_rule"],
    )


def _record_sort_key(record: dict) -> tuple[str, str, str, str]:
    target = record["target"]
    basis = record["construction_basis"]["generation_basis"]
    return (
        basis["derived_candidate"],
        record["probe_kind"],
        target.get("canonical_path") or target.get("candidate_url") or "",
        basis.get("reason", ""),
    )


def _sorted_limited(records) -> list[dict]:
    return sorted(records, key=_record_sort_key)[:MAX_CANDIDATES_PER_KIND]
