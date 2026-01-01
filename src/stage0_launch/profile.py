"""app_profile loading and validation (001 §3.1: stop on any invalid input and report the specific field).

The pydantic models correspond one-to-one to contracts/app_profile.schema.json (contract rule).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Annotated

from common.contracts import ContractValidationError, validate_artifact

from .errors import ProfileError

HTTP_METHODS = Literal["GET", "PUT", "POST", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]


class CredentialsRef(BaseModel):
    """Environment-variable name references for credentials: only the variable names are stored, never the credentials themselves (D10/D12)."""

    model_config = ConfigDict(extra="forbid")
    email_env: str = Field(min_length=1)
    password_env: str = Field(min_length=1)


class ProbeEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: HTTP_METHODS
    path: str = Field(pattern=r"^/")
    expect_status: int = Field(default=200, ge=100, le=599)
    unauthenticated_status: Optional[int] = Field(default=None, ge=100, le=599)
    expect_json_path: Optional[str] = Field(default=None, pattern=r"^\$")
    expect_json_equals: Optional[Any] = None

    @model_validator(mode="after")
    def json_equality_requires_path(self) -> "ProbeEndpoint":
        if "expect_json_equals" in self.model_fields_set and self.expect_json_path is None:
            raise ValueError("expect_json_equals requires expect_json_path")
        return self


DEFAULT_LOGIN_USERNAME_SELECTOR = 'input[name="email"]'
DEFAULT_LOGIN_PASSWORD_SELECTOR = 'input[name="password"]'
DEFAULT_LOGIN_SUBMIT_SELECTOR = "form button"


class LoginFormSelectors(BaseModel):
    """Login-page selectors for recorded browser_form activation.

    Every default reproduces the legacy hard-coded Conduit shape, so a profile that
    omits a selector keeps the behaviour it had before this field existed.
    """

    model_config = ConfigDict(extra="forbid")
    username: str = Field(default=DEFAULT_LOGIN_USERNAME_SELECTOR, min_length=1)
    password: str = Field(default=DEFAULT_LOGIN_PASSWORD_SELECTOR, min_length=1)
    submit: str = Field(default=DEFAULT_LOGIN_SUBMIT_SELECTOR, min_length=1)
    ready: Optional[str] = Field(default=None, min_length=1)
    timeout_ms: int = Field(default=30_000, ge=1, le=120_000)


class BrowserTokenActivation(BaseModel):
    """Where an obtained API token is installed in the recorded browser context."""

    model_config = ConfigDict(extra="forbid")
    storage: Literal["local_storage", "session_storage", "cookie"]
    key: str = Field(min_length=1)
    value_template: str = Field(min_length=1)
    entry_url: Optional[str] = None
    cookie_path: Optional[str] = None
    timeout_ms: int = Field(default=30_000, ge=1, le=120_000)


class ApiTokenLogin(BaseModel):
    """Configuration for the Stage2.5 tool-issued API token login; real credentials are injected only through placeholders."""

    model_config = ConfigDict(extra="forbid")
    method: HTTP_METHODS
    path: str = Field(pattern=r"^/")
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: Any
    token_json_path: str = Field(pattern=r"^\$")
    recording_activation: Optional[Literal["browser_form", "api_then_inject"]] = None
    selectors: Optional[LoginFormSelectors] = None
    browser_activation: Optional[BrowserTokenActivation] = None

    @model_validator(mode="after")
    def _validate_recording_activation(self) -> "ApiTokenLogin":
        if (
            self.recording_activation == "api_then_inject"
            and self.browser_activation is None
        ):
            raise ValueError(
                "api_token.recording_activation=api_then_inject requires browser_activation"
            )
        return self


class BrowserFormActivation(BaseModel):
    """Profile-managed browser activation after API session creation."""

    model_config = ConfigDict(extra="forbid")
    entry_url: str = Field(min_length=1)
    username_selector: str = Field(min_length=1)
    password_selector: str = Field(min_length=1)
    submit_selector: str = Field(min_length=1)
    ready_selector: str = Field(min_length=1)
    timeout_ms: int = Field(default=30_000, ge=1, le=120_000)


class CsrfDoubleSubmit(BaseModel):
    """Dynamic CSRF double-submit: the login request echoes a cookie value in a header."""

    model_config = ConfigDict(extra="forbid")
    cookie_name: str = Field(min_length=1)
    header_name: str = Field(min_length=1)


class CookieSessionLogin(BaseModel):
    """Configuration for the Stage2.5 tool-issued cookie session login; cookie values are used in memory only."""

    model_config = ConfigDict(extra="forbid")
    method: HTTP_METHODS
    path: str = Field(pattern=r"^/")
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: Any
    cookie_name: Optional[str] = Field(default=None, min_length=1)
    cookie_path: Optional[str] = None
    cookie_domain: Optional[str] = None
    browser_activation: Optional[BrowserFormActivation] = None
    csrf: Optional[CsrfDoubleSubmit] = None


class FreshSessionBasis(BaseModel):
    """Frozen, auditable basis for a scoped session-material-only declaration."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "official_documentation",
        "official_ui_test",
        "preregistered_equivalence_audit",
    ]
    locator: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim: Literal["session_material_only"]

    @model_validator(mode="after")
    def _validate_locator(self) -> "FreshSessionBasis":
        if (
            self.locator.startswith("/")
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", self.locator)
            or ".." in self.locator.split("/")
            or "\\" in self.locator
        ):
            raise ValueError("fresh_session_basis.locator must be a POSIX path relative to the repository root")
        return self


class ApiTokenResponseMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["api_token"]
    token_json_path: str = Field(pattern=r"^\$")


class CookieSessionResponseMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["cookie_session"]
    cookie_name: str = Field(min_length=1)


SessionResponseMaterial = Annotated[
    ApiTokenResponseMaterial | CookieSessionResponseMaterial,
    Field(discriminator="kind"),
]


class SessionMaintenanceEndpoint(BaseModel):
    """Exact actor-scoped policy for a credential-maintenance endpoint."""

    model_config = ConfigDict(extra="forbid")
    method: HTTP_METHODS
    path: str = Field(pattern=r"^/[^?#]*$")
    role: Literal["credential_refresh"]
    handling: Literal["fresh_session_satisfies", "execute_and_update_session"]
    material_kind: Literal["api_token", "cookie_session"]
    fresh_session_basis: Optional[FreshSessionBasis] = None
    response_material: Optional[SessionResponseMaterial] = None

    @model_validator(mode="after")
    def _validate_handling_shape(self) -> "SessionMaintenanceEndpoint":
        if self.handling == "fresh_session_satisfies":
            if self.fresh_session_basis is None or self.response_material is not None:
                raise ValueError(
                    "fresh_session_satisfies must declare fresh_session_basis and only fresh_session_basis"
                )
        elif self.response_material is None or self.fresh_session_basis is not None:
            raise ValueError(
                "execute_and_update_session must declare response_material and only response_material"
            )
        if (
            self.response_material is not None
            and self.response_material.kind != self.material_kind
        ):
            raise ValueError("response_material.kind must match material_kind")
        return self


