"""The single fresh-output UISemTest current-v2 M1–M14 orchestrator."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from argparse import Namespace
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .artifact_relocation import attested_sha256, attested_size
from types import MappingProxyType
from typing import Any, Callable, Mapping

from common.contracts import validate_artifact
from common.request_material_shape import load_request_material_shapes
from stage0_launch.profile import actor_auth
from stage1_record.workflow import load_recording_workflow
from stage2_5_probe.assemble import recover_probe_results_with_scheduled_execution
from stage2_recover.loader import LoadedBundle
from stage6_ground.ui_semantic_replay import SessionBundleReplayAdapter

from .auth_session_stratum import (
    calibrate_auth_session_tests,
    compile_auth_session_tests,
    evaluate_auth_session_stratum,
)
from .contracts import (
    FinalSuiteIndex,
    ObservedApiCatalog,
    ObservedValueFlowSet,
    ProposalEvidenceView,
    ProducerApplicability,
    RecordingBundle,
    UiApiTrace,
    V2RuntimeReadyMaterialSet,
)
from .current_adapter import (
    adapter_materialization_view,
    load_current_adapter,
    resolve_current_path_binding_targets,
    resolve_recording_material_aliases,
    resolve_current_request_bindings,
    resolve_current_request_material_bindings,
)
from .current_calibration import (
    build_final_calibrated_suite,
    validate_current_calibration_report,
    validate_final_calibrated_suite,
    validate_final_calibrated_view,
)
from .current_candidate_failure import CandidateLocalFailure
from .current_freeze import CurrentV2Freeze, write_current_v2_input_freeze
from .current_protocols import (
    build_current_protocol_tests,
    candidate_local_protocol_result,
    diagnose_current_protocol_failure,
    derive_current_protocol,
    execute_current_protocol,
    persist_current_protocol_execution,
    run_current_protocol_calibration,
)
from .current_relation import build_current_relation_closure
from .current_route_s import canonical_json_bytes
from .current_provider import (
    SealedResponseReplayRuntimeConfig,
    bind_evidence_card_proposal_calls,
    build_center_completion_provider_factory,
    build_current_provider_factory,
    load_current_provider_plan,
)
from .current_runtime_factory import build_current_runtime_factory
from .m11_bridge import bridge_v2_proposal_run_to_m11
from .m11b_materializer import (
    materialize_current_route_s_inputs,
    validate_and_persist_current_route_s_material,
)
from .output_publisher import OUTPUT_LEVELS, publish_current_output
from .proposal_run import (
    ProposalRunPlan,
    V2ProposalRunLineage,
    build_proposal_run_plan,
    execute_v2_proposal_run,
    largest_proposal_call_prompt,
    load_v2_proposal_run_lineage,
    union_v2_proposal_rounds,
)
from .v2_proposer import canonical_relation_core_identity
from .route_s_capture_redaction import (
    CaptureRedactionError,
    SensitiveMaterialUnavailable,
)
from .relation_phase_b import (
    canonical_sha256,
    summarize_generation,
    validate_certified_relation_tests,
)
from .v2_proposer import load_hardened_v2_input


OfflineBuilder = Callable[[Namespace], dict[str, Any]]


@dataclass(frozen=True)
class _FrozenM10Provider:
    kind: str = "frozen_m10"
    max_rendered_chars: int = 0


@dataclass(frozen=True)
class _FrozenM10Schedule:
    plan_id: str
    frozen_at: str
    normal_runs: int
    provider: _FrozenM10Provider


@dataclass(frozen=True)
class _FrozenM10Source:
    root: Path
    completion_sha256: str
    proposal_path: Path
    schedule: _FrozenM10Schedule
    lineage: V2ProposalRunLineage


@dataclass(frozen=True)
class _FrozenM10Activity:
    input_size_chars: int
    logical_call_count: int = 0
    transport_attempt_count: int = 0
    external_network_calls: int = 0
    external_provider_llm_calls: int = 0
    sealed_response_replay_count: int = 0
    response_delivery_kind: str = "frozen_m10"


@dataclass(frozen=True)
class _FrozenRecordingActor:
    actor_id: str
    run_id: str
    path: str
    manifest_sha256: str


METHOD_FILES = (
    "src/common/contracts.py",
    "src/common/oas_discovery.py",
    "src/stage0_launch/stage0.py",
    "src/stage1_record/workflow.py",
    "src/stage1_record/bundle_writer.py",
    "src/stage2_recover/loader.py",
    "src/stage2_recover/assemble.py",
    "src/stage2_5_probe/offline.py",
    "src/stage2_5_probe/assemble.py",
    "src/stage2_5_probe/discovery_planner.py",
    "src/stage2_5_probe/scheduled.py",
    "src/stage3_gate/assemble.py",
    "src/stage4_deps/valueflow.py",
    "src/stage4_deps/assemble.py",
    "src/stage5_synth/__init__.py",
    "src/ui_semantics/cli.py",
    "src/ui_semantics/contracts.py",
    "src/ui_semantics/trace_builder.py",
    "src/ui_semantics/candidate_normalization.py",
    "src/ui_semantics/replay_policy.py",
    "src/ui_semantics/current_route_s/__init__.py",
    "src/ui_semantics/current_route_s/core.py",
    "src/ui_semantics/current_route_s/runtime.py",
    "src/ui_semantics/current_settle.py",
    "src/ui_semantics/current_route_s/validation.py",
    "src/ui_semantics/current_protocols/__init__.py",
    "src/ui_semantics/current_protocols/actor_matrix.py",
    "src/ui_semantics/current_protocols/metamorphic_query.py",
    "src/ui_semantics/current_protocols/repeated_execution.py",
    "src/ui_semantics/current_protocols/negative_no_effect.py",
    "src/ui_semantics/current_protocols/single_state.py",
    "src/ui_semantics/current_protocols/multi_resource.py",
    "src/ui_semantics/current_protocols/temporal.py",
    "src/ui_semantics/current_protocols/v4.py",
    "src/ui_semantics/dsl.py",
    "src/ui_semantics/current_candidate_failure.py",
    "src/ui_semantics/current_freeze.py",
    "src/ui_semantics/current_adapter.py",
    "src/ui_semantics/current_provider.py",
    "src/ui_semantics/current_providers.py",
    "src/ui_semantics/current_runtime_factory.py",
    "src/ui_semantics/current_suite.py",
    "src/ui_semantics/current_http_runtime.py",
    "src/ui_semantics/offline_pipeline.py",
    "src/ui_semantics/offline_producer_partition.py",
    "src/ui_semantics/preproposal.py",
    "src/ui_semantics/v2_template.py",
    "src/ui_semantics/v2_proposer.py",
    "src/ui_semantics/candidate_lineage.py",
    "src/ui_semantics/proposal_run.py",
    "src/ui_semantics/m11_bridge.py",
    "src/ui_semantics/m11b_materializer.py",
    "src/ui_semantics/route_s_capture_redaction.py",
    "src/ui_semantics/current_relation.py",
    "src/ui_semantics/relation_phase_b.py",
    "src/ui_semantics/current_calibration.py",
    "src/ui_semantics/auth_session_stratum.py",
    "src/ui_semantics/output_publisher.py",
    "src/stage6_ground/resource_rebinding.py",
    "src/stage6_ground/discovery.py",
    "src/stage6_ground/http_client.py",
    "src/stage6_ground/relation_test_execution.py",
    "src/ui_semantics/current_orchestrator.py",
    "src/ui_semantics/method_registry.py",
)

PIPELINE_SCHEMA_FILES = (
    "current_route_s_execution_material_v1.schema.json",
    "current_route_s_evaluation_v1.schema.json",
    "current_protocol_result_v1.schema.json",
    "app_profile.schema.json",
    "metadata_envelope.schema.json",
    "test_suite.schema.json",
    "certified_relation_tests.schema.json",
    "current_calibration_report_v1.schema.json",
    "final_calibrated_view_v1.schema.json",
    "final_calibrated_suite_v1.schema.json",
    "current_subject_adapter_v1.schema.json",
)


def run_current_v2_pipeline(
    args: Namespace,
    *,
    repo_root: Path,
    offline_builder: OfflineBuilder,
) -> dict[str, Any]:
    """Execute the current pipeline with optional complete M10 sampling rounds."""

    if bool(getattr(args, "stop_after_m9", False)):
        return _run_current_v2_pipeline_once(
            args, repo_root=repo_root, offline_builder=offline_builder
        )
    sample_count = getattr(args, "m10_samples", 1)
    sample_mode = str(getattr(args, "m10_sample_mode", "independent"))
    if (
        not isinstance(sample_count, int)
        or isinstance(sample_count, bool)
        or sample_count < 1
    ):
        raise ValueError("M10 sample count must be a positive integer")
    if sample_mode not in {"independent", "union"}:
        raise ValueError("M10 sample mode must be independent or union")
    if sample_count == 1 and (
        sample_mode == "independent"
        or getattr(args, "frozen_m10_source", None) is not None
        or (
            bool(getattr(args, "resume_incomplete_m10", False))
            and not (args.output_root / "attempts").is_dir()
        )
        or bool(getattr(args, "stop_after_m10", False))
    ):
        return _run_current_v2_pipeline_once(
            args, repo_root=repo_root, offline_builder=offline_builder
        )
    if any(
        (
            getattr(args, "frozen_m10_source", None) is not None,
            bool(getattr(args, "stop_after_m10", False)),
        )
    ):
        raise ValueError(
            "multi-round M10 sampling requires a full provider run"
        )
    return _run_multi_round_current_pipeline(
        args,
        repo_root=repo_root,
        offline_builder=offline_builder,
        sample_count=sample_count,
        sample_mode=sample_mode,
    )


def _reuse_completed_current_output(
    args: Namespace, *, run_root: Path,
) -> dict[str, Any]:
    """Reuse a completed case or round only after closing its existing inputs."""

    report = _read_object(run_root / "run_manifest.json")
    if report.get("terminal_status") != "complete":
        raise ValueError("reused current output is not complete")
    if report.get("schema_version") == "uisemtest-current-m10-sampling-report-v1":
        if (
            report.get("mode") != args.m10_sample_mode
            or report.get("requested_complete_rounds") != args.m10_samples
            or report.get("completed_rounds") != args.m10_samples
        ):
            raise ValueError("completed sampling configuration differs from recovery")
        refs = (
            ["union"] if args.m10_sample_mode == "union"
            else [row["output_ref"] for row in report["rounds"]]
        )
        for ref in refs:
            child = (run_root / ref).resolve(strict=True)
            if not child.is_relative_to(run_root.resolve()):
                raise ValueError("completed sampling output escapes its root")
            _reuse_completed_current_output(args, run_root=child)
        return report
    adapter = load_current_adapter(args.profile, args.adapter)
    source = _load_frozen_m10_source(
        run_root,
        expected_completion_sha256=_sha256_file(run_root / "M10/proposal_run_completion.json"),
        profile_path=args.profile,
        adapter_path=args.adapter,
        subject_id=adapter.adapter.subject_id,
    )
    if bool(getattr(args, "stop_after_m10", False)) != (
        report.get("execution_boundary") == "completed_m10_before_m11a"
    ):
        raise ValueError("completed run terminal boundary differs from recovery")
    frozen_policy = _read_object(source.proposal_path)
    requested_policy = _read_object(args.proposal_plan)
    for value in (frozen_policy, requested_policy):
        value["provider"].pop("timeout_seconds", None)
    if frozen_policy != requested_policy:
        raise ValueError("completed run provider configuration differs from recovery")
    recording = RecordingBundle.model_validate_json(
        (run_root / "M01_09/recording_bundle.json").read_bytes(), strict=True,
    )
    requested_summary, _ = _recording_input_summary(
        recording_root=args.recording_root, recording=recording,
    )
    if requested_summary != _read_object(run_root / "M01_09/recording_input_summary.json"):
        raise ValueError("completed run recording differs from recovery")
    if recording.source_sha256.get("recording_workflow_result.json") != _sha256_file(
        args.recording_root / "recording_workflow_result.json"
    ):
        raise ValueError("completed run workflow result differs from recovery")
    return report


def _run_multi_round_current_pipeline(
    args: Namespace,
    *,
    repo_root: Path,
    offline_builder: OfflineBuilder,
    sample_count: int,
    sample_mode: str,
) -> dict[str, Any]:
    target = args.output_root.resolve()
    resume = bool(getattr(args, "resume_incomplete_m10", False))
    if target.exists() and not resume:
        raise ValueError("run output root must be fresh and must not already exist")
    if resume and not (target / "attempts").is_dir():
        raise ValueError("sampling recovery requires its existing attempts directory")
    root = repo_root.resolve()
    profile_path = args.profile.resolve(strict=True)
    adapter_path = args.adapter.resolve(strict=True)
    adapter_bundle = load_current_adapter(profile_path, adapter_path)
    provider_bundle = load_current_provider_plan(
        args.proposal_plan.resolve(strict=True),
        requested_provider=args.provider,
    )
    provider_kind = provider_bundle.provider.kind
    live_requested = (
        provider_kind in {"openai_compatible", "codex_cli"}
        or adapter_bundle.adapter.runtime.kind != "deterministic_fixture"
    )
    if not bool(getattr(args, "_suite_execution_authorized", False)):
        _require_execution_lock(
            root,
            live_requested=live_requested,
            subject_id=adapter_bundle.adapter.subject_id,
            provider_kind=provider_kind,
            runtime_kind=adapter_bundle.adapter.runtime.kind,
            profile_path=profile_path,
            adapter_path=adapter_path,
            output_root=target,
        )
    prior_report = (
        _read_object(target / "run_manifest.json")
        if resume and (target / "run_manifest.json").is_file()
        else {}
    )
    if prior_report and (
        prior_report.get("schema_version") != "uisemtest-current-m10-sampling-report-v1"
        or prior_report.get("mode") != sample_mode
        or prior_report.get("requested_complete_rounds") != sample_count
    ):
        raise ValueError("sampling recovery differs from the frozen round configuration")
    if prior_report.get("terminal_status") == "complete":
        if sample_mode == "union":
            _reuse_completed_current_output(args, run_root=target / "union")
        else:
            for row in prior_report["rounds"]:
                _reuse_completed_current_output(args, run_root=target / row["output_ref"])
        return {**prior_report, "output_root": str(target), "run_manifest": str(target / "run_manifest.json")}
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.multi-round-", dir=target.parent)
    ).resolve()
    if resume:
        _reject_symlinks(target)
        shutil.copytree(target, staging, dirs_exist_ok=True)
        # The original checkpoint remains at target until atomic publication.
        # Replace only its copied outer report with this invocation's report.
        (staging / "run_manifest.json").unlink(missing_ok=True)
    attempts_root = staging / "attempts"
    attempts_root.mkdir(exist_ok=True)
    existing_attempts = sorted(path.name for path in attempts_root.iterdir())
    if existing_attempts != [f"attempt-{index:04d}" for index in range(1, len(existing_attempts) + 1)]:
        raise ValueError("sampling recovery attempts must be a contiguous recorded prefix")
    prior_attempts = {row["attempt_index"]: row for row in prior_report.get("attempts", [])}
    attempt_records: list[dict[str, Any]] = []
    successful: list[tuple[Path, dict[str, Any]]] = []
    max_resume_invocations = provider_bundle.proposal_policy.retry_limit + 2
    m10_only = bool(getattr(args, "_suite_m10_only", False))
    if m10_only and (sample_mode != "union" or args.probe_budget != 0):
        raise ValueError("parallel suite M10 requires union sampling without active probes")

    try:
        for attempt_index in range(1, sample_count + 3):
            if len(successful) == sample_count:
                break
            attempt_root = attempts_root / f"attempt-{attempt_index:04d}"
            child_args = Namespace(**vars(args))
            child_args.output_root = attempt_root
            child_args.m10_samples = 1
            child_args.m10_sample_mode = "independent"
            child_args.output_level = "forensic"
            child_args.stop_after_m10 = True
            child_args.resume_incomplete_m10 = resume and attempt_root.exists()
            child_args._multi_round_execution_authorized = True
            prior_attempt = prior_attempts.get(attempt_index, {})
            if prior_attempt.get("status") == "invalid":
                attempt_records.append(prior_attempt)
                continue
            failure_path = attempt_root / "M10/proposal_run_failure.json"
            prior_failure = _read_object(failure_path) if failure_path.is_file() else {}
            invocation_count = (
                int(prior_failure.get("recovery_logical_invocation_count", 0)) + 1
                if prior_failure else 0
            )
            report: dict[str, Any] | None = None
            error_text: str | None = None
            error_traceback: str | None = None
            saved_manifest = attempt_root / "run_manifest.json"
            saved_report = _read_object(saved_manifest) if saved_manifest.is_file() else {}
            if saved_report.get("terminal_status") == "complete":
                report = _reuse_completed_current_output(child_args, run_root=attempt_root)
                recovery_path = attempt_root / "M10/proposal_run_recovery.json"
                recovery_report = _read_object(recovery_path) if recovery_path.is_file() else {}
                invocation_count = max(
                    int(prior_attempt.get("invocation_count", 0)),
                    int(recovery_report.get("recovery_logical_invocation_count", 0)) + 1,
                )
            elif saved_manifest.is_file() and {path.name for path in attempt_root.iterdir()} == {"M10", "run_manifest.json"}:
                saved_manifest.unlink()
            while report is None and invocation_count < max_resume_invocations:
                invocation_count += 1
                try:
                    report = _run_current_v2_pipeline_once(
                        child_args,
                        repo_root=repo_root,
                        offline_builder=offline_builder,
                    )
                    break
                except Exception as error:
                    error_text = f"{type(error).__name__}: {error}"
                    error_traceback = "".join(traceback.format_exception(error))
                    failure_path = attempt_root / "M10/proposal_run_failure.json"
                    if (
                        not failure_path.is_file()
                        or not _m10_failure_has_retryable_transport_work(failure_path)
                    ):
                        break
                    child_args.resume_incomplete_m10 = True
            completed = report is not None and report.get("terminal_status") == "complete"
            telemetry_path = (
                attempt_root / "M10/proposal_run_completion.json"
                if completed
                else attempt_root / "M10/proposal_run_failure.json"
            )
            telemetry = _read_object(telemetry_path) if telemetry_path.is_file() else {}
            record = {
                "attempt_index": attempt_index,
                "status": "complete" if completed else "invalid",
                "invocation_count": invocation_count,
                "output_ref": str(attempt_root.relative_to(staging)),
                "error": None if completed else error_text,
                "error_traceback": None if completed else error_traceback,
                "provider_concurrency_planned": int(
                    telemetry.get("provider_concurrency_planned", args.provider_concurrency)
                ),
                "provider_concurrency_actual_max": int(
                    telemetry.get("provider_concurrency_actual_max", 0)
                ),
            }
            if completed:
                record["successful_round_index"] = len(successful) + 1
                record["m10_completion_sha256"] = _sha256_file(
                    attempt_root / "M10/proposal_run_completion.json"
                )
                successful.append((attempt_root, report))
            attempt_records.append(record)

        if len(successful) < sample_count:
            summary = {
                "schema_version": "uisemtest-current-m10-sampling-report-v1",
                "status": "incomplete",
                "completion_reason": "m10_complete_round_shortfall",
                "terminal_status": "incomplete",
                "mode": sample_mode,
                "requested_complete_rounds": sample_count,
                "completed_rounds": len(successful),
                "maximum_attempted_rounds": sample_count + 2,
                "attempted_rounds": len(attempt_records),
                "provider_concurrency_planned": int(args.provider_concurrency),
                "provider_concurrency_actual_max": max(
                    (
                        row["provider_concurrency_actual_max"]
                        for row in attempt_records
                    ),
                    default=0,
                ),
                "attempts": attempt_records,
            }
            _write_json(staging / "run_manifest.json", summary)
            if resume:
                _replace_recovered_m10(target, staging)
            else:
                os.replace(staging, target)
            return {
                **summary,
                "output_root": str(target),
                "run_manifest": str(target / "run_manifest.json"),
            }

        downstream_report: dict[str, Any] | None = None
        independent_reports: list[tuple[Path, dict[str, Any]]] = []
        if sample_mode == "union":
            union_args = Namespace(**vars(args))
            union_args.output_root = staging / "union"
            union_args.m10_samples = 1
            union_args.m10_sample_mode = "independent"
            union_args.resume_incomplete_m10 = (union_args.output_root / "M10").is_dir()
            union_args.stop_after_m10 = m10_only
            if m10_only:
                union_args.output_level = "forensic"
            union_args._m10_union_sources = tuple(path for path, _ in successful)
            union_args._multi_round_execution_authorized = True
            union_error: Exception | None = None
            union_manifest = union_args.output_root / "run_manifest.json"
            union_saved = _read_object(union_manifest) if union_manifest.is_file() else {}
            if union_saved.get("terminal_status") == "complete":
                frozen_union = union_saved.get("execution_boundary") == "completed_m10_before_m11a"
                if frozen_union and not m10_only:
                    source_args = Namespace(**vars(union_args))
                    source_args.stop_after_m10 = True
                    _reuse_completed_current_output(source_args, run_root=union_args.output_root)
                    # The published frozen source survives until this case is
                    # replaced; keep its stable path in downstream provenance.
                    union_args.frozen_m10_source = target / "union"
                    union_args.frozen_m10_completion_sha256 = _sha256_file(
                        union_args.output_root / "M10/proposal_run_completion.json"
                    )
                    union_args.output_root = staging / ".union-downstream"
                    union_args._m10_union_sources = ()
                    union_args.resume_incomplete_m10 = False
                else:
                    downstream_report = _reuse_completed_current_output(union_args, run_root=union_args.output_root)
            elif union_manifest.is_file() and {path.name for path in union_args.output_root.iterdir()} == {"M10", "run_manifest.json"}:
                union_manifest.unlink()
            for _ in range(max_resume_invocations):
                if downstream_report is not None:
                    break
                try:
                    downstream_report = _run_current_v2_pipeline_once(
                        union_args,
                        repo_root=repo_root,
                        offline_builder=offline_builder,
                    )
                    union_error = None
                    break
                except Exception as error:
                    union_error = error
                    failure_path = (
                        union_args.output_root
                        / "M10/center_completion/proposal_run_failure.json"
                    )
                    if (
                        not failure_path.is_file()
                        or not _m10_failure_has_retryable_transport_work(
                            failure_path
                        )
                    ):
                        break
                    union_args.resume_incomplete_m10 = True
            if union_error is not None:
                raise union_error
            if union_args.output_root != staging / "union":
                _replace_recovered_m10(staging / "union", union_args.output_root)
        else:
            rounds_root = staging / "rounds"
            rounds_root.mkdir(exist_ok=True)
            for success_index, (source_path, _source_report) in enumerate(
                successful, start=1
            ):
                completion_path = source_path / "M10/proposal_run_completion.json"
                round_args = Namespace(**vars(args))
                round_args.output_root = rounds_root / f"round-{success_index:04d}"
                round_args.m10_samples = 1
                round_args.m10_sample_mode = "independent"
                round_args.resume_incomplete_m10 = False
                round_args.stop_after_m10 = False
                round_args.frozen_m10_source = source_path
                round_args.frozen_m10_completion_sha256 = _sha256_file(
                    completion_path
                )
                round_args._multi_round_execution_authorized = True
                report = (
                    _reuse_completed_current_output(args, run_root=round_args.output_root)
                    if (round_args.output_root / "run_manifest.json").is_file()
                    else _run_current_v2_pipeline_once(
                        round_args, repo_root=repo_root, offline_builder=offline_builder,
                    )
                )
                independent_reports.append((round_args.output_root, report))

        completed_rounds = []
        for success_index, (source_path, source_report) in enumerate(
            successful, start=1
        ):
            output_path, report = (
                independent_reports[success_index - 1]
                if sample_mode == "independent"
                else (source_path, source_report)
            )
            completion = _read_object(
                source_path / "M10/proposal_run_completion.json"
            )
            completed_rounds.append(
                {
                    "round_index": success_index,
                    "m10_source_ref": str(source_path.relative_to(staging)),
                    "output_ref": str(output_path.relative_to(staging)),
                    "run_manifest_ref": str(
                        (output_path / "run_manifest.json").relative_to(staging)
                    ),
                    "m10_completion_sha256": _sha256_file(
                        source_path / "M10/proposal_run_completion.json"
                    ),
                    "candidate_count": (
                        int(report.get("candidate_count", 0))
                        if sample_mode == "independent"
                        else int(completion["valid_admitted_count"])
                    ),
                    "provider_concurrency_planned": completion[
                        "provider_concurrency_planned"
                    ],
                    "provider_concurrency_actual_max": completion[
                        "provider_concurrency_actual_max"
                    ],
                }
            )
        summary = {
            "schema_version": "uisemtest-current-m10-sampling-report-v1",
            "status": downstream_report.get("status", "pass")
            if downstream_report is not None
            else "pass",
            "completion_reason": (
                "m10_round_union_complete_before_m11a" if m10_only else (
                    "m10_round_union_calibrated"
                    if sample_mode == "union"
                    else "independent_m10_rounds_calibrated"
                )
            ),
            "terminal_status": "incomplete" if m10_only else "complete",
            "mode": sample_mode,
            "requested_complete_rounds": sample_count,
            "completed_rounds": sample_count,
            "maximum_attempted_rounds": sample_count + 2,
            "attempted_rounds": len(attempt_records),
            "provider_concurrency_planned": int(args.provider_concurrency),
            "provider_concurrency_actual_max": max(
                row["provider_concurrency_actual_max"] for row in completed_rounds
            ),
            "rounds": completed_rounds,
            "attempts": attempt_records,
            "union_result_ref": "union/run_manifest.json"
            if downstream_report is not None
            else None,
        }
        _write_json(staging / "run_manifest.json", summary)
        if resume:
            _replace_recovered_m10(target, staging)
        else:
            os.replace(staging, target)
        return {
            **summary,
            "output_root": str(target),
            "run_manifest": str(target / "run_manifest.json"),
        }
    except Exception as error:
        if staging.exists():
            if (successful or any(attempts_root.glob("*/M10/proposal_run_failure.json"))) and (resume or not target.exists()):
                _write_json(
                    staging / "run_manifest.json",
                    {
                        "schema_version": "uisemtest-current-m10-sampling-report-v1",
                        "status": "incomplete",
                        "completion_reason": "downstream_execution_failed",
                        "terminal_status": "incomplete",
                        "mode": sample_mode,
                        "requested_complete_rounds": sample_count,
                        "completed_m10_rounds": len(successful),
                        "attempted_rounds": len(attempt_records),
                        "provider_concurrency_planned": int(
                            args.provider_concurrency
                        ),
                        "provider_concurrency_actual_max": max(
                            (
                                row["provider_concurrency_actual_max"]
                                for row in attempt_records
                            ),
                            default=0,
                        ),
                        "attempts": attempt_records,
                        "error": f"{type(error).__name__}: {error}",
                        "error_traceback": "".join(
                            traceback.format_exception(error)
                        ),
                    },
                )
                if resume:
                    _replace_recovered_m10(target, staging)
                else:
                    os.replace(staging, target)
            else:
                shutil.rmtree(staging)
        raise


def _m10_failure_has_retryable_transport_work(failure_path: Path) -> bool:
    failure = _read_object(failure_path)
    call_failures = failure.get("call_failures")
    if not isinstance(call_failures, Mapping):
        return False
    for row in call_failures.values():
        if not isinstance(row, Mapping):
            continue
        category = row.get("category")
        if isinstance(category, str) and category.endswith(
            ("_transport_failed", "_not_dispatched")
        ):
            return True
    return False


def _run_current_v2_pipeline_once(
    args: Namespace,
    *,
    repo_root: Path,
    offline_builder: OfflineBuilder,
) -> dict[str, Any]:
    """Execute one fresh-output current M1–M14 run through injected seams."""

    root = repo_root.resolve()
    _require_repo_runtime(root)
    probe_budget = getattr(args, "probe_budget", 32)
    if probe_budget < 0:
        raise ValueError("active probe budget must be nonnegative")
    provider_concurrency = getattr(args, "provider_concurrency", 12)
    if (
        not isinstance(provider_concurrency, int)
        or isinstance(provider_concurrency, bool)
        or provider_concurrency < 1
    ):
        raise ValueError("provider concurrency must be a positive integer")
    output_level = str(getattr(args, "output_level", "paper"))
    if output_level not in OUTPUT_LEVELS:
        raise ValueError(f"unknown current output level: {output_level!r}")
    active_execution_path = root / "docs/ACTIVE-EXECUTION.json"
    active_execution_before = active_execution_path.read_bytes()
    profile_path = args.profile.resolve(strict=True)
    adapter_path = args.adapter.resolve(strict=True)
    adapter_bundle = load_current_adapter(profile_path, adapter_path)
    frozen_source_arg = getattr(args, "frozen_m10_source", None)
    m10_union_sources = tuple(
        Path(path).resolve(strict=True)
        for path in getattr(args, "_m10_union_sources", ())
    )
    if frozen_source_arg is not None and m10_union_sources:
        raise ValueError("frozen M10 continuation and round union are exclusive")
    frozen_source = (
        _load_frozen_m10_source(
            Path(frozen_source_arg),
            expected_completion_sha256=str(
                getattr(args, "frozen_m10_completion_sha256", "")
            ),
            profile_path=profile_path,
            adapter_path=adapter_path,
            subject_id=adapter_bundle.adapter.subject_id,
        )
        if frozen_source_arg is not None
        else None
    )
    if frozen_source is None:
        recording_root = args.recording_root.resolve(strict=True)
        proposal_path = args.proposal_plan.resolve(strict=True)
        provider_bundle = load_current_provider_plan(
            proposal_path,
            requested_provider=args.provider,
        )
        schedule = provider_bundle
        provider_kind = schedule.provider.kind
    else:
        recording_root = frozen_source.root
        proposal_path = frozen_source.proposal_path
        provider_bundle = None
        schedule = frozen_source.schedule
        provider_kind = "sealed_response_replay"
    adapter = _read_object(adapter_path)
    live_requested = (
        provider_kind in {"openai_compatible", "codex_cli"}
        or adapter_bundle.adapter.runtime.kind != "deterministic_fixture"
    )
    target = args.output_root.resolve()
    resume_incomplete_m10 = bool(
        getattr(args, "resume_incomplete_m10", False)
    )
    stop_after_m10 = bool(getattr(args, "stop_after_m10", False))
    stop_after_m9 = bool(getattr(args, "stop_after_m9", False))
    resume_completed_m10 = resume_incomplete_m10 and (target / "M10/proposal_run_completion.json").is_file()
    if stop_after_m9 and (frozen_source is not None or stop_after_m10):
        raise ValueError("M9 stop boundary requires one fresh pre-M10 run")
    if stop_after_m10 and (frozen_source is not None or output_level != "forensic"):
        raise ValueError(
            "M10 stop boundary requires a fresh provider run and forensic output"
        )
    if not any(
        (
            bool(getattr(args, "_suite_execution_authorized", False)),
            bool(getattr(args, "_multi_round_execution_authorized", False)),
        )
    ):
        _require_execution_lock(
            root,
            live_requested=live_requested,
            subject_id=adapter_bundle.adapter.subject_id,
            provider_kind=provider_kind,
            runtime_kind=adapter_bundle.adapter.runtime.kind,
            profile_path=profile_path,
            adapter_path=adapter_path,
            output_root=target,
        )
    if resume_incomplete_m10:
        _validate_incomplete_m10_target(target)
    elif target.exists():
        raise ValueError("run output root must be fresh and must not already exist")
    extra_input_paths = (
        [
            *provider_bundle.fixture_response_paths,
            *provider_bundle.replay_source_paths,
            *(
                [adapter_bundle.fixture_tape_path]
                if adapter_bundle.fixture_tape_path is not None
                else []
            ),
        ]
        if provider_bundle is not None
        else [
            *(
                [adapter_bundle.fixture_tape_path]
                if adapter_bundle.fixture_tape_path is not None
                else []
            )
        ]
    )
    for source in (
        profile_path,
        adapter_path,
        proposal_path,
        recording_root,
        *extra_input_paths,
    ):
        if (
            target == source
            or source in target.parents
            or target in source.parents
        ):
            raise ValueError("run output root cannot contain or overwrite an input")
    target.parent.mkdir(parents=True, exist_ok=True)
    runtime_factory = None
    runtime_started = False
    active_trace_sha256: str | None = None
    active_request_bindings: dict[str, dict[str, Any]] | None = None
    publication_started = False
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent)
    ).resolve()
    stages: list[dict[str, Any]] = []
    try:
        input_snapshots = (
            _restore_frozen_m10_source(
                frozen_source,
                staging=staging,
                profile_path=profile_path,
                adapter_path=adapter_path,
                fixture_tape_path=adapter_bundle.fixture_tape_path,
            )
            if frozen_source is not None
            else _snapshot_current_inputs(
                staging,
                profile_path=profile_path,
                adapter_path=adapter_path,
                proposal_path=proposal_path,
                fixture_response_paths=provider_bundle.fixture_response_paths,
                replay_source_paths=provider_bundle.replay_source_paths,
                replay_source_root_path=(
                    provider_bundle.provider.source_run_root_path
                    if isinstance(
                        provider_bundle.provider, SealedResponseReplayRuntimeConfig
                    )
                    else None
                ),
                fixture_tape_path=adapter_bundle.fixture_tape_path,
            )
        )
        m1_9_root = staging / "M01_09"

        def active_probe_runtime_setup(trace: UiApiTrace):
            nonlocal runtime_factory, runtime_started
            nonlocal active_trace_sha256, active_request_bindings
            actor_by_run_id: dict[str, str] = {}
            for actor in trace.trace.get("actors", []):
                actor_id = str(actor["actor_id"])
                run_id = str(actor["session_bundle_ref"]["run_id"])
                if run_id in actor_by_run_id:
                    raise ValueError("typed trace contains duplicate actor run IDs")
                actor_by_run_id[run_id] = actor_id
            active_request_bindings = resolve_current_request_bindings(
                adapter_bundle,
                trace=trace,
                recording_root=recording_root,
            )
            runtime_factory = build_current_runtime_factory(
                adapter_bundle,
                run_id=schedule.plan_id,
                request_bindings=active_request_bindings,
                trace=_runtime_trace_with_resolved_recording_paths(
                    trace, recording_root
                ),
                recording_material_aliases=resolve_recording_material_aliases(
                    recording_root
                ),
            )
            runtime_factory.preflight()
            runtime_started = True
            runtime_factory.start(run_root=staging)
            active_trace_sha256 = trace.canonical_sha256()

            def run_active_probes(initial, bundles, _run_id):
                initial_path = m1_9_root / ".stage2-5-active-initial.json"
                _write_json(initial_path, initial)
                try:
                    probes, _runners = recover_probe_results_with_scheduled_execution(
                        initial_path,
                        [bundle.bundle_dir for bundle in bundles],
                        profile_path,
                        actor_by_run_id=actor_by_run_id,
                        probe_budget=probe_budget,
                        initial_oas_source_ref="logical:current:M3:initial-structure",
                    )
                    return probes
                finally:
                    initial_path.unlink(missing_ok=True)

            return run_active_probes

        offline_report = (
            {
                "status": "pass",
                "counts": dict(frozen_source.lineage.frozen_input.manifest.counts),
            }
            if frozen_source is not None
            else offline_builder(
                Namespace(
                    profile=profile_path,
                    recording_root=recording_root,
                    output_root=m1_9_root,
                    channels="semantic,ui-diff",
                    run_id=provider_bundle.evidence_run_id,
                    transfer_selection=None,
                    transfer_population=None,
                    evidence_organization=str(
                        getattr(args, "evidence_organization", "association")
                    ),
                    active_probe_runtime_setup=(
                        active_probe_runtime_setup
                        if (
                            adapter_bundle.adapter.runtime.kind == "local_http"
                            and probe_budget > 0
                        )
                        else None
                    ),
                )
            )
        )
        if offline_report.get("status") != "pass":
            raise ValueError("current M1-M9 offline build failed")
        producer_partition = _read_object(
            m1_9_root / "producer_partition_summary.json"
        )
        business_refs = producer_partition.get("business_producer_refs")
        business_available_refs = producer_partition.get(
            "business_available_producer_refs"
        )
        business_unsupported_refs = producer_partition.get(
            "business_unsupported_producer_refs"
        )
        for name, refs in (
            ("business", business_refs),
            ("available business", business_available_refs),
            ("unsupported business", business_unsupported_refs),
        ):
            if not isinstance(refs, list) or any(
                not isinstance(item, str) for item in refs
            ):
                raise ValueError(f"current producer partition lacks {name} refs")
        proposal_view = ProposalEvidenceView.model_validate_json(
            (m1_9_root / "proposal_evidence_view.json").read_bytes(), strict=True
        )
        if provider_bundle is not None and not stop_after_m9:
            provider_bundle = bind_evidence_card_proposal_calls(
                provider_bundle,
                proposal_view,
            )
            schedule = provider_bundle
        if frozen_source is not None:
            (
                recording_summary,
                recording_manifests,
                frozen_recording_actors,
            ) = _frozen_recording_input_summary(recording_root)
            recording_bundle = None
        else:
            recording_bundle = RecordingBundle.model_validate_json(
                (m1_9_root / "recording_bundle.json").read_bytes(), strict=True
            )
            recording_summary, recording_manifests = _recording_input_summary(
                recording_root=recording_root,
                recording=recording_bundle,
            )
            frozen_recording_actors = ()
        recording_summary_path = m1_9_root / "recording_input_summary.json"
        if frozen_source is not None:
            if _read_object(recording_summary_path) != recording_summary:
                raise ValueError(
                    "frozen recording closure differs from its input summary"
                )
        else:
            _write_json(recording_summary_path, recording_summary)
        recording_manifest_snapshots = (
            _snapshot_frozen_recording_manifests(
                staging,
                actors=frozen_recording_actors,
                manifest_paths=recording_manifests,
            )
            if frozen_source is not None
            else _snapshot_recording_manifests(
                staging,
                recording=recording_bundle,
                manifest_paths=recording_manifests,
            )
        )
        workflow_input_sources: dict[
            tuple[str, str, str], dict[str, Any]
        ] | None = None
        input_snapshots["recording_workflow_inputs"] = None

        def load_workflow_input_sources() -> Mapping[
            tuple[str, str, str], Mapping[str, Any]
        ]:
            nonlocal workflow_input_sources
            if workflow_input_sources is None:
                (
                    workflow_input_sources,
                    workflow_input_index_path,
                ) = _snapshot_workflow_input_sources(
                    staging,
                    repo_root=root,
                    manifest_paths=recording_manifests,
                )
                input_snapshots["recording_workflow_inputs"] = (
                    workflow_input_index_path
                )
            return workflow_input_sources
        freeze = (
            _load_copied_frozen_input(
                m1_9_root,
                expected_manifest_sha256=(
                    frozen_source.lineage.completion.input_freeze_manifest_sha256
                ),
            )
            if frozen_source is not None
            else write_current_v2_input_freeze(
                output_root=m1_9_root,
                system=adapter_bundle.adapter.subject_id,
                run_id=schedule.plan_id,
                frozen_at=schedule.frozen_at,
                sources={
                    "profile": _file_ref(staging, input_snapshots["profile"]),
                    "recording_input_summary": {
                        **_file_ref(staging, recording_summary_path),
                        "actor_count": recording_summary["actor_count"],
                        "consumed_file_count": recording_summary[
                            "consumed_file_count"
                        ],
                        "consumed_total_bytes": recording_summary[
                            "consumed_total_bytes"
                        ],
                        "aggregate_sha256": recording_summary[
                            "aggregate_sha256"
                        ],
                    },
                    "proposal_schedule": _file_ref(
                        staging, input_snapshots["provider_plan"]
                    ),
                    "provider_fixture_responses": [
                        _file_ref(staging, path)
                        for path in input_snapshots["fixture_responses"]
                    ],
                    "provider_replay_sources": [
                        _file_ref(staging, path)
                        for path in input_snapshots["replay_sources"]
                    ],
                    "subject_adapter": _file_ref(
                        staging, input_snapshots["adapter"]
                    ),
                    "runtime_fixture_tape": (
                        _file_ref(staging, input_snapshots["fixture_tape"])
                        if input_snapshots["fixture_tape"] is not None
                        else None
                    ),
                },
                counts=offline_report["counts"],
            )
        )
        request_domains = freeze.frozen_input.lineage.view.request_setup_domains
        proposal_available_refs = {
            ref for ref, row in request_domains.items()
            if row.get("status") == "available"
        }
        proposal_full_refs = {
            ref for ref, row in request_domains.items()
            if row.get("status") in {"available", "unsupported"}
        }
        proposal_unsupported_refs = {
            ref for ref, row in request_domains.items()
            if row.get("status") == "unsupported"
        }
        if (
            len(business_refs) != len(set(business_refs))
            or len(business_available_refs) != len(set(business_available_refs))
            or len(business_unsupported_refs) != len(set(business_unsupported_refs))
            or set(business_available_refs) & set(business_unsupported_refs)
            or set(business_refs)
            != set(business_available_refs) | set(business_unsupported_refs)
            or set(business_refs) != proposal_full_refs
            or set(business_available_refs) != proposal_available_refs
            or set(business_unsupported_refs) != proposal_unsupported_refs
        ):
            raise ValueError(
                "typed business partition differs from the frozen proposal populations"
            )
        _append_offline_stages(
            stages,
            run_root=staging,
            m1_9_root=m1_9_root,
            profile_path=input_snapshots["profile"],
            adapter_path=input_snapshots["adapter"],
            proposal_path=input_snapshots["provider_plan"],
            provider_response_paths=[
                *input_snapshots["fixture_responses"],
                *input_snapshots["replay_sources"],
            ],
            recording_summary_path=recording_summary_path,
            recording_manifest_paths=recording_manifest_snapshots,
            recording_summary=recording_summary,
            counts=offline_report["counts"],
            runtime_counts=(
                runtime_factory.route_s_counts() if runtime_started else None
            ),
        )
        if frozen_source is not None:
            for stage in stages:
                stage["execution_boundary"] = (
                    "validated_completed_frozen_source_reuse"
                )
                stage["reused_without_execution"] = True

        if stop_after_m9:
            if frozen_source is not None:
                raise AssertionError("frozen M10 source cannot stop before M10")
            if runtime_started:
                runtime_factory.teardown()
                runtime_started = False
            runtime_counts = Counter(
                runtime_factory.route_s_counts()
                if runtime_factory is not None
                else {}
            )
            if active_execution_path.read_bytes() != active_execution_before:
                raise RuntimeError("ACTIVE execution lock changed during the canonical run")
            method_hashes = {
                path: _sha256_file(root / path) for path in METHOD_FILES
            }
            contract_hashes = {
                name: _sha256_file(root / "contracts" / name)
                for name in PIPELINE_SCHEMA_FILES
            }
            counters = {
                "provider_logical_calls": 0,
                "provider_transport_attempts": 0,
                "external_provider_llm_calls": 0,
                "live_invocations": int(offline_report["counts"]["stage2_5_executed"] > 0),
                "external_network_calls": runtime_counts["external_network_calls"],
                "real_target_runs": runtime_counts["real_target_runs"],
                "real_browser_runs": runtime_counts["real_browser_runs"],
                "real_server_runs": runtime_counts["real_server_runs"],
                "real_docker_runs": runtime_counts["real_docker_runs"],
                "real_reset_runs": runtime_counts["real_reset_runs"],
                "stage2_5_planned_candidates": offline_report["counts"][
                    "stage2_5_records"
                ],
                "stage2_5_active_http_probes": offline_report["counts"][
                    "stage2_5_executed"
                ],
                "stage2_5_admitted": offline_report["counts"][
                    "stage2_5_admitted"
                ],
                "stage2_5_rejected": offline_report["counts"][
                    "stage2_5_rejected"
                ],
                "stage2_5_not_executed": offline_report["counts"][
                    "stage2_5_not_executed"
                ],
            }
            terminal_manifest = {
                "schema_version": "uisemtest-current-terminal-run-manifest-v1",
                "status": "pass",
                "completion_reason": "m1_m9_complete_provider_not_executed",
                "terminal_status": "complete",
                "canonical_entrypoint": "scripts/uisemtest run",
                "execution_mode": "fresh_m1_to_m9_forensic_source",
                "execution_boundary": "completed_m9_before_provider_execution",
                "run_id": schedule.plan_id,
                "output_root": ".",
                "paper_data": False,
                "environment": {
                    "python_version": ".".join(
                        str(item) for item in sys.version_info[:3]
                    ),
                    "git_head": _git_head(root),
                    "evidence_organization": str(getattr(args, "evidence_organization", "association")),
                },
                "inputs": {
                    "profile": _file_ref(staging, input_snapshots["profile"]),
                    "adapter": _file_ref(staging, input_snapshots["adapter"]),
                    "recording_input_summary": {
                        **_file_ref(staging, recording_summary_path),
                        "actor_count": recording_summary["actor_count"],
                        "consumed_file_count": recording_summary[
                            "consumed_file_count"
                        ],
                        "consumed_total_bytes": recording_summary[
                            "consumed_total_bytes"
                        ],
                        "aggregate_sha256": recording_summary[
                            "aggregate_sha256"
                        ],
                    },
                    "proposal_plan": _file_ref(
                        staging, input_snapshots["provider_plan"]
                    ),
                    "provider": "not_executed",
                    "runtime": adapter_bundle.adapter.runtime.kind,
                    "historical_result_inputs": 0,
                    "frozen_m10_source": None,
                },
                "method_hashes": {
                    "files": method_hashes,
                    "aggregate_sha256": canonical_sha256(method_hashes),
                },
                "provider_replay": None,
                "contract_hashes": {
                    "files": contract_hashes,
                    "aggregate_sha256": canonical_sha256(contract_hashes),
                },
                "contract_inventory": _contract_inventory(
                    method_hashes=method_hashes,
                    contract_hashes=contract_hashes,
                ),
                "stages": stages,
                "current_counts": {
                    "M1_M9": dict(offline_report["counts"]),
                    "proposal": {
                        "raw_proposed": 0,
                        "valid_admitted": 0,
                        "invalid_rejected": 0,
                        "deduplicated": 0,
                    },
                    "candidate_count": 0,
                    "attempted_count": 0,
                    "evaluable_count": 0,
                    "local_not_evaluable_count": 0,
                    "outcomes": {},
                    "protocol_verdicts": {},
                    "confirmed_count": 0,
                    "generated_test_count": 0,
                    "retained_test_count": 0,
                    "auth_session": {},
                    "total_generated_test_count": 0,
                    "total_retained_test_count": 0,
                    "admitted_canonical_relation_core_identities": None,
                    "retained_canonical_relation_core_identities": None,
                },
                "denominators": {},
                "counters": counters,
                "provider_preflight": {
                    "status": "not_executed",
                    "reason": "terminal M9 qualification boundary",
                    "scheduled_logical_calls": 0,
                },
                "active_execution_lock_unchanged": True,
                "execution_authorization": _execution_authorization_snapshot(
                    root, live_requested=live_requested
                ),
                "offline_lock": None,
            }
            _write_json(staging / "run_manifest.json", terminal_manifest)
            publication_started = True
            publication = publish_current_output(
                scratch_root=staging,
                target_root=target,
                output_level=output_level,
            )
            return {
                "schema_version": "uisemtest-current-run-result-v1",
                "status": "pass",
                "completion_reason": "m1_m9_complete_provider_not_executed",
                "terminal_status": "complete",
                "output_root": str(target),
                "run_manifest": str(target / "run_manifest.json"),
                "candidate_count": 0,
                "counters": counters,
                **publication,
            }

        trace = UiApiTrace.model_validate_json(
            (m1_9_root / "ui_api_trace.json").read_bytes(), strict=True
        )
        catalog = ObservedApiCatalog.model_validate_json(
            (m1_9_root / "observed_api_catalog.json").read_bytes(), strict=True
        )
        value_flows = ObservedValueFlowSet.model_validate_json(
            (m1_9_root / "observed_value_flow_set.json").read_bytes(), strict=True
        )
        if runtime_factory is None:
            request_bindings = resolve_current_request_bindings(
                adapter_bundle,
                trace=trace,
                recording_root=recording_root,
                recorded_bundles=input_snapshots.get("recording_bundles"),
            )
            runtime_factory = build_current_runtime_factory(
                adapter_bundle,
                run_id=schedule.plan_id,
                request_bindings=request_bindings,
                trace=_runtime_trace_with_resolved_recording_paths(
                    trace, recording_root
                ),
                recording_material_aliases=resolve_recording_material_aliases(
                    recording_root
                ),
                recorded_bundles=input_snapshots.get("recording_bundles"),
            )
            runtime_factory.preflight()
        else:
            if active_trace_sha256 != trace.canonical_sha256():
                raise ValueError("active-probe trace differs from persisted current trace")
            if active_request_bindings is None:
                raise RuntimeError("active-probe request bindings were not retained")
            request_bindings = active_request_bindings

        if resume_completed_m10:
            # A downstream failure can leave complete M10 without the outer
            # forensic closure. Rebuild the same offline inputs, then validate
            # and reuse the saved lineage, including its bounded completion.
            shutil.copytree(target / "M10", staging / "M10")
            proposal_lineage = load_v2_proposal_run_lineage(
                run_root=staging / "M10",
                input_freeze_manifest_path=freeze.manifest_path,
                expected_input_manifest_sha256=freeze.manifest_raw_sha256,
                expected_completion_sha256=_sha256_file(target / "M10/proposal_run_completion.json"),
            )
            plan = proposal_lineage.plan
            factory = _FrozenM10Activity(
                input_size_chars=len(freeze.frozen_input.lineage.rendered_input.rendered_text)
            )
        elif m10_union_sources:
            round_sources = tuple(
                _load_frozen_m10_source(
                    source,
                    expected_completion_sha256=_sha256_file(
                        source / "M10/proposal_run_completion.json"
                    ),
                    profile_path=profile_path,
                    adapter_path=adapter_path,
                    subject_id=adapter_bundle.adapter.subject_id,
                )
                for source in m10_union_sources
            )
            if provider_bundle is None:
                raise AssertionError("fresh M10 union lacks its provider bundle")
            factory = build_center_completion_provider_factory(
                provider_bundle,
                call_limiter=getattr(args, "_provider_call_limiter", None),
            )
            proposal_lineage = union_v2_proposal_rounds(
                frozen=freeze.frozen_input,
                rounds=tuple(source.lineage for source in round_sources),
                output_root=staging / "M10",
                provider_factory=factory,
                response_delivery_kind=factory.response_delivery_kind,
                provider_concurrency=provider_concurrency,
                incomplete_completion_root=(
                    target / "M10/center_completion"
                    if resume_incomplete_m10
                    else None
                ),
            )
            factory.assert_complete()
            if output_level == "forensic" and not stop_after_m10:
                if recording_bundle is None:
                    raise AssertionError(
                        "fresh M10 union lacks its recording bundle"
                    )
                _snapshot_recording_closure(
                    staging,
                    recording_root=recording_root,
                    recording=recording_bundle,
                )
            plan = proposal_lineage.plan
        elif frozen_source is not None:
            proposal_lineage = load_v2_proposal_run_lineage(
                run_root=staging / "M10",
                input_freeze_manifest_path=freeze.manifest_path,
                expected_input_manifest_sha256=freeze.manifest_raw_sha256,
                expected_completion_sha256=frozen_source.completion_sha256,
            )
            plan = proposal_lineage.plan
            factory = _FrozenM10Activity(
                input_size_chars=len(
                    freeze.frozen_input.lineage.rendered_input.rendered_text
                )
            )
        else:
            plan = build_proposal_run_plan(
                freeze.frozen_input,
                plan_id=schedule.plan_id,
                frozen_at=schedule.frozen_at,
                calls=provider_bundle.proposal_specs,
                actual_model_policy=provider_bundle.proposal_policy.actual_model_policy,
            )
            factory = build_current_provider_factory(
                provider_bundle,
                call_limiter=getattr(args, "_provider_call_limiter", None),
            )
            if provider_bundle.proposal_specs:
                factory.preflight(
                    largest_proposal_call_prompt(
                        freeze.frozen_input,
                        provider_bundle.proposal_specs,
                    )
                )
            proposal_lineage = execute_v2_proposal_run(
                input_freeze_manifest_path=freeze.manifest_path,
                expected_manifest_sha256=freeze.manifest_raw_sha256,
                plan=plan,
                provider_factory=factory,
                output_root=staging / "M10",
                response_delivery_kind=factory.response_delivery_kind,
                incomplete_run_root=(
                    target / "M10" if resume_incomplete_m10 else None
                ),
                provider_concurrency=provider_concurrency,
            )
            factory.assert_complete()
        m10_outputs = sorted(
            path for path in (staging / "M10").rglob("*") if path.is_file()
        )
        stages.append(
            _stage(
                "M10",
                inputs=[
                    freeze.manifest_path,
                    input_snapshots["provider_plan"],
                    *input_snapshots["fixture_responses"],
                    *input_snapshots["replay_sources"],
                ],
                outputs=m10_outputs,
                consumer="ui_semantics.m11_bridge:bridge_v2_proposal_run_to_m11",
                contract="ProposalRunPlan/V2ProposalRunLineage",
                schema="uisemtest-v2-proposal-run-plan-v2",
                counts={
                    "scheduled_calls": proposal_lineage.completion.scheduled_call_count,
                    "scan_calls": len(plan.calls),
                    "detail_calls": len(
                        proposal_lineage.union_provenance.detail_regions
                    ),
                    "center_completion_calls": int(
                        proposal_lineage.union_provenance.center_completion.get(
                            "scheduled_completion_call_count", 0
                        )
                    ),
                    "center_completion_provider_logical_calls": int(
                        proposal_lineage.union_provenance.center_completion.get(
                            "provider_logical_call_count", 0
                        )
                    ),
                    "provider_logical_calls": factory.logical_call_count,
                    "provider_transport_attempts": factory.transport_attempt_count,
                    "provider_concurrency_planned": (
                        proposal_lineage.completion.provider_concurrency_planned
                    ),
                    "provider_concurrency_actual_max": (
                        proposal_lineage.completion.provider_concurrency_actual_max
                    ),
                    "sealed_response_replays": factory.sealed_response_replay_count,
                    "union_candidates": len(proposal_lineage.candidate_set.candidates),
                    "raw_proposed_candidates": proposal_lineage.union_provenance.raw_proposed_count,
                    "valid_admitted_candidates": proposal_lineage.union_provenance.valid_admitted_count,
                    "invalid_rejected_candidates": proposal_lineage.union_provenance.invalid_rejected_count,
                    "deduplicated_candidates": proposal_lineage.union_provenance.deduplicated_count,
                    "external_provider_llm_calls": factory.external_provider_llm_calls,
                },
                activity_counts={
                    "external_provider_llm_calls": factory.external_provider_llm_calls,
                    "live_invocations": int(
                        schedule.provider.kind in {"openai_compatible", "codex_cli"}
                    ),
                    "external_network_calls": factory.external_network_calls,
                },
                run_root=staging,
            )
        )
        if frozen_source is not None or resume_completed_m10:
            stages[-1]["execution_boundary"] = (
                "validated_completed_frozen_source_reuse"
            )
            stages[-1]["reused_without_execution"] = True
        elif m10_union_sources:
            completion_calls = int(
                proposal_lineage.union_provenance.center_completion.get(
                    "scheduled_completion_call_count", 0
                )
            )
            stages[-1]["execution_boundary"] = (
                "bounded_center_completion_after_round_union"
                if completion_calls
                else "completed_m10_round_union_reuse"
            )
            stages[-1]["reused_without_execution"] = completion_calls == 0

        execution_plans = {
            str(row["plan_id"]): row
            for row in proposal_lineage.union_provenance.constructed_execution_plans
        }
        canonical_relation_core_by_candidate = {
            record.candidate_id: canonical_relation_core_identity(
                record.payload,
                execution_plans[str(record.payload["observation_opportunity_ref"])],
                freeze.frozen_input.lineage.view.api_requests,
            )
            for record in proposal_lineage.candidate_set.candidates
        }

        if stop_after_m10:
            if frozen_source is not None:
                raise AssertionError("frozen M10 cannot enter the M10 stop boundary")
            if recording_bundle is None:
                raise AssertionError("fresh M10 stop boundary lacks its recording bundle")
            _snapshot_recording_closure(
                staging,
                recording_root=recording_root,
                recording=recording_bundle,
            )
            if runtime_started:
                runtime_factory.teardown()
                runtime_started = False
            runtime_counts = Counter(runtime_factory.route_s_counts())
            if active_execution_path.read_bytes() != active_execution_before:
                raise RuntimeError("ACTIVE execution lock changed during the canonical run")
            completion_path = staging / "M10/proposal_run_completion.json"
            completion_sha256 = _sha256_file(completion_path)
            method_hashes = {
                path: _sha256_file(root / path) for path in METHOD_FILES
            }
            contract_hashes = {
                name: _sha256_file(root / "contracts" / name)
                for name in PIPELINE_SCHEMA_FILES
            }
            proposal_counts = {
                "raw_proposed": proposal_lineage.union_provenance.raw_proposed_count,
                "valid_admitted": proposal_lineage.union_provenance.valid_admitted_count,
                "invalid_rejected": proposal_lineage.union_provenance.invalid_rejected_count,
                "deduplicated": proposal_lineage.union_provenance.deduplicated_count,
            }
            counters = {
                "provider_logical_calls": factory.logical_call_count,
                "provider_transport_attempts": factory.transport_attempt_count,
                "external_provider_llm_calls": factory.external_provider_llm_calls,
                "live_invocations": int(live_requested),
                "external_network_calls": (
                    factory.external_network_calls
                    + runtime_counts["external_network_calls"]
                ),
                "real_target_runs": runtime_counts["real_target_runs"],
                "real_browser_runs": runtime_counts["real_browser_runs"],
                "real_server_runs": runtime_counts["real_server_runs"],
                "real_docker_runs": runtime_counts["real_docker_runs"],
                "real_reset_runs": runtime_counts["real_reset_runs"],
                "stage2_5_planned_candidates": offline_report["counts"][
                    "stage2_5_records"
                ],
                "stage2_5_active_http_probes": offline_report["counts"][
                    "stage2_5_executed"
                ],
                "stage2_5_admitted": offline_report["counts"][
                    "stage2_5_admitted"
                ],
                "stage2_5_rejected": offline_report["counts"][
                    "stage2_5_rejected"
                ],
                "stage2_5_not_executed": offline_report["counts"][
                    "stage2_5_not_executed"
                ],
            }
            if factory.sealed_response_replay_count:
                counters["sealed_response_replays"] = (
                    factory.sealed_response_replay_count
                )
            terminal_manifest = {
                "schema_version": "uisemtest-current-terminal-run-manifest-v1",
                "status": "pass",
                "completion_reason": "m10_complete_forensic_source",
                "terminal_status": "complete",
                "paper_data": False,
                "canonical_entrypoint": "scripts/uisemtest run",
                "execution_mode": (
                    "completed_m10_recovery_forensic_source"
                    if resume_completed_m10
                    else "fresh_m1_to_m10_forensic_source"
                ),
                "execution_boundary": "completed_m10_before_m11a",
                "run_id": schedule.plan_id,
                "output_root": ".",
                "environment": {
                    "python_version": ".".join(
                        str(item) for item in sys.version_info[:3]
                    ),
                    "git_head": _git_head(root),
                    "evidence_organization": str(getattr(args, "evidence_organization", "association")),
                },
                "inputs": {
                    "profile": _file_ref(staging, input_snapshots["profile"]),
                    "adapter": _file_ref(staging, input_snapshots["adapter"]),
                    "recording_input_summary": {
                        **_file_ref(staging, recording_summary_path),
                        "actor_count": recording_summary["actor_count"],
                        "consumed_file_count": recording_summary[
                            "consumed_file_count"
                        ],
                        "consumed_total_bytes": recording_summary[
                            "consumed_total_bytes"
                        ],
                        "aggregate_sha256": recording_summary[
                            "aggregate_sha256"
                        ],
                    },
                    "proposal_plan": _file_ref(
                        staging, input_snapshots["provider_plan"]
                    ),
                    "provider_fixture_responses": [
                        _file_ref(staging, path)
                        for path in input_snapshots["fixture_responses"]
                    ],
                    "provider_replay_sources": [
                        _file_ref(staging, path)
                        for path in input_snapshots["replay_sources"]
                    ],
                    "runtime_fixture_tape": (
                        _file_ref(staging, input_snapshots["fixture_tape"])
                        if input_snapshots["fixture_tape"] is not None
                        else None
                    ),
                    "provider": schedule.provider.kind,
                    "runtime": adapter_bundle.adapter.runtime.kind,
                    "historical_result_inputs": int(
                        bool(provider_bundle.replay_source_paths)
                    ),
                    "frozen_m10_source": None,
                },
                "method_hashes": {
                    "files": method_hashes,
                    "aggregate_sha256": canonical_sha256(method_hashes),
                },
                "provider_replay": (
                    {
                        "mode": "complete_m10_call_tree_exact_replay",
                        "source_m10_root_ref": schedule.provider.source_run_root_ref,
                        "external_provider_llm_calls": 0,
                        "external_network_calls": 0,
                    }
                    if isinstance(
                        schedule.provider, SealedResponseReplayRuntimeConfig
                    )
                    else None
                ),
                "contract_hashes": {
                    "files": contract_hashes,
                    "aggregate_sha256": canonical_sha256(contract_hashes),
                },
                "contract_inventory": _contract_inventory(
                    method_hashes=method_hashes,
                    contract_hashes=contract_hashes,
                ),
                "stages": stages,
                "current_counts": {
                    "proposal": proposal_counts,
                    "candidate_count": 0,
                    "attempted_count": 0,
                    "evaluable_count": 0,
                    "local_not_evaluable_count": 0,
                    "outcomes": {},
                    "protocol_verdicts": {},
                    "confirmed_count": 0,
                    "generated_test_count": 0,
                    "retained_test_count": 0,
                    "auth_session": {},
                    "total_generated_test_count": 0,
                    "total_retained_test_count": 0,
                    "admitted_canonical_relation_core_identities": list(
                        proposal_lineage.union_provenance.admitted_canonical_relation_core_identities
                    ),
                    "retained_canonical_relation_core_identities": None,
                },
                "denominators": {},
                "counters": counters,
                "provider_preflight": {
                    "rendered_input_chars": factory.input_size_chars,
                    "max_rendered_chars": schedule.provider.max_rendered_chars,
                    "scheduled_logical_calls": (
                        proposal_lineage.completion.scheduled_call_count
                        if factory.response_delivery_kind == "provider"
                        else 0
                    ),
                    "scheduled_response_deliveries": (
                        proposal_lineage.completion.scheduled_call_count
                    ),
                    "scheduled_sealed_response_replays": (
                        proposal_lineage.completion.scheduled_call_count
                        if factory.response_delivery_kind
                        == "sealed_response_replay"
                        else 0
                    ),
                    "frozen_m10_completed_calls_reused": 0,
                },
                "active_execution_lock_unchanged": True,
                "execution_authorization": _execution_authorization_snapshot(
                    root, live_requested=live_requested
                ),
                "offline_lock": (
                    {
                        "live_allowed": False,
                        "allowed_entrypoints": [],
                        "target_running": False,
                    }
                    if not live_requested
                    else None
                ),
            }
            _write_json(staging / "run_manifest.json", terminal_manifest)
            _load_frozen_m10_source(
                staging,
                expected_completion_sha256=completion_sha256,
                profile_path=profile_path,
                adapter_path=adapter_path,
                subject_id=adapter_bundle.adapter.subject_id,
            )
            publication_started = True
            publication = (
                _publish_recovered_current_output(
                    scratch_root=staging,
                    target_root=target,
                    output_level=output_level,
                )
                if resume_incomplete_m10
                else publish_current_output(
                    scratch_root=staging,
                    target_root=target,
                    output_level=output_level,
                )
            )
            _load_frozen_m10_source(
                target,
                expected_completion_sha256=completion_sha256,
                profile_path=profile_path,
                adapter_path=adapter_path,
                subject_id=adapter_bundle.adapter.subject_id,
            )
            return {
                "schema_version": "uisemtest-current-run-result-v1",
                "status": "pass",
                "completion_reason": "m10_complete_forensic_source",
                "terminal_status": "complete",
                "output_root": str(target),
                "run_manifest": str(target / "run_manifest.json"),
                "m10_completion": str(
                    target / "M10/proposal_run_completion.json"
                ),
                "m10_completion_sha256": completion_sha256,
                "candidate_count": len(
                    proposal_lineage.candidate_set.candidates
                ),
                "counters": counters,
                **publication,
            }

        materialization_adapter = adapter_materialization_view(
            adapter_bundle.adapter
        )
        materialization_adapter["request_bindings"] = request_bindings
        materialization_adapter["request_material_bindings"] = (
            resolve_current_request_material_bindings(
                trace=trace,
                request_bindings=request_bindings,
                recording_root=recording_root,
                recorded_bundles=input_snapshots.get("recording_bundles"),
                workflow_input_sources=load_workflow_input_sources,
            )
            if adapter_bundle.adapter.runtime.kind == "local_http"
            else ()
        )
        materialization_adapter["path_binding_targets"] = (
            resolve_current_path_binding_targets(
                value_flows=value_flows,
                catalog=catalog,
                recording_root=recording_root,
                request_bindings=request_bindings,
                recorded_bundles=input_snapshots.get("recording_bundles"),
            )
        )
        applicability = ProducerApplicability.model_validate_json(
            (m1_9_root / "producer_applicability.json").read_bytes(), strict=True
        )
        m11a = bridge_v2_proposal_run_to_m11(
            proposal_lineage,
            trace=trace,
            applicability=applicability,
            material_set_id=f"{schedule.plan_id}-m11a",
        )
        m11a_path = staging / "M11a/material_set.json"
        _write_bytes(m11a_path, m11a.canonical_bytes())
        m11a = V2RuntimeReadyMaterialSet.model_validate_json(
            m11a_path.read_bytes(),
            strict=True,
        )
        stages.append(
            _stage(
                "M11a",
                inputs=[
                    *m10_outputs,
                    m1_9_root / "ui_api_trace.json",
                    m1_9_root / "producer_applicability.json",
                ],
                outputs=[m11a_path],
                consumer="ui_semantics.m11b_materializer:materialize_current_route_s_inputs",
                contract="V2RuntimeReadyMaterialSet",
                schema="uisemtest-v2-runtime-ready-material-set-v1",
                counts={"bound_candidates": len(m11a.bound_candidates)},
                run_root=staging,
            )
        )

        scientific_pins = (
            _scientific_pins(
                root=root,
                profile_path=profile_path,
                adapter_path=adapter_path,
                adapter=materialization_adapter,
            )
            if output_level == "forensic"
            else {}
        )
        recording_trace = (
            SessionBundleReplayAdapter(
                _runtime_trace_with_resolved_recording_paths(
                    trace, recording_root
                ).trace,
                adapter_bundle.profile,
                recorded_bundles=input_snapshots.get("recording_bundles"),
            ).normalization_trace()
            if adapter_bundle.adapter.runtime.kind == "local_http"
            else None
        )
        m11b_result = materialize_current_route_s_inputs(
            m11a,
            trace=trace,
            value_flows=value_flows,
            binding_plan=materialization_adapter,
            scientific_pins=scientific_pins,
            output_level=output_level,
            recording_trace=recording_trace,
            recording_material_aliases=resolve_recording_material_aliases(
                recording_root
            ),
            authenticated_actor_identity_paths={
                actor_id: auth.probe_endpoint.expect_json_path
                for actor_id in [
                    str(item["actor_id"]) for item in trace.trace["actors"]
                ]
                if (
                    (auth := actor_auth(adapter_bundle.profile, actor_id))
                    .probe_endpoint is not None
                    and auth.probe_endpoint.expect_json_path is not None
                )
            },
            observed_catalog_requests={
                str(row["request_ref"]): row
                for row in proposal_lineage.frozen_input.lineage.view.api_requests
            },
            observed_catalog_operations={
                str(row["operation_id"]): row
                for row in proposal_lineage.frozen_input.lineage.view.api_operations
            },
        )
        m11b = m11b_result.materials
        if len(m11b) + len(m11b_result.ineligible) != len(m11a.bound_candidates):
            raise ValueError("M11b materialization partition drift")
        m11b_failures = list(m11b_result.ineligible)
        persisted_m11b = []
        for material in m11b:
            try:
                loaded_material = validate_and_persist_current_route_s_material(
                    material,
                    run_root=staging,
                    output_level=output_level,
                )
            except CandidateLocalFailure as error:
                if error.stage != "M11b":
                    raise
                _cleanup_candidate_scratch(staging, "M11b", material.candidate_id)
                m11b_failures.append(
                    error.record(
                        material.candidate_id,
                        status="materialization_ineligible",
                    )
                )
                continue
            persisted_m11b.append(loaded_material)
        m11b = tuple(persisted_m11b)
        _validate_candidate_partition(
            [item.candidate_id for item in m11a.bound_candidates],
            [item.candidate_id for item in m11b],
            [row["candidate_id"] for row in m11b_failures],
            label="M11b materialization",
        )
        eligibility_path = staging / "M11b/materialization_eligibility.json"
        _write_json(
            eligibility_path,
            {
                "artifact_type": "m11b_materialization_eligibility",
                "input_count": len(m11a.bound_candidates),
                "materialized_count": len(m11b),
                "materialization_ineligible_count": len(m11b_failures),
                "ineligible": sorted(
                    m11b_failures, key=lambda row: str(row["candidate_id"])
                ),
            },
        )
        m11b_outputs = sorted(
            path for path in (staging / "M11b").rglob("*") if path.is_file()
        )
        stages.append(
            _stage(
                "M11b",
                inputs=[
                    m11a_path,
                    m1_9_root / "ui_api_trace.json",
                    m1_9_root / "observed_api_catalog.json",
                    m1_9_root / "observed_value_flow_set.json",
                    input_snapshots["profile"],
                    input_snapshots["adapter"],
                    *(
                        [input_snapshots["recording_workflow_inputs"]]
                        if input_snapshots["recording_workflow_inputs"] is not None
                        else []
                    ),
                ],
                outputs=m11b_outputs,
                consumer="ui_semantics.current_protocols:execute_current_protocol",
                contract="current_route_s_execution_material_v1",
                schema="current_route_s_execution_material_v1.schema.json",
                counts={
                    "input_candidates": len(m11a.bound_candidates),
                    "materialized_candidates": len(m11b),
                    "materialization_ineligible": len(m11b_failures),
                    "contract_validated_candidates": len(m11b),
                    "persisted_core_candidates": len(m11b),
                    "execution_materials_validated": len(m11b),
                },
                run_root=staging,
            )
        )

        if not runtime_started:
            runtime_started = True
            runtime_factory.start(run_root=staging)
        route_s_records = []
        m12_rows = []
        m12_failures = []
        for material in m11b:
            runtime = runtime_factory.route_s_runtime(material)
            try:
                execution = execute_current_protocol(
                    material,
                    runtime,
                    artifact_writer=lambda ref, payload: _write_candidate_artifact(
                        staging,
                        material.candidate_id,
                        ref,
                        payload,
                    ),
                    output_level=output_level,
                )
                record = persist_current_protocol_execution(
                    run_root=staging,
                    material=material,
                    execution=execution,
                    output_level=output_level,
                )
            except (
                CandidateLocalFailure,
                CaptureRedactionError,
                SensitiveMaterialUnavailable,
            ) as error:
                if not isinstance(error, CandidateLocalFailure):
                    error = CandidateLocalFailure(
                        "M12", "capture_safety", str(error)
                    )
                if error.stage != "M12":
                    raise
                _cleanup_candidate_scratch(staging, "M12", material.candidate_id)
                failure = error.record(
                    material.candidate_id,
                    status="candidate_local_not_evaluable",
                )
                m12_failures.append(failure)
                protocol_result = candidate_local_protocol_result(
                    material.candidate_id,
                    error,
                    protocol_kind=derive_current_protocol(material),
                )
                m12_rows.append(
                    {
                        "candidate_id": material.candidate_id,
                        "attempted": True,
                        "evaluable": False,
                        "outcome": None,
                        "failure_stage": error.stage,
                        "failure_kind": failure["failure_kind"],
                        "category": error.category,
                        "reason_code": error.reason_code,
                        "protocol_result": protocol_result,
                    }
                )
                continue
            route_s_records.append(record)
            row = {
                "candidate_id": record.candidate_id,
                "attempted": True,
                "evaluable": True,
                "outcome": record.outcome,
                "certificate": record.source["certificate"],
                "protocol_result": copy.deepcopy(record.protocol_result),
            }
            diagnostic = diagnose_current_protocol_failure(execution)
            if diagnostic is not None:
                row.update(diagnostic)
            m12_rows.append(row)
        runtime_factory.assert_route_s_complete(len(m11b))
        route_s_runtime_counts = Counter(runtime_factory.route_s_counts())

        outcomes = Counter(item.outcome for item in route_s_records)
        protocol_verdicts = Counter(
            row["protocol_result"]["protocol_verdict"] for row in m12_rows
        )
        inconclusive_count = sum(
            outcomes[name]
            for name in ("infrastructure_failed", "setup_failed")
        )
        _validate_candidate_partition(
            [item.candidate_id for item in m11b],
            [item.candidate_id for item in route_s_records],
            [row["candidate_id"] for row in m12_failures],
            label="M12 evaluability",
        )
        if sum(outcomes.values()) != len(route_s_records):
            raise ValueError("Route-S outcome partition does not close evaluable candidates")
        if sum(protocol_verdicts.values()) != len(m11b):
            raise ValueError("current protocol verdict partition does not close attempted candidates")
        m12_report = {
            "schema_version": "uisemtest-current-route-s-run-report-v1",
            "status": "pass",
            "run_plan_id": schedule.plan_id,
            "candidate_input_count": len(m11b),
            "m11a_candidate_count": len(m11a.bound_candidates),
            "m11b_materialization_ineligible_count": len(m11b_failures),
            "candidate_attempted_count": len(m11b),
            "candidate_evaluable_count": len(route_s_records),
            "candidate_local_not_evaluable_count": len(m12_failures),
            "outcomes": dict(sorted(outcomes.items())),
            "protocol_verdicts": dict(sorted(protocol_verdicts.items())),
            "infrastructure_or_setup_inconclusive_count": inconclusive_count,
            "rows": m12_rows,
            "external_provider_llm_calls": factory.external_provider_llm_calls,
            "external_network_calls": (
                factory.external_network_calls
                + route_s_runtime_counts["external_network_calls"]
            ),
            "real_target_runs": route_s_runtime_counts["real_target_runs"],
            "real_reset_runs": route_s_runtime_counts["real_reset_runs"],
        }
        m12_report_path = staging / "M12/run_report.json"
        _write_json(m12_report_path, m12_report)
        auth_runtime = runtime_factory.auth_session_runtime()
        auth_request_start = int(
            getattr(auth_runtime, "local_http_requests", 0)
        )
        auth_reset_start = int(getattr(auth_runtime, "reset_runs", 0))
        auth_qualification = evaluate_auth_session_stratum(
            auth_runtime,
            adapter_bundle.profile,
            trace,
            producer_partition,
        )
        auth_qualification["activity_counts"] = {
            "local_http_requests": int(
                getattr(auth_runtime, "local_http_requests", 0)
            )
            - auth_request_start,
            "real_reset_runs": int(getattr(auth_runtime, "reset_runs", 0))
            - auth_reset_start,
            "external_provider_llm_calls": 0,
            "external_network_calls": 0,
        }
        auth_qualification_path = staging / "M12/auth_session_qualification.json"
        _write_json(auth_qualification_path, auth_qualification)
        if output_level == "forensic":
            m12_manifest_path = staging / "M12/recursive_manifest.json"
            _write_json(
                m12_manifest_path,
                _recursive_manifest(
                    staging,
                    prefixes=("M11b/", "M12/"),
                    exclude={"M12/recursive_manifest.json"},
                ),
            )
        m12_outputs = sorted(
            path for path in (staging / "M12").rglob("*") if path.is_file()
        )
        stages.append(
            _stage(
                "M12",
                inputs=[*m11b_outputs, input_snapshots["adapter"]],
                outputs=m12_outputs,
                consumer="ui_semantics.current_relation:build_current_relation_closure",
                contract="current protocol result with V1 evidence + certificate",
                schema="current_protocol_result_v1.schema.json",
                counts={
                    "attempted": len(m11b),
                    "evaluable": len(route_s_records),
                    "local_not_evaluable": len(m12_failures),
                    "completed": len(route_s_records),
                    "outcome_partition_total": sum(outcomes.values()),
                    **{
                        f"protocol_{key}": value
                        for key, value in sorted(protocol_verdicts.items())
                    },
                    **dict(sorted(outcomes.items())),
                    "auth_session_attempted": auth_qualification["denominator"][
                        "attempted"
                    ],
                    "auth_session_confirmed": auth_qualification["denominator"][
                        "confirmed"
                    ],
                    "auth_session_effect_absent": auth_qualification["denominator"][
                        "effect_absent"
                    ],
                    "auth_session_infrastructure_failed": auth_qualification[
                        "denominator"
                    ]["infrastructure_failed"],
                },
                activity_counts={
                    "external_provider_llm_calls": 0,
                    "live_invocations": int(
                        adapter_bundle.adapter.runtime.kind != "deterministic_fixture"
                    ),
                    "request_executions": (
                        route_s_runtime_counts["request_executions"]
                        + auth_qualification["activity_counts"][
                            "local_http_requests"
                        ]
                    ),
                    "external_network_calls": route_s_runtime_counts[
                        "external_network_calls"
                    ],
                    "real_target_runs": route_s_runtime_counts["real_target_runs"],
                    "real_browser_runs": route_s_runtime_counts["real_browser_runs"],
                    "real_server_runs": route_s_runtime_counts["real_server_runs"],
                    "real_docker_runs": route_s_runtime_counts["real_docker_runs"],
                    "real_reset_runs": (
                        route_s_runtime_counts["real_reset_runs"]
                        + auth_qualification["activity_counts"]["real_reset_runs"]
                    ),
                },
                run_root=staging,
            )
        )

        relation_closure = build_current_relation_closure(
            route_s_records,
            run_plan_id=schedule.plan_id,
            route_s_run_report_ref=_file_ref(staging, m12_report_path),
            repo_root=root,
        )
        closure_path = staging / "M13/current_relation_input_closure.json"
        _write_json(closure_path, relation_closure)
        suite = build_current_protocol_tests(
            relation_closure,
            run_id=f"{schedule.plan_id}-suite",
            normal_runs=schedule.normal_runs,
            created_at=schedule.frozen_at,
        )
        validate_certified_relation_tests(suite)
        for test in suite["tests"]:
            classes = Counter(item["assertion_class"] for item in test["assertions"])
            # The M13 validator owns the finite plan's generic definitions;
            # repeated execution has one status check per actual checkpoint.
            if classes["business"] != 1 or set(classes) != {"business", "generic"}:
                raise ValueError("current M13 assertion definition partition drift")
        suite_path = staging / "M13/certified_relation_tests.json"
        _write_json(suite_path, suite)
        suite = _read_object(suite_path)
        validate_certified_relation_tests(suite)
        generation = summarize_generation(suite, relation_closure)
        generation_path = staging / "M13/generation_report.json"
        _write_json(generation_path, generation)
        auth_tests = compile_auth_session_tests(
            auth_qualification,
            adapter_bundle.profile,
            normal_runs=schedule.normal_runs,
        )
        auth_tests_path = staging / "M13/auth_session_tests.json"
        _write_json(auth_tests_path, auth_tests)
        validated_count = protocol_verdicts["validated"]
        if len(suite["tests"]) != validated_count:
            raise ValueError("M13 generated test count does not equal validated count")
        stages.append(
            _stage(
                "M13",
                inputs=[*m12_outputs, input_snapshots["adapter"]],
                outputs=[
                    closure_path,
                    suite_path,
                    generation_path,
                    auth_tests_path,
                ],
                consumer="ui_semantics.current_protocols:run_current_protocol_calibration",
                contract="CertifiedRelationTestSuite",
                schema="certified_relation_tests.schema.json",
                counts={
                    "confirmed_input": validated_count,
                    "generated_tests": len(suite["tests"]),
                    "executable_eligible": generation["candidate_denominator"][
                        "executable_eligible"
                    ],
                    "conversion_dropped": generation["candidate_denominator"][
                        "conversion_dropped"
                    ],
                    "conversion_inconclusive": generation[
                        "candidate_denominator"
                    ]["conversion_inconclusive"],
                    "business_assertions": generation[
                        "assertion_definition_denominator"
                    ]["business"],
                    "generic_assertions": generation[
                        "assertion_definition_denominator"
                    ]["generic_status_schema"],
                    "auth_session_confirmed_input": auth_tests["confirmed_input"],
                    "auth_session_generated_tests": auth_tests["generated"],
                },
                run_root=staging,
            )
        )

        suite_ref = _file_ref(staging, suite_path)
        adapter_ref = _file_ref(staging, input_snapshots["adapter"])
        calibration_runtime = runtime_factory.calibration_runtime(suite)
        calibration = run_current_protocol_calibration(
            suite,
            runtime=calibration_runtime,
            suite_ref=suite_ref,
            adapter_ref=adapter_ref,
            canonical_relation_core_by_candidate=canonical_relation_core_by_candidate,
        )
        validate_current_calibration_report(
            calibration,
            suite=suite,
            adapter=adapter,
            run_root=staging,
        )
        calibration_path = staging / "M14/calibration_report.json"
        _write_json(calibration_path, calibration)
        calibration = _read_object(calibration_path)
        validate_current_calibration_report(
            calibration,
            suite=suite,
            adapter=adapter,
            run_root=staging,
        )
        final_view = {
            "schema_version": "uisemtest-final-calibrated-view-v1",
            "status": calibration["status"],
            "completion_reason": calibration["completion_reason"],
            "source_suite": _file_ref(staging, suite_path),
            "source_calibration": _file_ref(staging, calibration_path),
            "retained_candidate_ids": calibration["candidate_partition"]["retained"],
            "failed_candidate_ids": calibration["candidate_partition"]["failed"],
            "inconclusive_candidate_ids": calibration["candidate_partition"][
                "inconclusive"
            ],
            "not_run_candidate_ids": calibration["candidate_partition"]["not_run"],
            "candidate_denominator": calibration["candidate_denominator"],
            "test_denominator": calibration["test_denominator"],
            "assertion_definition_denominator": calibration[
                "assertion_definition_denominator"
            ],
            "physical_evaluation_denominator": calibration[
                "physical_evaluation_denominator"
            ],
            "m13_suite_mutated": calibration["suite_mutated"],
        }
        validate_final_calibrated_view(
            final_view,
            calibration=calibration,
            run_root=staging,
        )
        final_view_path = staging / "M14/final_calibrated_view.json"
        _write_json(final_view_path, final_view)
        final_suite = build_final_calibrated_suite(
            suite,
            calibration,
            final_view=final_view,
            final_view_ref=_file_ref(staging, final_view_path),
        )
        final_suite_path = staging / "M14/final_calibrated_suite.json"
        _write_json(final_suite_path, final_suite)
        final_suite = _read_object(final_suite_path)
        validate_final_calibrated_suite(
            final_suite,
            suite=suite,
            calibration=calibration,
            final_view=final_view,
            run_root=staging,
        )
        auth_calibration_request_start = int(
            getattr(auth_runtime, "local_http_requests", 0)
        )
        auth_calibration_reset_start = int(
            getattr(auth_runtime, "reset_runs", 0)
        )
        auth_calibration = calibrate_auth_session_tests(
            auth_runtime,
            adapter_bundle.profile,
            auth_tests,
        )
        auth_calibration["activity_counts"] = {
            "local_http_requests": int(
                getattr(auth_runtime, "local_http_requests", 0)
            )
            - auth_calibration_request_start,
            "real_reset_runs": int(getattr(auth_runtime, "reset_runs", 0))
            - auth_calibration_reset_start,
            "external_provider_llm_calls": 0,
            "external_network_calls": 0,
        }
        auth_calibration_path = staging / "M14/auth_session_calibration.json"
        _write_json(auth_calibration_path, auth_calibration)
        final_index = FinalSuiteIndex.model_validate(
            {
                "schema_version": "uisemtest-final-suite-index-v1",
                "artifact_type": "final_suite_index",
                "producer_partition": {
                    "domain_business": producer_partition["summary"]["business"],
                    "available": producer_partition["summary"]["business_available"],
                    "unsupported": producer_partition["summary"]["business_unsupported"],
                    "auth_session": producer_partition["summary"]["auth_session"],
                    "total": producer_partition["summary"]["total"],
                    "disjoint": producer_partition["summary"]["disjoint"],
                },
                "strata": {
                    "domain_business": {
                        "qualification_ref": _file_ref(staging, m12_report_path)[
                            "path"
                        ],
                        "tests_ref": _file_ref(staging, suite_path)["path"],
                        "calibration_ref": _file_ref(staging, final_suite_path)[
                            "path"
                        ],
                        "attempted": len(m11b),
                        "confirmed": validated_count,
                        "generated": len(suite["tests"]),
                        "retained": len(
                            calibration["candidate_partition"]["retained"]
                        ),
                    },
                    "auth_session": {
                        "qualification_ref": _file_ref(
                            staging, auth_qualification_path
                        )["path"],
                        "tests_ref": _file_ref(staging, auth_tests_path)["path"],
                        "calibration_ref": _file_ref(
                            staging, auth_calibration_path
                        )["path"],
                        "attempted": auth_qualification["denominator"][
                            "attempted"
                        ],
                        "confirmed": auth_qualification["denominator"][
                            "confirmed"
                        ],
                        "generated": auth_tests["generated"],
                        "retained": auth_calibration["test_denominator"][
                            "retained"
                        ],
                    },
                },
                "total_retained_count": (
                    len(calibration["candidate_partition"]["retained"])
                    + auth_calibration["test_denominator"]["retained"]
                ),
            },
            strict=True,
        )
        final_index_path = staging / "M14/final_suite_index.json"
        _write_bytes(final_index_path, canonical_json_bytes(final_index.model_dump(mode="json")))
        final_index = FinalSuiteIndex.model_validate_json(
            final_index_path.read_bytes(), strict=True
        )
        stages.append(
            _stage(
                "M14",
                inputs=[
                    suite_path,
                    auth_tests_path,
                    input_snapshots["adapter"],
                ],
                outputs=[
                    calibration_path,
                    final_view_path,
                    final_suite_path,
                    auth_calibration_path,
                    final_index_path,
                ],
                consumer="terminal run manifest",
                contract="CalibrationReport/final calibrated view/self-contained calibrated suite",
                schema="current_calibration_report_v1.schema.json;final_calibrated_view_v1.schema.json;final_calibrated_suite_v1.schema.json",
                counts={
                    "retained": len(calibration["candidate_partition"]["retained"]),
                    "failed": len(calibration["candidate_partition"]["failed"]),
                    "inconclusive": len(
                        calibration["candidate_partition"]["inconclusive"]
                    ),
                    "physical_evaluations": calibration[
                        "physical_evaluation_denominator"
                    ]["completed"],
                    "auth_session_generated": auth_tests["generated"],
                    "auth_session_retained": auth_calibration["test_denominator"][
                        "retained"
                    ],
                    "total_retained": final_index.total_retained_count,
                },
                activity_counts={
                    "external_provider_llm_calls": 0,
                    "live_invocations": int(
                        calibration["runtime_counts"]["real_target_runs"] > 0
                        and (
                            calibration["runtime_counts"]["request_executions"]
                            + auth_calibration["activity_counts"][
                                "local_http_requests"
                            ]
                            > 0
                            or calibration["runtime_counts"]["real_reset_runs"]
                            + auth_calibration["activity_counts"]["real_reset_runs"]
                            > 0
                        )
                    ),
                    "request_executions": (
                        calibration["runtime_counts"]["request_executions"]
                        + auth_calibration["activity_counts"][
                            "local_http_requests"
                        ]
                    ),
                    "external_network_calls": calibration["runtime_counts"][
                        "external_network_calls"
                    ],
                    "real_target_runs": calibration["runtime_counts"][
                        "real_target_runs"
                    ],
                    "real_browser_runs": calibration["runtime_counts"][
                        "real_browser_runs"
                    ],
                    "real_server_runs": calibration["runtime_counts"][
                        "real_server_runs"
                    ],
                    "real_docker_runs": calibration["runtime_counts"][
                        "real_docker_runs"
                    ],
                    "real_reset_runs": (
                        calibration["runtime_counts"]["real_reset_runs"]
                        + auth_calibration["activity_counts"]["real_reset_runs"]
                    ),
                },
                run_root=staging,
            )
        )

        runtime_factory.teardown()
        runtime_started = False
        total_runtime_counts = Counter(runtime_factory.route_s_counts())

        method_hashes = {
            path: _sha256_file(root / path) for path in METHOD_FILES
        }
        contract_hashes = {
            name: _sha256_file(root / "contracts" / name)
            for name in PIPELINE_SCHEMA_FILES
        }
        counters = {
            "provider_logical_calls": factory.logical_call_count,
            "provider_transport_attempts": factory.transport_attempt_count,
            "external_provider_llm_calls": factory.external_provider_llm_calls,
            "live_invocations": int(live_requested),
            "external_network_calls": (
                factory.external_network_calls
                + total_runtime_counts["external_network_calls"]
            ),
            "real_target_runs": total_runtime_counts["real_target_runs"],
            "real_browser_runs": total_runtime_counts["real_browser_runs"],
            "real_server_runs": total_runtime_counts["real_server_runs"],
            "real_docker_runs": total_runtime_counts["real_docker_runs"],
            "real_reset_runs": total_runtime_counts["real_reset_runs"],
            "route_s_reset_runs": route_s_runtime_counts["reset_runs"],
            "calibration_reset_runs": calibration["runtime_counts"]["reset_runs"],
            "auth_session_qualification_reset_runs": auth_qualification[
                "activity_counts"
            ]["real_reset_runs"],
            "auth_session_calibration_reset_runs": auth_calibration[
                "activity_counts"
            ]["real_reset_runs"],
            "auth_session_local_http_requests": (
                auth_qualification["activity_counts"]["local_http_requests"]
                + auth_calibration["activity_counts"]["local_http_requests"]
            ),
            "stage2_5_planned_candidates": offline_report["counts"][
                "stage2_5_records"
            ],
            "stage2_5_active_http_probes": offline_report["counts"][
                "stage2_5_executed"
            ],
            "stage2_5_admitted": offline_report["counts"]["stage2_5_admitted"],
            "stage2_5_rejected": offline_report["counts"]["stage2_5_rejected"],
            "stage2_5_not_executed": offline_report["counts"][
                "stage2_5_not_executed"
            ],
        }
        if factory.sealed_response_replay_count:
            counters["sealed_response_replays"] = factory.sealed_response_replay_count
        if frozen_source is not None:
            counters["frozen_m10_completed_calls_reused"] = (
                proposal_lineage.completion.completed_call_count
            )
        if active_execution_path.read_bytes() != active_execution_before:
            raise RuntimeError("ACTIVE execution lock changed during the canonical run")
        auth_confirmed = auth_qualification["denominator"]["confirmed"]
        empty_run = validated_count == 0 and auth_confirmed == 0
        completion_reason = (
            "relations_calibrated"
            if validated_count > 0
            else (
                "auth_session_calibrated"
                if auth_confirmed > 0
                else "no_confirmed_relations"
            )
        )
        terminal_manifest = {
            "schema_version": "uisemtest-current-terminal-run-manifest-v1",
            "status": "complete_empty" if empty_run else "pass",
            "completion_reason": completion_reason,
            "terminal_status": "complete",
            "paper_data": bool(getattr(args, "_paper_data_authorized", False)),
            "canonical_entrypoint": "scripts/uisemtest run",
            "execution_mode": (
                "completed_frozen_m10_to_m14"
                if frozen_source is not None
                else "fresh_m1_to_m14"
            ),
            "run_id": schedule.plan_id,
            "output_root": ".",
            "environment": {
                "python_version": ".".join(str(item) for item in sys.version_info[:3]),
                "git_head": _git_head(root),
                "evidence_organization": str(getattr(args, "evidence_organization", "association")),
            },
            "inputs": {
                "profile": _file_ref(staging, input_snapshots["profile"]),
                "adapter": _file_ref(staging, input_snapshots["adapter"]),
                "recording_input_summary": {
                    **_file_ref(staging, recording_summary_path),
                    "actor_count": recording_summary["actor_count"],
                    "consumed_file_count": recording_summary[
                        "consumed_file_count"
                    ],
                    "consumed_total_bytes": recording_summary[
                        "consumed_total_bytes"
                    ],
                    "aggregate_sha256": recording_summary[
                        "aggregate_sha256"
                    ],
                },
                "proposal_plan": _file_ref(
                    staging, input_snapshots["provider_plan"]
                ),
                "provider_fixture_responses": [
                    _file_ref(staging, path)
                    for path in input_snapshots["fixture_responses"]
                ],
                "provider_replay_sources": [
                    _file_ref(staging, path)
                    for path in input_snapshots["replay_sources"]
                ],
                "runtime_fixture_tape": (
                    _file_ref(staging, input_snapshots["fixture_tape"])
                    if input_snapshots["fixture_tape"] is not None
                    else None
                ),
                "recording_workflow_inputs": (
                    _file_ref(
                        staging,
                        input_snapshots["recording_workflow_inputs"],
                    )
                    if input_snapshots["recording_workflow_inputs"] is not None
                    else None
                ),
                "provider": schedule.provider.kind,
                "runtime": adapter_bundle.adapter.runtime.kind,
                "historical_result_inputs": int(
                    frozen_source is not None
                    or bool(provider_bundle.replay_source_paths)
                ),
                "frozen_m10_source": (
                    {
                        "source_root": str(frozen_source.root),
                        "completion_sha256": frozen_source.completion_sha256,
                        "copied_input_manifest": _file_ref(
                            staging, freeze.manifest_path
                        ),
                        "copied_completion": _file_ref(
                            staging, staging / "M10/proposal_run_completion.json"
                        ),
                    }
                    if frozen_source is not None
                    else None
                ),
            },
            "method_hashes": {
                "files": method_hashes,
                "aggregate_sha256": canonical_sha256(method_hashes),
            },
            "provider_replay": (
                {
                    "mode": "completed_frozen_m10_source_reuse",
                    "source_m10_root_ref": "M10",
                    "completed_calls_reused": (
                        proposal_lineage.completion.completed_call_count
                    ),
                    "external_provider_llm_calls": 0,
                    "external_network_calls": 0,
                }
                if frozen_source is not None
                else (
                    {
                        "mode": "complete_m10_call_tree_exact_replay",
                        "source_m10_root_ref": (
                            schedule.provider.source_run_root_ref
                        ),
                        "external_provider_llm_calls": 0,
                        "external_network_calls": 0,
                    }
                    if isinstance(
                        schedule.provider, SealedResponseReplayRuntimeConfig
                    )
                    else None
                )
            ),
            "contract_hashes": {
                "files": contract_hashes,
                "aggregate_sha256": canonical_sha256(contract_hashes),
            },
            "contract_inventory": _contract_inventory(
                method_hashes=method_hashes,
                contract_hashes=contract_hashes,
            ),
            "stages": stages,
            "current_counts": {
                "proposal": {
                    "raw_proposed": proposal_lineage.union_provenance.raw_proposed_count,
                    "valid_admitted": proposal_lineage.union_provenance.valid_admitted_count,
                    "invalid_rejected": proposal_lineage.union_provenance.invalid_rejected_count,
                    "deduplicated": proposal_lineage.union_provenance.deduplicated_count,
                },
                "candidate_count": len(m11b),
                "attempted_count": len(m11b),
                "evaluable_count": len(route_s_records),
                "local_not_evaluable_count": len(m12_failures),
                "outcomes": dict(sorted(outcomes.items())),
                "protocol_verdicts": dict(sorted(protocol_verdicts.items())),
                "confirmed_count": validated_count,
                "generated_test_count": len(suite["tests"]),
                "retained_test_count": len(
                    calibration["candidate_partition"]["retained"]
                ),
                "auth_session": {
                    "attempted": auth_qualification["denominator"]["attempted"],
                    "evaluable": auth_qualification["denominator"]["evaluable"],
                    "confirmed": auth_confirmed,
                    "outcomes": auth_qualification["outcomes"],
                    "generated_test_count": auth_tests["generated"],
                    "retained_test_count": auth_calibration[
                        "test_denominator"
                    ]["retained"],
                },
                "total_generated_test_count": (
                    len(suite["tests"]) + auth_tests["generated"]
                ),
                "total_retained_test_count": final_index.total_retained_count,
                "admitted_canonical_relation_core_identities": list(
                    proposal_lineage.union_provenance.admitted_canonical_relation_core_identities
                ),
                "retained_canonical_relation_core_identities": calibration[
                    "retained_canonical_relation_core_identities"
                ],
            },
            "denominators": {
                "candidate": calibration["candidate_denominator"],
                "test": calibration["test_denominator"],
                "assertion_definition": calibration[
                    "assertion_definition_denominator"
                ],
                "physical_evaluation": calibration[
                    "physical_evaluation_denominator"
                ],
                "auth_session": {
                    **auth_qualification["denominator"],
                    **auth_calibration["test_denominator"],
                },
            },
            "counters": counters,
            "provider_preflight": {
                "rendered_input_chars": factory.input_size_chars,
                "max_rendered_chars": schedule.provider.max_rendered_chars,
                "scheduled_logical_calls": (
                    proposal_lineage.completion.scheduled_call_count
                    if factory.response_delivery_kind == "provider"
                    else 0
                ),
                "scheduled_response_deliveries": (
                    0
                    if frozen_source is not None
                    else proposal_lineage.completion.scheduled_call_count
                ),
                "scheduled_sealed_response_replays": (
                    proposal_lineage.completion.scheduled_call_count
                    if factory.response_delivery_kind == "sealed_response_replay"
                    else 0
                ),
                "frozen_m10_completed_calls_reused": (
                    proposal_lineage.completion.completed_call_count
                    if frozen_source is not None
                    else 0
                ),
            },
            "active_execution_lock_unchanged": True,
            "execution_authorization": _execution_authorization_snapshot(
                root, live_requested=live_requested
            ),
            "offline_lock": (
                {
                    "live_allowed": False,
                    "allowed_entrypoints": [],
                    "target_running": False,
                }
                if not live_requested
                else None
            ),
        }
        manifest_path = staging / "run_manifest.json"
        _write_json(manifest_path, terminal_manifest)
        publication_started = True
        publication = (
            _publish_recovered_current_output(
                scratch_root=staging,
                target_root=target,
                output_level=output_level,
            )
            if resume_incomplete_m10
            else publish_current_output(
                scratch_root=staging,
                target_root=target,
                output_level=output_level,
            )
        )
        return {
            "schema_version": "uisemtest-current-run-result-v1",
            "status": "complete_empty" if empty_run else "pass",
            "completion_reason": completion_reason,
            "terminal_status": "complete",
            "paper_data": bool(getattr(args, "_paper_data_authorized", False)),
            "output_root": str(target),
            "run_manifest": str(target / "run_manifest.json"),
            "candidate_count": len(m11b),
            "candidate_attempted_count": len(m11b),
            "candidate_evaluable_count": len(route_s_records),
            "candidate_local_not_evaluable_count": len(m12_failures),
            "outcomes": dict(sorted(outcomes.items())),
            "protocol_verdicts": dict(sorted(protocol_verdicts.items())),
            "generated_test_count": len(suite["tests"]) + auth_tests["generated"],
            "retained_test_count": final_index.total_retained_count,
            "business_generated_test_count": len(suite["tests"]),
            "business_retained_test_count": len(
                calibration["candidate_partition"]["retained"]
            ),
            "auth_session": terminal_manifest["current_counts"]["auth_session"],
            "counters": counters,
            **publication,
        }
    except Exception:
        if runtime_started:
            try:
                runtime_factory.teardown()
            except Exception:
                pass
        m10_root = staging / "M10"
        if (
            frozen_source is None
            and not publication_started
            and m10_root.is_dir()
        ):
            if resume_incomplete_m10:
                _replace_recovered_m10(target / "M10", m10_root)
            elif not target.exists():
                target.mkdir()
                os.replace(m10_root, target / "M10")
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _load_frozen_m10_source(
    source_root: Path,
    *,
    expected_completion_sha256: str,
    profile_path: Path,
    adapter_path: Path,
    subject_id: str,
) -> _FrozenM10Source:
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("frozen M10 source is not a directory")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_completion_sha256):
        raise ValueError("frozen M10 completion SHA-256 is malformed")
    completion_path = root / "M10/proposal_run_completion.json"
    if (
        not completion_path.is_file()
        or _sha256_file(completion_path) != expected_completion_sha256
    ):
        raise ValueError("frozen M10 completion differs from its prebound SHA-256")
    completion = _read_object(completion_path)
    manifest_sha = completion.get("input_freeze_manifest_sha256")
    if not isinstance(manifest_sha, str):
        raise ValueError("frozen M10 completion lacks its M9 input pin")
    manifest_path = root / "M01_09/input_freeze_manifest.json"
    lineage = load_v2_proposal_run_lineage(
        run_root=root / "M10",
        input_freeze_manifest_path=manifest_path,
        expected_input_manifest_sha256=manifest_sha,
        expected_completion_sha256=expected_completion_sha256,
    )
    manifest = lineage.frozen_input.manifest
    if manifest.system != subject_id:
        raise ValueError("frozen M10 subject differs from the current adapter")
    profile_ref = _validated_frozen_source_ref(root, manifest.sources, "profile")
    adapter_ref = _validated_frozen_source_ref(
        root, manifest.sources, "subject_adapter"
    )
    proposal_path = _validated_frozen_source_ref(
        root, manifest.sources, "proposal_schedule"
    )
    if _sha256_file(profile_path) != _sha256_file(profile_ref):
        raise ValueError("current profile differs from the frozen M10 profile")
    if _sha256_file(adapter_path) != _sha256_file(adapter_ref):
        raise ValueError("current adapter differs from the frozen M10 adapter")
    proposal = _read_object(proposal_path)
    provider = proposal.get("provider")
    normal_runs = proposal.get("normal_runs")
    if (
        proposal.get("schema_version") != "uisemtest-current-provider-config-v1"
        or proposal.get("frozen_at") != manifest.frozen_at
        or not isinstance(normal_runs, int)
        or isinstance(normal_runs, bool)
        or normal_runs != 1
        or not isinstance(provider, dict)
        or provider.get("kind") not in {
            "fixture",
            "openai_compatible",
            "codex_cli",
            "sealed_response_replay",
        }
        or not isinstance(provider.get("max_rendered_chars"), int)
        or isinstance(provider.get("max_rendered_chars"), bool)
        or int(provider["max_rendered_chars"]) < 1
    ):
        raise ValueError("frozen M10 proposal schedule is not a closed replay input")
    _reject_symlinks(root / "M01_09")
    _reject_symlinks(root / "M10")
    recording_summary, _, _ = _frozen_recording_input_summary(root)
    if recording_summary != _read_object(
        root / "M01_09/recording_input_summary.json"
    ):
        raise ValueError("frozen M10 recording closure differs from its summary")
    return _FrozenM10Source(
        root=root,
        completion_sha256=expected_completion_sha256,
        proposal_path=proposal_path,
        schedule=_FrozenM10Schedule(
            plan_id=lineage.plan.plan_id,
            frozen_at=lineage.plan.frozen_at,
            normal_runs=normal_runs,
            provider=_FrozenM10Provider(
                max_rendered_chars=int(provider["max_rendered_chars"])
            ),
        ),
        lineage=lineage,
    )


def _validated_frozen_source_ref(
    root: Path,
    sources: Mapping[str, Any],
    name: str,
) -> Path:
    row = sources.get(name)
    if not isinstance(row, Mapping):
        raise ValueError(f"frozen M10 source lacks {name}")
    ref = row.get("path")
    digest = row.get("sha256")
    if not isinstance(ref, str) or not isinstance(digest, str):
        raise ValueError(f"frozen M10 source has an invalid {name} ref")
    relative = Path(ref)
    if relative.is_absolute() or relative == Path(".") or ".." in relative.parts:
        raise ValueError(f"frozen M10 source {name} ref is not root-relative")
    path = (root / relative).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(root):
        raise ValueError(f"frozen M10 source {name} ref escapes its root")
    if path.is_symlink() or _sha256_file(path) != digest:
        raise ValueError(f"frozen M10 source {name} ref differs from its pin")
    return path


def _restore_frozen_m10_source(
    source: _FrozenM10Source,
    *,
    staging: Path,
    profile_path: Path,
    adapter_path: Path,
    fixture_tape_path: Path | None,
) -> dict[str, Any]:
    _copy_frozen_tree(source.root / "M01_09", staging / "M01_09")
    _copy_frozen_tree(source.root / "M10", staging / "M10")
    _, _, actors = _frozen_recording_input_summary(source.root)
    for actor in actors:
        relative = Path(actor.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("frozen recording actor path is not root-relative")
        _copy_frozen_tree(
            (source.root / relative).resolve(strict=True),
            staging / relative,
        )
    reset_path = source.root / "reset/reset.json"
    if reset_path.exists():
        if not reset_path.is_file() or reset_path.is_symlink():
            raise ValueError("frozen recording reset is not one regular file")
        _snapshot_file(reset_path, staging / "reset/reset.json")

    manifest = source.lineage.frozen_input.manifest
    profile_target = staging / Path(str(manifest.sources["profile"]["path"]))
    adapter_target = staging / Path(
        str(manifest.sources["subject_adapter"]["path"])
    )
    proposal_target = staging / Path(
        str(manifest.sources["proposal_schedule"]["path"])
    )
    _snapshot_file(profile_path, profile_target)
    _snapshot_file(adapter_path, adapter_target)
    _snapshot_file(source.proposal_path, proposal_target)
    tape_snapshot: Path | None = None
    if fixture_tape_path is not None:
        relative = fixture_tape_path.resolve(strict=True).relative_to(
            adapter_path.resolve(strict=True).parent
        )
        tape_snapshot = adapter_target.parent / relative
        _snapshot_file(fixture_tape_path, tape_snapshot)
    return {
        "profile": profile_target,
        "adapter": adapter_target,
        "provider_plan": proposal_target,
        "fixture_responses": [],
        "replay_sources": [],
        "fixture_tape": tape_snapshot,
        "recording_bundles": _load_frozen_runtime_bundles(
            staging,
            actors=actors,
            trace=UiApiTrace.model_validate_json(
                (staging / "M01_09/ui_api_trace.json").read_bytes(), strict=True
            ),
        ),
    }


def _load_copied_frozen_input(
    m1_9_root: Path,
    *,
    expected_manifest_sha256: str,
) -> CurrentV2Freeze:
    manifest_path = m1_9_root / "input_freeze_manifest.json"
    frozen = load_hardened_v2_input(
        input_freeze_manifest_path=manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
        require_current_revision=True,
    )
    return CurrentV2Freeze(
        manifest=frozen.manifest,
        manifest_path=manifest_path,
        manifest_raw_sha256=frozen.manifest_raw_sha256,
        frozen_input=frozen,
    )


def _copy_frozen_tree(source: Path, target: Path) -> None:
    root = source.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("frozen source closure member is not a directory")
    _reject_symlinks(root)
    if target.exists():
        raise ValueError("frozen source closure collides in staging")
    shutil.copytree(root, target)


def _reject_symlinks(root: Path) -> None:
    if root.is_symlink() or any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("frozen source closure must not contain symlinks")


def _load_frozen_runtime_bundles(
    root: Path,
    *,
    actors: tuple[_FrozenRecordingActor, ...],
    trace: UiApiTrace,
) -> dict[str, LoadedBundle]:
    """Load only the request/action facts consumed by the downstream runtime."""

    expected = {
        (actor.actor_id, actor.run_id, actor.path)
        for actor in actors
    }
    observed = {
        (
            str(row["actor_id"]),
            str(row["session_bundle_ref"]["run_id"]),
            str(row["session_bundle_ref"]["path"]),
        )
        for row in trace.trace["actors"]
    }
    if observed != expected:
        raise ValueError("frozen trace actor/session refs differ from recording closure")
    bundles: dict[str, LoadedBundle] = {}
    for actor in actors:
        bundle_dir = (root / actor.path).resolve(strict=True)
        manifest = _read_object(bundle_dir / "manifest.json")
        members = manifest.get("members")
        if not isinstance(members, Mapping):
            raise ValueError("frozen runtime recording manifest lacks members")
        har_ref = members.get("har")
        actions_ref = members.get("ui_action_log")
        if not isinstance(har_ref, str) or not isinstance(actions_ref, str):
            raise ValueError("frozen runtime recording lacks HAR/action refs")
        har_path = (bundle_dir / har_ref).resolve(strict=True)
        actions_path = (bundle_dir / actions_ref).resolve(strict=True)
        if (
            not har_path.is_file()
            or not har_path.is_relative_to(bundle_dir)
            or not actions_path.is_file()
            or not actions_path.is_relative_to(bundle_dir)
        ):
            raise ValueError("frozen runtime recording member escapes its bundle")
        har = _read_object(har_path)
        validate_artifact("session_bundle_har.schema.json", har)
        entries = har.get("log", {}).get("entries")
        if not isinstance(entries, list):
            raise ValueError("frozen runtime HAR lacks entries")
        actions: list[dict[str, Any]] = []
        action_ids: set[str] = set()
        for line in actions_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("frozen runtime action is not an object")
            action_id = row.get("action_id")
            action_type = row.get("action_type")
            if (
                not isinstance(action_id, str)
                or not action_id
                or action_id in action_ids
                or not isinstance(action_type, str)
                or not action_type
            ):
                raise ValueError("frozen runtime actions are not uniquely identified")
            action_ids.add(action_id)
            actions.append(row)
        shapes = load_request_material_shapes(bundle_dir, manifest, entries)
        bundles[actor.run_id] = LoadedBundle(
            bundle_dir=bundle_dir,
            run_id=actor.run_id,
            manifest=manifest,
            entries=entries,
            actions=actions,
            decisions=[],
            request_material_shapes=MappingProxyType(shapes),
        )
    for event in trace.trace["events"]:
        ref = event["action_ref"]
        bundle = bundles.get(str(ref["run_id"]))
        if bundle is None or sum(
            row["action_id"] == ref["action_id"] for row in bundle.actions
        ) != 1:
            raise ValueError("frozen trace action ref is not uniquely recorded")
    return bundles


def _validate_incomplete_m10_target(target: Path) -> None:
    if not target.is_dir() or {path.name for path in target.iterdir()} != {"M10"}:
        raise ValueError("M10 recovery output must contain only one incomplete M10 root")
    m10 = target / "M10"
    if (m10 / "proposal_run_completion.json").is_file():
        # The current owner checks the complete lineage against freshly
        # reconstructed M9 before reuse; no provider dispatch is permitted.
        if (m10 / "proposal_run_failure.json").exists():
            raise ValueError("completed M10 recovery also contains a failure report")
        return
    regular_failure = (m10 / "proposal_run_failure.json").is_file()
    completion_failure = (
        (m10 / "center_completion/proposal_run_failure.json").is_file()
        and {path.name for path in m10.iterdir()} == {"center_completion"}
    )
    if (
        regular_failure == completion_failure
        or (m10 / "proposal_run_completion.json").exists()
        or (m10 / "union").exists()
    ):
        raise ValueError("M10 recovery output is not an incomplete current run")


def _replace_recovered_m10(previous: Path, replacement: Path) -> None:
    if not previous.is_dir() or not replacement.is_dir():
        raise ValueError("M10 recovery replacement roots are incomplete")
    backup = previous.parent / f".{previous.name}.resume-backup-{os.getpid()}"
    if backup.exists():
        raise ValueError("M10 recovery backup path already exists")
    os.replace(previous, backup)
    try:
        os.replace(replacement, previous)
    except Exception:
        os.replace(backup, previous)
        raise
    shutil.rmtree(backup)


def _publish_recovered_current_output(
    *,
    scratch_root: Path,
    target_root: Path,
    output_level: str,
) -> dict[str, Any]:
    target = target_root.resolve(strict=True)
    backup = target.parent / f".{target.name}.resume-backup-{os.getpid()}"
    if backup.exists():
        raise ValueError("current recovery publication backup already exists")
    os.replace(target, backup)
    try:
        publication = publish_current_output(
            scratch_root=scratch_root,
            target_root=target,
            output_level=output_level,
        )
    except Exception:
        if not target.exists():
            os.replace(backup, target)
        raise
    shutil.rmtree(backup)
    return publication


def _append_offline_stages(
    stages: list[dict[str, Any]],
    *,
    run_root: Path,
    m1_9_root: Path,
    profile_path: Path,
    adapter_path: Path,
    proposal_path: Path,
    provider_response_paths: list[Path],
    recording_summary_path: Path,
    recording_manifest_paths: list[Path],
    recording_summary: Mapping[str, Any],
    counts: Mapping[str, int],
    runtime_counts: Mapping[str, int] | None,
) -> None:
    artifacts = {
        name: m1_9_root / name
        for name in (
            "recording_bundle.json",
            "ui_api_trace.json",
            "observational_api_structure.json",
            "evidence_bundle.json",
            "producer_applicability.json",
            "discovery_candidate_audit.json",
            "observed_api_catalog.json",
            "observed_value_flow_set.json",
            "dependency_graph.json",
            "binding_opportunity_set.json",
            "preproposal_evidence_package.json",
            "proposal_evidence_view.json",
            "rendered_candidate_input.json",
            "effect_contract_v2.txt",
            "input_freeze_manifest.json",
        )
    }
    m1_outputs = [artifacts["recording_bundle.json"], recording_summary_path]
    m2_outputs = [artifacts["ui_api_trace.json"]]
    m3_outputs = [
        artifacts["observational_api_structure.json"],
        artifacts["evidence_bundle.json"],
        artifacts["producer_applicability.json"],
    ]
    m4_outputs = [artifacts["discovery_candidate_audit.json"]]
    m5_outputs = [artifacts["observed_api_catalog.json"]]
    m6_outputs = [artifacts["observed_value_flow_set.json"]]
    m7_outputs = [artifacts["dependency_graph.json"]]
    m8_outputs = [artifacts["binding_opportunity_set.json"]]
    m9_outputs = [
        artifacts["preproposal_evidence_package.json"],
        artifacts["proposal_evidence_view.json"],
        artifacts["rendered_candidate_input.json"],
        artifacts["effect_contract_v2.txt"],
        artifacts["input_freeze_manifest.json"],
    ]
    recording_inputs = list(recording_manifest_paths)
    rows = (
        ("M1", recording_inputs, m1_outputs, "ui_semantics.offline_pipeline:build_trace/build_observational_structure/build_evidence_bundle/producer_applicability", "RecordingBundle", "contract:pydantic:RecordingBundle", {"actors": recording_summary["actor_count"], "consumed_files": recording_summary["consumed_file_count"]}),
        ("M2", [*m1_outputs, profile_path], m2_outputs, "ui_semantics.offline_pipeline:build_evidence_bundle/producer_applicability;ui_semantics.preproposal:build_preproposal_mainline", "UiApiTrace", "contract:pydantic:UiApiTrace", {"events": counts["events"], "admitted_requests": counts["admitted_requests"]}),
        ("M3", [*m1_outputs, *m2_outputs, profile_path], m3_outputs, "ui_semantics.preproposal:build_preproposal_mainline", "ObservationalApiStructure/EvidenceBundle/ProducerApplicability", "contract:pydantic:M3-current", {"operations": counts["stage3_operations"]}),
        ("M4", [*m1_outputs, *m2_outputs, *m3_outputs], m4_outputs, "ui_semantics.preproposal:build_preproposal_evidence_package/build_proposal_evidence_view", "DiscoveryCandidateAudit", "contract:pydantic:DiscoveryCandidateAudit", {"planned": counts["stage2_5_records"], "executed": counts["stage2_5_executed"], "admitted": counts["stage2_5_admitted"], "rejected": counts["stage2_5_rejected"], "not_executed": counts["stage2_5_not_executed"]}),
        ("M5", [*m2_outputs, *m3_outputs, *m4_outputs], m5_outputs, "ui_semantics.preproposal:build_observed_dependency_graph/build_preproposal_evidence_package/build_proposal_evidence_view", "ObservedApiCatalog", "contract:pydantic:ObservedApiCatalog", {"observed_operations": counts["observed_catalog_operations"]}),
        ("M6", [*m1_outputs, *m2_outputs, *m3_outputs, *m5_outputs], m6_outputs, "ui_semantics.preproposal:build_observed_dependency_graph/build_binding_opportunity_set/build_preproposal_evidence_package/build_proposal_evidence_view", "ObservedValueFlowSet", "contract:pydantic:ObservedValueFlowSet", {"occurrences": counts["observed_value_flow_occurrences"]}),
        ("M7", [*m1_outputs, *m3_outputs, *m5_outputs, *m6_outputs], m7_outputs, "ui_semantics.preproposal:build_binding_opportunity_set/build_preproposal_evidence_package/build_proposal_evidence_view", "DependencyGraph", "contract:pydantic:DependencyGraph", {"edges": counts["dependency_edges"]}),
        ("M8", [*m3_outputs, *m6_outputs, *m7_outputs], m8_outputs, "ui_semantics.preproposal:build_preproposal_evidence_package/build_proposal_evidence_view", "BindingOpportunitySet", "contract:pydantic:BindingOpportunitySet", {"opportunities": counts["binding_opportunities"]}),
        ("M9", [*m1_outputs, *m2_outputs, *m3_outputs, *m4_outputs, *m5_outputs, *m6_outputs, *m7_outputs, *m8_outputs, profile_path, adapter_path, proposal_path, *provider_response_paths], m9_outputs, "ui_semantics.proposal_run:execute_v2_proposal_run", "PreProposalEvidencePackage/ProposalEvidenceView/RenderedCandidateInput/current input freeze", "uisemtest-current-v2-input-freeze-v2", {"provider_calls_at_freeze": 0}),
    )
    for stage_name, inputs, outputs, consumer, contract, schema, stage_counts in rows:
        stage_activity = None
        if stage_name == "M4" and runtime_counts is not None:
            stage_activity = {
                "live_invocations": int(counts["stage2_5_executed"] > 0),
                "external_network_calls": 0,
                "real_target_runs": runtime_counts["real_target_runs"],
                "real_server_runs": runtime_counts["real_server_runs"],
            }
        stage = _stage(
            stage_name,
            inputs=inputs,
            outputs=outputs,
            consumer=consumer,
            contract=contract,
            schema=schema,
            counts=stage_counts,
            run_root=run_root,
            activity_counts=stage_activity,
        )
        stage["execution_boundary"] = (
            "canonical_local_http_active_probe_then_in_memory_persist"
            if runtime_counts is not None
            else "existing_deterministic_offline_builder_in_memory_then_canonical_persist"
        )
        stage["write_reload_before_consumer"] = False
        stage["in_memory_inputs_hash_committed_by_current_contracts"] = True
        stages.append(stage)


def _stage(
    stage: str,
    *,
    inputs: list[Path],
    outputs: list[Path],
    consumer: str,
    contract: str,
    schema: str,
    counts: Mapping[str, int],
    run_root: Path,
    activity_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    activity = {
        "external_provider_llm_calls": 0,
        "live_invocations": 0,
        "request_executions": 0,
        "external_network_calls": 0,
        "real_target_runs": 0,
        "real_browser_runs": 0,
        "real_server_runs": 0,
        "real_docker_runs": 0,
        "real_reset_runs": 0,
    }
    if activity_counts is not None:
        unknown = set(activity_counts) - set(activity)
        if unknown or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in activity_counts.values()
        ):
            raise ValueError("stage activity counts are invalid")
        activity.update(activity_counts)
    return {
        "stage": stage,
        "status": "pass",
        "inputs": [_file_ref(run_root, path) for path in inputs],
        "outputs": [_file_ref(run_root, path) for path in outputs],
        "consumer": consumer,
        "contract": contract,
        "schema": schema,
        "current_artifact_count": len(outputs),
        "counts": dict(counts),
        "activity_counts": activity,
    }


def _contract_inventory(
    *,
    method_hashes: Mapping[str, str],
    contract_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Describe the real validator source for every current fixture stage."""

    def python_sources(*paths: str) -> list[dict[str, str]]:
        return [{"path": path, "sha256": method_hashes[path]} for path in paths]

    def schema_sources(*names: str) -> list[dict[str, str]]:
        return [
            {"path": f"contracts/{name}", "sha256": contract_hashes[name]}
            for name in names
        ]

    return {
        "coverage": "current-generic-M1-M14",
        "entries": [
            {
                "stages": ["inputs", "M10", "M11b", "M12", "M14"],
                "kind": "published-current-input-contracts",
                "contracts": [
                    "AppProfile",
                    "current_subject_adapter_v1",
                    "ProposalRunPlan/ProposalCallSpec + thin provider runtime config",
                    "fixture execution-facts tape (fixture implementation only)",
                ],
                "sources": [
                    *schema_sources(
                        "app_profile.schema.json",
                        "current_subject_adapter_v1.schema.json",
                    ),
                    *python_sources(
                        "src/ui_semantics/current_adapter.py",
                        "src/ui_semantics/current_provider.py",
                        "src/ui_semantics/current_runtime_factory.py",
                    ),
                ],
            },
            {
                "stages": [f"M{index}" for index in range(1, 10)],
                "kind": "pydantic-current-contracts",
                "contracts": [
                    "RecordingBundle",
                    "UiApiTrace",
                    "ObservationalApiStructure",
                    "EvidenceBundle",
                    "ProducerApplicability",
                    "DiscoveryCandidateAudit",
                    "ObservedApiCatalog",
                    "ObservedValueFlowSet",
                    "DependencyGraph",
                    "BindingOpportunitySet",
                    "PreProposalEvidencePackage",
                    "ProposalEvidenceView",
                    "RenderedCandidateInput",
                    "HardenedV2InputFreezeManifest",
                ],
                "sources": python_sources(
                    "src/ui_semantics/contracts.py",
                    "src/ui_semantics/trace_builder.py",
                    "src/ui_semantics/offline_pipeline.py",
                    "src/ui_semantics/preproposal.py",
                    "src/ui_semantics/v2_proposer.py",
                ),
            },
            {
                "stages": ["M10"],
                "kind": "pydantic-current-contracts",
                "contracts": [
                    "ProposalCallSpec",
                    "ProposalRunPlan",
                    "ProposalCallProvenance",
                    "ProposalUnionProvenance",
                    "ProposalRunCompletion",
                    "V2ProposalResponse",
                    "CandidateSet",
                    "V2ProposalRunLineage",
                ],
                "sources": python_sources(
                    "src/ui_semantics/contracts.py",
                    "src/ui_semantics/v2_proposer.py",
                    "src/ui_semantics/proposal_run.py",
                    "src/ui_semantics/current_provider.py",
                ),
            },
            {
                "stages": ["M11a"],
                "kind": "pydantic-current-contracts",
                "contracts": [
                    "V2BoundCandidate",
                    "V2RuntimeReadyMaterial",
                    "V2RuntimeReadyMaterialSet",
                ],
                "sources": python_sources(
                    "src/ui_semantics/contracts.py",
                    "src/ui_semantics/m11_bridge.py",
                ),
            },
            {
                "stages": ["M11b"],
                "kind": "published-json-schema-and-current-cross-validator",
                "contracts": [
                    "current_route_s_execution_material_v1",
                    "RouteSPreLiveMaterializedCandidate",
                ],
                "sources": [
                    *schema_sources(
                        "current_route_s_execution_material_v1.schema.json",
                    ),
                    *python_sources(
                        "src/ui_semantics/m11b_materializer.py",
                        "src/ui_semantics/current_adapter.py",
                        "src/ui_semantics/current_route_s/validation.py",
                    ),
                ],
            },
            {
                "stages": ["M12"],
                "kind": "published-json-schema-and-scientific-invariants",
                "contracts": [
                    "current_route_s_evaluation_v1",
                    "uisemtest-current-protocol-result-v1",
                    "uisemtest-current-route-s-run-report-v1",
                ],
                "sources": [
                    *schema_sources(
                        "current_route_s_evaluation_v1.schema.json",
                        "current_protocol_result_v1.schema.json",
                    ),
                    *python_sources(
                        "src/ui_semantics/current_protocols/__init__.py",
                        "src/ui_semantics/current_route_s/core.py",
                        "src/ui_semantics/current_route_s/runtime.py",
                        "src/ui_semantics/current_runtime_factory.py",
                        "src/ui_semantics/current_route_s/validation.py",
                        "src/ui_semantics/current_relation.py",
                    ),
                ],
            },
            {
                "stages": ["M13"],
                "kind": "published-json-schema-and-current-compiler",
                "contracts": [
                    "CertifiedRelationTestSuite",
                    "certified-relation-input-closure-current-v2",
                    "current relation generation report",
                ],
                "sources": [
                    *schema_sources(
                        "metadata_envelope.schema.json",
                        "test_suite.schema.json",
                        "certified_relation_tests.schema.json",
                    ),
                    *python_sources(
                        "src/ui_semantics/current_protocols/__init__.py",
                        "src/ui_semantics/relation_phase_b.py",
                    ),
                ],
            },
            {
                "stages": ["M14"],
                "kind": "published-json-schema-and-stage6-executable-contract",
                "contracts": [
                    "current_calibration_report_v1",
                    "final_calibrated_view_v1",
                    "final_calibrated_suite_v1",
                    "CertifiedRelationRuntime",
                ],
                "sources": [
                    *schema_sources(
                        "current_calibration_report_v1.schema.json",
                        "final_calibrated_view_v1.schema.json",
                        "final_calibrated_suite_v1.schema.json",
                    ),
                    *python_sources(
                        "src/ui_semantics/current_protocols/__init__.py",
                        "src/ui_semantics/current_calibration.py",
                        "src/stage6_ground/relation_test_execution.py",
                    ),
                ],
            },
        ],
    }


