"""V2 discovery mediator: conservative downstream execution promotion.

This layer does not discover new operations. It only reviews operations already
admitted into augmented_oas and promotes a narrow safe subset from
discovery_only to ready so Stage4/5/6 may consume them.
"""

from __future__ import annotations

import copy
from urllib.parse import urlsplit

from common.oas_discovery import DISCOVERY_EXT, execution_readiness

from .gate import is_success


def mediate_downstream_execution(augmented_oas: dict, probe_results: dict) -> tuple[dict, dict]:
    """Return (mediated_augmented_oas, report) for safe probe-discovered ops.

    First conservative rule: a scheduled, admitted, successful GET with no path
    variables, no required request inputs, no request body, no cleanup burden,
    and no recorded-literal material assumption may become ready. Everything
    else stays discovery_only with an auditable mediator reason.
    """
    doc = copy.deepcopy(augmented_oas)
    probes = {
        probe.get("probe_id"): probe
        for probe in probe_results.get("probes", [])
        if probe.get("probe_id")
    }
    report: dict[str, list[dict]] = {"promoted": [], "blocked": []}

    for canonical_path, item in doc.get("paths", {}).items():
        for method, operation in item.items():
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId")
            if execution_readiness(operation) == "ready":
                continue
            discovery = operation.get(DISCOVERY_EXT)
            if not isinstance(discovery, dict):
                continue
            probe_ids = [
                evidence.get("ref")
                for evidence in operation.get("x-carverflow-evidence", [])
                if evidence.get("type") == "probe_success"
            ]
            candidate_probes = [probes[pid] for pid in probe_ids if pid in probes]
            if not candidate_probes:
                _record_blocked(discovery, report, op_id, method, canonical_path, "no_probe_success_evidence")
                continue

            blocks: list[str] = []
            promoted = False
            for probe in sorted(candidate_probes, key=lambda p: p["probe_id"]):
                ok, reason = _safe_static_get_probe(
                    operation=operation,
                    method=method.upper(),
                    canonical_path=canonical_path,
                    probe=probe,
                )
                if not ok and "{" in canonical_path and "}" in canonical_path:
                    original_reason = reason
                    ok, template_reason = _safe_bindable_probe_template(
                        operation=operation,
                        method=method.upper(),
                        canonical_path=canonical_path,
                        probe=probe,
                    )
                    reason = template_reason if ok else original_reason
                if not ok and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                    ok, write_reason = _safe_write_probe(
                        method=method.upper(),
                        canonical_path=canonical_path,
                        probe=probe,
                    )
                    reason = write_reason if ok else reason
                if not ok:
                    blocks.append(reason)
                    continue
                _promote(discovery, probe)
                promoted_reason = reason
                if reason == "safe_bindable_probe_template":
                    discovery["material_basis"] = "fresh_replay"
                report["promoted"].append({
                    "operation_id": op_id,
                    "method": method.upper(),
                    "canonical_path": canonical_path,
                    "probe_id": probe["probe_id"],
                    "reason": promoted_reason,
                })
                promoted = True
                break
            if not promoted:
                reason = sorted(set(blocks))[0] if blocks else "no_mediator_rule_matched"
                _record_blocked(discovery, report, op_id, method, canonical_path, reason)

    return doc, report


def _record_blocked(discovery: dict, report: dict, op_id: str | None,
                    method: str, canonical_path: str, reason: str) -> None:
    reasons = set(discovery.get("reasons") or [])
    reasons.add(f"mediator_{reason}")
    discovery["reasons"] = sorted(reasons)
    report["blocked"].append({
        "operation_id": op_id,
        "method": method.upper(),
        "canonical_path": canonical_path,
        "reason": reason,
    })


def _promote(discovery: dict, probe: dict) -> None:
    cleanup = probe.get("cleanup") or {}
    material = probe.get("material") or {}
    discovery["execution_readiness"] = "ready"
    discovery["state_safety"] = _state_safety(cleanup)
    discovery["material_basis"] = material.get("value_basis", "not_applicable")
    discovery["reasons"] = []


def _safe_static_get_probe(*, operation: dict, method: str, canonical_path: str,
                           probe: dict) -> tuple[bool, str]:
    target = probe.get("target") or {}
    if method != "GET" or target.get("method", "").upper() != "GET":
        return False, "method_not_get"
    if target.get("canonical_path") != canonical_path:
        return False, "probe_target_mismatch"
    if probe.get("execution_mode") != "scheduled":
        return False, "probe_not_scheduled"
    if probe.get("admission", {}).get("admission_decision") != "admit_augmented_oas":
        return False, "probe_not_admitted"
    if not probe.get("success") or not is_success((probe.get("response") or {}).get("status", 0)):
        return False, "probe_not_successful"
    if "{" in canonical_path or "}" in canonical_path:
        return False, "parameterized_path"
    if _required_request_inputs(operation):
        return False, "request_inputs_required"
    if not _cleanup_safe(probe.get("cleanup") or {}):
        return False, "cleanup_not_safe"
    if not _material_safe(probe.get("material") or {}):
        return False, "material_not_safe"
    if not _request_matches_static_path(probe.get("request") or {}, canonical_path):
        return False, "request_path_mismatch"
    return True, "safe_static_get_probe"