class LogoutEndpoint(BaseModel):
    """Exact session-teardown endpoint; declared, never inferred from path wording."""

    model_config = ConfigDict(extra="forbid")
    method: HTTP_METHODS
    path: str = Field(pattern=r"^/[^?#]*$")


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["form_login", "api_token", "cookie_session", "none"]
    login_entry: Optional[str] = None
    credentials_ref: Optional[CredentialsRef] = None
    token_scheme: str = "Token"  # Authorization header scheme, injected per system via the profile (002 D19)
    probe_endpoint: Optional[ProbeEndpoint] = None
    logout_endpoint: Optional[LogoutEndpoint] = None
    api_token: Optional[ApiTokenLogin] = None
    cookie_session: Optional[CookieSessionLogin] = None
    session_maintenance: Optional[list[SessionMaintenanceEndpoint]] = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def _validate_by_method(self) -> "AuthConfig":
        if self.method == "form_login":
            missing = [
                name
                for name, value in (
                    ("login_entry", self.login_entry),
                    ("credentials_ref", self.credentials_ref),
                    ("probe_endpoint", self.probe_endpoint),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"form_login profile is missing fields: {', '.join(missing)}")
        elif self.method == "api_token":
            missing = [
                name
                for name, value in (
                    ("credentials_ref", self.credentials_ref),
                    ("api_token", self.api_token),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"api_token profile is missing fields: {', '.join(missing)}")
        elif self.method == "cookie_session":
            missing = [
                name
                for name, value in (
                    ("credentials_ref", self.credentials_ref),
                    ("cookie_session", self.cookie_session),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"cookie_session profile is missing fields: {', '.join(missing)}")
        elif self.method == "none":
            if (
                self.credentials_ref is not None
                or self.api_token is not None
                or self.cookie_session is not None
                or self.session_maintenance is not None
            ):
                raise ValueError(
                    "auth.method=none does not allow credentials_ref/api_token/cookie_session/session_maintenance"
                )
        if self.session_maintenance is not None:
            typed_configs = [
                ("api_token", self.api_token),
                ("cookie_session", self.cookie_session),
            ]
            declared = [(kind, value) for kind, value in typed_configs if value is not None]
            if self.method == "api_token":
                material_kind = "api_token"
                login_config = self.api_token
            elif self.method == "cookie_session":
                material_kind = "cookie_session"
                login_config = self.cookie_session
            elif self.method == "form_login" and len(declared) == 1:
                material_kind, login_config = declared[0]
            else:
                raise ValueError(
                    "a form_login that declares session_maintenance must have exactly one typed session backing"
                )
            if login_config is None:
                raise ValueError("session_maintenance lacks a typed session backing")
            seen: set[tuple[str, str]] = set()
            login_endpoint = (login_config.method, login_config.path)
            for endpoint in self.session_maintenance:
                key = (endpoint.method, endpoint.path)
                if key in seen:
                    raise ValueError("session_maintenance method/path composite keys must be unique")
                seen.add(key)
                if key == login_endpoint:
                    raise ValueError("session_maintenance must not be the same as the login endpoint")
                if endpoint.material_kind != material_kind:
                    raise ValueError(
                        "session_maintenance.material_kind must match the actor auth material"
                    )
        return self


class RetryOn429(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_retries: int = Field(default=0, ge=0)


class RateLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_concurrency: int = Field(ge=1)
    min_interval_ms: int = Field(ge=0)
    retry_on_429: Optional[RetryOn429] = None
    burst_bucket: Optional[dict] = None  # reserved; not consumed in V1
    per_host: Optional[dict] = None  # reserved; not consumed in V1


class ResetVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: HTTP_METHODS
    path: str = Field(pattern=r"^/")
    expect_status: int = Field(ge=100, le=599)
    expect_json_path: Optional[str] = Field(default=None, pattern=r"^\$")
    expect_json_equals: Optional[Any] = None

    @model_validator(mode="after")
    def json_equality_requires_path(self) -> "ResetVerifyRequest":
        if "expect_json_equals" in self.model_fields_set and self.expect_json_path is None:
            raise ValueError("expect_json_equals requires expect_json_path")
        return self


class ResetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: Optional[list[str]] = None
    script: Optional[str] = None
    verify_request: ResetVerifyRequest

    @model_validator(mode="after")
    def _one_reset_command(self) -> "ResetConfig":
        has_command = bool(self.command)
        has_script = bool(self.script)
        if has_command == has_script:
            raise ValueError("reset must configure exactly one of command or script")
        return self


class ActorConfig(BaseModel):
    """Additional actor authentication; the top-level auth remains `default`."""

    model_config = ConfigDict(extra="forbid")
    actor_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    auth: AuthConfig


class OfflineUrlRewrite(BaseModel):
    """Typed recording-only URL rewrite applied before offline reconstruction."""

    model_config = ConfigDict(extra="forbid")
    pattern: str
    replacement: str


class ReadSemanticEndpoint(BaseModel):
    """One exact method/path pair whose write-method requests carry read semantics.

    Some applications query through POST (a search or statistics endpoint whose
    body is the selector).  The profile declares such endpoints explicitly; the
    method never infers read semantics from path wording.  A declared request is
    not a mutation for UI-action anchoring, not a producer, and is read-like for
    the proposer, the binder and the runtime observer check.
    """

    model_config = ConfigDict(extra="forbid")
    method: HTTP_METHODS
    path: str = Field(pattern=r"^/[^?#]*$")


class AppProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str
    auth: AuthConfig
    reset: Optional[ResetConfig] = None
    rate_limit: RateLimit
    drive_mode: Literal["manual", "replay", "heuristic", "llm_agent", "random"]
    actors: list[ActorConfig] = Field(default_factory=list)
    offline_url_rewrite: Optional[OfflineUrlRewrite] = None
    read_semantic_endpoints: list[ReadSemanticEndpoint] = Field(default_factory=list)
    write_probe_safety: Optional[dict] = None  # reserved; not consumed in V1
    exploration_hints: Optional[dict] = None  # reserved; not consumed in V1

    @model_validator(mode="after")
    def _validate_actor_ids(self) -> "AppProfile":
        actor_ids = [actor.actor_id for actor in self.actors]
        if "default" in actor_ids:
            raise ValueError("actors must not declare default; the top-level auth already represents the default actor")
        duplicates = sorted({actor_id for actor_id in actor_ids if actor_ids.count(actor_id) > 1})
        if duplicates:
            raise ValueError(f"actors.actor_id must be unique; duplicate values: {', '.join(duplicates)}")
        return self


def load_app_profile(path: str | Path) -> AppProfile:
    """Read + contract validation + parse into the pydantic model. Any invalid input raises ProfileError (D11)."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"app_profile is unreadable or not valid JSON: {path}: {exc}") from exc
    try:
        validate_artifact("app_profile.schema.json", data)
    except ContractValidationError as exc:
        raise ProfileError(str(exc)) from exc
    return AppProfile.model_validate(data)


def resolve_credentials(profile: AppProfile) -> tuple[str, str]:
    """Resolve the environment-variable references into plaintext credentials. They live only in process memory and are never written to disk (D12)."""
    return _resolve_auth_credentials(profile.auth)


def actor_auth(profile: AppProfile, actor_id: str) -> AuthConfig:
    """Resolve an actor's auth config without materializing credentials."""
    if actor_id == "default":
        return profile.auth
    for actor in profile.actors:
        if actor.actor_id == actor_id:
            return actor.auth
    raise ProfileError(f"profile does not declare actor: {actor_id}")


def session_initialization_endpoint(
    auth: AuthConfig,
) -> tuple[str, str] | None:
    """Return the exact typed session-initialization endpoint for one auth config."""
    if auth.method == "none":
        return None
    if auth.method == "api_token":
        config = auth.api_token
    elif auth.method == "cookie_session":
        config = auth.cookie_session
    else:
        declared = [
            item
            for item in (auth.api_token, auth.cookie_session)
            if item is not None
        ]
        if len(declared) != 1:
            raise ValueError(
                "form_login profile does not uniquely declare a typed "
                "session-initialization endpoint"
            )
        config = declared[0]
    if config is None:
        raise ValueError("auth profile does not declare a typed session endpoint")
    return config.method.upper(), config.path


def actor_session_initialization_endpoint(
    profile: AppProfile,
    actor_id: str,
) -> tuple[str, str] | None:
    """Resolve one actor, including the top-level ``default`` actor, to its endpoint."""
    return session_initialization_endpoint(actor_auth(profile, actor_id))


def resolve_actor_credentials(profile: AppProfile, actor_id: str) -> tuple[str, str]:
    """Resolve one actor's credential values in memory only."""
    return _resolve_auth_credentials(actor_auth(profile, actor_id))


def _resolve_auth_credentials(auth: AuthConfig) -> tuple[str, str]:
    ref = auth.credentials_ref
    if ref is None:
        raise ProfileError("the current profile has no credentials_ref, so credentials cannot be resolved")
    email = os.environ.get(ref.email_env)
    password = os.environ.get(ref.password_env)
    missing = [name for name, val in ((ref.email_env, email), (ref.password_env, password)) if not val]
    if missing:
        raise ProfileError(f"credential environment variables are not set: {', '.join(missing)}")
    return email, password
