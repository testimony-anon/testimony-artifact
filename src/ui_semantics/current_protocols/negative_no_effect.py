"""Minimal negative-no-effect (V6) execution over current runtime primitives."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..current_route_s import canonical_json_bytes
from ..dsl import evaluate_predicate_result
from ..route_s_capture_redaction import (
    predicate_value_refs,
    reject_redacted_predicate_dependencies,
)


@dataclass(frozen=True)
class NegativeNoEffectCollectedEvidence:
    evidence: dict[str, Any]
    execution_evidence_bytes: bytes
    artifact_hashes: dict[str, str]
    artifact_bytes: dict[str, bytes]
    partial_records: tuple[dict[str, Any], ...]
    artifact_write_sequence: tuple[str, ...]
    runtime_counts: dict[str, int]
    volatile_sensitive_values: tuple[str, ...] = ()


def evaluate_negative_outcome(
    predicate: Mapping[str, Any],
    rejection_detector: Mapping[str, Any],
    *,
    negative_kind: str,
    before: Mapping[str, Any] | None = None,
    producer: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    failed_step: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Reduce one fresh negative execution, after caller-owned identity checks.

    M12 and M14 supply their own executed records, never an earlier verdict.
    Setup/session/before/request validity precedes business checks; a trusted
    rejection counterexample survives a later settling or observation failure.
    """
    if negative_kind not in {"rejection", "rejection_preservation"}:
        raise ValueError("negative_kind_invalid")
    preserve = negative_kind == "rejection_preservation"
    if predicate.get("family") != ("P20" if preserve else "P02"):
        raise ValueError("negative_primary_family_invalid")
    detector_kind = rejection_detector.get("kind")
    if detector_kind == "predicate":
        detector_predicate = rejection_detector["predicate"]
        if detector_predicate.get("family") != "P02" or (not preserve and detector_predicate != predicate):
            raise ValueError("negative_rejection_detector_predicate_mismatch")
        for ref in predicate_value_refs(detector_predicate):
            if ref.get("role") not in {"producer_status", "producer_response"} or ref.get("location") is not None:
                raise ValueError("negative_rejection_detector_source_invalid")
            if ref["role"] == "producer_status" and (ref.get("path") != "$" or ref.get("value_type") != "integer"):
                raise ValueError("negative_rejection_detector_status_ref_invalid")
    elif detector_kind != "http_status_class" or not preserve or rejection_detector.get("expected_class") != "client_error":
        raise ValueError("negative_rejection_detector_invalid")
    if preserve and any(ref.get("role") not in {"before", "after"} for ref in predicate_value_refs(predicate)):
        raise ValueError("negative_preservation_source_invalid")
    diagnostics: list[dict[str, Any]] = []
    producer = producer or {}
    before = before or {}
    after = after or {}
    if failed_step in {None, "settle", "after"} and preserve and not _healthy_observation(before):
        failed_step, failure_reason = "before", "negative_before_unavailable"
    if failed_step in {None, "settle", "after"} and _failed(producer):
        failed_step, failure_reason = "producer", "negative_response_unavailable"
    status = producer.get("transport_status")
    prerequisites_closed = failed_step not in {"reset", "setup", "session_boundary", "before", "producer"}
    if prerequisites_closed and (type(status) is not int or not (200 <= status < 300 or 400 <= status < 500)):
        failed_step = "producer"
        failure_reason = "negative_response_status_missing" if type(status) is not int else f"negative_response_status_{status}"
        prerequisites_closed = False
    if failed_step is not None:
        diagnostics.append({"step": failed_step, "reason_code": failure_reason or "execution_failed"})

    def unknown(check_id: str, reason: str) -> dict[str, Any]:
        return {"check_id": check_id, "satisfied": None, "reason_code": reason}

    def evaluate(check_id: str, atom: Mapping[str, Any], observations: Mapping[str, Any], sources: Mapping[str, Any]) -> dict[str, Any]:
        evaluated = evaluate_predicate_result(
            atom, observations,
            dependency_checker=lambda dependency, **_: reject_redacted_predicate_dependencies(dependency, sources),
        )
        check = {"check_id": check_id, "satisfied": evaluated["satisfied"], "reason_code": evaluated["reason_code"]}
        # Keep independently evaluated projection fields, but never their values.
        if isinstance(evaluated["observed"].get("checks"), list):
            check["checks"] = [
                {key: row[key] for key in ("check_id", "satisfied", "reason_code") if key in row}
                for row in evaluated["observed"]["checks"]
            ]
        return check

    rejection = unknown("rejection", "execution_prerequisite_unavailable")
    if prerequisites_closed:
        if detector_kind == "http_status_class":
            rejection = {"check_id": "rejection", "satisfied": 400 <= status < 500, "reason_code": None}
        else:
            observations = {"producer_status": {"body": status}}
            if "response" in producer:
                observations["producer_response"] = {"body": producer["response"]}
            rejection = evaluate("rejection", detector_predicate, observations,
                                 {"producer_response": ((producer, "response"),)})

    projection = None
    checks = [rejection]
    if preserve:
        projection = unknown("preservation", "execution_prerequisite_unavailable")
        if prerequisites_closed and failed_step is None and _healthy_observation(after):
            projection = evaluate("preservation", predicate, {
                "before": before["response"], "after": after["response"],
            }, {"before": ((before, "response"),), "after": ((after, "response"),)})
        elif prerequisites_closed:
            projection = unknown("preservation", failure_reason or "negative_after_unavailable")
            if failed_step is None:
                failed_step, failure_reason = "after", "negative_after_unavailable"
                diagnostics.append({"step": failed_step, "reason_code": failure_reason})
        checks.append(projection)
    for check in checks:
        if check["reason_code"] is not None:
            diagnostics.append({"check_id": check["check_id"], "reason_code": check["reason_code"]})
    satisfied = False if any(check["satisfied"] is False for check in checks) else (
        True if all(check["satisfied"] is True for check in checks) else None
    )
    predicate_result = {
        "family": predicate["family"],
        "status": "satisfied" if satisfied is True else "violated" if satisfied is False else "not_evaluable",
        "observed": {"checks": checks, "diagnostics": diagnostics},
        "reason_code": None if satisfied is not None else next((check["reason_code"] for check in checks if check["reason_code"]), failure_reason),
    }
    if satisfied is False:
        verdict, failure_class = "refuted", None
    elif failed_step == "settle" and failure_reason == "settle_timeout":
        verdict, failure_class = "not_evaluable", "settle_timeout"
    elif failed_step is not None:
        verdict, failure_class = "infrastructure_failed", _failure_class(failed_step)
        predicate_result = None
    elif satisfied is None:
        verdict, failure_class = "not_evaluable", "binding"
    else:
        verdict, failure_class = "validated", None
    return {
        "protocol_verdict": verdict, "failure_class": failure_class,
        "predicate_result": predicate_result, "rejection_result": rejection,
        "projection_result": projection, "diagnostics": diagnostics,
    }


