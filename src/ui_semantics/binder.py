"""Deterministic UI-action to API-request binding."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ASSET_PREFIXES = ("/assets/", "/static/", "/favicon")
ASSET_TYPES = {"font", "image", "media", "stylesheet"}
INPUT_LIKE_ACTION_TYPES = frozenset({"input", "fill", "type"})
SUBMIT_LIKE_ACTION_TYPES = frozenset({"click", "submit"})
SUBMIT_KEYS = frozenset({"Enter", "NumpadEnter"})
REDACTED_LITERAL = re.compile(r"^\[REDACTED(?::[A-Za-z0-9_.-]+)?\]$")
CSS_ATTRIBUTE_VALUE = re.compile(
    r"\[\s*[-A-Za-z0-9_:]+\s*[~|^$*]?=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\]\s]+))\s*\]"
)


@dataclass(frozen=True)
class BindingDecision:
    event_id: str
    request_ref: str | None
    status: str
    candidate_request_refs: tuple[str, ...]
    evidence: tuple[str, ...]
    reason: str


def bind_actions(
    actions: Iterable[dict[str, Any]],
    requests: Iterable[dict[str, Any]],
) -> list[BindingDecision]:
    """Bind by action window and actor, preferring causal mutations and page data."""
    request_list = list(requests)
    action_list = list(actions)
    action_by_step_id = {
        str(action.get("workflow_step_id")): action
        for action in action_list
        if action.get("workflow_step_id")
    }
    decisions = []
    previous_by_actor: dict[str, dict[str, Any]] = {}
    for action in action_list:
        actor = str(action["actor"])
        decisions.append(
            _bind_action(
                action,
                request_list,
                previous_action=previous_by_actor.get(actor),
                action_by_step_id=action_by_step_id,
            )
        )
        previous_by_actor[actor] = action
    return decisions


def _bind_action(
    action: dict[str, Any],
    requests: list[dict[str, Any]],
    *,
    previous_action: dict[str, Any] | None,
    action_by_step_id: dict[str, dict[str, Any]],
) -> BindingDecision:
    event_id = str(action["id"])
    actor = str(action["actor"])
    started = int(action["started_at_ms"])
    finished = int(action["finished_at_ms"])
    candidates = [
        request
        for request in requests
        if request.get("actor") == actor
        and started <= int(request.get("started_at_ms", -1)) <= finished
        and not _is_asset(request)
        and not _is_navigation_helper(request)
    ]
    refs = tuple(str(item["id"]) for item in candidates)
    base_evidence = ("action_window", "actor_session")
    if not candidates:
        return BindingDecision(event_id, None, "none", (), base_evidence, "no request in actor action window")

    mutations = [item for item in candidates if request_is_mutating(item)]
    if len(mutations) == 1:
        return _confirmed(
            event_id,
            mutations[0],
            refs,
            _candidate_evidence(action, mutations[0], base_evidence),
            "single mutating request in window",
        )
    if len(mutations) > 1:
        strong_match = _unique_strong_mutation_match(
            action,
            previous_action,
            mutations,
            action_by_step_id=action_by_step_id,
        )
        if strong_match is not None:
            request, reasons = strong_match
            return _confirmed(
                event_id,
                request,
                refs,
                (*_candidate_evidence(action, request, base_evidence), *reasons),
                reasons[0],
            )
        return _review(event_id, refs, base_evidence, "multiple mutating requests in window")

    graphql = [item for item in candidates if _graphql_operation(item)]
    if len(graphql) == 1 and len(candidates) == 1:
        return _confirmed(
            event_id,
            graphql[0],
            refs,
            (*base_evidence, "graphql_operation_name"),
            "single named GraphQL operation in window",
        )
    if len(graphql) > 1 and len(graphql) == len(candidates):
        return _review(event_id, refs, (*base_evidence, "graphql_operation_name"), "multiple GraphQL operations")

    after_path = _url_path((action.get("after") or {}).get("url"))
    page_matches = [item for item in candidates if _request_path(item) == after_path]
    if len(page_matches) == 1:
        return _confirmed(
            event_id,
            page_matches[0],
            refs,
            (*base_evidence, "url_transition"),
            "request path matches resulting page",
        )

    foreground = [item for item in candidates if not item.get("background", False)]
    if len(foreground) == 1:
        return _confirmed(event_id, foreground[0], refs, base_evidence, "single foreground request in window")
    if len(candidates) == 1:
        return _confirmed(event_id, candidates[0], refs, base_evidence, "single request in window")
    return _review(event_id, refs, base_evidence, "multiple read requests without deterministic primary")


def _confirmed(
    event_id: str,
    request: dict[str, Any],
    refs: tuple[str, ...],
    evidence: tuple[str, ...],
    reason: str,
) -> BindingDecision:
    return BindingDecision(event_id, str(request["id"]), "confirmed", refs, evidence, reason)


def _review(
    event_id: str,
    refs: tuple[str, ...],
    evidence: tuple[str, ...],
    reason: str,
) -> BindingDecision:
    return BindingDecision(event_id, None, "review_required", refs, evidence, reason)


def _is_asset(request: dict[str, Any]) -> bool:
    path = _request_path(request)
    return str(request.get("resource_type", "")).lower() in ASSET_TYPES or path.startswith(ASSET_PREFIXES)


def _is_navigation_helper(request: dict[str, Any]) -> bool:
    body = request.get("request_body")
    return _request_path(request).endswith("/fetch-redirect") and isinstance(body, dict) and "redirect" in body


def request_is_mutating(request: dict[str, Any]) -> bool:
    if str(request.get("method", "")).upper() not in MUTATING_METHODS:
        return False
    if request.get("declared_read_semantic") is True:
        # The profile declares this exact method/path pair as a read-semantic
        # query endpoint (see AppProfile.read_semantic_endpoints); it is not a
        # mutation for anchoring.  Undeclared POSTs stay mutating as before.
        return False
    operation_kind = graphql_operation_kind(request.get("request_body"))
    if operation_kind is None:
        return True
    return operation_kind == "mutation"


def graphql_operation_kind(body: Any) -> str | None:
    """Resolve one recorded GraphQL operation without endpoint-name heuristics.

    The selected operation is determined from the query document and
    ``operationName``. Ambiguous or malformed documents fail closed as
    ``"unknown"``; non-GraphQL bodies return ``None``.
    """

    if not isinstance(body, dict) or not isinstance(body.get("query"), str):
        return None
    document = _mask_graphql_comments_and_strings(body["query"])
    operations = _graphql_operation_definitions(document)
    if operations is None or not operations:
        return "unknown"
    selected = body.get("operationName")
    if selected is not None and (
        not isinstance(selected, str) or not selected.strip()
    ):
        return "unknown"
    if selected is None:
        return operations[0][0] if len(operations) == 1 else "unknown"
    matches = [kind for kind, name in operations if name == selected]
    return matches[0] if len(matches) == 1 else "unknown"


def _mask_graphql_comments_and_strings(document: str) -> str:
    chars = list(document)
    index = 0
    while index < len(chars):
        if chars[index] == "#":
            end = document.find("\n", index)
            end = len(chars) if end < 0 else end
            chars[index:end] = " " * (end - index)
            index = end
            continue
        if document.startswith('"""', index):
            end = document.find('"""', index + 3)
            if end < 0:
                return ""
            end += 3
            chars[index:end] = " " * (end - index)
            index = end
            continue
        if chars[index] == '"':
            end = index + 1
            escaped = False
            while end < len(chars):
                if chars[end] == '"' and not escaped:
                    end += 1
                    break
                escaped = chars[end] == "\\" and not escaped
                if chars[end] != "\\":
                    escaped = False
                end += 1
            else:
                return ""
            chars[index:end] = " " * (end - index)
            index = end
            continue
        index += 1
    return "".join(chars)


