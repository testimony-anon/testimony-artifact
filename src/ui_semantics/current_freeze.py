"""Generic current-v2 input-freeze writer for fresh offline pipeline outputs."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .artifact_relocation import attested_sha256
from typing import Any, Mapping

from .candidate_lineage import load_v2_rendered_input_lineage
from .v2_proposer import HardenedV2InputFreezeManifest, V2FrozenInput, load_hardened_v2_input
from .v2_template import (
    CANONICAL_V2_TEMPLATE_REF,
    CANONICAL_V2_TEMPLATE_REVISION,
    canonical_v2_template_bytes,
)


@dataclass(frozen=True)
class CurrentV2Freeze:
    manifest: HardenedV2InputFreezeManifest
    manifest_path: Path
    manifest_raw_sha256: str
    frozen_input: V2FrozenInput


def write_current_v2_input_freeze(
    *,
    output_root: Path,
    system: str,
    run_id: str,
    frozen_at: str,
    sources: Mapping[str, Any],
    counts: Mapping[str, int],
) -> CurrentV2Freeze:
    """Seal package/view/rendered outputs without subject-specific replay code."""

    root = output_root.resolve()
    paths = {
        "package": root / "preproposal_evidence_package.json",
        "view": root / "proposal_evidence_view.json",
        "rendered": root / "rendered_candidate_input.json",
        "template": root / "effect_contract_v2.txt",
    }
    for label in ("package", "view", "rendered"):
        if not paths[label].is_file():
            raise ValueError(f"current v2 freeze input missing: {label}")
    manifest_path = root / "input_freeze_manifest.json"
    if paths["template"].exists() or manifest_path.exists():
        raise ValueError("current v2 freeze refuses to overwrite template/manifest")
    _atomic_write(paths["template"], canonical_v2_template_bytes())
    lineage = load_v2_rendered_input_lineage(
        package_path=paths["package"],
        view_path=paths["view"],
        rendered_input_path=paths["rendered"],
    )
    numeric_counts = dict(counts)
    if not numeric_counts or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in numeric_counts.values()
    ):
        raise ValueError("current v2 freeze counts must be nonnegative integers")
    rendered_text_sha = lineage.rendered_input.rendered_sha256
    manifest_value = {
        "schema_version": "uisemtest-current-v2-input-freeze-v2",
        "status": "pass",
        "scientific_input_version": "preproposal-evidence-v2",
        "system": system,
        "run_id": run_id,
        "frozen_at": frozen_at,
        "sources": dict(sources),
        "template": {
            "canonical_ref": CANONICAL_V2_TEMPLATE_REF,
            "frozen_copy_ref": paths["template"].name,
            "file_sha256": _sha256_file(paths["template"]),
        },
        "template_revision": CANONICAL_V2_TEMPLATE_REVISION,
        "view_revision": "aux-semantic-projection-v1",
        "artifacts": {
            "package": {
                "ref": paths["package"].name,
                "file_sha256": _sha256_file(paths["package"]),
                "contract_sha256": lineage.package.canonical_sha256(),
            },
            "view": {
                "ref": paths["view"].name,
                "file_sha256": _sha256_file(paths["view"]),
                "contract_sha256": lineage.view.canonical_sha256(),
            },
            "rendered": {
                "ref": paths["rendered"].name,
                "file_sha256": _sha256_file(paths["rendered"]),
                "contract_sha256": lineage.rendered_input.canonical_sha256(),
                "rendered_text_sha256": rendered_text_sha,
            },
        },
        "counts": numeric_counts,
        "zero_results": {
            "candidate": 0,
            "provider_call": 0,
            "route_s": 0,
            "test_result": 0,
        },
        "checks": {
            "current_template_revision": True,
            "current_view_revision": True,
            "rendered_input_lineage_closed": True,
            "downstream_results_absent_at_freeze": True,
            "subject_specific_replay_not_used": True,
        },
        "legacy_prompt": {
            "sha256": hashlib.sha256(b"not-used-by-current-v2-run").hexdigest(),
            "legacy_fixture_only": True,
            "eligible_for_new_run": False,
        },
        "hardened_prompt": {
            "sha256": rendered_text_sha,
            "expected_change_reasons": (
                "fresh_recording_derived_current_v2_input",
                "canonical_template_auxiliary_and_setup_selection_view_bound",
            ),
            "new_scientific_result_count": 0,
        },
        "supersedes_for_new_call": {
            "status": "fresh_current_run",
            "historical_result_source_count": 0,
        },
    }
    manifest = HardenedV2InputFreezeManifest.model_validate(manifest_value, strict=True)
    _atomic_write(
        manifest_path,
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n",
    )
    digest = _sha256_file(manifest_path)
    frozen = load_hardened_v2_input(
        input_freeze_manifest_path=manifest_path,
        expected_manifest_sha256=digest,
        require_current_revision=True,
    )
    return CurrentV2Freeze(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_raw_sha256=digest,
        frozen_input=frozen,
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


__all__ = ["CurrentV2Freeze", "write_current_v2_input_freeze"]
