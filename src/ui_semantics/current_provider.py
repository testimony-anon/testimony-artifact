"""Thin runtime configuration around the existing current proposal contracts.

``ProposalRunPlan`` and ``ProposalCallSpec`` remain the only scientific call
plan.  This module only chooses the current fixture, sealed replay, HTTP, or
ChatGPT-authenticated CLI transport and resolves runtime inputs.
"""

from __future__ import annotations

from .artifact_relocation import attested_sha256
import hashlib
import json
import math
import os
import subprocess
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from threading import BoundedSemaphore, Lock
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from .contracts import ProposalEvidenceView, RenderedCandidateInput
from .proposal_run import (
    ProposalCallSpec,
    global_scan_batches,
    load_sealed_rendered_proposal_response,
    scan_soft_overflow_bytes,
)
from .current_providers import (
    CodexCLIRenderedTransport,
    OpenAICompatibleRenderedTransport,
    RenderedProposalProvider,
    RenderedProposalProviderAdapter,
    RenderedProposalResponse,
    RenderedProposalTransport,
)


CODEX_CLI_EXECUTABLE = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
CENTER_COMPLETION_CALL_PREFIX = "center-completion-"


class ProviderCallLimiter:
    """One suite-wide bound on in-flight real provider transports."""

    def __init__(self, concurrency: int) -> None:
        self._slots = BoundedSemaphore(concurrency)
        self._lock = Lock()
        self.active = 0
        self.actual_max = 0

    @contextmanager
    def slot(self):
        with self._slots:
            with self._lock:
                self.active += 1
                self.actual_max = max(self.actual_max, self.active)
            try:
                yield
            finally:
                with self._lock:
                    self.active -= 1


@dataclass(frozen=True)
class FixtureRuntimeConfig:
    kind: Literal["fixture"]
    max_rendered_chars: int


@dataclass(frozen=True)
class OpenAIRuntimeConfig:
    kind: Literal["openai_compatible"]
    base_url_env: str
    api_key_env: str
    timeout_seconds: int
    max_rendered_chars: int
    max_output_tokens: int


@dataclass(frozen=True)
class CodexCLIRuntimeConfig:
    kind: Literal["codex_cli"]
    timeout_seconds: int
    max_rendered_chars: int


@dataclass(frozen=True)
class SealedResponseReplayRuntimeConfig:
    kind: Literal["sealed_response_replay"]
    max_rendered_chars: int
    source_run_root_ref: str
    source_run_root_path: Path


ProviderRuntimeConfig = (
    FixtureRuntimeConfig
    | OpenAIRuntimeConfig
    | CodexCLIRuntimeConfig
    | SealedResponseReplayRuntimeConfig
)


@dataclass(frozen=True)
class ProposalPolicy:
    model: str
    temperature: float
    retry_limit: int
    endpoint_shape: str
    endpoint_host: str
    actual_model_policy: Literal["exact", "consistent"]
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class FixtureResponse:
    call_id: str
    response_path: Path
    response_sha256: str
    response_received_at: str


@dataclass(frozen=True)
class CurrentProviderBundle:
    plan_id: str
    frozen_at: str
    normal_runs: int
    provider: ProviderRuntimeConfig
    calls: tuple[ProposalCallSpec, ...]
    path: Path
    fixture_responses: tuple[FixtureResponse, ...]
    fixture_response_paths: tuple[Path, ...]
    proposal_policy: ProposalPolicy

    @property
    def replay_source_paths(self) -> tuple[Path, ...]:
        if not isinstance(self.provider, SealedResponseReplayRuntimeConfig):
            return ()
        return tuple(
            path
            for path in sorted(self.provider.source_run_root_path.rglob("*"))
            if path.is_file()
        )

    @property
    def proposal_specs(self) -> tuple[ProposalCallSpec, ...]:
        return self.calls

    @property
    def evidence_run_id(self) -> str:
        return self.plan_id


class CurrentProviderFactory(Protocol):
    logical_call_count: int
    transport_attempt_count: int
    external_network_calls: int
    external_provider_llm_calls: int
    sealed_response_replay_count: int
    input_size_chars: int
    response_delivery_kind: Literal["provider", "sealed_response_replay"]

    def preflight(self, rendered_prompt: str) -> None: ...
    def register_calls(self, calls: tuple[ProposalCallSpec, ...]) -> None: ...
    def mark_reused_call(self, spec: ProposalCallSpec) -> None: ...
    def resume_failed_call(
        self, spec: ProposalCallSpec, *, prior_attempt_count: int
    ) -> None: ...
    def transport_attempts_for(self, call_id: str) -> int: ...
    def __call__(self, spec: ProposalCallSpec) -> RenderedProposalProvider: ...
    def assert_complete(self) -> None: ...


