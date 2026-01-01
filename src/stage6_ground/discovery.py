"""Scheduled discovery runner for 013.

Runs a replay prefix with fresh values, then inserts one raw probe request that
is not yet an augmented OAS operation.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode

from .config import ReplayConfig
from .http_client import HttpResult, business_success, send
from .replay import ReplayClient, StepResult, _classify_failure, _response_envelope
from .valuepath import BodyPathError, set_body_value

BODY_BEARING_METHODS = {"POST", "PUT", "PATCH"}
_REDACTED_RE = re.compile(r"^\[REDACTED:[^\]]+\]$")


@dataclass
class RawProbeStep:
    method: str
    canonical_path: str | None = None
    candidate_url: str | None = None
    operation_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body_template: Any | None = None
    generated_body_fields: list[str] = field(default_factory=list)


@dataclass
class ScheduledProbeRun:
    prefix_passed: bool
    prefix_steps: list[StepResult]
    responses: dict
    probe_sent: bool
    probe_request: dict | None = None
    probe_response: HttpResult | None = None
    probe_success: bool = False
    probe_bindings_resolved: list[dict] = field(default_factory=list)
    runtime_secret_bindings: list[dict] = field(default_factory=list)
    audit_secret_values: list[str] = field(default_factory=list)
    literal_assumptions: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass
class _PreparedBody:
    body: Any | None
    send_body: bool
    runtime_secret_bindings: list[dict] = field(default_factory=list)
    literal_assumptions: list[dict] = field(default_factory=list)
    error: str | None = None


class ScheduledDiscoveryRunner:
    """Controlled Stage6-side entry for prefix replay + one raw discovery probe."""

    def __init__(self, cfg: ReplayConfig, op_index: dict, throttle=None):
        self.cfg = cfg
        self.client = ReplayClient(cfg, op_index, throttle)

    def run_probe(
        self,
        prefix_steps: list[str],
        bindings: list[dict],
        parameters: list[dict],
        raw_probe: RawProbeStep,
        prefix_body_templates: dict[int, Any] | None = None,
    ) -> ScheduledProbeRun:
        responses: dict = {}
        prefix_results: list[StepResult] = []
        prefix_body_templates = prefix_body_templates or {}
        prefix_runtime_secret_bindings: list[dict] = []

        for i, op_id in enumerate(prefix_steps):
            initial_body = deepcopy(prefix_body_templates[i]) if i in prefix_body_templates else None
            if initial_body is not None:
                try:
                    initial_body = self._replace_redacted_placeholders(
                        initial_body,
                        set(),
                        prefix_runtime_secret_bindings,
                    )
                except _UnresolvedRedactedPlaceholder as exc:
                    error = str(exc)
                    prefix_results.append(StepResult(i, op_id, False, None, error, []))
                    return ScheduledProbeRun(
                        False,
                        prefix_results,
                        responses,
                        False,
                        runtime_secret_bindings=prefix_runtime_secret_bindings,
                        error=error,
                    )
            pv, qv, body, headers, resolved_log, bind_failed = self.client._gather_inputs(
                i, bindings, parameters, responses, None, initial_body=initial_body
            )
            if bind_failed is not None:
                error = _bind_error(bind_failed)
                prefix_results.append(StepResult(i, op_id, False, None, error, resolved_log))
                return ScheduledProbeRun(
                    False,
                    prefix_results,
                    responses,
                    False,
                    runtime_secret_bindings=prefix_runtime_secret_bindings,
                    error=error,
                )

            method, url, hdrs, body_text = self.client._build_request(op_id, pv, qv, body, headers)
            self.client.throttle.wait()
            res = send(method, url, hdrs, body_text)
            ok = business_success(res)
            doc = res.json()
            prefix_results.append(
                StepResult(i, op_id, ok, res.status, None if ok else _classify_failure(res), resolved_log)
            )
            if not ok:
                return ScheduledProbeRun(
                    False,
                    prefix_results,
                    responses,
                    False,
                    runtime_secret_bindings=prefix_runtime_secret_bindings,
                    error=_classify_failure(res),
                )
            responses[i] = _response_envelope(res, doc if isinstance(doc, (dict, list)) else None)

        probe_step = len(prefix_steps)
        prepared = self._prepare_probe_body(raw_probe, bindings, parameters, probe_step)
        if prepared.error is not None:
            return ScheduledProbeRun(
                True,
                prefix_results,
                responses,
                False,
                runtime_secret_bindings=[
                    *prefix_runtime_secret_bindings,
                    *prepared.runtime_secret_bindings,
                ],
                error=prepared.error,
            )

        pv, qv, body, headers, resolved_log, bind_failed = self.client._gather_inputs(
            probe_step, bindings, parameters, responses, None, initial_body=prepared.body
        )
        if bind_failed is not None:
            return ScheduledProbeRun(
                True,
                prefix_results,
                responses,
                False,
                probe_bindings_resolved=resolved_log,
                runtime_secret_bindings=[
                    *prefix_runtime_secret_bindings,
                    *prepared.runtime_secret_bindings,
                ],
                literal_assumptions=prepared.literal_assumptions,
                error=_bind_error(bind_failed),
            )

        method, url, hdrs, body_text, audit_body_text = self._build_raw_request(
            raw_probe,
            pv,
            qv,
            body,
            headers,
            prepared.send_body,
            prepared.runtime_secret_bindings,
        )
        self.client.throttle.wait()
        res = send(method, url, hdrs, body_text)
        ok = business_success(res)
        request = {"method": method, "url": url}
        if hdrs:
            request["headers"] = _audit_headers(hdrs)
        if audit_body_text is not None:
            request["body"] = audit_body_text
        return ScheduledProbeRun(
            True,
            prefix_results,
            responses,
            True,
            probe_request=request,
            probe_response=res,
            probe_success=ok,
            probe_bindings_resolved=resolved_log,
            runtime_secret_bindings=[
                *prefix_runtime_secret_bindings,
                *prepared.runtime_secret_bindings,
            ],
            audit_secret_values=_auth_secret_values(hdrs),
            literal_assumptions=prepared.literal_assumptions,
        )

    def _prepare_probe_body(
        self,
        raw_probe: RawProbeStep,
        bindings: list[dict],
        parameters: list[dict],
        probe_step: int,
    ) -> _PreparedBody:
        method = raw_probe.method.upper()
        has_template = raw_probe.body_template is not None
        if method in BODY_BEARING_METHODS and not has_template:
            return _PreparedBody(None, False, error="missing_body_template")
        if not has_template:
            return _PreparedBody(None, False)

        parsed, error = _parse_body_template(raw_probe.body_template)
        if error is not None:
            return _PreparedBody(None, False, error=error)

        fresh_body_fields = _body_binding_fields(bindings, probe_step)
        parameter_body_fields = _body_parameter_fields(parameters, probe_step)
        generated_body_fields = set(raw_probe.generated_body_fields or [])
        overlay_fields = fresh_body_fields | parameter_body_fields | generated_body_fields
        runtime_secret_bindings: list[dict] = []
        try:
            body = self._replace_redacted_placeholders(
                parsed,
                fresh_body_fields,
                runtime_secret_bindings,
            )
        except _UnresolvedRedactedPlaceholder as exc:
            return _PreparedBody(None, False, error=str(exc))

        literal_assumptions = _literal_assumptions(
            parsed,
            overlay_fields,
            {b["field"] for b in runtime_secret_bindings},
        )
        return _PreparedBody(body, True, runtime_secret_bindings, literal_assumptions)

    def _replace_redacted_placeholders(
        self,
        value: Any,
        fresh_body_fields: set[str],
        runtime_secret_bindings: list[dict],
        path: str = "$",
    ) -> Any:
        if isinstance(value, dict):
            return {
                k: self._replace_redacted_placeholders(
                    v,
                    fresh_body_fields,
                    runtime_secret_bindings,
                    _child_path(path, k),
                )
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [
                self._replace_redacted_placeholders(
                    v,
                    fresh_body_fields,
                    runtime_secret_bindings,
                    f"{path}[{i}]",
                )
                for i, v in enumerate(value)
            ]
        if isinstance(value, str) and _REDACTED_RE.fullmatch(value):
            if path in fresh_body_fields:
                return None
            runtime_value = self.cfg.value_for("body", path)
            if runtime_value is None:
                raise _UnresolvedRedactedPlaceholder(f"unresolved_redacted_placeholder: {path}")
            runtime_secret_bindings.append({
                "location": "body",
                "field": path,
                "source": "replay_config",
            })
            return runtime_value
        return deepcopy(value)

    def _build_raw_request(
        self,
        raw_probe: RawProbeStep,
        path_vals: dict,
        query_vals: dict,
        body: Any,
        headers: dict,
        send_body: bool,
        runtime_secret_bindings: list[dict],
    ) -> tuple[str, str, dict, str | None, str | None]:
        target = raw_probe.candidate_url or raw_probe.canonical_path
        if not target:
            raise ValueError("raw probe requires canonical_path or candidate_url")
        url = _apply_path_values(target, path_vals)
        if not _is_absolute_url(url):
            url = self.cfg.base_url + url
        if query_vals:
            url += ("&" if "?" in url else "?") + urlencode({k: str(v) for k, v in query_vals.items()})
        merged_headers = {**raw_probe.headers, **headers}
        if self.cfg.auth_token and not any(str(k).lower() == "authorization" for k in merged_headers):
            merged_headers["Authorization"] = f"{self.cfg.token_scheme} {self.cfg.auth_token}"
        if self.cfg.session_cookie_header and not any(str(k).lower() == "cookie" for k in merged_headers):
            merged_headers["Cookie"] = self.cfg.session_cookie_header
        body_text = json.dumps(body, ensure_ascii=False) if send_body or body else None
        audit_body_text = None
        if body_text is not None:
            audit_body = _audit_body(body, runtime_secret_bindings)
            audit_body_text = json.dumps(audit_body, ensure_ascii=False)
        return raw_probe.method.upper(), url, merged_headers, body_text, audit_body_text


class _UnresolvedRedactedPlaceholder(Exception):
    pass


def _parse_body_template(template: Any) -> tuple[Any | None, str | None]:
    if isinstance(template, str):
        try:
            template = json.loads(template)
        except json.JSONDecodeError:
            return None, "invalid_body_template_json"
    if not isinstance(template, (dict, list)):
        return None, "invalid_body_template"
    return deepcopy(template), None


def _body_binding_fields(bindings: list[dict], probe_step: int) -> set[str]:
    return {
        str(binding["to_field"])
        for binding in bindings
        if binding.get("to_step") == probe_step and binding.get("to_location") == "body"
    }


def _body_parameter_fields(parameters: list[dict], probe_step: int) -> set[str]:
    return {
        str(parameter["to_field"])
        for parameter in parameters
        if parameter.get("to_step") == probe_step and parameter.get("to_location") == "body"
    }


def _literal_assumptions(template: Any, overlay_fields: set[str], runtime_secret_fields: set[str]) -> list[dict]:
    out = []
    for path, value in _iter_leaves(template):
        if path in overlay_fields or path in runtime_secret_fields:
            continue
        if isinstance(value, str) and _REDACTED_RE.fullmatch(value):
            continue
        if isinstance(value, (str, int, float, bool)):
            out.append({
                "location": "body",
                "field": path,
                "reason": "recorded_literal_assumption",
            })
    return out


def _iter_leaves(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _iter_leaves(child, _child_path(path, key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _iter_leaves(child, f"{path}[{i}]")
    else:
        yield path, value


def _child_path(path: str, key: str) -> str:
    return f"$.{key}" if path == "$" else f"{path}.{key}"


def _audit_body(body: Any, runtime_secret_bindings: list[dict]) -> Any:
    audit = deepcopy(body)
    for binding in runtime_secret_bindings:
        try:
            set_body_value(audit, binding["field"], "[REDACTED:runtime_secret]")
        except (BodyPathError, ValueError):
            continue
    return audit


def _audit_headers(headers: dict) -> dict:
    out = {}
    for key, value in headers.items():
        if str(key).lower() == "authorization":
            out[key] = _redacted_authorization(str(value))
        elif str(key).lower() == "cookie":
            out[key] = _redacted_cookie(str(value))
        else:
            out[key] = value
    return out


def _redacted_authorization(value: str) -> str:
    parts = value.split(None, 1)
    if len(parts) == 2:
        return f"{parts[0]} [REDACTED:auth_token]"
    return "[REDACTED:auth_token]"


def _redacted_cookie(value: str) -> str:
    parts = []
    for chunk in value.split(";"):
        item = chunk.strip()
        if not item:
            continue
        if "=" in item:
            name, _raw = item.split("=", 1)
            parts.append(f"{name.strip()}=[REDACTED:session_cookie]")
        else:
            parts.append("[REDACTED:session_cookie]")
    return "; ".join(parts) if parts else "[REDACTED:session_cookie]"


def _auth_secret_values(headers: dict) -> list[str]:
    values = []
    for key, value in headers.items():
        key_lower = str(key).lower()
        text = str(value)
        if key_lower == "authorization" and text:
            values.append(text)
            parts = text.split(None, 1)
            if len(parts) == 2 and parts[1]:
                values.append(parts[1])
        elif key_lower == "cookie" and text:
            values.append(text)
            for chunk in text.split(";"):
                item = chunk.strip()
                if "=" in item:
                    _name, raw = item.split("=", 1)
                    if raw:
                        values.append(raw)
    return sorted(set(values), key=len, reverse=True)


def _apply_path_values(path: str, path_vals: dict) -> str:
    out = path
    for name, value in path_vals.items():
        out = out.replace("{" + name + "}", quote(str(value), safe=""))
    return out


def _is_absolute_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _bind_error(bind_failed: dict) -> str:
    reason = bind_failed.get("reason", "producer_value_missing")
    field = bind_failed.get("from_field", bind_failed.get("to_field", "?"))
    src = f" from step{bind_failed['from_step']}" if "from_step" in bind_failed else ""
    return f"bind_fail(inconclusive_setup): {reason} @ {field}{src}"
