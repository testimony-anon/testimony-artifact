"""Stage 0 — profile and launch (decision record 001).

Five steps: validate the profile → fresh temporary context + attach the recorder → real login flow → probe verification inside the recorded channel
→ emit run_config (written to disk after passing the schema, artifacts/<run_id>/run_config.json, D12).

Form: a library module called by Stage 1. Fully deterministic (hard rule 2), zero ground-truth contact (hard rule 1).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from common.contracts import REPO_ROOT, make_envelope, validate_artifact

from .errors import AuthError, BrowserError
from .profile import (
    AppProfile,
    AuthConfig,
    LoginFormSelectors,
    actor_auth,
    load_app_profile,
    resolve_actor_credentials,
)
from .recorder import NetworkRecorder, RecordedRequest
from .throttle import Throttle
from stage6_ground.valuepath import extract_value

RecordingAuthMode = str

LOGIN_RESPONSE_TIMEOUT_S = 15.0
PROBE_OBSERVE_TIMEOUT_S = 5.0
DEFAULT_GOTO_TIMEOUT_MS = 120_000
CHROME_EXECUTABLE_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)

# JS that issues the request inside the page context: the recorder (single source of truth) can observe it, and it is same-origin with the application under test.
_PROBE_JS = """
async ([path, token, scheme]) => {
  const headers = token ? { Authorization: `${scheme} ${token}` } : {};
  const res = await fetch(path, { headers });
  return { status: res.status, retry_after: res.headers.get("retry-after") };
}
"""

# Typed cookie-session requests run inside the newly created browser context, so
# Set-Cookie and the subsequent probe use the same cookie jar as the UI recorder.
_COOKIE_SESSION_REQUEST_JS = """
async ([path, method, headers, body]) => {
  const options = { method, headers, credentials: "include" };
  if (body !== null) options.body = JSON.stringify(body);
  const res = await fetch(path, options);
  // Consume the body so that CDP reports the request as finished: a response
  // served with Cache-Control: no-store (Ghost's whole Admin API) never reaches
  // Network.loadingFinished while its body stays unread, and the recorder's
  // identity probe then finds no finished entry. Reading it changes nothing else.
  try { await res.text(); } catch (e) {}
  return { status: res.status };
}
"""

# Same as _PROBE_JS but with the probe method taken from the profile: identity probes
# are not always GET (Umami verifies the session with POST /api/auth/verify).
_PROBE_WITH_METHOD_JS = """
async ([path, method, token, scheme]) => {
  const headers = token ? { Authorization: `${scheme} ${token}` } : {};
  const res = await fetch(path, { method, headers });
  try { await res.text(); } catch (e) {}  // see _COOKIE_SESSION_REQUEST_JS
  return { status: res.status, retry_after: res.headers.get("retry-after") };
}
"""

# Installs the observed token where the front end expects to find it. The value is a
# profile-supplied template so a front end that stores a JSON string keeps its quotes.
_TOKEN_ACTIVATION_JS = """
([storage, key, value]) => {
  const target = storage === "session_storage" ? window.sessionStorage : window.localStorage;
  target.setItem(key, value);
  return true;
}
"""


@dataclass
class Stage0Environment:
    """Environment produced by Stage 0: controlled browser + recorder + throttle + run_config already written to disk."""

    run_id: str
    run_dir: Path
    run_config: dict
    run_config_path: Path
    browser: object
    context: object
    page: object
    recorder: NetworkRecorder
    throttle: Throttle
    profile: AppProfile
    auth_token: str = ""  # token of the verified session; lives only in process memory (D12) and is loaded into the Stage 1 secret set (002 D18)
    authenticated_identity_key: bytes | None = None

    def close(self) -> None:
        first_error: BaseException | None = None
        # Close contexts first so active workers do not stall browser teardown.
        for phase, cleanup in (
            ("context.close", self.context.close),
            ("browser.close", self.browser.close),
            ("playwright.stop", _release_playwright_for_current_thread),
        ):
            _write_teardown_phase(self.run_id, phase, "started")
            try:
                cleanup()
            except BaseException as exc:
                _write_teardown_phase(self.run_id, phase, "failed")
                if first_error is None:
                    first_error = exc
            else:
                _write_teardown_phase(self.run_id, phase, "completed")
        if first_error is not None:
            raise first_error


def run_recording_reset(profile: AppProfile, recording_root: Path) -> dict[str, str]:
    """Execute the profile reset exactly once before an N-actor workflow starts."""

    if profile.reset is None:
        raise RuntimeError("typed recording workflow requires profile.reset")
    reset_path = recording_root / "reset" / "reset.json"
    reset_path.parent.mkdir(parents=True, exist_ok=True)
    if profile.reset.command:
        command = list(profile.reset.command)
    else:
        script = Path(profile.reset.script or "")
        if not script.is_absolute():
            script = REPO_ROOT / script
        command = [str(script)]
    if "--output" in command:
        index = command.index("--output")
        if index + 1 >= len(command):
            raise RuntimeError("profile reset --output has no value")
        command[index + 1] = str(reset_path)
    else:
        command.extend(["--output", str(reset_path)])
    subprocess.run(
        command,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=120,
    )
    artifact = json.loads(reset_path.read_text(encoding="utf-8"))
    if not 200 <= int(artifact.get("status", 0)) < 300:
        raise RuntimeError("recording reset artifact is incomplete")
    verify = profile.reset.verify_request
    request = Request(urljoin(profile.base_url, verify.path), method=verify.method)
    with urlopen(request, timeout=20) as response:
        status = response.status
        body = response.read() if verify.expect_json_path is not None else b""
    if status != verify.expect_status:
        raise RuntimeError("recording reset verification failed")
    if verify.expect_json_path is not None:
        try:
            document = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("recording reset verification response is not JSON") from exc
        actual = extract_value(document, verify.expect_json_path)
        if actual is None:
            raise RuntimeError("recording reset verification JSON path is missing")
        if "expect_json_equals" in verify.model_fields_set and (
            type(actual) is not type(verify.expect_json_equals)
            or actual != verify.expect_json_equals
        ):
            raise RuntimeError("recording reset verification JSON value mismatch")
    return {
        "status": "completed",
        "record_id": str(artifact.get("reset_epoch_ref") or "workflow-reset"),
        "artifact_ref": reset_path.relative_to(recording_root).as_posix(),
    }


_THREAD_PLAYWRIGHT = threading.local()
_TEARDOWN_JOURNAL_LOCK = threading.Lock()
TEARDOWN_JOURNAL_ENV = "CARVERFLOW_STAGE0_TEARDOWN_JOURNAL"


def _write_teardown_phase(run_id: str, phase: str, outcome: str) -> None:
    """Write optional diagnostic phase boundaries without changing cleanup semantics."""
    journal_path = os.environ.get(TEARDOWN_JOURNAL_ENV)
    if not journal_path:
        return
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        "thread": threading.current_thread().name,
        "run_id": run_id,
        "phase": phase,
        "outcome": outcome,
    }
    try:
        with _TEARDOWN_JOURNAL_LOCK:
            with open(journal_path, "a", encoding="utf-8") as journal:
                journal.write(json.dumps(record, sort_keys=True) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
    except OSError:
        # Diagnostics must never replace or mask the cleanup result.
        return


def _get_playwright():
    """Per-thread Playwright driver instance; the sync API's greenlet cannot be reused across threads."""
    playwright = getattr(_THREAD_PLAYWRIGHT, "playwright", None)
    if playwright is None:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        _THREAD_PLAYWRIGHT.playwright = playwright
    return playwright


