"""Publish validated current-run scratch artifacts at a requested review level."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

from .artifact_relocation import attested_sha256
from typing import Any, Mapping


OUTPUT_LEVELS = ("paper", "debug", "forensic")

_REDUNDANT_PARTS = frozenset({"partials", "capabilities"})
_REDUNDANT_BASENAMES = frozenset(
    {
        "no_feedback.json",
        "pre_render_scan.json",
        "post_render_scan.json",
        "artifact_manifest.json",
        "recursive_manifest.json",
    }
)

_PAPER_EVIDENCE_ARTIFACTS = (
    "recording_bundle",
    "ui_api_trace",
    "observational_api_structure",
    "observed_api_catalog",
    "discovery_candidate_audit",
    "evidence_bundle",
    "producer_applicability",
    "observed_value_flow_set",
    "dependency_graph",
    "binding_opportunity_set",
)


def scientific_summary_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the path-free scientific counts used to compare publications."""

    stages = {
        str(row["stage"]): row.get("counts", {})
        for row in manifest.get("stages", [])
        if isinstance(row, Mapping) and isinstance(row.get("stage"), str)
    }
    m11b = stages.get("M11b", {})
    return {
        "proposal": copy.deepcopy(manifest["current_counts"]["proposal"]),
        "materialization": {
            key: copy.deepcopy(m11b[key])
            for key in (
                "input_candidates",
                "materialized_candidates",
                "materialization_ineligible",
            )
            if key in m11b
        },
        "route_s": {
            key: copy.deepcopy(manifest["current_counts"][key])
            for key in (
                "candidate_count",
                "attempted_count",
                "evaluable_count",
                "local_not_evaluable_count",
                "outcomes",
                "protocol_verdicts",
                "confirmed_count",
            )
        },
        "generated_test_count": copy.deepcopy(
            manifest["current_counts"]["generated_test_count"]
        ),
        "retained_test_count": copy.deepcopy(
            manifest["current_counts"]["retained_test_count"]
        ),
        "denominators": copy.deepcopy(manifest["denominators"]),
        "auth_session": copy.deepcopy(
            manifest["current_counts"].get("auth_session", {})
        ),
        "total_generated_test_count": copy.deepcopy(
            manifest["current_counts"].get("total_generated_test_count", 0)
        ),
        "total_retained_test_count": copy.deepcopy(
            manifest["current_counts"].get("total_retained_test_count", 0)
        ),
        "admitted_canonical_relation_core_identities": copy.deepcopy(
            manifest["current_counts"].get("admitted_canonical_relation_core_identities")
        ),
        "retained_canonical_relation_core_identities": copy.deepcopy(
            manifest["current_counts"].get("retained_canonical_relation_core_identities")
        ),
    }


def scientific_summary_sha256(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(scientific_summary_payload(manifest))
    ).hexdigest()