def _scientific_pins(
    *,
    root: Path,
    profile_path: Path,
    adapter_path: Path,
    adapter: Mapping[str, Any],
) -> dict[str, str]:
    route_s_sha = _sha256_file(root / "src/ui_semantics/current_route_s/core.py")
    runtime_sha = _sha256_file(root / "src/ui_semantics/current_route_s/runtime.py")
    return {
        "verifier_sha256": route_s_sha,
        "partial_schema_sha256": _sha256_file(root / "contracts/route_s_partial_certificate_v2.schema.json"),
        "certificate_schema_sha256": _sha256_file(root / "contracts/route_s_certificate_v4.schema.json"),
        "execution_evidence_schema_sha256": _sha256_file(root / "contracts/route_s_execution_evidence_v5.schema.json"),
        "projector_sha256": route_s_sha,
        "equivalence_sha256": route_s_sha,
        "predicate_evaluator_sha256": route_s_sha,
        "predicate_linter_sha256": _sha256_file(root / "src/ui_semantics/dsl.py"),
        "observer_request_policy_sha256": hashlib.sha256(canonical_json_bytes(adapter["observer_policy"])).hexdigest(),
        "reset_driver_sha256": runtime_sha,
        "session_materializer_sha256": runtime_sha,
        "settle_policy_sha256": hashlib.sha256(canonical_json_bytes(adapter["settle_policy"])).hexdigest(),
        "profile_sha256": _sha256_file(profile_path),
        "renderer_sha256": route_s_sha,
        "subject_pin_sha256": _sha256_file(adapter_path),
    }


