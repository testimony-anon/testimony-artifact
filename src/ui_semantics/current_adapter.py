"""Published, subject-neutral adapter boundary for the current UISemTest run.

The adapter is deliberately execution-only.  Candidate selection, predicates,
Route-S gates/outcomes, relation assertions, calibration decisions, and all
denominators remain owned by the method core.
"""

from __future__ import annotations

from .artifact_relocation import attested_sha256
import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal, Mapping
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from common.contracts import validate_artifact
from stage0_launch.profile import AppProfile, load_app_profile
from stage2_recover.loader import LoadedBundle, load_bundle
from stage6_ground.request_material import (
    input_action_matches_target_path,
)
from stage6_ground.resource_rebinding import extract_typed_value, scalar_sha256

from .contracts import ObservedApiCatalog, ObservedValueFlowSet, UiApiTrace
from .dsl import NumericObservation, with_numeric_body


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AdapterFileRef(_StrictModel):
    path: str = Field(min_length=1)


class DeterministicFixtureRuntimeConfig(_StrictModel):
    kind: Literal["deterministic_fixture"]
    transport_tape: AdapterFileRef


class HealthProbe(_StrictModel):
    url: str = Field(min_length=1)
    expect_status: int = Field(ge=100, le=599)


class LocalHttpRuntimeConfig(_StrictModel):
    kind: Literal["local_http"]
    source_root: str = Field(min_length=1)
    environment: dict[str, str]
    materialize_commands: tuple[tuple[str, ...], ...]
    server_commands: tuple[tuple[str, ...], ...] = Field(min_length=1)
    health_probes: tuple[HealthProbe, ...] = Field(min_length=1)
    teardown_generated_paths: tuple[str, ...]
    loopback_only: Literal[True]
    reset_from_profile: Literal[True]
    independent_arm_sessions: Literal[True]

    @model_validator(mode="after")
    def _commands_and_paths(self) -> "LocalHttpRuntimeConfig":
        commands = (*self.materialize_commands, *self.server_commands)
        if any(not command or any(not part for part in command) for command in commands):
            raise ValueError("local runtime commands must contain nonblank argv")
        for raw in self.teardown_generated_paths:
            _normalized_relative(raw, label="teardown generated path")
        source = Path(self.source_root)
        if not source.is_absolute():
            raise ValueError("local runtime source_root must be absolute")
        if any(
            not key or "=" in key or "\x00" in key + value
            for key, value in self.environment.items()
        ):
            raise ValueError("local runtime environment contains an invalid entry")
        for probe in self.health_probes:
            _require_loopback_http(probe.url)
        return self


SubjectRuntimeConfig = DeterministicFixtureRuntimeConfig | LocalHttpRuntimeConfig


class CurrentRequestBinding(_StrictModel):
    actor_id: str = Field(min_length=1)
    method: Literal["GET", "PUT", "POST", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]
    path: str = Field(pattern=r"^/[^?#]*$")
    body: Any = None
    query: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)


class RequestMappingPolicy(_StrictModel):
    mode: Literal["explicit_adapter", "current_recording_exact"]
    header_policy: Literal["accept_content_type_only"]
    static_headers: dict[str, str] = Field(default_factory=dict)


