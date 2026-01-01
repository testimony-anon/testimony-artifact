"""initial_oas assembly (003 D20/D25/D26).

Canonical serialization exit: sort_keys + fixed indentation + ensure_ascii=False + allow_nan=False;
lists carry explicit sort keys (observations by (run_id, entry_index)); envelopes are zeroed when comparing (D25).
"""

from __future__ import annotations

import json
import secrets as _pysecrets
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common.contracts import REPO_ROOT, make_envelope, validate_artifact
from oas_naming import operation_id

from .api_filter import ApiObservation, classify_bundle
from .canonical import CanonicalIndex
from .join import join_bundle
from .loader import LoadedBundle, load_bundles
from .schema_infer import infer_query_parameters, infer_schema


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r{stamp}-{_pysecrets.token_hex(2)}"


def _observation_record(obs: ApiObservation) -> dict:
    record: dict = {
        "run_id": obs.run_id,
        "entry_index": obs.entry_index,
        "timestamp": obs.started_at,
        "status": obs.status,
        "auth_present": obs.auth_present,
    }
    if obs.action_id is not None:
        record["action_id"] = obs.action_id
        record["confidence_tier"] = obs.confidence_tier
    else:
        record["orphan_class"] = obs.orphan_class
    return record


def _build_operation(
    method: str,
    canonical_path: str,
    index: CanonicalIndex,
    group: list[ApiObservation],
) -> dict:
    group = sorted(group, key=lambda o: (o.run_id, o.entry_index))
    operation: dict = {
        "operationId": operation_id(method, canonical_path),
        "x-carverflow-observations": [_observation_record(o) for o in group],
    }

    parameters: list[dict] = []
    for name in index.param_names_for(method, group[0].path):
        parameters.append(
            {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
        )
    parameters.extend(infer_query_parameters([o.query for o in group]))
    if parameters:
        operation["parameters"] = parameters

    # Request body (D24: required = every observation carries a body; bucketed by normalized mime)
    bodies = [o for o in group if o.request_body_text is not None]
    if bodies:
        content: dict = {}
        by_mime: dict[str, list] = defaultdict(list)
        for o in bodies:
            mime = o.request_body_mime or "application/octet-stream"
            if "json" in mime:
                try:
                    by_mime[mime].append(json.loads(o.request_body_text))
                except json.JSONDecodeError:
                    by_mime[mime].append(o.request_body_text)
            else:
                by_mime[mime].append(o.request_body_text)
        for mime in sorted(by_mime):
            content[mime] = {"schema": infer_schema(by_mime[mime])}
        operation["requestBody"] = {
            "required": len(bodies) == len(group),
            "content": content,
        }

    # Responses: bucketed by (status, normalized mime) (D24); status=0 does not enter responses (003A detail 3)
    responses: dict = {}
    by_status_mime: dict[tuple[int, str], list[ApiObservation]] = defaultdict(list)
    for o in group:
        if o.status:
            by_status_mime[(o.status, o.response_mime)].append(o)
    for (status, mime), obs_list in sorted(by_status_mime.items()):
        response = responses.setdefault(
            str(status), {"description": f"Observed response (status {status})"}
        )
        json_bodies = [o.response_body_json for o in obs_list
                       if o.response_body_json is not None]
        if json_bodies and mime:
            response.setdefault("content", {})[mime] = {
                "schema": infer_schema(json_bodies)
            }
    operation["responses"] = responses
    return operation


def recover_initial_oas(bundles: list[LoadedBundle]) -> tuple[dict, list[str]]:
    """Recover the initial_oas document from loaded session bundles (no file output). Returns (document, diagnostic warnings)."""
    all_observations: list[ApiObservation] = []
    warnings: list[str] = []
    for bundle in bundles:
        observations, bundle_warnings = classify_bundle(bundle)
        join_bundle(bundle, observations)
        all_observations.extend(observations)
        warnings.extend(bundle_warnings)

    hosts = sorted({o.scheme_host for o in all_observations})
    if len(hosts) > 1:
        raise ValueError(f"multiple hosts observed; V1 supports a single host only (D26): {hosts}")
    if not all_observations:
        warnings.append("no_api_observations")

    index = CanonicalIndex(all_observations)

    # Canonicalization fallback at the output boundary (D23): each observation maps to exactly one template
    groups: dict[tuple[str, str], list[ApiObservation]] = defaultdict(list)
    for obs in all_observations:
        canonical = index.canonical_path(obs.method, obs.path)
        groups[(obs.method, canonical)].append(obs)

    paths: dict = {}
    for (method, canonical), group in sorted(groups.items(), key=lambda kv: kv[0]):
        paths.setdefault(canonical, {})[method.lower()] = _build_operation(
            method, canonical, index, group
        )

    systems = sorted({b.manifest["session"]["system_under_test"] for b in bundles})
    document = {
        "openapi": "3.1.0",
        "info": {
            "title": f"{'+'.join(systems)} (recovered by the pipeline)",
            "version": "0.0.0-recovered",
        },
        "servers": [{"url": hosts[0]}] if hosts else [],
        "paths": paths,
        "x-carverflow-meta": make_envelope(
            artifact_type="initial_oas",
            stage="stage2",
            run_id=_new_run_id(),
            upstream_refs=[
                {
                    "artifact_type": "session_bundle",
                    "run_id": b.run_id,
                    "path": str(b.bundle_dir),
                }
                for b in sorted(bundles, key=lambda b: b.run_id)
            ],
        ),
    }
    return document, warnings


def canonical_dumps(document: dict) -> str:
    """D25 canonical serialization exit."""
    return json.dumps(
        document, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False
    ) + "\n"


def run_stage2(
    bundle_dirs: list[str | Path],
    artifacts_root: str | Path | None = None,
) -> tuple[dict, Path, list[str]]:
    """Stage 2 entry point: load → recover → contract validation → write to disk (D12 path convention)."""
    bundles = load_bundles(bundle_dirs)
    document, warnings = recover_initial_oas(bundles)
    validate_artifact("initial_oas.schema.json", document)  # schema-validate the artifact before writing

    artifacts_root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = artifacts_root / document["x-carverflow-meta"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "initial_oas.json"
    out_path.write_text(canonical_dumps(document))
    return document, out_path, warnings
