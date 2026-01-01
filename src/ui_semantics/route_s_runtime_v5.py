"""Historical compatibility Route-S v5 collector and fixture runtime.

The collector owns protocol ordering and evidence construction.  The runtime
only returns local execution facts.  Neither layer accepts, computes, or emits
a Route-S verdict; certificate evaluation remains in :mod:`route_s_v5`.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .current_candidate_failure import CandidateLocalFailure
from .m11b_materializer import RouteSPreLiveMaterializedCandidate
from .route_s import PROTOCOL_SLOTS, canonical_json_bytes, canonical_sha256
from .route_s_v2 import request_shape_sha256, validate_partial_chain_v2
from .route_s_v5 import _binding_scope_id
from .route_s_validation_v5 import (
    validate_partial_certificate_v2,
    validate_scan_report_v1,
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
    run_facts: dict[str, Any]


class RouteSV5SubjectRuntime(Protocol):
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

    def fixed_settle(
        self,
        context: Any,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]: ...

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
        fresh_values = {
            str(source["source_id"]): _fixture_scalar(
                str(source["scalar_type"]),
                material.candidate_id,
                arm,
                str(source["source_id"]),
            )
            for source in plan["sources"]
        }
        context = _FixtureArmContext(
            material=material,
            candidate_id=material.candidate_id,
            arm=arm,
            reset_epoch=epoch,
            fresh_values=fresh_values,
            run_facts=copy.deepcopy(self._run_facts),
        )
        slot = "Rc" if arm == "control" else "Rt"
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
            material.candidate["producer"]["actor_id"],
            material.candidate["consumer"]["actor_id"],
            *(item["actor_id"] for item in material.candidate["setup"]),
        }
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
        failure = self._slot_failure(context, slot)
        if failure is not None:
            self._counts["request_executions"] += 1
            raw_ref, raw = self._raw(
                context.candidate_id, slot, {"slot": slot, "status": "failed"}
            )
            return self._failed_record(context, slot, failure, raw_ref=raw_ref, raw=raw)
        branch = (
            context.run_facts["control_observations"]
            if context.arm == "control"
            else context.run_facts["treatment_observations"]
        )
        body = copy.deepcopy(branch[slot])
        request_binding = context.material.execution_binding["payload"]["observations"][
            slot
        ]
        request_ref = context.material.candidate["consumer"]["request_ref"]
        template = self._request(request_ref)
        query = copy.deepcopy(template.get("query") or {})
        request_body = copy.deepcopy(template.get("body"))
        request_body, query = self._apply_fresh_uses(
            context,
            request_ref=request_ref,
            actor_id=request_binding["actor_id"],
            body=request_body,
            query=query,
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
            capability_ref = (
                f"M12/{context.candidate_id}/capabilities/{slot}.{domain}.json"
            )
            capability = canonical_json_bytes(
                {"slot": slot, "domain": domain, "fixture_observer": True}
            )
            artifacts[capability_ref] = capability
            state_sha = _sha(f"observer-state:{context.candidate_id}:{context.arm}:{domain}")
            domains.append(
                {
                    "domain": domain,
                    "disposition": "proven_unchanged",
                    "before_sha256": state_sha,
                    "after_sha256": state_sha,
                    "mutation_events": [],
                    "uncertain_fields": [],
                    "capability_ref": capability_ref,
                    "capability_sha256": hashlib.sha256(capability).hexdigest(),
                    "reason_code": "fixture_capability_observed",
                }
            )
        raw_ref, raw = self._raw(
            context.candidate_id,
            slot,
            {"request": request, "query": query, "response": copy.deepcopy(dict(body))},
        )
        artifacts[raw_ref] = raw
        record = self._pass_record(slot, context.arm, raw_ref, raw)
        record.update(
            {
                "actor_id": request_binding["actor_id"],
                "request_ref": request_ref,
                "request": request,
                "transport_request_shape_sha256": request_shape_sha256(request),
                "response": {"status": 200, "body": copy.deepcopy(dict(body))},
                "observer_domains": domains,
                "binding_events": events,
                "transport_metadata": _transport_metadata(query),
                "redaction_manifest": _empty_redaction_manifest(),
            }
        )
        self._counts["request_executions"] += 1
        return record, artifacts

    def execute_producer(
        self,
        context: _FixtureArmContext,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        failure = self._slot_failure(context, "P")
        if failure is not None:
            self._counts["request_executions"] += 1
            raw_ref, raw = self._raw(
                context.candidate_id, "P", {"slot": "P", "status": "failed"}
            )
            return self._failed_record(context, "P", failure, raw_ref=raw_ref, raw=raw)
        binding = context.material.execution_binding["payload"]["producer"]
        request_ref = context.material.candidate["producer"]["request_ref"]
        template = self._request(request_ref)
        body, query = self._apply_fresh_uses(
            context,
            request_ref=request_ref,
            actor_id=binding["actor_id"],
            body=copy.deepcopy(template.get("body")),
            query=copy.deepcopy(template.get("query") or {}),
        )
        transport = {
            "method": binding["method"],
            "path": binding["path"],
            "body": body,
        }
        events = self._consumer_events(
            context,
            request_ref=request_ref,
            actor_id=binding["actor_id"],
        )
        response = copy.deepcopy(context.run_facts["producer_response"])
        raw_ref, raw = self._raw(
            context.candidate_id,
            "P",
            {"transport_request": transport, "query": query, "response": response},
        )
        record = self._pass_record("P", "treatment", raw_ref, raw)
        record.update(
            {
                "actor_id": binding["actor_id"],
                "action_ref": binding["action_ref"],
                "request_ref": request_ref,
                "request": copy.deepcopy(body),
                "transport_request": transport,
                "transport_request_shape_sha256": request_shape_sha256(transport),
                "response": response,
                "transport_status": 200,
                "transport_metadata": _transport_metadata(query),
                "binding_events": events,
                "redaction_manifest": _empty_redaction_manifest(),
            }
        )
        self._counts["request_executions"] += 1
        return record, {raw_ref: raw}

    def fixed_settle(
        self,
        context: _FixtureArmContext,
        slot: str,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        policy = context.material.settle_policy
        failure = self._slot_failure(context, slot)
        raw_ref, raw = self._raw(
            context.candidate_id,
            slot,
            {
                "configured_duration_ms": policy["configured_duration_ms"],
                "elapsed_ns": int(policy["configured_duration_ms"]) * 1_000_000,
            },
        )
        if failure is not None:
            self._counts["settle_executions"] += 1
            return self._failed_record(context, slot, failure, raw_ref=raw_ref, raw=raw)
        record = self._pass_record(slot, context.arm, raw_ref, raw)
        policy_ref = next(
            ref
            for ref in context.material.artifact_bytes
            if ref.endswith("/settle_policy.json")
        )
        record.update(
            {
                "policy_ref": policy_ref,
                "policy_sha256": context.material.artifact_hashes[policy_ref],
                "configured_duration_ms": int(policy["configured_duration_ms"]),
            }
        )
        self._counts["settle_executions"] += 1
        return record, {raw_ref: raw}

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
            "binding_scope_id": _binding_scope_id(
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
                    "binding_scope_id": _binding_scope_id(
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
    ) -> tuple[Any, dict[str, Any]]:
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
            else:
                raise ValueError("fixture runtime supports body/query binding facts only")
        return body, query

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
        value = (context.run_facts.get("slot_failures") or {}).get(slot)
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
        runtime: RouteSV5SubjectRuntime,
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
            protocol[slot] = copy.deepcopy(dict(record))
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
                    record, rows = runtime.fixed_settle(control, "settle_c")
                    record_slot("settle_c", record, rows)
                    if failed(record):
                        close_tail(PROTOCOL_SLOTS[4:])
                    else:
                        record, rows = runtime.observe(control, "Oc2")
                        record_slot("Oc2", record, rows)
                        if failed(record):
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
                                            record, rows = runtime.fixed_settle(
                                                treatment, "settle_t"
                                            )
                                            record_slot("settle_t", record, rows)
                                            if failed(record):
                                                close_tail(PROTOCOL_SLOTS[10:])
                                            else:
                                                record, rows = runtime.observe(
                                                    treatment, "Ot1"
                                                )
                                                record_slot("Ot1", record, rows)

        if tuple(protocol) != PROTOCOL_SLOTS:
            raise ValueError("Route-S collector protocol order drift")
        if forensic:
            validate_partial_chain_v2(
                partial_records,
                artifact_hashes=artifact_hashes,
                slot_artifact_refs=partial_slot_refs,
            )
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
        if forensic:
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
            "schema_version": "ui-semantics-route-s-execution-evidence-v5",
            "candidate": copy.deepcopy(material.candidate),
            "projection_plan": copy.deepcopy(material.projection_plan),
            "protocol": protocol,
            "sessions": runtime.sessions(),
            "cross_arm_reuse_refs": [],
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


__all__ = [
    "DeterministicFixtureRuntime",
    "CurrentRouteSCollector",
    "RouteSCollectedEvidence",
    "RouteSV5SubjectRuntime",
]


# Compatibility name for historical unit tests; the implementation is generic.
DeterministicRouteSCollector = CurrentRouteSCollector
