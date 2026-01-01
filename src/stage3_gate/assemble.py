"""Stage 3 gating assembly (004 D31/D32/D33 + 013-C): initial_oas + probe_results → augmented_oas.

D32 merge: UI observations and probe observations of the same (method, canonical_path) go into one operation.
D33 inheritance: every admitted operation in augmented_oas must carry x-carverflow-observations (UI ones with source=
stage1_session, probe ones with source=stage2_5_probe + probe_id); it also carries observed-responses (aggregated
summary of response statuses) and evidence (derived existence view).
D31/013-C gate: a success proves the operation exists; cleanup/trust/material are routed to
x-carverflow-discovery.execution_readiness.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common.contracts import REPO_ROOT, make_envelope, validate_artifact
from common.oas_discovery import DISCOVERY_EXT
from oas_naming import operation_id

from .gate import admit, is_success, observed_http_response
from .probe_template_inference import (
    ProbePathResolution,
    resolve_probe_template_paths,
    response_derived_concrete_probe,
    template_gated_probe,
)


def _ui_observation(obs: dict) -> dict:
    """Carry a UI observation into augmented: add source=stage1_session (initial shape + source, D33)."""
    return {"source": "stage1_session", **obs}


def _probe_observation(probe: dict, run_created_at: str) -> dict:
    """Probe observation: source=stage2_5_probe + probe_id referencing probe_results.
    timestamp is the probe_results run time (probe_results has no per-probe timestamps; the run's created_at is used)."""
    headers = probe.get("request", {}).get("headers", {})
    return {
        "source": "stage2_5_probe",
        "probe_id": probe["probe_id"],
        "timestamp": run_created_at,
        "status": probe["response"]["status"],
        "auth_present": any(k.lower() == "authorization" for k in headers),
    }


def _stage3_probe_candidate(probe: dict) -> bool:
    """Whether a probe may participate in Stage 3 admission.

    013 diagnostic/not-executed/candidate-only probes remain auditable in
    probe_results and are not written into augmented_oas.
    """
    if probe.get("execution_mode") == "not_executed":
        return False
    target = probe.get("target", {})
    method = target.get("method", "").upper()
    if method in {"OPTIONS", "HEAD", "TRACE"}:
        return False
    if not target.get("canonical_path"):
        return False
    response = probe.get("response")
    if not isinstance(response, dict) or "status" not in response:
        return False
    if not is_success(response["status"]):
        return False
    if _write_redirect_method_gap(probe):
        return False
    decision = probe.get("admission", {}).get("admission_decision")
    if decision in {"diagnostic_only", "not_admitted", "not_executed"}:
        return False
    return True


def _write_redirect_method_gap(probe: dict) -> bool:
    target = probe.get("target") or {}
    method = str(target.get("method") or "").upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    response_status = (probe.get("response") or {}).get("status")
    if not isinstance(response_status, int) or not (300 <= response_status < 400):
        return False
    basis = (probe.get("construction_basis") or {}).get("generation_basis") or {}
    generation_rule = basis.get("generation_rule")
    strategy = (probe.get("construction_basis") or {}).get("strategy")
    return generation_rule == "method_gap" or strategy == "method_completion"


def _cleanup_state(probe: dict) -> tuple[str, list[str]]:
    cleanup = probe.get("cleanup", {})
    if cleanup.get("basis") == "environment_reset":
        return "environment_reset", []
    if cleanup.get("required"):
        if cleanup.get("performed"):
            return "per_probe_cleanup", []
        return "unsafe_or_unverified", ["cleanup_unverified"]
    return "not_applicable", []


def _material_state(probe: dict) -> tuple[str, list[str]]:
    material = probe.get("material")
    if not isinstance(material, dict):
        return "not_applicable", ["material_unspecified"]
    basis = material.get("value_basis", "not_applicable")
    reasons = []
    method = str((probe.get("target") or {}).get("method") or "").upper()
    read_without_body = (
        method in {"GET", "HEAD", "OPTIONS"}
        and basis == "not_applicable"
        and material.get("material_sufficiency") == "not_applicable"
    )
    if (
        material.get("material_sufficiency") not in (None, "sufficient")
        and not read_without_body
    ):
        reasons.append("material_insufficient")
    if basis in {"recorded_literal", "recorded_literal_assumption"}:
        reasons.append("recorded_literal_assumption")
    if material.get("literal_assumptions"):
        reasons.append("literal_assumption")
    return basis, reasons


def _probe_ready(probe: dict) -> tuple[bool, str, str, list[str]]:
    state_safety, cleanup_reasons = _cleanup_state(probe)
    material_basis, material_reasons = _material_state(probe)
    reasons = cleanup_reasons + material_reasons
    method = str((probe.get("target") or {}).get("method") or "").upper()
    material_ready = material_basis in {
        "fresh_replay",
        "runtime_secret",
        "generated_mutation",
        "stable_literal_verified",
        "mixed",
    } or (
        method in {"GET", "HEAD", "OPTIONS"}
        and material_basis == "not_applicable"
    )
    ready = (
        not reasons
        and state_safety != "unsafe_or_unverified"
        and material_ready
    )
    return ready, state_safety, material_basis, reasons


def _discovery_record(ui_obs: list[dict], probe_obs: list[dict]) -> dict:
    """Build x-carverflow-discovery for an admitted operation."""
    if any(is_success(o["status"]) for o in ui_obs):
        return {
            "existence_status": "confirmed",
            "execution_readiness": "ready",
            "state_safety": "not_applicable",
            "material_basis": "not_applicable",
            "reasons": [],
        }

    successful = sorted(
        (p for p in probe_obs if is_success(p["response"]["status"])),
        key=lambda p: p["probe_id"],
    )
    fallback: tuple[str, str, list[str]] | None = None
    for probe in successful:
        ready, state_safety, material_basis, reasons = _probe_ready(probe)
        if ready:
            return {
                "existence_status": "confirmed",
                "execution_readiness": "ready",
                "state_safety": state_safety,
                "material_basis": material_basis,
                "reasons": [],
            }
        if fallback is None:
            fallback = (state_safety, material_basis, reasons)

    if not successful and ui_obs and any(observed_http_response(o["status"]) for o in ui_obs):
        statuses = sorted({int(o["status"]) for o in ui_obs if observed_http_response(o["status"])})
        return {
            "existence_status": "confirmed",
            "execution_readiness": "discovery_only",
            "state_safety": "not_applicable",
            "material_basis": "not_applicable",
            "reasons": [
                "observed_non_success_only",
                "ui_observed_error_only",
                *[f"observed_status_{status}" for status in statuses if not is_success(status)],
            ],
        }

    state_safety, material_basis, reasons = fallback or (
        "unsafe_or_unverified",
        "not_applicable",
        ["material_unspecified"],
    )
    return {
        "existence_status": "confirmed",
        "execution_readiness": "discovery_only",
        "state_safety": state_safety,
        "material_basis": material_basis,
        "reasons": sorted(set(reasons)),
    }


def _build_operation(method: str, canonical_path: str, initial_op: dict | None,
                     ui_obs: list[dict], probe_obs: list[dict], run_created_at: str,
                     template_resolutions: dict[str, ProbePathResolution] | None = None) -> dict:
    observations = [_ui_observation(o) for o in ui_obs]
    observations += [_probe_observation(p, run_created_at) for p in probe_obs]

    # observed-responses: aggregated summary by (status, source)
    seen: set[tuple[int, str]] = set()
    observed_responses = []
    for o in observations:
        if not observed_http_response(o["status"]):
            continue
        key = (o["status"], o["source"])
        if key not in seen:
            seen.add(key)
            observed_responses.append({"status": o["status"], "source": o["source"]})
    observed_responses.sort(key=lambda r: (r["status"], r["source"]))

    # evidence: derived existence view. UI 4xx/5xx is still evidence that the
    # operation was observed, but discovery readiness below keeps it out of
    # executable strong-material paths.
    evidence = []
    for o in ui_obs:
        if observed_http_response(o["status"]):
            ref = o.get("action_id") or f"{o['run_id']}#{o['entry_index']}"
            evidence.append({"type": "ui_observation", "ref": ref})
    for p in probe_obs:
        if is_success(p["response"]["status"]):
            evidence.append({"type": "probe_success", "ref": p["probe_id"]})
    if not evidence:
        # Unreachable in theory (admit guarantees ≥1 real UI response or probe success); defensive fallback
        raise ValueError(f"admitted operation {method} {canonical_path} has no observation evidence; gate logic contradiction")

    operation: dict = {
        "operationId": (initial_op or {}).get("operationId") or operation_id(method, canonical_path),
        "x-carverflow-observations": observations,
        "x-carverflow-observed-responses": observed_responses,
        "x-carverflow-evidence": evidence,
        DISCOVERY_EXT: _discovery_record(ui_obs, probe_obs),
    }
    if initial_op:
        for field in ("parameters", "responses", "requestBody"):
            if field in initial_op:
                operation[field] = initial_op[field]
    else:
        path_parameters = _path_parameters(canonical_path)
        if path_parameters:
            operation["parameters"] = path_parameters
    if "responses" not in operation:
        operation["responses"] = {
            str(o["status"]): {"description": "Observed response"}
            for o in observations
            if observed_http_response(o["status"])
        }
    template_record = _template_inference_record(probe_obs, template_resolutions or {})
    if template_record is not None:
        operation["x-carverflow-template-inference"] = template_record
    material_record = _probe_material_record(probe_obs)
    if material_record:
        operation["x-carverflow-probe-material"] = material_record
    return operation


def _probe_material_record(probe_obs: list[dict]) -> list[dict]:
    out: list[dict] = []
    for probe in sorted(probe_obs, key=lambda p: p.get("probe_id", "")):
        material = probe.get("material")
        if not isinstance(material, dict):
            continue
        fresh_bindings = material.get("fresh_value_bindings") or []
        if not fresh_bindings:
            continue
        schedule = probe.get("schedule") or {}
        record = {
            "probe_id": probe.get("probe_id"),
            "value_basis": material.get("value_basis"),
            "prefix_steps": list(schedule.get("prefix_steps") or []),
            "probe_step": schedule.get("probe_step"),
            "fresh_value_bindings": fresh_bindings,
        }
        for optional_key in (
            "producer_probe_id",
            "producer_operation_id",
            "consumer_template",
            "fresh_identity_source",
            "verification_status",
        ):
            if optional_key in material:
                record[optional_key] = material.get(optional_key)
        out.append(record)
    return out


def _path_parameters(canonical_path: str) -> list[dict]:
    parameters = []
    for segment in canonical_path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}") and len(segment) > 2:
            parameters.append({
                "name": segment[1:-1],
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            })
    return parameters


