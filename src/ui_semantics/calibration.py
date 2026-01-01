"""Normal-control calibration for deterministic business assertions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class CalibrationDecision:
    assertion_id: str
    retained: bool
    normal_runs: int
    reason: str | None


def calibrate_assertions(
    assertions: Iterable[dict[str, Any]],
    *,
    normal_runs: int,
    evaluate_normal: Callable[[dict[str, Any], int], bool],
) -> list[CalibrationDecision]:
    if normal_runs < 1:
        raise ValueError("normal_runs must be positive")
    decisions = []
    for assertion in assertions:
        assertion_id = str(assertion["assertion_id"])
        outcomes = [bool(evaluate_normal(assertion, run)) for run in range(normal_runs)]
        retained = all(outcomes)
        decisions.append(
            CalibrationDecision(
                assertion_id=assertion_id,
                retained=retained,
                normal_runs=normal_runs,
                reason=None if retained else "failed_normal_control",
            )
        )
    return decisions
