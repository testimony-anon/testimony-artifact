"""Session bundle loading (003 D20: 1 to N bundles; consumers schema-validate what they read, per the contract rules)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from common.contracts import validate_artifact
from common.request_material_shape import load_request_material_shapes


@dataclass
class LoadedBundle:
    bundle_dir: Path
    run_id: str
    manifest: dict
    entries: list[dict]  # HAR log.entries; the list index is the observations' entry_index
    actions: list[dict]  # ui_action_log records, one per line
    decisions: list[dict] = field(default_factory=list)  # deterministic_workflow decisions
    request_material_shapes: Mapping[int, dict] = field(
        default_factory=lambda: MappingProxyType({})
    )


def load_bundle(bundle_dir: str | Path) -> LoadedBundle:
    bundle_dir = Path(bundle_dir)
    manifest = json.loads((bundle_dir / "manifest.json").read_text())
    validate_artifact("session_bundle_manifest.schema.json", manifest)

    har = json.loads((bundle_dir / manifest["members"]["har"]).read_text())
    validate_artifact("session_bundle_har.schema.json", har)

    actions = []
    for line in (bundle_dir / manifest["members"]["ui_action_log"]).read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            validate_artifact("session_bundle_ui_action.schema.json", record)
            actions.append(record)

    decisions = []
    for line in (bundle_dir / manifest["members"]["action_decision_log"]).read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            validate_artifact("session_bundle_action_decision.schema.json", record)
            decisions.append(record)

    entries = har["log"]["entries"]
    request_material_shapes = load_request_material_shapes(bundle_dir, manifest, entries)

    return LoadedBundle(
        bundle_dir=bundle_dir,
        run_id=manifest["metadata"]["run_id"],
        manifest=manifest,
        entries=entries,
        actions=actions,
        decisions=decisions,
        request_material_shapes=MappingProxyType(request_material_shapes),
    )


def load_bundles(bundle_dirs: list[str | Path]) -> list[LoadedBundle]:
    bundles = [load_bundle(d) for d in bundle_dirs]
    if not bundles:
        raise ValueError("at least one session bundle is required (D20)")
    return bundles