def _require_repo_runtime(root: Path) -> None:
    expected = root / ".venv/bin/python"
    if not expected.is_file() or not Path(sys.executable).samefile(expected):
        raise RuntimeError("scripts/uisemtest run requires the repository .venv Python")


def _require_execution_lock(
    root: Path,
    *,
    live_requested: bool,
    subject_id: str,
    provider_kind: str,
    runtime_kind: str,
    profile_path: Path,
    adapter_path: Path,
    output_root: Path,
) -> None:
    active = _read_object(root / "docs/ACTIVE-EXECUTION.json")
    if not live_requested:
        if (
            active.get("live_allowed") is not False
            or active.get("allowed_entrypoints") != []
            or active.get("target_running") is not False
        ):
            raise RuntimeError("offline current run requires the closed ACTIVE lock")
        return
    if (
        active.get("live_allowed") is not True
        or active.get("target_running") is not False
        or "scripts/uisemtest run" not in active.get("allowed_entrypoints", [])
    ):
        raise RuntimeError("live current run is not authorized by ACTIVE")
    capability = _select_execution_capability(
        active,
        subject_id=subject_id,
        profile_ref=_execution_path_ref(root, profile_path),
        adapter_ref=_execution_path_ref(root, adapter_path),
        output_root_ref=_execution_path_ref(root, output_root),
    )
    owner = capability.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        raise RuntimeError("ACTIVE current execution capability lacks an owner")
    if capability.get("canonical_entrypoint") != "scripts/uisemtest run":
        raise RuntimeError("ACTIVE current execution entrypoint mismatch")
    admitted = set(capability.get("runtime_kinds") or [])
    providers = set(capability.get("provider_kinds") or [])
    if runtime_kind not in admitted or provider_kind not in providers:
        raise RuntimeError("ACTIVE does not admit the requested provider/runtime")


