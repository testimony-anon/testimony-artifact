"""013 scheduled discovery probe_results record assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stage6_ground.discovery import ScheduledDiscoveryRunner

from .write_materials import classify_probe_material

BODY_BEARING_METHODS = {"POST", "PUT", "PATCH"}
SPEC_LINK_MARKERS = ("swagger", "openapi", "api-docs", "wadl", "wsdl")
_SPEC_LINK_MARKER_PATTERN = "|".join(re.escape(marker) for marker in SPEC_LINK_MARKERS)
_SPEC_HREF_RE = re.compile(r"href\s*=\s*['\"][^'\"]*(?:" + _SPEC_LINK_MARKER_PATTERN + r")", re.IGNORECASE)
_SPEC_URL_RE = re.compile(r"(?:https?://|/)[^\s'\"<>]*(?:" + _SPEC_LINK_MARKER_PATTERN + r")", re.IGNORECASE)


@dataclass
class ScheduledProbePlan:
    probe_id: str
    method: str
    canonical_path: str | None
    prefix_steps: list[str]
    bindings: list[dict]
    probe_kind: str = "operation"
    parameters: list[dict] = field(default_factory=list)
    candidate_url: str | None = None
    operation_id: str | None = None
    generation_basis: dict | None = None
    schedule_kind: str = "same_resource_anchor"
    anchor_entry_id: str | None = None
    checkpoint_entry_id: str | None = None
    checkpoint_type: str | None = None
    checkpoint_method: str | None = None
    insertion_policy: str = "after_anchor"
    suffix_policy: str = "skip"
    body_template: Any | None = None
    body_template_source: str | None = None
    prefix_body_templates: dict[int, Any] = field(default_factory=dict)
    literal_assumptions: list[dict] = field(default_factory=list)
    body_material_basis: str | None = None
    generated_body_fields: list[str] = field(default_factory=list)


def execute_scheduled_probe(runner: "ScheduledDiscoveryRunner", plan: ScheduledProbePlan) -> dict:
    # Live execution dependencies stay behind this explicit function boundary;
    # importing the offline planner must not import Stage6 transports.
    from stage6_ground.discovery import RawProbeStep

    raw = RawProbeStep(
        method=plan.method,
        canonical_path=plan.canonical_path,
        candidate_url=plan.candidate_url,
        operation_id=plan.operation_id,
        body_template=plan.body_template,
        generated_body_fields=list(plan.generated_body_fields),
    )
    result = runner.run_probe(
        plan.prefix_steps,
        plan.bindings,
        plan.parameters,
        raw,
        prefix_body_templates=plan.prefix_body_templates,
    )
    probe_step = len(plan.prefix_steps)
    target = {"method": plan.method.upper()}
    if plan.canonical_path:
        target["canonical_path"] = plan.canonical_path
    if plan.candidate_url:
        target["candidate_url"] = plan.candidate_url
    if plan.operation_id:
        target["operation_id"] = plan.operation_id

    material = _material_record(plan, result, probe_step)
    construction_basis = {
        "strategy": "scheduled_discovery",
        "anchor_sequence": list(plan.prefix_steps),
    }
    if plan.generation_basis:
        construction_basis["generation_basis"] = dict(plan.generation_basis)
    spec_link_response = _is_spec_link_response(result.probe_response)
    record = {
        "probe_id": plan.probe_id,
        "probe_kind": plan.probe_kind,
        "execution_mode": "scheduled" if result.probe_sent else "not_executed",
        "target": target,
        "construction_basis": construction_basis,
        "schedule": _schedule(plan, probe_step),
        "material": material,
        "admission": {
            "existence_evidence": _existence_evidence(result.probe_sent, result.probe_success, spec_link_response),
            "admission_decision": _admission_decision(
                result.probe_sent,
                result.probe_success,
                spec_link_response,
            ),
        },
    }
    if result.probe_sent:
        record["request"] = result.probe_request or {}
        runtime_secret_values = [
            *_runtime_secret_values(runner, result.runtime_secret_bindings),
            *getattr(result, "audit_secret_values", []),
        ]
        record["response"] = _response_record(
            result.probe_response,
            sorted(set(runtime_secret_values), key=len, reverse=True),
            redact_spec_links=spec_link_response,
        )
        record["success"] = result.probe_success
        record["cleanup"] = _cleanup_record(plan, runner)
    else:
        record["not_executed_reason"] = result.error or "scheduled_probe_not_sent"
    return record


def _existence_evidence(probe_sent: bool, probe_success: bool, spec_link_response: bool = False) -> str:
    if not probe_sent:
        return "non_evidence"
    if probe_success and spec_link_response:
        return "diagnostic_exists"
    if probe_success:
        return "strong_success"
    return "non_evidence"


def _admission_decision(probe_sent: bool, probe_success: bool, spec_link_response: bool = False) -> str:
    if not probe_sent:
        return "not_executed"
    if probe_success and spec_link_response:
        return "diagnostic_only"
    if probe_success:
        return "admit_augmented_oas"
    return "not_admitted"


def _schedule(plan: ScheduledProbePlan, probe_step: int) -> dict:
    schedule = {
        "schedule_kind": plan.schedule_kind,
        "insertion_policy": plan.insertion_policy,
        "prefix_steps": list(plan.prefix_steps),
        "probe_step": probe_step,
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


def _material_record(plan: ScheduledProbePlan, result, probe_step: int) -> dict:
    fresh_bindings = _fresh_value_bindings(plan.bindings, probe_step)
    literal_assumptions = [*plan.literal_assumptions, *result.literal_assumptions]
    value_basis = classify_probe_material(
        has_fresh=bool(fresh_bindings),
        has_runtime_secret=bool(result.runtime_secret_bindings),
        has_literal_assumption=bool(literal_assumptions),
        has_template=plan.body_template is not None,
        template_value_basis=plan.body_material_basis,
    )
    material = {
        "fresh_value_bindings": fresh_bindings,
        "value_basis": value_basis,
        "material_sufficiency": _material_sufficiency(result.probe_sent, value_basis),
    }
    if plan.body_template is not None:
        material["body_template_source"] = plan.body_template_source or "inline_body_template"
    if plan.generated_body_fields:
        material["generated_value_fields"] = sorted(set(plan.generated_body_fields))
    if result.runtime_secret_bindings:
        material["runtime_secret_bindings"] = list(result.runtime_secret_bindings)
    if literal_assumptions:
        material["literal_assumptions"] = literal_assumptions
    return material


def _material_sufficiency(probe_sent: bool, value_basis: str) -> str:
    if not probe_sent:
        return "insufficient"
    if value_basis == "not_applicable":
        return "not_applicable"
    return "sufficient"


def _value_basis(has_fresh: bool, has_runtime_secret: bool, has_literal: bool, has_template: bool) -> str:
    # Backward-compatible fallback for plans that do not provide an explicit
    # body_material_basis.  Explicit classification is applied in
    # _material_record below by overwriting recorded-template cases.
    sources = [has_fresh, has_runtime_secret, has_literal]
    if sum(1 for source in sources if source) > 1:
        return "mixed"
    if has_runtime_secret:
        return "runtime_secret"
    if has_fresh:
        return "fresh_replay"
    if has_literal or has_template:
        return "recorded_literal"
    return "not_applicable"


def _runtime_secret_values(runner: ScheduledDiscoveryRunner, runtime_secret_bindings: list[dict]) -> list[str]:
    values = []
    for binding in runtime_secret_bindings:
        value = runner.cfg.value_for(binding["location"], binding["field"])
        if value is None:
            continue
        text = str(value)
        if text:
            values.append(text)
    return sorted(set(values), key=len, reverse=True)


def _redact_runtime_secrets(text: str, runtime_secret_values: list[str]) -> str:
    out = text
    for value in runtime_secret_values:
        out = out.replace(value, "[REDACTED:runtime_secret]")
    return out


def _redact_header_values(headers: dict, runtime_secret_values: list[str]) -> dict:
    return {
        k: _redact_runtime_secrets(str(v), runtime_secret_values)
        for k, v in headers.items()
        if str(k).lower() != "date"
    }


def _is_spec_link_response(response) -> bool:
    body = getattr(response, "body_text", None)
    if body is None:
        return False
    if not _looks_like_html_response(response, body):
        return False
    if _SPEC_HREF_RE.search(body):
        return True
    return bool(_SPEC_URL_RE.search(body))


def _looks_like_html_response(response, body: str) -> bool:
    headers = getattr(response, "headers", None) or {}
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
    if "text/html" in content_type or "application/xhtml+xml" in content_type:
        return True
    lowered = body.lower()
    stripped = lowered.lstrip()
    return (
        stripped.startswith("<!doctype html")
        or stripped.startswith("<html")
        or "<body" in lowered
        or "<a " in lowered
        or "href=" in lowered
    )


def _response_record(
    response,
    runtime_secret_values: list[str] | None = None,
    *,
    redact_spec_links: bool = False,
) -> dict:
    if response is None:
        return {"status": 0}
    runtime_secret_values = runtime_secret_values or []
    record = {"status": response.status}
    if response.headers:
        record["headers"] = _redact_header_values(response.headers, runtime_secret_values)
    if response.body_text is not None:
        if redact_spec_links:
            record["body"] = "[REDACTED:spec_link_page]"
        else:
            record["body"] = _redact_runtime_secrets(response.body_text, runtime_secret_values)
    return record


def _cleanup_record(plan: ScheduledProbePlan, runner: ScheduledDiscoveryRunner) -> dict:
    method = plan.method.upper()
    if method == "DELETE":
        return {
            "required": False,
            "performed": False,
            "basis": "per_probe_cleanup",
            "detail": "after a successful scheduled DELETE the deletion is the final state; suffix_policy=skip does not force replaying the recorded suffix",
        }
    if method in BODY_BEARING_METHODS:
        if getattr(runner, "cfg", None) is not None and getattr(runner.cfg, "trust_basis", None) == "environment_reset":
            return {
                "required": True,
                "performed": False,
                "basis": "environment_reset",
                "detail": "body_bearing_write_cleanup_delegated_to_environment_reset",
            }
        return {
            "required": True,
            "performed": False,
            "basis": "per_probe_cleanup",
            "detail": "body_bearing_write_cleanup_not_verified",
        }
    return {
        "required": False,
        "performed": False,
        "basis": "per_probe_cleanup",
    }
