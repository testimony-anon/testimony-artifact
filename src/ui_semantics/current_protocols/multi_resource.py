"""Finite C14 joint observations; sequential reads never imply an atomic snapshot."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from functools import partial
from typing import Any

from ..current_route_s import canonical_json_bytes
from ..current_settle import route_observer_is_pure
from ..dsl import _resolve_value_ref, _strict_equal, evaluate_predicate_result, merge_followup_observation
from ..route_s_capture_redaction import SensitiveMaterialUnavailable, reject_redacted_predicate_dependencies
from .metamorphic_query import evaluate_query_plan_predicate, query_request_observation
from .single_state import SingleStateCollectedEvidence


def evaluate_multi_resource_result(predicate: Mapping[str, Any], joint_observation: Mapping[str, Any],
                                   observation_plan: list[dict[str, Any]], records: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate frozen resources, consistency, collection closure and exact arithmetic."""
    reason = None
    observations, sources = {}, {}
    ordered = [step["role"] for step in observation_plan]
    rows = records.get("observations", [])
    if not records.get("complete") or len(rows) != len(ordered):
        reason = "joint_observation_plan_incomplete"
    elif records.get("identity_verified") is not True:
        reason = "joint_observation_identity_unverified"
    for step, record in zip(observation_plan, rows):
        role = step["role"]
        if record.get("state") != "executed" or record.get("status") != "pass" or not route_observer_is_pure(record):
            reason = "joint_observer_unavailable"
            continue
        if record.get("request_ref") != step["request_ref"] or record.get("actor_id") != step["actor"]:
            reason = "joint_observation_identity_mismatch"
            continue
        response = record.get("response", {})
        if type(response.get("status")) is not int or not 200 <= response["status"] < 300 or "body" not in response:
            reason = "joint_observer_response_unavailable"
            continue
        observations[role] = response
        observations[role + "_request"] = query_request_observation(record)
        sources[role] = ((record, "response"),)
        sources[role + "_request"] = tuple((record, channel) for channel in ("request_query", "request", "request_headers", "request_path"))
    diagnostics = copy.deepcopy(records.get("diagnostics", []))
    try:
        if reason is None and joint_observation["consistency"] != "no_competing_writes_workflow":
            refs = joint_observation["consistency_refs"]
            if {ref["role"] for ref in refs} != set(ordered):
                reason = "joint_consistency_roles_unclosed"
            for phase in ("before", "after"):
                selected = [ref for ref in refs if ref["role"] in {step["role"] for step in observation_plan if step["phase"] == phase}]
                values = []
                for ref in selected:
                    reject_redacted_predicate_dependencies(ref, sources)
                    values.append(_resolve_value_ref(ref, observations))
                if values and not all(_strict_equal(values[0], value) for value in values[1:]):
                    reason = "joint_consistency_not_established"
        atom = copy.deepcopy(dict(predicate))
        scope = joint_observation["query_scope"]
        if reason is None and scope["scope"] == "finite_query_plan":
            collection_roles = {role for closure in scope["closures"] for role in closure["roles"]}
            plan = [row for row in observation_plan if row["role"] in collection_roles]
            _, complete, extra = evaluate_query_plan_predicate(atom, plan, scope, observations, sources,
                plan_complete=True, evaluate_business=False)
            diagnostics.extend(extra)
            if not complete:
                reason = "joint_collection_scope_incomplete"
            else:
                roles = [row["role"] for row in plan]
                merged = merge_followup_observation(atom, observations, roles=roles)
                observations[atom["collection"]["role"]] = merged
                sources[atom["collection"]["role"]] = tuple(source for role in roles for source in sources[role])
                atom["scope"] = "actual_response"
        if reason is None:
            evaluated = evaluate_predicate_result(atom, observations,
                dependency_checker=partial(reject_redacted_predicate_dependencies, sources=sources))
        else:
            evaluated = {"satisfied": None, "observed": {}, "reason_code": reason}
    except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
        evaluated = {"satisfied": None, "observed": {}, "reason_code": "joint_consistency_or_scope_unavailable"}
        diagnostics.append({"reason_code": type(error).__name__})
    observed = {**evaluated["observed"], "consistency": joint_observation["consistency"],
                "observation_count": len(rows), "diagnostics": diagnostics}
    return {"family": predicate["family"], "status": "satisfied" if evaluated["satisfied"] is True else "violated" if evaluated["satisfied"] is False else "not_evaluable",
            "observed": observed, "reason_code": evaluated["reason_code"]}


