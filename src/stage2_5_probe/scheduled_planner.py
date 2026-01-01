"""013-D operation probe candidate planner.

This module is intentionally separate from the legacy standalone planner. It
plans auditable scheduled-discovery candidates without changing the default
Stage 2.5 probing pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

from oas_naming import operation_id as make_operation_id

from .initial_valueflow import (
    AUTHORIZATION_HEADER,
    InitialValueFlow,
    InitialValueFlowSelection,
    RecordedOperation,
    literal_parameters,
    recorded_operations,
    select_initial_value_flows_for_scheduled_planning,
)
from .loader import Stage25Inputs
from .scheduled import ScheduledProbePlan
from .write_materials import (
    WriteBodyMaterial,
    mutate_recorded_body_template,
)

OPERATION_PROBE_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"]
SAFE_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
BODY_BEARING_METHODS = {"POST", "PUT", "PATCH"}
AMBIGUOUS_INITIAL_VALUE_FLOW = "ambiguous_initial_value_flow"


@dataclass
class OperationProbePlanResult:
    plans: list[ScheduledProbePlan] = field(default_factory=list)
    not_executed: list[dict] = field(default_factory=list)

    @property
    def probes(self) -> list[ScheduledProbePlan | dict]:
        return [*self.plans, *self.not_executed]


@dataclass(frozen=True)
class _WriteBodyPlan:
    source: str | None
    material: WriteBodyMaterial

    @property
    def body_text(self) -> str:
        return self.material.body_text

    @property
    def value_basis(self) -> str:
        return self.material.value_basis

    @property
    def generated_fields(self) -> list[str]:
        return self.material.generated_fields


@dataclass(frozen=True)
class _DeletePlanSupport:
    supporting_plans: tuple[ScheduledProbePlan, ...] = ()
    delete_plan: ScheduledProbePlan | None = None
    blocked_reason: str | None = None


def plan_scheduled_operation_probes(inp: Stage25Inputs) -> OperationProbePlanResult:
    """Generate 013-D operation method-gap candidates.

    First cut:
    - GET/HEAD/OPTIONS with a concrete same-resource URL become scheduled plans.
    - POST with a reusable body and collection path may become a scheduled plan.
    - PUT/PATCH without enough same-resource/fresh anchor are recorded as not_executed.
    - DELETE is not sent unless a later planner can prove a fresh anchor.
    """
    out = OperationProbePlanResult()
    recorded = recorded_operations(inp)
    initial_selection = select_initial_value_flows_for_scheduled_planning(inp)
    planned_by_method_and_path: dict[tuple[str, str], ScheduledProbePlan] = {}
    cached_creator_plans: dict[str, ScheduledProbePlan | str | None] = {}

    def add_plan(plan: ScheduledProbePlan) -> None:
        if any(existing.probe_id == plan.probe_id for existing in out.plans):
            return
        out.plans.append(plan)
        if plan.canonical_path:
            planned_by_method_and_path[(plan.method.upper(), plan.canonical_path)] = plan

    for canonical_path in sorted(inp.paths):
        info = inp.paths[canonical_path]
        observed = {m.upper() for m in info.observed_methods}
        anchor_entry_id = _first_observation_ref(inp.initial_oas, canonical_path)
        concrete_url = _first_concrete_url(info.concrete_urls)
        reuse_ref, reuse_body = info.reusable_write_body

        for method in OPERATION_PROBE_METHODS:
            if method in observed:
                continue
            generation_basis = _generation_basis(method, canonical_path, anchor_entry_id)
            operation_id = make_operation_id(method, canonical_path)

            if method in SAFE_READ_METHODS:
                if not concrete_url:
                    out.not_executed.append(_not_executed_record(
                        method,
                        canonical_path,
                        operation_id,
                        generation_basis,
                        "missing_concrete_url",
                    ))
                    continue
                if not anchor_entry_id:
                    out.not_executed.append(_not_executed_record(
                        method,
                        canonical_path,
                        operation_id,
                        generation_basis,
                        "missing_same_resource_anchor",
                    ))
                    continue
                out.plans.append(ScheduledProbePlan(
                    probe_id=_probe_id(method, canonical_path),
                    method=method,
                    canonical_path=canonical_path,
                    candidate_url=concrete_url,
                    operation_id=operation_id,
                    prefix_steps=[],
                    bindings=[],
                    generation_basis=generation_basis,
                    schedule_kind="same_resource_anchor",
                    anchor_entry_id=anchor_entry_id,
                    checkpoint_type="none",
                    insertion_policy="after_anchor",
                    suffix_policy="not_applicable",
                ))
                continue

            if method == "DELETE":
                delete_support = _fresh_created_delete_plan(
                    inp,
                    recorded,
                    initial_selection,
                    canonical_path,
                    operation_id,
                    generation_basis,
                    anchor_entry_id,
                    planned_by_method_and_path,
                    cached_creator_plans,
                )
                if delete_support.delete_plan is not None:
                    for supporting_plan in delete_support.supporting_plans:
                        add_plan(supporting_plan)
                    add_plan(delete_support.delete_plan)
                    continue
                out.not_executed.append(_not_executed_record(
                    method,
                    canonical_path,
                    operation_id,
                    generation_basis,
                    delete_support.blocked_reason or "unsafe_destructive_without_fresh_anchor",
                ))
                continue

            if method in BODY_BEARING_METHODS:
                body_material = _write_body_template(
                    inp,
                    canonical_path,
                    method,
                    reuse_ref,
                    reuse_body,
                )
                if body_material is None:
                    out.not_executed.append(_not_executed_record(
                        method,
                        canonical_path,
                        operation_id,
                        generation_basis,
                        "body_template_required_for_write_method",
                    ))
                    continue
                body_ref, body_template = body_material.source, body_material.body_text
                if "{" in canonical_path:
                    write_plan = _fresh_created_write_plan(
                        inp,
                        recorded,
                        initial_selection,
                        canonical_path,
                        method,
                        operation_id,
                        generation_basis,
                        anchor_entry_id,
                        body_ref,
                        body_material,
                    )
                    if isinstance(write_plan, ScheduledProbePlan):
                        out.plans.append(write_plan)
                        continue
                    out.not_executed.append(_not_executed_record(
                        method,
                        canonical_path,
                        operation_id,
                        generation_basis,
                        write_plan or "missing_same_resource_anchor",
                    ))
                    continue
                if not concrete_url:
                    out.not_executed.append(_not_executed_record(
                        method,
                        canonical_path,
                        operation_id,
                        generation_basis,
                        "missing_concrete_url",
                    ))
                    continue
                prefix_result = _auth_prefix_from_body_source(recorded, initial_selection, body_ref)
                if prefix_result.blocked_reason is not None:
                    out.not_executed.append(_not_executed_record(
                        method,
                        canonical_path,
                        operation_id,
                        generation_basis,
                        prefix_result.blocked_reason,
                    ))
                    continue
                prefix = prefix_result.plan or _PrefixPlan([], [], [], {}, {})
                probe_step = len(prefix.steps)
                add_plan(ScheduledProbePlan(
                    probe_id=_probe_id(method, canonical_path),
                    method=method,
                    canonical_path=canonical_path,
                    candidate_url=concrete_url,
                    operation_id=operation_id,
                    prefix_steps=prefix.steps,
                    bindings=[
                        *prefix.bindings,
                        *_auth_binding_from_body_source(recorded, initial_selection, body_ref, prefix, probe_step),
                    ],
                    generation_basis=generation_basis,
                    schedule_kind="checkpoint",
                    anchor_entry_id=anchor_entry_id,
                    checkpoint_entry_id=reuse_ref,
                    checkpoint_type="operation_based",
                    insertion_policy="after_checkpoint",
                    suffix_policy="skip",
                    body_template=body_template,
                    body_template_source=body_ref,
                    body_material_basis=body_material.value_basis,
                    generated_body_fields=body_material.generated_fields,
                    parameters=prefix.parameters,
                    prefix_body_templates=prefix.body_templates,
                ))
    return out


def _not_executed_record(
    method: str,
    canonical_path: str,
    operation_id: str,
    generation_basis: dict,
    reason: str,
) -> dict:
    return {
        "probe_id": _probe_id(method, canonical_path),
        "probe_kind": "operation",
        "execution_mode": "not_executed",
        "not_executed_reason": reason,
        "target": {
            "method": method,
            "canonical_path": canonical_path,
            "operation_id": operation_id,
        },
        "construction_basis": {
            "strategy": "scheduled_discovery",
            "generation_basis": generation_basis,
        },
        "schedule": {
            "schedule_kind": "not_scheduled",
            "checkpoint_type": "none",
            "insertion_policy": "not_scheduled",
            "suffix_policy": "not_applicable",
        },
        "admission": {
            "existence_evidence": "non_evidence",
            "admission_decision": "not_executed",
        },
    }


def _generation_basis(method: str, canonical_path: str, source_entry_id: str | None) -> dict:
    basis = {
        "generation_rule": "method_gap",
        "source_location": "oas_operation",
        "source_part": "method_gap",
        "derived_candidate": f"{method} {canonical_path}",
        "reason": f"{method} was not observed for this known endpoint",
    }
    if source_entry_id:
        basis["source_entry_id"] = source_entry_id
    return basis


def _first_observation_ref(initial_oas: dict, canonical_path: str) -> str | None:
    item = initial_oas.get("paths", {}).get(canonical_path, {})
    refs = []
    for op in item.values():
        for obs in op.get("x-carverflow-observations", []):
            if "run_id" in obs and "entry_index" in obs:
                refs.append((str(obs["run_id"]), int(obs["entry_index"])))
    if not refs:
        return None
    run_id, entry_index = sorted(refs)[0]
    return f"{run_id}#{entry_index}"


def _fresh_created_delete_plan(
    inp: Stage25Inputs,
    recorded: list[RecordedOperation],
    initial_selection: InitialValueFlowSelection,
    canonical_path: str,
    operation_id: str,
    generation_basis: dict,
    anchor_entry_id: str | None,
    planned_by_method_and_path: dict[tuple[str, str], ScheduledProbePlan],
    cached_creator_plans: dict[str, ScheduledProbePlan | str | None],
) -> _DeletePlanSupport:
    collection_path, param = _collection_and_trailing_param(canonical_path)
    if collection_path is None or param is None:
        return _DeletePlanSupport(blocked_reason="unsafe_destructive_without_fresh_anchor")

    creator_plan = planned_by_method_and_path.get(("POST", collection_path))
    supporting_plans: tuple[ScheduledProbePlan, ...] = ()
    if creator_plan is None:
        if collection_path not in cached_creator_plans:
            cached_creator_plans[collection_path] = _independent_creator_probe_plan(
                inp,
                recorded,
                initial_selection,
                collection_path,
            )
        cached = cached_creator_plans[collection_path]
        if isinstance(cached, ScheduledProbePlan):
            creator_plan = cached
            supporting_plans = (cached,)
        else:
            return _DeletePlanSupport(
                blocked_reason=cached or "unsafe_destructive_without_fresh_anchor"
            )

    basis = dict(generation_basis)
    basis["reason"] = (
        f"DELETE was not observed; fresh resource will be created by supporting POST probe "
        f"{creator_plan.probe_id} and deleted in the same turn if the creator succeeds"
    )

    return _DeletePlanSupport(
        supporting_plans=supporting_plans,
        delete_plan=ScheduledProbePlan(
            probe_id=_probe_id("DELETE", canonical_path),
            method="DELETE",
            canonical_path=canonical_path,
            operation_id=operation_id,
            prefix_steps=[],
            bindings=[],
            generation_basis=basis,
            schedule_kind="checkpoint",
            anchor_entry_id=anchor_entry_id,
            checkpoint_entry_id=creator_plan.probe_id,
            checkpoint_type="operation_based",
            checkpoint_method="POST",
            insertion_policy="after_checkpoint",
            suffix_policy="skip",
        ),
    )


def _independent_creator_probe_plan(
    inp: Stage25Inputs,
    recorded: list[RecordedOperation],
    initial_selection: InitialValueFlowSelection,
    collection_path: str,
) -> ScheduledProbePlan | str | None:
    creator = _creator_operation(inp, recorded, collection_path)
    if creator is None:
        return None
    body_material = _creator_body_template(creator, collection_path)
    if body_material is None:
        return "unsafe_destructive_without_fresh_anchor"
    prefix_result = _build_prefix_plan(creator, initial_selection)
    if prefix_result.blocked_reason is not None:
        return prefix_result.blocked_reason
    prefix = prefix_result.plan
    if prefix is None:
        return None
    creator_step = prefix.step_by_ref[creator.ref]
    probe_step = len(prefix.steps[:creator_step])
    probe_parameters = _copied_probe_parameters(prefix.parameters, creator_step, probe_step)
    probe_bindings = _copied_probe_bindings(prefix.bindings, creator_step, probe_step)
    covered_path_fields = {
        binding["to_field"]
        for binding in probe_bindings
        if binding.get("to_location") == "path"
    }
    unsafe_path_fields = {
        parameter["to_field"]
        for parameter in probe_parameters
        if parameter.get("to_location") == "path"
        and parameter.get("to_field") not in covered_path_fields
    }
    if unsafe_path_fields:
        return "unsafe_destructive_without_fresh_anchor"
    probe_parameters = [
        parameter
        for parameter in probe_parameters
        if not (
            parameter.get("to_location") == "path"
            and parameter.get("to_field") in covered_path_fields
        )
    ]
    basis = {
        "generation_rule": "oas_destructive_probe_candidate",
        "source_location": "oas_operation",
        "source_part": "probe_plan",
        "derived_candidate": f"POST {collection_path}",
        "reason": (
            f"observed POST {collection_path} is replayed as an independent fresh creator "
            "probe so destructive method-gap candidates can bind to a same-turn created resource"
        ),
    }
    return ScheduledProbePlan(
        probe_id=_creator_probe_id(collection_path),
        method="POST",
        canonical_path=collection_path,
        candidate_url=(
            _first_concrete_url(inp.paths.get(collection_path).concrete_urls)
            if collection_path in inp.paths and "{" not in collection_path and "}" not in collection_path
            else None
        ),
        operation_id=make_operation_id("POST", collection_path),
        prefix_steps=prefix.steps[:creator_step],
        bindings=[
            *[binding for binding in prefix.bindings if binding.get("to_step", 0) < creator_step],
            *probe_bindings,
        ],
        parameters=[
            *[parameter for parameter in prefix.parameters if parameter.get("to_step", 0) < creator_step],
            *probe_parameters,
        ],
        generation_basis=basis,
        schedule_kind="checkpoint",
        anchor_entry_id=_first_observation_ref(inp.initial_oas, collection_path),
        checkpoint_entry_id=creator.ref,
        checkpoint_type="operation_based",
        checkpoint_method="POST",
        insertion_policy="after_checkpoint",
        suffix_policy="not_applicable",
        body_template=body_material.body_text,
        body_template_source=body_material.source or creator.ref,
        body_material_basis=body_material.value_basis,
        generated_body_fields=body_material.generated_fields,
        prefix_body_templates={
            step: body
            for step, body in prefix.body_templates.items()
            if step < creator_step
        },
    )


def _recorded_state_delete_plan(
    recorded: list[RecordedOperation],
    initial_selection: InitialValueFlowSelection,
    canonical_path: str,
    operation_id: str,
    generation_basis: dict,
    anchor_entry_id: str | None,
) -> ScheduledProbePlan | str | None:
    collection_path, param = _collection_and_trailing_param(canonical_path)
    if collection_path is None or param is None:
        return None

    anchor = _recorded_state_anchor(recorded, canonical_path)
    if anchor is None:
        return None
    prefix_result = _build_auth_only_prefix_plan(anchor, initial_selection)
    if prefix_result.blocked_reason is not None:
        return prefix_result.blocked_reason
    prefix = prefix_result.plan
    if prefix is None:
        return None

    anchor_step = prefix.step_by_ref[anchor.ref]
    probe_step = len(prefix.steps)
    probe_path_parameters = _copied_probe_path_parameters(prefix.parameters, anchor_step, probe_step)
    if not probe_path_parameters:
        return None

    basis = dict(generation_basis)
    basis["reason"] = (
        f"DELETE was not observed; recorded {anchor.method} {canonical_path} can confirm "
        "the old same-resource state before deleting it"
    )

    return ScheduledProbePlan(
        probe_id=_probe_id("DELETE", canonical_path),
        method="DELETE",
        canonical_path=canonical_path,
        operation_id=operation_id,
        prefix_steps=prefix.steps,
        bindings=[
            *prefix.bindings,
            *_inherited_request_bindings(prefix.bindings, anchor_step, probe_step),
        ],
        generation_basis=basis,
        schedule_kind="checkpoint",
        anchor_entry_id=anchor_entry_id,
        checkpoint_entry_id=anchor.ref,
        checkpoint_type="operation_based",
        checkpoint_method=anchor.method if anchor.method != "GET" else None,
        insertion_policy="after_checkpoint",
        suffix_policy="skip",
        parameters=[*prefix.parameters, *probe_path_parameters],
        prefix_body_templates=prefix.body_templates,
        literal_assumptions=[
            {
                "location": "path",
                "field": parameter["to_field"],
                "reason": "recorded_literal_reused",
            }
            for parameter in probe_path_parameters
        ],
    )


def _creator_body_template(
    creator: RecordedOperation,
    collection_path: str,
) -> _WriteBodyPlan | None:
    request_text = creator.entry.get("request", {}).get("postData", {}).get("text")
    if not request_text:
        return None
    material = mutate_recorded_body_template(
        request_text,
        f"DELETE-support:{collection_path}:{creator.ref}",
    )
    if material is None:
        return None
    return _WriteBodyPlan(creator.ref, material)


def _fresh_created_write_plan(
    inp: Stage25Inputs,
    recorded: list[RecordedOperation],
    initial_selection: InitialValueFlowSelection,
    canonical_path: str,
    method: str,
    operation_id: str,
    generation_basis: dict,
    anchor_entry_id: str | None,
    reuse_ref: str | None,
    body_material: _WriteBodyPlan,
) -> ScheduledProbePlan | str | None:
    collection_path, param = _collection_and_trailing_param(canonical_path)
    if collection_path is None or param is None:
        return None

    creator = _creator_operation(inp, recorded, collection_path)
    if creator is None:
        return None
    prefix_result = _build_prefix_plan(creator, initial_selection)
    if prefix_result.blocked_reason is not None:
        return prefix_result.blocked_reason
    prefix = prefix_result.plan
    if prefix is None:
        return None

    leaves = _json_leaves(_response_json(creator.entry))
    selected = _select_fresh_leaf(
        leaves,
        param,
        _concrete_path_segments(inp.paths.get(canonical_path).concrete_urls if canonical_path in inp.paths else []),
    )
    if selected is None:
        return None
    parsed_body = _parse_json_text(body_material.body_text)
    if parsed_body is None:
        return None

    jsonpath, _leaf_key, leaf_value, evidence = selected
    if reuse_ref and _body_binding_ambiguous(initial_selection, reuse_ref, parsed_body, leaf_value):
        return AMBIGUOUS_INITIAL_VALUE_FLOW
    creator_step = prefix.step_by_ref[creator.ref]
    probe_step = len(prefix.steps)
    probe_bindings = [
        *_inherited_request_bindings(prefix.bindings, creator_step, probe_step),
        {
            "from_step": creator_step,
            "from_location": "response_body",
            "from_field": jsonpath,
            "to_step": probe_step,
            "to_location": "path",
            "to_field": param,
        },
        *_body_bindings_from_fresh_leaf(
            parsed_body,
            leaf_value,
            creator_step,
            jsonpath,
            probe_step,
        ),
    ]
    basis = dict(generation_basis)
    basis["reason"] = (
        f"{method} was not observed; fresh resource can be created by POST {collection_path} "
        f"and reused body can be grounded from {jsonpath} ({evidence})"
    )

    return ScheduledProbePlan(
        probe_id=_probe_id(method, canonical_path),
        method=method,
        canonical_path=canonical_path,
        candidate_url=None,
        operation_id=operation_id,
        prefix_steps=prefix.steps,
        bindings=[*prefix.bindings, *probe_bindings],
        parameters=prefix.parameters,
        generation_basis=basis,
        schedule_kind="checkpoint",
        anchor_entry_id=anchor_entry_id,
        checkpoint_entry_id=creator.ref,
        checkpoint_type="operation_based",
        checkpoint_method="POST",
        insertion_policy="after_checkpoint",
        suffix_policy="skip",
        body_template=body_material.body_text,
        body_template_source=body_material.source or "reusable_write_body",
        body_material_basis=body_material.value_basis,
        generated_body_fields=body_material.generated_fields,
        prefix_body_templates=prefix.body_templates,
    )


def _collection_and_trailing_param(canonical_path: str) -> tuple[str | None, str | None]:
    parts = [part for part in canonical_path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None, None
    tail = parts[-1]
    if not (tail.startswith("{") and tail.endswith("}") and len(tail) > 2):
        return None, None
    collection = "/" + "/".join(parts[:-1])
    return collection, tail[1:-1]


def _creator_operation(
    inp: Stage25Inputs,
    recorded: list[RecordedOperation],
    collection_path: str,
) -> RecordedOperation | None:
    op = inp.initial_oas.get("paths", {}).get(collection_path, {}).get("post")
    if not isinstance(op, dict):
        return None

    refs: list[str] = []
    for obs in op.get("x-carverflow-observations", []):
        if "run_id" not in obs or "entry_index" not in obs:
            continue
        refs.append(f"{obs['run_id']}#{int(obs['entry_index'])}")
    wanted = set(refs)
    for recorded_op in recorded:
        if recorded_op.ref in wanted:
            return recorded_op
    return None


def _recorded_state_anchor(
    recorded: list[RecordedOperation],
    canonical_path: str,
) -> RecordedOperation | None:
    candidates = [
        op for op in recorded
        if op.canonical_path == canonical_path and op.method in {"GET", "PUT"}
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda op: (0 if op.method == "GET" else 1, op.run_id, op.entry_index, op.operation_id),
    )[0]


@dataclass
class _PrefixPlan:
    steps: list[str]
    bindings: list[dict]
    parameters: list[dict]
    body_templates: dict[int, Any]
    step_by_ref: dict[str, int]


@dataclass
class _PrefixBuildResult:
    plan: _PrefixPlan | None = None
    blocked_reason: str | None = None


def _build_prefix_plan(
    target: RecordedOperation,
    initial_selection: InitialValueFlowSelection,
) -> _PrefixBuildResult:
    flows_by_consumer: dict[str, list[InitialValueFlow]] = {}
    for flow in initial_selection.usable_flows:
        if not _prefix_flow_allowed(flow):
            continue
        flows_by_consumer.setdefault(flow.consumer.ref, []).append(flow)

    steps: list[str] = []
    bindings: list[dict] = []
    parameters: list[dict] = []
    body_templates: dict[int, Any] = {}
    step_by_ref: dict[str, int] = {}
    visiting: set[str] = set()
    blocked_reason: str | None = None

    def add(op: RecordedOperation) -> bool:
        nonlocal blocked_reason
        if op.ref in step_by_ref:
            return True
        if op.ref in visiting:
            return False
        if _has_blocking_ambiguity(initial_selection, op):
            blocked_reason = AMBIGUOUS_INITIAL_VALUE_FLOW
            return False
        visiting.add(op.ref)
        for flow in flows_by_consumer.get(op.ref, []):
            if not add(flow.producer):
                return False
        step = len(steps)
        step_by_ref[op.ref] = step
        steps.append(op.operation_id)
        body = _request_json(op.entry)
        if body is not None:
            if _contains_unusable_redacted(body):
                blocked_reason = "unresolved_redacted_placeholder"
                return False
            body_templates[step] = body
        for parameter in literal_parameters(op, step):
            if parameter["to_location"] == "body":
                continue
            if parameter["to_location"] == "header" and parameter["to_field"] == AUTHORIZATION_HEADER:
                continue
            parameters.append(parameter)
        for flow in flows_by_consumer.get(op.ref, []):
            bindings.append({
                "from_step": step_by_ref[flow.producer.ref],
                "from_location": flow.from_location,
                "from_field": flow.from_field,
                "to_step": step,
                "to_location": flow.to_location,
                "to_field": flow.to_field,
            })
        visiting.remove(op.ref)
        return True

    if not add(target):
        return _PrefixBuildResult(blocked_reason=blocked_reason)
    return _PrefixBuildResult(_PrefixPlan(steps, bindings, parameters, body_templates, step_by_ref))


def _build_auth_only_prefix_plan(
    target: RecordedOperation,
    initial_selection: InitialValueFlowSelection,
) -> _PrefixBuildResult:
    """Build a recorded-state prefix without upgrading business path/body values.

    Recorded-state DELETE intentionally confirms the old same-resource state
    before deletion. It may still need runtime auth context, but it must not turn
    path/query/body business literals into strong fresh bindings.
    """
    flows_by_consumer: dict[str, list[InitialValueFlow]] = {}
    for flow in initial_selection.usable_flows:
        if flow.to_location == "header" and flow.to_field == AUTHORIZATION_HEADER:
            flows_by_consumer.setdefault(flow.consumer.ref, []).append(flow)

    steps: list[str] = []
    bindings: list[dict] = []
    parameters: list[dict] = []
    body_templates: dict[int, Any] = {}
    step_by_ref: dict[str, int] = {}
    visiting: set[str] = set()
    blocked_reason: str | None = None

    def add(op: RecordedOperation) -> bool:
        nonlocal blocked_reason
        if op.ref in step_by_ref:
            return True
        if op.ref in visiting:
            return False
        visiting.add(op.ref)
        for flow in flows_by_consumer.get(op.ref, []):
            if not add(flow.producer):
                return False
        step = len(steps)
        step_by_ref[op.ref] = step
        steps.append(op.operation_id)
        body = _request_json(op.entry)
        if body is not None:
            if _contains_unusable_redacted(body):
                blocked_reason = "unresolved_redacted_placeholder"
                return False
            body_templates[step] = body
        for parameter in literal_parameters(op, step):
            if parameter["to_location"] == "body":
                continue
            if parameter["to_location"] == "header" and parameter["to_field"] == AUTHORIZATION_HEADER:
                continue
            parameters.append(parameter)
        for flow in flows_by_consumer.get(op.ref, []):
            bindings.append({
                "from_step": step_by_ref[flow.producer.ref],
                "from_location": flow.from_location,
                "from_field": flow.from_field,
                "to_step": step,
                "to_location": flow.to_location,
                "to_field": flow.to_field,
            })
        visiting.remove(op.ref)
        return True

    if not add(target):
        return _PrefixBuildResult(blocked_reason=blocked_reason)
    return _PrefixBuildResult(_PrefixPlan(steps, bindings, parameters, body_templates, step_by_ref))


def _auth_prefix_from_body_source(
    recorded: list[RecordedOperation],
    initial_selection: InitialValueFlowSelection,
    body_source: str | None,
) -> _PrefixBuildResult:
    flow = _auth_flow_for_body_source(recorded, initial_selection, body_source)
    if flow is None:
        return _PrefixBuildResult(_PrefixPlan([], [], [], {}, {}))
    return _build_auth_only_prefix_plan(flow.producer, initial_selection)


def _auth_binding_from_body_source(
    recorded: list[RecordedOperation],
    initial_selection: InitialValueFlowSelection,
    body_source: str | None,
    prefix: _PrefixPlan,
    probe_step: int,
) -> list[dict]:
    flow = _auth_flow_for_body_source(recorded, initial_selection, body_source)
    if flow is None or flow.producer.ref not in prefix.step_by_ref:
        return []
    return [{
        "from_step": prefix.step_by_ref[flow.producer.ref],
        "from_location": flow.from_location,
        "from_field": flow.from_field,
        "to_step": probe_step,
        "to_location": "header",
        "to_field": AUTHORIZATION_HEADER,
    }]


def _auth_flow_for_body_source(
    recorded: list[RecordedOperation],
    initial_selection: InitialValueFlowSelection,
    body_source: str | None,
) -> InitialValueFlow | None:
    source_ref = _body_source_ref(body_source)
    if source_ref is None:
        return None
    refs = {op.ref for op in recorded}
    if source_ref not in refs:
        return None
    flows = [
        flow for flow in initial_selection.usable_flows
        if flow.consumer.ref == source_ref
        and flow.to_location == "header"
        and flow.to_field == AUTHORIZATION_HEADER
    ]
    return sorted(
        flows,
        key=lambda flow: (
            flow.producer.run_id,
            flow.producer.entry_index,
            flow.producer.operation_id,
            flow.from_field,
        ),
    )[0] if flows else None


def _copied_probe_bindings(
    bindings: list[dict],
    from_step: int,
    to_step: int,
) -> list[dict]:
    copied = []
    for binding in bindings:
        if binding.get("to_step") != from_step:
            continue
        copied.append({
            "from_step": binding["from_step"],
            "from_location": binding.get("from_location", "response_body"),
            "from_field": binding["from_field"],
            "to_step": to_step,
            "to_location": binding["to_location"],
            "to_field": binding["to_field"],
        })
    return copied


def _copied_probe_parameters(
    parameters: list[dict],
    from_step: int,
    to_step: int,
) -> list[dict]:
    copied = []
    for parameter in parameters:
        if parameter.get("to_step") != from_step:
            continue
        copied.append({
            "to_step": to_step,
            "to_location": parameter["to_location"],
            "to_field": parameter["to_field"],
            "value": parameter["value"],
        })
    return copied


def _body_source_ref(body_source: str | None) -> str | None:
    if not body_source:
        return None
    if body_source.startswith("sibling:"):
        ref = body_source.rsplit(":", 1)[-1]
        return ref if "#" in ref else None
    return body_source if "#" in body_source else None


def _write_body_template(
    inp: Stage25Inputs,
    canonical_path: str,
    method: str,
    reuse_ref: str | None,
    reuse_body: str | None,
) -> _WriteBodyPlan | None:
    if reuse_body:
        material = mutate_recorded_body_template(
            reuse_body,
            f"{method}:{canonical_path}:{reuse_ref or 'recorded'}",
        )
        return _WriteBodyPlan(reuse_ref, material) if material is not None else None
    if method != "POST":
        return None
    sibling = _sibling_instance_write_body(inp, canonical_path)
    if sibling is None:
        return None
    sibling_path, sibling_ref, sibling_body = sibling
    material = mutate_recorded_body_template(
        sibling_body,
        f"{method}:{canonical_path}:{sibling_path}:{sibling_ref or ''}",
    )
    if material is None:
        return None
    return _WriteBodyPlan(f"sibling:{sibling_path}:{sibling_ref or 'unknown'}", material)


def _sibling_instance_write_body(
    inp: Stage25Inputs,
    collection_path: str,
) -> tuple[str, str | None, str] | None:
    collection_parts = _path_parts(collection_path)
    if not collection_parts:
        return None
    candidates: list[tuple[str, str | None, str]] = []
    for sibling_path, info in inp.paths.items():
        sibling_parts = _path_parts(sibling_path)
        if len(sibling_parts) != len(collection_parts) + 1:
            continue
        if sibling_parts[:-1] != collection_parts:
            continue
        tail = sibling_parts[-1]
        if not (tail.startswith("{") and tail.endswith("}") and len(tail) > 2):
            continue
        ref, body = info.reusable_write_body
        if body:
            candidates.append((sibling_path, ref, body))
    return sorted(candidates, key=lambda item: (item[0], item[1] or ""))[0] if candidates else None


def _path_parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def _response_json(entry: dict) -> Any | None:
    text = entry.get("response", {}).get("content", {}).get("text")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _request_json(entry: dict) -> Any | None:
    text = entry.get("request", {}).get("postData", {}).get("text")
    if not text:
        return None
    return _parse_json_text(text)


def _parse_json_text(text: str | None) -> Any | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _contains_redacted(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("[REDACTED:") and value.endswith("]")
    if isinstance(value, list):
        return any(_contains_redacted(child) for child in value)
    if isinstance(value, dict):
        return any(_contains_redacted(child) for child in value.values())
    return False


def _contains_unusable_redacted(value: Any, path: str = "$") -> bool:
    if isinstance(value, dict):
        return any(
            _contains_unusable_redacted(child, f"$.{key}" if path == "$" else f"{path}.{key}")
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(
            _contains_unusable_redacted(child, f"{path}[{i}]")
            for i, child in enumerate(value)
        )
    if isinstance(value, str) and _contains_redacted(value):
        return path not in {"$.user.email", "$.user.password"}
    return False


def _has_blocking_ambiguity(selection: InitialValueFlowSelection, op: RecordedOperation) -> bool:
    for key in selection.ambiguous_for_consumer(op.ref):
        if key.to_location in {"path", "query"}:
            return True
        if key.to_location == "body" and _id_like_field(key.to_field):
            return True
    return False


def _body_binding_ambiguous(
    selection: InitialValueFlowSelection,
    consumer_ref: str,
    body: Any,
    old_value: Any,
) -> bool:
    old_text = _scalar_text(old_value)
    if old_text is None:
        return False
    for path, _key, value in _json_leaves(body):
        if _scalar_text(value) != old_text:
            continue
        if selection.is_ambiguous(consumer_ref, "body", path, old_text):
            return True
    return False


def _copied_probe_path_parameters(parameters: list[dict], from_step: int, to_step: int) -> list[dict]:
    copied = []
    for parameter in parameters:
        if parameter.get("to_step") != from_step or parameter.get("to_location") != "path":
            continue
        copied.append({
            "to_step": to_step,
            "to_location": "path",
            "to_field": parameter["to_field"],
            "value": parameter["value"],
        })
    return copied


def _id_like_field(field: str) -> bool:
    tail = field.rsplit(".", 1)[-1].strip("$").strip("[]").lower()
    return tail in {"id", "slug", "uuid"} or tail.endswith("_id") or tail.endswith("id")


def _json_leaves(value: Any, path: str = "$") -> list[tuple[str, str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, str, Any]] = []
        for key, child in value.items():
            child_path = f"$.{key}" if path == "$" else f"{path}.{key}"
            out.extend(_json_leaves(child, child_path))
        return out
    if isinstance(value, list):
        out = []
        for i, child in enumerate(value):
            out.extend(_json_leaves(child, f"{path}[{i}]"))
        return out
    return [(path, _leaf_key(path), value)]


def _leaf_key(path: str) -> str:
    tail = path.rsplit(".", 1)[-1]
    if "[" in tail:
        tail = tail.split("[", 1)[0]
    return tail.strip("$")


def _select_fresh_leaf(
    leaves: list[tuple[str, str, Any]],
    param: str,
    concrete_segments: set[str],
) -> tuple[str, str, Any, str] | None:
    candidates = []
    param_lower = param.lower()
    for jsonpath, key, value in leaves:
        value_text = _scalar_text(value)
        if value_text is None:
            continue
        key_lower = key.lower()
        value_in_url = value_text in concrete_segments
        key_matches_param = key_lower == param_lower
        if not value_in_url and not key_matches_param:
            continue
        priority = 0 if value_in_url else 1
        evidence = "value_seen_in_same_resource_url" if value_in_url else "response_key_matches_path_param"
        candidates.append((priority, jsonpath, key, value, evidence))
    if not candidates:
        return None
    _priority, jsonpath, key, value, evidence = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    return jsonpath, key, value, evidence


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value)
        return text if text else None
    return None


def _body_bindings_from_fresh_leaf(
    body: Any,
    old_value: Any,
    from_step: int,
    from_field: str,
    to_step: int,
) -> list[dict]:
    old_text = _scalar_text(old_value)
    if old_text is None:
        return []
    out: list[dict] = []
    for path, _key, value in _json_leaves(body):
        if _scalar_text(value) != old_text:
            continue
        out.append({
            "from_step": from_step,
            "from_location": "response_body",
            "from_field": from_field,
            "to_step": to_step,
            "to_location": "body",
            "to_field": path,
        })
    return out


def _prefix_flow_allowed(flow: InitialValueFlow) -> bool:
    if flow.to_location in {"path", "query", "body"}:
        return True
    return flow.to_location == "header" and flow.to_field == AUTHORIZATION_HEADER


def _inherited_request_bindings(
    bindings: list[dict],
    producer_step: int,
    probe_step: int,
) -> list[dict]:
    inherited = []
    for binding in bindings:
        if binding.get("to_step") != producer_step:
            continue
        if not _inheritable_probe_binding(binding):
            continue
        inherited.append({
            "from_step": binding["from_step"],
            "from_location": binding.get("from_location", "response_body"),
            "from_field": binding["from_field"],
            "to_step": probe_step,
            "to_location": binding["to_location"],
            "to_field": binding["to_field"],
        })
    return inherited


def _inheritable_probe_binding(binding: dict) -> bool:
    if binding.get("to_location") == "path":
        return True
    return binding.get("to_location") == "header" and binding.get("to_field") == AUTHORIZATION_HEADER


def _concrete_path_segments(urls: list[str]) -> set[str]:
    segments: set[str] = set()
    for url in urls:
        parts = urlsplit(url)
        for segment in parts.path.strip("/").split("/"):
            if segment:
                segments.add(unquote(segment))
    return segments


def _first_concrete_url(urls: list[str]) -> str | None:
    normalized = sorted({_normalize_url(url) for url in urls if url})
    return normalized[0] if normalized else None


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def _probe_id(method: str, canonical_path: str) -> str:
    return f"pr-013d-{make_operation_id(method, canonical_path)}"


def _creator_probe_id(collection_path: str) -> str:
    return f"pr-013d-creator-{make_operation_id('POST', collection_path)}"
