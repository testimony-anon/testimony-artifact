"""Production replay adapter for deterministic UI-semantic two-arm verification."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from http.cookies import SimpleCookie
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from stage0_launch.profile import (
    AppProfile,
    SessionMaintenanceEndpoint,
    actor_auth,
    actor_session_initialization_endpoint,
)
from stage2_recover.loader import LoadedBundle, load_bundle
from .valuepath import BodyPathError, extract_value, set_body_value
from ui_semantics.replay_policy import (
    ReplayAdapter,
    SessionMaintenanceHandling,
    SetupSessionKind,
    SetupSessionPolicy,
)

from .http_client import response_set_cookies, send
from .resource_rebinding import (
    RecordedSetupRequest,
    ResourceRebindingError,
    SetupBindingPlan,
    apply_consumer_bindings,
    build_setup_binding_plan,
    capture_creator_values,
    scalar_sha256,
)
from .request_material import (
    input_action_matches_target_path,
)
from .test_execution import ActorSession, Transport, build_actor_sessions, reset_profile


class BaselineRequestShapeLossError(RuntimeError):
    """A recorded JSON body cannot be replayed without guessing its shape."""

    reason_code = "baseline_request_shape_loss"

    def __init__(self, *, request_ref: str | None, entry_index: int | None) -> None:
        location = []
        if request_ref is not None:
            location.append(f"request_ref={request_ref}")
        if entry_index is not None:
            location.append(f"entry_index={entry_index}")
        suffix = f" ({', '.join(location)})" if location else ""
        super().__init__(f"{self.reason_code}{suffix}")


class UnresolvedRequestMaterialError(RuntimeError):
    """Typed request material remains unresolved at the transport boundary."""

    reason_code = "unresolved_request_material"

    def __init__(self, *, request_ref: str | None, entry_index: int | None) -> None:
        location = []
        if request_ref is not None:
            location.append(f"request_ref={request_ref}")
        if entry_index is not None:
            location.append(f"entry_index={entry_index}")
        suffix = f" ({', '.join(location)})" if location else ""
        super().__init__(f"{self.reason_code}{suffix}")


@dataclass
class ReplayContext:
    sessions: dict[str, ActorSession]
    reset_ref: dict[str, Any]
    observation_sequence: int = 0
    resource_binding_plan: SetupBindingPlan | None = None
    resource_binding_values: dict[str, Any] = field(default_factory=dict)
    resource_binding_events: list[dict[str, Any]] = field(default_factory=list)
    material_aliases: tuple[dict[str, Any], ...] = ()
    request_material_bindings: tuple[dict[str, Any], ...] = ()
    request_material_environment: dict[str, str] = field(default_factory=dict)
    resolved_request_material_values: list[Any] = field(default_factory=list)
    resolved_request_material_targets: set[tuple[str, str, str]] = field(
        default_factory=set
    )


class SessionBundleReplayAdapter(ReplayAdapter):
    """Replay recorded request material under fresh actor sessions and resets."""

    _materialize_request = None
    _normalize_response = None

    def __init__(
        self,
        ui_trace: dict[str, Any],
        profile: AppProfile,
        *,
        transport: Transport = send,
        reset=None,
        login=None,
        materialize_request=None,
        normalize_response=None,
        recorded_bundles: Mapping[str, LoadedBundle] | None = None,
    ) -> None:
        self.ui_trace = ui_trace
        self.profile = profile
        self.transport = transport
        self._reset = reset or (lambda: reset_profile(profile))
        self._login = login
        self._materialize_request = materialize_request
        self._normalize_response = normalize_response
        self._requests = {item["request_ref"]: item for item in ui_trace["api_requests"]}
        self._bundles = self._normalized_bundles(
            (
                dict(recorded_bundles)
                if recorded_bundles is not None
                else self._load_bundles(ui_trace)
            ),
            ui_trace,
            profile,
        )
        self._session_initialization = self._session_initialization_endpoints(ui_trace)
        self._session_maintenance = self._session_maintenance_endpoints(ui_trace)

    def reset(self) -> tuple[ReplayContext, dict[str, Any]]:
        raw_ref = self._reset()
        ref = {
            "artifact_type": raw_ref.get("artifact_type", "ui_semantics_observation"),
            "run_id": raw_ref["run_id"],
            "record_id": raw_ref["record_id"],
        }
        sessions = build_actor_sessions(
            self.profile,
            [item["actor_id"] for item in self.ui_trace["actors"]],
            login=self._login,
        )
        return ReplayContext(
            sessions=sessions,
            reset_ref=ref,
            material_aliases=tuple(copy.deepcopy(raw_ref.get("material_aliases", ()))),
        ), ref

    def execute(self, context: ReplayContext, endpoint: dict[str, str]) -> dict[str, Any]:
        request_ref = endpoint["request_ref"]
        actor_id = endpoint["actor_id"]
        record = self._requests.get(request_ref)
        if record is None or record["actor_id"] != actor_id:
            raise ValueError(f"request/actor not present in ui_trace: {request_ref}")
        return self._execute_record(context, record)

    def prepare_setup(self, context: ReplayContext, setup: list[dict[str, str]]) -> None:
        if context.resource_binding_plan is not None:
            raise ValueError("setup material was already prepared for this replay context")
        records = []
        for order, endpoint in enumerate(setup):
            request_ref = endpoint["request_ref"]
            actor_id = endpoint["actor_id"]
            record = self._requests.get(request_ref)
            if record is None or record["actor_id"] != actor_id:
                raise ValueError(f"request/actor not present in ui_trace: {request_ref}")
            policy = self._policy_for_record(record)
            if policy.kind != SetupSessionKind.ORDINARY:
                records.append(
                    RecordedSetupRequest(
                        request_ref=request_ref,
                        actor_id=actor_id,
                        order=order,
                        method=record["method"],
                        request={},
                        response_status=0,
                        response_body=None,
                        ordinary=False,
                    )
                )
                continue
            entry = self._entry(record)
            self._request_value_for_record(record, entry)
            records.append(
                RecordedSetupRequest(
                    request_ref=request_ref,
                    actor_id=actor_id,
                    order=order,
                    method=record["method"],
                    request=entry["request"],
                    response_status=int(entry["response"]["status"]),
                    response_body=_response_value(entry),
                    ordinary=True,
                )
            )
        context.resource_binding_plan = build_setup_binding_plan(
            records,
            current_session_material=_all_session_material(context.sessions),
        )

    def execute_setup(
        self, context: ReplayContext, endpoint: dict[str, str]
    ) -> dict[str, Any]:
        if context.resource_binding_plan is None:
            raise ValueError("setup material was not prepared")
        request_ref = endpoint["request_ref"]
        actor_id = endpoint["actor_id"]
        record = self._requests.get(request_ref)
        if record is None or record["actor_id"] != actor_id:
            raise ValueError(f"request/actor not present in ui_trace: {request_ref}")
        return self._execute_record(context, record, setup_rebinding=True)

    def setup_session_policy(self, endpoint: dict[str, str]) -> SetupSessionPolicy:
        request_ref = endpoint["request_ref"]
        actor_id = endpoint["actor_id"]
        record = self._requests.get(request_ref)
        if record is None or record["actor_id"] != actor_id:
            raise ValueError(f"request/actor not present in ui_trace: {request_ref}")
        return self._policy_for_record(record)

    def is_session_initialization(self, endpoint: dict[str, str]) -> bool:
        """Compatibility alias; setup execution uses the typed policy method."""
        return self.setup_session_policy(endpoint).kind == SetupSessionKind.SESSION_INITIALIZATION

    def _apply_recorded_token_continuity(
        self,
        context: ReplayContext,
        *,
        actor_id: str,
        record: dict[str, Any],
        entry: Mapping[str, Any],
        response_body: Any,
    ) -> None:
        """Carry an in-band session token forward the way the recorded client did.

        Only actors without a declared auth config are handled here (declared
        sessions belong to the profile session layer).  The recording is the
        witness: a later request of the same session sent ``Authorization:
        <scheme> [REDACTED:h]`` and this response's recorded body carries the
        same marker at exactly one path, so the fresh value at that path is
        installed as the actor's Authorization header.
        """
        try:
            if actor_auth(self.profile, actor_id).method != "none":
                return
            bundles = getattr(self, "_bundles", None) or {}
            witness = _recorded_token_witness(
                bundles.get(str((record.get("observation_ref") or {}).get("run_id"))),
                record,
                entry,
            )
            if witness is None:
                return
            scheme, path = witness
            value = extract_value(response_body, path)
        except (BodyPathError, KeyError, TypeError, ValueError, IndexError, AttributeError):
            # Session continuity is best effort on top of the recorded witness;
            # an unresolvable witness never fails the replayed request itself.
            return
        if not isinstance(value, str) or not value or _REDACTION_MARKER.fullmatch(value):
            return
        session = context.sessions.get(actor_id)
        if session is None:
            return
        session.headers["Authorization"] = f"{scheme} {value}"

    def reinitialize_session(self, context: ReplayContext, actor_id: str) -> None:
        """Re-run the declared session initialization for one actor mid-setup.

        The recording authenticated the actor again after requests of its own
        (typically logout followed by login).  The recorded login body is
        redacted material and cannot be replayed, so the profile credentials
        establish the equivalent fresh session at the same point of the chain.
        """
        if actor_id not in context.sessions:
            raise ValueError(f"actor session is not part of this replay context: {actor_id}")
        fresh = build_actor_sessions(self.profile, [actor_id], login=self._login)
        context.sessions[actor_id] = fresh[actor_id]

    def _is_page_navigation(self, record: dict[str, Any]) -> bool:
        """A recorded browser document load (text/html) has no API effect to replay."""
        if str(record.get("method") or "").upper() != "GET":
            return False
        try:
            entry = self._entry(record)
        except (KeyError, TypeError, ValueError, IndexError):
            return False
        resource_type = str(entry.get("_resource_type") or "").strip().lower()
        content = (entry.get("response") or {}).get("content") or {}
        mime = str(content.get("mimeType") or "").strip().lower()
        return resource_type == "document" and mime.startswith("text/html")

    def _policy_for_record(self, record: dict[str, Any]) -> SetupSessionPolicy:
        actor_id = record["actor_id"]
        key = (record["method"].upper(), record["canonical_path"])
        declared = self._session_initialization.get(actor_id)
        if declared == key:
            return SetupSessionPolicy(SetupSessionKind.SESSION_INITIALIZATION)
        maintenance = self._session_maintenance.get(actor_id, {}).get(key)
        if maintenance is None:
            if self._is_page_navigation(record):
                return SetupSessionPolicy(SetupSessionKind.PAGE_NAVIGATION)
            return SetupSessionPolicy(SetupSessionKind.ORDINARY)
        return SetupSessionPolicy(
            SetupSessionKind.SESSION_MAINTENANCE,
            SessionMaintenanceHandling(maintenance.handling),
        )

    def execute_assignment(
        self,
        context: ReplayContext,
        endpoint: dict[str, str],
        *,
        location: str,
        field: str,
        value: Any,
    ) -> dict[str, Any]:
        record = self._requests.get(endpoint["request_ref"])
        if record is None or record["actor_id"] != endpoint["actor_id"]:
            raise ValueError("constraint target request/actor is not present in ui_trace")
        return self._execute_record(context, record, assignment=(location, field, value))

    def normalization_trace(self) -> dict[str, Any]:
        bindings = {item["event_id"]: item["request_ref"] for item in self.ui_trace["bindings"]}
        actions = []
        bundle_by_run = self._bundles
        for event in sorted(self.ui_trace["events"], key=lambda item: item["global_order"]):
            action_ref = event["action_ref"]
            bundle = bundle_by_run[action_ref["run_id"]]
            raw = next(item for item in bundle.actions if item["action_id"] == action_ref["action_id"])
            actions.append(
                {
                    "id": event["event_id"],
                    "actor": event["actor_id"],
                    "started_at_ms": event["global_order"],
                    "action_type": raw["action_type"],
                    "value": raw.get("value"),
                    "binding_v0": (
                        {"primary_request_id": bindings[event["event_id"]]}
                        if event["event_id"] in bindings
                        else None
                    ),
                }
            )
        requests = []
        for index, record in enumerate(self.ui_trace["api_requests"]):
            entry = self._entry(record)
            requests.append(
                {
                    "id": record["request_ref"],
                    "actor": record["actor_id"],
                    "started_at_ms": index,
                    "method": record["method"],
                    "path": record["canonical_path"],
                    "request_body": self._request_value_for_record(record, entry).get("body"),
                    "response_status": int(entry["response"]["status"]),
                    "response_body": _response_value(entry),
                }
            )
        return {"actions": actions, "api_requests": requests}

    def _execute_record(
        self,
        context: ReplayContext,
        record: dict[str, Any],
        assignment: tuple[str, str, Any] | None = None,
        *,
        setup_rebinding: bool = False,
    ) -> dict[str, Any]:
        actor_id = record["actor_id"]
        entry = self._entry(record)
        request = entry["request"]
        split = urlsplit(request["url"])
        path = split.path or "/"
        query = dict(parse_qsl(split.query, keep_blank_values=True))
        headers = dict(context.sessions[actor_id].headers)
        for item in request.get("headers", []):
            name = str(item.get("name") or "")
            if name.lower() in {"accept", "content-type"}:
                headers[name] = str(item.get("value") or "")
        request_value = self._request_value_for_record(record, entry)
        body = request_value.get("body", {})
        descriptor = self._request_material_descriptor(record)
        maintenance = self._session_maintenance.get(actor_id, {}).get(
            (record["method"].upper(), record["canonical_path"])
        )
        materialize = self._materialize_request
        plan = None
        if setup_rebinding:
            plan = context.resource_binding_plan
            if plan is None:
                raise ResourceRebindingError("setup binding plan is unavailable")
            _materialize_proven_header_targets(
                plan,
                request_ref=record["request_ref"],
                recorded_headers=request.get("headers", []),
                headers=headers,
            )
        if materialize is not None:
            path, query, headers, body = materialize(
                context, actor_id, path, query, headers, body
            )
        path, query, headers, body = self.materialize_request_material(
            context,
            request_ref=str(record["request_ref"]),
            actor_id=actor_id,
            path=path,
            query=query,
            headers=headers,
            body=body,
        )
        if not setup_rebinding:
            _assert_request_material_resolved(
                body,
                descriptor,
                request_ref=record.get("request_ref"),
                entry_index=(record.get("observation_ref") or {}).get("entry_index"),
            )
        if assignment is not None:
            location, field, value = assignment
            if location == "path":
                path = path.replace("{" + field + "}", str(value))
            elif location == "query":
                query[field] = value
            elif location == "header":
                headers[field] = str(value)
            elif location == "body":
                try:
                    set_body_value(body, field, value)
                except BodyPathError as error:
                    raise ValueError(f"invalid constraint body assignment: {field}") from error
            else:
                raise ValueError(f"unsupported constraint assignment location: {location}")
        if setup_rebinding:
            assert plan is not None
            path, query, headers, body = apply_consumer_bindings(
                plan,
                request_ref=record["request_ref"],
                path=path,
                query=query,
                headers=headers,
                body=body,
                values=context.resource_binding_values,
                events=context.resource_binding_events,
            )
            _assert_request_material_resolved(
                body,
                descriptor,
                request_ref=record.get("request_ref"),
                entry_index=(record.get("observation_ref") or {}).get("entry_index"),
            )
        _assert_transport_material_resolved(
            path,
            query,
            headers,
            body,
            request_ref=record.get("request_ref"),
            entry_index=(record.get("observation_ref") or {}).get("entry_index"),
        )
        if (
            maintenance is not None
            and maintenance.handling == "execute_and_update_session"
            and _contains_unsupported_session_material(
                {"path": unquote(path), "query": query, "body": body},
                _current_session_material(context.sessions[actor_id], maintenance),
            )
        ):
            raise ValueError(
                "session-maintenance request requires unsupported session body/query/path material"
            )
        url = self.profile.base_url.rstrip("/") + path
        if query:
            url += "?" + urlencode(query, doseq=True)
        body_text = _encode_recorded_body(request, body)
        response = self.transport(request["method"], url, headers, body_text)
        response_body = response.json()
        if response_body is None:
            response_body = response.body_text
        if (
            maintenance is not None
            and maintenance.handling == "execute_and_update_session"
            and 200 <= response.status < 400
        ):
            self._apply_session_maintenance_response(
                context,
                actor_id=actor_id,
                policy=maintenance,
                response=response,
            )
            response_body = _redact_session_maintenance_response(
                response_body,
                maintenance,
            )
        elif 200 <= response.status < 400 and (
            set_cookies := response_set_cookies(response)
        ):
            _update_cookie_header(context.sessions[actor_id], set_cookies)
        if 200 <= response.status < 400:
            self._apply_recorded_token_continuity(
                context, actor_id=actor_id, record=record, entry=entry, response_body=response_body
            )
        binding_response_body = copy.deepcopy(response_body)
        if setup_rebinding and 200 <= response.status < 400:
            assert plan is not None
            capture_creator_values(
                plan,
                request_ref=record["request_ref"],
                response_body=binding_response_body,
                values=context.resource_binding_values,
                events=context.resource_binding_events,
            )
        normalize = self._normalize_response
        if normalize is not None:
            response_body = normalize(context, actor_id, response_body)
        context.observation_sequence += 1
        result = {
            "status": response.status,
            "body": response_body,
            "request": {"body": response_body, "query": query, "path": path},
            "observation_ref": {
                "artifact_type": "ui_semantics_observation",
                "run_id": context.reset_ref["run_id"],
                "record_id": f"semantic-{context.observation_sequence:05d}",
            },
        }
        if setup_rebinding:
            result["binding_response_body"] = binding_response_body
        return result

    def producer_output_consumed(self, candidate: dict[str, Any]) -> bool:
        producer = self._entry(self._requests[candidate["producer"]["request_ref"]])
        consumer = self._entry(self._requests[candidate["consumer"]["request_ref"]])
        produced = _response_value(producer)
        consumed = self._request_value_for_record(
            self._requests[candidate["consumer"]["request_ref"]], consumer
        )
        consumed_values = {value for value in _scalar_values(consumed) if _hashable_scalar(value)}
        return any(value in consumed_values for value in _scalar_values(produced) if _hashable_scalar(value))

    def _entry(self, request: dict[str, Any]) -> dict[str, Any]:
        ref = request["observation_ref"]
        bundle = self._bundles.get(ref["run_id"])
        if bundle is None or ref["entry_index"] >= len(bundle.entries):
            raise ValueError("ui_trace request has an unresolved session-bundle observation")
        return bundle.entries[ref["entry_index"]]

    def _request_material_descriptor(
        self, record: dict[str, Any]
    ) -> dict[str, Any] | None:
        ref = record.get("observation_ref") or {}
        bundle = getattr(self, "_bundles", {}).get(ref.get("run_id"))
        if bundle is None:
            return None
        return bundle.request_material_shapes.get(ref.get("entry_index"))

    def materialize_request_material(
        self,
        context: ReplayContext,
        *,
        request_ref: str,
        actor_id: str,
        path: str,
        query: Mapping[str, Any],
        headers: Mapping[str, Any],
        body: Any,
    ) -> tuple[str, dict[str, Any], dict[str, Any], Any]:
        """Resolve proven recorded input material only at transport time."""

        bindings = [
            row
            for row in context.request_material_bindings
            if row.get("request_ref") == request_ref
        ]
        if not bindings:
            return path, dict(query), dict(headers), body
        targets = {
            (str(row.get("location") or ""), str(row.get("target_path") or ""))
            for row in bindings
        }
        if len(targets) != len(bindings):
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=None
            )
        record = self._requests.get(request_ref)
        if not isinstance(record, dict) or record.get("actor_id") != actor_id:
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=None
            )
        observation = record.get("observation_ref") or {}
        run_id = str(observation.get("run_id") or "")
        entry_index = observation.get("entry_index")
        bundle = self._bundles.get(run_id)
        if (
            bundle is None
            or not isinstance(entry_index, int)
            or isinstance(entry_index, bool)
        ):
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=None
            )
        target_events = [
            event
            for binding in self.ui_trace["bindings"]
            if binding["request_ref"] == request_ref
            for event in self.ui_trace["events"]
            if event["event_id"] == binding["event_id"]
        ]
        descriptor = bundle.request_material_shapes.get(entry_index)
        if len(target_events) != 1 or not isinstance(descriptor, Mapping):
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=entry_index
            )
        target_event = target_events[0]
        interval_start_global_order = max(
            (
                int(event["global_order"])
                for binding in self.ui_trace["bindings"]
                for event in self.ui_trace["events"]
                if event["event_id"] == binding["event_id"]
                and event.get("actor_id") == actor_id
                and event.get("action_ref", {}).get("run_id") == run_id
                and int(event.get("global_order", -1))
                < int(target_event.get("global_order", -1))
            ),
            default=-1,
        )
        visible_values = tuple(
            _visible_transport_scalars(path, query, headers, body)
        )
        possible_sources: list[
            tuple[Mapping[str, Any], Mapping[str, Any], Any]
        ] = []
        for possible_action in bundle.actions:
            if possible_action.get("action_type") not in {"fill", "type"}:
                continue
            possible_events = [
                event
                for event in self.ui_trace["events"]
                if event.get("action_ref") == {
                    "run_id": run_id,
                    "action_id": possible_action.get("action_id"),
                }
            ]
            possible_value = possible_action.get("value")
            if (
                len(possible_events) != 1
                or possible_events[0].get("actor_id") != actor_id
                or int(possible_events[0].get("global_order", -1))
                >= int(target_event.get("global_order", -1))
                or int(possible_events[0].get("global_order", -1))
                <= interval_start_global_order
                or (
                    possible_value is not None
                    and _request_material_scalar_type(possible_value) != "string"
                )
                or (
                    possible_value is not None
                    and any(
                        type(possible_value) is type(visible)
                        and possible_value == visible
                        for visible in visible_values
                    )
                )
            ):
                continue
            possible_sources.append(
                (possible_events[0], possible_action, possible_value)
            )
        binding_pairs = {
            (
                str(row.get("source_event_id") or ""),
                str((row.get("source_action_ref") or {}).get("action_id") or ""),
            )
            for row in bindings
        }
        possible_sources = [
            item
            for item in possible_sources
            if (
                str(item[0].get("event_id") or ""),
                str(item[1].get("action_id") or ""),
            )
            in binding_pairs
        ]
        if len(possible_sources) != len(bindings):
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=entry_index
            )
        possible_pairs = {
            (
                str(event.get("event_id") or ""),
                str(action.get("action_id") or ""),
            )
            for event, action, _value in possible_sources
        }
        resolved_pairs: set[tuple[str, str]] = set()
        materialized_body = copy.deepcopy(body)
        for binding in bindings:
            source_ref = binding.get("source_action_ref") or {}
            source_events = [
                event
                for event in self.ui_trace["events"]
                if event["event_id"] == binding.get("source_event_id")
            ]
            source_actions = [
                action
                for action in bundle.actions
                if action.get("action_id") == source_ref.get("action_id")
            ]
            if len(source_events) != 1 or len(source_actions) != 1:
                raise UnresolvedRequestMaterialError(
                    request_ref=request_ref, entry_index=entry_index
                )
            source_event = source_events[0]
            source_action = source_actions[0]
            value = source_action.get("value")
            target_path = str(binding.get("target_path") or "")
            source_material_kind = binding.get("source_material_kind")
            if source_material_kind == "workflow_value_env":
                if value is not None:
                    raise UnresolvedRequestMaterialError(
                        request_ref=request_ref, entry_index=entry_index
                    )
                environment_key = binding.get("source_value_env")
                if (
                    not isinstance(environment_key, str)
                    or set(context.request_material_environment) != {
                        str(row["source_value_env"])
                        for row in context.request_material_bindings
                        if row.get("source_material_kind") == "workflow_value_env"
                    }
                    or environment_key not in context.request_material_environment
                ):
                    raise UnresolvedRequestMaterialError(
                        request_ref=request_ref, entry_index=entry_index
                    )
                value = context.request_material_environment[environment_key]
            elif source_material_kind != "recorded_action_value" or value is None:
                raise UnresolvedRequestMaterialError(
                    request_ref=request_ref, entry_index=entry_index
                )
            try:
                marker = extract_value(materialized_body, target_path)
            except BodyPathError:
                raise UnresolvedRequestMaterialError(
                    request_ref=request_ref, entry_index=entry_index
                ) from None
            marker_match = (
                re.fullmatch(r"\[REDACTED:([0-9a-fA-F]+)\]", marker)
                if isinstance(marker, str)
                else None
            )
            marker_hash_prefix = (
                marker_match.group(1).lower()
                if marker_match is not None
                else None
            )
            descriptor_nodes = [
                node
                for node in descriptor.get("redactions", ())
                if _descriptor_typed_path(node.get("path")) == target_path
            ]
            if (
                binding.get("schema_version")
                != "uisemtest-current-recorded-input-material-binding-v1"
                or binding.get("provenance_kind")
                != "unique_preceding_unmatched_input"
                or binding.get("actor_id") != actor_id
                or binding.get("session_run_id") != run_id
                or binding.get("request_entry_index") != entry_index
                or binding.get("location") != "body"
                or source_ref.get("run_id") != run_id
                or (
                    str(source_event.get("event_id") or ""),
                    str(source_action.get("action_id") or ""),
                ) not in possible_pairs
                or (
                    len(bindings) > 1
                    and not input_action_matches_target_path(
                        source_action, source_event, target_path
                    )
                )
                or source_event.get("action_ref") != source_ref
                or source_event.get("actor_id") != actor_id
                or source_event.get("workflow_step_id")
                != binding.get("source_workflow_step_id")
                or (
                    source_material_kind == "workflow_value_env"
                    and source_event.get("global_step_index")
                    != binding.get("source_global_step_index")
                )
                or source_event.get("global_order")
                != binding.get("source_global_order")
                or target_event.get("event_id") != binding.get("target_event_id")
                or target_event.get("actor_id") != actor_id
                or target_event.get("action_ref", {}).get("run_id") != run_id
                or target_event.get("global_order")
                != binding.get("target_global_order")
                or int(source_event.get("global_order", -1))
                >= int(target_event.get("global_order", -1))
                or source_action.get("action_type") not in {"fill", "type"}
                or (
                    source_material_kind == "workflow_value_env"
                    and source_action.get("action_type")
                    != binding.get("source_action_kind")
                )
                or _canonical_sha256(source_action)
                != binding.get("source_action_sha256")
                or (
                    source_material_kind == "recorded_action_value"
                    and scalar_sha256(value) != binding.get("source_value_sha256")
                )
                or (
                    source_material_kind == "workflow_value_env"
                    and (
                        not isinstance(binding.get("source_workflow_ref"), str)
                        or not binding["source_workflow_ref"].startswith(
                            "inputs/recording/workflows/"
                        )
                        or re.fullmatch(
                            r"[0-9a-f]{64}",
                            str(binding.get("source_workflow_sha256") or ""),
                        )
                        is None
                        or re.fullmatch(
                            r"[0-9a-f]+",
                            str(binding.get("recorded_value_hash_prefix") or ""),
                        )
                        is None
                        or marker_hash_prefix
                        != binding.get("recorded_value_hash_prefix")
                    )
                )
                or _request_material_scalar_type(value)
                != binding.get("scalar_type")
                or len(descriptor_nodes) != 1
                or not isinstance(marker, str)
                or hashlib.sha256(marker.encode()).hexdigest()
                != binding.get("redaction_token_sha256")
            ):
                raise UnresolvedRequestMaterialError(
                    request_ref=request_ref, entry_index=entry_index
                )
            node = descriptor_nodes[0]
            placeholders = node.get("placeholders", ())
            if (
                node.get("runtime_material_required") is not True
                or node.get("redaction_form") != "whole_scalar"
                or node.get("original_scalar_type") != binding.get("scalar_type")
                or len(placeholders) != 1
                or placeholders[0].get("placeholder_sha256")
                != binding.get("redaction_token_sha256")
                or not any(
                    basis.get("source_class") == "explicit_registered_secret"
                    or (
                        basis.get("source_class") == "sensitive_key"
                        and basis.get("sensitive_key_match") == "exact_token"
                    )
                    for basis in placeholders[0].get("classification_bases", ())
                )
            ):
                raise UnresolvedRequestMaterialError(
                    request_ref=request_ref, entry_index=entry_index
                )
            try:
                set_body_value(materialized_body, target_path, copy.deepcopy(value))
            except (BodyPathError, TypeError, ValueError):
                raise UnresolvedRequestMaterialError(
                    request_ref=request_ref, entry_index=entry_index
                ) from None
            if not any(
                type(existing) is type(value) and existing == value
                for existing in context.resolved_request_material_values
            ):
                context.resolved_request_material_values.append(copy.deepcopy(value))
            context.resolved_request_material_targets.add(
                (actor_id, request_ref, target_path)
            )
            resolved_pairs.add(
                (
                    str(source_event.get("event_id") or ""),
                    str(source_action.get("action_id") or ""),
                )
            )
        if resolved_pairs != possible_pairs:
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=entry_index
            )
        return path, dict(query), dict(headers), materialized_body

    @staticmethod
    def _request_value_for_record(
        record: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        ref = record.get("observation_ref") or {}
        return _request_value(
            entry["request"],
            request_ref=record.get("request_ref"),
            entry_index=ref.get("entry_index"),
        )

    def _session_initialization_endpoints(
        self, ui_trace: dict[str, Any]
    ) -> dict[str, tuple[str, str] | None]:
        endpoints: dict[str, tuple[str, str] | None] = {}
        for actor in ui_trace["actors"]:
            actor_id = actor["actor_id"]
            endpoints[actor_id] = actor_session_initialization_endpoint(
                self.profile,
                actor_id,
            )
        return endpoints

    def _session_maintenance_endpoints(
        self, ui_trace: dict[str, Any]
    ) -> dict[str, dict[tuple[str, str], SessionMaintenanceEndpoint]]:
        endpoints: dict[str, dict[tuple[str, str], SessionMaintenanceEndpoint]] = {}
        for actor in ui_trace["actors"]:
            actor_id = actor["actor_id"]
            auth = actor_auth(self.profile, actor_id)
            endpoints[actor_id] = {
                (item.method.upper(), item.path): item
                for item in (auth.session_maintenance or [])
            }
        return endpoints

    def _apply_session_maintenance_response(
        self,
        context: ReplayContext,
        *,
        actor_id: str,
        policy: SessionMaintenanceEndpoint,
        response: Any,
    ) -> None:
        material = policy.response_material
        if material is None:
            raise ValueError("execute-and-update policy is missing response material")
        session = context.sessions[actor_id]
        auth = actor_auth(self.profile, actor_id)
        if material.kind == "api_token":
            token = extract_value(response.json(), material.token_json_path)
            if not isinstance(token, str) or not token:
                raise ValueError("session-maintenance response is missing the declared token")
            session.headers["Authorization"] = f"{auth.token_scheme} {token}"
            return
        _update_cookie_header(
            session,
            response_set_cookies(response),
            required_name=material.cookie_name,
        )

    @staticmethod
    def _load_bundles(ui_trace: dict[str, Any]) -> dict[str, LoadedBundle]:
        bundles = {}
        for actor in ui_trace["actors"]:
            ref = actor["session_bundle_ref"]
            bundle = load_bundle(ref["path"])
            if bundle.run_id != ref["run_id"]:
                raise ValueError("ui_trace session bundle run_id does not match the referenced bundle")
            bundles[bundle.run_id] = bundle
        return bundles

    @staticmethod
    def _normalized_bundles(
        bundles: dict[str, LoadedBundle],
        ui_trace: dict[str, Any],
        profile: AppProfile,
    ) -> dict[str, LoadedBundle]:
        """Build the private live-replay view from frozen trace paths and HAR query."""

        normalized = {
            run_id: replace(bundle, entries=copy.deepcopy(bundle.entries))
            for run_id, bundle in bundles.items()
        }
        assigned: dict[tuple[str, int], str] = {}
        for record in ui_trace["api_requests"]:
            ref = record["observation_ref"]
            run_id = str(ref["run_id"])
            entry_index = int(ref["entry_index"])
            bundle = normalized.get(run_id)
            if bundle is None or entry_index < 0 or entry_index >= len(bundle.entries):
                raise ValueError(
                    "ui_trace request has an unresolved session-bundle observation"
                )
            path = str(record["canonical_path"])
            key = (run_id, entry_index)
            previous = assigned.setdefault(key, path)
            if previous != path:
                raise ValueError("ui_trace observation has conflicting canonical paths")
            request = bundle.entries[entry_index]["request"]
            query = [
                (
                    str(item.get("name") or ""),
                    "" if item.get("value") is None else str(item["value"]),
                )
                for item in request.get("queryString", [])
            ]
            url = profile.base_url.rstrip("/") + path
            if query:
                url += "?" + urlencode(query)
            request["url"] = url
        return normalized


def _request_value(
    request: dict[str, Any],
    *,
    request_ref: str | None = None,
    entry_index: int | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "query": {item["name"]: item.get("value") for item in request.get("queryString", [])},
        "path": urlsplit(request.get("url") or "").path,
    }
    post = request.get("postData") or {}
    text = post.get("text")
    mime = str(post.get("mimeType") or "").lower()
    if "json" in mime and isinstance(text, str) and text:
        try:
            value["body"] = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            raise BaselineRequestShapeLossError(
                request_ref=request_ref,
                entry_index=entry_index,
            ) from None
        return value
    if text:
        try:
            value["body"] = json.loads(text)
        except json.JSONDecodeError:
            value["body"] = {item["name"]: item.get("value") for item in post.get("params", [])}
    else:
        value["body"] = {}
    return value


def _assert_request_material_resolved(
    body: Any,
    descriptor: dict[str, Any] | None,
    *,
    request_ref: str | None,
    entry_index: int | None,
) -> None:
    if descriptor is None:
        return
    for node in descriptor["redactions"]:
        current = body
        for segment in node["path"]:
            if segment["kind"] == "object_key":
                key = segment["key"]
                if not isinstance(current, dict) or key not in current:
                    raise UnresolvedRequestMaterialError(
                        request_ref=request_ref, entry_index=entry_index
                    )
                current = current[key]
            else:
                index = segment["index"]
                if not isinstance(current, list) or index >= len(current):
                    raise UnresolvedRequestMaterialError(
                        request_ref=request_ref, entry_index=entry_index
                    )
                current = current[index]
        if isinstance(current, str) and "[REDACTED" in current:
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=entry_index
            )
        expected_type = node["original_scalar_type"]
        if _request_material_scalar_type(current) != expected_type:
            raise UnresolvedRequestMaterialError(
                request_ref=request_ref, entry_index=entry_index
            )


def _descriptor_typed_path(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    path = "$"
    for segment in value:
        if not isinstance(segment, Mapping):
            return None
        if segment.get("kind") == "object_key":
            key = segment.get("key")
            if not isinstance(key, str) or re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", key
            ) is None:
                return None
            path += f".{key}"
        elif segment.get("kind") == "array_index":
            index = segment.get("index")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                return None
            path += f"[{index}]"
        else:
            return None
    return path


def _request_material_scalar_type(value: Any) -> str | None:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return None


def _visible_transport_scalars(
    path: str,
    query: Mapping[str, Any],
    headers: Mapping[str, Any],
    body: Any,
) -> list[Any]:
    values: list[Any] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif _request_material_scalar_type(value) is not None and not (
            isinstance(value, str) and _contains_unresolved_redacted(value)
        ):
            values.append(value)

    visit(query)
    visit(headers)
    visit(body)
    for segment in path.strip("/").split("/"):
        if segment:
            visit(segment)
    return values


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _assert_transport_material_resolved(
    path: str,
    query: Mapping[str, Any],
    headers: Mapping[str, Any],
    body: Any,
    *,
    request_ref: str | None,
    entry_index: int | None,
) -> None:
    if "[REDACTED:" in path or any(
        _contains_unresolved_redacted(value)
        for value in (query, headers, body)
    ):
        raise UnresolvedRequestMaterialError(
            request_ref=request_ref, entry_index=entry_index
        )


def _contains_unresolved_redacted(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_unresolved_redacted(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unresolved_redacted(item) for item in value)
    return isinstance(value, str) and "[REDACTED:" in value


def _response_value(entry: dict[str, Any]) -> Any:
    text = (entry.get("response", {}).get("content") or {}).get("text")
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


_REDACTION_MARKER = re.compile(r"^\[REDACTED:[0-9a-f]+\]$")
_TOKEN_HEADER = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9._-]*) (?P<marker>\[REDACTED:[0-9a-f]+\])$")


def _marker_paths(value: Any, marker: str, path: str = "$") -> list[str]:
    if isinstance(value, dict):
        return [
            found
            for key, item in value.items()
            for found in _marker_paths(item, marker, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            found
            for index, item in enumerate(value)
            for found in _marker_paths(item, marker, f"{path}[{index}]")
        ]
    return [path] if value == marker else []


def _recorded_token_witness(
    bundle: Any,
    record: Mapping[str, Any],
    entry: Mapping[str, Any],
) -> tuple[str, str] | None:
    """(scheme, response path) when a later recorded request of the same
    session carried this response's redacted token as its Authorization header."""

    if bundle is None:
        return None
    index = (record.get("observation_ref") or {}).get("entry_index")
    entries = getattr(bundle, "entries", None)
    if not isinstance(index, int) or not isinstance(entries, list):
        return None
    text = ((entry.get("response") or {}).get("content") or {}).get("text")
    if not isinstance(text, str) or not text:
        return None
    try:
        recorded_body = json.loads(text)
    except ValueError:
        return None
    for later in entries[index + 1:]:
        for header in (later.get("request") or {}).get("headers", []) or []:
            if str(header.get("name") or "").lower() != "authorization":
                continue
            match = _TOKEN_HEADER.fullmatch(str(header.get("value") or ""))
            if match is None:
                continue
            paths = _marker_paths(recorded_body, match.group("marker"))
            if len(paths) == 1:
                return match.group("scheme"), paths[0]
            return None
    return None


