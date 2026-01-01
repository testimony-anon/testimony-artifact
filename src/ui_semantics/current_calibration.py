"""Current M14 normal-state calibration using the existing Stage6 executor."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .artifact_relocation import attested_sha256
from typing import Any
from urllib.parse import quote

from common.contracts import validate_artifact
from stage6_ground.relation_test_execution import (
    CertifiedRelationRuntime,
    IN_MEMORY_PREDICATE_EVALUATOR,
    RelationExecutionError,
    _calibrate_assertions,
    _normal_run_passed,
    build_calibration_summary,
    calibration_arm_for_protocol,
    execute_certified_relation_suite,
    is_workflow_effect_test,
)
from stage6_ground.resource_rebinding import (
    ResourceRebindingError,
    extract_typed_value,
    scalar_sha256,
)
from stage6_ground.ui_semantic_replay import (
    BaselineRequestShapeLossError,
    UnresolvedRequestMaterialError,
)

from .current_route_s import binding_scope_id, request_shape_sha256
from .dsl import NumericObservation, _strict_equal, copy_numeric_sources
from .relation_phase_b import (
    assertion_layer_summary,
    canonical_sha256,
    validate_certified_relation_tests,
)
from .route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    predicate_value_refs,
    reject_redacted_predicate_dependencies,
    sanitize_capture,
)


@dataclass
class CalibrationContext:
    candidate_id: str
    arm: str
    reset_epoch: str
    fresh_value: str
    test: dict[str, Any]
    observer_calls: int = 0
    prepared_request: tuple[Any, ...] | None = None
    prepared_fields: dict[str, Any] | None = None
    step_calls: list[str] = field(default_factory=list)
    captured_values: dict[str, Any] = field(default_factory=dict)


class CertifiedRelationFixtureRuntime:
    """No-I/O runtime for executing the generated current suite normally."""

    def __init__(
        self,
        suite: Mapping[str, Any],
        *,
        request_bindings: Mapping[str, Any],
        execution_facts_by_candidate: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self._tests = {
            str(test["candidate_id"]): copy.deepcopy(dict(test))
            for test in suite["tests"]
        }
        self._request_bindings = copy.deepcopy(dict(request_bindings))
        self._execution_facts = copy.deepcopy(dict(execution_facts_by_candidate))
        self._run_counter = 0
        self._settle_clock_ns = 0
        self._counts = {
            "reset_runs": 0,
            "session_materializations": 0,
            "setup_executions": 0,
            "request_executions": 0,
            "settle_executions": 0,
            "external_provider_llm_calls": 0,
            "external_network_calls": 0,
            "real_target_runs": 0,
            "real_server_runs": 0,
            "real_browser_runs": 0,
            "real_docker_runs": 0,
            "real_reset_runs": 0,
        }

    def begin_arm(self, candidate_id: str, arm: str) -> tuple[CalibrationContext, dict[str, Any]]:
        test = self._tests.get(candidate_id)
        if test is None or arm not in (
            test["blueprint"]["reset_epochs"] if test["protocol_kind"] == "V5"
            else [calibration_arm_for_protocol(str(test["protocol_kind"]))]
        ):
            raise RelationExecutionError("fixture_calibration_candidate_or_arm_unknown")
        self._run_counter += 1
        epoch = f"fixture-calibration-epoch:{candidate_id}:{self._run_counter}"
        context = CalibrationContext(
            candidate_id=candidate_id,
            arm=arm,
            reset_epoch=epoch,
            fresh_value=f"fixture-calibration-fresh:{candidate_id}:{self._run_counter}",
            test=copy.deepcopy(self._tests[candidate_id]),
        )
        self._counts["reset_runs"] += 1
        self._counts["session_materializations"] += len(
            context.test["blueprint"]["actors"]
        )
        return context, {
            "artifact_type": "fixture_reset",
            "run_id": "current-v2-e2e-calibration",
            "record_id": epoch,
            "reset_artifact_ref": f"fixture:{epoch}",
            "reset_artifact_sha256": _sha(epoch),
        }

    def execute_setup(
        self,
        context: CalibrationContext,
        setup: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        descriptors = self._all_binding_descriptors(context.test)
        rows = []
        for item in setup:
            events = []
            response_body: dict[str, Any] = {}
            for descriptor in descriptors:
                if descriptor["creator_request_ref"] != item["request_ref"]:
                    continue
                response_body = _put_typed_path(
                    response_body,
                    descriptor["source_typed_path"],
                    context.fresh_value,
                )
                actor = str(item["actor_id"])
                context.captured_values[descriptor["source_id"]] = context.fresh_value
                events.append(
                    {
                        "event": "creator_value_captured",
                        "actor_id": actor,
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
                        "source_id": descriptor["source_id"],
                        "creator_request_ref": descriptor["creator_request_ref"],
                        "source_typed_path": descriptor["source_typed_path"],
                        "scalar_type": descriptor["scalar_type"],
                        "value_sha256": _scalar_sha256(context.fresh_value),
                    }
                )
            rows.append(
                {
                    "actor_id": item["actor_id"],
                    "request_ref": item["request_ref"],
                    "status": 200,
                    "response": {"body": response_body},
                    "binding_events": events,
                }
            )
        self._counts["setup_executions"] += len(rows)
        return rows

    def execute(
        self,
        context: CalibrationContext,
        endpoint: dict[str, str],
        *,
        step_id: str | None = None,
        occurrence_index: int | None = None,
        repeated: bool = False,
    ) -> dict[str, Any]:
        blueprint = context.test["blueprint"]
        query_plan = blueprint.get("query_plan")
        step_fact = None
        response_missing = False
        if context.test["protocol_kind"] == "V5":
            matching = [row for row in blueprint["execution_steps"]
                        if row["reset_epoch"] == context.arm and row["step_id"] == step_id]
            if len(matching) != 1 or matching[0]["endpoint"] != endpoint or matching[0]["occurrence_index"] != occurrence_index or repeated != (matching[0]["kind"] == "request"):
                raise RelationExecutionError("fixture_calibration_repeated_step_drift")
            step = matching[0]
            expected = [row["step_id"] for row in blueprint["execution_steps"] if row["reset_epoch"] == context.arm]
            if len(context.step_calls) >= len(expected) or step_id != expected[len(context.step_calls)]:
                raise RelationExecutionError("fixture_calibration_repeated_order_drift")
            step_fact = self._step_fact(context, step_id)
            requirement = step["binding_requirement"]
            response_body = copy.deepcopy(step_fact["body"])
            capture_requirement = {"events": [event for row in blueprint["execution_steps"]
                if row["reset_epoch"] == context.arm for event in row["binding_requirement"]["events"]
                if event["creator_request_ref"] == endpoint["request_ref"] and event.get("creator_actor_id", endpoint["actor_id"]) == endpoint["actor_id"]]}
            context.step_calls.append(step_id)
            context.observer_calls += step["kind"] == "observe"
        elif context.test["protocol_kind"] == "V8":
            step_fact = self._step_fact(context, step_id)
            if step_id == "P" and endpoint == blueprint["producer"]:
                requirement = blueprint["producer_binding_requirement"]
            elif step_id == "workflow_before" and endpoint == blueprint.get("before_observer"):
                requirement = blueprint["observer_binding_requirement"]["before"]
            else:
                matching = [row for row in blueprint["observation_plan"] if row["role"] == step_id and row["endpoint"] == endpoint]
                if len(matching) != 1:
                    raise RelationExecutionError("fixture_temporal_observation_binding_drift")
                requirement = matching[0]["binding_requirement"]
                context.observer_calls += 1
            if step_id in context.step_calls:
                raise RelationExecutionError("fixture_temporal_duplicate_send")
            context.step_calls.append(step_id)
            response_body = copy.deepcopy(step_fact["body"])
            all_events = [row for step in blueprint["observation_plan"] for row in step["binding_requirement"]["events"]]
            all_events += blueprint["producer_binding_requirement"]["events"]
            capture_requirement = {"events": [row for row in all_events if row["creator_request_ref"] == endpoint["request_ref"] and row["creator_actor_id"] == endpoint["actor_id"]]}
        elif context.test["protocol_kind"] == "V9":
            if step_id is not None:
                matching = [row for row in blueprint["observation_plan"] if row["role"] == step_id and row["endpoint"] == endpoint]
                if len(matching) != 1:
                    raise RelationExecutionError("fixture_joint_observation_binding_drift")
                requirement = matching[0]["binding_requirement"]
                response_body = copy.deepcopy(self._facts(context)["treatment_observations"][step_id])
                context.observer_calls += 1
            elif endpoint == blueprint["producer"]:
                requirement = blueprint["producer_binding_requirement"]
                response_body = copy.deepcopy(self._facts(context)["producer_response"])
            else:
                raise RelationExecutionError("fixture_joint_step_unbound")
            capture_requirement = None
        elif step_id in {"inverse", "workflow_intermediate"}:
            step_fact = self._step_fact(context, step_id)
            requirement = (blueprint["inverse_binding_requirement"] if step_id == "inverse"
                           else blueprint["intermediate_binding_requirement"])
            expected_endpoint = blueprint["inverse"] if step_id == "inverse" else blueprint["intermediate_observer"]
            if endpoint != expected_endpoint:
                raise RelationExecutionError("fixture_calibration_workflow_step_drift")
            response_body = copy.deepcopy(step_fact["body"])
            capture_requirement = None
        elif context.test["protocol_kind"] == "V2":
            if endpoint != blueprint["observer"]:
                raise RelationExecutionError("fixture_calibration_observation_drift")
            requirement = blueprint["observer_binding_requirement"]["after"]
            response_body = copy.deepcopy(
                self._facts(context)["treatment_observations"]["observation"]
            )
            capture_requirement = None
            context.observer_calls += 1
        elif query_plan is not None:
            matching = [
                row for row in query_plan
                if row["request_ref"] == endpoint["request_ref"]
            ]
            if len(matching) != 1:
                raise RelationExecutionError("fixture_calibration_query_role_ambiguous")
            role = str(matching[0]["role"])
            requirement = blueprint["query_binding_requirements"][role]
            response_body = copy.deepcopy(
                self._facts(context)["treatment_observations"][role]
            )
        elif endpoint["request_ref"] == blueprint["producer"]["request_ref"]:
            requirement = blueprint["producer_binding_requirement"]
            response_missing = context.test["protocol_kind"] == "V6" and "producer_response" not in self._facts(context)
            response_body = {} if response_missing else copy.deepcopy(self._facts(context)["producer_response"])
            capture_requirement = (
                blueprint["observer_binding_requirement"]["after"]
                if blueprint.get("workflow_kind") == "create_capture_read"
                else None
            )
        else:
            phase = (
                "after"
                if blueprint.get("workflow_kind")
                in {"create_capture_read", "postcondition_read"}
                else "before" if context.observer_calls == 0 else "after"
            )
            requirement = blueprint["observer_binding_requirement"][phase]
            phase_prefix = {"V4": "workflow", "V6": "negative", "V7": "actor"}.get(context.test["protocol_kind"])
            fact_key = f"{phase_prefix}_{phase}"
            if fact_key in self._facts(context).get("step_results", {}):
                step_fact = self._step_fact(context, fact_key)
                response_body = copy.deepcopy(step_fact["body"])
            else:
                response_body = copy.deepcopy(self._facts(context)["treatment_observations"]["Ot0" if phase == "before" else "Ot1"])
            context.observer_calls += 1
            capture_requirement = None
        if query_plan is not None:
            capture_requirement = None
        if repeated:
            if context.prepared_request is None or endpoint != blueprint["producer"]:
                raise RelationExecutionError("repeated_request_not_prepared_before_first_send")
            request_template, body, query, events = copy.deepcopy(context.prepared_request)
        else:
            request_template, body, query, events = self._prepare_endpoint_request(context, endpoint, requirement)
        capture_events = []
        capture_descriptors = {(row["source_id"], row["creator_request_ref"]): row
                               for row in (capture_requirement or {}).get("events", [])}
        for descriptor in capture_descriptors.values():
            if context.test["protocol_kind"] == "V5":
                if descriptor["source_id"] in context.captured_values:
                    continue
                # Explicit checkpoint bodies are observations, not fixture
                # destinations into which an expected identity may be inserted.
                captured = extract_typed_value(response_body, descriptor["source_typed_path"])
                context.captured_values.setdefault(descriptor["source_id"], copy.deepcopy(captured))
            else:
                response_body = _put_typed_path(response_body, descriptor["source_typed_path"], context.fresh_value)
                captured = context.fresh_value
                context.captured_values[descriptor["source_id"]] = captured
            actor = str(endpoint["actor_id"])
            capture_events.append(
                {
                    "event": "creator_value_captured",
                    "actor_id": actor,
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
                    "source_id": descriptor["source_id"],
                    "creator_request_ref": descriptor["creator_request_ref"],
                    "source_typed_path": descriptor["source_typed_path"],
                    "scalar_type": descriptor["scalar_type"],
                    "value_sha256": scalar_sha256(captured),
                }
            )
        transport = {
            "method": endpoint["method"],
            "path": endpoint["path"],
            "body": body,
        }
        observed_shape = request_shape_sha256(transport)
        if observed_shape != endpoint["request_shape_sha256"]:
            raise RelationExecutionError("fixture_calibration_request_shape_drift")
        self._counts["request_executions"] += 1
        physical_transport = {**transport, "path": request_template.get("path", endpoint["path"])}
        single_state_headers, single_state_header_redactions = (
            sanitize_capture(request_template.get("headers") or {})
            if context.test["protocol_kind"] in {"V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"} else ({}, [])
        )
        response_manifest = copy.deepcopy((step_fact or {}).get("redaction_manifest", {}).get("response", []))
        if context.test["protocol_kind"] in {"V5", "V6", "V8"}:
            safe_response, captured_manifest = sanitize_capture(response_body)
            response_body = copy_numeric_sources(response_body, safe_response) if isinstance(safe_response, dict) else safe_response
            response_manifest.extend(captured_manifest)
        result = copy_numeric_sources(response_body, {
            "status": (
                step_fact["status"] if step_fact is not None else
                int(self._facts(context).get("producer_status", 422))
                if context.test["protocol_kind"] == "V6"
                and endpoint["request_ref"] == blueprint["producer"]["request_ref"]
                else 200
            ),
            "body": copy.deepcopy(dict(response_body) if isinstance(response_body, NumericObservation) else response_body),
            "transport_request": transport,
            "semantic_request_body": copy.deepcopy(body),
            "transport_request_shape_sha256": observed_shape,
            "transport_metadata": {
                "query": query,
                "request_headers": {},
                "response_headers": {},
                "sensitive_values_persisted": False,
            },
            **({"physical_transport_request": copy.deepcopy(physical_transport), "physical_transport_metadata": {
                "query": copy.deepcopy(query), "request_headers": single_state_headers,
            }} if context.test["protocol_kind"] in {"V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"} else {}),
            "resource_binding_events": events,
            "fresh_capture_events": capture_events,
            "fresh_capture_error": None,
            "redaction_manifest": {
                "request": [],
                "request_query": [],
                "request_headers": single_state_header_redactions,
                "response": response_manifest,
                "response_headers": [],
            },
        })
        if hasattr(body, "numeric_body"):
            result.numeric_request_body = copy.deepcopy(body.numeric_body)
        if step_id is not None:
            result.update(checkpoint_id=step_id, occurrence_index=occurrence_index, reset_epoch=context.reset_epoch)
        if repeated:
            actual_fields = {**physical_transport, "query": query, "headers": request_template.get("headers") or {}}
            result["request_identity_verified"] = _strict_equal(actual_fields, context.prepared_fields)
        if response_missing:
            result.pop("body")
        if context.test["protocol_kind"] == "V8":
            result["timing"] = copy.deepcopy(step_fact.get("timing", {}))
        return result

    def temporal_wait_until(self, context: CalibrationContext, deadline_ns: int) -> None:
        # Per-step fixture responses explicitly include their send/receive clock.
        del context, deadline_ns

    def prepare_producer(self, context: CalibrationContext) -> dict[str, Any]:
        blueprint = context.test["blueprint"]
        prepared = self._prepare_endpoint_request(
            context, blueprint["producer"], blueprint["producer_binding_requirement"]
        )
        template, body, query, _events = prepared
        fields = {"method": blueprint["producer"]["method"], "path": template["path"],
                  "query": copy.deepcopy(query), "headers": copy.deepcopy(template.get("headers") or {}), "body": copy.deepcopy(body)}
        context.prepared_request = copy.deepcopy(prepared)
        context.prepared_fields = copy.deepcopy(fields)
        logical = copy.deepcopy(fields)
        logical["headers"] = {name: value for name, value in logical["headers"].items() if name.lower() not in {"authorization", "cookie"}}
        for descriptor in blueprint["producer_binding_requirement"]["events"]:
            location = descriptor["target_location"]
            marker = {"bound_resource": descriptor["source_id"]}
            if location == "path":
                logical["path"] = _bind_path_segment(logical["path"], descriptor["target_typed_path"], "{" + descriptor["source_id"] + "}", encode=False)
            elif location == "header":
                name = _bound_header_name(logical["headers"], descriptor["target_typed_path"])
                logical["headers"][name] = marker
            elif location in {"body", "query"}:
                logical[location] = _put_typed_path(logical[location], descriptor["target_typed_path"], marker)
            else:
                raise RelationExecutionError("fixture_calibration_binding_location_unsupported")
        safe_body, body_manifest = sanitize_capture(body)
        safe_fields, field_manifest = sanitize_capture(fields)
        safe_logical, logical_manifest = sanitize_capture(logical)
        return {"request": safe_body, "request_fields": safe_fields, "logical_request": safe_logical,
                "reset_epoch": context.reset_epoch, "redaction_manifest": {
                    "request": body_manifest, "request_fields": field_manifest, "logical_request": logical_manifest}}

    def _step_fact(self, context: CalibrationContext, step_id: str) -> dict[str, Any]:
        fact = self._facts(context).get("step_results", {}).get(step_id)
        if not isinstance(fact, dict) or "body" not in fact or type(fact.get("status")) is not int:
            raise RelationExecutionError("fixture_calibration_step_result_missing")
        return fact

    def verify_identity_topology(self, context: CalibrationContext, topology: Mapping[str, Any]) -> bool:
        observations = self._facts(context).get("identity_observations", {})
        actors = (topology["left_actor_id"], topology["right_actor_id"])
        if any(actor not in context.test["blueprint"]["actors"] for actor in actors):
            return False
        rows = [observations.get(actor) for actor in actors]
        if any(not isinstance(row, Mapping) or "principal" not in row or not isinstance(row.get("session_id"), str) or not row["session_id"] for row in rows):
            return False
        if any(row["principal"] in (None, "", [], {}) for row in rows):
            return False
        if (rows[0]["session_id"] == rows[1]["session_id"]) != (topology["session_relation"] == "same"):
            return False
        self._counts["request_executions"] += 2  # Same two authenticated probes as HTTP.
        return _strict_equal(rows[0]["principal"], rows[1]["principal"]) == (topology["principal_relation"] == "same")

    def _prepare_endpoint_request(
        self, context: CalibrationContext, endpoint: Mapping[str, Any], requirement: Mapping[str, Any],
    ) -> tuple[dict[str, Any], Any, dict[str, Any], list[dict[str, Any]]]:
        request_template = copy.deepcopy(self._request(str(endpoint["request_ref"])))
        request_template["path"] = str(request_template.get("path") or endpoint["path"])
        request_template["headers"] = copy.deepcopy(request_template.get("headers") or {})
        body = copy.deepcopy(request_template.get("body"))
        query = copy.deepcopy(request_template.get("query") or {})
        events = []
        for descriptor in requirement["events"]:
            if context.test["protocol_kind"] == "V5" and descriptor["source_id"] not in context.captured_values:
                raise RelationExecutionError("fixture_calibration_fresh_source_missing")
            fresh_value = context.captured_values.get(descriptor["source_id"], context.fresh_value)
            event = {
                **copy.deepcopy(descriptor),
                "candidate_id": context.candidate_id,
                "arm": context.arm,
                "reset_epoch": context.reset_epoch,
                "binding_scope_id": binding_scope_id(
                    context.candidate_id,
                    context.arm,
                    str(descriptor["actor_id"]),
                    context.reset_epoch,
                ),
                "value_sha256": scalar_sha256(fresh_value),
            }
            events.append(event)
            if event["target_location"] == "body":
                body = _put_typed_path(
                    body, event["target_typed_path"], fresh_value
                )
            elif event["target_location"] == "query":
                query = _put_typed_path(
                    query, event["target_typed_path"], fresh_value
                )
            elif event["target_location"] == "path":
                request_template["path"] = _bind_path_segment(request_template["path"], event["target_typed_path"], fresh_value)
            elif event["target_location"] == "header":
                name = _bound_header_name(request_template["headers"], event["target_typed_path"])
                request_template["headers"][name] = str(fresh_value)
            else:
                raise RelationExecutionError(
                    "fixture_calibration_binding_location_unsupported"
                )
        return request_template, body, query, events

    def verify_negative_session_boundary(
        self,
        context: CalibrationContext,
        boundary: Mapping[str, Any],
    ) -> bool:
        present = self._facts(context).get("authorization_material_present")
        return (
            context.arm == "negative_no_effect"
            and type(present) is bool
            and present == (boundary.get("kind") == "recorded_auth_preserved")
            and boundary.get("kind") in {
                "recorded_logout_and_runtime_auth_absence",
                "recorded_auth_preserved",
            }
            and boundary.get("negative_request_ref")
            == context.test["blueprint"]["producer"]["request_ref"]
        )

    def snapshot(self, context: CalibrationContext, actor_id: str) -> dict[str, str]:
        domains = context.test["blueprint"]["observer_purity_policy"]["domains"]
        return {
            domain: _sha(f"calibration-snapshot:{context.candidate_id}:{actor_id}:{domain}")
            for domain in domains
        }

    def settle_monotonic_ns(self) -> int:
        return self._settle_clock_ns

    def settle_sleep(self, seconds: float) -> None:
        self._settle_clock_ns += int(seconds * 1_000_000_000)

    def record_settle(self) -> None:
        self._counts["settle_executions"] += 1

    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def _facts(self, context: CalibrationContext) -> dict[str, Any]:
        value = self._execution_facts.get(context.candidate_id)
        if not isinstance(value, dict):
            raise RelationExecutionError("fixture_calibration_facts_missing")
        return value

    def _request(self, request_ref: str) -> dict[str, Any]:
        value = self._request_bindings.get(request_ref)
        if not isinstance(value, dict):
            raise RelationExecutionError("fixture_calibration_request_missing")
        return value

    @staticmethod
    def _all_binding_descriptors(test: Mapping[str, Any]) -> list[dict[str, Any]]:
        blueprint = test["blueprint"]
        rows = [
            *blueprint["producer_binding_requirement"]["events"],
            *blueprint["observer_binding_requirement"]["before"]["events"],
            *blueprint["observer_binding_requirement"]["after"]["events"],
            *(
                event
                for requirement in blueprint.get(
                    "query_binding_requirements", {}
                ).values()
                for event in requirement["events"]
            ),
            *(event for row in blueprint.get("execution_steps", []) for event in row["binding_requirement"]["events"]),
            *(event for row in blueprint.get("observation_plan", []) for event in row.get("binding_requirement", {}).get("events", [])),
            *blueprint.get("inverse_binding_requirement", {}).get("events", []),
            *blueprint.get("intermediate_binding_requirement", {}).get("events", []),
        ]
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            unique[(row["source_id"], row["creator_request_ref"])] = row
        return list(unique.values())


def _bind_path_segment(path: str, typed_path: str, value: Any, *, encode: bool = True) -> str:
    match = re.fullmatch(r"\$\.segments\[(\d+)\]", typed_path)
    if match is None:
        raise RelationExecutionError("fixture_calibration_path_target_invalid")
    parts = path.split("/")
    index = int(match.group(1)) + int(path.startswith("/"))
    if index >= len(parts):
        raise RelationExecutionError("fixture_calibration_path_target_missing")
    parts[index] = quote(str(value), safe="") if encode else str(value)
    return "/".join(parts)


def _bound_header_name(headers: Mapping[str, Any], typed_path: str) -> str:
    name = typed_path.removeprefix("$.")
    matches = [key for key in headers if key.casefold() == name.casefold()]
    if not typed_path.startswith("$.") or len(matches) != 1:
        raise RelationExecutionError("fixture_calibration_header_target_missing_or_ambiguous")
    return matches[0]


def run_current_calibration(
    suite: Mapping[str, Any],
    *,
    runtime: CertifiedRelationRuntime,
    suite_ref: Mapping[str, str],
    adapter_ref: Mapping[str, str],
    canonical_relation_core_by_candidate: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Execute without rewriting M13 and close four independent denominators."""

    validate_certified_relation_tests(suite)
    suite_before = canonical_sha256(suite)
    results: list[dict[str, Any]] = []
    execute_certified_relation_suite(
        suite,
        runtime,
        mode="qualifying-formal",
        is_candidate_local_error=_is_candidate_local_execution_error,
        on_result=lambda result: results.append(copy.deepcopy(result)),
    )
    suite_after = canonical_sha256(suite)
    if suite_after != suite_before:
        raise ValueError("M14 mutated the frozen M13 suite")
    expected_ids = [test["test_id"] for test in suite["tests"] if test["eligible"]]
    if [result["test_id"] for result in results] != expected_ids:
        raise ValueError("M14 completed results do not close the eligible M13 sequence")
    stable_results = _stable_results(results)
    if canonical_relation_core_by_candidate is not None:
        for result in stable_results:
            identity = canonical_relation_core_by_candidate.get(result["candidate_id"])
            if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
                raise ValueError("M14 candidate canonical relation-core identity is missing or invalid")
            result["canonical_relation_core_identity"] = identity
    summary = build_calibration_summary(suite, stable_results)
    physical_denominator = _physical_denominator(suite, stable_results)
    retained = [
        result["candidate_id"]
        for result in results
        if result["final_status"] == "normal_pass"
    ]
    failed = [
        result["candidate_id"]
        for result in results
        if result["final_status"] == "normal_fail"
    ]
    inconclusive = [
        result["candidate_id"]
        for result in results
        if result["final_status"] == "normal_inconclusive"
    ]
    completed_candidates = set(retained) | set(failed) | set(inconclusive)
    counts_method = getattr(runtime, "counts", None)
    if not callable(counts_method):
        raise ValueError("M14 runtime must expose auditable activity counts")
    runtime_counts = counts_method()
    if not isinstance(runtime_counts, dict):
        raise ValueError("M14 runtime activity counts must be an object")
    required_runtime_counts = {
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
    }
    if not required_runtime_counts <= set(runtime_counts) or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in runtime_counts.values()
    ):
        raise ValueError("M14 runtime activity counts are incomplete or invalid")
    empty = suite["source_input"]["confirmed_count"] == 0
    report = {
        "schema_version": "uisemtest-current-calibration-report-v1",
        **({"assertion_layers": assertion_layer_summary(suite["tests"])} if any(test["protocol_kind"] == "V2" or is_workflow_effect_test(test) for test in suite["tests"]) else {}),
        "status": "complete_empty" if empty else "pass",
        "completion_reason": (
            "no_confirmed_relations" if empty else "relations_calibrated"
        ),
        "mode": "qualifying-formal",
        "suite_ref": dict(suite_ref),
        "adapter_ref": dict(adapter_ref),
        "suite_sha256_before": suite_before,
        "suite_sha256_after": suite_after,
        "suite_mutated": False,
        "execution_terminal": {
            "status": "complete",
            "completed_result_count": len(results),
            "fatal_type": None,
        },
        "candidate_partition": {
            "retained": retained,
            "failed": failed,
            "inconclusive": inconclusive,
            "not_run": [
                test["candidate_id"]
                for test in suite["tests"]
                if test["candidate_id"] not in completed_candidates
            ],
        },
        "candidate_denominator": summary["candidate_denominator"],
        "test_denominator": summary["test_denominator"],
        "assertion_definition_denominator": summary[
            "assertion_definition_denominator"
        ],
        "physical_evaluation_denominator": physical_denominator,
        "assertion_calibration": summary["assertion_calibration"],
        "per_candidate": summary["per_candidate"],
        "results": stable_results,
        "runtime_counts": runtime_counts,
        "external_provider_llm_calls": runtime_counts["external_provider_llm_calls"],
        "external_network_calls": runtime_counts["external_network_calls"],
        "real_target_runs": runtime_counts["real_target_runs"],
        "real_reset_runs": runtime_counts["real_reset_runs"],
    }
    if canonical_relation_core_by_candidate is not None:
        report["retained_canonical_relation_core_identities"] = [
            canonical_relation_core_by_candidate[candidate_id]
            for candidate_id in retained
        ]
    return report