def load_current_provider_plan(
    path: Path,
    *,
    requested_provider: str,
) -> CurrentProviderBundle:
    source = path.resolve(strict=True)
    value = json.loads(source.read_text(encoding="utf-8"))
    base_fields = {
        "schema_version",
        "plan_id",
        "frozen_at",
        "normal_runs",
        "provider",
        "policy",
    }
    if not isinstance(value, dict):
        raise ValueError("current provider runtime config must be an object")
    provider_value = value.get("provider")
    if not isinstance(provider_value, dict):
        raise ValueError("current provider runtime config must declare provider")
    kind = provider_value.get("kind")
    expected_fields = base_fields | ({"responses"} if kind == "fixture" else set())
    if set(value) != expected_fields:
        raise ValueError("current provider runtime config shape mismatch")
    if value["schema_version"] != "uisemtest-current-provider-config-v1":
        raise ValueError("unsupported current provider runtime config")
    if kind != requested_provider:
        raise ValueError("CLI provider does not match runtime configuration")

    plan_id = _safe_id(value["plan_id"], "plan_id")
    frozen_at = str(value["frozen_at"])
    _timestamp(frozen_at)
    normal_runs = value["normal_runs"]
    if normal_runs != 1 or isinstance(normal_runs, bool):
        raise ValueError("current M14 normal_runs is frozen at one")

    if kind == "fixture":
        if set(provider_value) != {"kind", "max_rendered_chars"}:
            raise ValueError("fixture provider runtime config shape mismatch")
        provider: ProviderRuntimeConfig = FixtureRuntimeConfig(
            kind="fixture",
            max_rendered_chars=_positive_int(
                provider_value["max_rendered_chars"], "max_rendered_chars"
            ),
        )
    elif kind == "openai_compatible":
        if _timestamp(frozen_at) > datetime.now(UTC):
            raise ValueError("real provider plan frozen_at must not be in the future")
        if set(provider_value) != {
            "kind",
            "base_url_env",
            "api_key_env",
            "timeout_seconds",
            "max_rendered_chars",
            "max_output_tokens",
        }:
            raise ValueError("OpenAI-compatible runtime config shape mismatch")
        provider = OpenAIRuntimeConfig(
            kind="openai_compatible",
            base_url_env=_env_name(provider_value["base_url_env"]),
            api_key_env=_env_name(provider_value["api_key_env"]),
            timeout_seconds=_positive_int(
                provider_value["timeout_seconds"], "timeout_seconds"
            ),
            max_rendered_chars=_positive_int(
                provider_value["max_rendered_chars"], "max_rendered_chars"
            ),
            max_output_tokens=_positive_int(
                provider_value["max_output_tokens"], "max_output_tokens"
            ),
        )
    elif kind == "codex_cli":
        if _timestamp(frozen_at) > datetime.now(UTC):
            raise ValueError("real provider plan frozen_at must not be in the future")
        if set(provider_value) != {
            "kind",
            "timeout_seconds",
            "max_rendered_chars",
        }:
            raise ValueError("Codex CLI runtime config shape mismatch")
        provider = CodexCLIRuntimeConfig(
            kind="codex_cli",
            timeout_seconds=_positive_int(
                provider_value["timeout_seconds"], "timeout_seconds"
            ),
            max_rendered_chars=_positive_int(
                provider_value["max_rendered_chars"], "max_rendered_chars"
            ),
        )
    elif kind == "sealed_response_replay":
        if set(provider_value) != {
            "kind", "max_rendered_chars", "source_run_root_ref"
        }:
            raise ValueError("exact replay runtime config shape mismatch")
        source_root_ref = _relative_ref(
            provider_value["source_run_root_ref"], "source_run_root_ref"
        )
        source_root = _resolve_relative_dir(source.parent, source_root_ref)
        provider = SealedResponseReplayRuntimeConfig(
            kind="sealed_response_replay",
            max_rendered_chars=_positive_int(
                provider_value["max_rendered_chars"], "max_rendered_chars"
            ),
            source_run_root_ref=source_root_ref,
            source_run_root_path=source_root,
        )
    else:
        raise ValueError("unsupported current provider kind")

    policy_value = value["policy"]
    expected_policy = {
        "model",
        "temperature",
        "retry_limit",
        "endpoint_shape",
        "endpoint_host",
        "actual_model_policy",
    }
    if not isinstance(policy_value, dict) or set(policy_value) not in (
        expected_policy, expected_policy | {"reasoning_effort"}
    ):
        raise ValueError("current provider proposal policy shape mismatch")
    reasoning_effort = policy_value.get("reasoning_effort")
    if kind == "codex_cli" and reasoning_effort is None:
        raise ValueError("Codex CLI policy requires explicit reasoning_effort")
    if (
        kind == "openai_compatible"
        and reasoning_effort is not None
        and reasoning_effort not in {"minimal", "low", "medium", "high", "xhigh", "max"}
    ):
        raise ValueError("OpenAI-compatible reasoning_effort must be a known effort level")
    temperature = policy_value["temperature"]
    retry_limit = policy_value["retry_limit"]
    if (
        not isinstance(temperature, (int, float))
        or isinstance(temperature, bool)
        or not math.isfinite(float(temperature))
        or not 0.0 <= float(temperature) <= 2.0
    ):
        raise ValueError("current provider temperature is invalid")
    if (
        not isinstance(retry_limit, int)
        or isinstance(retry_limit, bool)
        or not 0 <= retry_limit <= 10
    ):
        raise ValueError("current provider retry_limit is invalid")
    string_fields = (
        policy_value["model"],
        policy_value["endpoint_shape"],
        policy_value["endpoint_host"],
    )
    if any(not isinstance(item, str) for item in string_fields):
        raise ValueError("current provider policy strings are invalid")
    actual_model_policy = policy_value["actual_model_policy"]
    if actual_model_policy not in {"exact", "consistent"}:
        raise ValueError("current provider actual-model policy is invalid")
    policy = ProposalPolicy(
        model=policy_value["model"],
        temperature=float(temperature),
        retry_limit=retry_limit,
        endpoint_shape=policy_value["endpoint_shape"],
        endpoint_host=policy_value["endpoint_host"],
        actual_model_policy=actual_model_policy,
        reasoning_effort=reasoning_effort,
    )
    _proposal_specs_from_policy(policy, (("preflight-card",),))
    if kind == "openai_compatible" and policy.endpoint_shape != "openai_compatible":
        raise ValueError("real provider call endpoint shape mismatch")
    if kind == "codex_cli" and policy.endpoint_shape != "codex_cli":
        raise ValueError("Codex CLI call endpoint shape mismatch")

    fixture_responses: list[FixtureResponse] = []
    fixture_paths: list[Path] = []
    for row in value.get("responses", []):
        if not isinstance(row, dict) or set(row) != {
            "call_id", "response_ref", "response_received_at"
        }:
            raise ValueError("fixture response shape mismatch")
        call_id = _safe_id(row["call_id"], "fixture response call_id")
        response_path = _resolve_relative(source.parent, str(row["response_ref"]))
        received_at = str(row["response_received_at"])
        _timestamp(received_at)
        fixture_paths.append(response_path)
        fixture_responses.append(FixtureResponse(
            call_id=call_id,
            response_path=response_path,
            response_sha256=_sha256_file(response_path),
            response_received_at=received_at,
        ))
    response_ids = [item.call_id for item in fixture_responses]
    if len(response_ids) != len(set(response_ids)):
        raise ValueError("fixture response call IDs must be unique")
    if kind == "fixture" and not fixture_responses:
        raise ValueError("fixture provider requires frozen scan/detail responses")

    return CurrentProviderBundle(
        plan_id=plan_id,
        frozen_at=frozen_at,
        normal_runs=normal_runs,
        provider=provider,
        calls=(),
        path=source,
        fixture_responses=tuple(fixture_responses),
        fixture_response_paths=tuple(fixture_paths),
        proposal_policy=policy,
    )


