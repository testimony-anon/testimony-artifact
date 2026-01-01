"""Suite organization with bounded M10 calls and serial target execution.

Suite metadata is consumed only by this orchestration/reporting owner.  Each
case is still recorded and executed by the existing single-workflow owners,
and no suite field is added to M1-M14 scientific artifacts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from argparse import Namespace
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping

from common.contracts import validate_artifact
from stage1_record.workflow import load_recording_workflow


_ORGANIZATION_KEYS = frozenset(
    {
        "suite_id",
        "module_id",
        "case_id",
        "layer",
        "initial_auth",
        "human_test_goal",
        "expected_relation",
        "expected_result",
        "expected_verdict",
    }
)
_FROZEN_M10_INPUT_FILES = (
    "input_freeze_manifest.json",
    "preproposal_evidence_package.json",
    "proposal_evidence_view.json",
    "rendered_candidate_input.json",
    "effect_contract_v2.txt",
)


def load_recording_suite(path: str | Path) -> dict[str, Any]:
    suite_path = Path(path).resolve(strict=True)
    raw = _read_object(suite_path)
    validate_artifact("recording_suite.schema.json", raw)
    cases = raw["cases"]
    case_ids = [str(case["case_id"]) for case in cases]
    workflow_refs = [str(case["workflow"]) for case in cases]
    module_ids = [str(module["module_id"]) for module in raw["modules"]]
    assigned = [
        str(case_id)
        for module in raw["modules"]
        for case_id in module["case_ids"]
    ]
    if raw["case_count"] != len(cases):
        raise ValueError("suite case_count differs from its cases")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("suite case IDs must be unique")
    if len(workflow_refs) != len(set(workflow_refs)):
        raise ValueError("suite workflow refs must be unique")
    if len(module_ids) != len(set(module_ids)):
        raise ValueError("suite module IDs must be unique")
    if len(assigned) != len(set(assigned)) or set(assigned) != set(case_ids):
        raise ValueError("suite modules must partition every case exactly once")
    suite_root = suite_path.parent
    suite_identities = {
        "suite_id": (str(raw["suite_id"]),),
        "case_id": tuple(case_ids),
    }
    for case in cases:
        workflow_path = (suite_root / str(case["workflow"])).resolve(strict=True)
        if not workflow_path.is_relative_to(suite_root):
            raise ValueError("suite workflow ref escapes its manifest directory")
        workflow = load_recording_workflow(workflow_path)
        if [actor.actor_id for actor in workflow.actors] != list(case["actors"]):
            raise ValueError("suite actor list differs from its typed workflow")
        workflow_payload = _read_object(workflow_path)
        workflow_payload.pop("workflow_id", None)
        leaked = _find_normalized_identity_values(
            workflow_payload,
            identities=suite_identities,
        )
        if leaked:
            raise ValueError(
                "suite organization identity appears in workflow scientific input: "
                + ", ".join(leaked)
            )
    return raw


def record_current_suite(
    suite_path: str | Path,
    *,
    artifacts_root: str | Path,
    headless: bool,
    repo_root: Path,
    recorder: Callable[..., dict[str, Any]],
    require_execution_lock: bool = True,
) -> dict[str, Any]:
    manifest_path = Path(suite_path).resolve(strict=True)
    suite = load_recording_suite(manifest_path)
    target = Path(artifacts_root).resolve()
    if require_execution_lock:
        _require_suite_execution_lock(
            repo_root,
            entrypoint="scripts/uisemtest record",
            suite_path=manifest_path,
            subject=str(suite["subject"]),
            recording_root=target,
            qualification_root=None,
        )
    if target.exists():
        raise ValueError("suite recording root must be fresh and must not already exist")
    target.mkdir(parents=True)
    (target / "suite_manifest.json").write_bytes(manifest_path.read_bytes())
    module_by_case = _module_by_case(suite)
    case_rows: list[dict[str, Any]] = []
    for case in suite["cases"]:
        case_id = str(case["case_id"])
        case_root = target / "cases" / case_id
        workflow_path = manifest_path.parent / str(case["workflow"])
        try:
            result = recorder(
                workflow_path,
                artifacts_root=case_root,
                headless=headless,
            )
            status = str(result["status"])
            failure = copy.deepcopy(result.get("failure"))
            reset_epoch = str(result.get("reset_epoch", {}).get("record_id", ""))
            if status == "completed" and not reset_epoch:
                raise ValueError("completed suite case lacks a reset epoch")
        except Exception as error:
            status = "rejected"
            failure = {
                "phase": "suite_case_dispatch",
                "reason_code": type(error).__name__,
                "message": str(error),
            }
            reset_epoch = ""
        case_rows.append(
            {
                "case_id": case_id,
                "module_id": module_by_case[case_id],
                "workflow_ref": str(case["workflow"]),
                "recording_root_ref": f"cases/{case_id}",
                "status": status,
                "reset_epoch": reset_epoch,
                "failure": failure,
            }
        )
    seen_resets: set[str] = set()
    for row in case_rows:
        reset_epoch = str(row["reset_epoch"])
        if row["status"] != "completed" or not reset_epoch:
            continue
        if reset_epoch in seen_resets:
            row["status"] = "rejected"
            row["failure"] = {
                "phase": "suite_reset_isolation",
                "reason_code": "duplicate_reset_epoch",
                "message": "suite cases must not reuse one reset epoch",
            }
            continue
        seen_resets.add(reset_epoch)
    completed = sum(row["status"] == "completed" for row in case_rows)
    resets = [row["reset_epoch"] for row in case_rows if row["reset_epoch"]]
    result = {
        "schema_version": "uisemtest-recording-suite-result-v1",
        "status": "completed" if completed == len(case_rows) else "rejected",
        "suite_id": suite["suite_id"],
        "subject": suite["subject"],
        "suite_manifest_ref": "suite_manifest.json",
        "case_count": len(case_rows),
        "completed_case_count": completed,
        "rejected_case_count": len(case_rows) - completed,
        "distinct_reset_count": len(set(resets)),
        "reset_isolation_closed": completed == len(case_rows),
        "serial_execution": True,
        "paper_data": False,
        "provider_llm_calls": 0,
        "cases": case_rows,
    }
    _write_json(target / "suite_recording_result.json", result)
    return {**result, "recording_root": str(target)}


def run_current_suite(
    args: Namespace,
    *,
    repo_root: Path,
    offline_builder: Callable[[Namespace], dict[str, Any]],
    single_runner: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    manifest_path = Path(args.suite).resolve(strict=True)
    suite = load_recording_suite(manifest_path)
    recording_root = Path(args.recording_root).resolve(strict=True)
    target = Path(args.output_root).resolve()
    paper_data_authorized = _require_suite_execution_lock(
        repo_root,
        entrypoint="scripts/uisemtest run",
        suite_path=manifest_path,
        subject=str(suite["subject"]),
        recording_root=recording_root,
        qualification_root=target,
        adapter_path=Path(args.adapter).resolve(strict=True),
        proposal_path=Path(args.proposal_plan).resolve(strict=True),
        provider_kind=str(args.provider),
        output_level=str(args.output_level),
        probe_budget=int(args.probe_budget),
        stop_after_m9=bool(args.stop_after_m9),
        m10_samples=int(args.m10_samples),
        m10_sample_mode=str(args.m10_sample_mode),
        provider_concurrency=int(args.provider_concurrency),
    )
    recording_result = _read_object(recording_root / "suite_recording_result.json")
    if recording_result.get("status") != "completed":
        raise ValueError("suite run requires a completed suite recording root")
    if (recording_root / "suite_manifest.json").read_bytes() != manifest_path.read_bytes():
        raise ValueError("suite recording manifest differs from the requested suite")
    expected_cases = [str(case["case_id"]) for case in suite["cases"]]
    recorded_rows = recording_result.get("cases", [])
    if not isinstance(recorded_rows, list):
        raise ValueError("suite recording cases are invalid")
    reset_epochs = [str(row.get("reset_epoch") or "") for row in recorded_rows]
    recording_closed = (
        recording_result.get("case_count") == len(expected_cases)
        and recording_result.get("completed_case_count") == len(expected_cases)
        and recording_result.get("rejected_case_count") == 0
        and recording_result.get("distinct_reset_count") == len(expected_cases)
        and recording_result.get("serial_execution") is True
        and recording_result.get("provider_llm_calls") == 0
        and len(recorded_rows) == len(expected_cases)
        and all(reset_epochs)
        and len(set(reset_epochs)) == len(expected_cases)
    )
    if not recording_closed:
        raise ValueError("suite recording reset/case isolation does not close")
    recorded_by_case = _validate_recorded_case_closure(
        suite=suite,
        manifest_path=manifest_path,
        recording_root=recording_root,
        recorded_rows=recorded_rows,
        repo_root=repo_root,
    )
    resume = bool(getattr(args, "resume_incomplete_m10", False))
    if target.exists() and not resume:
        raise ValueError("suite run output root must be fresh and must not already exist")
    if resume:
        if (target / "suite_manifest.json").read_bytes() != manifest_path.read_bytes():
            raise ValueError("suite recovery manifest differs from the requested suite")
    else:
        target.mkdir(parents=True)
        (target / "suite_manifest.json").write_bytes(manifest_path.read_bytes())
    module_by_case = _module_by_case(suite)
    rows: list[dict[str, Any]] = []
    children: dict[str, Namespace] = {}
    completed: dict[str, dict[str, Any]] = {}
    preparation_errors: dict[str, Exception] = {}
    parallel_m10 = (
        not bool(args.stop_after_m9)
        and int(args.probe_budget) == 0
        and str(args.m10_sample_mode) == "union"
    )
    from .current_provider import ProviderCallLimiter

    limiter = ProviderCallLimiter(int(args.provider_concurrency))
    for case in suite["cases"]:
        case_id = str(case["case_id"])
        recording_case_root = (
            recording_root / str(recorded_by_case[case_id]["recording_root_ref"])
        ).resolve(strict=True)
        if not recording_case_root.is_relative_to(recording_root):
            raise ValueError("suite case recording root escapes the suite root")
        workflow = load_recording_workflow(
            manifest_path.parent / str(case["workflow"])
        )
        profile_path = (repo_root / workflow.profile_ref).resolve(strict=True)
        case_target = target / "cases" / case_id
        child_args = Namespace(**vars(args))
        child_args.suite = None
        child_args.profile = profile_path
        child_args.recording_root = recording_case_root
        child_args.output_root = case_target
        child_args.resume_incomplete_m10 = resume and case_target.exists()
        child_args._suite_execution_authorized = True
        child_args._paper_data_authorized = paper_data_authorized
        child_args._provider_call_limiter = limiter
        children[case_id] = child_args
        try:
            saved_manifest = case_target / "run_manifest.json"
            if (
                child_args.resume_incomplete_m10
                and saved_manifest.is_file()
                and _read_object(saved_manifest).get("terminal_status") == "complete"
            ):
                from .current_orchestrator import _reuse_completed_current_output

                completed[case_id] = _reuse_completed_current_output(child_args, run_root=case_target)
        except Exception as error:
            preparation_errors[case_id] = error

    if parallel_m10:
        def freeze_m10(child_args: Namespace) -> None:
            freeze_args = Namespace(**vars(child_args))
            freeze_args._suite_m10_only = True
            report = single_runner(
                freeze_args, repo_root=repo_root, offline_builder=offline_builder,
            )
            if report.get("completion_reason") != "m10_round_union_complete_before_m11a":
                raise ValueError("suite case did not freeze its complete M10 union")

        pending = {
            case_id: child for case_id, child in children.items()
            if case_id not in completed and case_id not in preparation_errors
        }
        if pending:
            with ThreadPoolExecutor(max_workers=min(int(args.provider_concurrency), len(pending))) as executor:
                futures = {executor.submit(freeze_m10, child): case_id for case_id, child in pending.items()}
                for future in as_completed(futures):
                    case_id = futures[future]
                    try:
                        future.result()
                    except Exception as error:
                        preparation_errors[case_id] = error

    # No M10 preparation thread is alive while target/reset work is running.
    for case in suite["cases"]:
        case_id = str(case["case_id"])
        child_args = children[case_id]
        case_target = child_args.output_root
        recording_case_root = child_args.recording_root
        try:
            if case_id in preparation_errors:
                raise preparation_errors[case_id]
            report = completed.get(case_id)
            if report is None:
                child_args.resume_incomplete_m10 = case_target.exists()
                report = single_runner(
                    child_args,
                    repo_root=repo_root,
                    offline_builder=offline_builder,
                )
            if report.get("terminal_status") != "complete":
                raise ValueError("suite case did not reach its requested terminal boundary")
            scientific_run_root = _case_scientific_run_root(
                case_target,
                report,
                stop_after_m9=bool(args.stop_after_m9),
            )
            counts = _case_occurrence_counts(
                run_root=scientific_run_root,
                recording_root=recording_case_root,
            )
            isolation = inspect_scientific_metadata_isolation(
                scientific_run_root,
                suite_id=str(suite["suite_id"]),
                case_ids=expected_cases,
            )
            if isolation["status"] != "pass":
                raise ValueError("suite organization metadata entered scientific evidence")
            relation_cores = _downstream_relation_core_identities(scientific_run_root)
            m9_boundary = (
                _validate_m9_case_boundary(scientific_run_root)
                if bool(args.stop_after_m9)
                else None
            )
            rows.append(
                {
                    "case_id": case_id,
                    "module_id": module_by_case[case_id],
                    "status": "pass",
                    "run_root_ref": f"cases/{case_id}",
                    "terminal_stage": "M9" if bool(args.stop_after_m9) else "M14",
                    "occurrence_counts": counts,
                    "relation_core_identities": relation_cores,
                    "metadata_isolation": isolation,
                    "m9_boundary": m9_boundary,
                }
            )
        except Exception as error:
            rows.append(
                {
                    "case_id": case_id,
                    "module_id": module_by_case[case_id],
                    "status": "failed",
                    "run_root_ref": f"cases/{case_id}",
                    "terminal_stage": None,
                    "occurrence_counts": _empty_occurrence_counts(),
                    "relation_core_identities": None,
                    "metadata_isolation": {"status": "not_run"},
                    "failure": {
                        "kind": type(error).__name__,
                        "message": str(error),
                    },
                }
            )
    summary = aggregate_suite_case_summaries(suite, rows)
    summary["serial_case_execution"] = not parallel_m10
    summary["parallel_m10_preparation"] = parallel_m10
    summary["serial_target_execution"] = True
    summary["provider_concurrency_planned"] = int(args.provider_concurrency)
    summary["provider_concurrency_actual_max"] = limiter.actual_max
    summary["paper_data"] = paper_data_authorized and summary["status"] == "pass"
    _write_json(target / "suite_qualification_summary.json", summary)
    return {
        "schema_version": "uisemtest-current-suite-run-result-v1",
        "status": "pass" if summary["status"] == "pass" else "incomplete",
        "terminal_status": summary["terminal_status"],
        "completion_reason": summary["completion_reason"],
        "output_root": str(target),
        "suite_summary": str(target / "suite_qualification_summary.json"),
        "case_count": len(rows),
        "completed_case_count": sum(row["status"] == "pass" for row in rows),
        "provider_llm_calls": 0 if bool(args.stop_after_m9) else None,
    }


def aggregate_suite_case_summaries(
    suite: Mapping[str, Any], case_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    module_by_case = _module_by_case(suite)
    if [row["case_id"] for row in case_rows] != [
        case["case_id"] for case in suite["cases"]
    ]:
        raise ValueError("suite case summaries do not preserve manifest order")
    if any(row["module_id"] != module_by_case[row["case_id"]] for row in case_rows):
        raise ValueError("suite case summary module mapping drifted")
    by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in case_rows:
        by_module[str(row["module_id"])].append(row)
    modules = []
    for module in suite["modules"]:
        module_id = str(module["module_id"])
        rows = by_module[module_id]
        modules.append(
            {
                "module_id": module_id,
                "case_count": len(rows),
                "completed_case_count": sum(row["status"] == "pass" for row in rows),
                "occurrence_counts": _sum_occurrence_counts(rows),
                "relation_core_summaries": _relation_core_summaries(rows),
            }
        )
    completed = sum(row["status"] == "pass" for row in case_rows)
    all_m9 = completed == len(case_rows) and all(
        row["terminal_stage"] == "M9" for row in case_rows
    )
    return {
        "schema_version": "uisemtest-current-suite-qualification-summary-v1",
        "status": "pass" if completed == len(case_rows) else "incomplete",
        "terminal_status": "complete" if completed == len(case_rows) else "incomplete",
        "completion_reason": (
            "suite_m1_m9_complete_relation_cores_deferred"
            if all_m9
            else (
                "suite_terminal_cases_complete"
                if completed == len(case_rows)
                else "suite_case_failure"
            )
        ),
        "suite_id": suite["suite_id"],
        "subject": suite["subject"],
        "serial_case_execution": True,
        "case_count": len(case_rows),
        "completed_case_count": completed,
        "cases": case_rows,
        "modules": modules,
        "system": {
            "case_count": len(case_rows),
            "completed_case_count": completed,
            "occurrence_counts": _sum_occurrence_counts(case_rows),
            "relation_core_summaries": _relation_core_summaries(case_rows),
        },
    }


def inspect_scientific_metadata_isolation(
    run_root: Path, *, suite_id: str, case_ids: list[str]
) -> dict[str, Any]:
    evidence_root = run_root / "M01_09"
    forbidden_keys: set[str] = set()
    identity_value_hits: list[str] = []
    inspected: list[str] = []
    for name in _FROZEN_M10_INPUT_FILES:
        path = evidence_root / name
        if path.is_file():
            inspected.append(f"M01_09/{name}")
            text = path.read_text(encoding="utf-8")
            value = json.loads(text) if name.endswith(".json") else None
        elif name == "preproposal_evidence_package.json":
            value, replacement_refs = _reconstruct_paper_evidence_package(run_root)
            inspected.extend(replacement_refs)
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            raise ValueError(f"scientific provider artifact is missing: {name}")
        if value is not None:
            forbidden_keys.update(_find_keys(value) & _ORGANIZATION_KEYS)
        normalized_text = _normalized_identity(text)
        if re.search(r"wp[0-9]+", normalized_text):
            identity_value_hits.append(f"{name}:work_package")
        identities = {
            "suite_id": (suite_id,),
            "case_id": tuple(case_ids),
        }
        for label, needles in identities.items():
            if any(
                (normalized_needle := _normalized_identity(needle))
                and normalized_needle in normalized_text
                for needle in needles
            ):
                identity_value_hits.append(f"{name}:{label}")
    return {
        "status": "pass" if not forbidden_keys and not identity_value_hits else "fail",
        "inspected_files": inspected,
        "forbidden_keys": sorted(forbidden_keys),
        "organization_identity_value_hits": sorted(identity_value_hits),
    }


def _reconstruct_paper_evidence_package(
    run_root: Path,
) -> tuple[dict[str, Any], list[str]]:
    index_path = run_root / "M01_09/paper_evidence_index.json"
    if not index_path.is_file():
        raise ValueError(
            "scientific provider artifact is missing: "
            "preproposal_evidence_package.json"
        )
    index = _read_object(index_path)
    if (
        index.get("replaces_ref") != "M01_09/preproposal_evidence_package.json"
        or index.get("full_package_reconstructible_from_retained_artifacts") is not True
    ):
        raise ValueError("paper evidence package replacement is not reconstructible")
    metadata = index.get("package_metadata")
    artifacts = index.get("artifacts")
    if not isinstance(metadata, Mapping) or not isinstance(artifacts, Mapping):
        raise ValueError("paper evidence package replacement is incomplete")
    artifact_hashes = metadata.get("artifact_sha256")
    if not isinstance(artifact_hashes, Mapping) or set(artifact_hashes) != set(artifacts):
        raise ValueError("paper evidence package replacement artifact set drifted")

    payloads: dict[str, Any] = {}
    inspected = ["M01_09/paper_evidence_index.json"]
    resolved_root = run_root.resolve(strict=True)
    for artifact_name in sorted(artifacts):
        pin = artifacts[artifact_name]
        if not isinstance(pin, Mapping) or not isinstance(pin.get("path"), str):
            raise ValueError("paper evidence package replacement pin is invalid")
        artifact_path = (resolved_root / str(pin["path"])).resolve(strict=True)
        if not artifact_path.is_relative_to(resolved_root):
            raise ValueError("paper evidence package replacement escapes run root")
        raw = artifact_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin.get("file_sha256"):
            raise ValueError("paper evidence package replacement file hash drifted")
        payload = json.loads(raw)
        contract_sha = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if (
            contract_sha != pin.get("contract_sha256")
            or contract_sha != artifact_hashes[artifact_name]
        ):
            raise ValueError("paper evidence package replacement contract hash drifted")
        payloads[str(artifact_name)] = payload
        inspected.append(str(pin["path"]))

    package = dict(metadata)
    package["artifact_payloads"] = payloads
    package_sha = hashlib.sha256(
        json.dumps(
            package,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if package_sha != index.get("package_canonical_sha256"):
        raise ValueError("reconstructed paper evidence package hash drifted")
    freeze = _read_object(run_root / "M01_09/input_freeze_manifest.json")
    frozen_package = freeze.get("artifacts", {}).get("package", {})
    if (
        frozen_package.get("contract_sha256") != package_sha
        or frozen_package.get("file_sha256") != index.get("replaced_file_sha256")
    ):
        raise ValueError("paper evidence package replacement differs from M10 freeze")
    return package, inspected


def _normalized_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _find_normalized_identity_values(
    value: Any,
    *,
    identities: Mapping[str, tuple[str, ...]],
    path: str = "$",
) -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            hits.extend(
                _find_normalized_identity_values(
                    item,
                    identities=identities,
                    path=f"{path}.{key}",
                )
            )
        return hits
    if isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(
                _find_normalized_identity_values(
                    item,
                    identities=identities,
                    path=f"{path}[{index}]",
                )
            )
        return hits
    if not isinstance(value, str):
        return hits
    normalized_value = _normalized_identity(value)
    if re.search(r"wp[0-9]+", normalized_value):
        hits.append(f"{path}:work_package")
    for label, identity_values in identities.items():
        if any(
            (normalized_identity := _normalized_identity(identity))
            and normalized_identity in normalized_value
            for identity in identity_values
        ):
            hits.append(f"{path}:{label}")
    return hits


def _case_occurrence_counts(
    *, run_root: Path, recording_root: Path
) -> dict[str, dict[str, int]]:
    recording = _read_object(recording_root / "recording_workflow_result.json")
    trace = _read_object(run_root / "M01_09/ui_api_trace.json")
    structure = _read_object(run_root / "M01_09/observational_api_structure.json")
    audit = _read_object(run_root / "M01_09/discovery_candidate_audit.json")
    catalog = _read_object(run_root / "M01_09/observed_api_catalog.json")
    flows = _read_object(run_root / "M01_09/observed_value_flow_set.json")
    graph = _read_object(run_root / "M01_09/dependency_graph.json")
    opportunities = _read_object(run_root / "M01_09/binding_opportunity_set.json")
    applicability = _read_object(run_root / "M01_09/producer_applicability.json")
    partition = _read_object(run_root / "M01_09/producer_partition_summary.json")
    view = _read_object(run_root / "M01_09/proposal_evidence_view.json")
    trace_payload = trace["trace"]
    grouped = sum(
        len(group.get("members", []))
        for group in trace_payload["request_groups"]
    )
    unassigned = len(trace_payload["unassigned_requests"])
    cards = view["evidence_cards"]
    card_kind_counts: defaultdict[str, int] = defaultdict(int)
    atomic_request_occurrences = 0
    for card in cards:
        kind = str(card["card_kind"])
        card_kind_counts[kind] += 1
        if kind in {"action_episode", "unassigned_request"}:
            atomic_request_occurrences += len(card["request_refs"])
    setup_status: defaultdict[str, int] = defaultdict(int)
    for domain in view["request_setup_domains"].values():
        setup_status[str(domain["status"])] += 1
    ui_diff_summary = view["evidence_channel_summaries"].get("ui_diff", {})
    admitted = int(trace["admitted_request_count"])
    return {
        "M1": {
            "completed_recordings": int(recording["status"] == "completed"),
            "fresh_resets": int(bool(recording.get("reset_epoch", {}).get("record_id"))),
            "actors": len(recording["actor_bundles"]),
            "workflow_steps": len(recording["step_correspondence"]),
        },
        "M2": {
            "events": int(trace["event_count"]),
            "admitted_requests": admitted,
            "request_groups": len(trace_payload["request_groups"]),
            "grouped_requests": grouped,
            "unassigned_requests": unassigned,
            "automatic_anchors": int(trace["automatic_binding_count"]),
            "binding_reviews": int(trace["review_required_count"]),
            "request_accounting_cases_closed": int(grouped + unassigned == admitted),
        },
        "M3": {
            "stage2_operations": int(structure["stage2_operation_count"]),
            "stage2_5_records": int(structure["stage2_5_record_count"]),
            "stage3_operations": int(structure["stage3_operation_count"]),
        },
        "M4": {
            "planned": int(audit["planned_count"]),
            "executed": int(audit["executed_count"]),
            "admitted": int(audit["admitted_count"]),
            "rejected": int(audit["rejected_count"]),
            "not_executed": int(audit["not_executed_count"]),
        },
        "M5": {"observed_operations": int(catalog["operation_count"])},
        "M6": {"value_flow_occurrences": int(flows["occurrence_count"])},
        "M7": {"dependency_edges": int(graph["edge_count"])},
        "M8": {"binding_opportunities": int(opportunities["opportunity_count"])},
        "M9": {
            "producer_universe": int(applicability["universe_count"]),
            "producer_available": int(applicability["available_count"]),
            "producer_unsupported": int(applicability["unsupported_count"]),
            "auth_session_producers": int(partition["summary"]["auth_session"]),
            "evidence_cards": len(cards),
            "action_episode_cards": card_kind_counts["action_episode"],
            "unassigned_request_cards": card_kind_counts["unassigned_request"],
            "mechanical_neighborhood_cards": card_kind_counts[
                "mechanical_neighborhood"
            ],
            "proposal_target_cards": len(view["proposal_target_card_ids"]),
            "ui_diff_records": int(ui_diff_summary.get("record_count", 0)),
            "transition_facts": len(view["transition_facts"]),
            "setup_domains": len(view["request_setup_domains"]),
            "setup_available": setup_status["available"],
            "setup_unsupported": setup_status["unsupported"],
            "setup_not_applicable": setup_status["not_applicable"],
            "atomic_card_request_occurrences": atomic_request_occurrences,
            "atomic_request_accounting_cases_closed": int(
                atomic_request_occurrences == admitted
            ),
        },
    }


def _empty_occurrence_counts() -> dict[str, dict[str, int]]:
    return {f"M{stage}": {} for stage in range(1, 10)}


def _sum_occurrence_counts(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {f"M{stage}": {} for stage in range(1, 10)}
    for stage in result:
        keys = {
            key
            for row in rows
            for key in row["occurrence_counts"].get(stage, {})
        }
        result[stage] = {
            key: sum(
                int(row["occurrence_counts"].get(stage, {}).get(key, 0))
                for row in rows
            )
            for key in sorted(keys)
        }
    return result


def _relation_core_summaries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row.get("relation_core_identities") for row in rows]
    if any(value is None for value in values):
        return {
            stratum: {
                "status": "deferred_until_downstream_relations_exist",
                "occurrence_count": None,
                "unique_canonical_core_count": None,
                "deduplicated_occurrence_count": None,
            }
            for stratum in ("M10_admitted", "M14_retained")
        }
    result: dict[str, Any] = {}
    for stratum in ("M10_admitted", "M14_retained"):
        occurrences = [identity for value in values for identity in value[stratum]]
        unique = len(set(occurrences))
        result[stratum] = {
            "status": "available",
            "occurrence_count": len(occurrences),
            "unique_canonical_core_count": unique,
            "deduplicated_occurrence_count": len(occurrences) - unique,
        }
    return result


def _downstream_relation_core_identities(
    run_root: Path,
) -> dict[str, list[str]] | None:
    manifest = _read_object(run_root / "run_manifest.json")
    current_counts = manifest.get("current_counts", {})
    fields = {
        "M10_admitted": "admitted_canonical_relation_core_identities",
        "M14_retained": "retained_canonical_relation_core_identities",
    }
    values = {stratum: current_counts.get(field) for stratum, field in fields.items()}
    if all(value is None for value in values.values()):
        return None
    for value in values.values():
        if not isinstance(value, list) or any(
            not isinstance(identity, str)
            or len(identity) != 64
            or any(character not in "0123456789abcdef" for character in identity)
            for identity in value
        ):
            raise ValueError("downstream canonical relation core identities are invalid")
    return {stratum: list(value) for stratum, value in values.items()}


def _validate_m9_case_boundary(run_root: Path) -> dict[str, Any]:
    manifest = _read_object(run_root / "run_manifest.json")
    stages = [str(row.get("stage")) for row in manifest.get("stages", [])]
    counters = manifest.get("counters")
    if stages != [f"M{stage}" for stage in range(1, 10)]:
        raise ValueError("M9 suite case published a non-M1-M9 stage sequence")
    if not isinstance(counters, Mapping):
        raise ValueError("M9 suite case lacks execution counters")
    provider_keys = (
        "provider_logical_calls",
        "provider_transport_attempts",
        "external_provider_llm_calls",
        "external_network_calls",
        "real_target_runs",
        "real_browser_runs",
        "real_server_runs",
        "real_docker_runs",
        "real_reset_runs",
    )
    if any(counters.get(key) != 0 for key in provider_keys):
        raise ValueError("M9 suite case executed a provider")
    if any((run_root / stage).exists() for stage in ("M10", "M11a", "M11b", "M12", "M13", "M14")):
        raise ValueError("M9 suite case published downstream stage artifacts")
    if (
        manifest.get("execution_boundary")
        != "completed_m9_before_provider_execution"
        or manifest.get("paper_data") is not False
        or manifest.get("provider_preflight", {}).get("status") != "not_executed"
    ):
        raise ValueError("M9 suite case boundary metadata is invalid")
    return {
        "status": "pass",
        "provider_logical_calls": 0,
        "provider_transport_attempts": 0,
        "external_provider_llm_calls": 0,
        "external_network_calls": 0,
        "real_target_runs": 0,
        "real_browser_runs": 0,
        "real_server_runs": 0,
        "real_docker_runs": 0,
        "real_reset_runs": 0,
        "downstream_stage_artifacts": 0,
    }


def _case_scientific_run_root(
    case_root: Path,
    report: Mapping[str, Any],
    *,
    stop_after_m9: bool,
) -> Path:
    if stop_after_m9:
        return case_root
    ref = report.get("union_result_ref")
    if not isinstance(ref, str) or not ref.endswith("/run_manifest.json"):
        raise ValueError("full suite case must expose one canonical union terminal result")
    manifest = (case_root / ref).resolve(strict=True)
    if not manifest.is_relative_to(case_root.resolve()) or not manifest.is_file():
        raise ValueError("suite union terminal result escapes the case root")
    return manifest.parent


def _module_by_case(suite: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(case_id): str(module["module_id"])
        for module in suite["modules"]
        for case_id in module["case_ids"]
    }


def _find_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for item in value.values() for key in _find_keys(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in _find_keys(item)}
    return set()


def _require_suite_execution_lock(
    repo_root: Path,
    *,
    entrypoint: str,
    suite_path: Path,
    subject: str,
    recording_root: Path,
    qualification_root: Path | None,
    adapter_path: Path | None = None,
    proposal_path: Path | None = None,
    provider_kind: str | None = None,
    output_level: str | None = None,
    probe_budget: int | None = None,
    stop_after_m9: bool | None = None,
    m10_samples: int | None = None,
    m10_sample_mode: str | None = None,
    provider_concurrency: int | None = None,
) -> bool:
    active = _read_object(repo_root / "docs/ACTIVE-EXECUTION.json")
    if (
        active.get("live_allowed") is not True
        or entrypoint not in (active.get("allowed_entrypoints") or [])
    ):
        raise RuntimeError("suite execution is not authorized by ACTIVE")
    capability = active.get("current_execution_capability")
    listed = active.get("current_execution_capabilities")
    if isinstance(listed, list):
        # Two independent subjects may be authorized at once (their targets do
        # not share ports, databases or reset epochs); each suite selects only
        # the capability pinned to its own subject.
        matches = [
            item for item in listed
            if isinstance(item, Mapping) and item.get("subject_id") == subject
        ]
        if len(matches) != 1:
            raise RuntimeError("ACTIVE must list exactly one capability for the suite subject")
        capability = matches[0]
    if not isinstance(capability, Mapping):
        raise RuntimeError("ACTIVE lacks the suite execution capability")
    if capability.get("subject_id") != subject:
        raise RuntimeError("ACTIVE suite subject mismatch")
    m9_only = qualification_root is None or stop_after_m9 is True
    if m9_only:
        if capability.get("provider_enabled") is not False:
            raise RuntimeError("M1-M9 suite capability must disable the provider")
    else:
        proposal = _read_object(proposal_path) if proposal_path is not None else {}
        formal = {
            "provider_enabled": True,
            "provider_kind": "codex_cli",
            "requested_model": "gpt-6-astra",
            "reasoning_effort": "xhigh",
            "m10_samples": 1,
            "m10_sample_mode": "union",
            "provider_concurrency": 12,
            "retry_limit": 3,
            "normal_runs": 1,
        }
        # The author may pin a different formal protocol (model/provider) in ACTIVE;
        # it must be complete and explicit so the gate never widens silently.
        pinned = capability.get("formal_protocol")
        if pinned is not None:
            if not isinstance(pinned, Mapping) or set(pinned) != set(formal):
                raise RuntimeError("ACTIVE formal_protocol must pin every gate field")
            formal = dict(pinned)
        observed = {
            "provider_enabled": capability.get("provider_enabled"),
            "provider_kind": provider_kind,
            "requested_model": (proposal.get("policy") or {}).get("model"),
            "reasoning_effort": (proposal.get("policy") or {}).get("reasoning_effort"),
            "m10_samples": m10_samples,
            "m10_sample_mode": m10_sample_mode,
            "provider_concurrency": provider_concurrency,
            "retry_limit": (proposal.get("policy") or {}).get("retry_limit"),
            "normal_runs": proposal.get("normal_runs"),
        }
        if observed != formal:
            raise RuntimeError("formal suite protocol differs from the ACTIVE paper-data gate")
        if not isinstance(capability.get("paper_data"), bool):
            raise RuntimeError("ACTIVE suite paper-data classification must be boolean")
    expected = {
        "suite_ref": _path_ref(repo_root, suite_path),
        "recording_root_ref": _path_ref(repo_root, recording_root),
    }
    if qualification_root is not None:
        expected["qualification_root_ref"] = _path_ref(
            repo_root, qualification_root
        )
        if adapter_path is None or proposal_path is None:
            raise RuntimeError("M1-M9 suite run lacks frozen input paths")
        expected.update(
            {
                "adapter_ref": _path_ref(repo_root, adapter_path),
                "proposal_plan_ref": _path_ref(repo_root, proposal_path),
                "provider_kind": provider_kind,
                "output_level": output_level,
                "probe_budget": probe_budget,
                "stop_after_m9": stop_after_m9,
            }
        )
    if any(capability.get(key) != value for key, value in expected.items()):
        raise RuntimeError("ACTIVE suite input/output scope mismatch")
    admitted = capability.get("canonical_entrypoints")
    if not isinstance(admitted, list) or entrypoint not in admitted:
        raise RuntimeError("ACTIVE suite canonical entrypoint mismatch")
    return bool(capability.get("paper_data")) if not m9_only else False


def _validate_recorded_case_closure(
    *,
    suite: Mapping[str, Any],
    manifest_path: Path,
    recording_root: Path,
    recorded_rows: list[Any],
    repo_root: Path,
) -> dict[str, dict[str, Any]]:
    expected_case_ids = [str(case["case_id"]) for case in suite["cases"]]
    if [str(row.get("case_id")) for row in recorded_rows if isinstance(row, Mapping)] != expected_case_ids:
        raise ValueError("suite recording cases do not preserve manifest order")
    recorded_by_case: dict[str, dict[str, Any]] = {}
    seen_roots: set[Path] = set()
    seen_run_ids: set[str] = set()
    seen_manifests: set[Path] = set()
    for case, raw_row in zip(suite["cases"], recorded_rows, strict=True):
        if not isinstance(raw_row, dict):
            raise ValueError("suite recording case row is invalid")
        case_id = str(case["case_id"])
        expected_workflow_ref = str(case["workflow"])
        expected_root_ref = f"cases/{case_id}"
        if (
            raw_row.get("status") != "completed"
            or raw_row.get("failure") is not None
            or raw_row.get("workflow_ref") != expected_workflow_ref
            or raw_row.get("recording_root_ref") != expected_root_ref
        ):
            raise ValueError("suite recording case summary differs from the manifest")
        case_root = (recording_root / expected_root_ref).resolve(strict=True)
        if not case_root.is_relative_to(recording_root) or case_root in seen_roots:
            raise ValueError("suite recording case roots are not distinct and canonical")
        seen_roots.add(case_root)
        workflow_path = (manifest_path.parent / expected_workflow_ref).resolve(strict=True)
        workflow = load_recording_workflow(workflow_path)
        profile_path = (repo_root / workflow.profile_ref).resolve(strict=True)
        result = _read_object(case_root / "recording_workflow_result.json")
        validate_artifact("recording_workflow_result.schema.json", result)
        internal_reset = str(result.get("reset_epoch", {}).get("record_id", ""))
        if (
            result.get("status") != "completed"
            or result.get("failure") is not None
            or result.get("workflow_id") != workflow.workflow_id
            or not _matches_repo_logical_ref(
                result.get("workflow_ref"), workflow_path, repo_root
            )
            or not _matches_repo_logical_ref(
                result.get("profile_ref"), profile_path, repo_root
            )
            or result.get("reset_epoch", {}).get("status") != "completed"
            or internal_reset != str(raw_row.get("reset_epoch") or "")
        ):
            raise ValueError("suite recording workflow closure differs from its summary")
        actor_bundles = result.get("actor_bundles")
        expected_actors = sorted(actor.actor_id for actor in workflow.actors)
        if (
            not isinstance(actor_bundles, list)
            or sorted(str(row.get("actor_id")) for row in actor_bundles) != expected_actors
        ):
            raise ValueError("suite recording actor bundles differ from the workflow")
        for bundle in actor_bundles:
            run_id = str(bundle["run_id"])
            manifest_ref = Path(str(bundle["manifest_ref"]))
            if manifest_ref.is_absolute() or ".." in manifest_ref.parts:
                raise ValueError("suite recording actor manifest ref is invalid")
            manifest = (case_root / manifest_ref).resolve(strict=True)
            if (
                not manifest.is_relative_to(case_root)
                or run_id in seen_run_ids
                or manifest in seen_manifests
            ):
                raise ValueError("suite recording actor bundles are not isolated")
            seen_run_ids.add(run_id)
            seen_manifests.add(manifest)
            bundle_manifest = _read_object(manifest)
            validate_artifact("session_bundle_manifest.schema.json", bundle_manifest)
            session = bundle_manifest["session"]
            if (
                bundle_manifest.get("metadata", {}).get("run_id") != run_id
                or session.get("actor_id") != bundle["actor_id"]
                or session.get("workflow_id") != workflow.workflow_id
                or not _matches_repo_logical_ref(
                    session.get("workflow_ref"), workflow_path, repo_root
                )
                or not _matches_repo_logical_ref(
                    session.get("profile_ref"), profile_path, repo_root
                )
                or session.get("reset_epoch") != internal_reset
            ):
                raise ValueError("suite recording actor bundle closure is invalid")
        recorded_by_case[case_id] = raw_row
    return recorded_by_case


def _matches_repo_logical_ref(value: Any, expected: Path, repo_root: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        expected_parts = expected.resolve(strict=True).relative_to(
            repo_root.resolve(strict=True)
        ).parts
    except (OSError, ValueError):
        return False
    recorded_parts = Path(value).parts
    return len(recorded_parts) >= len(expected_parts) and tuple(
        recorded_parts[-len(expected_parts) :]
    ) == expected_parts


def _path_ref(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _read_object(path: Path) -> dict[str, Any]:
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


__all__ = [
    "aggregate_suite_case_summaries",
    "inspect_scientific_metadata_isolation",
    "load_recording_suite",
    "record_current_suite",
    "run_current_suite",
]
