"""Offline-only RWA acceptance replay for the pre-proposal v2 mainline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .eval_replay import (
    RWA_BUNDLES,
    RWA_RECORDING_ROOT,
    RWA_TEMPLATE,
    RWA_TRANSFER,
    RWA_TRANSFER_POPULATION,
    _absolute_paths,
    legacy_render_candidate_input,
)
from .offline_pipeline import (
    build_evidence_bundle,
    build_observational_structure,
    build_trace,
    materialize_semantic,
    producer_applicability,
    recording_bundle,
    sha256_file,
)
from .preproposal import CHANGE_REASON, PreProposalArtifacts, build_preproposal_mainline
from .route_s import canonical_sha256
from .v2_template import (
    CANONICAL_V2_TEMPLATE_REF,
    CANONICAL_V2_TEMPLATE_REVISION,
    canonical_v2_template_bytes,
    canonical_v2_template_sha256,
)


OUTPUT_ROOT = Path("eval/ui_semantics/preproposal-evidence-mainline-v2-20260723")
HISTORICAL_HARDENED_OUTPUT_ROOT = Path(
    "eval/ui_semantics/preproposal-hardened-v2-freeze-20260723/rwa"
)
HARDENED_OUTPUT_ROOT = Path(
    "eval/ui_semantics/preproposal-current-v2-freeze-20260723/rwa"
)
LEGACY_PROMPT_SHA256 = "dd13a112c7668aa2a54de5587765d7b4d373c208f14420deb09b9ff09938ed3c"
RWA_SELECTION_SHA256 = "eb14fe956395a02c4c8381d28a06ba676d8c96df7faeb5ee7bb521e21b1efc34"
RWA_POPULATION_SHA256 = "ddb9a0819ceec1c8a787f117a748d8d3b5ce21a5b29d461ea86ba3ae5d414f6c"
RUN_ID = "rwa-preproposal-evidence-mainline-v2"


def build_rwa_preproposal_v2(repo_root: Path, *, run_id: str = RUN_ID) -> dict[str, Any]:
    recording_root = repo_root / RWA_RECORDING_ROOT
    recording = recording_bundle(
        _absolute_paths(repo_root, RWA_BUNDLES),
        recording_id=f"{run_id}-recording",
        recording_root=recording_root,
    )
    trace = build_trace(
        recording,
        recording_root=recording_root,
        trace_id=f"{run_id}-trace",
    )
    structure, products = build_observational_structure(
        recording,
        recording_root=recording_root,
        structure_id=f"{run_id}-observational",
    )
    selection_bytes = (repo_root / RWA_TRANSFER).read_bytes()
    population_bytes = (repo_root / RWA_TRANSFER_POPULATION).read_bytes()
    evidence, documents = build_evidence_bundle(
        trace,
        recording,
        recording_root=recording_root,
        evidence_id=f"{run_id}-evidence",
        transfer_selection_bytes=selection_bytes,
        transfer_population_bytes=population_bytes,
    )
    applicability = producer_applicability(
        trace,
        recording,
        recording_root=recording_root,
        applicability_id=f"{run_id}-producer-applicability",
    )
    template_path = repo_root / RWA_TEMPLATE
    artifacts = build_preproposal_mainline(
        recording,
        trace,
        structure,
        products,
        evidence,
        applicability,
        recording_root=recording_root,
        run_id=run_id,
    )
    legacy_recording = recording_bundle(
        _absolute_paths(repo_root, RWA_BUNDLES),
        recording_id="rwa-r6-1-formal-attempt-01",
        recording_root=recording_root,
    )
    legacy_trace = build_trace(
        legacy_recording,
        recording_root=recording_root,
        trace_id="rwa-e1r6-formal-attempt-01",
    )
    _legacy_evidence, legacy_documents = build_evidence_bundle(
        legacy_trace,
        legacy_recording,
        recording_root=recording_root,
        evidence_id="rwa-r6-3-equivalence",
        transfer_selection_bytes=selection_bytes,
        transfer_population_bytes=population_bytes,
    )
    legacy_applicability = producer_applicability(
        legacy_trace,
        legacy_recording,
        recording_root=recording_root,
        applicability_id="rwa-r6-3-producer-universe",
    )
    legacy = legacy_render_candidate_input(
        template=template_path.read_text(encoding="utf-8"),
        material=materialize_semantic(
            legacy_trace,
            legacy_recording,
            recording_root,
            legacy_documents["semantic"],
        ),
        applicability=legacy_applicability,
    )
    return {
        "recording": recording,
        "trace": trace,
        "structure": structure,
        "products": products,
        "evidence": evidence,
        "evidence_documents": documents,
        "applicability": applicability,
        "artifacts": artifacts,
        "legacy": legacy,
    }


def write_rwa_preproposal_v2_reports(repo_root: Path, output_root: Path) -> dict[str, Any]:
    first = build_rwa_preproposal_v2(repo_root)
    second = build_rwa_preproposal_v2(repo_root)
    first_hashes = _determinism_hashes(first)
    second_hashes = _determinism_hashes(second)
    artifacts: PreProposalArtifacts = first["artifacts"]
    trace = first["trace"]
    structure = first["structure"]
    applicability = first["applicability"]
    legacy = first["legacy"]
    audit = artifacts.discovery_audit
    graph = artifacts.dependency_graph
    flows = artifacts.value_flows

    witness_actors = sorted({
        item.producer_actor_id
        for item in flows.flows
        if item.producer_entry_index == 16
        and item.consumer_entry_index == 18
        and item.from_field == "$.data.listBankAccount[0].userId"
        and item.to_field == "$.variables.userId"
    })
    checks = {
        "deterministic_double_build_exact": first_hashes == second_hashes,
        "trace_166_147_63_6": (
            trace.event_count,
            trace.admitted_request_count,
            trace.automatic_binding_count,
            trace.review_required_count,
        ) == (166, 147, 63, 6),
        "stage2_stage2_5_stage3_15_622_15": (
            structure.stage2_operation_count,
            structure.stage2_5_record_count,
            structure.stage3_operation_count,
        ) == (15, 622, 15),
        "stage2_5_all_non_evidence": (
            audit.planned_count,
            audit.executed_count,
            audit.admitted_count,
            audit.not_executed_count,
        ) == (622, 0, 0, 622),
        "stage2_5_kind_partition": audit.kind_counts
        == {"intermediate": 2, "operation": 76, "response": 544},
        "exact_request_level_flows_2022": flows.occurrence_count == 2022,
        "graph_38_edges_332_evidence": (
            graph.edge_count,
            graph.evidence_channel_count,
            graph.observed_flow_count,
        ) == (38, 332, 2022),
        "opportunity_closure_2022": artifacts.binding_opportunities.support_reference_count == 2022,
        "compact_trace_166_147_63_6": (
            len(artifacts.view.ui_actions),
            len(artifacts.view.api_requests),
            len(artifacts.view.automatic_bindings),
            len(artifacts.view.binding_reviews),
        ) == (166, 147, 63, 6),
        "compact_request_body_shape_partitions_closed": all(
            projection["shape_visible_count"] + projection["shape_omitted_count"]
            == projection["shape_total_count"]
            for request in artifacts.view.api_requests
            for projection in (request["request_body_shape"], request["response_body_shape"])
        ),
        "compact_producer_universe_complete": (
            len(artifacts.view.producer_applicability_rows),
            len(artifacts.view.producer_setup_domains),
        ) == (36, 36),
        "two_actor_entry16_entry18_witness": witness_actors == ["receiver", "sender"],
        "producer_universe_preserved": (
            applicability.universe_count,
            applicability.available_count,
            applicability.unsupported_count,
        ) == (36, 36, 0),
        "legacy_projection_exact": legacy["rendered_sha256"] == LEGACY_PROMPT_SHA256,
        "legacy_projection_noneligible": legacy["legacy_fixture_only"] and not legacy["eligible_for_new_run"],
        "canonical_v2_prompt_changed_expected": artifacts.rendered_input.rendered_sha256 != LEGACY_PROMPT_SHA256,
        "package_zero_new_results": (
            artifacts.package.new_candidate_count,
            artifacts.package.new_provider_call_count,
            artifacts.package.new_route_s_result_count,
            artifacts.package.new_test_result_count,
        ) == (0, 0, 0, 0),
    }

    output_root.mkdir(parents=True, exist_ok=True)
    package_path = output_root / "preproposal_evidence_package.json"
    view_path = output_root / "proposal_evidence_view.json"
    rendered_path = output_root / "rendered_candidate_input.json"
    _write_json(package_path, artifacts.package.model_dump(mode="json"))
    _write_json(view_path, artifacts.view.model_dump(mode="json"))
    _write_json(rendered_path, artifacts.rendered_input.model_dump(mode="json"))
    summary = {
        "schema_version": "uisemtest-preproposal-mainline-v2-integration-summary-v1",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "counts": {
            "trace_events": trace.event_count,
            "admitted_requests": trace.admitted_request_count,
            "automatic_bindings": trace.automatic_binding_count,
            "review_required": trace.review_required_count,
            "stage2_operations": structure.stage2_operation_count,
            "stage2_5_planned": audit.planned_count,
            "stage2_5_executed": audit.executed_count,
            "stage3_operations": structure.stage3_operation_count,
            "observed_value_flow_occurrences": flows.occurrence_count,
            "dependency_edges": graph.edge_count,
            "dependency_evidence_channels": graph.evidence_channel_count,
            "binding_opportunities": artifacts.binding_opportunities.opportunity_count,
            "compact_visible": artifacts.view.binding_opportunity_visible_count,
            "compact_omitted": artifacts.view.binding_opportunity_omitted_count,
            "compact_ui_actions": len(artifacts.view.ui_actions),
            "compact_api_requests": len(artifacts.view.api_requests),
        },
        "canonical_artifact_sha256": first_hashes,
        "files": {
            path.name: {"sha256": sha256_file(path)}
            for path in (package_path, view_path, rendered_path)
        },
        "legacy_prompt": {
            "sha256": legacy["rendered_sha256"],
            "legacy_fixture_only": True,
            "eligible_for_new_run": False,
        },
        "canonical_v2_prompt": {
            "sha256": artifacts.rendered_input.rendered_sha256,
            "canonical_v2_prompt_changed": "EXPECTED",
            "change_reason": CHANGE_REASON,
        },
        "candidate_equivalence": "NOT_APPLICABLE",
        "new_scientific_result_count": 0,
        "provider_llm_calls": 0,
        "live_target_browser_server_docker_reset_runs": 0,
        "new_formal_experiment_runs": 0,
    }
    _write_json(output_root / "integration_summary.json", summary)
    return summary


def write_rwa_hardened_v2_input_freeze(
    repo_root: Path,
    output_root: Path,
    *,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    """Freeze the single canonical RWA v2 input without invoking a proposer."""

    first = build_rwa_preproposal_v2(repo_root)
    second = build_rwa_preproposal_v2(repo_root)
    first_hashes = _determinism_hashes(first)
    artifacts: PreProposalArtifacts = first["artifacts"]
    selection_path = repo_root / RWA_TRANSFER
    population_path = repo_root / RWA_TRANSFER_POPULATION
    template_bytes = canonical_v2_template_bytes()
    selection_sha = sha256_file(selection_path)
    population_sha = sha256_file(population_path)
    population = _read_json(population_path)
    transfer_records = artifacts.package.artifact_payloads["evidence_bundle"]["channels"][
        "transfer"
    ]["records"]
    checks = {
        "deterministic_double_build_exact": first_hashes == _determinism_hashes(second),
        "selection_raw_sha_prebound": selection_sha == RWA_SELECTION_SHA256,
        "population_raw_sha_prebound": population_sha == RWA_POPULATION_SHA256,
        "selection_population_trust_root_closed": (
            first["evidence"].transfer_selection_sha256 == selection_sha
            and first["evidence"].transfer_population_sha256 == population_sha
        ),
        "transfer_20_exact_members_of_222": (
            len(transfer_records) == 20 and population.get("candidate_count") == 222
        ),
        "canonical_template_bound": (
            artifacts.rendered_input.template_sha256 == canonical_v2_template_sha256()
        ),
        "auxiliary_semantics_visible_20_39": (
            artifacts.view.evidence_channel_summaries["transfer"]["semantic_projection"]["visible_count"],
            artifacts.view.evidence_channel_summaries["ui_diff"]["semantic_projection"]["visible_count"],
        ) == (20, 39),
        "deterministic_core_counts": (
            first["trace"].event_count,
            first["trace"].admitted_request_count,
            first["trace"].automatic_binding_count,
            first["trace"].review_required_count,
            first["structure"].stage2_operation_count,
            first["structure"].stage2_5_record_count,
            first["structure"].stage3_operation_count,
            artifacts.value_flows.occurrence_count,
            artifacts.dependency_graph.edge_count,
            artifacts.binding_opportunities.opportunity_count,
        ) == (166, 147, 63, 6, 15, 622, 15, 2022, 38, 332),
        "legacy_projection_exact": first["legacy"]["rendered_sha256"] == LEGACY_PROMPT_SHA256,
        "zero_new_scientific_results": (
            artifacts.package.new_candidate_count,
            artifacts.package.new_provider_call_count,
            artifacts.package.new_route_s_result_count,
            artifacts.package.new_test_result_count,
        ) == (0, 0, 0, 0),
    }
    if not all(checks.values()):
        raise ValueError(f"hardened v2 input freeze preconditions failed: {checks}")

    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "package": output_root / "preproposal_evidence_package.json",
        "view": output_root / "proposal_evidence_view.json",
        "rendered": output_root / "rendered_candidate_input.json",
        "template": output_root / "effect_contract_v2.txt",
    }
    occupied = [str(path) for path in paths.values() if path.exists()]
    manifest_path = output_root / "input_freeze_manifest.json"
    if manifest_path.exists():
        occupied.append(str(manifest_path))
    if occupied:
        raise ValueError(f"hardened input freeze refuses to overwrite existing files: {occupied}")
    _write_json(paths["package"], artifacts.package.model_dump(mode="json"))
    _write_json(paths["view"], artifacts.view.model_dump(mode="json"))
    _write_json(paths["rendered"], artifacts.rendered_input.model_dump(mode="json"))
    paths["template"].write_bytes(template_bytes)

    actor_manifests = {
        actor.actor_id: {
            "run_id": actor.run_id,
            "ref": (
                RWA_RECORDING_ROOT / Path(actor.path) / "manifest.json"
            ).as_posix(),
            "sha256": actor.manifest_sha256,
        }
        for actor in first["recording"].actors
    }
    manifest = {
        "schema_version": "uisemtest-current-v2-input-freeze-v2",
        "status": "pass",
        "scientific_input_version": "preproposal-evidence-v2",
        "system": "rwa",
        "run_id": RUN_ID,
        "frozen_at": frozen_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "sources": {
            "recording_bundle": {
                "canonical_sha256": first["recording"].canonical_sha256(),
                "actor_manifests": actor_manifests,
            },
            "transfer_selection": {
                "ref": str(RWA_TRANSFER),
                "file_sha256": selection_sha,
            },
            "transfer_population": {
                "ref": str(RWA_TRANSFER_POPULATION),
                "file_sha256": population_sha,
            },
        },
        "template": {
            "canonical_ref": CANONICAL_V2_TEMPLATE_REF,
            "frozen_copy_ref": paths["template"].name,
            "file_sha256": sha256_file(paths["template"]),
        },
        "template_revision": CANONICAL_V2_TEMPLATE_REVISION,
        "view_revision": "aux-semantic-projection-v1",
        "artifacts": {
            "package": {
                "ref": paths["package"].name,
                "file_sha256": sha256_file(paths["package"]),
                "contract_sha256": artifacts.package.canonical_sha256(),
            },
            "view": {
                "ref": paths["view"].name,
                "file_sha256": sha256_file(paths["view"]),
                "contract_sha256": artifacts.view.canonical_sha256(),
            },
            "rendered": {
                "ref": paths["rendered"].name,
                "file_sha256": sha256_file(paths["rendered"]),
                "contract_sha256": artifacts.rendered_input.canonical_sha256(),
                "rendered_text_sha256": artifacts.rendered_input.rendered_sha256,
            },
        },
        "counts": {
            "trace_events": first["trace"].event_count,
            "admitted_requests": first["trace"].admitted_request_count,
            "automatic_bindings": first["trace"].automatic_binding_count,
            "review_required": first["trace"].review_required_count,
            "stage2_operations": first["structure"].stage2_operation_count,
            "stage2_5_planned": first["structure"].stage2_5_record_count,
            "stage3_operations": first["structure"].stage3_operation_count,
            "observed_value_flow_occurrences": artifacts.value_flows.occurrence_count,
            "dependency_edges": artifacts.dependency_graph.edge_count,
            "binding_opportunities": artifacts.binding_opportunities.opportunity_count,
            "transfer_selection": len(transfer_records),
            "transfer_population": int(population["candidate_count"]),
            "transfer_visible": artifacts.view.evidence_channel_summaries["transfer"]["semantic_projection"]["visible_count"],
            "transfer_omitted": artifacts.view.evidence_channel_summaries["transfer"]["semantic_projection"]["omitted_count"],
            "ui_diff_total": artifacts.view.evidence_channel_summaries["ui_diff"]["semantic_projection"]["total_count"],
            "ui_diff_visible": artifacts.view.evidence_channel_summaries["ui_diff"]["semantic_projection"]["visible_count"],
            "ui_diff_omitted": artifacts.view.evidence_channel_summaries["ui_diff"]["semantic_projection"]["omitted_count"],
        },
        "zero_results": {
            "candidate": 0,
            "provider_call": 0,
            "route_s": 0,
            "test_result": 0,
        },
        "checks": checks,
        "legacy_prompt": {
            "sha256": LEGACY_PROMPT_SHA256,
            "legacy_fixture_only": True,
            "eligible_for_new_run": False,
        },
        "hardened_prompt": {
            "sha256": artifacts.rendered_input.rendered_sha256,
            "expected_change_reasons": [
                "frozen_transfer_population_trust_root_added",
                "strict_oneof_template_parser_alignment",
                "transfer_and_ui_diff_semantic_projections_added",
            ],
            "new_scientific_result_count": 0,
        },
        "supersedes_for_new_call": {
            "ref": str(HISTORICAL_HARDENED_OUTPUT_ROOT),
            "manifest_file_sha256": "e36a490f7b8b2338a39603d3bafaeb7f8bb9031824e081cc8d3d2ecb529eee7c",
            "rendered_text_sha256": "69659c4bc12c181c3eb2924f2d98325544eda44d84eb10d916ac30327a858b23",
            "status": "superseded_for_new_call",
            "reason": "template_parser_alignment_and_auxiliary_semantic_visibility",
        },
    }
    _write_json(manifest_path, manifest)
    return manifest


def _determinism_hashes(result: dict[str, Any]) -> dict[str, str]:
    artifacts: PreProposalArtifacts = result["artifacts"]
    products = result["products"]
    values = {
        "recording_bundle": result["recording"].canonical_sha256(),
        "ui_api_trace": result["trace"].canonical_sha256(),
        "observational_api_structure": result["structure"].canonical_sha256(),
        "stage2_initial": canonical_sha256(products["initial_structure"]),
        "stage2_5_audit": canonical_sha256(products["audit_only_probe_results"]),
        "stage3_augmented": canonical_sha256(products["augmented_structure"]),
        "evidence_bundle": result["evidence"].canonical_sha256(),
        "producer_applicability": result["applicability"].canonical_sha256(),
        "observed_api_catalog": artifacts.catalog.canonical_sha256(),
        "discovery_candidate_audit": artifacts.discovery_audit.canonical_sha256(),
        "observed_value_flow_set": artifacts.value_flows.canonical_sha256(),
        "dependency_graph": artifacts.dependency_graph.canonical_sha256(),
        "binding_opportunity_set": artifacts.binding_opportunities.canonical_sha256(),
        "preproposal_evidence_package": artifacts.package.canonical_sha256(),
        "proposal_evidence_view": artifacts.view.canonical_sha256(),
        "rendered_candidate_input": artifacts.rendered_input.canonical_sha256(),
    }
    for name, document in sorted(result["evidence_documents"].items()):
        values[f"evidence_document_{name}"] = canonical_sha256(document)
    return values


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