def publish_current_output(
    *,
    scratch_root: Path,
    target_root: Path,
    output_level: str,
) -> dict[str, Any]:
    """Atomically publish artifacts generated for the requested output level.

    ``omitted_file_count`` counts generated publication artifacts replaced by
    the final review projection, not logical forensic refs or runtime scratch.
    """

    if output_level not in OUTPUT_LEVELS:
        raise ValueError(f"unknown current output level: {output_level!r}")
    scratch = scratch_root.resolve(strict=True)
    target = target_root.resolve()
    if target.exists():
        raise ValueError("publication target must remain fresh")
    omitted_count = 0
    direct_write = True
    if output_level == "paper":
        reset_root = scratch / "runtime/resets"
        if reset_root.exists():
            shutil.rmtree(reset_root)
        runtime_root = scratch / "runtime"
        if runtime_root.is_dir() and not any(runtime_root.iterdir()):
            runtime_root.rmdir()
        _replace_paper_evidence_package(scratch)
        omitted_count = 1 + _remove_paper_recording_snapshots(scratch)
        direct_write = False

    source_files = _file_map(scratch)
    full_manifest = _read_object(scratch / "run_manifest.json")
    summary_sha = scientific_summary_sha256(full_manifest)

    if output_level == "forensic":
        forensic_manifest = copy.deepcopy(full_manifest)
        forensic_manifest.update(
            {
                "output_level": "forensic",
                "generated_file_count": len(source_files),
                "retained_file_count": len(source_files),
                "omitted_file_count": 0,
                "forensic_logical_refs_materialized": True,
                "scientific_summary_sha256": summary_sha,
            }
        )
        _replace_bytes(
            scratch / "run_manifest.json",
            _canonical_json_bytes(forensic_manifest),
        )
        os.replace(scratch, target)
        return {
            "output_level": output_level,
            "generated_file_count": len(source_files),
            "retained_file_count": len(source_files),
            "omitted_file_count": 0,
            "forensic_logical_refs_materialized": True,
            "scientific_summary_sha256": summary_sha,
        }

    _validate_publication_paths(source_files, output_level=output_level)
    retained_files = sorted({*source_files, "publication_inventory.json"})
    retained_count = len(retained_files)
    generated_count = retained_count + omitted_count
    inventory = {
        "schema_version": "uisemtest-current-publication-inventory-v1",
        "output_level": output_level,
        "direct_write": direct_write,
        "generated_file_count": generated_count,
        "retained_file_count": retained_count,
        "omitted_file_count": omitted_count,
        "forensic_logical_refs_materialized": False,
        "retained_by_stage": _count_by_stage(retained_files),
        "retained_files": retained_files,
        "scientific_summary_sha256": summary_sha,
    }
    slim_manifest = _publication_manifest(
        full_manifest,
        output_level=output_level,
        direct_write=direct_write,
        generated_file_count=generated_count,
        retained_file_count=retained_count,
        omitted_file_count=omitted_count,
        scientific_summary_sha=summary_sha,
    )
    _replace_bytes(
        scratch / "run_manifest.json",
        _canonical_json_bytes(slim_manifest),
    )
    _write_bytes(
        scratch / "publication_inventory.json",
        _canonical_json_bytes(inventory),
    )
    published_files = _file_map(scratch)
    if sorted(published_files) != retained_files:
        raise ValueError("publication inventory differs from generated files")
    _validate_publication_paths(published_files, output_level=output_level)
    os.replace(scratch, target)
    return {
        "output_level": output_level,
        "generated_file_count": generated_count,
        "retained_file_count": retained_count,
        "omitted_file_count": omitted_count,
        "forensic_logical_refs_materialized": False,
        "scientific_summary_sha256": summary_sha,
    }


def _publication_manifest(
    full: Mapping[str, Any],
    *,
    output_level: str,
    direct_write: bool,
    generated_file_count: int,
    retained_file_count: int,
    omitted_file_count: int,
    scientific_summary_sha: str,
) -> dict[str, Any]:
    keep = (
        "schema_version",
        "status",
        "completion_reason",
        "terminal_status",
        "paper_data",
        "canonical_entrypoint",
        "run_id",
        "output_root",
        "environment",
        "inputs",
        "method_hashes",
        "provider_replay",
        "contract_hashes",
        "current_counts",
        "denominators",
        "counters",
        "active_execution_lock_unchanged",
        "execution_authorization",
        "offline_lock",
    )
    result = {key: copy.deepcopy(full[key]) for key in keep if key in full}
    result.update(
        {
            "output_level": output_level,
            "publication_view": "paper_review" if output_level == "paper" else "debug_review",
            "direct_write": direct_write,
            "forensic_replay_closure_published": False,
            "generated_file_count": generated_file_count,
            "retained_file_count": retained_file_count,
            "omitted_file_count": omitted_file_count,
            "forensic_logical_refs_materialized": False,
            "publication_inventory": "publication_inventory.json",
            "scientific_summary_sha256": scientific_summary_sha,
            "scientific_summary_scope": (
                "aggregate_counts_partitions_denominators;"
                "excludes_candidate_and_run_identity"
            ),
            "stages": [
                {
                    key: copy.deepcopy(row[key])
                    for key in (
                        "stage",
                        "status",
                        "consumer",
                        "contract",
                        "schema",
                        "counts",
                        "activity_counts",
                    )
                    if key in row
                }
                for row in full["stages"]
            ],
        }
    )
    return result


