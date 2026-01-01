"""Deterministic semantic-edge normalization and two-arm verdict boundary."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from .candidate_normalization import (
    CandidateDecision,
    derive_trace_enum_evidence,
    prepare_semantic_candidate,
)
from .dsl import evaluate_predicate, get_path
from .replay_policy import (
    ReplayAdapter,
    SessionMaintenanceHandling,
    SetupSessionKind,
    SetupSessionPolicy,
)


class TwoArmExecutor(Protocol):
    def verify(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Return verdict/reason plus immutable control and treatment references."""


class ReplayRuntimeFailure(RuntimeError):
    """A reset, login, transport, or setup failure after candidate admission."""


class DeterministicTwoArmVerifier:
    """Generic reset/control/treatment verifier; transport remains adapter-owned."""

    def __init__(self, adapter: ReplayAdapter) -> None:
        self._adapter = adapter

    def verify(self, candidate: dict[str, Any]) -> dict[str, Any]:
        try:
            if self._runtime_call(
                "value-flow scope check", self._adapter.producer_output_consumed, candidate
            ):
                return {
                    "verdict": "rejected_out_of_scope",
                    "reason": "consumer consumes producer-only output",
                }
            control, control_fingerprint = self._runtime_call("control reset", self._adapter.reset)
            self._execute_setup(control, candidate["setup"])
            control_first = self._runtime_call(
                "control consumer execution", self._adapter.execute, control, candidate["consumer"]
            )
            control_second = self._runtime_call(
                "control consumer replay", self._adapter.execute, control, candidate["consumer"]
            )
            if not _success(control_first) or not _success(control_second):
                return {"verdict": "rejected_predicate", "reason": "control consumer was not executable"}
            try:
                control_stable = _predicate_target(candidate["effect_predicate"], control_first) == _predicate_target(
                    candidate["effect_predicate"], control_second
                )
            except (KeyError, TypeError, ValueError):
                return {"verdict": "rejected_predicate", "reason": "control predicate target was not observable"}

            treatment, treatment_fingerprint = self._runtime_call("treatment reset", self._adapter.reset)
            self._execute_setup(treatment, candidate["setup"])
            before = self._runtime_call(
                "treatment consumer-before execution", self._adapter.execute, treatment, candidate["consumer"]
            )
            producer = self._runtime_call(
                "treatment producer execution", self._adapter.execute, treatment, candidate["producer"]
            )
            after = self._runtime_call(
                "treatment consumer-after execution", self._adapter.execute, treatment, candidate["consumer"]
            )
            if not all(_success(item) for item in (before, producer, after)):
                return {"verdict": "rejected_predicate", "reason": "treatment arm was not executable"}
            observations = {
                candidate["effect_predicate"].get("before_ref", "before"): before,
                candidate["effect_predicate"].get("after_ref", candidate["effect_predicate"].get("response_ref", "after")): after,
                "producer": {"request": producer.get("request"), "response": producer.get("body")},
                "consumer": {"request": after.get("request"), "response": after.get("body")},
            }
            try:
                passed, _details = evaluate_predicate(candidate["effect_predicate"], observations)
            except (KeyError, TypeError, ValueError):
                return {"verdict": "rejected_predicate", "reason": "effect predicate could not be evaluated"}
            if not control_stable or not passed:
                return {"verdict": "rejected_predicate", "reason": "control stability or effect predicate failed"}
            return {
                "verdict": "confirmed",
                "reason": "all deterministic checks passed",
                "verification": {
                    "control_ref": control_second["observation_ref"],
                    "treatment_ref": after["observation_ref"],
                    "reset_fingerprint_refs": [control_fingerprint, treatment_fingerprint],
                },
            }
        except ReplayRuntimeFailure as error:
            return {"verdict": "inconclusive", "reason": str(error)}
        except (KeyError, TypeError, ValueError) as error:
            return {"verdict": "rejected_malformed", "reason": str(error)}

    def _execute_setup(self, context: Any, setup: list[dict[str, str]]) -> None:
        if not setup:
            return
        self._runtime_call("setup preparation", self._adapter.prepare_setup, context, setup)
        for step in setup:
            policy = self._runtime_call(
                "setup session policy classification",
                self._adapter.setup_session_policy,
                step,
            )
            if policy.skip_setup:
                continue
            result = self._runtime_call(
                "setup request execution", self._adapter.execute_setup, context, step
            )
            if not _success(result):
                raise ReplayRuntimeFailure(f"setup request failed: {step['request_ref']}")

    @staticmethod
    def _runtime_call(label: str, function: Callable[..., Any], *args: Any) -> Any:
        try:
            return function(*args)
        except ReplayRuntimeFailure:
            raise
        except Exception as error:
            reason = getattr(error, "reason_code", type(error).__name__)
            raise ReplayRuntimeFailure(f"{label} failed: {reason}") from error


def verify_semantic_candidate(prepared: CandidateDecision, executor: TwoArmExecutor) -> CandidateDecision:
    if prepared.verdict != "ready" or prepared.candidate is None:
        return prepared
    result = executor.verify(prepared.candidate)
    verdict = result.get("verdict")
    reason = result.get("reason")
    if verdict == "confirmed":
        verification = result.get("verification")
        if not isinstance(verification, dict):
            raise ValueError("confirmed candidate requires deterministic verification references")
        return CandidateDecision("confirmed", None, reason, prepared.candidate, verification)
    if verdict in {"rejected_predicate", "rejected_out_of_scope", "rejected_malformed"}:
        return CandidateDecision("rejected", verdict, reason, prepared.candidate)
    if verdict == "inconclusive":
        return CandidateDecision("inconclusive", None, reason, prepared.candidate)
    raise ValueError(f"unknown two-arm verdict: {verdict!r}")


def _success(observation: dict[str, Any]) -> bool:
    status = observation.get("status")
    return isinstance(status, int) and 200 <= status < 400


def _predicate_target(predicate: dict[str, Any], observation: dict[str, Any]) -> Any:
    path = predicate.get("collection_path") if predicate["type"] == "item_appears" else predicate.get("target_path", "")
    return get_path(observation.get("body"), path)