def _update_cookie_header(
    session: ActorSession,
    raw: str | Sequence[str],
    *,
    required_name: str | None = None,
) -> None:
    # One cookie per Set-Cookie header, so a response that sets several arrives as
    # several values. A single string keeps the former behaviour byte for byte; the
    # duplicate guard below still runs over the whole response.
    values = (raw,) if isinstance(raw, str) else tuple(raw)
    joined = ", ".join(values)
    jar = SimpleCookie()
    for value in values:
        jar.load(value)
    if required_name is not None and required_name not in jar:
        raise ValueError("session-maintenance response is missing the declared cookie")
    for name in jar:
        occurrences = re.findall(
            rf"(?:^|[;,]\s*){re.escape(name)}=", joined, flags=re.IGNORECASE
        )
        if len(occurrences) != 1:
            raise ValueError(
                "session-maintenance response contains duplicate declared cookies"
                if required_name is not None
                else "session response contains duplicate cookies"
            )
    current = SimpleCookie()
    current.load(session.headers.get("Cookie", ""))
    for name, morsel in jar.items():
        current[name] = morsel.value
    session.headers["Cookie"] = "; ".join(
        f"{name}={morsel.value}" for name, morsel in current.items()
    )


def _current_session_material(
    session: ActorSession,
    policy: SessionMaintenanceEndpoint,
) -> tuple[str, ...]:
    if policy.material_kind == "api_token":
        authorization = session.headers.get("Authorization", "")
        parts = authorization.split(" ", 1)
        return (parts[1],) if len(parts) == 2 and parts[1] else ()
    cookie_header = session.headers.get("Cookie", "")
    jar = SimpleCookie()
    jar.load(cookie_header)
    material = policy.response_material
    cookie_name = material.cookie_name if material is not None and material.kind == "cookie_session" else None
    if cookie_name and cookie_name in jar:
        return (jar[cookie_name].value,)
    return ()