def _graphql_operation_definitions(
    document: str,
) -> list[tuple[str, str | None]] | None:
    operations: list[tuple[str, str | None]] = []
    depth = 0
    index = 0
    while index < len(document):
        char = document[index]
        if char == "{":
            if depth == 0:
                previous = document[:index].rstrip()
                if not previous or previous.endswith("}"):
                    operations.append(("query", None))
            depth += 1
            index += 1
            continue
        if char == "}":
            depth -= 1
            if depth < 0:
                return None
            index += 1
            continue
        if depth or not (char.isalpha() or char == "_"):
            index += 1
            continue
        end = index + 1
        while end < len(document) and (
            document[end].isalnum() or document[end] == "_"
        ):
            end += 1
        token = document[index:end]
        if token in {"query", "mutation", "subscription"}:
            cursor = end
            while cursor < len(document) and document[cursor].isspace():
                cursor += 1
            name: str | None = None
            if cursor < len(document) and (
                document[cursor].isalpha() or document[cursor] == "_"
            ):
                name_end = cursor + 1
                while name_end < len(document) and (
                    document[name_end].isalnum() or document[name_end] == "_"
                ):
                    name_end += 1
                name = document[cursor:name_end]
            operations.append((token, name))
        index = end
    if depth != 0 or any(kind == "subscription" for kind, _ in operations):
        return None
    return operations


