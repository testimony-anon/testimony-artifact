"""Local-loopback current runtime backed by the existing replay and HTTP stack."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .artifact_relocation import attested_sha256
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlsplit

from stage0_launch.profile import actor_auth, resolve_actor_credentials
from stage2_5_probe.prober import login_auth
from stage2_recover.loader import LoadedBundle
from ui_semantics.replay_policy import SetupSessionKind
from stage6_ground.http_client import HttpResult, send
from stage6_ground.relation_test_execution import (
    RelationExecutionError,
    calibration_arm_for_protocol,
)
from stage6_ground.resource_rebinding import (
    ResourceBindingSource,
    ResourceBindingUse,
    ResourceRebindingError,
    SetupBindingPlan,
    apply_consumer_bindings,
    capture_creator_values,
    extract_typed_value,
    scalar_sha256,
    typed_value_is_missing,
)
from stage6_ground.test_execution import encode_body
from stage6_ground.ui_semantic_replay import (
    BaselineRequestShapeLossError,
    ReplayContext,
    SessionBundleReplayAdapter,
    UnresolvedRequestMaterialError,
)

from .contracts import UiApiTrace
from .current_settle import poll_semantic_stability, route_observer_is_pure
from .current_adapter import CurrentAdapterBundle, LocalHttpRuntimeConfig
from .m11b_materializer import RouteSPreLiveMaterializedCandidate
from .current_route_s import binding_scope_id, canonical_json_bytes, request_shape_sha256
from .dsl import copy_numeric_sources, with_numeric_body, get_path
from .route_s_capture_redaction import dotted_tokens, sanitize_capture, predicate_value_refs


_RUNTIME_COUNT_KEYS = (
    "reset_runs",
    "session_materializations",
    "setup_executions",
    "request_executions",
    "settle_executions",
    "external_provider_llm_calls",
    "external_network_calls",
    "real_target_runs",
    "real_server_runs",
    "real_browser_runs",
    "real_docker_runs",
    "real_reset_runs",
)
_REDACTED_MATERIAL = re.compile(r"^\[REDACTED:[0-9a-fA-F]+\]$")
_RESET_DIAGNOSTIC_LIMIT = 4096
_RESET_SECRET_ENV_MARKERS = (
    "password",
    "token",
    "secret",
    "cookie",
    "authorization",
    "connection_string",
    "database_url",
    "dsn",
)
_RESET_SECRET_HEADER = re.compile(
    r"(?i)(\b(?:authorization|cookie|set-cookie)\b\s*:\s*)[^\r\n]*"
)
_RESET_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|token|secret|mmauthtoken)\b\s*[:=]\s*)"
    r"[^\s,;]+"
)
_RESET_URI_USERINFO = re.compile(
    r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@"
)


def _workflow_value_environment(
    bindings: tuple[dict[str, Any], ...],
    *,
    run_root: Path,
    environment: Mapping[str, str],
) -> dict[str, str]:
    """Read only workflow-declared dynamic inputs after exact provenance checks."""

    root = run_root.resolve(strict=True)
    workflows: dict[Path, Mapping[str, Any]] = {}
    allowed: dict[str, str] = {}
    for binding in bindings:
        if binding.get("source_material_kind") != "workflow_value_env":
            continue
        source_ref = binding.get("source_workflow_ref")
        source_sha256 = binding.get("source_workflow_sha256")
        value_env = binding.get("source_value_env")
        if (
            not isinstance(source_ref, str)
            or re.fullmatch(
                r"inputs/recording/workflows/[0-9a-f]{64}\.json", source_ref
            )
            is None
            or not isinstance(source_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
            or not isinstance(value_env, str)
            or not value_env
        ):
            raise ValueError("workflow value environment provenance is malformed")
        relative = Path(source_ref)
        workflow_candidate_path = root / relative
        if workflow_candidate_path.is_symlink():
            raise ValueError("workflow value environment source differs from its pin")
        workflow_path = workflow_candidate_path.resolve(strict=True)
        if (
            not workflow_path.is_file()
            or not workflow_path.is_relative_to(root)
            or attested_sha256(workflow_path)
            != source_sha256
            or workflow_path.name != f"{source_sha256}.json"
        ):
            raise ValueError("workflow value environment source differs from its pin")
        workflow = workflows.get(workflow_path)
        if workflow is None:
            loaded = json.loads(workflow_path.read_bytes())
            if not isinstance(loaded, Mapping):
                raise ValueError("workflow value environment source is malformed")
            workflows[workflow_path] = loaded
            workflow = loaded
        matching_steps = [
            step
            for step in workflow.get("steps", ())
            if isinstance(step, Mapping)
            and step.get("actor_id") == binding.get("actor_id")
            and step.get("workflow_step_id")
            == binding.get("source_workflow_step_id")
            and step.get("global_step_index")
            == binding.get("source_global_step_index")
            and isinstance(step.get("action"), Mapping)
            and step["action"].get("kind") == binding.get("source_action_kind")
            and step["action"].get("value_env") == value_env
        ]
        if len(matching_steps) != 1:
            raise ValueError("workflow value environment source does not match action")
        value = environment.get(value_env)
        if not value:
            raise ValueError("workflow value environment is unavailable")
        allowed[value_env] = value
    return {name: allowed[name] for name in sorted(allowed)}


def _bounded_reset_diagnostic(value: object, env: Mapping[str, str]) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    secrets = sorted(
        {
            item
            for name, item in env.items()
            if item
            and len(item) >= 4
            and any(marker in name.casefold() for marker in _RESET_SECRET_ENV_MARKERS)
        },
        key=len,
        reverse=True,
    )
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    text = _RESET_SECRET_HEADER.sub(r"\1[REDACTED]", text)
    text = _RESET_SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = _RESET_URI_USERINFO.sub(r"\1[REDACTED]@", text)
    return text[-_RESET_DIAGNOSTIC_LIMIT:]


def _sanitized_reset_record(
    value: Mapping[str, Any] | None,
    env: Mapping[str, str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result = {
        key: copy.deepcopy(value[key])
        for key in ("status", "reset_epoch_ref")
        if key in value
    }
    failure = value.get("failure")
    if isinstance(failure, Mapping):
        sanitized_failure = {
            key: copy.deepcopy(failure[key])
            for key in ("phase", "reason_code", "exit_code")
            if key in failure
        }
        for key in ("stdout", "stderr"):
            if key in failure:
                sanitized_failure[key] = _bounded_reset_diagnostic(
                    failure[key], env
                )
        result["failure"] = sanitized_failure
    return result


def _read_reset_record(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


@dataclass
class _HttpArmContext:
    candidate_id: str
    arm: str
    reset_epoch: str
    replay: ReplayContext
    full_reset_ref: dict[str, Any]
    material: RouteSPreLiveMaterializedCandidate
    binding_plan: SetupBindingPlan
    fresh_values: dict[str, Any] = field(default_factory=dict)
    response_value_aliases: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    reset_alias_source_events: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    snapshot_ordinals: dict[tuple[str, str, str], int] = field(default_factory=dict)
    snapshot_last: dict[tuple[str, str], str] = field(default_factory=dict)
    sensitive_values: list[str] = field(default_factory=list)
    removed_sensitive_values: list[str] = field(default_factory=list)
    in_memory_executions: dict[tuple[str, str], dict[str, Any]] = field(
        default_factory=dict
    )
    prepared_requests: dict[tuple[str, str], tuple[Any, ...]] = field(default_factory=dict)
    repeated_requests: dict[tuple[str, str], tuple[Any, ...]] = field(default_factory=dict)


def _workflow_effect_context(context: _HttpArmContext) -> bool:
    from .dsl import is_workflow_effect_predicate
    return context.arm in {"workflow", "repeat_once", "repeat_twice", "negative_no_effect", "actor_matrix"} and is_workflow_effect_predicate(context.material.candidate.get("primary_predicate", {}))


class _LocalHttpExecutionCore:
    _missing_collection_defaults: Mapping[str, list[Any]] = {}
    response_transform: Callable[[Mapping[str, Any], Any], Any] | None = None
    _external_lifecycle = False

    def __init__(
        self,
        bundle: CurrentAdapterBundle,
        *,
        run_id: str,
        request_bindings: Mapping[str, Any],
        trace: UiApiTrace,
        recording_material_aliases: tuple[dict[str, Any], ...],
        recorded_bundles: Mapping[str, LoadedBundle] | None = None,
    ) -> None:
        runtime = bundle.adapter.runtime
        if not isinstance(runtime, LocalHttpRuntimeConfig):
            raise TypeError("local HTTP core requires local_http runtime config")
        self.profile = bundle.profile
        self.runtime = runtime
        self.run_id = run_id
        self.request_bindings = copy.deepcopy(dict(request_bindings))
        self._static_headers = copy.deepcopy(
            dict(bundle.adapter.request_mapping.static_headers)
        )
        self._missing_collection_defaults = copy.deepcopy(
            dict(bundle.adapter.missing_collection_defaults)
        )
        self.trace = copy.deepcopy(trace.trace)
        self.recording_material_aliases = copy.deepcopy(recording_material_aliases)
        self.source_root = Path(runtime.source_root).resolve(strict=True)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.run_root: Path | None = None
        self.processes: list[subprocess.Popen[bytes]] = []
        self.counts: Counter[str] = Counter({key: 0 for key in _RUNTIME_COUNT_KEYS})
        self._reset_counter = 0
        self._last_full_reset_ref: dict[str, Any] | None = None
        self._started = False
        self._stopped = False
        self._preexisting_generated_paths: set[Path] = set()
        self.response_transform: Callable[[Mapping[str, Any], Any], Any] | None = None
        self._external_lifecycle = False
        self._evaluation_setup: tuple[_HttpArmContext, Mapping[str, Any]] | None = None
        self._replay = SessionBundleReplayAdapter(
            self.trace,
            self.profile,
            transport=self._replay_transport,
            reset=self._reset_for_replay,
            login=self._login,
            materialize_request=self._materialize_replay_request,
            normalize_response=_normalize_alias_response,
            recorded_bundles=recorded_bundles,
        )

    def _materialize_replay_request(
        self,
        context: ReplayContext,
        actor_id: str,
        path: str,
        query: Mapping[str, Any],
        headers: Mapping[str, Any],
        body: Any,
    ) -> tuple[str, dict[str, Any], dict[str, Any], Any]:
        request_headers = dict(headers)
        request_headers.update(copy.deepcopy(self._static_headers))
        return _materialize_alias_values(
            context, actor_id, path, query, request_headers, body
        )

    def preflight(self) -> None:
        for actor in self.trace["actors"]:
            actor_id = str(actor["actor_id"])
            if actor_auth(self.profile, actor_id).method != "none":
                resolve_actor_credentials(self.profile, actor_id)

    def start(self, run_root: Path) -> None:
        if self._started or self._stopped:
            raise RuntimeError("local target lifecycle may start only once")
        self.run_root = run_root.resolve(strict=True)
        self._started = True
        self._preexisting_generated_paths = {
            path
            for relative in self.runtime.teardown_generated_paths
            if (path := (self.source_root / relative).resolve()).exists()
        }
        env = self._target_env()
        for command in self.runtime.materialize_commands:
            subprocess.run(
                list(command),
                cwd=self.source_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=300,
            )
        for command in self.runtime.server_commands:
            process = subprocess.Popen(
                list(command),
                cwd=self.source_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.processes.append(process)
        self.counts["real_target_runs"] = 1
        self.counts["real_server_runs"] = len(self.processes)
        self._wait_for_health()

    def attach(self, run_root: Path) -> None:
        """Attach a case runtime to an evaluation-owned, already healthy target."""
        if self._started or self._stopped:
            raise RuntimeError("local target lifecycle may start only once")
        self.run_root = run_root.resolve(strict=True)
        self._external_lifecycle = True
        self._started = True

    def _transform_response(
        self, context: _HttpArmContext, request: Mapping[str, Any], result: Any,
    ) -> Any:
        if self.response_transform is None:
            return result
        metadata = {
            "candidate_id": context.candidate_id, "arm": context.arm,
            "reset_epoch": context.reset_epoch, **request,
            "sensitive_values": tuple(context.sensitive_values),
            "removed_strings": list(context.removed_sensitive_values),
        }
        return self.response_transform(metadata, result)

    def begin_arm(
        self,
        material: RouteSPreLiveMaterializedCandidate,
        arm: str,
    ) -> _HttpArmContext:
        if not self._started or self._stopped:
            raise RuntimeError("local HTTP arm requested outside target lifecycle")
        replay, short_ref = self._replay.reset()
        replay.request_material_bindings = tuple(
            copy.deepcopy(
                material.execution_material.get("request_material_bindings", ())
            )
        )
        if self.run_root is None:
            raise RuntimeError("local HTTP run root is unavailable")
        replay.request_material_environment = _workflow_value_environment(
            replay.request_material_bindings,
            run_root=self.run_root,
            environment=os.environ,
        )
        full_ref = self._last_full_reset_ref
        if full_ref is None or full_ref["record_id"] != short_ref["record_id"]:
            raise RuntimeError("local reset evidence did not close the replay reset")
        self._last_full_reset_ref = None
        self.counts["session_materializations"] += len(replay.sessions)
        plan = _binding_plan(material.resource_binding_plans[arm], self.request_bindings)
        context = _HttpArmContext(
            candidate_id=material.candidate_id,
            arm=arm,
            reset_epoch=short_ref["record_id"],
            replay=replay,
            full_reset_ref=copy.deepcopy(full_ref),
            material=material,
            binding_plan=plan,
        )
        _seed_binding_sources_from_reset_aliases(context, self.request_bindings)
        for actor in self.trace["actors"]:
            actor_id = str(actor["actor_id"])
            if actor_auth(self.profile, actor_id).method == "none":
                continue
            for value in resolve_actor_credentials(self.profile, actor_id):
                if value and value not in context.sensitive_values:
                    context.sensitive_values.append(value)
        self._remember_sensitive_headers(
            context,
            *(session.headers for session in replay.sessions.values()),
        )
        return context

    def execute_setup(self, context: _HttpArmContext) -> list[dict[str, Any]]:
        setup = [copy.deepcopy(row) for row in context.material.candidate["setup"]]
        if setup:
            if context.replay.resource_binding_plan is not None:
                raise ResourceRebindingError("setup binding plan was already installed")
            reset_alias_source_ids = set(context.reset_alias_source_events)
            context.replay.resource_binding_plan = context.binding_plan
            if reset_alias_source_ids:
                context.replay.resource_binding_values.update(
                    {
                        source_id: copy.deepcopy(context.fresh_values[source_id])
                        for source_id in reset_alias_source_ids
                    }
                )
        rows: list[dict[str, Any]] = []
        executed_actors: set[str] = set()
        for endpoint in setup:
            actor_id = str(endpoint["actor_id"])
            policy = self._replay.setup_session_policy(endpoint)
            policy_kind = getattr(policy, "kind", None)
            session_policy_note: str | None = None
            if (
                policy_kind == SetupSessionKind.SESSION_INITIALIZATION
                and actor_id in executed_actors
            ):
                # The recording authenticated this actor again after earlier
                # requests of its own (for example logout, then login).  The
                # session bootstrapped at reset no longer stands for that point
                # of the chain, so the declared initialization is re-run with
                # the profile credentials instead of replaying the redacted
                # recorded login body.
                try:
                    self._replay.reinitialize_session(context.replay, actor_id)
                except Exception as error:
                    # The recorded chain may have changed this actor's own
                    # credentials before logging in again (settings flows);
                    # the profile credentials are then rejected.  That is a
                    # candidate-local setup failure, not a run failure.
                    raise RelationExecutionError(
                        "local_http_session_reinitialization_failed"
                    ) from error
                self.counts["session_materializations"] += 1
                self._remember_sensitive_headers(
                    context, context.replay.sessions[actor_id].headers
                )
                response_status = 200
                response_body: Any = {}
                session_policy_note = "session_reinitialized"
            elif policy.skip_setup:
                response_status = 200
                response_body = {}
                session_policy_note = (
                    str(policy_kind.value)
                    if isinstance(policy_kind, SetupSessionKind)
                    else "skipped"
                )
            else:
                self._evaluation_setup = (context, endpoint)
                try:
                    result = self._replay.execute_setup(context.replay, endpoint)
                finally:
                    self._evaluation_setup = None
                self.counts["setup_executions"] += 1
                response_status = int(result["status"])
                response_body = copy.deepcopy(result["binding_response_body"])
                self._remember_request_material_values(context)
                self._remember_sensitive_headers(
                    context,
                    *(session.headers for session in context.replay.sessions.values()),
                )
                executed_actors.add(actor_id)
            events = (
                self._capture_sources(
                    context,
                    request_ref=str(endpoint["request_ref"]),
                    response_body=response_body,
                )
                if 200 <= response_status < 400
                else []
            )
            safe_response, response_manifest = sanitize_capture(
                response_body,
                sensitive_values=context.sensitive_values,
                removed_strings=context.removed_sensitive_values,
            )
            row = {
                "actor_id": endpoint["actor_id"],
                "request_ref": endpoint["request_ref"],
                "status": response_status,
                "response": {"body": safe_response},
                "binding_events": events,
            }
            if response_manifest:
                row["redaction_manifest"] = {"response": response_manifest}
            if session_policy_note is not None:
                row["session_policy"] = session_policy_note
            rows.append(row)
        return rows

    def _prepare_endpoint(
        self,
        context: _HttpArmContext,
        *,
        actor_id: str,
        request_ref: str,
        method: str,
        expected_path: str,
    ) -> tuple[Any, ...]:
        template = self.request_bindings.get(request_ref)
        if not isinstance(template, dict):
            raise RelationExecutionError("local_http_request_template_missing")
        if (
            template.get("actor_id") != actor_id
            or template.get("method") != method
            or template.get("path") != expected_path
        ):
            raise RelationExecutionError("local_http_request_template_drift")
        path = str(template["path"])
        query = copy.deepcopy(template.get("query") or {})
        headers = dict(context.replay.sessions[actor_id].headers)
        headers.update(copy.deepcopy(template.get("headers") or {}))
        body = copy.deepcopy(template.get("body"))
        body_was_none = body is None
        path, query, headers, body = _materialize_alias_values(
            context.replay,
            actor_id,
            path,
            query,
            headers,
            body,
        )
        if getattr(context.replay, "request_material_bindings", ()):
            path, query, headers, body = self._replay.materialize_request_material(
                context.replay,
                request_ref=request_ref,
                actor_id=actor_id,
                path=path,
                query=query,
                headers=headers,
                body=body,
            )
            self._remember_request_material_values(context)
        event_rows: list[dict[str, Any]] = []
        path, query, headers, materialized_body = apply_consumer_bindings(
            context.binding_plan,
            request_ref=request_ref,
            path=path,
            query=query,
            headers=headers,
            body={} if body is None else body,
            values=context.fresh_values,
            events=event_rows,
        )
        _assert_no_redacted_request_material(
            path,
            query,
            headers,
            materialized_body,
        )
        if body_was_none and not any(
            row.location == "body"
            for row in context.binding_plan.uses
            if row.consumer_request_ref == request_ref
        ):
            body = None
        else:
            body = materialized_body
        return path, query, headers, body, event_rows

    def execute_endpoint(
        self,
        context: _HttpArmContext,
        *,
        actor_id: str,
        request_ref: str,
        method: str,
        expected_path: str,
        step_id: str | None = None,
        occurrence_index: int | None = None,
        repeated: bool = False,
    ) -> dict[str, Any]:
        key = (actor_id, request_ref)
        prepared = context.repeated_requests.get(key) if repeated else context.prepared_requests.pop(key, None)
        if repeated and prepared is None:
            prepared = context.prepared_requests.pop(key, None)
            if prepared is None:
                raise RelationExecutionError("repeated_request_not_prepared_before_first_send")
            context.repeated_requests[key] = copy.deepcopy(prepared)
        if prepared is None:
            prepared = self._prepare_endpoint(context, actor_id=actor_id, request_ref=request_ref, method=method, expected_path=expected_path)
        path, query, headers, body, event_rows = prepared
        primary = context.material.candidate.get("primary_predicate", {})
        numeric_predicate = primary.get("body", primary) if primary.get("family") == "forall" else primary
        if primary.get("family") == "repeat_delta":
            numeric_predicate = primary["delta"]
        exact_numeric = context.arm == "temporal" or numeric_predicate.get("family") in {"P06", "P08", "P13", "P15", "P16", "P17", "P18", "P19"}
        evidence_path = _normalize_alias_path(context.replay, actor_id, path)
        evidence_query = _normalize_alias_response(
            context.replay, actor_id, query
        )
        evidence_headers = _normalize_alias_response(
            context.replay, actor_id, headers
        )
        evidence_body = _normalize_alias_response(
            context.replay, actor_id, body
        )
        causal_numeric = context.material.candidate.get("primary_predicate", {}).get("family") == "P06" and context.arm in {"control", "treatment"}
        semantic_body = (
            self._normalize_p06_evidence(context, actor_id, body, {"producer_request"})
            if causal_numeric else
            copy.deepcopy(body) if exact_numeric or _workflow_effect_context(context) else
            self._normalize_semantic_evidence(context, actor_id, body)
        )
        events = self._scope_consumer_events(context, event_rows)
        execution_key = (actor_id, request_ref, step_id, occurrence_index) if repeated or context.arm in {"repeat_once", "repeat_twice"} else (actor_id, request_ref)
        context.in_memory_executions[execution_key] = {
            "request_body": copy.deepcopy(body),
        }
        try:
            numeric_body = self._numeric_request_source(context, actor_id, request_ref, body) if exact_numeric else None
            if numeric_body is None:
                result = self._send(method, path, query, headers, body)
            else:
                result = self._send(method, path, query, headers, body, numeric_body=numeric_body)
        except OSError as error:
            self._transform_response(context, {
                "phase": "endpoint", "actor_id": actor_id, "request_ref": request_ref,
                "method": method, "path": path, "query": query, "request_body": body,
                "step_id": step_id, "occurrence_index": occurrence_index,
            }, error)
            raise RelationExecutionError("local_http_transport_failed") from error
        self._remember_sensitive_headers(context, headers, result.headers)
        result = self._transform_response(context, {
            "phase": "endpoint", "actor_id": actor_id, "request_ref": request_ref,
            "method": method, "path": path, "query": query, "request_body": body,
            "step_id": step_id, "occurrence_index": occurrence_index,
        }, result)
        workflow_effect = _workflow_effect_context(context)
        inverse_ref = ((context.material.execution_binding.get("payload", {}).get("inverse") or {}).get("request_ref"))
        action_ref = request_ref == inverse_ref or request_ref == (context.material.candidate.get("producer") or {}).get("request_ref")
        status_only = primary.get("family") == "P02" and all(ref.get("role") == "after_status" for ref in predicate_value_refs(primary))
        strict_observation = context.arm in {"single_state", "metamorphic_query", "multi_resource"} or ((workflow_effect or exact_numeric) and not action_ref)
        if strict_observation:
            self.counts["request_executions"] += 1
            declared_absence = primary.get("family") == "P01" and result.status in primary.get("absent_statuses", []) and request_ref != context.material.candidate["producer"]["request_ref"]
            physical_response_body = None if declared_absence or status_only else _single_state_response_body(result)
        else:
            physical_response_body = _response_body(result)
        context.in_memory_executions[execution_key]["response_body"] = (
            copy.deepcopy(physical_response_body)
        )
        if 200 <= result.status < 400:
            self._apply_postcondition_session_continuity(
                context,
                actor_id=actor_id,
                request_ref=request_ref,
                response_body=physical_response_body,
            )
        self._remember_sensitive_headers(
            context, context.replay.sessions[actor_id].headers
        )
        fresh_capture_events: list[dict[str, Any]] = []
        fresh_capture_error: str | None = None
        try:
            fresh_capture_events = self._capture_sources(
                context,
                request_ref=request_ref,
                response_body=physical_response_body,
            )
        except (KeyError, TypeError, ValueError, ResourceRebindingError):
            fresh_capture_error = "producer_response_identity_missing"
        response_body = (
            self._normalize_p06_evidence(
                context, actor_id, physical_response_body,
                {"producer_response"} if request_ref == context.material.candidate["producer"]["request_ref"] else {"before", "after"},
            ) if causal_numeric else copy.deepcopy(physical_response_body)
            if context.arm in {"single_state", "metamorphic_query", "multi_resource"} or workflow_effect or exact_numeric
            else self._normalize_response_evidence(
                context, actor_id, physical_response_body
            )
        )
        safe_physical_body, transport_request_manifest = sanitize_capture(
            body,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_physical_query, transport_query_manifest = sanitize_capture(
            query,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_physical_headers, transport_headers_manifest = sanitize_capture(
            headers,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_body, _semantic_request_manifest = sanitize_capture(
            evidence_body,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_semantic_body, request_manifest = sanitize_capture(
            semantic_body,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_query, query_manifest = sanitize_capture(
            evidence_query,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_request_headers, request_headers_manifest = sanitize_capture(
            evidence_headers,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_response, response_manifest = sanitize_capture(
            response_body,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        safe_response_headers, response_headers_manifest = sanitize_capture(
            result.headers,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values,
        )
        transport = {"method": method, "path": evidence_path, "body": safe_body}
        if not strict_observation:
            self.counts["request_executions"] += 1
        execution = {
            "checkpoint_id": step_id,
            "occurrence_index": occurrence_index,
            "reset_epoch": context.reset_epoch,
            "request_identity_verified": repeated and prepared == context.repeated_requests.get(key),
            "status": result.status,
            "body": safe_response,
            "transport_request": transport,
            "physical_transport_request": {
                "method": method,
                "path": path,
                "body": safe_physical_body,
            },
            "semantic_request_body": safe_semantic_body,
            "transport_request_shape_sha256": request_shape_sha256(
                {"method": method, "path": evidence_path, "body": evidence_body}
            ),
            "transport_metadata": {
                "query": safe_query,
                "request_headers": safe_request_headers,
                "response_headers": safe_response_headers,
                "sensitive_values_persisted": False,
            },
            "physical_transport_metadata": {
                "query": safe_physical_query,
                "request_headers": safe_physical_headers,
            },
            "resource_binding_events": events,
            "fresh_capture_events": fresh_capture_events,
            "fresh_capture_error": fresh_capture_error,
            "redaction_manifest": {
                "request": transport_request_manifest,
                "request_query": transport_query_manifest,
                "request_headers": transport_headers_manifest,
                "response": response_manifest,
                "response_headers": response_headers_manifest,
            },
        }
        if context.arm == "temporal":
            execution["timing"] = dict(result.timing)
        if exact_numeric:
            try:
                execution = with_numeric_body(execution, result.body_text)
            except (TypeError, ValueError):
                # Invalid or missing JSON cannot supply exact decimal operands.
                pass
            if hasattr(result, "numeric_request_body"):
                execution = copy_numeric_sources(execution, execution)
                execution.numeric_request_body = copy.deepcopy(result.numeric_request_body)
            if causal_numeric:
                if hasattr(execution, "numeric_body"):
                    execution.numeric_body = self._normalize_p06_evidence(
                        context, actor_id, execution.numeric_body,
                        {"producer_response"} if request_ref == context.material.candidate["producer"]["request_ref"] else {"before", "after"},
                        physical_value=physical_response_body,
                    )
                if hasattr(execution, "numeric_request_body"):
                    execution.numeric_request_body = self._normalize_p06_evidence(
                        context, actor_id, execution.numeric_request_body, {"producer_request"},
                        physical_value=body,
                    )
        return execution

    def _numeric_request_source(
        self, context: _HttpArmContext, actor_id: str, request_ref: str, body: Any,
    ) -> Any:
        """Recover only unchanged, unbound numeric leaves from original JSON.

        This tree is transient transport material. A float without its original
        text remains a float, so re-encoding it never creates decimal provenance.
        """
        replay = getattr(self, "_replay", None)
        record = getattr(replay, "_requests", {}).get(request_ref)
        if not isinstance(record, Mapping) or record.get("actor_id") != actor_id:
            return None
        observation = record.get("observation_ref") or {}
        bundle = getattr(replay, "_bundles", {}).get(observation.get("run_id"))
        index = observation.get("entry_index")
        if bundle is None or type(index) is not int or not 0 <= index < len(bundle.entries):
            return None
        text = (bundle.entries[index].get("request", {}).get("postData") or {}).get("text")
        if not isinstance(text, str):
            return None
        try:
            recorded = _single_state_response_body(HttpResult(200, text))
            lexical = with_numeric_body({}, text).numeric_body
        except (TypeError, ValueError, RelationExecutionError):
            return None
        # Binding can preserve an identical float value while losing its source.
        # Block the declared target even in that case, including its descendants.
        blocked = [dotted_tokens(use.target_path) for use in context.binding_plan.uses
                   if use.consumer_request_ref == request_ref and use.location == "body"]
        blocked.extend(dotted_tokens(str(row["target_path"]))
                       for row in context.replay.request_material_bindings
                       if row.get("request_ref") == request_ref and row.get("location") == "body")
        aliases = _material_alias_rows(context.replay, actor_id, reverse=False)

        def retain(current: Any, original: Any, exact: Any, tokens: tuple[Any, ...]) -> Any:
            if any(tokens[:len(prefix)] == prefix for prefix in blocked):
                return copy.deepcopy(current)
            if isinstance(current, dict) and isinstance(original, dict) and isinstance(exact, dict):
                return {key: retain(value, original.get(key), exact.get(key), (*tokens, key))
                        for key, value in current.items()}
            if isinstance(current, list) and isinstance(original, list) and isinstance(exact, list):
                return [retain(value, original[i] if i < len(original) else None,
                               exact[i] if i < len(exact) else None, (*tokens, i))
                        for i, value in enumerate(current)]
            if (type(current) is float and type(original) is float and current == original
                    and isinstance(exact, Decimal) and exact.is_finite()
                    and not any(type(target) is float and current == target for _, target in aliases)):
                return exact
            return copy.deepcopy(current)

        return retain(body, recorded, lexical, ())

    def prepare_producer(self, context: _HttpArmContext) -> dict[str, Any]:
        """Freeze the actual bound action request without sending it."""
        binding = context.material.execution_binding["payload"]["producer"]
        request_ref = context.material.candidate["producer"]["request_ref"]
        actor_id = binding["actor_id"]
        key = (actor_id, request_ref)
        if key not in context.prepared_requests:
            context.prepared_requests[key] = self._prepare_endpoint(
                context, actor_id=actor_id, request_ref=request_ref,
                method=binding["method"], expected_path=binding["path"],
            )
        path, query, headers, body, _ = context.prepared_requests[key]
        semantic_body = copy.deepcopy(body)
        safe_body, manifest = sanitize_capture(semantic_body,
            sensitive_values=context.sensitive_values,
            removed_strings=context.removed_sensitive_values)
        # Logical input differs only at evidence-proven resource targets. Never
        # normalize every equal scalar: a business amount can equal a fresh ID.
        logical = {"method": binding["method"], "path": path, "query": copy.deepcopy(query),
                   "body": copy.deepcopy(body), "headers": {name: value for name, value in headers.items() if name.lower() not in {"authorization", "cookie"}}}
        for use in context.binding_plan.uses:
            if use.consumer_request_ref != request_ref or use.actor_id != actor_id:
                continue
            marker = {"bound_resource": use.source_id}
            if use.location == "path":
                index = int(re.search(r"\d+", use.target_path).group()) + (1 if path.startswith("/") else 0)
                parts = logical["path"].split("/")
                parts[index] = "{" + use.source_id + "}"
                logical["path"] = "/".join(parts)
            else:
                location = "headers" if use.location == "header" else use.location
                tokens = use.target_path.removeprefix("$.").split(".")
                target = logical[location]
                for token in tokens[:-1]:
                    target = target[int(token)] if isinstance(target, list) else target[token]
                target[int(tokens[-1]) if isinstance(target, list) else tokens[-1]] = marker
        safe_logical, logical_manifest = sanitize_capture(logical, sensitive_values=context.sensitive_values, removed_strings=context.removed_sensitive_values)
        fields, fields_manifest = sanitize_capture({"method": binding["method"], "path": path, "query": query, "headers": headers, "body": body}, sensitive_values=context.sensitive_values, removed_strings=context.removed_sensitive_values)
        channels = {"request": manifest, "logical_request": logical_manifest, "request_fields": fields_manifest}
        for location, channel in (("query", "request_query"), ("path", "request_path"), ("headers", "request_headers")):
            _, channels[channel] = sanitize_capture({"query": query, "path": path, "headers": headers}[location], sensitive_values=context.sensitive_values, removed_strings=context.removed_sensitive_values)
        return {"request": safe_body, "request_fields": fields, "logical_request": safe_logical,
                "reset_epoch": context.reset_epoch, "redaction_manifest": channels}

    def verify_identity_topology(self, context: _HttpArmContext, topology: Mapping[str, Any]) -> bool:
        left, right = str(topology["left_actor_id"]), str(topology["right_actor_id"])
        sessions = context.replay.sessions
        if left not in sessions or right not in sessions:
            return False
        same_session = sessions[left] is sessions[right] and sessions[left].headers is sessions[right].headers
        if same_session != (topology["session_relation"] == "same"):
            return False
        identities = []
        for actor in (left, right):
            probe = actor_auth(self.profile, actor).probe_endpoint
            if probe is None or probe.expect_json_path is None:
                return False
            result = self._send(probe.method, probe.path, {}, dict(sessions[actor].headers), None)
            self.counts["request_executions"] += 1
            if result.status != probe.expect_status:
                return False
            try:
                identity = get_path(json.loads(result.body_text), probe.expect_json_path)
            except (ValueError, KeyError, TypeError):
                return False
            if identity in (None, "", [], {}):
                return False
            if "expect_json_equals" in probe.model_fields_set and (
                type(identity) is not type(probe.expect_json_equals)
                or identity != probe.expect_json_equals
            ):
                return False
            identities.append(canonical_json_bytes(identity))
        return (identities[0] == identities[1]) == (topology["principal_relation"] == "same")

    def evaluate_in_memory_predicate(
        self,
        context: _HttpArmContext,
        predicate: Mapping[str, Any],
    ) -> tuple[bool, dict[str, bool]] | None:
        """Evaluate the narrow exact P02 request-material boundary in memory."""

        if predicate.get("family") != "P02" or predicate.get("operator") != "eq":
            return None
        left = _predicate_role_ref(predicate.get("left"))
        right = _predicate_role_ref(predicate.get("right"))
        if left is None or right is None:
            return None
        by_role = {str(left.get("role")): left, str(right.get("role")): right}
        if set(by_role) != {"after", "producer_request"}:
            return None
        producer_ref = str(context.material.candidate["producer"]["request_ref"])
        producer_actor = str(context.material.candidate["producer"]["actor_id"])
        observations = context.material.execution_binding["payload"]["observations"]
        after_binding = observations.get("workflow_after")
        if not isinstance(after_binding, Mapping):
            return None
        after_ref = str(
            after_binding.get("request_ref")
            or context.material.candidate["consumer"]["request_ref"]
        )
        after_actor = str(after_binding.get("actor_id") or "")
        producer_execution = context.in_memory_executions.get(
            (producer_actor, producer_ref)
        )
        after_execution = context.in_memory_executions.get((after_actor, after_ref))
        if not isinstance(producer_execution, Mapping) or not isinstance(
            after_execution, Mapping
        ):
            return None
        producer_path = str(by_role["producer_request"].get("path") or "")
        after_path = str(by_role["after"].get("path") or "")
        bindings = [
            row
            for row in context.replay.request_material_bindings
            if row.get("request_ref") == producer_ref
            and row.get("actor_id") == producer_actor
            and row.get("location") == "body"
            and row.get("target_path") == producer_path
        ]
        if len(bindings) != 1:
            return None
        binding = bindings[0]
        exact_target = (producer_actor, producer_ref, producer_path)
        request_value = extract_typed_value(
            producer_execution.get("request_body"), producer_path
        )
        after_value = extract_typed_value(
            after_execution.get("response_body"), after_path
        )
        value_type = str(by_role["producer_request"].get("value_type") or "")
        if (
            exact_target not in context.replay.resolved_request_material_targets
            or typed_value_is_missing(request_value)
            or typed_value_is_missing(after_value)
            or value_type != "string"
            or by_role["after"].get("value_type") != value_type
            or binding.get("scalar_type") != value_type
            or not isinstance(request_value, str)
            or not isinstance(after_value, str)
        ):
            return None
        equal = (
            type(request_value) is type(after_value) and request_value == after_value
        )
        return equal, {"values_equal": equal}

    def _apply_postcondition_session_continuity(
        self,
        context: _HttpArmContext,
        *,
        actor_id: str,
        request_ref: str,
        response_body: Any,
    ) -> None:
        execution_material = getattr(
            context.material, "execution_material", {}
        )
        protocol_shape = (
            execution_material.get("protocol_shape", {})
            if isinstance(execution_material, Mapping)
            else {}
        )
        postcondition = protocol_shape.get("postcondition_flow", {})
        continuity = (
            postcondition.get("session_continuity", {})
            if isinstance(postcondition, Mapping)
            else {}
        )
        if not isinstance(continuity, Mapping) or not continuity:
            return
        if request_ref != continuity.get("producer_request_ref"):
            return
        session = context.replay.sessions.get(actor_id)
        if (
            session is None
            or continuity.get("kind") != "api_token"
            or continuity.get("actor_id") != actor_id
            or continuity.get("target_header") != "Authorization"
        ):
            raise RelationExecutionError(
                "postcondition_session_continuity_scope_mismatch"
            )
        token = extract_typed_value(
            response_body, str(continuity.get("response_path") or "")
        )
        if typed_value_is_missing(token) or not isinstance(token, str) or not token:
            raise RelationExecutionError(
                "postcondition_session_material_missing"
            )
        session.headers["Authorization"] = (
            f"{actor_auth(self.profile, actor_id).token_scheme} {token}"
        )
        if token not in context.sensitive_values:
            context.sensitive_values.append(token)

    def snapshot(
        self, context: _HttpArmContext, actor_id: str
    ) -> dict[str, str | None]:
        session = context.replay.sessions[actor_id]
        values = {
            "cookie": session.headers.get("Cookie", ""),
            "token": session.headers.get("Authorization", ""),
        }
        result: dict[str, str | None] = {"cache": None, "last_seen": None}
        for domain, raw in values.items():
            fingerprint = hashlib.sha256(raw.encode()).hexdigest()
            state_key = (actor_id, domain)
            ordinal_key = (actor_id, domain, fingerprint)
            if ordinal_key not in context.snapshot_ordinals:
                prior = [
                    value
                    for (actor, item, _fingerprint), value in context.snapshot_ordinals.items()
                    if actor == actor_id and item == domain
                ]
                context.snapshot_ordinals[ordinal_key] = len(prior)
            ordinal = context.snapshot_ordinals[ordinal_key]
            context.snapshot_last[state_key] = fingerprint
            result[domain] = _sha(
                f"current-local-observer:{context.candidate_id}:{context.arm}:"
                f"{actor_id}:{domain}:state-{ordinal}"
            )
        return result

    def capability_artifacts(
        self,
        context: _HttpArmContext,
        *,
        slot: str,
        actor_id: str,
        before: Mapping[str, str | None],
        after: Mapping[str, str | None],
    ) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
        rows = []
        artifacts = {}
        for domain in ("cookie", "token", "cache", "last_seen"):
            not_applicable = domain in {"cache", "last_seen"}
            unchanged = before[domain] == after[domain]
            row = {
                "domain": domain,
                "disposition": (
                    "not_applicable"
                    if not_applicable
                    else "proven_unchanged" if unchanged else "mutating"
                ),
                "before_sha256": before[domain],
                "after_sha256": after[domain],
                "mutation_events": (
                    [] if not_applicable or unchanged else ["runtime_state_changed"]
                ),
                "uncertain_fields": [],
                "reason_code": (
                    "client_runtime_domain_not_implemented"
                    if not_applicable
                    else "client_session_header_unchanged"
                    if unchanged
                    else "client_session_header_changed"
                ),
            }
            if context.material.output_level == "forensic":
                ref = f"M12/{context.candidate_id}/capabilities/{slot}.{domain}.json"
                payload = canonical_json_bytes(
                    {
                        "slot": slot,
                        "domain": domain,
                        "actor_id": actor_id,
                        "mechanism": (
                            "in_memory_session_header_ordinal"
                            if domain in {"cookie", "token"}
                            else "runtime_state_absent"
                        ),
                        "secret_values_persisted": False,
                    }
                )
                artifacts[ref] = payload
                row.update(
                    {
                        "capability_ref": ref,
                        "capability_sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            rows.append(row)
        return rows, artifacts

    @staticmethod
    def _remember_request_material_values(context: _HttpArmContext) -> None:
        for value in getattr(context.replay, "resolved_request_material_values", ()):
            if (
                isinstance(value, str)
                and value
                and value not in context.sensitive_values
            ):
                context.sensitive_values.append(value)

    @staticmethod
    def _remember_sensitive_headers(
        context: _HttpArmContext, *header_sets: Mapping[str, str]
    ) -> None:
        for headers in header_sets:
            for key, value in headers.items():
                name = key.casefold()
                if name not in {
                    "authorization",
                    "cookie",
                    "proxy-authorization",
                    "set-cookie",
                }:
                    continue
                candidates = [str(value)]
                if name in {"authorization", "proxy-authorization"}:
                    _scheme, separator, credential = str(value).partition(" ")
                    if separator and credential:
                        candidates.append(credential)
                else:
                    chunks = str(value).split(";")
                    if name == "set-cookie":
                        chunks = chunks[:1]
                    for chunk in chunks:
                        if "=" in chunk:
                            _cookie_name, cookie_value = chunk.strip().split("=", 1)
                            if cookie_value:
                                candidates.append(cookie_value)
                for candidate in candidates:
                    if candidate and candidate not in context.sensitive_values:
                        context.sensitive_values.append(candidate)

    def teardown(self) -> None:
        if self._external_lifecycle:
            self._stopped = True
            return
        if self._stopped:
            return
        errors: list[BaseException] = []
        for process in reversed(self.processes):
            if process.poll() is not None:
                continue
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            except BaseException as error:
                errors.append(error)
        deadline = time.monotonic() + 5
        for process in reversed(self.processes):
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except BaseException as error:
                    errors.append(error)
            except BaseException as error:
                errors.append(error)
        for relative in self.runtime.teardown_generated_paths:
            path = (self.source_root / relative).resolve()
            if (
                path.is_relative_to(self.source_root)
                and path not in self._preexisting_generated_paths
                and path.is_file()
            ):
                try:
                    path.unlink()
                except BaseException as error:
                    errors.append(error)
        self._stopped = True
        if errors:
            raise RuntimeError("local target teardown did not complete") from errors[0]

    def _capture_sources(
        self,
        context: _HttpArmContext,
        *,
        request_ref: str,
        response_body: Any,
    ) -> list[dict[str, Any]]:
        pending_sources = tuple(
            source
            for source in context.binding_plan.sources
            if source.source_id not in context.fresh_values
        )
        reset_events = []
        for source_id, event in tuple(context.reset_alias_source_events.items()):
            if event["creator_request_ref"] != request_ref:
                continue
            reset_events.append(copy.deepcopy(event))
            del context.reset_alias_source_events[source_id]
        if not pending_sources:
            return reset_events
        capture_plan = SetupBindingPlan(
            setup_request_refs=context.binding_plan.setup_request_refs,
            sources=pending_sources,
            uses=context.binding_plan.uses,
            issues=context.binding_plan.issues,
        )
        generated: list[dict[str, Any]] = []
        capture_creator_values(
            capture_plan,
            request_ref=request_ref,
            response_body=response_body,
            values=context.fresh_values,
            events=generated,
        )
        sources = {
            (row.creator_request_ref, row.response_path): row
            for row in pending_sources
        }
        result = reset_events
        for event in generated:
            source = sources[(request_ref, event["source_typed_path"])]
            actor = source.actor_id
            matching_uses = [
                row
                for row in context.binding_plan.uses
                if row.source_id == source.source_id
            ]
            if matching_uses:
                use = matching_uses[0]
                recorded = _target_value(
                    self.request_bindings[use.consumer_request_ref],
                    use.location,
                    use.target_path,
                )
            else:
                recorded = _projection_identity_value(
                    context.material.candidate,
                    source.recorded_value_sha256,
                )
            context.response_value_aliases[source.source_id] = (
                copy.deepcopy(context.fresh_values[source.source_id]),
                recorded,
            )
            if (
                _contains_redacted_material(recorded)
                and self._is_authenticated_profile_read_source(
                    source, matching_uses
                )
            ):
                fresh_text = str(context.fresh_values[source.source_id])
                if fresh_text and fresh_text not in context.sensitive_values:
                    context.sensitive_values.append(fresh_text)
            result.append(
                {
                    **event,
                    "source_id": source.source_id,
                    "creator_actor_id": actor,
                    "candidate_id": context.candidate_id,
                    "arm": context.arm,
                    "reset_epoch": context.reset_epoch,
                    "binding_scope_id": binding_scope_id(
                        context.candidate_id,
                        context.arm,
                        actor,
                        context.reset_epoch,
                    ),
                }
            )
        return result

    def _is_authenticated_profile_read_source(
        self,
        source: ResourceBindingSource,
        uses: list[ResourceBindingUse],
    ) -> bool:
        """Identify the narrow technical profile-to-read binding boundary."""

        if not hasattr(self, "trace") or not hasattr(self, "profile"):
            return False
        request_facts = {
            str(row["request_ref"]): row for row in self.trace["api_requests"]
        }
        creator = request_facts.get(source.creator_request_ref)
        if not isinstance(creator, Mapping):
            return False
        probe = actor_auth(self.profile, source.actor_id).probe_endpoint
        if (
            probe is None
            or probe.expect_json_path is None
            or str(creator.get("actor_id") or "") != source.actor_id
            or str(creator.get("method") or "").upper()
            != str(probe.method).upper()
            or str(creator.get("canonical_path") or "") != str(probe.path)
            or not (
                source.response_path == probe.expect_json_path
                or source.response_path.startswith(
                    str(probe.expect_json_path) + "."
                )
            )
            or not uses
        ):
            return False
        for use in uses:
            request = self.request_bindings.get(use.consumer_request_ref)
            observed = request_facts.get(use.consumer_request_ref)
            if not isinstance(request, Mapping):
                return False
            method = str(request.get("method") or "").upper()
            if method in {"GET", "HEAD", "OPTIONS"}:
                continue
            if (
                method == "POST"
                and isinstance(observed, Mapping)
                and (
                    observed.get("graphql_operation_kind") == "query"
                    or observed.get("mechanical_read_kind")
                    == "recorded_post_query"
                    or observed.get("declared_read_semantic") is True
                )
            ):
                continue
            return False
        return True

    def _normalize_semantic_evidence(
        self,
        context: _HttpArmContext,
        actor_id: str,
        value: Any,
    ) -> Any:
        normalized = _normalize_alias_response(context.replay, actor_id, value)
        return _replace_alias_values(
            normalized,
            tuple(context.response_value_aliases.values()),
            object_keys=True,
        )

    def _normalize_p06_evidence(
        self, context: _HttpArmContext, actor_id: str, value: Any,
        roles: set[str], *, physical_value: Any = None,
    ) -> Any:
        """Keep V1 identity aliases while retaining actual arithmetic operands."""
        predicate = context.material.candidate["primary_predicate"]
        refs = [predicate["before"], predicate["after"], predicate["delta"].get("ref", {})]
        protected = []
        for ref in refs:
            if ref.get("role") not in roles:
                continue
            if ref.get("source") == "collection_member":
                protected.append((*dotted_tokens(ref["collection_path"]), "*", *dotted_tokens(ref["field_path"])))
            else:
                protected.append(dotted_tokens(ref["path"]))
        rows = (*_material_alias_rows(context.replay, actor_id, reverse=True),
                *context.response_value_aliases.values())

        def normalize(current: Any, physical: Any, tokens: tuple[Any, ...]) -> Any:
            if any(len(path) == len(tokens) and all(wanted == "*" or wanted == token
                   for wanted, token in zip(path, tokens)) for path in protected):
                return copy.deepcopy(current)
            if isinstance(current, dict) and isinstance(physical, dict):
                result = {}
                for key, item in current.items():
                    normalized_key = _replace_alias_scalar(key, rows)
                    result[normalized_key] = normalize(item, physical.get(key), (*tokens, normalized_key))
                return result
            if isinstance(current, list) and isinstance(physical, list):
                return [normalize(item, physical[index], (*tokens, index)) for index, item in enumerate(current)]
            for source, target in rows:
                if type(physical) is type(source) and physical == source:
                    return copy.deepcopy(target)
            return copy.deepcopy(current)

        return normalize(value, value if physical_value is None else physical_value, ())

    def _normalize_response_evidence(
        self,
        context: _HttpArmContext,
        actor_id: str,
        value: Any,
    ) -> Any:
        normalized = self._normalize_semantic_evidence(
            context, actor_id, value
        )
        return _apply_missing_collection_defaults(
            normalized, self._missing_collection_defaults
        )

    def _scope_consumer_events(
        self,
        context: _HttpArmContext,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        uses = {
            (row.consumer_request_ref, row.location, row.target_path): row
            for row in context.binding_plan.uses
        }
        sources = {row.source_id: row for row in context.binding_plan.sources}
        result = []
        for event in events:
            use = uses[
                (
                    event["consumer_request_ref"],
                    event["target_location"],
                    event["target_typed_path"],
                )
            ]
            source = sources[use.source_id]
            actor = use.actor_id
            result.append(
                {
                    **event,
                    "source_id": source.source_id,
                    "creator_actor_id": source.actor_id,
                    "creator_request_ref": source.creator_request_ref,
                    "source_typed_path": source.response_path,
                    "candidate_id": context.candidate_id,
                    "arm": context.arm,
                    "reset_epoch": context.reset_epoch,
                    "binding_scope_id": binding_scope_id(
                        context.candidate_id,
                        context.arm,
                        actor,
                        context.reset_epoch,
                    ),
                }
            )
        return result

    def _send(
        self,
        method: str,
        path: str,
        query: Mapping[str, Any],
        headers: Mapping[str, str],
        body: Any,
        *,
        numeric_body: Any = None,
    ) -> HttpResult:
        url = self.profile.base_url.rstrip("/") + path
        if query:
            url += "?" + urlencode(query, doseq=True)
        _require_loopback_url(url)
        content_type = next(
            (value for key, value in headers.items() if key.lower() == "content-type"),
            "",
        ).lower()
        if body is None:
            body_text = None
        elif "application/x-www-form-urlencoded" in content_type:
            body_text = encode_body(body, "form_urlencoded").body_text
        elif numeric_body is not None:
            body_text = _encode_exact_request_json(numeric_body)
        elif isinstance(body, dict):
            body_text = encode_body(body, "json").body_text
        else:
            body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        result = send(method, url, dict(headers), body_text)
        if numeric_body is not None and "application/x-www-form-urlencoded" not in content_type:
            # Parse the exact text handed to transport, and retain float leaves
            # as unavailable where the input did not have original precision.
            try:
                wire = with_numeric_body({}, body_text).numeric_body
                result.numeric_request_body = _request_numeric_provenance(wire, numeric_body)
            except (TypeError, ValueError):
                pass
        return result

    def _replay_transport(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body_text: str | None,
    ) -> HttpResult:
        _require_loopback_url(url)
        try:
            result = send(method, url, headers, body_text)
            if self.response_transform is not None and self._evaluation_setup is not None:
                context, endpoint = self._evaluation_setup
                self._remember_sensitive_headers(context, headers or {}, result.headers)
                parsed = urlsplit(url)
                result = self._transform_response(context, {
                    "phase": "setup", **endpoint, "method": method,
                    "path": parsed.path, "query_string": parsed.query,
                    "request_body": json.loads(body_text) if body_text and body_text.lstrip().startswith(("{", "[")) else body_text,
                    "step_id": None, "occurrence_index": None,
                }, result)
            return result
        except OSError as error:
            if self.response_transform is not None and self._evaluation_setup is not None:
                context, endpoint = self._evaluation_setup
                self._transform_response(context, {"phase": "setup", **endpoint, "method": method,
                    "path": urlsplit(url).path, "query_string": urlsplit(url).query,
                    "step_id": None, "occurrence_index": None}, error)
            raise RelationExecutionError("local_http_transport_failed") from error

    def _login(self, base_url: str, email: str, password: str, auth: Any) -> Any:
        _require_loopback_url(base_url)
        return login_auth(base_url, email, password, auth)

    def _reset_for_replay(self) -> dict[str, Any]:
        if self.run_root is None or self.profile.reset is None:
            raise RuntimeError("local reset requested before target start")
        command = list(self.profile.reset.command or [])
        if not command:
            raise RuntimeError("local HTTP current runtime requires reset.command")
        self._reset_counter += 1
        reset_path = self.run_root / "runtime" / "resets" / f"reset-{self._reset_counter:04d}.json"
        reset_path.parent.mkdir(parents=True, exist_ok=True)
        if "--output" in command:
            index = command.index("--output")
            if index + 1 >= len(command):
                raise RuntimeError("profile reset --output has no value")
            command[index + 1] = str(reset_path)
        else:
            command.extend(["--output", str(reset_path)])
        reset_env = self._reset_env()
        try:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                env=reset_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
        except subprocess.TimeoutExpired as error:
            completed = None
            process_error: BaseException | None = error
        else:
            process_error = None
        value = _read_reset_record(reset_path)
        if completed is None or completed.returncode != 0:
            failure = value.get("failure") if isinstance(value, dict) else None
            phase = str(
                failure.get("phase") or "reset_subprocess"
                if isinstance(failure, Mapping)
                else "reset_subprocess"
            )
            reason_code = str(
                failure.get("reason_code") or "subprocess_exit_nonzero"
                if isinstance(failure, Mapping)
                else (
                    "subprocess_timeout"
                    if completed is None
                    else "subprocess_exit_nonzero"
                )
            )
            stdout = (
                getattr(process_error, "stdout", b"")
                if completed is None
                else completed.stdout
            )
            stderr = (
                getattr(process_error, "stderr", b"")
                if completed is None
                else completed.stderr
            )
            diagnostic = {
                "artifact_type": "local_target_reset_failure",
                "phase": phase,
                "reason_code": reason_code,
                "exit_code": None if completed is None else completed.returncode,
                "stdout": _bounded_reset_diagnostic(stdout, reset_env),
                "stderr": _bounded_reset_diagnostic(stderr, reset_env),
                "reset_record": _sanitized_reset_record(value, reset_env),
            }
            failure_path = reset_path.with_suffix(".failure.json")
            temporary = failure_path.with_suffix(failure_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(diagnostic, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(temporary, failure_path)
            raise RuntimeError(
                f"local_reset_failed:{phase}:{reason_code}"
            ) from process_error
        if not isinstance(value, dict):
            raise RuntimeError("local reset artifact is missing")
        if not isinstance(value, dict) or not 200 <= int(value.get("status", 0)) < 300:
            raise RuntimeError("local reset artifact is incomplete")
        verify = self.profile.reset.verify_request
        verify_result = self._send(
            verify.method,
            verify.path,
            {},
            {},
            None,
        )
        if verify_result.status != verify.expect_status:
            raise RuntimeError("local reset verification failed")
        digest = _sha_file(reset_path)
        epoch = f"{value.get('reset_epoch_ref', 'local-reset')}:{self._reset_counter:04d}"
        ref = {
            "artifact_type": "local_target_reset",
            "run_id": self.run_id,
            "record_id": epoch,
            "reset_artifact_ref": reset_path.relative_to(self.run_root).as_posix(),
            "reset_artifact_sha256": digest,
        }
        self._last_full_reset_ref = ref
        self.counts["reset_runs"] += 1
        self.counts["real_reset_runs"] += 1
        aliases = _compose_recording_material_aliases(
            self.recording_material_aliases,
            tuple(copy.deepcopy(value.get("material_aliases", []))),
        )
        return {
            **ref,
            "material_aliases": aliases,
        }

    def _wait_for_health(self) -> None:
        deadline = time.monotonic() + 60
        pending = list(self.runtime.health_probes)
        while pending and time.monotonic() < deadline:
            next_pending = []
            for probe in pending:
                if any(process.poll() is not None for process in self.processes):
                    raise RuntimeError("local target process exited before health")
                try:
                    result = send("GET", probe.url, timeout=2)
                except Exception:
                    next_pending.append(probe)
                    continue
                if result.status != probe.expect_status:
                    next_pending.append(probe)
            pending = next_pending
            if pending:
                time.sleep(0.2)
        if pending:
            raise RuntimeError("local target health deadline exceeded")

    def _target_env(self) -> dict[str, str]:
        return dict(self.runtime.environment)

    def _reset_env(self) -> dict[str, str]:
        environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONPATH": f"{self.repo_root / 'src'}:{self.repo_root}",
            "NO_PROXY": "localhost,127.0.0.1,::1",
            "no_proxy": "localhost,127.0.0.1,::1",
        }
        environment.update(
            {
                name: value
                for name, value in self.runtime.environment.items()
                if name.startswith("UISEMTEST_")
            }
        )
        return environment


class LocalHttpCurrentRouteSRuntime:
    def temporal_wait_until(self, context: _HttpArmContext, deadline_ns: int) -> None:
        del context
        remaining = deadline_ns - time.monotonic_ns()
        if remaining > 0:
            time.sleep(remaining / 1_000_000_000)

    def __init__(
        self,
        core: _LocalHttpExecutionCore,
        material: RouteSPreLiveMaterializedCandidate,
    ) -> None:
        self.core = core
        self.material = material
        self._sessions: list[dict[str, Any]] = []
        self._contexts: list[_HttpArmContext] = []
        self._started_counts = Counter(core.counts)

    def begin_arm(
        self,
        material: RouteSPreLiveMaterializedCandidate,
        arm: str,
    ) -> tuple[Any, dict[str, Any], dict[str, bytes]]:
        if material.candidate_id != self.material.candidate_id:
            raise ValueError("local Route-S material drift")
        slot = (
            f"{arm}_reset" if arm in {"repeat_once", "repeat_twice"}
            else
            "workflow_reset" if arm == "workflow"
            else "Rc" if arm == "control"
            else "Rt"
        )
        context = self.core.begin_arm(material, arm)
        if self.core.run_root is None:
            raise RuntimeError("local reset artifact requested outside run root")
        reset_path = (
            self.core.run_root / context.full_reset_ref["reset_artifact_ref"]
        ).resolve(strict=True)
        reset_bytes = reset_path.read_bytes()
        if hashlib.sha256(reset_bytes).hexdigest() != context.full_reset_ref[
            "reset_artifact_sha256"
        ]:
            raise RuntimeError("local reset artifact hash drift")
        reset_ref = f"M12/{material.candidate_id}/raw/{slot}.target-reset.json"
        context.full_reset_ref["reset_artifact_ref"] = reset_ref
        self._contexts.append(context)
        raw_value = {
            "reset_ref": {
                **context.full_reset_ref,
                "reset_epoch": context.reset_epoch,
                "resource_binding_plan": copy.deepcopy(
                    material.resource_binding_plans[arm]
                ),
            }
        }
        ref, raw = _raw(material.candidate_id, slot, raw_value)
        record = _pass_record(slot, arm, ref, raw)
        record["reset_epoch"] = context.reset_epoch
        actors = {
            material.candidate["consumer"]["actor_id"],
            *(row["actor_id"] for row in material.candidate["setup"]),
        }
        if material.candidate.get("producer") is not None:
            actors.add(material.candidate["producer"]["actor_id"])
        for actor in sorted(actors):
            stem = f"{material.candidate_id}:{arm}:{actor}:{context.reset_epoch}"
            self._sessions.append(
                {
                    "arm": arm,
                    "actor_id": actor,
                    "reset_epoch": context.reset_epoch,
                    "materialization_id": f"local-http-session:{_sha(stem)[:24]}",
                    "ownership_domain_sha256": _sha(f"ownership:{stem}"),
                    "jar_ownership_sha256": _sha(f"jar:{stem}"),
                    "mutation_domain_sha256": _sha(f"mutation:{stem}"),
                    "secret_values_present": False,
                }
            )
        return context, record, {ref: raw, reset_ref: reset_bytes}

    def execute_setup(
        self,
        context: _HttpArmContext,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        try:
            rows = self.core.execute_setup(context)
        except (
            BaselineRequestShapeLossError,
            RelationExecutionError,
            ResourceRebindingError,
            UnresolvedRequestMaterialError,
        ) as error:
            if not _is_candidate_local_slot_error(error):
                raise
            detail = str(error) if error.__cause__ is None else f"{error}: {error.__cause__}"
            return _failed_slot(context, slot, type(error).__name__, detail=detail)
        raw_ref, raw = _raw(context.candidate_id, slot, {"setup": rows})
        artifacts: dict[str, bytes] = {raw_ref: raw}
        provenance = []
        for index, row in enumerate(rows, start=1):
            ref = f"M12/{context.candidate_id}/raw/{slot}.setup-{index:02d}.json"
            payload = canonical_json_bytes(
                {
                    "actor_id": row["actor_id"],
                    "request_ref": row["request_ref"],
                    "status": "pass",
                }
            )
            artifacts[ref] = payload
            provenance.append(ref)
        if any(not 200 <= row["status"] < 300 for row in rows):
            return _failed_slot(
                context,
                slot,
                "setup_http_unsuccessful",
                raw_ref=raw_ref,
                raw=raw,
                artifacts=artifacts,
            )
        record = _pass_record(slot, context.arm, raw_ref, raw)
        record["provenance_refs"] = provenance
        return record, artifacts

    def observe(
        self,
        context: _HttpArmContext,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        return self._observe(context, slot, slot)

    def _observe(
        self,
        context: _HttpArmContext,
        binding_slot: str,
        record_slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        binding = context.material.execution_binding["payload"]["observations"][
            binding_slot
        ]
        request_ref = str(
            binding.get("request_ref")
            or context.material.candidate["consumer"]["request_ref"]
        )
        try:
            before = self.core.snapshot(context, binding["actor_id"])
            result = self.core.execute_endpoint(
                context,
                actor_id=binding["actor_id"],
                request_ref=request_ref,
                method=binding["method"],
                expected_path=binding["path"],
                step_id=record_slot,
            )
            after = self.core.snapshot(context, binding["actor_id"])
        except (
            BaselineRequestShapeLossError,
            RelationExecutionError,
            ResourceRebindingError,
            UnresolvedRequestMaterialError,
        ) as error:
            if not _is_candidate_local_slot_error(error):
                raise
            return _failed_slot(
                context, record_slot,
                "local_http_response_json_invalid"
                if isinstance(error, RelationExecutionError)
                and str(error) == "local_http_response_json_invalid"
                else type(error).__name__,
                detail=str(error),
            )
        domains, artifacts = self.core.capability_artifacts(
            context,
            slot=record_slot,
            actor_id=binding["actor_id"],
            before=before,
            after=after,
        )
        raw_ref, raw = _raw(
            context.candidate_id,
            record_slot,
            {
                "request": result["transport_request"],
                "query": result["transport_metadata"]["query"],
                "response": {
                    "status": result["status"],
                    "body": result["body"],
                },
            },
        )
        artifacts[raw_ref] = raw
        primary = context.material.candidate["primary_predicate"]
        accepted_resource_absence = (primary.get("family") == "P01" and int(result["status"]) in primary.get("absent_statuses", []) and binding_slot not in {"workflow_before", "actor_before"}
            or context.material.candidate["contract_kind"] == "C12" and primary["family"] == "P02" and context.arm == "actor_matrix" and 400 <= int(result["status"]) < 500)
        if not (200 <= int(result["status"]) < 300 or accepted_resource_absence):
            return _failed_slot(
                context,
                record_slot,
                f"observer_http_status_{int(result['status'])}",
                raw_ref=raw_ref,
                raw=raw,
                artifacts=artifacts,
            )
        record = _pass_record(record_slot, context.arm, raw_ref, raw)
        record.update({"checkpoint_id": record_slot, "reset_epoch": context.reset_epoch})
        if context.arm == "temporal":
            record["timing"] = dict(result.get("timing", {}))
        record.update(
            {
                "actor_id": binding["actor_id"],
                "request_ref": request_ref,
                "request": result["transport_request"],
                "physical_transport_request": result["physical_transport_request"],
                "transport_request_shape_sha256": result[
                    "transport_request_shape_sha256"
                ],
                "response": copy_numeric_sources(result, {"status": result["status"], "body": result["body"]}),
                "observer_domains": domains,
                "binding_events": result["resource_binding_events"],
                "fresh_capture_events": result["fresh_capture_events"],
                "fresh_capture_error": result["fresh_capture_error"],
                "transport_metadata": result["transport_metadata"],
                "physical_transport_metadata": result[
                    "physical_transport_metadata"
                ],
                "redaction_manifest": result["redaction_manifest"],
            }
        )
        return copy_numeric_sources(result, record), artifacts

    def execute_producer(
        self,
        context: _HttpArmContext,
        *,
        allow_client_error: bool = False,
        occurrence_index: int | None = None,
        repeated: bool = False,
        action_role: str = "producer",
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        binding = context.material.execution_binding["payload"][action_role]
        request_ref = binding.get("request_ref", context.material.candidate["producer"]["request_ref"])
        slot = f"{'A' if context.arm == 'repeat_once' else 'B'}_action{occurrence_index}" if repeated else "P" if action_role == "producer" else action_role
        try:
            result = self.core.execute_endpoint(
                context,
                actor_id=binding["actor_id"],
                request_ref=request_ref,
                method=binding["method"],
                expected_path=binding["path"],
                step_id=slot,
                occurrence_index=occurrence_index,
                repeated=repeated,
            )
        except (
            BaselineRequestShapeLossError,
            RelationExecutionError,
            ResourceRebindingError,
            UnresolvedRequestMaterialError,
        ) as error:
            if not _is_candidate_local_slot_error(error):
                raise
            return _failed_slot(context, slot, type(error).__name__, detail=str(error))
        raw_ref, raw = _raw(
            context.candidate_id,
            slot,
            {
                "transport_request": result["transport_request"],
                "query": result["transport_metadata"]["query"],
                "response": {
                    "status": result["status"],
                    "body": result["body"],
                },
            },
        )
        status = int(result["status"])
        if not (
            200 <= status < 300
            or allow_client_error and 400 <= status < 500
        ):
            return _failed_slot(
                context,
                slot,
                f"producer_http_status_{int(result['status'])}",
                raw_ref=raw_ref,
                raw=raw,
            )
        record = _pass_record(slot, context.arm, raw_ref, raw)
        record.update(
            {
                "actor_id": binding["actor_id"],
                "action_ref": binding.get("action_ref"),
                "checkpoint_id": slot,
                "occurrence_index": occurrence_index,
                "reset_epoch": context.reset_epoch,
                "request_identity_verified": result["request_identity_verified"],
                "request_fields": {**copy.deepcopy(result["physical_transport_request"]), "query": copy.deepcopy(result["physical_transport_metadata"]["query"]), "headers": copy.deepcopy(result["physical_transport_metadata"]["request_headers"])},
                "request_ref": request_ref,
                "request": copy.deepcopy(result["semantic_request_body"]),
                "transport_request": result["transport_request"],
                "physical_transport_request": result["physical_transport_request"],
                "transport_request_shape_sha256": result[
                    "transport_request_shape_sha256"
                ],
                "response": copy.deepcopy(result["body"]),
                "transport_status": result["status"],
                "transport_metadata": result["transport_metadata"],
                "physical_transport_metadata": result[
                    "physical_transport_metadata"
                ],
                "binding_events": result["resource_binding_events"],
                "fresh_capture_events": result["fresh_capture_events"],
                "fresh_capture_error": result["fresh_capture_error"],
                "redaction_manifest": result["redaction_manifest"],
            }
        )
        if context.arm == "temporal":
            record["timing"] = dict(result.get("timing", {}))
        return copy_numeric_sources(result, record), {raw_ref: raw}

    def execute_negative_producer(
        self, context: _HttpArmContext, **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        return self.execute_producer(context, allow_client_error=True, **kwargs)

    def execute_inverse(self, context: _HttpArmContext) -> tuple[dict[str, Any], dict[str, bytes]]:
        return self.execute_producer(context, action_role="inverse")

    def verify_identity_topology(self, context: _HttpArmContext, topology: Mapping[str, Any]) -> bool:
        return self.core.verify_identity_topology(context, topology)

    def negative_session_boundary(
        self, context: _HttpArmContext
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        shape = context.material.execution_material["protocol_shape"]
        boundary = shape.get("session_boundary") or {}
        actor_id = str(context.material.candidate["producer"]["actor_id"])
        session = context.replay.sessions.get(actor_id)
        if (
            boundary.get("kind") not in {
                "recorded_logout_and_runtime_auth_absence",
                "recorded_auth_preserved",
            }
            or boundary.get("negative_request_ref")
            != context.material.candidate["producer"]["request_ref"]
            or session is None
        ):
            return _failed_slot(
                context, "negative_session_boundary", "session_boundary_unclosed"
            )
        material_present = any(
            str(session.headers.get(name) or "")
            for name in ("Authorization", "Cookie")
        )
        auth_absent = boundary.get("kind") == "recorded_logout_and_runtime_auth_absence"
        boundary_ok = not material_present if auth_absent else material_present
        raw_ref, raw = _raw(
            context.candidate_id,
            "negative_session_boundary",
            {
                "actor_id": actor_id,
                "recorded_boundary_event_id": boundary.get("event_id"),
                "authorization_material_absent": not material_present,
                "secret_values_persisted": False,
            },
        )
        if not boundary_ok:
            return _failed_slot(
                context,
                "negative_session_boundary",
                "original_auth_material_present",
                raw_ref=raw_ref,
                raw=raw,
            )
        record = _pass_record(
            "negative_session_boundary", context.arm, raw_ref, raw
        )
        record["authorization_material_absent"] = not material_present
        return record, {raw_ref: raw}

    def observe_until_stable(
        self,
        context: _HttpArmContext,
        settle_slot: str,
        observer_slot: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        policy = context.material.settle_policy
        artifacts: dict[str, bytes] = {}

        def observe(poll_index: int) -> Mapping[str, Any]:
            record, rows = self._observe(
                context,
                observer_slot,
                f"{observer_slot}.poll-{poll_index:02d}",
            )
            artifacts.update(rows)
            return record

        outcome = poll_semantic_stability(
            policy,
            observe,
            observer_is_pure=route_observer_is_pure,
        )
        raw_ref, raw = _raw(
            context.candidate_id,
            settle_slot,
            {
                "policy": policy,
                "status": outcome.status,
                "elapsed_ns": outcome.elapsed_ns,
                "poll_count": outcome.poll_count,
                "consecutive_identical": outcome.consecutive_identical,
                "projection_sha256": outcome.projection_sha256,
            },
        )
        artifacts[raw_ref] = raw
        if outcome.status == "stable":
            record = _pass_record(settle_slot, context.arm, raw_ref, raw)
        else:
            record, rows = _failed_slot(
                context,
                settle_slot,
                outcome.status,
                raw_ref=raw_ref,
                raw=raw,
                artifacts=artifacts,
            )
            artifacts.update(rows)
        external_policy_refs = tuple(
            ref
            for ref in context.material.artifact_bytes
            if ref.endswith("/settle_policy.json")
        )
        if context.material.artifact_inventory:
            if len(external_policy_refs) != 1:
                raise RuntimeError("settle_policy_artifact_not_unique")
            policy_ref = external_policy_refs[0]
        else:
            if external_policy_refs:
                raise RuntimeError("compact_settle_policy_artifact_unexpected")
            policy_ref = "execution_material:settle_policy"
        record.update(
            {
                "policy_ref": policy_ref,
                "policy_sha256": (
                    context.material.artifact_hashes[policy_ref]
                    if context.material.artifact_inventory
                    else None
                ),
                "policy": copy.deepcopy(policy),
                "elapsed_ns": outcome.elapsed_ns,
                "poll_count": outcome.poll_count,
                "consecutive_identical": outcome.consecutive_identical,
                "projection_sha256": outcome.projection_sha256,
            }
        )
        self.core.counts["settle_executions"] += 1
        if outcome.final_observation is None or outcome.status == "settle_timeout":
            final_observation = {
                "slot": observer_slot,
                "state": "not_executed",
                "reason_code": outcome.status,
            }
        else:
            final_observation = copy.deepcopy(outcome.final_observation)
            final_observation["slot"] = observer_slot
            poll_ref = str(final_observation["raw_ref"])
            poll_payload = artifacts.get(poll_ref)
            if poll_payload is None:
                raise ValueError("stable observer poll artifact is missing")
            final_ref = f"M12/{context.candidate_id}/raw/{observer_slot}.json"
            artifacts[final_ref] = poll_payload
            final_observation["raw_ref"] = final_ref
            final_observation["raw_sha256"] = hashlib.sha256(
                poll_payload
            ).hexdigest()
        return record, final_observation, artifacts

    def sessions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._sessions)

    def counts(self) -> dict[str, int]:
        current = Counter(self.core.counts)
        result = {
            key: current[key] - self._started_counts[key]
            for key in _RUNTIME_COUNT_KEYS
        }
        result["real_target_runs"] = current["real_target_runs"]
        result["real_server_runs"] = current["real_server_runs"]
        return result

    def sensitive_values_in_memory(self) -> tuple[str, ...]:
        values = {
            value
            for context in self._contexts
            for value in context.sensitive_values
            if value
        }
        values.update(
            value
            for context in self._contexts
            for value in context.removed_sensitive_values
            if value and value.casefold() not in {"true", "false", "null", "none"}
        )
        return tuple(sorted(values, key=lambda item: (-len(item), item)))

    def prepare_producer(self, context: _HttpArmContext) -> dict[str, Any]:
        return self.core.prepare_producer(context)

    def evaluate_in_memory_predicate(
        self,
        context: _HttpArmContext,
        predicate: Mapping[str, Any],
    ) -> tuple[bool, dict[str, bool]] | None:
        return self.core.evaluate_in_memory_predicate(context, predicate)


class LocalHttpCalibrationRuntime:
    def temporal_wait_until(self, context: _HttpArmContext, deadline_ns: int) -> None:
        del context
        remaining = deadline_ns - time.monotonic_ns()
        if remaining > 0:
            time.sleep(remaining / 1_000_000_000)

    def __init__(
        self,
        core: _LocalHttpExecutionCore,
        *,
        materials: Mapping[str, RouteSPreLiveMaterializedCandidate],
        blueprints: Mapping[str, Mapping[str, Any]],
        protocol_kinds: Mapping[str, str],
    ) -> None:
        self.core = core
        self.materials = dict(materials)
        self.blueprints = copy.deepcopy(dict(blueprints))
        self.protocol_kinds = dict(protocol_kinds)
        self.started_counts = Counter(core.counts)

    def begin_arm(
        self, candidate_id: str, arm: str
    ) -> tuple[_HttpArmContext, dict[str, Any]]:
        valid_arms = ({"repeat_once", "repeat_twice"} if self.protocol_kinds.get(candidate_id) == "V5" and self.blueprints[candidate_id].get("repetition_kind") == "repeat_equal" else {"repeat_twice"} if self.protocol_kinds.get(candidate_id) == "V5" else {calibration_arm_for_protocol(self.protocol_kinds[candidate_id])} if candidate_id in self.materials else set())
        if candidate_id not in self.materials or arm not in valid_arms:
            raise RelationExecutionError("local_calibration_candidate_or_arm_unknown")
        context = self.core.begin_arm(self.materials[candidate_id], arm)
        return context, copy.deepcopy(context.full_reset_ref)

    def execute_setup(
        self,
        context: _HttpArmContext,
        setup: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        expected = self.blueprints[context.candidate_id]["setup"]
        if setup != expected:
            raise RelationExecutionError("local_calibration_setup_drift")
        return self.core.execute_setup(context)

    def execute(
        self,
        context: _HttpArmContext,
        endpoint: dict[str, str],
        *, step_id: str | None = None, occurrence_index: int | None = None, repeated: bool = False,
    ) -> dict[str, Any]:
        return self.core.execute_endpoint(
            context,
            actor_id=endpoint["actor_id"],
            request_ref=endpoint["request_ref"],
            method=endpoint["method"],
            expected_path=endpoint["path"],
            step_id=step_id, occurrence_index=occurrence_index, repeated=repeated,
        )

    def verify_negative_session_boundary(
        self,
        context: _HttpArmContext,
        boundary: Mapping[str, Any],
    ) -> bool:
        actor_id = str(
            self.blueprints[context.candidate_id]["producer"]["actor_id"]
        )
        session = context.replay.sessions.get(actor_id)
        return (
            context.arm == "negative_no_effect"
            and boundary.get("kind") in {"recorded_logout_and_runtime_auth_absence", "recorded_auth_preserved"}
            and boundary.get("negative_request_ref")
            == self.blueprints[context.candidate_id]["producer"]["request_ref"]
            and session is not None
            and bool(any(
                str(session.headers.get(name) or "")
                for name in ("Authorization", "Cookie")
            )) == (boundary.get("kind") == "recorded_auth_preserved")
        )

    def verify_identity_topology(self, context: _HttpArmContext, topology: Mapping[str, Any]) -> bool:
        return self.core.verify_identity_topology(context, topology)

    def snapshot(
        self, context: _HttpArmContext, actor_id: str
    ) -> dict[str, str | None]:
        snapshot = self.core.snapshot(context, actor_id)
        return {
            domain: (
                value
                if value is not None or domain not in {"cache", "last_seen"}
                else _sha(f"current-local-calibration:not-applicable:{domain}")
            )
            for domain, value in snapshot.items()
        }

    def settle_monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def settle_sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def record_settle(self) -> None:
        self.core.counts["settle_executions"] += 1

    def counts(self) -> dict[str, int]:
        current = Counter(self.core.counts)
        result = {
            key: current[key] - self.started_counts[key]
            for key in _RUNTIME_COUNT_KEYS
        }
        result["real_target_runs"] = current["real_target_runs"]
        result["real_server_runs"] = current["real_server_runs"]
        return result

    def prepare_producer(self, context: _HttpArmContext) -> dict[str, Any]:
        return self.core.prepare_producer(context)

    def evaluate_in_memory_predicate(
        self,
        context: _HttpArmContext,
        predicate: Mapping[str, Any],
    ) -> tuple[bool, dict[str, bool]] | None:
        return self.core.evaluate_in_memory_predicate(context, predicate)


class LocalHttpCurrentRuntimeFactory:
    runtime_kind = "local_http"

    def __init__(
        self,
        bundle: CurrentAdapterBundle,
        *,
        run_id: str,
        request_bindings: Mapping[str, Any],
        trace: UiApiTrace,
        recording_material_aliases: tuple[dict[str, Any], ...],
        recorded_bundles: Mapping[str, LoadedBundle] | None = None,
    ) -> None:
        self.core = _LocalHttpExecutionCore(
            bundle,
            run_id=run_id,
            request_bindings=request_bindings,
            trace=trace,
            recording_material_aliases=recording_material_aliases,
            recorded_bundles=recorded_bundles,
        )
        self.materials: dict[str, RouteSPreLiveMaterializedCandidate] = {}
        self.runtimes: list[LocalHttpCurrentRouteSRuntime] = []

    def preflight(self) -> None:
        self.core.preflight()

    def start(self, *, run_root: Path) -> None:
        self.core.start(run_root)

    def route_s_runtime(
        self, material: RouteSPreLiveMaterializedCandidate
    ) -> LocalHttpCurrentRouteSRuntime:
        if material.candidate_id in self.materials:
            raise ValueError("local Route-S candidate requested more than once")
        self.materials[material.candidate_id] = material
        runtime = LocalHttpCurrentRouteSRuntime(self.core, material)
        self.runtimes.append(runtime)
        return runtime

    def assert_route_s_complete(self, expected_candidates: int) -> None:
        if len(self.materials) != expected_candidates:
            raise ValueError("local Route-S runtime count does not close candidates")

    def calibration_runtime(
        self, suite: Mapping[str, Any]
    ) -> LocalHttpCalibrationRuntime:
        blueprints = {
            str(test["candidate_id"]): copy.deepcopy(test["blueprint"])
            for test in suite["tests"]
        }
        protocol_kinds = {
            str(test["candidate_id"]): str(test["protocol_kind"])
            for test in suite["tests"]
        }
        missing = set(blueprints) - set(self.materials)
        if missing:
            raise ValueError("local calibration material is missing confirmed candidates")
        return LocalHttpCalibrationRuntime(
            self.core,
            materials={key: self.materials[key] for key in blueprints},
            blueprints=blueprints,
            protocol_kinds=protocol_kinds,
        )

    def auth_session_runtime(self) -> Any:
        from .auth_session_stratum import _LocalAuthSessionRuntime

        return _LocalAuthSessionRuntime(self.core)

    def route_s_counts(self) -> dict[str, int]:
        return {key: self.core.counts[key] for key in _RUNTIME_COUNT_KEYS}

    def teardown(self) -> None:
        self.core.teardown()


def _alias_source_key(row: Mapping[str, Any]) -> tuple[str | None, type, Any, bool]:
    logical = row.get("logical_value")
    try:
        hash(logical)
    except TypeError as error:
        raise ValueError("material alias logical value must be scalar") from error
    actor = row.get("actor_id")
    if actor is not None and (not isinstance(actor, str) or not actor):
        raise ValueError("material alias actor must be a nonblank string")
    normalize = row.get("normalize_response")
    if not isinstance(normalize, bool):
        raise ValueError("material alias normalization policy must be boolean")
    required = {"logical_value", "runtime_value", "normalize_response"}
    if actor is not None:
        required.add("actor_id")
    if set(row) != required:
        raise ValueError("material alias has an invalid shape")
    return actor, type(logical), logical, normalize


def _compose_recording_material_aliases(
    recording_aliases: tuple[dict[str, Any], ...],
    live_aliases: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Translate exact recorded reset values to one fresh reset epoch."""

    recorded_by_key: dict[tuple[str | None, type, Any, bool], list[dict[str, Any]]] = {}
    live_by_key: dict[tuple[str | None, type, Any, bool], list[dict[str, Any]]] = {}
    for row in recording_aliases:
        recorded_by_key.setdefault(_alias_source_key(row), []).append(row)
    for row in live_aliases:
        live_by_key.setdefault(_alias_source_key(row), []).append(row)
    if set(recorded_by_key) != set(live_by_key):
        raise ValueError("recording and live reset material aliases do not close")

    result: list[dict[str, Any]] = []
    for key, recorded_rows in recorded_by_key.items():
        fresh_rows = live_by_key[key]
        recorded_values = list(
            dict.fromkeys(
                (type(row["runtime_value"]), row["runtime_value"])
                for row in recorded_rows
            )
        )
        fresh_values = list(
            dict.fromkeys(
                (type(row["runtime_value"]), row["runtime_value"])
                for row in fresh_rows
            )
        )
        if len(recorded_values) != 1:
            raise ValueError("recording reset material alias source is not unique")
        if len(fresh_values) != 1:
            raise ValueError("live reset material alias target is not unique")
        recorded_type, recorded_value = recorded_values[0]
        actor, _logical_type, _logical_value, normalize = key
        for fresh_type, fresh_value in fresh_values:
            if fresh_type is not recorded_type:
                raise ValueError("recording and live material alias types differ")
            row: dict[str, Any] = {
                "logical_value": copy.deepcopy(recorded_value),
                "runtime_value": copy.deepcopy(fresh_value),
                "normalize_response": normalize,
            }
            if actor is not None:
                row["actor_id"] = actor
            result.append(row)
    return tuple(result)


