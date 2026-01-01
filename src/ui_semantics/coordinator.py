"""Production UI-semantics coordinator: propose, verify, and persist typed audits."""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from common.contracts import REPO_ROOT, make_envelope, validate_artifact
from common.oas_discovery import is_execution_ready
from stage0_launch.profile import AppProfile
from stage6_ground.ui_semantic_replay import SessionBundleReplayAdapter

from .assertions import lint_assertion_candidates
from .constraints import classify_constraint_result
from .pipeline import (
    UiSemanticsConfig,
    validate_constraint_audit_invariants,
    validate_evidence_invariants,
    validate_semantic_audit_invariants,
)
from .proposers import (
    ProposalBatch,
    propose_assertion_transfer,
    propose_constraint_inputs,
    propose_semantic_edges,
    propose_ui_diff_assertions,
)
from .providers import ProposalProvider
from .semantic_edges import DeterministicTwoArmVerifier, prepare_semantic_candidate, verify_semantic_candidate


@dataclass(frozen=True)
class PromptSpec:
    rendered: str
    template: str


@dataclass(frozen=True)
class UiSemanticsRunResult:
    run_dir: Path
    semantic_edge_audit: dict[str, Any] | None
    assertion_audit: dict[str, Any] | None
    constraint_input_audit: dict[str, Any] | None


def run_ui_semantics(
    *,
    config: UiSemanticsConfig,
    ui_trace: dict[str, Any],
    augmented_oas: dict[str, Any],
    profile: AppProfile,
    evidence_by_channel: Mapping[str, dict[str, Any]],
    prompts: Mapping[str, PromptSpec],
    provider: ProposalProvider,
    test_blueprints: dict[str, Any] | None = None,
    artifacts_root: str | Path | None = None,
    replay_adapter: SessionBundleReplayAdapter | None = None,
) -> UiSemanticsRunResult:
    """Run enabled proposal channels; the provider never makes admission decisions."""
    validate_artifact("ui_trace.schema.json", ui_trace)
    validate_artifact("augmented_oas.schema.json", augmented_oas)
    if not config.enabled or not config.llm_enabled:
        raise ValueError("run_ui_semantics requires enabled=true and llm_enabled=true")
    for channel, enabled in config.channels.items():
        if not enabled:
            continue
        evidence = evidence_by_channel.get(channel)
        if evidence is None or prompts.get(channel) is None:
            raise ValueError(f"enabled UI semantics channel lacks evidence or prompt: {channel}")
        validate_artifact("ui_semantics_evidence.schema.json", evidence)
        validate_evidence_invariants(evidence)
        if evidence["channel"] != channel:
            raise ValueError(f"evidence channel mismatch: expected {channel}, got {evidence['channel']}")
    if config.channels["ui_constraints"]:
        if test_blueprints is None:
            raise ValueError("ui_constraints channel requires pre-registered test_blueprints")
        validate_artifact("test_blueprints.schema.json", test_blueprints)

    run_id = _run_id()
    root = Path(artifacts_root) if artifacts_root is not None else REPO_ROOT / "artifacts"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    adapter = replay_adapter or SessionBundleReplayAdapter(ui_trace, profile)

    semantic_audit = _run_semantic_channel(config, ui_trace, evidence_by_channel, prompts, provider, adapter, run_id)
    assertion_audit = _run_assertion_channels(config, evidence_by_channel, prompts, provider, run_id)
    constraint_audit = _run_constraint_channel(
        config,
        ui_trace,
        evidence_by_channel,
        prompts,
        provider,
        adapter,
        run_id,
        augmented_oas,
        test_blueprints,
    )
    for name, document in (
        ("semantic_edge_audit.json", semantic_audit),
        ("assertion_audit.json", assertion_audit),
        ("constraint_input_audit.json", constraint_audit),
    ):
        if document is not None:
            _write_json(run_dir / name, document)
    return UiSemanticsRunResult(run_dir, semantic_audit, assertion_audit, constraint_audit)