def _is_candidate_local_execution_error(error: BaseException) -> bool:
    """Only named candidate material/request failures may degrade one test."""

    return isinstance(
        error,
        (
            BaselineRequestShapeLossError,
            ResourceRebindingError,
            UnresolvedRequestMaterialError,
        ),
    ) or (
        isinstance(error, RelationExecutionError)
        and (str(error).startswith(("single_state_observer_unavailable:", "workflow_step_unavailable:")) or str(error) in {
            "local_http_transport_failed",
            "local_http_response_json_invalid",
            "single_state_observation_body_unavailable",
            "endpoint_not_bound_to_fresh_creator",
        })
    )


def validate_current_calibration_report(
    report: Mapping[str, Any],
    *,
    suite: Mapping[str, Any],
    adapter: Mapping[str, Any],
    run_root: Path,
) -> None:
    """Schema-validate and recompute the M14 cross-artifact closure."""

    validate_artifact("current_calibration_report_v1.schema.json", report)
    if any(test["protocol_kind"] == "V2" or is_workflow_effect_test(test) for test in suite["tests"]) and report.get("assertion_layers") != assertion_layer_summary(suite["tests"]):
        raise ValueError("M14 assertion reporting layers differ from frozen tests")
    root = run_root.resolve()
    _validate_ref(root, report["suite_ref"])
    _validate_ref(root, report["adapter_ref"])
    suite_path = _resolve_ref(root, report["suite_ref"])
    persisted_suite = json.loads(suite_path.read_bytes())
    if persisted_suite != suite:
        raise ValueError("M14 suite object differs from the persisted M13 suite")
    adapter_path = _resolve_ref(root, report["adapter_ref"])
    persisted_adapter = json.loads(adapter_path.read_bytes())
    if persisted_adapter != adapter:
        raise ValueError("M14 adapter object differs from the persisted fixture adapter")
    suite_sha = canonical_sha256(suite)
    if (
        report["suite_sha256_before"] != suite_sha
        or report["suite_sha256_after"] != suite_sha
        or report["suite_mutated"] is not False
    ):
        raise ValueError("M14 suite hash closure mismatch")

    tests = list(suite["tests"])
    eligible_tests = [test for test in tests if test["eligible"]]
    test_ids = [str(test["test_id"]) for test in tests]
    candidate_ids = [str(test["candidate_id"]) for test in tests]
    eligible_test_ids = [str(test["test_id"]) for test in eligible_tests]
    eligible_candidate_ids = [str(test["candidate_id"]) for test in eligible_tests]
    if len(test_ids) != len(set(test_ids)) or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("M14 suite IDs are not unique")

    results = list(report["results"])
    terminal = report["execution_terminal"]
    if [row["test_id"] for row in results] != eligible_test_ids:
        raise ValueError("M14 result order/IDs do not close the eligible suite sequence")
    if [row["candidate_id"] for row in results] != eligible_candidate_ids:
        raise ValueError("M14 result candidates do not close the eligible suite sequence")
    if terminal["completed_result_count"] != len(results):
        raise ValueError("M14 execution terminal count differs from raw results")
    if (
        terminal["status"] != "complete"
        or len(results) != len(eligible_test_ids)
        or terminal["fatal_type"] is not None
    ):
        raise ValueError("M14 complete terminal does not close the eligible suite")
    empty = suite["source_input"]["confirmed_count"] == 0
    expected_status = "complete_empty" if empty else "pass"
    expected_reason = "no_confirmed_relations" if empty else "relations_calibrated"
    if (
        report["status"] != expected_status
        or report["completion_reason"] != expected_reason
    ):
        raise ValueError("M14 completion status differs from the confirmed denominator")
    expected_summary = build_calibration_summary(suite, results)
    for key in (
        "candidate_denominator",
        "test_denominator",
        "assertion_definition_denominator",
        "assertion_calibration",
        "per_candidate",
    ):
        if report[key] != expected_summary[key]:
            raise ValueError(f"M14 recomputed summary mismatch: {key}")
    expected_physical = _physical_denominator(suite, results)
    if report["physical_evaluation_denominator"] != expected_physical:
        raise ValueError("M14 physical evaluation denominator mismatch")

    definitions = {
        assertion["assertion_id"]: assertion
        for test in tests
        for assertion in test["assertions"]
    }
    tests_by_id = {str(test["test_id"]): test for test in tests}
    reset_epochs: set[str] = set()
    for result in results:
        test = tests_by_id[result["test_id"]]
        if result["source"] != test["source"]:
            raise ValueError("M14 raw result source differs from the suite")
        if (
            result["normal_runs"] != test["normal_runs"]
            or result["normal_runs_planned"] != test["normal_runs"]
        ):
            raise ValueError("M14 raw result run plan differs from the suite")
        runs = list(result["runs"])
        if (
            len(runs) != test["normal_runs"]
            or [run["run_index"] for run in runs] != list(range(test["normal_runs"]))
        ):
            raise ValueError("M14 raw runs do not exactly close the test plan")
        completed = sum(run["mechanical_status"] == "complete" for run in runs)
        if result["normal_runs_completed"] != completed:
            raise ValueError("M14 completed-run count differs from raw runs")
        expected_pass_count = sum(_normal_run_passed(test, run) for run in runs)
        if result["pass_count"] != expected_pass_count:
            raise ValueError("M14 pass count differs from raw runs")
        expected_assertion_calibration = _calibrate_assertions(test, runs)
        if result["assertion_calibration"] != expected_assertion_calibration:
            raise ValueError("M14 assertion calibration differs from raw runs")
        expected_final_status = (
            "normal_fail"
            if (test["protocol_kind"] in {"V2", "V3", "V5", "V6", "V7", "V8", "V9"} or is_workflow_effect_test(test)) and any(row["status"] == "fail" for row in expected_assertion_calibration)
            else
            "normal_inconclusive"
            if any(row["status"] == "inconclusive" for row in expected_assertion_calibration)
            else "normal_fail"
            if any(row["status"] == "fail" for row in expected_assertion_calibration)
            else "normal_pass"
        )
        expected_reason = next(
            (
                run["reason_code"]
                for run in runs
                if run["mechanical_status"] != "complete"
            ),
            None,
        )
        if (
            result["final_status"] != expected_final_status
            or result["reason_code"] != expected_reason
        ):
            raise ValueError("M14 final status differs from raw runs")
        calibration_ids = []
        for row in result["assertion_calibration"]:
            definition = definitions.get(row["assertion_id"])
            if definition is None:
                raise ValueError("M14 calibration references an unknown assertion")
            calibration_ids.append(row["assertion_id"])
            for key in (
                "assertion_class",
                "assertion_source",
                "predicate_type",
                "definition_sha256",
            ):
                if row[key] != definition[key]:
                    raise ValueError("M14 calibration assertion definition drift")
        expected_assertion_ids = [row["assertion_id"] for row in test["assertions"]]
        if calibration_ids != expected_assertion_ids:
            raise ValueError("M14 assertion calibration does not exactly close the test")
        for run in result["runs"]:
            _validate_run_reset_refs(test, run, reset_epochs)
            if is_workflow_effect_test(test):
                primary = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
                if primary["family"] == "P04" and (run.get("mechanical_status") == "complete" or run.get("applicability") is not None):
                    applicability = run.get("applicability")
                    if not isinstance(applicability, Mapping) or (
                        applicability.get("evaluator") != "ui_semantics.dsl.evaluate_workflow_applicability"
                        or applicability.get("checked_before_action") is not True
                        or applicability.get("status") not in {"satisfied", "not_evaluable"}
                        or not isinstance(applicability.get("observed"), Mapping)
                        or run.get("before") is None
                    ):
                        raise ValueError("M14 workflow applicability evidence drift")
                    if applicability["status"] == "satisfied" and (
                        applicability["observed"] != {"before_matches": True}
                        or applicability.get("reason_code") is not None
                    ):
                        raise ValueError("M14 workflow established applicability evidence drift")
                    if run.get("mechanical_status") == "complete" and applicability["status"] != "satisfied":
                        raise ValueError("M14 workflow action requires established applicability")
                    if applicability["status"] == "not_evaluable" and (
                        run.get("producer") is not None or run.get("after") is not None
                        or run.get("assertion_results") or not applicability.get("reason_code")
                        or run.get("mechanical_status") == "complete"
                    ):
                        raise ValueError("M14 workflow action ran without applicability")
            raw_ids = []
            for row in run.get("assertion_results", []):
                definition = definitions.get(row["assertion_id"])
                if definition is None:
                    raise ValueError("M14 raw result references an unknown assertion")
                raw_ids.append(row["assertion_id"])
                for key in (
                    "assertion_class",
                    "assertion_source",
                    "predicate_type",
                    "definition_sha256",
                ):
                    if row[key] != definition[key]:
                        raise ValueError("M14 raw assertion definition drift")
                primary = definition["predicate"]
                detail = row.get("detail") or {}
                in_memory = isinstance(detail, Mapping) and detail.get("evaluator") == IN_MEMORY_PREDICATE_EVALUATOR
                if in_memory:
                    _validate_in_memory_business_evidence(test, definition, row, run)
                if (
                    definition["assertion_class"] == "business"
                    and row["verdict"] in {"passed", "failed"}
                    and not in_memory
                    and (
                        not isinstance(row.get("detail"), Mapping)
                        or row["detail"].get("evaluator")
                        != _expected_business_evaluator(test)
                    )
                ):
                    raise ValueError("M14 business assertion evaluator drift")
                if test["protocol_kind"] in {"V5", "V6"} and definition["assertion_class"] == "business":
                    _validate_fixed_protocol_checks(test, row)
                if test["protocol_kind"] == "V8" and definition["assertion_class"] == "business" and detail.get("observed"):
                    from .current_protocols.temporal import validate_temporal_predicate_result
                    validate_temporal_predicate_result({"status": {"passed": "satisfied", "failed": "violated", "unable": "not_evaluable"}[row["verdict"]], "observed": detail["observed"]})
                if test["protocol_kind"] == "V7" and definition["assertion_class"] == "business" and primary.get("family") == "P20" and primary.get("projection") and (row["verdict"] in {"passed", "failed"} or "checks" in detail.get("observed", {})):
                    _validate_projection_checks(primary, detail["observed"], row["verdict"])
                if is_workflow_effect_test(test) and definition["assertion_class"] == "business" and row["verdict"] in {"passed", "failed"}:
                    observed = detail.get("observed") or {}
                    if primary["family"] == "P20" and primary.get("projection"):
                        _validate_projection_checks(primary, observed, row["verdict"])
                        continue
                    if primary["family"] in {"P01", "P02"}:
                        if not in_memory:
                            _validate_workflow_atomic_evidence(primary, observed, row["verdict"], detail.get("reason_code"))
                        continue
                    key = {"P04": "after_matches", "P06": "values_equal", "P07": "direction_satisfied", "P20": "values_equal"}[primary["family"]]
                    if observed.get(key) is not (row["verdict"] == "passed") or detail.get("reason_code") is not None:
                        raise ValueError("M14 workflow predicate evidence drift")
                    if primary["family"] == "P06":
                        from .dsl import validate_numeric_delta_observed
                        validate_numeric_delta_observed(observed, row["verdict"] == "passed", predicate=primary)
                    if primary["family"] == "P04" and observed.get("applicability_satisfied") is not True:
                        raise ValueError("M14 workflow predicate applicability drift")
                if (
                    test["protocol_kind"] in {"V2", "V3"}
                    and definition["assertion_class"] == "business"
                    and (primary.get("family") in {"forall", "P08", "P10", "P15", "P16", "P17", "P18", "P19"} or primary.get("family") == "P11" and primary.get("target") is not None or primary.get("family") == "P03" and primary.get("operator") == "range")
                    and detail.get("evaluator") in {"ui_semantics.dsl.evaluate_predicate_result", "ui_semantics.current_protocols.metamorphic_query.evaluate_query_plan_predicate"}
                ):
                    from .current_protocols import _validate_single_state_check_evidence

                    try:
                        _validate_single_state_check_evidence({
                            "family": primary["family"],
                            "status": {"passed": "satisfied", "failed": "violated", "unable": "not_evaluable"}[row["verdict"]],
                            "reason_code": detail.get("reason_code"),
                            "observed": detail["observed"],
                        }, predicate=primary)
                    except (KeyError, TypeError, ValueError) as error:
                        raise ValueError("M14 single-state composite check evidence drift") from error
            if run.get("mechanical_status") == "complete" and raw_ids != expected_assertion_ids:
                raise ValueError("M14 completed run assertion partition is incomplete")

    partitions = report["candidate_partition"]
    partition_sets = [set(partitions[name]) for name in ("retained", "failed", "inconclusive", "not_run")]
    if sum(len(values) for values in partition_sets) != len(set().union(*partition_sets)):
        raise ValueError("M14 candidate partitions overlap")
    if set().union(*partition_sets) != set(candidate_ids):
        raise ValueError("M14 candidate partitions do not close the suite")
    expected_partition = {
        "retained": [row["candidate_id"] for row in results if row["final_status"] == "normal_pass"],
        "failed": [row["candidate_id"] for row in results if row["final_status"] == "normal_fail"],
        "inconclusive": [row["candidate_id"] for row in results if row["final_status"] == "normal_inconclusive"],
        "not_run": [candidate_id for candidate_id in candidate_ids if candidate_id not in {row["candidate_id"] for row in results}],
    }
    if partitions != expected_partition:
        raise ValueError("M14 candidate partition differs from raw results")
    if "retained_canonical_relation_core_identities" in report:
        result_core_by_candidate = {
            row["candidate_id"]: row.get("canonical_relation_core_identity")
            for row in results
        }
        expected_cores = [
            result_core_by_candidate[candidate_id]
            for candidate_id in partitions["retained"]
        ]
        if (
            report["retained_canonical_relation_core_identities"] != expected_cores
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in expected_cores
            )
        ):
            raise ValueError("M14 retained canonical relation-core occurrences differ from results")
    counts = report["runtime_counts"]
    for key in (
        "external_provider_llm_calls",
        "external_network_calls",
        "real_target_runs",
        "real_reset_runs",
    ):
        if report[key] != counts[key]:
            raise ValueError(f"M14 top-level/runtime activity count drift: {key}")


