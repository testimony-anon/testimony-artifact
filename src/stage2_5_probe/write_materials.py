"""Write-side scheduled discovery material classification and mutation.

The helpers here keep Stage 2.5 write-probe material decisions in one place:
recorded request bodies may provide structure, but safe scalar leaves are
converted into deterministic generated test values before being sent.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any


FRESH_REPLAY = "fresh_replay"
RUNTIME_SECRET = "runtime_secret"
STABLE_LITERAL_VERIFIED = "stable_literal_verified"
RECORDED_LITERAL_ASSUMPTION = "recorded_literal_assumption"
GENERATED_MUTATION = "generated_mutation"
MIXED = "mixed"
INSUFFICIENT = "insufficient"
NOT_APPLICABLE = "not_applicable"

_REDACTED_RE = re.compile(r"^\[REDACTED:[^\]]+\]$")
_SENSITIVE_PARTS = (
    "auth",
    "authorization",
    "cookie",
    "credential",
    "jwt",
    "passwd",
    "password",
    "secret",
    "set-cookie",
    "token",
)


@dataclass
class WriteBodyMaterial:
    body_text: str
    generated_fields: list[str] = field(default_factory=list)
    stable_literal_fields: list[str] = field(default_factory=list)
    insufficient_fields: list[str] = field(default_factory=list)
    value_basis: str = GENERATED_MUTATION


def mutate_recorded_body_template(body_text: str, seed: str) -> WriteBodyMaterial | None:
    """Return a deterministic write body derived from a recorded JSON body.

    Redacted placeholders are preserved for the runtime secret resolver.  Safe
    scalar leaves are replaced/toggled so old business literals are not silently
    reused.  If a non-redacted sensitive scalar appears, it is converted to a
    redacted placeholder so the runner must resolve it from runtime config or
    mark the material insufficient.
    """
    parsed = _parse_json_text(body_text)
    if parsed is None:
        return None
    suffix = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    generated_fields: list[str] = []
    stable_fields: list[str] = []
    insufficient_fields: list[str] = []
    mutated = _mutate_value(
        deepcopy(parsed),
        suffix,
        path="$",
        key_hint="value",
        generated_fields=generated_fields,
        stable_fields=stable_fields,
        insufficient_fields=insufficient_fields,
    )
    value_basis = GENERATED_MUTATION if generated_fields else STABLE_LITERAL_VERIFIED
    if insufficient_fields and not generated_fields:
        value_basis = INSUFFICIENT
    return WriteBodyMaterial(
        body_text=json.dumps(mutated, ensure_ascii=False),
        generated_fields=sorted(set(generated_fields)),
        stable_literal_fields=sorted(set(stable_fields)),
        insufficient_fields=sorted(set(insufficient_fields)),
        value_basis=value_basis,
    )


def classify_probe_material(
    *,
    has_fresh: bool,
    has_runtime_secret: bool,
    has_literal_assumption: bool,
    has_template: bool,
    template_value_basis: str | None = None,
) -> str:
    """Classify executed probe request material using the shared vocabulary."""
    if has_literal_assumption:
        if has_fresh or has_runtime_secret or template_value_basis in {GENERATED_MUTATION, STABLE_LITERAL_VERIFIED}:
            return MIXED
        return RECORDED_LITERAL_ASSUMPTION
    sources = []
    if has_fresh:
        sources.append(FRESH_REPLAY)
    if has_runtime_secret:
        sources.append(RUNTIME_SECRET)
    if template_value_basis in {GENERATED_MUTATION, STABLE_LITERAL_VERIFIED}:
        sources.append(template_value_basis)
    elif has_template and not (has_fresh or has_runtime_secret):
        sources.append(RECORDED_LITERAL_ASSUMPTION)
    if not sources:
        return NOT_APPLICABLE
    unique = set(sources)
    return sources[0] if len(unique) == 1 else MIXED


def literal_assumption(location: str, field: str, reason: str = "recorded_literal_assumption") -> dict:
    return {"location": location, "field": field, "reason": reason}


def _parse_json_text(text: str | None) -> Any | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _mutate_value(
    value: Any,
    suffix: str,
    *,
    path: str,
    key_hint: str,
    generated_fields: list[str],
    stable_fields: list[str],
    insufficient_fields: list[str],
) -> Any:
    if isinstance(value, dict):
        return {
            key: _mutate_value(
                child,
                suffix,
                path=_child_path(path, str(key)),
                key_hint=str(key),
                generated_fields=generated_fields,
                stable_fields=stable_fields,
                insufficient_fields=insufficient_fields,
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _mutate_value(
                child,
                suffix,
                path=f"{path}[{index}]",
                key_hint=key_hint,
                generated_fields=generated_fields,
                stable_fields=stable_fields,
                insufficient_fields=insufficient_fields,
            )
            for index, child in enumerate(value)
        ]
    if isinstance(value, str):
        if _REDACTED_RE.fullmatch(value):
            insufficient_fields.append(path)
            return value
        if _sensitive_field(key_hint):
            insufficient_fields.append(path)
            return "[REDACTED:scheduled_discovery]"
        if _id_like_field(key_hint):
            stable_fields.append(path)
            return value
        generated_fields.append(path)
        return _generated_string(key_hint, value, suffix)
    if isinstance(value, bool):
        generated_fields.append(path)
        return not value
    if isinstance(value, int) and not isinstance(value, bool):
        if _id_like_field(key_hint):
            stable_fields.append(path)
            return value
        generated_fields.append(path)
        return _generated_int(key_hint, suffix)
    if isinstance(value, float):
        generated_fields.append(path)
        return round(float(_generated_int(key_hint, suffix)) + 0.25, 2)
    if value is None:
        stable_fields.append(path)
        return None
    stable_fields.append(path)
    return deepcopy(value)


def _generated_string(key_hint: str, old_value: str, suffix: str) -> str:
    key = key_hint.lower()
    compact = suffix[:6]
    if "email" in key:
        return f"carver-{compact}@example.test"
    if key.endswith("url") or "url" in key or key in {"href", "link", "uri"}:
        return f"https://example.test/cf-{compact}"
    if "date" in key or key in {"checkin", "checkout", "start", "end"}:
        base = date(2028, 1, 1) + timedelta(days=int(suffix[:2], 16) % 28)
        return base.isoformat()
    if "time" in key:
        base = datetime(2028, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(
            minutes=int(suffix[:2], 16) % 60
        )
        return base.isoformat().replace("+00:00", "Z")
    if key in {"slug", "code", "key"}:
        return f"cf-{compact}"
    if old_value and len(old_value) <= 24:
        return f"{old_value[: max(1, 24 - len(compact) - 4)]} cf-{compact}"
    return f"cf-{_clean_token(key_hint)}-{compact}"


def _generated_int(key_hint: str, suffix: str) -> int:
    key = key_hint.lower()
    if "price" in key or "amount" in key:
        return 1
    return 1 + (int(suffix[:2], 16) % 9)


def _sensitive_field(key_hint: str) -> bool:
    normalized = key_hint.lower().replace("_", "-")
    return any(part in normalized for part in _SENSITIVE_PARTS)


def _id_like_field(key_hint: str) -> bool:
    key = key_hint.lower()
    return key in {"id", "uuid"} or key.endswith("_id") or key.endswith("id")


def _clean_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return token or "value"


def _child_path(path: str, key: str) -> str:
    return f"$.{key}" if path == "$" else f"{path}.{key}"
