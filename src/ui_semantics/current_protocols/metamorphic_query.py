"""Metamorphic-query protocol over one frozen read-only query plan."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..current_route_s import canonical_json_bytes, validate_proven_path_change
from ..current_settle import route_observer_is_pure
from ..dsl import (
    _strict_equal, evaluate_predicate_result, get_path, merge_followup_observation,
    parse_request_value, request_numeric_observation,
)
from ..route_s_capture_redaction import (
    SensitiveMaterialUnavailable,
    predicate_value_refs,
    sensitive_field_category,
    reject_redacted_predicate_dependencies,
)


@dataclass(frozen=True)
class MetamorphicQueryCollectedEvidence:
    evidence: dict[str, Any]
    execution_evidence_bytes: bytes
    artifact_hashes: dict[str, str]
    artifact_bytes: dict[str, bytes]
    partial_records: tuple[dict[str, Any], ...]
    artifact_write_sequence: tuple[str, ...]
    runtime_counts: dict[str, int]
    volatile_sensitive_values: tuple[str, ...] = ()


def execute_metamorphic_query(
    material: Any,
    runtime: Any,
    *,
    artifact_writer: Callable[[str, bytes], None],
    output_level: str,
) -> tuple[MetamorphicQueryCollectedEvidence, dict[str, Any], dict[str, Any]]:
    del artifact_writer, output_level
    artifacts = dict(material.artifact_bytes)

    context, reset, rows = runtime.begin_arm(material, "metamorphic_query")
    artifacts.update(rows)
    shape = material.execution_material["protocol_shape"]
    transform_kind = shape["transform_kind"]
    plan = copy.deepcopy(shape["query_plan"])
    protocol: dict[str, Any] = {"reset": copy.deepcopy(reset), "queries": []}
    failed_step = "reset" if _failed(reset) else None
    if failed_step is None:
        setup, rows = runtime.execute_setup(context, "query_setup")
        artifacts.update(rows)
        protocol["setup"] = copy.deepcopy(setup)
        if _failed(setup):
            failed_step = "setup"
    for step in plan:
        if failed_step is not None:
            break
        record, rows = runtime.observe(context, step["role"])
        artifacts.update(rows)
        protocol["queries"].append(copy.deepcopy(record))
        if _failed(record):
            failed_step = step["role"]
    protocol.setdefault("setup", {"state": "not_executed", "reason_code": "prior_failure"})

    predicate = copy.deepcopy(material.candidate["primary_predicate"])
    observations: dict[str, Any] = {}
    sources: dict[str, tuple[Any, ...]] = {}
    diagnostics: list[dict[str, Any]] = []
    identity_closed = True
    observer_pure = True
    read_only = True
    for step, record in zip(plan, protocol["queries"]):
        role = step["role"]
        if _failed(record):
            diagnostics.append({"role": role, "reason_code": "query_observer_failed"})
            continue
        binding = material.execution_binding["payload"]["observations"][role]
        expected_actor = shape["roles"][role]["actor"]
        valid_identity = (
            record.get("actor_id") == expected_actor
            and record.get("request_ref") == step["request_ref"]
        )
        pure = route_observer_is_pure(record)
        safe_read = _is_read_only_binding(
            binding, mechanically_read=step["request_ref"] in shape.get("read_execution_evidence", {}),
        )
        identity_closed &= valid_identity
        observer_pure &= pure
        read_only &= safe_read
        if not valid_identity or not pure or not safe_read:
            diagnostics.append({"role": role, "reason_code": "query_observation_untrusted"})
            continue
        response = record.get("response")
        if (
            not isinstance(response, Mapping) or "body" not in response
            or type(response.get("status")) is not int or not 200 <= response["status"] < 300
        ):
            failed_step = role
            diagnostics.append({"role": role, "reason_code": "query_response_incomplete"})
            continue
        observations[role] = copy.deepcopy(response)
        sources[role] = ((record, "response"),)
        observations[role + "_request"] = query_request_observation(record)
        sources[role + "_request"] = tuple(
            (record, channel) for channel in ("request_query", "request", "request_headers", "request_path")
        )
    complete = failed_step is None and len(observations) == 2 * len(plan)
    session_consistent = _single_query_session(runtime.sessions(), material, plan)
    predicate_result, scope_complete, diagnostics = evaluate_query_plan_predicate(
        predicate, plan, shape["query_scope"],
        observations, sources, plan_complete=complete, diagnostics=diagnostics,
        query_transform=shape["query_transform"],
        query_endpoints=material.execution_binding["payload"]["observations"],
    )
    if not session_consistent:
        predicate_result = None
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"
    elif predicate_result["status"] == "violated":
        verdict, claim_kind, failure_class = "refuted", None, None
    elif failed_step is not None:
        verdict, claim_kind, failure_class = (
            "infrastructure_failed", None,
            "setup_failure" if failed_step in {"reset", "setup"} else "observer_failure",
        )
    elif not identity_closed or not read_only or not observer_pure:
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"
    elif predicate_result["status"] == "satisfied" and complete and scope_complete:
        verdict, claim_kind, failure_class = "validated", "metamorphic_confirmed", None
    else:
        verdict, claim_kind, failure_class = "not_evaluable", None, "binding"
    protocol["diagnostics"] = diagnostics

    gates = {
        "query_plan_complete": complete,
        "same_actor_session": session_consistent,
        "read_only": read_only,
        "query_scope_complete": scope_complete,
        "observation_identity_closed": identity_closed,
        "observer_pure": observer_pure,
    }
    evidence = {
        "schema_version": "uisemtest-current-metamorphic-query-execution-evidence-v1",
        "candidate": copy.deepcopy(material.candidate),
        "transform_kind": transform_kind,
        "query_plan": plan,
        "query_scope": copy.deepcopy(shape["query_scope"]),
        "query_transform": copy.deepcopy(shape["query_transform"]),
        "protocol": protocol,
        "sessions": copy.deepcopy(runtime.sessions()),
        "qualification_gates": gates,
    }
    result = {
        "schema_version": "uisemtest-current-protocol-result-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V3",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": predicate_result,
        "failure_class": failure_class,
        "evidence_ref": f"M12/{material.candidate_id}/execution_evidence.json",
        "certificate_ref": f"M12/{material.candidate_id}/certificate.json",
        "v1_legacy_outcome": None,
    }
    certificate = {
        "schema_version": "uisemtest-current-metamorphic-query-certificate-v1",
        "candidate_id": material.candidate_id,
        "protocol_kind": "V3",
        "protocol_verdict": verdict,
        "claim_kind": claim_kind,
        "predicate_result": copy.deepcopy(predicate_result),
        "failure_class": failure_class,
        "transform_kind": transform_kind,
        "query_plan": plan,
        "query_scope": copy.deepcopy(shape["query_scope"]),
        "query_transform": copy.deepcopy(shape["query_transform"]),
        "diagnostics": copy.deepcopy(diagnostics),
        "qualification_gates": gates,
    }
    payload = canonical_json_bytes(evidence)
    return (
        MetamorphicQueryCollectedEvidence(
            evidence=evidence,
            execution_evidence_bytes=payload,
            artifact_hashes={}, artifact_bytes=artifacts,
            partial_records=(), artifact_write_sequence=(),
            runtime_counts=runtime.counts(),
        ),
        certificate,
        result,
    )


def query_request_observation(record: Mapping[str, Any]) -> dict[str, Any]:
    """Expose only parameters actually sent by this query, never recorded defaults."""
    transport = record.get("physical_transport_request") or {}
    metadata = record.get("physical_transport_metadata") or {}
    value = request_numeric_observation(record, transport.get("body"))
    value["request"] = {
        **{target: copy.deepcopy(metadata[source]) for source, target in (
            ("query", "query"), ("request_headers", "headers"),
        ) if source in metadata},
        **{key: copy.deepcopy(transport[key]) for key in ("body", "path")
           if key in transport},
    }
    return value


def _without_query_parameters(request: Mapping[str, Any], location: str, paths: list[str]) -> dict[str, Any]:
    """Compare actual selectors after removing only declared traversal fields."""
    selected = {key: copy.deepcopy(request[key]) for key in ("query", "body", "path") if key in request}
    for path in paths:
        if path == "$":
            selected[location] = None
            continue
        node = selected.get(location)
        tokens = path.removeprefix("$.").split(".")
        for token in tokens[:-1]:
            if isinstance(node, dict):
                node = node.get(token)
            elif isinstance(node, list) and token.isdecimal() and int(token) < len(node):
                node = node[int(token)]
            else:
                node = None
                break
        if isinstance(node, dict):
            node.pop(tokens[-1], None)
        elif isinstance(node, list) and tokens[-1].isdecimal() and int(tokens[-1]) < len(node):
            node[int(tokens[-1])] = None
    return selected



def _exact_request_selectors(observation: Mapping[str, Any]) -> dict[str, Any]:
    request = copy.deepcopy(observation.get("request"))
    if not isinstance(request, dict) or not {"query", "body", "headers", "path"} <= request.keys():
        raise KeyError("query_actual_request_unavailable")
    if hasattr(observation, "numeric_body"):
        request["body"] = copy.deepcopy(observation.numeric_body)
    return request


def _request_selectors_have_float(value: Any) -> bool:
    if type(value) is float:
        return True
    if isinstance(value, dict):
        return any(_request_selectors_have_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_request_selectors_have_float(item) for item in value)
    return False


def _query_actual_transform_reason(
    declaration: Mapping[str, Any], roles: list[str], observations: Mapping[str, Any],
    sources: Mapping[str, tuple[Any, ...]], endpoints: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Check only sent selectors; the frozen hypothesis supplies business meaning."""
    selectors = []
    actual_paths = {}
    declared_key_present = False
    for role in roles:
        if role not in observations:
            continue  # A missing later response is handled by plan completeness.
        request_role = role + "_request"
        try:
            request = _exact_request_selectors(observations.get(request_role, {}))
        except KeyError:
            return "query_actual_request_unavailable"
        for location in ("query", "body", "path"):
            reject_redacted_predicate_dependencies(
                {"role": request_role, "location": location, "path": "$"}, sources,
            )
        if not isinstance(request["headers"], Mapping):
            return "query_actual_request_unavailable"
        headers = {}
        for name, value in request["headers"].items():
            # Authentication values are governed by the existing same-session
            # binding; their capture placeholders are not selector operands.
            if sensitive_field_category(name) in {"authorization", "cookie", "credential", "session", "token"}:
                continue
            reject_redacted_predicate_dependencies(
                {"role": request_role, "location": "headers", "path": "$." + name}, sources,
            )
            normalized_name = name.casefold()
            if normalized_name in headers:
                return "query_header_name_ambiguous"
            headers[normalized_name] = copy.deepcopy(value)
        location = declaration["location"]
        if location == "query":
            if not isinstance(request["query"], dict):
                return "query_actual_request_unavailable"
            for key in declaration["keys"]:
                declared_key_present |= key in request["query"]
                request["query"].pop(key, None)
            selector = _without_query_parameters(request, location, [])
        else:
            for key in declaration["keys"]:
                try:
                    get_path(request["body"], key)
                    declared_key_present = True
                except KeyError:
                    pass
            selector = _without_query_parameters(request, location, declaration["keys"])
        selector["headers"] = headers
        endpoint = endpoints.get(role)
        if endpoint is not None:
            records = sources.get(role) or sources.get(request_role) or ()
            record = records[0][0] if records else {}
            canonical = record.get("request") or record.get("transport_request") or {}
            if not isinstance(canonical.get("path"), str):
                return "query_endpoint_path_unavailable"
            if canonical["path"] != endpoint.get("path"):
                try:
                    validate_proven_path_change(
                        str(endpoint.get("path")), canonical["path"],
                        record.get("binding_events", record.get("resource_binding_events", [])), endpoint,
                    )
                except ValueError:
                    return "query_endpoint_path_unproven"
            # Distinct admitted operations retain their own path binding. Queries
            # of one operation must still address the same actual resource.
            operation = (endpoint.get("method"), endpoint.get("path"))
            if operation in actual_paths and actual_paths[operation] != request["path"]:
                return "query_selector_drift"
            actual_paths[operation] = request["path"]
            selector.pop("path", None)
        if _request_selectors_have_float(selector):
            return "query_request_precision_source_missing"
        selectors.append(selector)
    if not declared_key_present:
        return "query_transform_key_unavailable"
    if any(not _strict_equal(selectors[0], row) for row in selectors[1:]):
        return "query_selector_drift"
    return None