def _validate_in_memory_business_evidence(
    test: Mapping[str, Any], definition: Mapping[str, Any],
    row: Mapping[str, Any], run: Mapping[str, Any],
) -> None:
    """Close only the existing private, exact request-material P02 path."""
    predicate = definition["predicate"]
    refs = predicate_value_refs(predicate)
    detail = row["detail"]
    observed = detail.get("observed")
    workflow_kind = test.get("blueprint", {}).get("workflow_kind")
    if (
        definition["assertion_class"] != "business"
        or test.get("protocol_kind") != "V4"
        or workflow_kind not in {"create_capture_read", "postcondition_read"}
        or predicate.get("family") != "P02" or predicate.get("operator") != "eq"
        or len(refs) != 2 or {ref.get("role") for ref in refs} != {"after", "producer_request"}
        or any(ref.get("value_type") != "string" for ref in refs)
        or row["verdict"] not in {"passed", "failed"}
        or set(detail) != {"observed", "reason_code", "evaluator"}
        or detail["reason_code"] is not None
        or not isinstance(observed, Mapping) or set(observed) != {"values_equal"}
        or observed["values_equal"] is not (row["verdict"] == "passed")
        or run.get("before") != {"not_applicable": True, "reason_code": f"{workflow_kind}_has_no_before"}
    ):
        raise ValueError("M14 in-memory predicate evidence drift")
    for binding in (run.get("producer_binding", {}), run.get("observer_binding", {}).get("after", {})):
        if (
            binding.get("status") != "pass"
            or binding.get("scope_recomputed_from_current_reset") is not True
            or binding.get("fresh_creator_value_equality") is not True
        ):
            raise ValueError("M14 in-memory predicate binding evidence drift")
    try:
        reject_redacted_predicate_dependencies(predicate, {
            "producer_request": ((run.get("producer", {}), "request"),),
            "after": ((run.get("after", {}), "response"),),
        })
    except SensitiveMaterialUnavailable:
        return
    raise ValueError("M14 in-memory predicate lacks a redacted dependency")