def _release_playwright_for_current_thread() -> None:
    playwright = getattr(_THREAD_PLAYWRIGHT, "playwright", None)
    if playwright is None:
        return
    _THREAD_PLAYWRIGHT.playwright = None
    try:
        playwright.stop()
    except Exception:
        pass


def _close_stage0_startup_resources(*, context: object | None, browser: object | None) -> None:
    """Best-effort cleanup before a Stage0Environment exists.

    Startup failures must preserve their original exception, so cleanup errors
    are deliberately suppressed after every owned resource has been attempted.
    """
    for resource in (context, browser):
        if resource is None:
            continue
        try:
            resource.close()
        except BaseException:
            pass
    _release_playwright_for_current_thread()


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r{stamp}-{secrets.token_hex(2)}"


def _launch_chromium(playwright, *, headless: bool):
    launch_options = _browser_launch_options(headless=headless)
    try:
        return playwright.chromium.launch(**launch_options)
    except Exception as default_exc:
        candidates = [os.environ.get("CARVERFLOW_CHROME_EXECUTABLE"), *CHROME_EXECUTABLE_CANDIDATES]
        for candidate in candidates:
            if not candidate or not Path(candidate).is_file():
                continue
            try:
                return playwright.chromium.launch(**launch_options, executable_path=candidate)
            except Exception:
                continue
        raise default_exc


