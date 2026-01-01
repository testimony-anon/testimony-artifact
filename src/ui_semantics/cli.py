"""Single offline CLI for the UISemTest method pipeline."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from stage0_launch.profile import (
    AppProfile,
    actor_session_initialization_endpoint,
    load_app_profile,
)

from .offline_pipeline import (
    build_evidence_bundle,
    build_observational_structure,
    build_trace,
    declared_read_semantic_endpoints,
    declared_session_maintenance_endpoints,
    declared_session_transaction_endpoints,
    observed_response_statuses,
    producer_applicability,
    recording_bundle,
)
from .offline_producer_partition import partition_offline_producers
from .preproposal import build_preproposal_mainline


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def doctor_report() -> dict[str, Any]:
    root = repo_root()
    expected = root / ".venv/bin/python"
    executable = Path(sys.executable)
    resolved_executable = executable.resolve()
    dependencies = {}
    for name in ("pydantic", "jsonschema", "playwright"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "unavailable"
    active = _read_json(root / "docs/ACTIVE-EXECUTION.json")
    provider_authorized = (
        active.get("live_allowed") is True
        and "scripts/uisemtest run" in active.get("allowed_entrypoints", [])
    )
    checks = {
        "repository_venv_executable": executable.samefile(expected),
        "python_3_12": sys.version_info[:2] == (3, 12),
        "dependencies_available": all(value != "unavailable" for value in dependencies.values()),
        "current_active_target_stopped": active.get("target_running") is False,
    }
    return {
        "schema_version": "uisemtest-doctor-v1",
        "status": "pass" if all(checks.values()) else "fail",
        "executable": str(executable),
        "resolved_executable": str(resolved_executable),
        "expected_executable": str(expected),
        "python_version": ".".join(str(item) for item in sys.version_info[:3]),
        "dependencies": dependencies,
        "checks": checks,
        "live_commands_available": 0,
        "provider_commands_available": 1,
        "provider_commands_authorized": int(provider_authorized),
    }


def offline_build(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root()
    recording_root = args.recording_root.resolve()
    output_root = args.output_root.resolve()
    profile_model = load_app_profile(args.profile.resolve())
    profile = profile_model.model_dump(mode="json")
    bundles = _discover_actor_bundles(recording_root)
    normalizer = _profile_url_normalizer(profile)
    recording = recording_bundle(
        bundles,
        recording_id=args.run_id,
        recording_root=recording_root,
    )
    read_semantic_endpoints = declared_read_semantic_endpoints(profile_model)
    trace = build_trace(
        recording,
        recording_root=recording_root,
        trace_id=f"{args.run_id}-trace",
        url_normalizer=normalizer,
        read_semantic_endpoints=read_semantic_endpoints,
    )
    active_probe_setup = getattr(args, "active_probe_runtime_setup", None)
    active_probe_runner = (
        active_probe_setup(trace) if active_probe_setup is not None else None
    )
    structure, products = build_observational_structure(
        recording,
        recording_root=recording_root,
        structure_id=f"{args.run_id}-observational",
        url_normalizer=normalizer,
        active_probe_runner=active_probe_runner,
    )
    transfer_selection_bytes = args.transfer_selection.read_bytes() if args.transfer_selection else None
    transfer_population_bytes = args.transfer_population.read_bytes() if args.transfer_population else None
    evidence, _documents = build_evidence_bundle(
        trace,
        recording,
        recording_root=recording_root,
        evidence_id=f"{args.run_id}-evidence",
        enabled_channels={value.strip() for value in args.channels.split(",") if value.strip()},
        transfer_selection_bytes=transfer_selection_bytes,
        transfer_population_bytes=transfer_population_bytes,
    )
    applicability = producer_applicability(
        trace,
        recording,
        recording_root=recording_root,
        applicability_id=f"{args.run_id}-producers",
        session_endpoints=_session_endpoints(profile_model),
        read_semantic_endpoints=read_semantic_endpoints,
        session_maintenance_endpoints=declared_session_maintenance_endpoints(
            profile_model
        ),
        session_transaction_endpoints=declared_session_transaction_endpoints(
            profile_model
        ),
    )
    producer_partition = partition_offline_producers(
        trace,
        profile_model,
        applicability,
        response_status_by_request=observed_response_statuses(
            trace,
            recording,
            recording_root=recording_root,
        ),
    )
    mainline = build_preproposal_mainline(
        recording,
        trace,
        structure,
        products,
        evidence,
        applicability,
        recording_root=recording_root,
        run_id=args.run_id,
        organization=str(getattr(args, "evidence_organization", "association")),
    )
    artifacts = {
        "recording_bundle.json": recording.model_dump(mode="json"),
        "ui_api_trace.json": trace.model_dump(mode="json"),
        "observational_api_structure.json": structure.model_dump(mode="json"),
        "evidence_bundle.json": evidence.model_dump(mode="json"),
        "producer_applicability.json": applicability.model_dump(mode="json"),
        "producer_partition_summary.json": producer_partition,
        "discovery_candidate_audit.json": mainline.discovery_audit.model_dump(mode="json"),
        "observed_api_catalog.json": mainline.catalog.model_dump(mode="json"),
        "observed_value_flow_set.json": mainline.value_flows.model_dump(mode="json"),
        "dependency_graph.json": mainline.dependency_graph.model_dump(mode="json"),
        "binding_opportunity_set.json": mainline.binding_opportunities.model_dump(mode="json"),
        "preproposal_evidence_package.json": mainline.package.model_dump(mode="json"),
        "proposal_evidence_view.json": mainline.view.model_dump(mode="json"),
        "rendered_candidate_input.json": mainline.rendered_input.model_dump(mode="json"),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        _write_json(output_root / name, value)
    return {
        "schema_version": "uisemtest-offline-build-report-v1",
        "status": "pass",
        "output_root": str(output_root),
        "artifacts": sorted(artifacts),
        "counts": {
            "events": trace.event_count,
            "admitted_requests": trace.admitted_request_count,
            "automatic_bindings": trace.automatic_binding_count,
            "review_required": trace.review_required_count,
            "stage2_operations": structure.stage2_operation_count,
            "stage2_5_records": structure.stage2_5_record_count,
            "stage2_5_executed": mainline.discovery_audit.executed_count,
            "stage2_5_admitted": mainline.discovery_audit.admitted_count,
            "stage2_5_rejected": mainline.discovery_audit.rejected_count,
            "stage2_5_not_executed": mainline.discovery_audit.not_executed_count,
            "stage3_operations": structure.stage3_operation_count,
            "observed_catalog_operations": mainline.catalog.operation_count,
            "producer_universe": applicability.universe_count,
            "producer_available": applicability.available_count,
            "producer_unsupported": applicability.unsupported_count,
            "auth_session_producers": producer_partition["summary"]["auth_session"],
            "observed_value_flow_occurrences": mainline.value_flows.occurrence_count,
            "dependency_edges": mainline.dependency_graph.edge_count,
            "binding_opportunities": mainline.binding_opportunities.opportunity_count,
        },
        "channel_states": {
            key: {"status": value.status, "reason": value.reason, "records": len(value.records)}
            for key, value in evidence.channels.items()
        },
        "scientific_input_version": mainline.rendered_input.scientific_input_version,
        "rendered_candidate_input_sha256": mainline.rendered_input.rendered_sha256,
        "provider_llm_calls": 0,
        "live_target_browser_server_docker_reset_runs": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uisemtest",
        description="Canonical current UISemTest method pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from cli import configure_record_parser

    record = subparsers.add_parser("record", help="record a Stage 1 session")
    configure_record_parser(record)

    run = subparsers.add_parser(
        "run",
        help="run the canonical current business and auth/session strata",
    )
    run.add_argument("--profile", type=Path)
    run.add_argument("--adapter", type=Path, required=True)
    run.add_argument(
        "--suite",
        type=Path,
        help="serially run every independently recorded case in one suite manifest",
    )
    run.add_argument("--recording-root", type=Path)
    run.add_argument(
        "--frozen-m10-source",
        type=Path,
        help="continue M11a-M14 from one validated, completed M1-M10 source",
    )
    run.add_argument(
        "--frozen-m10-completion-sha256",
        help="prebound raw SHA-256 of the frozen M10 completion",
    )
    run.add_argument(
        "--proposal-plan",
        type=Path,
        help="fixture or sealed-response replay qualification plan",
    )
    run.add_argument(
        "--provider-policy",
        type=Path,
        help="recommended: derive a business plan from the typed producer partition",
    )
    run.add_argument(
        "--provider",
        choices=(
            "fixture",
            "openai_compatible",
            "codex_cli",
            "sealed_response_replay",
        ),
    )
    run.add_argument(
        "--output-level",
        choices=("paper", "debug", "forensic"),
        default="paper",
        help="canonical run artifact publication level (default: paper)",
    )
    run.add_argument(
        "--probe-budget",
        type=int,
        default=32,
        help="maximum Stage2.5 candidates selected before any active HTTP",
    )
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument(
        "--resume-incomplete-m10",
        action="store_true",
        help="strictly resume the incomplete M10 already under --output-root",
    )
    run.add_argument(
        "--provider-concurrency",
        type=int,
        default=12,
        help="runtime-only maximum concurrent calls within one M10 provider stage",
    )
    run.add_argument(
        "--m10-samples",
        type=int,
        default=1,
        help="number of complete independent M10 proposal rounds (formal default: 1)",
    )
    run.add_argument(
        "--m10-sample-mode",
        choices=("independent", "union"),
        default="union",
        help="calibrate every round independently or calibrate their canonical union",
    )
    run.add_argument(
        "--evidence-organization",
        choices=("association", "temporal", "flat"),
        default="association",
        help="RQ3 ablation: 'temporal' hides every explicit association structure; 'flat' also drops action grouping, neighborhoods, page-change rows and negative facts",
    )
    run.add_argument(
        "--stop-after-m9",
        action="store_true",
        help="publish a completed forensic M1-M9 input without executing a provider",
    )
    run.add_argument(
        "--stop-after-m10",
        action="store_true",
        help="publish a completed forensic M1-M10 source without entering M11a",
    )

    doctor = subparsers.add_parser("doctor", help="report the pinned runtime and dependencies")
    doctor.add_argument("--json", action="store_true", help="emit compact machine JSON")

    export_pytest = subparsers.add_parser(
        "export-pytest",
        help="export a frozen M14 retained business suite as readable pytest source",
    )
    export_pytest.add_argument("--run-root", type=Path, required=True)
    export_pytest.add_argument("--output", type=Path, required=True)

    from .maintenance_cli import configure_maintenance_parser

    maintenance = subparsers.add_parser(
        "maintenance",
        help="offline compatibility and boundary utilities",
    )
    configure_maintenance_parser(maintenance)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(raw_argv)
    root = repo_root()
    if args.command == "record":
        from cli import run_record_command

        return run_record_command(args)
    if args.command == "doctor":
        report = doctor_report()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=None if args.json else 2))
        return 0 if report["status"] == "pass" else 2
    if args.command == "export-pytest":
        from .pytest_export import export_pytest_project

        report = export_pytest_project(
            run_root=args.run_root,
            output_root=args.output,
        )
    elif args.command == "run":
        if args.provider_concurrency < 1:
            raise ValueError("provider concurrency must be a positive integer")
        frozen_m10 = args.frozen_m10_source is not None
        suite_run = args.suite is not None
        configs = [
            value
            for value in (args.provider_policy, args.proposal_plan)
            if value is not None
        ]
        if frozen_m10:
            if (
                args.frozen_m10_completion_sha256 is None
                or suite_run
                or args.recording_root is not None
                or configs
                or args.provider is not None
                or args.resume_incomplete_m10
                or args.stop_after_m9
                or args.stop_after_m10
            ):
                raise ValueError(
                    "frozen M10 continuation requires its source and completion "
                    "SHA-256, without recording/provider/resume inputs"
                )
            if args.output_level != "forensic":
                raise ValueError(
                    "frozen M10 continuation requires forensic self-contained output"
                )
            args.proposal_plan = None
        elif (
            args.profile is None and not suite_run
        ):
            raise ValueError("current single-case run requires --profile")
        elif suite_run and args.profile is not None:
            raise ValueError("suite run derives each case profile and forbids --profile")
        elif suite_run and args.stop_after_m10:
            raise ValueError("suite run does not support an M10-only terminal boundary")
        elif (
            args.recording_root is None
            or len(configs) != 1
            or args.provider is None
            or args.frozen_m10_completion_sha256 is not None
        ):
            raise ValueError(
                "current run requires --provider plus exactly one of "
                "--provider-policy or compatibility --proposal-plan"
            )
        else:
            args.proposal_plan = configs[0]
            if args.stop_after_m9 and (
                args.provider != "fixture"
                or args.output_level != "forensic"
                or args.stop_after_m10
                or args.resume_incomplete_m10
            ):
                raise ValueError(
                    "M9 stop boundary requires a fresh forensic fixture-plan run"
                )
            if args.stop_after_m10 and args.output_level != "forensic":
                raise ValueError(
                    "M10 stop boundary requires forensic self-contained output"
                )
        from .current_orchestrator import run_current_v2_pipeline

        if suite_run:
            from .current_suite import run_current_suite

            report = run_current_suite(
                args,
                repo_root=root,
                offline_builder=offline_build,
                single_runner=run_current_v2_pipeline,
            )
        else:
            report = run_current_v2_pipeline(
                args,
                repo_root=root,
                offline_builder=offline_build,
            )
    elif args.command == "maintenance":
        from .maintenance_cli import run_maintenance_command

        report = run_maintenance_command(
            args,
            root=root,
            offline_builder=offline_build,
        )
    else:
        raise ValueError(f"unsupported UISemTest command: {args.command}")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] in {"pass", "complete_empty"} else 2


def _discover_actor_bundles(recording_root: Path) -> dict[str, Path]:
    result_path = recording_root / "recording_workflow_result.json"
    if not result_path.is_file():
        raise ValueError("recording root lacks recording_workflow_result.json")
    result = _read_json(result_path)
    from common.contracts import validate_artifact

    validate_artifact("recording_workflow_result.schema.json", result)
    if result["status"] != "completed":
        raise ValueError("current M2 accepts only a completed recording workflow")
    bundles: dict[str, Path] = {}
    for actor in result["actor_bundles"]:
        actor_id = str(actor["actor_id"])
        manifest = (recording_root / str(actor["manifest_ref"])).resolve(strict=True)
        try:
            manifest.relative_to(recording_root.resolve())
        except ValueError as exc:
            raise ValueError("workflow actor manifest escapes recording root") from exc
        bundle = manifest.parent
        if actor_id in bundles:
            raise ValueError(f"recording root contains multiple bundles for actor: {actor_id}")
        value = _read_json(manifest)
        if str(value["session"]["actor_id"]) != actor_id:
            raise ValueError("workflow result actor differs from session manifest")
        if str(value["metadata"]["run_id"]) != str(actor["run_id"]):
            raise ValueError("workflow result run ID differs from session manifest")
        if str(value["session"]["workflow_id"]) != str(result["workflow_id"]):
            raise ValueError("actor bundle workflow ID differs from workflow result")
        if str(value["session"]["reset_epoch"]) != str(result["reset_epoch"]["record_id"]):
            raise ValueError("actor bundle reset epoch differs from workflow result")
        bundles[actor_id] = bundle
    return bundles


def _profile_url_normalizer(profile: Mapping[str, Any]) -> Callable[[str], str] | None:
    rule = profile.get("offline_url_rewrite")
    if rule is None:
        return None
    if not isinstance(rule, dict) or not isinstance(rule.get("pattern"), str) or not isinstance(rule.get("replacement"), str):
        raise ValueError("offline_url_rewrite requires pattern and replacement strings")
    pattern = re.compile(rule["pattern"])
    replacement = rule["replacement"]
    return lambda value: pattern.sub(replacement, str(value))


def _session_endpoints(profile: AppProfile) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for actor_id in ["default", *(actor.actor_id for actor in profile.actors)]:
        endpoint = actor_session_initialization_endpoint(profile, actor_id)
        if endpoint is not None:
            result[actor_id] = endpoint
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
