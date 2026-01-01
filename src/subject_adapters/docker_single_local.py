"""Subject-agnostic single-container Docker lifecycle for current local subjects.

This module is the generic counterpart of ``conduit_local`` (docker compose)
and ``rwa_local`` (HTTP seed endpoint): every application that ships as one
Docker image and exposes its whole surface on loopback HTTP can be supervised
and reset from *data* instead of a new Python module per subject.

The data lives in the subject's ``fixtures/adapters/<subject>_current_local.json``
under the optional, additive ``docker_single`` key (schema
``contracts/current_subject_adapter_v1.schema.json``).  Interface parity with
``conduit_local``:

* ``supervise``  start the container, wait for readiness, run the optional seed
  script, then block until SIGTERM/SIGINT and tear the container (and its
  ``fresh_on_reset`` volumes) down.
* ``reset --output <path>``  apply the declared reset strategy, wait for
  readiness again, re-run the seed script and write the reset artifact that
  ``LocalHttpCurrentTargetRuntime._reset_for_replay`` consumes
  (``status`` 2xx + ``reset_epoch_ref``).
* ``readiness``  offline-friendly diagnostic: wait for the declared probes only.

Determinism and blast-radius rules enforced here, not left to the operator:

* the image is always addressed as ``repository@sha256:...``; a tag alone is
  refused, so a moving ``:latest`` can never enter a study run;
* published ports are bound to ``127.0.0.1`` only, and host ports already owned
  by the pinned Conduit / RWA / Mattermost subjects are refused;
* readiness probes must be loopback HTTP;
* ``supervise`` refuses to start when a container of the same deterministic name
  already exists (same freshness rule as ``conduit_local``), so a hand-started
  stack is never silently reused or destroyed;
* every diagnostic written into the reset artifact is truncated and redacted.
"""

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
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_DIAGNOSTIC_LIMIT = 4096
_SECRET_NAME_MARKERS = ("password", "token", "secret", "cookie", "authorization")
_SECRET_HEADER = re.compile(
    r"(?i)(\b(?:authorization|cookie|set-cookie)\b\s*:\s*)[^\r\n]*"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|token|secret)\b\s*[:=]\s*)[^\s,;]+"
)
_URI_USERINFO = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
_LOCAL_TOOL_PATHS = ("/usr/local/bin", "/opt/homebrew/bin")
_ENV_TEMPLATE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: Host ports owned by the already pinned subjects of the study.  A new subject
#: that grabbed one of these would silently break a Conduit / RWA / Mattermost
#: run, so the generic adapter refuses them by construction.
RESERVED_HOST_PORTS = (3001, 5433, 14000, 14001, 18065, 18066)

_DEFAULT_READINESS_TIMEOUT_SECONDS = 180
_DEFAULT_READINESS_POLL_MS = 250
_DEFAULT_PHASE_TIMEOUT_SECONDS = 300
_DEFAULT_RESET_TIMEOUT_SECONDS = 180
_DEFAULT_SCRIPT_TIMEOUT_SECONDS = 120

ADAPTER_ENV = "UISEMTEST_DOCKER_SINGLE_ADAPTER"
RESET_SCHEMA_VERSION = "uisemtest-docker-single-local-reset-v1"
SPEC_SCHEMA_VERSION = "uisemtest-docker-single-runtime-v1"


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


# ---------------------------------------------------------------------------
# specification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Script:
    """A reset or seed script, either on the host or inside the container."""

    location: str
    command: tuple[str, ...]
    workdir: str | None
    timeout_seconds: int

    @staticmethod
    def parse(value: dict[str, Any]) -> "Script":
        location = str(value["location"])
        if location not in {"host", "container"}:
            raise ValueError("docker_single script location must be host or container")
        command = tuple(_expand(str(part)) for part in value["command"])
        if not command or any(not part for part in command):
            raise ValueError("docker_single script command must be nonblank argv")
        workdir = value.get("workdir")
        if workdir is not None:
            workdir = _expand(str(workdir))
            if location != "container":
                raise ValueError("docker_single script workdir applies to container only")
        return Script(
            location=location,
            command=command,
            workdir=workdir,
            timeout_seconds=int(value.get("timeout_seconds", _DEFAULT_SCRIPT_TIMEOUT_SECONDS)),
        )


@dataclass(frozen=True)
class Volume:
    kind: str
    name: str | None
    source: str | None
    container_path: str
    read_only: bool
    reset_scope: str

    @property
    def fresh_on_reset(self) -> bool:
        return self.kind == "named" and self.reset_scope == "fresh_on_reset"


@dataclass(frozen=True)
class Probe:
    url: str
    expect_status: int