def _run_semantic_channel(config, ui_trace, evidence_by_channel, prompts, provider, adapter, run_id):
    if not config.channels["semantic_edges"]:
        return None
    evidence = evidence_by_channel["semantic_edges"]
    batch = _invoke(propose_semantic_edges, provider, prompts["semantic_edges"], evidence, f"{run_id}-semantic")
    verifier = DeterministicTwoArmVerifier(adapter)
    normalization_trace = adapter.normalization_trace()
    candidates = []
    for index, raw in enumerate(batch.items, start=1):
        candidate_id = str(raw.get("candidate_id") or raw.get("id") or f"semantic-{index:04d}")
        prepared = prepare_semantic_candidate(raw, trace=normalization_trace, improved=True)
        if prepared.candidate is None:
            candidates.append(_malformed_candidate(candidate_id, batch.proposal_run["proposal_run_id"], raw, prepared.reason))
            continue
        decision = verify_semantic_candidate(prepared, verifier)
        normalized = copy.deepcopy(decision.candidate)
        record = {
            "candidate_record_version": "v2",
            "candidate_shape": "well_formed",
            "candidate_id": candidate_id,
            "proposal_run_id": batch.proposal_run["proposal_run_id"],
            **normalized,
            "semantic_verdict": decision.verdict,
        }
        if decision.verdict == "confirmed":
            record["verification"] = copy.deepcopy(decision.verification)
        elif decision.verdict == "rejected":
            record["rejection_class"] = decision.rejection_class
            record["reason"] = decision.reason or "deterministic verification rejected the candidate"
        else:
            record["reason"] = decision.reason or "deterministic verification was inconclusive"
        candidates.append(record)
    document = {
        "metadata": make_envelope(
            "semantic_edge_audit",
            "stage4",
            f"{run_id}-semantic",
            upstream_refs=[{"artifact_type": "ui_trace", "run_id": ui_trace["metadata"]["run_id"]}],
        ),
        "proposal_runs": [batch.proposal_run],
        "candidates": candidates,
    }
    validate_artifact("semantic_edge_audit.schema.json", document)
    validate_semantic_audit_invariants(document)
    return document


def _run_assertion_channels(config, evidence_by_channel, prompts, provider, run_id):
    definitions = (
        ("ui_diff_assertions", "ui_diff", propose_ui_diff_assertions),
        ("ui_assertion_transfer", "ui_assertion_transfer", propose_assertion_transfer),
    )
    proposal_runs = []
    candidates = []
    for channel, source, function in definitions:
        if not config.channels[channel]:
            continue
        evidence = evidence_by_channel[channel]
        batch = _invoke(function, provider, prompts[channel], evidence, f"{run_id}-{channel}")
        proposal_runs.append(batch.proposal_run)
        refs = _evidence_refs(evidence)
        linted = lint_assertion_candidates(batch.items, source=source, improved=True)
        for item in linted:
            candidate_id = _unique_id(item["candidate_id"], candidates)
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "assertion_source": source,
                    "proposal_run_id": batch.proposal_run["proposal_run_id"],
                    "raw_predicate": item["normalized_predicate"] if item["lint_verdict"] == "pass" else item["raw_predicate"],
                    "lint_verdict": item["lint_verdict"],
                    "lint_reason": item["lint_reason"],
                    "promoted_test_ref": None,
                    "evidence_refs": refs,
                }
            )
    if not proposal_runs:
        return None
    document = {
        "metadata": make_envelope("assertion_audit", "stage5", f"{run_id}-assertions"),
        "proposal_runs": proposal_runs,
        "candidates": candidates,
    }
    validate_artifact("assertion_audit.schema.json", document)
    return document


