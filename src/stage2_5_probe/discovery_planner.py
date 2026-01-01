"""013-D-E discovery candidate composition.

Combines the independent 013-D candidate planners into one audit-only view.
Scheduled plans are retained for future explicit execution, but the default
pipeline records them as not_executed audit records and does not send HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .loader import Stage25Inputs
from .path_graph_planner import plan_path_graph_probe_candidates
from .response_planner import plan_response_probe_candidates
from .scheduled import ScheduledProbePlan
from .scheduled_planner import plan_scheduled_operation_probes
from .write_materials import classify_probe_material


@dataclass
class DiscoveryCandidatePlanResult:
    audit_records: list[dict] = field(default_factory=list)
    scheduled_plans: list[ScheduledProbePlan] = field(default_factory=list)

    @property
    def probes(self) -> list[dict]:
        return list(self.audit_records)


def plan_discovery_candidates(inp: Stage25Inputs) -> DiscoveryCandidatePlanResult:
    """Return combined 013-D discovery candidates without executing probes."""
    operation = plan_scheduled_operation_probes(inp)
    response = plan_response_probe_candidates(inp)
    path_graph = plan_path_graph_probe_candidates(inp)

    records = [
        *(audit_record_for_scheduled_plan(plan) for plan in operation.plans),
        *operation.not_executed,
        *response.not_executed,
        *path_graph.not_executed,
    ]
    return DiscoveryCandidatePlanResult(
        audit_records=_dedupe_and_sort(records),
        scheduled_plans=list(operation.plans),
    )


def audit_record_for_scheduled_plan(
    plan: ScheduledProbePlan,
    reason: str = "scheduled_execution_disabled",
) -> dict:
    target: dict[str, Any] = {"method": plan.method.upper()}
    if plan.canonical_path:
        target["canonical_path"] = plan.canonical_path
    if plan.candidate_url:
        target["candidate_url"] = plan.candidate_url
    if plan.operation_id:
        target["operation_id"] = plan.operation_id

    construction_basis: dict[str, Any] = {"strategy": "scheduled_discovery"}
    if plan.prefix_steps:
        construction_basis["anchor_sequence"] = list(plan.prefix_steps)
    if plan.generation_basis:
        construction_basis["generation_basis"] = dict(plan.generation_basis)

    return {
        "probe_id": plan.probe_id,
        "probe_kind": plan.probe_kind,
        "execution_mode": "not_executed",
        "not_executed_reason": reason,
        "target": target,
        "construction_basis": construction_basis,
        "schedule": _schedule_record(plan),
        "material": _material_record(plan),
        "admission": {
            "existence_evidence": "non_evidence",
            "admission_decision": "not_executed",
        },
    }


def _schedule_record(plan: ScheduledProbePlan) -> dict:
    schedule = {
        "schedule_kind": plan.schedule_kind,
        "insertion_policy": plan.insertion_policy,
        "prefix_steps": list(plan.prefix_steps),
        "probe_step": len(plan.prefix_steps),
        "suffix_policy": plan.suffix_policy,
    }
    if plan.anchor_entry_id:
        schedule["anchor_entry_id"] = plan.anchor_entry_id
    if plan.checkpoint_entry_id:
        schedule["checkpoint_entry_id"] = plan.checkpoint_entry_id
    if plan.checkpoint_type:
        schedule["checkpoint_type"] = plan.checkpoint_type
    if plan.checkpoint_method:
        schedule["checkpoint_method"] = plan.checkpoint_method
    return schedule


def _material_record(plan: ScheduledProbePlan) -> dict:
    fresh_bindings = _fresh_value_bindings(plan.bindings, len(plan.prefix_steps))
    literal_assumptions = list(plan.literal_assumptions)
    material: dict[str, Any] = {
        "fresh_value_bindings": fresh_bindings,
        "value_basis": classify_probe_material(
            has_fresh=bool(fresh_bindings),
            has_runtime_secret=False,
            has_literal_assumption=bool(literal_assumptions),
            has_template=plan.body_template is not None,
            template_value_basis=plan.body_material_basis,
        ),
        "material_sufficiency": (
            "not_applicable"
            if not fresh_bindings and plan.body_template is None and not literal_assumptions
            else "insufficient"
        ),
    }
    if plan.body_template is not None:
        material["body_template_source"] = plan.body_template_source or "inline_body_template"
    if plan.generated_body_fields:
        material["generated_value_fields"] = sorted(set(plan.generated_body_fields))
    if literal_assumptions:
        material["literal_assumptions"] = literal_assumptions
    return material


def _fresh_value_bindings(bindings: list[dict], probe_step: int) -> list[dict]:
    out = []
    for binding in bindings:
        if binding.get("to_step") != probe_step:
            continue
        out.append({
            "from_step": binding["from_step"],
            "from_location": binding.get("from_location", "response_body"),
            "from_field": binding["from_field"],
            "to_location": binding["to_location"],
            "to_field": binding["to_field"],
        })
    return out


def _value_basis(has_fresh: bool, has_template: bool, has_literal: bool = False) -> str:
    if sum(1 for source in (has_fresh, has_template or has_literal) if source) > 1:
        return "mixed"
    if has_fresh:
        return "fresh_replay"
    if has_template or has_literal:
        return "recorded_literal"
    return "not_applicable"


def _dedupe_and_sort(records: list[dict]) -> list[dict]:
    deduped: dict[tuple[str, str, str, str], dict] = {}
    for record in records:
        key = _semantic_key(record)
        existing = deduped.get(key)
        if existing is None or _sort_key(record) < _sort_key(existing):
            deduped[key] = record
    return [deduped[key] for key in sorted(deduped, key=lambda key: _sort_key(deduped[key]))]


def _semantic_key(record: dict) -> tuple[str, str, str, str]:
    target = record.get("target", {})
    basis = record.get("construction_basis", {}).get("generation_basis", {})
    return (
        record.get("probe_kind", ""),
        target.get("method", ""),
        target.get("canonical_path") or target.get("candidate_url") or "",
        basis.get("generation_rule", ""),
    )


def _sort_key(record: dict) -> tuple[str, str, str, str, str]:
    target = record.get("target", {})
    basis = record.get("construction_basis", {}).get("generation_basis", {})
    return (
        target.get("method", ""),
        target.get("canonical_path") or target.get("candidate_url") or "",
        record.get("probe_kind", ""),
        basis.get("generation_rule", ""),
        record.get("probe_id", ""),
    )
