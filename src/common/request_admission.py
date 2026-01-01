"""One request-admission MIME policy, shared by M1 and the Stage2/Stage3 recovery path.

M1 (``ui_semantics.trace_builder``) and Stage 2/3 (``stage2_recover.api_filter``) classify
the same HAR entries for different purposes, and they must not disagree about which
entries carry an API surface: an entry that Stage 3 turns into an operation observation
but M1 never admitted has no ``request_ref`` to point at, and
``ui_semantics.preproposal.build_observed_api_catalog`` rejects the whole run.

Both therefore read the exclusion list from here. It holds framework transport media
types that arrive as fetch/xhr but carry no API surface: Next.js App Router prefetches
every navigation link as ``text/x-component`` (RSC), which on a Next.js subject can be
the large majority of the otherwise admitted entries.
"""

from __future__ import annotations

from typing import Any, Mapping

EXCLUDED_RESPONSE_MIME_TYPES = frozenset({"text/x-component"})


def normalize_media_type(value: Any) -> str:
    """Canonical lowercase media type, parameters stripped; "" when unknown."""
    return str(value or "").split(";")[0].strip().lower()


def response_media_type(entry: Mapping[str, Any]) -> str:
    """Media type of one HAR entry's response.

    Prefers the recorded ``response.content.mimeType`` and falls back to the
    ``Content-Type`` response header, so a recorder that fills only one of the two
    still yields the same verdict on both sides.
    """
    response = entry.get("response") or {}
    raw = (response.get("content") or {}).get("mimeType")
    if not raw:
        for header in response.get("headers") or []:
            if str(header.get("name") or "").strip().lower() == "content-type":
                raw = header.get("value")
                break
    return normalize_media_type(raw)


def response_mime_is_admitted(entry: Mapping[str, Any]) -> bool:
    """True unless the entry's response media type is an excluded framework transport."""
    return response_media_type(entry) not in EXCLUDED_RESPONSE_MIME_TYPES