def _run_constraint_channel(
    config,
    ui_trace,
    evidence_by_channel,
    prompts,
    provider,
    adapter,
    run_id,
    augmented_oas,
    test_blueprints,
):
    if not config.channels["ui_constraints"]:
        return None
    evidence = evidence_by_channel["ui_constraints"]
    batch = _invoke(propose_constraint_inputs, provider, prompts["ui_constraints"], evidence, f"{run_id}-constraints")
    observations = []
    candidates = []
    for index, raw in enumerate(batch.items, start=1):
        candidate_id = str(raw.get("candidate_id") or raw.get("case_id") or f"constraint-{index:04d}")
        try:
            candidate = _normalize_constraint(
                raw,
                evidence,
                candidate_id,
                batch.proposal_run["proposal_run_id"],
                ui_trace=ui_trace,
                augmented_oas=augmented_oas,
                test_blueprints=test_blueprints,
            )
        except (KeyError, TypeError, ValueError) as error:
            candidates.append(_malformed_constraint(candidate_id, batch.proposal_run["proposal_run_id"], raw, str(error)))
            continue
        if candidate["target"]["resolution"] != "resolved":
            candidate["admission"] = {
                "verdict": "rejected_malformed",
                "reason": "deterministic target did not resolve uniquely",
                "baseline_observation_refs": [],
            }
            candidate["execution"] = None
            candidates.append(candidate)
            continue
        try:
            baseline_context, baseline_reset = adapter.reset()
            selected = candidate["target"]["selected"]
            endpoint = _target_endpoint(ui_trace, selected)
            baseline_result = adapter.execute(baseline_context, endpoint)
            baseline_observation = _constraint_observation(
                f"baseline-{candidate_id}", "baseline", endpoint, selected["operation_id"], baseline_result, baseline_reset
            )
            observations.append(baseline_observation)
            if not _accepted(baseline_result):
                candidate["admission"] = {
                    "verdict": "unable",
                    "reason": "valid baseline was not accepted",
                    "baseline_observation_refs": [],
                }
                candidate["execution"] = None
                candidates.append(candidate)
                continue
            variant_context, variant_reset = adapter.reset()
            value = _replacement_value(candidate["replacement"], raw)
            variant_result = adapter.execute_assignment(
                variant_context,
                endpoint,
                location=selected["location"],
                field=selected["field"],
                value=value,
            )
            variant_observation = _constraint_observation(
                f"variant-{candidate_id}", "variant", endpoint, selected["operation_id"], variant_result, variant_reset
            )
            observations.append(variant_observation)
            candidate["admission"] = {
                "verdict": "ready",
                "reason": None,
                "baseline_observation_refs": [_audit_ref(f"{run_id}-constraints", baseline_observation["record_id"])],
            }
            if candidate["expected_ui_acceptance"] is None:
                candidate["execution"] = {
                    "classification": "unable",
                    "divergence_direction": None,
                    "reason": "expected UI acceptance is unknown",
                    "variant_observation_refs": [],
                }
            else:
                classification = classify_constraint_result(
                    ui_declared_accepts=candidate["expected_ui_acceptance"],
                    backend_outcome="accepted" if _accepted(variant_result) else "rejected",
                )
                candidate["execution"] = {
                    **classification,
                    "reason": None,
                    "variant_observation_refs": [_audit_ref(f"{run_id}-constraints", variant_observation["record_id"])],
                }
        except Exception as error:
            candidate["admission"] = {
                "verdict": "unable",
                "reason": f"live constraint execution failed: {type(error).__name__}",
                "baseline_observation_refs": [],
            }
            candidate["execution"] = None
        candidates.append(candidate)
    document = {
        "metadata": make_envelope("constraint_input_audit", "stage5", f"{run_id}-constraints"),
        "proposal_runs": [batch.proposal_run],
        "observations": observations,
        "candidates": candidates,
    }
    validate_artifact("constraint_input_audit.schema.json", document)
    validate_constraint_audit_invariants(document, evidence_artifacts=[evidence])
    return document


def _normalize_constraint(
    raw,
    evidence,
    candidate_id,
    proposal_run_id,
    *,
    ui_trace,
    augmented_oas,
    test_blueprints,
):
    form_id = str(raw["form_id"])
    field_id = str(raw["field"])
    record = next(item for item in evidence["records"] if item["record_id"] == form_id)
    field = next(item for item in record["fields"] if item["field_id"] == field_id)
    replacement = copy.deepcopy(raw["replacement"])
    constraint_refs = list(raw.get("constraint_refs") or [field_id])
    target = _constraint_target(field["target"])
    _validate_constraint_target(target, field["target"], ui_trace, augmented_oas, test_blueprints)
    candidate = {
        "candidate_record_version": "v2",
        "candidate_shape": "well_formed",
        "candidate_id": candidate_id,
        "proposal_run_id": proposal_run_id,
        "form_id": form_id,
        "field": field_id,
        "constraint_refs": constraint_refs,
        "target": target,
        "case_kind": raw["case_kind"],
        "replacement": replacement,
        "expected_ui_acceptance": raw.get("expected_ui_acceptance"),
        "admission": {"verdict": "rejected_malformed", "reason": "not executed", "baseline_observation_refs": []},
        "execution": None,
        "evidence_refs": [
            {
                "artifact_type": "ui_semantics_evidence",
                "run_id": evidence["metadata"]["run_id"],
                "record_id": record["record_id"],
            }
        ],
    }
    return candidate


def _constraint_target(target):
    if target["resolution"] != "resolved":
        return copy.deepcopy(target)
    selected = target["selected"]
    return {
        "resolution": "resolved",
        "selected": {
            "request_ref": copy.deepcopy(selected["target_request_ref"]),
            "operation_id": selected["target_operation_id"],
            "test_id": selected["target_blueprint_ref"]["record_id"],
            "step_id": selected["target_step_id"],
            "location": selected["assignment_location"],
            "field": selected["assignment_field"],
        },
    }


