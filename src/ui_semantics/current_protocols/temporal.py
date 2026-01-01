"""Finite temporal observations, evaluated from this execution's responses.

Client receive-time observations and timestamped server evidence are separate
claims. Neither polling nor settling establishes continuous server state.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from ..dsl import _exact_operand, evaluate_predicate_result, get_path, request_numeric_observation, copy_numeric_sources
from ..route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    reject_redacted_predicate_dependencies,
)


def _nanoseconds(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("temporal_time_requires_nonnegative_integer_nanoseconds")
    return value


def resolve_temporal_requirement(spec: Mapping[str, Any], action: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve duration sources once against the actually sent action.

    Nanoseconds are an internal clock unit. Decimal durations use the already
    established exact-operand parser, never a float-to-decimal reconstruction.
    """
    result = {key: spec[key] for key in ("kind", "observation_mode", "origin", "timestamp_evidence") if key in spec}
    scale = {"nanoseconds": 1, "milliseconds": 1_000_000, "seconds": 1_000_000_000}[spec["unit"]]
    observations = {"producer_request": request_numeric_observation(action, action.get("request")),
                    "producer_response": copy_numeric_sources(action, {"body": action.get("response")})}
    for source, target in (("duration_parameter", "duration_ns"), ("hold_duration_parameter", "hold_ns"),
                           ("error_before_parameter", "error_before_ns"), ("error_after_parameter", "error_after_ns")):
        operand = spec.get(source)
        if operand is None:
            if source == "duration_parameter":
                raise ValueError("temporal_duration_missing")
            result[target] = 0
            continue
        reject_redacted_predicate_dependencies({"parameter": operand}, {
            "producer_request": tuple((action, channel) for channel in ("request", "request_query", "request_path", "request_headers")),
            "producer_response": ((action, "response"),),
        })
        value, _ = _exact_operand(operand, observations)
        nanoseconds = value * scale
        if nanoseconds < 0 or getattr(nanoseconds, "denominator", 1) != 1:
            raise ValueError("temporal_duration_not_representable_in_nanoseconds")
        result[target] = int(nanoseconds)
    return result