def _expected_business_evaluator(test: Mapping[str, Any]) -> str:
    if test.get("protocol_kind") == "V8":
        return "ui_semantics.current_protocols.temporal.evaluate_temporal_result"
    if test.get("protocol_kind") == "V9":
        return "ui_semantics.current_protocols.multi_resource.evaluate_multi_resource_result"
    if test.get("protocol_kind") == "V5":
        return "ui_semantics.current_protocols.repeated_execution.evaluate_repeated_result"
    if test.get("protocol_kind") == "V6":
        return "ui_semantics.current_protocols.negative_no_effect.evaluate_negative_outcome"
    if test.get("protocol_kind") == "V7":
        return "ui_semantics.dsl.evaluate_predicate_result"
    if test.get("protocol_kind") == "V3":
        return "ui_semantics.current_protocols.metamorphic_query.evaluate_query_plan_predicate"
    if test.get("protocol_kind") == "V2" or is_workflow_effect_test(test):
        return "ui_semantics.dsl.evaluate_predicate_result"
    blueprint = test.get("blueprint")
    no_before_workflow = (
        test.get("protocol_kind") == "V4"
        and isinstance(blueprint, Mapping)
        and blueprint.get("workflow_kind")
        in {"create_capture_read", "postcondition_read"}
    )
    if test.get("protocol_kind") in {"V3", "V6", "V7"} or no_before_workflow:
        return "ui_semantics.dsl.evaluate_predicate"
    return "ui_semantics.current_route_s.core.evaluate_pair"


