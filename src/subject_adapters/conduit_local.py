"""Minimal Docker Compose lifecycle for the current local Conduit subject."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


_DIAGNOSTIC_LIMIT = 4096
_SECRET_NAME_MARKERS = ("password", "token", "secret", "cookie", "authorization")
_SECRET_HEADER = re.compile(
    r"(?i)(\b(?:authorization|cookie|set-cookie)\b\s*:\s*)[^\r\n]*"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|token|secret)\b\s*[:=]\s*)[^\s,;]+"
)
_URI_USERINFO = re.compile(
    r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@"
)
_LOCAL_TOOL_PATHS = ("/usr/local/bin", "/opt/homebrew/bin")


class LifecyclePhaseError(RuntimeError):
    """One stable, bounded, sanitized lifecycle failure."""

    def __init__(
        self,
        phase: str,
        reason_code: str,
        *,
        exit_code: int | None = None,
        stdout: object = "",
        stderr: object = "",
    ) -> None:
        super().__init__(f"{phase}:{reason_code}")
        self.record = {
            "phase": phase,
            "reason_code": reason_code,
            "exit_code": exit_code,
            "stdout": _redact_diagnostic(stdout),
            "stderr": _redact_diagnostic(stderr),
        }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _redact_diagnostic(value: object) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    secrets = sorted(
        {
            item
            for name, item in os.environ.items()
            if item
            and len(item) >= 4
            and any(marker in name.casefold() for marker in _SECRET_NAME_MARKERS)
        },
        key=len,
        reverse=True,
    )
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    text = _SECRET_HEADER.sub(r"\1[REDACTED]", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = _URI_USERINFO.sub(r"\1[REDACTED]@", text)
    return text[-_DIAGNOSTIC_LIMIT:]


def _phase_failure(error: BaseException, phase: str) -> dict[str, object]:
    if isinstance(error, LifecyclePhaseError):
        return dict(error.record)
    if isinstance(error, subprocess.TimeoutExpired):
        return LifecyclePhaseError(
            phase,
            "phase_timeout",
            stdout=error.stdout,
            stderr=error.stderr,
        ).record
    return LifecyclePhaseError(phase, type(error).__name__).record


def _project_name() -> str:
    output_root = Path(os.environ["UISEMTEST_CONDUIT_OUTPUT_ROOT"]).resolve()
    digest = hashlib.sha256(str(output_root).encode()).hexdigest()[:16]
    return f"uisemtest-conduit-{digest}"


def _deploy_root() -> Path:
    root = Path(os.environ["UISEMTEST_CONDUIT_DEPLOY_ROOT"]).resolve(strict=True)
    if not (root / "docker-compose.yml").is_file() or not (root / "reset.sh").is_file():
        raise RuntimeError("Conduit deployment root is incomplete")
    return root


def _run_phase(
    phase: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            command,
            cwd=_deploy_root(),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise LifecyclePhaseError(
            phase,
            "phase_timeout",
            stdout=error.stdout,
            stderr=error.stderr,
        ) from error
    if completed.returncode != 0:
        raise LifecyclePhaseError(
            phase,
            "command_failed",
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def _compose(
    *args: str,
    phase: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    command = [
        "docker",
        "compose",
        "-p",
        _project_name(),
        "-f",
        str(_deploy_root() / "docker-compose.yml"),
        *args,
    ]
    if check:
        return _run_phase(phase, command, env=_lifecycle_env(), timeout=300)
    try:
        return subprocess.run(
            command,
            cwd=_deploy_root(),
            env=_lifecycle_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise LifecyclePhaseError(
            phase,
            "phase_timeout",
            stdout=error.stdout,
            stderr=error.stderr,
        ) from error


def _lifecycle_env() -> dict[str, str]:
    env = dict(os.environ)
    path_entries = [item for item in env.get("PATH", "").split(os.pathsep) if item]
    for entry in _LOCAL_TOOL_PATHS:
        if entry not in path_entries:
            path_entries.append(entry)
    env["PATH"] = os.pathsep.join(path_entries)
    env["COMPOSE_PROJECT_NAME"] = _project_name()
    return env


def _wait_http(url: str, timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.25)
    raise LifecyclePhaseError("health", "readiness_timeout")


def _write_json(path: Path, value: dict[str, object]) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def supervise() -> int:
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    existing = _compose("ps", "-q", phase="freshness_check")
    if existing.stdout.strip():
        raise LifecyclePhaseError("freshness_check", "project_not_fresh")
    try:
        _compose("up", "-d", "--build", phase="compose_start")
        _wait_http("http://127.0.0.1:3001/api/tags")
        _wait_http("http://127.0.0.1:3001/")
        while not stopping:
            time.sleep(0.1)
    finally:
        _compose(
            "down",
            "--timeout",
            "2",
            "-v",
            "--remove-orphans",
            phase="compose_stop",
            check=False,
        )
    return 0


def reset(output: Path) -> int:
    started_at = _utc_now()
    try:
        _run_phase(
            "reset_database_and_accounts",
            [str(_deploy_root() / "reset.sh")],
            env=_lifecycle_env(),
            timeout=120,
        )
        _wait_http("http://127.0.0.1:3001/api/tags", timeout=30)
        finished_at = _utc_now()
        epoch_material = f"{_project_name()}:{finished_at}".encode()
        value: dict[str, object] = {
            "schema_version": "uisemtest-conduit-local-reset-v1",
            "system": "conduit",
            "adapter": "docker_compose_database_reset",
            "status": 200,
            "started_at": started_at,
            "finished_at": finished_at,
            "reset_epoch_ref": (
                "conduit-current:"
                + hashlib.sha256(epoch_material).hexdigest()[:24]
            ),
        }
    except BaseException as error:
        value = {
            "schema_version": "uisemtest-conduit-local-reset-v1",
            "system": "conduit",
            "status": 500,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "failure": _phase_failure(error, "reset"),
        }
    _write_json(output, value)
    if int(value["status"]) == 200:
        return 0
    print(json.dumps(value["failure"], sort_keys=True), file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("supervise")
    reset_parser = subparsers.add_parser("reset")
    reset_parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.mode == "supervise":
        return supervise()
    return reset(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