def temporal_send_offsets(requirement: Mapping[str, Any]) -> tuple[int, ...]:
    """Program-defined finite schedule, never adapted to predicate outcomes."""
    duration = _nanoseconds(requirement["duration_ns"])
    hold = _nanoseconds(requirement.get("hold_ns", 0))
    if requirement["observation_mode"] == "returned_sample":
        return (max(0, duration - _nanoseconds(requirement.get("error_before_ns", 0))),)
    if requirement["observation_mode"] == "sampled":
        return (0, duration // 2, duration + hold // 2)
    # Timestamped historical-state / interval / event evidence is read after
    # the requested horizon; its own server clock establishes business time.
    return (duration + hold,)


def _check(name: str, value: bool | None, reason: str | None = None) -> dict[str, Any]:
    return {"check_id": name, "status": "satisfied" if value is True else "violated" if value is False else "not_evaluable", "reason_code": reason}


def _finish(checks: list[dict[str, Any]], *, complete: bool,
            diagnostics: list[dict[str, Any]], counts: Mapping[str, Any]) -> dict[str, Any]:
    statuses = [row["status"] for row in checks]
    if "violated" in statuses:
        verdict, failure = "refuted", None
    elif diagnostics:
        verdict, failure = "infrastructure_failed", "observer_failure"
    elif "not_evaluable" in statuses or not complete:
        verdict, failure = "not_evaluable", "binding"
    else:
        verdict, failure = "validated", None
    return {"protocol_verdict": verdict, "failure_class": failure,
            "claim_kind": "temporal_observation_confirmed" if verdict == "validated" else None,
            "checks": checks, "protocol_complete": complete,
            "diagnostics": diagnostics, "observed": dict(counts)}


def evaluate_received_samples(requirement: Mapping[str, Any], samples: Sequence[Mapping[str, Any]],
                              *, complete: bool, diagnostics: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Reduce predicate results at actual receive offsets, not scheduled times.

    The caller evaluates each fresh response with the common DSL. This reducer
    does not inspect a previous M12 verdict and never changes the frozen schedule.
    """
    duration = _nanoseconds(requirement["duration_ns"])
    hold = _nanoseconds(requirement.get("hold_ns", 0))
    rows = [dict(row) for row in samples]
    for row in rows:
        _nanoseconds(row["receive_offset_ns"])
        if row["satisfied"] is not None and type(row["satisfied"]) is not bool:
            raise TypeError("temporal_sample_truth_is_not_boolean")
    if any(left["receive_offset_ns"] > right["receive_offset_ns"] for left, right in zip(rows, rows[1:])):
        raise ValueError("temporal_receive_order_invalid")
    counts = {"observed_sample_count": len(rows), "before_deadline_usable_count": 0,
              "preservation_sample_count": 0, "first_witness_offset_ns": None}
    errors = [dict(row) for row in diagnostics]
    if requirement["kind"] == "deadline_state" and requirement["observation_mode"] == "returned_sample":
        if len(rows) != 1:
            return _finish([_check("deadline_state", None, "designated_sample_missing")], complete=complete, diagnostics=errors, counts=counts)
        before = _nanoseconds(requirement.get("error_before_ns", 0))
        after = _nanoseconds(requirement.get("error_after_ns", 0))
        sample = rows[0]
        within = max(0, duration - before) <= sample["receive_offset_ns"] <= duration + after
        value = sample["satisfied"] if within else None
        return _finish([_check("deadline_state", value, None if within and value is not None else "sample_outside_receive_window" if not within else "sample_operand_unavailable")], complete=complete, diagnostics=errors, counts=counts)
    if requirement["kind"] != "appearance_preservation" or requirement["observation_mode"] != "sampled":
        raise ValueError("received_samples_cannot_prove_server_time_or_events")
    usable = [row for row in rows if row["receive_offset_ns"] <= duration and row["satisfied"] is not None]
    counts["before_deadline_usable_count"] = len(usable)
    witness = next((row for row in usable if row["satisfied"] is True), None)
    if witness is None:
        # Completed finite observations with usable pre-deadline false values
        # refute the sampled claim, not the absence of a transient server event.
        unknown = any(row["receive_offset_ns"] <= duration and row["satisfied"] is None for row in rows)
        deadline = False if complete and usable and not unknown and not errors else None
        return _finish([_check("deadline_witness", deadline, "no_predeadline_witness"), _check("required_samples", None, "no_witness")], complete=complete, diagnostics=errors, counts=counts)
    start = witness["receive_offset_ns"]
    counts["first_witness_offset_ns"] = start
    index = rows.index(witness)
    later = [row for row in rows[index + 1:] if row["receive_offset_ns"] <= duration + hold]
    counts["preservation_sample_count"] = len(later)
    preservation = False if any(row["satisfied"] is False for row in later) else None if any(row["satisfied"] is None for row in later) else True
    return _finish([_check("deadline_witness", True), _check("required_samples", preservation, "sample_operand_unavailable" if preservation is None else None)], complete=complete, diagnostics=errors, counts=counts)


def _atom(predicate: Mapping[str, Any], action: Mapping[str, Any], response: Mapping[str, Any], record: Mapping[str, Any] | None = None) -> bool | None:
    sources = {
        "after": response,
        "after_status": {"body": response["status"]},
        "producer_request": request_numeric_observation(action, action.get("request")),
        "producer_response": copy_numeric_sources(action, {"body": action.get("response")}),
    }
    dependencies = {"after": ((record if record is not None else {"response": response}, "response"),),
                    "after_status": (),
                    "producer_request": tuple((action, channel) for channel in ("request", "request_query", "request_path", "request_headers")),
                    "producer_response": ((action, "response"),)}
    for ref in (predicate.get("target"), predicate.get("left"), predicate.get("collection")):
        if isinstance(ref, Mapping) and str(ref.get("role", "")).startswith("actor_after:"):
            sources[ref["role"]] = response
            dependencies[ref["role"]] = dependencies["after"]
    try:
        result = evaluate_predicate_result(predicate, sources, dependency_checker=lambda atom, **_kwargs: reject_redacted_predicate_dependencies(atom, dependencies))
        return result["satisfied"]
    except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable):
        return None


def _executed(record: Mapping[str, Any]) -> bool:
    return record.get("state") == "executed" and record.get("status") == "pass"


def _timestamped(requirement: Mapping[str, Any], predicate: Mapping[str, Any],
                 action: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
                 *, complete: bool, diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    """Read a declared state/history/event interface; never infer it from polls.

    Both origin and observations use response-supplied timestamps with the same
    explicit clock identifier. No server timestamp is subtracted from a local
    monotonic timestamp. All paths are frozen, observed interface references.
    """
    evidence = requirement.get("timestamp_evidence")
    counts = {"observed_sample_count": len(records), "before_deadline_usable_count": 0,
              "preservation_sample_count": 0, "first_witness_offset_ns": None}
    kind = requirement["kind"]
    check_name = "event_occurrence" if kind == "event_occurrence" else "deadline_state" if kind == "deadline_state" else "deadline_witness"
    try:
        if not isinstance(evidence, Mapping) or requirement["origin"] != "event":
            raise ValueError("timestamped_evidence_or_comparable_origin_missing")
        origin_body = action["response"]
        scale = {"nanoseconds": 1, "milliseconds": 1_000_000, "seconds": 1_000_000_000}[evidence.get("unit", "nanoseconds")]
        origin = _nanoseconds(get_path(origin_body, evidence["origin_time_path"])) * scale
        clock = get_path(origin_body, evidence["clock_id_path"])
        if type(clock) is not str or not clock or clock.startswith("[REDACTED"):
            raise ValueError("comparable_clock_missing")
        duration = _nanoseconds(requirement["duration_ns"])
        hold = _nanoseconds(requirement.get("hold_ns", 0))
        observations: list[dict[str, Any]] = []
        coverage: list[tuple[int, int]] = []
        for record in records:
            body = record["response"]["body"]
            if get_path(body, evidence["clock_id_path"]) != clock:
                raise ValueError("server_clock_identity_mismatch")
            items = get_path(body, evidence["items_path"])
            if type(items) is not list:
                raise ValueError("timestamped_items_missing")
            for item in items:
                start = _nanoseconds(get_path(item, evidence["time_path"])) * scale
                end = _nanoseconds(get_path(item, evidence["end_time_path"])) * scale if evidence.get("end_time_path") else start
                if end < start:
                    raise ValueError("timestamped_interval_invalid")
                state = get_path(item, evidence.get("value_path", "$"))
                value = _atom(predicate, action, {"status": 200, "body": state})
                observations.append({"start": start, "end": end, "satisfied": value})
            if evidence.get("coverage_start_path") is not None and evidence.get("complete_path") is not None and get_path(body, evidence["complete_path"]) is True:
                start = _nanoseconds(get_path(body, evidence["coverage_start_path"])) * scale
                end = _nanoseconds(get_path(body, evidence["coverage_end_path"])) * scale
                if end < start:
                    raise ValueError("timestamped_coverage_invalid")
                coverage.append((start, end))
        deadline = origin + duration
        if kind == "deadline_state":
            matches = [row for row in observations if row["start"] == deadline and row["end"] == deadline]
            value = matches[0]["satisfied"] if len(matches) == 1 else None
            return _finish([_check("deadline_state", value, "exact_state_evidence_missing" if value is None else None)], complete=complete, diagnostics=diagnostics, counts=counts)
        if kind == "event_occurrence":
            within = [row for row in observations if origin <= row["start"] <= deadline]
            witness = any(row["satisfied"] is True for row in within)
            window_complete = _covers(coverage, origin, deadline)
            value = True if witness else False if window_complete and all(row["satisfied"] is not None for row in within) else None
            return _finish([_check("event_occurrence", value, "event_window_incomplete" if value is None else None)], complete=complete, diagnostics=diagnostics, counts=counts)
        if requirement["observation_mode"] != "continuous":
            raise ValueError("timestamped_mode_mismatch")
        ordered = sorted(observations, key=lambda row: row["start"])
        witness = next((row for row in ordered if row["satisfied"] is True and row["start"] <= deadline and row["end"] >= origin), None)
        if witness is None:
            covered = _covers([(row["start"], row["end"]) for row in ordered if row["satisfied"] is False], origin, deadline)
            return _finish([_check("deadline_witness", False if covered else None, "continuous_witness_unavailable"), _check("required_samples", None, "no_witness")], complete=complete, diagnostics=diagnostics, counts=counts)
        start = max(origin, witness["start"])
        endpoint = deadline + hold
        counts["first_witness_offset_ns"] = start - origin
        later = [row for row in ordered if row["end"] >= start and row["start"] <= endpoint]
        false = any(row["satisfied"] is False and row["end"] >= start and row["start"] <= endpoint for row in later)
        covered = _covers([(row["start"], row["end"]) for row in later if row["satisfied"] is True], start, endpoint)
        value = False if false else True if covered else None
        return _finish([_check("deadline_witness", True), _check("required_samples", value, "continuous_interval_incomplete" if value is None else None)], complete=complete, diagnostics=diagnostics, counts=counts)
    except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
        return _finish([_check(check_name, None, str(error))], complete=complete, diagnostics=diagnostics, counts=counts)


def _covers(intervals: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    cursor = start
    observed = False
    for left, right in sorted(intervals):
        if right < cursor:
            continue
        if left > cursor:
            return False
        observed = True
        cursor = max(cursor, right)
        if cursor >= end:
            return True
    return observed and cursor >= end


def evaluate_temporal_result(predicate: Mapping[str, Any], requirement: Mapping[str, Any],
                             records: Mapping[str, Any]) -> dict[str, Any]:
    """Common M12/M14 evaluator; values and timings belong to this fresh run."""
    action = records.get("producer", {})
    diagnostics = [dict(row) for row in records.get("diagnostics", ())]
    complete = records.get("complete") is True
    if not _executed(action) or type(action.get("transport_status")) is not int or not 200 <= action["transport_status"] < 300:
        return _finish([_check("action", None, "temporal_action_unavailable")], complete=False, diagnostics=[{"reason_code": "temporal_action_unavailable"}], counts={})
    if records.get("identity_verified") is not True:
        return _finish([_check("identity", None, "temporal_identity_unverified")], complete=False, diagnostics=[], counts={})
    usable = []
    for record in records.get("observations", ()):
        status = record.get("response", {}).get("status")
        status_only = predicate.get("family") == "P02" and predicate.get("left", {}).get("role") == "after_status"
        absent = predicate.get("family") == "P01" and status in predicate.get("absent_statuses", [])
        if not _executed(record) or type(status) is not int or not (200 <= status < 300 or status_only and 400 <= status < 500 or absent):
            diagnostics.append({"reason_code": "temporal_observation_unavailable", "checkpoint_id": record.get("checkpoint_id")})
            continue
        usable.append(record)
    mode = requirement["observation_mode"]
    if mode not in {"returned_sample", "sampled"}:
        return _timestamped(requirement, predicate, action, usable, complete=complete, diagnostics=diagnostics)
    try:
        origin_key = {"ack": "receive_ns", "send": "send_ns"}[requirement.get("origin", "ack")]
        origin = _nanoseconds(action["timing"][origin_key])
        samples = []
        for record in usable:
            send = _nanoseconds(record["timing"]["send_ns"])
            receive = _nanoseconds(record["timing"]["receive_ns"])
            if send < origin or receive < send:
                raise ValueError("temporal_observation_clock_invalid")
            samples.append({"receive_offset_ns": receive - origin,
                            "satisfied": _atom(predicate, action, record["response"], record)})
        return evaluate_received_samples(requirement, samples, complete=complete, diagnostics=diagnostics)
    except (KeyError, TypeError, ValueError) as error:
        return _finish([_check("clock", None, str(error))], complete=False, diagnostics=diagnostics, counts={})


def temporal_predicate_result(predicate: Mapping[str, Any], evaluated: Mapping[str, Any]) -> dict[str, Any]:
    verdict = evaluated["protocol_verdict"]
    return {"family": predicate["family"],
            "status": "satisfied" if verdict == "validated" else "violated" if verdict == "refuted" else "not_evaluable",
            "observed": {**evaluated["observed"], "checks": evaluated["checks"],
                         "protocol_complete": evaluated["protocol_complete"], "diagnostics": evaluated["diagnostics"]},
            "reason_code": None if verdict in {"validated", "refuted"} else "temporal_evidence_unavailable"}


def validate_temporal_predicate_result(result: Mapping[str, Any]) -> None:
    observed = result["observed"]
    checks = observed["checks"]
    if not checks or len({row["check_id"] for row in checks}) != len(checks):
        raise ValueError("temporal_check_set_invalid")
    if type(observed["protocol_complete"]) is not bool or not isinstance(observed["diagnostics"], list):
        raise ValueError("temporal_completeness_invalid")
    if any(row["status"] not in {"satisfied", "violated", "not_evaluable"} or "reason_code" not in row for row in checks):
        raise ValueError("temporal_check_status_invalid")
    expected = ("violated" if any(row["status"] == "violated" for row in checks) else
                "satisfied" if observed["protocol_complete"] and not observed["diagnostics"] and all(row["status"] == "satisfied" for row in checks)
                else "not_evaluable")
    if result["status"] != expected:
        raise ValueError("temporal_check_reduction_drift")


def execute_temporal(material: Any, runtime: Any, *, artifact_writer: Any, output_level: str):
    from ..current_route_s import canonical_json_bytes
    from ..current_settle import route_observer_is_pure
    from .single_state import SingleStateCollectedEvidence

    del artifact_writer, output_level
    shape = material.execution_material["protocol_shape"]
    artifacts = dict(material.artifact_bytes)
    context, reset, rows = runtime.begin_arm(material, "temporal")
    artifacts.update(rows)
    setup, rows = runtime.execute_setup(context, "temporal_setup")
    artifacts.update(rows)
    protocol = {"reset": reset, "setup": setup, "observations": [], "diagnostics": []}
    healthy = all(_executed(row) for row in (reset, setup))
    if healthy and shape.get("roles", {}).get("before") is not None:
        before, rows = runtime.observe(context, "workflow_before")
        artifacts.update(rows)
        protocol["before"] = before
        healthy = _executed(before) and route_observer_is_pure(before)
    requirement = None
    if healthy:
        action, rows = runtime.execute_producer(context)
        artifacts.update(rows)
        protocol["producer"] = action
        healthy = _executed(action) and 200 <= action.get("transport_status", 0) < 300
        if healthy:
            try:
                requirement = resolve_temporal_requirement(shape["time_requirement"], action)
                offsets = temporal_send_offsets(requirement)
                plan = shape["observation_plan"]
                if [row["role"] for row in plan] != [f"D{i + 1}" for i in range(len(offsets))]:
                    raise ValueError("temporal_observation_plan_drift")
                origin_key = "send_ns" if requirement["origin"] == "send" else "receive_ns"
                # Event time is compared only by the evaluator's server clock;
                # local acknowledgement merely schedules the historical read.
                origin = _nanoseconds(action["timing"][origin_key])
                for step, offset in zip(plan, offsets):
                    runtime.temporal_wait_until(context, origin + offset)
                    record, rows = runtime.observe(context, step["role"])
                    artifacts.update(rows)
                    protocol["observations"].append(record)
                    if not _executed(record) or not route_observer_is_pure(record):
                        healthy = False
                        break
            except (KeyError, TypeError, ValueError) as error:
                healthy = False
                protocol["diagnostics"].append({"reason_code": str(error)})
    sessions = runtime.sessions()
    selected = [row for row in sessions if row.get("arm") == "temporal"]
    actors = {material.candidate["producer"]["actor_id"], *(row["actor"] for row in shape["observation_plan"])}
    identity = actors.issubset({row["actor_id"] for row in selected}) and all(row.get("reset_epoch") == reset.get("reset_epoch") and row.get("secret_values_present") is False for row in selected)
    if shape.get("identity_topology") is not None:
        identity = identity and runtime.verify_identity_topology(context, shape["identity_topology"])
    protocol.update(complete=healthy and len(protocol["observations"]) == len(shape["observation_plan"]), identity_verified=identity)
    evaluated = (evaluate_temporal_result(material.candidate["primary_predicate"], requirement, protocol) if requirement is not None else
                 _finish([_check("prerequisite", None, "temporal_prerequisite_unavailable")], complete=False,
                         diagnostics=protocol["diagnostics"] or [{"reason_code": "temporal_prerequisite_unavailable"}], counts={}))
    result = temporal_predicate_result(material.candidate["primary_predicate"], evaluated)
    common = {"candidate_id": material.candidate_id, "protocol_kind": "V8", "protocol_verdict": evaluated["protocol_verdict"],
              "claim_kind": evaluated["claim_kind"], "predicate_result": result, "failure_class": evaluated["failure_class"]}
    certificate = {"schema_version": "uisemtest-current-temporal-certificate-v1", **common,
                   "time_requirement": copy.deepcopy(shape["time_requirement"]), "observation_plan": copy.deepcopy(shape["observation_plan"]),
                   "qualification_gates": {"plan_complete": protocol["complete"], "identity_verified": identity}}
    evidence = {"schema_version": "uisemtest-current-temporal-evidence-v1", "candidate": copy.deepcopy(material.candidate),
                "protocol": protocol, "sessions": sessions, "time_requirement": copy.deepcopy(shape["time_requirement"]),
                "resolved_requirement": requirement}
    outcome = {"schema_version": "uisemtest-current-protocol-result-v1", **common,
               "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json", "certificate_ref": f"M12/{material.candidate_id}/certificate.json", "v1_legacy_outcome": None}
    return SingleStateCollectedEvidence(evidence, canonical_json_bytes(evidence), {}, artifacts, (), (), runtime.counts()), certificate, outcome
