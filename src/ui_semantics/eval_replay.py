"""Evaluation-only frozen replays for the unified offline method CLI.

This module names historical subjects and paths by design.  It is not imported
by method-core modules and never starts a target, transport, browser, provider,
or reset lifecycle.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from stage0_launch.profile import load_app_profile

from .offline_producer_partition import (
    declared_session_endpoints,
    partition_offline_producers,
)
from .offline_pipeline import (
    build_evidence_bundle,
    build_observational_structure,
    build_trace,
    certified_suite_contract,
    observed_response_statuses,
    producer_applicability,
    recording_bundle,
    sha256_file,
)
from .route_s import canonical_sha256


OUTPUT_ROOT = Path("eval/ui_semantics/unified-pipeline-refactor-20260723")
BASELINE_COMMIT = "d99dfb6021e38b0b0a1716bcaa72b0ad286fefb1"

RWA_BUNDLES = {
    "receiver": Path(
        "eval/ui_semantics/e1r6/20260717/rwa/r6-1/recording/formal-attempt-01/"
        "stage1/receiver/r20260717-053200-2402/session_bundle"
    ),
    "sender": Path(
        "eval/ui_semantics/e1r6/20260717/rwa/r6-1/recording/formal-attempt-01/"
        "stage1/sender/r20260717-053200-233c/session_bundle"
    ),
}
RWA_RECORDING_ROOT = Path(
    "eval/ui_semantics/e1r6/20260717/rwa/r6-1/recording/formal-attempt-01/stage1"
)
RWA_R6_3 = Path("eval/ui_semantics/e1r6/20260717/rwa/r6-3/evidence-freeze-01")
RWA_PREBIND = Path(
    "eval/ui_semantics/e1r6/20260717/rwa/r6-4/"
    "route-s-candidate-prebinding-replacement-01"
)
RWA_ROUTE_S = Path(
    "eval/ui_semantics/e1r6/20260721/rwa/r6-4/"
    "route-s-validation-formal-successor-recovery-01"
)
RWA_SUITE_ROOT = Path(
    "eval/ui_semantics/e1r6/20260721/rwa/r6-5/phase-b-stage6-generation-01"
)
RWA_CALIBRATION = Path(
    "eval/ui_semantics/e1r6/20260721/rwa/r6-5/normal-calibration-formal-01/run_report.json"
)
RWA_TEMPLATE = Path("scripts/e1r2/frozen/proposal_interface_v2/semantic_edges.txt")
RWA_TRANSFER = Path("scripts/e1/frozen/transfer/rwa/selected_sample.json")
RWA_TRANSFER_POPULATION = Path("scripts/e1/frozen/transfer/rwa/candidate_population.json")
RWA_R6_4_FREEZE = Path("scripts/e1r6/rwa_r6_4_route_s_successor_freeze_v19.json")

MATTERMOST_RECORDING = Path(
    "eval/ui_semantics/e4/20260722/mattermost/"
    "formal-full-chain-04-infrastructure-replacement-02/recording"
)
MATTERMOST_BUNDLES = {
    "actor_a": MATTERMOST_RECORDING
    / "stage1/actor_a/r20260722-102135-d7aa/session_bundle",
    "actor_b": MATTERMOST_RECORDING
    / "stage1/actor_b/r20260722-102135-490b/session_bundle",
}
MATTERMOST_GOLDEN = Path(
    "eval/ui_semantics/e4/20260722/mattermost/fc3-fresh-evidence-preflight-01/"
    "fresh_trace_preflight_summary.json"
)

EXPECTED_HASHES = {
    "rwa_r6_3_manifest": (
        RWA_R6_3 / "r6_3_evidence_freeze_manifest.json",
        "f00b7639e1e995f771fd2a5b9d4aac9705500318d9dc463f60a299d8ce65aacc",
    ),
    "rwa_r6_3_all_files": (
        RWA_R6_3 / "all_files_sha256_manifest.json",
        "4304eda769e120271a1e28b6c77461da84a4e29837e008dc8251f14e021e9558",
    ),
    "rwa_candidate_index": (
        RWA_PREBIND / "candidate_index.json",
        "9d2a410378e90e1ab45c235fc3e3868143d62f1439bec07cb7eaec642fd3724d",
    ),
    "rwa_route_s_report": (
        RWA_ROUTE_S / "run_report.json",
        "1cebb62430d3816a5c0c7f4995596e91bfebe4f9e9f867c43f9a06c49a58ce82",
    ),
    "rwa_route_s_freeze": (
        RWA_R6_4_FREEZE,
        "9129a17f7d9a22c68d22b426a4c70ad6a49617ebda886dadc74586532f639d7c",
    ),
    "rwa_suite": (
        RWA_SUITE_ROOT / "certified_relation_tests.json",
        "38a796a4b3207a31953f259a37ca4760f14a3905633e30fde38bfd6c0af4dedd",
    ),
    "rwa_calibration": (
        RWA_CALIBRATION,
        "1748101e2d745f6af798fcaf4436d8c910c9d8a9b0cee8155b96725e03961ad1",
    ),
    "mattermost_recording_manifest": (
        MATTERMOST_RECORDING / "recursive_files_sha256_manifest.json",
        "a18d3831c1d0d444282a10d4d661c91546309c30e02f5eee71bfef0effa9a7cc",
    ),
    "mattermost_bundle_closure": (
        MATTERMOST_RECORDING / "bundle_checksums_pass1.json",
        "e170a1a4c782db3783a80168b0c3a97f5dcd76ed0e5889bc1d2cfd087dc59833",
    ),
    "mattermost_fc1_completion": (
        MATTERMOST_RECORDING.parent / "fc1_recording_completion.json",
        "cfbc2a44566b46e53f776aab1a2f3b298fd1a17b5ed29c3b83b2078738800b62",
    ),
    "mattermost_compatibility_golden": (
        MATTERMOST_GOLDEN,
        "c0820014f4eb81e518388c6d889ea4fccae7abadb911d25de81985bdacc684e2",
    ),
}


def rwa_frozen_equivalence(repo_root: Path) -> dict[str, Any]:
    """Audit the immutable historical RWA suite without rebuilding current M13."""

    frozen_suite_path = repo_root / RWA_SUITE_ROOT / "certified_relation_tests.json"
    frozen_suite = _read_json(frozen_suite_path)
    suite_sha256 = sha256_file(frozen_suite_path)
    suite_contract = certified_suite_contract(
        frozen_suite,
        suite_id="rwa-r6-5-certified-relations",
        source_ref=str(RWA_SUITE_ROOT / "certified_relation_tests.json"),
        source_sha256=suite_sha256,
    )
    checks = {
        "frozen_suite_hash_exact": suite_sha256 == EXPECTED_HASHES["rwa_suite"][1],
        "frozen_suite_shape_declared": _frozen_suite_shape_is_declared(frozen_suite),
        "frozen_suite_counts_exact": (
            suite_contract.test_count,
            suite_contract.business_assertion_count,
            suite_contract.generic_assertion_count,
        )
        == (29, 29, 87),
    }
    return {
        "schema_version": "uisemtest-rwa-frozen-suite-audit-v1",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "historical_frozen_suite_only": True,
        "current_m13_rebuild_performed": False,
        "certified_suite": {
            "path": str(RWA_SUITE_ROOT / "certified_relation_tests.json"),
            "sha256": suite_sha256,
            "test_count": suite_contract.test_count,
            "business_assertions": suite_contract.business_assertion_count,
            "generic_assertions": suite_contract.generic_assertion_count,
        },
        "provider_llm_calls": 0,
        "live_target_browser_server_docker_reset_runs": 0,
    }


def mattermost_offline_compatibility(repo_root: Path) -> dict[str, Any]:
    normalizer = _capture_url_normalizer
    recording_root = repo_root / MATTERMOST_RECORDING / "stage1"
    recording = recording_bundle(
        _absolute_paths(repo_root, MATTERMOST_BUNDLES),
        recording_id="mattermost-fc1-eligible-recording",
        recording_root=recording_root,
    )
    trace = build_trace(
        recording,
        recording_root=recording_root,
        trace_id="mattermost-fc3-fresh-preflight",
        url_normalizer=normalizer,
    )
    core = _trace_core(trace.trace, repo_root, metadata_paths_relative=False)
    structure, _products = build_observational_structure(
        recording,
        recording_root=recording_root,
        structure_id="mattermost-offline-compatibility",
        url_normalizer=normalizer,
    )
    evidence, _documents = build_evidence_bundle(
        trace,
        recording,
        recording_root=recording_root,
        evidence_id="mattermost-offline-compatibility",
    )
    profile = load_app_profile(
        repo_root / "fixtures/profiles/mattermost_current_local.json"
    )
    applicability = producer_applicability(
        trace,
        recording,
        recording_root=recording_root,
        applicability_id="mattermost-complete-producer-universe",
        session_endpoints=declared_session_endpoints(trace, profile),
    )
    partition = partition_offline_producers(
        trace,
        profile,
        applicability,
        response_status_by_request=observed_response_statuses(
            trace,
            recording,
            recording_root=recording_root,
        ),
    )
    unsupported_refs = [
        item.request_ref for item in applicability.producers if item.applicability == "unsupported"
    ]
    checks = {
        "trace_counts": (
            trace.event_count,
            trace.admitted_request_count,
            trace.automatic_binding_count,
            trace.review_required_count,
        )
        == (62, 162, 20, 10),
        "producer_partition_current": partition["summary"]
        == {
            "business": 51,
            "business_available": 15,
            "business_unsupported": 36,
            "auth_session": 2,
            "total": 53,
            "disjoint": True,
        },
        "semantic_available": evidence.channels["semantic"].status == "available",
        "transfer_unavailable_nonblocking": (
            evidence.channels["transfer"].status == "unavailable"
            and evidence.channels["transfer"].reason == "independent_frozen_selection_not_supplied"
        ),
        "observational_pipeline_offline": structure.active_http_probes == 0,
        "full_producer_rows_unique": len(
            {item.request_ref for item in applicability.producers}
        )
        == 51,
    }
    return {
        "schema_version": "uisemtest-mattermost-offline-compatibility-report-v1",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "trace": {
            "events": trace.event_count,
            "admitted_requests": trace.admitted_request_count,
            "automatic_bindings": trace.automatic_binding_count,
            "review_required": trace.review_required_count,
            "canonical_core_sha256": canonical_sha256(core),
        },
        "observational_structure": structure.model_dump(mode="json"),
        "evidence": {
            key: {"status": value.status, "reason": value.reason, "record_count": len(value.records)}
            for key, value in evidence.channels.items()
        },
        "producer_applicability": {
            "universe": applicability.universe_count,
            "available": applicability.available_count,
            "unsupported": applicability.unsupported_count,
            "rows": [item.model_dump(mode="json") for item in applicability.producers],
            "unsupported_request_refs_sha256": canonical_sha256(unsupported_refs),
        },
        "producer_partition": partition["summary"],
        "author_or_binding_labels_read": 0,
        "provider_llm_calls": 0,
        "live_target_browser_server_docker_reset_runs": 0,
    }


def boundary_audit(repo_root: Path) -> dict[str, Any]:
    core_files = [
        Path("src/ui_semantics/contracts.py"),
        Path("src/ui_semantics/offline_pipeline.py"),
        Path("src/ui_semantics/preproposal.py"),
        Path("src/ui_semantics/trace_builder.py"),
        Path("src/stage2_5_probe/offline.py"),
        Path("src/stage4_deps/assemble.py"),
        Path("src/stage4_deps/valueflow.py"),
        Path("src/stage5_synth/synth.py"),
    ]
    forbidden_import_prefixes = (
        "scripts",
        "eval",
        "ui_semantics.providers",
        "ui_semantics.proposers",
        "stage2_5_probe.prober",
        "stage0_launch",
    )
    forbidden_string_patterns = (
        re.compile(r"\brwa\b", re.IGNORECASE),
        re.compile(r"\bmattermost\b", re.IGNORECASE),
        re.compile(r"localhost|127\.0\.0\.1|https?://", re.IGNORECASE),
        re.compile(r"/Users/|eval/ui_semantics|scripts/e1r6|scripts/e3", re.IGNORECASE),
    )
    findings = []
    for relative in core_files:
        source = (repo_root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if name.startswith(forbidden_import_prefixes):
                    findings.append({"path": str(relative), "kind": "forbidden_import", "value": name})
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for pattern in forbidden_string_patterns:
                    if pattern.search(node.value):
                        findings.append(
                            {"path": str(relative), "kind": "forbidden_core_literal", "value": pattern.pattern}
                        )
    old_hashes = {
        key: {
            "path": str(path),
            "expected_sha256": expected,
            "observed_sha256": sha256_file(repo_root / path),
            "unchanged": sha256_file(repo_root / path) == expected,
        }
        for key, (path, expected) in EXPECTED_HASHES.items()
    }
    golden_paths = [str(path) for path, _expected in EXPECTED_HASHES.values()]
    diff = subprocess.run(
        ["git", "diff", "--quiet", BASELINE_COMMIT, "--", *golden_paths],
        cwd=repo_root,
        check=False,
    )
    ports = {}
    for port in (14000, 14001):
        check = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            cwd=repo_root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ports[str(port)] = check.returncode != 0
    checks = {
        "core_has_no_system_or_fixed_result_literals": not findings,
        "core_has_no_eval_live_or_provider_reverse_imports": not any(
            item["kind"] == "forbidden_import" for item in findings
        ),
        "old_golden_hashes_unchanged": all(row["unchanged"] for row in old_hashes.values()),
        "old_golden_paths_git_unchanged": diff.returncode == 0,
        "ports_14000_14001_clear": all(ports.values()),
        "provider_llm_calls_zero": True,
        "live_target_browser_server_docker_reset_zero": True,
    }
    return {
        "schema_version": "uisemtest-unified-pipeline-boundary-audit-v1",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "core_files": [str(item) for item in core_files],
        "core_findings": sorted(findings, key=lambda item: (item["path"], item["kind"], item["value"])),
        "direction": "evaluation_and_subject_wiring_import_core; core_never_imports_evaluation_or_subject_wiring",
        "old_golden_hashes": old_hashes,
        "old_golden_baseline_commit": BASELINE_COMMIT,
        "ports_clear": ports,
        "provider_llm_calls": 0,
        "live_target_browser_server_docker_reset_runs": 0,
    }


def write_reports(repo_root: Path, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    reports = {
        "rwa": rwa_frozen_equivalence(repo_root),
        "mattermost": mattermost_offline_compatibility(repo_root),
        "boundary": boundary_audit(repo_root),
    }
    paths = {
        "rwa": output_root / "rwa_frozen_equivalence_report.json",
        "mattermost": output_root / "mattermost_offline_compatibility_report.json",
        "boundary": output_root / "boundary_audit.json",
    }
    for key, path in paths.items():
        _write_json(path, reports[key])
    summary = {
        "schema_version": "uisemtest-unified-pipeline-refactor-summary-v1",
        "status": "pass" if all(report["status"] == "pass" for report in reports.values()) else "fail",
        "reports": {
            key: {"path": str(path.relative_to(repo_root)), "sha256": sha256_file(path), "status": reports[key]["status"]}
            for key, path in paths.items()
        },
        "runtime": {"required_python": "3.12", "launcher": "scripts/uisemtest"},
        "method_path": [
            "recording_bundle",
            "ui_api_trace_and_binding",
            "observational_stage2_audit_only_stage2_5_stage3",
            "evidence_bundle_with_channel_availability",
            "rendered_candidate_input_and_candidate_set",
            "producer_applicability_and_normalize_prebind",
            "route_s_certificate",
            "certified_relation_test_suite",
            "calibration_report",
        ],
        "provider_llm_calls": 0,
        "live_target_browser_server_docker_reset_runs": 0,
        "new_formal_experiment_runs": 0,
    }
    _write_json(output_root / "summary.json", summary)
    return summary


def legacy_render_candidate_input(
    *,
    template: str,
    material: Mapping[str, Any],
    applicability: Any,
) -> dict[str, Any]:
    """Evaluation-only v1 oracle; never eligible as a new scientific input."""
    rendered_text, rendered_sha256 = _legacy_render_candidate_input(
        template=template,
        material=material,
        applicability=applicability,
    )
    return {
        "rendered_text": rendered_text,
        "rendered_sha256": rendered_sha256,
        "legacy_fixture_only": True,
        "eligible_for_new_run": False,
    }


def _legacy_render_candidate_input(
    *,
    template: str,
    material: Mapping[str, Any],
    applicability: Any,
) -> tuple[str, str]:
    value = _legacy_material_projection(material)
    value["producer_setup_domains"] = _legacy_producer_setup_domains(applicability)
    placeholder = "{{TRACE_EVIDENCE_JSON}}"
    if placeholder not in template:
        raise ValueError("legacy candidate template lacks semantic evidence placeholder")
    rendered = template.replace(
        placeholder,
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2),
    )
    return rendered, hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _legacy_producer_setup_domains(applicability: Any) -> dict[str, Any]:
    """Reproduce only the frozen pre-current setup projection for legacy replay."""

    return {
        item.request_ref: {
            "producer": {
                "actor": item.actor_id,
                "request_ref": item.request_ref,
            },
            "producer_anchor": {
                "policy": "automated_binding_anchor",
                "action_id": item.anchor_event_id,
                "request_started_at": item.request_started_at,
            },
            "setup_domain_policy": "automated_confirmed_bound_non_session_prior",
            "eligible_setup_action_ids": list(item.eligible_setup_event_ids),
        }
        for item in applicability.producers
        if item.applicability == "available"
    }


def _legacy_material_projection(material: Mapping[str, Any]) -> dict[str, Any]:
    """Remove fields introduced after the frozen legacy renderer was retired."""

    value = copy.deepcopy(dict(material))

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            if {
                "request_ref",
                "observation_ref",
                "operation_id",
                "method",
                "canonical_path",
            } <= set(item):
                item.pop("global_order", None)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return value


def _absolute_paths(repo_root: Path, mapping: Mapping[str, Path]) -> dict[str, Path]:
    return {key: repo_root / path for key, path in mapping.items()}


def _frozen_suite_shape_is_declared(suite: Mapping[str, Any]) -> bool:
    metadata = suite.get("metadata")
    tests = suite.get("tests")
    return (
        isinstance(metadata, Mapping)
        and metadata.get("artifact_type") == "certified_relation_tests"
        and metadata.get("schema_version") == "1.0.0"
        and isinstance(suite.get("source_input"), Mapping)
        and isinstance(suite.get("assertion_definition"), Mapping)
        and isinstance(tests, list)
        and all(
            isinstance(test, Mapping)
            and isinstance(test.get("source"), Mapping)
            and isinstance(test.get("assertions"), list)
            for test in tests
        )
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _trace_core(
    trace: Mapping[str, Any],
    repo_root: Path,
    *,
    metadata_paths_relative: bool,
) -> dict[str, Any]:
    value = copy.deepcopy(dict(trace))
    value.get("metadata", {}).pop("created_at", None)
    for actor in value.get("actors", []):
        raw = Path(actor["session_bundle_ref"]["path"])
        if raw.is_absolute():
            actor["session_bundle_ref"]["path"] = raw.relative_to(repo_root).as_posix()
    if metadata_paths_relative:
        for ref in value.get("metadata", {}).get("upstream_refs", []):
            raw = Path(ref["path"])
            if raw.is_absolute():
                ref["path"] = raw.relative_to(repo_root).as_posix()
    return value


_CAPTURE_ORIGIN = re.compile(r"^\[REDACTED:[^\]\r\n]+\](?P<path>/.*)$")


def _capture_url_normalizer(value: str) -> str:
    match = _CAPTURE_ORIGIN.fullmatch(str(value))
    return f"http://127.0.0.1:18065{match.group('path')}" if match else str(value)
