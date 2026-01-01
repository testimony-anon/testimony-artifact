"""Stage6 execution and normal-state calibration for certified relations."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections import Counter
from functools import partial
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import unquote

from ui_semantics.dsl import (
    copy_numeric_sources, request_numeric_observation,
    evaluate_predicate, evaluate_predicate_result, evaluate_workflow_applicability,
    is_workflow_effect_predicate, merge_followup_observation,
)
from ui_semantics.current_settle import poll_semantic_stability
from ui_semantics.relation_phase_b import canonical_sha256, validate_certified_relation_tests
from ui_semantics.current_route_s import (
    binding_scope_id,
    empty_object_no_body_shape_compatible,
    evaluate_pair,
    validate_proven_path_change,
)
from stage6_ground.resource_rebinding import (
    _coerce_to_proof_scalar_type,
    extract_typed_value,
    scalar_sha256,
)
from ui_semantics.route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    predicate_value_refs,
    reject_redacted_predicate_dependencies,
    typed_redaction_sentinel_attested,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
IN_MEMORY_PREDICATE_EVALUATOR = "stage6_ground.relation_test_execution._evaluate_in_memory_predicate"


class CertifiedRelationRuntime(Protocol):
    """Request-reference runtime supplied by a subject adapter."""

    def begin_arm(self, candidate_id: str, arm: str) -> tuple[Any, dict[str, Any]]: ...

    def execute_setup(
        self,
        context: Any,
        setup: list[dict[str, str]],
    ) -> list[dict[str, Any]]: ...

    def execute(
        self,
        context: Any,
        endpoint: dict[str, str],
        *, step_id: str | None = None, occurrence_index: int | None = None,
        repeated: bool = False,
    ) -> dict[str, Any]: ...

    def prepare_producer(self, context: Any) -> dict[str, Any]: ...

    def verify_identity_topology(self, context: Any, topology: Mapping[str, Any]) -> bool: ...

    def verify_negative_session_boundary(
        self,
        context: Any,
        boundary: Mapping[str, Any],
    ) -> bool: ...

    def snapshot(self, context: Any, actor_id: str) -> dict[str, str | None]: ...

    def settle_monotonic_ns(self) -> int: ...

    def settle_sleep(self, seconds: float) -> None: ...

    def record_settle(self) -> None: ...


class RelationExecutionError(RuntimeError):
    """The generated suite or runtime result violates Stage6 invariants."""


def calibration_arm_for_protocol(protocol_kind: str) -> str:
    try:
        return {
            "V1": "treatment",
            "V2": "single_state",
            "V9": "multi_resource",
            "V8": "temporal",
            "V3": "metamorphic_query",
            "V4": "workflow",
            "V5": "repeat_twice",
            "V6": "negative_no_effect",
            "V7": "actor_matrix",
        }[protocol_kind]
    except KeyError as error:
        raise RelationExecutionError("calibration_protocol_kind_unknown") from error


def execute_certified_relation_suite(
    suite: Mapping[str, Any],
    runtime: CertifiedRelationRuntime,
    *,
    mode: str,
    is_candidate_local_error: Callable[[BaseException], bool],
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Traverse every eligible frozen test once, with globally fresh reset epochs."""

    validate_certified_relation_tests(suite)
    results: list[dict[str, Any]] = []
    reset_epochs: set[str] = set()
    for test in suite["tests"]:
        if not test["eligible"]:
            continue
        result = execute_certified_relation_test(
            test,
            runtime,
            mode=mode,
            is_candidate_local_error=is_candidate_local_error,
        )
        for run in result["runs"]:
            reset_refs = run.get("reset_refs", [run.get("reset_ref") or {}])
            if not reset_refs and run.get("mechanical_status") == "complete":
                raise RelationExecutionError("completed_run_reset_epoch_missing")
            for reset_ref in reset_refs:
                reset_epoch = reset_ref.get("record_id")
                if reset_epoch is None:
                    if run.get("mechanical_status") == "complete":
                        raise RelationExecutionError("completed_run_reset_epoch_missing")
                    continue
                if not isinstance(reset_epoch, str) or not reset_epoch:
                    raise RelationExecutionError("run_reset_epoch_invalid")
                if reset_epoch in reset_epochs:
                    raise RelationExecutionError("cross_test_reset_epoch_reused")
                reset_epochs.add(reset_epoch)
        if on_result is not None:
            on_result(result)
        results.append(result)
    return results


def execute_certified_relation_test(
    test: Mapping[str, Any],
    runtime: CertifiedRelationRuntime,
    *,
    mode: str,
    is_candidate_local_error: Callable[[BaseException], bool],
) -> dict[str, Any]:
    """Execute all frozen normal runs for one relation test.

    Rehearsal output intentionally omits assertion evaluation and verdicts.  A
    qualifying execution evaluates the exact frozen definitions and retains
    every normal run so calibration is independently replayable.
    """

    if mode not in {"rehearsal", "qualifying-formal"}:
        raise ValueError("unsupported relation test mode")
    if not test.get("eligible"):
        raise RelationExecutionError("ineligible_test_reached_stage6")
    runs = []
    for run_index in range(int(test["normal_runs"])):
        runs.append(
            _execute_once(
                test,
                runtime,
                mode=mode,
                run_index=run_index,
                is_candidate_local_error=is_candidate_local_error,
            )
        )
    if mode == "rehearsal":
        return {
            "test_id": test["test_id"],
            "candidate_id": test["candidate_id"],
            "mechanical_status": (
                "complete"
                if all(run["mechanical_status"] == "complete" for run in runs)
                else "candidate_local_incomplete"
            ),
            "normal_runs_planned": test["normal_runs"],
            "normal_runs_completed": sum(run["mechanical_status"] == "complete" for run in runs),
            "business_outcomes_evaluated": False,
            "business_outcomes_persisted": False,
            "runs": runs,
        }
    assertion_calibration = _calibrate_assertions(test, runs)
    pass_count = sum(_normal_run_passed(test, run) for run in runs)
    if (test["protocol_kind"] in {"V2", "V3", "V5", "V6", "V7", "V8", "V9"} or is_workflow_effect_test(test)) and any(item["status"] == "fail" for item in assertion_calibration):
        # A failed check over the valid fresh response remains a counterexample
        # when a separate generic check lacks an operand.
        final_status = "normal_fail"
    elif any(item["status"] == "inconclusive" for item in assertion_calibration):
        final_status = "normal_inconclusive"
    elif any(item["status"] == "fail" for item in assertion_calibration):
        final_status = "normal_fail"
    else:
        final_status = "normal_pass"
    reason = next(
        (
            run["reason_code"]
            for run in runs
            if run["mechanical_status"] != "complete"
        ),
        None,
    )
    return {
        "test_id": test["test_id"],
        "candidate_id": test["candidate_id"],
        "final_status": final_status,
        "reason_code": reason,
        "normal_runs": test["normal_runs"],
        "normal_runs_planned": test["normal_runs"],
        "normal_runs_completed": sum(run["mechanical_status"] == "complete" for run in runs),
        "pass_count": pass_count,
        "source": copy.deepcopy(test["source"]),
        "assertion_calibration": assertion_calibration,
        "runs": runs,
    }


def _normal_run_passed(test: Mapping[str, Any], run: Mapping[str, Any]) -> bool:
    if run.get("mechanical_status") != "complete":
        return False
    results = run.get("assertion_results")
    if not isinstance(results, list):
        return False
    expected_ids = [row["assertion_id"] for row in test["assertions"]]
    return (
        [row.get("assertion_id") for row in results] == expected_ids
        and all(row.get("verdict") == "passed" for row in results)
    )