def _candidate_evidence(
    action: dict[str, Any],
    request: dict[str, Any],
    base: tuple[str, ...],
) -> tuple[str, ...]:
    evidence = list(base)
    after_path = _url_path((action.get("after") or {}).get("url"))
    if after_path and _request_path(request) == after_path:
        evidence.append("url_transition")
    if _parameter_overlap(action, request):
        evidence.append("parameter_overlap")
    if _form_field_overlap(action, request):
        evidence.append("form_field_overlap")
    if _graphql_operation(request):
        evidence.append("graphql_operation_name")
    return tuple(dict.fromkeys(evidence))


def _parameter_overlap(action: dict[str, Any], request: dict[str, Any]) -> bool:
    page_url = str((action.get("after") or {}).get("url") or "")
    page = urlsplit(page_url)
    page_values = {part for part in page.path.split("/") if part}
    page_values.update(value for _, value in parse_qsl(page.query) if value)
    request_url = urlsplit(str(request.get("path") or ""))
    request_values = {part for part in request_url.path.split("/") if part}
    request_values.update(value for _, value in parse_qsl(request_url.query) if value)
    return bool(page_values & request_values)


def _form_field_overlap(action: dict[str, Any], request: dict[str, Any]) -> bool:
    fields = action.get("form_fields") or action.get("input_values")
    body = request.get("request_body")
    if not isinstance(fields, dict) or not isinstance(body, dict):
        return False
    return bool(set(fields) & set(body))


def _unique_strong_mutation_match(
    action: dict[str, Any],
    previous_action: dict[str, Any] | None,
    mutations: list[dict[str, Any]],
    *,
    action_by_step_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], tuple[str, ...]] | None:
    if not _is_submit_like(action):
        return None
    request_scalars = [_request_leaf_scalars(request) for request in mutations]
    evidence_targets: list[tuple[int, str]] = []

    material_refs = tuple(action.get("binding_material_source_step_ids") or ())
    if material_refs:
        source_actions = [action_by_step_id.get(str(item)) for item in material_refs]
        if any(source is None for source in source_actions):
            return None
        material_reason = "explicit_input_material_match"
    elif (
        previous_action is not None
        and str(previous_action.get("action_type") or "").lower()
        in INPUT_LIKE_ACTION_TYPES
    ):
        source_actions = [previous_action]
        material_reason = "adjacent_input_literal_match"
    else:
        source_actions = []
        material_reason = ""

    for source in source_actions:
        literals = _input_literals(source)
        if not literals:
            return None
        for literal in literals:
            matches = [
                index
                for index, scalars in enumerate(request_scalars)
                if literal in scalars
            ]
            if len(matches) != 1:
                return None
            evidence_targets.append((matches[0], material_reason))

    locator_values = _locator_material_values(action)
    for value in locator_values:
        matches = [
            index
            for index, scalars in enumerate(request_scalars)
            if _typed_scalar_key(value) in scalars
        ]
        if len(matches) > 1:
            return None
        if len(matches) == 1:
            evidence_targets.append((matches[0], "locator_leaf_exact_match"))

    if not evidence_targets:
        return None
    indexes = {index for index, _ in evidence_targets}
    if len(indexes) != 1:
        return None
    index = next(iter(indexes))
    reason_order = (
        "explicit_input_material_match",
        "adjacent_input_literal_match",
        "locator_leaf_exact_match",
    )
    reasons = {reason for _, reason in evidence_targets}
    ordered_reasons = tuple(reason for reason in reason_order if reason in reasons)
    return mutations[index], ordered_reasons


