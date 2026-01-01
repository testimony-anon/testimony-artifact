"""Stage 6 write replay safety adapters.

The implementation below is the legacy Conduit adapter used by the original
Stage 6 live acceptance path: reset → seed articles → replay → cleanup → verify
GET 404. Multi-system V2 smokes use profile-driven reset/replay paths instead
of this adapter. `SafetyShell` remains as a compatibility alias for existing
011/012/Stage6 tests and callers.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from common.contracts import REPO_ROOT

from .config import ReplayConfig
from .http_client import Throttle, business_success, send

RESET_SCRIPT = REPO_ROOT / "deploy" / "conduit" / "reset.sh"


class CleanupFailedError(Exception):
    """Post-delete verification failed during cleanup → circuit breaker (D48/S3)."""


@dataclass
class LegacyConduitSafetyShell:
    """Conduit-specific application safety adapter kept for legacy Stage6 live runs."""

    cfg: ReplayConfig
    throttle: Throttle = field(default_factory=Throttle)
    reset_cmd: list = field(default_factory=lambda: ["bash", str(RESET_SCRIPT)])

    # ---- environment level ----

    def reset(self) -> None:
        """Reset legacy Conduit to baseline (account present, no articles)."""
        env_note = subprocess.run(self.reset_cmd, capture_output=True, text=True, timeout=120)
        if env_note.returncode != 0:
            raise RuntimeError(f"reset.sh failed: {env_note.stderr[-300:]}")

    # ---- application level ----

    def login(self) -> str:
        self.throttle.wait()
        res = send("POST", self.cfg.base_url + "/api/users/login",
                   body_text=json.dumps({"user": {"email": self.cfg.email,
                                                   "password": self.cfg.password}}))
        if not business_success(res):
            raise RuntimeError(f"login failed: {res.status}")
        return res.json()["user"]["token"]

    def seed_article(self, token: str, title: str | None = None) -> str:
        """Seed one tagged article so that list/tags are non-empty (M1); returns the slug."""
        self.throttle.wait()
        body = {"article": {"title": title or self.cfg.seed_title, "description": "seed",
                            "body": "seed body", "tagList": [self.cfg.seed_tag]}}
        res = send("POST", self.cfg.base_url + "/api/articles",
                   headers={"Authorization": f"{self.cfg.token_scheme} {token}"},
                   body_text=json.dumps(body))
        if not business_success(res):
            raise RuntimeError(f"seeding article failed: {res.status} {res.body_text}")
        return res.json()["article"]["slug"]

    def seed_articles(self, token: str, n: int) -> list[str]:
        """Seed n distinct articles sharing one tag (decision record 010, D62: make the list size >= n and tags non-empty),
        supporting $.articles[N] bindings (N+1 articles). Returns the slugs (in creation order)."""
        # the first article keeps the bare cfg.seed_title (literal equivalence with the V1 single seed: first article of seed_articles(_,1) == seed_article(_));
        # the rest get a sequence number. Titles are pairwise distinct ("Carver Seed" / "Carver Seed 2" / ...) → slugs are pairwise distinct.
        return [self.seed_article(token, title=(self.cfg.seed_title if i == 0 else f"{self.cfg.seed_title} {i + 1}"))
                for i in range(n)]

    def cleanup_articles(self, token: str, slugs: list[str]) -> list[dict]:
        """Delete the articles and verify GET 404 afterwards (D28a/D48). Any residue → raise CleanupFailedError (S3 circuit breaker)."""
        log = []
        auth = {"Authorization": f"{self.cfg.token_scheme} {token}"}
        for slug in dict.fromkeys(slugs):  # deduplicate, preserving order
            url = f"{self.cfg.base_url}/api/articles/{slug}"
            self.throttle.wait()
            d = send("DELETE", url, headers=auth)
            self.throttle.wait()
            v = send("GET", url, headers=auth)
            ok = (200 <= d.status < 300 or d.status == 404) and v.status == 404
            log.append({"slug": slug, "delete_status": d.status, "verify_get": v.status, "ok": ok})
            if not ok:
                raise CleanupFailedError(
                    f"cleanup left residue slug={slug}: DELETE={d.status} verifyGET={v.status} (expected GET 404)")
        return log

    def verify_baseline_clean(self, token: str, slug: str) -> bool:
        """Verify the baseline: the given slug must not exist (GET 404)."""
        self.throttle.wait()
        v = send("GET", f"{self.cfg.base_url}/api/articles/{slug}",
                 headers={"Authorization": f"{self.cfg.token_scheme} {token}"})
        return v.status == 404


SafetyShell = LegacyConduitSafetyShell
