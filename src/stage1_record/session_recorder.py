"""Session-level recorder (002 D15 + S3): extends the Stage 0 NetworkRecorder.

- enlarges the Network buffers (maxTotalBufferSize/maxResourceBufferSize);
- response bodies are queued when loadingFinished arrives and pulled promptly by the main loop (the sync API forbids calls inside handlers);
- bodies are kept only for XHR/fetch with text-like content (json/text/xml/form); static resources record only their size (by design, no annotation);
- a body that should have been kept but was not → `_body_dropped` + reason (distinguishing 'no body' from 'dropped');
- redirect chains / multiple hops under the same requestId: one independent record per hop (S3 item 1, no hard matching by index);
- dual timestamps: CDP monotonic + wallTime, with the conversion base written alongside the har (S3 item 2);
- finalization waits for outstanding body fetches (S3 item 3).
"""

from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, parse_qsl

from common import TOOL_VERSION
from stage0_launch.recorder import NetworkRecorder, RecordedRequest

CAPTURE_RESOURCE_TYPES = {"XHR", "Fetch"}
TEXT_MIME_MARKERS = (
    "application/json",
    "text/",
    "application/xml",
    "+json",
    "+xml",
    "application/x-www-form-urlencoded",
)


def _is_text_mime(mime: str | None) -> bool:
    return bool(mime) and any(m in mime for m in TEXT_MIME_MARKERS)


@dataclass
class SessionRecordedRequest(RecordedRequest):
    """Extends the Stage 0 record with the fields required by D15."""

    monotonic_time: float = 0.0
    resource_type: Optional[str] = None
    post_data: Optional[str] = None
    response_headers: dict = field(default_factory=dict)
    status_text: str = ""
    http_version: str = "HTTP/1.1"
    encoded_size: int = 0
    body_dropped: Optional[str] = None
    failed_reason: Optional[str] = None
    redirect_hop: int = 0


