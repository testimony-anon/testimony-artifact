"""Minimal localhost Mattermost lifecycle for the current subject adapter."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Mapping
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import quote


_DIAGNOSTIC_LIMIT = 4096
_SECRET_NAME_MARKERS = ("password", "token", "secret", "cookie", "authorization")
_SECRET_HEADER = re.compile(
    r"(?i)(\b(?:authorization|cookie|set-cookie)\b\s*:\s*)[^\r\n]*"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|token|secret|mmauthtoken)\b\s*[:=]\s*)"
    r"[^\s,;]+"
)
_URI_USERINFO = re.compile(
    r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@"
)


class LifecyclePhaseError(RuntimeError):
    """One stable, sanitized Mattermost lifecycle failure."""

    def __init__(
        self,
        phase: str,
        reason_code: str,
        *,
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(f"{phase}:{reason_code}")
        self.record = {
            "phase": phase,
            "reason_code": reason_code,
            "exit_code": exit_code,
            "stdout": _redact_diagnostic(stdout),
            "stderr": _redact_diagnostic(stderr),
        }


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
            stdout=_redact_diagnostic(error.stdout),
            stderr=_redact_diagnostic(error.stderr),
        ).record
    if isinstance(error, subprocess.CalledProcessError):
        return LifecyclePhaseError(
            phase,
            "command_failed",
            exit_code=error.returncode,
            stdout=_redact_diagnostic(error.stdout),
            stderr=_redact_diagnostic(error.stderr),
        ).record
    return LifecyclePhaseError(
        phase,
        type(error).__name__,
    ).record


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
            stdout=_redact_diagnostic(error.stdout),
            stderr=_redact_diagnostic(error.stderr),
        ) from error
    if completed.returncode != 0:
        raise LifecyclePhaseError(
            phase,
            "command_failed",
            exit_code=completed.returncode,
            stdout=_redact_diagnostic(completed.stdout),
            stderr=_redact_diagnostic(completed.stderr),
        )
    return completed


def _runtime_root(output_root: Path) -> Path:
    digest = hashlib.sha256(str(output_root.resolve()).encode()).hexdigest()[:16]
    return Path("/tmp") / f"uisemtest-mm-{digest}"


def _compose(
    runtime_root: Path,
    *args: str,
    check: bool = True,
    phase: str = "compose",
) -> subprocess.CompletedProcess[bytes]:
    project = f"uisemtest-mm-{runtime_root.name.rsplit('-', 1)[-1]}"
    command = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        os.environ["UISEMTEST_MATTERMOST_COMPOSE_FILE"],
        *args,
    ]
    if check:
        return _run_phase(phase, command, timeout=120)
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as error:
        raise LifecyclePhaseError(
            phase,
            "phase_timeout",
            stdout=_redact_diagnostic(error.stdout),
            stderr=_redact_diagnostic(error.stderr),
        ) from error


def _wait_http(url: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.25)
    raise RuntimeError("Mattermost readiness deadline exceeded")


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def _server_environment(runtime_root: Path, epoch: int) -> dict[str, str]:
    data = runtime_root / f"epoch-{epoch}"
    for name in ("data", "logs", "plugins", "client-plugins"):
        (data / name).mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "MM_CONFIG": (
                "postgres://mmuser:mostest@localhost:5432/"
                "mattermost_test?sslmode=disable&connect_timeout=10"
            ),
            "MM_SQLSETTINGS_DRIVERNAME": "postgres",
            "MM_SQLSETTINGS_DATASOURCE": (
                "postgres://mmuser:mostest@localhost:5432/"
                "mattermost_test?sslmode=disable&connect_timeout=10"
            ),
            "MM_SERVICESETTINGS_LISTENADDRESS": ":18065",
            "MM_SERVICESETTINGS_SITEURL": "http://127.0.0.1:18065",
            "MM_SERVICESETTINGS_ENABLELOCALMODE": "true",
            "MM_SERVICESETTINGS_LOCALMODESOCKETLOCATION": str(
                runtime_root / "mmctl.sock"
            ),
            "MM_FILESETTINGS_DIRECTORY": str(data / "data"),
            "MM_LOGSETTINGS_FILELOCATION": str(data / "logs/mattermost.log"),
            "MM_PLUGINSETTINGS_DIRECTORY": str(data / "plugins"),
            "MM_PLUGINSETTINGS_CLIENTDIRECTORY": str(data / "client-plugins"),
        }
    )
    return env


def _json_request(
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    cookie: str | None = None,
) -> tuple[dict[str, object], Mapping[str, str]]:
    payload = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:18065" + path,
        data=payload,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    if cookie is not None:
        request.add_header("Cookie", cookie)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read()), response.headers


def _provision(runtime_root: Path) -> tuple[dict[str, object], ...]:
    mmctl = os.environ["UISEMTEST_MATTERMOST_MMCTL"]
    env = dict(os.environ)
    env["MMCTL_LOCAL_SOCKET_PATH"] = str(runtime_root / "mmctl.sock")
    actors = (
        (
            os.environ["MATTERMOST_R3_ACTOR_A_USERNAME"],
            os.environ["MATTERMOST_R3_ACTOR_A_PASSWORD"],
        ),
        (
            os.environ["MATTERMOST_R3_ACTOR_B_USERNAME"],
            os.environ["MATTERMOST_R3_ACTOR_B_PASSWORD"],
        ),
    )
    for username, password in actors:
        _run_phase(
            "provision_actor_user",
            [
                mmctl,
                "--local",
                "--quiet",
                "user",
                "create",
                "--username",
                username,
                "--email",
                f"{username}@example.invalid",
                "--password",
                password,
                "--email-verified",
                "--disable-welcome-email",
            ],
            env=env,
            timeout=30,
        )
    # A fresh database is created for every reset epoch, so one stable UI route
    # is both collision-free and reproducible across workflow attempts.
    team = "uisemtest-current"
    _run_phase(
        "provision_team",
        [mmctl, "--local", "--quiet", "team", "create", "--name", team,
         "--display-name", "UISemTest"],
        env=env,
        timeout=30,
    )
    _run_phase(
        "provision_team_members",
        [mmctl, "--local", "--quiet", "team", "users", "add", team,
         actors[0][0], actors[1][0]],
        env=env,
        timeout=30,
    )
    actor_cookies = []
    for username, password in actors:
        _login, headers = _json_request(
            "POST",
            "/api/v4/users/login",
            body={"login_id": username, "password": password},
        )
        cookies = SimpleCookie()
        cookies.load(str(headers.get("Set-Cookie") or ""))
        if "MMAUTHTOKEN" not in cookies:
            raise RuntimeError("Mattermost provisioning login did not return a session")
        actor_cookies.append(f"MMAUTHTOKEN={cookies['MMAUTHTOKEN'].value}")
    actor_a_cookie, actor_b_cookie = actor_cookies
    actor_a, _ = _json_request(
        "GET",
        f"/api/v4/users/username/{quote(actors[0][0], safe='')}",
        cookie=actor_a_cookie,
    )
    actor_b, _ = _json_request(
        "GET",
        f"/api/v4/users/username/{quote(actors[1][0], safe='')}",
        cookie=actor_a_cookie,
    )
    team_value, _ = _json_request(
        "GET", f"/api/v4/teams/name/{quote(team, safe='')}", cookie=actor_a_cookie
    )
    team_id = str(team_value["id"])
    town_square, _ = _json_request(
        "GET",
        f"/api/v4/teams/{quote(team_id, safe='')}/channels/name/town-square",
        cookie=actor_a_cookie,
    )
    off_topic, _ = _json_request(
        "GET",
        f"/api/v4/teams/{quote(team_id, safe='')}/channels/name/off-topic",
        cookie=actor_a_cookie,
    )
    baseline, _ = _json_request(
        "POST",
        "/api/v4/posts",
        body={
            "channel_id": str(town_square["id"]),
            "message": "R4 visible base message 20260717 A1",
        },
        cookie=actor_a_cookie,
    )
    seed_reaction, _ = _json_request(
        "POST",
        "/api/v4/reactions",
        body={
            "user_id": str(actor_b["id"]),
            "post_id": str(baseline["id"]),
            "emoji_name": "slightly_frowning_face",
        },
        cookie=actor_b_cookie,
    )
    final_baseline, _ = _json_request(
        "GET",
        f"/api/v4/posts/{quote(str(baseline['id']), safe='')}",
        cookie=actor_a_cookie,
    )
    aliases: list[dict[str, object]] = [
        {"logical_value": logical, "runtime_value": runtime, "normalize_response": True}
        for logical, runtime in (
            ("oo3ufirrribk8expc3cpkuykro", str(actor_a["id"])),
            ("6arez33zkpnp5xe58ziu4qsjoy", str(actor_b["id"])),
            ("n1yda8mmxtrhdj93uuhi3314iw", team_id),
            ("16qqmsdrd3ymbdr8xquqq88ugw", str(town_square["id"])),
            ("mxms5ret53fc3xx6p3c5exdicr", str(off_topic["id"])),
            ("e4nnurhzdtb6imfjgazrwpi5io", str(baseline["id"])),
            ("[REDACTED:037dafe9]", "R4 visible base message 20260717 A1"),
        )
    ]
    aliases.append(
        {
            "logical_value": "1784715785215",
            "runtime_value": str(baseline["create_at"]),
            "normalize_response": False,
        }
    )
    aliases.extend(
        {
            "logical_value": 1784715812978,
            "runtime_value": runtime,
            "normalize_response": True,
        }
        for runtime in dict.fromkeys(
            (seed_reaction["create_at"], seed_reaction["update_at"])
        )
    )
    aliases.append(
        {
            "logical_value": "1784715864488",
            "runtime_value": str(final_baseline["update_at"]),
            "normalize_response": False,
        }
    )
    aliases.extend(
        {
            "actor_id": actor_id,
            "logical_value": logical,
            "runtime_value": "slightly_frowning_face",
            "normalize_response": False,
        }
        for actor_id, logical in (
            ("actor_a", "[REDACTED:62d519e5]"),
            ("actor_b", "[REDACTED:2160f3a3]"),
        )
    )
    aliases.extend(
        {
            "actor_id": actor_id,
            "logical_value": logical,
            "runtime_value": runtime,
            "normalize_response": False,
        }
        for actor_id, logical, runtime in (
            ("actor_a", "[REDACTED:bb2b82e8]", False),
            ("actor_a", "[REDACTED:4c9b5284]", True),
            ("actor_b", "[REDACTED:fd5fc85c]", False),
            ("actor_b", "[REDACTED:4a8b797c]", True),
        )
    )
    return tuple(aliases)


def _start_epoch(
    runtime_root: Path, epoch: int
) -> tuple[subprocess.Popen[bytes], tuple[dict[str, object], ...]]:
    _compose(runtime_root, "up", "-d", "postgres", phase="postgres_start")
    deadline = time.monotonic() + 60
    ready: subprocess.CompletedProcess[bytes] | None = None
    while time.monotonic() < deadline:
        ready = _compose(
            runtime_root,
            "exec",
            "-T",
            "postgres",
            "pg_isready",
            "-U",
            "mmuser",
            "-d",
            "mattermost_test",
            check=False,
            phase="postgres_ready",
        )
        if ready.returncode == 0:
            break
        time.sleep(0.25)
    else:
        raise LifecyclePhaseError(
            "postgres_ready",
            "postgres_readiness_timeout",
            exit_code=None if ready is None else ready.returncode,
            stdout="" if ready is None else _redact_diagnostic(ready.stdout),
            stderr="" if ready is None else _redact_diagnostic(ready.stderr),
        )
    process = subprocess.Popen(
        [os.environ["UISEMTEST_MATTERMOST_SERVER"]],
        cwd=Path(os.environ["UISEMTEST_MATTERMOST_CHECKOUT"]) / "server",
        env=_server_environment(runtime_root, epoch),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        try:
            _wait_http("http://127.0.0.1:18065/api/v4/system/ping")
        except RuntimeError as error:
            log_path = runtime_root / f"epoch-{epoch}" / "logs/mattermost.log"
            log_tail = ""
            if log_path.exists():
                log_tail = _redact_diagnostic(log_path.read_text(
                    encoding="utf-8", errors="replace"
                ))
            raise LifecyclePhaseError(
                "mattermost_health",
                "mattermost_readiness_timeout",
                exit_code=process.poll(),
                stderr=log_tail,
            ) from error
        deadline = time.monotonic() + 30
        while not (runtime_root / "mmctl.sock").exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not (runtime_root / "mmctl.sock").exists():
            raise LifecyclePhaseError(
                "mattermost_local_socket",
                "local_socket_timeout",
                exit_code=process.poll(),
            )
        try:
            aliases = _provision(runtime_root)
        except LifecyclePhaseError:
            raise
        except BaseException as error:
            raise LifecyclePhaseError(
                "provision",
                type(error).__name__,
            ) from error
        return process, aliases
    except BaseException:
        _stop_process(process)
        raise


class _ReadyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200 if self.path == "/ready" else 404)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def supervise() -> int:
    output_root = Path(os.environ["UISEMTEST_MATTERMOST_OUTPUT_ROOT"])
    runtime_root = _runtime_root(output_root)
    checkout = Path(os.environ["UISEMTEST_MATTERMOST_CHECKOUT"])
    client = checkout / "server/client"
    if runtime_root.exists() or client.exists() or client.is_symlink():
        raise RuntimeError("Mattermost current runtime is not fresh")
    runtime_root.mkdir(mode=0o700)
    (runtime_root / "web-dist").symlink_to(
        Path(os.environ["UISEMTEST_MATTERMOST_WEB_DIST"])
    )
    client.symlink_to(runtime_root / "web-dist")
    control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    control.bind(str(runtime_root / "control.sock"))
    os.chmod(runtime_root / "control.sock", 0o600)
    control.listen(1)
    control.settimeout(0.2)
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    epoch = 1
    process: subprocess.Popen[bytes] | None = None
    ready: http.server.ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None
    try:
        process, _aliases = _start_epoch(runtime_root, epoch)
        ready = http.server.ThreadingHTTPServer(("127.0.0.1", 18066), _ReadyHandler)
        thread = threading.Thread(target=ready.serve_forever, daemon=True)
        thread.start()
        while not stopping:
            try:
                connection, _ = control.accept()
            except TimeoutError:
                continue
            with connection:
                request = json.loads(connection.recv(4096))
                if request != {"op": "reset"}:
                    connection.sendall(b'{"status":400}\n')
                    continue
                try:
                    _stop_process(process)
                    process = None
                    _compose(
                        runtime_root,
                        "down",
                        "-v",
                        "--remove-orphans",
                        phase="reset_teardown",
                    )
                    epoch += 1
                    process, aliases = _start_epoch(runtime_root, epoch)
                    response = {
                        "status": 200,
                        "reset_epoch_ref": f"mattermost-current:{epoch}",
                        "material_aliases": aliases,
                    }
                except BaseException as error:
                    response = {
                        "status": 500,
                        "reset_epoch_ref": f"mattermost-current:{epoch}",
                        "failure": _phase_failure(error, "reset_epoch"),
                    }
                    stopping = True
                connection.sendall(
                    json.dumps(response, sort_keys=True).encode() + b"\n"
                )
    finally:
        if ready is not None:
            ready.shutdown()
            ready.server_close()
        if thread is not None:
            thread.join(timeout=1)
        control.close()
        _stop_process(process)
        _compose(runtime_root, "down", "-v", "--remove-orphans", check=False)
        if client.is_symlink() and client.resolve() == (runtime_root / "web-dist").resolve():
            client.unlink()
        shutil.rmtree(runtime_root, ignore_errors=True)
    return 0


def reset(output: Path) -> int:
    runtime_root = _runtime_root(Path(os.environ["UISEMTEST_MATTERMOST_OUTPUT_ROOT"]))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(115)
            client.connect(str(runtime_root / "control.sock"))
            client.sendall(b'{"op":"reset"}')
            line = client.makefile("rb").readline()
        if not line:
            response = {
                "status": 500,
                "failure": _phase_failure(
                    EOFError("reset control socket closed"), "reset_control"
                ),
            }
        else:
            response = json.loads(line)
    except BaseException as error:
        response = {
            "status": 500,
            "failure": _phase_failure(error, "reset_control"),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(response, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    if 200 <= int(response.get("status", 0)) < 300:
        return 0
    print(
        json.dumps(response.get("failure") or {}, sort_keys=True),
        file=sys.stderr,
    )
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