def execute_multi_resource(material: Any, runtime: Any, *, artifact_writer: Any, output_level: str):
    del artifact_writer, output_level
    shape = material.execution_material["protocol_shape"]
    plan = copy.deepcopy(shape["observation_plan"])
    artifacts = dict(material.artifact_bytes)
    context, reset, rows = runtime.begin_arm(material, "multi_resource")
    artifacts.update(rows)
    setup, rows = runtime.execute_setup(context, "joint_setup")
    artifacts.update(rows)
    protocol = {"reset": reset, "setup": setup, "observations": []}
    healthy = all(row.get("state") == "executed" and row.get("status") == "pass" for row in (reset, setup))
    action_sent = False
    for step in plan:
        if not healthy:
            break
        if step["phase"] == "after" and material.candidate.get("producer") is not None and not action_sent:
            action, rows = runtime.execute_producer(context)
            artifacts.update(rows)
            protocol["producer"] = action
            action_sent = True
            healthy = action.get("state") == "executed" and action.get("status") == "pass" and 200 <= action.get("transport_status", 0) < 300
            if not healthy:
                break
        record, rows = runtime.observe(context, step["role"])
        artifacts.update(rows)
        protocol["observations"].append(record)
        healthy = record.get("state") == "executed" and record.get("status") == "pass"
    sessions = runtime.sessions()
    actors = {row["actor"] for row in plan}
    selected = [row for row in sessions if row.get("arm") == "multi_resource"]
    identity = actors == {row["actor_id"] for row in selected} and all(row.get("reset_epoch") == reset.get("reset_epoch") and row.get("secret_values_present") is False for row in selected)
    evaluated = evaluate_multi_resource_result(material.candidate["primary_predicate"], shape["joint_observation"], plan,
        {**protocol, "complete": healthy and len(protocol["observations"]) == len(plan), "identity_verified": identity})
    verdict = "infrastructure_failed" if not healthy else {"satisfied": "validated", "violated": "refuted", "not_evaluable": "not_evaluable"}[evaluated["status"]]
    common = {"candidate_id": material.candidate_id, "protocol_kind": "V9", "protocol_verdict": verdict,
        "claim_kind": "joint_observation_confirmed" if verdict == "validated" else None,
        "predicate_result": evaluated, "failure_class": "observer_failure" if not healthy else "binding" if verdict == "not_evaluable" else None}
    certificate = {"schema_version": "uisemtest-current-joint-observation-certificate-v1", **common,
        "observation_plan": plan, "joint_observation": copy.deepcopy(shape["joint_observation"]),
        "qualification_gates": {"plan_complete": healthy and len(protocol["observations"]) == len(plan), "identity_verified": identity}}
    evidence = {"schema_version": "uisemtest-current-joint-observation-evidence-v1", "candidate": copy.deepcopy(material.candidate),
        "protocol": protocol, "sessions": sessions, "observation_plan": plan, "joint_observation": copy.deepcopy(shape["joint_observation"])}
    result = {"schema_version": "uisemtest-current-protocol-result-v1", **common,
        "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json", "certificate_ref": f"M12/{material.candidate_id}/certificate.json", "v1_legacy_outcome": None}
    return SingleStateCollectedEvidence(evidence, canonical_json_bytes(evidence), {}, artifacts, (), (), runtime.counts()), certificate, result
