"""Canonical path normalization (003 D23, conservative by default + 003A disclosure details).

Not parameterized by default. Parameterizing a segment requires one of these positive evidences:
(1) strong value form (UUID/ObjectId/ISO date/≥3-digit number/≥16-digit hex; a single observation suffices);
(2) value flow: the value exactly matches a string in a strictly earlier 2xx JSON response body of the same bundle;
    a stable word form must also come from an identity-like field; a short number also needs a source path of the same resource family;
(3) diverse values at the same position and neither side is a stable word form (^[A-Za-z][A-Za-z0-9_]*$).
Anti-merge criterion (veto): disjoint and both non-empty top-level shape signature sets of 2xx JSON responses → no merge.
Canonicalization fallback at the output boundary (each observation maps to exactly one template).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from .api_filter import ApiObservation

STRONG_FORM_PATTERNS = [
    re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),  # UUID
    re.compile(r"^[0-9a-fA-F]{24}$"),  # Mongo ObjectId
    re.compile(r"^\d{4}-\d{2}-\d{2}(T.*)?$"),  # ISO date/date-time
    re.compile(r"^\d{3,}$"),  # ≥3-digit number
    re.compile(r"^[0-9a-fA-F]{16,}$"),  # ≥16 hex digits
]
STABLE_SEGMENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")  # 003A disclosure detail 1
# Backwards-compatible export for Stage2.5 canonicalization.  The semantics are
# intentionally widened from lowercase words to API collection-like identifiers
# such as BasketItems and SecurityQuestions.
STABLE_WORD = STABLE_SEGMENT
SHORT_DIGITS = re.compile(r"^\d{1,2}$")
IDENTITY_FIELD = re.compile(
    r"(^id$|(?:^|[_-])[a-z0-9]*id$|^[a-z0-9]+id$|^slug$|^uuid$|^number$|^index$)"
)


@dataclass(frozen=True)
class IdentityValueSeen:
    started_ts: float
    path: str
    field_path: tuple[str, ...]


def _collect_strings(value, out: set[str]) -> None:
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _collect_strings(v, out)


def _identity_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9_-]+", "", name.lower())
    return bool(IDENTITY_FIELD.match(normalized))


def _collect_identity_values(
    value, out: dict[str, list[tuple[str, ...]]], path: tuple[str, ...] = ()
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            if (
                _identity_field(str(key))
                and not isinstance(child, bool)
                and isinstance(child, (int, float, str))
            ):
                text = str(child)
                if text:
                    out.setdefault(text, []).append(child_path)
            _collect_identity_values(child, out, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_identity_values(child, out, (*path, str(index)))


def build_value_first_seen(observations: list[ApiObservation]) -> dict[str, dict[str, float]]:
    """Per session bundle: string value → start time of the request whose 2xx JSON response body first contained it."""
    first_seen: dict[str, dict[str, float]] = defaultdict(dict)
    for obs in sorted(observations, key=lambda o: (o.run_id, o.started_ts)):
        if obs.response_body_json is None:
            continue
        strings: set[str] = set()
        _collect_strings(obs.response_body_json, strings)
        per_bundle = first_seen[obs.run_id]
        for s in strings:
            if s not in per_bundle or obs.started_ts < per_bundle[s]:
                per_bundle[s] = obs.started_ts
    return first_seen


def build_identity_value_seen(
    observations: list[ApiObservation],
) -> dict[str, dict[str, list[IdentityValueSeen]]]:
    """Per session bundle: identity-like response field value → its 2xx JSON response body sources."""
    seen: dict[str, dict[str, list[IdentityValueSeen]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for obs in sorted(observations, key=lambda o: (o.run_id, o.started_ts)):
        if obs.response_body_json is None:
            continue
        values: dict[str, list[tuple[str, ...]]] = {}
        _collect_identity_values(obs.response_body_json, values)
        per_bundle = seen[obs.run_id]
        for value, field_paths in values.items():
            for field_path in field_paths:
                per_bundle[value].append(
                    IdentityValueSeen(
                        started_ts=obs.started_ts,
                        path=obs.path,
                        field_path=field_path,
                    )
                )
    return seen


def _segments(path: str) -> list[str]:
    stripped = path.strip("/")
    return stripped.split("/") if stripped else []


def _resource_token(segment: str) -> str:
    token = segment.lower()
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def _resource_family_tokens(segments: list[str]) -> list[str]:
    out = [_resource_token(segment) for segment in segments]
    while out and (out[0] in {"api", "rest"} or re.fullmatch(r"v\d+", out[0])):
        out.pop(0)
    if out and out[-1] in {"search", "list", "index", "all"}:
        out.pop()
    return out


def _namespace_parent(segments: list[str], index: int) -> bool:
    """True when segments[index] is the top-level collection under /api or /rest."""
    parent = [segment.lower() for segment in segments[:index]]
    while parent and re.fullmatch(r"v\d+", parent[-1]):
        parent.pop()
    return bool(parent) and all(segment in {"api", "rest"} for segment in parent)


def _same_resource_family(source_path: str, target_path: str, value: str) -> bool:
    source = _segments(source_path)
    target = _segments(target_path)
    for index, segment in enumerate(target):
        if segment != value:
            continue
        parent = target[:index]
        if not parent or not source:
            continue
        if source == parent:
            return True
        if len(source) == len(parent) and all(
            a == b or _resource_token(a) == _resource_token(b)
            for a, b in zip(source, parent)
        ):
            return True
        if source[:-1] == parent[:-1] and _resource_token(source[-1]) == _resource_token(
            parent[-1]
        ):
            return True
        normalized_source = _resource_family_tokens(source)
        normalized_parent = _resource_family_tokens(parent)
        if normalized_source and normalized_source == normalized_parent:
            return True
    return False


class CanonicalIndex:
    """Induce templates from the observation set and map literal paths → canonical templates."""

    def __init__(self, observations: list[ApiObservation]):
        self._observations = observations
        self._value_first_seen = build_value_first_seen(observations)
        self._identity_value_seen = build_identity_value_seen(observations)
        # (method, literal_path) → shape signature set / evidence observations
        self._by_literal: dict[tuple[str, str], list[ApiObservation]] = defaultdict(list)
        for obs in observations:
            self._by_literal[(obs.method, obs.path)].append(obs)
        self._template_map = self._induce()  # (method, literal_path) → template segment tuple
        self._resolve_weak_static_collisions()
        self._param_names = self._assign_param_names()

    # --- evidence checks ---

    def _has_value_flow(self, method: str, path: str, value: str) -> bool:
        """003A detail 2: value-flow evidence (exact match with a strictly earlier response body value in the same session bundle)."""
        for obs in self._by_literal[(method, path)]:
            seen = self._value_first_seen.get(obs.run_id, {})
            ts = seen.get(value)
            if ts is not None and ts < obs.started_ts:
                return True
        return False

    def _has_identity_value_flow(self, method: str, path: str, value: str) -> bool:
        """A short numeric path segment only accepts identity-like response field + same resource family + causal order evidence."""
        if not SHORT_DIGITS.match(value):
            return False
        for obs in self._by_literal[(method, path)]:
            records = self._identity_value_seen.get(obs.run_id, {}).get(value, [])
            for record in records:
                if record.started_ts < obs.started_ts and _same_resource_family(
                    record.path, path, value
                ):
                    return True
        return False

    def _has_any_identity_value_flow(self, method: str, path: str, value: str) -> bool:
        """Identity-field value flow for non-numeric IDs used by collision resolution."""
        for obs in self._by_literal[(method, path)]:
            records = self._identity_value_seen.get(obs.run_id, {}).get(value, [])
            for record in records:
                if record.started_ts < obs.started_ts and _same_resource_family(
                    record.path, path, value
                ):
                    return True
        return False

    def _has_identity_origin_value_flow(
        self, method: str, path: str, value: str
    ) -> bool:
        """Accept prior identity across resources, e.g. transaction.id in comments/{id}."""
        for obs in self._by_literal[(method, path)]:
            records = self._identity_value_seen.get(obs.run_id, {}).get(value, [])
            if any(record.started_ts < obs.started_ts for record in records):
                return True
        return False

    @staticmethod
    def _strong_form(value: str) -> bool:
        return any(p.match(value) for p in STRONG_FORM_PATTERNS)

    def _param_evidence(self, method: str, path: str, value: str, diverse: bool) -> bool:
        if self._strong_form(value):
            return True  # (1)
        if self._has_identity_value_flow(method, path, value):
            return True  # (2) (short numeric identity-like value flow)
        if not SHORT_DIGITS.match(value) and self._has_identity_origin_value_flow(
            method, path, value
        ):
            return True  # (2) (cross-resource identity-like value flow)
        if self._has_value_flow(method, path, value) and not STABLE_SEGMENT.match(value):
            return True  # (2) (plain value flow of a non-stable word form)
        return diverse and not STABLE_SEGMENT.match(value)  # (3)

    def _shape_signature(self, method: str, path: str) -> frozenset:
        shapes = set()
        for obs in self._by_literal[(method, path)]:
            body = obs.response_body_json
            if body is None:
                continue
            if isinstance(body, list):
                shapes.add(("array",))
            elif isinstance(body, dict):
                shapes.add(("object", tuple(sorted(body.keys()))))
            else:
                shapes.add(("scalar", type(body).__name__))
        return frozenset(shapes)

    def _shapes_compatible(self, method: str, a: str, b: str) -> bool:
        sa, sb = self._shape_signature(method, a), self._shape_signature(method, b)
        return not sa or not sb or bool(sa & sb)  # no veto when either side lacks evidence (D23)

    def _mergeable(self, method: str, a: str, b: str) -> bool:
        sa, sb = a.strip("/").split("/"), b.strip("/").split("/")
        if len(sa) != len(sb):
            return False
        diff = [i for i in range(len(sa)) if sa[i] != sb[i]]
        if not diff:
            return True
        if not self._shapes_compatible(method, a, b):
            return False  # anti-merge criterion (the feed trap)
        for i in diff:
            if (
                _namespace_parent(sa, i)
                and _namespace_parent(sb, i)
                and STABLE_SEGMENT.match(sa[i])
                and STABLE_SEGMENT.match(sb[i])
            ):
                return False
            if not self._param_evidence(method, a, sa[i], diverse=True):
                return False
            if not self._param_evidence(method, b, sb[i], diverse=True):
                return False
        return True

    # --- induction ---

    def _cluster_bucket(self, method: str, paths: list[str]) -> list[list[str]]:
        """Union-find clustering within a bucket (deterministic: pairwise checks over sorted paths)."""
        parent = {p: p for p in paths}

        def find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                if self._mergeable(method, paths[i], paths[j]):
                    parent[find(paths[j])] = find(paths[i])
        clusters: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            clusters[find(p)].append(p)
        return [sorted(members) for _, members in sorted(clusters.items())]

    def _template_for_cluster(self, method: str, members: list[str]) -> tuple[str, ...]:
        """Cluster → template: multi-valued segments are parameterized (evidence already checked in mergeable); a single-path single-valued segment needs strong evidence (1)/(2)."""
        seg_lists = [m.strip("/").split("/") for m in members]
        template: list[str] = []
        for i in range(len(seg_lists[0])):
            values = sorted({segs[i] for segs in seg_lists})
            if len(values) > 1:
                template.append("{}")
            elif (
                len(members) == 1
                and not (
                    _namespace_parent(seg_lists[0], i)
                    and STABLE_SEGMENT.match(values[0])
                )
                and self._param_evidence(method, members[0], values[0], diverse=False)
            ):
                template.append("{}")  # single-path induction (003 D23 single-valued segment rule)
            else:
                template.append(values[0])
        return tuple(template)

    def _induce(self) -> dict[tuple[str, str], tuple[str, ...]]:
        result: dict[tuple[str, str], tuple[str, ...]] = {}
        buckets: dict[tuple[str, int], list[str]] = defaultdict(list)
        for (method, path) in sorted(self._by_literal):
            buckets[(method, len(path.strip("/").split("/")))].append(path)
        for (method, _), paths in sorted(buckets.items()):
            for members in self._cluster_bucket(method, sorted(paths)):
                template = self._template_for_cluster(method, members)
                for m in members:
                    result[(method, m)] = template
        return result

    def _resolve_weak_static_collisions(self) -> None:
        """Keep one weak stable literal exact when provisional templates collide.

        Pairwise clustering already rejects incompatible response shapes. A separate
        failure mode remains when two single-member clusters independently infer the
        same template. Only a uniquely identifiable, generic-value-flow stable literal
        may be demoted automatically; every ambiguous collision fails closed.
        """
        groups: dict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
        for (method, path), template in self._template_map.items():
            groups[(method, template)].append(path)

        for (method, template), paths in sorted(groups.items()):
            if len(paths) < 2:
                continue
            incompatible = {
                path
                for path in paths
                if any(
                    not self._shapes_compatible(method, path, peer)
                    for peer in paths
                    if peer != path
                )
            }
            if not incompatible:
                continue
            weak = [
                path
                for path in paths
                if path in incompatible and self._weak_static_template(method, path, template)
            ]
            if len(weak) != 1:
                raise ValueError(
                    "ambiguous canonical collision: "
                    f"{method} {self._display_template(template)} <- {sorted(paths)}; "
                    f"weak_static_candidates={sorted(weak)}"
                )
            literal = weak[0]
            self._template_map[(method, literal)] = tuple(_segments(literal))

    def _weak_static_template(
        self, method: str, path: str, template: tuple[str, ...]
    ) -> bool:
        literal = _segments(path)
        for value, segment in zip(literal, template):
            if segment != "{}" or not STABLE_SEGMENT.match(value):
                continue
            if self._strong_form(value) or self._has_any_identity_value_flow(method, path, value):
                continue
            if self._has_value_flow(method, path, value):
                return True
        return False

    @staticmethod
    def _display_template(template: tuple[str, ...]) -> str:
        return "/" + "/".join("{}" if item == "{}" else item for item in template)

    def _assign_param_names(self) -> dict[tuple[int, tuple[str, ...]], str]:
        keys = set()
        for template in self._template_map.values():
            for i, seg in enumerate(template):
                if seg == "{}":
                    keys.add((i, tuple(template[:i])))
        return {key: f"var{n}" for n, key in enumerate(sorted(keys), start=1)}

    # --- public API ---

    def canonical_path(self, method: str, literal_path: str) -> str:
        template = self._template_map[(method, literal_path)]
        parts = []
        for i, seg in enumerate(template):
            if seg == "{}":
                parts.append("{" + self._param_names[(i, tuple(template[:i]))] + "}")
            else:
                parts.append(seg)
        return "/" + "/".join(parts)

    def param_names_for(self, method: str, literal_path: str) -> list[str]:
        template = self._template_map[(method, literal_path)]
        return [
            self._param_names[(i, tuple(template[:i]))]
            for i, seg in enumerate(template)
            if seg == "{}"
        ]