def _validate_workflow_atomic_evidence(predicate: Mapping[str, Any], observed: Mapping[str, Any], verdict: str, reason: Any) -> None:
    keys = ("actual", "expected") if predicate["family"] == "P01" else ("left", "right")
    if reason is not None or any(not re.fullmatch(r"[0-9a-f]{64}", str(observed.get(key + "_sha256", ""))) for key in keys):
        raise ValueError("M14 workflow atomic evidence drift")
    if predicate["family"] == "P01":
        expected = predicate["operator"] == "exists"
        actual = expected if verdict == "passed" else not expected
        if observed != {"actual_sha256": canonical_sha256(actual), "expected_sha256": canonical_sha256(expected)}:
            raise ValueError("M14 workflow presence evidence drift")
    # P02 operands are deliberately retained only as hashes. Their ordering or
    # numeric equality cannot be reconstructed from those hashes (e.g. -0.0/0.0).


def _validate_projection_checks(predicate: Mapping[str, Any], observed: Mapping[str, Any], verdict: str) -> None:
    checks = observed.get("checks")
    if not isinstance(checks, list) or [row.get("check_id") for row in checks] != predicate["projection"]:
        raise ValueError("M14 projection fixed checks differ from the predicate")
    values = []
    for check in checks:
        value = check.get("satisfied")
        if value is not None and type(value) is not bool:
            raise ValueError("M14 projection check truth invalid")
        if "satisfied" not in check or "reason_code" not in check:
            raise ValueError("M14 projection check incomplete")
        values.append(value)
    reduced = False if False in values else None if None in values else True
    expected = {"passed": True, "failed": False, "unable": None}[verdict]
    if reduced is not expected:
        raise ValueError("M14 projection fixed check reduction differs")


