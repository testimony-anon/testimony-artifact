"""Protocol-neutral current M12/M13/M14 facade."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from common.contracts import validate_artifact

from ..current_calibration import run_current_calibration
from ..current_candidate_failure import CandidateLocalFailure
from ..current_relation import (
    CurrentRouteSArtifactRecord,
    persist_current_route_s_result,
)
from ..current_route_s import (
    CurrentRouteSCollector,
    RouteSCollectedEvidence,
    construct_v1_route_s_certificate,
    canonical_json_bytes,
)
from ..relation_phase_b import build_certified_relation_tests
from .v4 import LifecycleCollectedEvidence, execute_lifecycle_workflow
from .actor_matrix import ActorMatrixCollectedEvidence, execute_actor_matrix
from .metamorphic_query import MetamorphicQueryCollectedEvidence, execute_metamorphic_query
from .single_state import SingleStateCollectedEvidence, execute_single_state
from .negative_no_effect import (
    NegativeNoEffectCollectedEvidence,
    execute_negative_no_effect,
)


REGISTERED_PROTOCOLS = ("V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9")
_V8_CONTRACT_PREDICATES = {contract: {("P01", "exists"), ("P01", "absent"), *(("P02", op) for op in ("eq", "neq", "numeric_eq", "numeric_neq", "lt", "le", "gt", "ge")), ("P13", "contains"), ("P13", "not_contains")} for contract in ("C01", "C02", "C03", "C11", "C12", "self_exclusion")}
_V9_CONTRACT_PREDICATES = {"C14": {*(("P08", op) for op in ("add", "subtract", "multiply", "divide", "linear_delta")), *(("P19", op) for op in ("count", "sum", "min", "max"))}}
_V2_CONTRACT_PREDICATES = {
    "single_state_constraint": {
        ("P01", "present"), ("P01", "absent"), ("P11", "le"), ("P21", None),
        *(("P02", operator) for operator in ("eq", "neq", "numeric_eq", "numeric_neq", "lt", "le", "gt", "ge")),
        ("P03", "range"), ("P03", "in"), ("forall", None),
        *(("P09", operator) for operator in ("contains", "prefix", "suffix")),
        ("P10", None), ("P15", None), ("P13", "contains"), ("P13", "not_contains"),
        *(("P08", op) for op in ("add", "subtract", "multiply", "divide")),
        *(("P19", op) for op in ("count", "sum", "min", "max")),
        *(("P11", operator) for operator in ("eq", "neq", "lt", "gt", "ge")),
    },
}
_V2_CONTRACT_PREDICATES["C14"] = {*( ("P08", op) for op in ("add", "subtract", "multiply", "divide")), *( ("P19", op) for op in ("count", "sum", "min", "max"))}
_V1_PREDICATES = frozenset({"P01", "P02", "P04", "P06", "P12", "P14"})
_V1_CONTRACT_PREDICATES = {
    "C01": {("P01", "exists"), ("P12", None), ("P14", "added")},
    "C02": {
        ("P02", "eq"),
        ("P04", "from_to"),
        ("P04", "toggle"),
        ("P06", None),
    },
    "C03": {("P01", "absent"), ("P12", None), ("P14", "removed")},
    "C11": {("P12", None)},
}
_V4_CONTRACT_PREDICATES = {
    "C01": {("P01", "exists"), ("P12", None), ("P14", "added")},
    "C02": {
        ("P02", "eq"),
        ("P04", "from_to"),
        ("P04", "toggle"),
        ("P06", None),
        *(("P07", op) for op in ("gt", "lt", "ge", "le")),
    },
    "C04": {("P20", "equal")},
    "C03": {("P01", "absent"), ("P12", None), ("P14", "removed")},
}
_V7_CONTRACT_PREDICATES = {
    "C11": {
        ("P01", "absent"),
        ("P01", "exists"),
        ("P02", "eq"),
        ("P12", None),
        ("P13", "contains"),
        ("P13", "not_contains"),
        ("P14", "added"),
        ("P14", "removed"),
    },
    "C12": {("P01", "absent"), ("P13", "not_contains")},
}
_V4_CONTRACT_PREDICATES.update({"inverse_restoration": {("P20", "equal")}, "read_preservation": {("P20", "equal")}})
_V4_CONTRACT_PREDICATES["C02"].update(("P02", op) for op in ("neq", "numeric_eq", "numeric_neq", "lt", "le", "gt", "ge"))
_V7_CONTRACT_PREDICATES.update({"self_exclusion": {("P01", "absent"), ("P13", "not_contains")}, "C04": {("P20", "equal")}})
_V7_CONTRACT_PREDICATES["C12"].update(("P02", op) for op in ("eq", "neq", "ge", "gt", "le", "lt"))
_V7_CONTRACT_PREDICATES["C11"].update(("P02", op) for op in ("neq", "numeric_eq", "numeric_neq", "lt", "le", "gt", "ge"))
_V5_CONTRACT_PREDICATES = {"C05": {(kind, None) for kind in ("repeat_equal", "repeat_rejected", "repeat_delta")}}
_V3_CONTRACT_PREDICATES = {
    "C07": {("P17", "equal")},
    "C09": {("P16", None)},
    "single_state_constraint": {("forall", None)},
    "C08": {("P17", "subset"), ("P17", "superset")},
    "C10": {("P15", None), ("P18", "pairwise_disjoint"), ("P18", "complete_union"), ("P18", "partition_difference")},
}
_V6_CONTRACT_PREDICATES = {
    contract: {("P20", "equal"), *(("P02", op) for op in ("eq", "neq", "numeric_eq", "numeric_neq", "lt", "le", "gt", "ge"))} for contract in ("C06", "C12")
}


def current_executable_relation_language() -> tuple[dict[str, Any], ...]:
    """Project the protocol-neutral C/P language implemented by current M12."""

    rows = {
        (contract, predicate, operator)
        for mapping in (
            _V1_CONTRACT_PREDICATES,
            _V2_CONTRACT_PREDICATES,
            _V3_CONTRACT_PREDICATES,
            _V4_CONTRACT_PREDICATES,
            _V5_CONTRACT_PREDICATES,
            _V6_CONTRACT_PREDICATES,
            _V7_CONTRACT_PREDICATES,
            _V9_CONTRACT_PREDICATES,
            _V8_CONTRACT_PREDICATES,
        )
        for contract, pairs in mapping.items()
        for predicate, operator in pairs
    }
    return tuple(
        {
            "contract_kind": contract,
            "predicate_family": predicate,
            "operator": operator,
        }
        for contract, predicate, operator in sorted(
            rows, key=lambda row: (row[0], row[1], row[2] or "")
        )
    )


def current_shape_supports_relation(
    shape_kind: str,
    contract_kind: str,
    predicate_family: str,
    operator: str | None,
    *,
    transform_kind: str | None = None,
    signed_delta: int | None = None,
) -> bool:
    """Answer whether one constructed shape has a current M12 implementation."""

    mapping = {
        "causal_two_arm": _V1_CONTRACT_PREDICATES,
        "single_state": _V2_CONTRACT_PREDICATES,
        "metamorphic_query": _V3_CONTRACT_PREDICATES,
        "lifecycle_workflow": _V4_CONTRACT_PREDICATES,
        "repeated_execution": _V5_CONTRACT_PREDICATES,
        "negative_no_effect": _V6_CONTRACT_PREDICATES,
        "actor_matrix": _V7_CONTRACT_PREDICATES,
        "multi_resource": _V9_CONTRACT_PREDICATES,
        "temporal": _V8_CONTRACT_PREDICATES,
    }.get(shape_kind)
    supported = bool(
        mapping
        and contract_kind in mapping
        and (predicate_family, operator) in mapping[contract_kind]
    )
    if supported and predicate_family == "P12" and contract_kind in {"C01", "C03"}:
        supported = (
            isinstance(signed_delta, int)
            and not isinstance(signed_delta, bool)
            and ((contract_kind == "C01" and signed_delta > 0)
                 or (contract_kind == "C03" and signed_delta < 0))
        )
    if not supported or shape_kind != "metamorphic_query":
        return supported
    if contract_kind == "C08":
        return (
            (operator == "subset" and transform_kind == "filter_refinement")
            or (operator == "superset" and transform_kind == "filter_expansion")
        )
    return (contract_kind == "C10" and transform_kind == "pagination_partition"
            or contract_kind == "C07" and transform_kind == "equivalent_input"
            or contract_kind == "C09" and transform_kind == "sort"
            or contract_kind == "single_state_constraint" and transform_kind == "finite_query_plan")


_INFRASTRUCTURE_OUTCOMES = {
    "infrastructure_failed": "request_transport_failure",
    "setup_failed": "setup_failure",
    "arm_isolation_failed": "setup_failure",
    "observer_mutating_or_uncertain": "observer_failure",
}
_REFUTED_OUTCOMES = {
    "control_unstable",
    "baseline_mismatch",
    "effect_absent",
}


@dataclass(frozen=True)
class CurrentProtocolExecution:
    protocol_kind: str
    collected: RouteSCollectedEvidence | SingleStateCollectedEvidence | LifecycleCollectedEvidence | ActorMatrixCollectedEvidence | MetamorphicQueryCollectedEvidence | NegativeNoEffectCollectedEvidence
    certificate: dict[str, Any]
    result: dict[str, Any]


def derive_current_protocol(material: Any) -> str:
    """Derive the registered protocol from frozen candidate/material shape."""

    predicate = material.candidate.get("primary_predicate")
    predicate_family = predicate.get("family") if isinstance(predicate, Mapping) else None
    operator = predicate.get("operator") if isinstance(predicate, Mapping) else None
    contract_kind = material.candidate.get("contract_kind")
    execution_material = getattr(material, "execution_material", {})
    shape = execution_material.get("protocol_shape") or {}
    shape_kind = shape.get("shape_kind", "causal_two_arm")
    if shape_kind == "temporal" and current_shape_supports_relation(shape_kind, contract_kind, predicate_family, operator) and set(material.resource_binding_plans) == {"temporal"}:
        return "V8"
    if shape_kind == "multi_resource" and current_shape_supports_relation(shape_kind, contract_kind, predicate_family, operator) and set(material.resource_binding_plans) == {"multi_resource"}:
        return "V9"
    if shape_kind == "repeated_execution" and contract_kind == "C05" and predicate_family in {"repeat_equal", "repeat_rejected", "repeat_delta"}:
        expected = {"repeat_once", "repeat_twice"} if predicate_family == "repeat_equal" else {"repeat_twice"}
        if set(material.resource_binding_plans) == expected and shape.get("repetition_kind") == predicate_family:
            return "V5"
    if (
        shape_kind == "single_state"
        and current_shape_supports_relation(shape_kind, contract_kind, predicate_family, operator)
        and material.candidate.get("producer") is None
        and set(material.resource_binding_plans) == {"single_state"}
        and len(shape.get("observation_plan", [])) == 1
    ):
        return "V2"
    if shape_kind == "causal_two_arm":
        if predicate_family == "P04" and predicate.get("before", {}).get("value_type") != "boolean":
            raise ValueError("current_protocol_predicate_not_registered")
        if not (
            predicate_family in _V1_PREDICATES
            and contract_kind in _V1_CONTRACT_PREDICATES
            and (predicate_family, operator) in _V1_CONTRACT_PREDICATES[contract_kind]
            and _signed_p12_contract_matches(
                contract_kind, predicate_family, predicate
            )
        ):
            raise ValueError("current_protocol_predicate_not_registered")
        if set(material.resource_binding_plans) == {"control", "treatment"}:
            return "V1"
    if (
        shape_kind == "metamorphic_query"
        and contract_kind in _V3_CONTRACT_PREDICATES
        and (predicate_family, operator) in _V3_CONTRACT_PREDICATES[contract_kind]
        and current_shape_supports_relation(shape_kind, contract_kind, predicate_family, operator, transform_kind=shape.get("transform_kind"))
        and set(material.resource_binding_plans) == {"metamorphic_query"}
        and isinstance(shape.get("query_plan"), list)
    ):
        return "V3"
    if (
        shape_kind == "lifecycle_workflow"
        and contract_kind in _V4_CONTRACT_PREDICATES
        and (predicate_family, operator) in _V4_CONTRACT_PREDICATES[contract_kind]
        and _signed_p12_contract_matches(contract_kind, predicate_family, predicate)
        and set(material.resource_binding_plans) == {"workflow"}
        and isinstance(shape.get("workflow_plan"), list)
    ):
        return "V4"
    if (
        shape_kind == "negative_no_effect"
        and contract_kind in _V6_CONTRACT_PREDICATES
        and (predicate_family, operator) in _V6_CONTRACT_PREDICATES[contract_kind]
        and set(material.resource_binding_plans) == {"negative_no_effect"}
        and isinstance(shape.get("negative_plan"), list)
        and shape.get("negative_kind") in {"rejection", "rejection_preservation"}
        and shape.get("rejection_detector", {}).get("kind") in {"http_status_class", "predicate"}
    ):
        return "V6"
    if (
        shape_kind == "actor_matrix"
        and contract_kind in _V7_CONTRACT_PREDICATES
        and (predicate_family, operator) in _V7_CONTRACT_PREDICATES[contract_kind]
        and set(material.resource_binding_plans) == {"actor_matrix"}
        and isinstance(shape.get("actor_plan"), list)
    ):
        return "V7"
    raise ValueError("current_protocol_material_shape_not_registered")


def _signed_p12_contract_matches(
    contract_kind: Any,
    predicate_family: Any,
    predicate: Any,
) -> bool:
    if predicate_family != "P12" or contract_kind not in {"C01", "C03"}:
        return True
    delta = predicate.get("delta") if isinstance(predicate, Mapping) else None
    return (
        isinstance(delta, int)
        and not isinstance(delta, bool)
        and ((contract_kind == "C01" and delta > 0)
             or (contract_kind == "C03" and delta < 0))
    )


def execute_current_protocol(
    material: Any,
    runtime: Any,
    *,
    artifact_writer: Callable[[str, bytes], None],
    output_level: str,
) -> CurrentProtocolExecution:
    protocol_kind = derive_current_protocol(material)
    if protocol_kind == "V8":
        from .temporal import execute_temporal
        collected, certificate, result = execute_temporal(material, runtime, artifact_writer=artifact_writer, output_level=output_level)
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(protocol_kind, collected, certificate, result)
    if protocol_kind == "V9":
        from .multi_resource import execute_multi_resource
        collected, certificate, result = execute_multi_resource(material, runtime, artifact_writer=artifact_writer, output_level=output_level)
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(protocol_kind, collected, certificate, result)
    if protocol_kind == "V5":
        from .repeated_execution import execute_repeated_execution
        collected, certificate, result = execute_repeated_execution(material, runtime, artifact_writer=artifact_writer, output_level=output_level)
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(protocol_kind, collected, certificate, result)
    if protocol_kind == "V2":
        collected, certificate, result = execute_single_state(
            material, runtime, artifact_writer=artifact_writer, output_level=output_level
        )
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(protocol_kind, collected, certificate, result)
    if protocol_kind == "V3":
        collected, certificate, result = execute_metamorphic_query(
            material, runtime, artifact_writer=artifact_writer, output_level=output_level
        )
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(protocol_kind, collected, certificate, result)
    if protocol_kind == "V4":
        collected, certificate, result = execute_lifecycle_workflow(
            material,
            runtime,
            artifact_writer=artifact_writer,
            output_level=output_level,
        )
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(
            protocol_kind=protocol_kind,
            collected=collected,
            certificate=certificate,
            result=result,
        )
    if protocol_kind == "V7":
        collected, certificate, result = execute_actor_matrix(
            material,
            runtime,
            artifact_writer=artifact_writer,
            output_level=output_level,
        )
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(
            protocol_kind=protocol_kind,
            collected=collected,
            certificate=certificate,
            result=result,
        )
    if protocol_kind == "V6":
        collected, certificate, result = execute_negative_no_effect(
            material,
            runtime,
            artifact_writer=artifact_writer,
            output_level=output_level,
        )
        validate_current_protocol_result(result, predicate=material.candidate["primary_predicate"])
        return CurrentProtocolExecution(
            protocol_kind=protocol_kind,
            collected=collected,
            certificate=certificate,
            result=result,
        )
    collected = CurrentRouteSCollector().collect(
        material,
        runtime,
        artifact_writer=artifact_writer,
        output_level=output_level,
    )
    certificate = construct_v1_route_s_certificate(collected, material)
    result = project_v1_protocol_result(
        candidate_id=material.candidate_id,
        predicate_family=material.candidate["primary_predicate"]["family"],
        certificate=certificate,
    )
    return CurrentProtocolExecution(
        protocol_kind=protocol_kind,
        collected=collected,
        certificate=certificate,
        result=result,
    )


def diagnose_current_protocol_failure(
    execution: CurrentProtocolExecution,
) -> dict[str, str] | None:
    """Explain a failed M12 execution without changing its scientific verdict."""

    result = execution.result
    verdict = result["protocol_verdict"]
    if verdict not in {"infrastructure_failed", "not_evaluable"}:
        return None
    predicate_reason = _predicate_unavailable_reason(execution)
    if verdict == "not_evaluable" and predicate_reason is not None:
        return {
            "failure_stage": "M12",
            "failure_phase": "predicate_evaluation",
            "failure_kind": "candidate_not_executable",
            "reason_code": _symbolic_reason(predicate_reason),
        }
    if verdict == "infrastructure_failed":
        phase, reason = _first_failed_protocol_record(
            execution.collected.evidence.get("protocol", {})
        )
        return {
            "failure_stage": "M12",
            "failure_phase": phase or str(result.get("failure_class") or "runtime"),
            "failure_kind": "runtime_adapter_failure",
            "reason_code": _symbolic_reason(
                reason or str(result.get("failure_class") or "runtime_failure")
            ),
        }
    predicate_result = result.get("predicate_result")
    reason = (
        predicate_result.get("reason_code")
        if isinstance(predicate_result, Mapping)
        else None
    )
    return {
        "failure_stage": "M12",
        "failure_phase": "predicate_evaluation",
        "failure_kind": "candidate_not_executable",
        "reason_code": _symbolic_reason(
            str(reason or result.get("failure_class") or "candidate_not_evaluable")
        ),
    }


def _predicate_unavailable_reason(
    execution: CurrentProtocolExecution,
) -> str | None:
    route_certificate = execution.certificate.get("route_s_certificate")
    fail_closed_reasons = (
        route_certificate.get("fail_closed_reasons", ())
        if isinstance(route_certificate, Mapping)
        else ()
    )
    return next(
        (
            str(reason)
            for reason in fail_closed_reasons
            if str(reason).startswith("predicate_operands_unavailable:")
        ),
        None,
    )


def _first_failed_protocol_record(value: Any, prefix: str = "") -> tuple[str, str]:
    if isinstance(value, Mapping):
        if value.get("status") == "failed" or value.get("state") == "failed":
            return prefix, str(value.get("reason_code") or "runtime_failure")
        for key, item in value.items():
            phase, reason = _first_failed_protocol_record(
                item, f"{prefix}.{key}" if prefix else str(key)
            )
            if phase:
                return phase, reason
    elif isinstance(value, list):
        for index, item in enumerate(value):
            phase, reason = _first_failed_protocol_record(
                item, f"{prefix}[{index}]"
            )
            if phase:
                return phase, reason
    return "", ""


def _symbolic_reason(value: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    return re.sub(r"[^a-z0-9]+", "_", snake).strip("_") or "runtime_failure"


def project_v1_protocol_result(
    *,
    candidate_id: str,
    predicate_family: str,
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    if predicate_family not in _V1_PREDICATES:
        raise ValueError("current_protocol_predicate_not_registered")
    inner = certificate.get("route_s_certificate")
    if (
        not isinstance(inner, Mapping)
        or inner.get("candidate", {}).get("candidate_id") != candidate_id
    ):
        raise ValueError("current_protocol_certificate_candidate_mismatch")
    outcome = inner.get("outcome")
    gate = inner.get("gates", {}).get("treatment_effect_present") or {}
    settle_timeout = any(
        inner.get("protocol", {}).get(slot, {}).get("reason_code")
        == "settle_timeout"
        for slot in ("settle_c", "settle_t")
    )
    if settle_timeout:
        verdict, claim_kind, failure_class = "not_evaluable", None, "settle_timeout"
    elif outcome == "confirmed":
        verdict, claim_kind, failure_class = "validated", "causal_confirmed", None
    elif outcome in _REFUTED_OUTCOMES:
        verdict, claim_kind, failure_class = "refuted", None, None
    elif outcome in _INFRASTRUCTURE_OUTCOMES:
        verdict, claim_kind = "infrastructure_failed", None
        failure_class = _INFRASTRUCTURE_OUTCOMES[outcome]
    elif outcome == "malformed_or_unsupported":
        verdict, claim_kind, failure_class = "not_evaluable", None, "contract"
    else:
        raise ValueError("current_protocol_legacy_outcome_unknown")
    predicate_result = None
    if settle_timeout:
        predicate_result = {
            "family": predicate_family,
            "status": "not_evaluable",
            "observed": {},
            "reason_code": "settle_timeout",
        }
    elif verdict in {"validated", "refuted"}:
        value = gate.get("value") if gate.get("computed") is True else None
        status = (
            "satisfied"
            if value is True
            else "violated"
            if value is False
            else "not_evaluable"
        )
        predicate_result = {
            "family": predicate_family,
            "status": status,
            "observed": {"treatment_effect_present": value},
            "reason_code": None if status != "not_evaluable" else "projection_unavailable",
        }
    result = {
        "schema_version": "uisemtest-current-protocol-result-v1",
        "candidate_id": candidate_id,
        "protocol_kind": "V1",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": predicate_result,
        "failure_class": failure_class,
        "evidence_ref": f"M12/{candidate_id}/execution_evidence.json",
        "certificate_ref": f"M12/{candidate_id}/certificate.json",
        "v1_legacy_outcome": outcome,
    }
    validate_current_protocol_result(result)
    return result


def candidate_local_protocol_result(
    candidate_id: str,
    error: CandidateLocalFailure,
    *,
    protocol_kind: str = "V1",
) -> dict[str, Any]:
    result = {
        "schema_version": "uisemtest-current-protocol-result-v1",
        "candidate_id": candidate_id,
        "protocol_kind": protocol_kind,
        "protocol_verdict": "not_evaluable",
        "claim_kind": None,
        "predicate_result": None,
        "failure_class": error.category,
        "evidence_ref": None,
        "certificate_ref": None,
        "v1_legacy_outcome": None,
    }
    validate_current_protocol_result(result)
    return result


def _validate_single_state_check_evidence(
    predicate_result: Mapping[str, Any], *, predicate: Mapping[str, Any] | None = None,
) -> None:
    """Close the finite range/member records against their reported reduction."""
    def conjunction(checks: list[Mapping[str, Any]]) -> bool | None:
        states = [check["satisfied"] for check in checks]
        return False if any(state is False for state in states) else None if any(state is None for state in states) else True

    def result_state(row: Mapping[str, Any], identifiers: set[str] | None = None) -> bool | None:
        if set(row) != {"satisfied", "observed", "reason_code", *(identifiers or set())} or not isinstance(row["observed"], Mapping):
            raise ValueError("finite_check_record_shape_drift")
        state, reason = row["satisfied"], row["reason_code"]
        if state is not None and type(state) is not bool or (state is None) != (isinstance(reason, str) and bool(reason)) or state is not None and reason is not None:
            raise ValueError("finite_check_state_reason_drift")
        return state

    def collection_relation_state(observed: Mapping[str, Any], atom: Mapping[str, Any] | None = None) -> bool:
        if (set(observed) != {"relation", "representation", "comparison_basis", "left_count", "right_count"}
            or type(observed["relation"]) is not bool
            or observed["representation"] not in {"set", "multiset", "sequence"}
            or observed["comparison_basis"] not in {"full_json_value", "frozen_projection", "identity_tuple"}
            or any(type(observed[name]) is not int or observed[name] < 0 for name in ("left_count", "right_count"))):
            raise ValueError("collection_relation_record_shape_drift")
        if atom is not None and (observed["representation"] != atom.get("representation", "set") or observed["comparison_basis"] != atom.get("comparison_basis", "identity_tuple")):
            raise ValueError("collection_relation_frozen_basis_drift")
        if observed["relation"] and observed["representation"] in {"multiset", "sequence"} and observed["left_count"] != observed["right_count"]:
            raise ValueError("collection_relation_count_drift")
        return observed["relation"]

    def ordering_state(observed: Mapping[str, Any]) -> bool | None:
        if set(observed) != {"checks"} or [row.get("check_id") for row in observed["checks"]] != ["order", "multiset"]:
            raise ValueError("ordering_fixed_checks_drift")
        order, multiset = observed["checks"]
        result_state(order, {"check_id"})
        result_state(multiset, {"check_id"})
        detail = order["observed"]
        if "ordering_checks" in detail:
            if set(detail) != {"member_count", "ordering_checks"} or type(detail["member_count"]) is not int or detail["member_count"] < 0:
                raise ValueError("ordering_member_count_drift")
            count, rows = detail["member_count"], detail["ordering_checks"]
            missing = [row for row in rows if "previous_index" not in row]
            missing_indices = [row["member_index"] for row in missing]
            if (missing_indices != sorted(set(missing_indices))
                or any(type(index) is not int or not 0 <= index < count for index in missing_indices)):
                raise ValueError("ordering_missing_key_records_drift")
            for row in missing:
                if result_state(row, {"member_index"}) is not None:
                    raise ValueError("ordering_missing_key_truth_drift")
            pairs = [row for row in rows if "previous_index" in row]
            expected = [index for index in range(1, count) if index not in missing_indices and index - 1 not in missing_indices]
            if rows != missing + pairs or [row["member_index"] for row in pairs] != expected:
                raise ValueError("ordering_adjacent_records_drift")
            for row in pairs:
                result_state(row, {"member_index", "previous_index"})
                if type(row["member_index"]) is not int or type(row["previous_index"]) is not int or row["previous_index"] != row["member_index"] - 1:
                    raise ValueError("ordering_adjacent_index_drift")
                if row["satisfied"] is not None and row["observed"]:
                    raise ValueError("ordering_comparison_record_drift")
            if order["satisfied"] is not conjunction(rows):
                raise ValueError("ordering_order_reduction_drift")
        elif order["satisfied"] is not None or "diagnostics" not in detail:
            raise ValueError("ordering_member_records_missing")
        if multiset["satisfied"] is not None:
            basis = {"representation": "multiset", "comparison_basis": predicate.get("comparison_basis", "full_json_value")} if predicate is not None else {"representation": "multiset", "comparison_basis": multiset["observed"].get("comparison_basis")}
            if multiset["satisfied"] is not collection_relation_state(multiset["observed"], basis):
                raise ValueError("ordering_multiset_reduction_drift")
            if "member_count" in detail and detail["member_count"] != multiset["observed"]["right_count"]:
                raise ValueError("ordering_check_member_count_drift")
        elif "diagnostics" not in multiset["observed"]:
            raise ValueError("ordering_multiset_material_drift")
        return conjunction(observed["checks"])

    def disjoint_state(observed: Mapping[str, Any]) -> bool | None:
        if set(observed) != {"partition_checks"} or not isinstance(observed["partition_checks"], list) or not observed["partition_checks"]:
            raise ValueError("partition_pair_records_missing")
        rows = observed["partition_checks"]
        if predicate is not None:
            count = len(predicate["partitions"])
        else:
            count = max(row.get("right_partition", -1) for row in rows) + 1
        expected = [(left, right) for left in range(count) for right in range(left + 1, count)]
        if [(row.get("left_partition"), row.get("right_partition")) for row in rows] != expected:
            raise ValueError("partition_pair_records_drift")
        for row in rows:
            result_state(row, {"left_partition", "right_partition"})
            if type(row["left_partition"]) is not int or type(row["right_partition"]) is not int or row["satisfied"] is not None and row["observed"]:
                raise ValueError("partition_pair_record_shape_drift")
        return conjunction(rows)

    def check_status(state: bool | None) -> None:
        expected = "satisfied" if state is True else "violated" if state is False else "not_evaluable"
        if predicate_result["reason_code"] == "query_scope_incomplete":
            if predicate_result["status"] != "not_evaluable" or not predicate_result["observed"].get("diagnostics"):
                raise ValueError("query_incomplete_scope_result_drift")
        elif predicate_result["status"] != expected:
            raise ValueError("single_state_composite_reduction_drift")

    def range_state(observed: Mapping[str, Any]) -> bool | None:
        checks = observed["checks"]
        if [check["check_id"] for check in checks] != ["lower", "upper"]:
            raise ValueError("single_state_range_check_order_drift")
        return conjunction(checks)

    def uniqueness_state(observed: Mapping[str, Any]) -> bool | None:
        rows = observed["uniqueness_checks"]
        if set(observed) != {"member_count", "uniqueness_checks"} or type(observed["member_count"]) is not int or observed["member_count"] != len(rows) or [row["member_index"] for row in rows] != list(range(len(rows))):
            raise ValueError("single_state_uniqueness_member_records_drift")
        for row in rows:
            if (set(row) != {"member_index", "duplicate_of", "satisfied", "reason_code"}
                or type(row["member_index"]) is not int
                or row["satisfied"] is not None and type(row["satisfied"]) is not bool
                or row["reason_code"] not in {None, "predicate_operand_missing", "predicate_operand_type_mismatch", "predicate_operand_invalid", "sensitive_material_unavailable", "numeric_precision_source_missing"}):
                raise ValueError("single_state_uniqueness_record_shape_drift")
            index, duplicate = row["member_index"], row["duplicate_of"]
            if duplicate is not None and (type(duplicate) is not int or not 0 <= duplicate < index or rows[duplicate]["satisfied"] is not True):
                raise ValueError("single_state_uniqueness_duplicate_reference_drift")
            state = row["satisfied"]
            if ((state is False) != (duplicate is not None)
                or (state is None) != (row["reason_code"] is not None)):
                raise ValueError("single_state_uniqueness_check_drift")
        return conjunction(rows)

    def atom_state(atom: Mapping[str, Any], observed: Mapping[str, Any]) -> bool | None:
        if "diagnostics" in observed:
            return None
        if atom["family"] == "P10":
            if set(observed) != {"format_valid"} or type(observed["format_valid"]) is not bool:
                raise ValueError("single_state_format_record_shape_drift")
            return observed["format_valid"]
        if (set(observed) != {"measured_value", "threshold"}
            or type(observed["measured_value"]) is not int or observed["measured_value"] < 0
            or type(observed["threshold"]) is not int):
            raise ValueError("single_state_measurement_record_shape_drift")
        actual, threshold = observed["measured_value"], observed["threshold"]
        if atom.get("empty") == "allow" and actual == 0:
            return True
        return {"eq": lambda: actual == threshold, "neq": lambda: actual != threshold,
                "lt": lambda: actual < threshold, "le": lambda: actual <= threshold,
                "gt": lambda: actual > threshold, "ge": lambda: actual >= threshold}[atom["operator"]]()

    observed = {key: value for key, value in predicate_result["observed"].items() if key != "diagnostics"} if any(key != "diagnostics" for key in predicate_result["observed"]) else predicate_result["observed"]
    family = predicate_result["family"]
    if family in {"P08", "P19"}:
        if predicate_result["status"] != "not_evaluable":
            from ..dsl import validate_arithmetic_observed
            validate_arithmetic_observed(observed, predicate_result["status"] == "satisfied", predicate)
        elif (set(observed) not in (set(), {"diagnostics"}, {"member_count"})
              or "member_count" in observed and (family != "P19" or observed["member_count"] != 0 or predicate_result["reason_code"] != "numeric_empty_extremum")):
            raise ValueError("arithmetic_unknown_evidence_drift")
        return
    if family == "P16":
        if "checks" not in observed:
            if predicate_result["status"] == "not_evaluable" and "diagnostics" in observed:
                return
            raise ValueError("ordering_fixed_checks_missing")
        check_status(ordering_state(observed))
        return
    if family == "P17":
        if "relation" in observed:
            check_status(collection_relation_state(observed, predicate))
        elif predicate_result["status"] != "not_evaluable" or "diagnostics" not in observed:
            raise ValueError("collection_relation_records_missing")
        return
    if family == "P18" and ("partition_checks" in observed or predicate is not None and predicate["operator"] == "pairwise_disjoint"):
        check_status(disjoint_state(observed))
        return
    if predicate is not None and (predicate["family"] == "P10" or predicate["family"] == "P11" and predicate.get("target") is not None):
        state = atom_state(predicate, observed)
        expected = "satisfied" if state is True else "violated" if state is False else "not_evaluable"
        if predicate_result["status"] != expected:
            raise ValueError("single_state_atom_reduction_drift")
        return
    if predicate_result["family"] == "P15":
        if "uniqueness_checks" not in observed:
            if predicate_result["status"] == "not_evaluable" and "diagnostics" in observed:
                return
            raise ValueError("single_state_uniqueness_records_missing")
        state = uniqueness_state(observed)
        check_status(state)
        return
    if predicate is not None and predicate.get("family") == "P03" and predicate.get("operator") == "range" and "checks" not in observed:
        raise ValueError("single_state_range_checks_missing")
    if "checks" not in observed:
        if predicate_result["family"] == "forall" and not (
            predicate_result["status"] == "not_evaluable" and "diagnostics" in observed
        ):
            raise ValueError("single_state_forall_member_records_missing")
        return
    if predicate_result["family"] == "P03":
        if "member_count" in observed:
            raise ValueError("single_state_range_check_shape_drift")
        state = range_state(observed)
    elif predicate_result["family"] == "forall":
        if "member_count" not in observed:
            raise ValueError("single_state_forall_member_records_missing")
        members = observed["checks"]
        parameters = observed["parameter_checks"]
        if predicate is not None and predicate.get("item_guard") is None:
            for member in members:
                implicit_guard = member["guard"]
                if (
                    set(implicit_guard) != {"satisfied", "observed", "reason_code"}
                    or implicit_guard["satisfied"] is not True
                    or implicit_guard["observed"] != {}
                    or implicit_guard["reason_code"] is not None
                    or member["body"] is None
                ):
                    raise ValueError("single_state_forall_implicit_guard_drift")
        applicable = sum(member["guard"]["satisfied"] is True for member in members)
        if (
            observed["member_count"] != len(members)
            or [member["member_index"] for member in members] != list(range(len(members)))
            or observed["applicable_member_count"] != applicable
            or observed["nonempty_support"] is not (applicable > 0)
            or applicable > 0 and parameters
            or len({check["check_id"] for check in parameters}) != len(parameters)
            or any(check["check_id"] not in {"right", "lower", "upper", "domain", "item_guard.right"} for check in parameters)
        ):
            raise ValueError("single_state_forall_member_count_drift")
        if predicate is not None:
            expected_parameters = []
            if applicable == 0:
                for prefix, atom in (("", predicate["body"]), ("item_guard.", predicate.get("item_guard"))):
                    if atom is None:
                        continue
                    fields = ("right",) if atom["family"] in {"P02", "P09", "P11"} else ("lower", "upper") if atom["family"] == "P03" and atom["operator"] == "range" else ("domain",) if atom["family"] == "P03" else ()
                    expected_parameters.extend(prefix + field for field in fields if atom[field].get("ref", {}).get("role") != "item")
            if [check["check_id"] for check in parameters] != expected_parameters:
                raise ValueError("single_state_forall_parameter_records_drift")
        for member in members:
            guard, body = member["guard"]["satisfied"], member["body"]
            if guard is True:
                if body is None:
                    raise ValueError("single_state_forall_body_result_missing")
                if predicate is not None and predicate["body"].get("family") == "P03" and predicate["body"].get("operator") == "range" and "checks" not in body["observed"]:
                    raise ValueError("single_state_forall_range_checks_missing")
                if "checks" in body["observed"] and body["satisfied"] is not range_state(body["observed"]):
                    raise ValueError("single_state_forall_range_reduction_drift")
                if predicate is not None and predicate["body"]["family"] in {"P10", "P11"}:
                    if body["satisfied"] is not atom_state(predicate["body"], body["observed"]):
                        raise ValueError("single_state_atom_reduction_drift")
                if predicate is not None and predicate["body"].get("family") == "P15":
                    if "uniqueness_checks" not in body["observed"]:
                        if body["satisfied"] is not None or "diagnostics" not in body["observed"]:
                            raise ValueError("single_state_uniqueness_records_missing")
                    elif body["satisfied"] is not uniqueness_state(body["observed"]):
                        raise ValueError("single_state_uniqueness_reduction_drift")
                member_state = body["satisfied"]
            else:
                if body is not None:
                    raise ValueError("single_state_forall_body_without_applicability")
                member_state = True if guard is False else None
            if member["satisfied"] is not member_state:
                raise ValueError("single_state_forall_member_reduction_drift")
        state = conjunction(members + parameters)
    else:
        raise ValueError("single_state_composite_family_drift")
    check_status(state)


def validate_current_protocol_result(
    result: Mapping[str, Any], *, predicate: Mapping[str, Any] | None = None,
) -> None:
    validate_artifact("current_protocol_result_v1.schema.json", result)
    verdict = result["protocol_verdict"]
    legacy_outcome = result["v1_legacy_outcome"]
    refs_present = all(
        isinstance(result[key], str) and bool(result[key])
        for key in ("evidence_ref", "certificate_ref")
    )
    refs_absent = all(
        result[key] is None for key in ("evidence_ref", "certificate_ref")
    )
    protocol = result["protocol_kind"]
    if protocol == "V2" and result["predicate_result"] is not None and result["predicate_result"]["family"] not in {"P01", "P02", "P03", "P08", "P09", "P10", "P11", "P13", "P15", "P19", "P21", "forall"}:
        raise ValueError("single_state_predicate_not_registered")
    if protocol in {"V2", "V3"} and result["predicate_result"] is not None:
        _validate_single_state_check_evidence(result["predicate_result"], predicate=predicate)
    if protocol == "V8" and result["predicate_result"] is not None:
        from .temporal import validate_temporal_predicate_result
        validate_temporal_predicate_result(result["predicate_result"])
    if protocol == "V9" and result["predicate_result"] is not None and result["predicate_result"]["status"] != "not_evaluable":
        from ..dsl import validate_arithmetic_observed
        observed = {key: value for key, value in result["predicate_result"]["observed"].items() if key not in {"consistency", "observation_count", "diagnostics"}}
        validate_arithmetic_observed(observed, result["predicate_result"]["status"] == "satisfied", predicate)
    primary_result = result.get("predicate_result")
    if protocol == "V4" and primary_result is not None and primary_result["family"] == "P06" and primary_result["status"] != "not_evaluable":
        from ..dsl import validate_numeric_delta_observed
        validate_numeric_delta_observed(primary_result["observed"], primary_result["status"] == "satisfied", predicate)
    if protocol != "V3" and primary_result is not None and primary_result["reason_code"] == "query_scope_incomplete":
        raise ValueError("query_scope_reason_outside_query_protocol")
    if protocol in {"V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"}:
        expected_claim = {
            "V2": "single_state_confirmed",
            "V9": "joint_observation_confirmed",
            "V8": "temporal_observation_confirmed",
            "V3": "metamorphic_confirmed",
            "V4": "workflow_confirmed",
            "V5": "repeated_execution_confirmed",
            "V6": "negative_behavior_confirmed",
            "V7": "actor_relation_confirmed",
        }[protocol]
        if result["v1_legacy_outcome"] is not None or not (
            refs_present or verdict == "not_evaluable" and refs_absent
        ):
            raise ValueError("non_v1_current_protocol_result_invalid")
        if verdict == "validated" and (
            result["claim_kind"] != expected_claim
            or result["predicate_result"]["status"] != "satisfied"
            or result["failure_class"] is not None
        ):
            raise ValueError("validated_non_v1_current_protocol_result_invalid")
        if verdict == "refuted" and (
            result["claim_kind"] is not None
            or result["predicate_result"]["status"]
            not in ({"satisfied", "violated"} if protocol == "V6" else {"violated"})
            or result["failure_class"] is not None
        ):
            raise ValueError("refuted_non_v1_current_protocol_result_invalid")
        if verdict == "infrastructure_failed" and (
            result["claim_kind"] is not None
            or result["predicate_result"] is not None and (protocol not in {"V3", "V5", "V6", "V8", "V9"} or result["predicate_result"]["status"] == "violated")
            or result["failure_class"] not in {
                "setup_failure", "request_transport_failure", "observer_failure"
            }
        ):
            raise ValueError("infrastructure_non_v1_current_protocol_result_invalid")
        if verdict == "not_evaluable" and (
            result["claim_kind"] is not None
            or result["failure_class"] not in {"binding", "contract", "settle_timeout"}
        ):
            raise ValueError("not_evaluable_non_v1_current_protocol_result_invalid")
        return
    if verdict == "validated":
        if (
            legacy_outcome != "confirmed"
            or not refs_present
            or result["claim_kind"] != "causal_confirmed"
            or result["predicate_result"]["status"] != "satisfied"
            or result["failure_class"] is not None
        ):
            raise ValueError("validated_current_protocol_result_invalid")
    elif verdict == "refuted":
        if (
            legacy_outcome not in _REFUTED_OUTCOMES
            or not refs_present
            or result["claim_kind"] is not None
            or result["failure_class"] is not None
        ):
            raise ValueError("refuted_current_protocol_result_invalid")
    elif verdict == "not_evaluable":
        if (
            not (
                legacy_outcome == "malformed_or_unsupported" and refs_present
                or legacy_outcome == "infrastructure_failed"
                and refs_present
                and result["failure_class"] == "settle_timeout"
                or legacy_outcome is None and refs_absent
            )
            or result["claim_kind"] is not None
            or result["failure_class"]
            not in {
                "binding",
                "contract",
                "writer",
                "capture_safety",
                "settle_timeout",
            }
        ):
            raise ValueError("not_evaluable_current_protocol_result_invalid")
    elif verdict == "infrastructure_failed":
        if (
            legacy_outcome not in _INFRASTRUCTURE_OUTCOMES
            or not refs_present
            or result["claim_kind"] is not None
            or result["failure_class"]
            not in {
                "setup_failure",
                "request_transport_failure",
                "observer_failure",
            }
        ):
            raise ValueError("infrastructure_current_protocol_result_invalid")


def persist_current_protocol_execution(
    *,
    run_root: Path,
    material: Any,
    execution: CurrentProtocolExecution,
    output_level: str,
) -> CurrentRouteSArtifactRecord:
    if execution.protocol_kind != derive_current_protocol(material):
        raise ValueError("current_protocol_execution_dispatch_drift")
    if execution.protocol_kind in {"V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"}:
        evidence_ref = f"M12/{material.candidate_id}/execution_evidence.json"
        certificate_ref = f"M12/{material.candidate_id}/certificate.json"
        evidence_bytes = execution.collected.execution_evidence_bytes
        certificate_bytes = canonical_json_bytes(execution.certificate)
        for ref, payload in (
            (evidence_ref, evidence_bytes),
            (certificate_ref, certificate_bytes),
        ):
            path = run_root / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        if output_level in {"forensic", "debug"}:
            _persist_candidate_raw_artifacts(
                run_root=run_root,
                candidate_id=material.candidate_id,
                artifact_bytes=getattr(execution.collected, "artifact_bytes", None) or {},
            )
        source = {
            "candidate": _memory_ref(
                f"M11b/{material.candidate_id}/candidate.json",
                canonical_json_bytes(material.candidate),
            ),
            "execution_material": _memory_ref(
                f"M11b/{material.candidate_id}/execution_material.json",
                material.execution_material_bytes,
            ),
            "execution_evidence": _memory_ref(evidence_ref, evidence_bytes),
            "certificate": _memory_ref(certificate_ref, certificate_bytes),
            "normalized_candidate_sha256": material.bound_candidate_sha256,
        }
        return CurrentRouteSArtifactRecord(
            candidate_id=material.candidate_id,
            outcome=execution.result["protocol_verdict"],
            material=material,
            collected=execution.collected,
            envelope=execution.certificate,
            protocol_result=execution.result,
            source=source,
        )
    return persist_current_route_s_result(
        run_root=run_root,
        material=material,
        collected=execution.collected,
        envelope=execution.certificate,
        protocol_result=execution.result,
        output_level=output_level,
    )


def _persist_candidate_raw_artifacts(
    *,
    run_root: Path,
    candidate_id: str,
    artifact_bytes: Mapping[str, bytes],
) -> list[str]:
    """Write the raw slot records (setup rows, error records, checkpoints) a
    V2-V9 execution collected under ``M12/<candidate>/raw/``.

    The evidence JSON references these files by ``raw_ref``/``error_ref``; before
    this they were kept in memory only, which left setup failures without any
    on-disk reason beyond the exception class name.
    """

    prefix = f"M12/{candidate_id}/raw/"
    candidate_root = (run_root / f"M12/{candidate_id}").resolve()
    written: list[str] = []
    for ref in sorted(artifact_bytes):
        if not ref.startswith(prefix):
            continue
        target = (run_root / ref).resolve()
        if not target.is_relative_to(candidate_root):
            raise ValueError("candidate raw artifact path escapes its M12 root")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact_bytes[ref])
        written.append(ref)
    return written


def _memory_ref(path: str, payload: bytes) -> dict[str, str]:
    import hashlib

    return {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}


def build_current_protocol_tests(*args: Any, **kwargs: Any) -> dict[str, Any]:
    closure = args[0] if args else kwargs.get("closure")
    if not isinstance(closure, Mapping) or any(
        (row.get("protocol_kind"), row.get("claim_kind"))
        not in {
            ("V1", "causal_confirmed"),
            ("V2", "single_state_confirmed"),
            ("V9", "joint_observation_confirmed"),
            ("V8", "temporal_observation_confirmed"),
            ("V3", "metamorphic_confirmed"),
            ("V4", "workflow_confirmed"),
            ("V5", "repeated_execution_confirmed"),
            ("V6", "negative_behavior_confirmed"),
            ("V7", "actor_relation_confirmed"),
        }
        for row in closure.get("confirmed", [])
    ):
        raise ValueError("current_M13_protocol_not_registered")
    return build_certified_relation_tests(*args, **kwargs)


def run_current_protocol_calibration(
    suite: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    if any(test.get("protocol_kind") not in REGISTERED_PROTOCOLS for test in suite.get("tests", [])):
        raise ValueError("current_M14_protocol_not_registered")
    if any(test.get("normal_runs") != 1 for test in suite.get("tests", [])):
        raise ValueError("current_M14_normal_runs_must_equal_one")
    if not isinstance(kwargs.get("canonical_relation_core_by_candidate"), Mapping):
        raise ValueError("current_M14_canonical_relation_core_mapping_required")
    return run_current_calibration(suite, **kwargs)


__all__ = (
    "CurrentProtocolExecution",
    "REGISTERED_PROTOCOLS",
    "build_current_protocol_tests",
    "candidate_local_protocol_result",
    "current_executable_relation_language",
    "current_shape_supports_relation",
    "derive_current_protocol",
    "execute_current_protocol",
    "persist_current_protocol_execution",
    "project_v1_protocol_result",
    "run_current_protocol_calibration",
    "validate_current_protocol_result",
)
