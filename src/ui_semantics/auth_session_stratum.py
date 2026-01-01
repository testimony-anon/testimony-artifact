"""Typed auth/session stratum evaluation, compilation, and calibration."""

from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any, Mapping

from stage0_launch.profile import (
    AppProfile,
    actor_auth,
    actor_session_initialization_endpoint,
    resolve_actor_credentials,
)
from stage2_5_probe.prober import _extract_session_cookie, _render_template
from stage6_ground.http_client import HttpResult
from stage6_ground.valuepath import extract_value

from .contracts import UiApiTrace
if TYPE_CHECKING:
    from .current_http_runtime import _LocalHttpExecutionCore


@dataclass(frozen=True)
class _ProbeState:
    status: int
    shape: Any
    body: Any


class _LocalAuthSessionRuntime:
    def __init__(self, core: _LocalHttpExecutionCore) -> None:
        self.core = core
        self.local_http_requests = 0
        self.reset_runs = 0

    def reset(self) -> None:
        self.core._reset_for_replay()
        self.reset_runs += 1

    def probe(self, profile: AppProfile, actor_id: str, headers: Mapping[str, str]) -> HttpResult:
        probe = actor_auth(profile, actor_id).probe_endpoint
        if probe is None:
            raise ValueError("auth-session actor has no typed protected probe")
        self.local_http_requests += 1
        self.core.counts["request_executions"] += 1
        return self.core._send(probe.method, probe.path, {}, headers, None)

    def _login_headers(self, config: Any) -> dict[str, str]:
        """Static profile headers, plus a dynamic CSRF double-submit when declared.

        Without ``cookie_session.csrf`` this is exactly ``dict(config.headers)`` and no
        extra request is issued, i.e. the login this replaced sent before the field
        existed. With it, the entry page is fetched once so the framework can set its
        CSRF cookie, and that value is echoed both as a Cookie and in the declared
        header — the same concept as ``stage2_5_probe.prober``.
        """
        headers = dict(config.headers)
        csrf = getattr(config, "csrf", None)
        if csrf is None:
            return headers
        self.local_http_requests += 1
        self.core.counts["request_executions"] += 1
        prewarm = self.core._send("GET", "/", {}, {}, None)
        jar = SimpleCookie()
        try:
            for value in getattr(prewarm, "set_cookies", ()):
                jar.load(value)
        except Exception:  # noqa: BLE001 - an unparsable jar is reported below as a missing cookie
            jar = SimpleCookie()
        morsel = jar.get(csrf.cookie_name)
        if morsel is None or not morsel.value:
            raise ValueError(
                "auth-session login failed: the declared CSRF cookie "
                f"{csrf.cookie_name} was not set by the prewarm request"
            )
        headers[csrf.header_name] = morsel.value
        headers["Cookie"] = f"{csrf.cookie_name}={morsel.value}"
        return headers

    def login(
        self,
        profile: AppProfile,
        actor_id: str,
    ) -> tuple[HttpResult, dict[str, str], bool]:
        auth = actor_auth(profile, actor_id)
        config = _typed_login_config(auth)
        email, password = resolve_actor_credentials(profile, actor_id)
        body = _render_template(config.body_template, email, password)
        login_headers = self._login_headers(config)
        self.local_http_requests += 1
        self.core.counts["request_executions"] += 1
        result = self.core._send(
            config.method,
            config.path,
            {},
            login_headers,
            body,
        )
        if not 200 <= result.status < 300:
            return result, {}, False
        if auth.cookie_session is config:
            try:
                name, value = _extract_session_cookie(
                    result.headers,
                    config.cookie_name,
                    set_cookies=getattr(result, "set_cookies", ()),
                )
            except RuntimeError:
                return result, {}, False
            self.core.counts["session_materializations"] += 1
            return result, {"Cookie": f"{name}={value}"}, True
        token = extract_value(result.json(), config.token_json_path)
        if token is None:
            return result, {}, False
        self.core.counts["session_materializations"] += 1
        return result, {"Authorization": f"{auth.token_scheme} {token}"}, True