def _output_root_within_scope(output_root_ref: str, scope_ref: Any) -> bool:
    """The run writes exactly the declared root, or one directory inside it.

    A per-case frozen-M10 continuation writes ``<scope>/cases/<case>/union``;
    the lock names the scope directory once instead of every case root.
    """
    if not isinstance(scope_ref, str) or not scope_ref:
        return False
    scope = scope_ref.rstrip("/")
    return output_root_ref == scope or output_root_ref.startswith(scope + "/")


def _select_execution_capability(
    active: Mapping[str, Any],
    *,
    subject_id: str,
    profile_ref: str,
    adapter_ref: str,
    output_root_ref: str,
) -> Mapping[str, Any]:
    """Pick the one declared capability that admits this run's subject and scope.

    ``current_execution_capability`` (single) and ``current_execution_capabilities``
    (list, one entry per subject/profile scope) are both accepted; exactly one
    entry may match the subject, profile, adapter and output-root scope.
    """
    declared: list[Mapping[str, Any]] = []
    single = active.get("current_execution_capability")
    if isinstance(single, Mapping):
        declared.append(single)
    listed = active.get("current_execution_capabilities")
    if isinstance(listed, list):
        declared.extend(item for item in listed if isinstance(item, Mapping))
    if not declared:
        raise RuntimeError("ACTIVE lacks a current subject execution capability")
    same_subject = [item for item in declared if item.get("subject_id") == subject_id]
    if not same_subject:
        raise RuntimeError("ACTIVE current execution subject mismatch")
    matching = [
        item
        for item in same_subject
        if item.get("profile_ref") == profile_ref
        and item.get("adapter_ref") == adapter_ref
        and _output_root_within_scope(output_root_ref, item.get("output_root_ref"))
    ]
    if len(matching) != 1:
        raise RuntimeError("ACTIVE current execution input/output scope mismatch")
    return matching[0]


