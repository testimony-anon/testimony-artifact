"""Pure audit-only Stage 2.5 composition.

This module plans deterministic candidates from observation-derived Stage2
material and records them as not executed.  It never resolves credentials or
constructs a transport.
"""

from __future__ import annotations

from typing import Any, Iterable

from common.contracts import make_envelope
from stage2_recover.loader import LoadedBundle

from .discovery_planner import plan_discovery_candidates
from .loader import PathInfo, Stage25Inputs


WRITE = {"POST", "PUT", "DELETE", "PATCH"}


def build_audit_only_probe_results(
    initial_structure: dict[str, Any],
    bundles: Iterable[LoadedBundle],
    *,
    run_id: str,
) -> dict[str, Any]:
    """Return the full deterministic Stage2.5 audit view with zero HTTP."""
    by_run_id = {bundle.run_id: bundle for bundle in bundles}
    inputs = Stage25Inputs(
        initial_oas=initial_structure,
        bundles=by_run_id,
        paths=_path_inputs(initial_structure, by_run_id),
    )
    planned = plan_discovery_candidates(inputs)
    return {
        "metadata": make_envelope(
            "probe_results",
            "stage2.5",
            run_id,
            upstream_refs=[
                {
                    "artifact_type": "initial_oas",
                    "run_id": str(initial_structure.get("x-carverflow-meta", {}).get("run_id") or run_id),
                    "path": "in-memory-observational-structure",
                }
            ],
        ),
        "probes": planned.audit_records,
    }


def _path_inputs(
    initial_structure: dict[str, Any],
    bundles: dict[str, LoadedBundle],
) -> dict[str, PathInfo]:
    paths: dict[str, PathInfo] = {}
    for canonical_path, item in initial_structure["paths"].items():
        info = PathInfo(canonical_path=canonical_path)
        body_candidates: list[tuple[str, str, str]] = []
        for method, operation in item.items():
            method_upper = method.upper()
            info.observed_methods.add(method_upper)
            for observation in operation["x-carverflow-observations"]:
                entry = bundles[observation["run_id"]].entries[observation["entry_index"]]
                info.concrete_urls.append(entry["request"]["url"])
                post = entry["request"].get("postData")
                if method_upper in WRITE and post and post.get("text"):
                    ref = f"{observation['run_id']}#{observation['entry_index']}"
                    body_candidates.append((method_upper, ref, post["text"]))
        if body_candidates:
            _method, ref, body = sorted(body_candidates)[0]
            info.reusable_write_body = (ref, body)
        paths[canonical_path] = info
    return paths
