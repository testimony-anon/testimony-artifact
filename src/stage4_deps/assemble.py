"""Stage 4 assembly (005 D35/D40): produce dependency_graph + write dependency edges back into augmented_oas.

Pure-function assembly (never replays any request; grounded is always false; F8); consumes augmented_oas + session_bundle.
"""

from __future__ import annotations

import copy
import json
import secrets as _pysecrets
from datetime import datetime, timezone
from pathlib import Path

from common.contracts import REPO_ROOT, make_envelope, validate_artifact
from common.oas_discovery import is_execution_ready
from stage2_recover.loader import load_bundle

from .valueflow import (
    Stage4Inputs,
    converge_edges,
    extract_candidates,
    scheduled_probe_material_edges,
    template_inference_edges,
)


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r{stamp}-{_pysecrets.token_hex(2)}"


def _operation_ids(augmented_oas: dict) -> list[str]:
    return sorted(op["operationId"] for item in augmented_oas["paths"].values()
                  for op in item.values() if is_execution_ready(op))


def build_dependency_graph(
    augmented_oas: dict,
    bundle_dirs: list[str | Path],
    *,
    ui_trace: dict | None = None,
    semantic_edge_audit: dict | None = None,
    semantic_edge_audit_path: str | None = None,
    run_id: str | None = None,
) -> tuple[dict, dict]:
    """Assemble the dependency_graph (not written to disk). Returns (document, filtered diagnostic counts)."""
    bundles = {b.run_id: b for b in (load_bundle(d) for d in bundle_dirs)}
    inp = Stage4Inputs(augmented_oas=augmented_oas, bundles=bundles)
    candidates, filtered = extract_candidates(inp)
    edges = converge_edges(candidates)
    edges = _merge_edges(
        edges,
        template_inference_edges(augmented_oas),
        scheduled_probe_material_edges(augmented_oas),
    )
    if semantic_edge_audit is not None:
        if ui_trace is None or semantic_edge_audit_path is None:
            raise ValueError("semantic edge merge requires ui_trace and semantic_edge_audit_path")
        validate_artifact("ui_trace.schema.json", ui_trace)
        validate_artifact("semantic_edge_audit.schema.json", semantic_edge_audit)
        edges = _merge_edges(
            edges,
            _semantic_order_edges(
                ui_trace,
                semantic_edge_audit,
                semantic_edge_audit_path=semantic_edge_audit_path,
                allowed_operations=set(_operation_ids(augmented_oas)),
            ),
        )

    envelope = make_envelope(
        artifact_type="dependency_graph",
        stage="stage4",
        run_id=run_id or _new_run_id(),
        upstream_refs=[{
            "artifact_type": "augmented_oas",
            "run_id": augmented_oas["x-carverflow-meta"]["run_id"],
        }],
    )
    if run_id is not None:
        envelope["created_at"] = "1970-01-01T00:00:00.000+00:00"
    document = {
        "metadata": envelope,
        "nodes": _operation_ids(augmented_oas),
        "edges": edges,
    }
    return document, filtered


def _merge_edges(*edge_groups: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str, str], dict] = {}
    for edges in edge_groups:
        for edge in edges:
            family = "semantic_order" if edge.get("kind") == "semantic_order" else "value_binding"
            key = (edge["producer"], edge["consumer"], family)
            existing = merged.get(key)
            if existing is None:
                merged[key] = copy.deepcopy(edge)
                continue
            existing["evidence"].extend(copy.deepcopy(edge.get("evidence") or []))
            existing["confidence"] = max(float(existing.get("confidence") or 0), float(edge.get("confidence") or 0))
            if existing.get("kind") != "auth":
                existing["kind"] = edge.get("kind", existing.get("kind", "data"))
    for edge in merged.values():
        edge["evidence"].sort(key=lambda e: (
            e.get("type", ""),
            e.get("detail", {}).get("to_location", ""),
            e.get("detail", {}).get("to_field", ""),
            e.get("detail", {}).get("from_location", ""),
            e.get("detail", {}).get("from_field", ""),
        ))
    out = list(merged.values())
    out.sort(key=lambda e: (e["producer"], e["consumer"], e.get("kind", "data")))
    return out


