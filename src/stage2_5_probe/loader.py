"""Stage 2.5 input loading (004 consumption contract: initial_oas + session_bundle).

Takes canonical templates and observed methods from initial_oas; follows the observations' run_id+entry_index back to the
session bundle HAR for concrete URLs and observed write bodies (D29/D20). Consumers schema-validate their input (contract rules).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from common.contracts import validate_artifact
from stage2_recover.loader import LoadedBundle, load_bundle


@dataclass
class PathInfo:
    canonical_path: str
    observed_methods: set[str] = field(default_factory=set)
    concrete_urls: list[str] = field(default_factory=list)
    # observed write body for this path: (reused_request_ref, body_text) or (None, None)
    reusable_write_body: tuple[str | None, str | None] = (None, None)


@dataclass
class Stage25Inputs:
    initial_oas: dict
    bundles: dict[str, LoadedBundle]
    paths: dict[str, PathInfo]


WRITE = {"POST", "PUT", "DELETE", "PATCH"}


def load_inputs(initial_oas_path: str | Path, bundle_dirs: list[str | Path]) -> Stage25Inputs:
    initial_oas = json.loads(Path(initial_oas_path).read_text())
    validate_artifact("initial_oas.schema.json", initial_oas)
    bundles = {b.run_id: b for b in (load_bundle(d) for d in bundle_dirs)}

    paths: dict[str, PathInfo] = {}
    for canonical_path, item in initial_oas["paths"].items():
        info = PathInfo(canonical_path=canonical_path)
        write_body_candidates: list[tuple[str, str, str]] = []  # (method, ref, body)
        for method, op in item.items():
            info.observed_methods.add(method.upper())
            for obs in op["x-carverflow-observations"]:
                entry = bundles[obs["run_id"]].entries[obs["entry_index"]]
                info.concrete_urls.append(entry["request"]["url"])
                post = entry["request"].get("postData")
                if method.upper() in WRITE and post and post.get("text"):
                    ref = f"{obs['run_id']}#{obs['entry_index']}"
                    write_body_candidates.append((method.upper(), ref, post["text"]))
        if write_body_candidates:
            # deterministic pick: sort by (method, ref) and take the first non-empty body
            method, ref, body = sorted(write_body_candidates)[0]
            info.reusable_write_body = (ref, body)
        paths[canonical_path] = info

    return Stage25Inputs(initial_oas=initial_oas, bundles=bundles, paths=paths)