def _automatic_partition_request_reason(
    plan: list[dict[str, Any]], observations: Mapping[str, Any],
    sources: Mapping[str, tuple[Any, ...]], endpoints: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Bind automatic pagination to its sent pages without claiming a full scope."""
    if len(plan) < 3 or plan[0].get("role") != "source_query":
        return None
    base = plan[0].get("query")
    followups = [step.get("query") for step in plan[1:]]
    if not isinstance(base, dict) or "page" in base or not all(
        isinstance(query, dict) and "page" in query
        and _strict_equal({key: value for key, value in query.items() if key != "page"}, base)
        for query in followups
    ):
        return None
    roles = [step["role"] for step in plan]
    reason = _query_actual_transform_reason(
        {"location": "query", "keys": ["page"]}, roles, observations, sources, endpoints,
    )
    if reason is not None:
        return reason
    for step in plan:
        if step["role"] not in observations:
            continue
        actual = observations[step["role"] + "_request"]["request"]["query"]
        frozen = step["query"]
        if ("page" in actual) != ("page" in frozen) or (
            "page" in frozen and not _strict_equal(actual["page"], frozen["page"])
        ):
            return "query_partition_request_drift"
    return None


def _query_common_parameter_reason(
    predicate: Mapping[str, Any], roles: list[str], observations: Mapping[str, Any],
    sources: Mapping[str, tuple[Any, ...]],
) -> str | None:
    if predicate.get("family") != "forall" or predicate.get("scope") != "finite_query_plan":
        return None
    for ref in predicate_value_refs(predicate):
        if ref.get("role") != "source_query_request" or ref.get("location") not in {"query", "body"}:
            continue
        values = []
        for role in roles:
            if role not in observations:
                continue
            request_role = role + "_request"
            request_observation = observations.get(request_role, {})
            request = request_observation.get("request", {})
            location = ref["location"]
            if location not in request:
                return "query_actual_request_unavailable"
            reject_redacted_predicate_dependencies({**ref, "role": request_role}, sources)
            root = getattr(request_observation, "numeric_body", request[location]) if location == "body" else request[location]
            try:
                value = get_path(root, ref["path"])
            except KeyError:
                return "query_common_parameter_unavailable"
            if _request_selectors_have_float(value):
                return "query_request_precision_source_missing"
            values.append(value)
        if any(not _strict_equal(values[0], value) for value in values[1:]):
            return "query_common_parameter_drift"
    return None


def _query_traversal_reason(
    closure: Mapping[str, Any], observations: Mapping[str, Any], sources: Mapping[str, tuple[Any, ...]],
) -> str | None:
    roles = closure["roles"]
    rule = closure["traversal"]["value"]
    if not isinstance(rule, Mapping):
        return "query_traversal_rule_unavailable"
    kind = rule.get("kind")
    requests = []
    for role in roles:
        request = observations.get(role + "_request", {}).get("request")
        if not isinstance(request, Mapping) or not any(key in request for key in ("query", "body", "path")):
            return "query_actual_request_unavailable"
        # Sanitized selectors cannot prove that two queries select the same scope.
        for location in ("query", "body", "path"):
            if location in request:
                reject_redacted_predicate_dependencies(
                    {"role": role + "_request", "location": location, "path": "$"}, sources,
                )
        requests.append(request)
    if kind == "single_response":
        return None if len(roles) == 1 and closure["termination"]["kind"] == "total_count" else "query_single_response_scope_invalid"
    if kind not in {"page_number", "offset", "cursor"}:
        return "query_traversal_rule_unavailable"
    location = rule["location"]
    parameter = rule["parameter"]
    paths = [parameter, *([rule["limit_parameter"]] if kind == "offset" else [])]
    selectors = [_without_query_parameters(request, location, paths) for request in requests]
    if any(not _strict_equal(selectors[0], selector) for selector in selectors[1:]):
        return "query_selector_drift"
    expected_offset = 0
    for index, (role, request) in enumerate(zip(roles, requests)):
        if location not in request:
            return "query_actual_request_unavailable"
        try:
            actual = get_path(request[location], parameter)
        except KeyError:
            if kind == "cursor" and index == 0:
                actual = None
            else:
                return "query_traversal_parameter_missing"
        if kind == "page_number":
            actual = parse_request_value(actual, "integer", location)
            if actual != rule["first"] + index:
                return "query_page_sequence_incomplete"
        elif kind == "offset":
            actual = parse_request_value(actual, "integer", location)
            limit = parse_request_value(get_path(request[location], rule["limit_parameter"]), "integer", location)
            if limit <= 0 or actual != expected_offset:
                return "query_offset_sequence_incomplete"
            expected_offset += limit
        elif index == 0:
            if actual is not None:
                return "query_initial_cursor_not_empty"
        else:
            previous = roles[index - 1]
            reject_redacted_predicate_dependencies(
                {"role": previous, "path": rule["next_path"]}, sources,
            )
            cursor = get_path(observations[previous]["body"], rule["next_path"])
            if cursor is None or not _strict_equal(actual, cursor):
                return "query_cursor_sequence_incomplete"
    return None


def evaluate_query_plan_predicate(
    predicate: Mapping[str, Any],
    plan: list[dict[str, Any]],
    query_scope: Mapping[str, Any],
    observations: Mapping[str, Any],
    sources: Mapping[str, tuple[Any, ...]],
    *,
    plan_complete: bool,
    diagnostics: list[dict[str, Any]] | None = None,
    evaluate_business: bool = True,
    query_transform: Mapping[str, Any] | None = None,
    query_endpoints: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], bool, list[dict[str, Any]]]:
    """Evaluate the same frozen query proposition against M12 or M14 responses.

    A bounded request list and a proved terminating collection are separate.
    Partial uniqueness, universal checks, and disjointness retain their concrete
    counterexamples; incomplete collections cannot prove an equality or inclusion.
    """
    diagnostics = copy.deepcopy(diagnostics or [])
    observations = dict(observations)
    sources = dict(sources)
    ordered_roles = [str(step["role"]) for step in plan]
    followup_roles = [role for role in ordered_roles if role.startswith("followup_query:")]
    if len(followup_roles) == 1:
        request_role = followup_roles[0] + "_request"
        if request_role in observations:
            observations["followup_query_request"] = observations[request_role]
            sources["followup_query_request"] = sources.get(request_role, ())
    request_conditions_complete = True
    try:
        request_reason = _query_common_parameter_reason(predicate, ordered_roles, observations, sources)
        if request_reason is None:
            request_reason = (
                _query_actual_transform_reason(
                    query_transform, ordered_roles, observations, sources, query_endpoints or {},
                ) if query_transform is not None else
                _automatic_partition_request_reason(plan, observations, sources, query_endpoints or {})
            )
    except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
        request_reason = _predicate_failure_reason(error)
    if request_reason is not None:
        request_conditions_complete = False
        diagnostics.append({"reason_code": request_reason})
    scope_complete = plan_complete and request_conditions_complete
    if not plan_complete:
        diagnostics.append({"reason_code": "query_plan_incomplete"})
    if query_scope.get("scope") == "finite_query_plan":
        closures = query_scope.get("closures", [])
        covered = [role for closure in closures for role in closure["roles"]]
        if not closures or set(covered) != set(ordered_roles):
            scope_complete = False
            diagnostics.append({"reason_code": "query_scope_roles_unclosed"})
        for index, closure in enumerate(closures):
            termination = closure["termination"]
            roles = closure["roles"]
            reason = None
            try:
                if (
                    not roles or termination["ref"]["role"] != roles[-1]
                    or roles != [role for role in ordered_roles if role in roles]
                ):
                    raise ValueError("query_scope_order_invalid")
                available_roles = [role for role in roles if role in observations]
                traversal_reason = None
                if available_roles != roles[:len(available_roles)]:
                    traversal_reason = "query_traversal_response_gap"
                elif available_roles:
                    try:
                        traversal_reason = _query_traversal_reason(
                            {**closure, "roles": available_roles}, observations, sources,
                        )
                    except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
                        traversal_reason = _predicate_failure_reason(error)
                if traversal_reason is not None:
                    scope_complete = False
                    request_conditions_complete = False
                    diagnostics.append({"closure_index": index, "reason_code": traversal_reason})
                    continue
                if available_roles != roles:
                    raise KeyError("query_scope_response_missing")
                # Metadata is an execution premise, independently checked for
                # redaction and type before deciding that the scope is complete.
                dependency = {"family": "P21", "target": termination["ref"], "expected_type": termination["ref"]["value_type"]}
                reject_redacted_predicate_dependencies(dependency, sources)
                terminal = get_path(observations[roles[-1]]["body"], termination["ref"]["path"])
                for role in roles:
                    reject_redacted_predicate_dependencies(
                        {"family": "P21", "target": {"role": role, "path": closure["collection_path"], "value_type": "array"}, "expected_type": "array"}, sources,
                    )
                collections = [get_path(observations[role]["body"], closure["collection_path"]) for role in roles]
                if any(not isinstance(value, list) for value in collections):
                    raise TypeError("query_scope_requires_arrays")
                if termination["kind"] == "total_count":
                    if type(terminal) is not int or terminal < 0:
                        raise TypeError("query_total_requires_nonnegative_integer")
                    reached = sum(len(value) for value in collections) == terminal
                elif termination["kind"] == "terminal_value":
                    atom = {"family": "P02", "left": termination["ref"], "operator": "eq", "right": termination["expected"]}
                    reached = evaluate_predicate_result(atom, observations)["satisfied"] is True
                else:
                    raise ValueError("query_termination_unsupported")
                if not reached:
                    reason = "query_termination_not_reached"
            except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
                reason = _predicate_failure_reason(error)
            if reason is not None:
                scope_complete = False
                diagnostics.append({"closure_index": index, "reason_code": reason})

    merged_bindings: list[dict[str, Any]] = []
    aggregate_incomplete = False
    if predicate.get("family") in {"forall", "P15"} and predicate["collection"]["role"] == "followup_query":
        roles = [role for role in ordered_roles if predicate["family"] == "forall" or role.startswith("followup_query:")]
        path = predicate["collection"]["path"]
        available = []
        for role in roles:
            try:
                value = get_path(observations[role]["body"], path)
                if not isinstance(value, list):
                    raise TypeError("query_collection_requires_array")
            except (KeyError, TypeError):
                aggregate_incomplete = True
                diagnostics.append({"role": role, "reason_code": "query_collection_unavailable"})
                continue
            available.append(role)
            merged_bindings.extend({"role": role, "path": f"{path}.{index}"} for index in range(len(value)))
        observations["followup_query"] = merge_followup_observation(dict(predicate), observations, roles=available)
        sources["followup_query"] = tuple(item for role in available for item in sources.get(role, ()))
        if aggregate_incomplete:
            scope_complete = False

    def check_dependencies(atom: Mapping[str, Any], *, item_bindings: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        bindings = copy.deepcopy(item_bindings or {})
        binding = bindings.get("item")
        if binding and binding.get("role") == "followup_query":
            prefix = str(predicate["collection"]["path"]) + "."
            index = int(str(binding["path"])[len(prefix):])
            bindings["item"] = merged_bindings[index]
        if atom.get("role") == "followup_query" and predicate.get("collection") is not None:
            prefix = str(predicate["collection"]["path"]) + "."
            path = str(atom.get("path", ""))
            if path.startswith(prefix):
                index, separator, suffix = path[len(prefix):].partition(".")
                if index.isdecimal():
                    origin = merged_bindings[int(index)]
                    atom = {**atom, "role": origin["role"], "path": origin["path"] + (separator + suffix if separator else "")}
        reject_redacted_predicate_dependencies(atom, sources, item_bindings=bindings)

    evaluated = (
        evaluate_predicate_result(predicate, observations, dependency_checker=check_dependencies)
        if evaluate_business else
        {"satisfied": None, "observed": {}, "reason_code": "rehearsal_predicate_not_evaluated"}
    )
    satisfied = evaluated["satisfied"]
    if not scope_complete:
        monotone_counterexample = (
            predicate["family"] in {"P15", "forall"}
            or predicate["family"] == "P18" and predicate["operator"] == "pairwise_disjoint"
            or predicate["family"] == "P16" and any(
                check.get("check_id") == "order" and check.get("satisfied") is False
                for check in evaluated["observed"].get("checks", [])
            )
        )
        if not request_conditions_complete or satisfied is not False or not monotone_counterexample:
            satisfied = None
            evaluated["reason_code"] = "query_scope_incomplete"
    observed = copy.deepcopy(evaluated["observed"])
    if diagnostics:
        observed.setdefault("diagnostics", []).extend(diagnostics)
    return ({
        "family": predicate["family"],
        "status": "satisfied" if satisfied is True else "violated" if satisfied is False else "not_evaluable",
        "observed": observed,
        "reason_code": evaluated["reason_code"],
    }, scope_complete, diagnostics)


def _single_query_session(sessions: list[Mapping[str, Any]], material: Any, plan: list[dict[str, Any]]) -> bool:
    actors = {
        material.execution_material["protocol_shape"]["roles"][step["role"]]["actor"]
        for step in plan
    }
    rows = [
        row
        for row in sessions
        if row.get("arm") == "metamorphic_query"
        and row.get("actor_id") in actors
    ]
    return len(actors) == 1 and len(rows) == 1 and rows[0].get("actor_id") in actors


def _failed(record: Mapping[str, Any]) -> bool:
    return record.get("state") != "executed" or record.get("status") != "pass"


def _is_read_only_binding(
    value: Mapping[str, Any], *, mechanically_read: bool = False
) -> bool:
    method = str(value.get("method") or "").upper()
    return method in {"GET", "HEAD", "OPTIONS"} or (
        method == "POST"
        and (
            value.get("graphql_operation_kind") == "query"
            or mechanically_read
        )
    )


def _predicate_failure_reason(error: BaseException) -> str:
    if isinstance(error, SensitiveMaterialUnavailable):
        return "sensitive_material_unavailable"
    if isinstance(error, KeyError):
        return "path_missing"
    if isinstance(error, TypeError):
        return "type_mismatch"
    return "identity_missing"