def execute_negative_no_effect(
    material: Any,
    runtime: Any,
    *,
    artifact_writer: Callable[[str, bytes], None],
    output_level: str,
) -> tuple[NegativeNoEffectCollectedEvidence, dict[str, Any], dict[str, Any]]:
    """Execute the frozen rejection-only or rejection-and-preservation plan."""

    del artifact_writer, output_level
    artifacts = dict(material.artifact_bytes)

    def add(rows: Mapping[str, bytes]) -> None:
        artifacts.update(rows)

    shape = material.execution_material["protocol_shape"]
    negative_kind = shape["negative_kind"]
    if negative_kind not in {"rejection", "rejection_preservation"}:
        raise ValueError("negative_kind_invalid")
    preserve = negative_kind == "rejection_preservation"
    context, reset, rows = runtime.begin_arm(material, "negative_no_effect")
    add(rows)
    protocol: dict[str, Any] = {"reset": copy.deepcopy(reset)}
    calls = [
        ("setup", lambda: runtime.execute_setup(context, "negative_setup")),
        ("session_boundary", lambda: runtime.negative_session_boundary(context)),
    ]
    if preserve:
        calls.append(("before", lambda: runtime.observe(context, "negative_before")))
    calls.append(("producer", lambda: runtime.execute_negative_producer(context)))
    failed_step = "reset" if _failed(reset) else None
    if failed_step is None:
        for step, call in calls:
            record, rows = call()
            add(rows)
            protocol[step] = copy.deepcopy(record)
            if _failed(record) or step == "before" and not _healthy_observation(record):
                failed_step = step
                break

    failure_reason = protocol.get(failed_step, {}).get("reason_code") if failed_step else None
    if failed_step is None:
        status = protocol["producer"].get("transport_status")
        if type(status) is not int:
            failed_step = "producer"
            failure_reason = "negative_response_status_missing"
        elif not (200 <= status < 300 or 400 <= status < 500):
            failed_step = "producer"
            failure_reason = f"negative_response_status_{status}"
    if failed_step is None and preserve:
        settle, after, rows = runtime.observe_until_stable(
            context, "negative_settle", "negative_after"
        )
        add(rows)
        protocol["settle"] = copy.deepcopy(settle)
        protocol["after"] = copy.deepcopy(after)
        if _failed(settle):
            failed_step = "settle"
        elif _failed(after):
            failed_step = "after"
        if failed_step:
            failure_reason = protocol[failed_step].get("reason_code")
    for step in (
        "setup", "session_boundary", "before", "producer",
        "rejection_gate", "settle", "after",
    ):
        if preserve or step not in {"before", "settle", "after"}:
            protocol.setdefault(step, {"state": "not_executed", "reason_code": "prior_failure"})

    predicate = copy.deepcopy(material.candidate["primary_predicate"])
    outcome = evaluate_negative_outcome(
        predicate, shape["rejection_detector"], negative_kind=negative_kind,
        before=protocol.get("before"), producer=protocol.get("producer"),
        after=protocol.get("after"), failed_step=failed_step, failure_reason=failure_reason,
    )
    predicate_result = outcome["predicate_result"]
    rejection_satisfied = outcome["rejection_result"]["satisfied"]
    protocol["rejection_gate"] = {
        "state": "executed" if rejection_satisfied is not None else "not_executed",
        "status": "pass" if rejection_satisfied is not None else "failed",
        "detector": copy.deepcopy(shape["rejection_detector"]),
        "response_status": protocol["producer"].get("transport_status"),
        "rejected": rejection_satisfied,
    }
    protocol["diagnostics"] = outcome["diagnostics"]

    evidence = {
        "schema_version": "uisemtest-current-v6-execution-evidence-v1",
        "candidate": copy.deepcopy(material.candidate),
        "negative_kind": negative_kind,
        "negative_plan": copy.deepcopy(
            material.execution_material["protocol_shape"]["negative_plan"]
        ),
        "rejection_detector": copy.deepcopy(
            material.execution_material["protocol_shape"]["rejection_detector"]
        ),
        "projection": copy.deepcopy(shape.get("projection")),
        "protocol": protocol,
        "sessions": runtime.sessions(),
    }
    verdict, failure_class = outcome["protocol_verdict"], outcome["failure_class"]
    claim_kind = "negative_behavior_confirmed" if verdict == "validated" else None
    result = {
        "schema_version": "uisemtest-current-protocol-result-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V6",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": predicate_result,
        "failure_class": failure_class,
        "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json",
        "certificate_ref": f"M12/{material.candidate_id}/certificate.json",
        "v1_legacy_outcome": None,
    }
    certificate = {
        "schema_version": "uisemtest-current-v6-certificate-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V6",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "failure_class": failure_class,
        "negative_kind": negative_kind,
        "gates": {
            "client_error_rejection": rejection_satisfied,
            "business_projection_equal": outcome["projection_result"]["satisfied"] if preserve else None,
        },
        "predicate_result": copy.deepcopy(predicate_result),
        "negative_plan": copy.deepcopy(evidence["negative_plan"]),
    }
    payload = canonical_json_bytes(evidence)
    collected = NegativeNoEffectCollectedEvidence(
        evidence=evidence,
        execution_evidence_bytes=payload,
        artifact_hashes={},
        artifact_bytes=artifacts,
        partial_records=(),
        artifact_write_sequence=(),
        runtime_counts=runtime.counts(),
    )
    return collected, certificate, result


def _failed(record: Mapping[str, Any]) -> bool:
    return record.get("state") != "executed" or record.get("status") != "pass"


def _healthy_observation(record: Mapping[str, Any]) -> bool:
    response = record.get("response")
    return (
        not _failed(record) and isinstance(response, Mapping) and "body" in response
        and type(response.get("status")) is int and 200 <= response["status"] < 300
    )


def _failure_class(step: str) -> str:
    if step in {"reset", "setup", "session_boundary"}:
        return "setup_failure"
    if step in {"before", "after"}:
        return "observer_failure"
    return "request_transport_failure"
