"""014H Runtime Material driven probe plan sidecar.

This module is Phase4 planning/audit plus explicit read-safe probe execution.
The default path remains no-egress.  When a caller explicitly requests
execution, only read-safe executable runtime material probe plans may send HTTP,
and their results remain diagnostic probe_results records.  They are not
admitted into Augmented OAS.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from common.contracts import make_envelope, validate_artifact
from oas_naming import operation_id

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
_WRITE_METHODS = {"POST", "PUT", "PATCH"}
_DESTRUCTIVE_METHODS = {"DELETE"}
_COMMON_PREFIXES = {"api", "v1", "v2", "v3"}
_SENSITIVE_RE = re.compile(r"(authorization|bearer|cookie|credential|jwt|password|passwd|secret|token|api[_-]?key)", re.I)
_PAGINATION_RE = re.compile(r"(cursor|page|offset|limit|next|previous|prev)", re.I)
_STATIC_EXT_RE = re.compile(r"\.(?:css|js|png|jpe?g|gif|svg|ico|woff2?|ttf|map|html?)$", re.I)
_ID_FIELD_RE = re.compile(r"(^id$|id$|slug$|uuid$|href$|url$|uri$|link$|self$|resource$|location$|path$|name$|title$)", re.I)
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~-]{1,96}$")


def build_runtime_probe_plan_report_from_paths(
    *,
    runtime_material_report_path: str | Path | None = None,
    runtime_lifecycle_plan_report_path: str | Path | None = None,
    stage45_runtime_evidence_report_path: str | Path | None = None,
    augmented_oas_path: str | Path | None = None,
    probe_results_path: str | Path | None = None,
    run_id: str | None = None,
    execute_requested: bool = False,
) -> dict:
    inputs: dict[str, Any] = {}
    parse_failures: dict[str, str] = {}

    def _load(name: str, path: str | Path | None) -> None:
        if path is None:
            return
        try:
            inputs[name] = json.loads(Path(path).read_text())
        except Exception as exc:  # pragma: no cover - parser type is not significant.
            parse_failures[name] = f"{type(exc).__name__}: {exc}"
            inputs[name] = None

    _load("runtime_material_report", runtime_material_report_path)
    _load("runtime_lifecycle_plan_report", runtime_lifecycle_plan_report_path)
    _load("stage45_runtime_evidence_report", stage45_runtime_evidence_report_path)
    _load("augmented_oas", augmented_oas_path)
    _load("probe_results", probe_results_path)
    return build_runtime_probe_plan_report(
        runtime_material_report=inputs.get("runtime_material_report"),
        runtime_lifecycle_plan_report=inputs.get("runtime_lifecycle_plan_report"),
        stage45_runtime_evidence_report=inputs.get("stage45_runtime_evidence_report"),
        augmented_oas=inputs.get("augmented_oas"),
        probe_results=inputs.get("probe_results"),
        input_paths={
            "runtime_material_report": _path_or_none(runtime_material_report_path),
            "runtime_lifecycle_plan_report": _path_or_none(runtime_lifecycle_plan_report_path),
            "stage45_runtime_evidence_report": _path_or_none(stage45_runtime_evidence_report_path),
            "augmented_oas": _path_or_none(augmented_oas_path),
            "probe_results": _path_or_none(probe_results_path),
        },
        parse_failures=parse_failures,
        run_id=run_id,
        execute_requested=execute_requested,
    )


def build_runtime_probe_plan_report(
    *,
    runtime_material_report: dict | None = None,
    runtime_lifecycle_plan_report: dict | None = None,
    stage45_runtime_evidence_report: dict | None = None,
    augmented_oas: dict | None = None,
    probe_results: dict | None = None,
    input_paths: dict[str, str | None] | None = None,
    parse_failures: dict[str, str] | None = None,
    run_id: str | None = None,
    execute_requested: bool = False,
) -> dict:
    """Build and validate a Phase4 no-admission runtime probe plan report."""
    input_paths = input_paths or {}
    parse_failures = parse_failures or {}
    op_index = _operation_index(augmented_oas or {})
    context = _Context(op_index=op_index, probe_index=_probe_operation_index(probe_results or {}))

    generated: list[dict] = []
    blocked: list[dict] = []
    material_audit: dict[str | None, dict] = {}
    template_hints: list[dict] = []

    for material in (runtime_material_report or {}).get("materials", []) or []:
        plans = _plans_from_material(material, context)
        if not plans:
            _audit(material_audit, material, "ignored", ["material did not expose resource probe material"], None)
            continue
        for plan in plans:
            if plan["execution_eligibility"] == "blocked":
                blocked.append(plan)
                _audit(material_audit, material, "blocked", [plan["blocked_reason"]], plan["probe_id"])
            else:
                generated.append(plan)
                _audit(material_audit, material, "used", [plan["generation_rule"]], plan["probe_id"])
                if plan.get("expected_template_hint"):
                    template_hints.append(_template_hint(len(template_hints) + 1, plan))

    for plan in _plans_from_lifecycle(runtime_lifecycle_plan_report or {}, context):
        (blocked if plan["execution_eligibility"] == "blocked" else generated).append(plan)
        if plan.get("expected_template_hint"):
            template_hints.append(_template_hint(len(template_hints) + 1, plan))

    for plan in _write_plans_from_oas(augmented_oas or {}, context):
        (blocked if plan["execution_eligibility"] == "blocked" else generated).append(plan)
        if plan.get("expected_template_hint"):
            template_hints.append(_template_hint(len(template_hints) + 1, plan))

    generated = _dedupe_plans(generated)
    blocked = _dedupe_plans(blocked)
    template_hints = _dedupe_hints(template_hints, {plan["probe_id"] for plan in generated})
    material_audit_list = sorted(material_audit.values(), key=lambda item: str(item.get("material_id") or ""))
    warnings = _warnings(parse_failures, blocked, execute_requested)
    report = {
        "metadata": make_envelope(
            "runtime_probe_plan_report",
            "runtime_materials_phase4",
            run_id or _first_run_id(runtime_material_report, runtime_lifecycle_plan_report, stage45_runtime_evidence_report, augmented_oas, probe_results),
            upstream_refs=_upstream_refs(
                runtime_material_report=runtime_material_report,
                runtime_lifecycle_plan_report=runtime_lifecycle_plan_report,
                stage45_runtime_evidence_report=stage45_runtime_evidence_report,
                augmented_oas=augmented_oas,
                probe_results=probe_results,
            ),
        ),
        "input_coverage": _input_coverage(
            runtime_material_report=runtime_material_report,
            runtime_lifecycle_plan_report=runtime_lifecycle_plan_report,
            stage45_runtime_evidence_report=stage45_runtime_evidence_report,
            augmented_oas=augmented_oas,
            probe_results=probe_results,
            input_paths=input_paths,
            parse_failures=parse_failures,
            generated=generated,
            blocked=blocked,
        ),
        "runtime_material_sources": _material_sources(runtime_material_report or {}, material_audit_list),
        "generated_probe_plans": generated,
        "blocked_probe_plans": blocked,
        "material_audit": material_audit_list,
        "template_hints": template_hints,
        "summary": _summary(generated, blocked, template_hints, warnings),
        "warnings": warnings,
    }
    validate_artifact("runtime_probe_plan_report.schema.json", report)
    return report


def write_runtime_probe_plan_report(path: str | Path, report: dict) -> None:
    validate_artifact("runtime_probe_plan_report.schema.json", report)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n")


def probe_audit_records_from_runtime_probe_plan_report(report: dict) -> list[dict]:
    """Return probe_results-compatible not_executed audit records for plans.

    This is intentionally not an execution path.  It lets explicit callers
    surface Phase4 generated plans alongside Stage2.5 probe_results without
    pretending that Phase5 OAS admission occurred.
    """
    return [
        _not_executed_probe_record(plan, "runtime_material_probe_plan_not_executed")
        for plan in report.get("generated_probe_plans", []) or []
    ]


def apply_runtime_probe_plan_to_probe_results(
    probe_results: dict,
    runtime_probe_plan_report: dict,
    *,
    execute: bool = False,
    base_url: str | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 5.0,
) -> tuple[dict, dict]:
    """Append Phase4 runtime probe audit/execute records to probe_results.

    This is the formal bridge from runtime_probe_plan_report to probe_results.
    Default behavior is audit-only/no-egress.  With execute=True, only plans
    that are explicitly read-safe and executable may send HTTP.  Successful
    runtime records are still diagnostic-only and cannot be admitted into OAS.
    """
    enriched = copy.deepcopy(probe_results)
    existing = {_probe_dedupe_key(probe) for probe in enriched.get("probes", []) or []}
    records: list[dict] = []
    http_request_count = 0
    executed_count = 0
    success_count = 0
    failure_count = 0
    not_executed_count = 0
    skipped_duplicates = 0
    by_not_executed_reason: Counter[str] = Counter()
    by_status: Counter[str] = Counter()

    for plan in runtime_probe_plan_report.get("generated_probe_plans", []) or []:
        if not execute:
            record = _not_executed_probe_record(plan, "runtime_material_probe_plan_not_executed")
        else:
            reason = _runtime_probe_execution_block_reason(plan, base_url)
            if reason:
                record = _not_executed_probe_record(plan, reason)
            else:
                record = _execute_read_safe_probe_record(plan, base_url or "", headers or {}, timeout_seconds)
        key = _probe_dedupe_key(record)
        if key in existing:
            skipped_duplicates += 1
            continue
        existing.add(key)
        records.append(record)
        if record.get("execution_mode") == "not_executed":
            not_executed_count += 1
            by_not_executed_reason[str(record.get("not_executed_reason") or "unknown")] += 1
        else:
            executed_count += 1
            http_request_count += 1
            status = record.get("response", {}).get("status")
            if status is not None:
                by_status[str(status)] += 1
            if record.get("success") is True:
                success_count += 1
            else:
                failure_count += 1

    enriched.setdefault("probes", []).extend(records)
    validate_artifact("probe_results.schema.json", enriched)
    return enriched, {
        "runtime_probe_record_count": len(records),
        "runtime_probe_audit_record_count": not_executed_count,
        "runtime_probe_executed_record_count": executed_count,
        "runtime_probe_success_count": success_count,
        "runtime_probe_failure_count": failure_count,
        "runtime_probe_http_request_count": http_request_count,
        "runtime_probe_duplicate_skipped_count": skipped_duplicates,
        "runtime_probe_by_not_executed_reason": dict(by_not_executed_reason),
        "runtime_probe_by_response_status": dict(by_status),
        "runtime_probe_oas_admission_performed": False,
    }


def _not_executed_probe_record(plan: dict, reason: str) -> dict:
    target = _probe_target(plan)
    return {
        "probe_id": plan["probe_id"],
        "probe_kind": "operation" if plan["method"] not in _READ_METHODS else "response",
        "execution_mode": "not_executed",
        "not_executed_reason": reason,
        "target": target,
        "construction_basis": {
            "strategy": "scheduled_discovery",
            "generation_basis": _runtime_generation_basis(plan),
        },
        "schedule": _not_scheduled(),
        "material": _runtime_probe_material(plan, executed=False),
        "admission": {
            "existence_evidence": "non_evidence",
            "admission_decision": "not_executed",
        },
    }


def _execute_read_safe_probe_record(plan: dict, base_url: str, headers: dict[str, str], timeout_seconds: float) -> dict:
    method = str(plan["method"]).upper()
    path = _runtime_probe_path(plan)
    url = _join_base_url(base_url, path or "/")
    started = time.monotonic()
    status = 599
    response_headers: dict[str, str] = {}
    response_body: Any = None
    error: str | None = None
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            response_headers = _redact_headers(dict(response.headers.items()))
            response_body = None if method == "HEAD" else _decode_response_body(response.read())
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        response_headers = _redact_headers(dict(exc.headers.items()))
        try:
            response_body = None if method == "HEAD" else _decode_response_body(exc.read())
        except Exception:
            response_body = None
        error = f"HTTPError: {exc.code}"
    except Exception as exc:  # pragma: no cover - network failure type is environment-specific.
        error = f"{type(exc).__name__}: {exc}"
    duration_ms = int((time.monotonic() - started) * 1000)
    success = 200 <= status < 400
    response = {
        "status": status,
        "headers": response_headers,
        "body": response_body if response_body is not None else ({"error": error} if error else None),
    }
    return {
        "probe_id": plan["probe_id"],
        "probe_kind": "response",
        "execution_mode": "scheduled",
        "target": _probe_target(plan),
        "construction_basis": {
            "strategy": "scheduled_discovery",
            "generation_basis": _runtime_generation_basis(plan),
        },
        "schedule": _not_scheduled(),
        "material": _runtime_probe_material(plan, executed=True),
        "request": {
            "method": method,
            "url": url,
            "headers": _redact_headers(headers),
            "body": None,
        },
        "response": response,
        "success": success,
        "cleanup": {
            "required": False,
            "performed": False,
            "detail": f"read_safe_runtime_probe_no_cleanup; duration_ms={duration_ms}",
        },
        "admission": {
            "existence_evidence": "diagnostic_exists" if success else "non_evidence",
            "admission_decision": "diagnostic_only" if success else "not_admitted",
        },
    }


def _runtime_probe_execution_block_reason(plan: dict, base_url: str | None) -> str | None:
    if plan.get("execution_eligibility") != "executable":
        return "runtime_material_probe_not_read_safe_executable"
    if str(plan.get("method") or "").upper() not in _READ_METHODS:
        return "runtime_material_probe_write_or_destructive_not_executed"
    if not base_url:
        return "runtime_material_probe_base_url_missing"
    path = _runtime_probe_path(plan)
    if not path or "{" in path or "}" in path:
        return "runtime_material_probe_template_target_not_executable"
    return None


def _runtime_probe_path(plan: dict) -> str | None:
    target = plan.get("target") or {}
    resolved = target.get("resolved_execution_path")
    if isinstance(resolved, str) and resolved.startswith("/") and "{" not in resolved and "}" not in resolved:
        return resolved
    candidate = target.get("candidate_url")
    canonical = target.get("canonical_path")
    if isinstance(candidate, str) and candidate.startswith("/") and not urlsplit(candidate).query and not urlsplit(candidate).fragment:
        return candidate
    if isinstance(canonical, str) and canonical.startswith("/") and "{" not in canonical and "}" not in canonical:
        return canonical
    return None


def _probe_target(plan: dict) -> dict:
    return {k: v for k, v in (plan.get("target") or {}).items() if v is not None}


def _runtime_generation_basis(plan: dict) -> dict:
    target = _probe_target(plan)
    provenance = plan.get("material_provenance") or {}
    source_artifact = provenance.get("source_artifact") or "unknown"
    resolution_note = ""
    if target.get("resolved_execution_path") or target.get("resolution_reason"):
        resolution_note = (
            f"; original_candidate_path={target.get('original_candidate_path')}; "
            f"resolved_execution_path={target.get('resolved_execution_path')}; "
            f"expected_template_hint={target.get('expected_template_hint')}; "
            f"resolution_reason={target.get('resolution_reason')}"
        )
    basis = {
        "generation_rule": plan["generation_rule"],
        "source_location": _generation_source_location(source_artifact),
        "source_part": _generation_source_part(source_artifact),
        "derived_candidate": f"{plan['method']} {target.get('canonical_path') or target.get('candidate_url')}",
        "reason": "014H runtime material probe plan; diagnostic-only until Phase5 admission gate",
        "notes": f"source_artifact={source_artifact}; source_path={provenance.get('source_path')}{resolution_note}",
    }
    if provenance.get("material_id"):
        basis["source_field"] = str(provenance["material_id"])
    if provenance.get("value_preview"):
        basis["source_value"] = str(provenance["value_preview"])[:256]
    return basis


def _generation_source_location(source_artifact: str) -> str:
    if source_artifact in {"runtime_material_report", "runtime_lifecycle_plan_report", "stage45_runtime_evidence_report", "augmented_oas"}:
        return source_artifact
    return "runtime_material_report"


def _generation_source_part(source_artifact: str) -> str:
    return {
        "runtime_material_report": "runtime_material",
        "runtime_lifecycle_plan_report": "runtime_lifecycle_plan",
        "stage45_runtime_evidence_report": "probe_plan",
        "augmented_oas": "oas_operation",
    }.get(source_artifact, "probe_plan")


def _runtime_probe_material(plan: dict, *, executed: bool) -> dict:
    method = str(plan.get("method") or "").upper()
    if method in _READ_METHODS:
        value_basis = "not_applicable"
        material_sufficiency = "not_applicable" if executed else "diagnostic_only"
    elif method in _WRITE_METHODS:
        value_basis = "mixed"
        material_sufficiency = "diagnostic_only"
    else:
        value_basis = "not_applicable"
        material_sufficiency = "insufficient"
    material = {
        "value_basis": value_basis,
        "material_sufficiency": material_sufficiency,
    }
    if plan.get("body_material_source"):
        material["body_template_source"] = str(plan["body_material_source"])
    return material


def _not_scheduled() -> dict:
    return {
        "schedule_kind": "not_scheduled",
        "checkpoint_type": "none",
        "insertion_policy": "not_scheduled",
        "suffix_policy": "not_applicable",
    }


def _probe_dedupe_key(probe: dict) -> tuple:
    target = probe.get("target") or {}
    basis = ((probe.get("construction_basis") or {}).get("generation_basis") or {})
    return (
        target.get("method"),
        target.get("canonical_path"),
        target.get("candidate_url"),
        basis.get("generation_rule"),
        basis.get("derived_candidate"),
    )


def _join_base_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _decode_response_body(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text[:4096]


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        str(key): ("[REDACTED:sensitive-header]" if _SENSITIVE_RE.search(str(key)) or _SENSITIVE_RE.search(str(value)) else str(value))
        for key, value in (headers or {}).items()
    }


class _Context:
    def __init__(self, *, op_index: dict[str, dict], probe_index: dict[str, dict] | None = None):
        self.op_index = op_index
        self.probe_index = probe_index or {}
        paths_by_method: dict[str, set[str]] = defaultdict(set)
        all_paths: set[str] = set()
        for op in op_index.values():
            path = str(op["path"])
            paths_by_method[str(op["method"]).upper()].add(path)
            all_paths.add(path)
        self.paths_by_method = {
            method: sorted(paths)
            for method, paths in paths_by_method.items()
        }
        self.all_paths = sorted(all_paths)

    def operation(self, operation_id: str | None) -> dict | None:
        if not operation_id:
            return None
        return self.op_index.get(operation_id) or self.probe_index.get(operation_id)

    def probe_operation(self, probe_id: str | None) -> dict | None:
        if not probe_id:
            return None
        return self.probe_index.get(probe_id)

    def paths_for_method(self, method: str) -> list[str]:
        return self.paths_by_method.get(str(method).upper(), [])

    def paths_for_any_method(self) -> list[str]:
        return self.all_paths


def _plans_from_material(material: dict, context: _Context) -> list[dict]:
    source = material.get("source") or {}
    material_id = material.get("material_id")
    kind = material.get("material_kind")
    value_shape = material.get("value_shape")
    preview = material.get("value_preview")
    source_path = source.get("source_path")
    source_location = source.get("source_location")
    blocked_reason = _material_blocked_reason(material)
    if blocked_reason:
        return [_blocked_plan(
            material=material,
            method="GET",
            target_path=None,
            generation_rule="runtime_material_blocked",
            blocked_reason=blocked_reason,
            notes=[f"material {material_id} blocked before target construction"],
        )]

    url_path, url_block = _same_origin_resource_path(preview)
    if url_block:
        return [_blocked_plan(
            material=material,
            method="GET",
            target_path=preview if isinstance(preview, str) else None,
            generation_rule="runtime_material_url_candidate",
            blocked_reason=url_block,
            notes=[f"value_shape={value_shape}", f"source_location={source_location}"],
        )]
    if url_path:
        return [_read_plan_from_path(
            material,
            url_path,
            "runtime_material_url_candidate",
            template_hint=_template_from_concrete_path(url_path, _param_name_from_source(source_path)),
            context=context,
        )]

    if kind in {"fresh_resource", "observed_resource", "link"}:
        token = _safe_identity_token(preview, source_path)
        if token is None:
            reason = "pagination_material" if _is_pagination(source_path or preview) else "not_business_resource_material"
            return [_blocked_plan(
                material=material,
                method="GET",
                target_path=None,
                generation_rule="runtime_material_identity_candidate",
                blocked_reason=reason,
                notes=[f"value_preview={preview}", f"source_path={source_path}"],
            )]
        op = context.operation(source.get("source_operation_id")) or context.probe_operation(source.get("source_probe_id"))
        base_path = _collection_base_for_material(op, material)
        if base_path is None:
            candidates = _candidate_consumers(material, context)
            if candidates:
                return [_read_plan_from_path(
                    material,
                    candidate,
                    "runtime_material_existing_consumer_candidate",
                    template_hint=candidate,
                    canonical=True,
                    context=context,
                ) for candidate in candidates]
            return [_blocked_plan(
                material=material,
                method="GET",
                target_path=None,
                generation_rule="runtime_material_identity_candidate",
                blocked_reason="missing_runtime_material",
                notes=["no source operation collection path or candidate consumer"],
            )]
        concrete = _join_path(base_path, token)
        return [_read_plan_from_path(
            material,
            concrete,
            "runtime_material_identity_candidate",
            template_hint=_join_path(base_path, "{" + _param_name_from_source(source_path) + "}"),
            context=context,
        )]

    if kind == "body_template":
        op = context.operation(source.get("source_operation_id"))
        if op and op["method"] in _WRITE_METHODS:
            return [_write_material_plan(material, op, "recorded_body_template")]
        return []

    return []


def _plans_from_lifecycle(runtime_lifecycle_plan_report: dict, context: _Context) -> list[dict]:
    plans: list[dict] = []
    for idx, structured in enumerate(runtime_lifecycle_plan_report.get("structured_lifecycle_plans", []) or [], start=1):
        for step in (structured.get("target_steps") or []) + (structured.get("verification_steps") or []):
            method = str(step.get("method") or "").upper()
            path = step.get("path")
            if method in _READ_METHODS and isinstance(path, str) and path.startswith("/"):
                is_template = "{" in path or "}" in path
                is_auth_capability = _is_auth_capability_path(path)
                plans.append(_plan(
                    probe_id=_probe_id("runtime_lifecycle_plan", method, path, str(structured.get("plan_id") or idx)),
                    method=method,
                    target=_target(method, canonical_path=path if is_template else None, candidate_url=None if is_template else path),
                    generation_rule="runtime_lifecycle_plan_read_candidate",
                    material_provenance={
                        "source_artifact": "runtime_lifecycle_plan_report",
                        "material_id": str(structured.get("plan_id") or f"structured_{idx}"),
                        "source_material_kind": "structured_lifecycle_plan",
                        "source_path": "structured_lifecycle_plans",
                        "source_operation_id": step.get("operation_id"),
                        "value_preview": path,
                        "source_location": "target_steps",
                        "source_probe_id": None,
                    },
                    resource_family_candidate=_family_for_path(path),
                    safety_classification="diagnostic_only" if is_auth_capability else "read_safe",
                    execution_eligibility="audit_only" if is_template or is_auth_capability else "executable",
                    expected_template_hint=path,
                    blocked_reason="none",
                    body_material_source=None,
                    cleanup_reset_requirement=None,
                    notes=[
                        "lifecycle plan target looks like auth/capability singleton; audit-only until auth setup is explicit"
                        if is_auth_capability
                        else
                        "lifecycle plan target is read-safe; template targets remain audit-only"
                        if is_template
                        else "lifecycle plan target is concrete and read-safe; execution remains explicit and diagnostic-only"
                    ],
                ))
        for step in structured.get("cleanup_steps", []) or []:
            method = str(step.get("method") or "").upper()
            path = step.get("path")
            if method == "DELETE" and isinstance(path, str):
                status = structured.get("plan_status")
                blocked_reason = "none" if structured.get("cleanup_reuses_target") or status in {"allow", "require_cleanup"} else "cleanup_missing"
                plans.append(_plan(
                    probe_id=_probe_id("runtime_lifecycle_cleanup", method, path, str(structured.get("plan_id") or idx)),
                    method=method,
                    target=_target(method, canonical_path=path),
                    generation_rule="runtime_lifecycle_cleanup_candidate",
                    material_provenance={
                        "source_artifact": "runtime_lifecycle_plan_report",
                        "material_id": str(structured.get("plan_id") or f"structured_{idx}"),
                        "source_material_kind": "structured_lifecycle_plan",
                        "source_path": "cleanup_steps",
                        "source_operation_id": step.get("operation_id"),
                        "value_preview": path,
                        "source_location": "cleanup_steps",
                        "source_probe_id": None,
                    },
                    resource_family_candidate=_family_for_path(path),
                    safety_classification="destructive_requires_fresh_or_reset",
                    execution_eligibility="audit_only" if blocked_reason == "none" else "blocked",
                    expected_template_hint=path,
                    blocked_reason=blocked_reason,
                    body_material_source=None,
                    cleanup_reset_requirement="cleanup_reuses_target" if structured.get("cleanup_reuses_target") else "cleanup_required",
                    notes=["destructive cleanup candidate remains audit-only in Phase4"],
                ))
    return plans


def _write_plans_from_oas(augmented_oas: dict, context: _Context) -> list[dict]:
    plans: list[dict] = []
    for op_id, op in sorted(context.op_index.items()):
        method = op["method"]
        path = op["path"]
        if method not in _WRITE_METHODS:
            if method == "DELETE":
                plans.append(_plan(
                    probe_id=_probe_id("oas_destructive_block", method, path, op_id),
                    method=method,
                    target=_target(method, canonical_path=path),
                    generation_rule="oas_destructive_probe_candidate",
                    material_provenance=_oas_provenance(op_id, method, path),
                    resource_family_candidate=_family_for_path(path),
                    safety_classification="destructive_requires_fresh_or_reset",
                    execution_eligibility="blocked",
                    expected_template_hint=path,
                    blocked_reason="only_observed_existing_resource",
                    body_material_source=None,
                    cleanup_reset_requirement="fresh_or_reset_required",
                    notes=["observed existing destructive probe is blocked by Phase4 safety gate"],
                ))
            continue
        body_source = _oas_body_source(op["operation"])
        if body_source is None:
            plans.append(_plan(
                probe_id=_probe_id("oas_write_block", method, path, op_id),
                method=method,
                target=_target(method, canonical_path=path),
                generation_rule="oas_write_probe_candidate",
                material_provenance=_oas_provenance(op_id, method, path),
                resource_family_candidate=_family_for_path(path),
                safety_classification="blocked_insufficient_material",
                execution_eligibility="blocked",
                expected_template_hint=path,
                blocked_reason="body_template_missing",
                body_material_source=None,
                cleanup_reset_requirement="cleanup_or_reset_required",
                notes=["write probe lacks request body material"],
            ))
            continue
        plans.append(_plan(
            probe_id=_probe_id("oas_write_candidate", method, path, op_id),
            method=method,
            target=_target(method, canonical_path=path),
            generation_rule="oas_request_body_schema_candidate",
            material_provenance=_oas_provenance(op_id, method, path),
            resource_family_candidate=_family_for_path(path),
            safety_classification="write_requires_body_and_cleanup",
            execution_eligibility="audit_only",
            expected_template_hint=path,
            blocked_reason="none",
            body_material_source=body_source,
            cleanup_reset_requirement="cleanup_or_reset_required",
            notes=["requestBody schema exists; execution still requires explicit Stage2.5 safety scheduling"],
        ))
    return plans


def _write_material_plan(material: dict, op: dict, body_source: str) -> dict:
    method = op["method"]
    path = op["path"]
    return _plan(
        probe_id=_probe_id("runtime_material_body", method, path, material.get("material_id")),
        method=method,
        target=_target(method, canonical_path=path),
        generation_rule="runtime_body_template_write_candidate",
        material_provenance=_provenance(material),
        resource_family_candidate=_family_for_path(path),
        safety_classification="write_requires_body_and_cleanup",
        execution_eligibility="audit_only",
        expected_template_hint=path,
        blocked_reason="none",
        body_material_source=body_source,
        cleanup_reset_requirement="cleanup_or_reset_required",
        notes=["body template material available; execution remains explicit and gated"],
    )


def _resolve_runtime_execution_path(
    method: str,
    concrete_path: str,
    template_hint: str | None,
    context: _Context | None,
) -> dict:
    original = _normalize_runtime_path(concrete_path)
    fallback_template = template_hint if isinstance(template_hint, str) and template_hint.startswith("/") else None
    if not original or "{" in original or "}" in original or context is None:
        return {
            "original_candidate_path": original or concrete_path,
            "resolved_execution_path": original or concrete_path,
            "expected_template_hint": fallback_template,
            "resolution_reason": "no_oas_context",
        }

    method_paths = context.paths_for_method(method)
    exact_matches = [path for path in method_paths if _normalize_runtime_path(path) == original]
    if exact_matches:
        return {
            "original_candidate_path": original,
            "resolved_execution_path": original,
            "expected_template_hint": exact_matches[0],
            "resolution_reason": "matches_existing_oas_path",
        }

    direct_templates = [path for path in method_paths if _template_matches_concrete(path, original)]
    if len(direct_templates) == 1:
        return {
            "original_candidate_path": original,
            "resolved_execution_path": original,
            "expected_template_hint": direct_templates[0],
            "resolution_reason": "matches_existing_oas_template",
        }
    if len(direct_templates) > 1:
        return {
            "original_candidate_path": original,
            "resolved_execution_path": original,
            "expected_template_hint": fallback_template,
            "resolution_reason": "ambiguous_existing_oas_template",
        }
    cross_method_templates = [
        path for path in context.paths_for_any_method()
        if path not in method_paths and _template_matches_concrete(path, original)
    ]
    if len(cross_method_templates) == 1:
        return {
            "original_candidate_path": original,
            "resolved_execution_path": original,
            "expected_template_hint": cross_method_templates[0],
            "resolution_reason": "matches_existing_oas_template",
        }
    if len(cross_method_templates) > 1:
        return {
            "original_candidate_path": original,
            "resolved_execution_path": original,
            "expected_template_hint": fallback_template,
            "resolution_reason": "ambiguous_existing_oas_template",
        }

    suffix_matches: list[tuple[int, int, str, str]] = []
    for template in method_paths:
        aligned = _align_concrete_path_to_template_suffix(template, original)
        if not aligned:
            continue
        resolved, overlap_len, static_match_count = aligned
        if resolved == original:
            continue
        suffix_matches.append((overlap_len, static_match_count, template, resolved))

    if suffix_matches:
        suffix_matches.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        best_overlap, best_static, best_template, best_resolved = suffix_matches[0]
        same_quality = [
            item for item in suffix_matches
            if item[0] == best_overlap and item[1] == best_static
        ]
        if len(same_quality) == 1:
            return {
                "original_candidate_path": original,
                "resolved_execution_path": best_resolved,
                "expected_template_hint": best_template,
                "resolution_reason": "suffix_template_prefix_alignment",
            }
        return {
            "original_candidate_path": original,
            "resolved_execution_path": original,
            "expected_template_hint": fallback_template,
            "resolution_reason": "ambiguous_suffix_template_alignment",
        }

    cross_method_suffix_matches: list[tuple[int, int, str, str]] = []
    for template in context.paths_for_any_method():
        if template in method_paths:
            continue
        aligned = _align_concrete_path_to_template_suffix(template, original)
        if not aligned:
            continue
        resolved, overlap_len, static_match_count = aligned
        if resolved == original:
            continue
        cross_method_suffix_matches.append((overlap_len, static_match_count, template, resolved))

    if cross_method_suffix_matches:
        cross_method_suffix_matches.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        best_overlap, best_static, best_template, best_resolved = cross_method_suffix_matches[0]
        same_quality = [
            item for item in cross_method_suffix_matches
            if item[0] == best_overlap and item[1] == best_static
        ]
        if len(same_quality) == 1:
            return {
                "original_candidate_path": original,
                "resolved_execution_path": best_resolved,
                "expected_template_hint": best_template,
                "resolution_reason": "suffix_template_prefix_alignment",
            }
        return {
            "original_candidate_path": original,
            "resolved_execution_path": original,
            "expected_template_hint": fallback_template,
            "resolution_reason": "ambiguous_suffix_template_alignment",
        }

    return {
        "original_candidate_path": original,
        "resolved_execution_path": original,
        "expected_template_hint": fallback_template,
        "resolution_reason": "no_matching_oas_template",
    }


def _normalize_runtime_path(path: str | None) -> str | None:
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    parts = [part for part in path.strip("/").split("/") if part]
    return "/" + "/".join(parts) if parts else "/"


def _path_segments(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def _is_template_segment(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _template_matches_concrete(template: str, concrete: str) -> bool:
    template_parts = _path_segments(template)
    concrete_parts = _path_segments(concrete)
    if len(template_parts) != len(concrete_parts):
        return False
    return _template_tail_matches_concrete(template_parts, concrete_parts)


def _template_tail_matches_concrete(template_parts: list[str], concrete_parts: list[str]) -> bool:
    if len(template_parts) != len(concrete_parts):
        return False
    for template_part, concrete_part in zip(template_parts, concrete_parts):
        if _is_template_segment(template_part):
            continue
        if template_part != concrete_part:
            return False
    return True


def _align_concrete_path_to_template_suffix(template: str, concrete: str) -> tuple[str, int, int] | None:
    template_parts = _path_segments(template)
    concrete_parts = _path_segments(concrete)
    if not template_parts or not concrete_parts or len(template_parts) <= len(concrete_parts):
        return None
    template_tail = template_parts[-len(concrete_parts):]
    if not _template_tail_matches_concrete(template_tail, concrete_parts):
        return None
    static_match_count = sum(
        1
        for template_part, concrete_part in zip(template_tail, concrete_parts)
        if not _is_template_segment(template_part) and template_part == concrete_part
    )
    if static_match_count < 1:
        return None
    prefix = template_parts[:len(template_parts) - len(concrete_parts)]
    return "/" + "/".join([*prefix, *concrete_parts]), len(concrete_parts), static_match_count


def _read_plan_from_path(
    material: dict,
    concrete_path: str,
    generation_rule: str,
    *,
    template_hint: str | None,
    canonical: bool = False,
    context: _Context | None = None,
) -> dict:
    method = "GET"
    resolution = None if canonical else _resolve_runtime_execution_path(method, concrete_path, template_hint, context)
    effective_template_hint = (resolution or {}).get("expected_template_hint") or template_hint
    effective_path = (resolution or {}).get("resolved_execution_path") or concrete_path
    is_auth_capability = _is_auth_capability_path(effective_path)
    target = _target(
        method,
        canonical_path=concrete_path if canonical else None,
        candidate_url=None if canonical else concrete_path,
        operation_id=operation_id(method, template_hint or concrete_path) if canonical else None,
        original_candidate_path=(resolution or {}).get("original_candidate_path"),
        resolved_execution_path=(resolution or {}).get("resolved_execution_path"),
        expected_template_hint=(resolution or {}).get("expected_template_hint"),
        resolution_reason=(resolution or {}).get("resolution_reason"),
    )
    notes = ["read-safe candidate; Phase4 template hint is not OAS admission"]
    if resolution:
        notes.append(
            "path_resolution="
            f"{resolution['resolution_reason']}; "
            f"original={resolution['original_candidate_path']}; "
            f"resolved={resolution['resolved_execution_path']}; "
            f"template={resolution.get('expected_template_hint')}"
        )
    if is_auth_capability:
        notes.append("target looks like auth/capability singleton; audit-only until auth/session material is explicit")
    return _plan(
        probe_id=_probe_id(generation_rule, method, concrete_path, material.get("material_id")),
        method=method,
        target=target,
        generation_rule=generation_rule,
        material_provenance=_provenance(material),
        resource_family_candidate=_family_for_path(effective_template_hint or concrete_path),
        safety_classification="diagnostic_only" if is_auth_capability else "read_safe",
        execution_eligibility="audit_only" if is_auth_capability else "executable",
        expected_template_hint=effective_template_hint,
        blocked_reason="none",
        body_material_source=None,
        cleanup_reset_requirement=None,
        notes=notes,
    )


def _blocked_plan(
    *,
    material: dict,
    method: str,
    target_path: str | None,
    generation_rule: str,
    blocked_reason: str,
    notes: list[str],
) -> dict:
    return _plan(
        probe_id=_probe_id(generation_rule, method, target_path or "blocked", material.get("material_id")),
        method=method,
        target=_target(method, candidate_url=target_path if target_path and _looks_urlish(target_path) else None),
        generation_rule=generation_rule,
        material_provenance=_provenance(material),
        resource_family_candidate=_family_for_path(target_path) if target_path else None,
        safety_classification="blocked_external_or_sensitive" if blocked_reason in {"external_host", "sensitive_material", "capability_material_not_business_resource"} else "blocked_insufficient_material",
        execution_eligibility="blocked",
        expected_template_hint=_template_from_concrete_path(target_path, _param_name_from_source((material.get("source") or {}).get("source_path"))) if target_path and target_path.startswith("/") else None,
        blocked_reason=blocked_reason,
        body_material_source=None,
        cleanup_reset_requirement=None,
        notes=notes,
    )


def _plan(
    *,
    probe_id: str,
    method: str,
    target: dict,
    generation_rule: str,
    material_provenance: dict,
    resource_family_candidate: str | None,
    safety_classification: str,
    execution_eligibility: str,
    expected_template_hint: str | None,
    blocked_reason: str,
    body_material_source: str | None,
    cleanup_reset_requirement: str | None,
    notes: list[str],
) -> dict:
    return {
        "probe_id": probe_id,
        "method": method,
        "target": target,
        "generation_rule": generation_rule,
        "material_provenance": material_provenance,
        "resource_family_candidate": resource_family_candidate,
        "safety_classification": safety_classification,
        "execution_eligibility": execution_eligibility,
        "expected_template_hint": expected_template_hint,
        "blocked_reason": blocked_reason,
        "body_material_source": body_material_source,
        "cleanup_reset_requirement": cleanup_reset_requirement,
        "notes": notes,
        "phase5_admission_policy": {
            "template_hint_only": True,
            "does_not_admit_augmented_oas": True,
            "requires_phase5_gate": True,
        },
    }


def _target(
    method: str,
    *,
    canonical_path: str | None = None,
    candidate_url: str | None = None,
    operation_id: str | None = None,
    original_candidate_path: str | None = None,
    resolved_execution_path: str | None = None,
    expected_template_hint: str | None = None,
    resolution_reason: str | None = None,
) -> dict:
    return {
        "method": method,
        "canonical_path": canonical_path,
        "candidate_url": candidate_url,
        "operation_id": operation_id,
        "original_candidate_path": original_candidate_path,
        "resolved_execution_path": resolved_execution_path,
        "expected_template_hint": expected_template_hint,
        "resolution_reason": resolution_reason,
    }


def _provenance(material: dict) -> dict:
    source = material.get("source") or {}
    return {
        "source_artifact": "runtime_material_report",
        "material_id": material.get("material_id"),
        "source_material_kind": material.get("material_kind"),
        "source_path": source.get("source_path"),
        "source_operation_id": source.get("source_operation_id"),
        "value_preview": material.get("value_preview"),
        "source_location": source.get("source_location"),
        "source_probe_id": source.get("source_probe_id"),
    }


def _oas_provenance(operation_id_value: str, method: str, path: str) -> dict:
    return {
        "source_artifact": "augmented_oas",
        "material_id": operation_id_value,
        "source_material_kind": "oas_operation",
        "source_path": f"{path}.{method.lower()}",
        "source_operation_id": operation_id_value,
        "value_preview": f"{method} {path}",
        "source_location": "operation",
        "source_probe_id": None,
    }


def _operation_index(oas: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path, item in (oas or {}).get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if not isinstance(op, dict):
                continue
            method_upper = str(method).upper()
            if method_upper not in _READ_METHODS | _WRITE_METHODS | _DESTRUCTIVE_METHODS:
                continue
            op_id = op.get("operationId") or operation_id(method_upper, path)
            out[str(op_id)] = {"method": method_upper, "path": path, "operation": op}
    return out


def _probe_operation_index(probe_results: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for probe in (probe_results or {}).get("probes", []) or []:
        target = probe.get("target") or {}
        method = str(target.get("method") or "").upper()
        if method not in _READ_METHODS | _WRITE_METHODS | _DESTRUCTIVE_METHODS:
            continue
        path = _target_path_from_probe(target)
        if not path:
            continue
        item = {
            "method": method,
            "path": path,
            "operation": {},
            "source_kind": "probe_results",
            "probe_id": probe.get("probe_id"),
        }
        op_id = target.get("operation_id")
        if op_id:
            out[str(op_id)] = item
        probe_id = probe.get("probe_id")
        if probe_id:
            out[str(probe_id)] = item
    return out


def _target_path_from_probe(target: dict) -> str | None:
    for key in ("canonical_path", "candidate_url"):
        value = target.get(key)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith("/"):
            return _normalize_runtime_path(value)
        parts = urlsplit(value)
        if parts.path.startswith("/"):
            return _normalize_runtime_path(parts.path)
    return None


def _material_blocked_reason(material: dict) -> str | None:
    if material.get("redacted"):
        return "sensitive_material"
    kind = material.get("material_kind")
    if kind == "link" and _is_response_key_path_extension_material(material):
        return "not_business_resource_material"
    if kind == "capability":
        return "capability_material_not_business_resource"
    if kind == "pagination" or _is_pagination(material.get("value_preview")) or _is_pagination((material.get("source") or {}).get("source_path")):
        return "pagination_material"
    if kind == "literal" and (material.get("trust") or {}).get("evidence_level") == "literal_assumption":
        return "literal_assumption_only"
    text = str(material.get("value_preview") or "")
    if _SENSITIVE_RE.search(text):
        return "sensitive_material"
    return None


def _is_response_key_path_extension_material(material: dict) -> bool:
    trust = material.get("trust") or {}
    reason = " ".join(
        str(item)
        for item in [trust.get("diagnostic_reason"), *((trust.get("confidence_breakdown") or []))]
        if item
    )
    if "response_key_path_extension" not in reason:
        return False
    source_path = (material.get("source") or {}).get("source_path")
    return str(material.get("value_preview") or "") == _source_tail(str(source_path or ""))


def _same_origin_resource_path(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    text = value.strip()
    if _SENSITIVE_RE.search(text):
        return None, "sensitive_material"
    if text.startswith("/") and not text.startswith("//"):
        parts = urlsplit(text)
        if parts.query or parts.fragment:
            return None, "query_or_fragment_not_supported"
        return _safe_path_or_block(parts.path)
    parts = urlsplit(text)
    if parts.scheme in {"http", "https"} and parts.netloc:
        return None, "external_host"
    return None, None


def _safe_path_or_block(path: str) -> tuple[str | None, str | None]:
    clean = path.rstrip("/") or "/"
    if clean == "/" or _STATIC_EXT_RE.search(clean):
        return None, "not_business_resource_material"
    segments = [part for part in clean.split("/") if part]
    if any(_SENSITIVE_RE.search(part) for part in segments):
        return None, "sensitive_material"
    if any(not _SAFE_SEGMENT_RE.fullmatch(part) for part in segments):
        return None, "not_business_resource_material"
    return clean, None


def _safe_identity_token(value: Any, source_path: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.startswith("[REDACTED:"):
        return None
    if _SENSITIVE_RE.search(text) or _SENSITIVE_RE.search(str(source_path or "")):
        return None
    if _is_pagination(source_path or text):
        return None
    if not _ID_FIELD_RE.search(_source_tail(source_path or "")):
        return None
    if not _SAFE_SEGMENT_RE.fullmatch(text):
        return None
    if _looks_like_boolean_or_status(text):
        return None
    return text


def _collection_base_for_material(op: dict | None, material: dict) -> str | None:
    if not op:
        return None
    path = op["path"]
    if _STATIC_EXT_RE.search(path):
        return None
    parts = [part for part in path.strip("/").split("/") if part]
    if not parts:
        return None
    token = str(material.get("value_preview") or "").strip()
    if op.get("source_kind") == "probe_results" and token and parts[-1] == token and len(parts) > 1:
        parts = parts[:-1]
    # If source operation is already an instance template, use its collection.
    elif parts[-1].startswith("{") and parts[-1].endswith("}") and len(parts) > 1:
        parts = parts[:-1]
    return "/" + "/".join(parts)


def _candidate_consumers(material: dict, context: _Context) -> list[str]:
    consumers = ((material.get("usage") or {}).get("candidate_consumers") or [])[:3]
    out = []
    for op_id in consumers:
        op = context.operation(op_id)
        if not op:
            continue
        if op["method"] in _READ_METHODS and "{" in op["path"]:
            out.append(op["path"])
    return sorted(set(out))


def _template_from_concrete_path(path: str | None, param_name: str = "id") -> str | None:
    if not path or not path.startswith("/"):
        return None
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2:
        return path
    if parts[-1].startswith("{") and parts[-1].endswith("}"):
        return "/" + "/".join(parts)
    parts[-1] = "{" + (param_name or "id") + "}"
    return "/" + "/".join(parts)


def _param_name_from_source(source_path: str | None) -> str:
    tail = _source_tail(source_path or "")
    if tail.lower() in {"href", "link", "location", "path", "resource", "self", "uri", "url"}:
        return "id"
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", tail).strip("_")
    if clean and not _SENSITIVE_RE.search(clean) and not _PAGINATION_RE.search(clean):
        return clean.lower()[:32]
    return "id"


def _source_tail(source_path: str) -> str:
    text = str(source_path or "")
    if not text:
        return ""
    text = text.rstrip("]")
    tail = re.split(r"[./@\[\]]+", text)[-1]
    return tail or text


def _join_path(base: str, segment: str) -> str:
    return f"{base.rstrip('/')}/{segment.strip('/')}"


def _family_for_path(path: str | None) -> str | None:
    if not path or not path.startswith("/"):
        return None
    parts = [part for part in path.strip("/").split("/") if part]
    if not parts:
        return "/"
    if parts[0] in _COMMON_PREFIXES and len(parts) > 1:
        parts = parts[1:]
    family: list[str] = []
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            break
        family.append(part)
    return "/" + "/".join(family or parts[:1])


def _is_auth_capability_path(path: str | None) -> bool:
    if not path or not path.startswith("/"):
        return False
    parts = [part.lower() for part in path.strip("/").split("/") if part]
    if not parts or any(_is_template_segment(part) for part in parts):
        return False
    tail = parts[-1].replace("_", "-")
    if tail in {"auth", "login", "logout", "me", "current-user", "session", "sessions", "token", "tokens"}:
        return True
    # Common singleton current-user endpoint. Plural /users remains a normal
    # business collection candidate.
    return tail == "user"


def _oas_body_source(operation: dict) -> str | None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content") or {}
    if not isinstance(content, dict) or not content:
        return None
    for content_type, item in sorted(content.items()):
        if isinstance(item, dict) and item.get("schema"):
            return f"oas_requestBody_schema:{content_type}"
    return None


def _is_pagination(value: Any) -> bool:
    return bool(value is not None and _PAGINATION_RE.search(str(value)))


def _looks_like_boolean_or_status(text: str) -> bool:
    lowered = text.lower()
    return lowered in {"true", "false", "null", "none", "ok", "error", "success", "failed"}


def _looks_urlish(value: str) -> bool:
    return value.startswith("/") or value.startswith("http://") or value.startswith("https://")


def _audit(store: dict, material: dict, decision: str, reasons: list[str], probe_id: str | None) -> None:
    material_id = material.get("material_id")
    item = store.setdefault(material_id, {
        "material_id": material_id,
        "decision": decision,
        "reasons": [],
        "generated_probe_ids": [],
        "blocked_probe_ids": [],
    })
    if item["decision"] != "used" and decision == "used":
        item["decision"] = "used"
    elif item["decision"] == "ignored" and decision == "blocked":
        item["decision"] = "blocked"
    item["reasons"] = sorted(set([*item["reasons"], *[str(reason) for reason in reasons if reason]]))
    if probe_id:
        key = "generated_probe_ids" if decision == "used" else "blocked_probe_ids"
        item[key] = sorted(set([*item[key], probe_id]))


def _template_hint(index: int, plan: dict) -> dict:
    return {
        "hint_id": f"hint_{index:04d}",
        "probe_id": plan["probe_id"],
        "expected_template": plan["expected_template_hint"],
        "hint_basis": plan["generation_rule"],
        "admission_policy": "phase5_gate_required",
    }


def _dedupe_plans(plans: list[dict]) -> list[dict]:
    by_key: dict[tuple, dict] = {}
    for plan in plans:
        target = plan["target"]
        key = (
            plan["method"],
            target.get("canonical_path"),
            target.get("candidate_url"),
            plan["generation_rule"],
            plan["blocked_reason"],
        )
        existing = by_key.get(key)
        if existing is None or plan["probe_id"] < existing["probe_id"]:
            by_key[key] = plan
    return [by_key[key] for key in sorted(by_key, key=lambda item: tuple("" if value is None else str(value) for value in item))]


def _dedupe_hints(hints: list[dict], generated_ids: set[str]) -> list[dict]:
    out = {}
    for hint in hints:
        if hint["probe_id"] not in generated_ids:
            continue
        key = (hint["probe_id"], hint["expected_template"])
        out.setdefault(key, {**hint, "hint_id": f"hint_{len(out) + 1:04d}"})
    return list(out.values())


def _material_sources(runtime_material_report: dict, audits: list[dict]) -> list[dict]:
    by_source = Counter()
    used = Counter()
    blocked = Counter()
    decision_by_material = {item["material_id"]: item for item in audits}
    for material in runtime_material_report.get("materials", []) or []:
        source = ((material.get("source") or {}).get("source_artifact")) or "unknown"
        by_source[source] += 1
        audit = decision_by_material.get(material.get("material_id"))
        if audit and audit.get("generated_probe_ids"):
            used[source] += 1
        if audit and audit.get("blocked_probe_ids"):
            blocked[source] += 1
    return [
        {
            "source_artifact": source,
            "material_count": count,
            "used_for_probe_count": used.get(source, 0),
            "blocked_material_count": blocked.get(source, 0),
        }
        for source, count in sorted(by_source.items())
    ]


def _input_coverage(
    *,
    runtime_material_report: dict | None,
    runtime_lifecycle_plan_report: dict | None,
    stage45_runtime_evidence_report: dict | None,
    augmented_oas: dict | None,
    probe_results: dict | None,
    input_paths: dict[str, str | None],
    parse_failures: dict[str, str],
    generated: list[dict],
    blocked: list[dict],
) -> dict:
    generated_count = len(generated) + len(blocked)
    return {
        "runtime_material_report": _coverage_item("runtime_material_report", runtime_material_report, input_paths, parse_failures, generated_count),
        "runtime_lifecycle_plan_report": _coverage_item("runtime_lifecycle_plan_report", runtime_lifecycle_plan_report, input_paths, parse_failures, len((runtime_lifecycle_plan_report or {}).get("structured_lifecycle_plans", []) or []), compatibility=True),
        "stage45_runtime_evidence_report": _coverage_item("stage45_runtime_evidence_report", stage45_runtime_evidence_report, input_paths, parse_failures, len((stage45_runtime_evidence_report or {}).get("stage5_sequence_annotations", []) or []), compatibility=True),
        "augmented_oas": _coverage_item("augmented_oas", augmented_oas, input_paths, parse_failures, len(_operation_index(augmented_oas or {}))),
        "probe_results": _coverage_item("probe_results", probe_results, input_paths, parse_failures, len((probe_results or {}).get("probes", []) or []), compatibility=True),
    }


def _coverage_item(name: str, doc: Any, paths: dict[str, str | None], parse_failures: dict[str, str], evidence_count: int, *, compatibility: bool = False) -> dict:
    if name in parse_failures:
        return {"status": "parse_failed", "path": paths.get(name), "evidence_count": 0, "diagnostic_reason": parse_failures[name]}
    if doc is None:
        return {"status": "missing", "path": paths.get(name), "evidence_count": 0, "diagnostic_reason": "input not provided"}
    if evidence_count <= 0:
        status = "present_but_no_evidence"
    else:
        status = "compatibility_read" if compatibility else "present"
    return {"status": status, "path": paths.get(name), "evidence_count": max(0, int(evidence_count)), "diagnostic_reason": "Phase4 runtime probe planner input"}


def _summary(generated: list[dict], blocked: list[dict], template_hints: list[dict], warnings: list[dict]) -> dict:
    all_plans = [*generated, *blocked]
    return {
        "generated_probe_count": len(generated),
        "blocked_probe_count": len(blocked),
        "executable_probe_count": sum(1 for plan in generated if plan["execution_eligibility"] == "executable"),
        "executed_probe_count": 0,
        "read_safe_probe_count": sum(1 for plan in all_plans if plan["method"] in _READ_METHODS),
        "write_probe_count": sum(1 for plan in all_plans if plan["method"] in _WRITE_METHODS),
        "destructive_probe_count": sum(1 for plan in all_plans if plan["method"] in _DESTRUCTIVE_METHODS),
        "external_or_sensitive_block_count": sum(1 for plan in blocked if plan["blocked_reason"] in {"external_host", "sensitive_material", "capability_material_not_business_resource"}),
        "template_hint_count": len(template_hints),
        "warning_count": len(warnings),
        "http_egress_performed": False,
        "augmented_oas_mutated": False,
        "phase5_admission_performed": False,
        "by_generation_rule": dict(Counter(plan["generation_rule"] for plan in all_plans)),
        "by_blocked_reason": dict(Counter(plan["blocked_reason"] for plan in blocked)),
        "by_execution_eligibility": dict(Counter(plan["execution_eligibility"] for plan in all_plans)),
    }


def _warnings(parse_failures: dict[str, str], blocked: list[dict], execute_requested: bool) -> list[dict]:
    warnings = []
    idx = 0
    for name, reason in parse_failures.items():
        idx += 1
        warnings.append({"warning_id": f"warn_{idx:04d}", "severity": "blocker", "message": f"{name} parse failed: {reason}", "source": {"input": name}})
    if execute_requested:
        idx += 1
        warnings.append({
            "warning_id": f"warn_{idx:04d}",
            "severity": "info",
            "message": "Phase4 execute was requested, but this sidecar only plans/audits; no OAS admission is performed",
            "source": {"phase": "014H"},
        })
    for reason, count in sorted(Counter(plan["blocked_reason"] for plan in blocked).items()):
        if reason == "none":
            continue
        idx += 1
        warnings.append({"warning_id": f"warn_{idx:04d}", "severity": "warning", "message": f"{count} probe plans blocked: {reason}", "source": {"blocked_reason": reason}})
    return warnings


def _probe_id(prefix: str, method: str, target: Any, source: Any) -> str:
    digest = hashlib.sha1(f"{prefix}|{method}|{target}|{source}".encode("utf-8")).hexdigest()[:12]
    return f"pr-014h-{digest}"


def _path_or_none(path: str | Path | None) -> str | None:
    return str(path) if path is not None else None


def _first_run_id(*docs: dict | None) -> str:
    for doc in docs:
        if not doc:
            continue
        meta = doc.get("metadata") or doc.get("x-carverflow-meta") or {}
        run_id = meta.get("run_id")
        if run_id:
            return str(run_id)
    return "runtime-probe-plan"


def _upstream_refs(**docs: dict | None) -> list[dict]:
    refs = []
    for name, doc in docs.items():
        if not doc:
            continue
        meta = doc.get("metadata") or doc.get("x-carverflow-meta") or {}
        artifact_type = meta.get("artifact_type") or name
        run_id = meta.get("run_id") or "unknown"
        refs.append({"artifact_type": artifact_type, "run_id": str(run_id)})
    return refs
