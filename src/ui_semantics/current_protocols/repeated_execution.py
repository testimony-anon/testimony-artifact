"""The three frozen V5 repetition plans and their fresh-result evaluator."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

from ..current_route_s import canonical_json_bytes
from ..current_settle import route_observer_is_pure
from ..dsl import (
    PredicateNotEvaluable,
    _resolve_value_ref,
    _strict_equal,
    copy_numeric_sources,
    evaluate_predicate,
    request_numeric_observation,
)
from ..route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    reject_redacted_predicate_dependencies,
)

CHECKS = {
    "repeat_equal": ("projection_equal",),
    "repeat_rejected": ("second_rejection", "preservation"),
    "repeat_delta": ("first_delta", "second_delta"),
}


@dataclass(frozen=True)
class RepeatedCollectedEvidence:
    evidence: dict[str, Any]
    execution_evidence_bytes: bytes
    artifact_hashes: dict[str, str]
    artifact_bytes: dict[str, bytes]
    partial_records: tuple[dict[str, Any], ...]
    artifact_write_sequence: tuple[str, ...]
    runtime_counts: dict[str, int]
    volatile_sensitive_values: tuple[str, ...] = ()


def _row(check_id: str, value: bool | None, observed: Mapping[str, Any] | None = None,
         reason: str | None = None) -> dict[str, Any]:
    return {"check_id": check_id,
            "status": "satisfied" if value is True else "violated" if value is False else "not_evaluable",
            "observed": dict(observed or {}), "reason_code": reason}


def _reason(error: BaseException) -> str:
    if isinstance(error, PredicateNotEvaluable):
        return error.reason_code
    if isinstance(error, SensitiveMaterialUnavailable):
        return "sensitive_material_unavailable"
    if isinstance(error, KeyError):
        return "path_or_operand_missing"
    if isinstance(error, TypeError):
        return "type_mismatch"
    return str(error) or "operand_unavailable"


def _executed(record: Mapping[str, Any]) -> bool:
    return record.get("state") == "executed" and record.get("status") == "pass"


def _http_status(record: Mapping[str, Any], *, observer: bool = False) -> int | None:
    status = (record.get("response") or {}).get("status") if observer else record.get("transport_status")
    return status if type(status) is int else None


def _sources(action: Mapping[str, Any], **observations: Mapping[str, Any]) -> dict[str, Any]:
    return {**observations,
            "producer_request": request_numeric_observation(action, action.get("request")),
            "producer_response": copy_numeric_sources(action, {"body": action.get("response")}),
            "producer_status": {"body": _http_status(action)}}


def evaluate_repeated_result(predicate: Mapping[str, Any], records: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate only this run's checkpoints, never a prior predicate verdict.

    Runtime request-identity flags are mechanical checks against its frozen
    prepared transport, not business assertions. Every check retains its own
    dependencies so a later unrelated failure cannot erase a trusted false.
    """
    family = predicate["family"]
    if family not in CHECKS:
        raise ValueError("unsupported repetition predicate")
    diagnostics: list[dict[str, str]] = []
    applicability: list[dict[str, Any]] = []

    def diagnostic(slot: str, reason: str, failure_class: str = "binding") -> None:
        row = {"checkpoint_id": slot, "reason_code": reason, "failure_class": failure_class}
        if row not in diagnostics:
            diagnostics.append(row)

    def unavailable(slot: str, *, observer: bool = False, rejection: bool = False) -> str | None:
        record = records.get(slot)
        if not isinstance(record, Mapping):
            return "required_checkpoint_missing"
        if record.get("state") == "not_executed" and record.get("status") != "failed":
            return "required_checkpoint_missing"
        if not _executed(record):
            reason = str(record.get("reason_code") or "execution_failed")
            kind = "setup_failure" if slot.endswith(("_reset", "_setup")) else "observer_failure" if observer else "request_transport_failure"
            diagnostic(slot, reason, "settle_timeout" if reason == "settle_timeout" else kind)
            return reason
        if observer:
            status = _http_status(record, observer=True)
            if status is None or not 200 <= status < 300:
                diagnostic(slot, "observer_http_unsuccessful", "observer_failure")
                return "observer_http_unsuccessful"
            if not route_observer_is_pure(record):
                diagnostic(slot, "observer_mutating_or_uncertain", "observer_failure")
                return "observer_mutating_or_uncertain"
        elif "_action" in slot:
            status = _http_status(record)
            if status is None or not (200 <= status < 300 or rejection and 400 <= status < 500):
                diagnostic(slot, "action_http_unsuccessful", "request_transport_failure")
                return "action_http_unsuccessful"
            if record.get("request_identity_verified") is not True:
                diagnostic(slot, "repeated_request_identity_unverified")
                return "repeated_request_identity_unverified"
            occurrence = int(slot[-1])
            if record.get("occurrence_index") != occurrence or type(record.get("occurrence_index")) is not int:
                return "repeated_occurrence_mismatch"
        return None

    def arm_valid(prefix: str) -> str | None:
        for suffix in ("reset", "setup"):
            reason = unavailable(f"{prefix}_{suffix}")
            if reason:
                return reason
        return None

    def dependencies(slots: tuple[str, ...], action_slot: str, *, rejection: bool = False) -> str | None:
        prefix = action_slot[0]
        if reason := arm_valid(prefix):
            return reason
        if reason := unavailable(action_slot, rejection=rejection):
            return reason
        action = records[action_slot]
        epoch = action.get("reset_epoch")
        reset_epoch = records[f"{prefix}_reset"].get("reset_epoch")
        if not isinstance(epoch, str) or not epoch or epoch != reset_epoch:
            return "repeated_reset_epoch_mismatch"
        for slot in slots:
            if reason := unavailable(slot, observer=True):
                return reason
            if records[slot].get("reset_epoch") != epoch or records[slot].get("checkpoint_id") != slot:
                return "repeated_checkpoint_identity_mismatch"
        if action.get("checkpoint_id") != action_slot:
            return "repeated_checkpoint_identity_mismatch"
        # The second effect is a repeated request only after the first
        # request and its intermediate checkpoint actually completed.
        if action_slot.endswith("2") and (reason := dependencies((f"{prefix}1",), f"{prefix}_action1")):
            return reason
        return None

    def projection(check_id: str, left_slot: str, right_slot: str,
                   left_action: str, right_action: str, *, rejection: bool = False) -> dict[str, Any]:
        atom = predicate["projection"]
        for slot, action, is_rejection in ((left_slot, left_action, False), (right_slot, right_action, rejection)):
            if reason := dependencies((slot,), action, rejection=is_rejection):
                return _row(check_id, None, reason=reason)
        try:
            values = []
            for key, slot, action_slot in (("left", left_slot, left_action), ("right", right_slot, right_action)):
                action = records[action_slot]
                observation = records[slot]
                ref = atom[key]
                reject_redacted_predicate_dependencies({"target": ref}, {
                    ref["role"]: ((observation, "response"),),
                    "producer_request": ((action, "request"),),
                    "producer_response": ((action, "response"),),
                })
                values.append(_resolve_value_ref(ref, _sources(action, **{ref["role"]: observation["response"]})))
            # Resolve each located endpoint against its own fresh arm identity.
            comparison = {"family": "P20", "operator": "equal",
                          "left": {"role": "before", "path": "$", "value_type": atom["left"]["value_type"]},
                          "right": {"role": "after", "path": "$", "value_type": atom["right"]["value_type"]}}
            value, _ = evaluate_predicate(comparison, {"before": {"body": values[0]}, "after": {"body": values[1]}})
            return _row(check_id, value, {"values_equal": value})
        except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
            return _row(check_id, None, reason=_reason(error))

    def delta(check_id: str, before: str, after: str, action_slot: str) -> dict[str, Any]:
        if reason := dependencies((before, after), action_slot):
            return _row(check_id, None, reason=reason)
        action = records[action_slot]
        atom = predicate["delta"]
        try:
            reject_redacted_predicate_dependencies(atom, {
                "before": ((records[before], "response"),), "after": ((records[after], "response"),),
                "producer_request": ((action, "request"),), "producer_response": ((action, "response"),),
            })
            value, observed = evaluate_predicate(atom, _sources(action, before=records[before]["response"], after=records[after]["response"]))
            return _row(check_id, value, observed)
        except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
            return _row(check_id, None, reason=_reason(error))

    def rejected(action: Mapping[str, Any]) -> bool:
        atom = predicate.get("rejection")
        if atom is None:
            return 400 <= _http_status(action) < 500
        reject_redacted_predicate_dependencies(atom, {"producer_response": ((action, "response"),)})
        value, _ = evaluate_predicate(atom, _sources(action))
        return value

    if family == "repeat_equal":
        baseline = projection("baseline_equivalent", "A0", "B0", "A_action1", "B_action1")
        # Baseline is applicability, never a counterexample to idempotence.
        applicability.append(baseline)
        try:
            prepared = [records[f"{prefix}_prepare"] for prefix in ("A", "B")]
            if any(not _executed(record) for record in prepared):
                raise ValueError("prepared_request_unavailable")
            # Authentication headers are deliberately excluded from the logical
            # business input; their separate transport redaction is not a hole
            # in the comparable input used by this check.
            if any((record.get("redaction_manifest") or {}).get("logical_request") for record in prepared):
                raise SensitiveMaterialUnavailable("sensitive_material_unavailable")
            logical = [record["logical_request"] for record in prepared]
            equal = _strict_equal(logical[0], logical[1])
            epochs = [records[f"{prefix}_reset"].get("reset_epoch") for prefix in ("A", "B")]
            isolated = all(isinstance(epoch, str) and epoch for epoch in epochs) and epochs[0] != epochs[1]
            applicability.append(_row("logical_input_equivalent", equal and isolated,
                                      {"values_equal": equal, "reset_epochs_distinct": isolated}))
        except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
            applicability.append(_row("logical_input_equivalent", None, reason=_reason(error)))
        if all(row["status"] == "satisfied" for row in applicability):
            checks = [projection("projection_equal", "A1", "B2", "A_action1", "B_action2")]
        else:
            checks = [_row("projection_equal", None, reason="repeat_baseline_or_input_not_established")]
    elif family == "repeat_rejected":
        first = records.get("B_action1", {})
        first_status = _http_status(first)
        if first.get("state") == "executed" and first_status is not None and 400 <= first_status < 500:
            first_reason = "repeat_first_success_not_established"
        else:
            first_reason = dependencies(("B0", "B1"), "B_action1")
        if first_reason is None and predicate.get("rejection") is not None:
            try:
                if rejected(first):
                    first_reason = "repeat_first_success_not_established"
            except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
                first_reason = _reason(error)
        applicability.append(_row("first_success", first_reason is None, reason=first_reason))
        if first_reason:
            checks = [_row(key, None, reason=first_reason) for key in CHECKS[family]]
        else:
            second_reason = dependencies((), "B_action2", rejection=True)
            if second_reason:
                rejection_check = _row("second_rejection", None, reason=second_reason)
            else:
                action = records["B_action2"]
                try:
                    value = rejected(action)
                    rejection_check = _row("second_rejection", value, {"rejected": value, "response_status": _http_status(action)})
                except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
                    rejection_check = _row("second_rejection", None, reason=_reason(error))
            checks = [rejection_check, projection("preservation", "B1", "B2", "B_action1", "B_action2", rejection=True)]
    else:
        checks = [delta("first_delta", "B0", "B1", "B_action1"),
                  delta("second_delta", "B1", "B2", "B_action2")]

    # Diagnose executed failures even when another dependency short-circuited.
    for slot, record in records.items():
        if isinstance(record, Mapping) and record.get("status") == "failed":
            if family == "repeat_rejected" and slot == "B_action1" and _http_status(record) is not None and 400 <= _http_status(record) < 500:
                continue
            unavailable(slot, observer=slot in {"A0", "A1", "B0", "B1", "B2"}, rejection=family == "repeat_rejected" and slot == "B_action2")
    required = ("A0", "A1", "B0", "B1", "B2") if family == "repeat_equal" else ("B0", "B1", "B2")
    complete = all(unavailable(slot, observer=True) is None for slot in required)
    status = "violated" if any(row["status"] == "violated" for row in checks) else "satisfied" if complete and all(row["status"] == "satisfied" for row in checks) else "not_evaluable"
    reason = None if status != "not_evaluable" else next((row["reason_code"] for row in checks if row["reason_code"]), "repeat_protocol_incomplete")
    return {"family": family, "status": status,
            "observed": {"checks": checks, "applicability": applicability, "diagnostics": diagnostics},
            "reason_code": reason}


