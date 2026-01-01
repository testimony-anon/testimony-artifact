"""Explicit lazy namespace for pre-current UISemTest APIs."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "binder": ("..binder", None),
    "calibration": ("..calibration", None),
    "constraints": ("..constraints", None),
    "coordinator": ("..coordinator", None),
    "pipeline": ("..pipeline", None),
    "proposers": ("..proposers", None),
    "providers": ("..providers", None),
    "semantic_edges": ("..semantic_edges", None),
    "unit_scale": ("..unit_scale", None),
    "BindingDecision": ("..binder", "BindingDecision"),
    "bind_actions": ("..binder", "bind_actions"),
    "CalibrationDecision": ("..calibration", "CalibrationDecision"),
    "calibrate_assertions": ("..calibration", "calibrate_assertions"),
    "classify_constraint_result": ("..constraints", "classify_constraint_result"),
    "validate_constraint_cases": ("..constraints", "validate_constraint_cases"),
    "LintResult": ("..dsl", "LintResult"),
    "evaluate_predicate": ("..dsl", "evaluate_predicate"),
    "lint_predicate": ("..dsl", "lint_predicate"),
    "OpenAICompatibleProvider": ("..providers", "OpenAICompatibleProvider"),
    "ProposalProvider": ("..providers", "ProposalProvider"),
    "ProposalResponse": ("..providers", "ProposalResponse"),
    "PromptSpec": ("..coordinator", "PromptSpec"),
    "run_ui_semantics": ("..coordinator", "run_ui_semantics"),
    "ProposalBatch": ("..proposers", "ProposalBatch"),
    "propose_assertion_transfer": ("..proposers", "propose_assertion_transfer"),
    "propose_constraint_inputs": ("..proposers", "propose_constraint_inputs"),
    "propose_semantic_edges": ("..proposers", "propose_semantic_edges"),
    "propose_ui_diff_assertions": ("..proposers", "propose_ui_diff_assertions"),
    "UiSemanticsConfig": ("..pipeline", "UiSemanticsConfig"),
    "build_ui_trace_from_bundles": ("..trace_builder", "build_ui_trace_from_bundles"),
    "load_constraint_input_audit": ("..pipeline", "load_constraint_input_audit"),
    "load_semantic_edge_audit": ("..pipeline", "load_semantic_edge_audit"),
    "load_test_blueprints": ("..pipeline", "load_test_blueprints"),
    "load_typed_artifact": ("..pipeline", "load_typed_artifact"),
    "load_ui_semantics_config": ("..pipeline", "load_ui_semantics_config"),
    "load_ui_semantics_evidence": ("..pipeline", "load_ui_semantics_evidence"),
    "validate_blueprint_invariants": ("..pipeline", "validate_blueprint_invariants"),
    "validate_constraint_audit_invariants": ("..pipeline", "validate_constraint_audit_invariants"),
    "validate_constraint_variant_links": ("..pipeline", "validate_constraint_variant_links"),
    "validate_semantic_audit_invariants": ("..pipeline", "validate_semantic_audit_invariants"),
    "CandidateDecision": ("..semantic_edges", "CandidateDecision"),
    "DeterministicTwoArmVerifier": ("..semantic_edges", "DeterministicTwoArmVerifier"),
    "SessionMaintenanceHandling": ("..semantic_edges", "SessionMaintenanceHandling"),
    "SetupSessionKind": ("..semantic_edges", "SetupSessionKind"),
    "SetupSessionPolicy": ("..semantic_edges", "SetupSessionPolicy"),
    "derive_trace_enum_evidence": ("..semantic_edges", "derive_trace_enum_evidence"),
    "prepare_semantic_candidate": ("..semantic_edges", "prepare_semantic_candidate"),
    "verify_semantic_candidate": ("..semantic_edges", "verify_semantic_candidate"),
    "ScalePair": ("..unit_scale", "ScalePair"),
    "derive_unit_scale": ("..unit_scale", "derive_unit_scale"),
    "parse_currency_decimal": ("..unit_scale", "parse_currency_decimal"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    module = import_module(module_name, __name__)
    value = module if attribute is None else getattr(module, attribute)
    globals()[name] = value
    return value
