"""Probe planning (004 D27 endpoint level + 004A rulings 1/2/4).

For every recovered canonical template, plan probes for the methods not observed from the UI:
- safe methods GET/HEAD/OPTIONS: one request per observed concrete URL;
- write methods POST/PUT/DELETE/PATCH: only when the template is a "write endpoint" (some write method was observed);
  POST/PUT/PATCH reuse the observed write body of that path (DELETE carries no body by convention);
  a reused body containing an irreversible redaction placeholder (login only) → downgrade to no body (ruling 4).

Planning only, no requests are sent (fully deterministic). Concrete URLs and bodies are real literal values taken
from the session bundle HAR entries via the observations' run_id+entry_index (D29/D20).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .loader import Stage25Inputs

SAFE_METHODS = ["GET", "HEAD", "OPTIONS"]
WRITE_METHODS = ["POST", "PUT", "DELETE", "PATCH"]
ALL_PROBE_METHODS = SAFE_METHODS + WRITE_METHODS  # deterministic order
BODY_REUSE_METHODS = {"POST", "PUT", "PATCH"}  # DELETE carries no body by convention (HTTP semantics + apicarver default branch)
REDACTED = re.compile(r"\[REDACTED:[0-9a-f]{8}\]")


@dataclass
class ProbeTarget:
    method: str
    canonical_path: str
    concrete_url: str  # scheme+host+pathname (no query, no trailing slash)
    reused_request_ref: str | None = None  # "run_id#entry_index"
    reused_body: str | None = None  # body text actually reused (confirmed free of placeholders)
    body_skipped_irreversible: bool = False  # ruling 4: reuse was intended but the body contains an irreversible placeholder
    anchor_sequence: list[str] = field(default_factory=list)


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def plan_probes(inp: Stage25Inputs) -> list[ProbeTarget]:
    targets: list[ProbeTarget] = []
    for canonical_path in sorted(inp.paths):
        info = inp.paths[canonical_path]
        observed = info.observed_methods
        is_write_endpoint = bool(observed & set(WRITE_METHODS))
        concrete_urls = sorted({_normalize_url(u) for u in info.concrete_urls})
        reuse_ref, reuse_body = info.reusable_write_body  # (ref, body_text) or (None, None)
        body_has_placeholder = bool(reuse_body and REDACTED.search(reuse_body))

        for method in ALL_PROBE_METHODS:
            if method in observed:
                continue  # already observed, nothing to complete
            if method in WRITE_METHODS and not is_write_endpoint:
                continue  # conservative red line: no write probes against read-only endpoints
            for url in concrete_urls:
                target = ProbeTarget(
                    method=method, canonical_path=canonical_path, concrete_url=url
                )
                if method in BODY_REUSE_METHODS and is_write_endpoint and reuse_ref:
                    target.reused_request_ref = reuse_ref
                    if body_has_placeholder:
                        target.body_skipped_irreversible = True  # ruling 4: downgrade to no body
                    else:
                        target.reused_body = reuse_body
                targets.append(target)
    return targets
