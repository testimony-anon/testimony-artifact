"""Evidence-backed unit scaling derived from repeated trace observations."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


CURRENCY_TOKEN = re.compile(r"[$€£¥]\s*([+-]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)")
CANONICAL_DECIMAL = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
ABSOLUTE_TOLERANCE = Decimal("1e-9")
RELATIVE_TOLERANCE = Decimal("1e-9")


@dataclass(frozen=True)
class ScalePair:
    ui_text: str
    ui_observation_ref: dict[str, Any]
    api_value: int | float | str
    api_observation_ref: dict[str, Any]


def derive_unit_scale(
    pairs: Iterable[ScalePair],
    *,
    evidence_id: str,
    quantity_key: str,
    derived_at: str | None = None,
) -> dict[str, Any]:
    """Derive a positive integer factor; one usable pair remains review-only."""
    records = []
    for pair in pairs:
        ui_value = parse_currency_decimal(pair.ui_text)
        api_value = parse_api_decimal(pair.api_value)
        if ui_value == 0:
            raise ValueError("unit_scale UI value must be non-zero")
        ratio = api_value / ui_value
        records.append(
            {
                "ui_observation_ref": pair.ui_observation_ref,
                "api_observation_ref": pair.api_observation_ref,
                "ui_text_sha256": hashlib.sha256(pair.ui_text.encode()).hexdigest(),
                "parsed_ui_value": _json_number(ui_value),
                "api_value": _json_number(api_value),
                "ratio": _json_number(ratio),
            }
        )
    if not records:
        raise ValueError("unit_scale requires at least one observation pair")

    candidate = int(Decimal(str(records[0]["ratio"])).to_integral_value())
    ratios_match = candidate >= 1 and all(_close_to_factor(Decimal(str(item["ratio"])), candidate) for item in records)
    distinct = len({Decimal(str(item["parsed_ui_value"])) for item in records}) >= 2
    if ratios_match and len(records) >= 2 and distinct:
        status, factor = "confirmed", candidate
    elif ratios_match:
        status, factor = "review_required", candidate
    else:
        status, factor = "rejected", None
    return {
        "evidence_id": evidence_id,
        "quantity_key": quantity_key,
        "derivation_status": status,
        "factor": factor,
        "pairs": records,
        "parser": "currency_decimal_v1",
        "absolute_tolerance": float(ABSOLUTE_TOLERANCE),
        "relative_tolerance": float(RELATIVE_TOLERANCE),
        "derived_at": derived_at or datetime.now(timezone.utc).isoformat(),
    }


def parse_currency_decimal(text: str) -> Decimal:
    hits = CURRENCY_TOKEN.findall(unicodedata.normalize("NFKC", text))
    if len(hits) != 1:
        raise ValueError("currency_decimal_v1 requires exactly one currency token")
    try:
        return Decimal(hits[0].replace(",", ""))
    except InvalidOperation as error:  # pragma: no cover
        raise ValueError("invalid UI decimal") from error


def parse_api_decimal(value: int | float | str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not an API numeric value")
    raw = str(value)
    if not CANONICAL_DECIMAL.fullmatch(raw):
        raise ValueError("API value is not a canonical decimal")
    return Decimal(raw)


def confirmed_scale_evidence(evidence: Any, *, factor: int, evidence_ref: str) -> bool:
    return (
        isinstance(evidence, dict)
        and evidence.get("evidence_id") == evidence_ref
        and evidence.get("derivation_status") == "confirmed"
        and evidence.get("factor") == factor
        and len(evidence.get("pairs") or []) >= 2
        and len({item.get("parsed_ui_value") for item in evidence.get("pairs") or []}) >= 2
    )


def _close_to_factor(ratio: Decimal, factor: int) -> bool:
    delta = abs(ratio - Decimal(factor))
    return delta <= ABSOLUTE_TOLERANCE or delta / max(abs(Decimal(factor)), Decimal(1)) <= RELATIVE_TOLERANCE


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)
