"""Probe execution + safety shell for write probes (004 D28/D29 + 004A).

- Probe requests go directly from the tool (urllib, not page scripts; D29); the auth header uses the real token of a fresh runtime login;
- create-use-cleanup: a write probe that creates a resource with 2xx → paired DELETE → GET after deletion must return 404 (D28a);
  cleanup failure → circuit breaker (stop further probes, D28b);
- probe_results is redacted by SecretRegistry before writing (D18): the real token stays in memory and never reaches disk;
- this module has no request-body synthesis path (ruling 3: reuse observed bodies or send none), guarded by the E9 static assertion.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any

from stage1_record.secrets import SecretRegistry
from stage6_ground.valuepath import extract_value

from .planner import ProbeTarget


class CleanupFailedError(Exception):
    """Cleanup failure → circuit breaker (D28b)."""


@dataclass
class HttpResult:
    status: int
    headers: dict
    body_text: str | None
    # `headers` is a flat dict, so a repeated header collapses to a single value
    # (`dict(Message)` keeps the first). Set-Cookie is the one header where that
    # loses information -- a login response may set the session cookie and a CSRF
    # cookie in separate headers -- so every value is preserved here as well.
    set_cookies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeAuth:
    """Runtime auth material. The real token/cookie is used in memory only and must be redacted before artifacts are written."""

    token: str | None = None
    token_scheme: str = "Token"
    session_cookie_name: str | None = None
    session_cookie_value: str | None = None
    session_cookie_header: str | None = None
    # CSRF double submit (only when profile.auth.cookie_session.csrf is declared): the
    # framework's CSRF cookie as set by the login response (Django rotates it on login)
    # or, failing that, by the prewarm request, echoed as a Cookie and in the declared header.
    csrf_cookie_header: str | None = None
    csrf_header_name: str | None = None
    csrf_header_value: str | None = None

    def secret_values(self) -> list[str]:
        values = []
        for value in (
            self.token,
            self.session_cookie_value,
            self.session_cookie_header,
            self.csrf_cookie_header,
            self.csrf_header_value,
        ):
            if value:
                values.append(str(value))
        return sorted(set(values), key=len, reverse=True)


def _http(method: str, url: str, token: str | None, scheme: str,
          body_text: str | None, body_mime: str | None,
          extra_headers: dict[str, str] | None = None,
          session_cookie_header: str | None = None) -> HttpResult:
    """Send one HTTP request; 4xx/5xx are caught via HTTPError and returned as normal results (a probe always gets a response)."""
    headers = dict(extra_headers or {})
    if token:
        headers["Authorization"] = f"{scheme} {token}"
    if session_cookie_header and not any(str(k).lower() == "cookie" for k in headers):
        headers["Cookie"] = session_cookie_header
    data = None
    if body_text is not None:
        data = body_text.encode("utf-8")
        headers.setdefault("Content-Type", body_mime or "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return HttpResult(
                resp.status,
                dict(resp.headers),
                raw or None,
                all_set_cookies(resp.headers),
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return HttpResult(
            exc.code,
            dict(exc.headers),
            raw or None,
            all_set_cookies(exc.headers),
        )


@dataclass
class Prober:
    base_url: str
    token: str | None
    token_scheme: str
    secrets: SecretRegistry
    session_cookie_header: str | None = None
    session_cookie_name: str | None = None
    min_interval_ms: int = 100
    trust_basis: str = "per_probe_cleanup"  # D60: per_probe_cleanup | environment_reset
    _fused: bool = False
    _last_at: float = 0.0
    cleanup_log: list[str] = field(default_factory=list)

    def _throttle(self) -> None:
        delta = self.min_interval_ms / 1000.0 - (time.monotonic() - self._last_at)
        if delta > 0:
            time.sleep(delta)
        self._last_at = time.monotonic()

    def _extract_handle(self, body_text: str | None) -> str | None:
        """Extract the created resource handle from a 2xx response body (slug/id of a single-key top-level object)."""
        if not body_text:
            return None
        try:
            doc = json.loads(body_text)
        except json.JSONDecodeError:
            return None
        if isinstance(doc, dict) and len(doc) == 1:
            inner = next(iter(doc.values()))
            if isinstance(inner, dict):
                for key in ("slug", "id"):
                    if key in inner:
                        return str(inner[key])
        return None

    def _cleanup(self, probe_url: str, handle: str) -> tuple[bool, str]:
        """Paired cleanup: DELETE the resource → GET after deletion must return 404 (D28a). Returns (success, detail).

        Success requires **both**: the DELETE itself returns 2xx and the GET after deletion returns 404 (tightened by 004A finding 2:
        GET==404 alone is a false positive when the DELETE failed but the resource is unreachable for unrelated reasons; the DELETE status must count).
        """
        delete_url = probe_url.rstrip("/") + "/" + handle
        self._throttle()
        delete_res = _http(
            "DELETE", delete_url, self.token, self.token_scheme, None, None,
            session_cookie_header=self.session_cookie_header,
        )
        self._throttle()
        verify_res = _http(
            "GET", delete_url, self.token, self.token_scheme, None, None,
            session_cookie_header=self.session_cookie_header,
        )
        delete_ok = 200 <= delete_res.status < 300
        if delete_ok and verify_res.status == 404:
            return True, f"cleaned: DELETE {delete_res.status}, verify GET 404"
        return (False,
                f"cleanup_failed: DELETE {delete_res.status}, verify GET {verify_res.status} "
                f"(expected DELETE 2xx and GET 404)")

    @property
    def fused(self) -> bool:
        return self._fused

    def execute(self, target: ProbeTarget, probe_id: str) -> dict:
        """Execute one probe and return the probe record (not redacted; redaction happens at the assemble exit).
        On cleanup failure, record the probe and set the fuse flag (no raise); the orchestration layer stops further probes (D28b)."""
        if self._fused:
            raise CleanupFailedError("safety shell circuit breaker tripped; refusing further probes")
        self._throttle()

        body_text = target.reused_body
        body_mime = "application/json" if body_text else None
        result = _http(
            target.method,
            target.concrete_url,
            self.token,
            self.token_scheme,
            body_text,
            body_mime,
            session_cookie_header=self.session_cookie_header,
        )
        success = 200 <= result.status < 400

        cleanup = {"required": False, "performed": False}
        if success and target.method in ("POST", "PUT", "PATCH", "DELETE"):
            handle = self._extract_handle(result.body_text) if target.method == "POST" else None
            if handle is not None:
                cleanup["required"] = True
                ok, detail = self._cleanup(target.concrete_url, handle)
                cleanup["performed"] = ok
                cleanup["detail"] = detail
                self.cleanup_log.append(f"{probe_id} {target.method} {target.concrete_url}: {detail}")
                if not ok:
                    self._fused = True  # D28b circuit breaker (this probe is recorded; the orchestration layer stops on fused)
            else:
                # Write probe returned 2xx but no handle can be extracted (PUT/PATCH modify in place / DELETE removes a real resource): reversibility cannot be proven per probe.
                cleanup["required"] = True
                cleanup["performed"] = False
                if self.trust_basis == "environment_reset":
                    # D60: environment-level reversibility fallback: record the basis and do not trip the breaker (the end-of-batch
                    # reset by the orchestration layer delivers reversibility); the gate admits basis=environment_reset as trusted.
                    cleanup["basis"] = "environment_reset"
                    cleanup["detail"] = ("write_2xx_no_handle: no extractable handle, reversibility cannot be proven per probe; "
                                         "trust_basis=environment_reset → trusted admission relies on the end-of-batch reset (D60)")
                else:
                    # per_probe_cleanup (V1 behavior): mark as untrusted and trip the breaker (D28a caution).
                    cleanup["basis"] = "per_probe_cleanup"
                    cleanup["detail"] = "write_2xx_no_handle: relies on the environment-level reset fallback; reversibility cannot be proven per probe, breaker tripped"
                    self._fused = True
                self.cleanup_log.append(f"{probe_id} {target.method} {target.concrete_url}: {cleanup['detail']}")

        # Build the probe record (reused_request_ref present and request.body absent ⟺ body skipped due to irreversible redaction, ruling 4)
        construction_basis = {"strategy": "method_completion"}
        if target.reused_request_ref:
            construction_basis["reused_request_ref"] = target.reused_request_ref
        if target.anchor_sequence:
            construction_basis["anchor_sequence"] = target.anchor_sequence

        request: dict = {"method": target.method, "url": target.concrete_url}
        if self.token:
            request["headers"] = {"Authorization": f"{self.token_scheme} {self.token}"}
        if self.session_cookie_header:
            request.setdefault("headers", {})["Cookie"] = _redacted_cookie_header(self.session_cookie_header)
        if body_text is not None:
            request["body"] = body_text

        response: dict = {"status": result.status}
        if result.body_text is not None:
            response["body"] = result.body_text

        return {
            "probe_id": probe_id,
            "target": {"method": target.method, "canonical_path": target.canonical_path},
            "construction_basis": construction_basis,
            "request": request,
            "response": response,
            "success": success,
            "cleanup": cleanup,
        }


def login_token(base_url: str, email: str, password: str, auth) -> str | None:
    """API login per the profile to obtain the real Authorization token; returns None for auth.method=none/cookie_session.

    The login path, body template and token JSONPath all come from app_profile, so Stage2.5 is not bound to Conduit.
    """
    return login_auth(base_url, email, password, auth).token


def login_auth(base_url: str, email: str, password: str, auth) -> RuntimeAuth:
    """Obtain the runtime auth context per the profile (Authorization token or session cookie)."""
    method = getattr(auth, "method", None)
    if method == "none":
        return RuntimeAuth(token_scheme=getattr(auth, "token_scheme", "Token"))
    if method == "cookie_session":
        return _login_cookie_session(base_url, email, password, auth)
    api_token = getattr(auth, "api_token", None)
    if api_token is None:
        raise RuntimeError("Stage 2.5 authentication failed: profile.auth.api_token is not configured")

    body = _render_template(api_token.body_template, email, password)
    res = _http(
        api_token.method,
        _join_url(base_url, api_token.path),
        None,
        "",
        json.dumps(body, ensure_ascii=False),
        "application/json",
        dict(getattr(api_token, "headers", {}) or {}),
    )
    if not (200 <= res.status < 300) or not res.body_text:
        raise RuntimeError(f"Stage 2.5 authentication failed: login returned {res.status}")
    try:
        doc = json.loads(res.body_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Stage 2.5 authentication failed: login response is not JSON") from exc
    token = extract_value(doc, api_token.token_json_path)
    if token is None:
        raise RuntimeError(f"Stage 2.5 authentication failed: login response lacks token {api_token.token_json_path}")
    return RuntimeAuth(token=str(token), token_scheme=getattr(auth, "token_scheme", "Token"))


def _login_cookie_session(base_url: str, email: str, password: str, auth) -> RuntimeAuth:
    cfg = getattr(auth, "cookie_session", None)
    if cfg is None:
        raise RuntimeError("Stage 2.5 authentication failed: profile.auth.cookie_session is not configured")
    body = _render_template(cfg.body_template, email, password)
    login_headers, csrf_cookie_header = _cookie_session_login_headers(base_url, cfg)
    res = _http(
        cfg.method,
        _join_url(base_url, cfg.path),
        None,
        "",
        json.dumps(body, ensure_ascii=False),
        "application/json",
        login_headers,
        csrf_cookie_header,
    )
    if not (200 <= res.status < 300):
        raise RuntimeError(f"Stage 2.5 authentication failed: cookie login returned {res.status}")
    cookie_name, cookie_value = _extract_session_cookie(
        res.headers,
        getattr(cfg, "cookie_name", None),
        set_cookies=res.set_cookies,
    )
    csrf_cookie_header_after_login = None
    csrf_header_name = None
    csrf_header_value = None
    csrf = getattr(cfg, "csrf", None)
    if csrf is not None:
        # Prefer the cookie rotated by the login response; keep the prewarm value otherwise.
        jar = SimpleCookie()
        try:
            for value in res.set_cookies:
                jar.load(value)
        except Exception:  # noqa: BLE001 - an unparsable jar falls back to the prewarm cookie
            jar = SimpleCookie()
        morsel = jar.get(csrf.cookie_name)
        token_value = morsel.value if morsel is not None and morsel.value else None
        if token_value is None and csrf_cookie_header:
            token_value = csrf_cookie_header.split("=", 1)[1]
        if token_value:
            csrf_cookie_header_after_login = f"{csrf.cookie_name}={token_value}"
            csrf_header_name = csrf.header_name
            csrf_header_value = token_value
    return RuntimeAuth(
        token_scheme=getattr(auth, "token_scheme", "Token"),
        session_cookie_name=cookie_name,
        session_cookie_value=cookie_value,
        session_cookie_header=f"{cookie_name}={cookie_value}",
        csrf_cookie_header=csrf_cookie_header_after_login,
        csrf_header_name=csrf_header_name,
        csrf_header_value=csrf_header_value,
    )


def _cookie_session_login_headers(base_url: str, cfg) -> tuple[dict[str, str], str | None]:
    """Static profile headers, plus a dynamic CSRF double-submit when the profile declares one.

    Without ``cookie_session.csrf`` this returns exactly ``dict(cfg.headers)`` and no
    cookie header, i.e. the request the caller sent before the field existed. With it,
    the entry page is fetched once so the framework can set its CSRF cookie, and that
    value is echoed both as a Cookie and in the declared header.
    """
    headers = dict(getattr(cfg, "headers", {}) or {})
    csrf = getattr(cfg, "csrf", None)
    if csrf is None:
        return headers, None
    prewarm = _http("GET", _join_url(base_url, "/"), None, "", None, None)
    jar = SimpleCookie()
    try:
        for value in prewarm.set_cookies:
            jar.load(value)
    except Exception:  # noqa: BLE001 - an unparsable jar is reported below as a missing cookie
        jar = SimpleCookie()
    morsel = jar.get(csrf.cookie_name)
    if morsel is None or not morsel.value:
        raise RuntimeError(
            "Stage 2.5 authentication failed: the declared CSRF cookie "
            f"{csrf.cookie_name} was not set by the prewarm request"
        )
    headers[csrf.header_name] = morsel.value
    return headers, f"{csrf.cookie_name}={morsel.value}"


def all_set_cookies(message) -> tuple[str, ...]:
    """Every Set-Cookie value of one response, in order.

    ``dict(resp.headers)`` keeps only one value of a repeated header, which is exactly
    wrong for Set-Cookie. ``email.message.Message.get_all`` keeps them all; a message
    object without it (or with a single value) degrades to the old result.
    """
    getter = getattr(message, "get_all", None)
    if getter is not None:
        return tuple(str(value) for value in (getter("Set-Cookie") or ()))
    value = _header_value(message, "Set-Cookie")
    return (value,) if value else ()


def _extract_session_cookie(
    headers: dict,
    expected_name: str | None = None,
    *,
    set_cookies: tuple[str, ...] | list[str] = (),
) -> tuple[str, str]:
    # A single Set-Cookie gives exactly the former single-string behaviour.
    values = tuple(set_cookies) or tuple(
        value for value in (_header_value(headers, "Set-Cookie"),) if value
    )
    if not values:
        raise RuntimeError("Stage 2.5 authentication failed: cookie login response lacks Set-Cookie")
    jar = SimpleCookie()
    try:
        for value in values:
            jar.load(value)
    except Exception as exc:
        raise RuntimeError("Stage 2.5 authentication failed: Set-Cookie cannot be parsed") from exc
    if not jar:
        raise RuntimeError("Stage 2.5 authentication failed: Set-Cookie carries no usable cookie")
    if expected_name:
        morsel = jar.get(expected_name)
        if morsel is None:
            raise RuntimeError(f"Stage 2.5 authentication failed: Set-Cookie lacks cookie {expected_name}")
        return expected_name, morsel.value
    name = next(iter(jar.keys()))
    return name, jar[name].value


def _header_value(headers: dict, name: str) -> str | None:
    wanted = name.lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == wanted:
            return str(value)
    return None


def _redacted_cookie_header(cookie_header: str) -> str:
    parts = []
    for chunk in cookie_header.split(";"):
        item = chunk.strip()
        if not item:
            continue
        if "=" in item:
            name, _value = item.split("=", 1)
            parts.append(f"{name.strip()}=[REDACTED:session_cookie]")
        else:
            parts.append("[REDACTED:session_cookie]")
    return "; ".join(parts) if parts else "[REDACTED:session_cookie]"


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _render_template(value: Any, email: str, password: str) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(child, email, password) for key, child in value.items()}
    if isinstance(value, list):
        return [_render_template(child, email, password) for child in value]
    if isinstance(value, str):
        return value.replace("${email}", email).replace("${password}", password)
    return value
