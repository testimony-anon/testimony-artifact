"""Session bundle validity checker (002 D17: criterion = the manifest exists and passes the schema; each member passes its schema)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from common.contracts import ContractValidationError, validate_artifact
from common.request_material_shape import (
    RequestMaterialShapeError,
    load_request_material_shapes,
)


def validate_session_bundle(bundle_dir: str | Path) -> tuple[bool, list[str]]:
    """Return (is_valid, list of problems). A directory without a manifest is an invalid bundle."""
    bundle_dir = Path(bundle_dir)
    problems: list[str] = []

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        return False, ["manifest.json does not exist (interrupted/crashed bundle, invalid per D17)"]
    try:
        manifest = json.loads(manifest_path.read_text())
        validate_artifact("session_bundle_manifest.schema.json", manifest)
    except (json.JSONDecodeError, ContractValidationError) as exc:
        return False, [f"manifest is invalid: {exc}"]

    members = manifest["members"]
    har_path = bundle_dir / members["har"]
    if not har_path.is_file():
        problems.append("har.json is missing")
    else:
        try:
            har = json.loads(har_path.read_text())
            validate_artifact("session_bundle_har.schema.json", har)
            load_request_material_shapes(bundle_dir, manifest, har["log"]["entries"])
        except (json.JSONDecodeError, ContractValidationError) as exc:
            problems.append(f"har is invalid: {exc}")
        except RequestMaterialShapeError as exc:
            problems.append(f"request_material_shapes is invalid: {exc}")

    for member, schema in (
        ("ui_action_log", "session_bundle_ui_action.schema.json"),
        ("action_decision_log", "session_bundle_action_decision.schema.json"),
    ):
        path = bundle_dir / members[member]
        if not path.is_file():
            problems.append(f"{member} is missing")
            continue
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                validate_artifact(schema, json.loads(line))
            except (json.JSONDecodeError, ContractValidationError) as exc:
                problems.append(f"{member}:{i} is invalid: {exc}")

    for ps in members["page_state"]:
        ps_path = bundle_dir / ps["file"] if not ps["file"].endswith(".gz") else bundle_dir / ps["file"]
        if not ps_path.is_file():
            problems.append(f"page_state file is missing: {ps['file']}")
            continue
        try:
            with gzip.open(ps_path, "rt", encoding="utf-8") as f:
                json.load(f)
        except Exception as exc:
            problems.append(f"page_state file is unreadable: {ps['file']}: {exc}")

    return (not problems), problems
