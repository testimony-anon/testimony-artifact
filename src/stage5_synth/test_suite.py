"""Deterministic promotion from assertion audit candidates to Stage 5 test suites."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from common.contracts import make_envelope, validate_artifact
from stage0_launch.profile import AppProfile, actor_auth
from ui_semantics.pipeline import UiSemanticsConfig, validate_blueprint_invariants, validate_constraint_variant_links


ASSERTION_SOURCES = {"value_flow", "ui_diff", "ui_constraint", "ui_assertion_transfer"}
GENERIC_ASSERTION_TYPES = {"status_success", "schema_type"}


def build_test_suite(
    assertion_audit: dict[str, Any],
    case_blueprints: list[dict[str, Any]],
    *,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Promote lint-passing assertion candidates selected by explicit case blueprints.

    A blueprint has the test-case schema shape, except that it names
    ``assertion_candidate_ids`` instead of embedding assertions. Stage 5 does
    not calibrate; Stage 6 applies the declared calibration policy.
    """
    validate_artifact("assertion_audit.schema.json", assertion_audit)
    updated_audit = copy.deepcopy(assertion_audit)
    candidates = {candidate["candidate_id"]: candidate for candidate in updated_audit["candidates"]}
    if len(candidates) != len(updated_audit["candidates"]):
        raise ValueError("assertion audit contains duplicate candidate ids")

    cases = []
    promoted: set[str] = set()
    for raw_blueprint in case_blueprints:
        blueprint = copy.deepcopy(raw_blueprint)
        candidate_ids = blueprint.pop("assertion_candidate_ids", None)
        blueprint.pop("provenance_refs", None)
        if not isinstance(candidate_ids, list) or not candidate_ids:
            raise ValueError("test case blueprint requires assertion_candidate_ids")
        test_id = blueprint.get("test_id")
        if not isinstance(test_id, str) or not test_id:
            raise ValueError("test case blueprint requires test_id")
        assertions = []
        for candidate_id in candidate_ids:
            if candidate_id in promoted:
                raise ValueError(f"assertion candidate promoted more than once: {candidate_id}")
            candidate = candidates.get(candidate_id)
            if candidate is None:
                raise ValueError(f"unknown assertion candidate: {candidate_id}")
            if candidate["lint_verdict"] != "pass":
                raise ValueError(f"cannot promote non-passing assertion candidate: {candidate_id}")
            source = candidate["assertion_source"]
            if source not in ASSERTION_SOURCES:
                raise ValueError(f"unsupported assertion source: {source}")
            predicate = copy.deepcopy(candidate["raw_predicate"])
            assertions.append(
                {
                    "assertion_id": candidate_id,
                    "assertion_source": source,
                    "assertion_class": (
                        "generic" if predicate.get("type") in GENERIC_ASSERTION_TYPES else "business"
                    ),
                    "predicate": predicate,
                    "evidence_refs": [_artifact_ref_text(ref) for ref in candidate["evidence_refs"]],
                }
            )
            candidate["promoted_test_ref"] = test_id
            promoted.add(candidate_id)
        blueprint["assertions"] = assertions
        cases.append(blueprint)

    suite = {
        "metadata": make_envelope(
            "test_suite",
            "stage5",
            run_id,
            upstream_refs=[
                {
                    "artifact_type": "assertion_audit",
                    "run_id": assertion_audit["metadata"]["run_id"],
                }
            ],
        ),
        "cases": cases,
    }
    if "transform_evidence" in assertion_audit:
        suite["transform_evidence"] = copy.deepcopy(assertion_audit["transform_evidence"])
    validate_artifact("assertion_audit.schema.json", updated_audit)
    validate_artifact("test_suite.schema.json", suite)
    return updated_audit, suite