def build_calibration_summary(
    suite: Mapping[str, Any],
    results: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build separate candidate, test, definition, and evaluation denominators."""

    validate_certified_relation_tests(suite)
    tests = suite["tests"]
    result_by_test = {row["test_id"]: row for row in results}
    if len(result_by_test) != len(results):
        raise RelationExecutionError("duplicate_test_result")
    statuses = Counter()
    assertion_statuses = Counter()
    assertion_class_statuses = Counter()
    evaluation_count = 0
    per_candidate = []
    for test in tests:
        result = result_by_test.get(test["test_id"])
        if result is None:
            if test["eligible"]:
                status = "not_run_due_run_fatal"
            elif test["constraint"]["reason"]:
                status = "conversion_dropped"
            else:
                status = "conversion_inconclusive"
            assertion_rows = []
        else:
            status = result["final_status"]
            assertion_rows = result["assertion_calibration"]
            evaluation_count += sum(
                len(run.get("assertion_results", [])) for run in result.get("runs", [])
            )
        statuses[status] += 1
        for assertion in test["assertions"]:
            row = next(
                (item for item in assertion_rows if item["assertion_id"] == assertion["assertion_id"]),
                None,
            )
            assertion_status = row["status"] if row is not None else "not_run"
            assertion_statuses[assertion_status] += 1
            assertion_class_statuses[(assertion["assertion_class"], assertion_status)] += 1
        per_candidate.append(
            {
                "candidate_id": test["candidate_id"],
                "test_id": test["test_id"],
                "final_status": status,
                "normal_runs": result["normal_runs"] if result is not None else test["normal_runs"],
                "pass_count": result["pass_count"] if result is not None else 0,
                "source": copy.deepcopy(test["source"]),
                "blueprint_sha256": canonical_sha256(test["blueprint"]),
                "constraint_sha256": canonical_sha256(test["constraint"]),
                "test_definition_sha256": canonical_sha256(test),
                "business_assertion_ids": [
                    item["assertion_id"]
                    for item in test["assertions"]
                    if item["assertion_class"] == "business"
                ],
                "generic_assertion_ids": [
                    item["assertion_id"]
                    for item in test["assertions"]
                    if item["assertion_class"] == "generic"
                ],
                "assertion_calibration": copy.deepcopy(assertion_rows),
            }
        )
    assertion_definitions = [item for test in tests for item in test["assertions"]]
    return {
        "candidate_denominator": {
            "confirmed_input": suite["source_input"]["confirmed_count"],
            "blueprint_generated": len(tests),
            "constraint_complete": sum(test["constraint"]["status"] == "complete" for test in tests),
            "stage6_test_generated": len(tests),
            "executable_eligible": sum(test["eligible"] for test in tests),
            "normal_state_calibration_pass": statuses["normal_pass"],
            "normal_state_calibration_fail": statuses["normal_fail"],
            "normal_state_calibration_inconclusive": statuses["normal_inconclusive"],
            "not_run_due_run_fatal": statuses["not_run_due_run_fatal"],
            "conversion_dropped": statuses["conversion_dropped"],
            "conversion_inconclusive": statuses["conversion_inconclusive"],
        },
        "test_denominator": {
            "generated": len(tests),
            "eligible": sum(test["eligible"] for test in tests),
            "tests_with_business_assertion": sum(
                any(item["assertion_class"] == "business" for item in test["assertions"])
                for test in tests
            ),
        },
        "assertion_definition_denominator": {
            "total": len(assertion_definitions),
            "business": sum(item["assertion_class"] == "business" for item in assertion_definitions),
            "generic_status_schema": sum(item["assertion_class"] == "generic" for item in assertion_definitions),
        },
        "assertion_calibration": {
            "pass": assertion_statuses["pass"],
            "fail": assertion_statuses["fail"],
            "inconclusive": assertion_statuses["inconclusive"],
            "not_run": assertion_statuses["not_run"],
            "business": {
                "pass": assertion_class_statuses[("business", "pass")],
                "fail": assertion_class_statuses[("business", "fail")],
                "inconclusive": assertion_class_statuses[("business", "inconclusive")],
                "not_run": assertion_class_statuses[("business", "not_run")],
            },
            "generic_status_schema": {
                "pass": assertion_class_statuses[("generic", "pass")],
                "fail": assertion_class_statuses[("generic", "fail")],
                "inconclusive": assertion_class_statuses[("generic", "inconclusive")],
                "not_run": assertion_class_statuses[("generic", "not_run")],
            },
        },
        "assertion_evaluation_count": evaluation_count,
        "dropped_reasons": {},
        "inconclusive_reasons": dict(
            sorted(
                Counter(
                    row.get("reason_code") or "assertion_unable"
                    for row in results
                    if row.get("final_status") == "normal_inconclusive"
                ).items()
            )
        ),
        "per_candidate": per_candidate,
    }


def _fresh_primary_assertion_rows(
    test: Mapping[str, Any], evaluated: Mapping[str, Any] | None,
    observations: Mapping[str, Any], *, evaluator: str,
) -> list[dict[str, Any]]:
    """Project this run's common evaluator result into the frozen assertions."""
    rows = []
    for assertion in test["assertions"]:
        try:
            if assertion["assertion_class"] == "business":
                status = (evaluated or {}).get("status", "not_evaluable")
                passed = True if status == "satisfied" else False if status == "violated" else None
                detail = {
                    "observed": copy.deepcopy((evaluated or {}).get("observed", {})),
                    "reason_code": (evaluated or {}).get("reason_code", "protocol_execution_unavailable"),
                    "evaluator": evaluator,
                }
            else:
                passed, observed = evaluate_predicate(assertion["predicate"], observations)
                detail = _safe_detail(observed)
            verdict = "unable" if passed is None else "passed" if passed else "failed"
        except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
            verdict, detail = "unable", {"reason": _safe_error_code(error)}
        rows.append({
            **{key: copy.deepcopy(assertion[key]) for key in (
                "assertion_id", "assertion_class", "assertion_source", "predicate_type",
                "definition_sha256", "evidence_refs",
            )},
            "verdict": verdict, "detail": detail,
        })
    return rows


def _execute_negative_once(
    test: Mapping[str, Any], runtime: CertifiedRelationRuntime, *, mode: str,
    run_index: int, is_candidate_local_error: Callable[[BaseException], bool],
) -> dict[str, Any]:
    from ui_semantics.current_protocols.negative_no_effect import evaluate_negative_outcome

    started = time.monotonic_ns()
    blueprint = test["blueprint"]
    candidate_id, arm = test["candidate_id"], "negative_no_effect"
    preserve = blueprint["negative_kind"] == "rejection_preservation"
    predicate = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
    reset_ref: dict[str, Any] = {}
    setup = []
    values: dict[str, Any] = {}
    bindings: dict[str, Any] = {}
    step = "reset"
    failure_step = failure_reason = None
    reset_elapsed_ms = 0.0
    settle = None
    negative_boundary_closed = False
    try:
        context, reset_ref = runtime.begin_arm(candidate_id, arm)
        reset_elapsed_ms = (time.monotonic_ns() - started) / 1_000_000
        step = "setup"
        setup = runtime.execute_setup(context, list(blueprint["setup"]))
        hashes = _validate_setup_bindings(setup, candidate_id=candidate_id, arm=arm, reset_epoch=reset_ref["record_id"])
        step = "session_boundary"
        if blueprint.get("identity_topology") is not None and runtime.verify_identity_topology(context, blueprint["identity_topology"]) is not True:
            raise RelationExecutionError("negative_identity_topology_unclosed")
        negative_boundary_closed = runtime.verify_negative_session_boundary(context, blueprint["session_boundary"])
        if negative_boundary_closed is not True:
            raise RelationExecutionError("negative_session_boundary_unclosed")

        def read(phase: str) -> dict[str, Any]:
            endpoint = blueprint.get("before_observer", blueprint["observer"]) if phase == "before" else blueprint["observer"]
            left = runtime.snapshot(context, endpoint["actor_id"])
            value = runtime.execute(context, dict(endpoint))
            right = runtime.snapshot(context, endpoint["actor_id"])
            _validate_runtime_result(value, phase, endpoint)
            _require_workflow_step_success(value, phase)
            purity = _validate_observer_purity(left, right, blueprint["observer_purity_policy"]["domains"])
            bindings[phase] = _validate_endpoint_binding(
                value, endpoint, blueprint["observer_binding_requirement"][phase],
                candidate_id=candidate_id, arm=arm, reset_epoch=reset_ref["record_id"], creator_hashes=hashes,
            )
            values[phase] = value
            return {"state": "executed", "status": "pass", "response": _observation(value),
                    "runtime_observation": value, "observer_purity": purity}

        if preserve:
            step = "before"
            read("before")
            hashes = _validate_runtime_creator_captures(
                values["before"], blueprint.get("before_observer", blueprint["observer"]),
                blueprint["producer_binding_requirement"],
                candidate_id=candidate_id, arm=arm, reset_epoch=reset_ref["record_id"],
                creator_hashes=hashes, normalized_response=True,
            )
        step = "producer"
        value = runtime.execute(context, dict(blueprint["producer"]))
        _validate_runtime_result(value, step, blueprint["producer"])
        bindings["producer"] = _validate_producer_binding(
            value, blueprint["producer"], blueprint["producer_binding_requirement"],
            candidate_id=candidate_id, arm=arm, reset_epoch=reset_ref["record_id"], creator_hashes=hashes,
        )
        values["producer"] = value
        if not 200 <= value["status"] < 300 and not 400 <= value["status"] < 500:
            raise RelationExecutionError("negative_request_http_unavailable")
        if preserve:
            step = "settle"
            settle = poll_semantic_stability(
                blueprint["settle_policy"], lambda _index: read("after"),
                observer_is_pure=lambda row: row["observer_purity"]["status"] == "pass",
                monotonic_ns=runtime.settle_monotonic_ns, sleep=runtime.settle_sleep,
            )
            runtime.record_settle()
            if settle.status != "stable":
                failure_step, failure_reason = "settle", settle.status
    except BaseException as error:
        if not is_candidate_local_error(error) and not isinstance(error, RelationExecutionError):
            raise
        failure_step, failure_reason = step, _safe_error_code(error)
    record = _incomplete_run(run_index, started, failure_step or "execution", failure_reason or "unavailable", reset_ref=reset_ref, reset_elapsed_ms=reset_elapsed_ms)
    record.update({
        "mechanical_status": "candidate_local_incomplete" if failure_step else "complete",
        "reason_code": f"{failure_step}:{failure_reason}" if failure_step else None,
        "setup_count": len(setup),
        "setup_binding_event_count": sum(len(row.get("binding_events") or []) for row in setup),
        "negative_session_boundary_closed": negative_boundary_closed,
        "negative_kind": blueprint["negative_kind"], "endpoint_bindings": bindings,
        **{name: _step_summary(value, include_semantic_evidence=mode != "rehearsal") for name, value in values.items()},
        "settle_elapsed_ns": int(settle.elapsed_ns) if settle else 0,
        "settle_poll_count": settle.poll_count if settle else 0,
        "elapsed_ms": (time.monotonic_ns() - started) / 1_000_000,
    })
    if mode == "rehearsal":
        record.update(business_outcomes_evaluated=False, business_outcomes_persisted=False)
        return record
    producer = values.get("producer")
    negative_producer = None if producer is None else copy_numeric_sources(producer, {
        "state": "executed", "status": "pass", "transport_status": producer["status"],
        **({"response": producer["body"]} if "body" in producer else {}),
        "request": producer.get("semantic_request_body"),
        "redaction_manifest": producer.get("redaction_manifest", {}),
    })
    def observed(phase: str) -> dict[str, Any] | None:
        value = values.get(phase)
        return None if value is None else {
            "state": "executed", "status": "pass", "response": _observation(value),
            "redaction_manifest": value.get("redaction_manifest", {}),
        }
    outcome = evaluate_negative_outcome(
        predicate, blueprint["rejection_detector"], negative_kind=blueprint["negative_kind"],
        before=observed("before"), producer=negative_producer, after=observed("after"),
        failed_step=failure_step, failure_reason=failure_reason,
    )
    observations = {name: _observation(value) for name, value in values.items()}
    if producer is not None:
        observations["producer_status"] = {"body": producer["status"]}
        observations["producer_response"] = _producer_observation(producer)
    if "after" in observations:
        observations["consumer"] = observations["after"]
    record["negative_diagnostics"] = copy.deepcopy(outcome["diagnostics"])
    record["assertion_results"] = _fresh_primary_assertion_rows(
        test, outcome["predicate_result"], observations,
        evaluator="ui_semantics.current_protocols.negative_no_effect.evaluate_negative_outcome",
    )
    return record


def _execute_repeated_once(
    test: Mapping[str, Any], runtime: CertifiedRelationRuntime, *, mode: str,
    run_index: int, is_candidate_local_error: Callable[[BaseException], bool],
) -> dict[str, Any]:
    from ui_semantics.current_protocols.repeated_execution import evaluate_repeated_result

    started = time.monotonic_ns()
    blueprint = test["blueprint"]
    predicate = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
    arms = ["repeat_once", "repeat_twice"] if predicate["family"] == "repeat_equal" else ["repeat_twice"]
    if blueprint["reset_epochs"] != arms or blueprint["repetition_kind"] != predicate["family"]:
        raise RelationExecutionError("repeated_frozen_plan_drift")
    records: dict[str, Any] = {}
    values: dict[str, Any] = {}
    resets = []
    setup_count = setup_bindings = 0
    reset_elapsed_ms = 0.0
    failures = []
    for arm in arms:
        prefix = "A" if arm == "repeat_once" else "B"
        slot = f"{prefix}_reset"
        context = None
        try:
            reset_start = time.monotonic_ns()
            context, reset_ref = runtime.begin_arm(test["candidate_id"], arm)
            reset_elapsed_ms += (time.monotonic_ns() - reset_start) / 1_000_000
            resets.append(_safe_reset_ref(reset_ref))
            epoch = reset_ref["record_id"]
            records[slot] = {"state": "executed", "status": "pass", "reset_epoch": epoch}
            slot = f"{prefix}_setup"
            setup = runtime.execute_setup(context, list(blueprint["setup"]))
            setup_count += len(setup)
            setup_bindings += sum(len(row.get("binding_events") or []) for row in setup)
            hashes = _validate_setup_bindings(setup, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch)
            records[slot] = {"state": "executed", "status": "pass", "reset_epoch": epoch}
            prepared = False
            prior: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
            steps = [row for row in blueprint["execution_steps"] if row["reset_epoch"] == arm]
            expected_slots = [f"{prefix}0", f"{prefix}_action1", f"{prefix}1"]
            if arm == "repeat_twice":
                expected_slots += [f"{prefix}_action2", f"{prefix}2"]
            if [row["step_id"] for row in steps] != expected_slots:
                raise RelationExecutionError("repeated_checkpoint_sequence_drift")
            for step in steps:
                slot = step["step_id"]
                endpoint, requirement = step["endpoint"], step["binding_requirement"]
                for prior_endpoint, prior_result in prior:
                    events = [event for event in requirement["events"]
                              if event.get("creator_actor_id") == prior_endpoint["actor_id"]
                              and event.get("creator_request_ref") == prior_endpoint["request_ref"]
                              and event.get("source_id") not in hashes]
                    if events:
                        hashes = _validate_runtime_creator_captures(
                            prior_result, prior_endpoint, {"events": events},
                            candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch,
                            creator_hashes=hashes, normalized_response=True,
                        )
                if step["kind"] == "request" and not prepared:
                    slot = f"{prefix}_prepare"
                    preparation = runtime.prepare_producer(context)
                    records[slot] = {
                        **{key: copy.deepcopy(preparation[key]) for key in (
                            "logical_request", "redaction_manifest",
                        ) if key in preparation},
                        "state": "executed", "status": "pass",
                        "reset_epoch": epoch, "checkpoint_id": slot,
                    }
                    prepared, slot = True, step["step_id"]
                if step["kind"] == "observe":
                    left = runtime.snapshot(context, endpoint["actor_id"])
                result = runtime.execute(
                    context, dict(endpoint), step_id=slot,
                    occurrence_index=step["occurrence_index"], repeated=step["kind"] == "request",
                )
                _validate_runtime_result(result, slot, endpoint)
                _validate_endpoint_binding(result, endpoint, requirement, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch, creator_hashes=hashes)
                values[slot] = result
                common = {"state": "executed", "status": "pass", "reset_epoch": epoch,
                          "checkpoint_id": slot, "redaction_manifest": result.get("redaction_manifest", {})}
                if step["kind"] == "observe":
                    right = runtime.snapshot(context, endpoint["actor_id"])
                    _require_workflow_step_success(result, slot)
                    _validate_observer_purity(left, right, blueprint["observer_purity_policy"]["domains"])
                    records[slot] = {**common, "response": _observation(result), "observer_domains": [
                        {"domain": domain, "disposition": "proven_unchanged", "before_sha256": left[domain],
                         "after_sha256": right[domain], "mutation_events": [], "uncertain_fields": []}
                        for domain in blueprint["observer_purity_policy"]["domains"]
                    ]}
                else:
                    records[slot] = copy_numeric_sources(result, {
                        **common, "request": copy.deepcopy(result.get("semantic_request_body")),
                        "response": copy.deepcopy(result.get("body")), "transport_status": result["status"],
                        "occurrence_index": step["occurrence_index"],
                        "request_identity_verified": result.get("request_identity_verified") is True,
                    })
                    if result.get("request_identity_verified") is not True:
                        raise RelationExecutionError("repeated_request_identity_unverified")
                    if not (200 <= result["status"] < 300 or predicate["family"] == "repeat_rejected" and 400 <= result["status"] < 500):
                        raise RelationExecutionError("repeated_action_response_unavailable")
                    if predicate["family"] == "repeat_rejected" and step["occurrence_index"] == 1 and not 200 <= result["status"] < 300:
                        break
                prior.append((endpoint, result))
                if predicate["family"] == "repeat_rejected" and slot == "B1":
                    first_result = evaluate_repeated_result(predicate, records)
                    if first_result["observed"]["applicability"][0]["status"] != "satisfied":
                        break
        except BaseException as error:
            if not is_candidate_local_error(error) and not isinstance(error, RelationExecutionError):
                raise
            records[slot] = {"state": "not_executed", "status": "failed", "reason_code": _safe_error_code(error)}
            failures.append({"checkpoint_id": slot, "reason_code": _safe_error_code(error)})
    planned_slots = [row["step_id"] for row in blueprint["execution_steps"]]
    complete = not failures and all(slot in values for slot in planned_slots)
    record = _incomplete_run(run_index, started, "repeated_execution", "incomplete", reset_ref=resets[0] if resets else {}, reset_elapsed_ms=reset_elapsed_ms)
    record.update({
        "reset_refs": resets, "setup_count": setup_count, "setup_binding_event_count": setup_bindings,
        "mechanical_status": "complete" if complete else "candidate_local_incomplete",
        "reason_code": None if complete else f"repeated_execution:{failures[0]['reason_code'] if failures else 'prerequisite_unavailable'}",
        "steps": {slot: _step_summary(value, include_semantic_evidence=mode != "rehearsal") for slot, value in values.items()},
        "repeated_diagnostics": failures, "settle_elapsed_ns": 0,
        "elapsed_ms": (time.monotonic_ns() - started) / 1_000_000,
    })
    if mode == "rehearsal":
        record.update(business_outcomes_evaluated=False, business_outcomes_persisted=False)
        return record
    evaluated = evaluate_repeated_result(predicate, records)
    observations = {slot: _observation(value) for slot, value in values.items()}
    for role, slot in {"before": "B0", "after": "B2", "producer": "B_action2", "consumer": "B2"}.items():
        if slot in observations:
            observations[role] = observations[slot]
    record["assertion_results"] = _fresh_primary_assertion_rows(
        test, evaluated, observations,
        evaluator="ui_semantics.current_protocols.repeated_execution.evaluate_repeated_result",
    )
    return record


def _close_prior_captures(history, requirement, hashes, *, candidate_id, arm, reset_epoch):
    """Use only an exact earlier source already executed in this finite plan."""
    for event in requirement["events"]:
        if event["source_id"] in hashes:
            continue
        matches = [(endpoint, value) for endpoint, value in history
                   if endpoint["request_ref"] == event["creator_request_ref"] and endpoint["actor_id"] == event["creator_actor_id"]]
        if len(matches) != 1:
            raise RelationExecutionError("runtime_creator_requirement_invalid")
        endpoint, value = matches[0]
        hashes = _validate_runtime_creator_captures(value, endpoint, {"events": [event]},
            candidate_id=candidate_id, arm=arm, reset_epoch=reset_epoch, creator_hashes=hashes)
    return hashes


def _execute_joint_once(test: Mapping[str, Any], runtime: CertifiedRelationRuntime, *, mode: str,
                        run_index: int, is_candidate_local_error: Callable[[BaseException], bool]) -> dict[str, Any]:
    from ui_semantics.current_protocols.multi_resource import evaluate_multi_resource_result

    started = time.monotonic_ns()
    blueprint, arm = test["blueprint"], "multi_resource"
    predicate = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
    reset_ref, values, observations, failures = {}, {}, [], []
    setup_rows = []
    history = []
    slot = "reset"
    try:
        context, reset_ref = runtime.begin_arm(test["candidate_id"], arm)
        epoch = reset_ref["record_id"]
        slot = "setup"
        setup_rows = runtime.execute_setup(context, blueprint["setup"])
        hashes = _validate_setup_bindings(setup_rows, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch)
        action_sent = False
        for step in blueprint["observation_plan"]:
            if step["phase"] == "after" and blueprint["producer"] is not None and not action_sent:
                slot = "producer"
                endpoint = blueprint["producer"]
                value = runtime.execute(context, dict(endpoint))
                _validate_runtime_result(value, slot, endpoint)
                hashes = _close_prior_captures(history, blueprint["producer_binding_requirement"], hashes, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch)
                _validate_endpoint_binding(value, endpoint, blueprint["producer_binding_requirement"], candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch, creator_hashes=hashes)
                _require_workflow_step_success(value, slot)
                values[slot], action_sent = value, True
                history.append((endpoint, value))
            slot, endpoint = step["role"], step["endpoint"]
            left = runtime.snapshot(context, endpoint["actor_id"])
            value = runtime.execute(context, dict(endpoint), step_id=slot)
            right = runtime.snapshot(context, endpoint["actor_id"])
            _validate_runtime_result(value, slot, endpoint)
            hashes = _close_prior_captures(history, step["binding_requirement"], hashes, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch)
            _validate_endpoint_binding(value, endpoint, step["binding_requirement"], candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch, creator_hashes=hashes)
            _require_workflow_step_success(value, slot)
            _validate_observer_purity(left, right, blueprint["observer_purity_policy"]["domains"])
            values[slot] = value
            history.append((endpoint, value))
            observations.append({"state": "executed", "status": "pass", "actor_id": endpoint["actor_id"], "request_ref": endpoint["request_ref"],
                "response": _observation(value), "request": copy.deepcopy(value.get("semantic_request_body")),
                "physical_transport_request": copy.deepcopy(value.get("physical_transport_request", value["transport_request"])),
                "physical_transport_metadata": copy.deepcopy(value.get("physical_transport_metadata", value.get("transport_metadata", {}))),
                "query": copy.deepcopy(value.get("physical_transport_metadata", value.get("transport_metadata", {})).get("query", {})),
                "method": endpoint["method"], "path": value.get("physical_transport_request", value["transport_request"])["path"],
                "redaction_manifest": value.get("redaction_manifest", {}),
                "observer_domains": [{"domain": domain, "disposition": "proven_unchanged", "before_sha256": left[domain], "after_sha256": right[domain], "mutation_events": [], "uncertain_fields": []} for domain in blueprint["observer_purity_policy"]["domains"]]})
    except BaseException as error:
        if not is_candidate_local_error(error) and not isinstance(error, RelationExecutionError):
            raise
        failures.append({"checkpoint_id": slot, "reason_code": _safe_error_code(error)})
    complete = not failures and len(observations) == len(blueprint["observation_plan"])
    record = _incomplete_run(run_index, started, "multi_resource", "incomplete", reset_ref=reset_ref, reset_elapsed_ms=0.0)
    record.update(mechanical_status="complete" if complete else "candidate_local_incomplete", reason_code=None if complete else "joint_observation_plan_incomplete",
        setup_count=len(setup_rows), setup_binding_event_count=sum(len(row.get("binding_events", [])) for row in setup_rows), settle_elapsed_ns=0,
        joint_observations=[_step_summary(value, include_semantic_evidence=mode != "rehearsal") for key, value in values.items() if key != "producer"], joint_diagnostics=failures)
    if mode == "rehearsal":
        record.update(business_outcomes_evaluated=False, business_outcomes_persisted=False)
        return record
    evaluated = evaluate_multi_resource_result(predicate, blueprint["joint_observation"], blueprint["observation_plan"],
        {"observations": observations, "complete": complete, "identity_verified": complete, "diagnostics": failures})
    record["assertion_results"] = _fresh_primary_assertion_rows(test, evaluated, {role: _observation(value) for role, value in values.items()}, evaluator="ui_semantics.current_protocols.multi_resource.evaluate_multi_resource_result")
    return record


def _execute_temporal_once(test: Mapping[str, Any], runtime: CertifiedRelationRuntime, *, mode: str,
                           run_index: int, is_candidate_local_error: Callable[[BaseException], bool]) -> dict[str, Any]:
    from ui_semantics.current_protocols.temporal import (
        evaluate_temporal_result, resolve_temporal_requirement, temporal_send_offsets, temporal_predicate_result,
    )

    started = time.monotonic_ns()
    blueprint, arm = test["blueprint"], "temporal"
    predicate = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
    reset_ref, setup_rows, history, samples, failures = {}, [], [], [], []
    requirement, action, identity, slot = None, {}, False, "reset"
    try:
        context, reset_ref = runtime.begin_arm(test["candidate_id"], arm)
        epoch = reset_ref["record_id"]
        slot = "setup"
        setup_rows = runtime.execute_setup(context, blueprint["setup"])
        hashes = _validate_setup_bindings(setup_rows, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch)

        def execute(endpoint: Mapping[str, Any], binding: Mapping[str, Any], checkpoint: str, *, observe: bool):
            nonlocal hashes
            left = runtime.snapshot(context, endpoint["actor_id"]) if observe else None
            value = runtime.execute(context, dict(endpoint), step_id=checkpoint)
            _validate_runtime_result(value, checkpoint, endpoint)
            hashes = _close_prior_captures(history, binding, hashes, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch)
            _validate_endpoint_binding(value, endpoint, binding, candidate_id=test["candidate_id"], arm=arm, reset_epoch=epoch, creator_hashes=hashes)
            accepted_absence = observe and predicate.get("family") == "P01" and value["status"] in predicate.get("absent_statuses", [])
            accepted_status = observe and predicate.get("family") == "P02" and predicate.get("left", {}).get("role") == "after_status" and 400 <= value["status"] < 500
            if not accepted_absence and not accepted_status:
                _require_workflow_step_success(value, checkpoint)
            if observe:
                _validate_observer_purity(left, runtime.snapshot(context, endpoint["actor_id"]), blueprint["observer_purity_policy"]["domains"])
            history.append((endpoint, value))
            return value

        if blueprint.get("before_observer") is not None:
            slot = "workflow_before"
            execute(blueprint["before_observer"], blueprint["observer_binding_requirement"]["before"], slot, observe=True)
        slot = "P"
        value = execute(blueprint["producer"], blueprint["producer_binding_requirement"], slot, observe=False)
        action = copy_numeric_sources(value, {"state": "executed", "status": "pass", "transport_status": value["status"],
            "request": copy.deepcopy(value.get("semantic_request_body")), "response": copy.deepcopy(value.get("body")),
            "request_fields": {**value.get("physical_transport_request", value["transport_request"]),
                               "query": value.get("physical_transport_metadata", {}).get("query", {}),
                               "headers": value.get("physical_transport_metadata", {}).get("request_headers", {})},
            "redaction_manifest": value.get("redaction_manifest", {}), "timing": value.get("timing", {})})
        requirement = resolve_temporal_requirement(blueprint["time_requirement"], action)
        offsets = temporal_send_offsets(requirement)
        if [row["role"] for row in blueprint["observation_plan"]] != [f"D{i + 1}" for i in range(len(offsets))]:
            raise RelationExecutionError("temporal_observation_plan_drift")
        origin = action["timing"]["send_ns" if requirement["origin"] == "send" else "receive_ns"]
        identity = (runtime.verify_identity_topology(context, blueprint["identity_topology"])
                    if blueprint.get("identity_topology") is not None else True)
        for step, offset in zip(blueprint["observation_plan"], offsets):
            slot = step["role"]
            runtime.temporal_wait_until(context, origin + offset)
            value = execute(step["endpoint"], step["binding_requirement"], slot, observe=True)
            samples.append({"state": "executed", "status": "pass", "checkpoint_id": slot,
                           "response": _observation(value), "timing": value.get("timing", {}),
                           "redaction_manifest": value.get("redaction_manifest", {})})
    except BaseException as error:
        if not is_candidate_local_error(error) and not isinstance(error, (RelationExecutionError, KeyError, TypeError, ValueError)):
            raise
        failures.append({"checkpoint_id": slot, "reason_code": _safe_error_code(error)})
    complete = not failures and len(samples) == len(blueprint["observation_plan"])
    record = _incomplete_run(run_index, started, "temporal", "incomplete", reset_ref=reset_ref, reset_elapsed_ms=0.0)
    record.update(mechanical_status="complete" if complete else "candidate_local_incomplete", reason_code=None if complete else "temporal_plan_incomplete",
        setup_count=len(setup_rows), setup_binding_event_count=sum(len(row.get("binding_events", [])) for row in setup_rows), settle_elapsed_ns=0,
        temporal_observations=[_step_summary(value, include_semantic_evidence=mode != "rehearsal") for _, value in history], temporal_diagnostics=failures)
    if mode == "rehearsal":
        record.update(business_outcomes_evaluated=False, business_outcomes_persisted=False)
        return record
    evaluated = None
    if requirement is not None:
        raw = evaluate_temporal_result(predicate, requirement, {"producer": action, "observations": samples,
            "complete": complete, "identity_verified": identity, "diagnostics": failures})
        evaluated = temporal_predicate_result(predicate, raw)
    observation = samples[-1]["response"] if samples else {}
    generic_observations = {row["checkpoint_id"]: row["response"] for row in samples}
    generic_observations["producer"] = {"status": action.get("transport_status"), "body": action.get("response")}
    record["assertion_results"] = _fresh_primary_assertion_rows(test, evaluated,
        {**generic_observations, "after": observation, "after_status": {"body": observation.get("status")}, "producer_request": {"body": action.get("request")}, "producer_response": {"body": action.get("response")}},
        evaluator="ui_semantics.current_protocols.temporal.evaluate_temporal_result")
    return record


def _execute_once(
    test: Mapping[str, Any],
    runtime: CertifiedRelationRuntime,
    *,
    mode: str,
    run_index: int,
    is_candidate_local_error: Callable[[BaseException], bool],
) -> dict[str, Any]:
    if test["protocol_kind"] == "V8":
        return _execute_temporal_once(test, runtime, mode=mode, run_index=run_index, is_candidate_local_error=is_candidate_local_error)
    if test["protocol_kind"] == "V9":
        return _execute_joint_once(test, runtime, mode=mode, run_index=run_index, is_candidate_local_error=is_candidate_local_error)
    if test["protocol_kind"] == "V6":
        return _execute_negative_once(
            test, runtime, mode=mode, run_index=run_index,
            is_candidate_local_error=is_candidate_local_error,
        )
    if test["protocol_kind"] == "V5":
        return _execute_repeated_once(
            test, runtime, mode=mode, run_index=run_index,
            is_candidate_local_error=is_candidate_local_error,
        )
    candidate_id = test["candidate_id"]
    arm = calibration_arm_for_protocol(str(test["protocol_kind"]))
    started = time.monotonic_ns()
    reset_started = time.monotonic_ns()
    try:
        context, reset_ref = runtime.begin_arm(candidate_id, arm)
    except BaseException as error:
        if is_candidate_local_error(error):
            return _incomplete_run(
                run_index,
                started,
                "candidate_local_begin",
                _safe_error_code(error),
                reset_elapsed_ms=(time.monotonic_ns() - reset_started) / 1_000_000,
            )
        raise
    reset_elapsed_ms = (time.monotonic_ns() - reset_started) / 1_000_000
    in_memory_business_result: tuple[bool, dict[str, bool]] | None = None
    use_in_memory_business_result = False
    applicability = None
    extra_steps: dict[str, Any] = {}
    try:
        blueprint = test["blueprint"]
        business_predicate = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
        single_state = test["protocol_kind"] == "V2"
        workflow_effect = is_workflow_effect_test(test)
        point_resource = business_predicate.get("family") == "P01" and business_predicate["target"]["value_type"] == "object"
        point_status = test["protocol_kind"] == "V7" and any(ref["role"] == "after_status" for ref in _canonical_value_refs(business_predicate))
        create_capture_read = (
            test["protocol_kind"] == "V4"
            and blueprint.get("workflow_kind") == "create_capture_read"
        )
        no_before_workflow = (
            test["protocol_kind"] == "V4"
            and blueprint.get("workflow_kind")
            in {"create_capture_read", "postcondition_read"}
        )
        before_observer = blueprint.get("before_observer", blueprint["observer"])
        if test["protocol_kind"] == "V7":
            before_actor = str(before_observer["actor_id"])
            after_actor = str(blueprint["observer"]["actor_id"])
            if before_actor != after_actor or before_observer.get("session_ref") != blueprint["observer"].get("session_ref"):
                raise RelationExecutionError("actor_matrix_target_actor_binding_invalid")
        setup = runtime.execute_setup(context, list(blueprint["setup"]))
        reset_epoch = reset_ref.get("record_id")
        creator_hashes = _validate_setup_bindings(
            setup,
            candidate_id=candidate_id,
            arm=arm,
            reset_epoch=reset_epoch,
        )
        if test["protocol_kind"] == "V7" and runtime.verify_identity_topology(context, blueprint["identity_topology"]) is not True:
            raise RelationExecutionError("actor_identity_topology_unclosed")
        query_results: dict[str, dict[str, Any]] | None = None
        if single_state:
            endpoint = blueprint["observer"]
            purity_left = runtime.snapshot(context, endpoint["actor_id"])
            after = runtime.execute(context, dict(endpoint))
            purity_right = runtime.snapshot(context, endpoint["actor_id"])
            _validate_runtime_result(after, "observation", endpoint)
            if type(after["status"]) is not int or not 200 <= after["status"] < 300:
                raise RelationExecutionError(
                    f"single_state_observer_unavailable:http_status:{after['status']}"
                )
            if "body" not in after:
                raise RelationExecutionError("single_state_observation_body_unavailable")
            try:
                after_purity = _validate_observer_purity(
                    purity_left, purity_right, blueprint["observer_purity_policy"]["domains"]
                )
            except RelationExecutionError as error:
                raise RelationExecutionError(f"single_state_observer_unavailable:{error}") from error
            after_binding = _validate_endpoint_binding(
                after, endpoint, blueprint["observer_binding_requirement"]["after"],
                candidate_id=candidate_id, arm=arm, reset_epoch=reset_epoch,
                creator_hashes=creator_hashes,
            )
            before = producer = None
            before_binding = producer_binding = {"status": "not_applicable", "reason_code": "single_state_has_no_action_or_before"}
            before_purity = copy.deepcopy(before_binding)
            settle_elapsed_ns = settle_poll_count = settle_consecutive_identical = 0
            settle_projection_sha256 = None
        elif test["protocol_kind"] == "V3":
            from ui_semantics.current_protocols.metamorphic_query import (
                evaluate_query_plan_predicate, query_request_observation,
            )
            query_results = {}
            query_failure = None
            query_bindings: dict[str, dict[str, Any]] = {}
            query_purity: dict[str, dict[str, Any]] = {}
            query_history: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for step in blueprint["query_plan"]:
                try:
                    role = str(step["role"])
                    endpoint = {
                        key: copy.deepcopy(step[key])
                        for key in (
                            "actor_id",
                            "request_ref",
                            "method",
                            "path",
                            "request_shape_sha256",
                        )
                    }
                    purity_left = runtime.snapshot(context, endpoint["actor_id"])
                    result = runtime.execute(context, endpoint)
                    purity_right = runtime.snapshot(context, endpoint["actor_id"])
                    query_purity[role] = _validate_observer_purity(
                        purity_left,
                        purity_right,
                        blueprint["observer_purity_policy"]["domains"],
                    )
                    _validate_runtime_result(result, role, endpoint)
                    if type(result.get("status")) is not int or not 200 <= result["status"] < 300 or "body" not in result:
                        raise RelationExecutionError("query_observer_response_unavailable")
                    requirement = blueprint["query_binding_requirements"][role]
                    unresolved_by_prior: dict[int, list[Mapping[str, Any]]] = {}
                    for event in requirement.get("events") or []:
                        source_id = str(event.get("source_id") or "")
                        if source_id in creator_hashes:
                            continue
                        matching_prior = [
                            index
                            for index, (prior_endpoint, _prior_result) in enumerate(
                                query_history
                            )
                            if event.get("creator_actor_id")
                            == prior_endpoint.get("actor_id")
                            and event.get("creator_request_ref")
                            == prior_endpoint.get("request_ref")
                        ]
                        if len(matching_prior) != 1:
                            raise RelationExecutionError(
                                "runtime_creator_requirement_invalid"
                            )
                        unresolved_by_prior.setdefault(matching_prior[0], []).append(event)
                    for prior_index, events in unresolved_by_prior.items():
                        prior_endpoint, prior_result = query_history[prior_index]
                        creator_hashes = _validate_runtime_creator_captures(
                            prior_result,
                            prior_endpoint,
                            {"events": events},
                            candidate_id=candidate_id,
                            arm=arm,
                            reset_epoch=reset_epoch,
                            creator_hashes=creator_hashes,
                            normalized_response=True,
                        )
                    query_bindings[role] = _validate_endpoint_binding(
                        result,
                        endpoint,
                        requirement,
                        candidate_id=candidate_id,
                        arm=arm,
                        reset_epoch=reset_epoch,
                        creator_hashes=creator_hashes,
                    )
                    query_results[role] = result
                    query_history.append((endpoint, result))
                except BaseException as error:
                    if not is_candidate_local_error(error) or not query_results:
                        raise
                    query_failure = {"role": str(step["role"]), "reason_code": _safe_error_code(error)}
                    break
            source_role = str(blueprint["query_plan"][0]["role"])
            after_role = next(reversed(query_results))
            before = query_results[source_role]
            producer = before
            after = query_results[after_role]
            before_binding = query_bindings[source_role]
            producer_binding = copy.deepcopy(before_binding)
            after_binding = query_bindings[after_role]
            before_purity = query_purity[source_role]
            after_purity = query_purity[after_role]
            settle_elapsed_ns = 0
            settle_poll_count = 0
            settle_consecutive_identical = 0
            settle_projection_sha256 = None
            query_observations = {role: _observation(value) for role, value in query_results.items()}
            query_sources = {role: ((value, "response"),) for role, value in query_results.items()}
            for role, value in query_results.items():
                query_observations[role + "_request"] = query_request_observation(value)
                query_sources[role + "_request"] = tuple(
                    (value, channel) for channel in ("request_query", "request", "request_headers", "request_path")
                )
            business_predicate = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
            query_evaluation, query_scope_complete, query_diagnostics = evaluate_query_plan_predicate(
                business_predicate, blueprint["query_plan"],
                blueprint["query_scope"],
                query_observations, query_sources,
                plan_complete=query_failure is None and len(query_results) == len(blueprint["query_plan"]),
                diagnostics=[query_failure] if query_failure is not None else [],
                evaluate_business=mode != "rehearsal",
                query_transform=blueprint["query_transform"],
                query_endpoints={step["role"]: step for step in blueprint["query_plan"]},
            )
        else:
            observer_actor = blueprint["observer"]["actor_id"]
            if no_before_workflow:
                before = None
                before_binding = {
                    "status": "not_applicable",
                    "reason_code": (
                        f"{blueprint['workflow_kind']}_has_no_before"
                    ),
                }
                before_purity = copy.deepcopy(before_binding)
            else:
                before_actor = before_observer["actor_id"]
                before_purity_left = runtime.snapshot(context, before_actor)
                before = runtime.execute(context, dict(before_observer))
                before_purity_right = runtime.snapshot(context, before_actor)
                before_purity = _validate_observer_purity(
                    before_purity_left,
                    before_purity_right,
                    blueprint["observer_purity_policy"]["domains"],
                )
                _validate_runtime_result(before, "before", before_observer)
                if workflow_effect and point_resource and business_predicate["operator"] == "absent":
                    if before["status"] not in business_predicate["absent_statuses"]:
                        _require_workflow_step_success(before, "before")
                    prerequisite = copy.deepcopy(business_predicate)
                    prerequisite["operator"] = "exists"
                    prerequisite["target"]["role"] = "before"
                    before_result = evaluate_predicate_result(
                        prerequisite, {"before": _observation(before)},
                        dependency_checker=partial(reject_redacted_predicate_dependencies, sources={"before": ((before, "response"),)}),
                    )
                    applicability = {
                        "status": "satisfied" if before_result["satisfied"] is True else "not_evaluable",
                        "observed": {"before_matches": before_result["satisfied"]},
                        "reason_code": None if before_result["satisfied"] is True else "delete_before_resource_not_established",
                    }
                    if applicability["status"] != "satisfied":
                        record = _incomplete_run(
                            run_index, started, "workflow_applicability", applicability["reason_code"],
                            reset_ref=reset_ref, reset_elapsed_ms=reset_elapsed_ms,
                        )
                        record.update(
                            setup_count=len(setup),
                            setup_binding_event_count=sum(len(item.get("binding_events") or []) for item in setup),
                            before=_step_summary(before, include_semantic_evidence=mode != "rehearsal"),
                            applicability=_safe_workflow_applicability(applicability),
                        )
                        return record
                creator_hashes = _validate_runtime_creator_captures(
                    before,
                    before_observer,
                    blueprint["producer_binding_requirement"],
                    candidate_id=candidate_id,
                    arm=arm,
                    reset_epoch=reset_epoch,
                    creator_hashes=creator_hashes,
                    normalized_response=True,
                )
                before_binding = _validate_endpoint_binding(
                    before,
                    before_observer,
                    blueprint["observer_binding_requirement"]["before"],
                    candidate_id=candidate_id,
                    arm=arm,
                    reset_epoch=reset_epoch,
                    creator_hashes=creator_hashes,
                )
            if workflow_effect and before is not None:
                _require_workflow_step_success(before, "before")
                business = next(row for row in test["assertions"] if row["assertion_class"] == "business")
                predicate = business["predicate"]
                if predicate["family"] == "P04":
                    applicability_observations = {"before": _observation(before)}
                    try:
                        reject_redacted_predicate_dependencies(predicate, {"before": ((before, "response"),)})
                        if any(ref["role"] == "producer_request" for ref in _canonical_value_refs(predicate)):
                            prepare = getattr(runtime, "prepare_producer", None)
                            if not callable(prepare):
                                raise RelationExecutionError("workflow_producer_request_unavailable")
                            prepared = prepare(context)
                            reject_redacted_predicate_dependencies(predicate, {"producer_request": tuple((prepared, channel) for channel in ("request", "request_query", "request_headers", "request_path"))})
                            applicability_observations["producer_request"] = request_numeric_observation(prepared, prepared["request"])
                        applicability = evaluate_workflow_applicability(predicate, applicability_observations)
                    except (SensitiveMaterialUnavailable, RelationExecutionError) as error:
                        applicability = {"status": "not_evaluable", "observed": {}, "reason_code": _safe_error_code(error)}
                if applicability is not None:
                    if applicability["status"] != "satisfied":
                        record = _incomplete_run(
                            run_index, started, "workflow_applicability", applicability["reason_code"],
                            reset_ref=reset_ref, reset_elapsed_ms=reset_elapsed_ms,
                        )
                        record.update({
                            "setup_count": len(setup),
                            "setup_binding_event_count": sum(len(item.get("binding_events") or []) for item in setup),
                            "before": _step_summary(before, include_semantic_evidence=mode == "qualifying-formal"),
                            "applicability": _safe_workflow_applicability(applicability),
                        })
                        return record
            producer = runtime.execute(context, dict(blueprint["producer"]))
            _validate_runtime_result(producer, "producer", blueprint["producer"])
            producer_binding = _validate_producer_binding(
                producer,
                blueprint["producer"],
                blueprint["producer_binding_requirement"],
                candidate_id=candidate_id,
                arm=arm,
                reset_epoch=reset_epoch,
                creator_hashes=creator_hashes,
            )
            if workflow_effect:
                _require_workflow_step_success(producer, "producer")
            if create_capture_read:
                creator_hashes = _validate_runtime_creator_captures(
                    producer,
                    blueprint["producer"],
                    blueprint["observer_binding_requirement"]["after"],
                    candidate_id=candidate_id,
                    arm=arm,
                    reset_epoch=reset_epoch,
                    creator_hashes=creator_hashes,
                    normalized_response=True,
                )
            if blueprint.get("workflow_kind") == "inverse_restoration":
                intermediate_endpoint = blueprint["intermediate_observer"]
                intermediate_requirement = blueprint["intermediate_binding_requirement"]
                creator_hashes = _validate_runtime_creator_captures(
                    producer, blueprint["producer"], intermediate_requirement,
                    candidate_id=candidate_id, arm=arm, reset_epoch=reset_epoch,
                    creator_hashes=creator_hashes, normalized_response=True,
                )
                purity_left = runtime.snapshot(context, intermediate_endpoint["actor_id"])
                intermediate = runtime.execute(context, dict(intermediate_endpoint), step_id="workflow_intermediate")
                purity_right = runtime.snapshot(context, intermediate_endpoint["actor_id"])
                _validate_runtime_result(intermediate, "workflow_intermediate", intermediate_endpoint)
                _require_workflow_step_success(intermediate, "workflow_intermediate")
                _validate_observer_purity(purity_left, purity_right, blueprint["observer_purity_policy"]["domains"])
                _validate_endpoint_binding(
                    intermediate, intermediate_endpoint, intermediate_requirement,
                    candidate_id=candidate_id, arm=arm, reset_epoch=reset_epoch, creator_hashes=creator_hashes,
                )
                inverse_requirement = blueprint["inverse_binding_requirement"]
                for source_endpoint, source_result in ((blueprint["producer"], producer), (intermediate_endpoint, intermediate)):
                    source_events = [event for event in inverse_requirement["events"]
                                     if event.get("creator_actor_id") == source_endpoint["actor_id"]
                                     and event.get("creator_request_ref") == source_endpoint["request_ref"]
                                     and event.get("source_id") not in creator_hashes]
                    if source_events:
                        creator_hashes = _validate_runtime_creator_captures(
                            source_result, source_endpoint, {"events": source_events},
                            candidate_id=candidate_id, arm=arm, reset_epoch=reset_epoch,
                            creator_hashes=creator_hashes, normalized_response=True,
                        )
                inverse = runtime.execute(context, dict(blueprint["inverse"]), step_id="inverse")
                _validate_runtime_result(inverse, "inverse", blueprint["inverse"])
                _require_workflow_step_success(inverse, "inverse")
                _validate_endpoint_binding(
                    inverse, blueprint["inverse"], inverse_requirement,
                    candidate_id=candidate_id, arm=arm, reset_epoch=reset_epoch, creator_hashes=creator_hashes,
                )
                for source_endpoint, source_result in ((blueprint["producer"], producer), (intermediate_endpoint, intermediate), (blueprint["inverse"], inverse)):
                    source_events = [event for event in blueprint["observer_binding_requirement"]["after"]["events"]
                                     if event.get("creator_actor_id") == source_endpoint["actor_id"]
                                     and event.get("creator_request_ref") == source_endpoint["request_ref"]
                                     and event.get("source_id") not in creator_hashes]
                    if source_events:
                        creator_hashes = _validate_runtime_creator_captures(
                            source_result, source_endpoint, {"events": source_events},
                            candidate_id=candidate_id, arm=arm, reset_epoch=reset_epoch,
                            creator_hashes=creator_hashes, normalized_response=True,
                        )
                extra_steps = {"workflow_intermediate": intermediate, "inverse": inverse}
            def poll_after(_poll_index: int) -> Mapping[str, Any]:
                purity_left = runtime.snapshot(context, observer_actor)
                observation = runtime.execute(context, dict(blueprint["observer"]))
                purity_right = runtime.snapshot(context, observer_actor)
                _validate_runtime_result(observation, "after", blueprint["observer"])
                declared_absence = point_resource and observation["status"] in business_predicate.get("absent_statuses", [])
                declared_rejection = point_status and type(observation["status"]) is int and 400 <= observation["status"] < 500
                if (workflow_effect or test["protocol_kind"] == "V7") and not (declared_absence or declared_rejection):
                    _require_workflow_step_success(observation, "after")
                purity = _validate_observer_purity(
                    purity_left,
                    purity_right,
                    blueprint["observer_purity_policy"]["domains"],
                )
                return {
                    "state": "executed",
                    "status": "pass",
                    "response": {
                        "status": observation["status"],
                        "body": copy.deepcopy(observation["body"]),
                    },
                    "runtime_observation": observation,
                    "observer_purity": purity,
                }

            settle = poll_semantic_stability(
                blueprint["settle_policy"],
                poll_after,
                observer_is_pure=lambda observation: observation.get(
                    "observer_purity", {}
                ).get("status")
                == "pass",
                monotonic_ns=runtime.settle_monotonic_ns,
                sleep=runtime.settle_sleep,
            )
            runtime.record_settle()
            if settle.status == "settle_timeout":
                record = _incomplete_run(
                    run_index,
                    started,
                    "candidate_local_execution",
                    "settle_timeout",
                    reset_ref=reset_ref,
                    reset_elapsed_ms=reset_elapsed_ms,
                )
                if applicability is not None:
                    record["applicability"] = _safe_workflow_applicability(applicability)
                    record["before"] = _step_summary(before, include_semantic_evidence=mode == "qualifying-formal")
                return record
            if settle.status != "stable" or settle.final_observation is None:
                raise RelationExecutionError(settle.status)
            settle_elapsed_ns = settle.elapsed_ns
            settle_poll_count = settle.poll_count
            settle_consecutive_identical = settle.consecutive_identical
            settle_projection_sha256 = settle.projection_sha256
            after = copy.deepcopy(settle.final_observation["runtime_observation"])
            after_purity = copy.deepcopy(settle.final_observation["observer_purity"])
            after_binding = _validate_endpoint_binding(
                after,
                blueprint["observer"],
                blueprint["observer_binding_requirement"]["after"],
                candidate_id=candidate_id,
                arm=arm,
                reset_epoch=reset_epoch,
                creator_hashes=creator_hashes,
            )
            if no_before_workflow:
                business = next(
                    item
                    for item in test["assertions"]
                    if item["assertion_class"] == "business"
                )
                in_memory_business_result = _evaluate_in_memory_predicate(
                    runtime, context, business["predicate"]
                )
            if not workflow_effect or no_before_workflow:
                use_in_memory_business_result = _validate_business_dependencies(
                    test,
                    before or {},
                    producer,
                    after,
                    in_memory_predicate_available=(in_memory_business_result is not None),
                )
    except BaseException as error:
        if is_candidate_local_error(error):
            record = _incomplete_run(
                run_index,
                started,
                "candidate_local_execution",
                _safe_error_code(error),
                reset_ref=reset_ref,
                reset_elapsed_ms=reset_elapsed_ms,
            )
            if applicability is not None:
                record["applicability"] = _safe_workflow_applicability(applicability)
                record["before"] = _step_summary(before, include_semantic_evidence=mode == "qualifying-formal")
            return record
        raise

    record = {
        "run_index": run_index,
        "mechanical_status": "complete",
        "reason_code": None,
        "reset_ref": _safe_reset_ref(reset_ref),
        "reset_elapsed_ms": reset_elapsed_ms,
        "setup_count": len(setup),
        "setup_binding_event_count": sum(len(item.get("binding_events") or []) for item in setup),
        "before": (
            {"not_applicable": True, "reason_code": "single_state_has_no_before"}
            if single_state
            else
            {
                "not_applicable": True,
                "reason_code": f"{blueprint['workflow_kind']}_has_no_before",
            }
            if no_before_workflow
            else _step_summary(
                before, include_semantic_evidence=mode == "qualifying-formal"
            )
        ),
        "producer": (
            {"not_applicable": True, "reason_code": "single_state_has_no_producer"}
            if single_state else _step_summary(producer, include_semantic_evidence=mode == "qualifying-formal")
        ),
        "after": _step_summary(
            after, include_semantic_evidence=mode == "qualifying-formal"
        ),
        "producer_binding": producer_binding,
        "observer_binding": {
            "before": before_binding,
            "after": after_binding,
            "same_fresh_creator_values": True,
        },
        "observer_purity": {
            "before_observer": before_purity,
            "after_observer": after_purity,
        },
        "settle_elapsed_ns": int(settle_elapsed_ns),
        "settle_poll_count": settle_poll_count,
        "settle_consecutive_identical": settle_consecutive_identical,
        "settle_projection_sha256": settle_projection_sha256,
        "elapsed_ms": (time.monotonic_ns() - started) / 1_000_000,
    }
    if extra_steps:
        record["steps"] = {key: _step_summary(value, include_semantic_evidence=mode != "rehearsal") for key, value in extra_steps.items()}
    if use_in_memory_business_result:
        # Reuse the actual capture manifests so M14 can check why operands
        # stayed private. Neither their values nor value hashes are exported.
        record["producer"]["redaction_manifest"] = {
            "request": copy.deepcopy((producer.get("redaction_manifest") or {}).get("request", [])),
        }
        record["after"]["redaction_manifest"] = {
            "response": copy.deepcopy((after.get("redaction_manifest") or {}).get("response", [])),
        }
    if test["protocol_kind"] == "V3":
        record["query_diagnostics"] = copy.deepcopy(query_diagnostics)
        record["query_scope_complete"] = query_scope_complete
        if query_failure is not None or not query_scope_complete:
            record["mechanical_status"] = "candidate_local_incomplete"
            record["reason_code"] = (query_failure or {}).get("reason_code", "query_scope_incomplete")
    if applicability is not None:
        record["applicability"] = _safe_workflow_applicability(applicability)
    if mode == "rehearsal":
        record.update(
            {
                "assertion_results": [],
                "business_outcomes_evaluated": False,
                "business_outcomes_persisted": False,
            }
        )
        return record

    observations = {
        "after": _observation(after),
        "consumer": _consumer_observation(after),
        "after_status": {"body": after["status"]},
    }
    observations.update({step: _observation(value) for step, value in extra_steps.items()})
    if producer is not None:
        observations["producer"] = _producer_observation(producer)
    if single_state:
        observations["observation"] = _observation(after)
        from ui_semantics.current_protocols.metamorphic_query import query_request_observation
        observations["observation_request"] = query_request_observation(after)
    if before is not None:
        observations["before"] = _observation(before)
    assertion_results = []
    for assertion in test["assertions"]:
        try:
            if assertion["assertion_class"] == "business":
                business_steps = (
                    (after,)
                    if single_state
                    else
                    (producer, after)
                    if no_before_workflow
                    else (before, producer, after)
                )
                steps_succeeded = (
                    type(after.get("status")) is int and 200 <= after["status"] < 300
                    if single_state
                    else all(type(value.get("status")) is int and (
                        200 <= value["status"] < 300
                        or (value is before or value is after) and point_resource and value["status"] in business_predicate.get("absent_statuses", [])
                        or (value is before or value is after) and point_status and 400 <= value["status"] < 500
                    ) for value in business_steps)
                    if workflow_effect or test["protocol_kind"] == "V7"
                    else all(_business_step_success(value) for value in business_steps)
                )
                if not steps_succeeded:
                    assertion_results.append(
                        {
                            "assertion_id": assertion["assertion_id"],
                            "assertion_class": assertion["assertion_class"],
                            "assertion_source": assertion["assertion_source"],
                            "predicate_type": assertion["predicate_type"],
                            "definition_sha256": assertion["definition_sha256"],
                            "evidence_refs": copy.deepcopy(assertion["evidence_refs"]),
                            "verdict": "unable",
                            "detail": {"reason": "business_protocol_step_unsuccessful"},
                        }
                    )
                    continue
                if no_before_workflow and use_in_memory_business_result:
                    assert in_memory_business_result is not None
                    passed, detail = in_memory_business_result
                    safe_detail = {
                        "observed": copy.deepcopy(detail),
                        "reason_code": None,
                        "evaluator": IN_MEMORY_PREDICATE_EVALUATOR,
                    }
                elif single_state:
                    evaluated = evaluate_predicate_result(
                        assertion["predicate"], observations,
                        dependency_checker=partial(
                            reject_redacted_predicate_dependencies,
                            sources={
                                "observation": ((after, "response"),),
                                "observation_request": tuple((after, channel) for channel in ("request_query", "request", "request_headers", "request_path")),
                            },
                        ),
                    )
                    passed, detail = evaluated["satisfied"], evaluated["observed"]
                    safe_detail = {"observed": _safe_single_state_detail(detail), "reason_code": evaluated["reason_code"], "evaluator": "ui_semantics.dsl.evaluate_predicate_result"}
                elif workflow_effect:
                    evaluated = evaluate_predicate_result(
                        assertion["predicate"],
                        {**observations, "producer_request": request_numeric_observation(producer, producer.get("semantic_request_body")),
                         "producer_response": _producer_observation(producer)},
                        dependency_checker=partial(
                            reject_redacted_predicate_dependencies,
                            sources={**({"before": ((before, "response"),)} if before is not None else {}), "after": ((after, "response"),),
                                     "producer_request": tuple((producer, channel) for channel in ("request", "request_query", "request_headers", "request_path")),
                                     "producer_response": ((producer, "response"),)},
                        ),
                    )
                    passed = evaluated["satisfied"]
                    safe_detail = {
                        "observed": _safe_workflow_detail(evaluated["observed"]),
                        "reason_code": evaluated["reason_code"],
                        "evaluator": "ui_semantics.dsl.evaluate_predicate_result",
                    }
                elif test["protocol_kind"] == "V3":
                    passed = (
                        True if query_evaluation["status"] == "satisfied"
                        else False if query_evaluation["status"] == "violated" else None
                    )
                    safe_detail = {
                        "observed": _safe_single_state_detail(query_evaluation["observed"]),
                        "reason_code": query_evaluation["reason_code"],
                        "query_scope_complete": query_scope_complete,
                        "query_diagnostics": copy.deepcopy(query_diagnostics),
                        "evaluator": "ui_semantics.current_protocols.metamorphic_query.evaluate_query_plan_predicate",
                    }
                elif test["protocol_kind"] == "V7":
                    actor_observations = {
                        "before": _observation(before),
                        "after": _observation(after),
                        "after_status": {"body": after["status"]},
                        "producer_request": request_numeric_observation(producer, producer.get("semantic_request_body")),
                        "producer_response": _producer_observation(producer),
                    }
                    actor_sources = {
                        "before": ((before, "response"),), "after": ((after, "response"),),
                        "producer_request": tuple((producer, channel) for channel in ("request", "request_query", "request_headers", "request_path")),
                        "producer_response": ((producer, "response"),),
                    }
                    for reference in _canonical_value_refs(assertion["predicate"]):
                        role = str(reference["role"])
                        if role.startswith("actor_before:"):
                            actor_observations[role] = _observation(before)
                            actor_sources[role] = ((before, "response"),)
                        elif role.startswith("actor_after:"):
                            actor_observations[role] = _observation(after)
                            actor_sources[role] = ((after, "response"),)
                    evaluated = evaluate_predicate_result(
                        assertion["predicate"], actor_observations,
                        dependency_checker=partial(reject_redacted_predicate_dependencies, sources=actor_sources),
                    )
                    passed = evaluated["satisfied"]
                    safe_detail = {
                        "observed": _safe_workflow_detail(evaluated["observed"]),
                        "reason_code": evaluated["reason_code"],
                        "evaluator": "ui_semantics.dsl.evaluate_predicate_result",
                    }
                elif no_before_workflow:
                    passed, detail = evaluate_predicate(
                        assertion["predicate"],
                        {
                            "after": _observation(after),
                            "producer_request": _producer_observation(producer),
                            "producer_response": _producer_observation(producer),
                        },
                    )
                    safe_detail = {
                        "observed": _safe_detail(detail),
                        "evaluator": "ui_semantics.dsl.evaluate_predicate",
                    }
                else:
                    passed, operands, reason_code = evaluate_pair(
                        assertion["predicate"],
                        _route_s_observation(
                            before,
                            "runtime:before",
                        ),
                        _route_s_observation(after, "runtime:after"),
                        _route_s_producer(producer),
                    )
                    safe_detail = {
                        "reason_code": reason_code,
                        "operands": [_safe_operand(item) for item in operands],
                        "evaluator": "ui_semantics.current_route_s.core.evaluate_pair",
                    }
            else:
                passed, detail = evaluate_predicate(assertion["predicate"], observations)
                safe_detail = _safe_detail(detail)
            verdict = "unable" if (single_state or workflow_effect or test["protocol_kind"] in {"V3", "V7"}) and passed is None else "passed" if passed else "failed"
        except BaseException as error:
            verdict = "unable"
            safe_detail = {"reason": type(error).__name__}
        assertion_results.append(
            {
                "assertion_id": assertion["assertion_id"],
                "assertion_class": assertion["assertion_class"],
                "assertion_source": assertion["assertion_source"],
                "predicate_type": assertion["predicate_type"],
                "definition_sha256": assertion["definition_sha256"],
                "evidence_refs": copy.deepcopy(assertion["evidence_refs"]),
                "verdict": verdict,
                "detail": safe_detail,
            }
        )
    record["assertion_results"] = assertion_results
    return record


def _calibrate_assertions(
    test: Mapping[str, Any],
    runs: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for assertion in test["assertions"]:
        outcomes = []
        for run in runs:
            row = next(
                (
                    item
                    for item in run.get("assertion_results", [])
                    if item["assertion_id"] == assertion["assertion_id"]
                ),
                None,
            )
            outcomes.append(row["verdict"] if row is not None else "unable")
        if test["protocol_kind"] in {"V3", "V5", "V6", "V7", "V8", "V9"} and assertion["assertion_class"] == "business" and "failed" in outcomes:
            status = "fail"
        elif any(run["mechanical_status"] != "complete" for run in runs) or "unable" in outcomes:
            status = "inconclusive"
        elif all(outcome == "passed" for outcome in outcomes):
            status = "pass"
        else:
            status = "fail"
        result.append(
            {
                "assertion_id": assertion["assertion_id"],
                "assertion_class": assertion["assertion_class"],
                "assertion_source": assertion["assertion_source"],
                "predicate_type": assertion["predicate_type"],
                "definition_sha256": assertion["definition_sha256"],
                "status": status,
                "normal_run_verdicts": outcomes,
            }
        )
    return result


def _validate_runtime_result(
    value: Any,
    label: str,
    endpoint: Mapping[str, Any],
) -> None:
    if not isinstance(value, dict):
        raise RelationExecutionError(f"{label}_result_not_object")
    status = value.get("status")
    transport = value.get("transport_request")
    if not isinstance(status, int) or not isinstance(transport, dict):
        raise RelationExecutionError(f"{label}_result_incomplete")
    if not isinstance(transport.get("method"), str) or not isinstance(transport.get("path"), str):
        raise RelationExecutionError(f"{label}_transport_incomplete")
    if transport["method"] != endpoint.get("method"):
        raise RelationExecutionError(f"{label}_transport_method_drift")
    actual_shape = value.get("transport_request_shape_sha256")
    expected_shape = endpoint.get("request_shape_sha256")
    if actual_shape != expected_shape and not empty_object_no_body_shape_compatible(
        transport, str(expected_shape)
    ):
        raise RelationExecutionError(f"{label}_transport_shape_drift")
    if transport["path"] != endpoint.get("path"):
        events = value.get("resource_binding_events") or []
        if not any(
            item.get("target_location") == "path"
            and item.get("consumer_request_ref") == endpoint.get("request_ref")
            for item in events
            if isinstance(item, dict)
        ):
            raise RelationExecutionError(f"{label}_transport_path_drift_without_binding")


def _observation(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy_numeric_sources(value, {
        "request": copy.deepcopy(value["transport_request"].get("body")),
        "response": copy.deepcopy(value.get("body")),
        "body": copy.deepcopy(value.get("body")),
        "status": value["status"],
    })


def _producer_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    observation = _observation(value)
    observation["response"] = copy_numeric_sources(value, {
        "body": copy.deepcopy(value.get("body")), "status": value["status"],
    })
    return observation


def _route_s_observation(value: Mapping[str, Any], raw_ref: str) -> dict[str, Any]:
    return {
        "state": "executed", "status": "pass", "raw_ref": raw_ref,
        "response": copy_numeric_sources(value, {"body": copy.deepcopy(value.get("body"))}),
    }


def _route_s_producer(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy_numeric_sources(value, {
        "state": "executed", "status": "pass", "raw_ref": "runtime:producer",
        "request": copy.deepcopy(value["semantic_request_body"]),
        "response": copy.deepcopy(value.get("body")),
    })


def _consumer_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    return _observation(value)


def _step_summary(
    value: Mapping[str, Any], *, include_semantic_evidence: bool
) -> dict[str, Any]:
    transport = value["transport_request"]
    result = {
        "transport_request_sha256": canonical_sha256(transport),
        "binding_event_count": len(value.get("resource_binding_events") or []),
        "method": transport["method"],
        "path_sha256": canonical_sha256(transport["path"]),
        "sensitive_values_persisted": False,
        "fresh_values_persisted": False,
    }
    if include_semantic_evidence:
        result["status"] = value["status"]
        result["response_body_sha256"] = canonical_sha256(value.get("body"))
    return result


def _safe_reset_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "artifact_type",
        "run_id",
        "record_id",
        "reset_artifact_ref",
        "reset_artifact_sha256",
        "attempt_ref",
        "attempt_sha256",
        "completion_ref",
        "completion_sha256",
    }
    return {key: copy.deepcopy(item) for key, item in value.items() if key in allowed}


def is_workflow_effect_test(test: Mapping[str, Any]) -> bool:
    """Limit the workflow expansion to its new V4 predicate signatures."""
    return test.get("protocol_kind") == "V4" and any(
        row.get("assertion_class") == "business"
        and is_workflow_effect_predicate(row["predicate"])
        for row in test.get("assertions", ())
    )


def _safe_workflow_detail(detail: Mapping[str, Any]) -> dict[str, Any]:
    if "checks" in detail:
        return _safe_single_state_detail(detail)
    if "equal" in detail:
        return {"values_equal": detail["equal"]}
    structural = {"before_matches", "applicability_satisfied", "after_matches", "direction_satisfied", "numeric_mode", "values_equal", "precision_sources"}
    return {
        key if key in structural else key + "_sha256":
        copy.deepcopy(value) if key in structural else canonical_sha256(value)
        for key, value in detail.items()
    }


def _safe_workflow_applicability(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": result["status"],
        "observed": _safe_workflow_detail(result["observed"]),
        "reason_code": result["reason_code"],
        "evaluator": "ui_semantics.dsl.evaluate_workflow_applicability",
        "checked_before_action": True,
    }


def _safe_detail(detail: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("status", "actual_type", "expected_type", "before", "after"):
        value = detail.get(key)
        if isinstance(value, (int, float, bool)) or value is None or key in {"actual_type", "expected_type"}:
            safe[key] = value
    for key in ("actual", "expected", "left", "right"):
        if key in detail:
            safe[f"{key}_sha256"] = canonical_sha256(detail[key])
    if not safe:
        safe["reason"] = "deterministic_predicate_evaluated"
    return safe


def _safe_single_state_detail(detail: Mapping[str, Any]) -> dict[str, Any]:
    """Retain the finite check tree while withholding business operand values."""
    raw_keys = {"actual", "expected", "left", "right", "target", "domain"}
    structural_keys = {
        "checks", "parameter_checks", "check_id", "member_index", "guard", "body", "satisfied",
        "observed", "reason_code", "diagnostics", "error_type", "member_count",
        "applicable_member_count", "nonempty_support", "present", "expected_present",
        "actual_count", "request_limit", "actual_type", "expected_type", "values_equal",
        "format_valid", "measured_value", "threshold", "uniqueness_checks", "duplicate_of",
        "numeric_mode", "precision_sources", "output", "item", "factor", "ordering_checks",
        "relation", "representation", "comparison_basis", "left_count", "right_count", "partition_checks",
        "left_partition", "right_partition", "previous_index", "match_count",
    }
    def safe(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key + "_sha256" if key in raw_keys else key:
                canonical_sha256(child) if key in raw_keys else copy.deepcopy(child) if key == "precision_sources" else safe(child)
                for key, child in value.items() if key in raw_keys or key in structural_keys
            }
        if isinstance(value, list):
            return [safe(child) for child in value]
        return copy.deepcopy(value)
    return safe(detail)


def _safe_operand(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "name",
        "normalization_rule",
        "normalized_value_sha256",
        "operator",
        "raw_ref",
    )
    result = {key: copy.deepcopy(value[key]) for key in allowed if key in value}
    if not _SHA256.fullmatch(str(result.get("normalized_value_sha256") or "")):
        raise RelationExecutionError("business_operand_hash_missing")
    return result


def _validate_observer_purity(
    before: Any,
    after: Any,
    expected_domains: list[str],
) -> dict[str, Any]:
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise RelationExecutionError("observer_snapshot_not_object")
    if set(before) != set(expected_domains) or set(after) != set(expected_domains):
        raise RelationExecutionError("observer_snapshot_domain_drift")
    for domain in expected_domains:
        left = before[domain]
        right = after[domain]
        if not isinstance(left, str) or not _SHA256.fullmatch(left):
            raise RelationExecutionError(f"observer_snapshot_unproven:{domain}")
        if not isinstance(right, str) or not _SHA256.fullmatch(right):
            raise RelationExecutionError(f"observer_snapshot_unproven:{domain}")
        if left != right:
            raise RelationExecutionError(f"observer_mutated_runtime_state:{domain}")
    return {
        "status": "pass",
        "domains": sorted(expected_domains),
        "sensitive_values_persisted": False,
    }


def _validate_producer_binding(
    producer: Mapping[str, Any],
    endpoint: Mapping[str, Any],
    requirement: Mapping[str, Any],
    *,
    candidate_id: str,
    arm: str,
    reset_epoch: Any,
    creator_hashes: Mapping[str, str],
) -> dict[str, Any]:
    return _validate_endpoint_binding(
        producer,
        endpoint,
        requirement,
        candidate_id=candidate_id,
        arm=arm,
        reset_epoch=reset_epoch,
        creator_hashes=creator_hashes,
    )


def _validate_setup_bindings(
    setup: Any,
    *,
    candidate_id: str,
    arm: str,
    reset_epoch: Any,
) -> dict[str, str]:
    if not isinstance(setup, list) or not isinstance(reset_epoch, str) or not reset_epoch:
        raise RelationExecutionError("setup_or_reset_binding_evidence_invalid")
    creator_hashes: dict[str, str] = {}
    for row in setup:
        if not isinstance(row, dict):
            raise RelationExecutionError("setup_result_not_object")
        events = row.get("binding_events") or []
        if not isinstance(events, list):
            raise RelationExecutionError("setup_binding_events_not_array")
        for event in events:
            _validate_event_scope(
                event,
                candidate_id=candidate_id,
                arm=arm,
                reset_epoch=reset_epoch,
            )
            kind = event.get("event")
            if kind in {
                "creator_value_captured",
                "creator_value_recovered_from_reset_alias",
            }:
                source_id = str(event.get("source_id") or "")
                value_sha = str(event.get("value_sha256") or "")
                if (
                    not _SHA256.fullmatch(source_id)
                    or not _SHA256.fullmatch(value_sha)
                    or event.get("creator_request_ref") != row.get("request_ref")
                    or event.get("creator_actor_id") != event.get("actor_id")
                ):
                    raise RelationExecutionError("setup_creator_binding_event_invalid")
                if kind == "creator_value_captured":
                    response = row.get("response") or {}
                    source_path = str(
                        event.get("observed_source_typed_path")
                        or event.get("source_typed_path")
                        or ""
                    )
                    creator_value = extract_typed_value(
                        response.get("body"),
                        source_path,
                    )
                    creator_value = _captured_transport_value(
                        creator_value,
                        event,
                    )
                    creator_value = _coerce_to_proof_scalar_type(
                        creator_value, str(event.get("scalar_type") or "")
                    )
                    try:
                        creator_value_sha = scalar_sha256(creator_value)
                    except BaseException as error:
                        manifest = (row.get("redaction_manifest") or {}).get(
                            "response"
                        )
                        if not isinstance(manifest, list) or not (
                            typed_redaction_sentinel_attested(
                                creator_value,
                                typed_path=source_path,
                                original_json_type=str(event.get("scalar_type") or ""),
                                manifest=manifest,
                            )
                        ):
                            raise RelationExecutionError(
                                "setup_creator_value_not_observable_scalar"
                            ) from error
                        creator_value_sha = value_sha
                    if (
                        creator_value_sha != value_sha
                        or (
                            not isinstance(creator_value, Mapping)
                            and _scalar_type(creator_value) != event.get("scalar_type")
                        )
                    ):
                        raise RelationExecutionError(
                            "setup_creator_value_evidence_mismatch"
                        )
                previous = creator_hashes.get(source_id)
                if previous is not None and previous != value_sha:
                    raise RelationExecutionError("setup_creator_value_changed_within_reset")
                creator_hashes[source_id] = value_sha
            elif kind == "consumer_value_rebound":
                source_id = str(event.get("source_id") or "")
                if creator_hashes.get(source_id) != event.get("value_sha256"):
                    raise RelationExecutionError("setup_consumer_not_bound_to_fresh_creator")
                if event.get("consumer_request_ref") != row.get("request_ref"):
                    raise RelationExecutionError("setup_consumer_request_ref_drift")
                _validate_injected_value(row, event)
            else:
                raise RelationExecutionError("setup_binding_event_kind_unsupported")
    return creator_hashes


def _validate_runtime_creator_captures(
    producer: Mapping[str, Any],
    endpoint: Mapping[str, Any],
    consumer_requirement: Mapping[str, Any],
    *,
    candidate_id: str,
    arm: str,
    reset_epoch: str,
    creator_hashes: Mapping[str, str],
    normalized_response: bool = False,
) -> dict[str, str]:
    """Close deferred creator identities captured from this producer response."""

    expected_by_source: dict[str, Mapping[str, Any]] = {}
    for event in consumer_requirement.get("events") or []:
        source_id = str(event.get("source_id") or "")
        if not _SHA256.fullmatch(source_id):
            raise RelationExecutionError("runtime_creator_requirement_invalid")
        if source_id in creator_hashes:
            continue
        is_endpoint_creator = (
            event.get("creator_actor_id") == endpoint.get("actor_id")
            and event.get("creator_request_ref") == endpoint.get("request_ref")
        )
        if not is_endpoint_creator:
            if source_id not in creator_hashes:
                raise RelationExecutionError("runtime_creator_requirement_invalid")
            continue
        previous = expected_by_source.get(source_id)
        if previous is not None and (
            previous.get("source_typed_path") != event.get("source_typed_path")
            or previous.get("scalar_type") != event.get("scalar_type")
        ):
            raise RelationExecutionError("runtime_creator_requirement_ambiguous")
        expected_by_source[source_id] = event
    captures = producer.get("fresh_capture_events")
    if producer.get("fresh_capture_error") is not None:
        raise RelationExecutionError(str(producer["fresh_capture_error"]))
    if not isinstance(captures, list):
        raise RelationExecutionError("runtime_creator_capture_events_missing")
    merged = dict(creator_hashes)
    seen: set[str] = set()
    response = producer.get("body")
    for capture in captures:
        _validate_event_scope(
            capture,
            candidate_id=candidate_id,
            arm=arm,
            reset_epoch=reset_epoch,
        )
        source_id = str(capture.get("source_id") or "")
        capture_value_sha = str(capture.get("value_sha256") or "")
        expected = expected_by_source.get(source_id)
        if (
            capture.get("event") != "creator_value_captured"
            or capture.get("actor_id") != endpoint.get("actor_id")
            or capture.get("creator_actor_id") != endpoint.get("actor_id")
            or capture.get("creator_request_ref") != endpoint.get("request_ref")
            or not _SHA256.fullmatch(source_id)
            or not _SHA256.fullmatch(capture_value_sha)
            or not isinstance(capture.get("source_typed_path"), str)
            or not capture["source_typed_path"]
            or capture.get("scalar_type") not in {
                "string", "integer", "number", "boolean"
            }
        ):
            raise RelationExecutionError("runtime_creator_capture_signature_drift")
        if expected is None:
            continue
        if (
            source_id in seen
            or capture.get("source_typed_path") != expected.get("source_typed_path")
            or capture.get("scalar_type") != expected.get("scalar_type")
        ):
            raise RelationExecutionError("runtime_creator_capture_signature_drift")
        value = extract_typed_value(
            response,
            str(
                capture.get("observed_source_typed_path")
                or capture["source_typed_path"]
            ),
        )
        value = _captured_transport_value(value, capture)
        value = _coerce_to_proof_scalar_type(
            value, str(capture.get("scalar_type") or "")
        )
        if isinstance(value, Mapping):
            manifest = (producer.get("redaction_manifest") or {}).get("response")
            if not (
                normalized_response
                and isinstance(manifest, list)
                and typed_redaction_sentinel_attested(
                    value,
                    typed_path=str(
                        capture.get("observed_source_typed_path")
                        or capture["source_typed_path"]
                    ),
                    original_json_type=str(capture.get("scalar_type") or ""),
                    manifest=manifest,
                )
            ):
                raise RelationExecutionError(
                    "runtime_creator_value_evidence_mismatch"
                )
            value_sha = capture_value_sha
        else:
            if _scalar_type(value) != capture.get("scalar_type"):
                raise RelationExecutionError("runtime_creator_value_evidence_mismatch")
            if normalized_response:
                value_sha = capture_value_sha
            else:
                try:
                    value_sha = scalar_sha256(value)
                except BaseException as error:
                    raise RelationExecutionError(
                        "runtime_creator_value_not_observable_scalar"
                    ) from error
                if value_sha != capture_value_sha:
                    raise RelationExecutionError(
                        "runtime_creator_value_evidence_mismatch"
                    )
        if source_id in merged and merged[source_id] != value_sha:
            raise RelationExecutionError("runtime_creator_value_changed_within_reset")
        merged[source_id] = value_sha
        seen.add(source_id)
    if seen != set(expected_by_source):
        raise RelationExecutionError("runtime_creator_capture_source_set_drift")
    return merged


def _validate_endpoint_binding(
    result: Mapping[str, Any],
    endpoint: Mapping[str, Any],
    requirement: Mapping[str, Any],
    *,
    candidate_id: str,
    arm: str,
    reset_epoch: Any,
    creator_hashes: Mapping[str, str],
) -> dict[str, Any]:
    events = result.get("resource_binding_events")
    expected_events = requirement.get("events")
    if not isinstance(events, list) or not isinstance(expected_events, list):
        raise RelationExecutionError("endpoint_binding_events_missing")
    if requirement.get("scope_derivation") != "candidate_arm_actor_reset_epoch_v1":
        raise RelationExecutionError("endpoint_binding_scope_rule_drift")
    if len(events) != requirement.get("event_count") or len(events) != len(expected_events):
        raise RelationExecutionError("endpoint_binding_event_count_drift")
    actual_descriptors = [_event_descriptor(event) for event in events]
    if Counter(_descriptor_key(row) for row in actual_descriptors) != Counter(
        _descriptor_key(row) for row in expected_events
    ):
        raise RelationExecutionError("endpoint_binding_event_signature_drift")
    source_ids: set[str] = set()
    for event in events:
        _validate_event_scope(
            event,
            candidate_id=candidate_id,
            arm=arm,
            reset_epoch=reset_epoch,
        )
        if event.get("consumer_request_ref") != endpoint.get("request_ref"):
            raise RelationExecutionError("endpoint_binding_consumer_ref_drift")
        if event.get("actor_id") != endpoint.get("actor_id"):
            raise RelationExecutionError("endpoint_binding_actor_drift")
        source_id = str(event.get("source_id") or "")
        value_sha = str(event.get("value_sha256") or "")
        if creator_hashes.get(source_id) != value_sha:
            raise RelationExecutionError("endpoint_not_bound_to_fresh_creator")
        _validate_injected_value(result, event)
        source_ids.add(source_id)
    if source_ids != set(requirement.get("source_ids") or []):
        raise RelationExecutionError("endpoint_binding_source_set_drift")
    transport = result["transport_request"]
    if transport["path"] != endpoint.get("path"):
        try:
            validate_proven_path_change(
                str(endpoint.get("path")),
                str(transport["path"]),
                events,
                endpoint,
            )
        except BaseException as error:
            raise RelationExecutionError("endpoint_path_change_not_exactly_proven") from error
    return {
        "status": "pass",
        "event_count": len(events),
        "source_ids": sorted(source_ids),
        "scope_recomputed_from_current_reset": True,
        "fresh_creator_value_equality": True,
        "fresh_values_persisted": False,
    }


def _validate_event_scope(
    event: Any,
    *,
    candidate_id: str,
    arm: str,
    reset_epoch: str,
) -> None:
    if not isinstance(event, dict):
        raise RelationExecutionError("binding_event_not_object")
    actor_id = event.get("actor_id")
    if (
        event.get("candidate_id") != candidate_id
        or event.get("arm") != arm
        or event.get("reset_epoch") != reset_epoch
        or not isinstance(actor_id, str)
        or not actor_id
    ):
        raise RelationExecutionError("binding_event_runtime_scope_drift")
    expected_scope = binding_scope_id(candidate_id, arm, actor_id, reset_epoch)
    if event.get("binding_scope_id") != expected_scope:
        raise RelationExecutionError("binding_event_current_scope_derivation_failed")
    if not _SHA256.fullmatch(str(event.get("value_sha256") or "")):
        raise RelationExecutionError("binding_event_value_hash_missing")


def _event_descriptor(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict) or event.get("event") != "consumer_value_rebound":
        raise RelationExecutionError("endpoint_binding_event_not_consumer_rebound")
    keys = (
        "event",
        "actor_id",
        "creator_actor_id",
        "creator_request_ref",
        "consumer_request_ref",
        "scalar_type",
        "source_id",
        "source_typed_path",
        "target_location",
        "target_typed_path",
    )
    if any(not isinstance(event.get(key), str) or not event[key] for key in keys):
        raise RelationExecutionError("endpoint_binding_event_descriptor_incomplete")
    result = {key: copy.deepcopy(event[key]) for key in keys}
    if "target_group_size" in event:
        result["target_group_size"] = event["target_group_size"]
    return result


def _descriptor_key(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validate_injected_value(result: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    transport = result.get("physical_transport_request") or result.get(
        "transport_request"
    )
    if not isinstance(transport, dict):
        raise RelationExecutionError("binding_transport_request_missing")
    location = event["target_location"]
    path = event["target_typed_path"]
    if location == "body":
        value = extract_typed_value(transport.get("body"), path)
    elif location == "path":
        match = re.fullmatch(r"\$\.segments\[(\d+)\]", path)
        segments = [unquote(item) for item in str(transport.get("path") or "").split("/") if item]
        if match is None or int(match.group(1)) >= len(segments):
            raise RelationExecutionError("binding_path_target_missing")
        value = segments[int(match.group(1))]
    elif location == "query":
        name = path[2:] if path.startswith("$.") else ""
        metadata = result.get("physical_transport_metadata") or result.get(
            "transport_metadata"
        )
        query = (metadata or {}).get("query") or {}
        if not name or not isinstance(query, dict) or name not in query:
            raise RelationExecutionError("binding_query_target_missing")
        value = query[name]
    elif location == "header":
        name = path[2:] if path.startswith("$.") else ""
        metadata = result.get("physical_transport_metadata") or result.get(
            "transport_metadata"
        )
        headers = (metadata or {}).get("request_headers") or {}
        keys = [key for key in headers if str(key).casefold() == name.casefold()]
        if not name or not isinstance(headers, dict) or len(keys) != 1:
            raise RelationExecutionError("binding_header_target_missing")
        value = headers[keys[0]]
    else:
        raise RelationExecutionError("binding_target_location_unsupported")
    try:
        actual_sha = scalar_sha256(value)
    except BaseException as error:
        manifest_key = {
            "body": "request",
            "query": "request_query",
            "header": "request_headers",
        }.get(location)
        manifest = (result.get("redaction_manifest") or {}).get(manifest_key)
        if (
            manifest_key is None
            or not isinstance(manifest, list)
            or not typed_redaction_sentinel_attested(
                value,
                typed_path=path,
                original_json_type=str(event.get("scalar_type") or ""),
                manifest=manifest,
            )
        ):
            raise RelationExecutionError("binding_target_value_not_scalar") from error
        actual_sha = str(event.get("value_sha256") or "")
    if actual_sha != event.get("value_sha256"):
        raise RelationExecutionError("binding_event_does_not_match_outgoing_value")


def _validate_business_dependencies(
    test: Mapping[str, Any],
    before: Mapping[str, Any],
    producer: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    query_results: Mapping[str, Mapping[str, Any]] | None = None,
    in_memory_predicate_available: bool = False,
) -> bool:
    business = next(
        item for item in test["assertions"] if item["assertion_class"] == "business"
    )
    predicate = business["predicate"]
    value_refs = _canonical_value_refs(predicate)
    observation_sources: dict[str, tuple[tuple[Mapping[str, Any], str], ...]] = {
        "before": ((before, "response"),),
        "after": ((after, "response"),),
    }
    if query_results is not None:
        observation_sources.update({
            role: ((result, "response"),)
            for role, result in query_results.items()
        })
    for reference in value_refs:
        role = str(reference["role"])
        if role.startswith("actor_before:"):
            observation_sources[role] = ((before, "response"),)
        elif role.startswith("actor_after:"):
            observation_sources[role] = ((after, "response"),)
    if "followup_query" in {str(row["role"]) for row in value_refs}:
        matching = tuple(
            row
            for role, rows in observation_sources.items()
            if role.startswith("followup_query:")
            for row in rows
        )
        if not matching:
            raise RelationExecutionError("query_dependency_role_missing")
        observation_sources["followup_query"] = matching
    redacted_dependency = False
    try:
        reject_redacted_predicate_dependencies(predicate, observation_sources)
    except SensitiveMaterialUnavailable as error:
        if not in_memory_predicate_available:
            raise RelationExecutionError(
                "business_observation_dependency_redacted"
            ) from error
        redacted_dependency = True
    try:
        reject_redacted_predicate_dependencies(
            predicate,
            {
                "producer_request": ((producer, "request"),),
                "producer_response": ((producer, "response"),),
            },
        )
    except SensitiveMaterialUnavailable as error:
        if not in_memory_predicate_available:
            raise RelationExecutionError(
                "business_symbolic_dependency_redacted"
            ) from error
        redacted_dependency = True
    return redacted_dependency


def _evaluate_in_memory_predicate(
    runtime: CertifiedRelationRuntime,
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


def _canonical_value_refs(predicate: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return predicate_value_refs(predicate)


def _require_workflow_step_success(value: Mapping[str, Any], step: str) -> None:
    status = value.get("status")
    if type(status) is not int or not 200 <= status < 300:
        raise RelationExecutionError(f"workflow_step_unavailable:{step}:http_status:{status}")


def _business_step_success(value: Mapping[str, Any]) -> bool:
    status = value.get("status")
    if not isinstance(status, int) or not 200 <= status < 300:
        return False
    body = value.get("body")
    return not (
        isinstance(body, dict)
        and "errors" in body
        and bool(body.get("errors"))
    )


def _scalar_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return None


def _captured_transport_value(value: Any, event: Mapping[str, Any]) -> Any:
    """Reproduce an explicitly attested URL-path serialization for evidence checks."""

    encoding = event.get("transport_encoding")
    if encoding is None:
        return value
    if encoding != "url_path_segment_string":
        raise RelationExecutionError("creator_transport_encoding_unsupported")
    if (
        event.get("scalar_type") != "string"
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
    ):
        raise RelationExecutionError("creator_transport_encoding_invalid")
    return str(value)


def _incomplete_run(
    run_index: int,
    started_ns: int,
    stage: str,
    error_type: str,
    *,
    reset_ref: Mapping[str, Any] | None = None,
    reset_elapsed_ms: float,
) -> dict[str, Any]:
    return {
        "run_index": run_index,
        "mechanical_status": "candidate_local_incomplete",
        "reason_code": f"{stage}:{error_type}",
        "reset_ref": _safe_reset_ref(reset_ref or {}),
        "reset_elapsed_ms": reset_elapsed_ms,
        "setup_count": 0,
        "setup_binding_event_count": 0,
        "before": None,
        "producer": None,
        "after": None,
        "settle_elapsed_ns": None,
        "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000,
        "assertion_results": [],
    }


def _safe_error_code(error: BaseException) -> str:
    code = str(error)
    if isinstance(error, RelationExecutionError) and _SAFE_ERROR_CODE.fullmatch(code):
        return code
    return type(error).__name__


__all__ = [
    "CertifiedRelationRuntime",
    "RelationExecutionError",
    "build_calibration_summary",
    "execute_certified_relation_test",
    "execute_certified_relation_suite",
]
