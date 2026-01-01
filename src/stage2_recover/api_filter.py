"""API traffic classification (003 D21, conjunctive criterion).

An API observation requires `_resource_type ∈ {XHR, Fetch}` and `_initiator.type == "script"`; entries where the
two disagree get a diagnostic warning (non-blocking, not treated as API). The decision is independent of the response
status (4xx/5xx still count as observations). CORS preflight OPTIONS is not an operation observation; HEAD/TRACE likewise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit

from common.request_admission import response_mime_is_admitted

from .loader import LoadedBundle

API_RESOURCE_TYPES = {"XHR", "Fetch"}
EXCLUDED_METHODS = {"OPTIONS", "HEAD", "TRACE"}


def _normalize_mime(content_type: str | None) -> str:
    """Content-Type → normalized mime (drops charset and other parameters; lesson from malformed media-type keys in the old library)."""
    if not content_type:
        return ""
    return content_type.split(";")[0].strip().lower()


def _strip_trailing_slash(path: str) -> str:
    """Trailing-slash normalization (D23; the root path is left as is)."""
    return path.rstrip("/") if path != "/" else path


@dataclass
class ApiObservation:
    """Parsed view of one API observation (the HAR entry remains the source of truth, reachable via entry_index)."""

    run_id: str
    entry_index: int
    method: str
    path: str  # pathname without query and trailing slash
    scheme_host: str
    query: list[dict]  # [{name, value}]
    status: int
    response_mime: str
    auth_present: bool
    started_at: str
    started_ts: float
    initiator: dict
    response_body_json: object = None  # parsed 2xx JSON body (None if absent)
    request_body_text: Optional[str] = None
    request_body_mime: str = ""
    # join results (filled in by join.py)
    action_id: Optional[str] = None
    orphan_class: Optional[str] = None
    confidence_tier: Optional[str] = None


def classify_bundle(bundle: LoadedBundle) -> tuple[list[ApiObservation], list[str]]:
    observations: list[ApiObservation] = []
    warnings: list[str] = []
    for index, entry in enumerate(bundle.entries):
        is_xhr = entry.get("_resource_type") in API_RESOURCE_TYPES
        is_script = entry.get("_initiator", {}).get("type") == "script"
        if is_xhr != is_script:
            warnings.append(
                f"[D21 diagnostic] {bundle.run_id}#{index} resource type and initiator criteria disagree: "
                f"resource_type={entry.get('_resource_type')} "
                f"initiator={entry.get('_initiator', {}).get('type')} "
                f"{entry['request']['method']} {entry['request']['url']}"
            )
        if not (is_xhr and is_script):
            continue
        if not response_mime_is_admitted(entry):
            # Same criterion M1 applies (common.request_admission): a framework
            # transport payload carries no API surface, and admitting it here while
            # M1 drops it would leave a Stage3 observation with no request_ref.
            continue
        method = entry["request"]["method"].upper()
        if method in EXCLUDED_METHODS:
            continue  # preflight/sniffing noise is not an operation observation (kept in the HAR)

        url_parts = urlsplit(entry["request"]["url"])
        status = entry["response"]["status"] or 0
        mime = _normalize_mime(entry["response"]["content"].get("mimeType"))
        body_json = None
        if 200 <= status < 300 and "json" in mime:
            text = entry["response"]["content"].get("text")
            if text is not None:
                try:
                    body_json = json.loads(text)
                except json.JSONDecodeError:
                    body_json = None
        post = entry["request"].get("postData")
        auth_present = any(
            h["name"].lower() == "authorization" for h in entry["request"]["headers"]
        )
        observations.append(
            ApiObservation(
                run_id=bundle.run_id,
                entry_index=index,
                method=method,
                path=_strip_trailing_slash(url_parts.path),
                scheme_host=f"{url_parts.scheme}://{url_parts.netloc}",
                query=list(entry["request"].get("queryString", [])),
                status=status,
                response_mime=mime,
                auth_present=auth_present,
                started_at=entry["startedDateTime"],
                started_ts=datetime.fromisoformat(entry["startedDateTime"]).timestamp(),
                initiator=entry.get("_initiator", {}),
                response_body_json=body_json,
                request_body_text=post.get("text") if post else None,
                request_body_mime=_normalize_mime(post.get("mimeType")) if post else "",
            )
        )
    return observations, warnings