def build_augmented_oas(initial_oas: dict, probe_results: dict) -> dict:
    """Gate and assemble into augmented_oas (no file output)."""
    run_created_at = probe_results["metadata"]["created_at"]

    # Collect the UI observations and probe observations of each (method, canonical_path)
    ops: dict[tuple[str, str], dict] = {}
    for path, item in initial_oas["paths"].items():
        for method, op in item.items():
            ops[(method.upper(), path)] = {
                "initial_op": op,
                "ui_obs": list(op["x-carverflow-observations"]),
                "probe_obs": [],
            }
    probes = list(probe_results["probes"])
    direct_candidates = [
        probe for probe in probe_results["probes"] if _stage3_probe_candidate(probe)
    ]
    template_candidates = [
        probe for probe in probes if template_gated_probe(probe, initial_oas)
    ]
    response_probe_paths = resolve_probe_template_paths(initial_oas, [*direct_candidates, *template_candidates])
    initial_paths = set(initial_oas.get("paths", {}))
    stage3_candidates = _dedupe_probe_candidates([
        *direct_candidates,
        *[
            probe for probe in template_candidates
            if probe.get("probe_id") in response_probe_paths
        ],
    ])
    for probe in stage3_candidates:
        target = probe["target"]
        canonical_path = target.get("canonical_path")
        resolution = response_probe_paths.get(probe["probe_id"])
        if resolution is not None:
            canonical_path = resolution.canonical_path
        elif response_derived_concrete_probe(probe, initial_paths):
            continue
        if not isinstance(canonical_path, str) or not canonical_path.startswith("/"):
            continue
        key = (target["method"].upper(), canonical_path)
        bucket = ops.setdefault(key, {"initial_op": None, "ui_obs": [], "probe_obs": []})
        bucket["probe_obs"].append(probe)

    # gate + assembly
    paths: dict[str, dict] = defaultdict(dict)
    for (method, canonical_path), bucket in sorted(ops.items()):
        if not admit(method, bucket["ui_obs"], bucket["probe_obs"]):
            continue  # not admitted → failed probes are diagnostics only and stay out of augmented (D31)
        paths[canonical_path][method.lower()] = _build_operation(
            method, canonical_path, bucket["initial_op"],
            bucket["ui_obs"], bucket["probe_obs"], run_created_at,
            response_probe_paths,
        )

    document = {
        "openapi": "3.1.0",
        "info": initial_oas.get("info", {"title": "augmented", "version": "0.0.0-augmented"}),
        "servers": initial_oas.get("servers", []),
        "paths": dict(paths),
        "x-carverflow-meta": make_envelope(
            artifact_type="augmented_oas",
            stage="stage3",
            run_id=_new_run_id(),
            upstream_refs=[
                {"artifact_type": "initial_oas", "run_id": initial_oas["x-carverflow-meta"]["run_id"]},
                {"artifact_type": "probe_results", "run_id": probe_results["metadata"]["run_id"]},
            ],
        ),
    }
    return document


