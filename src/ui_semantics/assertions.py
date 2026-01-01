"""Assertion candidate linting shared by UI-diff and assertion-transfer channels."""

from __future__ import annotations

from typing import Any, Iterable

from .dsl import LintResult, lint_predicate


def lint_assertion_candidates(
    candidates: Iterable[dict[str, Any]],
    *,
    source: str,
    improved: bool = False,
    enum_evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result = []
    for index, candidate in enumerate(candidates, start=1):
        candidate_id = str(candidate.get("candidate_id") or candidate.get("assertion_id") or f"{source}-{index:04d}")
        predicate = candidate.get("assertion", candidate.get("translation", candidate))
        lint = lint_predicate(predicate, assertion=True, improved=improved, enum_evidence=enum_evidence)
        result.append(
            {
                "candidate_id": candidate_id,
                "assertion_source": source,
                "raw_predicate": predicate if isinstance(predicate, dict) else {},
                "lint_verdict": lint.verdict,
                "lint_reason": lint.reason,
                "normalized_predicate": lint.predicate,
            }
        )
    return result
