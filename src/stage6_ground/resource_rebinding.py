"""Deterministic setup-only creator/use resource rebinding."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from urllib.parse import parse_qsl, quote, unquote, urlsplit


_CREATOR_METHODS = {"POST", "PUT", "PATCH"}
_REDACTED = re.compile(r"\[REDACTED:[0-9a-f]+\]")
_PATH_SEGMENT = re.compile(r"^\$\.segments\[(\d+)]$")
_SENSITIVE_PARTS = {
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
}
_EXCLUDED_HEADERS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "connection",
    "content-length",
    "content-type",
    "host",
    "origin",
    "referer",
    "user-agent",
}
_MISSING = object()


class ResourceRebindingError(ValueError):
    """A setup resource dependency cannot be replayed without guessing."""


@dataclass(frozen=True)
class RecordedSetupRequest:
    request_ref: str
    actor_id: str
    order: int
    method: str
    request: dict[str, Any]
    response_status: int
    response_body: Any
    ordinary: bool = True


@dataclass(frozen=True)
class ResourceBindingSource:
    source_id: str
    actor_id: str
    creator_request_ref: str
    response_path: str
    scalar_type: str
    recorded_value_sha256: str
    collection_identity: tuple[tuple[str, str, str], ...] = ()
    collection_identity_shape: tuple[tuple[str, str], ...] = ()
    transport_encoding: str | None = None
    identity_equivalence_request_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceBindingUse:
    source_id: str
    actor_id: str
    consumer_request_ref: str
    location: str
    target_path: str
    scalar_type: str
    recorded_value_sha256: str


@dataclass(frozen=True)
class ResourceBindingIssue:
    consumer_request_ref: str
    reason: str


@dataclass(frozen=True)
class SetupBindingPlan:
    setup_request_refs: tuple[str, ...]
    sources: tuple[ResourceBindingSource, ...]
    uses: tuple[ResourceBindingUse, ...]
    issues: tuple[ResourceBindingIssue, ...]

    @property
    def empty(self) -> bool:
        return not self.sources and not self.uses and not self.issues


@dataclass(frozen=True)
class _ScalarLocation:
    location: str
    path: str
    value: Any
    sensitive: bool


@dataclass(frozen=True)
class _Creator:
    request_ref: str
    actor_id: str
    order: int
    response_paths: tuple[str, ...]
    scalar_type: str
    recorded_value_sha256: str


def build_setup_binding_plan(
    records: list[RecordedSetupRequest],
    *,
    current_session_material: Iterable[str] = (),
) -> SetupBindingPlan:
    """Infer only unique, ordinary-resource bindings from frozen setup facts."""

    refs = tuple(record.request_ref for record in records)
    if len(set(refs)) != len(refs):
        raise ResourceRebindingError("setup contains duplicate request refs")
    secrets = tuple(value for value in current_session_material if value)
    creators_by_value: dict[tuple[str, str], list[_Creator]] = {}
    blocked_by_value: dict[tuple[str, str], list[tuple[str, int, str]]] = {}
    observed_redacted_by_actor_and_field: dict[
        tuple[tuple[str, str], str, str], list[_Creator]
    ] = {}
    for record in records:
        if record.ordinary and 200 <= record.response_status < 400:
            for locations in _group_response_scalars(record.response_body).values():
                for location in locations:
                    if (
                        _redacted_placeholder(location.value)
                        and not location.sensitive
                    ):
                        creator = _Creator(
                            request_ref=record.request_ref,
                            actor_id=record.actor_id,
                            order=record.order,
                            response_paths=(location.path,),
                            scalar_type="string",
                            recorded_value_sha256=scalar_sha256(location.value),
                        )
                        observed_redacted_by_actor_and_field.setdefault(
                            (
                                _value_key(location.value),
                                record.actor_id,
                                _terminal_field(location.path),
                            ),
                            [],
                        ).append(creator)
        if not record.ordinary or record.method.upper() not in _CREATOR_METHODS:
            continue
        if not 200 <= record.response_status < 400:
            continue
        request_values = {
            _value_key(item.value)
            for item in _request_locations(record.request)
            if _eligible_scalar(item.value)
        }
        response_groups = _group_response_scalars(record.response_body)
        for key, locations in response_groups.items():
            if key in request_values:
                continue  # Echoed input is not a newly produced resource value.
            sensitive = any(item.sensitive or _sensitive_value(item.value, secrets) for item in locations)
            if sensitive:
                blocked_by_value.setdefault(key, []).append(
                    (
                        record.actor_id,
                        record.order,
                        "credential-like creator material is not rebindable",
                    )
                )
                continue
            exemplar = locations[0].value
            creator = _Creator(
                request_ref=record.request_ref,
                actor_id=record.actor_id,
                order=record.order,
                response_paths=tuple(item.path for item in locations),
                scalar_type=_scalar_type(exemplar),
                recorded_value_sha256=scalar_sha256(exemplar),
            )
            creators_by_value.setdefault(key, []).append(creator)

    sources: dict[str, ResourceBindingSource] = {}
    uses: list[ResourceBindingUse] = []
    issues: dict[tuple[str, str], ResourceBindingIssue] = {}
    for consumer in records:
        if not consumer.ordinary:
            continue
        target_groups = _group_locations(_request_locations(consumer.request))
        for key, targets in target_groups.items():
            if _redacted_placeholder(targets[0].value) and not any(
                target.sensitive for target in targets
            ):
                target_fields = {_terminal_field(target.path) for target in targets}
                observed = (
                    [
                        source
                        for source in observed_redacted_by_actor_and_field.get(
                            (key, consumer.actor_id, next(iter(target_fields))), []
                        )
                        if source.order < consumer.order
                    ]
                    if len(target_fields) == 1
                    else []
                )
                if observed:
                    latest_order = max(source.order for source in observed)
                    latest = [
                        source for source in observed if source.order == latest_order
                    ]
                    source_keys = {
                        (source.request_ref, source.response_paths[0])
                        for source in latest
                    }
                    if len(source_keys) != 1:
                        reason = "redacted request material source is not unique"
                        issues[(consumer.request_ref, reason)] = ResourceBindingIssue(
                            consumer.request_ref, reason
                        )
                        continue
                    creator = latest[0]
                    source_id = _source_id(creator)
                    sources.setdefault(
                        source_id,
                        ResourceBindingSource(
                            source_id=source_id,
                            actor_id=creator.actor_id,
                            creator_request_ref=creator.request_ref,
                            response_path=creator.response_paths[0],
                            scalar_type=creator.scalar_type,
                            recorded_value_sha256=creator.recorded_value_sha256,
                        ),
                    )
                    for target in sorted(
                        targets, key=lambda item: (item.location, item.path)
                    ):
                        uses.append(
                            ResourceBindingUse(
                                source_id=source_id,
                                actor_id=consumer.actor_id,
                                consumer_request_ref=consumer.request_ref,
                                location=target.location,
                                target_path=target.path,
                                scalar_type=creator.scalar_type,
                                recorded_value_sha256=creator.recorded_value_sha256,
                            )
                        )
                    continue
            prior = [
                creator
                for creator in creators_by_value.get(key, [])
                if creator.order < consumer.order
            ]
            blocked = [
                reason
                for _actor_id, order, reason in blocked_by_value.get(key, [])
                if order < consumer.order
            ]
            if not prior:
                if blocked:
                    issues[(consumer.request_ref, blocked[0])] = ResourceBindingIssue(
                        consumer.request_ref, blocked[0]
                    )
                continue
            if any(target.sensitive or _sensitive_value(target.value, secrets) for target in targets):
                reason = "credential-like consumer material is not rebindable"
                issues[(consumer.request_ref, reason)] = ResourceBindingIssue(consumer.request_ref, reason)
                continue
            if len(prior) != 1:
                reason = "resource creator is not unique"
                issues[(consumer.request_ref, reason)] = ResourceBindingIssue(consumer.request_ref, reason)
                continue
            creator = prior[0]
            if len(creator.response_paths) != 1:
                reason = "resource creator response path is not unique"
                issues[(consumer.request_ref, reason)] = ResourceBindingIssue(consumer.request_ref, reason)
                continue
            if creator.actor_id != consumer.actor_id:
                # Equal scalar values are not cross-actor identity evidence.  Across
                # sessions we only carry a value that was produced at an identity
                # field into an observed path/identifier field.  Ordinary flags,
                # counts and labels therefore remain literal request data.
                if (
                    creator.scalar_type == "boolean"
                    or not _identity_named_path(creator.response_paths[0])
                ):
                    continue
                targets = [
                    target
                    for target in targets
                    if target.location == "path" or _identity_named_path(target.path)
                ]
                if not targets:
                    continue
            target_keys = [(target.location, target.path) for target in targets]
            if len(set(target_keys)) != len(target_keys):
                reason = "resource consumer target location is duplicated"
                issues[(consumer.request_ref, reason)] = ResourceBindingIssue(consumer.request_ref, reason)
                continue
            if any(creator.scalar_type != _scalar_type(target.value) for target in targets):
                reason = "resource source and target types differ"
                issues[(consumer.request_ref, reason)] = ResourceBindingIssue(consumer.request_ref, reason)
                continue
            source_id = _source_id(creator)
            sources.setdefault(
                source_id,
                ResourceBindingSource(
                    source_id=source_id,
                    actor_id=creator.actor_id,
                    creator_request_ref=creator.request_ref,
                    response_path=creator.response_paths[0],
                    scalar_type=creator.scalar_type,
                    recorded_value_sha256=creator.recorded_value_sha256,
                ),
            )
            for target in sorted(targets, key=lambda item: (item.location, item.path)):
                uses.append(
                    ResourceBindingUse(
                        source_id=source_id,
                        actor_id=consumer.actor_id,
                        consumer_request_ref=consumer.request_ref,
                        location=target.location,
                        target_path=target.path,
                        scalar_type=creator.scalar_type,
                        recorded_value_sha256=creator.recorded_value_sha256,
                    )
                )
    return SetupBindingPlan(
        setup_request_refs=refs,
        sources=tuple(sorted(sources.values(), key=lambda item: item.source_id)),
        uses=tuple(
            sorted(uses, key=lambda item: (item.consumer_request_ref, item.location, item.target_path))
        ),
        issues=tuple(
            sorted(issues.values(), key=lambda item: (item.consumer_request_ref, item.reason))
        ),
    )


def capture_creator_values(
    plan: SetupBindingPlan,
    *,
    request_ref: str,
    response_body: Any,
    values: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    """Capture fresh creator values in arm-local memory after a successful replay."""

    for source in plan.sources:
        if source.identity_equivalence_request_refs:
            if request_ref not in source.identity_equivalence_request_refs:
                continue
            value = extract_typed_value(response_body, source.response_path)
            if (
                value is _MISSING
                or not _eligible_scalar(value)
                or _scalar_type(value) != source.scalar_type
            ):
                raise ResourceRebindingError("observed_fresh_source_ambiguous")
            witness_key = _identity_witness_value_key(source.source_id, request_ref)
            existing = values.get(witness_key, _MISSING)
            if existing is not _MISSING and (
                type(existing) is not type(value) or existing != value
            ):
                raise ResourceRebindingError("observed_fresh_source_ambiguous")
            values[witness_key] = copy.deepcopy(value)
            captured = [
                values.get(
                    _identity_witness_value_key(source.source_id, witness),
                    _MISSING,
                )
                for witness in source.identity_equivalence_request_refs
            ]
            if any(item is _MISSING for item in captured):
                continue
            exemplar = captured[0]
            if any(
                type(item) is not type(exemplar) or item != exemplar
                for item in captured[1:]
            ):
                raise ResourceRebindingError("observed_fresh_source_ambiguous")
            values[source.source_id] = copy.deepcopy(exemplar)
            events.append(
                {
                    "event": "creator_value_captured",
                    "actor_id": source.actor_id,
                    "creator_request_ref": source.creator_request_ref,
                    "source_typed_path": source.response_path,
                    "scalar_type": source.scalar_type,
                    "value_sha256": scalar_sha256(exemplar),
                    "fresh_identity_equivalence_proven": True,
                    "identity_witness_count": len(captured),
                }
            )
            continue
        if source.creator_request_ref != request_ref:
            continue
        if source.source_id in values:
            if _scalar_type(values[source.source_id]) != source.scalar_type:
                raise ResourceRebindingError(
                    "preexisting fresh creator scalar type differs from the recorded proof"
                )
            continue
        value, observed_path = _fresh_creator_value(
            response_body, source, values=values
        )
        value = _transport_compatible_source_value(value, source, plan.uses)
        if value is _MISSING or not _eligible_scalar(value):
            raise ResourceRebindingError("fresh creator response is missing the proven scalar")
        value = _coerce_to_proof_scalar_type(value, source.scalar_type)
        if _scalar_type(value) != source.scalar_type:
            raise ResourceRebindingError("fresh creator scalar type differs from the recorded proof")
        values[source.source_id] = value
        event = {
            "event": "creator_value_captured",
            "actor_id": source.actor_id,
            "creator_request_ref": source.creator_request_ref,
            "source_typed_path": source.response_path,
            "scalar_type": source.scalar_type,
            "value_sha256": scalar_sha256(value),
        }
        if source.transport_encoding is not None:
            event["transport_encoding"] = source.transport_encoding
        if observed_path != source.response_path:
            event["observed_source_typed_path"] = observed_path
        events.append(event)


def _identity_witness_value_key(source_id: str, request_ref: str) -> str:
    """Name one arm-local identity witness without exposing its value."""

    return f"{source_id}:identity-witness:{request_ref}"


def _transport_compatible_source_value(
    value: Any,
    source: ResourceBindingSource,
    uses: Sequence[ResourceBindingUse],
) -> Any:
    """Serialize a numeric response identity only for proven URL-path uses."""

    source_uses = [row for row in uses if row.source_id == source.source_id]
    if (
        source.transport_encoding == "url_path_segment_string"
        and source.scalar_type == "string"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and source_uses
        and all(row.location == "path" for row in source_uses)
    ):
        return str(value)
    return value


def apply_consumer_bindings(
    plan: SetupBindingPlan,
    *,
    request_ref: str,
    path: str,
    query: dict[str, Any],
    headers: dict[str, str],
    body: dict[str, Any],
    values: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], dict[str, str], dict[str, Any]]:
    """Atomically apply fresh values to every proven location in a consumer."""

    matching_issues = [issue for issue in plan.issues if issue.consumer_request_ref == request_ref]
    if matching_issues:
        raise ResourceRebindingError(matching_issues[0].reason)
    matching_uses = [use for use in plan.uses if use.consumer_request_ref == request_ref]
    if not matching_uses:
        return path, query, headers, body

    source_rows: dict[str, list[ResourceBindingSource]] = {}
    for source in plan.sources:
        source_rows.setdefault(source.source_id, []).append(source)
    grouped_uses: dict[str, list[ResourceBindingUse]] = {}
    for use in matching_uses:
        grouped_uses.setdefault(use.source_id, []).append(use)

    prepared: list[tuple[ResourceBindingUse, Any, int]] = []
    seen_targets: set[tuple[str, str]] = set()
    for source_id, group in sorted(grouped_uses.items()):
        sources = source_rows.get(source_id, [])
        if len(sources) != 1:
            raise ResourceRebindingError("resource binding source is not unique in the plan")
        source = sources[0]
        proof_rows = {
            (use.scalar_type, use.recorded_value_sha256) for use in group
        }
        if proof_rows != {
            (source.scalar_type, source.recorded_value_sha256)
        }:
            raise ResourceRebindingError("resource consumer target group proof is inconsistent")
        value = values.get(source_id, _MISSING)
        if value is _MISSING:
            raise ResourceRebindingError(
                "observed_fresh_source_ambiguous"
                if source.identity_equivalence_request_refs
                else "fresh creator value is unavailable before resource use"
            )
        if _scalar_type(value) != source.scalar_type:
            raise ResourceRebindingError("fresh creator scalar type changed before resource use")
        ordered_group = sorted(group, key=lambda item: (item.location, item.target_path))
        for use in ordered_group:
            target_key = (use.location, use.target_path)
            if target_key in seen_targets:
                raise ResourceRebindingError("resource consumer target location is duplicated")
            seen_targets.add(target_key)
            _preflight_location(
                use,
                fresh_value=value,
                path=path,
                query=query,
                headers=headers,
                body=body,
            )
            prepared.append((use, value, len(ordered_group)))

    materialized_path = path
    materialized_query = copy.deepcopy(query)
    materialized_headers = copy.deepcopy(headers)
    materialized_body = copy.deepcopy(body)
    pending_events = []
    for use, value, group_size in prepared:
        materialized_path, materialized_query, materialized_headers, materialized_body = (
            _replace_location(
                use,
                value=value,
                path=materialized_path,
                query=materialized_query,
                headers=materialized_headers,
                body=materialized_body,
            )
        )
        event = {
            "event": "consumer_value_rebound",
            "actor_id": use.actor_id,
            "consumer_request_ref": use.consumer_request_ref,
            "target_location": use.location,
            "target_typed_path": use.target_path,
            "scalar_type": use.scalar_type,
            "value_sha256": scalar_sha256(value),
        }
        if group_size > 1:
            event.update({"source_id": use.source_id, "target_group_size": group_size})
        pending_events.append(event)
    events.extend(pending_events)
    return materialized_path, materialized_query, materialized_headers, materialized_body


def extract_typed_value(value: Any, path: str) -> Any:
    """Read the JSONPath subset used by recorded response binding proofs."""

    if path == "$":
        return value
    return _extract_typed_tokens(value, _json_path_tokens(path))


def _coerce_to_proof_scalar_type(value: Any, scalar_type: str) -> Any:
    """Render an integer identifier as text when the recorded proof is a string.

    Integer-id APIs (Vikunja, Paperless-ngx) return ``{"id": 3}`` while the
    recorded consumer carries the same identifier as a path or query segment,
    so the binding proof is typed ``string``.  The fresh value is then compared
    and substituted as the text ``"3"``; proofs of any other type, booleans and
    non-numeric values are returned unchanged.
    """

    if (
        scalar_type == "string"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return str(value)
    return value


def _fresh_creator_value(
    response_body: Any,
    source: ResourceBindingSource,
    *,
    values: dict[str, Any],
) -> tuple[Any, str]:
    value = extract_typed_value(response_body, source.response_path)
    tokens = _json_path_tokens(source.response_path)
    indexed = [index for index, token in enumerate(tokens) if isinstance(token, int)]
    if not indexed:
        return value, source.response_path
    collection_index = indexed[-1]
    collection = _extract_typed_tokens(response_body, tokens[:collection_index])
    if not isinstance(collection, list):
        return value, source.response_path
    suffix = tokens[collection_index + 1 :]
    matches: list[tuple[Any, int]] = []
    for member_index, member in enumerate(collection):
        candidate = _coerce_to_proof_scalar_type(
            _extract_typed_tokens(member, suffix), source.scalar_type
        )
        if not _eligible_scalar(candidate) or _scalar_type(candidate) != source.scalar_type:
            continue
        if source.collection_identity:
            if _member_matches_fresh_identity(member, source=source, values=values):
                matches.append((candidate, member_index))
        elif scalar_sha256(candidate) == source.recorded_value_sha256:
            matches.append((candidate, member_index))
    if len(matches) > 1:
        raise ResourceRebindingError(
            "fresh creator collection contains multiple proven scalar matches"
        )
    if len(matches) == 1:
        candidate, member_index = matches[0]
        observed_tokens = [
            *tokens[:collection_index],
            member_index,
            *suffix,
        ]
        return candidate, _typed_path_from_tokens(observed_tokens)
    raise ResourceRebindingError(
        "fresh creator collection is missing the proven scalar"
    )


def _member_matches_fresh_identity(
    member: Any,
    *,
    source: ResourceBindingSource,
    values: dict[str, Any],
) -> bool:
    if not isinstance(member, dict):
        return False
    for path, scalar_type in source.collection_identity_shape:
        value = extract_typed_value(member, path)
        if value is _MISSING or not _eligible_scalar(value) or _scalar_type(value) != scalar_type:
            return False
    for path, proof_source_id, scalar_type in source.collection_identity:
        proof = values.get(proof_source_id, _MISSING)
        if proof is _MISSING:
            raise ResourceRebindingError(
                "fresh collection identity proof is unavailable before member lookup"
            )
        value = extract_typed_value(member, path)
        if (
            _scalar_type(proof) != scalar_type
            or value is _MISSING
            or type(value) is not type(proof)
            or value != proof
        ):
            return False
    return True


def _extract_typed_tokens(value: Any, tokens: Sequence[str | int]) -> Any:
    current = value
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return _MISSING
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return _MISSING
            current = current[token]
    return current


def _typed_path_from_tokens(tokens: Sequence[str | int]) -> str:
    path = "$"
    for token in tokens:
        path += f"[{token}]" if isinstance(token, int) else f".{token}"
    return path


def typed_value_is_missing(value: Any) -> bool:
    """Return whether ``extract_typed_value`` found no value at its path."""

    return value is _MISSING


def scalar_sha256(value: Any) -> str:
    payload = json.dumps(
        {"type": _scalar_type(value), "value": value},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _replace_location(
    use: ResourceBindingUse,
    *,
    value: Any,
    path: str,
    query: dict[str, Any],
    headers: dict[str, str],
    body: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, str], dict[str, Any]]:
    if use.location == "path":
        match = _PATH_SEGMENT.fullmatch(use.target_path)
        if match is None:
            raise ResourceRebindingError("invalid proven path target")
        segments = path.split("/")
        index = int(match.group(1)) + (1 if path.startswith("/") else 0)
        if index >= len(segments):
            raise ResourceRebindingError("proven path target is missing")
        _assert_bindable_value(unquote(segments[index]), use, fresh_value=value)
        segments[index] = quote(str(value), safe="")
        path = "/".join(segments)
    elif use.location == "query":
        name = _single_key_path(use.target_path)
        if name not in query:
            raise ResourceRebindingError("proven query target is missing")
        _assert_bindable_value(query[name], use, fresh_value=value)
        query[name] = value
    elif use.location == "header":
        name = _single_key_path(use.target_path)
        keys = [key for key in headers if key.lower() == name.lower()]
        if len(keys) != 1:
            raise ResourceRebindingError("proven header target is not unique")
        _assert_bindable_value(headers[keys[0]], use, fresh_value=value)
        headers[keys[0]] = str(value)
    elif use.location == "body":
        current = extract_typed_value(body, use.target_path)
        if current is _MISSING:
            raise ResourceRebindingError("proven body target is missing")
        _assert_bindable_value(current, use, fresh_value=value)
        _strict_set_body_value(body, use.target_path, value)
    else:
        raise ResourceRebindingError("unsupported resource target location")
    return path, query, headers, body


def _preflight_location(
    use: ResourceBindingUse,
    *,
    fresh_value: Any,
    path: str,
    query: dict[str, Any],
    headers: dict[str, str],
    body: dict[str, Any],
) -> None:
    """Validate one target without mutating any request material."""

    if use.location == "path":
        match = _PATH_SEGMENT.fullmatch(use.target_path)
        if match is None:
            raise ResourceRebindingError("invalid proven path target")
        segments = path.split("/")
        index = int(match.group(1)) + (1 if path.startswith("/") else 0)
        if index >= len(segments):
            raise ResourceRebindingError("proven path target is missing")
        current_value = unquote(segments[index])
    elif use.location == "query":
        name = _single_key_path(use.target_path)
        if name not in query:
            raise ResourceRebindingError("proven query target is missing")
        current_value = query[name]
    elif use.location == "header":
        name = _single_key_path(use.target_path)
        keys = [key for key in headers if key.lower() == name.lower()]
        if len(keys) != 1:
            raise ResourceRebindingError("proven header target is not unique")
        current_value = headers[keys[0]]
    elif use.location == "body":
        current_value = extract_typed_value(body, use.target_path)
        if current_value is _MISSING:
            raise ResourceRebindingError("proven body target is missing")
    else:
        raise ResourceRebindingError("unsupported resource target location")
    _assert_bindable_value(current_value, use, fresh_value=fresh_value)


def _assert_bindable_value(
    current_value: Any,
    use: ResourceBindingUse,
    *,
    fresh_value: Any,
) -> None:
    if not _eligible_scalar(current_value) or _scalar_type(current_value) != use.scalar_type:
        raise ResourceRebindingError("recorded consumer material no longer matches the binding proof")
    current_sha256 = scalar_sha256(current_value)
    if current_sha256 not in {
        use.recorded_value_sha256,
        scalar_sha256(fresh_value),
    }:
        raise ResourceRebindingError("recorded consumer value hash no longer matches the binding proof")


def _strict_set_body_value(body: dict[str, Any], path: str, value: Any) -> None:
    tokens = _json_path_tokens(path)
    if not tokens:
        raise ResourceRebindingError("empty body target path")
    current: Any = body
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                raise ResourceRebindingError("body array target is missing")
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                raise ResourceRebindingError("body object target is missing")
            current = current[token]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(current, list) or last >= len(current):
            raise ResourceRebindingError("body array target is missing")
        current[last] = value
    else:
        if not isinstance(current, dict) or last not in current:
            raise ResourceRebindingError("body object target is missing")
        current[last] = value


def _request_locations(request: dict[str, Any]) -> list[_ScalarLocation]:
    locations: list[_ScalarLocation] = []
    split = urlsplit(str(request.get("url") or ""))
    for index, segment in enumerate(item for item in split.path.split("/") if item):
        value = unquote(segment)
        locations.append(_ScalarLocation("path", f"$.segments[{index}]", value, False))
    query_rows = request.get("queryString")
    if not isinstance(query_rows, list) or (not query_rows and split.query):
        query_rows = [{"name": key, "value": value} for key, value in parse_qsl(split.query, keep_blank_values=True)]
    for row in query_rows:
        name = str(row.get("name") or "")
        value = row.get("value")
        locations.append(_ScalarLocation("query", f"$.{name}", value, _sensitive_path(name)))
    post = request.get("postData") or {}
    mime = str(post.get("mimeType") or "").lower()
    text = post.get("text")
    if "json" in mime and isinstance(text, str) and text:
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = None
        if body is not None:
            locations.extend(_walk_scalars(body, location="body"))
    elif "x-www-form-urlencoded" in mime:
        for row in post.get("params") or []:
            name = str(row.get("name") or "")
            value = row.get("value")
            locations.append(_ScalarLocation("body", f"$.{name}", value, _sensitive_path(name)))
    for row in request.get("headers") or []:
        name = str(row.get("name") or "")
        folded = name.lower()
        if folded in _EXCLUDED_HEADERS:
            continue
        locations.append(
            _ScalarLocation("header", f"$.{name}", row.get("value"), _sensitive_path(name))
        )
    return locations


def _group_response_scalars(value: Any) -> dict[tuple[str, str], list[_ScalarLocation]]:
    if not isinstance(value, (dict, list)):
        return {}
    return _group_locations(_walk_scalars(value, location="response"))


def _group_locations(locations: Iterable[_ScalarLocation]) -> dict[tuple[str, str], list[_ScalarLocation]]:
    groups: dict[tuple[str, str], list[_ScalarLocation]] = {}
    for location in locations:
        if not _eligible_scalar(location.value):
            continue
        groups.setdefault(_value_key(location.value), []).append(location)
    return groups


def _walk_scalars(value: Any, *, location: str, path: str = "$") -> list[_ScalarLocation]:
    rows: list[_ScalarLocation] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if isinstance(child, (dict, list)):
                rows.extend(_walk_scalars(child, location=location, path=child_path))
            else:
                rows.append(
                    _ScalarLocation(location, child_path, child, _sensitive_path(child_path))
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if isinstance(child, (dict, list)):
                rows.extend(_walk_scalars(child, location=location, path=child_path))
            else:
                rows.append(
                    _ScalarLocation(location, child_path, child, _sensitive_path(child_path))
                )
    return rows


def _eligible_scalar(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value)
    return isinstance(value, (int, float, bool))


def _scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    raise ResourceRebindingError("resource value is not a supported scalar")


def _value_key(value: Any) -> tuple[str, str]:
    return _scalar_type(value), json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sensitive_path(path: str) -> bool:
    folded = path.lower().replace("_", "-")
    return any(part in folded for part in _SENSITIVE_PARTS)


def _identity_named_path(path: str) -> bool:
    """Recognize an observed identifier position without using subject semantics."""

    name = path.rsplit(".", 1)[-1]
    name = re.sub(r"\[\d+]$", "", name)
    folded = name.lower().replace("-", "_")
    return (
        folded in {"id", "uuid"}
        or folded.endswith(("_id", "_uuid"))
        or name.endswith(("Id", "ID", "Uuid", "UUID"))
    )


def _sensitive_value(value: Any, secrets: tuple[str, ...]) -> bool:
    return isinstance(value, str) and (
        _REDACTED.search(value) is not None or any(secret and secret in value for secret in secrets)
    )


def _redacted_placeholder(value: Any) -> bool:
    return isinstance(value, str) and _REDACTED.fullmatch(value) is not None


def _terminal_field(path: str) -> str:
    name = path.rsplit(".", 1)[-1]
    return re.sub(r"\[\d+]$", "", name).lower().replace("-", "_")


def _source_id(creator: _Creator) -> str:
    payload = "|".join(
        (
            creator.actor_id,
            creator.request_ref,
            creator.response_paths[0],
            creator.scalar_type,
            creator.recorded_value_sha256,
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _single_key_path(path: str) -> str:
    if not path.startswith("$.") or "." in path[2:] or "[" in path:
        raise ResourceRebindingError("target is not a single-key typed path")
    return path[2:]


def _json_path_tokens(path: str) -> list[str | int]:
    if path == "$":
        return []
    tokens: list[str | int] = []
    if path.startswith("$["):
        root = re.match(r"^\$\[(\d+)](?:\.(.*))?$", path)
        if root is None:
            raise ResourceRebindingError("typed path is outside the supported JSONPath subset")
        tokens.append(int(root.group(1)))
        remainder = root.group(2)
        if remainder is None:
            return tokens
    elif path.startswith("$."):
        remainder = path[2:]
    else:
        raise ResourceRebindingError("typed path must start with $.")
    for segment in remainder.split("."):
        match = re.fullmatch(r"([A-Za-z0-9_]+)(?:\[(\d+)])?", segment)
        if match is None:
            raise ResourceRebindingError("typed path is outside the supported JSONPath subset")
        tokens.append(match.group(1))
        if match.group(2) is not None:
            tokens.append(int(match.group(2)))
    return tokens