def _semantic_order_edges(
    ui_trace: dict,
    semantic_edge_audit: dict,
    *,
    semantic_edge_audit_path: str,
    allowed_operations: set[str],
) -> list[dict]:
    request_details = {
        request["request_ref"]: (request["operation_id"], request["actor_id"])
        for request in ui_trace.get("api_requests", [])
    }
    audit_run_id = semantic_edge_audit["metadata"]["run_id"]
    seen_ids: set[str] = set()
    edges: list[dict] = []
    for candidate in semantic_edge_audit.get("candidates", []):
        candidate_id = candidate["candidate_id"]
        if candidate_id in seen_ids:
            raise ValueError(f"duplicate semantic candidate id: {candidate_id}")
        seen_ids.add(candidate_id)
        if candidate["semantic_verdict"] != "confirmed":
            continue
        producer_ref = candidate["producer"]["request_ref"]
        consumer_ref = candidate["consumer"]["request_ref"]
        if producer_ref not in request_details or consumer_ref not in request_details:
            raise ValueError(f"confirmed semantic edge {candidate_id} references an unmapped request")
        producer, producer_actor = request_details[producer_ref]
        consumer, consumer_actor = request_details[consumer_ref]
        if candidate["producer"]["actor_id"] != producer_actor or candidate["consumer"]["actor_id"] != consumer_actor:
            raise ValueError(f"confirmed semantic edge {candidate_id} actor does not match ui_trace")
        if producer not in allowed_operations or consumer not in allowed_operations:
            raise ValueError(f"confirmed semantic edge {candidate_id} references an operation outside augmented OAS")
        if producer == consumer:
            raise ValueError(f"confirmed semantic edge {candidate_id} collapses to one operation")
        edges.append(
            {
                "producer": producer,
                "consumer": consumer,
                "kind": "semantic_order",
                "confidence": 1.0,
                "evidence": [
                    {
                        "type": "business_semantic",
                        "detail": {
                            "semantic_edge_id": candidate_id,
                            "audit_ref": {
                                "artifact_type": "semantic_edge_audit",
                                "run_id": audit_run_id,
                                "path": semantic_edge_audit_path,
                                "record_id": candidate_id,
                            },
                        },
                    }
                ],
            }
        )
    return edges


def writeback_augmented(augmented_oas: dict, dependency_graph: dict) -> dict:
    """Write each edge back into x-carverflow-dependencies of its producer operation (005A, rule 3)."""
    aug = copy.deepcopy(augmented_oas)
    by_producer: dict[str, list[dict]] = {}
    for edge in dependency_graph["edges"]:
        by_producer.setdefault(edge["producer"], []).append(edge)
    for item in aug["paths"].values():
        for op in item.values():
            deps = by_producer.get(op["operationId"])
            if deps:
                op["x-carverflow-dependencies"] = deps
    return aug


def canonical_dumps(document: dict) -> str:
    """D40: canonical serialization output (same rule as every stage)."""
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"


def edge_set(document: dict) -> set[tuple[str, str]]:
    return {(e["producer"], e["consumer"]) for e in document["edges"]}


def run_stage4(
    augmented_oas_path: str | Path,
    bundle_dirs: list[str | Path],
    artifacts_root: str | Path | None = None,
    *,
    ui_trace_path: str | Path | None = None,
    semantic_edge_audit_path: str | Path | None = None,
) -> tuple[dict, dict, Path, dict]:
    """Main entry point: load (schema-validated) -> assemble -> write back -> validate -> write to disk.
    Returns (dependency_graph, augmented_oas after write-back, path of the written dependency_graph, filtered counts)."""
    augmented_oas = json.loads(Path(augmented_oas_path).read_text())
    validate_artifact("augmented_oas.schema.json", augmented_oas)

    ui_trace = json.loads(Path(ui_trace_path).read_text()) if ui_trace_path is not None else None
    semantic_edge_audit = (
        json.loads(Path(semantic_edge_audit_path).read_text())
        if semantic_edge_audit_path is not None
        else None
    )
    document, filtered = build_dependency_graph(
        augmented_oas,
        bundle_dirs,
        ui_trace=ui_trace,
        semantic_edge_audit=semantic_edge_audit,
        semantic_edge_audit_path=str(semantic_edge_audit_path) if semantic_edge_audit_path is not None else None,
    )
    validate_artifact("dependency_graph.schema.json", document)  # schema-validate before writing

    aug_back = writeback_augmented(augmented_oas, document)
    validate_artifact("augmented_oas.schema.json", aug_back)  # still schema-valid after write-back

    artifacts_root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = artifacts_root / document["metadata"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    dep_path = run_dir / "dependency_graph.json"
    dep_path.write_text(canonical_dumps(document))
    (run_dir / "augmented_oas.json").write_text(canonical_dumps(aug_back))
    return document, aug_back, dep_path, filtered
