"""Typed current-run failures attributable to exactly one candidate."""

from __future__ import annotations

import re


_CATEGORIES = {"binding", "contract", "writer", "capture_safety"}
_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SETUP_DOMAIN_MISSING_REASONS = {
    "producer_request_missing_from_trace",
    "selected_setup_request_actor_missing",
}
_CREATOR_IDENTITY_AMBIGUITY_REASONS = {
    "observed_fresh_source_ambiguous",
    "producer_lookup_source_ambiguous",
    "setup_dependency_producer_ambiguous",
}
_CANDIDATE_NOT_EXECUTABLE_REASONS = {
    "observer_identity_available_only_after_treatment_producer",
    "observer_identity_source_not_prior_to_treatment_producer",
}


def _failure_kind(stage: str, category: str, reason_code: str) -> str:
    """Project an existing symbolic failure onto the T10 setup taxonomy."""

    if category in {"writer", "capture_safety"}:
        return "harness_infrastructure_failure"
    if stage == "M11b" and reason_code in _SETUP_DOMAIN_MISSING_REASONS:
        return "setup_domain_missing"
    if (
        stage == "M11b"
        and category == "binding"
        and reason_code in _CREATOR_IDENTITY_AMBIGUITY_REASONS
    ):
        return "creator_identity_ambiguous"
    if category == "contract" or reason_code in _CANDIDATE_NOT_EXECUTABLE_REASONS:
        return "candidate_not_executable"
    return "dependency_or_fresh_binding_failed"


class CandidateLocalFailure(RuntimeError):
    """A symbolic, non-sensitive candidate-local M11b/M12 failure."""

    def __init__(self, stage: str, category: str, reason_code: str) -> None:
        if stage not in {"M11b", "M12"}:
            raise ValueError("candidate-local failure stage is not current M11b/M12")
        if category not in _CATEGORIES:
            raise ValueError("candidate-local failure category is not admitted")
        if not _REASON_CODE.fullmatch(reason_code):
            raise ValueError("candidate-local failure reason code is not symbolic")
        self.stage = stage
        self.category = category
        self.reason_code = reason_code
        super().__init__(f"{stage}:{category}:{reason_code}")

    def record(self, candidate_id: str, *, status: str) -> dict[str, str]:
        return {
            "candidate_id": candidate_id,
            "status": status,
            "failure_stage": self.stage,
            "failure_kind": _failure_kind(
                self.stage, self.category, self.reason_code
            ),
            "category": self.category,
            "reason_code": self.reason_code,
        }


__all__ = ["CandidateLocalFailure"]
