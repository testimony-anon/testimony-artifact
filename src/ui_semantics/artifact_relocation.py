"""Content-hash attestation for relocated reproduction packages.

The reproduction package rewrites absolute machine paths inside a few provenance
manifests (recording session manifests, recording input manifests, recording
workflow results) to neutral placeholders.  Those files are pinned by SHA-256 in
the frozen lineage (recording bundle, input freeze manifest, M10 completion, ...),
so the rewritten bytes would no longer match their pins.  The package therefore
ships ``docs/artifact-relocation.json`` with a map from the SHA-256 of every
rewritten file to the SHA-256 of its original bytes.  ``attested_sha256`` returns
the original digest for such a file and the plain digest for every other file, so
every pin check in the pipeline sees the values recorded during the study while
the shipped bytes stay free of machine paths.

Outside a relocated package (no attestation file) this is exactly ``sha256`` of
the file bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_ATTESTATION: dict[str, dict[str, object]] | None = None


def attestation_path() -> Path:
    override = os.environ.get("UISEMTEST_RELOCATION_ATTESTATION")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "docs/artifact-relocation.json"


def _load() -> dict[str, dict[str, object]]:
    global _ATTESTATION
    if _ATTESTATION is None:
        path = attestation_path()
        mapping: dict[str, dict[str, object]] = {}
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = payload.get("sha256_map") if isinstance(payload, dict) else None
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(value, str):
                        mapping[str(key)] = {"sha256": value}
                    elif isinstance(value, dict) and isinstance(value.get("sha256"), str):
                        entry: dict[str, object] = {"sha256": value["sha256"]}
                        if isinstance(value.get("bytes"), int) and not isinstance(value.get("bytes"), bool):
                            entry["bytes"] = value["bytes"]
                        mapping[str(key)] = entry
        _ATTESTATION = mapping
    return _ATTESTATION


def reset_cache() -> None:
    global _ATTESTATION
    _ATTESTATION = None


def raw_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attested_sha256(path: Path | str) -> str:
    """SHA-256 of a file, translated to its pre-relocation digest when attested."""
    digest = raw_sha256(path)
    entry = _load().get(digest)
    return str(entry["sha256"]) if entry else digest


def attested_size(path: Path | str) -> int:
    """Byte size of a file, translated to its pre-relocation size when attested."""
    size = Path(path).stat().st_size
    mapping = _load()
    if not mapping:
        return size
    entry = mapping.get(raw_sha256(path))
    if entry and isinstance(entry.get("bytes"), int):
        return int(entry["bytes"])
    return size
