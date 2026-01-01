"""Current Route-S sealing and direct relation-to-test closure."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from .artifact_relocation import attested_sha256
from typing import Any, Iterable, Mapping

from .current_candidate_failure import CandidateLocalFailure
from .m11b_materializer import RouteSPreLiveMaterializedCandidate
from .current_route_s import (
    RouteSCollectedEvidence,
    canonical_json_bytes,
    validate_artifact_manifest_v1,
    validate_artifact_manifest,
    validate_current_route_s_evaluation,
    validate_final_seal_v1,
    validate_final_seal_v2,
    validate_outer_envelope_v5,
    validate_scan_report_v1,
)
from .relation_phase_b import BUSINESS_EVALUATOR, canonical_sha256


@dataclass(frozen=True)
class CurrentRouteSArtifactRecord:
    candidate_id: str
    outcome: str
    material: RouteSPreLiveMaterializedCandidate
    collected: RouteSCollectedEvidence
    envelope: dict[str, Any]
    protocol_result: dict[str, Any]
    source: dict[str, Any]


def persist_current_route_s_result(
    *,
    run_root: Path,
    material: RouteSPreLiveMaterializedCandidate,
    collected: RouteSCollectedEvidence,
    envelope: Mapping[str, Any],
    protocol_result: Mapping[str, Any],
    output_level: str,
) -> CurrentRouteSArtifactRecord:
    """Persist and seal only this run's current evidence/certificate closure."""

    root = run_root.resolve()
    if output_level not in {"paper", "debug", "forensic"}:
        raise ValueError(f"unknown current output level: {output_level!r}")
    value = copy.deepcopy(dict(envelope))
    if output_level != "forensic":
        validate_current_route_s_evaluation(collected.evidence)
        validate_current_route_s_evaluation(value)
        candidate_id = material.candidate_id
        evidence_ref = f"M12/{candidate_id}/execution_evidence.json"
        certificate_ref = f"M12/{candidate_id}/certificate.json"
        evidence_bytes = collected.execution_evidence_bytes
        certificate_bytes = canonical_json_bytes(value)
        if _volatile_sensitive_value_refs(
            material.artifact_bytes, collected.volatile_sensitive_values
        ):
            raise ValueError("persisted M11b material retained volatile sensitive value")
        m12_payloads = {
            **collected.artifact_bytes,
            evidence_ref: evidence_bytes,
            certificate_ref: certificate_bytes,
        }
        findings = _volatile_sensitive_value_refs(
            m12_payloads, collected.volatile_sensitive_values
        )
        if findings:
            raise CandidateLocalFailure(
                "M12", "capture_safety", "volatile_sensitive_material_retained"
            )
        _write_exact(root, evidence_ref, evidence_bytes)
        _write_exact(root, certificate_ref, certificate_bytes)
        outcome = str(value["route_s_certificate"]["outcome"])
        source = {
            "candidate": _memory_file_ref(
                f"M11b/{candidate_id}/candidate.json",
                canonical_json_bytes(material.candidate),
            ),
            "execution_material": _memory_file_ref(
                f"M11b/{candidate_id}/execution_material.json",
                material.execution_material_bytes,
            ),
            "execution_evidence": _memory_file_ref(evidence_ref, evidence_bytes),
            "certificate": _memory_file_ref(certificate_ref, certificate_bytes),
            "normalized_candidate_sha256": material.bound_candidate_sha256,
        }
        return CurrentRouteSArtifactRecord(
            candidate_id=candidate_id,
            outcome=outcome,
            material=material,
            collected=collected,
            envelope=value,
            protocol_result=copy.deepcopy(dict(protocol_result)),
            source=source,
        )

    validate_outer_envelope_v5(value, evidence=collected.evidence)
    candidate_id = material.candidate_id
    evidence_ref = f"M12/{candidate_id}/execution_evidence.json"
    certificate_ref = f"M12/{candidate_id}/certificate.json"
    evidence_bytes = collected.execution_evidence_bytes
    certificate_bytes = canonical_json_bytes(value)
    material_findings = _volatile_sensitive_value_refs(
        material.artifact_bytes,
        collected.volatile_sensitive_values,
    )
    if material_findings:
        raise ValueError("persisted M11b material retained volatile sensitive value")
    m12_findings = _volatile_sensitive_value_refs(
        {
            **collected.artifact_bytes,
            evidence_ref: evidence_bytes,
            certificate_ref: certificate_bytes,
        },
        collected.volatile_sensitive_values,
    )
    if m12_findings:
        m12_prefix = f"M12/{candidate_id}/"
        if any(
            ref in material.artifact_bytes or not ref.startswith(m12_prefix)
            for ref in m12_findings
        ):
            raise ValueError(
                "Route-S volatile sensitive material escaped candidate M12 scope"
            )
        raise CandidateLocalFailure(
            "M12", "capture_safety", "volatile_sensitive_material_retained"
        )
    written: dict[str, bytes] = {}
    for ref, payload in sorted(collected.artifact_bytes.items()):
        if output_level == "forensic" or (
            output_level == "debug" and "raw" in Path(ref).parts
        ):
            _write_exact(root, ref, payload)
        written[ref] = payload

    binding_wrapper_ref = f"M11b/{candidate_id}/execution_binding.wrapper.json"
    pins_wrapper_ref = f"M11b/{candidate_id}/pre_live_binding_pins.wrapper.json"
    m11b_manifest_ref = f"M11b/{candidate_id}/material_manifest.json"
    expected_upstream = {
        binding_wrapper_ref: canonical_json_bytes(material.execution_binding),
    }
    if output_level == "forensic":
        expected_upstream[pins_wrapper_ref] = canonical_json_bytes(
            material.pre_live_binding_pins
        )
    for ref, expected in expected_upstream.items():
        payload = (root / ref).read_bytes()
        if payload != expected:
            raise ValueError("persisted M11b wrapper drifted before M12")
        written[ref] = payload
    if output_level == "forensic":
        m11b_manifest_bytes = (root / m11b_manifest_ref).read_bytes()
        m11b_manifest = json.loads(m11b_manifest_bytes)
        if (
            m11b_manifest.get("candidate_id") != candidate_id
            or m11b_manifest.get("persistence_boundary")
            != "write_reload_validate_before_route_s"
        ):
            raise ValueError("M12 requires a write/reload-validated M11b manifest")
        written[m11b_manifest_ref] = m11b_manifest_bytes

    for ref, payload in (
        (evidence_ref, evidence_bytes),
        (certificate_ref, certificate_bytes),
    ):
        _write_exact(root, ref, payload)
        written[ref] = payload

    pre_scan_ref = collected.evidence["run_attestation"]["pre_render_scan_ref"]
    pre_scan = json.loads(collected.artifact_bytes[pre_scan_ref])
    pre_scope = dict(material.artifact_hashes)
    post_scope = dict(collected.artifact_hashes)
    post_scope[evidence_ref] = hashlib.sha256(evidence_bytes).hexdigest()
    post_scope[certificate_ref] = hashlib.sha256(certificate_bytes).hexdigest()
    post_scan = {
        "schema_version": "ui-semantics-route-s-scan-report-v1",
        "phase": "post_render",
        "status": "pass",
        "scope_refs": sorted(post_scope),
        "scope_hashes": dict(sorted(post_scope.items())),
        "finding_records": [],
        "findings_count": 0,
        "provider_calls": 0,
        "no_feedback": True,
    }
    validate_scan_report_v1(post_scan)
    post_scan_ref = f"M12/{candidate_id}/post_render_scan.json"
    post_scan_bytes = canonical_json_bytes(post_scan)
    if output_level == "forensic":
        _write_exact(root, post_scan_ref, post_scan_bytes)
    written[post_scan_ref] = post_scan_bytes
    final_seal = {
        "schema_version": "ui-semantics-route-s-final-seal-v1",
        "pre_render_scan_sha256": canonical_sha256(pre_scan),
        "post_render_scan_sha256": canonical_sha256(post_scan),
        "execution_evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "certificate_sha256": hashlib.sha256(certificate_bytes).hexdigest(),
        "status": "pass",
        "provider_calls": 0,
    }
    validate_final_seal_v2(
        final_seal,
        pre_scan=pre_scan,
        post_scan=post_scan,
        required_pre_scope=pre_scope,
        required_post_scope=post_scope,
        execution_evidence_bytes=evidence_bytes,
        certificate_bytes=certificate_bytes,
    )
    validate_final_seal_v1(final_seal)
    final_seal_ref = f"M12/{candidate_id}/final_seal.json"
    final_seal_bytes = canonical_json_bytes(final_seal)
    _write_exact(root, final_seal_ref, final_seal_bytes)
    written[final_seal_ref] = final_seal_bytes

    outcome = str(value["route_s_certificate"]["outcome"])
    candidate_result = {
        "schema_version": "uisemtest-current-route-s-candidate-result-v1",
        "candidate_id": candidate_id,
        "attempted": True,
        "outcome": outcome,
        "execution_evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "certificate_sha256": hashlib.sha256(certificate_bytes).hexdigest(),
        "final_seal_sha256": hashlib.sha256(final_seal_bytes).hexdigest(),
        "outcome_source": "route_s_certificate.outcome",
        "outcome_derived_by_current_evaluator": True,
        "adapter_supplied_outcome": False,
    }
    candidate_result_ref = f"M12/{candidate_id}/candidate_result.json"
    candidate_result_bytes = canonical_json_bytes(candidate_result)
    _write_exact(root, candidate_result_ref, candidate_result_bytes)
    written[candidate_result_ref] = candidate_result_bytes
    completion = {
        "schema_version": "uisemtest-current-route-s-candidate-completion-v1",
        "candidate_id": candidate_id,
        "status": "complete",
        "attempted": True,
        "candidate_result_sha256": hashlib.sha256(candidate_result_bytes).hexdigest(),
        "final_seal_sha256": hashlib.sha256(final_seal_bytes).hexdigest(),
        "external_provider_llm_calls": 0,
        "external_network_calls": collected.runtime_counts["external_network_calls"],
        "real_target_runs": collected.runtime_counts["real_target_runs"],
        "real_reset_runs": collected.runtime_counts["real_reset_runs"],
    }
    completion_ref = f"M12/{candidate_id}/candidate_completion.json"
    completion_bytes = canonical_json_bytes(completion)
    _write_exact(root, completion_ref, completion_bytes)
    written[completion_ref] = completion_bytes

    manifest_ref = f"M12/{candidate_id}/artifact_manifest.json"
    if output_level == "forensic":
        manifest_payloads = {
            ref: payload
            for ref, payload in written.items()
            if ref.startswith(f"M11b/{candidate_id}/")
            or ref.startswith(f"M12/{candidate_id}/")
        }
        records = [
            {
                "relative_path": ref,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for ref, payload in sorted(manifest_payloads.items())
        ]
        manifest = {
            "schema_version": "ui-semantics-route-s-artifact-manifest-v1",
            "generated_last": True,
            "files": records,
            "aggregate_sha256": canonical_sha256(records),
        }
        validate_artifact_manifest(manifest, exact_artifacts=manifest_payloads)
        validate_artifact_manifest_v1(manifest)
        _write_exact(root, manifest_ref, canonical_json_bytes(manifest))

    reloaded_evidence_bytes = (root / evidence_ref).read_bytes()
    reloaded_evidence = json.loads(reloaded_evidence_bytes)
    collected = replace(
        collected,
        evidence=reloaded_evidence,
        execution_evidence_bytes=reloaded_evidence_bytes,
    )
    reloaded_envelope = json.loads((root / certificate_ref).read_bytes())
    validate_outer_envelope_v5(reloaded_envelope, evidence=collected.evidence)
    if reloaded_envelope["route_s_certificate"]["outcome"] != outcome:
        raise ValueError("persisted Route-S outcome changed across reload")
    reloaded_pre_scan = (
        json.loads((root / pre_scan_ref).read_bytes())
        if output_level == "forensic"
        else pre_scan
    )
    reloaded_post_scan = (
        json.loads((root / post_scan_ref).read_bytes())
        if output_level == "forensic"
        else post_scan
    )
    validate_scan_report_v1(reloaded_pre_scan)
    validate_scan_report_v1(reloaded_post_scan)
    reloaded_final_seal = json.loads((root / final_seal_ref).read_bytes())
    validate_final_seal_v2(
        reloaded_final_seal,
        pre_scan=reloaded_pre_scan,
        post_scan=reloaded_post_scan,
        required_pre_scope=pre_scope,
        required_post_scope=post_scope,
        execution_evidence_bytes=reloaded_evidence_bytes,
        certificate_bytes=(root / certificate_ref).read_bytes(),
    )
    validate_final_seal_v1(reloaded_final_seal)
    if output_level == "forensic":
        reloaded_manifest = json.loads((root / manifest_ref).read_bytes())
        validate_artifact_manifest_v1(reloaded_manifest)
        reloaded_manifest_payloads = {}
        for row in reloaded_manifest["files"]:
            ref = str(row["relative_path"])
            path = (root / ref).resolve()
            if not path.is_relative_to(root):
                raise ValueError("persisted Route-S manifest ref escapes the run root")
            reloaded_manifest_payloads[ref] = path.read_bytes()
        validate_artifact_manifest(
            reloaded_manifest,
            exact_artifacts=reloaded_manifest_payloads,
        )

    source = {
        "candidate": _file_ref(
            root, root / f"M11b/{candidate_id}/candidate.json"
        ),
        "execution_material": _file_ref(
            root, root / f"M11b/{candidate_id}/execution_material.json"
        ),
        "certificate": _file_ref(root, root / certificate_ref),
        "execution_evidence": _file_ref(root, root / evidence_ref),
        "normalized_candidate_sha256": material.bound_candidate_sha256,
    }
    return CurrentRouteSArtifactRecord(
        candidate_id=candidate_id,
        outcome=outcome,
        material=material,
        collected=collected,
        envelope=reloaded_envelope,
        protocol_result=copy.deepcopy(dict(protocol_result)),
        source=source,
    )


def build_current_relation_closure(
    records: Iterable[CurrentRouteSArtifactRecord],
    *,
    run_plan_id: str,
    route_s_run_report_ref: Mapping[str, str],
    repo_root: Path,
) -> dict[str, Any]:
    """Build the compiler's in-memory input directly from current Route-S."""

    rows = sorted(records, key=lambda item: item.candidate_id)
    derived_outcomes: dict[str, str] = {}
    for item in rows:
        if item.protocol_result.get("protocol_kind") in {"V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"}:
            if (
                item.protocol_result.get("candidate_id") != item.candidate_id
                or item.envelope.get("candidate_id") != item.candidate_id
                or item.envelope.get("protocol_verdict")
                != item.protocol_result.get("protocol_verdict")
                or item.protocol_result.get("v1_legacy_outcome") is not None
            ):
                raise ValueError("current protocol result differs from single-arm certificate")
            derived_outcomes[item.candidate_id] = str(
                item.protocol_result["protocol_verdict"]
            )
            continue
        if item.material.output_level == "forensic":
            validate_outer_envelope_v5(item.envelope, evidence=item.collected.evidence)
        else:
            validate_current_route_s_evaluation(item.collected.evidence)
            validate_current_route_s_evaluation(item.envelope)
        inner_outcome = str(item.envelope["route_s_certificate"]["outcome"])
        if item.outcome != inner_outcome:
            raise ValueError("cached Route-S outcome differs from the certificate")
        if item.envelope["route_s_certificate"]["candidate"]["candidate_id"] != item.candidate_id:
            raise ValueError("Route-S certificate candidate identity mismatch")
        if (
            item.protocol_result.get("candidate_id") != item.candidate_id
            or item.protocol_result.get("protocol_kind") != "V1"
            or item.protocol_result.get("v1_legacy_outcome") != inner_outcome
        ):
            raise ValueError("current protocol result differs from V1 certificate")
        derived_outcomes[item.candidate_id] = inner_outcome
    confirmed = [
        item
        for item in rows
        if item.protocol_result.get("protocol_verdict") == "validated"
    ]
    current_records = []
    for item in confirmed:
        if item.protocol_result["protocol_kind"] in {"V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9"}:
            protocol_kind = str(item.protocol_result["protocol_kind"])
            claim_kind = {
                "V2": "single_state_confirmed",
                "V9": "joint_observation_confirmed",
                "V8": "temporal_observation_confirmed",
            "V3": "metamorphic_confirmed",
                "V4": "workflow_confirmed",
                "V5": "repeated_execution_confirmed",
                "V6": "negative_behavior_confirmed",
                "V7": "actor_relation_confirmed",
            }[protocol_kind]
            plan_key = {
                "V8": "observation_plan", "V9": "observation_plan", "V2": "observation_plan", "V3": "query_plan", "V4": "workflow_plan",
                "V5": "repeated_plan", "V6": "negative_plan", "V7": "actor_plan"
            }[protocol_kind]
            protocol = item.collected.evidence["protocol"]
            runtime_requirements = (
                {
                    step["role"]: _event_requirements(
                        record.get("binding_events") or []
                    )
                    for step, record in zip(
                        item.envelope[plan_key], protocol["observations"] if protocol_kind in {"V2", "V8", "V9"} else protocol["queries"]
                    )
                }
                if protocol_kind in {"V2", "V3", "V8", "V9"}
                else {key: _event_requirements(record.get("binding_events") or []) for key, record in protocol.items() if isinstance(record, Mapping)} if protocol_kind == "V5"
                else {"P": _event_requirements(protocol["producer"].get("binding_events") or [])}
                if protocol_kind == "V6" and item.material.execution_material["protocol_shape"]["negative_kind"] == "rejection"
                else {
                    "P": _event_requirements(protocol["producer"].get("binding_events") or []),
                    "before": _event_requirements(protocol["before"].get("binding_events") or []),
                    "after": _event_requirements(protocol["after"].get("binding_events") or []),
                }
            )
            if protocol_kind in {"V8", "V9"} and "producer" in protocol:
                runtime_requirements["P"] = _event_requirements(protocol["producer"].get("binding_events") or [])
            if protocol_kind == "V8" and "before" in protocol:
                runtime_requirements["before"] = _event_requirements(protocol["before"].get("binding_events") or [])
            current_records.append(
                {
                    "candidate_id": item.candidate_id,
                    "protocol_kind": protocol_kind,
                    "claim_kind": claim_kind,
                    "outcome": "validated",
                    "candidate": copy.deepcopy(item.material.candidate),
                    "projection": {
                        key: copy.deepcopy(value)
                        for key, value in item.material.projection_plan.items()
                        if key not in {"artifact_ref", "artifact_sha256"}
                    },
                    "binding": copy.deepcopy(
                        item.material.execution_binding["payload"]
                    ),
                    "certificate_inner": copy.deepcopy(item.envelope),
                    "protocol_plan": copy.deepcopy(item.envelope[plan_key]),
                    **{key: copy.deepcopy(item.material.execution_material["protocol_shape"][key]) for key in ("workflow_kind", "negative_kind", "repetition_kind", "required_checks", "identity_topology", "joint_observation", "time_requirement") if key in item.material.execution_material["protocol_shape"]},
                    **({key: _event_requirements(protocol[key].get("binding_events") or []) for key in ("inverse", "intermediate")} if protocol_kind == "V4" and "inverse" in protocol else {}),
                    **({key: copy.deepcopy(item.envelope[key]) for key in ("query_scope", "query_transform")} if protocol_kind == "V3" else {}),
                    **({"sampling": copy.deepcopy(item.envelope["sampling"])} if protocol_kind == "V2" else {}),
                    **(
                        {
                            "session_boundary": copy.deepcopy(
                                item.material.execution_material["protocol_shape"][
                                    "session_boundary"
                                ]
                            ),
                            "rejection_detector": copy.deepcopy(
                                item.material.execution_material["protocol_shape"][
                                    "rejection_detector"
                                ]
                            ),
                        }
                        if protocol_kind == "V6"
                        else {}
                    ),
                    "protocol_evidence": {
                        "protocol": copy.deepcopy(protocol),
                        "sessions": copy.deepcopy(item.collected.evidence["sessions"]),
                    },
                    "runtime_binding_requirements": runtime_requirements,
                    "observer_policy": copy.deepcopy(item.material.observer_policy),
                    "settle_policy": copy.deepcopy(item.material.settle_policy),
                    "source": copy.deepcopy(item.source),
                    "record_sha256": canonical_sha256(
                        {
                            "candidate_id": item.candidate_id,
                            "outcome": "validated",
                            "source": item.source,
                        }
                    ),
                }
            )
            continue
        inner = item.envelope["route_s_certificate"]
        if inner["outcome"] != "confirmed":
            raise ValueError("non-confirmed certificate reached current M13")
        attestations = item.envelope["request_binding_attestation"]
        runtime_records = {
            slot: copy.deepcopy(item.collected.evidence["protocol"][slot])
            for slot in ("P", "Ot0", "Ot1")
        }
        current_records.append(
            {
                "candidate_id": item.candidate_id,
                "protocol_kind": "V1",
                "claim_kind": "causal_confirmed",
                "outcome": item.outcome,
                "candidate": copy.deepcopy(inner["candidate"]),
                "projection": {
                    key: copy.deepcopy(value)
                    for key, value in inner["projection_plan"].items()
                    if key not in {"artifact_ref", "artifact_sha256"}
                },
                "binding": copy.deepcopy(item.envelope["execution_binding"]["payload"]),
                "certificate_inner": copy.deepcopy(inner),
                "request_binding_attestation": copy.deepcopy(attestations),
                "runtime_binding_requirements": {
                    slot: _event_requirements(record.get("binding_events") or [])
                    for slot, record in runtime_records.items()
                },
                "observer_policy": copy.deepcopy(item.material.observer_policy),
                "settle_policy": copy.deepcopy(item.material.settle_policy),
                "source": copy.deepcopy(item.source),
                "record_sha256": canonical_sha256(
                    {
                        "candidate_id": item.candidate_id,
                        "outcome": item.outcome,
                        "source": item.source,
                    }
                ),
            }
        )
    confirmed_ids = [item.candidate_id for item in confirmed]
    confirmed_id_set = set(confirmed_ids)
    outcomes = Counter(derived_outcomes.values())
    evaluator_path = repo_root / "src/ui_semantics/current_route_s/core.py"
    empty = not confirmed
    return {
        "schema_version": "certified-relation-input-closure-current-v2",
        "status": (
            "COMPLETE_EMPTY_NO_CONFIRMED_RELATIONS"
            if empty
            else "PASS_CURRENT_CONFIRMED_INPUT_CLOSED"
        ),
        "completion_reason": (
            "no_confirmed_relations" if empty else "confirmed_relations_closed"
        ),
        "run_plan_id": run_plan_id,
        "upstream": {
            "run_report": dict(route_s_run_report_ref),
        },
        "implementation_pins": {
            "business_evaluator": BUSINESS_EVALUATOR,
            "business_evaluator_source": {
                "path": "src/ui_semantics/current_route_s/core.py",
                "sha256": _sha256_file(evaluator_path),
            },
        },
        "confirmed_count": len(confirmed),
        "confirmed_ids": confirmed_ids,
        "confirmed_set_sha256": canonical_sha256(confirmed_ids),
        "rejected_count": len(rows) - len(confirmed),
        "outcomes": dict(sorted(outcomes.items())),
        "confirmed": current_records,
        "rejected": [
            {
                "candidate_id": item.candidate_id,
                "outcome": derived_outcomes[item.candidate_id],
                "protocol_result": copy.deepcopy(item.protocol_result),
            }
            for item in rows
            if item.candidate_id not in confirmed_id_set
        ],
        "historical_result_source_count": 0,
        "provider_llm_calls": 0,
    }


def _volatile_sensitive_value_refs(
    payloads: Mapping[str, bytes],
    sensitive_values: Iterable[str],
) -> tuple[str, ...]:
    secrets = tuple(value for value in sensitive_values if value)
    if not secrets:
        return ()
    findings = []
    for ref, payload in sorted(payloads.items()):
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = payload.decode("utf-8", errors="replace")
        if _contains_sensitive_text(value, secrets):
            findings.append(ref)
    return tuple(findings)


def _contains_sensitive_text(value: Any, secrets: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(secret in value for secret in secrets)
    if isinstance(value, Mapping):
        return any(_contains_sensitive_text(child, secrets) for child in value.values())
    if isinstance(value, list):
        return any(_contains_sensitive_text(child, secrets) for child in value)
    return False


def _event_requirements(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "event",
        "actor_id",
        "creator_actor_id",
        "creator_request_ref",
        "consumer_request_ref",
        "scalar_type",
        "source_id",
        "source_typed_path",
        "target_location",
        "target_typed_path",
    )
    result = []
    for event in events:
        if event.get("event") != "consumer_value_rebound":
            continue
        row = {key: copy.deepcopy(event[key]) for key in keys}
        if "target_group_size" in event:
            row["target_group_size"] = event["target_group_size"]
        result.append(row)
    return result


def _file_ref(root: Path, path: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": _sha256_file(path)}


def _memory_file_ref(path: str, payload: bytes) -> dict[str, str]:
    return {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}


def _write_exact(root: Path, ref: str, payload: bytes) -> None:
    path = (root / ref).resolve()
    if not path.is_relative_to(root):
        raise ValueError("current Route-S artifact ref escapes the run root")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            if ref.startswith("M12/"):
                raise CandidateLocalFailure(
                    "M12", "writer", "candidate_artifact_collision"
                )
            raise ValueError(f"current Route-S artifact overwrite refused: {ref}")
        return
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


__all__ = [
    "CurrentRouteSArtifactRecord",
    "build_current_relation_closure",
    "persist_current_route_s_result",
]
