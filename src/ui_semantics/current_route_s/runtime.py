"""Single current Route-S collector/runtime SPI and deterministic fixture runtime.

The collector owns protocol ordering and evidence construction.  The runtime
only returns local execution facts.  Neither layer accepts, computes, or emits
a Route-S verdict; certificate evaluation remains in :mod:`.core`.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Protocol

from stage6_ground.resource_rebinding import ResourceBindingUse, _replace_location

from ..current_candidate_failure import CandidateLocalFailure
from ..current_settle import poll_semantic_stability, route_observer_is_pure
from ..route_s_capture_redaction import sanitize_capture
from ..dsl import NumericObservation, copy_numeric_sources
if TYPE_CHECKING:
    from ..m11b_materializer import RouteSPreLiveMaterializedCandidate
from .core import (
    PROTOCOL_SLOTS,
    build_current_route_s_certificate,
    build_route_s_certificate_v5,
    canonical_json_bytes,
    canonical_sha256,
)
from .core import request_shape_sha256, validate_partial_chain_v2
from .core import binding_scope_id
from .validation import (
    validate_partial_certificate_v2,
    validate_scan_report_v1,
    validate_execution_evidence_v5,
    validate_outer_envelope_v5,
    validate_current_route_s_evaluation,
)


TS = "2026-08-10T00:00:00Z"
OBSERVATION_SLOTS = ("Oc1", "Oc2", "Ot0", "Ot1")


@dataclass(frozen=True)
class RouteSCollectedEvidence:
    evidence: dict[str, Any]
    execution_evidence_bytes: bytes
    artifact_hashes: dict[str, str]
    artifact_bytes: dict[str, bytes]
    partial_records: tuple[dict[str, Any], ...]
    artifact_write_sequence: tuple[str, ...]
    runtime_counts: dict[str, int]
    volatile_sensitive_values: tuple[str, ...] = ()


@dataclass
class _FixtureArmContext:
    material: RouteSPreLiveMaterializedCandidate
    candidate_id: str
    arm: str
    reset_epoch: str
    fresh_values: dict[str, Any]
    pending_fresh_values: dict[str, Any]
    run_facts: dict[str, Any]
    prepared_request: Any = None
    prepared_binding_events: Any = None


class CurrentRouteSSubjectRuntime(Protocol):
    def begin_arm(
        self,
        material: RouteSPreLiveMaterializedCandidate,
        arm: str,
    ) -> tuple[Any, dict[str, Any], dict[str, bytes]]: ...

    def execute_setup(
        self,
        context: Any,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]: ...

    def observe(
        self,
        context: Any,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]: ...

    def execute_producer(
        self,
        context: Any,
    ) -> tuple[dict[str, Any], dict[str, bytes]]: ...

    def observe_until_stable(
        self,
        context: Any,
        settle_slot: str,
        observer_slot: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]: ...

    def sessions(self) -> list[dict[str, Any]]: ...

    def counts(self) -> dict[str, int]: ...


class RouteSArtifactWriter(Protocol):
    """Persist one immutable current-run artifact at its normalized ref."""

    def __call__(self, artifact_ref: str, payload: bytes) -> None: ...


class DeterministicFixtureRuntime:
    """A no-I/O runtime that materializes only frozen fixture execution facts."""

    def __init__(self, adapter: Mapping[str, Any], route_run: Mapping[str, Any]) -> None:
        self._adapter = copy.deepcopy(dict(adapter))
        self._run_facts = copy.deepcopy(dict(route_run))
        self._sessions: list[dict[str, Any]] = []
        self._counts = {
            "reset_runs": 0,
            "session_materializations": 0,
            "setup_executions": 0,
            "request_executions": 0,
            "settle_executions": 0,
            "external_provider_llm_calls": 0,
            "external_network_calls": 0,
            "real_target_runs": 0,
            "real_browser_runs": 0,
            "real_server_runs": 0,
            "real_docker_runs": 0,
            "real_reset_runs": 0,
        }

    def begin_arm(
        self,
        material: RouteSPreLiveMaterializedCandidate,
        arm: str,
    ) -> tuple[_FixtureArmContext, dict[str, Any], dict[str, bytes]]:
        epoch = f"fixture-epoch:{material.candidate_id}:{arm}"
        plan = material.resource_binding_plans[arm]
        generated_values = {
            str(source["source_id"]): _fixture_scalar(
                str(source["scalar_type"]),
                material.candidate_id,
                arm,
                str(source["source_id"]),
            )
            for source in plan["sources"]
        }
        fresh_values = {
            source_id: value
            for source_id, value in generated_values.items()
            if next(
                row for row in plan["sources"]
                if str(row["source_id"]) == source_id
            ).get("capture_timing") != "producer_response"
        }
        pending_fresh_values = {
            source_id: value
            for source_id, value in generated_values.items()
            if source_id not in fresh_values
        }
        context = _FixtureArmContext(
            material=material,
            candidate_id=material.candidate_id,
            arm=arm,
            reset_epoch=epoch,
            fresh_values=fresh_values,
            pending_fresh_values=pending_fresh_values,
            run_facts=copy.deepcopy(self._run_facts),
        )
        slot = (
            f"{arm}_reset" if arm in {"repeat_once", "repeat_twice"}
            else "workflow_reset" if arm == "workflow"
            else "Rc" if arm == "control"
            else "Rt"
        )
        raw = {
            "reset_ref": {
                "record_id": f"fixture-reset:{material.candidate_id}:{arm}",
                "reset_epoch": epoch,
                "resource_binding_plan": {
                    "sources": copy.deepcopy(plan["sources"]),
                    "uses": copy.deepcopy(plan["uses"]),
                },
            }
        }
        ref, payload = self._raw(material.candidate_id, slot, raw)
        failure = self._slot_failure(context, slot)
        if failure is None:
            record = self._pass_record(slot, arm, ref, payload)
            artifacts = {ref: payload}
        else:
            record, artifacts = self._failed_record(
                context, slot, failure, raw_ref=ref, raw=payload
            )
        record["reset_epoch"] = epoch
        actors = {
            material.candidate["consumer"]["actor_id"],
            *(item["actor_id"] for item in material.candidate["setup"]),
        }
        if material.candidate.get("producer") is not None:
            actors.add(material.candidate["producer"]["actor_id"])
        for actor in sorted(actors):
            stem = f"{material.candidate_id}:{arm}:{actor}"
            self._sessions.append(
                {
                    "arm": arm,
                    "actor_id": actor,
                    "reset_epoch": epoch,
                    "materialization_id": f"fixture-materialization:{stem}",
                    "ownership_domain_sha256": _sha(f"ownership:{stem}"),
                    "jar_ownership_sha256": _sha(f"jar:{stem}"),
                    "mutation_domain_sha256": _sha(f"mutation:{stem}"),
                    "secret_values_present": False,
                }
            )
            self._counts["session_materializations"] += 1
        self._counts["reset_runs"] += 1
        return context, record, artifacts

    def execute_setup(
        self,
        context: _FixtureArmContext,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        failure = self._slot_failure(context, slot)
        if failure is not None:
            self._counts["setup_executions"] += 1
            raw_ref, raw = self._raw(
                context.candidate_id, slot, {"slot": slot, "status": "failed"}
            )
            return self._failed_record(context, slot, failure, raw_ref=raw_ref, raw=raw)

        provenance_refs: list[str] = []
        rows: list[dict[str, Any]] = []
        artifacts: dict[str, bytes] = {}
        sources = context.material.resource_binding_plans[context.arm]["sources"]
        for index, setup in enumerate(context.material.candidate["setup"], start=1):
            request_ref = str(setup["request_ref"])
            creator_events = [
                self._creator_event(context, source)
                for source in sources
                if source["creator_request_ref"] == request_ref
                and source["actor_id"] == setup["actor_id"]
            ]
            rows.append(
                {
                    "actor_id": setup["actor_id"],
                    "request_ref": request_ref,
                    "status": "pass",
                    "response": self._creator_response(context, creator_events),
                    "binding_events": creator_events,
                }
            )
            provenance_ref = (
                f"M12/{context.candidate_id}/raw/{slot}.setup-{index:02d}.json"
            )
            artifacts[provenance_ref] = canonical_json_bytes(
                {
                    "actor_id": setup["actor_id"],
                    "request_ref": request_ref,
                    "status": "pass",
                }
            )
            provenance_refs.append(provenance_ref)
        raw_ref, raw = self._raw(context.candidate_id, slot, {"setup": rows})
        artifacts[raw_ref] = raw
        record = self._pass_record(slot, context.arm, raw_ref, raw)
        record["provenance_refs"] = provenance_refs
        self._counts["setup_executions"] += 1
        return record, artifacts

    def observe(
        self,
        context: _FixtureArmContext,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        return self._observe(context, slot, slot)

    def _observe(
        self,
        context: _FixtureArmContext,
        binding_slot: str,
        record_slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        failure = self._slot_failure(context, binding_slot)
        if failure is not None:
            self._counts["request_executions"] += 1
            raw_ref, raw = self._raw(
                context.candidate_id,
                record_slot,
                {"slot": binding_slot, "status": "failed"},
            )
            return self._failed_record(
                context, record_slot, failure, raw_ref=raw_ref, raw=raw
            )
        branch = context.run_facts.get("control_observations" if context.arm == "control" else "treatment_observations", {})
        fact_slot = {
            "workflow_before": "Ot0",
            "workflow_after": "Ot1",
            "negative_before": "Ot0",
            "negative_after": "Ot1",
            "actor_before": "Ot0",
            "actor_after": "Ot1",
        }.get(binding_slot, binding_slot)
        step_result = context.run_facts.get("step_results", {}).get(binding_slot)
        if context.arm in {"repeat_once", "repeat_twice", "temporal"} and step_result is None:
            return self._failed_record(context, record_slot, "fixture_step_result_missing")
        body = copy.deepcopy(step_result["body"] if step_result is not None else branch[fact_slot])
        request_binding = context.material.execution_binding["payload"]["observations"][
            binding_slot
        ]
        request_ref = str(
            request_binding.get("request_ref")
            or context.material.candidate["consumer"]["request_ref"]
        )
        template = self._request(request_ref)
        query = copy.deepcopy(template.get("query") or {})
        request_body = copy.deepcopy(template.get("body"))
        request_body, query, physical_path, headers = self._apply_fresh_uses(
            context,
            request_ref=request_ref,
            actor_id=request_binding["actor_id"],
            body=request_body,
            query=query,
            path=template["path"],
            headers=copy.deepcopy(template.get("headers") or {}),
        )
        request = {
            "method": request_binding["method"],
            "path": request_binding["path"],
            "body": request_body,
        }
        events = self._consumer_events(
            context,
            request_ref=request_ref,
            actor_id=request_binding["actor_id"],
        )
        artifacts: dict[str, bytes] = {}
        domains = []
        for domain in ("cookie", "token", "cache", "last_seen"):
            state_sha = _sha(f"observer-state:{context.candidate_id}:{context.arm}:{domain}")
            row = {
                "domain": domain,
                "disposition": "proven_unchanged",
                "before_sha256": state_sha,
                "after_sha256": state_sha,
                "mutation_events": [],
                "uncertain_fields": [],
                "reason_code": "fixture_capability_observed",
            }
            if context.material.output_level == "forensic":
                capability_ref = (
                    f"M12/{context.candidate_id}/capabilities/{record_slot}.{domain}.json"
                )
                capability = canonical_json_bytes(
                    {
                        "slot": record_slot,
                        "domain": domain,
                        "fixture_observer": True,
                    }
                )
                artifacts[capability_ref] = capability
                row.update(
                    {
                        "capability_ref": capability_ref,
                        "capability_sha256": hashlib.sha256(capability).hexdigest(),
                    }
                )
            domains.append(row)
        raw_ref, raw = self._raw(
            context.candidate_id,
            record_slot,
            {"request": request, "query": query, "response": copy.deepcopy(body)},
        )
        artifacts[raw_ref] = raw
        record = self._pass_record(record_slot, context.arm, raw_ref, raw)
        record.update(
            {
                "actor_id": request_binding["actor_id"],
                "request_ref": request_ref,
                "request": request,
                "transport_request_shape_sha256": request_shape_sha256(request),
                "response": copy_numeric_sources(body, {"status": step_result["status"] if step_result is not None else 200, "body": copy.deepcopy(dict(body) if isinstance(body, NumericObservation) else body)}),
                "checkpoint_id": record_slot,
                "reset_epoch": context.reset_epoch,
                "observer_domains": domains,
                "binding_events": events,
                "transport_metadata": _transport_metadata(query),
                "redaction_manifest": _empty_redaction_manifest(),
            }
        )
        if context.arm not in {"control", "treatment"}:
            record["physical_transport_request"] = {**copy.deepcopy(request), "path": physical_path}
            headers, header_redactions = sanitize_capture(headers)
            record["physical_transport_metadata"] = {
                "query": copy.deepcopy(query), "request_headers": headers,
            }
            record["redaction_manifest"]["request_headers"] = header_redactions
        if context.arm == "temporal":
            record["timing"] = copy.deepcopy(step_result.get("timing", {}))
        self._counts["request_executions"] += 1
        record = copy_numeric_sources(body, record)
        if hasattr(request_body, "numeric_body"):
            record.numeric_request_body = copy.deepcopy(request_body.numeric_body)
        return record, artifacts

    def prepare_producer(self, context: _FixtureArmContext) -> dict[str, Any]:
        binding = context.material.execution_binding["payload"]["producer"]
        body, query, path, headers = self._prepare_request(context, binding)
        context.prepared_request = copy.deepcopy((body, query, path, headers))
        context.prepared_binding_events = self._consumer_events(
            context, request_ref=binding["request_ref"], actor_id=binding["actor_id"],
        )
        safe, manifest = sanitize_capture(body)
        template = self._request(binding["request_ref"])
        logical, logical_manifest = sanitize_capture({"method": binding["method"], "path": binding["path"], "query": template.get("query") or {}, "body": template.get("body"), "headers": {key: value for key, value in template.get("headers", {}).items() if key.lower() not in {"authorization", "cookie"}}})
        fields = {"body": safe, "method": binding["method"]}
        channels = {"request": manifest, "logical_request": logical_manifest}
        for location, channel, value in (("query", "request_query", query), ("path", "request_path", path), ("headers", "request_headers", headers)):
            fields[location], channels[channel] = sanitize_capture(value)
        return {"request": safe, "request_fields": fields,
                "logical_request": logical, "reset_epoch": context.reset_epoch, "redaction_manifest": channels}

    def _prepare_request(self, context: _FixtureArmContext, binding: Mapping[str, Any]) -> tuple[Any, dict[str, Any], str, dict[str, Any]]:
        request_ref = binding["request_ref"]
        template = self._request(request_ref)
        return self._apply_fresh_uses(
            context,
            request_ref=request_ref,
            actor_id=binding["actor_id"],
            body=copy.deepcopy(template.get("body")),
            query=copy.deepcopy(template.get("query") or {}),
            path=template["path"],
            headers=copy.deepcopy(template.get("headers") or {}),
        )

    def execute_producer(
        self,
        context: _FixtureArmContext,
        *, occurrence_index: int | None = None, repeated: bool = False, action_role: str = "producer",
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        slot = f"{'A' if context.arm == 'repeat_once' else 'B'}_action{occurrence_index}" if repeated else "P" if action_role == "producer" else action_role
        failure = self._slot_failure(context, slot)
        if failure is not None:
            self._counts["request_executions"] += 1
            raw_ref, raw = self._raw(
                context.candidate_id, slot, {"slot": slot, "status": "failed"}
            )
            return self._failed_record(context, slot, failure, raw_ref=raw_ref, raw=raw)
        binding = context.material.execution_binding["payload"][action_role]
        request_ref = binding.get("request_ref", context.material.candidate["producer"]["request_ref"])
        slot = f"{'A' if context.arm == 'repeat_once' else 'B'}_action{occurrence_index}" if repeated else "P" if action_role == "producer" else action_role
        step_result = context.run_facts.get("step_results", {}).get(slot)
        if context.arm == "temporal" and step_result is None:
            return self._failed_record(context, slot, "fixture_step_result_missing")
        if repeated and (context.prepared_request is None or step_result is None) or action_role == "inverse" and step_result is None:
            return self._failed_record(context, slot, "fixture_step_result_missing")
        body, query, physical_path, headers = copy.deepcopy(context.prepared_request) if repeated else self._prepare_request(context, binding)
        transport = {
            "method": binding["method"],
            "path": binding["path"],
            "body": body,
        }
        events = copy.deepcopy(context.prepared_binding_events) if repeated else self._consumer_events(
            context,
            request_ref=request_ref,
            actor_id=binding["actor_id"],
        )
        response = copy.deepcopy(step_result["body"] if step_result is not None else context.run_facts["producer_response"])
        capture_events = []
        for source in context.material.resource_binding_plans[context.arm]["sources"]:
            source_id = str(source["source_id"])
            if source_id not in context.pending_fresh_values:
                continue
            value = context.pending_fresh_values.pop(source_id)
            response = _put_typed_path(
                response, str(source["response_path"]), value
            )
            context.fresh_values[source_id] = value
            capture_events.append(self._creator_event(context, source))
        raw_ref, raw = self._raw(
            context.candidate_id,
            slot,
            {"transport_request": transport, "query": query, "response": response},
        )
        transport_status = step_result["status"] if step_result is not None else int(
            context.run_facts.get(
                "producer_status", 422 if context.arm == "negative_no_effect" else 200
            )
        )
        record = self._pass_record(slot, context.arm, raw_ref, raw)
        request_fields = {"method": binding["method"], "body": copy.deepcopy(body), "query": copy.deepcopy(query), "path": physical_path}
        request_fields["headers"], header_manifest = sanitize_capture(headers)
        record.update(
            {
                "actor_id": binding["actor_id"],
                "action_ref": binding.get("action_ref"),
                "checkpoint_id": slot, "occurrence_index": occurrence_index, "reset_epoch": context.reset_epoch,
                "request_identity_verified": bool(repeated and context.prepared_request == (body, query, physical_path, headers)),
                "request_fields": request_fields,
                "request_ref": request_ref,
                "request": copy.deepcopy(body),
                "transport_request": transport,
                "physical_transport_request": {**copy.deepcopy(transport), "path": physical_path},
                "physical_transport_metadata": {"query": copy.deepcopy(query), "request_headers": copy.deepcopy(request_fields["headers"])},
                "transport_request_shape_sha256": request_shape_sha256(transport),
                "response": response,
                "transport_status": transport_status,
                "transport_metadata": _transport_metadata(query),
                "binding_events": events,
                "fresh_capture_events": capture_events,
                "fresh_capture_error": None,
                "redaction_manifest": _empty_redaction_manifest(),
            }
        )
        record["redaction_manifest"]["request_headers"] = header_manifest
        if context.arm == "temporal":
            record["timing"] = copy.deepcopy(step_result.get("timing", {}))
        self._counts["request_executions"] += 1
        record = copy_numeric_sources(response, record)
        if isinstance(response, NumericObservation):
            record["response"] = copy.deepcopy(dict(response))
        if hasattr(body, "numeric_body"):
            record.numeric_request_body = copy.deepcopy(body.numeric_body)
        return record, {raw_ref: raw}

    def temporal_wait_until(self, context: _FixtureArmContext, deadline_ns: int) -> None:
        # Fixture timings come from explicit per-send facts, never wall time.
        del context, deadline_ns

    def execute_negative_producer(
        self,
        context: _FixtureArmContext,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        record, artifacts = self.execute_producer(context, **kwargs)
        status = record.get("transport_status")
        if (
            record.get("state") == "executed"
            and record.get("status") == "pass"
            and isinstance(status, int)
            and not (200 <= status < 300 or 400 <= status < 500)
        ):
            return self._failed_record(
                context,
                "P",
                f"producer_http_status_{status}",
                artifacts=artifacts,
            )
        return record, artifacts

    def execute_inverse(self, context: _FixtureArmContext):
        return self.execute_producer(context, action_role="inverse")

    def verify_identity_topology(self, context: _FixtureArmContext, topology: Mapping[str, Any]) -> bool:
        rows = context.run_facts.get("identity_observations", {})
        left, right = (rows.get(topology[key], {}) for key in ("left_actor_id", "right_actor_id"))
        if any(row.get("principal") in (None, "") or not row.get("session_id") for row in (left, right)):
            return False
        return ((canonical_json_bytes(left["principal"]) == canonical_json_bytes(right["principal"])) == (topology["principal_relation"] == "same")
                and (left["session_id"] == right["session_id"]) == (topology["session_relation"] == "same"))

    def negative_session_boundary(
        self,
        context: _FixtureArmContext,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        boundary = context.material.execution_material["protocol_shape"].get(
            "session_boundary"
        ) or {}
        material_present = context.run_facts.get("authorization_material_present")
        ref, payload = self._raw(
            context.candidate_id,
            "negative_session_boundary",
            {
                "recorded_boundary_event_id": boundary.get("event_id"),
                "authorization_material_absent": not material_present if type(material_present) is bool else None,
                "secret_values_persisted": False,
            },
        )
        if (
            context.arm != "negative_no_effect"
            or boundary.get("kind") not in {
                "recorded_logout_and_runtime_auth_absence",
                "recorded_auth_preserved",
            }
            or (
                material_present is not False
                and boundary.get("kind")
                == "recorded_logout_and_runtime_auth_absence"
            )
            or (
                material_present is not True
                and boundary.get("kind") == "recorded_auth_preserved"
            )
        ):
            return self._failed_record(
                context,
                "negative_session_boundary",
                "session_boundary_unclosed",
                raw_ref=ref,
                raw=payload,
            )
        return (
            self._pass_record(
                "negative_session_boundary", context.arm, ref, payload
            ),
            {ref: payload},
        )

    def observe_until_stable(
        self,
        context: _FixtureArmContext,
        settle_slot: str,
        observer_slot: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        policy = context.material.settle_policy
        elapsed_ns = 0
        artifacts: dict[str, bytes] = {}

        def monotonic_ns() -> int:
            return elapsed_ns

        def sleep(seconds: float) -> None:
            nonlocal elapsed_ns
            elapsed_ns += int(seconds * 1_000_000_000)

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
            monotonic_ns=monotonic_ns,
            sleep=sleep,
        )
        raw_ref, raw = self._raw(
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
            record = self._pass_record(settle_slot, context.arm, raw_ref, raw)
        else:
            record = self._failed_record(
                context,
                settle_slot,
                outcome.status,
                raw_ref=raw_ref,
                raw=raw,
            )[0]
        policy_ref = (
            next(
                ref
                for ref in context.material.artifact_bytes
                if ref.endswith("/settle_policy.json")
            )
            if context.material.output_level == "forensic" and context.arm in {"control", "treatment"}
            else "execution_material:settle_policy"
        )
        record.update(
            {
                "policy_ref": policy_ref,
                "policy_sha256": (
                    context.material.artifact_hashes[policy_ref]
                    if policy_ref != "execution_material:settle_policy"
                    else None
                ),
                "policy": copy.deepcopy(policy),
                "elapsed_ns": outcome.elapsed_ns,
                "poll_count": outcome.poll_count,
                "consecutive_identical": outcome.consecutive_identical,
                "projection_sha256": outcome.projection_sha256,
            }
        )
        self._counts["settle_executions"] += 1
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
        return dict(self._counts)

    def _request(self, request_ref: str) -> dict[str, Any]:
        value = (self._adapter.get("request_bindings") or {}).get(request_ref)
        if not isinstance(value, dict):
            raise ValueError(f"fixture runtime request missing: {request_ref}")
        return copy.deepcopy(value)

    def _creator_event(
        self,
        context: _FixtureArmContext,
        source: Mapping[str, Any],
    ) -> dict[str, Any]:
        actor = str(source["actor_id"])
        return {
            "event": "creator_value_captured",
            "actor_id": actor,
            "creator_actor_id": actor,
            "candidate_id": context.candidate_id,
            "arm": context.arm,
            "reset_epoch": context.reset_epoch,
            "binding_scope_id": binding_scope_id(
                context.candidate_id, context.arm, actor, context.reset_epoch
            ),
            "source_id": str(source["source_id"]),
            "creator_request_ref": str(source["creator_request_ref"]),
            "source_typed_path": str(source["response_path"]),
            "scalar_type": str(source["scalar_type"]),
            "value_sha256": _scalar_sha256(
                context.fresh_values[str(source["source_id"])]
            ),
        }

    def _consumer_events(
        self,
        context: _FixtureArmContext,
        *,
        request_ref: str,
        actor_id: str,
    ) -> list[dict[str, Any]]:
        plan = context.material.resource_binding_plans[context.arm]
        sources = {str(row["source_id"]): row for row in plan["sources"]}
        events = []
        for use in plan["uses"]:
            if (
                use["consumer_request_ref"] != request_ref
                or use["actor_id"] != actor_id
            ):
                continue
            source = sources[str(use["source_id"])]
            events.append(
                {
                    "event": "consumer_value_rebound",
                    "actor_id": actor_id,
                    "creator_actor_id": source["actor_id"],
                    "candidate_id": context.candidate_id,
                    "arm": context.arm,
                    "reset_epoch": context.reset_epoch,
                    "binding_scope_id": binding_scope_id(
                        context.candidate_id,
                        context.arm,
                        actor_id,
                        context.reset_epoch,
                    ),
                    "source_id": source["source_id"],
                    "creator_request_ref": source["creator_request_ref"],
                    "source_typed_path": source["response_path"],
                    "scalar_type": source["scalar_type"],
                    "value_sha256": _scalar_sha256(
                        context.fresh_values[str(source["source_id"])]
                    ),
                    "consumer_request_ref": request_ref,
                    "target_location": use["location"],
                    "target_typed_path": use["target_path"],
                }
            )
        return events

    def _apply_fresh_uses(
        self,
        context: _FixtureArmContext,
        *,
        request_ref: str,
        actor_id: str,
        body: Any,
        query: dict[str, Any],
        path: str,
        headers: dict[str, Any],
    ) -> tuple[Any, dict[str, Any], str, dict[str, Any]]:
        for use in context.material.resource_binding_plans[context.arm]["uses"]:
            if (
                use["consumer_request_ref"] != request_ref
                or use["actor_id"] != actor_id
            ):
                continue
            if use["location"] == "body":
                body = _set_typed_path(
                    body,
                    str(use["target_path"]),
                    context.fresh_values[str(use["source_id"])],
                )
            elif use["location"] == "query":
                query = _set_typed_path(
                    query,
                    str(use["target_path"]),
                    context.fresh_values[str(use["source_id"])],
                )
            elif use["location"] in {"path", "header"}:
                path, query, headers, body = _replace_location(
                    ResourceBindingUse(**use),
                    value=context.fresh_values[str(use["source_id"])],
                    path=path, query=query, headers=headers, body=body,
                )
            else:
                raise ValueError("fixture runtime binding location is unsupported")
        return body, query, path, headers

    def _creator_response(
        self,
        context: _FixtureArmContext,
        creator_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        response: dict[str, Any] = {}
        for event in creator_events:
            response = _put_typed_path(
                response,
                str(event["source_typed_path"]),
                context.fresh_values[str(event["source_id"])],
            )
        return response

    @staticmethod
    def _slot_failure(
        context: _FixtureArmContext, slot: str
    ) -> Mapping[str, Any] | None:
        fact_slot = {
            "workflow_reset": "Rt",
            "workflow_setup": "St",
            "workflow_before": "Ot0",
            "workflow_settle": "settle_t",
            "workflow_after": "Ot1",
        }.get(slot, slot)
        value = (context.run_facts.get("slot_failures") or {}).get(fact_slot)
        if value is None:
            return None
        if not isinstance(value, Mapping) or not isinstance(value.get("reason_code"), str):
            raise ValueError("fixture slot failure fact is malformed")
        return value

    @staticmethod
    def _failed_record(
        context: _FixtureArmContext,
        slot: str,
        failure: Mapping[str, Any],
        *,
        raw_ref: str,
        raw: bytes,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        error_ref = f"M12/{context.candidate_id}/raw/{slot}.error.json"
        error = canonical_json_bytes(
            {"reason_code": str(failure["reason_code"]), "fixture_local": True}
        )
        return (
            {
                "slot": slot,
                "state": "executed",
                "raw_ref": raw_ref,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "started_at": TS,
                "finished_at": TS,
                "status": "failed",
                "arm": context.arm,
                "error_ref": error_ref,
                "error_sha256": hashlib.sha256(error).hexdigest(),
                "reason_code": str(failure["reason_code"]),
            },
            {raw_ref: raw, error_ref: error},
        )

    @staticmethod
    def _pass_record(slot: str, arm: str, ref: str, payload: bytes) -> dict[str, Any]:
        return {
            "slot": slot,
            "state": "executed",
            "raw_ref": ref,
            "raw_sha256": hashlib.sha256(payload).hexdigest(),
            "started_at": TS,
            "finished_at": TS,
            "status": "pass",
            "arm": arm,
        }

    @staticmethod
    def _raw(candidate_id: str, slot: str, value: Mapping[str, Any]) -> tuple[str, bytes]:
        ref = f"M12/{candidate_id}/raw/{slot}.json"
        return ref, canonical_json_bytes(value)


class CurrentRouteSCollector:
    """Construct complete write-through evidence from any execution-facts runtime."""

    def collect(
        self,
        material: RouteSPreLiveMaterializedCandidate,
        runtime: CurrentRouteSSubjectRuntime,
        *,
        artifact_writer: RouteSArtifactWriter,
        output_level: str,
    ) -> RouteSCollectedEvidence:
        if output_level not in {"paper", "debug", "forensic"}:
            raise ValueError(f"unknown current output level: {output_level!r}")
        forensic = output_level == "forensic"
        artifact_bytes = dict(material.artifact_bytes)
        artifact_hashes = dict(material.artifact_hashes)
        protocol: dict[str, Any] = {}
        write_sequence: list[str] = []
        partial_records: list[dict[str, Any]] = []
        partial_states = {slot: "pending" for slot in PROTOCOL_SLOTS}
        partial_slot_refs: dict[str, tuple[str, ...]] = {}
        previous_partial_sha256: str | None = None
        partial_prefix_open = True

        def write_artifact(ref: str, payload: bytes) -> None:
            if forensic:
                write_sequence.append(ref)
            if forensic or (
                output_level == "debug" and "raw" in ref.split("/")
            ):
                artifact_writer(ref, payload)

        def merge(rows: Mapping[str, bytes]) -> None:
            if not forensic:
                rows = (
                    {
                        ref: payload
                        for ref, payload in rows.items()
                        if output_level == "debug" and "raw" in ref.split("/")
                    }
                )
            _merge_artifacts(
                artifact_bytes,
                artifact_hashes,
                rows,
                artifact_writer=write_artifact,
            )

        def append_partial(
            slot: str,
            ref: str | None,
            digest: str | None,
        ) -> None:
            nonlocal previous_partial_sha256
            if not forensic:
                return
            record = {
                "schema_version": "ui-semantics-route-s-partial-certificate-v2",
                "certificate_status": "partial",
                "candidate_id": material.candidate_id,
                "record_sequence": len(partial_records),
                "recorded_at": TS,
                "previous_record_sha256": previous_partial_sha256,
                "last_closed_slot": slot,
                "last_closed_artifact_ref": ref,
                "last_closed_artifact_sha256": digest,
                "protocol_slot_states": dict(partial_states),
                "outcome": "pending",
                "provider_calls": 0,
                "live_result_eligible": False,
            }
            validate_partial_certificate_v2(record)
            label = "none" if slot == "none" else slot
            partial_ref = (
                f"M12/{material.candidate_id}/partials/"
                f"{len(partial_records):03d}-{label}.json"
            )
            merge({partial_ref: canonical_json_bytes(record)})
            partial_records.append(record)
            previous_partial_sha256 = canonical_sha256(record)

        def record_slot(
            slot: str,
            record: Mapping[str, Any],
            rows: Mapping[str, bytes],
        ) -> None:
            nonlocal partial_prefix_open
            scientific_record = copy_numeric_sources(record, copy.deepcopy(dict(record)))
            if (
                slot in {"Sc", "St"}
                and record.get("state") == "executed"
                and record.get("status") == "pass"
            ):
                raw = rows.get(str(record.get("raw_ref") or ""))
                if raw is None:
                    raise ValueError("Route-S setup evidence payload missing")
                value = json.loads(raw)
                setup = value.get("setup") if isinstance(value, dict) else None
                if not isinstance(setup, list):
                    raise ValueError("Route-S setup evidence rows missing")
                scientific_record["setup_executions"] = [
                    {
                        "actor_id": row.get("actor_id"),
                        "request_ref": row.get("request_ref"),
                        "status": row.get("status"),
                        "binding_events": copy.deepcopy(row.get("binding_events") or []),
                    }
                    for row in setup
                    if isinstance(row, dict)
                ]
            protocol[slot] = (
                copy.deepcopy(scientific_record)
                if forensic
                else _compact_protocol_record(slot, scientific_record)
            )
            merge(rows)
            if not forensic:
                return
            if not partial_prefix_open:
                return
            if record.get("state") != "executed":
                partial_prefix_open = False
                return
            ref = str(record["raw_ref"])
            digest = artifact_hashes.get(ref)
            if digest is None:
                raise ValueError(f"Route-S partial source artifact missing: {slot}")
            partial_states[slot] = "executed"
            partial_slot_refs[slot] = (ref,)
            append_partial(slot, ref, digest)

        def close_tail(slots: tuple[str, ...]) -> None:
            for pending_slot in slots:
                record_slot(
                    pending_slot,
                    {
                        "slot": pending_slot,
                        "state": "not_executed",
                        "reason_code": "prior_failure",
                    },
                    {},
                )

        def split_settle_artifacts(
            final_record: Mapping[str, Any],
            rows: Mapping[str, bytes],
        ) -> tuple[dict[str, bytes], dict[str, bytes]]:
            if final_record.get("state") != "executed":
                return dict(rows), {}
            final_ref = str(final_record.get("raw_ref") or "")
            final_payload = rows.get(final_ref)
            if final_payload is None:
                raise ValueError("Route-S final observer artifact missing")
            return (
                {ref: payload for ref, payload in rows.items() if ref != final_ref},
                {final_ref: final_payload},
            )

        def failed(record: Mapping[str, Any]) -> bool:
            return record.get("state") != "executed" or record.get("status") != "pass"

        if forensic:
            append_partial("none", None, None)

        control, record, rows = runtime.begin_arm(material, "control")
        record_slot("Rc", record, rows)
        if failed(record):
            close_tail(PROTOCOL_SLOTS[1:])
        else:
            record, rows = runtime.execute_setup(control, "Sc")
            record_slot("Sc", record, rows)
            if failed(record):
                close_tail(PROTOCOL_SLOTS[2:])
            else:
                record, rows = runtime.observe(control, "Oc1")
                record_slot("Oc1", record, rows)
                if failed(record):
                    close_tail(PROTOCOL_SLOTS[3:])
                else:
                    settle_record, final_record, rows = runtime.observe_until_stable(
                        control, "settle_c", "Oc2"
                    )
                    settle_rows, final_rows = split_settle_artifacts(
                        final_record, rows
                    )
                    record_slot("settle_c", settle_record, settle_rows)
                    if failed(settle_record):
                        close_tail(PROTOCOL_SLOTS[4:])
                    else:
                        record_slot("Oc2", final_record, final_rows)
                        if failed(final_record):
                            close_tail(PROTOCOL_SLOTS[5:])
                        else:
                            treatment, record, rows = runtime.begin_arm(
                                material, "treatment"
                            )
                            record_slot("Rt", record, rows)
                            if failed(record):
                                close_tail(PROTOCOL_SLOTS[6:])
                            else:
                                record, rows = runtime.execute_setup(treatment, "St")
                                record_slot("St", record, rows)
                                if failed(record):
                                    close_tail(PROTOCOL_SLOTS[7:])
                                else:
                                    record, rows = runtime.observe(treatment, "Ot0")
                                    record_slot("Ot0", record, rows)
                                    if failed(record):
                                        close_tail(PROTOCOL_SLOTS[8:])
                                    else:
                                        record, rows = runtime.execute_producer(treatment)
                                        record_slot("P", record, rows)
                                        if failed(record):
                                            close_tail(PROTOCOL_SLOTS[9:])
                                        else:
                                            (
                                                settle_record,
                                                final_record,
                                                rows,
                                            ) = runtime.observe_until_stable(
                                                treatment, "settle_t", "Ot1"
                                            )
                                            settle_rows, final_rows = (
                                                split_settle_artifacts(
                                                    final_record, rows
                                                )
                                            )
                                            record_slot(
                                                "settle_t",
                                                settle_record,
                                                settle_rows,
                                            )
                                            if failed(settle_record):
                                                close_tail(PROTOCOL_SLOTS[10:])
                                            else:
                                                record_slot(
                                                    "Ot1",
                                                    final_record,
                                                    final_rows,
                                                )

        if tuple(protocol) != PROTOCOL_SLOTS:
            raise ValueError("Route-S collector protocol order drift")
        if forensic:
            validate_partial_chain_v2(
                partial_records,
                artifact_hashes=artifact_hashes,
                slot_artifact_refs=partial_slot_refs,
            )
        if forensic:
            pre_scan_ref = f"M12/{material.candidate_id}/pre_render_scan.json"
            pre_scope = dict(sorted(material.artifact_hashes.items()))
            pre_scan_value = {
                "schema_version": "ui-semantics-route-s-scan-report-v1",
                "phase": "pre_render",
                "status": "pass",
                "scope_refs": sorted(pre_scope),
                "scope_hashes": pre_scope,
                "finding_records": [],
                "findings_count": 0,
                "provider_calls": 0,
                "no_feedback": True,
            }
            validate_scan_report_v1(pre_scan_value)
            pre_scan = canonical_json_bytes(pre_scan_value)
            no_feedback_ref = f"M12/{material.candidate_id}/no_feedback.json"
            no_feedback = canonical_json_bytes(
                {"provider_calls": 0, "no_feedback": True, "execution_only": True}
            )
            merge({pre_scan_ref: pre_scan, no_feedback_ref: no_feedback})
            sequence_ref = f"M12/{material.candidate_id}/write_through_sequence.json"
            sequence_payload = canonical_json_bytes(
                {
                    "schema_version": "uisemtest-route-s-write-through-sequence-v1",
                    "candidate_id": material.candidate_id,
                    "ordered_artifact_refs_before_self": list(write_sequence),
                    "partial_write_through": True,
                    "sequence_excludes_self": True,
                }
            )
            merge({sequence_ref: sequence_payload})
        evidence = {
            "schema_version": (
                "ui-semantics-route-s-execution-evidence-v5"
                if forensic
                else "uisemtest-current-route-s-execution-evidence-v1"
            ),
            **({} if forensic else {"document_kind": "execution_evidence"}),
            "candidate": copy.deepcopy(material.candidate),
            "projection_plan": copy.deepcopy(material.projection_plan),
            "protocol": protocol,
            "sessions": runtime.sessions(),
            "cross_arm_reuse_refs": [],
            **(
                {
                    "pins": copy.deepcopy(material.scientific_pins),
                    "run_attestation": {
                        "pre_render_scan_ref": pre_scan_ref,
                        "pre_render_scan_sha256": hashlib.sha256(pre_scan).hexdigest(),
                        "pre_render_scan_status": "pass",
                        "pre_render_findings": 0,
                        "provider_calls": 0,
                        "no_feedback": True,
                        "no_feedback_ref": no_feedback_ref,
                        "no_feedback_sha256": hashlib.sha256(no_feedback).hexdigest(),
                    },
                }
                if forensic
                else {}
            ),
        }
        if not forensic:
            validate_current_route_s_evaluation(evidence)
        payload = canonical_json_bytes(evidence)
        sensitive_values_method = getattr(runtime, "sensitive_values_in_memory", None)
        sensitive_values = (
            tuple(sensitive_values_method())
            if callable(sensitive_values_method)
            else ()
        )
        return RouteSCollectedEvidence(
            evidence=evidence,
            execution_evidence_bytes=payload,
            artifact_hashes=artifact_hashes,
            artifact_bytes=artifact_bytes,
            partial_records=tuple(partial_records),
            artifact_write_sequence=tuple(write_sequence),
            runtime_counts=runtime.counts(),
            volatile_sensitive_values=sensitive_values,
        )


def _compact_protocol_record(
    slot: str, record: Mapping[str, Any]
) -> dict[str, Any]:
    from ..dsl import copy_numeric_sources
    value = copy_numeric_sources(record, copy.deepcopy(dict(record)))
    value["raw_ref"] = f"protocol:{slot}"
    for key in (
        "raw_sha256",
        "error_ref",
        "error_sha256",
        "provenance_refs",
        "policy_ref",
        "policy_sha256",
    ):
        value.pop(key, None)
    for domain in value.get("observer_domains") or []:
        domain.pop("capability_ref", None)
        domain.pop("capability_sha256", None)
    return value


def _merge_artifacts(
    artifact_bytes: dict[str, bytes],
    artifact_hashes: dict[str, str],
    rows: Mapping[str, bytes],
    *,
    artifact_writer: RouteSArtifactWriter | None = None,
) -> None:
    for ref, payload in rows.items():
        if ref in artifact_bytes and artifact_bytes[ref] != payload:
            raise CandidateLocalFailure(
                "M12", "writer", "candidate_artifact_collision"
            )
        if artifact_writer is not None:
            artifact_writer(ref, payload)
        artifact_bytes[ref] = payload
        artifact_hashes[ref] = hashlib.sha256(payload).hexdigest()


def _empty_redaction_manifest() -> dict[str, list[dict[str, Any]]]:
    return {
        "request": [],
        "request_query": [],
        "request_headers": [],
        "response": [],
        "response_headers": [],
    }


def _transport_metadata(query: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "query": copy.deepcopy(dict(query)),
        "request_headers": {},
        "response_headers": {},
        "sensitive_values_persisted": False,
    }


def _set_typed_path(value: Any, path: str, replacement: Any) -> Any:
    if not path.startswith("$.") or "[" in path:
        raise ValueError("fixture binding path must be a dotted object path")
    result = copy.deepcopy(value)
    if not isinstance(result, dict):
        raise ValueError("fixture binding target root must be an object")
    current = result
    parts = path[2:].split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            raise ValueError("fixture binding target path is absent")
        current = child
    if parts[-1] not in current:
        raise ValueError("fixture binding target leaf is absent")
    current[parts[-1]] = replacement
    if hasattr(result, "numeric_body"):
        result.numeric_body = _put_typed_path(result.numeric_body, path, replacement)
    return result


def _put_typed_path(value: Any, path: str, replacement: Any) -> dict[str, Any]:
    if not path.startswith("$.") or "[" in path:
        raise ValueError("fixture source path must be a dotted object path")
    result = copy.deepcopy(value)
    if not isinstance(result, dict):
        raise ValueError("fixture source root must be an object")
    current = result
    parts = path[2:].split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ValueError("fixture source path collides with a scalar")
        current = child
    current[parts[-1]] = replacement
    if hasattr(result, "numeric_body"):
        result.numeric_body = _put_typed_path(result.numeric_body, path, replacement)
    return result


def _fixture_scalar(
    scalar_type: str, candidate_id: str, arm: str, source_id: str
) -> Any:
    seed = int(_sha(f"{candidate_id}:{arm}:{source_id}")[:12], 16)
    if scalar_type == "string":
        return f"fixture-fresh:{candidate_id}:{arm}:{source_id[:12]}"
    if scalar_type == "integer":
        return seed
    if scalar_type == "number":
        return float(seed) + 0.5
    if scalar_type == "boolean":
        return bool(seed % 2)
    raise ValueError("fixture fresh scalar type is unsupported")


def _scalar_sha256(value: Any) -> str:
    if isinstance(value, bool):
        kind = "boolean"
    elif isinstance(value, int):
        kind = "integer"
    elif isinstance(value, float):
        kind = "number"
    elif isinstance(value, str):
        kind = "string"
    elif value is None:
        kind = "null"
    else:
        raise ValueError("fixture fresh value must be a JSON scalar")
    return hashlib.sha256(
        json.dumps(
            {"type": kind, "value": value},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def construct_v1_route_s_certificate(
    collected: Any,
    material: Any,
) -> dict[str, Any]:
    """Current construction boundary: schema, evaluator, and outer closure."""


    if material.output_level != "forensic":
        validate_current_route_s_evaluation(collected.evidence)
        envelope = build_current_route_s_certificate(
            collected.evidence,
            execution_material=material.execution_material,
            execution_evidence_sha256=hashlib.sha256(
                collected.execution_evidence_bytes
            ).hexdigest(),
        )
        validate_current_route_s_evaluation(envelope)
        return envelope

    validate_execution_evidence_v5(collected.evidence)
    envelope = build_route_s_certificate_v5(
        collected.evidence,
        execution_evidence_bytes=collected.execution_evidence_bytes,
        execution_binding=material.execution_binding,
        pre_live_binding_pins=material.pre_live_binding_pins,
        pre_live_binding_pins_bytes=material.pre_live_binding_pins_bytes,
        expected_pre_live_binding_pins_ref=material.pre_live_binding_pins[
            "artifact_ref"
        ],
        expected_pre_live_binding_pins_sha256=material.pre_live_binding_pins[
            "artifact_sha256"
        ],
        artifact_hashes=collected.artifact_hashes,
        artifact_bytes=collected.artifact_bytes,
        expected_pins=material.scientific_pins,
        execution_material=material.execution_material,
    )
    validate_outer_envelope_v5(envelope, evidence=collected.evidence)
    return envelope

__all__ = [
    "CurrentRouteSCollector",
    "DeterministicFixtureRuntime",
    "RouteSArtifactWriter",
    "RouteSCollectedEvidence",
    "CurrentRouteSSubjectRuntime",
    "construct_v1_route_s_certificate",
]
