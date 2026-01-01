"""Neutral bounded semantic-stability polling for current M12 and M14."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping


SETTLE_SCHEMA_VERSION = "uisemtest-current-settle-policy-v2"
SETTLE_RULE = "bounded_semantic_stability_v1"


@dataclass(frozen=True)
class StabilityPollResult:
    status: Literal["stable", "settle_timeout", "observer_failed", "observer_impure"]
    elapsed_ns: int
    poll_count: int
    consecutive_identical: int
    projection_sha256: str | None
    final_observation: dict[str, Any] | None
    observations: tuple[dict[str, Any], ...]


def validate_settle_policy(policy: Mapping[str, Any]) -> None:
    expected = {
        "schema_version": SETTLE_SCHEMA_VERSION,
        "rule": SETTLE_RULE,
        "minimum_duration_ms": 500,
        "poll_interval_ms": 100,
        "consecutive_identical_observations": 3,
        "maximum_duration_ms": 2_000,
    }
    if dict(policy) != expected:
        raise ValueError("current settle policy must equal the frozen neutral policy")


def semantic_projection_sha256(observation: Mapping[str, Any]) -> str:
    """Hash only normalized transport semantics, never predicate truth."""

    response = observation.get("response")
    if not isinstance(response, Mapping):
        raise ValueError("settle observer response is not an object")
    payload = json.dumps(
        {
            "status": response.get("status"),
            "body": response.get("body"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def poll_semantic_stability(
    policy: Mapping[str, Any],
    observe: Callable[[int], Mapping[str, Any]],
    *,
    observer_is_pure: Callable[[Mapping[str, Any]], bool],
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    sleep: Callable[[float], None] = time.sleep,
) -> StabilityPollResult:
    """Poll one already read-only observer until its semantic response is stable."""

    validate_settle_policy(policy)
    minimum_ns = int(policy["minimum_duration_ms"]) * 1_000_000
    interval_ns = int(policy["poll_interval_ms"]) * 1_000_000
    maximum_ns = int(policy["maximum_duration_ms"]) * 1_000_000
    required = int(policy["consecutive_identical_observations"])
    started = monotonic_ns()
    deadline = started + maximum_ns
    sleep(minimum_ns / 1_000_000_000)
    records: list[dict[str, Any]] = []
    previous_sha: str | None = None
    consecutive = 0

    while monotonic_ns() <= deadline:
        record = dict(observe(len(records) + 1))
        records.append(record)
        elapsed = monotonic_ns() - started
        if record.get("state") != "executed" or record.get("status") != "pass":
            return StabilityPollResult(
                "observer_failed",
                elapsed,
                len(records),
                consecutive,
                previous_sha,
                record,
                tuple(records),
            )
        if not observer_is_pure(record):
            return StabilityPollResult(
                "observer_impure",
                elapsed,
                len(records),
                consecutive,
                previous_sha,
                record,
                tuple(records),
            )
        projection_sha = semantic_projection_sha256(record)
        consecutive = consecutive + 1 if projection_sha == previous_sha else 1
        previous_sha = projection_sha
        if consecutive >= required and elapsed <= maximum_ns:
            return StabilityPollResult(
                "stable",
                elapsed,
                len(records),
                consecutive,
                projection_sha,
                record,
                tuple(records),
            )
        remaining = deadline - monotonic_ns()
        if remaining < interval_ns:
            break
        sleep(interval_ns / 1_000_000_000)

    return StabilityPollResult(
        "settle_timeout",
        min(monotonic_ns() - started, maximum_ns),
        len(records),
        consecutive,
        previous_sha,
        records[-1] if records else None,
        tuple(records),
    )


def route_observer_is_pure(observation: Mapping[str, Any]) -> bool:
    domains = observation.get("observer_domains")
    if not isinstance(domains, list) or len(domains) != 4:
        return False
    if {row.get("domain") for row in domains if isinstance(row, Mapping)} != {
        "cache",
        "cookie",
        "last_seen",
        "token",
    }:
        return False
    for row in domains:
        if not isinstance(row, Mapping):
            return False
        disposition = row.get("disposition")
        empty = row.get("mutation_events") == [] and row.get("uncertain_fields") == []
        if disposition == "proven_unchanged":
            if not (
                row.get("before_sha256")
                and row.get("before_sha256") == row.get("after_sha256")
                and empty
            ):
                return False
        elif disposition == "not_applicable":
            if not (
                row.get("before_sha256") is None
                and row.get("after_sha256") is None
                and empty
                and row.get("reason_code")
            ):
                return False
        else:
            return False
    return True