def _execution_path_ref(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _execution_authorization_snapshot(
    root: Path, *, live_requested: bool
) -> dict[str, Any]:
    active = _read_object(root / "docs/ACTIVE-EXECUTION.json")
    return {
        "mode": "live_local_qualification" if live_requested else "offline",
        "live_allowed": active.get("live_allowed"),
        "allowed_entrypoints": copy_list(active.get("allowed_entrypoints")),
        "target_running_at_entry": active.get("target_running"),
        "canonical_entrypoint_authorized": (
            "scripts/uisemtest run" in (active.get("allowed_entrypoints") or [])
            if live_requested
            else active.get("allowed_entrypoints") == []
        ),
    }


def copy_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _recursive_manifest(
    root: Path,
    *,
    prefixes: tuple[str, ...],
    exclude: set[str],
) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        ref = path.relative_to(root).as_posix()
        if ref in exclude or not ref.startswith(prefixes):
            continue
        files.append(
            {"path": ref, "bytes": attested_size(path), "sha256": _sha256_file(path)}
        )
    return {
        "schema_version": "uisemtest-current-recursive-manifest-v1",
        "generated_last": True,
        "files": files,
        "aggregate_sha256": canonical_sha256(files),
    }


def _validate_candidate_partition(
    input_ids: list[str],
    completed_ids: list[str],
    failed_ids: list[str],
    *,
    label: str,
) -> None:
    if any(len(rows) != len(set(rows)) for rows in (input_ids, completed_ids, failed_ids)):
        raise ValueError(f"{label} candidate IDs are not unique")
    if set(completed_ids) & set(failed_ids):
        raise ValueError(f"{label} candidate partitions overlap")
    if set(input_ids) != set(completed_ids) | set(failed_ids):
        raise ValueError(f"{label} candidate partitions do not close input")


def _cleanup_candidate_scratch(run_root: Path, stage: str, candidate_id: str) -> None:
    if stage not in {"M11b", "M12"}:
        raise ValueError("candidate scratch cleanup stage is invalid")
    _, candidate_root = _candidate_stage_path(run_root, stage, candidate_id)
    if candidate_root.exists():
        shutil.rmtree(candidate_root)


def _write_candidate_artifact(
    run_root: Path,
    candidate_id: str,
    ref: str,
    payload: bytes,
) -> None:
    _, candidate_root = _candidate_stage_path(run_root, "M12", candidate_id)
    target = (run_root / ref).resolve()
    if not target.is_relative_to(candidate_root):
        raise ValueError("candidate artifact path escapes its M12 root")
    if target.exists():
        raise CandidateLocalFailure(
            "M12", "writer", "candidate_artifact_collision"
        )
    _write_bytes(target, payload)


def _candidate_stage_path(
    run_root: Path,
    stage: str,
    candidate_id: str,
) -> tuple[Path, Path]:
    candidate_segment = Path(candidate_id)
    if (
        not candidate_id
        or candidate_id in {".", ".."}
        or candidate_segment.name != candidate_id
        or len(candidate_segment.parts) != 1
    ):
        raise ValueError("candidate ID must be one ordinary path segment")
    stage_root = (run_root / stage).resolve()
    candidate_root = (stage_root / candidate_id).resolve()
    if candidate_root.parent != stage_root:
        raise ValueError("candidate path does not have the stage root as parent")
    return stage_root, candidate_root


def _recording_input_summary(
    *,
    recording_root: Path,
    recording: RecordingBundle,
) -> tuple[dict[str, Any], list[Path]]:
    return _recording_input_summary_from_actors(
        recording_root=recording_root,
        actors=tuple(
            _FrozenRecordingActor(
                actor_id=actor.actor_id,
                run_id=actor.run_id,
                path=actor.path,
                manifest_sha256=actor.manifest_sha256,
            )
            for actor in recording.actors
        ),
    )


def _frozen_recording_input_summary(
    recording_root: Path,
) -> tuple[dict[str, Any], list[Path], tuple[_FrozenRecordingActor, ...]]:
    """Validate only the recorded actor/session closure pinned by frozen M1-M10.

    A completed frozen M10 may predate the typed workflow driver.  Downstream
    stages consume its already-frozen trace and evidence rather than workflow
    correspondence, so this boundary deliberately validates only the common
    actor bundle facts and their byte-exact input summary.  The ordinary
    recording path continues to require ``RecordingBundle``.
    """

    root = recording_root.resolve(strict=True)
    raw = _read_object(root / "M01_09/recording_bundle.json")
    if (
        raw.get("schema_version") != "uisemtest.method.v1"
        or raw.get("artifact_type") != "recording_bundle"
        or not isinstance(raw.get("recording_id"), str)
        or not raw["recording_id"]
        or not isinstance(raw.get("actors"), list)
        or not raw["actors"]
    ):
        raise ValueError("frozen recording bundle lacks its actor/session closure")
    actors: list[_FrozenRecordingActor] = []
    actor_ids: set[str] = set()
    run_ids: set[str] = set()
    for row in raw["actors"]:
        if not isinstance(row, Mapping):
            raise ValueError("frozen recording actor entry is malformed")
        actor_id = row.get("actor_id")
        run_id = row.get("run_id")
        path = row.get("path")
        manifest_sha256 = row.get("manifest_sha256")
        if (
            not isinstance(actor_id, str)
            or not actor_id
            or not isinstance(run_id, str)
            or not run_id
            or not isinstance(path, str)
            or not path
            or not isinstance(manifest_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
            or actor_id in actor_ids
            or run_id in run_ids
        ):
            raise ValueError("frozen recording actors are not unique and closed")
        relative = Path(path)
        if relative.is_absolute() or relative == Path(".") or ".." in relative.parts:
            raise ValueError("frozen recording actor path is not root-relative")
        actor_ids.add(actor_id)
        run_ids.add(run_id)
        actors.append(
            _FrozenRecordingActor(
                actor_id=actor_id,
                run_id=run_id,
                path=path,
                manifest_sha256=manifest_sha256,
            )
        )
    summary, manifests = _recording_input_summary_from_actors(
        recording_root=root,
        actors=tuple(actors),
    )
    return summary, manifests, tuple(actors)


def _recording_input_summary_from_actors(
    *,
    recording_root: Path,
    actors: tuple[_FrozenRecordingActor, ...],
) -> tuple[dict[str, Any], list[Path]]:
    root = recording_root.resolve(strict=True)
    consumed: list[tuple[str, str]] = []
    consumed_paths: set[Path] = set()
    actor_manifests: list[dict[str, str]] = []
    manifest_paths: list[Path] = []

    for actor in sorted(actors, key=lambda item: (item.actor_id, item.run_id)):
        relative_bundle = Path(actor.path)
        bundle = (root / relative_bundle).resolve(strict=True)
        if not bundle.is_dir() or not bundle.is_relative_to(root):
            raise ValueError("frozen recording actor bundle escapes its root")
        manifest_path = (bundle / "manifest.json").resolve(strict=True)
        manifest_sha = _sha256_file(manifest_path)
        if manifest_sha != actor.manifest_sha256:
            raise ValueError("frozen recording actor manifest differs from its pin")
        manifest = _read_object(manifest_path)
        if manifest.get("metadata", {}).get("run_id") != actor.run_id:
            raise ValueError("frozen recording actor run ID differs from its manifest")
        members = manifest.get("members")
        if not isinstance(members, dict):
            raise ValueError("frozen recording actor manifest lacks members")
        relative_members = [Path("manifest.json")]
        for value in members.values():
            if isinstance(value, str):
                relative_members.append(Path(value))
            elif isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict) or not isinstance(
                        item.get("file"), str
                    ):
                        raise ValueError("frozen recording member list lacks file refs")
                    relative_members.append(Path(item["file"]))
            else:
                raise ValueError("frozen recording member declaration is malformed")
        for relative in relative_members:
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("frozen recording member path is not bundle-relative")
            path = (bundle / relative).resolve(strict=True)
            if not path.is_file() or not path.is_relative_to(bundle):
                raise ValueError("frozen recording member escapes its actor bundle")
            if path in consumed_paths:
                raise ValueError("frozen recording closure contains a duplicate file")
            consumed_paths.add(path)
            consumed.append(
                (
                    f"{actor.actor_id}/{actor.run_id}/{relative.as_posix()}",
                    _sha256_file(path),
                )
            )
        actor_manifests.append(
            {
                "actor_id": actor.actor_id,
                "run_id": actor.run_id,
                "path": manifest_path.relative_to(root).as_posix(),
                "sha256": manifest_sha,
            }
        )
        manifest_paths.append(manifest_path)
    consumed.sort()
    return (
        {
            "schema_version": "uisemtest-current-recording-input-summary-v1",
            "actor_count": len(actors),
            "consumed_file_count": len(consumed_paths),
            "consumed_total_bytes": sum(attested_size(path) for path in consumed_paths),
            "aggregate_sha256": canonical_sha256(consumed),
            "actor_manifests": actor_manifests,
        },
        manifest_paths,
    )


def _snapshot_current_inputs(
    run_root: Path,
    *,
    profile_path: Path,
    adapter_path: Path,
    proposal_path: Path,
    fixture_response_paths: tuple[Path, ...],
    replay_source_paths: tuple[Path, ...],
    replay_source_root_path: Path | None,
    fixture_tape_path: Path | None,
) -> dict[str, Any]:
    inputs = run_root / "inputs"
    profile_snapshot = inputs / "subject/profile.json"
    adapter_snapshot = inputs / "subject/adapter.json"
    provider_snapshot = inputs / "provider/provider_plan.json"
    _snapshot_file(profile_path, profile_snapshot)
    _snapshot_file(adapter_path, adapter_snapshot)

    if replay_source_root_path is None:
        if replay_source_paths:
            raise ValueError("sealed replay sources require their declared source root")
        _snapshot_file(proposal_path, provider_snapshot)
    else:
        if not replay_source_paths:
            raise ValueError("sealed replay source root has no declared dependencies")
        portable_plan = copy.deepcopy(_read_object(proposal_path))
        provider = portable_plan.get("provider")
        if not isinstance(provider, dict) or provider.get("kind") != "sealed_response_replay":
            raise ValueError("sealed replay snapshot plan/provider mismatch")
        provider["source_run_root_ref"] = "replay/source-run"
        _write_json(provider_snapshot, portable_plan)

    fixture_snapshots: list[Path] = []
    proposal_parent = proposal_path.resolve(strict=True).parent
    for source in fixture_response_paths:
        try:
            relative = source.resolve(strict=True).relative_to(proposal_parent)
        except ValueError as exc:
            raise ValueError("fixture response escapes its provider plan root") from exc
        target = provider_snapshot.parent / relative
        _snapshot_file(source, target)
        fixture_snapshots.append(target)

    replay_snapshots: list[Path] = []
    replay_root = (
        replay_source_root_path.resolve(strict=True)
        if replay_source_root_path is not None
        else None
    )
    for source in replay_source_paths:
        assert replay_root is not None
        try:
            relative = source.resolve(strict=True).relative_to(replay_root)
        except ValueError as exc:
            raise ValueError("sealed replay dependency escapes its source run root") from exc
        target = inputs / "provider/replay/source-run" / relative
        _snapshot_file(source, target)
        replay_snapshots.append(target)

    tape_snapshot: Path | None = None
    if fixture_tape_path is not None:
        adapter_parent = adapter_path.resolve(strict=True).parent
        try:
            relative = fixture_tape_path.resolve(strict=True).relative_to(
                adapter_parent
            )
        except ValueError as exc:
            raise ValueError("fixture tape escapes its adapter root") from exc
        tape_snapshot = adapter_snapshot.parent / relative
        _snapshot_file(fixture_tape_path, tape_snapshot)

    return {
        "profile": profile_snapshot,
        "adapter": adapter_snapshot,
        "provider_plan": provider_snapshot,
        "fixture_responses": fixture_snapshots,
        "replay_sources": replay_snapshots,
        "fixture_tape": tape_snapshot,
    }


def _snapshot_recording_manifests(
    run_root: Path,
    *,
    recording: RecordingBundle,
    manifest_paths: list[Path],
) -> list[Path]:
    by_run = {
        str(_read_object(path).get("metadata", {}).get("run_id")): path
        for path in manifest_paths
    }
    snapshots: list[Path] = []
    for index, actor in enumerate(
        sorted(recording.actors, key=lambda item: item.actor_id), start=1
    ):
        source = by_run.get(actor.run_id)
        if source is None:
            raise ValueError("recording manifest snapshot cannot resolve actor run")
        target = run_root / "inputs/recording" / f"actor-{index:04d}.manifest.json"
        _snapshot_file(source, target)
        snapshots.append(target)
    return snapshots


def _snapshot_recording_closure(
    run_root: Path,
    *,
    recording_root: Path,
    recording: RecordingBundle,
) -> None:
    """Copy the exact typed actor/reset closure needed by frozen M10 reuse."""

    source_root = recording_root.resolve(strict=True)
    for actor in recording.actors:
        relative = Path(actor.path)
        source = (source_root / relative).resolve(strict=True)
        if not source.is_relative_to(source_root):
            raise ValueError("recording actor closure escapes its root")
        _copy_frozen_tree(source, run_root / relative)

    workflow_ref = Path(recording.workflow_result_ref)
    if workflow_ref.is_absolute() or ".." in workflow_ref.parts:
        raise ValueError("recording workflow result ref is not root-relative")
    workflow_path = (source_root / workflow_ref).resolve(strict=True)
    if not workflow_path.is_file() or not workflow_path.is_relative_to(source_root):
        raise ValueError("recording workflow result escapes its root")
    _snapshot_file(workflow_path, run_root / workflow_ref)
    workflow_result = _read_object(workflow_path)
    reset = workflow_result.get("reset_epoch")
    reset_ref = reset.get("artifact_ref") if isinstance(reset, Mapping) else None
    if reset_ref is not None:
        if not isinstance(reset_ref, str):
            raise ValueError("recording reset artifact ref is malformed")
        relative = Path(reset_ref)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("recording reset artifact ref is not root-relative")
        reset_path = (source_root / relative).resolve(strict=True)
        if not reset_path.is_file() or not reset_path.is_relative_to(source_root):
            raise ValueError("recording reset artifact escapes its root")
        _snapshot_file(reset_path, run_root / relative)


def _snapshot_frozen_recording_manifests(
    run_root: Path,
    *,
    actors: tuple[_FrozenRecordingActor, ...],
    manifest_paths: list[Path],
) -> list[Path]:
    by_run = {
        str(_read_object(path).get("metadata", {}).get("run_id")): path
        for path in manifest_paths
    }
    snapshots: list[Path] = []
    for index, actor in enumerate(
        sorted(actors, key=lambda item: item.actor_id), start=1
    ):
        source = by_run.get(actor.run_id)
        if source is None:
            raise ValueError("frozen recording manifest cannot resolve actor run")
        target = run_root / "inputs/recording" / f"actor-{index:04d}.manifest.json"
        _snapshot_file(source, target)
        snapshots.append(target)
    return snapshots


def _snapshot_workflow_input_sources(
    run_root: Path,
    *,
    repo_root: Path,
    manifest_paths: list[Path],
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], Path]:
    """Snapshot the exact current workflows and index their dynamic inputs."""

    workflow_root = repo_root.resolve(strict=True) / "fixtures/recording_workflows"
    current_by_id: dict[str, list[Path]] = {}
    for path in sorted(workflow_root.rglob("*.json")):
        raw = _read_object(path)
        workflow_id = raw.get("workflow_id")
        if isinstance(workflow_id, str) and workflow_id:
            current_by_id.setdefault(workflow_id, []).append(path)

    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    workflow_refs: dict[str, dict[str, str]] = {}
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(manifest_paths):
        manifest = _read_object(manifest_path)
        metadata = manifest.get("metadata")
        session = manifest.get("session")
        if not isinstance(metadata, Mapping) or not isinstance(session, Mapping):
            raise ValueError("recording manifest lacks workflow provenance")
        run_id = metadata.get("run_id")
        actor_id = session.get("actor_id")
        workflow_id = session.get("workflow_id")
        recorded_ref = session.get("workflow_ref")
        if (
            not isinstance(run_id, str)
            or not run_id
            or not isinstance(actor_id, str)
            or not actor_id
            or not isinstance(workflow_id, str)
            or not workflow_id
            or not isinstance(recorded_ref, str)
            or not recorded_ref
        ):
            raise ValueError("recording manifest workflow provenance is malformed")
        recorded_source_path = Path(recorded_ref)
        if not recorded_source_path.is_absolute():
            raise ValueError("recorded workflow ref must be absolute")
        if recorded_source_path.is_symlink():
            raise ValueError("recorded workflow ref is not one regular file")
        recorded_path = recorded_source_path.resolve(strict=True)
        if not recorded_path.is_file():
            raise ValueError("recorded workflow ref is not one regular file")
        candidates = current_by_id.get(workflow_id, [])
        if len(candidates) != 1:
            raise ValueError("recorded workflow ID does not resolve uniquely")
        current_source_path = candidates[0]
        if current_source_path.is_symlink():
            raise ValueError("current workflow is not one regular file")
        current_path = current_source_path.resolve(strict=True)
        if (
            recorded_path.read_bytes() != current_path.read_bytes()
        ):
            raise ValueError("current workflow differs from recorded workflow bytes")
        workflow = load_recording_workflow(current_path)
        if workflow.workflow_id != workflow_id:
            raise ValueError("current workflow identity differs from recording")
        if actor_id not in {actor.actor_id for actor in workflow.actors}:
            raise ValueError("recording actor is absent from current workflow")
        workflow_sha256 = _sha256_file(current_path)
        snapshot_path = (
            run_root / "inputs/recording/workflows" / f"{workflow_sha256}.json"
        )
        _snapshot_file(current_path, snapshot_path)
        workflow_ref = snapshot_path.relative_to(run_root).as_posix()
        workflow_refs[workflow_id] = {
            "workflow_id": workflow_id,
            "workflow_ref": workflow_ref,
            "workflow_sha256": workflow_sha256,
        }
        for step in workflow.steps:
            value_env = step.action.value_env
            if step.actor_id != actor_id or value_env is None:
                continue
            key = (run_id, actor_id, step.workflow_step_id)
            if key in sources:
                raise ValueError("workflow input source is not unique")
            row = {
                "run_id": run_id,
                "actor_id": actor_id,
                "workflow_step_id": step.workflow_step_id,
                "global_step_index": step.global_step_index,
                "action_kind": step.action.kind,
                "value_env": value_env,
                "workflow_ref": workflow_ref,
                "workflow_sha256": workflow_sha256,
            }
            sources[key] = row
            rows.append(row)

    index_path = run_root / "inputs/recording/workflow_input_sources.json"
    _write_json(
        index_path,
        {
            "schema_version": "uisemtest-current-workflow-input-sources-v1",
            "workflows": [workflow_refs[key] for key in sorted(workflow_refs)],
            "sources": sorted(
                rows,
                key=lambda row: (
                    row["run_id"],
                    row["actor_id"],
                    row["global_step_index"],
                    row["workflow_step_id"],
                ),
            ),
        },
    )
    return sources, index_path


