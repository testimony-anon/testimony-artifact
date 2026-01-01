"""Stage 6 execution and normal-control calibration for typed test suites."""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import quote, urlencode

from common.contracts import REPO_ROOT, make_envelope, validate_artifact
from stage0_launch.profile import AppProfile, actor_auth, load_app_profile, resolve_actor_credentials
from ui_semantics.dsl import evaluate_predicate

from .http_client import HttpResult, response_set_cookies, send
from .replay import build_op_index
from .valuepath import BodyPathError, extract_value, set_body_value


class Transport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body_text: str | None,
    ) -> HttpResult: ...


@dataclass(frozen=True)
class ActorSession:
    actor_id: str
    headers: dict[str, str]


@dataclass(frozen=True)
class EncodedBody:
    body_text: str | None
    content_type: str | None


def encode_body(body: dict[str, Any], encoding: str) -> EncodedBody:
    if encoding == "none":
        if body:
            raise ValueError("body_encoding=none cannot carry body assignments")
        return EncodedBody(None, None)
    if encoding == "json":
        return EncodedBody(json.dumps(body, ensure_ascii=False, separators=(",", ":")), "application/json")
    if encoding == "form_urlencoded":
        return EncodedBody(urlencode(body, doseq=True), "application/x-www-form-urlencoded")
    if encoding == "multipart":
        boundary = "carverflow-boundary"
        lines = []
        for name, value in sorted(body.items()):
            values = value if isinstance(value, list) else [value]
            for item in values:
                lines.extend(
                    [
                        f"--{boundary}",
                        f'Content-Disposition: form-data; name="{name}"',
                        "",
                        str(item),
                    ]
                )
        lines.extend([f"--{boundary}--", ""])
        return EncodedBody("\r\n".join(lines), f"multipart/form-data; boundary={boundary}")
    raise ValueError(f"unsupported body encoding: {encoding}")


def build_actor_sessions(
    profile: AppProfile,
    actor_ids: list[str],
    *,
    login: Callable[..., Any] | None = None,
    unauthenticated_actor_ids: set[str] | None = None,
) -> dict[str, ActorSession]:
    """Create isolated in-memory auth headers in the declared actor order."""
    if login is None:
        # Local import avoids a package initialization cycle: Stage2.5 already
        # consumes Stage6 replay primitives.
        from stage2_5_probe.prober import login_auth

        login = login_auth
    sessions = {}
    unauthenticated_actor_ids = unauthenticated_actor_ids or set()
    for actor_id in actor_ids:
        auth = actor_auth(profile, actor_id)
        headers: dict[str, str] = {}
        if auth.method != "none" and actor_id not in unauthenticated_actor_ids:
            email, password = resolve_actor_credentials(profile, actor_id)
            runtime = login(profile.base_url, email, password, auth)
            if runtime.token:
                headers["Authorization"] = f"{runtime.token_scheme} {runtime.token}"
            if runtime.session_cookie_header:
                headers["Cookie"] = runtime.session_cookie_header
            if runtime.csrf_cookie_header and runtime.csrf_header_name and runtime.csrf_header_value:
                # Double submit for frameworks that require it on unsafe methods (Django).
                headers["Cookie"] = "; ".join(
                    part for part in (headers.get("Cookie"), runtime.csrf_cookie_header) if part
                )
                headers[runtime.csrf_header_name] = runtime.csrf_header_value
        sessions[actor_id] = ActorSession(actor_id=actor_id, headers=headers)
    return sessions