def _dedupe_probe_candidates(probes: list[dict]) -> list[dict]:
    out: dict[str, dict] = {}
    for probe in probes:
        probe_id = probe.get("probe_id")
        if not probe_id:
            continue
        out.setdefault(str(probe_id), probe)
    return [out[key] for key in sorted(out)]


def _template_inference_record(
    probe_obs: list[dict],
    resolutions: dict[str, ProbePathResolution],
) -> dict | None:
    relevant = [
        (probe, resolutions[probe["probe_id"]])
        for probe in probe_obs
        if probe.get("probe_id") in resolutions
    ]
    if not relevant:
        return None
    param_bindings: dict[tuple[str, int], dict] = {}
    probe_ids: set[str] = set()
    reasons: set[str] = set()
    example_values: set[str] = set()
    for probe, resolution in relevant:
        probe_ids.add(probe["probe_id"])
        reasons.add(resolution.reason)
        example_values.update(resolution.example_values)
        for binding in resolution.param_bindings:
            key = (str(binding.get("param")), int(binding.get("position", -1)))
            existing = param_bindings.get(key)
            merged = _merge_param_binding(existing, binding) if existing else dict(binding)
            param_bindings[key] = merged
    if not param_bindings:
        return None
    return {
        "source": "stage3_probe_template_gate",
        "reasons": sorted(reasons),
        "probe_ids": sorted(probe_ids),
        "example_values": sorted(example_values),
        "param_bindings": [
            _normalized_param_binding(binding)
            for _key, binding in sorted(param_bindings.items(), key=lambda item: (item[0][1], item[0][0]))
        ],
    }