def bind_evidence_card_proposal_calls(
    bundle: CurrentProviderBundle,
    view: ProposalEvidenceView,
) -> CurrentProviderBundle:
    """Bind deterministic compact global-scan batches over all atomic cards."""

    batches = global_scan_batches(view)
    calls = _proposal_specs_from_policy(
        bundle.proposal_policy,
        batches,
        soft_overflow_bytes=scan_soft_overflow_bytes(view, batches),
    )
    return replace(bundle, calls=calls)


def _proposal_specs_from_policy(
    policy: ProposalPolicy,
    scan_batches: tuple[tuple[str, ...], ...],
    *,
    soft_overflow_bytes: dict[int, int] | None = None,
) -> tuple[ProposalCallSpec, ...]:
    soft_overflow_bytes = soft_overflow_bytes or {}
    return tuple(
        ProposalCallSpec(
            call_id=f"global-scan-{index:04d}",
            call_order=index,
            model=policy.model,
            reasoning_effort=policy.reasoning_effort,
            temperature=policy.temperature,
            retry_limit=policy.retry_limit,
            endpoint_shape=policy.endpoint_shape,
            endpoint_host=policy.endpoint_host,
            stratum="business",
            proposal_round="global_scan",
            evidence_card_ids=card_ids,
            scan_soft_overflow_utf8_bytes=soft_overflow_bytes.get(index - 1),
        )
        for index, card_ids in enumerate(scan_batches, start=1)
    )


