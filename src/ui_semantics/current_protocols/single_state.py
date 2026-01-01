"""One predeclared fresh response for a single-state constraint (V2)."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

from ..current_route_s import canonical_json_bytes
from ..current_settle import route_observer_is_pure
from ..dsl import evaluate_predicate_result
from ..route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    reject_redacted_predicate_dependencies,
)
from .metamorphic_query import _failed, _is_read_only_binding, _predicate_failure_reason, query_request_observation


@dataclass(frozen=True)
class SingleStateCollectedEvidence:
    evidence: dict[str, Any]
    execution_evidence_bytes: bytes
    artifact_hashes: dict[str, str]
    artifact_bytes: dict[str, bytes]
    partial_records: tuple[dict[str, Any], ...]
    artifact_write_sequence: tuple[str, ...]
    runtime_counts: dict[str, int]
    volatile_sensitive_values: tuple[str, ...] = ()


def execute_single_state(
    material: Any,
    runtime: Any,
    *,
    artifact_writer: Callable[[str, bytes], None],
    output_level: str,
) -> tuple[SingleStateCollectedEvidence, dict[str, Any], dict[str, Any]]:
    del artifact_writer, output_level
    shape = material.execution_material["protocol_shape"]
    plan = copy.deepcopy(shape["observation_plan"])
    if len(plan) != 1 or plan[0]["role"] != "observation":
        raise ValueError("single_state_requires_one_observation")
    binding = material.execution_binding["payload"]["observations"]["observation"]
    read_only = _is_read_only_binding(
        binding,
        mechanically_read=plan[0]["request_ref"]
        in shape.get("read_execution_evidence", {}),
    )
    if not read_only or material.candidate.get("producer") is not None:
        raise ValueError("single_state_requires_read_without_producer")
    artifacts = dict(material.artifact_bytes)
    context, reset, rows = runtime.begin_arm(material, "single_state")
    artifacts.update(rows)
    protocol = {"reset": copy.deepcopy(reset), "observations": []}
    failed_step = "reset" if _failed(reset) else None
    if failed_step is None:
        setup, rows = runtime.execute_setup(context, "observation_setup")
        artifacts.update(rows)
        protocol["setup"] = copy.deepcopy(setup)
        if _failed(setup):
            failed_step = "setup"
    if failed_step is None:
        record, rows = runtime.observe(context, "observation")
        artifacts.update(rows)
        protocol["observations"].append(copy.deepcopy(record))
        if (
            _failed(record)
            or not isinstance(record.get("response"), Mapping)
            or "body" not in record["response"]
        ):
            failed_step = "observation"
    protocol.setdefault(
        "setup", {"state": "not_executed", "reason_code": "prior_failure"}
    )
    sessions = copy.deepcopy(runtime.sessions())
    session_rows = [
        row
        for row in sessions
        if row.get("arm") == "single_state"
        and row.get("actor_id") == binding["actor_id"]
    ]
    session_closed = (
        len(session_rows) == 1
        and session_rows[0].get("secret_values_present") is False
        and session_rows[0].get("reset_epoch") == reset.get("reset_epoch")
    )
    observation = protocol["observations"][0] if protocol["observations"] else {}
    identity_closed = (
        observation.get("actor_id") == binding["actor_id"]
        and observation.get("request_ref") == plan[0]["request_ref"]
    )
    observer_pure = route_observer_is_pure(observation)
    if failed_step is None and not observer_pure:
        failed_step = "observation"
        protocol["observation_validity"] = {
            "state": "executed", "status": "failed",
            "reason_code": "observer_mutating_or_uncertain",
        }
    predicate = copy.deepcopy(material.candidate["primary_predicate"])
    predicate_result = None
    if failed_step is None and session_closed and identity_closed:
        record = protocol["observations"][0]
        try:
            evaluated = evaluate_predicate_result(
                predicate,
                {
                    "observation": record["response"],
                    "observation_request": query_request_observation(record),
                },
                dependency_checker=partial(
                    reject_redacted_predicate_dependencies,
                    sources={
                        "observation": ((record, "response"),),
                        "observation_request": tuple(
                            (record, channel) for channel in ("request_query", "request", "request_headers", "request_path")
                        ),
                    },
                ),
            )
            satisfied, observed, reason = evaluated["satisfied"], evaluated["observed"], evaluated["reason_code"]
        except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
            satisfied, observed, reason = None, {}, _predicate_failure_reason(error)
        predicate_result = {
            "family": predicate["family"],
            "status": "satisfied"
            if satisfied is True
            else "violated"
            if satisfied is False
            else "not_evaluable",
            "observed": observed,
            "reason_code": reason,
        }
    if failed_step is not None:
        verdict, claim, failure = (
            "infrastructure_failed",
            None,
            "setup_failure"
            if failed_step in {"reset", "setup"}
            else "observer_failure",
        )
    elif not session_closed or not identity_closed or predicate_result["status"] == "not_evaluable":
        verdict, claim, failure = "not_evaluable", None, "binding"
    elif predicate_result["status"] == "violated":
        verdict, claim, failure = "refuted", None, None
    else:
        verdict, claim, failure = "validated", "single_state_confirmed", None
    gates = {
        "observation_plan_complete": failed_step is None,
        "same_actor_session": session_closed,
        "observation_identity_closed": identity_closed,
        "observer_pure": observer_pure,
        "read_only": read_only,
    }
    common = {
        "candidate_id": material.candidate_id,
        "protocol_kind": "V2",
        "protocol_verdict": verdict,
        "claim_kind": claim,
        "predicate_result": predicate_result,
        "failure_class": failure,
    }
    certificate = {
        "schema_version": "uisemtest-current-single-state-certificate-v1",
        **copy.deepcopy(common),
        "observation_plan": plan,
        "sampling": copy.deepcopy(shape["sampling"]),
        "qualification_gates": gates,
    }
    evidence = {
        "schema_version": "uisemtest-current-single-state-execution-evidence-v1",
        "candidate": copy.deepcopy(material.candidate),
        "observation_plan": plan,
        "sampling": copy.deepcopy(shape["sampling"]),
        "protocol": protocol,
        "sessions": sessions,
        "qualification_gates": gates,
    }
    result = {
        "schema_version": "uisemtest-current-protocol-result-v1",
        **common,
        "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json",
        "certificate_ref": f"M12/{material.candidate_id}/certificate.json",
        "v1_legacy_outcome": None,
    }
    return (
        SingleStateCollectedEvidence(
            evidence,
            canonical_json_bytes(evidence),
            {},
            artifacts,
            (),
            (),
            runtime.counts(),
        ),
        certificate,
        result,
    )
