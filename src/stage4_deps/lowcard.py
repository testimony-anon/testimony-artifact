"""Low-cardinality exclusion (005 D39, first paragraph: zero-threshold hard rule at the type/degenerate level).

Low-cardinality values are not used as value-flow evidence -- this keeps status/boolean/pagination offset=0 style values
from flooding the graph with spurious edges. The second paragraph (frequency/spread) only feeds the confidence downgrade
(see the query-position cap in valueflow.py), not the hard exclusion.
"""

from __future__ import annotations

import re

_INT_STRING = re.compile(r"^-?\d+$")
# Alphabetic enum words (not treated as identifiers even when length >= 4); follows apicarver's "alphabetic enums are not ids" rule
ENUM_KEYWORDS = {
    "true", "false", "null", "none", "published", "draft",
    "public", "private", "active", "inactive",
}


def is_low_card(value) -> bool:
    """Low-cardinality test (a hit means the value is not used as value-flow evidence). Accepts only JSON scalar leaf values."""
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True  # numeric scalars (followersCount/favoritesCount/id=1, etc.)
    if isinstance(value, str):
        s = value.strip()
        if len(s) <= 2:
            return True
        if _INT_STRING.match(s):
            return True  # integer strings (query offset=0/limit=3)
        if s.lower() in ENUM_KEYWORDS:
            return True
        return False
    return True  # other non-scalar types are not treated as leaf values