def build_current_provider_factory(
    bundle: CurrentProviderBundle,
    *, call_limiter: ProviderCallLimiter | None = None,
) -> CurrentProviderFactory:
    if isinstance(bundle.provider, FixtureRuntimeConfig):
        return _FixtureFactoryAdapter(
            bundle.calls,
            tuple(
                response
                for response in bundle.fixture_responses
                if not response.call_id.startswith(CENTER_COMPLETION_CALL_PREFIX)
            ),
            max_rendered_chars=bundle.provider.max_rendered_chars,
        )
    if isinstance(bundle.provider, SealedResponseReplayRuntimeConfig):
        return _ExactProposalRunReplayFactory(
            bundle.provider.source_run_root_path,
            bundle.calls,
        )
    if isinstance(bundle.provider, CodexCLIRuntimeConfig):
        return _CodexCLIFactory(bundle.calls, bundle.provider, call_limiter=call_limiter)
    if not isinstance(bundle.provider, OpenAIRuntimeConfig):
        raise TypeError("real provider runtime config is missing")
    return _OpenAIFactory(bundle.calls, bundle.provider, call_limiter=call_limiter)


def build_center_completion_provider_factory(
    bundle: CurrentProviderBundle,
    *, call_limiter: ProviderCallLimiter | None = None,
) -> CurrentProviderFactory:
    """Build the same current transport with only completion responses in scope."""

    calls: tuple[ProposalCallSpec, ...] = ()
    if isinstance(bundle.provider, FixtureRuntimeConfig):
        return _FixtureFactoryAdapter(
            calls,
            tuple(
                response
                for response in bundle.fixture_responses
                if response.call_id.startswith(CENTER_COMPLETION_CALL_PREFIX)
            ),
            max_rendered_chars=bundle.provider.max_rendered_chars,
            allow_unused_responses=True,
        )
    if isinstance(bundle.provider, SealedResponseReplayRuntimeConfig):
        completion_root = bundle.provider.source_run_root_path / "center_completion"
        return (
            _ExactProposalRunReplayFactory(completion_root, calls)
            if completion_root.is_dir()
            else _EmptyCompletionReplayFactory()
        )
    if isinstance(bundle.provider, CodexCLIRuntimeConfig):
        return _CodexCLIFactory(calls, bundle.provider, call_limiter=call_limiter)
    if not isinstance(bundle.provider, OpenAIRuntimeConfig):
        raise TypeError("real provider runtime config is missing")
    return _OpenAIFactory(calls, bundle.provider, call_limiter=call_limiter)


def build_exact_proposal_replay_factory(
    *,
    source_run_root: Path,
    scan_calls: tuple[ProposalCallSpec, ...],
) -> "_ExactProposalRunReplayFactory":
    """Replay one completed M10 call tree through the same current executor."""

    return _ExactProposalRunReplayFactory(source_run_root, scan_calls)


class _FixtureFactoryAdapter:
    def __init__(
        self,
        scan_calls: tuple[ProposalCallSpec, ...],
        responses: tuple[FixtureResponse, ...],
        *,
        max_rendered_chars: int,
        allow_unused_responses: bool = False,
    ) -> None:
        self._calls = {call.call_id: call for call in scan_calls}
        self._responses = {response.call_id: response for response in responses}
        self._created: set[str] = set()
        self._completed: set[str] = set()
        self._max_rendered_chars = max_rendered_chars
        self._allow_unused_responses = allow_unused_responses
        self.logical_call_count = 0
        self.transport_attempt_count = 0
        self.external_network_calls = 0
        self.external_provider_llm_calls = 0
        self.sealed_response_replay_count = 0
        self.input_size_chars = 0
        self.response_delivery_kind: Literal["provider"] = "provider"
        self._lock = Lock()

    def preflight(self, rendered_prompt: str) -> None:
        self.input_size_chars = max(
            self.input_size_chars,
            _preflight_size(rendered_prompt, self._max_rendered_chars),
        )

    def __call__(self, spec: ProposalCallSpec) -> RenderedProposalProvider:
        with self._lock:
            planned = self._calls.get(spec.call_id)
            response = self._responses.get(spec.call_id)
            if planned != spec or response is None or spec.call_id in self._created:
                raise ValueError("fixture proposal call is absent, duplicated, or unplanned")
            self._created.add(spec.call_id)

        def transport(*, rendered_prompt: str) -> RenderedProposalResponse:
            with self._lock:
                if not rendered_prompt or spec.call_id in self._completed:
                    raise ValueError("fixture proposal transport was empty or repeated")
            content = response.response_path.read_text(encoding="utf-8")
            if hashlib.sha256(content.encode("utf-8")).hexdigest() != response.response_sha256:
                raise ValueError("fixture provider response changed after plan load")
            with self._lock:
                self._completed.add(spec.call_id)
                self.logical_call_count += 1
            return RenderedProposalResponse(
                content=content,
                raw_envelope={
                    "schema_version": "uisemtest-frozen-fixture-response-v1",
                    "call_id": spec.call_id,
                    "response_file_sha256": response.response_sha256,
                    "transport_invoked": False,
                },
                model=spec.model,
                reasoning_effort=spec.reasoning_effort,
                endpoint_shape=spec.endpoint_shape,
                endpoint_host=spec.endpoint_host,
                temperature=spec.temperature,
                retry_count=0,
                response_received_at=response.response_received_at,
            )

        return RenderedProposalProviderAdapter(transport=transport)

    def register_calls(self, calls: tuple[ProposalCallSpec, ...]) -> None:
        with self._lock:
            for call in calls:
                if call.call_id in self._calls or call.call_id not in self._responses:
                    raise ValueError("fixture dynamic detail call is duplicated or lacks a response")
                self._calls[call.call_id] = call

    def assert_complete(self) -> None:
        with self._lock:
            expected = set(self._calls)
            if (
                self._created != expected
                or self._completed != expected
                or (
                    not self._allow_unused_responses
                    and expected != set(self._responses)
                )
                or self.logical_call_count != len(expected)
            ):
                raise ValueError("fixture provider did not close the planned scan/detail call tree")