def _validate_publication_paths(
    files: Mapping[str, Path],
    *,
    output_level: str,
) -> None:
    for ref in files:
        path = Path(ref)
        if any(part in _REDUNDANT_PARTS for part in path.parts):
            raise ValueError(f"redundant artifact escaped publication: {ref}")
        if path.name in _REDUNDANT_BASENAMES:
            raise ValueError(f"redundant manifest escaped publication: {ref}")
        if output_level == "paper" and "raw" in path.parts:
            raise ValueError(f"raw artifact escaped paper publication: {ref}")


def _replace_paper_evidence_package(root: Path) -> None:
    m1_9 = root / "M01_09"
    package_path = m1_9 / "preproposal_evidence_package.json"
    package = _read_object(package_path)
    artifact_hashes = package.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict) or set(artifact_hashes) != set(
        _PAPER_EVIDENCE_ARTIFACTS
    ):
        raise ValueError("paper evidence package artifact set is incomplete")
    artifact_payloads = package.get("artifact_payloads")
    if not isinstance(artifact_payloads, dict) or set(artifact_payloads) != set(
        _PAPER_EVIDENCE_ARTIFACTS
    ):
        raise ValueError("paper evidence package payload set is incomplete")

    artifacts: dict[str, dict[str, str]] = {}
    for name in _PAPER_EVIDENCE_ARTIFACTS:
        artifact_path = m1_9 / f"{name}.json"
        artifact = _read_object(artifact_path)
        canonical_sha = hashlib.sha256(
            _canonical_json_bytes(artifact)
        ).hexdigest()
        if canonical_sha != artifact_hashes[name]:
            raise ValueError("paper evidence artifact differs from package pin")
        if artifact != artifact_payloads[name]:
            raise ValueError("paper evidence artifact differs from package payload")
        artifacts[name] = {
            "path": artifact_path.relative_to(root).as_posix(),
            "file_sha256": _sha256_file(artifact_path),
            "contract_sha256": canonical_sha,
        }

    index = {
        "schema_version": "uisemtest-current-paper-evidence-index-v1",
        "replaces_ref": package_path.relative_to(root).as_posix(),
        "replaced_file_sha256": _sha256_file(package_path),
        "package_canonical_sha256": hashlib.sha256(
            _canonical_json_bytes(package)
        ).hexdigest(),
        "package_metadata": {
            key: copy.deepcopy(value)
            for key, value in package.items()
            if key != "artifact_payloads"
        },
        "artifacts": artifacts,
        "full_package_reconstructible_from_retained_artifacts": True,
    }
    _write_bytes(
        m1_9 / "paper_evidence_index.json",
        _canonical_json_bytes(index),
    )
    package_path.unlink()


def _remove_paper_recording_snapshots(root: Path) -> int:
    """Remove machine-local recording manifests from the paper projection."""

    recording_snapshots = root / "inputs/recording"
    if not recording_snapshots.exists():
        return 0
    omitted = sum(1 for path in recording_snapshots.rglob("*") if path.is_file())
    shutil.rmtree(recording_snapshots)
    return omitted


def _count_by_stage(refs: list[str]) -> dict[str, int]:
    counts = Counter(
        Path(ref).parts[0] if len(Path(ref).parts) > 1 else "run"
        for ref in refs
    )
    return dict(sorted(counts.items()))


def _file_map(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"publication refuses to overwrite: {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _replace_bytes(path: Path, payload: bytes) -> None:
    if not path.is_file():
        raise ValueError(f"publication manifest is missing: {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


__all__ = [
    "OUTPUT_LEVELS",
    "publish_current_output",
    "scientific_summary_payload",
    "scientific_summary_sha256",
]