def _is_submit_like(action: dict[str, Any]) -> bool:
    action_type = str(action.get("action_type") or "").lower()
    return action_type in SUBMIT_LIKE_ACTION_TYPES or (
        action_type == "press" and action.get("key") in SUBMIT_KEYS
    )


def _input_literals(action: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    values: list[Any] = [action.get("value")]
    for field in ("input_values", "form_fields"):
        mapping = action.get(field)
        if isinstance(mapping, dict):
            values.extend(mapping.values())
    literals: list[Any] = []
    for value in values:
        if value is None or isinstance(value, (dict, list)):
            continue
        if isinstance(value, str) and (
            not value.strip() or REDACTED_LITERAL.fullmatch(value.strip())
        ):
            continue
        if not isinstance(value, (str, bool, int, float)):
            continue
        literals.append(value)
    return tuple(dict.fromkeys(_typed_scalar_key(value) for value in literals))


def _locator_material_values(action: dict[str, Any]) -> tuple[str, ...]:
    selector = action.get("selector")
    locator: Any = None
    if isinstance(selector, dict):
        locator = selector
    elif isinstance(selector, str):
        try:
            parsed = json.loads(selector)
        except (TypeError, ValueError):
            parsed = None
        locator = parsed if isinstance(parsed, dict) else {"kind": "css", "value": selector}
    if not isinstance(locator, dict):
        return ()
    kind = locator.get("kind")
    value = locator.get("value")
    if not isinstance(value, str):
        return ()
    if kind == "test_id":
        return (value,)
    if kind != "css":
        return ()
    values = []
    for match in CSS_ATTRIBUTE_VALUE.finditer(value):
        candidate = next(item for item in match.groups() if item is not None)
        if candidate:
            values.append(candidate)
    return tuple(dict.fromkeys(values))


def _request_leaf_scalars(request: dict[str, Any]) -> set[tuple[str, Any]]:
    split = urlsplit(str(request.get("path") or ""))
    values: list[Any] = [part for part in split.path.split("/") if part]
    values.extend(value for _, value in parse_qsl(split.query, keep_blank_values=False))
    values.extend(_nested_scalars(request.get("request_body")))
    return {
        _typed_scalar_key(value)
        for value in values
        if value is not None and isinstance(value, (str, bool, int, float))
    }


def _typed_scalar_key(value: Any) -> tuple[str, Any]:
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, int):
        return ("integer", value)
    if isinstance(value, float):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    raise TypeError("binding material is not a JSON scalar")


def _nested_scalars(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [scalar for child in value.values() for scalar in _nested_scalars(child)]
    if isinstance(value, (list, tuple)):
        return [scalar for child in value for scalar in _nested_scalars(child)]
    return [value]


def _request_path(request: dict[str, Any]) -> str:
    return urlsplit(str(request.get("path") or "/")).path or "/"


def _url_path(url: Any) -> str:
    if not url or str(url) == "about:blank":
        return ""
    return urlsplit(str(url)).path or "/"


def _graphql_operation(request: dict[str, Any]) -> str | None:
    body = request.get("request_body")
    if (
        graphql_operation_kind(body) in {"query", "mutation"}
        and isinstance(body.get("operationName"), str)
    ):
        return body["operationName"]
    return None