def repeated_result_outcome(result: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    """Shared M12/M14 outcome precedence for a freshly evaluated V5 result."""
    if result["status"] == "violated":
        return "refuted", None, None
    if result["status"] == "satisfied":
        return "validated", "repeated_execution_confirmed", None
    failures = [row["failure_class"] for row in result["observed"]["diagnostics"]]
    for failure in ("setup_failure", "request_transport_failure", "observer_failure"):
        if failure in failures:
            return "infrastructure_failed", None, failure
    return "not_evaluable", None, "settle_timeout" if "settle_timeout" in failures else "binding"


def execute_repeated_execution(material: Any, runtime: Any, *,
                               artifact_writer: Callable[[str, bytes], None],
                               output_level: str) -> tuple[RepeatedCollectedEvidence, dict[str, Any], dict[str, Any]]:
    """Execute the fixed once/twice or twice-only plan without result selection."""
    del artifact_writer, output_level
    from ..current_http_runtime import (
        BaselineRequestShapeLossError,
        RelationExecutionError,
        ResourceRebindingError,
        UnresolvedRequestMaterialError,
        _is_candidate_local_slot_error,
    )
    errors = (OSError, BaselineRequestShapeLossError, RelationExecutionError,
              ResourceRebindingError, UnresolvedRequestMaterialError)
    artifacts = dict(material.artifact_bytes)
    predicate = copy.deepcopy(material.candidate["primary_predicate"])
    family = predicate["family"]
    if family not in CHECKS:
        raise ValueError("unsupported repetition predicate")
    records: dict[str, Any] = {}

    def invoke(slot: str, call: Callable[[], Any], *, prepared: bool = False) -> bool:
        try:
            returned = call()
        except errors as error:
            if not isinstance(error, OSError) and not _is_candidate_local_slot_error(error):
                raise
            record, rows = {"state": "not_executed", "status": "failed", "reason_code": type(error).__name__}, {}
        else:
            record, rows = (returned, {}) if prepared else returned
        artifacts.update(rows)
        if prepared:
            record = {key: copy.deepcopy(record[key]) for key in ("state", "status", "logical_request", "redaction_manifest", "reset_epoch", "checkpoint_id", "reason_code") if key in record}
            record.setdefault("state", "executed")
            record.setdefault("status", "pass")
        records[slot] = copy.deepcopy(record)
        return _executed(record)

    arms = (("A", "repeat_once", 1), ("B", "repeat_twice", 2)) if family == "repeat_equal" else (("B", "repeat_twice", 2),)
    for prefix, arm, occurrences in arms:
        try:
            context, reset, rows = runtime.begin_arm(material, arm)
        except errors as error:
            if not isinstance(error, OSError) and not _is_candidate_local_slot_error(error):
                raise
            records[f"{prefix}_reset"] = {"state": "not_executed", "status": "failed", "reason_code": type(error).__name__}
            continue
        artifacts.update(rows)
        records[f"{prefix}_reset"] = copy.deepcopy(reset)
        if not _executed(reset):
            continue
        if not invoke(f"{prefix}_setup", partial(runtime.execute_setup, context, f"{prefix}_setup")):
            continue
        if not invoke(f"{prefix}0", partial(runtime.observe, context, f"{prefix}0")):
            continue
        before_status = _http_status(records[f"{prefix}0"], observer=True)
        if before_status is None or not 200 <= before_status < 300 or not route_observer_is_pure(records[f"{prefix}0"]):
            continue
        if not invoke(f"{prefix}_prepare", partial(runtime.prepare_producer, context), prepared=True):
            continue
        for occurrence in range(1, occurrences + 1):
            action_slot = f"{prefix}_action{occurrence}"
            method = runtime.execute_negative_producer if family == "repeat_rejected" and occurrence == 2 else runtime.execute_producer
            if not invoke(action_slot, partial(method, context, occurrence_index=occurrence, repeated=True)):
                break
            status = _http_status(records[action_slot])
            valid_status = status is not None and (200 <= status < 300 or family == "repeat_rejected" and occurrence == 2 and 400 <= status < 500)
            if not valid_status or records[action_slot].get("request_identity_verified") is not True:
                break
            checkpoint = f"{prefix}{occurrence}"
            if not invoke(checkpoint, partial(runtime.observe, context, checkpoint)):
                break
            after_status = _http_status(records[checkpoint], observer=True)
            if after_status is None or not 200 <= after_status < 300 or not route_observer_is_pure(records[checkpoint]):
                break
            if family == "repeat_rejected" and occurrence == 1:
                first_result = evaluate_repeated_result(predicate, records)
                if first_result["observed"]["applicability"][0]["status"] != "satisfied":
                    break

    evaluated = evaluate_repeated_result(predicate, records)
    verdict, claim, failure = repeated_result_outcome(evaluated)
    shape = copy.deepcopy(material.execution_material["protocol_shape"])
    evidence = {"schema_version": "uisemtest-current-v5-execution-evidence-v1",
                "candidate": copy.deepcopy(material.candidate), "repeated_plan": shape["repeated_plan"],
                "protocol": records, "sessions": runtime.sessions()}
    result = {"schema_version": "uisemtest-current-protocol-result-v1", "candidate_id": material.candidate_id,
              "protocol_kind": "V5", "protocol_verdict": verdict, "claim_kind": claim,
              "predicate_result": evaluated, "failure_class": failure,
              "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json",
              "certificate_ref": f"M12/{material.candidate_id}/certificate.json", "v1_legacy_outcome": None}
    certificate = {"schema_version": "uisemtest-current-v5-certificate-v1", "candidate_id": material.candidate_id,
                   "protocol_kind": "V5", "protocol_verdict": verdict, "claim_kind": claim,
                   "predicate_result": copy.deepcopy(evaluated), "failure_class": failure,
                   "repeated_plan": shape["repeated_plan"]}
    collected = RepeatedCollectedEvidence(evidence, canonical_json_bytes(evidence), {}, artifacts, (), (),
                                         runtime.counts(), tuple(getattr(runtime, "sensitive_values_in_memory", lambda: ())()))
    return collected, certificate, result