def build_test_suite_with_channels(
    assertion_audit: dict[str, Any],
    test_blueprints: dict[str, Any],
    augmented_oas: dict[str, Any],
    config: UiSemanticsConfig,
    *,
    run_id: str,
    assertion_audit_path: str,
    test_blueprints_path: str,
    output_test_suite_path: str,
    constraint_input_audit: dict[str, Any] | None = None,
    constraint_input_audit_path: str | None = None,
    profile: AppProfile | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build one suite under a frozen channel configuration and record every constraint decision."""
    validate_artifact("assertion_audit.schema.json", assertion_audit)
    validate_artifact("test_blueprints.schema.json", test_blueprints)
    validate_artifact("augmented_oas.schema.json", augmented_oas)
    validate_blueprint_invariants(test_blueprints)
    validate_blueprint_execution_readiness(test_blueprints, augmented_oas, profile=profile)
    if constraint_input_audit is not None:
        validate_artifact("constraint_input_audit.schema.json", constraint_input_audit)
        validate_constraint_variant_links(test_blueprints, constraint_input_audit)

    enabled_sources = {"value_flow"}
    if config.enabled:
        if config.channels["ui_diff_assertions"]:
            enabled_sources.add("ui_diff")
        if config.channels["ui_constraints"]:
            enabled_sources.add("ui_constraint")
        if config.channels["ui_assertion_transfer"]:
            enabled_sources.add("ui_assertion_transfer")
    candidate_sources = {
        item["candidate_id"]: item["assertion_source"] for item in assertion_audit["candidates"]
    }
    decisions: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for raw in test_blueprints["blueprints"]:
        blueprint = copy.deepcopy(raw)
        test_id = blueprint["test_id"]
        constraint_variants_for_case: list[dict[str, Any]] = []
        candidate_ids = [
            candidate_id
            for candidate_id in blueprint["assertion_candidate_ids"]
            if candidate_sources.get(candidate_id) in enabled_sources
        ]
        variants = []
        for variant in blueprint["input_variants"]:
            if variant.get("variant_source") != "ui_constraint":
                variants.append(variant)
                continue
            constraint_variants_for_case.append(variant)
            if not config.enabled or not config.channels["ui_constraints"]:
                decisions.append(
                    _build_decision(
                        test_id,
                        variant,
                        "not_promoted_channel_disabled",
                        "ui_constraints channel is disabled",
                    )
                )
                continue
            if constraint_input_audit is None:
                raise ValueError(f"blueprint {test_id} requires constraint_input_audit")
            variants.append(variant)
        if not candidate_ids:
            for variant in variants:
                if variant.get("variant_source") == "ui_constraint":
                    decisions.append(
                        _build_decision(
                            test_id,
                            variant,
                            "not_promoted_no_assertion_blueprint",
                            "no enabled assertion candidate remains",
                        )
                    )
            continue
        baselines = [
            item
            for item in variants
            if item.get("variant_role") == "baseline" and item.get("variant_source") != "ui_constraint"
        ]
        if raw.get("input_variants") and any(
            item.get("variant_source") == "ui_constraint" for item in raw["input_variants"]
        ) and not baselines:
            decisions.append(
                {
                    "decision_id": f"decision-{len(decisions) + 1:05d}",
                    "test_id": test_id,
                    "variant_id": None,
                    "constraint_candidate_ref": None,
                    "status": "excluded_blueprint_no_baseline",
                    "reason": "no explicit non-constraint baseline remains",
                }
            )
            continue
        if not variants:
            continue
        for variant in constraint_variants_for_case:
            if variant in variants:
                decisions.append(_build_decision(test_id, variant, "promoted", None))
        blueprint["assertion_candidate_ids"] = candidate_ids
        blueprint["input_variants"] = variants
        selected.append(blueprint)

    updated_audit, suite = build_test_suite(assertion_audit, selected, run_id=run_id)
    config_sha256 = hashlib.sha256(
        json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    build_audit = {
        "metadata": make_envelope(
            "test_suite_build_audit",
            "stage5",
            f"{run_id}-build",
            upstream_refs=[
                {
                    "artifact_type": "test_blueprints",
                    "run_id": test_blueprints["metadata"]["run_id"],
                    "path": test_blueprints_path,
                },
                {
                    "artifact_type": "assertion_audit",
                    "run_id": assertion_audit["metadata"]["run_id"],
                    "path": assertion_audit_path,
                },
            ],
        ),
        "config_sha256": config_sha256,
        "input_refs": {
            "test_blueprints": _artifact_path_ref(test_blueprints, test_blueprints_path),
            "assertion_audit": _artifact_path_ref(assertion_audit, assertion_audit_path),
            "constraint_input_audit": (
                _artifact_path_ref(constraint_input_audit, constraint_input_audit_path)
                if constraint_input_audit is not None and constraint_input_audit_path is not None
                else None
            ),
        },
        "decisions": _renumber_decisions(decisions),
        "output_test_suite_ref": {
            "artifact_type": "test_suite",
            "run_id": suite["metadata"]["run_id"],
            "path": output_test_suite_path,
        },
    }
    validate_artifact("test_suite_build_audit.schema.json", build_audit)
    return updated_audit, suite, build_audit


def validate_blueprint_execution_readiness(
    test_blueprints: dict[str, Any],
    augmented_oas: dict[str, Any],
    *,
    profile: AppProfile | None = None,
) -> None:
    """Fail before Stage6 when a blueprint lacks admitted operations or required material."""
    operations = _operation_index(augmented_oas)
    for blueprint in test_blueprints["blueprints"]:
        test_id = blueprint["test_id"]
        steps = {
            (item.get("step_id") or item.get("observation_id")): item
            for phase in ("setup_steps", "observe_before", "action_steps", "observe_after")
            for item in blueprint[phase]
        }
        for variant in blueprint["input_variants"]:
            variant_id = variant["variant_id"]
            assignments = {}
            for assignment in variant["assignments"]:
                step_id = assignment["step_id"]
                if step_id not in steps:
                    raise ValueError(
                        f"blueprint {test_id} variant {variant_id} assignment references unknown step {step_id}"
                    )
                key = (step_id, assignment["location"], assignment["field"])
                if key in assignments:
                    raise ValueError(
                        f"blueprint {test_id} variant {variant_id} duplicates assignment {key}"
                    )
                _validate_external_parameter(assignment, test_id=test_id, variant_id=variant_id)
                assignments[key] = assignment
            for step_id, step in steps.items():
                operation_id = step["operation_id"]
                operation = operations.get(operation_id)
                if operation is None:
                    raise ValueError(
                        f"blueprint {test_id} references operation not admitted by gated OAS: {operation_id}"
                    )
                _validate_required_material(
                    test_id, variant_id, step_id, step, operation, assignments
                )
                external = [
                    assignment
                    for key, assignment in assignments.items()
                    if key[0] == step_id and assignment["generation_source"] == "external_parameter"
                ]
                if external:
                    if profile is None:
                        raise ValueError(
                            f"blueprint {test_id} variant {variant_id} requires a profile "
                            "to validate external parameters"
                        )
                    if not _is_declared_login_operation(profile, step["actor_id"], operation):
                        raise ValueError(
                            f"blueprint {test_id} variant {variant_id} uses profile credentials "
                            "outside the declared login endpoint"
                        )


def _operation_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or not operation.get("operationId"):
                continue
            result[operation["operationId"]] = {
                **operation,
                "__method": method.upper(),
                "__path": path,
            }
    return result


def _validate_external_parameter(
    assignment: dict[str, Any], *, test_id: str, variant_id: str
) -> None:
    if assignment["generation_source"] != "external_parameter":
        return
    value = assignment["value"]
    if not isinstance(value, dict) or set(value) != {"profile_credential"}:
        raise ValueError(
            f"blueprint {test_id} variant {variant_id} has invalid external parameter token"
        )
    if value["profile_credential"] not in {"email", "password"}:
        raise ValueError(
            f"blueprint {test_id} variant {variant_id} has unknown profile credential token"
        )


def _is_declared_login_operation(
    profile: AppProfile, actor_id: str, operation: dict[str, Any]
) -> bool:
    auth = actor_auth(profile, actor_id)
    cfg = (
        auth.api_token
        if auth.method == "api_token"
        else auth.cookie_session
        if auth.method == "cookie_session"
        else None
    )
    return (
        cfg is not None
        and cfg.method.upper() == operation["__method"]
        and cfg.path == operation["__path"]
    )


def _validate_required_material(
    test_id: str,
    variant_id: str,
    step_id: str,
    step: dict[str, Any],
    operation: dict[str, Any],
    assignments: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    for parameter in operation.get("parameters", []):
        if not parameter.get("required"):
            continue
        location = parameter.get("in")
        field = parameter.get("name")
        if location in {"path", "query", "header"} and (step_id, location, field) not in assignments:
            raise ValueError(
                f"blueprint {test_id} variant {variant_id} lacks required {location} material "
                f"for {step_id}.{field}"
            )
    request_body = operation.get("requestBody") or {}
    if not request_body.get("required"):
        return
    content = request_body.get("content") or {}
    media_type = {
        "json": "application/json",
        "form_urlencoded": "application/x-www-form-urlencoded",
        "multipart": "multipart/form-data",
    }.get(step.get("body_encoding"))
    media = content.get(media_type) if media_type is not None else None
    if media is None:
        if len(content) != 1:
            raise ValueError(
                f"blueprint {test_id} variant {variant_id} does not select one admitted "
                f"request media type for {step_id}"
            )
        media = next(iter(content.values()))
    schema = media.get("schema") or {}
    required = schema.get("required") or [] if schema.get("type") == "object" else []
    if required:
        for field in sorted(required):
            if (step_id, "body", f"$.{field}") not in assignments:
                raise ValueError(
                    f"blueprint {test_id} variant {variant_id} lacks required body material "
                    f"for {step_id}.$.{field}"
                )
    elif not any(key[0] == step_id and key[1] == "body" for key in assignments):
        raise ValueError(
            f"blueprint {test_id} variant {variant_id} lacks required body material for {step_id}"
        )


def _artifact_ref_text(ref: dict[str, Any]) -> str:
    parts = [ref["artifact_type"], ref["run_id"], ref["record_id"]]
    if ref.get("path"):
        parts.append(ref["path"])
    return ":".join(parts)


def _artifact_path_ref(document: dict[str, Any], path: str | None) -> dict[str, str]:
    if not path:
        raise ValueError("artifact path is required for test-suite build provenance")
    return {
        "artifact_type": document["metadata"]["artifact_type"],
        "run_id": document["metadata"]["run_id"],
        "path": path,
    }


def _build_decision(
    test_id: str,
    variant: dict[str, Any],
    status: str,
    reason: str | None,
) -> dict[str, Any]:
    return {
        "decision_id": "pending",
        "test_id": test_id,
        "variant_id": variant["variant_id"],
        "constraint_candidate_ref": copy.deepcopy(variant.get("constraint_candidate_ref")),
        "status": status,
        "reason": reason,
    }


def _renumber_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for decision in decisions:
        key = (
            decision["test_id"],
            decision.get("variant_id"),
            decision["status"],
        )
        if key in seen:
            continue
        seen.add(key)
        item = copy.deepcopy(decision)
        item["decision_id"] = f"decision-{len(result) + 1:05d}"
        result.append(item)
    return result
