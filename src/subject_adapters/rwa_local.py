"""Minimal local reset adapter for the current RWA subject bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: dict[str, object]) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode()
        + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def reset(*, url: str, output: Path) -> dict[str, object]:
    started_at = _utc_now()
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
        status = response.status
    if not 200 <= status < 300:
        raise RuntimeError(f"RWA reset failed with HTTP {status}")
    finished_at = _utc_now()
    body_sha = hashlib.sha256(body).hexdigest()
    value: dict[str, object] = {
        "schema_version": "uisemtest-rwa-local-reset-v1",
        "system": "rwa",
        "adapter": "rwa_test_data_seed",
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "response_sha256": body_sha,
        "reset_epoch_ref": f"rwa:{body_sha[:16]}:{finished_at}",
    }
    _write_json(output, value)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    reset_parser = subparsers.add_parser("reset")
    reset_parser.add_argument(
        "--url", default="http://localhost:14001/testData/seed"
    )
    reset_parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    value = reset(url=args.url, output=args.output)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