def _all_session_material(sessions: dict[str, ActorSession]) -> tuple[str, ...]:
    values = []
    for session in sessions.values():
        authorization = session.headers.get("Authorization", "")
        if " " in authorization:
            values.append(authorization.split(" ", 1)[1])
        cookie_header = session.headers.get("Cookie", "")
        jar = SimpleCookie()
        jar.load(cookie_header)
        values.extend(morsel.value for morsel in jar.values())
    return tuple(value for value in values if value)


def _materialize_proven_header_targets(
    plan: SetupBindingPlan,
    *,
    request_ref: str,
    recorded_headers: list[dict[str, Any]],
    headers: dict[str, str],
) -> None:
    for use in plan.uses:
        if use.consumer_request_ref != request_ref or use.location != "header":
            continue
        name = use.target_path[2:] if use.target_path.startswith("$.") else ""
        matches = [
            row for row in recorded_headers if str(row.get("name") or "").lower() == name.lower()
        ]
        if len(matches) != 1:
            raise ResourceRebindingError("proven header target is not unique")
        headers[name] = str(matches[0].get("value") or "")


def _contains_unsupported_session_material(value: Any, secrets: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(_contains_unsupported_session_material(item, secrets) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unsupported_session_material(item, secrets) for item in value)
    return isinstance(value, str) and (
        "[REDACTED:" in value or any(secret and secret in value for secret in secrets)
    )


def _redact_session_maintenance_response(
    body: Any,
    policy: SessionMaintenanceEndpoint,
) -> Any:
    material = policy.response_material
    if material is None or material.kind != "api_token":
        return body
    if material.token_json_path == "$":
        return "[REDACTED:session_material]"
    if not isinstance(body, dict):
        return body
    redacted = copy.deepcopy(body)
    set_body_value(redacted, material.token_json_path, "[REDACTED:session_material]")
    return redacted


def _scalar_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _scalar_values(child)]
    if isinstance(value, list):
        return [item for child in value for item in _scalar_values(child)]
    return [value]


def _encode_recorded_body(request: dict[str, Any], body: Any) -> str | None:
    post = request.get("postData") or {}
    if not post:
        return None
    mime = str(post.get("mimeType") or "").lower()
    if "application/json" in mime:
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if "application/x-www-form-urlencoded" in mime:
        return urlencode(body, doseq=True)
    return post.get("text")


def _hashable_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and value not in {"", 0, False, None}
