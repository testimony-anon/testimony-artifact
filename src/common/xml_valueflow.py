"""Conservative XML scalar extraction for response-body value flow.

The helper is intentionally small: it only consumes runtime response bodies,
skips HTML/spec-like documents, and exposes stable field paths that can be
resolved during replay.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from typing import Any

XML_FIELD_PREFIX = "xml:"
_MAX_SCALAR_LEN = 128
_SEGMENT_RE = re.compile(r"^(?P<name>[^/@\[\]]+)(?:\[(?P<index>\d+)\])?$")
_SPEC_ROOTS = {"application", "definitions", "description"}
_SPEC_KEYWORDS = ("wadl", "wsdl", "swagger", "openapi", "api-docs", "soap:")


def iter_xml_scalar_values(
    body_text: str | None,
    content_type: str | None = None,
) -> list[tuple[str, str]]:
    """Return ``(xml_field, scalar_value)`` pairs in document order.

    Fields use a compact path syntax such as ``xml:/accounts/account[0]/id`` or
    ``xml:/item/@href``. Sibling indexes are included only when needed to
    disambiguate repeated tags under the same parent.
    """

    root = _parse_runtime_xml(body_text, content_type)
    if root is None:
        return []
    out: list[tuple[str, str]] = []
    _walk(root, f"{XML_FIELD_PREFIX}/{_local_name(root.tag)}", out)
    return out


def extract_xml_value(body_text: str | None, from_field: str) -> Any | None:
    """Resolve one ``xml:/...`` field from raw XML body text."""

    if not str(from_field).startswith(f"{XML_FIELD_PREFIX}/"):
        return None
    root = _parse_runtime_xml(body_text, None)
    if root is None:
        return None
    path = str(from_field)[len(XML_FIELD_PREFIX):]
    parts = [part for part in path.strip("/").split("/") if part]
    if not parts:
        return None
    root_name = _local_name(root.tag)
    if parts[0] != root_name:
        return None
    cur = root
    for part in parts[1:]:
        if part.startswith("@"):
            return _scalar(cur.attrib.get(_attr_key(cur, part[1:])))
        match = _SEGMENT_RE.fullmatch(part)
        if not match:
            return None
        name = match.group("name")
        index = int(match.group("index") or 0)
        matches = [child for child in list(cur) if _local_name(child.tag) == name]
        if index >= len(matches):
            return None
        cur = matches[index]
    if list(cur):
        return None
    return _scalar(cur.text)


def is_xml_field(field: str) -> bool:
    return str(field).startswith(f"{XML_FIELD_PREFIX}/")


def is_xml_id_like_field(field: str) -> bool:
    terminal = str(field).rstrip("/").rsplit("/", 1)[-1]
    if terminal.startswith("@"):
        terminal = terminal[1:]
    if "[" in terminal:
        terminal = terminal.split("[", 1)[0]
    return terminal.lower().endswith("id")


def _parse_runtime_xml(body_text: str | None, content_type: str | None) -> ET.Element | None:
    if not _looks_like_runtime_xml(body_text, content_type):
        return None
    try:
        root = ET.fromstring(str(body_text))
    except ET.ParseError:
        return None
    if _is_spec_like_xml(root, str(body_text)):
        return None
    return root


def _looks_like_runtime_xml(body_text: str | None, content_type: str | None) -> bool:
    if not body_text:
        return False
    text = str(body_text).lstrip()
    if not text.startswith("<"):
        return False
    lowered = text[:400].lower()
    if "<html" in lowered or lowered.startswith("<!doctype html"):
        return False
    ctype = (content_type or "").lower()
    return "xml" in ctype or text.startswith("<?xml") or bool(re.match(r"^<[A-Za-z_][\w:.-]*(\s|>|/>)", text))


def _is_spec_like_xml(root: ET.Element, body_text: str) -> bool:
    root_name = _local_name(root.tag).lower()
    sample = body_text[:1500].lower()
    if root_name in _SPEC_ROOTS and any(keyword in sample for keyword in _SPEC_KEYWORDS):
        return True
    if root_name in {"html", "head", "body"}:
        return True
    return False


def _walk(element: ET.Element, path: str, out: list[tuple[str, str]]) -> None:
    for attr_name, attr_value in sorted(element.attrib.items(), key=lambda item: _local_name(item[0])):
        scalar = _scalar(attr_value)
        if scalar is not None:
            out.append((f"{path}/@{_local_name(attr_name)}", scalar))
    children = list(element)
    if not children:
        scalar = _scalar(element.text)
        if scalar is not None:
            out.append((path, scalar))
        return
    counts = Counter(_local_name(child.tag) for child in children)
    seen: dict[str, int] = defaultdict(int)
    for child in children:
        name = _local_name(child.tag)
        idx = seen[name]
        seen[name] += 1
        seg = f"{name}[{idx}]" if counts[name] > 1 else name
        _walk(child, f"{path}/{seg}", out)


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > _MAX_SCALAR_LEN:
        return None
    if "\n" in text or "\r" in text:
        return None
    return text


def _local_name(name: str) -> str:
    if "}" in name:
        name = name.rsplit("}", 1)[-1]
    if ":" in name:
        name = name.rsplit(":", 1)[-1]
    return name


def _attr_key(element: ET.Element, local_name: str) -> str | None:
    for key in element.attrib:
        if _local_name(key) == local_name:
            return key
    return None
