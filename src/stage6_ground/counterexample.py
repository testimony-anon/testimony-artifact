"""Counterexample (counterfactual) validation (D50, the most critical part): judge each used dependency edge hard/soft/inconclusive.

Per-edge-kind perturbation values (M4; two counter-intuitive pitfalls corrected by live runs):
- id/resource edges (slug -> path): replace_nonexistent (substitute a nonexistent value, stable 404); drop is forbidden
  (an emptied path segment falls through to the list route -> 200, a false negative).
- auth edges: drop_all_sources (remove every source -> 401, judges the category hard) + switch_alternative_source (an alternative
  source still gives 200, judges the single edge soft); replacing with a bad token is forbidden (-> 500, a dirty signal).
Qualified failure codes (M3): id edges accept only 404, auth edges only 401/403; incidental 5xx/429 do not count -> inconclusive.
Three levels (M3): hard (qualified failure) / soft (positive value flow usable, counterexample does not fail) / inconclusive (non-qualified failure or not run).
Majority vote (S4): each counterexample runs several times and takes the majority, to resist transient flakiness.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .replay import DROP, ReplayClient

FROM_RESPONSE_BODY = "response_body"

NONEXISTENT_SLUG = "carverflow-nonexistent-slug-zzz999"
NONEXISTENT_TAG = "carverflow-nonexistent-tag-zzz999"
PERTURBED_VALUE = "carverflow-perturbed-value"

# Qualified failure codes (M3): gated by edge kind
QUALIFIED = {
    ("data", "path"): {404},
    ("data", "header"): {412, 428},
    ("auth", "header"): {401, 403},
    # data query/body: the consumer still returns 200 after perturbation (filter/value not required) -> no qualified failure code -> judged soft
}


@dataclass
class EdgeVerdict:
    producer: str
    consumer: str
    edge_kind: str
    perturbation: str
    consumer_status: int | None
    consumer_failed: bool
    dependency_strength: str
    sequence_id: str
    reason: str


def _broken_value(to_location: str) -> object:
    if to_location == "path":
        return NONEXISTENT_SLUG
    if to_location == "query":
        return NONEXISTENT_TAG
    return PERTURBED_VALUE


def _same_binding(a: dict, b: dict) -> bool:
    return (a["from_step"] == b["from_step"]
            and a.get("from_location", FROM_RESPONSE_BODY) == b.get("from_location", FROM_RESPONSE_BODY)
            and a["from_field"] == b["from_field"]
            and a["to_step"] == b["to_step"]
            and a["to_location"] == b["to_location"] and a["to_field"] == b["to_field"])


def _consumer_step_result(outcome, consumer_step: int):
    for sr in outcome.steps:
        if sr.step_index == consumer_step:
            return sr
    return None


def _single_verdict(consumer_passed: bool, status: int | None, qualified: set) -> tuple[str, bool]:
    """Single counterexample verdict -> (strength, consumer_failed)."""
    if consumer_passed:
        return "soft", False                 # consumer still succeeds with the perturbed value -> not required
    if status in qualified:
        return "hard", True                  # qualified failure -> requiredness confirmed
    return "inconclusive", False             # non-qualified failure (5xx dirty signal / binding break) -> not attributed


def _strict_majority(verdicts: list[str]) -> str:
    """Deterministic majority vote (S4/D52): adopt only a strict majority (> half), otherwise inconclusive.

    Does not rely on the tie iteration order of Counter.most_common (hash-dependent, non-deterministic): takes the
    highest count explicitly; a unique maximum above half -> adopted; a three-way tie / no strict majority ->
    inconclusive (unstable signal, not attributed, M3).
    """
    counts = Counter(verdicts)
    top = max(counts.values())
    winners = sorted(v for v, c in counts.items() if c == top)
    if len(winners) == 1 and top * 2 > len(verdicts):
        return winners[0]
    return "inconclusive"


def run_counterexample(client: ReplayClient, steps: list[str], bindings: list[dict],
                       parameters: list[dict], target_binding: dict, kind: str,
                       perturbation: str, sequence_id: str, majority_n: int = 3,
                       switch_token: str | None = None) -> EdgeVerdict:
    """Run the counterexample for one used value-flow (majority vote). Returns the edge verdict."""
    consumer_step = target_binding["to_step"]
    producer_op = steps[target_binding["from_step"]]
    consumer_op = steps[consumer_step]
    to_location = target_binding["to_location"]
    qualified = QUALIFIED.get((kind, to_location), set())
    # Truncate at the consumer step: the counterexample only needs to run up to the consumer of the edge under test, never
    # downstream steps (avoids downstream write side effects, e.g. accidentally hitting delete_var1 while auth-drop tests get_articles).
    steps = steps[:consumer_step + 1]
    bindings = [b for b in bindings if b["to_step"] <= consumer_step]

    def override(b, default):
        if not _same_binding(b, target_binding):
            return default
        if perturbation == "drop_all_sources":
            return DROP
        if perturbation == "switch_alternative_source":
            return switch_token if switch_token is not None else default
        return _broken_value(to_location)   # replace_nonexistent

    verdicts: list[str] = []
    statuses: list[int | None] = []
    failed_flags: list[bool] = []
    for _ in range(majority_n):
        outcome = client.replay(steps, bindings, parameters, value_override=override)
        sr = _consumer_step_result(outcome, consumer_step)
        passed = bool(sr and sr.passed)
        status = sr.response_status if sr else None
        strength, cfailed = _single_verdict(passed, status, qualified)
        verdicts.append(strength)
        statuses.append(status)
        failed_flags.append(cfailed)

    strength = _strict_majority(verdicts)
    # Representative status code/failure flag of the majority; when a tie forces inconclusive no single run matches -> take the last one
    rep_idx = next((i for i, v in enumerate(verdicts) if v == strength), len(verdicts) - 1)
    from_ref = f"{target_binding.get('from_location', FROM_RESPONSE_BODY)}:{target_binding['from_field']}"
    reason = (f"{perturbation} perturbed {producer_op}.{from_ref} -> "
              f"{consumer_op} {to_location}/{target_binding['to_field']}; "
              f"consumer status over {majority_n} runs={statuses}, majority verdict {strength}"
              f" (qualified failure codes={sorted(qualified) or 'none'})")
    return EdgeVerdict(producer_op, consumer_op, kind, perturbation, statuses[rep_idx],
                       failed_flags[rep_idx], strength, sequence_id, reason)
