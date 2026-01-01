"""Conservative structured parsing for Location/Link response headers."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

LOCATION_PATH_PREFIX = "location.path["
_LOCATION_PATH_RE = re.compile(r"^location\.path\[(?P<index>-?\d+)\]$")
_MAX_SEGMENT_LEN = 128
_SENSITIVE_QUERY_NAMES = {
    "auth",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
}
_LINK_RE = re.compile(r"\s*<(?P<url>[^>]*)>\s*(?P<params>(?:;\s*[^;,]+)*)")


def iter_location_path_values(location_value: str | None, request_url: str | None = None) -> list[tuple[str, str]]:
    """Return ``(location.path[index], segment)`` pairs for safe Location headers.

    Accepted forms are same-origin absolute HTTP(S) URLs and root-relative paths.
    Query strings containing sensitive names reject the whole Location value.
    """

    path = _safe_location_path(location_value, request_url)
    if path is None:
        return []
    segments = [segment for segment in path.strip("/").split("/") if segment]
    out: list[tuple[str, str]] = []
    for idx, segment in enumerate(segments):
        if _safe_segment(segment):
            out.append((f"location.path[{idx}]", segment))
    return out


def extract_location_path_value(
    location_value: str | None,
    from_field: str,
    request_url: str | None = None,
) -> str | None:
    """Resolve one ``location.path[index]`` selector from a Location header."""

    match = _LOCATION_PATH_RE.fullmatch(str(from_field))
    if not match:
        return None
    values = [value for _field, value in iter_location_path_values(location_value, request_url)]
    if not values:
        return None
    index = int(match.group("index"))
    if index < 0:
        index += len(values)
    if index < 0 or index >= len(values):
        return None
    return values[index]


def is_location_path_field(from_field: str) -> bool:
    return bool(_LOCATION_PATH_RE.fullmatch(str(from_field)))


def parse_link_header(link_value: str | None) -> list[dict[str, str]]:
    """Parse basic RFC5988-style Link values for diagnostics/guards.

    The parser is intentionally not used to create ordinary data dependencies.
    """

    if not link_value:
        return []
    links: list[dict[str, str]] = []
    for part in str(link_value).split(","):
        match = _LINK_RE.fullmatch(part.strip())
        if not match:
            continue
        item = {"url": match.group("url")}
        for raw_param in match.group("params").split(";"):
            if "=" not in raw_param:
                continue
            name, value = raw_param.split("=", 1)
            item[name.strip().lower()] = value.strip().strip('"')
        links.append(item)
    return links


def _safe_location_path(location_value: str | None, request_url: str | None) -> str | None:
    if location_value is None:
        return None
    value = str(location_value).strip()
    if not value or "\r" in value or "\n" in value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme.lower() not in {"http", "https"}:
            return None
        if request_url is not None and not _same_origin(parsed, urlsplit(str(request_url))):
            return None
    elif not value.startswith("/"):
        return None
    if _has_sensitive_query(parsed.query):
        return None
    path = parsed.path or ""
    if not path.startswith("/"):
        return None
    return path.rstrip("/") or "/"


def _same_origin(location, request) -> bool:
    return (
        location.scheme.lower() == request.scheme.lower()
        and location.netloc.lower() == request.netloc.lower()
    )


def _has_sensitive_query(query: str) -> bool:
    if not query:
        return False
    for pair in query.split("&"):
        name = pair.split("=", 1)[0].strip().lower()
        if name in _SENSITIVE_QUERY_NAMES or any(marker in name for marker in _SENSITIVE_QUERY_NAMES):
            return True
    return False


def _safe_segment(segment: str) -> bool:
    if not segment or len(segment) > _MAX_SEGMENT_LEN:
        return False
    if "\r" in segment or "\n" in segment:
        return False
    lowered = segment.lower()
    return not any(marker in lowered for marker in _SENSITIVE_QUERY_NAMES)