def _validate_fixed_protocol_checks(test: Mapping[str, Any], row: Mapping[str, Any]) -> None:
    """Close the finite checks actually emitted by the shared V5/V6 evaluator."""
    primary = next(item["predicate"] for item in test["assertions"] if item["assertion_class"] == "business")
    detail = row.get("detail") or {}
    if detail.get("evaluator") != _expected_business_evaluator(test):
        raise ValueError("M14 fixed protocol evaluator drift")
    observed = detail.get("observed")
    if row["verdict"] == "unable" and observed == {}:
        # The execution failed before a usable predicate result existed.
        if not detail.get("reason_code"):
            raise ValueError("M14 unavailable protocol result requires a reason")
        return
    if not isinstance(observed, Mapping) or not isinstance(observed.get("diagnostics"), list):
        raise ValueError("M14 fixed protocol observations incomplete")
    repeated = test["protocol_kind"] == "V5"
    if repeated:
        from .current_protocols.repeated_execution import CHECKS
        expected_ids = list(CHECKS[primary["family"]])
    else:
        expected_ids = ["rejection"] + (["preservation"] if test["blueprint"]["negative_kind"] == "rejection_preservation" else [])
    checks = observed.get("checks")
    if not isinstance(checks, list) or [check.get("check_id") for check in checks] != expected_ids:
        raise ValueError("M14 fixed protocol checks missing duplicated or reordered")
    states = []
    for check in checks:
        if "reason_code" not in check:
            raise ValueError("M14 fixed protocol check reason missing")
        if repeated:
            status = check.get("status")
            if status not in {"satisfied", "violated", "not_evaluable"}:
                raise ValueError("M14 repeated check status invalid")
            value = {"satisfied": True, "violated": False, "not_evaluable": None}[status]
        else:
            if "satisfied" not in check or check["satisfied"] is not None and type(check["satisfied"]) is not bool:
                raise ValueError("M14 negative check truth invalid")
            value = check["satisfied"]
            if check["check_id"] == "preservation" and primary.get("projection") and (value is not None or "checks" in check):
                _validate_projection_checks(primary, check, "passed" if value is True else "failed" if value is False else "unable")
        states.append(value)
    applicable = True
    if repeated:
        expected_applicability = {"repeat_equal": ["baseline_equivalent", "logical_input_equivalent"],
                                  "repeat_rejected": ["first_success"], "repeat_delta": []}[primary["family"]]
        applicability = observed.get("applicability")
        if not isinstance(applicability, list) or [check.get("check_id") for check in applicability] != expected_applicability:
            raise ValueError("M14 repeated applicability checks differ")
        if any(check.get("status") not in {"satisfied", "violated", "not_evaluable"} for check in applicability):
            raise ValueError("M14 repeated applicability status invalid")
        applicable = all(check["status"] == "satisfied" for check in applicability)
    if row["verdict"] == "failed":
        valid = applicable and False in states
    elif row["verdict"] == "passed":
        valid = applicable and all(value is True for value in states)
    else:
        valid = False not in states and (not applicable or None in states or bool(detail.get("reason_code")))
    if not valid:
        raise ValueError("M14 fixed protocol check reduction differs")