def _seed_binding_sources_from_reset_aliases(
    context: _HttpArmContext,
    request_bindings: Mapping[str, Any],
) -> None:
    """Use one exact reset alias before replaying an order-unstable creator.

    The alias rows already close a recorded reset value to the current reset
    epoch.  They may replace a fresh creator capture only when the binding
    source's recorded scalar hash and actor scope select exactly one row.
    """

    for source in context.binding_plan.sources:
        if not _response_path_depends_on_reset_alias(
            source,
            context.replay.material_aliases,
        ):
            continue
        matching_uses = [
            row
            for row in context.binding_plan.uses
            if row.source_id == source.source_id
        ]
        if matching_uses:
            recorded_values = {
                (
                    type(value),
                    json.dumps(value, ensure_ascii=False, sort_keys=True),
                ): value
                for use in matching_uses
                for value in (
                    _target_value(
                        request_bindings[use.consumer_request_ref],
                        use.location,
                        use.target_path,
                    ),
                )
                if scalar_sha256(value) == source.recorded_value_sha256
            }
            if len(recorded_values) != 1:
                continue
            recorded = next(iter(recorded_values.values()))
        else:
            recorded = _projection_identity_value(
                context.material.candidate,
                source.recorded_value_sha256,
            )
        rows = [
            row
            for row in context.replay.material_aliases
            if row.get("actor_id") in {None, source.actor_id}
            and type(row.get("logical_value")) is type(recorded)
            and row.get("logical_value") == recorded
        ]
        fresh = {
            (
                type(row.get("runtime_value")),
                json.dumps(
                    row.get("runtime_value"),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ): row.get("runtime_value")
            for row in rows
            if scalar_sha256(row.get("logical_value"))
            == source.recorded_value_sha256
        }
        if len(fresh) != 1:
            continue
        fresh_value = next(iter(fresh.values()))
        context.fresh_values[source.source_id] = copy.deepcopy(fresh_value)
        context.response_value_aliases[source.source_id] = (
            copy.deepcopy(fresh_value),
            copy.deepcopy(recorded),
        )
        context.reset_alias_source_events[source.source_id] = {
            "event": "creator_value_recovered_from_reset_alias",
            "actor_id": source.actor_id,
            "creator_actor_id": source.actor_id,
            "creator_request_ref": source.creator_request_ref,
            "source_typed_path": source.response_path,
            "scalar_type": source.scalar_type,
            "value_sha256": scalar_sha256(fresh_value),
            "source_id": source.source_id,
            "candidate_id": context.candidate_id,
            "arm": context.arm,
            "reset_epoch": context.reset_epoch,
            "binding_scope_id": binding_scope_id(
                context.candidate_id,
                context.arm,
                source.actor_id,
                context.reset_epoch,
            ),
        }


def _response_path_depends_on_reset_alias(
    source: ResourceBindingSource,
    aliases: tuple[dict[str, Any], ...],
) -> bool:
    """Return whether a source path is unstable across a fresh reset.

    Numeric array positions are inherently order-dependent.  An object path
    is reset-dependent only when an *intermediate* member name exactly equals
    one recorded logical value and actor-scoped reset aliases map that value
    to one distinct fresh member name.  Missing or ambiguous member aliases
    remain fail-closed; a normal leaf such as ``$.channel_id`` is never enough.
    """

    if re.search(r"\[[0-9]+\]", source.response_path) is not None:
        return True
    path = source.response_path.strip()
    if not path.startswith("$."):
        return False
    segments = path[2:].split(".")
    if len(segments) < 2 or any(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", segment) is None
        for segment in segments
    ):
        return False
    for member in segments[:-1]:
        rows = [
            row
            for row in aliases
            if row.get("actor_id") in {None, source.actor_id}
            and type(row.get("logical_value")) is str
            and row.get("logical_value") == member
        ]
        if not rows:
            continue
        fresh_members = {
            row.get("runtime_value")
            for row in rows
            if type(row.get("runtime_value")) is str
            and row.get("runtime_value") != member
        }
        if len(fresh_members) != 1:
            return False
        return True
    return False


def _projection_identity_value(
    candidate: Mapping[str, Any], recorded_value_sha256: str
) -> Any:
    predicate = candidate.get("primary_predicate")
    if not isinstance(predicate, Mapping):
        raise ResourceRebindingError("projection identity predicate is missing")
    values: dict[tuple[type, str], Any] = {}
    for side in ("left", "right"):
        ref = predicate.get(side)
        if isinstance(ref, Mapping) and isinstance(ref.get("ref"), Mapping):
            ref = ref["ref"]
        if not isinstance(ref, Mapping):
            continue
        path = str(ref.get("path") or "")
        if not path.startswith("$."):
            continue
        for token in path[2:].split("."):
            if token and scalar_sha256(token) == recorded_value_sha256:
                values[(str, token)] = token
    if len(values) != 1:
        raise ResourceRebindingError("projection identity source is not unique")
    return next(iter(values.values()))


def _predicate_role_ref(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("source") == "role":
        value = value.get("ref")
    return value if isinstance(value, Mapping) else None


def _binding_plan(
    value: Mapping[str, Any],
    request_bindings: Mapping[str, Any],
) -> SetupBindingPlan:
    source_values: dict[str, tuple[str, str]] = {}
    uses: list[ResourceBindingUse] = []
    for row in value["uses"]:
        template = request_bindings.get(str(row["consumer_request_ref"]))
        if not isinstance(template, Mapping):
            raise ValueError("local binding plan request template is missing")
        recorded = _target_value(template, str(row["location"]), str(row["target_path"]))
        digest = scalar_sha256(recorded)
        pair = (str(row["scalar_type"]), digest)
        previous = source_values.setdefault(str(row["source_id"]), pair)
        if previous != pair:
            raise ValueError("local binding plan recorded values disagree")
        uses.append(
            ResourceBindingUse(
                source_id=str(row["source_id"]),
                actor_id=str(row["actor_id"]),
                consumer_request_ref=str(row["consumer_request_ref"]),
                location=str(row["location"]),
                target_path=str(row["target_path"]),
                scalar_type=str(row["scalar_type"]),
                recorded_value_sha256=digest,
            )
        )
    sources = []
    for row in value["sources"]:
        pair = source_values.get(str(row["source_id"]))
        if pair is None:
            digest = str(row.get("recorded_value_sha256") or "")
            scalar_type = str(row["scalar_type"])
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(
                    "normalization-only binding source lacks a recorded value proof"
                )
        else:
            scalar_type, digest = pair
        if scalar_type != row["scalar_type"]:
            raise ValueError("local binding plan source/use type differs")
        witnesses = tuple(
            str(item) for item in row.get("identity_equivalence_request_refs", ())
        )
        primary_witness = str(row["creator_request_ref"])
        if witnesses and (
            len(witnesses) < 2
            or len(set(witnesses)) != len(witnesses)
            or primary_witness not in witnesses
            or any(not item for item in witnesses)
        ):
            raise ValueError("local identity equivalence proof is invalid")
        sources.append(
            ResourceBindingSource(
                source_id=str(row["source_id"]),
                actor_id=str(row["actor_id"]),
                creator_request_ref=str(row["creator_request_ref"]),
                response_path=str(row["response_path"]),
                scalar_type=str(row["scalar_type"]),
                recorded_value_sha256=digest,
                collection_identity=tuple(
                    (
                        str(item["member_path"]),
                        str(item["source_id"]),
                        str(item["scalar_type"]),
                    )
                    for item in row.get("collection_identity", ())
                ),
                collection_identity_shape=tuple(
                    (str(item["member_path"]), str(item["scalar_type"]))
                    for item in row.get("collection_identity_shape", ())
                ),
                transport_encoding=(
                    str(row["transport_encoding"])
                    if "transport_encoding" in row
                    else None
                ),
                identity_equivalence_request_refs=witnesses,
            )
        )
    source_by_id = {source.source_id: source for source in sources}
    if len(source_by_id) != len(sources):
        raise ValueError("local binding plan source ids are not unique")
    for source in sources:
        if bool(source.collection_identity) != bool(source.collection_identity_shape):
            raise ValueError("local collection identity proof is incomplete")
        for _path, proof_id, scalar_type in source.collection_identity:
            proof = source_by_id.get(proof_id)
            if proof is None or proof_id == source.source_id or proof.scalar_type != scalar_type:
                raise ValueError("local collection identity source proof differs")
    return SetupBindingPlan(
        setup_request_refs=tuple(
            dict.fromkeys(
                request_ref
                for source in sources
                for request_ref in (
                    source.identity_equivalence_request_refs
                    or (source.creator_request_ref,)
                )
            )
        ),
        sources=tuple(sources),
        uses=tuple(uses),
        issues=(),
    )


def _target_value(template: Mapping[str, Any], location: str, path: str) -> Any:
    if location == "path":
        if not path.startswith("$.segments[") or not path.endswith("]"):
            raise ValueError("local path binding target is not segment-indexed")
        index = int(path[len("$.segments[") : -1])
        parts = str(template["path"]).strip("/").split("/")
        if index >= len(parts):
            raise ValueError("local path binding target is absent")
        return parts[index]
    root = template.get({"body": "body", "query": "query", "header": "headers"}[location])
    if location in {"query", "header"}:
        if not path.startswith("$.") or not isinstance(root, Mapping):
            raise ValueError("local scalar binding target is not a top-level key")
        name = path[2:]
        if location == "query":
            if name not in root:
                raise ValueError("local query binding target is absent")
            return root[name]
        matches = [key for key in root if str(key).casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError("local header binding target is not unique")
        return root[matches[0]]
    return extract_typed_value(root, path)


def _material_alias_rows(
    context: ReplayContext,
    actor_id: str,
    *,
    reverse: bool,
) -> tuple[tuple[Any, Any], ...]:
    rows = []
    for item in context.material_aliases:
        scoped_actor = item.get("actor_id")
        if scoped_actor is not None and scoped_actor != actor_id:
            continue
        if reverse:
            if item["normalize_response"]:
                rows.append((item["runtime_value"], item["logical_value"]))
        else:
            rows.append((item["logical_value"], item["runtime_value"]))
    return tuple(rows)


def _replace_alias_scalar(value: Any, rows: tuple[tuple[Any, Any], ...]) -> Any:
    for source, target in rows:
        if type(value) is type(source) and value == source:
            return copy.deepcopy(target)
    return value


def _replace_alias_values(
    value: Any,
    rows: tuple[tuple[Any, Any], ...],
    *,
    object_keys: bool = False,
) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            new_key = _replace_alias_scalar(key, rows) if object_keys else key
            result[new_key] = _replace_alias_values(
                item, rows, object_keys=object_keys
            )
        return result
    if isinstance(value, list):
        return [
            _replace_alias_values(item, rows, object_keys=object_keys)
            for item in value
        ]
    return _replace_alias_scalar(value, rows)


def _materialize_alias_request(
    context: ReplayContext,
    actor_id: str,
    path: str,
    query: Mapping[str, Any],
    headers: Mapping[str, Any],
    body: Any,
) -> tuple[str, dict[str, Any], dict[str, Any], Any]:
    result = _materialize_alias_values(
        context,
        actor_id,
        path,
        query,
        headers,
        body,
    )
    _assert_no_redacted_request_material(*result)
    return result


def _materialize_alias_values(
    context: ReplayContext,
    actor_id: str,
    path: str,
    query: Mapping[str, Any],
    headers: Mapping[str, Any],
    body: Any,
) -> tuple[str, dict[str, Any], dict[str, Any], Any]:
    rows = _material_alias_rows(context, actor_id, reverse=False)
    segments = path.split("/")
    path = "/".join(str(_replace_alias_scalar(item, rows)) for item in segments)
    return (
        path,
        _replace_alias_values(dict(query), rows),
        _replace_alias_values(dict(headers), rows),
        _replace_alias_values(body, rows),
    )


def _assert_no_redacted_request_material(
    path: str,
    query: Mapping[str, Any],
    headers: Mapping[str, Any],
    body: Any,
) -> None:
    if (
        any(_REDACTED_MATERIAL.fullmatch(segment) for segment in path.split("/"))
        or _contains_redacted_material(query)
        or _contains_redacted_material(headers)
        or _contains_redacted_material(body)
    ):
        raise UnresolvedRequestMaterialError(request_ref=None, entry_index=None)


def _contains_redacted_material(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_redacted_material(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_redacted_material(item) for item in value)
    return isinstance(value, str) and _REDACTED_MATERIAL.fullmatch(value) is not None


def _normalize_alias_response(
    context: ReplayContext,
    actor_id: str,
    value: Any,
) -> Any:
    rows = _material_alias_rows(context, actor_id, reverse=True)
    return _replace_alias_values(value, rows, object_keys=True)


def _normalize_alias_path(
    context: ReplayContext,
    actor_id: str,
    path: str,
) -> str:
    rows = _material_alias_rows(context, actor_id, reverse=True)
    return "/".join(str(_replace_alias_scalar(item, rows)) for item in path.split("/"))


def _apply_missing_collection_defaults(
    value: Any,
    defaults: Mapping[str, list[Any]],
) -> Any:
    result = copy.deepcopy(value)

    def apply(current: Any, tokens: list[str], default: list[Any]) -> None:
        if not tokens:
            return
        token = tokens[0]
        if token == "*":
            children = current.values() if isinstance(current, dict) else current
            if not isinstance(current, (dict, list)):
                return
            for child in children:
                apply(child, tokens[1:], default)
            return
        if not isinstance(current, dict):
            return
        if len(tokens) == 1:
            current.setdefault(token, copy.deepcopy(default))
        elif token in current:
            apply(current[token], tokens[1:], default)

    for path, default in defaults.items():
        apply(result, path.removeprefix("$.").split("."), default)
    return result


def _encode_exact_request_json(value: Any) -> str:
    """Encode verified Decimal leaves without conversion through binary float."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite request number")
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + _encode_exact_request_json(item)
            for key, item in value.items()
        ) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_encode_exact_request_json(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _request_numeric_provenance(wire: Any, source: Any) -> Any:
    if isinstance(wire, dict) and isinstance(source, dict):
        return {key: _request_numeric_provenance(value, source.get(key)) for key, value in wire.items()}
    if isinstance(wire, list) and isinstance(source, list):
        return [_request_numeric_provenance(value, source[index]) for index, value in enumerate(wire)]
    # A serialized old float is not evidence of its original decimal value.
    if type(source) is float:
        return source
    return wire


def _response_body(result: HttpResult) -> Any:
    value = result.json()
    return value if value is not None else result.body_text


def _single_state_response_body(result: HttpResult) -> Any:
    """Preserve every JSON root type, without treating parse failure as a value."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON object key")
            value[key] = item
        return value

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant: {value}")

    try:
        value = json.loads(
            result.body_text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        # Also rejects overflow to infinity from a syntactically numeric exponent.
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise RelationExecutionError("local_http_response_json_invalid") from error
    return value


def _pass_record(slot: str, arm: str, ref: str, payload: bytes) -> dict[str, Any]:
    now = _now()
    return {
        "slot": slot,
        "state": "executed",
        "raw_ref": ref,
        "raw_sha256": hashlib.sha256(payload).hexdigest(),
        "started_at": now,
        "finished_at": now,
        "status": "pass",
        "arm": arm,
    }


def _is_candidate_local_slot_error(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            BaselineRequestShapeLossError,
            ResourceRebindingError,
            UnresolvedRequestMaterialError,
        ),
    ) or (
        isinstance(error, RelationExecutionError)
        and str(error) in {
            "local_http_transport_failed", "local_http_response_json_invalid",
            "local_http_session_reinitialization_failed",
        }
    )


def _failed_slot(
    context: _HttpArmContext,
    slot: str,
    reason: str,
    *,
    raw_ref: str | None = None,
    raw: bytes | None = None,
    artifacts: Mapping[str, bytes] | None = None,
    detail: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    if raw_ref is None or raw is None:
        raw_ref, raw = _raw(
            context.candidate_id,
            slot,
            {"slot": slot, "status": "failed"},
        )
    rows = dict(artifacts or {})
    rows[raw_ref] = raw
    error_ref = f"M12/{context.candidate_id}/raw/{slot}.error.json"
    error_record: dict[str, Any] = {"reason_code": reason, "runtime": "local_http"}
    if detail:
        # Diagnostic text only (exception message); the reason_code stays the
        # typed contract value and the evidence record does not change.
        error_record["detail"] = detail[:2000]
    error = canonical_json_bytes(error_record)
    rows[error_ref] = error
    now = _now()
    return (
        {
            "slot": slot,
            "state": "executed",
            "raw_ref": raw_ref,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "started_at": now,
            "finished_at": now,
            "status": "failed",
            "arm": context.arm,
            "error_ref": error_ref,
            "error_sha256": hashlib.sha256(error).hexdigest(),
            "reason_code": reason,
        },
        rows,
    )


def _raw(candidate_id: str, slot: str, value: Mapping[str, Any]) -> tuple[str, bytes]:
    ref = f"M12/{candidate_id}/raw/{slot}.json"
    return ref, canonical_json_bytes(value)


def _require_loopback_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("current local runtime may call loopback HTTP only")


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = ["LocalHttpCurrentRuntimeFactory"]