def _browser_launch_options(*, headless: bool) -> dict:
    options: dict = {"headless": headless}
    if headless:
        return options
    size = os.environ.get("CARVERFLOW_RECORDING_WINDOW_SIZE") or os.environ.get("CARVERFLOW_DEMO_WINDOW_SIZE") or ""
    parsed = _parse_window_size(size)
    if parsed:
        width, height = parsed
        options["args"] = ["--window-position=72,72", f"--window-size={width},{height}"]
    return options


def _parse_window_size(raw: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d{3,5})x(\d{3,5})\s*", str(raw or ""))
    if not match:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    if width < 800 or height < 600:
        return None
    return width, height


def _pump_until(page, predicate, timeout_s: float):
    """Poll the recorder until the predicate matches; page.wait_for_timeout keeps the event loop turning."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = predicate()
        if result is not None:
            return result
        page.wait_for_timeout(100)
    return None


def _goto_timeout_ms() -> int:
    raw = os.environ.get("CARVERFLOW_STAGE0_GOTO_TIMEOUT_MS")
    if not raw:
        return DEFAULT_GOTO_TIMEOUT_MS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_GOTO_TIMEOUT_MS
    return max(1_000, value)


def _materialize_auth_template(value, *, email: str, password: str):
    """Materialize the two profile credential placeholders in memory only."""
    if isinstance(value, dict):
        return {
            key: _materialize_auth_template(item, email=email, password=password)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _materialize_auth_template(item, email=email, password=password)
            for item in value
        ]
    if isinstance(value, str):
        return value.replace("${email}", email).replace("${password}", password)
    return value


def _request_observed(recorder, *, method: str, path: str, status: int):
    return recorder.find(
        lambda entry: entry.method == method
        and urlsplit(entry.url).path == path
        and entry.status == status
    )


def _recorded_probe_identity(
    *,
    page,
    recorder: NetworkRecorder,
    entry: RecordedRequest,
    json_path: str | None,
    expect_exact: bool = False,
    expected: object = None,
) -> bytes | None:
    if json_path is None:
        return None
    finished = _pump_until(
        page,
        lambda: True if getattr(entry, "finished", False) else None,
        PROBE_OBSERVE_TIMEOUT_S,
    )
    if finished is None:
        raise AuthError("authentication verification failed: identity probe response was not fully captured")
    body_text = recorder.fetch_body(entry)
    try:
        document = json.loads(body_text or "")
    except json.JSONDecodeError as exc:
        raise AuthError("authentication verification failed: identity probe response is not JSON") from exc
    identity = extract_value(document, json_path)
    if identity is None or identity == "" or identity == {} or identity == []:
        raise AuthError("authentication verification failed: identity probe path has no non-empty identity")
    if expect_exact and (
        type(identity) is not type(expected) or identity != expected
    ):
        raise AuthError("authentication verification failed: identity probe value does not match the fixed identity in the profile")
    try:
        canonical = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AuthError("authentication verification failed: identity probe value is not canonicalizable JSON") from exc
    return (type(identity).__name__ + ":" + canonical).encode("utf-8")


def _cookie_session_login_headers(
    login,
    *,
    context,
    base_url: str,
) -> dict[str, str]:
    """Static profile headers, plus the dynamic CSRF header when the profile declares one.

    A profile without ``cookie_session.csrf`` gets exactly ``dict(login.headers)``, i.e.
    the request this function replaced sent before the field existed.
    """
    headers = dict(login.headers)
    csrf = getattr(login, "csrf", None)
    if csrf is None:
        return headers
    value = next(
        (
            cookie.get("value")
            for cookie in context.cookies(base_url)
            if cookie.get("name") == csrf.cookie_name
        ),
        None,
    )
    if not value:
        raise AuthError(
            "authentication verification failed: the declared CSRF cookie "
            f"{csrf.cookie_name} was not set before the login request"
        )
    headers[csrf.header_name] = value
    return headers


def _authenticate_cookie_session(
    *,
    profile: AppProfile,
    auth: AuthConfig,
    actor_id: str,
    email: str,
    password: str,
    page,
    context,
    recorder: NetworkRecorder,
    throttle: Throttle,
    goto_timeout: int,
) -> tuple[dict, bytes | None]:
    login = auth.cookie_session
    probe = auth.probe_endpoint
    if login is None or probe is None:
        raise AuthError("cookie_session recording requires a typed login and a probe_endpoint")

    page.goto(profile.base_url, timeout=goto_timeout)
    body = _materialize_auth_template(
        login.body_template,
        email=email,
        password=password,
    )
    # The goto above is also the CSRF prewarm: a framework that guards its login
    # endpoint sets the token cookie while rendering the entry/login page.
    login_headers = _cookie_session_login_headers(
        login,
        context=context,
        base_url=profile.base_url,
    )
    login_result = throttle.run(
        lambda: page.evaluate(
            _COOKIE_SESSION_REQUEST_JS,
            [login.path, login.method, login_headers, body],
        )
    )
    login_status = login_result.get("status")
    if not isinstance(login_status, int) or not 200 <= login_status < 300:
        raise AuthError(f"authentication verification failed: login response status {login_status}")
    login_entry = _pump_until(
        page,
        lambda: _request_observed(
            recorder,
            method=login.method,
            path=login.path,
            status=login_status,
        ),
        LOGIN_RESPONSE_TIMEOUT_S,
    )
    if login_entry is None:
        raise AuthError("authentication verification failed: cookie_session login request was not observed by the recorder")

    cookies = context.cookies(profile.base_url)
    if login.cookie_name and not any(
        cookie.get("name") == login.cookie_name for cookie in cookies
    ):
        raise AuthError(
            f"authentication verification failed: login response did not set the declared cookie {login.cookie_name}"
        )

    probe_result = throttle.run(
        lambda: page.evaluate(
            _COOKIE_SESSION_REQUEST_JS,
            [probe.path, probe.method, {}, None],
        )
    )
    probe_status = probe_result.get("status")
    if probe_status != probe.expect_status:
        raise AuthError(
            f"authentication verification failed: probe {probe.method} {probe.path} returned {probe_status}"
        )
    probe_entry = _pump_until(
        page,
        lambda: _request_observed(
            recorder,
            method=probe.method,
            path=probe.path,
            status=probe_status,
        ),
        PROBE_OBSERVE_TIMEOUT_S,
    )
    if probe_entry is None:
        raise AuthError("authentication verification failed: cookie_session probe was not observed by the recorder")
    identity_key = _recorded_probe_identity(
        page=page,
        recorder=recorder,
        entry=probe_entry,
        json_path=probe.expect_json_path,
        expect_exact="expect_json_equals" in probe.model_fields_set,
        expected=probe.expect_json_equals,
    )

    activation = login.browser_activation
    if activation is not None:
        page.goto(activation.entry_url, timeout=activation.timeout_ms)
        controls = [
            page.locator(activation.username_selector),
            page.locator(activation.password_selector),
            page.locator(activation.submit_selector),
        ]
        if any(control.count() != 1 for control in controls):
            raise AuthError("browser authentication activation failed: login controls are not a unique match")
        controls[0].fill(email)
        controls[1].fill(password)
        controls[2].click()
        ready = page.locator(activation.ready_selector)
        ready.wait_for(state="visible", timeout=activation.timeout_ms)
        if ready.count() != 1:
            raise AuthError("browser authentication activation failed: ready control is not a unique match")
    else:
        # Re-enter the application after authentication so recording starts
        # from the authenticated UI, not the pre-login shell.
        page.goto(profile.base_url, timeout=goto_timeout)
    auth_context = {
        "verified": True,
        "method": auth.method,
        "auth_mode": "auto_login",
        "actor_id": actor_id,
        "probe_status": probe_status,
        "verified_at": probe_entry.started_at,
    }
    if identity_key is not None:
        auth_context["probe_identity_observed"] = True
    return auth_context, identity_key


def _materialize_token_template(template: str, *, token: str) -> str:
    """Materialize the ${token} placeholder in memory only."""
    return template.replace("${token}", token)


def _observed_login_token(
    *,
    page,
    recorder: NetworkRecorder,
    entry: RecordedRequest,
    token_json_path: str,
) -> str:
    """Read the token out of the login response the recorder observed (D8: never forged)."""
    _pump_until(
        page,
        lambda: True if getattr(entry, "finished", False) else None,
        LOGIN_RESPONSE_TIMEOUT_S,
    )
    body_text = recorder.fetch_body(entry)
    token = None
    if body_text:
        try:
            token = extract_value(json.loads(body_text), token_json_path)
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
            token = None
    if not isinstance(token, str) or not token:
        raise AuthError("authentication verification failed: no token observed in the login response")
    return token


def _authenticate_api_token(
    *,
    profile: AppProfile,
    auth: AuthConfig,
    actor_id: str,
    email: str,
    password: str,
    page,
    context,
    recorder: NetworkRecorder,
    throttle: Throttle,
    goto_timeout: int,
) -> tuple[dict, bytes | None, str]:
    """Record a session whose material is an API token, without forging the token.

    Two profile-selected activations: ``browser_form`` drives the real login page with
    profile-supplied selectors (defaults reproduce the legacy Conduit shape) and reads
    the token from the login response the recorder observed; ``api_then_inject`` issues
    the login request inside the page context and installs the observed token where the
    front end keeps it, then re-enters the application.
    """
    login = auth.api_token
    probe = auth.probe_endpoint
    if login is None or probe is None:
        raise AuthError("api_token recording requires a typed api_token login and a probe_endpoint")
    activation_mode = login.recording_activation or "browser_form"

    if activation_mode == "browser_form":
        selectors = login.selectors or LoginFormSelectors()
        page.goto(profile.base_url + (auth.login_entry or ""), timeout=goto_timeout)
        controls = [
            page.locator(selectors.username),
            page.locator(selectors.password),
            page.locator(selectors.submit),
        ]
        # A client-rendered login page (Umami) mounts its form only after hydration:
        # counting straight after goto observes 0 matches. Wait for each control to
        # attach first, so the uniqueness check below judges the settled page.
        for control in controls:
            try:
                control.first.wait_for(state="attached", timeout=selectors.timeout_ms)
            except Exception as exc:
                raise AuthError(
                    "browser authentication activation failed: a login control did not "
                    f"attach within {selectors.timeout_ms} ms"
                ) from exc
        if any(control.count() != 1 for control in controls):
            raise AuthError("browser authentication activation failed: login controls are not a unique match")
        controls[0].fill(email)
        controls[1].fill(password)
        submit_wall_time = time.time()
        controls[2].click()
        login_entry = _pump_until(
            page,
            lambda: recorder.find(
                lambda item: item.method.upper() == login.method.upper()
                and urlsplit(item.url).path == login.path
                and item.wall_time >= submit_wall_time - 0.5
                and item.status is not None
            ),
            LOGIN_RESPONSE_TIMEOUT_S,
        )
        if login_entry is None:
            raise AuthError("authentication verification failed: no login request response observed after submitting the login")
        if not (200 <= login_entry.status < 300):
            raise AuthError(f"authentication verification failed: login response status {login_entry.status}")
        token = _observed_login_token(
            page=page,
            recorder=recorder,
            entry=login_entry,
            token_json_path=login.token_json_path,
        )
        if selectors.ready is not None:
            ready = page.locator(selectors.ready)
            ready.wait_for(state="visible", timeout=goto_timeout)
            if ready.count() != 1:
                raise AuthError("browser authentication activation failed: ready control is not a unique match")
    else:
        activation = login.browser_activation
        if activation is None:
            raise AuthError("api_then_inject recording requires api_token.browser_activation")
        page.goto(profile.base_url, timeout=goto_timeout)
        body = _materialize_auth_template(
            login.body_template,
            email=email,
            password=password,
        )
        login_result = throttle.run(
            lambda: page.evaluate(
                _COOKIE_SESSION_REQUEST_JS,
                [login.path, login.method, dict(login.headers), body],
            )
        )
        login_status = login_result.get("status")
        if not isinstance(login_status, int) or not 200 <= login_status < 300:
            raise AuthError(f"authentication verification failed: login response status {login_status}")
        login_entry = _pump_until(
            page,
            lambda: _request_observed(
                recorder,
                method=login.method,
                path=login.path,
                status=login_status,
            ),
            LOGIN_RESPONSE_TIMEOUT_S,
        )
        if login_entry is None:
            raise AuthError("authentication verification failed: api_token login request was not observed by the recorder")
        token = _observed_login_token(
            page=page,
            recorder=recorder,
            entry=login_entry,
            token_json_path=login.token_json_path,
        )
        value = _materialize_token_template(activation.value_template, token=token)
        if activation.storage == "cookie":
            cookie: dict = {"name": activation.key, "value": value}
            if activation.cookie_path:
                cookie["domain"] = urlsplit(profile.base_url).hostname or ""
                cookie["path"] = activation.cookie_path
            else:
                cookie["url"] = profile.base_url
            context.add_cookies([cookie])
        else:
            page.evaluate(_TOKEN_ACTIVATION_JS, [activation.storage, activation.key, value])
        page.goto(
            profile.base_url + (activation.entry_url or ""),
            timeout=activation.timeout_ms,
        )

    # Probe verification inside the recorded channel; the probe method comes from the
    # profile because an identity probe is not always GET.
    def do_probe() -> dict:
        return page.evaluate(
            _PROBE_WITH_METHOD_JS,
            [probe.path, probe.method, token, auth.token_scheme],
        )

    probe_response = throttle.run(do_probe)
    probe_status = probe_response.get("status")
    if probe_status != probe.expect_status:
        raise AuthError(
            f"authentication verification failed: probe {probe.method} {probe.path} returned {probe_status}"
        )
    probe_entry = _pump_until(
        page,
        lambda: _request_observed(
            recorder,
            method=probe.method,
            path=probe.path,
            status=probe_status,
        ),
        PROBE_OBSERVE_TIMEOUT_S,
    )
    if probe_entry is None:
        raise AuthError("authentication verification failed: probe request was not observed by the recorder")
    identity_key = _recorded_probe_identity(
        page=page,
        recorder=recorder,
        entry=probe_entry,
        json_path=probe.expect_json_path,
        expect_exact="expect_json_equals" in probe.model_fields_set,
        expected=probe.expect_json_equals,
    )
    auth_context = {
        "verified": True,
        "method": auth.method,
        "auth_mode": "auto_login",
        "actor_id": actor_id,
        "recording_activation": activation_mode,
        "probe_status": probe_status,
        "verified_at": probe_entry.started_at,
    }
    if identity_key is not None:
        auth_context["probe_identity_observed"] = True
    return auth_context, identity_key, token


def run_stage0(
    profile_path: str | Path,
    artifacts_root: str | Path | None = None,
    headless: bool = True,
    recorder: NetworkRecorder | None = None,
    auth_mode: RecordingAuthMode = "auto_login",
    actor_id: str = "default",
) -> Stage0Environment:
    """Run the five-step Stage 0 flow; fail fast on error (D11) and never emit a run_config from a broken state."""
    if auth_mode not in {"auto_login", "manual_user_login"}:
        raise ValueError(f"unsupported stage0 auth_mode: {auth_mode}")
    # Step 1: load and validate app_profile (invalid input raises ProfileError naming the specific field)
    profile = load_app_profile(profile_path)
    auth = actor_auth(profile, actor_id)
    email = password = ""
    if auth_mode == "auto_login" and auth.credentials_ref is not None:
        email, password = resolve_actor_credentials(
            profile, actor_id
        )  # plaintext lives only in process memory (D12)

    # Step 2: fresh temporary context (reuses no persisted state; decided for replayability), attach the recorder
    try:
        playwright = _get_playwright()
    except Exception as exc:
        raise BrowserError(f"Playwright failed to start: {exc}") from exc
    browser = None
    context = None
    try:
        browser = _launch_chromium(playwright, headless=headless)
        context_options: dict = {}
        size = _parse_window_size(os.environ.get("CARVERFLOW_RECORDING_WINDOW_SIZE") or os.environ.get("CARVERFLOW_DEMO_WINDOW_SIZE") or "")
        if size and not headless:
            context_options["viewport"] = {"width": size[0], "height": size[1]}
        context = browser.new_context(**context_options)
        page = context.new_page()
        if recorder is None:
            recorder = NetworkRecorder()
        recorder.attach(page)  # Stage 1 may inject an extended recorder (001 §1: Stage 0 is a library module called by Stage 1)
    except Exception as exc:
        _close_stage0_startup_resources(context=context, browser=browser)
        raise BrowserError(f"browser environment setup failed: {exc}") from exc

    throttle = Throttle(
        max_concurrency=profile.rate_limit.max_concurrency,
        min_interval_ms=profile.rate_limit.min_interval_ms,
        max_retries_429=(
            profile.rate_limit.retry_on_429.max_retries
            if profile.rate_limit.retry_on_429
            else 0
        ),
    )
    goto_timeout = _goto_timeout_ms()

    try:
        if auth_mode == "manual_user_login":
            entry = auth.login_entry if auth.login_entry else ""
            page.goto(profile.base_url + entry, timeout=goto_timeout)
            return _stage0_environment(
                profile=profile,
                artifacts_root=artifacts_root,
                browser=browser,
                context=context,
                page=page,
                recorder=recorder,
                throttle=throttle,
                token="",
                auth_context={
                    "verified": False,
                    "method": auth.method,
                    "auth_mode": "manual_user_login",
                    "actor_id": actor_id,
                    "login_entry": entry or None,
                    "reason": "user_login_not_auto_verified",
                    "started_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                },
            )

        if auth.method == "none":
            page.goto(profile.base_url, timeout=goto_timeout)
            token = ""
            auth_context = {
                "verified": True,
                "method": auth.method,
                "auth_mode": "auto_login",
                "actor_id": actor_id,
                "verified_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            }
            return _stage0_environment(
                profile=profile,
                artifacts_root=artifacts_root,
                browser=browser,
                context=context,
                page=page,
                recorder=recorder,
                throttle=throttle,
                token=token,
                auth_context=auth_context,
            )

        if auth.method == "cookie_session":
            auth_context, identity_key = _authenticate_cookie_session(
                profile=profile,
                auth=auth,
                actor_id=actor_id,
                email=email,
                password=password,
                page=page,
                context=context,
                recorder=recorder,
                throttle=throttle,
                goto_timeout=goto_timeout,
            )
            return _stage0_environment(
                profile=profile,
                artifacts_root=artifacts_root,
                browser=browser,
                context=context,
                page=page,
                recorder=recorder,
                throttle=throttle,
                token="",
                auth_context=auth_context,
                authenticated_identity_key=identity_key,
            )
        # New branch: token-material sessions. It also serves a form_login profile that
        # explicitly opts in via api_token.recording_activation; a form_login profile
        # that does not declare it (Conduit) still falls through to the legacy path below.
        if auth.method == "api_token" or (
            auth.api_token is not None
            and auth.api_token.recording_activation is not None
        ):
            auth_context, identity_key, token = _authenticate_api_token(
                profile=profile,
                auth=auth,
                actor_id=actor_id,
                email=email,
                password=password,
                page=page,
                context=context,
                recorder=recorder,
                throttle=throttle,
                goto_timeout=goto_timeout,
            )
            return _stage0_environment(
                profile=profile,
                artifacts_root=artifacts_root,
                browser=browser,
                context=context,
                page=page,
                recorder=recorder,
                throttle=throttle,
                token=token,
                auth_context=auth_context,
                authenticated_identity_key=identity_key,
            )
        if auth.method != "form_login":
            raise AuthError(f"Stage0 recording does not yet support auth.method={auth.method}")

        # Step 3: real login flow (the login traffic itself is recorded as well; D8)
        page.goto(profile.base_url + auth.login_entry, timeout=goto_timeout)
        page.fill('input[name="email"]', email)
        page.fill('input[name="password"]', password)
        submit_wall_time = time.time()
        page.click("form button")

        def login_response() -> RecordedRequest | None:
            return recorder.find(
                lambda e: e.method == "POST"
                and e.wall_time >= submit_wall_time - 0.5
                and e.status is not None
            )

        login_entry = _pump_until(page, login_response, LOGIN_RESPONSE_TIMEOUT_S)
        if login_entry is None:
            raise AuthError("authentication verification failed: no login request response observed after submitting the login")
        if not (200 <= login_entry.status < 300):
            raise AuthError(f"authentication verification failed: login response status {login_entry.status}")

        # take the JWT from the login response body observed by the recorder (no hand-forged token; D8)
        def login_finished() -> bool | None:
            return True if login_entry.finished else None

        _pump_until(page, login_finished, LOGIN_RESPONSE_TIMEOUT_S)
        body_text = recorder.fetch_body(login_entry)
        token = None
        if body_text:
            try:
                token = json.loads(body_text).get("user", {}).get("token")
            except (json.JSONDecodeError, AttributeError):
                token = None
        if not token:
            raise AuthError("authentication verification failed: no token observed in the login response")

        # Step 4: probe verification inside the recorded channel (issued from the browser context with the recorder attached)
        probe = auth.probe_endpoint

        def do_probe() -> dict:
            # the scheme is injected via the profile rather than hard-coded (002 D19)
            return page.evaluate(_PROBE_JS, [probe.path, token, auth.token_scheme])

        probe_response = throttle.run(do_probe)
        probe_status = probe_response.get("status")
        if not (probe_status and 200 <= probe_status < 300):
            raise AuthError(f"authentication verification failed: probe {probe.method} {probe.path} returned {probe_status}")

        # A3: the probe request must be confirmed by observation through the recorder (single source of truth)
        def probe_observed() -> RecordedRequest | None:
            return recorder.find(
                lambda e: e.url.endswith(probe.path) and e.status == probe_status
            )

        probe_entry = _pump_until(page, probe_observed, PROBE_OBSERVE_TIMEOUT_S)
        if probe_entry is None:
            raise AuthError("authentication verification failed: probe request was not observed by the recorder")
        identity_key = _recorded_probe_identity(
            page=page,
            recorder=recorder,
            entry=probe_entry,
            json_path=probe.expect_json_path,
            expect_exact="expect_json_equals" in probe.model_fields_set,
            expected=probe.expect_json_equals,
        )
        # the verified-at time is the probe request timestamp observed by the recorder (single source of truth), not the write time
        verified_at = probe_entry.started_at

        auth_context = {
            "verified": True,
            "method": auth.method,
            "auth_mode": "auto_login",
            "actor_id": actor_id,
            "probe_status": probe_status,
            "verified_at": verified_at,
        }
        if identity_key is not None:
            auth_context["probe_identity_observed"] = True
        return _stage0_environment(
            profile=profile,
            artifacts_root=artifacts_root,
            browser=browser,
            context=context,
            page=page,
            recorder=recorder,
            throttle=throttle,
            token=token,
            auth_context=auth_context,
            authenticated_identity_key=identity_key,
        )
    except Exception:
        # on failure, clean up the browser resources and re-raise as-is (D11: never emit from a broken state)
        _close_stage0_startup_resources(context=context, browser=browser)
        raise


def _stage0_environment(
    *,
    profile: AppProfile,
    artifacts_root: str | Path | None,
    browser: object,
    context: object,
    page: object,
    recorder: NetworkRecorder,
    throttle: Throttle,
    token: str,
    auth_context: dict,
    authenticated_identity_key: bytes | None = None,
) -> Stage0Environment:
    """Write run_config and return the live Stage0 browser environment."""
    run_id = _new_run_id()
    run_config = {
        "metadata": make_envelope(
            artifact_type="run_config", stage="stage0", run_id=run_id
        ),
        "app_profile": profile.model_dump(exclude_none=True),
        "auth_context": auth_context,
        "rate_limit": profile.rate_limit.model_dump(exclude_none=True),
        "drive_mode": profile.drive_mode,  # lifted from the profile as-is (001 D10)
    }
    validate_artifact("run_config.schema.json", run_config)

    root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_config_path = run_dir / "run_config.json"
    run_config_path.write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n"
    )

    return Stage0Environment(
        run_id=run_id,
        run_dir=run_dir,
        run_config=run_config,
        run_config_path=run_config_path,
        browser=browser,
        context=context,
        page=page,
        recorder=recorder,
        throttle=throttle,
        profile=profile,
        auth_token=token,
        authenticated_identity_key=authenticated_identity_key,
    )
