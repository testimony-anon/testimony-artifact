"""Stage 5 assembly (006 D45/D46): produce test_sequences + skills.

Pure function (zero outbound requests; Stage 5 executes nothing); every artifact has status=candidate (grounded
meaning = unverified hypothesis); canonical serialization is byte-for-byte deterministic.
"""

from __future__ import annotations

import json
import secrets as _pysecrets
from datetime import datetime, timezone
from pathlib import Path

from common.contracts import REPO_ROOT, make_envelope, validate_artifact

from .synth import synthesize


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r{stamp}-{_pysecrets.token_hex(2)}"


def build_artifacts(augmented_oas: dict, dependency_graph: dict) -> tuple[dict, dict]:
    """Assemble the (test_sequences, skills) documents (not written to disk)."""
    sequences, skills = synthesize(augmented_oas, dependency_graph)
    upstream = [
        {"artifact_type": "augmented_oas", "run_id": augmented_oas["x-carverflow-meta"]["run_id"]},
        {"artifact_type": "dependency_graph", "run_id": dependency_graph["metadata"]["run_id"]},
    ]
    ts_doc = {
        "metadata": make_envelope("test_sequences", "stage5", _new_run_id(), upstream_refs=upstream),
        "sequences": sequences,
    }
    sk_doc = {
        "metadata": make_envelope("skills", "stage5", ts_doc["metadata"]["run_id"], upstream_refs=upstream),
        "skills": skills,
    }
    return ts_doc, sk_doc


def canonical_dumps(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"


def run_stage5(augmented_oas_path: str | Path, dependency_graph_path: str | Path,
               artifacts_root: str | Path | None = None) -> tuple[dict, dict, Path]:
    """Main entry point: load (schema-validated) -> assemble -> validate -> write to disk. Returns (test_sequences, skills, directory)."""
    augmented_oas = json.loads(Path(augmented_oas_path).read_text())
    validate_artifact("augmented_oas.schema.json", augmented_oas)
    dependency_graph = json.loads(Path(dependency_graph_path).read_text())
    validate_artifact("dependency_graph.schema.json", dependency_graph)

    ts_doc, sk_doc = build_artifacts(augmented_oas, dependency_graph)
    validate_artifact("test_sequences.schema.json", ts_doc)
    validate_artifact("skills.schema.json", sk_doc)

    artifacts_root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = artifacts_root / ts_doc["metadata"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "test_sequences.json").write_text(canonical_dumps(ts_doc))
    (run_dir / "skills.json").write_text(canonical_dumps(sk_doc))
    return ts_doc, sk_doc, run_dir