def _safe_write_probe(*, method: str, canonical_path: str, probe: dict) -> tuple[bool, str]:
    target = probe.get("target") or {}
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False, "method_not_write"
    if target.get("method", "").upper() != method:
        return False, "probe_method_mismatch"
    if target.get("canonical_path") != canonical_path:
        return False, "probe_target_mismatch"
    if probe.get("execution_mode") != "scheduled":
        return False, "probe_not_scheduled"
    if probe.get("admission", {}).get("admission_decision") != "admit_augmented_oas":
        return False, "probe_not_admitted"
    if not probe.get("success") or not is_success((probe.get("response") or {}).get("status", 0)):
        return False, "probe_not_successful"
    if not _cleanup_safe(probe.get("cleanup") or {}):
        return False, "cleanup_not_safe"
    if not _write_material_safe(probe.get("material") or {}):
        return False, "material_not_safe"
    return True, "safe_write_probe"


def _safe_bindable_probe_template(*, operation: dict, method: str, canonical_path: str,
                                  probe: dict) -> tuple[bool, str]:
    if method != "GET" or probe.get("target", {}).get("method", "").upper() != "GET":
        return False, "method_not_get"
    if "{" not in canonical_path or "}" not in canonical_path:
        return False, "not_parameterized_template"
    if probe.get("execution_mode") != "scheduled":
        return False, "probe_not_scheduled"
    if not probe.get("success") or not is_success((probe.get("response") or {}).get("status", 0)):
        return False, "probe_not_successful"
    if not _cleanup_safe(probe.get("cleanup") or {}):
        return False, "cleanup_not_safe"
    inference = operation.get("x-carverflow-template-inference")
    if not isinstance(inference, dict):
        return False, "no_template_inference_metadata"
    probe_ids = inference.get("probe_ids") or []
    if len(set(probe_ids)) < 2:
        return False, "insufficient_template_probe_count"
    if probe.get("probe_id") not in probe_ids:
        return False, "probe_not_in_template_evidence"
    bindings = inference.get("param_bindings") or []
    if not bindings:
        return False, "missing_template_param_bindings"
    for binding in bindings:
        if not binding.get("param") or not _template_binding_source(binding):
            return False, "missing_template_param_source"
        if len(set(binding.get("source_entry_ids") or [])) < 1:
            return False, "missing_template_source_entry"
        if len(set(binding.get("example_values") or [])) < 2:
            return False, "insufficient_template_examples"
    return True, "safe_bindable_probe_template"


def _template_binding_source(binding: dict) -> str | None:
    for key in ("source_jsonpath", "source_xpath", "source_field"):
        value = binding.get(key)
        if value:
            return str(value)
    return None


def _required_request_inputs(operation: dict) -> list[tuple[str, str]]:
    inputs: list[tuple[str, str]] = []
    if operation.get("requestBody"):
        inputs.append(("body", "$"))
    for param in operation.get("parameters", []):
        location = param.get("in")
        name = param.get("name", "")
        if location == "path":
            inputs.append(("path", name))
        elif param.get("required"):
            inputs.append((str(location), name))
    return inputs


def _cleanup_safe(cleanup: dict) -> bool:
    if cleanup.get("required"):
        return cleanup.get("performed") or cleanup.get("basis") == "environment_reset"
    return True


def _state_safety(cleanup: dict) -> str:
    if cleanup.get("basis") == "environment_reset":
        return "environment_reset"
    if cleanup.get("required"):
        return "per_probe_cleanup" if cleanup.get("performed") else "unsafe_or_unverified"
    return "not_applicable"


def _material_safe(material: dict) -> bool:
    if material.get("value_basis", "not_applicable") != "not_applicable":
        return False
    if material.get("literal_assumptions"):
        return False
    return material.get("material_sufficiency") in {None, "not_applicable", "sufficient"}


def _write_material_safe(material: dict) -> bool:
    if material.get("literal_assumptions"):
        return False
    if material.get("material_sufficiency") not in {None, "sufficient"}:
        return False
    return material.get("value_basis") in {
        "fresh_replay",
        "runtime_secret",
        "generated_mutation",
        "stable_literal_verified",
        "mixed",
    }


def _request_matches_static_path(request: dict, canonical_path: str) -> bool:
    url = request.get("url")
    if not isinstance(url, str):
        return False
    return (urlsplit(url).path.rstrip("/") or "/") == canonical_path
