"""Subject runtime factory seam shared by fixture and real current runs."""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Protocol

from stage2_recover.loader import LoadedBundle
from stage6_ground.relation_test_execution import CertifiedRelationRuntime

from .current_adapter import (
    CurrentAdapterBundle,
    DeterministicFixtureRuntimeConfig,
    LocalHttpRuntimeConfig,
)
from .current_calibration import CertifiedRelationFixtureRuntime
from .contracts import UiApiTrace
from .m11b_materializer import RouteSPreLiveMaterializedCandidate
from .current_route_s import (
    CurrentRouteSSubjectRuntime,
    DeterministicFixtureRuntime,
)


_STANDARD_RUNTIME_COUNTS = (
    "reset_runs",
    "session_materializations",
    "setup_executions",
    "request_executions",
    "settle_executions",
    "external_provider_llm_calls",
    "external_network_calls",
    "real_target_runs",
    "real_server_runs",
    "real_browser_runs",
    "real_docker_runs",
    "real_reset_runs",
)


class CurrentSubjectRuntimeFactory(Protocol):
    runtime_kind: str

    def preflight(self) -> None: ...
    def start(self, *, run_root: Path) -> None: ...
    def route_s_runtime(
        self, material: RouteSPreLiveMaterializedCandidate
    ) -> CurrentRouteSSubjectRuntime: ...
    def assert_route_s_complete(self, expected_candidates: int) -> None: ...
    def calibration_runtime(
        self, suite: Mapping[str, Any]
    ) -> CertifiedRelationRuntime: ...
    def auth_session_runtime(self) -> Any | None: ...
    def route_s_counts(self) -> dict[str, int]: ...
    def teardown(self) -> None: ...


def build_current_runtime_factory(
    bundle: CurrentAdapterBundle,
    *,
    run_id: str,
    request_bindings: Mapping[str, Any],
    trace: UiApiTrace,
    recording_material_aliases: tuple[dict[str, Any], ...] = (),
    recorded_bundles: Mapping[str, LoadedBundle] | None = None,
) -> CurrentSubjectRuntimeFactory:
    if isinstance(bundle.adapter.runtime, DeterministicFixtureRuntimeConfig):
        return DeterministicFixtureRuntimeFactory(
            bundle, request_bindings=request_bindings
        )
    if isinstance(bundle.adapter.runtime, LocalHttpRuntimeConfig):
        from .current_http_runtime import LocalHttpCurrentRuntimeFactory

        return LocalHttpCurrentRuntimeFactory(
            bundle,
            run_id=run_id,
            request_bindings=request_bindings,
            trace=trace,
            recording_material_aliases=recording_material_aliases,
            recorded_bundles=recorded_bundles,
        )
    raise TypeError("unsupported current subject runtime")


class DeterministicFixtureRuntimeFactory:
    runtime_kind = "deterministic_fixture"

    def __init__(
        self,
        bundle: CurrentAdapterBundle,
        *,
        request_bindings: Mapping[str, Any],
    ) -> None:
        if bundle.fixture_tape is None:
            raise ValueError("fixture runtime requires its validated transport tape")
        self._adapter = bundle.adapter.model_dump(mode="json")
        self._adapter["request_bindings"] = copy.deepcopy(dict(request_bindings))
        self._route_runs = copy.deepcopy(bundle.fixture_tape["route_runs"])
        self._next = 0
        self._execution_facts: dict[str, dict[str, Any]] = {}
        self._runtimes: list[DeterministicFixtureRuntime] = []
        self._started = False
        self._stopped = False

    def preflight(self) -> None:
        return None

    def start(self, *, run_root: Path) -> None:
        if self._started or self._stopped:
            raise ValueError("fixture runtime factory lifecycle may start only once")
        if not run_root.is_dir():
            raise ValueError("fixture runtime run root must already exist")
        self._started = True

    def route_s_runtime(
        self, material: RouteSPreLiveMaterializedCandidate
    ) -> DeterministicFixtureRuntime:
        if not self._started or self._stopped:
            raise ValueError("fixture Route-S runtime requested outside lifecycle")
        if self._next >= len(self._route_runs):
            raise ValueError("fixture runtime tape has fewer Route-S runs than candidates")
        if material.candidate_id in self._execution_facts:
            raise ValueError("fixture candidate runtime requested more than once")
        facts = copy.deepcopy(self._route_runs[self._next])
        self._next += 1
        self._execution_facts[material.candidate_id] = facts
        runtime = DeterministicFixtureRuntime(self._adapter, facts)
        self._runtimes.append(runtime)
        return runtime

    def assert_route_s_complete(self, expected_candidates: int) -> None:
        if self._next != expected_candidates or self._next != len(self._route_runs):
            raise ValueError("fixture runtime tape count does not exactly close candidates")

    def calibration_runtime(
        self, suite: Mapping[str, Any]
    ) -> CertifiedRelationFixtureRuntime:
        if not self._started or self._stopped:
            raise ValueError("fixture calibration runtime requested outside lifecycle")
        return CertifiedRelationFixtureRuntime(
            suite,
            request_bindings=self._adapter["request_bindings"],
            execution_facts_by_candidate=self._execution_facts,
        )

    def auth_session_runtime(self) -> None:
        return None

    def route_s_counts(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for runtime in self._runtimes:
            counts.update(runtime.counts())
        return {key: counts[key] for key in _STANDARD_RUNTIME_COUNTS}

    def teardown(self) -> None:
        if self._stopped:
            return
        self._stopped = True


__all__ = [
    "CurrentSubjectRuntimeFactory",
    "DeterministicFixtureRuntimeFactory",
    "build_current_runtime_factory",
]