class _EmptyCompletionReplayFactory:
    """Permit a replay union with no completion trigger and fail on any call."""

    logical_call_count = 0
    transport_attempt_count = 0
    external_network_calls = 0
    external_provider_llm_calls = 0
    sealed_response_replay_count = 0
    input_size_chars = 0
    response_delivery_kind: Literal["sealed_response_replay"] = (
        "sealed_response_replay"
    )

    def register_calls(self, calls: tuple[ProposalCallSpec, ...]) -> None:
        if calls:
            raise ValueError("exact replay source lacks its required center completion")

    def __call__(self, spec: ProposalCallSpec) -> RenderedProposalProvider:
        raise ValueError(f"unavailable center-completion replay call: {spec.call_id}")

    def assert_complete(self) -> None:
        return None


class _OpenAIFactory:
    def __init__(
        self,
        calls: tuple[ProposalCallSpec, ...],
        config: OpenAIRuntimeConfig,
        *, call_limiter: ProviderCallLimiter | None = None,
    ) -> None:
        self.call_limiter = call_limiter
        self._calls = {call.call_id: call for call in calls}
        self._created: set[str] = set()
        self._completed: set[str] = set()
        self._attempts_by_call: dict[str, int] = {}
        self._prior_attempts_by_call: dict[str, int] = {}
        self._config = config
        self.logical_call_count = 0
        self.transport_attempt_count = 0
        self.external_network_calls = 0
        self.external_provider_llm_calls = 0
        self.sealed_response_replay_count = 0
        self.input_size_chars = 0
        self.response_delivery_kind: Literal["provider"] = "provider"
        self._base_url: str | None = None
        self._api_key: str | None = None
        self._lock = Lock()

    def preflight(self, rendered_prompt: str) -> None:
        self.input_size_chars = max(self.input_size_chars, _preflight_size(
            rendered_prompt, self._config.max_rendered_chars
        ))
        base_url = os.environ.get(self._config.base_url_env)
        api_key = os.environ.get(self._config.api_key_env)
        missing = [
            name
            for name, value in (
                (self._config.base_url_env, base_url),
                (self._config.api_key_env, api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"provider environment variable missing: {', '.join(missing)}")
        parsed = urlsplit(str(base_url))
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("real provider base URL must be credential-free HTTPS")
        planned_hosts = {call.endpoint_host for call in self._calls.values()}
        if planned_hosts != {parsed.netloc.lower()}:
            raise ValueError("real provider host differs from ProposalCallSpec")
        self._base_url = str(base_url)
        self._api_key = str(api_key)

    def register_calls(self, calls: tuple[ProposalCallSpec, ...]) -> None:
        with self._lock:
            for call in calls:
                if call.call_id in self._calls:
                    raise ValueError("dynamic proposal call ID is duplicated")
                self._calls[call.call_id] = call

    def mark_reused_call(self, spec: ProposalCallSpec) -> None:
        with self._lock:
            if self._calls.get(spec.call_id) != spec or spec.call_id in self._created:
                raise ValueError("reused provider call is absent or duplicated")
            self._created.add(spec.call_id)
            self._completed.add(spec.call_id)
            self.sealed_response_replay_count += 1

    def resume_failed_call(
        self, spec: ProposalCallSpec, *, prior_attempt_count: int
    ) -> None:
        with self._lock:
            if (
                self._calls.get(spec.call_id) != spec
                or spec.call_id in self._created
                or not 0 <= prior_attempt_count <= spec.retry_limit
            ):
                raise ValueError("failed provider call cannot start its bounded recovery")
            self._prior_attempts_by_call[spec.call_id] = prior_attempt_count
            self._attempts_by_call[spec.call_id] = prior_attempt_count

    def __call__(self, spec: ProposalCallSpec) -> RenderedProposalProvider:
        with self._lock:
            planned = self._calls.get(spec.call_id)
            if planned != spec or spec.call_id in self._created:
                raise ValueError("real provider call is absent or duplicated")
            if self._base_url is None or self._api_key is None:
                raise ValueError("real provider requested before preflight")
            self._created.add(spec.call_id)
            base_url = self._base_url
            api_key = self._api_key
            prior_attempt_count = self._prior_attempts_by_call.get(spec.call_id, 0)
        provider = OpenAICompatibleRenderedTransport(
            base_url=base_url,
            api_key=api_key,
            model=spec.model,
            reasoning_effort=spec.reasoning_effort,
            temperature=spec.temperature,
            max_retries=spec.retry_limit,
            timeout_seconds=self._config.timeout_seconds,
            max_output_tokens=self._config.max_output_tokens,
            on_transport_attempt=lambda: self._record_transport_attempt(
                spec.call_id
            ),
            prior_attempt_count=prior_attempt_count,
        )
        transport = _CountingTransport(spec.call_id, provider, self)
        return RenderedProposalProviderAdapter(transport=transport)

    def _begin(self, call_id: str) -> None:
        with self._lock:
            self.logical_call_count += 1
            self.external_provider_llm_calls += 1

    def _record_transport_attempt(self, call_id: str) -> None:
        with self._lock:
            self._attempts_by_call[call_id] = self._attempts_by_call.get(call_id, 0) + 1
            self.transport_attempt_count += 1
            self.external_network_calls += 1

    def transport_attempts_for(self, call_id: str) -> int:
        with self._lock:
            return self._attempts_by_call.get(call_id, 0)

    def _complete(self, call_id: str, response: RenderedProposalResponse) -> None:
        with self._lock:
            if self._attempts_by_call.get(call_id, 0) != response.retry_count + 1:
                raise ValueError("real provider transport attempt count drift")
            self._completed.add(call_id)

    def assert_complete(self) -> None:
        with self._lock:
            expected = set(self._calls)
            if self._created != expected or self._completed != expected:
                raise ValueError("real provider did not complete every ProposalCallSpec")


class _CodexCLIFactory:
    def __init__(
        self,
        calls: tuple[ProposalCallSpec, ...],
        config: CodexCLIRuntimeConfig,
        *, call_limiter: ProviderCallLimiter | None = None,
    ) -> None:
        self.call_limiter = call_limiter
        self._calls = {call.call_id: call for call in calls}
        self._created: set[str] = set()
        self._completed: set[str] = set()
        self._attempts_by_call: dict[str, int] = {}
        self._prior_attempts_by_call: dict[str, int] = {}
        self._config = config
        self.logical_call_count = 0
        self.transport_attempt_count = 0
        self.external_network_calls = 0
        self.external_provider_llm_calls = 0
        self.sealed_response_replay_count = 0
        self.input_size_chars = 0
        self.response_delivery_kind: Literal["provider"] = "provider"
        self._cli_version: str | None = None
        self._lock = Lock()

    def preflight(self, rendered_prompt: str) -> None:
        self.input_size_chars = max(
            self.input_size_chars,
            _preflight_size(rendered_prompt, self._config.max_rendered_chars),
        )
        planned_shapes = {call.endpoint_shape for call in self._calls.values()}
        planned_hosts = {call.endpoint_host for call in self._calls.values()}
        if planned_shapes != {"codex_cli"} or len(planned_hosts) != 1:
            raise ValueError("Codex CLI call specs do not share one transport identity")
        self._cli_version = _codex_cli_preflight(CODEX_CLI_EXECUTABLE)

    def register_calls(self, calls: tuple[ProposalCallSpec, ...]) -> None:
        with self._lock:
            for call in calls:
                if call.call_id in self._calls:
                    raise ValueError("dynamic proposal call ID is duplicated")
                if call.endpoint_shape != "codex_cli":
                    raise ValueError("dynamic Codex CLI call changed transport shape")
                self._calls[call.call_id] = call

    def mark_reused_call(self, spec: ProposalCallSpec) -> None:
        with self._lock:
            if self._calls.get(spec.call_id) != spec or spec.call_id in self._created:
                raise ValueError("reused provider call is absent or duplicated")
            self._created.add(spec.call_id)
            self._completed.add(spec.call_id)
            self.sealed_response_replay_count += 1

    def resume_failed_call(
        self, spec: ProposalCallSpec, *, prior_attempt_count: int
    ) -> None:
        with self._lock:
            if (
                self._calls.get(spec.call_id) != spec
                or spec.call_id in self._created
                or not 0 <= prior_attempt_count <= spec.retry_limit
            ):
                raise ValueError("failed provider call cannot start its bounded recovery")
            self._prior_attempts_by_call[spec.call_id] = prior_attempt_count
            self._attempts_by_call[spec.call_id] = prior_attempt_count

    def __call__(self, spec: ProposalCallSpec) -> RenderedProposalProvider:
        with self._lock:
            if self._calls.get(spec.call_id) != spec or spec.call_id in self._created:
                raise ValueError("real provider call is absent or duplicated")
            if self._cli_version is None:
                raise ValueError("Codex CLI provider requested before preflight")
            self._created.add(spec.call_id)
            prior_attempt_count = self._prior_attempts_by_call.get(spec.call_id, 0)
            cli_version = self._cli_version
        provider = CodexCLIRenderedTransport(
            executable=CODEX_CLI_EXECUTABLE,
            cli_version=cli_version,
            model=spec.model,
            reasoning_effort=spec.reasoning_effort,
            endpoint_host=spec.endpoint_host,
            temperature=spec.temperature,
            max_retries=spec.retry_limit,
            timeout_seconds=self._config.timeout_seconds,
            on_transport_attempt=lambda: self._record_transport_attempt(spec.call_id),
            prior_attempt_count=prior_attempt_count,
        )
        return RenderedProposalProviderAdapter(
            transport=_CountingTransport(spec.call_id, provider, self)
        )

    def _begin(self, call_id: str) -> None:
        with self._lock:
            self.logical_call_count += 1
            self.external_provider_llm_calls += 1

    def _record_transport_attempt(self, call_id: str) -> None:
        with self._lock:
            self._attempts_by_call[call_id] = self._attempts_by_call.get(call_id, 0) + 1
            self.transport_attempt_count += 1
            self.external_network_calls += 1

    def transport_attempts_for(self, call_id: str) -> int:
        with self._lock:
            return self._attempts_by_call.get(call_id, 0)

    def _complete(self, call_id: str, response: RenderedProposalResponse) -> None:
        with self._lock:
            if self._attempts_by_call.get(call_id, 0) != response.retry_count + 1:
                raise ValueError("real provider transport attempt count drift")
            self._completed.add(call_id)

    def assert_complete(self) -> None:
        with self._lock:
            expected = set(self._calls)
            if self._created != expected or self._completed != expected:
                raise ValueError("real provider did not complete every ProposalCallSpec")


class _ExactProposalRunReplayFactory:
    def __init__(
        self,
        source_run_root: Path,
        scan_calls: tuple[ProposalCallSpec, ...],
    ) -> None:
        self._root = source_run_root.resolve(strict=True)
        provenance = _read_object(self._root / "union" / "union_provenance.json")
        resolved = provenance.get("resolved_calls")
        if not isinstance(resolved, list) or not resolved:
            raise ValueError("exact replay source is not a completed dynamic M10 run")
        specs = []
        for row in resolved:
            if not isinstance(row, dict):
                raise ValueError("exact replay source contains an invalid call")
            value = dict(row)
            if "evidence_card_ids" in value:
                value["evidence_card_ids"] = tuple(value["evidence_card_ids"])
            specs.append(ProposalCallSpec.model_validate(value, strict=True))
        if tuple(specs[:len(scan_calls)]) != scan_calls:
            raise ValueError("exact replay scan schedule differs from the current plan")
        self._calls = {spec.call_id: spec for spec in specs}
        self._created: set[str] = set()
        self._completed: set[str] = set()
        self.logical_call_count = 0
        self.transport_attempt_count = 0
        self.external_network_calls = 0
        self.external_provider_llm_calls = 0
        self.sealed_response_replay_count = 0
        self.input_size_chars = 0
        self.response_delivery_kind: Literal["sealed_response_replay"] = (
            "sealed_response_replay"
        )
        self._lock = Lock()

    def preflight(self, rendered_prompt: str) -> None:
        if not rendered_prompt:
            raise ValueError("exact replay preflight requires rendered input")
        self.input_size_chars = max(self.input_size_chars, len(rendered_prompt))

    def register_calls(self, calls: tuple[ProposalCallSpec, ...]) -> None:
        with self._lock:
            expected = tuple(
                self._calls[call.call_id]
                for call in calls
                if call.call_id in self._calls
            )
            if expected != calls:
                raise ValueError("exact replay detail schedule differs from the source run")

    def __call__(self, spec: ProposalCallSpec) -> RenderedProposalProvider:
        with self._lock:
            if self._calls.get(spec.call_id) != spec or spec.call_id in self._created:
                raise ValueError("exact replay call is absent or duplicated")
            self._created.add(spec.call_id)
        call_root = self._root / "calls" / spec.call_id
        expected_rendered = RenderedCandidateInput.model_validate_json(
            (call_root / "rendered_candidate_input.json").read_bytes(), strict=True
        )
        response = load_sealed_rendered_proposal_response(
            call_root / "provider_response_envelope.json",
            expected_file_sha256=_sha256_file(
                call_root / "provider_response_envelope.json"
            ),
        )

        def transport(*, rendered_prompt: str) -> RenderedProposalResponse:
            if rendered_prompt != expected_rendered.rendered_text:
                raise ValueError("exact replay rendered input differs from the source run")
            with self._lock:
                if spec.call_id in self._completed:
                    raise ValueError("exact replay transport called more than once")
                self._completed.add(spec.call_id)
                self.sealed_response_replay_count += 1
            return response

        return RenderedProposalProviderAdapter(transport=transport)

    def assert_complete(self) -> None:
        with self._lock:
            if self._created != set(self._calls) or self._completed != set(self._calls):
                raise ValueError("exact replay did not consume the complete scan/detail call tree")
            if any((
                self.logical_call_count,
                self.transport_attempt_count,
                self.external_network_calls,
                self.external_provider_llm_calls,
            )):
                raise ValueError("exact replay unexpectedly performed an external call")


class _CountingTransport:
    def __init__(
        self,
        call_id: str,
        provider: RenderedProposalTransport,
        factory: _OpenAIFactory | _CodexCLIFactory,
    ) -> None:
        self._call_id = call_id
        self._provider = provider
        self._factory = factory
        self._called = False

    def __call__(self, *, rendered_prompt: str) -> RenderedProposalResponse:
        if self._called:
            raise ValueError("real provider transport called more than once")
        self._called = True
        limiter = self._factory.call_limiter
        with limiter.slot() if limiter is not None else nullcontext():
            self._factory._begin(self._call_id)
            response = self._provider(rendered_prompt=rendered_prompt)
            self._factory._complete(self._call_id, response)
        return response


def _preflight_size(rendered_prompt: str, limit: int) -> int:
    if not isinstance(rendered_prompt, str) or not rendered_prompt:
        raise ValueError("provider preflight requires the frozen rendered input")
    size = len(rendered_prompt)
    if size > limit:
        raise ValueError("frozen rendered input exceeds provider context preflight")
    return size


def _codex_cli_preflight(executable: Path) -> str:
    if executable != CODEX_CLI_EXECUTABLE or not executable.is_file():
        raise ValueError("approved ChatGPT desktop Codex CLI is unavailable")
    environment = dict(os.environ)
    for name in CodexCLIRenderedTransport._STRIPPED_ENVIRONMENT:
        environment.pop(name, None)
    version = subprocess.run(
        [str(executable), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=15,
        check=False,
        text=True,
    )
    if version.returncode != 0 or not version.stdout.strip().startswith("codex-cli "):
        raise ValueError("approved Codex CLI version preflight failed")
    login = subprocess.run(
        [str(executable), "login", "status"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=15,
        check=False,
        text=True,
    )
    login_output = f"{login.stdout}\n{login.stderr}"
    if login.returncode != 0 or "Logged in using ChatGPT" not in login_output:
        raise ValueError("Codex CLI is not authenticated with ChatGPT")
    return version.stdout.strip()


def _safe_id(value: Any, label: str) -> str:
    raw = str(value)
    if not raw or len(raw) > 128 or not all(
        character.isalnum() or character in "_.-" for character in raw
    ):
        raise ValueError(f"current {label} is invalid")
    return raw


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"current {label} must be a positive integer")
    return value


def _env_name(value: Any) -> str:
    raw = str(value)
    if not raw or not raw.replace("_", "A").isalnum() or raw.upper() != raw:
        raise ValueError("provider environment reference is invalid")
    return raw


def _relative_ref(value: Any, label: str) -> str:
    raw = str(value)
    ref = PurePosixPath(raw)
    if (
        not raw
        or ref.is_absolute()
        or ref.as_posix() != raw
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
        raise ValueError(f"current {label} must be a normalized relative ref")
    return raw


def _resolve_relative_dir(root: Path, raw_ref: str) -> Path:
    target = (root / Path(*PurePosixPath(raw_ref).parts)).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_dir():
        raise ValueError("exact replay source ref escapes the provider config root")
    return target


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("provider timestamp must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError("provider timestamp requires an explicit timezone")
    return parsed.astimezone(UTC)


def _resolve_relative(root: Path, raw_ref: str) -> Path:
    ref = PurePosixPath(raw_ref)
    if (
        ref.is_absolute()
        or ref.as_posix() != raw_ref
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
        raise ValueError("fixture response ref must be normalized relative POSIX")
    target = (root / Path(*ref.parts)).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("fixture response ref escapes the provider config root")
    return target


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


__all__ = [
    "CodexCLIRuntimeConfig",
    "CurrentProviderBundle",
    "CurrentProviderFactory",
    "ProposalPolicy",
    "SealedResponseReplayRuntimeConfig",
    "bind_evidence_card_proposal_calls",
    "build_center_completion_provider_factory",
    "build_current_provider_factory",
    "load_current_provider_plan",
]
