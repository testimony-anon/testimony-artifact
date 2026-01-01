"""Actor-matrix protocol execution over the shared current runtime primitives."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..current_route_s import canonical_json_bytes
from ..dsl import evaluate_predicate, evaluate_predicate_result, PredicateNotEvaluable, get_path, request_numeric_observation
from ..route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    reject_redacted_predicate_dependencies,
)


@dataclass(frozen=True)
class ActorMatrixCollectedEvidence:
    evidence: dict[str, Any]
    execution_evidence_bytes: bytes
    artifact_hashes: dict[str, str]
    artifact_bytes: dict[str, bytes]
    partial_records: tuple[dict[str, Any], ...]
    artifact_write_sequence: tuple[str, ...]
    runtime_counts: dict[str, int]
    volatile_sensitive_values: tuple[str, ...] = ()


def execute_actor_matrix(
    material: Any,
    runtime: Any,
    *,
    artifact_writer: Callable[[str, bytes], None],
    output_level: str,
) -> tuple[ActorMatrixCollectedEvidence, dict[str, Any], dict[str, Any]]:
    """Run one reset with isolated producer/target sessions and target observations."""

    del artifact_writer, output_level
    artifacts = dict(material.artifact_bytes)

    def add(rows: Mapping[str, bytes]) -> None:
        artifacts.update(rows)

    context, reset, rows = runtime.begin_arm(material, "actor_matrix")
    add(rows)
    shape = material.execution_material["protocol_shape"]
    roles = shape["roles"]
    before_roles = [role for role in roles if role.startswith("actor_before:")]
    after_roles = [role for role in roles if role.startswith("actor_after:")]
    if len(before_roles) != 1 or len(after_roles) != 1:
        raise ValueError("actor_matrix_target_role_set_not_unique")
    before_role = before_roles[0]
    after_role = after_roles[0]
    producer_actor = str(roles["producer"]["actor"])
    before_actor = str(roles[before_role]["actor"])
    target_actor = str(roles[after_role]["actor"])
    if before_actor != target_actor:
        raise ValueError("actor_matrix_target_actor_binding_invalid")
    sessions = runtime.sessions()
    topology = material.execution_material["protocol_shape"].get("identity_topology")
    isolated = (producer_actor == target_actor or _sessions_are_isolated(
        sessions, producer_actor=producer_actor, target_actor=target_actor
    ))
    protocol: dict[str, Any] = {"reset": copy.deepcopy(reset)}
    failed_step = "reset" if _failed(reset) else None
    if failed_step is None and not isolated:
        failed_step = "session_isolation"
    sequence = (
        ("setup", lambda: runtime.execute_setup(context, "actor_setup")),
        ("before", lambda: runtime.observe(context, "actor_before")),
        ("producer", lambda: runtime.execute_producer(context)),
    )
    if failed_step is None:
        for step, call in sequence:
            record, rows = call()
            add(rows)
            protocol[step] = copy.deepcopy(record)
            if _failed(record):
                failed_step = step
                break
            if step == "setup":
                verifier = getattr(runtime, "verify_identity_topology", None)
                verified = topology is not None and callable(verifier) and verifier(context, topology)
                protocol["identity_topology"] = {"verified": bool(verified), "relation": copy.deepcopy(topology)}
                if not verified:
                    failed_step = "session_isolation"
                    break
    if failed_step is None:
        settle, after, rows = runtime.observe_until_stable(
            context, "actor_settle", "actor_after"
        )
        add(rows)
        protocol["settle"] = copy.deepcopy(settle)
        protocol["after"] = copy.deepcopy(after)
        if _failed(settle):
            failed_step = "settle"
        elif _failed(after):
            failed_step = "after"
    for step in ("setup", "before", "producer", "settle", "after"):
        protocol.setdefault(step, {"state": "not_executed", "reason_code": "prior_failure"})

    predicate = copy.deepcopy(material.candidate["primary_predicate"])
    predicate_result = None
    if failed_step is None:
        observations = {
            before_role: protocol["before"]["response"],
            after_role: protocol["after"]["response"],
            # V7's execution shape names the target actor explicitly, while the
            # shared predicate language intentionally uses the protocol-neutral
            # before/after roles.  There is exactly one target actor in a valid
            # actor-matrix shape, so these are aliases of the same observations,
            # not additional or inferred evidence.
            "before": protocol["before"]["response"],
            "after": protocol["after"]["response"],
            # Predicate roles stay in the arm-local semantic alias namespace.
            # The physical transport request remains available in execution
            # evidence for binding attestation, but must not be compared with
            # observer bodies whose proven fresh aliases were normalized.
            "producer_request": request_numeric_observation(protocol["producer"], protocol["producer"].get("request")),
            "producer_response": {"body": protocol["producer"]["response"]},
            "after_status": {"body": protocol["after"]["response"]["status"]},
        }
        try:
            dependency_roles = {
                    before_role: ((protocol["before"], "response"),),
                    after_role: ((protocol["after"], "response"),),
                    "before": ((protocol["before"], "response"),),
                    "after": ((protocol["after"], "response"),),
                    "producer_request": tuple((protocol["producer"], channel) for channel in ("request", "request_query", "request_path", "request_headers")),
                    "producer_response": ((protocol["producer"], "response"),),
                    "after_status": (),
            }
            evaluated = evaluate_predicate_result(predicate, observations, dependency_checker=lambda atom, **_kwargs: reject_redacted_predicate_dependencies(atom, dependency_roles))
            satisfied, observed = evaluated["satisfied"], evaluated["observed"]
            if satisfied is None:
                raise PredicateNotEvaluable(evaluated["reason_code"], observed)
        except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
            satisfied, observed = None, error.observed if isinstance(error, PredicateNotEvaluable) else {}
            reason_code = _predicate_failure_reason(error)
        else:
            reason_code = None
            observed = _published_observation(
                predicate, observations, observed, satisfied=satisfied
            )
        predicate_result = {
            "family": predicate["family"],
            "status": (
                "satisfied" if satisfied is True
                else "violated" if satisfied is False
                else "not_evaluable"
            ),
            "observed": observed,
            "reason_code": reason_code,
        }

    if failed_step == "settle" and protocol["settle"].get("reason_code") == "settle_timeout":
        verdict, claim_kind, failure_class = "not_evaluable", None, "settle_timeout"
        predicate_result = {
            "family": predicate["family"],
            "status": "not_evaluable",
            "observed": {},
            "reason_code": "settle_timeout",
        }
    elif failed_step == "session_isolation":
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"
    elif failed_step is not None:
        verdict, claim_kind, failure_class = (
            "infrastructure_failed", None, _failure_class(failed_step)
        )
    elif predicate_result["status"] == "satisfied":
        verdict, claim_kind, failure_class = (
            "validated", "actor_relation_confirmed", None
        )
    elif predicate_result["status"] == "violated":
        verdict, claim_kind, failure_class = "refuted", None, None
    else:
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"

    evidence = {
        "schema_version": "uisemtest-current-actor-matrix-execution-evidence-v1",
        "candidate": copy.deepcopy(material.candidate),
        "actor_plan": copy.deepcopy(shape["actor_plan"]),
        "protocol": protocol,
        "sessions": copy.deepcopy(sessions),
        "qualification_gates": {"session_isolation": isolated},
    }
    result = {
        "schema_version": "uisemtest-current-protocol-result-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V7",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": predicate_result,
        "failure_class": failure_class,
        "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json",
        "certificate_ref": f"M12/{material.candidate_id}/certificate.json",
        "v1_legacy_outcome": None,
    }
    certificate = {
        "schema_version": "uisemtest-current-actor-matrix-certificate-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V7",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": copy.deepcopy(predicate_result),
        "failure_class": failure_class,
        "actor_plan": copy.deepcopy(evidence["actor_plan"]),
        "qualification_gates": copy.deepcopy(evidence["qualification_gates"]),
    }
    payload = canonical_json_bytes(evidence)
    return (
        ActorMatrixCollectedEvidence(
            evidence=evidence,
            execution_evidence_bytes=payload,
            artifact_hashes={},
            artifact_bytes=artifacts,
            partial_records=(),
            artifact_write_sequence=(),
            runtime_counts=runtime.counts(),
        ),
        certificate,
        result,
    )


def _sessions_are_isolated(
    sessions: list[Mapping[str, Any]], *, producer_actor: str, target_actor: str
) -> bool:
    if producer_actor == target_actor:
        return False
    rows = {
        str(row.get("actor_id")): row
        for row in sessions
        if row.get("arm") == "actor_matrix"
        and row.get("actor_id") in {producer_actor, target_actor}
        and row.get("secret_values_present") is False
    }
    if set(rows) != {producer_actor, target_actor}:
        return False
    for field in (
        "materialization_id", "ownership_domain_sha256", "jar_ownership_sha256"
    ):
        values = [rows[actor].get(field) for actor in (producer_actor, target_actor)]
        if any(not isinstance(value, str) or not value for value in values):
            return False
        if len(set(values)) != 2:
            return False
    return True


def _published_observation(
    predicate: Mapping[str, Any],
    observations: Mapping[str, Any],
    observed: Mapping[str, Any],
    *,
    satisfied: bool,
) -> dict[str, Any]:
    family = predicate["family"]
    if family == "P01":
        if predicate.get("member") is None:
            return {"target_present": bool(observed["actual"])}
        return {"match_count": 1 if observed["actual"] else 0}
    if family == "P02":
        return {"values_equal": satisfied}
    if family == "P20":
        return {"values_equal": satisfied, **({"checks": observed["checks"]} if "checks" in observed else {})}
    if family == "P12":
        before = get_path(
            observations[predicate["before"]["role"]]["body"],
            predicate["before"]["path"],
        )
        after = get_path(
            observations[predicate["after"]["role"]]["body"],
            predicate["after"]["path"],
        )
        return {
            "before_count": len(before),
            "after_count": len(after),
            "actual_delta": len(after) - len(before),
        }
    if family == "P13":
        return {"match_count": int(observed["matches"])}
    return {
        "before_matches": int(observed["before"]),
        "after_matches": int(observed["after"]),
    }


def _failed(record: Mapping[str, Any]) -> bool:
    return record.get("state") != "executed" or record.get("status") != "pass"


def _failure_class(step: str) -> str:
    if step in {"reset", "setup"}:
        return "setup_failure"
    if step in {"before", "after"}:
        return "observer_failure"
    return "request_transport_failure"


def _predicate_failure_reason(error: BaseException) -> str:
    if isinstance(error, PredicateNotEvaluable):
        return error.reason_code
    if isinstance(error, SensitiveMaterialUnavailable):
        return "sensitive_material_unavailable"
    if isinstance(error, KeyError):
        return "path_missing"
    if isinstance(error, TypeError):
        return "type_mismatch"
    if "identity_ambiguous" in str(error):
        return "identity_ambiguous"
    return "identity_missing"
