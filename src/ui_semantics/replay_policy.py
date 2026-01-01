"""Execution-only replay protocol shared by current and compatibility code."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class SetupSessionKind(str, Enum):
    ORDINARY = "ordinary"
    SESSION_INITIALIZATION = "session_initialization"
    SESSION_MAINTENANCE = "session_maintenance"
    # A recorded browser document load (text/html page) carries no API effect;
    # replaying it against the API origin only produces a spurious 404.
    PAGE_NAVIGATION = "page_navigation"


class SessionMaintenanceHandling(str, Enum):
    FRESH_SESSION_SATISFIES = "fresh_session_satisfies"
    EXECUTE_AND_UPDATE_SESSION = "execute_and_update_session"


@dataclass(frozen=True)
class SetupSessionPolicy:
    kind: SetupSessionKind
    handling: SessionMaintenanceHandling | None = None

    def __post_init__(self) -> None:
        if self.kind == SetupSessionKind.SESSION_MAINTENANCE:
            if self.handling is None:
                raise ValueError("session-maintenance policy requires handling")
        elif self.handling is not None:
            raise ValueError("only session-maintenance policy may carry handling")

    @property
    def skip_setup(self) -> bool:
        return self.kind in {
            SetupSessionKind.SESSION_INITIALIZATION,
            SetupSessionKind.PAGE_NAVIGATION,
        } or (
            self.kind == SetupSessionKind.SESSION_MAINTENANCE
            and self.handling == SessionMaintenanceHandling.FRESH_SESSION_SATISFIES
        )


class ReplayAdapter(Protocol):
    def reset(self) -> tuple[Any, dict[str, Any]]: ...

    def execute(self, context: Any, endpoint: dict[str, str]) -> dict[str, Any]: ...

    def prepare_setup(self, context: Any, setup: list[dict[str, str]]) -> None: ...

    def execute_setup(self, context: Any, endpoint: dict[str, str]) -> dict[str, Any]: ...

    def producer_output_consumed(self, candidate: dict[str, Any]) -> bool: ...

    def setup_session_policy(self, endpoint: dict[str, str]) -> SetupSessionPolicy: ...