def _validate_constraint_target(target, evidence_target, ui_trace, augmented_oas, test_blueprints):
    if target["resolution"] != "resolved":
        return
    selected = target["selected"]
    original = evidence_target["selected"]
    if original["target_request_ref"]["run_id"] != ui_trace["metadata"]["run_id"]:
        raise ValueError("constraint target request ref does not point to the supplied ui_trace")
    request = next(
        (item for item in ui_trace["api_requests"] if item["request_ref"] == selected["request_ref"]["record_id"]),
        None,
    )
    if request is None or request["operation_id"] != selected["operation_id"]:
        raise ValueError("constraint target request and operation do not agree")
    operations = {
        operation["operationId"]
        for path_item in augmented_oas.get("paths", {}).values()
        for operation in path_item.values()
        if isinstance(operation, dict) and operation.get("operationId") and is_execution_ready(operation)
    }
    if selected["operation_id"] not in operations:
        raise ValueError("constraint target operation is not execution-ready in augmented OAS")
    blueprint_ref = original["target_blueprint_ref"]
    if blueprint_ref["run_id"] != test_blueprints["metadata"]["run_id"]:
        raise ValueError("constraint target blueprint ref points to another artifact")
    blueprint = next(
        (item for item in test_blueprints["blueprints"] if item["test_id"] == selected["test_id"]),
        None,
    )
    if blueprint is None:
        raise ValueError("constraint target blueprint does not exist")
    steps = {item["step_id"]: item for item in blueprint["setup_steps"] + blueprint["action_steps"]}
    step = steps.get(selected["step_id"])
    if step is None or step["operation_id"] != selected["operation_id"]:
        raise ValueError("constraint target blueprint step does not match its operation")


def _malformed_candidate(candidate_id, proposal_run_id, raw, reason):
    return {
        "candidate_record_version": "v2",
        "candidate_shape": "malformed",
        "candidate_id": candidate_id,
        "proposal_run_id": proposal_run_id,
        "semantic_verdict": "rejected",
        "rejection_class": "rejected_malformed",
        "reason": reason or "semantic candidate was malformed",
        "raw_proposal": copy.deepcopy(raw),
        "raw_proposal_sha256": _sha256(raw),
    }


def _malformed_constraint(candidate_id, proposal_run_id, raw, reason):
    return {
        "candidate_record_version": "v2",
        "candidate_shape": "malformed",
        "candidate_id": candidate_id,
        "proposal_run_id": proposal_run_id,
        "admission": {"verdict": "rejected_malformed", "reason": reason, "baseline_observation_refs": []},
        "raw_proposal": copy.deepcopy(raw),
        "raw_proposal_sha256": _sha256(raw),
    }


def _invoke(function, provider, prompt, evidence, proposal_run_id) -> ProposalBatch:
    return function(
        provider,
        prompt=prompt.rendered,
        prompt_template=prompt.template,
        evidence=evidence,
        evidence_frozen_at=evidence["metadata"]["created_at"],
        proposal_run_id=proposal_run_id,
    )


def _evidence_refs(evidence):
    return [
        {
            "artifact_type": "ui_semantics_evidence",
            "run_id": evidence["metadata"]["run_id"],
            "record_id": record["record_id"],
        }
        for record in evidence["records"]
    ]


def _target_endpoint(ui_trace, selected):
    request_ref = selected["request_ref"]["record_id"]
    request = next(item for item in ui_trace["api_requests"] if item["request_ref"] == request_ref)
    return {"actor_id": request["actor_id"], "request_ref": request_ref}


def _constraint_observation(record_id, phase, endpoint, operation_id, result, reset_ref):
    return {
        "record_id": record_id,
        "phase": phase,
        "actor_id": endpoint["actor_id"],
        "operation_id": operation_id,
        "status": result.get("status"),
        "body_digest": _sha256(result.get("body")) if "body" in result else None,
        "reset_fingerprint_ref": copy.deepcopy(reset_ref),
        "environment_error": None,
    }


def _replacement_value(replacement, raw):
    kind = replacement["kind"]
    if kind == "literal":
        return replacement["value"]
    if kind == "string_length":
        return replacement["char"] * replacement["length"]
    if kind == "null_value":
        return None
    if kind == "numeric_boundary":
        boundary = raw.get(replacement["boundary"])
        if not isinstance(boundary, (int, float)):
            raise ValueError("numeric boundary replacement lacks its declared boundary value")
        return boundary + replacement["offset"]
    if kind == "baseline_ref":
        values = raw.get("baseline_values") or {}
        if replacement["field"] not in values:
            raise ValueError("baseline_ref replacement lacks a baseline value")
        return values[replacement["field"]]
    raise ValueError(f"unsupported replacement kind: {kind}")


def _audit_ref(run_id, record_id):
    return {"artifact_type": "constraint_input_audit", "run_id": run_id, "record_id": record_id}


def _accepted(result):
    return isinstance(result.get("status"), int) and 200 <= result["status"] < 400


def _unique_id(candidate_id, candidates):
    used = {item["candidate_id"] for item in candidates}
    if candidate_id not in used:
        return candidate_id
    index = 2
    while f"{candidate_id}-{index}" in used:
        index += 1
    return f"{candidate_id}-{index}"


def _sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _run_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"rui-{stamp}-{secrets.token_hex(2)}"


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n")