def _validate_run_reset_refs(test: Mapping[str, Any], run: Mapping[str, Any], seen: set[str]) -> None:
    if test["protocol_kind"] == "V5":
        refs = run.get("reset_refs")
        if not isinstance(refs, list) or len(refs) > len(test["blueprint"]["reset_epochs"]):
            raise ValueError("M14 repeated reset epochs differ from plan")
        if run.get("mechanical_status") == "complete" and len(refs) != len(test["blueprint"]["reset_epochs"]):
            raise ValueError("M14 repeated reset epoch missing")
        if refs and run.get("reset_ref") != refs[0]:
            raise ValueError("M14 repeated first reset reference differs")
        if run.get("mechanical_status") == "complete" and set(run.get("steps", {})) != {step["step_id"] for step in test["blueprint"]["execution_steps"]}:
            raise ValueError("M14 repeated checkpoint results do not close the plan")
    else:
        refs = [run.get("reset_ref") or {}]
    for ref in refs:
        epoch = ref.get("record_id")
        if epoch is None and run.get("mechanical_status") != "complete":
            continue
        if not isinstance(epoch, str) or not epoch or epoch in seen:
            raise ValueError("M14 reset epoch missing or reused")
        seen.add(epoch)


def validate_final_calibrated_view(
    view: Mapping[str, Any],
    *,
    calibration: Mapping[str, Any],
    run_root: Path,
) -> None:
    """Require the final view to be an exact projection of persisted M14."""

    validate_artifact("final_calibrated_view_v1.schema.json", view)
    root = run_root.resolve()
    _validate_ref(root, view["source_suite"])
    _validate_ref(root, view["source_calibration"])
    if view["source_suite"] != calibration["suite_ref"]:
        raise ValueError("final view suite source differs from calibration")
    persisted_calibration = json.loads(
        _resolve_ref(root, view["source_calibration"]).read_bytes()
    )
    if persisted_calibration != calibration:
        raise ValueError("final view calibration source differs from persisted M14")
    expected = {
        "status": calibration["status"],
        "completion_reason": calibration["completion_reason"],
        "retained_candidate_ids": calibration["candidate_partition"]["retained"],
        "failed_candidate_ids": calibration["candidate_partition"]["failed"],
        "inconclusive_candidate_ids": calibration["candidate_partition"]["inconclusive"],
        "not_run_candidate_ids": calibration["candidate_partition"]["not_run"],
        "candidate_denominator": calibration["candidate_denominator"],
        "test_denominator": calibration["test_denominator"],
        "assertion_definition_denominator": calibration["assertion_definition_denominator"],
        "physical_evaluation_denominator": calibration["physical_evaluation_denominator"],
        "m13_suite_mutated": calibration["suite_mutated"],
    }
    if any(view[key] != value for key, value in expected.items()):
        raise ValueError("final calibrated view is not an exact calibration projection")