class SessionRecorder(NetworkRecorder):
    def __init__(self):
        super().__init__()
        self._pending_bodies: deque[str] = deque()
        self._clock_base: dict | None = None
        self._hop_counts: dict[str, int] = {}

    def attach(self, page) -> None:
        self._cdp = page.context.new_cdp_session(page)
        self._cdp.send(
            "Network.enable",
            {"maxTotalBufferSize": 200_000_000, "maxResourceBufferSize": 50_000_000},
        )
        self._cdp.on("Network.requestWillBeSent", self._on_request_will_be_sent)
        self._cdp.on("Network.responseReceived", self._on_response_received)
        self._cdp.on("Network.loadingFinished", self._on_loading_finished)
        self._cdp.on("Network.loadingFailed", self._on_loading_failed)

    # --- CDP event handlers (record and enqueue only; no CDP calls inside handlers) ---

    def _on_request_will_be_sent(self, params: dict) -> None:
        rid = params.get("requestId", "")
        request = params.get("request", {})
        wall_time = params.get("wallTime", 0.0)
        monotonic = params.get("timestamp", 0.0)
        if self._clock_base is None:
            self._clock_base = {"wall_time": wall_time, "monotonic": monotonic}

        # redirect chain: the same requestId arrives again with redirectResponse; the previous hop is frozen as an independent record (S3 item 1)
        if rid in self._entries and params.get("redirectResponse"):
            prev = self._entries[rid]
            redirect = params["redirectResponse"]
            prev.status = redirect.get("status")
            prev.status_text = redirect.get("statusText", "")
            prev.mime_type = redirect.get("mimeType")
            prev.response_headers = dict(redirect.get("headers", {}))
            prev.finished = True
            hop = self._hop_counts.get(rid, 0)
            hop_key = f"{rid}#hop{hop}"
            self._hop_counts[rid] = hop + 1
            self._entries[hop_key] = prev
            self._order[self._order.index(rid)] = hop_key
        entry = SessionRecordedRequest(
            request_id=rid,
            url=request.get("url", ""),
            method=request.get("method", ""),
            wall_time=wall_time,
            started_at=datetime.fromtimestamp(wall_time, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            initiator=params.get("initiator", {}),
            request_headers=dict(request.get("headers", {})),
            monotonic_time=monotonic,
            resource_type=params.get("type"),
            post_data=request.get("postData"),
            redirect_hop=self._hop_counts.get(rid, 0),
        )
        self._entries[rid] = entry
        self._order.append(rid)

    def _on_response_received(self, params: dict) -> None:
        entry = self._entries.get(params.get("requestId", ""))
        if not isinstance(entry, SessionRecordedRequest):
            return
        response = params.get("response", {})
        entry.status = response.get("status")
        entry.status_text = response.get("statusText", "")
        entry.mime_type = response.get("mimeType")
        entry.response_headers = dict(response.get("headers", {}))
        entry.http_version = response.get("protocol") or "HTTP/1.1"
        if params.get("type"):
            entry.resource_type = params["type"]

    def _should_capture_body(self, entry: SessionRecordedRequest) -> bool:
        return entry.resource_type in CAPTURE_RESOURCE_TYPES and _is_text_mime(entry.mime_type)

    def _on_loading_finished(self, params: dict) -> None:
        rid = params.get("requestId", "")
        entry = self._entries.get(rid)
        if not isinstance(entry, SessionRecordedRequest):
            return
        entry.finished = True
        entry.encoded_size = int(params.get("encodedDataLength", 0))
        if self._should_capture_body(entry):
            self._pending_bodies.append(rid)  # enqueue; the main loop pulls it promptly

    def _on_loading_failed(self, params: dict) -> None:
        entry = self._entries.get(params.get("requestId", ""))
        if not isinstance(entry, SessionRecordedRequest):
            return
        entry.finished = True
        entry.failed_reason = params.get("errorText", "loading_failed")

    # --- Main-loop interface ---

    def drain_pending_bodies(self) -> None:
        """Called on every main-loop tick: fetch the bodies of finished responses immediately; failures are annotated with _body_dropped (D15)."""
        while self._pending_bodies:
            rid = self._pending_bodies.popleft()
            entry = self._entries.get(rid)
            if not isinstance(entry, SessionRecordedRequest) or entry.response_body is not None:
                continue
            try:
                result = self._cdp.send("Network.getResponseBody", {"requestId": rid})
                body = result.get("body", "")
                if result.get("base64Encoded"):
                    body = base64.b64decode(body).decode("utf-8", errors="replace")
                entry.response_body = body
            except Exception as exc:  # discarded by navigation / evicted from the buffer; do not block, annotate honestly
                entry.body_dropped = f"fetch_failed: {exc}"

    def _has_inflight_captures(self) -> bool:
        return any(
            isinstance(entry, SessionRecordedRequest)
            and entry.resource_type in CAPTURE_RESOURCE_TYPES
            and not entry.finished
            for entry in self.entries
        )

    def settle(self, page, timeout_ms: int = 1500) -> None:
        """Bounded wait for in-flight captures, then pull their bodies.

        Called before every workflow step: a navigation that follows a submit
        evicts the previous document's network resources from the browser, and
        an XHR that finished after the post-action drain would otherwise be
        recorded as ``_body_dropped`` (observed on the RWA ``POST
        /transactions`` creation responses).  The wait is bounded; anything
        still in flight at the deadline stays honestly marked.
        """
        import time

        deadline = time.monotonic() + timeout_ms / 1000.0
        while (
            self._pending_bodies or self._has_inflight_captures()
        ) and time.monotonic() < deadline:
            self.drain_pending_bodies()
            if self._pending_bodies or self._has_inflight_captures():
                page.wait_for_timeout(100)
        self.drain_pending_bodies()

    def finish(self, page, timeout_ms: int = 5000) -> None:
        """Finalization: wait for outstanding body fetches (S3 item 3) so trailing responses do not lose their bodies at the instant the session ends."""
        self.settle(page, timeout_ms=timeout_ms)

    # --- HAR assembly (D17: assembled at finalization; redaction is done by BundleWriter as a rescan against the full secret set) ---

    def assemble_har(self) -> dict:
        entries = []
        for e in self.entries:
            if not isinstance(e, SessionRecordedRequest):
                continue
            url_parts = urlsplit(e.url)
            request: dict = {
                "method": e.method,
                "url": e.url,
                "httpVersion": e.http_version,
                "cookies": [],
                "headers": [{"name": k, "value": v} for k, v in e.request_headers.items()],
                "queryString": [
                    {"name": k, "value": v} for k, v in parse_qsl(url_parts.query)
                ],
                "headersSize": -1,
                "bodySize": len(e.post_data) if e.post_data else -1,
            }
            if e.post_data is not None:
                request["postData"] = {
                    "mimeType": e.request_headers.get("Content-Type", ""),
                    "text": e.post_data,
                }
            content: dict = {
                "size": e.encoded_size,
                "mimeType": e.mime_type or "",
            }
            if e.response_body is not None:
                content["text"] = e.response_body
            entry: dict = {
                "startedDateTime": e.started_at,
                "time": -1,
                "request": request,
                "response": {
                    "status": e.status or 0,
                    "statusText": e.status_text,
                    "httpVersion": e.http_version,
                    "cookies": [],
                    "headers": [
                        {"name": k, "value": v} for k, v in e.response_headers.items()
                    ],
                    "content": content,
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": e.encoded_size or -1,
                },
                "cache": {},
                "timings": {"send": -1, "wait": -1, "receive": -1},
                "_initiator": e.initiator,
                "_monotonic_time": e.monotonic_time,
                "_resource_type": e.resource_type,
                "_redirect_hop": e.redirect_hop,
            }
            if e.body_dropped:
                entry["_body_dropped"] = e.body_dropped
            if e.failed_reason:
                entry["_loading_failed"] = e.failed_reason
            entries.append(entry)
        return {
            "log": {
                "version": "1.2",
                "creator": {"name": "carverflow-recorder", "version": TOOL_VERSION},
                "entries": entries,
                "_clock_base": self._clock_base or {},
            }
        }
