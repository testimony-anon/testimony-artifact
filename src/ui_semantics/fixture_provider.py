"""Frozen file-backed proposal provider used only by deterministic offline runs."""

from __future__ import annotations

from .artifact_relocation import attested_sha256
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .proposal_run import ProposalCallSpec
from .current_providers import RenderedProposalResponse


@dataclass(frozen=True)
class FixtureScheduledCall:
    spec: ProposalCallSpec
    response_path: Path
    response_sha256: str
    response_received_at: str


@dataclass(frozen=True)
class FixtureProposalSchedule:
    plan_id: str
    frozen_at: str
    calls: tuple[FixtureScheduledCall, ...]
    raw_file_sha256: str


def load_fixture_proposal_schedule(path: Path) -> FixtureProposalSchedule:
    source = path.resolve(strict=True)
    if not source.is_file():
        raise ValueError("fixture proposal schedule is not a file")
    raw = source.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "plan_id",
        "frozen_at",
        "calls",
    }:
        raise ValueError("fixture proposal schedule shape mismatch")
    if value["schema_version"] != "uisemtest-fixture-proposal-schedule-v1":
        raise ValueError("unsupported fixture proposal schedule")
    rows = value["calls"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("fixture proposal schedule requires calls")
    calls: list[FixtureScheduledCall] = []
    spec_fields = set(ProposalCallSpec.model_fields)
    required_spec_fields = {
        key
        for key, field in ProposalCallSpec.model_fields.items()
        if field.is_required()
    }
    fixture_fields = {"response_ref", "response_sha256", "response_received_at"}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not required_spec_fields | fixture_fields <= set(row)
            or not set(row) <= spec_fields | fixture_fields
        ):
            raise ValueError("fixture scheduled call shape mismatch")
        spec_value = {key: row[key] for key in spec_fields if key in row}
        if "evidence_card_ids" in spec_value:
            spec_value["evidence_card_ids"] = tuple(
                spec_value["evidence_card_ids"]
            )
        spec = ProposalCallSpec.model_validate(spec_value, strict=True)
        response_path = _resolve_relative(source.parent, str(row["response_ref"]))
        response_sha = _sha256_file(response_path)
        if response_sha != row["response_sha256"]:
            raise ValueError("fixture provider response SHA-256 mismatch")
        response_value = json.loads(response_path.read_text(encoding="utf-8"))
        if not isinstance(response_value, dict):
            raise ValueError("fixture provider response must be an object")
        calls.append(
            FixtureScheduledCall(
                spec=spec,
                response_path=response_path,
                response_sha256=response_sha,
                response_received_at=str(row["response_received_at"]),
            )
        )
    if [item.spec.call_order for item in calls] != list(range(1, len(calls) + 1)):
        raise ValueError("fixture scheduled calls are not contiguous")
    if len({item.spec.call_id for item in calls}) != len(calls):
        raise ValueError("fixture scheduled call IDs are not unique")
    return FixtureProposalSchedule(
        plan_id=str(value["plan_id"]),
        frozen_at=str(value["frozen_at"]),
        calls=tuple(calls),
        raw_file_sha256=hashlib.sha256(raw).hexdigest(),
    )


class FixtureProviderFactory:
    """Return each frozen response exactly once, without a transport."""

    def __init__(self, schedule: FixtureProposalSchedule) -> None:
        self._calls = {item.spec.call_id: item for item in schedule.calls}
        self._created: set[str] = set()
        self.logical_call_count = 0

    def __call__(self, spec: ProposalCallSpec) -> "FrozenFixtureProvider":
        scheduled = self._calls.get(spec.call_id)
        if scheduled is None or scheduled.spec != spec:
            raise ValueError("fixture provider call is absent from the frozen schedule")
        if spec.call_id in self._created:
            raise ValueError("fixture provider instance requested more than once")
        self._created.add(spec.call_id)
        return FrozenFixtureProvider(scheduled, self)

    def assert_complete(self) -> None:
        if self._created != set(self._calls):
            raise ValueError("fixture provider factory did not instantiate every scheduled call")
        if self.logical_call_count != len(self._calls):
            raise ValueError("fixture provider logical call count does not equal the plan")


class FrozenFixtureProvider:
    def __init__(
        self,
        scheduled: FixtureScheduledCall,
        factory: FixtureProviderFactory,
    ) -> None:
        self._scheduled = scheduled
        self._factory = factory
        self._called = False

    def propose_rendered(self, *, rendered_prompt: str) -> RenderedProposalResponse:
        if self._called:
            raise ValueError("fixture provider call may deliver the rendered input only once")
        if not isinstance(rendered_prompt, str) or not rendered_prompt:
            raise ValueError("fixture provider requires the frozen rendered input")
        self._called = True
        self._factory.logical_call_count += 1
        content = self._scheduled.response_path.read_text(encoding="utf-8")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != self._scheduled.response_sha256:
            raise ValueError("fixture provider response changed after schedule load")
        spec = self._scheduled.spec
        return RenderedProposalResponse(
            content=content,
            raw_envelope={
                "schema_version": "uisemtest-frozen-fixture-response-v1",
                "call_id": spec.call_id,
                "response_file_sha256": self._scheduled.response_sha256,
                "transport_invoked": False,
            },
            model=spec.model,
            endpoint_shape=spec.endpoint_shape,
            endpoint_host=spec.endpoint_host,
            temperature=spec.temperature,
            retry_count=0,
            response_received_at=self._scheduled.response_received_at,
        )


def _resolve_relative(root: Path, raw_ref: str) -> Path:
    ref = PurePosixPath(raw_ref)
    if (
        ref.is_absolute()
        or ref.as_posix() != raw_ref
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
        raise ValueError("fixture response ref must be normalized relative POSIX")
    target = (root / Path(*ref.parts)).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("fixture response ref escapes the schedule root")
    return target


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


__all__ = [
    "FixtureProposalSchedule",
    "FixtureProviderFactory",
    "load_fixture_proposal_schedule",
]
