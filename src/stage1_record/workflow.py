"""Typed current N-actor workflow loader, scheduler, and recorder."""

from __future__ import annotations

import json
import os
import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, Mapping
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field, model_validator

from common.contracts import REPO_ROOT, validate_artifact
from stage0_launch import run_recording_reset, run_stage0
from stage0_launch.profile import load_app_profile

from .session import RecordingSession, activate_recording_session, now_iso
from .session_recorder import SessionRecorder

ACTOR_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
FORBIDDEN_KEYS = {
    "expected_result", "predicate", "contract", "protocol", "protocol_kind",
    "control", "treatment", "confirmed", "refuted", "verdict",
}
PRIMITIVE_ACTION_TIMEOUT_MS = 120_000


class LocatorShape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["role", "label", "text", "test_id", "css"]
    value: str = Field(min_length=1)
    name: str | None = None
    exact: bool = True
    has_text: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_shape(self) -> "LocatorShape":
        if self.kind == "role" and not self.name:
            raise ValueError("role locator requires name")
        if self.kind != "role" and self.name is not None:
            raise ValueError("only role locator accepts name")
        return self


class ScopeLocator(LocatorShape):
    has_text_env: str | None = Field(default=None, pattern=ID_PATTERN)

    @model_validator(mode="after")
    def one_text_filter(self) -> "ScopeLocator":
        if self.has_text is not None and self.has_text_env is not None:
            raise ValueError("locator accepts only one text filter")
        return self


class Locator(LocatorShape):
    scope: ScopeLocator | None = None
    has_text_env: str | None = Field(default=None, pattern=ID_PATTERN)

    @model_validator(mode="after")
    def one_text_filter(self) -> "Locator":
        if self.has_text is not None and self.has_text_env is not None:
            raise ValueError("locator accepts only one text filter")
        return self


class WorkflowExecutionError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class PrimitiveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "navigate", "click", "fill", "type", "hover", "press", "select_option",
        "scroll_until_visible",
    ]
    locator: Locator | None = None
    scroll_locator: Locator | None = None
    url: str | None = None
    value: str | None = None
    value_env: str | None = Field(default=None, pattern=ID_PATTERN)
    key: str | None = None
    option: str | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=20)
    attempt_timeout_ms: int | None = Field(default=None, ge=1, le=30_000)
    optional_if_absent: bool = False
    accept_confirm: Literal[True] | None = None
    dismiss_confirm: Literal[True] | None = None
    close_alert: Literal[True] | None = None
    wait_for_clicked_target_detached: Literal[True] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "PrimitiveAction":
        if self.kind == "navigate":
            if not self.url or any(
                value is not None
                for value in (
                    self.locator, self.scroll_locator, self.value, self.value_env,
                    self.key, self.option, self.max_attempts, self.attempt_timeout_ms,
                    self.accept_confirm, self.dismiss_confirm, self.close_alert,
                    self.wait_for_clicked_target_detached,
                )
            ):
                raise ValueError("navigate requires only url")
            return self
        if self.locator is None or self.url is not None:
            raise ValueError(f"{self.kind} requires locator and no url")
        if self.kind in {"fill", "type"}:
            if (self.value is None) == (self.value_env is None):
                raise ValueError(
                    f"{self.kind} requires exactly one of value or value_env"
                )
        elif self.value is not None or self.value_env is not None:
            raise ValueError(f"{self.kind} does not accept value or value_env")
        required = {"press": self.key, "select_option": self.option}
        if self.kind in required and required[self.kind] is None:
            raise ValueError(f"{self.kind} requires its typed value")
        if self.kind == "scroll_until_visible":
            if any(
                value is None
                for value in (
                    self.scroll_locator, self.key, self.max_attempts,
                    self.attempt_timeout_ms,
                )
            ):
                raise ValueError(
                    "scroll_until_visible requires target locator, scroll_locator, "
                    "key, max_attempts, and attempt_timeout_ms"
                )
        elif any(
            value is not None
            for value in (self.scroll_locator, self.max_attempts, self.attempt_timeout_ms)
        ):
            raise ValueError(
                f"{self.kind} does not accept scroll_locator/max_attempts/attempt_timeout_ms"
            )
        dialog_controls = (
            self.accept_confirm, self.dismiss_confirm, self.close_alert,
        )
        if sum(value is not None for value in dialog_controls) > 1:
            raise ValueError("click accepts only one native dialog control")
        if any(value is not None for value in dialog_controls) and self.kind != "click":
            raise ValueError("native dialog controls are allowed only for click")
        if self.wait_for_clicked_target_detached is not None and self.kind != "click":
            raise ValueError("wait_for_clicked_target_detached is allowed only for click")
        return self


