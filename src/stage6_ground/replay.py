"""Live replay executor (D47, in the style of the apicarver ReplayClient).

Executes the steps of a sequence/skill in order: sends real HTTP requests, receives real responses, and per binding
resolves the from_field of the producer step's response into the to_location/to_field of the consumer step; external inputs are filled in from the configuration.

Sequences and edges are kept separate (M2): this module only decides whether the whole sequence runs through (business_success
at every step + every binding resolved); it never judges any edge hard/soft here — that is the job of the counterexamples (counterexample.py).
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode, urlsplit

from common.oas_discovery import is_execution_ready
from common.location_link_valueflow import extract_location_path_value, is_location_path_field, parse_link_header
from common.xml_valueflow import extract_xml_value, is_xml_field

from .config import ReplayConfig
from .http_client import HttpResult, Throttle, business_success, send
from .valuepath import BodyPathError, extract_value, set_body_value

FROM_RESPONSE_BODY = "response_body"
FROM_RESPONSE_HEADER = "response_header"

# bindings whose value is never stored in clear text (token, D18): bindings_resolved records only resolved, not the value
_SECRET_TO_FIELD = {"Authorization"}

# counterexample sentinel: an override returning DROP means "deliberately do not apply this binding" (drop_all_sources; the consumer request is still sent, D50/M4)
DROP = object()


def build_op_index(augmented_oas: dict) -> dict:
    """operationId -> (method_upper, canonical_path, op_def)."""
    idx = {}
    for path, item in augmented_oas["paths"].items():
        for method, op in item.items():
            if not is_execution_ready(op):
                continue
            idx[op["operationId"]] = (method.upper(), path, op)
    return idx


@dataclass
class StepResult:
    step_index: int
    operation_id: str
    passed: bool
    response_status: int | None
    error: str | None
    bindings_resolved: list[dict]


@dataclass
class ReplayOutcome:
    passed: bool
    steps: list[StepResult]
    failed_step_index: int | None = None
    responses: dict = field(default_factory=dict)        # step_index -> {"body","headers","status"}
    created_articles: list[str] = field(default_factory=list)  # for legacy cleanup: slug/id produced by POST responses


class ReplayClient:
    """Replays one list of steps sequentially; holds base_url/op_index/config/throttle."""

    def __init__(self, cfg: ReplayConfig, op_index: dict, throttle: Throttle | None = None):
        self.cfg = cfg
        self.op_index = op_index
        self.throttle = throttle or Throttle()

    # ---- request construction ----

    def _build_request(self, op_id: str, path_vals: dict, query_vals: dict,
                       body: dict, headers: dict) -> tuple[str, str, dict, str | None]:
        method, path, _ = self.op_index[op_id]
        for name, val in path_vals.items():
            path = path.replace("{" + name + "}", quote(str(val), safe=""))
        url = self.cfg.base_url + path
        if query_vals:
            url += "?" + urlencode({k: str(v) for k, v in query_vals.items()})
        body_text = json.dumps(body, ensure_ascii=False) if body else None
        if self.cfg.auth_token and not any(str(k).lower() == "authorization" for k in headers):
            headers["Authorization"] = f"{self.cfg.token_scheme} {self.cfg.auth_token}"
        if self.cfg.session_cookie_header and not any(str(k).lower() == "cookie" for k in headers):
            headers["Cookie"] = self.cfg.session_cookie_header
        return method, url, headers, body_text

    def _apply(self, to_location: str, to_field: str, value,
               path_vals: dict, query_vals: dict, body: dict, headers: dict) -> None:
        if to_location == "path":
            path_vals[to_field] = value
        elif to_location == "query":
            query_vals[to_field] = value
        elif to_location == "header":
            if to_field == "Authorization":
                headers["Authorization"] = f"{self.cfg.token_scheme} {value}"
            else:
                headers[to_field] = str(value)
        elif to_location == "body":
            set_body_value(body, to_field, value)

    # ---- single-step execution ----

    @staticmethod
    def _resolve_binding(
        b: dict,
        responses: dict,
        response_request_urls: dict,
        override,
    ) -> tuple[object, bool, dict]:
        """Fetch the value of this binding and build the bindings_resolved record; returns (value, dropped, record)."""
        from_location = b.get("from_location", FROM_RESPONSE_BODY)
        value = _resolve_from_response(
            responses.get(b["from_step"]),
            from_location,
            b["from_field"],
            response_request_urls.get(b["from_step"]),
        )
        if override is not None:
            value = _call_value_override(override, b, value, responses.get(b["from_step"]))
        dropped = value is DROP
        resolved = dropped or value is not None
        rec = {"from_step": b["from_step"], "from_location": from_location,
               "from_field": b["from_field"], "to_location": b["to_location"],
               "to_field": b["to_field"], "resolved": resolved}
        if resolved and not dropped and b["to_field"] not in _SECRET_TO_FIELD \
                and b["to_location"] != "header":
            rec["resolved_value"] = _short(value)
        return value, dropped, rec

    def _gather_inputs(self, step: int, bindings: list[dict], parameters: list[dict],
                       responses: dict, response_request_urls: dict | None = None, override=None,
                       initial_body=None) -> tuple[dict, dict, dict, dict, list[dict], dict | None]:
        """Gather the request inputs of the given step; returns (path,query,body,headers,bindings_resolved,bind_failed)."""
        response_request_urls = response_request_urls or {}
        path_vals: dict = {}
        query_vals: dict = {}
        body: dict = deepcopy(initial_body) if initial_body is not None else {}
        headers: dict = {}
        resolved_log: list[dict] = []
        bind_failed: dict | None = None

        def apply(loc: str, field: str, val) -> None:
            nonlocal bind_failed
            try:
                self._apply(loc, field, val, path_vals, query_vals, body, headers)
            except BodyPathError as exc:  # D61: array missing / index out of range → bind_fail (other exceptions are not swallowed silently)
                bind_failed = bind_failed or {"to_field": field, "reason": "array_index_out_of_range",
                                              "detail": str(exc)}

        # D61 ordering ruling (ruling a): params lay down the skeleton first, bindings refine and override afterwards — coarse-grained defaults must not wipe out fine-grained data flows.
        for p in parameters:
            if p["to_step"] != step:
                continue
            val = p["value"] if "value" in p else self.cfg.value_for(p["to_location"], p["to_field"])
            if val is None:
                bind_failed = bind_failed or {"to_field": p["to_field"], "reason": "missing_param"}
                continue
            apply(p["to_location"], p["to_field"], val)
        for b in bindings:
            if b["to_step"] != step:
                continue
            value, dropped, rec = self._resolve_binding(b, responses, response_request_urls, override)
            resolved_log.append(rec)
            if dropped:
                continue  # drop_all_sources: do not apply this binding, send the request anyway (D50/M4)
            if not rec["resolved"]:
                bind_failed = bind_failed or {**b, "reason": "producer_value_missing"}
                continue
            apply(b["to_location"], b["to_field"], value)
        return path_vals, query_vals, body, headers, resolved_log, bind_failed

    def replay(self, steps: list[str], bindings: list[dict], parameters: list[dict],
               value_override=None) -> ReplayOutcome:
        """Replay the whole list of steps.

        value_override(binding, default)->value lets counterexamples change values (may return DROP). The V2 replay
        smoke may optionally use value_override(binding, default, producer_response) for conservative material completion.
        """
        responses: dict = {}
        response_request_urls: dict = {}
        results: list[StepResult] = []
        created: list[str] = []
        for i, op_id in enumerate(steps):
            pv, qv, body, headers, resolved_log, bind_failed = self._gather_inputs(
                i, bindings, parameters, responses, response_request_urls, value_override)

            # missing binding/param value or missing array → not sendable, short-circuit (setup break; S1: counted as inconclusive rather than business failure)
            if bind_failed is not None:
                reason = bind_failed.get("reason", "producer_value_missing")
                miss = bind_failed.get("from_field", bind_failed.get("to_field"))
                src = f" from step{bind_failed['from_step']}" if "from_step" in bind_failed else ""
                results.append(StepResult(i, op_id, False, None,
                    f"bind_fail(inconclusive_setup): {reason} @ {miss}{src}", resolved_log))
                return ReplayOutcome(False, results, i, responses, created)

            method, url, hdrs, body_text = self._build_request(op_id, pv, qv, body, headers)
            self.throttle.wait()
            res = send(method, url, hdrs, body_text)
            ok = business_success(res)
            doc = res.json()

            if ok and method == "POST" and isinstance(doc, dict):
                created_key = _created_resource_key(doc)
                if created_key:
                    created.append(created_key)

            results.append(StepResult(i, op_id, ok, res.status,
                                      None if ok else _classify_failure(res), resolved_log))
            if not ok:
                return ReplayOutcome(False, results, i, responses, created)
            responses[i] = _response_envelope(res, doc if isinstance(doc, (dict, list)) else None)
            response_request_urls[i] = url

        return ReplayOutcome(True, results, None, responses, created)


def _response_envelope(res: HttpResult, body) -> dict:
    envelope = {"body": body, "headers": _canonical_headers(res.headers), "status": res.status}
    if body is None and res.body_text:
        envelope["body_text"] = res.body_text
    return envelope


def _created_resource_key(doc: dict) -> str | None:
    for key in ("slug", "id", "uuid"):
        value = doc.get(key)
        if isinstance(value, (str, int)) and str(value):
            return str(value)
    for value in doc.values():
        if isinstance(value, dict):
            found = _created_resource_key(value)
            if found:
                return found
    return None


def _call_value_override(override, binding: dict, default, producer_response):
    try:
        return override(binding, default, producer_response)
    except TypeError as exc:
        try:
            return override(binding, default)
        except TypeError:
            raise exc


def _is_response_envelope(response) -> bool:
    return isinstance(response, dict) and "body" in response and "headers" in response and "status" in response


def _response_body(response):
    if _is_response_envelope(response):
        return response.get("body")
    # compatibility with old unit tests / old internal callers: responses passed directly as the parsed body.
    return response


def _canonical_headers(headers: dict | None) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (headers or {}).items()}


def _response_headers(response) -> dict[str, str]:
    if _is_response_envelope(response):
        return _canonical_headers(response.get("headers"))
    return {}


def _response_body_text(response) -> str | None:
    if _is_response_envelope(response):
        value = response.get("body_text")
        return str(value) if value is not None else None
    return None


def _resolve_from_response(
    response,
    from_location: str,
    from_field: str,
    request_url: str | None = None,
):
    if from_location == FROM_RESPONSE_HEADER:
        if is_location_path_field(from_field):
            return extract_location_path_value(
                _response_headers(response).get("location"),
                from_field,
                request_url,
            )
        link_value = _extract_link_path_value(
            _response_headers(response).get("link"),
            from_field,
            request_url,
        )
        if link_value is not None:
            return link_value
        return _response_headers(response).get(str(from_field).lower())
    if from_location == FROM_RESPONSE_BODY and is_xml_field(from_field):
        return extract_xml_value(_response_body_text(response), from_field)
    try:
        return extract_value(_response_body(response), from_field)
    except ValueError:
        # Unsupported JSONPath syntax remains unresolved so V2 replay material
        # overrides can conservatively handle cases such as list wildcards.
        return None


def _extract_link_path_value(link_header: str | None, from_field: str, request_url: str | None) -> str | None:
    field = str(from_field)
    if not field.lower().startswith("link;rel=") or ".path[" not in field or not field.endswith("]"):
        return None
    rel, _, index_text = field[len("Link;rel="):].partition(".path[")
    if not rel or not index_text.endswith("]"):
        return None
    try:
        index = int(index_text[:-1])
    except ValueError:
        return None
    base = urlsplit(str(request_url or ""))
    for link in parse_link_header(link_header):
        if str(link.get("rel") or "link") != rel:
            continue
        url = str(link.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme or parts.netloc:
            if not request_url or parts.scheme != base.scheme or parts.netloc != base.netloc:
                continue
        if parts.query or parts.fragment:
            continue
        path = parts.path if parts.path.startswith("/") else ""
        values = [part for part in path.strip("/").split("/") if part]
        if not values:
            continue
        selected = index
        if selected < 0:
            selected += len(values)
        if selected < 0 or selected >= len(values):
            continue
        return values[selected]
    return None


def _short(value) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return s if len(s) <= 80 else s[:77] + "..."


def _classify_failure(res: HttpResult) -> str:
    """Classify a business failure (S1 diagnostic info goes into the error text; gap a: no dedicated field is added)."""
    doc = res.json()
    detail = ""
    if isinstance(doc, dict) and isinstance(doc.get("errors"), dict):
        detail = json.dumps(doc["errors"], ensure_ascii=False)[:120]
    return f"business_failure: status={res.status} {detail}".strip()