class TestSuiteExecutor:
    __test__ = False

    def __init__(
        self,
        augmented_oas: dict[str, Any],
        profile: AppProfile,
        *,
        transport: Transport = send,
        reset: Callable[[], dict[str, str]] | None = None,
        login: Callable[..., Any] | None = None,
    ) -> None:
        self.augmented_oas = augmented_oas
        self.profile = profile
        self.op_index = build_op_index(augmented_oas)
        self.transport = transport
        self.reset = reset or (lambda: reset_profile(profile))
        self.login = login
        self.run_id = _run_id(augmented_oas, profile)
        self._observation_sequence = 0

    def execute(self, test_suite: dict[str, Any], *, profile_path: str | Path | None = None) -> dict[str, Any]:
        validate_artifact("test_suite.schema.json", test_suite)
        self._validate_profile_invariants(test_suite)
        reset_refs: list[dict[str, str]] = []
        case_results = []
        for case in test_suite["cases"]:
            for variant in case["input_variants"]:
                result, refs = self._execute_variant(case, variant)
                case_results.append(result)
                reset_refs.extend(refs)
        if not reset_refs:
            reset_refs.append(self.reset())
        environment = {
            "subject_digest": _sha256_json(self.augmented_oas),
            "reset_fingerprint_refs": reset_refs,
        }
        if profile_path is not None:
            environment["profile_sha256"] = hashlib.sha256(Path(profile_path).read_bytes()).hexdigest()
        report = {
            "metadata": make_envelope(
                "test_execution_report",
                "stage6",
                self.run_id,
                upstream_refs=[
                    {"artifact_type": "test_suite", "run_id": test_suite["metadata"]["run_id"]}
                ],
            ),
            "environment": environment,
            "cases": case_results,
        }
        validate_artifact("test_execution_report.schema.json", report)
        return report

    def _execute_variant(self, case: dict[str, Any], variant: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
        normal_runs = case["calibration_policy"]["normal_control_runs"]
        runs = []
        reset_refs = []
        for _ in range(normal_runs):
            reset_ref = self.reset()
            reset_refs.append(reset_ref)
            sessions = build_actor_sessions(
                self.profile,
                case["actors"],
                login=self.login,
                unauthenticated_actor_ids=self._login_action_actor_ids(case),
            )
            runs.append(self._execute_once(case, variant, sessions))

        assertion_ids = [assertion["assertion_id"] for assertion in case["assertions"]]
        kept = []
        dropped = []
        for assertion_id in assertion_ids:
            outcomes = [
                next((item for item in run["assertion_results"] if item["assertion_id"] == assertion_id), None)
                for run in runs
            ]
            if any(run["environment_errors"] for run in runs):
                dropped.append({"assertion_id": assertion_id, "reason": "missing_normal_control_outcome"})
            elif any(outcome is None or outcome["verdict"] == "unable" for outcome in outcomes):
                dropped.append({"assertion_id": assertion_id, "reason": "missing_normal_control_outcome"})
            elif any(outcome["verdict"] != "passed" for outcome in outcomes):
                dropped.append({"assertion_id": assertion_id, "reason": "failed_normal_control"})
            else:
                kept.append(assertion_id)
        final = runs[-1]
        final.update(
            {
                "test_id": case["test_id"],
                "variant_id": variant["variant_id"],
                "calibration": {
                    "normal_runs": normal_runs,
                    "kept_assertion_ids": kept,
                    "dropped": dropped,
                },
            }
        )
        return final, reset_refs

    def _execute_once(
        self,
        case: dict[str, Any],
        variant: dict[str, Any],
        sessions: dict[str, ActorSession],
    ) -> dict[str, Any]:
        observations: dict[str, dict[str, Any]] = {}
        environment_errors: list[str] = []
        phases = {}
        for phase in ("setup_steps", "observe_before", "action_steps", "observe_after"):
            results = []
            for step in case[phase]:
                step_id = step.get("step_id") or step.get("observation_id")
                try:
                    result, observation = self._execute_step(step, variant, sessions[step["actor_id"]])
                    observations[step_id] = observation
                    results.append(result)
                    if phase != "action_steps" and not 200 <= result["status"] < 400:
                        environment_errors.append(f"{phase}:{step_id}: unsuccessful prerequisite")
                except Exception as error:  # Do not serialize request material or exception text.
                    environment_errors.append(f"{phase}:{step_id}: {type(error).__name__}")
            phases[phase] = results
        assertion_results = []
        for assertion in case["assertions"]:
            try:
                passed, detail = evaluate_predicate(assertion["predicate"], observations)
                assertion_results.append(
                    {
                        "assertion_id": assertion["assertion_id"],
                        "verdict": "passed" if passed else "failed",
                        "detail": _safe_assertion_detail(detail),
                    }
                )
            except Exception as error:
                assertion_results.append(
                    {
                        "assertion_id": assertion["assertion_id"],
                        "verdict": "unable",
                        "detail": {"reason": type(error).__name__},
                    }
                )
        return {
            "setup_results": phases["setup_steps"],
            "observe_before": phases["observe_before"],
            "action_results": phases["action_steps"],
            "observe_after": phases["observe_after"],
            "assertion_results": assertion_results,
            "environment_errors": environment_errors,
        }

    def _execute_step(
        self,
        step: dict[str, Any],
        variant: dict[str, Any],
        session: ActorSession,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        step_id = step.get("step_id") or step.get("observation_id")
        operation_id = step["operation_id"]
        if operation_id not in self.op_index:
            raise ValueError(f"operation not admitted: {operation_id}")
        method, path, operation = self.op_index[operation_id]
        path_values: dict[str, Any] = {}
        query: dict[str, Any] = {}
        headers = dict(session.headers)
        body: dict[str, Any] = {}
        for assignment in variant["assignments"]:
            if assignment["step_id"] != step_id:
                continue
            location = assignment["location"]
            field = assignment["field"]
            value = assignment["value"]
            if assignment["generation_source"] == "external_parameter":
                value = self._resolve_external_parameter(value, step["actor_id"])
            if location == "path":
                path_values[field] = value
            elif location == "query":
                query[field] = value
            elif location == "header":
                headers[field] = str(value)
            elif location == "body":
                try:
                    set_body_value(body, field, value)
                except BodyPathError as error:
                    raise ValueError(f"invalid body assignment: {field}") from error
        for name, value in path_values.items():
            path = path.replace("{" + name + "}", quote(str(value), safe=""))
        if "{" in path or "}" in path:
            raise ValueError("unresolved path parameter")
        url = self.profile.base_url.rstrip("/") + path
        if query:
            url += "?" + urlencode(query, doseq=True)
        encoding = step.get("body_encoding") or _body_encoding(operation)
        encoded = encode_body(body, encoding)
        if encoded.content_type:
            headers["Content-Type"] = encoded.content_type
        response = self.transport(method, url, headers, encoded.body_text)
        if self._is_login_operation(step["actor_id"], method, path):
            self._apply_login_response(session, response)
        body_value = response.json()
        if body_value is None:
            body_value = response.body_text
        request_context = {**body, "body": body, "query": query, "path": path_values}
        observation = {
            "request": request_context,
            "response": body_value,
            "body": body_value,
            "status": response.status,
        }
        self._observation_sequence += 1
        observation_ref = {
            "run_id": self.run_id,
            "record_id": f"obs-{self._observation_sequence:05d}",
        }
        result = {
            "step_id": step_id,
            "actor_id": session.actor_id,
            "status": response.status,
            "body_digest": _sha256_json(body_value),
            "observation_ref": observation_ref,
        }
        return result, observation

    def _login_action_actor_ids(self, case: dict[str, Any]) -> set[str]:
        actors = set()
        for step in case["action_steps"]:
            operation = self.op_index.get(step["operation_id"])
            if operation is None:
                continue
            method, path, _document = operation
            if self._is_login_operation(step["actor_id"], method, path):
                actors.add(step["actor_id"])
        return actors

    def _is_login_operation(self, actor_id: str, method: str, path: str) -> bool:
        auth = actor_auth(self.profile, actor_id)
        cfg = auth.api_token if auth.method == "api_token" else auth.cookie_session if auth.method == "cookie_session" else None
        return cfg is not None and cfg.method.upper() == method.upper() and cfg.path == path

    def _resolve_external_parameter(self, value: Any, actor_id: str) -> str:
        if not isinstance(value, dict) or set(value) != {"profile_credential"}:
            raise ValueError("invalid external parameter token")
        email, password = resolve_actor_credentials(self.profile, actor_id)
        token = value["profile_credential"]
        if token == "email":
            return email
        if token == "password":
            return password
        raise ValueError("unknown profile credential token")

    def _apply_login_response(self, session: ActorSession, response: HttpResult) -> None:
        if not 200 <= response.status < 300:
            return
        auth = actor_auth(self.profile, session.actor_id)
        if auth.method == "cookie_session":
            cfg = auth.cookie_session
            if cfg is None:
                raise ValueError("cookie login profile is incomplete")
            # Every Set-Cookie value, not just the one a flat header dict keeps: a
            # login may set the session cookie and a CSRF cookie in separate headers.
            values = response_set_cookies(response)
            if not values:
                raise ValueError("login response is missing Set-Cookie")
            jar = SimpleCookie()
            for value in values:
                jar.load(value)
            name = cfg.cookie_name or (next(iter(jar.keys())) if jar else None)
            if not name or name not in jar:
                raise ValueError("login response is missing the declared cookie")
            session.headers["Cookie"] = f"{name}={jar[name].value}"
            return
        if auth.method == "api_token":
            cfg = auth.api_token
            body = response.json()
            token = extract_value(body, cfg.token_json_path) if cfg is not None else None
            if token is None:
                raise ValueError("login response is missing the declared token")
            session.headers["Authorization"] = f"{auth.token_scheme} {token}"

    def _validate_profile_invariants(self, test_suite: dict[str, Any]) -> None:
        for case in test_suite["cases"]:
            steps = {
                (item.get("step_id") or item.get("observation_id")): item
                for phase in ("setup_steps", "observe_before", "action_steps", "observe_after")
                for item in case[phase]
            }
            for variant in case["input_variants"]:
                for assignment in variant["assignments"]:
                    if assignment["generation_source"] != "external_parameter":
                        continue
                    step = steps.get(assignment["step_id"])
                    if step is None:
                        raise ValueError("external parameter references an unknown step")
                    operation = self.op_index.get(step["operation_id"])
                    if operation is None:
                        raise ValueError("external parameter operation is not admitted")
                    method, path, _document = operation
                    if not self._is_login_operation(step["actor_id"], method, path):
                        raise ValueError("profile credential token is only valid on the declared login endpoint")
                    value = assignment["value"]
                    if not isinstance(value, dict) or set(value) != {"profile_credential"}:
                        raise ValueError("invalid profile credential token")
                    if value["profile_credential"] not in {"email", "password"}:
                        raise ValueError("unknown profile credential token")


def run_test_suite(
    augmented_oas_path: str | Path,
    test_suite_path: str | Path,
    profile_path: str | Path,
    *,
    artifacts_root: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    augmented_oas = json.loads(Path(augmented_oas_path).read_text())
    validate_artifact("augmented_oas.schema.json", augmented_oas)
    test_suite = json.loads(Path(test_suite_path).read_text())
    profile = load_app_profile(profile_path)
    executor = TestSuiteExecutor(augmented_oas, profile)
    report = executor.execute(test_suite, profile_path=profile_path)
    root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = root / report["metadata"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "test_execution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"
    )
    return report, run_dir


def _body_encoding(operation: dict[str, Any]) -> str:
    content = (operation.get("requestBody") or {}).get("content") or {}
    if not content:
        return "none"
    supported = {
        "application/json": "json",
        "application/x-www-form-urlencoded": "form_urlencoded",
        "multipart/form-data": "multipart",
    }
    for media_type in content:
        if media_type in supported:
            return supported[media_type]
    raise ValueError(f"unsupported request media type: {', '.join(sorted(content))}")


def reset_profile(profile: AppProfile) -> dict[str, str]:
    reset = profile.reset
    if reset is None:
        raise RuntimeError("test suite execution requires profile.reset")
    command = list(reset.command) if reset.command else ["bash", str((REPO_ROOT / str(reset.script)).resolve())]
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    if completed.returncode != 0:
        raise RuntimeError("profile reset command failed")
    verify = reset.verify_request
    request = urllib.request.Request(profile.base_url.rstrip("/") + verify.path, method=verify.method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read()
    if status != verify.expect_status:
        raise RuntimeError("profile reset verification failed")
    digest = hashlib.sha256(body).hexdigest()
    return {"run_id": "environment-reset", "record_id": f"reset-{digest[:16]}"}


def _run_id(augmented_oas: dict[str, Any], profile: AppProfile) -> str:
    material = f"{augmented_oas['x-carverflow-meta']['run_id']}|{profile.base_url}"
    return f"testexec-{hashlib.sha256(material.encode()).hexdigest()[:16]}"


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _safe_assertion_detail(detail: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    if "actual" in detail:
        safe["actual_summary"] = _bounded(detail["actual"])
    if "expected" in detail:
        safe["expected_summary"] = _bounded(detail["expected"])
    if not safe:
        safe["reason"] = "deterministic predicate evaluated"
    return safe


def _bounded(value: Any) -> Any:
    if isinstance(value, str):
        return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sha256_json(value)