class LoadStateWait(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["load_state"]
    state: Literal["domcontentloaded", "load"]
    timeout_ms: int = Field(default=10_000, ge=1, le=120_000)


class UrlWait(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["url"]
    exact_url: str | None = None
    pattern: str | None = None
    timeout_ms: int = Field(default=10_000, ge=1, le=120_000)

    @model_validator(mode="after")
    def exactly_one(self) -> "UrlWait":
        if (self.exact_url is None) == (self.pattern is None):
            raise ValueError("url wait requires exactly one of exact_url or pattern")
        if self.pattern is not None:
            re.compile(self.pattern)
        return self


class LocatorWait(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["locator"]
    locator: Locator
    state: Literal["visible", "hidden", "attached", "detached"]
    timeout_ms: int = Field(default=10_000, ge=1, le=120_000)


class QuietWait(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["dom_quiet", "network_quiet"]
    quiet_ms: int = Field(ge=50, le=5_000)
    timeout_ms: int = Field(default=10_000, ge=1, le=120_000)


class DelayWait(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["bounded_delay"]
    duration_ms: int = Field(ge=1, le=5_000)


MechanicalWait = Annotated[
    LoadStateWait | UrlWait | LocatorWait | QuietWait | DelayWait,
    Field(discriminator="kind"),
]


class BootstrapStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bootstrap_step_id: str = Field(pattern=ID_PATTERN)
    action: PrimitiveAction
    waits: tuple[MechanicalWait, ...] = ()

    @model_validator(mode="after")
    def navigate_only(self) -> "BootstrapStep":
        if self.action.kind != "navigate":
            raise ValueError("bootstrap action must be navigate")
        return self


class WorkflowActor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str = Field(pattern=ACTOR_PATTERN)
    principal_group: str | None = Field(default=None, pattern=ID_PATTERN)
    session_ref: str | None = Field(default=None, pattern=ID_PATTERN)
    bootstrap: tuple[BootstrapStep, ...] = ()
    ready_waits: tuple[MechanicalWait, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ready_is_observable(self) -> "WorkflowActor":
        if all(item.kind == "bounded_delay" for item in self.ready_waits):
            raise ValueError("actor ready barrier cannot consist only of delay")
        return self


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_step_id: str = Field(pattern=ID_PATTERN)
    workflow_step_id: str = Field(pattern=ID_PATTERN)
    global_step_index: int = Field(ge=0)
    actor_id: str = Field(pattern=ACTOR_PATTERN)
    action: PrimitiveAction
    binding_material_source_step_ids: tuple[str, ...] = ()
    waits: tuple[MechanicalWait, ...] = ()

    @model_validator(mode="after")
    def business_action_is_required(self) -> "WorkflowStep":
        if self.action.optional_if_absent:
            raise ValueError("business workflow action cannot be optional")
        if len(self.binding_material_source_step_ids) != len(
            set(self.binding_material_source_step_ids)
        ):
            raise ValueError("binding material source step IDs must be unique")
        return self


class RecordingWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["uisemtest-recording-workflow-v1"]
    workflow_id: str = Field(pattern=ID_PATTERN)
    profile_ref: str
    actors: tuple[WorkflowActor, ...] = Field(min_length=1)
    steps: tuple[WorkflowStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def closure(self) -> "RecordingWorkflow":
        actor_ids = [item.actor_id for item in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("workflow actor IDs must be unique")
        session_refs = [actor.session_ref or actor.actor_id for actor in self.actors]
        if len(session_refs) != len(set(session_refs)):
            raise ValueError("workflow actor sessions must be independently named")
        step_ids = [item.workflow_step_id for item in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("workflow step IDs must be unique")
        if [item.global_step_index for item in self.steps] != list(range(len(self.steps))):
            raise ValueError("global_step_index must be contiguous and follow file order")
        unknown = sorted({item.actor_id for item in self.steps} - set(actor_ids))
        if unknown:
            raise ValueError(f"workflow steps reference unknown actors: {unknown}")
        steps_by_id = {item.workflow_step_id: item for item in self.steps}
        for step in self.steps:
            for source_id in step.binding_material_source_step_ids:
                source = steps_by_id.get(source_id)
                if source is None:
                    raise ValueError("binding material source step does not exist")
                if source.actor_id != step.actor_id:
                    raise ValueError("binding material source must belong to the same actor")
                if source.global_step_index >= step.global_step_index:
                    raise ValueError("binding material source must be strictly earlier")
                if source.action.kind not in {"input", "fill", "type"}:
                    raise ValueError("binding material source must be an input-like action")
                if source.action.value_env is not None:
                    raise ValueError("environment material cannot be binding evidence")
        path = PurePosixPath(self.profile_ref)
        if path.is_absolute() or ".." in path.parts or "\\" in self.profile_ref:
            raise ValueError("profile_ref must be repository-root-relative POSIX")
        return self


def load_recording_workflow(path: str | Path) -> RecordingWorkflow:
    workflow_path = Path(path).resolve(strict=True)
    raw = json.loads(workflow_path.read_text(encoding="utf-8"))
    _reject_semantic_oracles(raw)
    validate_artifact("recording_workflow.schema.json", raw)
    return RecordingWorkflow.model_validate(raw)


def _reject_semantic_oracles(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                raise ValueError(f"workflow contains forbidden semantic field: {'.'.join((*path, key))}")
            _reject_semantic_oracles(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_semantic_oracles(child, (*path, str(index)))


@dataclass
class _Command:
    kind: str
    payload: Any = None


class _ActorWorker(threading.Thread):
    def __init__(self, *, actor: WorkflowActor, profile_path: Path, workflow_path: Path,
                 workflow_id: str, actor_root: Path, headless: bool, reset_epoch: str) -> None:
        super().__init__(name=f"record-{actor.actor_id}", daemon=False)
        self.actor = actor
        self.profile_path = profile_path
        self.workflow_path = workflow_path
        self.workflow_id = workflow_id
        self.actor_root = actor_root
        self.headless = headless
        self.reset_epoch = reset_epoch
        self.commands: queue.Queue[_Command] = queue.Queue()
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.env: Any | None = None
        self.session: RecordingSession | None = None

    def run(self) -> None:
        try:
            recorder = SessionRecorder()
            self.env = run_stage0(
                self.profile_path, artifacts_root=self.actor_root, headless=self.headless,
                recorder=recorder, auth_mode="auto_login", actor_id=self.actor.actor_id,
            )
            bootstrap_results = [
                _execute_primitive(
                    self.env.page,
                    step.action,
                    step.waits,
                    bootstrap=True,
                    value_override=_action_material_value(step.action),
                )
                for step in self.actor.bootstrap
            ]
            ready_results = _execute_waits(self.env.page, self.actor.ready_waits)
            self.events.put({"status": "ready", "bootstrap": bootstrap_results, "ready": ready_results})
            while True:
                command = self.commands.get()
                if command.kind == "activate":
                    barrier_at = str(command.payload)
                    self.session = activate_recording_session(
                        env=self.env, profile_path=self.profile_path, actor_id=self.actor.actor_id,
                        workflow_id=self.workflow_id, workflow_ref=str(self.workflow_path),
                        reset_epoch=self.reset_epoch, business_started_at=barrier_at,
                    )
                    self.events.put({"status": "activated"})
                elif command.kind == "step":
                    self.events.put(self._execute_step(command.payload))
                elif command.kind == "finish":
                    if self.session is None:
                        raise RuntimeError("actor was never activated")
                    manifest = self.session.finish()
                    self.events.put(
                        {
                            "status": "finished",
                            "manifest": str(manifest),
                            "run_id": self.env.run_id,
                        }
                    )
                    return
                elif command.kind == "abort":
                    if self.session is not None:
                        self.session.abort()
                    elif self.env is not None:
                        self.env.close()
                    self.events.put({"status": "aborted"})
                    return
                else:
                    raise RuntimeError(f"unknown workflow command: {command.kind}")
        except BaseException as exc:
            if self.session is not None:
                try:
                    self.session.abort()
                except BaseException:
                    pass
            elif self.env is not None:
                try:
                    self.env.close()
                except BaseException:
                    pass
            self.events.put({"status": "failed", "reason_code": _reason_code(exc)})

    def _execute_step(self, step: WorkflowStep) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("business step dispatched before activation")
        action_id = f"workflow-action-{step.global_step_index:04d}"
        # Each business primitive owns a fresh pre-action observation.  Reusing
        # the previous action's post-state is not equivalent when another actor
        # has executed in between, or when the page changed asynchronously.
        self.session.snapshot(f"before:{action_id}")
        # Capture bodies of responses that completed after the previous step's
        # drain before this step can navigate away and evict them.
        _settle_recorder(self.session.recorder, self.session.env.page, timeout_ms=1500)
        started_at = now_iso()
        page_url = str(self.session.env.page.url)
        material_value = _action_material_value(step.action)
        for secret_value in _action_material_secrets(step.action):
            self.session.secrets.register(secret_value)
        result = _execute_primitive(
            self.session.env.page,
            step.action,
            step.waits,
            bootstrap=False,
            value_override=material_value,
        )
        _settle_recorder(self.session.recorder, self.session.env.page, timeout_ms=500)
        ended_at = now_iso()
        selector, accessibility = _action_observation(step.action)
        self.session.record_workflow_action(
            action_id=action_id, scenario_step_id=step.scenario_step_id,
            workflow_step_id=step.workflow_step_id,
            global_step_index=step.global_step_index, action_type=step.action.kind,
            selector=selector, page_url=page_url, element_accessibility=accessibility,
            started_at=started_at, ended_at=ended_at,
            locator_match_count=result["locator_match_count"], wait_results=result["wait_results"],
            dialog_result=result["dialog_result"],
            value=(
                step.action.value
                if step.action.kind in {"fill", "type"}
                and step.action.value_env is None
                else None
            ),
            key=step.action.key if step.action.kind == "press" else None,
            binding_material_source_step_ids=(
                step.binding_material_source_step_ids
            ),
        )
        return {
            "status": "step_completed", "scenario_step_id": step.scenario_step_id,
            "workflow_step_id": step.workflow_step_id,
            "global_step_index": step.global_step_index, "actor_id": step.actor_id,
            "action_id": action_id, "started_at": started_at, "ended_at": ended_at,
            "binding_material_source_step_ids": list(
                step.binding_material_source_step_ids
            ),
        }


def _locator(root: Any, spec: LocatorShape) -> Any:
    if spec.kind == "role":
        return root.get_by_role(spec.value, name=spec.name, exact=spec.exact)
    if spec.kind == "label":
        return root.get_by_label(spec.value, exact=spec.exact)
    if spec.kind == "text":
        return root.get_by_text(spec.value, exact=spec.exact)
    if spec.kind == "test_id":
        return root.get_by_test_id(spec.value)
    return root.locator(spec.value)


def _scoped_locator(page: Any, spec: Locator) -> Any:
    root = page
    if spec.scope is not None:
        root = _locator(page, spec.scope)
        if spec.scope.has_text is not None:
            root = root.filter(has_text=spec.scope.has_text)
        elif spec.scope.has_text_env is not None:
            root = root.filter(
                has_text=_required_env_material(spec.scope.has_text_env)
            )
        scope_count = root.count()
        if scope_count == 0:
            raise WorkflowExecutionError("scope_locator_missing")
        if scope_count > 1:
            raise WorkflowExecutionError("scope_locator_ambiguous")
    result = _locator(root, spec)
    if spec.has_text is not None:
        result = result.filter(has_text=spec.has_text)
    elif spec.has_text_env is not None:
        result = result.filter(has_text=_required_env_material(spec.has_text_env))
    return result


def _action_observation(action: PrimitiveAction) -> tuple[str, dict[str, Any]]:
    if action.locator is None:
        return "", {}
    rendered = json.dumps(
        action.locator.model_dump(exclude_none=True), ensure_ascii=False, sort_keys=True
    )
    accessibility = {}
    if action.locator.kind == "role":
        accessibility = {"role": action.locator.value, "name": action.locator.name}
    return rendered, accessibility


def _execute_primitive(
    page: Any,
    action: PrimitiveAction,
    waits: tuple[MechanicalWait, ...],
    *,
    bootstrap: bool,
    value_override: str | None = None,
) -> dict[str, Any]:
    match_count: int | None = None
    dialog_result: dict[str, str] | None = None
    clicked_target_detached = False
    try:
        if action.kind == "navigate":
            page.goto(urljoin(page.url, action.url), wait_until="domcontentloaded")
        elif action.kind == "scroll_until_visible":
            match_count = _scroll_until_visible(page, action)
        else:
            loc = _scoped_locator(page, action.locator)
            match_count = loc.count()
            if match_count == 0 and bootstrap and action.optional_if_absent:
                return {
                    "locator_match_count": 0,
                    "wait_results": _execute_waits(page, waits),
                }
            if match_count == 0:
                raise WorkflowExecutionError("locator_missing")
            if match_count > 1:
                raise WorkflowExecutionError("locator_ambiguous")
            if action.kind == "click":
                clicked_target = (
                    loc.element_handle()
                    if action.wait_for_clicked_target_detached
                    else None
                )
                if action.wait_for_clicked_target_detached and clicked_target is None:
                    raise WorkflowExecutionError("locator_missing")
                if action.accept_confirm:
                    dialog_result = _click_with_native_dialog(
                        page, loc, expected_type="confirm", disposition="accept"
                    )
                elif action.dismiss_confirm:
                    dialog_result = _click_with_native_dialog(
                        page, loc, expected_type="confirm", disposition="dismiss"
                    )
                elif action.close_alert:
                    dialog_result = _click_with_native_dialog(
                        page, loc, expected_type="alert", disposition="close"
                    )
                else:
                    loc.click(timeout=PRIMITIVE_ACTION_TIMEOUT_MS)
                if clicked_target is not None:
                    page.wait_for_function(
                        "(element) => !element.isConnected",
                        arg=clicked_target,
                        timeout=PRIMITIVE_ACTION_TIMEOUT_MS,
                    )
                    clicked_target_detached = True
            elif action.kind == "fill":
                loc.fill(
                    value_override if value_override is not None else action.value,
                    timeout=PRIMITIVE_ACTION_TIMEOUT_MS,
                )
            elif action.kind == "type":
                loc.press_sequentially(
                    value_override if value_override is not None else action.value,
                    timeout=PRIMITIVE_ACTION_TIMEOUT_MS,
                )
            elif action.kind == "hover":
                loc.hover(timeout=PRIMITIVE_ACTION_TIMEOUT_MS)
            elif action.kind == "press":
                loc.press(action.key, timeout=PRIMITIVE_ACTION_TIMEOUT_MS)
            elif action.kind == "select_option":
                loc.select_option(action.option, timeout=PRIMITIVE_ACTION_TIMEOUT_MS)
    except WorkflowExecutionError:
        raise
    except BaseException as exc:
        code = "action_timeout" if _is_timeout_exception(exc) else "action_failed"
        raise WorkflowExecutionError(code) from None
    return {
        "locator_match_count": match_count,
        "dialog_result": dialog_result,
        "clicked_target_detached": clicked_target_detached,
        "wait_results": _execute_waits(page, waits),
    }


def _click_with_native_dialog(
    page: Any,
    locator: Any,
    *,
    expected_type: Literal["alert", "confirm"],
    disposition: Literal["accept", "dismiss", "close"],
) -> dict[str, str]:
    """Click once and handle exactly one native alert or confirm fail-closed."""

    observation: dict[str, Any] = {
        "seen": False,
        "dialog_type": None,
        "handled": False,
        "handling_failed": False,
    }

    def handle(dialog: Any) -> None:
        observation["seen"] = True
        observation["dialog_type"] = str(dialog.type)
        if observation["dialog_type"] != expected_type:
            try:
                dialog.dismiss()
            except BaseException:
                observation["handling_failed"] = True
            return
        try:
            if disposition == "dismiss":
                dialog.dismiss()
            else:
                dialog.accept()
        except BaseException:
            observation["handling_failed"] = True
            try:
                dialog.dismiss()
            except BaseException:
                pass
        else:
            observation["handled"] = True

    page.once("dialog", handle)
    try:
        locator.click(timeout=PRIMITIVE_ACTION_TIMEOUT_MS)
    finally:
        try:
            page.remove_listener("dialog", handle)
        except BaseException:
            observation["handling_failed"] = True

    reason_prefix = f"{expected_type}_dialog"
    if not observation["seen"]:
        raise WorkflowExecutionError(f"{reason_prefix}_missing")
    if observation["dialog_type"] != expected_type:
        raise WorkflowExecutionError(f"{reason_prefix}_wrong_type")
    if observation["handling_failed"] or not observation["handled"]:
        raise WorkflowExecutionError(f"{reason_prefix}_failed")
    return {
        "dialog_type": expected_type,
        "disposition": disposition,
        "status": "handled",
    }


def _action_material_value(action: PrimitiveAction) -> str | None:
    if action.value_env is None:
        return None
    return _required_env_material(action.value_env)


def _required_env_material(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise WorkflowExecutionError("workflow_material_unavailable")
    return value


def _action_material_secrets(action: PrimitiveAction) -> tuple[str, ...]:
    names = []
    if action.value_env is not None:
        names.append(action.value_env)
    for locator in (action.locator, action.scroll_locator):
        if locator is None:
            continue
        if locator.has_text_env is not None:
            names.append(locator.has_text_env)
        if locator.scope is not None and locator.scope.has_text_env is not None:
            names.append(locator.scope.has_text_env)
    return tuple(_required_env_material(name) for name in dict.fromkeys(names))


def _scroll_until_visible(page: Any, action: PrimitiveAction) -> int:
    target = _scoped_locator(page, action.locator)
    scroller = _scoped_locator(page, action.scroll_locator)
    scroll_count = scroller.count()
    if scroll_count == 0:
        raise WorkflowExecutionError("scroll_locator_missing")
    if scroll_count > 1:
        raise WorkflowExecutionError("scroll_locator_ambiguous")
    for attempt in range(action.max_attempts + 1):
        count = target.count()
        if count > 1:
            raise WorkflowExecutionError("locator_ambiguous")
        if count == 1:
            try:
                target.wait_for(state="visible", timeout=action.attempt_timeout_ms)
                return count
            except BaseException as exc:
                if not _is_timeout_exception(exc):
                    raise WorkflowExecutionError("action_failed") from None
        if attempt < action.max_attempts:
            scroller.press(action.key)
            try:
                target.wait_for(
                    state="visible", timeout=action.attempt_timeout_ms
                )
            except BaseException as exc:
                if not _is_timeout_exception(exc):
                    raise WorkflowExecutionError("action_failed") from None
                continue
            count = target.count()
            if count > 1:
                raise WorkflowExecutionError("locator_ambiguous")
            if count == 1:
                return count
    raise WorkflowExecutionError("locator_missing")


def _execute_waits(
    page: Any, waits: tuple[MechanicalWait, ...]
) -> list[dict[str, Any]]:
    results = []
    for wait in waits:
        try:
            if wait.kind == "load_state":
                page.wait_for_load_state(wait.state, timeout=wait.timeout_ms)
            elif wait.kind == "url":
                target = (
                    wait.exact_url
                    if wait.exact_url is not None
                    else re.compile(wait.pattern)
                )
                page.wait_for_url(target, timeout=wait.timeout_ms)
            elif wait.kind == "locator":
                loc = _scoped_locator(page, wait.locator)
                count = loc.count()
                if count == 0 and wait.state in {"hidden", "detached"}:
                    pass
                elif count == 0:
                    loc.wait_for(state=wait.state, timeout=wait.timeout_ms)
                    count = loc.count()
                    if count == 0:
                        raise WorkflowExecutionError("wait_locator_missing")
                    if count > 1:
                        raise WorkflowExecutionError("wait_locator_ambiguous")
                elif count > 1:
                    raise WorkflowExecutionError("wait_locator_ambiguous")
                else:
                    loc.wait_for(state=wait.state, timeout=wait.timeout_ms)
            elif wait.kind == "network_quiet":
                page.wait_for_load_state("networkidle", timeout=wait.timeout_ms)
                page.wait_for_timeout(wait.quiet_ms)
            elif wait.kind == "dom_quiet":
                page.evaluate(
                    """([quietMs, timeoutMs]) => new Promise((resolve, reject) => {
                      let timer;
                      const deadline = setTimeout(() => {
                        observer.disconnect(); reject(new Error('dom_quiet_timeout'));
                      }, timeoutMs);
                      const done = () => {
                        clearTimeout(deadline); observer.disconnect(); resolve(true);
                      };
                      const arm = () => { clearTimeout(timer); timer = setTimeout(done, quietMs); };
                      const observer = new MutationObserver(arm);
                      observer.observe(document.documentElement, {subtree:true, childList:true, attributes:true});
                      arm();
                    })""",
                    [wait.quiet_ms, wait.timeout_ms],
                )
            elif wait.kind == "bounded_delay":
                page.wait_for_timeout(wait.duration_ms)
        except WorkflowExecutionError:
            raise
        except BaseException as exc:
            timed_out = wait.kind == "dom_quiet" or _is_timeout_exception(exc)
            raise WorkflowExecutionError(
                "wait_timeout" if timed_out else "wait_failed"
            ) from None
        results.append({"kind": wait.kind, "status": "satisfied"})
    return results


def _is_timeout_exception(exc: BaseException) -> bool:
    return "timeout" in type(exc).__name__.lower()


def _reason_code(exc: BaseException) -> str:
    if isinstance(exc, WorkflowExecutionError):
        return exc.reason_code
    if isinstance(exc, queue.Empty):
        return "worker_event_timeout"
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).lower()
    return f"unexpected_{name}"


def _event_reason(event: Mapping[str, Any]) -> str:
    value = str(event.get("reason_code") or "unexpected_worker_failure")
    return value if re.fullmatch(r"[a-z][a-z0-9_]*", value) else "unexpected_worker_failure"


def _join_workers(
    workers: Mapping[str, _ActorWorker], timeout_s: float
) -> bool:
    for worker in workers.values():
        worker.join(timeout=timeout_s)
    return all(not worker.is_alive() for worker in workers.values())


def _record_verified_actor_relations(workers: Mapping[str, _ActorWorker]) -> None:
    rows = list(workers.values())
    relations: list[dict[str, Any]] = []
    identity_keys = [
        getattr(worker.env, "authenticated_identity_key", None) for worker in rows
    ]
    if len(rows) > 1:
        if any(not isinstance(key, bytes) or not key for key in identity_keys):
            raise WorkflowExecutionError("actor_identity_missing")
        contexts = [getattr(worker.env, "context", None) for worker in rows]
        if any(context is None for context in contexts):
            raise WorkflowExecutionError("actor_session_missing")
        if len({id(context) for context in contexts}) != len(contexts):
            raise WorkflowExecutionError("actor_session_not_distinct")
        for index, left in enumerate(rows):
            for right_index in range(index + 1, len(rows)):
                right = rows[right_index]
                # Undeclared groups remain distinct.  A group name is only a
                # requested identity relation, never evidence of identity.
                same_principal = (
                    left.actor.principal_group is not None
                    and left.actor.principal_group == right.actor.principal_group
                )
                observed_same = identity_keys[index] == identity_keys[right_index]
                if observed_same != same_principal:
                    raise WorkflowExecutionError(
                        "actor_identity_not_same" if same_principal
                        else "actor_identity_not_distinct"
                    )
                relations.append({
                    "left_actor_id": left.actor.actor_id,
                    "right_actor_id": right.actor.actor_id,
                    "left_session_ref": left.actor.session_ref or left.actor.actor_id,
                    "right_session_ref": right.actor.session_ref or right.actor.actor_id,
                    "principal_relation": "same" if same_principal else "different",
                    "session_relation": "different",
                    "verification_source": "authenticated_probe",
                    "verified": True,
                })
    for worker in rows:
        auth = worker.env.run_config["auth_context"]
        auth["session_ref"] = worker.actor.session_ref or worker.actor.actor_id
        if len(rows) > 1:
            auth["actor_identity_distinct"] = len(set(identity_keys)) == len(rows)
            auth["identity_relations_verified"] = True
            auth["identity_relations"] = relations
        worker.env.run_config_path.write_text(
            json.dumps(worker.env.run_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def execute_recording_workflow(
    workflow_path: str | Path,
    *,
    artifacts_root: str | Path | None = None,
    headless: bool = True,
    worker_timeout_s: float = 180.0,
) -> dict[str, Any]:
    workflow_path = Path(workflow_path).resolve(strict=True)
    workflow = load_recording_workflow(workflow_path)
    profile_path = (REPO_ROOT / workflow.profile_ref).resolve(strict=True)
    if not profile_path.is_relative_to(REPO_ROOT.resolve()):
        raise ValueError("workflow profile_ref escapes repository root")
    profile = load_app_profile(profile_path)
    root = (
        Path(artifacts_root).resolve()
        if artifacts_root
        else REPO_ROOT / "artifacts" / "recordings" / workflow.workflow_id
    )
    root.mkdir(parents=True, exist_ok=False)
    result_path = root / "recording_workflow_result.json"
    try:
        reset = run_recording_reset(profile, root)
    except BaseException as exc:
        reset = {"status": "failed", "record_id": "unavailable", "artifact_ref": None}
        result = _workflow_result(
            workflow,
            workflow_path,
            profile_path,
            reset,
            {},
            [],
            {"phase": "reset", "reason_code": _reason_code(exc)},
            "rejected",
        )
        validate_artifact("recording_workflow_result.schema.json", result)
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {**result, "recording_root": str(root), "result_path": str(result_path)}
    workers = {
        actor.actor_id: _ActorWorker(
            actor=actor,
            profile_path=profile_path,
            workflow_path=workflow_path,
            workflow_id=workflow.workflow_id,
            actor_root=root / "actors" / actor.actor_id,
            headless=headless,
            reset_epoch=reset["record_id"],
        )
        for actor in workflow.actors
    }
    correspondence: list[dict[str, Any]] = []
    failure: dict[str, Any] | None = None
    manifests: dict[str, dict[str, str]] = {}
    for worker in workers.values():
        worker.start()
    try:
        for actor_id, worker in workers.items():
            try:
                event = worker.events.get(timeout=worker_timeout_s)
            except queue.Empty as exc:
                failure = {
                    "phase": "actor_ready",
                    "actor_id": actor_id,
                    "reason_code": _reason_code(exc),
                }
                raise WorkflowExecutionError(failure["reason_code"]) from None
            if event.get("status") != "ready":
                failure = {
                    "phase": "actor_ready",
                    "actor_id": actor_id,
                    "reason_code": _event_reason(event),
                }
                raise WorkflowExecutionError(failure["reason_code"])
        try:
            _record_verified_actor_relations(workers)
        except WorkflowExecutionError as exc:
            failure = {"phase": "actor_identity", "reason_code": exc.reason_code}
            raise
        barrier_at = now_iso()
        for worker in workers.values():
            worker.commands.put(_Command("activate", barrier_at))
        for actor_id, worker in workers.items():
            try:
                event = worker.events.get(timeout=worker_timeout_s)
            except queue.Empty as exc:
                failure = {
                    "phase": "actor_activation",
                    "actor_id": actor_id,
                    "reason_code": _reason_code(exc),
                }
                raise WorkflowExecutionError(failure["reason_code"]) from None
            if event.get("status") != "activated":
                failure = {
                    "phase": "actor_activation",
                    "actor_id": actor_id,
                    "reason_code": _event_reason(event),
                }
                raise WorkflowExecutionError(failure["reason_code"])
        for step in workflow.steps:
            worker = workers[step.actor_id]
            worker.commands.put(_Command("step", step))
            try:
                event = worker.events.get(timeout=worker_timeout_s)
            except queue.Empty as exc:
                event = {"status": "failed", "reason_code": _reason_code(exc)}
            if event.get("status") != "step_completed":
                failure = {
                    "phase": "business_step",
                    "scenario_step_id": step.scenario_step_id,
                    "workflow_step_id": step.workflow_step_id,
                    "global_step_index": step.global_step_index,
                    "actor_id": step.actor_id,
                    "reason_code": _event_reason(event),
                }
                raise WorkflowExecutionError(failure["reason_code"])
            correspondence.append(event)
        for worker in workers.values():
            worker.commands.put(_Command("finish"))
        for actor_id, worker in workers.items():
            try:
                event = worker.events.get(timeout=worker_timeout_s)
            except queue.Empty as exc:
                failure = {
                    "phase": "actor_finish",
                    "actor_id": actor_id,
                    "reason_code": _reason_code(exc),
                }
                raise WorkflowExecutionError(failure["reason_code"]) from None
            if event.get("status") != "finished":
                failure = {
                    "phase": "actor_finish",
                    "actor_id": actor_id,
                    "reason_code": _event_reason(event),
                }
                raise WorkflowExecutionError(failure["reason_code"])
            manifests[actor_id] = {
                "manifest_ref": Path(event["manifest"]).relative_to(root).as_posix(),
                "run_id": str(event["run_id"]),
            }
        if not _join_workers(workers, worker_timeout_s):
            failure = {
                "phase": "worker_shutdown",
                "reason_code": "worker_shutdown_timeout",
            }
            raise WorkflowExecutionError("worker_shutdown_timeout")
        result = _workflow_result(
            workflow, workflow_path, profile_path, reset, manifests,
            correspondence, None, "completed",
        )
    except BaseException as exc:
        if failure is None:
            failure = {"phase": "workflow", "reason_code": _reason_code(exc)}
        for worker in workers.values():
            if worker.is_alive():
                worker.commands.put(_Command("abort"))
        if not _join_workers(workers, worker_timeout_s):
            failure = {
                "phase": "worker_shutdown",
                "reason_code": "worker_shutdown_timeout",
            }
        result = _workflow_result(
            workflow, workflow_path, profile_path, reset, manifests,
            correspondence, failure, "rejected",
        )
    validate_artifact("recording_workflow_result.schema.json", result)
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {**result, "recording_root": str(root), "result_path": str(result_path)}


def _workflow_result(
    workflow: RecordingWorkflow,
    workflow_path: Path,
    profile_path: Path,
    reset: dict[str, Any],
    manifests: dict[str, dict[str, str]],
    correspondence: list[dict[str, Any]],
    failure: dict[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    return {
        "schema_version": "uisemtest-recording-workflow-result-v1",
        "status": status,
        "workflow_id": workflow.workflow_id,
        "workflow_ref": str(workflow_path),
        "profile_ref": str(profile_path),
        "reset_epoch": reset,
        "actor_bundles": [
            {"actor_id": actor_id, **manifest}
            for actor_id, manifest in sorted(manifests.items())
        ],
        "step_correspondence": correspondence,
        "failure": failure,
    }


def _settle_recorder(recorder: Any, page: Any, *, timeout_ms: int) -> None:
    """Pull finished response bodies before/after a step (bounded wait)."""
    settle = getattr(recorder, "settle", None)
    if callable(settle):
        settle(page, timeout_ms=timeout_ms)
    else:
        recorder.drain_pending_bodies()