def _snapshot_file(source: Path, target: Path) -> None:
    payload = source.resolve(strict=True).read_bytes()
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError("run input snapshots collide with different bytes")
        return
    _write_bytes(target, payload)


def _runtime_trace_with_resolved_recording_paths(
    trace: UiApiTrace,
    recording_root: Path,
) -> UiApiTrace:
    """Resolve persisted recording-relative actor refs for runtime memory only."""

    runtime_trace = copy.deepcopy(trace.trace)
    root = recording_root.resolve(strict=True)
    for actor in runtime_trace["actors"]:
        ref = actor["session_bundle_ref"]
        relative = Path(str(ref["path"]))
        if relative.is_absolute() or relative == Path(".") or ".." in relative.parts:
            raise ValueError("runtime recording path is not root-relative")
        path = (root / relative).resolve(strict=True)
        if not path.is_dir() or not path.is_relative_to(root):
            raise ValueError("runtime recording path escapes the recording root")
        ref["path"] = str(path)
    return trace.model_copy(update={"trace": runtime_trace})


def _file_ref(root: Path, path: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    return {
        "path": resolved.relative_to(root.resolve(strict=True)).as_posix(),
        "sha256": _sha256_file(resolved),
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    _write_bytes(path, canonical_json_bytes(value))


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"current run refuses to overwrite: {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


def _git_head(root: Path) -> str:
    """Code revision recorded in run manifests.

    Inside the research repository this is the git HEAD.  A reproduction package
    extracted from an archive is not a git checkout; it carries ARTIFACT-VERSION
    (written by the package builder) whose first line is recorded instead.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        marker = root / "ARTIFACT-VERSION"
        if marker.is_file():
            first = marker.read_text(encoding="utf-8").strip().splitlines()
            if first:
                return first[0].strip()
        return "unknown-not-a-git-checkout"


__all__ = ["run_current_v2_pipeline"]