class FreshMaterializationPolicy(_StrictModel):
    source: Literal["current_observed_value_flow_set"]
    selection: Literal["exact_setup_to_candidate_consumers_v1"]
    allowed_target_locations: tuple[
        Literal["path", "query", "header", "body"], ...
    ] = Field(min_length=1)
    allowed_scalar_types: tuple[
        Literal["string", "integer", "number", "boolean"], ...
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "FreshMaterializationPolicy":
        if len(self.allowed_target_locations) != len(set(self.allowed_target_locations)):
            raise ValueError("fresh target locations must be unique")
        if len(self.allowed_scalar_types) != len(set(self.allowed_scalar_types)):
            raise ValueError("fresh scalar types must be unique")
        return self


class ObserverPolicy(_StrictModel):
    schema_version: Literal["uisemtest-current-observer-policy-v1"]
    purity_domains_exact_set: tuple[
        Literal["cache", "cookie", "last_seen", "token"], ...
    ] = Field(min_length=1)
    request_method_policy: Literal["read_only"]


class SettlePolicy(_StrictModel):
    schema_version: Literal["uisemtest-current-settle-policy-v2"]
    rule: Literal["bounded_semantic_stability_v1"]
    minimum_duration_ms: Literal[500]
    poll_interval_ms: Literal[100]
    consecutive_identical_observations: Literal[3]
    maximum_duration_ms: Literal[2000]


class SensitiveClassification(_StrictModel):
    forbidden_source_refs: tuple[str, ...]
    forbidden_projection_paths: tuple[str, ...]


class CurrentSubjectAdapter(_StrictModel):
    schema_version: Literal["uisemtest-current-subject-adapter-v1"]
    adapter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    subject_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    runtime: SubjectRuntimeConfig = Field(discriminator="kind")
    # Additive optional field (2026-09-20, subject-expansion groundwork): the
    # declarative configuration of the subject-agnostic single-container Docker
    # helper (``subject_adapters.docker_single_local``).  It is deliberately
    # opaque here and ``exclude=True``: the method core never reads it, the
    # helper subprocess re-reads and schema-validates the adapter file itself,
    # and excluding it keeps ``model_dump`` byte-identical for every adapter
    # written before the field existed.
    docker_single: dict[str, Any] | None = Field(default=None, exclude=True)
    request_mapping: RequestMappingPolicy
    missing_collection_defaults: dict[str, list[Any]] = Field(default_factory=dict)
    request_bindings: dict[str, CurrentRequestBinding]
    fresh_materialization_policy: FreshMaterializationPolicy
    observer_policy: ObserverPolicy
    settle_policy: SettlePolicy
    sensitive_classification: SensitiveClassification

    @model_validator(mode="after")
    def _closed_collections(self) -> "CurrentSubjectAdapter":
        if any(value for value in self.missing_collection_defaults.values()):
            raise ValueError("missing collection defaults must be empty collections")
        if self.request_mapping.mode == "explicit_adapter" and not self.request_bindings:
            raise ValueError("explicit request mapping requires request bindings")
        if self.request_mapping.mode == "current_recording_exact" and self.request_bindings:
            raise ValueError("recording-exact request mapping cannot carry duplicate templates")
        domains = self.observer_policy.purity_domains_exact_set
        if len(domains) != len(set(domains)):
            raise ValueError("observer purity domains must be unique")
        if set(domains) != {
            "cache", "cookie", "last_seen", "token"
        }:
            raise ValueError("observer purity domains must match the frozen Route-S set")
        forbidden_sources = self.sensitive_classification.forbidden_source_refs
        if len(forbidden_sources) != len(set(forbidden_sources)):
            raise ValueError("forbidden source refs must be unique")
        forbidden_paths = self.sensitive_classification.forbidden_projection_paths
        if len(forbidden_paths) != len(set(forbidden_paths)):
            raise ValueError("forbidden projection paths must be unique")
        return self


@dataclass(frozen=True)
class CurrentAdapterBundle:
    profile: AppProfile
    profile_path: Path
    profile_sha256: str
    adapter: CurrentSubjectAdapter
    adapter_path: Path
    adapter_sha256: str
    fixture_tape: dict[str, Any] | None
    fixture_tape_path: Path | None


_SCIENTIFIC_KEYS = frozenset({
    "candidate", "candidate_id", "candidate_selection", "predicate", "phi",
    "route_s_gate", "route_s_gates", "gate", "gates", "outcome", "verdict",
    "confirmed", "effect_absent", "inconclusive", "retained", "dropped",
    "denominator", "calibration_status", "assertion_verdict",
})


def load_current_adapter(profile_path: Path, adapter_path: Path) -> CurrentAdapterBundle:
    """Load the formal AppProfile and the published current adapter contract."""

    profile_source = profile_path.resolve(strict=True)
    adapter_source = adapter_path.resolve(strict=True)
    profile = _resolve_profile_runtime(load_app_profile(profile_source))
    adapter_raw = _read_object(adapter_source)
    validate_artifact("current_subject_adapter_v1.schema.json", adapter_raw)
    _reject_scientific_fields(adapter_raw)
    adapter = CurrentSubjectAdapter.model_validate_json(
        json.dumps(
            _expand_runtime_environment(adapter_raw, adapter_source.parent),
            ensure_ascii=False,
            sort_keys=True,
        ),
        strict=True,
    )
    _validate_profile_runtime(profile, adapter)
    declared_actors = {"default", *(actor.actor_id for actor in profile.actors)}
    missing = sorted({row.actor_id for row in adapter.request_bindings.values()} - declared_actors)
    if missing:
        raise ValueError(f"adapter request bindings reference undeclared profile actors: {missing}")

    tape: dict[str, Any] | None = None
    tape_path: Path | None = None
    if isinstance(adapter.runtime, DeterministicFixtureRuntimeConfig):
        tape_path = _resolve_relative(adapter_source.parent, adapter.runtime.transport_tape.path)
        tape = _read_object(tape_path)
        _validate_fixture_tape(tape)
        # Fixture transport text has the same numeric provenance boundary as
        # HTTP body text. Keep parsed decimals only in volatile attributes; the
        # original tape is already snapshotted byte-for-byte for pytest replay.
        precise_tape = with_numeric_body({}, tape_path.read_text()).numeric_body
        for row, precise_row in zip(tape["route_runs"], precise_tape["route_runs"], strict=True):
            for branch in ("control_observations", "treatment_observations"):
                for slot, body in row[branch].items():
                    if isinstance(body, dict):
                        row[branch][slot] = NumericObservation(body)
                        row[branch][slot].numeric_body = precise_row[branch][slot]
            if isinstance(row["producer_response"], dict):
                row["producer_response"] = NumericObservation(row["producer_response"])
                row["producer_response"].numeric_body = precise_row["producer_response"]
            for slot, result in row.get("step_results", {}).items():
                if isinstance(result["body"], dict):
                    result["body"] = NumericObservation(result["body"])
                    result["body"].numeric_body = precise_row["step_results"][slot]["body"]
    return CurrentAdapterBundle(
        profile=profile,
        profile_path=profile_source,
        profile_sha256=_sha256_file(profile_source),
        adapter=adapter,
        adapter_path=adapter_source,
        adapter_sha256=_sha256_file(adapter_source),
        fixture_tape=tape,
        fixture_tape_path=tape_path,
    )


_ENV_TEMPLATE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


def _expand_runtime_environment(
    adapter: dict[str, Any],
    adapter_root: Path,
) -> dict[str, Any]:
    """Expand explicit ``${ENV_VAR}`` references in local runtime fields."""

    value = dict(adapter)
    runtime = value.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("kind") != "local_http":
        return value
    expanded = dict(runtime)
    source_root = Path(_expand_environment_value(runtime["source_root"]))
    if not source_root.is_absolute():
        source_root = adapter_root.resolve(strict=True) / source_root
    expanded["source_root"] = str(source_root.resolve())
    expanded["environment"] = {
        key: _expand_environment_value(item)
        for key, item in runtime["environment"].items()
    }
    for field in ("materialize_commands", "server_commands"):
        expanded[field] = [
            [_expand_environment_value(part) for part in command]
            for command in runtime[field]
        ]
    value["runtime"] = expanded
    return value


def _resolve_profile_runtime(profile: AppProfile) -> AppProfile:
    reset = profile.reset
    if reset is None or reset.command is None:
        return profile
    command = [_expand_environment_value(part) for part in reset.command]
    executable = Path(command[0])
    if not executable.is_absolute() and len(executable.parts) > 1:
        command[0] = str(
            (Path(__file__).resolve().parents[2] / executable).resolve(strict=True)
        )
    return profile.model_copy(
        update={"reset": reset.model_copy(update={"command": command})}
    )


def _expand_environment_value(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if not resolved:
            raise ValueError(
                f"adapter runtime environment variable is unset: {name}"
            )
        return resolved

    return _ENV_TEMPLATE.sub(replace, value)


def adapter_materialization_view(adapter: CurrentSubjectAdapter) -> dict[str, Any]:
    """Return only the M11b execution-policy fields as canonical JSON data."""

    return {
        "schema_version": adapter.schema_version,
        "request_bindings": {
            key: value.model_dump(mode="json")
            for key, value in sorted(adapter.request_bindings.items())
        },
        "fresh_materialization_policy": adapter.fresh_materialization_policy.model_dump(mode="json"),
        "observer_policy": adapter.observer_policy.model_dump(mode="json"),
        "settle_policy": adapter.settle_policy.model_dump(mode="json"),
        "sensitive_classification": adapter.sensitive_classification.model_dump(mode="json"),
    }


def resolve_current_request_bindings(
    bundle: CurrentAdapterBundle,
    *,
    trace: UiApiTrace,
    recording_root: Path,
    recorded_bundles: Mapping[str, LoadedBundle] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve explicit fixture templates or exact current recording requests."""

    static_headers = bundle.adapter.request_mapping.static_headers
    if bundle.adapter.request_mapping.mode == "explicit_adapter":
        result = {
            key: value.model_dump(mode="json")
            for key, value in sorted(bundle.adapter.request_bindings.items())
        }
        for binding in result.values():
            binding["headers"].update(static_headers)
        return result
    loaded = dict(recorded_bundles or {})
    if recorded_bundles is None:
        for manifest in sorted(recording_root.resolve(strict=True).rglob("session_bundle/manifest.json")):
            item = load_bundle(manifest.parent)
            if item.run_id in loaded:
                raise ValueError("recording request mapping contains duplicate run IDs")
            loaded[item.run_id] = item
    result: dict[str, dict[str, Any]] = {}
    for row in trace.trace["api_requests"]:
        observation = row["observation_ref"]
        run_id = str(observation["run_id"])
        index = int(observation["entry_index"])
        source = loaded.get(run_id)
        if source is None or index < 0 or index >= len(source.entries):
            raise ValueError("recording request mapping cannot resolve trace observation")
        request = source.entries[index]["request"]
        if str(request.get("method") or "").upper() != row["method"]:
            raise ValueError("recording request method differs from current trace")
        query: dict[str, Any] = {}
        for item in request.get("queryString", []):
            key = str(item.get("name") or "")
            value = "" if item.get("value") is None else str(item["value"])
            if key in query:
                prior = query[key]
                query[key] = [*prior, value] if isinstance(prior, list) else [prior, value]
            else:
                query[key] = value
        headers = {
            str(item["name"]): str(item.get("value") or "")
            for item in request.get("headers", [])
            if str(item.get("name") or "").lower() in {"accept", "content-type"}
        }
        headers.update(static_headers)
        result[str(row["request_ref"])] = {
            "actor_id": str(row["actor_id"]),
            "method": str(row["method"]),
            "path": str(row["canonical_path"]),
            "body": _har_request_body(request),
            "query": query,
            "headers": headers,
        }
    if set(result) != {str(row["request_ref"]) for row in trace.trace["api_requests"]}:
        raise ValueError("recording request mapping does not close the current trace")
    return result


def resolve_current_request_material_bindings(
    *,
    trace: UiApiTrace,
    request_bindings: Mapping[str, Mapping[str, Any]],
    recording_root: Path,
    recorded_bundles: Mapping[str, LoadedBundle] | None = None,
    workflow_input_sources: Mapping[
        tuple[str, str, str], Mapping[str, Any]
    ] | Callable[
        [], Mapping[tuple[str, str, str], Mapping[str, Any]]
    ] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Bind redacted JSON request scalars to exact earlier workflow inputs.

    The persisted result contains only hashes, recording references, and exact
    workflow ``value_env`` symbols. Runtime values are resolved only immediately
    before transport.
    """

    loaded = dict(recorded_bundles or {})
    if recorded_bundles is None:
        for manifest in sorted(
            recording_root.resolve(strict=True).rglob("session_bundle/manifest.json")
        ):
            item = load_bundle(manifest.parent)
            if item.run_id in loaded:
                raise ValueError(
                    "recording request material contains duplicate run IDs"
                )
            loaded[item.run_id] = item

    events_by_action: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for event in trace.trace["events"]:
        events_by_action.setdefault(
            (
                str(event["action_ref"]["run_id"]),
                str(event["action_ref"]["action_id"]),
            ),
            [],
        ).append(event)
    events_by_id = {
        str(event["event_id"]): event for event in trace.trace["events"]
    }
    request_events: dict[str, list[Mapping[str, Any]]] = {}
    for binding in trace.trace["bindings"]:
        event = events_by_id.get(str(binding["event_id"]))
        if event is not None:
            request_events.setdefault(str(binding["request_ref"]), []).append(event)

    result: list[dict[str, Any]] = []
    for row in trace.trace["api_requests"]:
        request_ref = str(row["request_ref"])
        observation = row["observation_ref"]
        run_id = str(observation["run_id"])
        entry_index = int(observation["entry_index"])
        bundle = loaded.get(run_id)
        template = request_bindings.get(request_ref)
        target_events = request_events.get(request_ref, [])
        if (
            bundle is None
            or not isinstance(template, Mapping)
            or len(target_events) != 1
            or entry_index not in bundle.request_material_shapes
        ):
            continue
        target_event = target_events[0]
        interval_start_global_order = max(
            (
                int(event["global_order"])
                for events in request_events.values()
                for event in events
                if str(event.get("actor_id") or "") == str(row["actor_id"])
                and str(event.get("action_ref", {}).get("run_id") or "")
                == run_id
                and int(event.get("global_order", -1))
                < int(target_event.get("global_order", -1))
            ),
            default=-1,
        )
        if (
            str(target_event.get("actor_id") or "") != str(row["actor_id"])
            or str(target_event.get("action_ref", {}).get("run_id") or "")
            != run_id
        ):
            continue

        descriptor = bundle.request_material_shapes[entry_index]
        redactions = [
            resolved
            for node in descriptor.get("redactions", ())
            if (resolved := _exact_input_redaction(node, template)) is not None
        ]
        if not redactions:
            continue

        preceding_inputs: list[tuple[Mapping[str, Any], Mapping[str, Any], Any]] = []
        for action in bundle.actions:
            if str(action.get("action_type") or "").lower() not in {"fill", "type"}:
                continue
            action_events = events_by_action.get(
                (run_id, str(action.get("action_id") or "")), []
            )
            if len(action_events) != 1:
                continue
            event = action_events[0]
            value = action.get("value")
            if (
                str(event.get("actor_id") or "") != str(row["actor_id"])
                or int(event.get("global_order", -1))
                >= int(target_event.get("global_order", -1))
                or int(event.get("global_order", -1))
                <= interval_start_global_order
            ):
                continue
            preceding_inputs.append((event, action, value))

        visible_values = tuple(_visible_request_scalars(template))
        unexplained = [
            item
            for item in preceding_inputs
            if item[2] is None
            or not any(
                type(item[2]) is type(visible) and item[2] == visible
                for visible in visible_values
            )
        ]
        if len(unexplained) != len(redactions):
            continue

        pairs: list[
            tuple[
                tuple[str, str, str],
                tuple[Mapping[str, Any], Mapping[str, Any], Any],
            ]
        ] = []
        if len(redactions) == 1 and len(unexplained) == 1:
            redaction = redactions[0]
            item = unexplained[0]
            if (
                item[2] is not None
                and _request_material_scalar_type(item[2]) != redaction[1]
            ):
                continue
            pairs.append((redaction, item))
        else:
            remaining = list(unexplained)
            for redaction in redactions:
                target_path, scalar_type, _placeholder_sha256 = redaction
                matches = [
                    item
                    for item in remaining
                    if input_action_matches_target_path(
                        item[1], item[0], target_path
                    )
                    and (
                        item[2] is None
                        or _request_material_scalar_type(item[2]) == scalar_type
                    )
                ]
                if len(matches) != 1:
                    pairs = []
                    break
                pairs.append((redaction, matches[0]))
                remaining.remove(matches[0])
            if remaining or len(pairs) != len(redactions):
                continue

        resolved_rows: list[dict[str, Any]] = []
        for redaction, item in pairs:
            target_path, scalar_type, placeholder_sha256 = redaction
            source_event, source_action, recorded_value = item
            workflow_source: Mapping[str, Any] | None = None
            source_material_kind = "recorded_action_value"
            if recorded_value is None:
                available_workflow_sources = (
                    workflow_input_sources()
                    if callable(workflow_input_sources)
                    else workflow_input_sources or {}
                )
                workflow_source = available_workflow_sources.get(
                    (
                        run_id,
                        str(row["actor_id"]),
                        str(source_event["workflow_step_id"]),
                    )
                )
                if (
                    not isinstance(workflow_source, Mapping)
                    or scalar_type != "string"
                    or workflow_source.get("actor_id") != row["actor_id"]
                    or workflow_source.get("workflow_step_id")
                    != source_event["workflow_step_id"]
                    or workflow_source.get("global_step_index")
                    != source_event.get("global_step_index")
                    or workflow_source.get("action_kind")
                    != str(source_action.get("action_type") or "").lower()
                    or not isinstance(workflow_source.get("value_env"), str)
                    or not workflow_source["value_env"]
                ):
                    resolved_rows = []
                    break
                source_material_kind = "workflow_value_env"
            elif _request_material_scalar_type(recorded_value) != scalar_type:
                resolved_rows = []
                break
            resolved_rows.append({
                "schema_version": (
                    "uisemtest-current-recorded-input-material-binding-v1"
                ),
                "provenance_kind": "unique_preceding_unmatched_input",
                "request_ref": request_ref,
                "actor_id": str(row["actor_id"]),
                "session_run_id": run_id,
                "request_entry_index": entry_index,
                "location": "body",
                "target_path": target_path,
                "scalar_type": scalar_type,
                "redaction_token_sha256": placeholder_sha256,
                "source_action_ref": {
                    "run_id": run_id,
                    "action_id": str(source_action["action_id"]),
                },
                "source_event_id": str(source_event["event_id"]),
                "source_workflow_step_id": str(source_event["workflow_step_id"]),
                "source_global_order": int(source_event["global_order"]),
                "target_event_id": str(target_event["event_id"]),
                "target_global_order": int(target_event["global_order"]),
                "source_material_kind": source_material_kind,
                **(
                    {
                        "source_value_env": workflow_source["value_env"],
                        "source_action_kind": workflow_source["action_kind"],
                        "source_global_step_index": workflow_source[
                            "global_step_index"
                        ],
                        "source_workflow_ref": workflow_source["workflow_ref"],
                        "source_workflow_sha256": workflow_source[
                            "workflow_sha256"
                        ],
                        "recorded_value_hash_prefix": _redacted_hash_prefix(
                            extract_typed_value(template.get("body"), target_path)
                        ),
                    }
                    if source_material_kind == "workflow_value_env"
                    else {}
                ),
                **(
                    {"source_value_sha256": scalar_sha256(recorded_value)}
                    if source_material_kind == "recorded_action_value"
                    else {}
                ),
                "source_action_sha256": _canonical_sha256(source_action),
            })
        result.extend(resolved_rows)
    return tuple(
        sorted(
            result,
            key=lambda item: (
                str(item["request_ref"]),
                str(item["location"]),
                str(item["target_path"]),
            ),
        )
    )


def _redacted_hash_prefix(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("recorded request material lacks its redacted fingerprint")
    match = re.fullmatch(r"\[REDACTED:([0-9a-fA-F]+)\]", value)
    if match is None:
        raise ValueError("recorded request material lacks its redacted fingerprint")
    return match.group(1).lower()


def _exact_input_redaction(
    node: Mapping[str, Any], request: Mapping[str, Any]
) -> tuple[str, str, str] | None:
    if (
        node.get("runtime_material_required") is not True
        or node.get("redaction_form") != "whole_scalar"
        or len(node.get("placeholders", ())) != 1
    ):
        return None
    placeholder = node["placeholders"][0]
    if not any(
        basis.get("source_class") == "explicit_registered_secret"
        or (
            basis.get("source_class") == "sensitive_key"
            and basis.get("sensitive_key_match") == "exact_token"
        )
        for basis in placeholder.get("classification_bases", ())
        if isinstance(basis, Mapping)
    ):
        return None
    target_path = _descriptor_json_path(node.get("path"))
    if target_path is None:
        return None
    value = extract_typed_value(request.get("body"), target_path)
    digest = str(placeholder.get("placeholder_sha256") or "")
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\[REDACTED:[0-9a-fA-F]+\]", value) is None
        or hashlib.sha256(value.encode()).hexdigest() != digest
    ):
        return None
    scalar_type = str(node.get("original_scalar_type") or "")
    if scalar_type != "string":
        return None
    return target_path, scalar_type, digest


def _descriptor_json_path(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    path = "$"
    for segment in value:
        if not isinstance(segment, Mapping):
            return None
        if segment.get("kind") == "object_key":
            key = segment.get("key")
            if not isinstance(key, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None:
                return None
            path += f".{key}"
        elif segment.get("kind") == "array_index":
            index = segment.get("index")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                return None
            path += f"[{index}]"
        else:
            return None
    return path


def _visible_request_scalars(request: Mapping[str, Any]) -> list[Any]:
    result: list[Any] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif _request_material_scalar_type(value) is not None and not (
            isinstance(value, str)
            and re.fullmatch(r"\[REDACTED:[0-9a-fA-F]+\]", value) is not None
        ):
            result.append(value)

    visit(request.get("body"))
    visit(request.get("query") or {})
    visit(request.get("headers") or {})
    for segment in str(request.get("path") or "").strip("/").split("/"):
        if segment:
            visit(segment)
    return result


def _request_material_scalar_type(value: Any) -> str | None:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return None


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def resolve_recording_material_aliases(
    recording_root: Path,
) -> tuple[dict[str, Any], ...]:
    """Load the exact reset aliases that produced a current typed recording."""

    path = recording_root.resolve(strict=True) / "reset/reset.json"
    if not path.exists():
        return ()
    value = _read_object(path)
    aliases = value.get("material_aliases", [])
    if not isinstance(aliases, list):
        raise ValueError("recording reset material aliases are not a list")
    result: list[dict[str, Any]] = []
    for row in aliases:
        if not isinstance(row, dict):
            raise ValueError("recording reset material alias is not an object")
        if set(row) not in (
            {"logical_value", "runtime_value", "normalize_response"},
            {"actor_id", "logical_value", "runtime_value", "normalize_response"},
        ):
            raise ValueError("recording reset material alias has an invalid shape")
        if not isinstance(row.get("normalize_response"), bool):
            raise ValueError("recording reset material alias lacks a boolean policy")
        if "actor_id" in row and (
            not isinstance(row["actor_id"], str) or not row["actor_id"]
        ):
            raise ValueError("recording reset material alias has an invalid actor")
        result.append(copy.deepcopy(row))
    return tuple(result)


def resolve_current_path_binding_targets(
    *,
    value_flows: ObservedValueFlowSet,
    catalog: ObservedApiCatalog,
    recording_root: Path,
    request_bindings: Mapping[str, Any],
    recorded_bundles: Mapping[str, LoadedBundle] | None = None,
) -> dict[str, dict[str, str]]:
    """Locate path-flow target segments from the same frozen recording facts."""

    template_paths = {
        str(ref["request_ref"]): operation.canonical_path
        for operation in catalog.operations
        for ref in operation.observation_refs
        if "request_ref" in ref
    }
    bundles = dict(recorded_bundles or {})
    if recorded_bundles is None:
        for manifest in sorted(recording_root.resolve(strict=True).rglob("session_bundle/manifest.json")):
            item = load_bundle(manifest.parent)
            bundles[item.run_id] = item
    result: dict[str, dict[str, str]] = {}
    for flow in value_flows.flows:
        if flow.to_location != "path" or flow.from_location != "response_body":
            continue
        producer = bundles.get(flow.producer_session_run_id)
        if producer is None:
            continue
        producer_entry = producer.entries[flow.producer_entry_index]
        text = (producer_entry.get("response", {}).get("content") or {}).get("text")
        try:
            body = json.loads(text) if isinstance(text, str) else None
        except json.JSONDecodeError:
            continue
        value = extract_typed_value(body, flow.from_field)
        if not isinstance(value, (str, int, float, bool)):
            continue
        consumer_binding = request_bindings.get(flow.consumer_request_ref)
        if not isinstance(consumer_binding, Mapping):
            raise ValueError("path-flow consumer lacks a current request binding")
        path = str(consumer_binding["path"])
        segments = [unquote(part) for part in path.strip("/").split("/")]
        matches = [index for index, part in enumerate(segments) if part == str(value)]
        if len(matches) != 1:
            continue
        template_segments = (
            template_paths.get(flow.consumer_request_ref, "").strip("/").split("/")
        )
        index = matches[0]
        if (
            len(template_segments) != len(segments)
            or index >= len(template_segments)
            or not template_segments[index].startswith("{")
            or not template_segments[index].endswith("}")
        ):
            continue
        target = f"$.segments[{index}]"
        rows = result.setdefault(flow.consumer_request_ref, {})
        previous = rows.setdefault(flow.to_field, target)
        if previous != target:
            raise ValueError("recording path-flow target segment is inconsistent")
    return result


def _validate_profile_runtime(profile: AppProfile, adapter: CurrentSubjectAdapter) -> None:
    parsed = urlsplit(profile.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("current AppProfile base_url must be an absolute credential-free HTTP(S) URL")
    if isinstance(adapter.runtime, DeterministicFixtureRuntimeConfig):
        if parsed.scheme != "https" or not parsed.hostname.endswith(".invalid"):
            raise ValueError("deterministic fixture profile must use an HTTPS .invalid host")
    else:
        _require_loopback_http(profile.base_url)
        if profile.reset is None:
            raise ValueError("local HTTP runtime requires a profile reset contract")
        profile_origin = _http_origin(profile.base_url)
        if not any(
            _http_origin(probe.url) == profile_origin
            for probe in adapter.runtime.health_probes
        ):
            raise ValueError(
                "local HTTP runtime requires a health probe at the profile base origin"
            )


def _require_loopback_http(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
        raise ValueError("local HTTP runtime is restricted to credential-free loopback HTTP")


def _http_origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    return parsed.scheme, str(parsed.hostname).lower(), parsed.port or 80


def _har_request_body(request: Mapping[str, Any]) -> Any:
    post = request.get("postData") or {}
    text = post.get("text")
    if isinstance(text, str) and text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    params = post.get("params") or []
    if params:
        return {str(item["name"]): item.get("value") for item in params}
    return None


def _reject_scientific_fields(value: Mapping[str, Any]) -> None:
    scopes = [value]
    for key in (
        "runtime",
        "fresh_materialization_policy",
        "observer_policy",
        "settle_policy",
        "sensitive_classification",
    ):
        child = value.get(key)
        if isinstance(child, Mapping):
            scopes.append(child)
    found = sorted(
        str(key)
        for scope in scopes
        for key in scope
        if str(key).lower() in _SCIENTIFIC_KEYS
    )
    if found:
        raise ValueError(f"subject adapter cannot carry scientific fields: {found}")


def _validate_fixture_tape(value: Mapping[str, Any]) -> None:
    if set(value) != {"schema_version", "tape_id", "route_runs"} or value.get(
        "schema_version"
    ) != "uisemtest-current-fixture-runtime-tape-v1":
        raise ValueError("fixture runtime tape shape mismatch")
    rows = value.get("route_runs")
    required = {
        "control_observations",
        "treatment_observations",
        "producer_response",
        "slot_failures",
    }
    if not isinstance(rows, list) or any(
        not isinstance(row, Mapping) or not required <= set(row)
        or set(row) - required - {"step_results", "identity_observations", "producer_status", "authorization_material_present"}
        for row in rows
    ):
        raise ValueError("fixture runtime tape requires execution-fact rows")
    if any(set(row) & _SCIENTIFIC_KEYS for row in rows):
        raise ValueError("fixture runtime tape cannot carry scientific decisions")
    allowed_steps = {"A0", "A_action1", "A1", "B0", "B_action1", "B1", "B_action2", "B2", "inverse", "workflow_intermediate", "workflow_before", "workflow_after", "actor_before", "actor_after", "negative_before", "negative_after"}
    allowed_steps.update({"P", "D1", "D2", "D3"})
    for row in rows:
        if "authorization_material_present" in row and type(row["authorization_material_present"]) is not bool:
            raise ValueError("fixture authorization material presence must be a boolean execution fact")
        steps = row.get("step_results", {})
        if not isinstance(steps, Mapping) or set(steps) - allowed_steps or any(
            not isinstance(result, Mapping) or not {"status", "body"} <= set(result) or set(result) - {"status", "body", "timing"}
            or type(result["status"]) is not int or not 100 <= result["status"] <= 599
            for result in steps.values()
        ):
            raise ValueError("fixture step results require actual finite checkpoint responses")
        for result in steps.values():
            if "timing" not in result:
                continue
            timing = result["timing"]
            if (not isinstance(timing, Mapping) or set(timing) != {"send_ns", "receive_ns"}
                    or any(type(value) is not int or value < 0 for value in timing.values())
                    or timing["receive_ns"] < timing["send_ns"]):
                raise ValueError("fixture timing requires ordered nonnegative integer send and receive facts")
        identities = row.get("identity_observations", {})
        if not isinstance(identities, Mapping) or any(
            not isinstance(identity, Mapping) or set(identity) != {"principal", "session_id"}
            or not isinstance(identity["session_id"], str) or not identity["session_id"]
            for identity in identities.values()
        ):
            raise ValueError("fixture identity observations require actual principal and session facts")


def _resolve_relative(root: Path, raw_ref: str) -> Path:
    ref = _normalized_relative(raw_ref, label="adapter file ref")
    target = (root / Path(*ref.parts)).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("adapter file ref escapes its trust root")
    return target


def _normalized_relative(raw: str, *, label: str) -> PurePosixPath:
    ref = PurePosixPath(raw)
    if ref.is_absolute() or ref.as_posix() != raw or any(part in {"", ".", ".."} for part in ref.parts):
        raise ValueError(f"{label} must be normalized relative POSIX")
    return ref


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


__all__ = [
    "CurrentAdapterBundle",
    "CurrentSubjectAdapter",
    "DeterministicFixtureRuntimeConfig",
    "LocalHttpRuntimeConfig",
    "adapter_materialization_view",
    "load_current_adapter",
    "resolve_current_request_material_bindings",
    "resolve_current_request_bindings",
]