@dataclass(frozen=True)
class DockerSingleSpec:
    """The validated, environment-expanded ``docker_single`` block."""

    subject_id: str
    adapter_path: Path
    instance_key: str
    container_name: str
    image_reference: str
    pull_policy: str
    command: tuple[str, ...]
    ports: tuple[tuple[int, int], ...]
    environment: dict[str, str]
    volumes: tuple[Volume, ...]
    probes: tuple[Probe, ...]
    readiness_timeout_seconds: int
    readiness_poll_ms: int
    reset_strategy: str
    reset_timeout_seconds: int
    reset_script: Script | None
    seed: Script | None

    def volume_name(self, volume: Volume) -> str:
        return f"{self.container_name}-{volume.name}"

    @property
    def fresh_volumes(self) -> tuple[Volume, ...]:
        return tuple(item for item in self.volumes if item.fresh_on_reset)


def _expand(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if not resolved:
            raise ValueError(f"docker_single environment variable is unset: {name}")
        return resolved

    return _ENV_TEMPLATE.sub(replace, value)


def _require_loopback_http(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("docker_single readiness probes are loopback HTTP only")


def adapter_path(explicit: Path | None = None) -> Path:
    """Resolve the adapter JSON from ``--adapter`` or the documented env var."""

    if explicit is not None:
        return Path(explicit).resolve(strict=True)
    raw = os.environ.get(ADAPTER_ENV)
    if not raw:
        raise ValueError(
            f"docker_single adapter path requires --adapter or {ADAPTER_ENV}"
        )
    return Path(_expand(raw)).resolve(strict=True)


def load_spec(path: Path | None = None, *, validate: bool = True) -> DockerSingleSpec:
    """Read, schema-validate and environment-expand one adapter's docker_single."""

    source = adapter_path(path)
    adapter = json.loads(source.read_text(encoding="utf-8"))
    if validate:
        from common.contracts import validate_artifact

        validate_artifact("current_subject_adapter_v1.schema.json", adapter)
    raw = adapter.get("docker_single")
    if not isinstance(raw, dict):
        raise ValueError(f"adapter declares no docker_single block: {source}")
    if raw.get("schema_version") != SPEC_SCHEMA_VERSION:
        raise ValueError("docker_single block carries an unknown schema_version")

    subject_id = str(adapter["subject_id"])
    prefix = str(raw.get("container_name_prefix") or f"uisemtest-{subject_id}")
    instance_env = raw.get("instance_key_env")
    if instance_env:
        instance_source = os.environ.get(str(instance_env))
        if not instance_source:
            raise ValueError(
                f"docker_single instance key environment variable is unset: {instance_env}"
            )
    else:
        instance_source = str(source)
    if os.path.isabs(instance_source):
        instance_source = str(Path(instance_source).resolve())
    instance_key = hashlib.sha256(instance_source.encode()).hexdigest()[:16]

    image = raw["image"]
    repository = _expand(str(image["repository"])).split("@")[0].split(":")[0]
    digest = str(image["digest"])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("docker_single image digest must be a full sha256 digest")
    pull_policy = str(image.get("pull_policy", "if_absent"))

    ports: list[tuple[int, int]] = []
    for item in raw["ports"]:
        host_port = int(item["host"])
        if host_port in RESERVED_HOST_PORTS:
            raise ValueError(
                f"docker_single host port {host_port} is reserved by a pinned subject"
            )
        ports.append((host_port, int(item["container"])))
    if len({host for host, _ in ports}) != len(ports):
        raise ValueError("docker_single host ports must be unique")

    volumes: list[Volume] = []
    for item in raw.get("volumes", ()):
        kind = str(item["kind"])
        name = item.get("name")
        origin = item.get("source")
        if kind == "named" and not name:
            raise ValueError("docker_single named volume requires a name")
        if kind == "bind":
            if not origin:
                raise ValueError("docker_single bind volume requires a source")
            origin = _expand(str(origin))
            if not Path(origin).is_absolute():
                raise ValueError("docker_single bind volume source must be absolute")
        volumes.append(
            Volume(
                kind=kind,
                name=None if name is None else str(name),
                source=origin,
                container_path=str(item["container_path"]),
                read_only=bool(item.get("read_only", False)),
                reset_scope=str(item.get("reset_scope", "persistent")),
            )
        )

    readiness = raw["readiness"]
    probes: list[Probe] = []
    for item in readiness["probes"]:
        url = _expand(str(item["url"]))
        _require_loopback_http(url)
        probes.append(Probe(url=url, expect_status=int(item["expect_status"])))

    reset = raw["reset"]
    strategy = str(reset["strategy"])
    reset_script = Script.parse(reset["script"]) if reset.get("script") else None
    if strategy == "run_script" and reset_script is None:
        raise ValueError("docker_single run_script reset requires a script")
    if strategy == "recreate_with_fresh_volume" and not any(
        volume.fresh_on_reset for volume in volumes
    ):
        raise ValueError(
            "docker_single recreate_with_fresh_volume requires one fresh_on_reset volume"
        )

    return DockerSingleSpec(
        subject_id=subject_id,
        adapter_path=source,
        instance_key=instance_key,
        container_name=f"{prefix}-{instance_key}",
        image_reference=f"{repository}@{digest}",
        pull_policy=pull_policy,
        command=tuple(_expand(str(part)) for part in raw.get("command", ())),
        ports=tuple(ports),
        environment={
            str(key): _expand(str(value))
            for key, value in (raw.get("environment") or {}).items()
        },
        volumes=tuple(volumes),
        probes=tuple(probes),
        readiness_timeout_seconds=int(
            readiness.get("timeout_seconds", _DEFAULT_READINESS_TIMEOUT_SECONDS)
        ),
        readiness_poll_ms=int(readiness.get("poll_interval_ms", _DEFAULT_READINESS_POLL_MS)),
        reset_strategy=strategy,
        reset_timeout_seconds=int(
            reset.get("timeout_seconds", _DEFAULT_RESET_TIMEOUT_SECONDS)
        ),
        reset_script=reset_script,
        seed=Script.parse(raw["seed"]) if raw.get("seed") else None,
    )


# ---------------------------------------------------------------------------
# process plumbing
# ---------------------------------------------------------------------------


def _lifecycle_env() -> dict[str, str]:
    """``docker`` lives outside the sanitized reset PATH on macOS/Homebrew."""

    env = dict(os.environ)
    path_entries = [item for item in env.get("PATH", "").split(os.pathsep) if item]
    for entry in _LOCAL_TOOL_PATHS:
        if entry not in path_entries:
            path_entries.append(entry)
    env["PATH"] = os.pathsep.join(path_entries)
    return env


def _run_phase(
    phase: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            command,
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
    if check and completed.returncode != 0:
        raise LifecyclePhaseError(
            phase,
            "command_failed",
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def _docker(
    *args: str,
    phase: str,
    timeout: float = _DEFAULT_PHASE_TIMEOUT_SECONDS,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return _run_phase(
        phase,
        ["docker", *args],
        env=_lifecycle_env(),
        timeout=timeout,
        check=check,
    )


def _wait_http(url: str, expect_status: int, *, timeout: float, poll_ms: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == expect_status:
                    return
        except urllib.error.HTTPError as error:  # a 4xx/5xx may be the expected state
            if error.code == expect_status:
                return
        except OSError:
            pass
        time.sleep(poll_ms / 1000)
    raise LifecyclePhaseError("readiness", "readiness_timeout")


def _write_json(path: Path, value: dict[str, object]) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


# ---------------------------------------------------------------------------
# lifecycle phases
# ---------------------------------------------------------------------------


def run_argv(spec: DockerSingleSpec) -> list[str]:
    """The exact ``docker run`` argv; kept pure so tests can assert on it."""

    argv = ["run", "-d", "--name", spec.container_name, "--pull", "never"]
    for host_port, container_port in spec.ports:
        argv += ["-p", f"127.0.0.1:{host_port}:{container_port}"]
    for key in sorted(spec.environment):
        argv += ["-e", f"{key}={spec.environment[key]}"]
    for volume in spec.volumes:
        source = spec.volume_name(volume) if volume.kind == "named" else str(volume.source)
        mount = f"{source}:{volume.container_path}"
        if volume.read_only:
            mount += ":ro"
        argv += ["-v", mount]
    argv.append(spec.image_reference)
    argv.extend(spec.command)
    return argv


def _ensure_image(spec: DockerSingleSpec) -> None:
    if spec.pull_policy == "never":
        _docker("image", "inspect", spec.image_reference, phase="image_check", timeout=60)
        return
    if spec.pull_policy == "if_absent":
        present = _docker(
            "image",
            "inspect",
            spec.image_reference,
            phase="image_check",
            timeout=60,
            check=False,
        )
        if present.returncode == 0:
            return
    _docker("pull", spec.image_reference, phase="image_pull", timeout=900)


def _container_state(spec: DockerSingleSpec) -> str:
    """``""`` when no container of this name exists, else its docker state."""

    completed = _docker(
        "ps",
        "-a",
        "--filter",
        f"name=^/{spec.container_name}$",
        "--format",
        "{{.State}}",
        phase="freshness_check",
        timeout=60,
    )
    return completed.stdout.decode("utf-8", errors="replace").strip()


def _create_named_volumes(spec: DockerSingleSpec) -> None:
    for volume in spec.volumes:
        if volume.kind != "named":
            continue
        _docker("volume", "create", spec.volume_name(volume), phase="volume_create", timeout=60)


def _remove_volumes(spec: DockerSingleSpec, volumes: tuple[Volume, ...]) -> None:
    for volume in volumes:
        _docker(
            "volume",
            "rm",
            "-f",
            spec.volume_name(volume),
            phase="volume_remove",
            timeout=60,
            check=False,
        )


def _await_readiness(spec: DockerSingleSpec) -> None:
    for probe in spec.probes:
        _wait_http(
            probe.url,
            probe.expect_status,
            timeout=spec.readiness_timeout_seconds,
            poll_ms=spec.readiness_poll_ms,
        )


def _run_script(spec: DockerSingleSpec, script: Script, *, phase: str) -> None:
    if script.location == "host":
        _run_phase(
            phase,
            list(script.command),
            env=_lifecycle_env(),
            timeout=script.timeout_seconds,
        )
        return
    argv = ["exec"]
    if script.workdir:
        argv += ["-w", script.workdir]
    argv += [spec.container_name, *script.command]
    _docker(*argv, phase=phase, timeout=script.timeout_seconds)


def _start_container(spec: DockerSingleSpec) -> None:
    _ensure_image(spec)
    _create_named_volumes(spec)
    _docker(*run_argv(spec), phase="container_start", timeout=_DEFAULT_PHASE_TIMEOUT_SECONDS)
    _await_readiness(spec)
    if spec.seed is not None:
        _run_script(spec, spec.seed, phase="seed")


def _teardown(spec: DockerSingleSpec) -> None:
    _docker(
        "rm",
        "-f",
        "-v",
        spec.container_name,
        phase="container_stop",
        timeout=120,
        check=False,
    )
    _remove_volumes(spec, spec.fresh_volumes)


def supervise(spec: DockerSingleSpec) -> int:
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if _container_state(spec):
        raise LifecyclePhaseError("freshness_check", "container_not_fresh")
    try:
        _start_container(spec)
        while not stopping:
            time.sleep(0.1)
    finally:
        _teardown(spec)
    return 0


def _reset_phases(spec: DockerSingleSpec) -> None:
    if spec.reset_strategy == "restart_container":
        _docker(
            "restart",
            "-t",
            "5",
            spec.container_name,
            phase="reset_restart_container",
            timeout=spec.reset_timeout_seconds,
        )
    elif spec.reset_strategy == "recreate_with_fresh_volume":
        _docker(
            "rm",
            "-f",
            "-v",
            spec.container_name,
            phase="reset_remove_container",
            timeout=spec.reset_timeout_seconds,
            check=False,
        )
        _remove_volumes(spec, spec.fresh_volumes)
        _ensure_image(spec)
        _create_named_volumes(spec)
        _docker(
            *run_argv(spec),
            phase="reset_recreate_container",
            timeout=spec.reset_timeout_seconds,
        )
    elif spec.reset_strategy == "run_script":
        assert spec.reset_script is not None
        _run_script(spec, spec.reset_script, phase="reset_run_script")
    else:  # pragma: no cover - load_spec rejects unknown strategies first
        raise LifecyclePhaseError("reset", "unknown_reset_strategy")
    _await_readiness(spec)
    if spec.seed is not None:
        _run_script(spec, spec.seed, phase="reset_seed")


def reset(spec: DockerSingleSpec, output: Path) -> int:
    started_at = _utc_now()
    try:
        _reset_phases(spec)
        finished_at = _utc_now()
        epoch_material = f"{spec.container_name}:{finished_at}".encode()
        value: dict[str, object] = {
            "schema_version": RESET_SCHEMA_VERSION,
            "system": spec.subject_id,
            "adapter": f"docker_single_{spec.reset_strategy}",
            "status": 200,
            "started_at": started_at,
            "finished_at": finished_at,
            "reset_epoch_ref": (
                f"{spec.subject_id}-docker-single:"
                + hashlib.sha256(epoch_material).hexdigest()[:24]
            ),
        }
    except BaseException as error:
        value = {
            "schema_version": RESET_SCHEMA_VERSION,
            "system": spec.subject_id,
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
    parser = argparse.ArgumentParser(prog="docker_single_local")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for name in ("supervise", "reset", "readiness"):
        sub = subparsers.add_parser(name)
        sub.add_argument(
            "--adapter",
            type=Path,
            default=None,
            help=f"adapter JSON with a docker_single block (default: ${ADAPTER_ENV})",
        )
        if name == "reset":
            sub.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = load_spec(args.adapter)
    if args.mode == "supervise":
        return supervise(spec)
    if args.mode == "readiness":
        _await_readiness(spec)
        return 0
    return reset(spec, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
