"""Minimal lifecycle-workflow (V4) execution over current runtime primitives."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..current_route_s import canonical_json_bytes
from ..current_settle import route_observer_is_pure
from ..dsl import (copy_numeric_sources, request_numeric_observation, PredicateNotEvaluable, evaluate_predicate, evaluate_predicate_result, evaluate_workflow_applicability,
                   is_workflow_effect_predicate, workflow_applicability_predicate)
from ..route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    reject_redacted_predicate_dependencies,
    predicate_value_refs,
)


@dataclass(frozen=True)
class LifecycleCollectedEvidence:
    evidence: dict[str, Any]
    execution_evidence_bytes: bytes
    artifact_hashes: dict[str, str]
    artifact_bytes: dict[str, bytes]
    partial_records: tuple[dict[str, Any], ...]
    artifact_write_sequence: tuple[str, ...]
    runtime_counts: dict[str, int]
    volatile_sensitive_values: tuple[str, ...] = ()


def execute_lifecycle_workflow(
    material: Any,
    runtime: Any,
    *,
    artifact_writer: Callable[[str, bytes], None],
    output_level: str,
) -> tuple[LifecycleCollectedEvidence, dict[str, Any], dict[str, Any]]:
    """Run one frozen lifecycle workflow, including deferred create/read."""

    del artifact_writer, output_level
    artifacts = dict(material.artifact_bytes)
    predicate = copy.deepcopy(material.candidate["primary_predicate"])
    applicability = None

    def add(rows: Mapping[str, bytes]) -> None:
        for ref, payload in rows.items():
            artifacts[ref] = payload

    context, reset, rows = runtime.begin_arm(material, "workflow")
    add(rows)
    protocol: dict[str, Any] = {"reset": copy.deepcopy(reset)}
    shape = material.execution_material["protocol_shape"]
    workflow_kind = shape.get("workflow_kind", "before_write_after")
    create_capture_read = workflow_kind == "create_capture_read"
    no_before = workflow_kind in {"create_capture_read", "postcondition_read"}
    sequence = [
        ("setup", lambda: runtime.execute_setup(context, "workflow_setup")),
    ]
    if not no_before:
        sequence.append(
            ("before", lambda: runtime.observe(context, "workflow_before"))
        )
    sequence.append(("producer", lambda: runtime.execute_producer(context)))
    if workflow_kind == "inverse_restoration":
        sequence.extend([("intermediate", lambda: runtime.observe(context, "workflow_intermediate")),
                         ("inverse", lambda: runtime.execute_inverse(context))])
    failed_step = "reset" if _failed(reset) else None
    capture_failure = None
    if failed_step is None:
        for step, call in sequence:
            record, rows = call()
            add(rows)
            protocol[step] = copy.deepcopy(record)
            if _failed(record):
                failed_step = step
                break
            if step == "before" and is_workflow_effect_predicate(predicate) and not route_observer_is_pure(record):
                protocol[step].update({"status": "failed", "reason_code": "observer_mutating_or_uncertain"})
                failed_step = step
                break
            if step == "before" and workflow_applicability_predicate(predicate) is not None:
                observations = {"before": record["response"]}
                sources = {"before": ((record, "response"),)}
                try:
                    if any(ref["role"] == "producer_request" for ref in predicate_value_refs(workflow_applicability_predicate(predicate))):
                        prepare = getattr(runtime, "prepare_producer", None)
                        if not callable(prepare):
                            raise KeyError("producer_request")
                        # Reuse the HTTP request slot's registered failures at
                        # this earlier preparation boundary. The import stays
                        # local because the runtime factory also loads V4.
                        from ..current_http_runtime import (
                            BaselineRequestShapeLossError,
                            RelationExecutionError,
                            ResourceRebindingError,
                            UnresolvedRequestMaterialError,
                            _is_candidate_local_slot_error,
                        )
                        try:
                            prepared = prepare(context)
                        except (
                            BaselineRequestShapeLossError,
                            RelationExecutionError,
                            ResourceRebindingError,
                            UnresolvedRequestMaterialError,
                        ) as error:
                            if not _is_candidate_local_slot_error(error):
                                raise
                            protocol["producer"] = {
                                "state": "not_executed",
                                "status": "failed",
                                "reason_code": type(error).__name__,
                            }
                            failed_step = "producer"
                            break
                        observations["producer_request"] = request_numeric_observation(prepared, prepared["request"])
                        sources["producer_request"] = tuple((prepared, channel) for channel in ("request", "request_query", "request_path", "request_headers"))
                    applicability = evaluate_workflow_applicability(
                        predicate, observations,
                        dependency_checker=lambda atom: reject_redacted_predicate_dependencies(atom, sources),
                    )
                except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
                    applicability = {"status": "not_evaluable", "observed": {}, "reason_code": _predicate_failure_reason(error)}
                protocol["applicability"] = {**copy.deepcopy(applicability), "checked_before_action": True}
                if applicability["status"] != "satisfied":
                    break
            if step == "before" and material.candidate.get("contract_kind") == "C03" and predicate["family"] == "P01":
                exists = copy.deepcopy(predicate)
                exists["target"]["role"] = "before"
                exists["operator"] = "exists"
                exists["absent_statuses"] = []
                prepared = runtime.prepare_producer(context)
                check = evaluate_predicate_result(exists, {"before": record["response"], "producer_request": request_numeric_observation(prepared, prepared["request"])})
                applicability = {"status": "satisfied" if check["satisfied"] is True else "not_evaluable", "observed": check["observed"], "reason_code": None if check["satisfied"] is True else "delete_target_not_established"}
                protocol["applicability"] = {**applicability, "checked_before_action": True}
                if check["satisfied"] is not True:
                    break
            if (
                create_capture_read
                and step == "producer"
                and record.get("fresh_capture_error") is not None
            ):
                capture_failure = str(record["fresh_capture_error"])
                break
    applicability_failed = applicability is not None and applicability["status"] != "satisfied"
    if failed_step is None and capture_failure is None and not applicability_failed:
        settle, after, rows = runtime.observe_until_stable(
            context, "workflow_settle", "workflow_after"
        )
        add(rows)
        protocol["settle"] = copy.deepcopy(settle)
        protocol["after"] = copy.deepcopy(after)
        if _failed(settle):
            failed_step = "settle"
        elif _failed(after):
            failed_step = "after"
    if no_before:
        protocol.setdefault(
            "before",
            {
                "state": "not_applicable",
                "reason_code": f"{workflow_kind}_has_no_before",
            },
        )
    for step in ("setup", "before", "producer", "settle", "after"):
        protocol.setdefault(
            step,
            {"state": "not_executed", "reason_code": "prior_failure"},
        )

    predicate_result = None
    if failed_step is None and capture_failure is None and not applicability_failed:
        used_in_memory_predicate = False
        try:
            dependency_roles = {
                "after": ((protocol["after"], "response"),),
                "producer_request": tuple((protocol["producer"], channel) for channel in ("request", "request_query", "request_path", "request_headers")),
                "producer_response": ((protocol["producer"], "response"),),
            }
            if not no_before:
                dependency_roles["before"] = (
                    (protocol["before"], "response"),
                )
            observations = {
                    "after": protocol["after"]["response"],
                    "producer_request": request_numeric_observation(protocol["producer"], protocol["producer"].get("request")),
                    "producer_response": copy_numeric_sources(protocol["producer"], {"body": protocol["producer"]["response"]}),
            }
            observations["producer_status"] = {"body": protocol["producer"].get("transport_status")}
            if not no_before:
                observations["before"] = protocol["before"]["response"]
            evaluated = evaluate_predicate_result(predicate, observations,
                dependency_checker=lambda atom, **_kwargs: reject_redacted_predicate_dependencies(atom, dependency_roles))
            satisfied, observed = evaluated["satisfied"], evaluated["observed"]
            if evaluated["reason_code"] == "sensitive_material_unavailable":
                recovered = _evaluate_in_memory_predicate(runtime, context, predicate)
                if recovered is not None:
                    satisfied, observed = recovered
                    used_in_memory_predicate = True
            if satisfied is None:
                raise PredicateNotEvaluable(evaluated["reason_code"], observed)
        except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
            satisfied = None
            observed = error.observed if isinstance(error, PredicateNotEvaluable) else {}
            reason_code = _predicate_failure_reason(error)
        else:
            reason_code = None
            observed = (
                observed
                if used_in_memory_predicate
                else _published_observation(predicate, observed)
            )
            if predicate["family"] == "P02":
                observed = {"values_equal": satisfied}
        predicate_result = {
            "family": predicate["family"],
            "status": (
                "satisfied" if satisfied is True else
                "violated" if satisfied is False else
                "not_evaluable"
            ),
            "observed": observed,
            "reason_code": reason_code,
        }
    elif applicability_failed:
        predicate_result = {"family": predicate["family"], "status": "not_evaluable",
                            "observed": {}, "reason_code": applicability["reason_code"]}
    elif capture_failure is not None:
        predicate_result = {
            "family": predicate["family"],
            "status": "not_evaluable",
            "observed": {},
            "reason_code": capture_failure,
        }

    evidence = {
        "schema_version": "uisemtest-current-v4-execution-evidence-v1",
        "candidate": copy.deepcopy(material.candidate),
        "workflow_plan": copy.deepcopy(
            material.execution_material["protocol_shape"]["workflow_plan"]
        ),
        "protocol": protocol,
        "sessions": runtime.sessions(),
    }
    if failed_step == "settle" and protocol["settle"].get("reason_code") == "settle_timeout":
        verdict, claim_kind, failure_class = "not_evaluable", None, "settle_timeout"
        predicate_result = {
            "family": predicate["family"],
            "status": "not_evaluable",
            "observed": {},
            "reason_code": "settle_timeout",
        }
    elif failed_step is not None:
        verdict, claim_kind, failure_class = (
            "infrastructure_failed", None, _failure_class(failed_step)
        )
    elif applicability_failed:
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"
    elif capture_failure is not None:
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"
    elif predicate_result["status"] == "satisfied":
        verdict, claim_kind, failure_class = "validated", "workflow_confirmed", None
    elif predicate_result["status"] == "violated":
        verdict, claim_kind, failure_class = "refuted", None, None
    else:
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"
    result = {
        "schema_version": "uisemtest-current-protocol-result-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V4",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": predicate_result,
        "failure_class": failure_class,
        "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json",
        "certificate_ref": f"M12/{material.candidate_id}/certificate.json",
        "v1_legacy_outcome": None,
    }
    certificate = {
        "schema_version": "uisemtest-current-v4-certificate-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V4",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": copy.deepcopy(predicate_result),
        "failure_class": failure_class,
        "workflow_plan": copy.deepcopy(evidence["workflow_plan"]),
    }
    payload = canonical_json_bytes(evidence)
    collected = LifecycleCollectedEvidence(
        evidence=evidence,
        execution_evidence_bytes=payload,
        artifact_hashes={},
        artifact_bytes=artifacts,
        partial_records=(),
        artifact_write_sequence=(),
        runtime_counts=runtime.counts(),
        volatile_sensitive_values=tuple(
            getattr(runtime, "sensitive_values_in_memory", lambda: ())()
        ),
    )
    return collected, certificate, result


def _evaluate_in_memory_predicate(
    runtime: Any,
    context: Any,
    predicate: Mapping[str, Any],
) -> tuple[bool, dict[str, bool]] | None:
    evaluator = getattr(runtime, "evaluate_in_memory_predicate", None)
    if not callable(evaluator):
        return None
    result = evaluator(context, predicate)
    if (
        not isinstance(result, tuple)
        or len(result) != 2
        or not isinstance(result[0], bool)
        or result[1] != {"values_equal": result[0]}
    ):
        return None
    return result


def _failed(record: Mapping[str, Any]) -> bool:
    return record.get("state") != "executed" or record.get("status") != "pass"


def _failure_class(step: str) -> str:
    if step in {"reset", "setup"}:
        return "setup_failure"
    if step in {"before", "after"}:
        return "observer_failure"
    return "request_transport_failure"


def _published_observation(
    predicate: Mapping[str, Any], observed: Mapping[str, Any]
) -> dict[str, Any]:
    if predicate["family"] == "P14":
        return {
            "before_matches": int(observed["before"]),
            "after_matches": int(observed["after"]),
        }
    if predicate["family"] == "P02":
        return {"values_equal": observed.get("actual") == observed.get("expected")}
    if predicate["family"] == "P04" and is_workflow_effect_predicate(predicate):
        return dict(observed)
    if predicate["family"] == "P07":
        return dict(observed)
    if predicate["family"] == "P20":
        return {"values_equal": bool(observed["equal"]), **({"checks": observed["checks"]} if "checks" in observed else {})}
    if predicate["family"] == "P04":
        return {
            "before": observed.get("before"),
            "after": observed.get("after"),
            "expected_before": observed.get("expected_before"),
            "expected_after": observed.get("expected_after"),
        }
    if predicate["family"] == "P06":
        return dict(observed)
    if predicate["family"] == "P12":
        return {
            "before_count": int(observed["before_count"]),
            "after_count": int(observed["after_count"]),
            "actual_delta": int(observed["actual_delta"]),
        }
    if predicate.get("member") is None:
        return {"target_present": bool(observed["actual"])}
    return {"match_count": 1 if observed["actual"] else 0}


def _predicate_failure_reason(error: BaseException) -> str:
    if isinstance(error, PredicateNotEvaluable):
        return error.reason_code
    if isinstance(error, SensitiveMaterialUnavailable):
        return "sensitive_material_unavailable"
    if "identity_ambiguous" in str(error):
        return "identity_ambiguous"
    if "identity_missing" in str(error):
        return "identity_missing"
    if isinstance(error, KeyError):
        return "role_missing" if error.args and error.args[0] in {
            "before", "after", "producer_request", "producer_response"
        } else "path_missing"
    if isinstance(error, TypeError):
        return "type_mismatch"
    return "identity_missing"
