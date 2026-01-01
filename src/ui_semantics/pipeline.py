"""Typed UI-semantics configuration and cross-artifact loader invariants."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from common.contracts import validate_artifact


LLM_CHANNELS = (
    "semantic_edges",
    "ui_diff_assertions",
    "ui_constraints",
    "ui_assertion_transfer",
)


@dataclass(frozen=True)
class UiSemanticsConfig:
    enabled: bool
    llm_enabled: bool
    channels: dict[str, bool]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "UiSemanticsConfig":
        validate_artifact("ui_semantics_config.schema.json", value)
        return cls(
            enabled=bool(value["enabled"]),
            llm_enabled=bool(value["llm_enabled"]),
            channels={name: bool(value["channels"][name]) for name in LLM_CHANNELS},
        )

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "llm_enabled": self.llm_enabled, "channels": dict(self.channels)}


def load_ui_semantics_config(path: str | Path) -> UiSemanticsConfig:
    return UiSemanticsConfig.from_dict(_load_json(path))


def load_typed_artifact(path: str | Path, schema_name: str) -> dict[str, Any]:
    document = _load_json(path)
    validate_artifact(schema_name, document)
    return document


def load_ui_semantics_evidence(path: str | Path) -> dict[str, Any]:
    document = load_typed_artifact(path, "ui_semantics_evidence.schema.json")
    validate_evidence_invariants(document)
    return document


def load_test_blueprints(path: str | Path) -> dict[str, Any]:
    document = load_typed_artifact(path, "test_blueprints.schema.json")
    validate_blueprint_invariants(document)
    return document


def load_constraint_input_audit(
    path: str | Path,
    *,
    evidence_artifacts: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    document = load_typed_artifact(path, "constraint_input_audit.schema.json")
    validate_constraint_audit_invariants(document, evidence_artifacts=evidence_artifacts)
    return document


def load_semantic_edge_audit(path: str | Path) -> dict[str, Any]:
    document = load_typed_artifact(path, "semantic_edge_audit.schema.json")
    validate_semantic_audit_invariants(document)
    return document


def validate_evidence_invariants(document: dict[str, Any]) -> None:
    if document["channel"] != "ui_constraints":
        return
    for record in document["records"]:
        _require_unique(
            (field["field_id"] for field in record["fields"]),
            f"ui constraint record {record['record_id']} field_id",
        )


def validate_blueprint_invariants(document: dict[str, Any]) -> None:
    _require_unique((item["test_id"] for item in document["blueprints"]), "test_id")
    for blueprint in document["blueprints"]:
        test_id = blueprint["test_id"]
        _require_unique(
            (step["step_id"] for step in blueprint["setup_steps"] + blueprint["action_steps"]),
            f"blueprint {test_id} combined step_id",
        )
        _require_unique(
            (
                observation["observation_id"]
                for observation in blueprint["observe_before"] + blueprint["observe_after"]
            ),
            f"blueprint {test_id} combined observation_id",
        )
        _require_unique((item["variant_id"] for item in blueprint["input_variants"]), f"blueprint {test_id} variant_id")
        constraint_variants = [
            item for item in blueprint["input_variants"] if item.get("variant_source") == "ui_constraint"
        ]
        if constraint_variants:
            baselines = [
                item
                for item in blueprint["input_variants"]
                if item.get("variant_role") == "baseline" and item.get("variant_source") != "ui_constraint"
            ]
            if not baselines:
                raise ValueError(f"blueprint {test_id} has ui_constraint variants but no explicit baseline")


def validate_constraint_audit_invariants(
    document: dict[str, Any],
    *,
    evidence_artifacts: Iterable[dict[str, Any]] = (),
) -> None:
    _require_unique((item["proposal_run_id"] for item in document["proposal_runs"]), "proposal_run_id")
    _require_unique((item["record_id"] for item in document["observations"]), "constraint observation record_id")
    _require_unique((item["candidate_id"] for item in document["candidates"]), "constraint candidate_id")

    proposal_ids = {item["proposal_run_id"] for item in document["proposal_runs"]}
    observation_ids = {item["record_id"] for item in document["observations"]}
    audit_run_id = document["metadata"]["run_id"]
    evidence_by_key = {
        (artifact["metadata"]["run_id"], record["record_id"]): record
        for artifact in evidence_artifacts
        for record in artifact.get("records", [])
    }
    for candidate in document["candidates"]:
        candidate_id = candidate["candidate_id"]
        if candidate["proposal_run_id"] not in proposal_ids:
            raise ValueError(f"constraint candidate {candidate_id} references unknown proposal_run_id")
        if candidate.get("candidate_shape") == "malformed":
            _validate_raw_hash(candidate, label=f"constraint candidate {candidate_id}")
            continue
        refs = candidate["admission"]["baseline_observation_refs"]
        execution = candidate.get("execution")
        if execution is not None:
            refs = refs + execution["variant_observation_refs"]
        for ref in refs:
            if ref["run_id"] != audit_run_id or ref["record_id"] not in observation_ids:
                raise ValueError(f"constraint candidate {candidate_id} has unresolved observation ref")
        if evidence_by_key:
            allowed_constraints: set[str] = set()
            for ref in candidate["evidence_refs"]:
                record = evidence_by_key.get((ref["run_id"], ref["record_id"]))
                if record is None:
                    raise ValueError(f"constraint candidate {candidate_id} has unresolved evidence ref")
                allowed_constraints.update(_constraint_ids(record))
            missing = sorted(set(candidate["constraint_refs"]) - allowed_constraints)
            if missing:
                raise ValueError(
                    f"constraint candidate {candidate_id} references constraints absent from typed evidence: {missing}"
                )


def validate_semantic_audit_invariants(document: dict[str, Any]) -> None:
    _require_unique((item["proposal_run_id"] for item in document["proposal_runs"]), "proposal_run_id")
    _require_unique((item["candidate_id"] for item in document["candidates"]), "semantic candidate_id")
    proposal_ids = {item["proposal_run_id"] for item in document["proposal_runs"]}
    for candidate in document["candidates"]:
        candidate_id = candidate["candidate_id"]
        if candidate["proposal_run_id"] not in proposal_ids:
            raise ValueError(f"semantic candidate {candidate_id} references unknown proposal_run_id")
        if candidate.get("candidate_shape") == "malformed":
            _validate_raw_hash(candidate, label=f"semantic candidate {candidate_id}")


def validate_constraint_variant_links(
    blueprints: dict[str, Any],
    constraint_audit: dict[str, Any],
) -> None:
    candidates = {item["candidate_id"]: item for item in constraint_audit["candidates"]}
    audit_run_id = constraint_audit["metadata"]["run_id"]
    for blueprint in blueprints["blueprints"]:
        steps = {item["step_id"]: item for item in blueprint["setup_steps"] + blueprint["action_steps"]}
        for variant in blueprint["input_variants"]:
            if variant.get("variant_source") != "ui_constraint":
                continue
            ref = variant["constraint_candidate_ref"]
            if ref["run_id"] != audit_run_id or ref["record_id"] not in candidates:
                raise ValueError(f"variant {variant['variant_id']} has unresolved constraint candidate ref")
            candidate = candidates[ref["record_id"]]
            execution = candidate.get("execution") or {}
            if candidate["admission"]["verdict"] != "ready" or execution.get("classification") not in {
                "comparable_consistent",
                "comparable_divergent",
            }:
                raise ValueError(f"variant {variant['variant_id']} references a non-promotable constraint candidate")
            target = candidate["target"]
            if target["resolution"] != "resolved":
                raise ValueError(f"variant {variant['variant_id']} references an unresolved constraint target")
            selected = target["selected"]
            if selected["test_id"] != blueprint["test_id"] or selected["step_id"] not in steps:
                raise ValueError(f"variant {variant['variant_id']} target does not match its blueprint")
            step = steps[selected["step_id"]]
            if step["operation_id"] != selected["operation_id"]:
                raise ValueError(f"variant {variant['variant_id']} target operation does not match its step")
            assignments = [
                item
                for item in variant["assignments"]
                if item["step_id"] == selected["step_id"]
                and item["location"] == selected["location"]
                and item["field"] == selected["field"]
            ]
            if len(assignments) != 1:
                raise ValueError(f"variant {variant['variant_id']} must contain exactly one matching target assignment")


def _constraint_ids(record: dict[str, Any]) -> set[str]:
    values = {str(record["record_id"])}
    for field in record.get("fields", []):
        values.add(str(field["field_id"]))
        for key in ("constraint_observation_refs", "validation_message_refs"):
            values.update(str(ref["record_id"]) for ref in field.get(key, []))
    return values


def _validate_raw_hash(candidate: dict[str, Any], *, label: str) -> None:
    actual = hashlib.sha256(
        json.dumps(candidate["raw_proposal"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if actual != candidate["raw_proposal_sha256"]:
        raise ValueError(f"{label} raw_proposal_sha256 mismatch")


def _require_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ValueError(f"{label} must be unique; duplicates: {', '.join(sorted(duplicates))}")


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value
