"""Recorder: Playwright + our own CDP Network domain listener (001 D7).

Captures every request/response (including response bodies), millisecond timestamps, and the CDP initiator (written to HAR `_initiator`).
Stage 0 only attaches it and smoke-tests it (in-memory); writing the session bundle to disk belongs to Stage 1 (001 §7).
The recorder is the single source of truth for session content (engineering invariant).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


@dataclass
class RecordedRequest:
    """Raw observation record of one network request (facts only, no inference; D3)."""

    request_id: str
    url: str
    method: str
    wall_time: float  # epoch seconds (CDP wallTime, millisecond precision)
    started_at: str  # ISO 8601, millisecond resolution
    initiator: dict  # CDP initiator as-is (includes type; written to HAR `_initiator`)
    status: Optional[int] = None
    mime_type: Optional[str] = None
    response_body: Optional[str] = None
    finished: bool = False
    request_headers: dict = field(default_factory=dict)


class NetworkRecorder:
    """CDP Network domain recorder attached independently to the browser page."""

    def __init__(self, capture_body_url_substring: str = "/api"):
        self._entries: dict[str, RecordedRequest] = {}
        self._order: list[str] = []
        self._cdp = None
        self._capture_body_url_substring = capture_body_url_substring

    def attach(self, page) -> None:
        self._cdp = page.context.new_cdp_session(page)
        self._cdp.send("Network.enable")
        self._cdp.on("Network.requestWillBeSent", self._on_request_will_be_sent)
        self._cdp.on("Network.responseReceived", self._on_response_received)
        self._cdp.on("Network.loadingFinished", self._on_loading_finished)

    # --- CDP event handlers (record only, no inference) ---

    def _on_request_will_be_sent(self, params: dict) -> None:
        request = params.get("request", {})
        wall_time = params.get("wallTime", 0.0)
        entry = RecordedRequest(
            request_id=params.get("requestId", ""),
            url=request.get("url", ""),
            method=request.get("method", ""),
            wall_time=wall_time,
            started_at=datetime.fromtimestamp(wall_time, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            initiator=params.get("initiator", {}),
            request_headers=dict(request.get("headers", {})),
        )
        self._entries[entry.request_id] = entry
        self._order.append(entry.request_id)

    def _on_response_received(self, params: dict) -> None:
        entry = self._entries.get(params.get("requestId", ""))
        if entry is None:
            return
        response = params.get("response", {})
        entry.status = response.get("status")
        entry.mime_type = response.get("mimeType")

    def _on_loading_finished(self, params: dict) -> None:
        entry = self._entries.get(params.get("requestId", ""))
        if entry is None:
            return
        entry.finished = True

    def fetch_body(self, entry: RecordedRequest) -> Optional[str]:
        """Fetch the response body from CDP on demand (must be called from the main flow, not inside an event handler: sync API re-entrancy limit)."""
        if entry.response_body is not None:
            return entry.response_body
        try:
            result = self._cdp.send(
                "Network.getResponseBody", {"requestId": entry.request_id}
            )
            body = result.get("body", "")
            if result.get("base64Encoded"):
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            entry.response_body = body
        except Exception:
            # the browser may already have discarded the response body; a missing body does not affect the request record itself
            entry.response_body = None
        return entry.response_body

    # --- Query interface ---

    @property
    def entries(self) -> list[RecordedRequest]:
        return [self._entries[rid] for rid in self._order]

    def find(
        self, predicate: Callable[[RecordedRequest], bool]
    ) -> Optional[RecordedRequest]:
        for entry in self.entries:
            if predicate(entry):
                return entry
        return None
