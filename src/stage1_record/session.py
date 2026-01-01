"""Current Stage 1 deterministic workflow recording session."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.contracts import make_envelope
from stage0_launch.profile import actor_auth, resolve_actor_credentials

from .bundle_writer import BundleWriter
from .secrets import SecretRegistry
from .session_recorder import SessionRecorder

INITIAL_ACTION_ID = "initial"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class RecordingSession:
    """One actor-owned Stage 1 session, used only from its Playwright thread."""

    def __init__(
        self,
        *,
        env: Any,
        writer: BundleWriter,
        recorder: SessionRecorder,
        secrets: SecretRegistry,
        profile_path: Path,
        workflow_id: str,
        workflow_ref: str,
        actor_id: str,
        reset_epoch: str,
        business_started_at: str,
    ) -> None:
        self.env = env
        self.writer = writer
        self.recorder = recorder
        self.secrets = secrets
        self.profile_path = profile_path
        self.workflow_id = workflow_id
        self.workflow_ref = workflow_ref
        self.actor_id = actor_id
        self.reset_epoch = reset_epoch
        self.business_started_at = business_started_at
        self.started_at = business_started_at
        self._finished = False

    def snapshot(self, action_id: str) -> None:
        page = self.env.page
        self.writer.write_page_state(
            url=page.url,
            title=page.title(),
            dom_html=page.content(),
            action_id=action_id,
            captured_at=now_iso(),
        )

    def record_workflow_action(
        self,
        *,
        action_id: str,
        scenario_step_id: str,
        workflow_step_id: str,
        global_step_index: int,
        action_type: str,
        selector: str,
        page_url: str,
        element_accessibility: dict[str, Any],
        started_at: str,
        ended_at: str,
        locator_match_count: int | None,
        wait_results: list[dict[str, Any]],
        dialog_result: dict[str, str] | None = None,
        value: str | None = None,
        key: str | None = None,
        binding_material_source_step_ids: tuple[str, ...] = (),
    ) -> None:
        action = {
            "action_id": action_id,
            "timestamp": started_at,
            "action_type": action_type,
            "selector": selector,
            "page_url": page_url,
            "element_accessibility": element_accessibility,
            "scenario_step_id": scenario_step_id,
            "workflow_step_id": workflow_step_id,
            "global_step_index": global_step_index,
            "binding_material_source_step_ids": list(
                binding_material_source_step_ids
            ),
        }
        if value is not None:
            action["value"] = value
        if key is not None:
            action["key"] = key
        self.writer.append_ui_action(action)
        decision_detail = {
            "workflow_id": self.workflow_id,
            "scenario_step_id": scenario_step_id,
            "workflow_step_id": workflow_step_id,
            "global_step_index": global_step_index,
            "actor_id": self.actor_id,
            "action_type": action_type,
            "executed": True,
            "locator_match_count": locator_match_count,
            "wait_results": wait_results,
            "binding_material_source_step_ids": list(
                binding_material_source_step_ids
            ),
        }
        if dialog_result is not None:
            decision_detail["dialog_result"] = dialog_result
        self.writer.append_decision(
            {
                "timestamp": ended_at,
                "strategy": "deterministic_workflow",
                "action_id": action_id,
                "detail": decision_detail,
            }
        )
        self.snapshot(action_id)

    def finish(self) -> Path:
        if self._finished:
            return self.writer.bundle_dir / "manifest.json"
        self._finished = True
        self.recorder.finish(self.env.page)
        har = self.recorder.assemble_har()
        entries = har.get("log", {}).get("entries", [])
        har["log"]["entries"] = [
            item
            for item in entries
            if str(item.get("startedDateTime") or "") >= self.business_started_at
        ]
        metadata = make_envelope(
            artifact_type="session_bundle",
            stage="stage1",
            run_id=self.env.run_id,
            upstream_refs=[
                {
                    "artifact_type": "run_config",
                    "run_id": self.env.run_id,
                    "path": str(self.env.run_config_path),
                }
            ],
        )
        session_meta = {
            "system_under_test": self.profile_path.stem,
            "profile_ref": str(self.profile_path),
            "started_at": self.started_at,
            "ended_at": now_iso(),
            "auth_context": dict(self.env.run_config["auth_context"]),
            "workflow_id": self.workflow_id,
            "workflow_ref": self.workflow_ref,
            "actor_id": self.actor_id,
            "reset_epoch": self.reset_epoch,
            "business_barrier_at": self.business_started_at,
        }
        try:
            return self.writer.finalize(har=har, metadata=metadata, session=session_meta)
        finally:
            self.env.close()

    def abort(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.env.close()


def activate_recording_session(
    *,
    env: Any,
    profile_path: str | Path,
    actor_id: str,
    workflow_id: str,
    workflow_ref: str,
    reset_epoch: str,
    business_started_at: str,
) -> RecordingSession:
    """Activate M1 after authentication/bootstrap and the workflow barrier."""

    profile_path = Path(profile_path)
    secrets = SecretRegistry()
    selected_auth = actor_auth(env.profile, actor_id)
    if selected_auth.credentials_ref is not None:
        email, password = resolve_actor_credentials(env.profile, actor_id)
        secrets.register(email)
        secrets.register(password)
    if env.auth_token:
        secrets.register(env.auth_token)
    session = RecordingSession(
        env=env,
        writer=BundleWriter(env.run_dir / "session_bundle", secrets),
        recorder=env.recorder,
        secrets=secrets,
        profile_path=profile_path,
        workflow_id=workflow_id,
        workflow_ref=workflow_ref,
        actor_id=actor_id,
        reset_epoch=reset_epoch,
        business_started_at=business_started_at,
    )
    session.snapshot(INITIAL_ACTION_ID)
    return session
