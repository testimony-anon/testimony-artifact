"""Stage 2.5 public API with lazy live imports.

Importing :mod:`stage2_5_probe.offline` is guaranteed not to pull credential,
transport, reset, or Stage6 execution modules.  Historical public attributes
remain available through lazy loading for compatibility.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "build_audit_only_probe_results": (".offline", "build_audit_only_probe_results"),
    "Stage25Inputs": (".loader", "Stage25Inputs"),
    "PathInfo": (".loader", "PathInfo"),
    "load_inputs": (".loader", "load_inputs"),
    "DiscoveryCandidatePlanResult": (".discovery_planner", "DiscoveryCandidatePlanResult"),
    "plan_discovery_candidates": (".discovery_planner", "plan_discovery_candidates"),
    "InitialValueFlow": (".initial_valueflow", "InitialValueFlow"),
    "InitialValueFlowKey": (".initial_valueflow", "InitialValueFlowKey"),
    "InitialValueFlowSelection": (".initial_valueflow", "InitialValueFlowSelection"),
    "RecordedOperation": (".initial_valueflow", "RecordedOperation"),
    "infer_initial_value_flows": (".initial_valueflow", "infer_initial_value_flows"),
    "recorded_operations": (".initial_valueflow", "recorded_operations"),
    "select_initial_value_flows_for_scheduled_planning": (
        ".initial_valueflow",
        "select_initial_value_flows_for_scheduled_planning",
    ),
    "PathGraphProbePlanResult": (".path_graph_planner", "PathGraphProbePlanResult"),
    "plan_path_graph_probe_candidates": (
        ".path_graph_planner",
        "plan_path_graph_probe_candidates",
    ),
    "ProbeTarget": (".planner", "ProbeTarget"),
    "plan_probes": (".planner", "plan_probes"),
    "ResponseProbePlanResult": (".response_planner", "ResponseProbePlanResult"),
    "extract_response_json_tokens": (".response_planner", "extract_response_json_tokens"),
    "plan_response_probe_candidates": (".response_planner", "plan_response_probe_candidates"),
    "apply_runtime_probe_plan_to_probe_results": (
        ".runtime_material_planner",
        "apply_runtime_probe_plan_to_probe_results",
    ),
    "build_runtime_probe_plan_report": (
        ".runtime_material_planner",
        "build_runtime_probe_plan_report",
    ),
    "build_runtime_probe_plan_report_from_paths": (
        ".runtime_material_planner",
        "build_runtime_probe_plan_report_from_paths",
    ),
    "probe_audit_records_from_runtime_probe_plan_report": (
        ".runtime_material_planner",
        "probe_audit_records_from_runtime_probe_plan_report",
    ),
    "write_runtime_probe_plan_report": (
        ".runtime_material_planner",
        "write_runtime_probe_plan_report",
    ),
    "ScheduledProbePlan": (".scheduled", "ScheduledProbePlan"),
    "execute_scheduled_probe": (".scheduled", "execute_scheduled_probe"),
    "OperationProbePlanResult": (".scheduled_planner", "OperationProbePlanResult"),
    "plan_scheduled_operation_probes": (
        ".scheduled_planner",
        "plan_scheduled_operation_probes",
    ),
    "recover_probe_results": (".assemble", "recover_probe_results"),
    "recover_probe_results_audit_only": (".assemble", "recover_probe_results_audit_only"),
    "recover_probe_results_with_scheduled_execution": (".assemble", "recover_probe_results_with_scheduled_execution"),
    "run_stage2_5": (".assemble", "run_stage2_5"),
    "canonical_dumps": (".assemble", "canonical_dumps"),
    "discovery_set": (".assemble", "discovery_set"),
    "Prober": (".prober", "Prober"),
    "RuntimeAuth": (".prober", "RuntimeAuth"),
    "CleanupFailedError": (".prober", "CleanupFailedError"),
    "login_auth": (".prober", "login_auth"),
    "login_token": (".prober", "login_token"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