def _merge_param_binding(existing: dict | None, incoming: dict) -> dict:
    if existing is None:
        return dict(incoming)
    merged = dict(existing)
    for list_field in ("source_entry_ids", "example_values"):
        merged[list_field] = sorted(set(merged.get(list_field) or []) | set(incoming.get(list_field) or []))
    for source_field in ("source_jsonpath", "source_xpath", "source_field"):
        if not merged.get(source_field) and incoming.get(source_field):
            merged[source_field] = incoming[source_field]
    return merged


def _normalized_param_binding(binding: dict) -> dict:
    out = {
        "param": str(binding.get("param")),
        "position": int(binding.get("position", -1)),
        "source_location": str(binding.get("source_location") or "response_body"),
        "source_entry_ids": sorted(set(binding.get("source_entry_ids") or [])),
        "example_values": sorted(set(binding.get("example_values") or [])),
    }
    for source_field in ("source_jsonpath", "source_xpath", "source_field"):
        if binding.get(source_field):
            out[source_field] = binding[source_field]
    return out


def _new_run_id() -> str:
    import secrets as _pysecrets
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r{stamp}-{_pysecrets.token_hex(2)}"


def canonical_dumps(document: dict) -> str:
    """D34/E7: canonical serialization exit (same rules as Stage 2: sort_keys/fixed indentation/no NaN)."""
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"


def operation_set(document: dict) -> set[tuple[str, str]]:
    return {(m.upper(), p) for p, item in document["paths"].items() for m in item}


def run_stage3(initial_oas_path: str | Path, probe_results_path: str | Path,
               artifacts_root: str | Path | None = None) -> tuple[dict, Path]:
    """Entry point: read (schema-validated) → gate → contract validation → write to disk."""
    initial_oas = json.loads(Path(initial_oas_path).read_text())
    validate_artifact("initial_oas.schema.json", initial_oas)
    probe_results = json.loads(Path(probe_results_path).read_text())
    validate_artifact("probe_results.schema.json", probe_results)

    document = build_augmented_oas(initial_oas, probe_results)
    validate_artifact("augmented_oas.schema.json", document)  # schema-validate before writing

    artifacts_root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = artifacts_root / document["x-carverflow-meta"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "augmented_oas.json"
    out_path.write_text(canonical_dumps(document))
    return document, out_path
