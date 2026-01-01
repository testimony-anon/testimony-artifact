"""Replay configuration (D47: external inputs take test values from the config; not ground truth but operator-provided test data).

Credentials come from environment variables (same source as run_config.credentials_ref, D12); the other external inputs are
deterministic test constants (keeps the D52 verdicts deterministic). A plain ReplayConfig no longer carries any system-specific
business default material; the legacy Conduit acceptance run enables the old defaults explicitly via ReplayConfig.from_env().
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

TOKEN_SCHEME = "Token"  # default Authorization scheme; a profile-derived config may override it.

# External-input test values for the legacy Conduit acceptance run (indexed by to_location/to_field).
_PARAM_VALUES: dict[tuple[str, str], object] = {
    ("query", "limit"): "20",
    ("query", "offset"): "0",
    ("body", "$.article.title"): "Carver Seed",
    ("body", "$.article.description"): "Seed description",
    ("body", "$.article.body"): "Seed body text.",
    ("body", "$.article.tagList"): ["carvertag"],
    ("body", "$.comment.body"): "Seed comment body.",
}


@dataclass
class ReplayConfig:
    base_url: str
    email: str
    password: str
    token_scheme: str = TOKEN_SCHEME
    auth_token: str | None = None
    session_cookie_header: str | None = None
    session_cookie_name: str | None = None
    trust_basis: str = "per_probe_cleanup"
    seed_title: str = "Carver Seed"      # -> slug "carver-seed" (deterministic)
    seed_tag: str = "carvertag"
    seed_slug: str = "carver-seed"
    param_values: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, base_url: str) -> "ReplayConfig":
        """Build the legacy Conduit replay config from CONDUIT_TEST_* env vars."""
        return cls(
            base_url=base_url.rstrip("/"),
            email=os.environ.get("CONDUIT_TEST_EMAIL", "carver@carverflow.local"),
            password=os.environ.get("CONDUIT_TEST_PASSWORD", "carverflow-test-pw"),
            param_values=dict(_PARAM_VALUES),
        )

    def value_for(self, to_location: str, to_field: str) -> object | None:
        """Resolve an external input: credentials come from email/password, everything else from the test-constant table."""
        if to_location == "body" and to_field == "$.user.email":
            return self.email
        if to_location == "body" and to_field == "$.user.password":
            return self.password
        return self.param_values.get((to_location, to_field))