def build_final_calibrated_suite(
    suite: Mapping[str, Any],
    calibration: Mapping[str, Any],
    *,
    final_view: Mapping[str, Any],
    final_view_ref: Mapping[str, str],
) -> dict[str, Any]:
    """Embed the full retained M13 definitions without rewriting M13."""

    retained_ids = list(calibration["candidate_partition"]["retained"])
    retained_set = set(retained_ids)
    retained_tests = [
        copy.deepcopy(test)
        for test in suite["tests"]
        if test["candidate_id"] in retained_set
    ]
    if [test["candidate_id"] for test in retained_tests] != retained_ids:
        raise ValueError("final suite retained test order differs from calibration")
    return {
        "schema_version": "uisemtest-final-calibrated-suite-v1",
        "status": calibration["status"],
        "completion_reason": calibration["completion_reason"],
        "source_suite": copy.deepcopy(calibration["suite_ref"]),
        "source_calibration": copy.deepcopy(final_view["source_calibration"]),
        "source_final_view": copy.deepcopy(final_view_ref),
        "retained_count": len(retained_tests),
        "retained_candidate_ids": retained_ids,
        "retained_tests": retained_tests,
        "retained_tests_sha256": canonical_sha256(retained_tests),
        "candidate_denominator": copy.deepcopy(calibration["candidate_denominator"]),
        "test_denominator": copy.deepcopy(calibration["test_denominator"]),
        "assertion_definition_denominator": copy.deepcopy(
            calibration["assertion_definition_denominator"]
        ),
        "physical_evaluation_denominator": copy.deepcopy(
            calibration["physical_evaluation_denominator"]
        ),
        "m13_suite_mutated": calibration["suite_mutated"],
    }


def validate_final_calibrated_suite(
    final_suite: Mapping[str, Any],
    *,
    suite: Mapping[str, Any],
    calibration: Mapping[str, Any],
    final_view: Mapping[str, Any],
    run_root: Path,
) -> None:
    """Close the self-contained retained definitions to all persisted M13/M14 roots."""

    validate_artifact("final_calibrated_suite_v1.schema.json", final_suite)
    root = run_root.resolve()
    for key in ("source_suite", "source_calibration", "source_final_view"):
        _validate_ref(root, final_suite[key])
    if final_suite["source_suite"] != calibration["suite_ref"]:
        raise ValueError("final suite source differs from M14 suite source")
    if json.loads(_resolve_ref(root, final_suite["source_suite"]).read_bytes()) != suite:
        raise ValueError("final suite persisted M13 source differs")
    if json.loads(_resolve_ref(root, final_suite["source_calibration"]).read_bytes()) != calibration:
        raise ValueError("final suite persisted calibration source differs")
    if json.loads(_resolve_ref(root, final_suite["source_final_view"]).read_bytes()) != final_view:
        raise ValueError("final suite persisted final view source differs")
    retained_ids = calibration["candidate_partition"]["retained"]
    expected_tests = [
        test for test in suite["tests"] if test["candidate_id"] in set(retained_ids)
    ]
    expected = {
        "status": calibration["status"],
        "completion_reason": calibration["completion_reason"],
        "retained_count": len(expected_tests),
        "retained_candidate_ids": retained_ids,
        "retained_tests": expected_tests,
        "retained_tests_sha256": canonical_sha256(expected_tests),
        "candidate_denominator": calibration["candidate_denominator"],
        "test_denominator": calibration["test_denominator"],
        "assertion_definition_denominator": calibration[
            "assertion_definition_denominator"
        ],
        "physical_evaluation_denominator": calibration[
            "physical_evaluation_denominator"
        ],
        "m13_suite_mutated": calibration["suite_mutated"],
    }
    if any(final_suite[key] != value for key, value in expected.items()):
        raise ValueError("final calibrated suite differs from its M13/M14 closure")


def _physical_denominator(
    suite: Mapping[str, Any],
    results: list[Mapping[str, Any]],
) -> dict[str, Any]:
    definitions = {
        assertion["assertion_id"]: assertion["assertion_class"]
        for test in suite["tests"]
        for assertion in test["assertions"]
    }
    planned = sum(
        int(test["normal_runs"]) * len(test["assertions"])
        for test in suite["tests"]
        if test["eligible"]
    )
    physical = Counter()
    physical_by_class: dict[str, Counter[str]] = {
        "business": Counter(),
        "generic_status_schema": Counter(),
    }
    for result in results:
        for run in result.get("runs", []):
            for row in run.get("assertion_results", []):
                verdict = str(row["verdict"])
                if verdict not in {"passed", "failed", "unable"}:
                    raise ValueError("M14 physical verdict is invalid")
                assertion_class = definitions.get(row["assertion_id"])
                if assertion_class is None:
                    raise ValueError("M14 physical result references an unknown assertion")
                physical[verdict] += 1
                bucket = "business" if assertion_class == "business" else "generic_status_schema"
                physical_by_class[bucket][verdict] += 1
    completed = sum(physical.values())
    if completed > planned:
        raise ValueError("M14 physical evaluation count exceeds the plan")
    planned_by_class = {
        "business": sum(
            int(test["normal_runs"])
            * sum(row["assertion_class"] == "business" for row in test["assertions"])
            for test in suite["tests"]
            if test["eligible"]
        ),
        "generic_status_schema": sum(
            int(test["normal_runs"])
            * sum(row["assertion_class"] == "generic" for row in test["assertions"])
            for test in suite["tests"]
            if test["eligible"]
        ),
    }

    def class_denominator(name: str) -> dict[str, int]:
        class_completed = sum(physical_by_class[name].values())
        return {
            "planned": planned_by_class[name],
            "completed": class_completed,
            "passed": physical_by_class[name]["passed"],
            "failed": physical_by_class[name]["failed"],
            "unable": physical_by_class[name]["unable"],
            "not_executed": planned_by_class[name] - class_completed,
        }

    return {
        "planned": planned,
        "completed": completed,
        "passed": physical["passed"],
        "failed": physical["failed"],
        "unable": physical["unable"],
        "not_executed": planned - completed,
        "business": class_denominator("business"),
        "generic_status_schema": class_denominator("generic_status_schema"),
    }


def _resolve_ref(root: Path, ref: Mapping[str, str]) -> Path:
    raw = Path(str(ref["path"]))
    path = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if not raw.is_absolute() and not path.is_relative_to(root):
        raise ValueError("M14 artifact ref escapes the run root")
    return path


def _validate_ref(root: Path, ref: Mapping[str, str]) -> None:
    path = _resolve_ref(root, ref)
    if not path.is_file() or attested_sha256(path) != ref["sha256"]:
        raise ValueError("M14 artifact ref hash mismatch")


def _stable_results(results: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Drop non-scientific wall-clock timings from deterministic fixture output."""

    stable = copy.deepcopy(results)
    for result in stable:
        for run in result.get("runs", []):
            run.pop("elapsed_ms", None)
            run.pop("reset_elapsed_ms", None)
    return stable


def _put_typed_path(value: Any, path: str, replacement: Any) -> Any:
    if not path.startswith("$.") or "[" in path:
        raise RelationExecutionError("fixture_calibration_typed_path_unsupported")
    result = copy.deepcopy(value)
    if result is None:
        result = {}
    if not isinstance(result, dict):
        raise RelationExecutionError("fixture_calibration_typed_path_root_invalid")
    current = result
    parts = path[2:].split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise RelationExecutionError("fixture_calibration_typed_path_invalid")
        current = child
    current[parts[-1]] = replacement
    if hasattr(result, "numeric_body"):
        result.numeric_body = _put_typed_path(result.numeric_body, path, replacement)
    return result


def _scalar_sha256(value: str) -> str:
    return hashlib.sha256(
        ("{\"type\":\"string\",\"value\":" + _json_string(value) + "}").encode(
            "utf-8"
        )
    ).hexdigest()


def _json_string(value: str) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "CertifiedRelationFixtureRuntime",
    "build_final_calibrated_suite",
    "run_current_calibration",
    "validate_current_calibration_report",
    "validate_final_calibrated_suite",
    "validate_final_calibrated_view",
]
