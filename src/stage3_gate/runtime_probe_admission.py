"""014I Phase5 Runtime Material probe admission gate.

This module consumes Phase4 runtime probe diagnostics and, only when called
explicitly, writes a copy-on-write Augmented OAS with runtime-admission
annotations or conservative new read-safe operations.  It never mutates the
input OAS in place and never sends HTTP.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from common.contracts import make_envelope, validate_artifact
from oas_naming import operation_id, path_parameter_name
from stage2_recover.schema_infer import infer_schema

_READ_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ADMITTABLE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SUCCESS_MIN = 200
_SUCCESS_MAX = 399
_STATIC_EXT_RE = re.compile(r"\.(?:css|js|png|jpe?g|gif|svg|ico|woff2?|ttf|map|html?)$", re.I)
_SENSITIVE_RE = re.compile(r"(authorization|bearer|cookie|credential|jwt|password|passwd|secret|token|api[_-]?key)", re.I)
_PAGINATION_RE = re.compile(r"(^|[._/-])(cursor|page|offset|limit|next|previous|prev)($|[._/-])", re.I)
_INSTANCE_SEGMENT_RE = re.compile(
    r"(^-?\d+$|^[0-9a-f]{12,}$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|.*[-_][0-9a-f]{4,}.*)",
    re.I,
)
_VERSION_SEGMENT_RE = re.compile(r"^v\d+$", re.I)


def build_runtime_probe_admission_report_from_paths(
    *,
    augmented_oas_path: str | Path,
    probe_results_path: str | Path,
    runtime_probe_plan_report_path: str | Path | None = None,
    run_id: str | None = None,
    allow_oas_mutation: bool = False,
) -> tuple[dict, dict]:
    augmented_oas = json.loads(Path(augmented_oas_path).read_text())
    probe_results = json.loads(Path(probe_results_path).read_text())
    runtime_probe_plan_report = None
    if runtime_probe_plan_report_path is not None:
        runtime_probe_plan_report = json.loads(Path(runtime_probe_plan_report_path).read_text())
    return build_runtime_probe_admission_report(
        augmented_oas=augmented_oas,
        probe_results=probe_results,
        runtime_probe_plan_report=runtime_probe_plan_report,
        input_paths={
            "augmented_oas": str(augmented_oas_path),
            "probe_results": str(probe_results_path),
            "runtime_probe_plan_report": str(runtime_probe_plan_report_path) if runtime_probe_plan_report_path else None,
        },
        run_id=run_id,
        allow_oas_mutation=allow_oas_mutation,
    )


def build_runtime_probe_admission_report(
    *,
    augmented_oas: dict,
    probe_results: dict,
    runtime_probe_plan_report: dict | None = None,
    input_paths: dict[str, str | None] | None = None,
    run_id: str | None = None,
    allow_oas_mutation: bool = False,
) -> tuple[dict, dict]:
    """Return ``(admitted_oas_copy, admission_report)``.

    ``allow_oas_mutation`` means "write annotations/new operations into the
    returned copy."  The input Augmented OAS is never modified in place.
    """
    input_paths = input_paths or {}
    admitted_oas = copy.deepcopy(augmented_oas)
    existing = _operation_index(admitted_oas)
    plan_index = {
        str(plan.get("probe_id")): plan
        for plan in (runtime_probe_plan_report or {}).get("generated_probe_plans", []) or []
        if plan.get("probe_id")
    }
    decisions: list[dict] = []
    warnings: list[dict] = []
    counters: Counter[str] = Counter()

    for idx, probe in enumerate(probe_results.get("probes", []) or [], start=1):
        if not _is_runtime_material_probe(probe, plan_index):
            continue
        decision = _evaluate_probe(
            probe,
            idx,
            existing,
            plan_index.get(str(probe.get("probe_id"))),
            allow_oas_mutation=allow_oas_mutation,
        )
        if allow_oas_mutation and decision["admission_action"] in {"annotated_existing_operation", "added_operation"}:
            _apply_decision(admitted_oas, decision, probe)
            existing = _operation_index(admitted_oas)
        decisions.append(decision)
        counters[decision["admission_action"]] += 1
        if decision.get("blocked_reason"):
            counters[f"blocked:{decision['blocked_reason']}"] += 1

    report = {
        "metadata": make_envelope(
            "runtime_probe_admission_report",
            "runtime_materials_phase5",
            run_id or _first_run_id(augmented_oas, probe_results, runtime_probe_plan_report),
            upstream_refs=_upstream_refs(augmented_oas, probe_results, runtime_probe_plan_report),
        ),
        "input_coverage": _input_coverage(
            augmented_oas=augmented_oas,
            probe_results=probe_results,
            runtime_probe_plan_report=runtime_probe_plan_report,
            input_paths=input_paths,
            candidate_count=len(decisions),
        ),
        "candidate_decisions": decisions,
        "summary": _summary(decisions, counters, allow_oas_mutation),
        "warnings": warnings,
    }
    validate_artifact("runtime_probe_admission_report.schema.json", report)
    if allow_oas_mutation:
        validate_artifact("augmented_oas.schema.json", admitted_oas)
    return admitted_oas, report


def write_runtime_probe_admission_report(path: str | Path, report: dict) -> None:
    validate_artifact("runtime_probe_admission_report.schema.json", report)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n")


def write_runtime_admitted_augmented_oas(path: str | Path, augmented_oas: dict) -> None:
    validate_artifact("augmented_oas.schema.json", augmented_oas)
    Path(path).write_text(json.dumps(augmented_oas, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n")


def _evaluate_probe(
    probe: dict,
    index: int,
    existing: dict[tuple[str, str], dict],
    plan: dict | None,
    *,
    allow_oas_mutation: bool,
) -> dict:
    probe_id = str(probe.get("probe_id") or f"probe_{index:04d}")
    target = probe.get("target") or {}
    method = str(target.get("method") or probe.get("request", {}).get("method") or "").upper()
    response_status = probe.get("response", {}).get("status")
    canonical = _resolve_canonical_path(probe, existing, plan)
    blocked_reason = _blocked_reason(probe, method, response_status, canonical, plan)
    action = "blocked"
    existing_operation = False
    if blocked_reason is None:
        existing_operation = (method.lower(), canonical["canonical_path"]) in existing
        action = "annotated_existing_operation" if existing_operation else "added_operation"
        if not allow_oas_mutation:
            action = "eligible_no_mutation"

    return {
        "decision_id": f"runtime_admission_{index:04d}",
        "probe_id": probe_id,
        "method": method or "GET",
        "response_status": response_status,
        "success": bool(probe.get("success") is True),
        "read_safe": method in _READ_SAFE_METHODS,
        "execution_mode": str(probe.get("execution_mode") or "standalone"),
        "source_generation_rule": _generation_basis(probe).get("generation_rule"),
        "source_material_id": _source_material_id(probe, plan),
        "resolved_execution_path": canonical.get("resolved_execution_path"),
        "original_candidate_path": canonical.get("original_candidate_path"),
        "expected_template_hint": canonical.get("expected_template_hint"),
        "canonical_path": canonical.get("canonical_path"),
        "canonicalization_reason": canonical.get("canonicalization_reason"),
        "existing_operation": existing_operation,
        "admission_action": action,
        "blocked_reason": blocked_reason,
        "oas_mutation_requested": bool(allow_oas_mutation),
        "oas_mutation_performed": action in {"annotated_existing_operation", "added_operation"},
        "evidence_level": "runtime_probe_success" if blocked_reason is None else "diagnostic_only",
        "policy": {
            "phase": "phase5_runtime_probe_admission",
            "does_not_execute_http": True,
            "does_not_mutate_input_oas": True,
            "does_not_touch_dependency_graph": True,
            "does_not_touch_sequences_or_skills": True,
            "requires_explicit_phase5_flag": True,
        },
        "source_refs": {
            "probe_id": probe_id,
            "material_id": _source_material_id(probe, plan),
            "template_hint": canonical.get("expected_template_hint"),
            "resolved_execution_path": canonical.get("resolved_execution_path"),
        },
        "notes": _decision_notes(probe, canonical, blocked_reason, action),
    }


def _blocked_reason(probe: dict, method: str, response_status: Any, canonical: dict, plan: dict | None) -> str | None:
    target = probe.get("target") or {}
    if method not in _ADMITTABLE_METHODS:
        return "write_or_destructive_probe"
    if method not in {"GET"}:
        return "protocol_method_not_business_operation"
    if probe.get("execution_mode") != "scheduled":
        return "probe_not_executed"
    if probe.get("success") is not True or not isinstance(response_status, int) or not (_SUCCESS_MIN <= response_status <= _SUCCESS_MAX):
        if response_status in {401, 403}:
            return "auth_or_forbidden_response"
        return "failed_or_non_success_probe"
    admission_decision = (probe.get("admission") or {}).get("admission_decision")
    if admission_decision not in {"diagnostic_only", "not_admitted"}:
        return "not_runtime_diagnostic_probe"
    if _external_or_query_fragment(target):
        return "external_or_query_fragment"
    if canonical.get("blocked_reason"):
        return canonical["blocked_reason"]
    path_for_checks = canonical.get("resolved_execution_path") or canonical.get("canonical_path") or target.get("candidate_url") or ""
    if _is_static_path(path_for_checks):
        return "static_asset"
    basis_text = json.dumps(_generation_basis(probe), ensure_ascii=False).lower()
    provenance_text = json.dumps((plan or {}).get("material_provenance") or {}, ensure_ascii=False).lower()
    combined = f"{basis_text} {provenance_text} {path_for_checks}".lower()
    if _SENSITIVE_RE.search(combined) or _is_capability_path(path_for_checks):
        return "auth_or_capability_material"
    if _PAGINATION_RE.search(combined):
        return "pagination_material"
    if not canonical.get("canonical_path"):
        return "canonical_path_unresolved"
    return None


def _resolve_canonical_path(probe: dict, existing: dict[tuple[str, str], dict], plan: dict | None) -> dict:
    target = probe.get("target") or {}
    method = str(target.get("method") or probe.get("request", {}).get("method") or "").upper()
    concrete = _normalize_path(target.get("resolved_execution_path")) or _path_from_request(probe) or _normalize_path(target.get("candidate_url"))
    original = _normalize_path(target.get("original_candidate_path")) or _normalize_path(target.get("candidate_url")) or concrete
    hint = _normalize_path(target.get("expected_template_hint")) or _normalize_path((plan or {}).get("expected_template_hint"))
    target_canonical = _normalize_path(target.get("canonical_path"))
    method_paths = [path for (m, path), _op in existing.items() if m == method.lower()]

    if hint and concrete and _path_matches_template_or_same(hint, concrete):
        return _canonical_result(
            canonical_path=hint,
            resolved=concrete,
            original=original,
            hint=hint,
            reason="expected_template_hint_match",
        )
    if target_canonical and "{" in target_canonical and concrete and _path_matches_template_or_same(target_canonical, concrete):
        return _canonical_result(
            canonical_path=target_canonical,
            resolved=concrete,
            original=original,
            hint=hint or target_canonical,
            reason="target_canonical_template_match",
        )
    if concrete:
        exact_existing = [path for path in method_paths if _normalize_path(path) == concrete]
        if exact_existing:
            return _canonical_result(
                canonical_path=exact_existing[0],
                resolved=concrete,
                original=original,
                hint=hint or exact_existing[0],
                reason="existing_oas_path_match",
            )
        template_matches = [path for path in method_paths if _path_matches_template_or_same(path, concrete)]
        if len(template_matches) == 1:
            return _canonical_result(
                canonical_path=template_matches[0],
                resolved=concrete,
                original=original,
                hint=hint or template_matches[0],
                reason="existing_oas_template_match",
            )
        if len(template_matches) > 1:
            return _canonical_result(
                canonical_path=None,
                resolved=concrete,
                original=original,
                hint=hint,
                reason="ambiguous_existing_oas_template",
                blocked_reason="ambiguous_canonical_template",
            )
        if _looks_like_concrete_instance_path(concrete):
            return _canonical_result(
                canonical_path=None,
                resolved=concrete,
                original=original,
                hint=hint,
                reason="concrete_instance_without_trusted_template",
                blocked_reason="concrete_instance_without_template",
            )
        return _canonical_result(
            canonical_path=concrete,
            resolved=concrete,
            original=original,
            hint=hint,
            reason="collection_path_without_template",
        )

    if target_canonical and "{" not in target_canonical:
        return _canonical_result(
            canonical_path=target_canonical,
            resolved=target_canonical,
            original=original,
            hint=hint,
            reason="target_canonical_collection_path",
        )
    return _canonical_result(
        canonical_path=None,
        resolved=concrete,
        original=original,
        hint=hint,
        reason="missing_concrete_target",
        blocked_reason="canonical_path_unresolved",
    )


def _apply_decision(admitted_oas: dict, decision: dict, probe: dict) -> None:
    method = decision["method"].lower()
    path = decision["canonical_path"]
    if not path:
        return
    admitted_oas.setdefault("paths", {}).setdefault(path, {})
    if method in admitted_oas["paths"][path]:
        _append_runtime_admission_annotation(admitted_oas["paths"][path][method], decision, probe)
        return
    operation = _operation_from_probe(method, path, decision, probe)
    admitted_oas["paths"][path][method] = operation


def _operation_from_probe(method: str, path: str, decision: dict, probe: dict) -> dict:
    status = int(probe.get("response", {}).get("status") or 200)
    content_type = _content_type(probe)
    body = probe.get("response", {}).get("body")
    operation = {
        "operationId": operation_id(method, path),
        "responses": _responses_from_probe(status, content_type, body),
        "x-carverflow-observations": [{
            "source": "stage2_5_probe",
            "probe_id": str(probe.get("probe_id")),
            "timestamp": _now(),
            "status": status,
            "auth_present": _auth_present(probe),
        }],
        "x-carverflow-observed-responses": [{
            "status": status,
            "source": "stage2_5_probe",
            "observed_at": _now(),
            "content_type": content_type,
            "body_sample": body,
        }],
        "x-carverflow-evidence": [{
            "type": "probe_success",
            "ref": str(probe.get("probe_id")),
        }],
        "x-carverflow-discovery": {
            "existence_status": "confirmed",
            "execution_readiness": "discovery_only",
            "state_safety": "not_applicable",
            "material_basis": "not_applicable",
            "reasons": [
                "runtime_probe_phase5_admitted",
                "read_safe_probe_success",
                "downstream_assets_not_regenerated",
            ],
        },
    }
    parameters = _path_parameters(path)
    if parameters:
        operation["parameters"] = parameters
    _append_runtime_admission_annotation(operation, decision, probe)
    return operation


def _append_runtime_admission_annotation(operation: dict, decision: dict, probe: dict) -> None:
    annotation = {
        "phase": "phase5_runtime_probe_admission",
        "decision_id": decision["decision_id"],
        "source_probe_id": decision["probe_id"],
        "admission_action": decision["admission_action"],
        "canonical_path": decision["canonical_path"],
        "resolved_execution_path": decision["resolved_execution_path"],
        "expected_template_hint": decision["expected_template_hint"],
        "positive_evidence": [
            f"runtime probe returned {decision['response_status']}",
            f"canonicalization={decision['canonicalization_reason']}",
        ],
        "negative_evidence": [],
        "not_promoted_reason": "phase5_only_augmented_oas_copy; downstream assets unchanged",
        "policy": {
            "core_stage3_input_unchanged": True,
            "does_not_set_dependency_strength": True,
            "does_not_set_grounded": True,
            "does_not_regenerate_stage4_or_stage5": True,
        },
    }
    operation.setdefault("x-carverflow-runtime-admission", []).append(annotation)


def _responses_from_probe(status: int, content_type: str | None, body: Any) -> dict:
    response: dict[str, Any] = {"description": f"Runtime probe observed HTTP {status}"}
    if body is not None and content_type:
        media = "application/json" if "json" in content_type.lower() else "text/plain"
        schema = infer_schema([body]) if media == "application/json" else {"type": "string"}
        response["content"] = {media: {"schema": schema}}
    return {str(status): response}


def _path_parameters(path: str) -> list[dict]:
    params = []
    for raw in re.findall(r"\{([^{}]+)\}", path):
        params.append({
            "name": path_parameter_name(raw),
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        })
    return params


def _operation_index(oas: dict) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path, item in (oas.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if not isinstance(op, dict):
                continue
            out[(str(method).lower(), str(path))] = op
    return out


def _is_runtime_material_probe(probe: dict, plan_index: dict[str, dict]) -> bool:
    probe_id = str(probe.get("probe_id") or "")
    if probe_id in plan_index:
        return True
    target = probe.get("target") or {}
    if target.get("resolved_execution_path") or target.get("expected_template_hint") or target.get("original_candidate_path"):
        return True
    rule = str(_generation_basis(probe).get("generation_rule") or "")
    return rule.startswith(("runtime_material_", "runtime_lifecycle_", "oas_"))


def _generation_basis(probe: dict) -> dict:
    return ((probe.get("construction_basis") or {}).get("generation_basis") or {})


def _source_material_id(probe: dict, plan: dict | None) -> str | None:
    if plan and (plan.get("material_provenance") or {}).get("material_id") is not None:
        return str((plan.get("material_provenance") or {}).get("material_id"))
    basis = _generation_basis(probe)
    value = basis.get("source_field")
    return str(value) if value is not None else None


def _canonical_result(
    *,
    canonical_path: str | None,
    resolved: str | None,
    original: str | None,
    hint: str | None,
    reason: str,
    blocked_reason: str | None = None,
) -> dict:
    return {
        "canonical_path": canonical_path,
        "resolved_execution_path": resolved,
        "original_candidate_path": original,
        "expected_template_hint": hint,
        "canonicalization_reason": reason,
        "blocked_reason": blocked_reason,
    }


def _normalize_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        return None
    if parsed.query or parsed.fragment:
        return None
    path = parsed.path if parsed.path else value
    if not path.startswith("/"):
        return None
    parts = [part for part in path.strip("/").split("/") if part]
    return "/" + "/".join(parts) if parts else "/"


def _path_from_request(probe: dict) -> str | None:
    url = (probe.get("request") or {}).get("url")
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment:
        return None
    return _normalize_path(parsed.path)


def _path_matches_template_or_same(template: str, concrete: str) -> bool:
    template_parts = _segments(template)
    concrete_parts = _segments(concrete)
    if len(template_parts) != len(concrete_parts):
        return False
    for left, right in zip(template_parts, concrete_parts):
        if left.startswith("{") and left.endswith("}"):
            continue
        if left != right:
            return False
    return True


def _segments(path: str) -> list[str]:
    return [part for part in str(path).strip("/").split("/") if part]


def _looks_like_concrete_instance_path(path: str) -> bool:
    parts = _segments(path)
    if not parts:
        return False
    tail = parts[-1]
    if _VERSION_SEGMENT_RE.match(tail):
        return False
    if _INSTANCE_SEGMENT_RE.match(tail):
        return True
    return any(ch.isdigit() for ch in tail) and ("-" in tail or "_" in tail)


def _external_or_query_fragment(target: dict) -> bool:
    for key in ("candidate_url", "original_candidate_path", "resolved_execution_path", "canonical_path"):
        value = target.get(key)
        if not isinstance(value, str):
            continue
        parsed = urlsplit(value)
        if parsed.scheme and parsed.netloc:
            return True
        if parsed.query or parsed.fragment:
            return True
    return False


def _is_static_path(path: str | None) -> bool:
    return bool(path and _STATIC_EXT_RE.search(path))


def _is_capability_path(path: str | None) -> bool:
    if not path:
        return False
    lowered = path.lower()
    return any(part in lowered for part in ("/auth", "/login", "/logout", "/token", "/session", "/csrf"))


def _auth_present(probe: dict) -> bool:
    headers = (probe.get("request") or {}).get("headers") or {}
    return any(str(key).lower() in {"authorization", "cookie", "x-csrf-token", "x-xsrf-token"} for key in headers)


def _content_type(probe: dict) -> str | None:
    headers = (probe.get("response") or {}).get("headers") or {}
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            return str(value)
    body = (probe.get("response") or {}).get("body")
    if isinstance(body, (dict, list)):
        return "application/json"
    if isinstance(body, str):
        return "text/plain"
    return None


def _decision_notes(probe: dict, canonical: dict, blocked_reason: str | None, action: str) -> list[str]:
    notes = [
        "Phase5 admission consumes only explicit executed read-safe runtime probes",
        f"canonicalization_reason={canonical.get('canonicalization_reason')}",
    ]
    if blocked_reason:
        notes.append(f"blocked_reason={blocked_reason}")
    if action == "eligible_no_mutation":
        notes.append("eligible but OAS mutation flag was not enabled")
    if canonical.get("expected_template_hint"):
        notes.append(f"template_hint={canonical.get('expected_template_hint')}")
    if canonical.get("resolved_execution_path"):
        notes.append(f"resolved_execution_path={canonical.get('resolved_execution_path')}")
    return notes


def _input_coverage(
    *,
    augmented_oas: dict,
    probe_results: dict,
    runtime_probe_plan_report: dict | None,
    input_paths: dict[str, str | None],
    candidate_count: int,
) -> dict:
    return {
        "augmented_oas": _coverage("present" if augmented_oas else "missing", input_paths.get("augmented_oas"), len((augmented_oas or {}).get("paths", {}))),
        "probe_results": _coverage("present" if probe_results else "missing", input_paths.get("probe_results"), len((probe_results or {}).get("probes", []))),
        "runtime_probe_plan_report": _coverage(
            "present" if runtime_probe_plan_report else "missing",
            input_paths.get("runtime_probe_plan_report"),
            len((runtime_probe_plan_report or {}).get("generated_probe_plans", [])),
        ),
        "runtime_probe_candidates": _coverage("present" if candidate_count else "present_but_no_evidence", None, candidate_count),
    }


def _coverage(status: str, path: str | None, count: int) -> dict:
    return {
        "status": status,
        "path": path,
        "evidence_count": int(count),
        "diagnostic_reason": "ok" if status == "present" else status,
    }


def _summary(decisions: list[dict], counters: Counter[str], allow_oas_mutation: bool) -> dict:
    blocked = [item for item in decisions if item["admission_action"] == "blocked"]
    annotated = [item for item in decisions if item["admission_action"] == "annotated_existing_operation"]
    added = [item for item in decisions if item["admission_action"] == "added_operation"]
    eligible = [item for item in decisions if item["admission_action"] == "eligible_no_mutation"]
    return {
        "candidate_count": len(decisions),
        "admitted_count": len(annotated) + len(added),
        "annotated_existing_count": len(annotated),
        "added_operation_count": len(added),
        "eligible_no_mutation_count": len(eligible),
        "blocked_count": len(blocked),
        "failed_probe_blocked_count": counters.get("blocked:failed_or_non_success_probe", 0) + counters.get("blocked:auth_or_forbidden_response", 0),
        "concrete_path_blocked_count": counters.get("blocked:concrete_instance_without_template", 0),
        "write_or_destructive_blocked_count": counters.get("blocked:write_or_destructive_probe", 0),
        "http_egress_performed": False,
        "probe_execution_performed": False,
        "input_augmented_oas_mutated": False,
        "admitted_augmented_oas_copy_written": bool(allow_oas_mutation and (annotated or added)),
        "phase5_admission_performed": bool(allow_oas_mutation),
        "by_action": dict(Counter(item["admission_action"] for item in decisions)),
        "by_blocked_reason": dict(Counter(str(item.get("blocked_reason")) for item in blocked)),
    }


def _upstream_refs(augmented_oas: dict, probe_results: dict, runtime_probe_plan_report: dict | None) -> list[dict]:
    refs = []
    for artifact_type, doc in [
        ("augmented_oas", augmented_oas),
        ("probe_results", probe_results),
        ("runtime_probe_plan_report", runtime_probe_plan_report),
    ]:
        metadata = (doc or {}).get("metadata") or (doc or {}).get("x-carverflow-meta") or {}
        if metadata.get("run_id"):
            refs.append({"artifact_type": artifact_type, "run_id": str(metadata["run_id"])})
    return refs


def _first_run_id(*docs: dict | None) -> str:
    for doc in docs:
        metadata = (doc or {}).get("metadata") or (doc or {}).get("x-carverflow-meta") or {}
        if metadata.get("run_id"):
            return str(metadata["run_id"])
    return "runtime_probe_admission"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