def evaluate_auth_session_stratum(
    runtime: Any | None,
    profile: AppProfile,
    trace: UiApiTrace,
    partition: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate the typed auth/session producers inside the canonical lifecycle."""

    producers = _auth_session_inputs(trace, partition, profile)
    if producers and runtime is None:
        raise TypeError("auth-session producers require a local subject runtime")
    rows = [
        _evaluate_actor(runtime, profile, producer)
        for producer in producers
    ]
    outcomes: dict[str, int] = {}
    for row in rows:
        outcome = str(row["outcome"])
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    evaluable = sum(
        count for outcome, count in outcomes.items() if outcome != "infrastructure_failed"
    )
    return {
        "artifact_type": "auth_session_qualification",
        "status": "pass",
        "stratum": "auth_session",
        "producer_partition": {
            "domain_business": int(partition["summary"]["business"]),
            "available": int(partition["summary"]["business_available"]),
            "unsupported": int(partition["summary"]["business_unsupported"]),
            "auth_session": int(partition["summary"]["auth_session"]),
            "total": int(partition["summary"]["total"]),
            "disjoint": bool(partition["summary"]["disjoint"]),
        },
        "denominator": {
            "attempted": len(rows),
            "evaluable": evaluable,
            "confirmed": outcomes.get("confirmed", 0),
            "effect_absent": outcomes.get("effect_absent", 0),
            "infrastructure_failed": outcomes.get("infrastructure_failed", 0),
        },
        "outcomes": dict(sorted(outcomes.items())),
        "rows": rows,
    }


def compile_auth_session_tests(
    qualification: Mapping[str, Any],
    profile: AppProfile,
    *,
    normal_runs: int,
) -> dict[str, Any]:
    if normal_runs < 1:
        raise ValueError("auth-session normal_runs must be positive")
    tests = []
    for row in qualification.get("rows", []):
        if row.get("outcome") != "confirmed":
            continue
        actor_id = str(row["actor_id"])
        auth = actor_auth(profile, actor_id)
        login = _typed_login_config(auth)
        probe = auth.probe_endpoint
        if probe is None or probe.unauthenticated_status is None:
            raise ValueError("confirmed auth-session row lacks a typed protected probe")
        tests.append(
            {
                "test_id": f"auth-session-{actor_id}",
                "actor_id": actor_id,
                "producer_request_ref": str(row["producer_request_ref"]),
                "producer_event_id": str(row["producer_event_id"]),
                "binding_basis": str(row["binding_basis"]),
                "login": {"method": login.method, "path": login.path},
                "protected_probe": {
                    "method": probe.method,
                    "path": probe.path,
                    "authenticated_status": probe.expect_status,
                    "unauthenticated_status": probe.unauthenticated_status,
                    "authenticated_json_path": probe.expect_json_path,
                },
                "normal_runs": normal_runs,
            }
        )
    tests.sort(key=lambda item: item["test_id"])
    return {
        "artifact_type": "auth_session_tests",
        "status": "pass",
        "stratum": "auth_session",
        "confirmed_input": len(tests),
        "generated": len(tests),
        "tests": tests,
    }


def calibrate_auth_session_tests(
    runtime: Any | None,
    profile: AppProfile,
    suite: Mapping[str, Any],
) -> dict[str, Any]:
    tests = list(suite.get("tests", []))
    if tests and runtime is None:
        raise TypeError("auth-session tests require a local subject runtime")
    rows = []
    retained = []
    for test in tests:
        run_rows = [
            _evaluate_actor(
                runtime,
                profile,
                {
                    "actor_id": str(test["actor_id"]),
                    "request_ref": str(test["producer_request_ref"]),
                    "event_id": str(test["producer_event_id"]),
                    "binding_basis": str(test["binding_basis"]),
                },
            )
            for _ in range(int(test["normal_runs"]))
        ]
        outcomes = [str(row["outcome"]) for row in run_rows]
        pass_count = sum(outcome == "confirmed" for outcome in outcomes)
        if "infrastructure_failed" in outcomes:
            status = "inconclusive"
        elif pass_count == int(test["normal_runs"]):
            status = "pass"
            retained.append(str(test["test_id"]))
        else:
            status = "fail"
        rows.append(
            {
                "test_id": str(test["test_id"]),
                "actor_id": str(test["actor_id"]),
                "binding_basis": str(test["binding_basis"]),
                "normal_runs": int(test["normal_runs"]),
                "pass_count": pass_count,
                "outcomes": outcomes,
                "status": status,
            }
        )
    return {
        "artifact_type": "auth_session_calibration",
        "status": "pass",
        "stratum": "auth_session",
        "test_denominator": {
            "generated": len(tests),
            "retained": len(retained),
            "failed": sum(row["status"] == "fail" for row in rows),
            "inconclusive": sum(row["status"] == "inconclusive" for row in rows),
        },
        "retained_test_ids": retained,
        "rows": rows,
    }


def _auth_session_inputs(
    trace: UiApiTrace,
    partition: Mapping[str, Any],
    profile: AppProfile,
) -> tuple[dict[str, str], ...]:
    rows = partition.get("auth_session_producers")
    summary = partition.get("summary")
    if not isinstance(rows, list) or not isinstance(summary, Mapping):
        raise ValueError("auth-session typed producer partition is malformed")
    if int(summary.get("auth_session", -1)) != len(rows):
        raise ValueError("auth-session typed producer denominator drift")
    bindings: dict[str, list[Mapping[str, Any]]] = {}
    for binding in trace.trace["bindings"]:
        bindings.setdefault(str(binding["request_ref"]), []).append(binding)
    events = {
        str(event["event_id"]): event for event in trace.trace["events"]
    }
    requests = {
        str(request["request_ref"]): request
        for request in trace.trace["api_requests"]
    }
    result = []
    actors: set[str] = set()
    for row in rows:
        actor_id = str(row["actor_id"])
        request_ref = str(row["request_ref"])
        expected = actor_session_initialization_endpoint(profile, actor_id)
        actual = (str(row["method"]).upper(), str(row["canonical_path"]))
        if expected != actual:
            raise ValueError("auth-session producer differs from typed profile endpoint")
        event_id, binding_basis = _resolve_auth_session_binding(
            request_ref=request_ref,
            actor_id=actor_id,
            endpoint=actual,
            bindings=bindings,
            reviews=trace.trace["binding_reviews"],
            events=events,
            requests=requests,
        )
        event = events.get(event_id)
        if event is None or str(event["actor_id"]) != actor_id:
            raise ValueError("auth-session producer event actor drift")
        probe = actor_auth(profile, actor_id).probe_endpoint
        if (
            probe is None
            or probe.unauthenticated_status is None
            or probe.expect_json_path is None
        ):
            raise ValueError("auth-session actor lacks declared state-probe expectations")
        if actor_id in actors:
            raise ValueError("auth-session producer actor is duplicated")
        actors.add(actor_id)
        result.append(
            {
                "actor_id": actor_id,
                "request_ref": request_ref,
                "event_id": event_id,
                "binding_basis": binding_basis,
            }
        )
    return tuple(result)


def _resolve_auth_session_binding(
    *,
    request_ref: str,
    actor_id: str,
    endpoint: tuple[str, str],
    bindings: Mapping[str, list[Mapping[str, Any]]],
    reviews: list[Mapping[str, Any]],
    events: Mapping[str, Mapping[str, Any]],
    requests: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str]:
    confirmed = [
        binding
        for binding in bindings.get(request_ref, [])
        if binding.get("status") == "confirmed"
    ]
    if len(confirmed) == 1:
        return str(confirmed[0]["event_id"]), "confirmed_recording_binding"
    if confirmed:
        raise ValueError("auth-session producer has non-unique confirmed bindings")

    matching_reviews = [
        review
        for review in reviews
        if request_ref
        in {str(item) for item in review.get("candidate_request_refs", [])}
    ]
    if len(matching_reviews) != 1:
        raise ValueError("auth-session producer review window is not unique")
    review = matching_reviews[0]
    event_id = str(review["event_id"])
    event = events.get(event_id)
    if event is None or str(event["actor_id"]) != actor_id:
        raise ValueError("auth-session producer review event actor drift")
    method, canonical_path = endpoint
    exact_refs = []
    for candidate_ref in review.get("candidate_request_refs", []):
        ref = str(candidate_ref)
        candidate = requests.get(ref)
        if candidate is None:
            continue
        if (
            str(candidate["actor_id"]) == actor_id
            and str(candidate["method"]).upper() == method
            and str(candidate["canonical_path"]) == canonical_path
        ):
            exact_refs.append(ref)
    if exact_refs != [request_ref]:
        raise ValueError("auth-session producer typed review match is not unique")
    return event_id, "typed_session_endpoint_review_disambiguation"


def _evaluate_actor(
    runtime: Any,
    profile: AppProfile,
    producer: Mapping[str, str],
) -> dict[str, Any]:
    actor_id = producer["actor_id"]
    statuses: dict[str, Any] = {
        "control": [None, None],
        "treatment_pre": None,
        "login": None,
        "treatment_post": None,
        "isolation": None,
    }
    gates = {
        "control_stable_logged_out": False,
        "treatment_pre_compatible": False,
        "login_2xx": False,
        "session_material_present": False,
        "treatment_post_authenticated": False,
        "treatment_state_changed": False,
        "isolation_logged_out": False,
    }
    auth = actor_auth(profile, actor_id)
    probe = auth.probe_endpoint
    if probe is None:
        raise ValueError("auth-session actor has no protected probe")
    runtime.reset()
    control_1 = _probe_state(runtime.probe(profile, actor_id, {}))
    control_2 = _probe_state(runtime.probe(profile, actor_id, {}))
    statuses["control"] = [control_1.status, control_2.status]
    control_signature = (control_1.status, control_1.shape)
    gates["control_stable_logged_out"] = (
        control_signature == (control_2.status, control_2.shape)
        and control_1.status == probe.unauthenticated_status
        and extract_value(control_1.body, probe.expect_json_path) is None
        and extract_value(control_2.body, probe.expect_json_path) is None
    )

    runtime.reset()
    treatment_pre = _probe_state(runtime.probe(profile, actor_id, {}))
    statuses["treatment_pre"] = treatment_pre.status
    gates["treatment_pre_compatible"] = (
        treatment_pre.status,
        treatment_pre.shape,
    ) == control_signature

    login, session_headers, material_present = runtime.login(profile, actor_id)
    statuses["login"] = login.status
    gates["login_2xx"] = 200 <= login.status < 300
    gates["session_material_present"] = material_present

    treatment_post = _probe_state(runtime.probe(profile, actor_id, session_headers))
    statuses["treatment_post"] = treatment_post.status
    gates["treatment_post_authenticated"] = (
        treatment_post.status == probe.expect_status
        and extract_value(treatment_post.body, probe.expect_json_path) is not None
    )
    gates["treatment_state_changed"] = (
        treatment_post.status,
        treatment_post.shape,
    ) != (treatment_pre.status, treatment_pre.shape)

    isolation = _probe_state(runtime.probe(profile, actor_id, {}))
    statuses["isolation"] = isolation.status
    gates["isolation_logged_out"] = (
        (isolation.status, isolation.shape) == control_signature
        and extract_value(isolation.body, probe.expect_json_path) is None
    )
    observed_statuses = [
        *statuses["control"],
        statuses["treatment_pre"],
        statuses["login"],
        statuses["treatment_post"],
        statuses["isolation"],
    ]
    infrastructure_reason = None
    if any(isinstance(status, int) and status >= 500 for status in observed_statuses):
        outcome = "infrastructure_failed"
        infrastructure_reason = "local_http_5xx"
    elif all(gates.values()):
        outcome = "confirmed"
    else:
        outcome = "effect_absent"

    row = {
        "actor_id": actor_id,
        "producer_request_ref": producer["request_ref"],
        "producer_event_id": producer["event_id"],
        "binding_basis": producer["binding_basis"],
        "statuses": statuses,
        "session_material_present": gates["session_material_present"],
        "gates": gates,
        "outcome": outcome,
    }
    if infrastructure_reason is not None:
        row["infrastructure_reason"] = infrastructure_reason
    return row


def _probe_state(result: HttpResult) -> _ProbeState:
    body = result.json()
    return _ProbeState(result.status, _json_shape(body, result.body_text), body)


def _json_shape(value: Any, body_text: str | None) -> Any:
    if value is None:
        return ("empty",) if not body_text else ("text",)
    if isinstance(value, dict):
        return (
            "object",
            tuple((str(key), _json_shape(child, "present")) for key, child in sorted(value.items())),
        )
    if isinstance(value, list):
        return ("array", tuple(_json_shape(child, "present") for child in value))
    if isinstance(value, bool):
        return ("boolean",)
    if isinstance(value, (int, float)):
        return ("number",)
    return ("string",)


def _typed_login_config(auth: Any) -> Any:
    if auth.method == "cookie_session":
        config = auth.cookie_session
    elif auth.method == "api_token":
        config = auth.api_token
    else:
        declared = [
            config
            for config in (auth.api_token, auth.cookie_session)
            if config is not None
        ]
        if len(declared) != 1:
            raise ValueError("form-login auth has no unique typed session backing")
        config = declared[0]
    if config is None:
        raise ValueError("auth-session producer has no typed login request")
    return config


__all__ = [
    "calibrate_auth_session_tests",
    "compile_auth_session_tests",
    "evaluate_auth_session_stratum",
]
