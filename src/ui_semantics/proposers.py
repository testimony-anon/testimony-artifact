"""Typed proposer entry points. Providers propose; deterministic code admits."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .providers import ProposalProvider, ProposalResponse


@dataclass(frozen=True)
class ProposalBatch:
    channel: str
    items: tuple[dict[str, Any], ...]
    proposal_run: dict[str, Any]


def propose_semantic_edges(
    provider: ProposalProvider,
    *,
    prompt: str,
    evidence: dict[str, Any],
    proposal_run_id: str,
    prompt_template: str | None = None,
    evidence_frozen_at: str | None = None,
) -> ProposalBatch:
    return _propose(
        provider,
        "semantic_edges",
        "candidates",
        prompt,
        evidence,
        proposal_run_id,
        prompt_template=prompt_template,
        evidence_frozen_at=evidence_frozen_at,
    )


def propose_ui_diff_assertions(
    provider: ProposalProvider,
    *,
    prompt: str,
    evidence: dict[str, Any],
    proposal_run_id: str,
    prompt_template: str | None = None,
    evidence_frozen_at: str | None = None,
) -> ProposalBatch:
    response, proposal_run = _invoke_provider(
        provider,
        prompt=prompt,
        evidence=evidence,
        proposal_run_id=proposal_run_id,
        prompt_template=prompt_template,
        evidence_frozen_at=evidence_frozen_at,
    )
    business = _extract_items(response.content, ("business_assertions", "assertions"), False)
    generic = response.content.get("generic_assertions", [])
    if not isinstance(generic, list) or not all(isinstance(item, dict) for item in generic):
        raise ValueError("generic_assertions must contain object items")
    items = [dict(item, assertion_class="business") for item in business]
    items.extend(dict(item, assertion_class="generic") for item in generic)
    return ProposalBatch(
        channel="ui_diff",
        items=tuple(items),
        proposal_run=proposal_run,
    )


def propose_constraint_inputs(
    provider: ProposalProvider,
    *,
    prompt: str,
    evidence: dict[str, Any],
    proposal_run_id: str,
    prompt_template: str | None = None,
    evidence_frozen_at: str | None = None,
) -> ProposalBatch:
    return _propose(
        provider,
        "constraints",
        ("cases", "inputs"),
        prompt,
        evidence,
        proposal_run_id,
        prompt_template=prompt_template,
        evidence_frozen_at=evidence_frozen_at,
    )


def propose_assertion_transfer(
    provider: ProposalProvider,
    *,
    prompt: str,
    evidence: dict[str, Any],
    proposal_run_id: str,
    prompt_template: str | None = None,
    evidence_frozen_at: str | None = None,
) -> ProposalBatch:
    return _propose(
        provider,
        "assertion_transfer",
        ("translations", "assertions", "result"),
        prompt,
        evidence,
        proposal_run_id,
        allow_single=True,
        prompt_template=prompt_template,
        evidence_frozen_at=evidence_frozen_at,
    )


def _propose(
    provider: ProposalProvider,
    channel: str,
    keys: str | tuple[str, ...],
    prompt: str,
    evidence: dict[str, Any],
    proposal_run_id: str,
    *,
    allow_single: bool = False,
    prompt_template: str | None = None,
    evidence_frozen_at: str | None = None,
) -> ProposalBatch:
    response, proposal_run = _invoke_provider(
        provider,
        prompt=prompt,
        evidence=evidence,
        proposal_run_id=proposal_run_id,
        prompt_template=prompt_template,
        evidence_frozen_at=evidence_frozen_at,
    )
    items = _extract_items(response.content, (keys,) if isinstance(keys, str) else keys, allow_single)
    return ProposalBatch(
        channel=channel,
        items=tuple(items),
        proposal_run=proposal_run,
    )


def _extract_items(content: dict[str, Any], keys: tuple[str, ...], allow_single: bool) -> list[dict[str, Any]]:
    for key in keys:
        if key not in content:
            continue
        value = content[key]
        if allow_single and isinstance(value, dict):
            return [value]
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
        raise ValueError(f"proposal field {key!r} must contain object items")
    if allow_single and any(key in content for key in ("type", "untranslatable_reason")):
        return [content]
    raise ValueError(f"proposal response missing one of {keys!r}")


def _invoke_provider(
    provider: ProposalProvider,
    *,
    prompt: str,
    evidence: dict[str, Any],
    proposal_run_id: str,
    prompt_template: str | None,
    evidence_frozen_at: str | None,
) -> tuple[ProposalResponse, dict[str, Any]]:
    evidence_sha256 = _sha256_json(evidence)
    response = provider.propose(prompt=prompt, evidence=evidence)
    if _sha256_json(evidence) != evidence_sha256:
        raise ValueError("typed evidence changed during proposal call")
    return response, _proposal_run(
        proposal_run_id,
        prompt=prompt,
        prompt_template=prompt_template,
        evidence_sha256=evidence_sha256,
        evidence_frozen_at=evidence_frozen_at,
        response=response,
    )


def _proposal_run(
    proposal_run_id: str,
    *,
    prompt: str,
    prompt_template: str | None,
    evidence_sha256: str,
    evidence_frozen_at: str | None,
    response: ProposalResponse,
) -> dict[str, Any]:
    endpoint_shape = response.endpoint_shape
    if endpoint_shape == "frozen_test_only":
        endpoint_shape = "other_disclosed"
    record = {
        "proposal_run_id": proposal_run_id,
        "prompt_sha256": _sha256_text(prompt),
        "evidence_sha256": evidence_sha256,
        "response_sha256": response.response_sha256,
        "model": response.model,
        "endpoint_shape": endpoint_shape,
        "temperature": response.temperature,
        "retry_count": response.retry_count,
    }
    if response.endpoint_shape == "frozen_test_only":
        return record
    if prompt_template is None or evidence_frozen_at is None or response.response_received_at is None:
        raise ValueError("live proposal requires v2 template and timing provenance")
    _validate_v2_provenance(
        endpoint_host=response.endpoint_host,
        evidence_frozen_at=evidence_frozen_at,
        response_received_at=response.response_received_at,
    )
    record.update(
        {
            "provenance_version": "v2",
            "template_sha256": _sha256_text(prompt_template),
            "endpoint_host": response.endpoint_host,
            "evidence_frozen_at": evidence_frozen_at,
            "response_received_at": response.response_received_at,
        }
    )
    return record


def _validate_v2_provenance(*, endpoint_host: str, evidence_frozen_at: str, response_received_at: str) -> None:
    if (
        not endpoint_host
        or any(token in endpoint_host for token in ("://", "/", "?", "#", "@"))
        or any(character.isspace() for character in endpoint_host)
    ):
        raise ValueError("endpoint_host must contain only a host and optional port")
    frozen = _parse_utc(evidence_frozen_at)
    received = _parse_utc(response_received_at)
    if received <= frozen:
        raise ValueError("response_received_at must be later than evidence_frozen_at")


def _parse_utc(value: str) -> datetime:
    try:
        normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("proposal provenance timestamp must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("proposal provenance timestamp must be UTC")
    return parsed


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha256_json(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_text(canonical)
