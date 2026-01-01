"""Secret redaction registry (002 D18).

Global string placeholder = [REDACTED:<first 8 hex digits of sha256(session salt + value)>].
- the same string secret is replaced by the same placeholder everywhere within a session (preserving exact data-flow linkability for Stage 4);
- JSON-literal strings and non-string scalars under a sensitive typed path use local placeholders from a separate domain and are not promoted to global value sources;
- the session-level salt prevents dictionary lookup of weak passwords (equality only needs to hold within a session);
- redaction is pinned at the single disk-write exit (BundleWriter); at no moment does unredacted content exist on disk.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets as _pysecrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, quote_plus

_MIN_SECRET_LEN = 4  # full-text replacement of very short values causes widespread false hits; real credentials/tokens are never shorter than this
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "auth_token",
    "cookie",
    "credential",
    "password",
    "secret",
    "set-cookie",
    "session",
    "token",
)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_AUTH_HEADER = re.compile(r"(?i)^\s*(bearer|token)\s+(.+?)\s*$")
_REDACTION_MARKER = re.compile(r"^\[REDACTED(?::[A-Za-z0-9_.-]+)?\]$")
_JSON_LITERAL_STRINGS = frozenset({"true", "false", "null"})
_LOCAL_TYPED_DOMAIN_SEPARATOR = "\x00path-local-typed\x00"
_SOURCE_ORDER = {
    "explicit_registered_secret": 0,
    "authorization": 1,
    "cookie": 2,
    "jwt": 3,
    "sensitive_key": 4,
}
_MATCH_ORDER = {
    "not_applicable": 0,
    "exact_token": 0,
    "separator_delimited_token": 1,
    "substring_only": 2,
}


@dataclass(frozen=True)
class ClassificationBasis:
    source_class: str
    sensitive_key_match: str = "not_applicable"

    def as_dict(self) -> dict[str, str]:
        return {
            "source_class": self.source_class,
            "sensitive_key_match": self.sensitive_key_match,
        }


class SecretRegistry:
    def __init__(self, session_salt: str | None = None):
        self._salt = session_salt or _pysecrets.token_hex(8)
        self._placeholders: dict[str, str] = {}
        self._classification_bases: dict[str, set[ClassificationBasis]] = {}
        self._typed_local_placeholders: dict[tuple[str, str], str] = {}
        self._typed_local_classification_bases: dict[
            tuple[str, str], set[ClassificationBasis]
        ] = {}

    @property
    def salt(self) -> str:
        return self._salt

    def register(
        self,
        value: str | None,
        *,
        source_class: str = "explicit_registered_secret",
        sensitive_key_match: str = "not_applicable",
    ) -> None:
        """Register one secret value. Resolved credentials are registered at session start; the token is registered when the login response body is captured."""
        if not value or len(value) < _MIN_SECRET_LEN:
            return
        basis = ClassificationBasis(source_class, sensitive_key_match)
        if source_class not in _SOURCE_ORDER:
            raise ValueError("unsupported secret classification source")
        if sensitive_key_match not in _MATCH_ORDER:
            raise ValueError("unsupported sensitive-key match classification")
        if (source_class == "sensitive_key") != (sensitive_key_match != "not_applicable"):
            raise ValueError("sensitive-key classification basis is inconsistent")
        if value not in self._placeholders:
            digest = hashlib.sha256((self._salt + value).encode()).hexdigest()[:8]
            self._placeholders[value] = f"[REDACTED:{digest}]"
        self._classification_bases.setdefault(value, set()).add(basis)

    def register_from_obj(self, obj: Any, *, key: str = "") -> None:
        """Best-effort discover runtime secrets from captured structured data.

        Manual recording does not know credentials upfront. Before writing HAR,
        scan captured headers/query/body/JSON and register obvious password,
        token, cookie, authorization, and secret values so equality-preserving
        placeholders are used instead of leaking runtime credentials.
        """
        path = [{"kind": "object_key", "key": key}] if key else []
        self._register_from_obj_at_path(obj, path)

    def _register_from_obj_at_path(
        self, obj: Any, path: list[dict[str, Any]]
    ) -> None:
        if isinstance(obj, dict):
            name = obj.get("name")
            if isinstance(name, str) and "value" in obj and _is_sensitive_key(name):
                self._register_sensitive_value(
                    obj.get("value"),
                    key=name,
                    path=[*path, {"kind": "object_key", "key": name}],
                )
            for item_key, item_value in obj.items():
                item_path = [*path, {"kind": "object_key", "key": str(item_key)}]
                if _is_sensitive_key(str(item_key)):
                    self._register_sensitive_value(
                        item_value,
                        key=str(item_key),
                        path=item_path,
                    )
                else:
                    self._register_from_obj_at_path(item_value, item_path)
            return
        if isinstance(obj, list):
            for index, item in enumerate(obj):
                self._register_from_obj_at_path(
                    item,
                    [*path, {"kind": "array_index", "index": index}],
                )
            return
        if isinstance(obj, str):
            for token in _JWT.findall(obj):
                self.register(token, source_class="jwt")
            self._register_structured_text(obj)

    def placeholder_for(self, value: str) -> str | None:
        return self._placeholders.get(value)

    def redact_text(self, text: str) -> str:
        # replace longer values first so that a short value that is a substring of a longer one does not break the longer value's placeholder
        for value in sorted(self._placeholders, key=len, reverse=True):
            placeholder = self._placeholders[value]
            for representation in _secret_representations(value):
                if representation in text:
                    text = text.replace(representation, placeholder)
        return text

    def redact_obj(self, obj: Any, *, key: str = "") -> Any:
        """Recursively redact an arbitrary JSON structure (dict/list/str; other types are returned as-is)."""
        path = [{"kind": "object_key", "key": key}] if key else []
        return self._redact_obj_at_path(obj, path)

    def _redact_obj_at_path(self, obj: Any, path: list[dict[str, Any]]) -> Any:
        if isinstance(obj, str):
            if self._is_known_placeholder(obj):
                return obj
            structured, changed = self._redact_structured_json_text_if_needed(obj)
            if changed:
                return structured
            redacted = self.redact_text(obj)
            if _path_local_sensitive_match(path) and redacted == obj and obj:
                return "[REDACTED]"
            return redacted
        if isinstance(obj, dict):
            name = obj.get("name")
            sensitive_name = (
                name
                if isinstance(name, str) and "value" in obj and _is_sensitive_key(name)
                else None
            )
            return {
                item_key: self._redact_obj_at_path(
                    item_value,
                    [
                        *path,
                        {
                            "kind": "object_key",
                            "key": (
                                sensitive_name
                                if sensitive_name is not None and item_key == "value"
                                else str(item_key)
                            ),
                        },
                    ],
                )
                for item_key, item_value in obj.items()
            }
        if isinstance(obj, list):
            return [
                self._redact_obj_at_path(
                    item,
                    [*path, {"kind": "array_index", "index": index}],
                )
                for index, item in enumerate(obj)
            ]
        if obj is not None:
            global_placeholder = self._placeholders.get(str(obj))
            if global_placeholder is not None:
                return global_placeholder
            match = _path_local_sensitive_match(path)
            if match is not None:
                identity = self._register_typed_local(obj, match)
                return self._typed_local_placeholders[identity]
        return obj

    def redact_json_value(self, value: Any) -> tuple[Any, list[dict[str, Any]]]:
        """Redact a parsed JSON tree and return typed, non-secret node descriptors."""

        # Collect all classification bases before emitting any descriptor so
        # repeated typed identities get a complete, deterministic basis list.
        self.register_from_obj(value)
        descriptors: list[dict[str, Any]] = []

        def visit(current: Any, path: list[dict[str, Any]]) -> Any:
            if isinstance(current, dict):
                return {
                    key: visit(child, [*path, {"kind": "object_key", "key": key}])
                    for key, child in current.items()
                }
            if isinstance(current, list):
                return [
                    visit(child, [*path, {"kind": "array_index", "index": index}])
                    for index, child in enumerate(current)
                ]
            if current is None:
                return None

            original_type = _json_scalar_type(current)
            local_identity = None
            if isinstance(current, str):
                redacted, placeholders = self._redact_string(current)
                if not placeholders:
                    match = _path_local_sensitive_match(path)
                    if match is None or not _is_json_literal_string(current):
                        return current
                    local_identity = self._register_typed_local(current, match)
                    redacted = self._typed_local_placeholders[local_identity]
                    placeholders = [redacted]
                    form = "whole_scalar"
                else:
                    form = (
                        "whole_scalar"
                        if len(placeholders) == 1 and redacted == placeholders[0]
                        else "string_substitution"
                    )
            else:
                secret = str(current)
                placeholder = self._placeholders.get(secret)
                if placeholder is None:
                    match = _path_local_sensitive_match(path)
                    if match is None:
                        return current
                    local_identity = self._register_typed_local(current, match)
                    placeholder = self._typed_local_placeholders[local_identity]
                redacted = placeholder
                placeholders = [placeholder]
                form = "whole_scalar"

            descriptors.append(
                {
                    "path": path,
                    "original_scalar_type": original_type,
                    "redaction_form": form,
                    "placeholders": [
                        {
                            "placeholder_sha256": hashlib.sha256(
                                placeholder.encode()
                            ).hexdigest(),
                            "classification_bases": (
                                self._typed_local_bases(local_identity)
                                if local_identity is not None
                                else self._bases_for_placeholder(placeholder)
                            ),
                        }
                        for placeholder in placeholders
                    ],
                    "runtime_material_required": True,
                }
            )
            return redacted

        return visit(value, []), descriptors

    def _redact_string(self, text: str) -> tuple[str, list[str]]:
        redacted = self.redact_text(text)
        placeholders = []
        for placeholder in self._placeholders.values():
            if placeholder in redacted and placeholder not in placeholders:
                placeholders.append(placeholder)
        return redacted, placeholders

    def _bases_for_placeholder(self, placeholder: str) -> list[dict[str, str]]:
        secrets = [
            value for value, candidate in self._placeholders.items() if candidate == placeholder
        ]
        if len(secrets) != 1:
            raise ValueError("secret placeholder collision prevents typed redaction")
        bases = self._classification_bases.get(secrets[0], set())
        if not bases:
            raise ValueError("redacted secret has no classification basis")
        ordered = sorted(
            bases,
            key=lambda item: (
                _SOURCE_ORDER[item.source_class],
                _MATCH_ORDER[item.sensitive_key_match],
            ),
        )
        return [item.as_dict() for item in ordered]

    def _register_typed_local(
        self, value: Any, sensitive_key_match: str
    ) -> tuple[str, str]:
        if (
            sensitive_key_match not in _MATCH_ORDER
            or sensitive_key_match == "not_applicable"
        ):
            raise ValueError("typed local secret requires a sensitive-key classification")
        identity = _typed_local_identity(value)
        if identity not in self._typed_local_placeholders:
            scalar_type, canonical = identity
            digest = hashlib.sha256(
                (
                    self._salt
                    + _LOCAL_TYPED_DOMAIN_SEPARATOR
                    + scalar_type
                    + "\x00"
                    + canonical
                ).encode()
            ).hexdigest()[:8]
            self._typed_local_placeholders[identity] = f"[REDACTED:{digest}]"
        self._typed_local_classification_bases.setdefault(identity, set()).add(
            ClassificationBasis("sensitive_key", sensitive_key_match)
        )
        return identity

    def _typed_local_bases(
        self, identity: tuple[str, str] | None
    ) -> list[dict[str, str]]:
        if identity is None:
            raise ValueError("typed local descriptor is missing its identity")
        bases = self._typed_local_classification_bases.get(identity, set())
        if not bases:
            raise ValueError("typed local redaction has no classification basis")
        ordered = sorted(
            bases,
            key=lambda item: (
                _SOURCE_ORDER[item.source_class],
                _MATCH_ORDER[item.sensitive_key_match],
            ),
        )
        return [item.as_dict() for item in ordered]

    def _register_sensitive_value(
        self,
        value: Any,
        *,
        key: str = "",
        path: list[dict[str, Any]] | None = None,
    ) -> None:
        path = path or ([{"kind": "object_key", "key": key}] if key else [])
        if isinstance(value, dict):
            self._register_from_obj_at_path(value, path)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._register_sensitive_value(
                    item,
                    key=key,
                    path=[*path, {"kind": "array_index", "index": index}],
                )
            return
        if value is None:
            return
        if not isinstance(value, str):
            match = _path_local_sensitive_match(path) or _classify_sensitive_key(key)
            if match is None:
                raise ValueError("typed local secret has no sensitive-key owner")
            self._register_typed_local(value, match)
            return
        text = str(value)
        if not text:
            return
        if self._is_known_placeholder(text):
            return
        if _is_json_literal_string(text):
            return
        for token in _JWT.findall(text):
            self.register(token, source_class="jwt")
        if "authorization" in key.lower():
            match = _AUTH_HEADER.match(text)
            if match:
                self.register(match.group(2), source_class="authorization")
                return
        if "cookie" in key.lower():
            for part in text.split(";"):
                if "=" in part:
                    _name, cookie_value = part.split("=", 1)
                    self.register(cookie_value.strip(), source_class="cookie")
            self.register(text, source_class="cookie")
            return
        match = _classify_sensitive_key(key)
        self.register(
            text,
            source_class="sensitive_key",
            sensitive_key_match=match or "substring_only",
        )

    def _is_known_placeholder(self, text: str) -> bool:
        return (
            _REDACTION_MARKER.fullmatch(text) is not None
            or text in self._placeholders.values()
            or text in self._typed_local_placeholders.values()
        )

    def _redact_structured_json_text_if_needed(self, text: str) -> tuple[str, bool]:
        trimmed = text.strip()
        if not trimmed or trimmed[:1] not in ("{", "["):
            return text, False
        try:
            parsed = json.loads(trimmed)
        except (json.JSONDecodeError, TypeError):
            return text, False
        if not isinstance(parsed, (dict, list)):
            return text, False
        redacted, descriptors = self.redact_json_value(parsed)
        if not descriptors:
            return text, False
        return (
            json.dumps(redacted, ensure_ascii=False, separators=(",", ":")),
            True,
        )

    def _register_structured_text(self, text: str) -> None:
        trimmed = text.strip()
        if not trimmed:
            return
        if trimmed[:1] in ("{", "["):
            try:
                self.register_from_obj(json.loads(trimmed))
                return
            except Exception:
                pass
        if "=" in trimmed:
            try:
                pairs = parse_qsl(trimmed, keep_blank_values=True)
            except Exception:
                pairs = []
            for name, value in pairs:
                if _is_sensitive_key(name):
                    self._register_sensitive_value(value, key=name)


def _is_sensitive_key(key: str) -> bool:
    return _classify_sensitive_key(key) is not None


def _classify_sensitive_key(key: str) -> str | None:
    folded = key.lower().replace("_", "-")
    classifications = []
    for raw_part in _SENSITIVE_KEY_PARTS:
        part = raw_part.lower()
        start = 0
        while True:
            index = folded.find(part, start)
            if index < 0:
                break
            end = index + len(part)
            if index == 0 and end == len(folded):
                classifications.append("exact_token")
            elif (index == 0 or folded[index - 1] == "-") and (
                end == len(folded) or folded[end] == "-"
            ):
                classifications.append("separator_delimited_token")
            else:
                classifications.append("substring_only")
            start = index + 1
    if not classifications:
        return None
    return min(classifications, key=lambda item: _MATCH_ORDER[item])


def _json_scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    raise TypeError("typed JSON redaction supports scalar values only")


def _typed_local_identity(value: Any) -> tuple[str, str]:
    scalar_type = _json_scalar_type(value)
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return scalar_type, canonical


def _is_json_literal_string(value: str) -> bool:
    return value.casefold() in _JSON_LITERAL_STRINGS


def _path_local_sensitive_match(path: list[dict[str, Any]]) -> str | None:
    object_index = None
    for index in range(len(path) - 1, -1, -1):
        if path[index]["kind"] == "object_key":
            object_index = index
            break
    if object_index is None:
        return None
    if any(segment["kind"] != "array_index" for segment in path[object_index + 1 :]):
        return None
    return _classify_sensitive_key(str(path[object_index]["key"]))


def _secret_representations(value: str) -> tuple[str, ...]:
    """Return deterministic wire encodings that may carry a registered secret."""

    representations = {
        value,
        quote(value, safe=""),
        quote_plus(value, safe=""),
    }
    # Percent escapes are case-insensitive on the wire. Preserve literal text
    # case while accepting either hex spelling emitted by clients.
    representations.update(_lower_percent_escapes(item) for item in tuple(representations))
    return tuple(sorted(representations, key=len, reverse=True))


def _lower_percent_escapes(value: str) -> str:
    return re.sub(r"%[0-9A-Fa-f]{2}", lambda match: match.group(0).lower(), value)
