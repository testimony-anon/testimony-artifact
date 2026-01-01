"""Stage 6: executable grounding (live replay + counterexample validation; decision record 007).

The "verify" half of propose-and-verify: sequences are replayed live (grounded/validation_failed), the used dependency edges
are judged hard/soft/inconclusive by counterexamples; results are written back into the three artifacts + a grounded_report.
"""

from importlib import import_module
from typing import Any


_EXPORTS = {
    "GroundingRunner": (".assemble", "GroundingRunner"),
    "build_grounded_report": (".assemble", "build_grounded_report"),
    "canonical_dumps": (".assemble", "canonical_dumps"),
    "run_stage6": (".assemble", "run_stage6"),
    "ReplayConfig": (".config", "ReplayConfig"),
    "RawProbeStep": (".discovery", "RawProbeStep"),
    "ScheduledDiscoveryRunner": (".discovery", "ScheduledDiscoveryRunner"),
    "ScheduledProbeRun": (".discovery", "ScheduledProbeRun"),
    "SUPPORTED_GRAPHAMP_TEMPLATES": (".graphamp_parity", "SUPPORTED_GRAPHAMP_TEMPLATES"),
    "evaluate_supported_outcome": (".graphamp_parity", "evaluate_supported_outcome"),
    "ReplayClient": (".replay", "ReplayClient"),
    "build_op_index": (".replay", "build_op_index"),
    "LegacyConduitSafetyShell": (".safety", "LegacyConduitSafetyShell"),
    "SafetyShell": (".safety", "SafetyShell"),
    "TestSuiteExecutor": (".test_execution", "TestSuiteExecutor"),
    "build_actor_sessions": (".test_execution", "build_actor_sessions"),
    "encode_body": (".test_execution", "encode_body"),
    "reset_profile": (".test_execution", "reset_profile"),
    "run_test_suite": (".test_execution", "run_test_suite"),
    "SessionBundleReplayAdapter": (".ui_semantic_replay", "SessionBundleReplayAdapter"),
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
