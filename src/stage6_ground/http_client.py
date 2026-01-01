"""Stage 6 low-level replay HTTP (real outbound traffic; sent directly via urllib, D47/D29 style) + business_success oracle (M5).

Tokens stay in memory only (D18): this module writes nothing to disk; the caller must redact before writing grounded_report.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


def _canonical_headers(headers: dict | None) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (headers or {}).items()}


def _all_set_cookies(message) -> tuple[str, ...]:
    """Every Set-Cookie value of one response, in order (see HttpResult.set_cookies)."""
    getter = getattr(message, "get_all", None)
    if getter is None:
        return ()
    return tuple(str(value) for value in (getter("Set-Cookie") or ()))


def response_set_cookies(response) -> tuple[str, ...]:
    """Every Set-Cookie value a replay response carries.

    ``headers`` is flat, so a response that sets several cookies in separate headers
    keeps only one of them there. A transport that fills ``set_cookies`` gives the full
    list; a replay fixture or test double that does not degrades to the single flat
    value, which is exactly what the callers read before this existed.
    """
    values = tuple(getattr(response, "set_cookies", ()) or ())
    if values:
        return values
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("set-cookie") if hasattr(headers, "get") else None
    return (str(raw),) if raw else ()


@dataclass
class HttpResult:
    status: int
    body_text: str | None
    headers: dict[str, str] = field(default_factory=dict)
    timing: dict[str, int] = field(default_factory=dict)
    # `headers` is a flat dict, so a repeated header collapses to a single value
    # (`dict(Message)` keeps the first). Set-Cookie is the one header where that
    # loses information -- a login response may set the session cookie and a CSRF
    # cookie in separate headers -- so every value is preserved here as well.
    # Empty for replay-constructed results.
    set_cookies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.headers = _canonical_headers(self.headers)

    def json(self) -> dict | list | None:
        if not self.body_text:
            return None
        try:
            return json.loads(self.body_text)
        except json.JSONDecodeError:
            return None


def send(method: str, url: str, headers: dict | None = None,
         body_text: str | None = None, timeout: int = 15) -> HttpResult:
    """Send one real HTTP request; 4xx/5xx are caught via HTTPError and returned as normal results (a replay always receives a response)."""
    h = dict(headers or {})
    data = None
    if body_text is not None:
        data = body_text.encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    sent = time.monotonic_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            return HttpResult(resp.status, raw or None, dict(resp.headers), {"send_ns": sent, "receive_ns": time.monotonic_ns()}, _all_set_cookies(resp.headers))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return HttpResult(exc.code, raw or None, dict(exc.headers or {}), {"send_ns": sent, "receive_ns": time.monotonic_ns()}, _all_set_cookies(exc.headers))


def business_success(result: HttpResult) -> bool:
    """Business-success oracle (M5): status code 2xx/3xx and no error structure in the response body.

    Legacy Conduit and several simple REST apps use {"errors": ...} as an
    application-level failure shape; if a 2xx response still contains that
    explicit error key, keep the replay verdict conservative.
    """
    if not (200 <= result.status < 400):
        return False
    doc = result.json()
    if isinstance(doc, dict) and doc.get("errors"):
        return False
    return True


class Throttle:
    """Replay throttling (reuses the run_config.rate_limit idea; end of D48)."""

    def __init__(self, min_interval_ms: int = 80):
        self.min_interval = min_interval_ms / 1000.0
        self._last = 0.0

    def wait(self) -> None:
        delta = self.min_interval - (time.monotonic() - self._last)
        if delta > 0:
            time.sleep(delta)
        self._last = time.monotonic()
