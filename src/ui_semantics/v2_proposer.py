"""Single-rendered-input proposer boundary for hardened preproposal-evidence-v2.

This module has no live provider implementation.  It validates one frozen input
closure, sends exactly ``RenderedCandidateInput.rendered_text`` to a supplied
in-memory/protocol implementation, and persists a strictly parsed CandidateSet.
"""

from __future__ import annotations

from .artifact_relocation import attested_sha256
import hashlib
import itertools
import json
import math
import re
import copy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, model_serializer, ValidationError

from .candidate_lineage import (
    V2RenderedInputLineage,
    load_v2_candidate_lineage,
    load_v2_rendered_input_lineage,
)
from .contracts import CandidateRecord, CandidateSet, Contract
from .dsl import parse_query_limit, get_path, _json_type, UnsupportedTextPattern
from .preproposal import _selector_snapshot_sha256, render_preproposal_candidate_input
from .current_providers import RenderedProposalProvider
from .route_s_capture_redaction import sensitive_field_category
from .current_protocols import (
    current_executable_relation_language,
    current_shape_supports_relation,
)
from .v2_template import (
    CANONICAL_V2_TEMPLATE_REF,
    CANONICAL_V2_TEMPLATE_REVISION,
    canonical_v2_template_bytes,
    canonical_v2_template_sha256,
    canonical_v2_template_text,
)


SCIENTIFIC_INPUT_VERSION = "preproposal-evidence-v2"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
READ_METHODS = frozenset({"GET", "HEAD"})


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FrozenArtifactRef(_StrictModel):
    ref: str = Field(min_length=1)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FrozenRenderedArtifactRef(FrozenArtifactRef):
    rendered_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FrozenArtifactSet(_StrictModel):
    package: FrozenArtifactRef
    view: FrozenArtifactRef
    rendered: FrozenRenderedArtifactRef


class FrozenTemplateRef(_StrictModel):
    canonical_ref: Literal[CANONICAL_V2_TEMPLATE_REF]
    frozen_copy_ref: str = Field(min_length=1)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LegacyPromptDeclaration(_StrictModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    legacy_fixture_only: Literal[True]
    eligible_for_new_run: Literal[False]


class HardenedPromptDeclaration(_StrictModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_change_reasons: tuple[str, ...]
    new_scientific_result_count: Literal[0]


class HardenedV2InputFreezeManifest(_StrictModel):
    schema_version: Literal[
        "uisemtest-hardened-v2-input-freeze-v1",
        "uisemtest-current-v2-input-freeze-v2",
    ]
    status: Literal["pass"]
    scientific_input_version: Literal["preproposal-evidence-v2"]
    system: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    frozen_at: str = Field(min_length=1)
    sources: dict[str, Any]
    template: FrozenTemplateRef
    artifacts: FrozenArtifactSet
    counts: dict[str, int]
    zero_results: dict[str, int]
    checks: dict[str, bool]
    legacy_prompt: LegacyPromptDeclaration
    hardened_prompt: HardenedPromptDeclaration
    template_revision: Literal[CANONICAL_V2_TEMPLATE_REVISION] | None = None
    view_revision: Literal["aux-semantic-projection-v1"] | None = None
    supersedes_for_new_call: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _freeze_is_qualifying_input_only(self) -> "HardenedV2InputFreezeManifest":
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in self.counts.values()):
            raise ValueError("hardened input freeze counts must be nonnegative integers")
        if self.zero_results != {
            "candidate": 0,
            "provider_call": 0,
            "route_s": 0,
            "test_result": 0,
        }:
            raise ValueError("hardened input freeze must contain zero downstream results")
        if not self.checks or not all(self.checks.values()):
            raise ValueError("hardened input freeze checks are not all passing")
        if self.schema_version == "uisemtest-current-v2-input-freeze-v2" and (
            self.template_revision != CANONICAL_V2_TEMPLATE_REVISION
            or self.view_revision != "aux-semantic-projection-v1"
            or self.supersedes_for_new_call is None
        ):
            raise ValueError("current v2 input freeze lacks explicit template/view revision")
        return self


class ProposalEndpoint(_StrictModel):
    actor: str = Field(min_length=1)
    request_ref: str = Field(min_length=1)

    @field_validator("actor", "request_ref")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("proposal endpoint strings must be nonblank")
        return value


class ValueRef(_StrictModel):
    role: str = Field(min_length=1)
    path: str = Field(min_length=1)
    value_type: Literal["object", "array", "string", "number", "integer", "boolean", "null"]

    @field_validator("role")
    @classmethod
    def _role_is_current(cls, value: str) -> str:
        if value in {
            "before", "after", "producer_request", "producer_response",
            "source_query", "followup_query", "observation", "item", "producer_status", "after_status",
        }:
            return value
        if value.startswith("followup_query:") and value.removeprefix("followup_query:").isalnum():
            return value
        prefix, separator, actor = value.partition(":")
        if (
            separator
            and prefix in {"actor_before", "actor_after", "joint_before", "joint_after"}
            and actor
            and actor[0].isalpha()
            and all(character.isalnum() or character in "_-" for character in actor)
        ):
            return value
        raise ValueError("value ref role is outside the current closed role domain")


class RoleOperand(_StrictModel):
    source: Literal["role"]
    ref: ValueRef


class IdentitySpec(_StrictModel):
    paths: list[str] = Field(min_length=1)
    semantics: Literal["strict-tuple"]

    @field_validator("paths")
    @classmethod
    def _paths_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("identity paths must be unique")
        return value


class IdentityFieldPair(_StrictModel):
    member_path: str
    collection_item_path: str


class MemberIdentitySpec(_StrictModel):
    field_pairs: list[IdentityFieldPair] = Field(min_length=1)
    semantics: Literal["strict-tuple"]

    @field_validator("field_pairs")
    @classmethod
    def _field_pairs_are_unique(
        cls, value: list[IdentityFieldPair]
    ) -> list[IdentityFieldPair]:
        pairs = [
            (item.member_path, item.collection_item_path)
            for item in value
        ]
        if len(pairs) != len(set(pairs)):
            raise ValueError("identity field pairs must be unique")
        return value


class LocatedMemberFieldRef(_StrictModel):
    source: Literal["collection_member"]
    role: Literal["before", "after"]
    collection_path: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    value_type: Literal[
        "object", "array", "string", "number", "integer", "boolean", "null"
    ]
    member: RoleOperand
    identity: MemberIdentitySpec

    @field_validator("collection_path", "field_path")
    @classmethod
    def _paths_are_concrete(cls, value: str) -> str:
        if not value.startswith("$") or "[*]" in value:
            raise ValueError("located member paths must be concrete and rooted at $")
        return value


class PresencePredicate(_StrictModel):
    family: Literal["P01"]
    operator: Literal["exists", "absent", "present"]
    target: ValueRef
    member: RoleOperand | None
    identity: MemberIdentitySpec | None
    absent_statuses: list[Literal[404]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _presence_shape_is_closed(self) -> "PresencePredicate":
        if self.target.role in {"observation", "item"}:
            if self.operator not in {"present", "absent"} or self.member is not None or self.identity is not None:
                raise ValueError("single-state presence requires one field and no member identity")
            return self
        if self.target.value_type == "object" and self.member is None and self.identity is None:
            if self.operator not in {"exists", "absent"} or (self.operator == "exists" and self.absent_statuses):
                raise ValueError("point presence requires exists or declared absence")
            return self
        if self.absent_statuses:
            raise ValueError("resource status absence requires a point resource")
        if self.operator == "present":
            raise ValueError("present requires the observation role")
        is_array = self.target.value_type == "array"
        if is_array != (self.member is not None and self.identity is not None):
            raise ValueError("P01 array target requires member and identity; boolean target forbids them")
        if not is_array and self.target.value_type != "boolean":
            raise ValueError("P01 target must be boolean or array")
        return self


class JsonTypePredicate(_StrictModel):
    family: Literal["P21"]
    target: ValueRef
    expected_type: Literal["object", "array", "string", "number", "integer", "boolean", "null"]


class QueryRequestValueRef(_StrictModel):
    role: Literal["observation_request", "source_query_request", "followup_query_request", "producer_request"]
    location: Literal["query", "body", "path", "headers"]
    path: str = Field(pattern=r"^\$(?:\.[^.*\[\]]+)*$")
    value_type: Literal["object", "array", "string", "number", "integer", "boolean", "null"]


class QueryRequestOperand(_StrictModel):
    source: Literal["request"]
    ref: QueryRequestValueRef


class HypothesisOperand(_StrictModel):
    source: Literal["hypothesis"]
    value_type: Literal["object", "array", "string", "number", "integer", "boolean", "null"]
    value: Any
    evidence_refs: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _frozen_typed_json(self) -> "HypothesisOperand":
        if _json_type(self.value) != self.value_type:
            raise ValueError("hypothesis must preserve the declared strict JSON type")
        def check(value: Any) -> None:
            _json_type(value)
            if isinstance(value, dict):
                if any(type(key) is not str for key in value):
                    raise ValueError("hypothesis object keys must be strings")
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
        check(self.value)
        if not self.rationale.strip() or any(not ref.strip() for ref in self.evidence_refs) or len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("hypothesis needs nonblank, unique visible provenance")
        return self


SingleStateOperand = RoleOperand | QueryRequestOperand | HypothesisOperand


class EqualityPredicate(_StrictModel):
    family: Literal["P02"]
    operator: Literal["eq", "neq", "numeric_eq", "numeric_neq", "lt", "le", "gt", "ge"]
    left: ValueRef | LocatedMemberFieldRef
    right: SingleStateOperand


class ValueDomainPredicate(_StrictModel):
    family: Literal["P03"]
    operator: Literal["range", "in"]
    target: ValueRef
    lower: SingleStateOperand | None = None
    upper: SingleStateOperand | None = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    domain: SingleStateOperand | None = None

    @model_validator(mode="after")
    def _domain_shape(self) -> "ValueDomainPredicate":
        if self.operator == "range":
            if self.lower is None or self.upper is None or self.domain is not None:
                raise ValueError("numeric range requires both frozen bounds and no domain")
        elif self.domain is None or self.lower is not None or self.upper is not None or not self.lower_inclusive or not self.upper_inclusive:
            raise ValueError("enumeration requires one domain and no range bounds")
        return self


class StringPredicate(_StrictModel):
    family: Literal["P09"]
    operator: Literal["contains", "prefix", "suffix"]
    target: ValueRef
    right: SingleStateOperand

    @model_validator(mode="after")
    def _string_operands(self) -> "StringPredicate":
        right_type = self.right.value_type if isinstance(self.right, HypothesisOperand) else self.right.ref.value_type
        if self.target.value_type != "string" or right_type != "string":
            raise ValueError("string relation requires string operands; exact uses P02 eq")
        return self


class FormatPredicate(_StrictModel):
    family: Literal["P10"]
    target: ValueRef
    format: Literal["date_yyyy_mm_dd", "pattern"]
    pattern: HypothesisOperand | None = None
    flags: Literal[0] = 0

    @field_validator("flags", mode="before")
    @classmethod
    def _strict_flags(cls, value):
        if type(value) is not int:
            raise ValueError("format flags must be the integer 0")
        return value

    @model_validator(mode="after")
    def _frozen_format(self) -> "FormatPredicate":
        from .dsl import validate_text_pattern
        if self.target.value_type != "string":
            raise ValueError("format requires a string field")
        if self.format == "pattern":
            if self.pattern is None or self.pattern.value_type != "string":
                raise ValueError("pattern requires a frozen string hypothesis with provenance")
            validate_text_pattern(self.pattern.value)
        elif self.pattern is not None:
            raise ValueError("date format does not take a pattern")
        return self


class CountBoundPredicate(_StrictModel):
    family: Literal["P11"]
    operator: Literal["eq", "neq", "lt", "le", "gt", "ge"]
    right: SingleStateOperand
    collection: ValueRef | None = None
    target: ValueRef | None = None
    projection: Literal["count", "length"] | None = None
    unit: Literal["items", "unicode_code_point", "utf16_code_unit"] | None = None
    newline: Literal["preserve", "html_textarea_api"] | None = None
    empty: Literal["compare", "allow"] | None = None

    @model_validator(mode="after")
    def _measurement_shape(self) -> "CountBoundPredicate":
        if self.collection is not None:
            if (self.operator != "le" or not isinstance(self.right, QueryRequestOperand)
                or (self.right.ref.location, self.right.ref.path, self.right.ref.value_type) != ("query", "$.limit", "integer")
                or any(value is not None for value in (self.target, self.projection, self.unit, self.newline, self.empty))):
                raise ValueError("P11 collection branch requires the exact integer query.limit operand")
            return self
        if self.target is None or self.projection is None:
            raise ValueError("P11 requires a fixed count/length projection")
        right_type = self.right.value_type if isinstance(self.right, HypothesisOperand) else self.right.ref.value_type
        if right_type != "integer":
            raise ValueError("P11 threshold requires an exact integer, excluding bool")
        if self.projection == "count":
            if self.target.value_type != "array" or self.unit != "items" or self.newline is not None or self.empty is not None:
                raise ValueError("count requires an array, items unit and no string options")
        elif (self.target.value_type != "string" or self.unit not in {"unicode_code_point", "utf16_code_unit"}
              or self.newline is None or self.empty is None
              or self.newline == "html_textarea_api" and self.unit != "utf16_code_unit"):
            raise ValueError("length requires explicit string unit, newline and empty handling")
        if self.empty == "allow" and (self.unit != "utf16_code_unit" or self.operator != "ge"):
            raise ValueError("empty allow is the optional HTML minlength form only")
        return self

    @model_serializer(mode="wrap")
    def _serialize_shape(self, handler):
        # Omitted fields distinguish the two closed forms, without changing the
        # first slice's exact query.limit predicate or identity.
        return {key: value for key, value in handler(self).items() if value is not None}


class CollectionUniquenessPredicate(_StrictModel):
    family: Literal["P15"]
    collection: ValueRef
    identity: IdentitySpec
    scope: Literal["actual_response"] | None = None

    @model_validator(mode="after")
    def _uniqueness_scope(self) -> "CollectionUniquenessPredicate":
        if (self.collection.role in {"observation", "item"}) != (self.scope == "actual_response"):
            raise ValueError("single-response uniqueness requires scope actual_response; query-plan scope is unchanged")
        if self.scope is not None and any(not re.fullmatch(r"\$(?:\.[^.*\[\]]+)*", path) for path in self.identity.paths):
            raise ValueError("uniqueness keys require concrete member-relative paths")
        return self

    @model_serializer(mode="wrap")
    def _serialize_scope(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


class ForallPredicate(_StrictModel):
    family: Literal["forall"]
    collection: ValueRef
    scope: Literal["actual_response", "finite_query_plan"]
    item_guard: EqualityPredicate | None
    body: Annotated[PresencePredicate | JsonTypePredicate | EqualityPredicate | ValueDomainPredicate | StringPredicate | FormatPredicate | CountBoundPredicate | CollectionUniquenessPredicate, Field(discriminator="family")]

    @model_validator(mode="after")
    def _one_item_predicate(self) -> "ForallPredicate":
        expected_role = "observation" if self.scope == "actual_response" else "followup_query"
        if self.collection.role != expected_role or self.collection.value_type != "array":
            raise ValueError("forall requires the array role for its frozen scope")
        target = (self.body.left if isinstance(self.body, EqualityPredicate) else self.body.collection if isinstance(self.body, CollectionUniquenessPredicate) else self.body.target)
        if not isinstance(target, ValueRef) or target.role != "item":
            raise ValueError("forall body requires a member-relative field")
        if self.item_guard is not None:
            guard = self.item_guard
            if not isinstance(guard.left, ValueRef) or guard.left.role != "item":
                raise ValueError("item guard requires a member-relative field")
            guard_paths = [ref.path.split(".") for ref in _predicate_value_refs(guard) if ref.role == "item"]
            body_paths = [ref.path.split(".") for ref in _predicate_value_refs(self.body) if ref.role == "item"]
            if any(left[:len(right)] == right or right[:len(left)] == left for left in guard_paths for right in body_paths) or isinstance(guard.right, QueryRequestOperand):
                raise ValueError("item guard must be independent of the tested field and request selector")
        return self


class TransitionFactConstant(_StrictModel):
    source: Literal["transition_fact"]
    fact_ref: str = Field(pattern=r"^transition-fact-[0-9a-f]{24}$")
    value_type: Literal["boolean", "integer", "number"]
    value: bool | int | float

    @model_validator(mode="after")
    def _constant_is_strict_and_finite(self) -> "TransitionFactConstant":
        expected = {bool: "boolean", int: "integer", float: "number"}
        if expected.get(type(self.value)) != self.value_type:
            raise ValueError("transition constant must preserve its exact JSON type")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("transition constant must be finite")
        return self


class StateTransitionPredicate(_StrictModel):
    family: Literal["P04"]
    operator: Literal["from_to", "toggle"]
    before: ValueRef | LocatedMemberFieldRef
    after: ValueRef | LocatedMemberFieldRef
    from_value: TransitionFactConstant | SingleStateOperand
    to_value: TransitionFactConstant | SingleStateOperand

    @model_validator(mode="after")
    def _state_transition_is_closed(self) -> "StateTransitionPredicate":
        grounded_boolean = (self.before.value_type == "boolean"
                            and isinstance(self.from_value, TransitionFactConstant)
                            and isinstance(self.to_value, TransitionFactConstant))
        if grounded_boolean:
            if (
                self.after.value_type != "boolean"
                or not isinstance(self.from_value, TransitionFactConstant)
                or not isinstance(self.to_value, TransitionFactConstant)
                or self.from_value.value_type != "boolean"
                or self.to_value.value_type != "boolean"
                or self.from_value.fact_ref != self.to_value.fact_ref
                or self.from_value.value is self.to_value.value
            ):
                raise ValueError("boolean P04 requires one grounded boolean transition fact")
            _validate_transition_value_ref_pair(self.before, self.after)
        else:
            if (
                self.operator != "from_to"
                or self.before.value_type not in {"string", "integer", "boolean"}
                or isinstance(self.from_value, TransitionFactConstant)
                or isinstance(self.to_value, TransitionFactConstant)
                or (self.from_value.value_type if isinstance(self.from_value, HypothesisOperand) else self.from_value.ref.value_type) != self.before.value_type
                or (self.to_value.value_type if isinstance(self.to_value, HypothesisOperand) else self.to_value.ref.value_type) != self.before.value_type
            ):
                raise ValueError("state P04 requires same-type scalar parameters")
            for value in (self.from_value, self.to_value):
                if isinstance(value, RoleOperand) and value.ref.role not in {"before", "producer_request"}:
                    raise ValueError("state parameters must be available before the action")
            _validate_workflow_value_ref_pair(self.before, self.after)
        return self


class NumericDirectionPredicate(_StrictModel):
    family: Literal["P07"]
    operator: Literal["gt", "lt", "ge", "le"]
    before: ValueRef | LocatedMemberFieldRef
    after: ValueRef | LocatedMemberFieldRef

    @model_validator(mode="after")
    def _numeric_direction_is_closed(self) -> "NumericDirectionPredicate":
        _validate_workflow_value_ref_pair(self.before, self.after)
        if self.before.value_type not in {"integer", "number"}:
            raise ValueError("P07 requires integer or finite-number endpoints")
        return self


class NumericHypothesisOperand(HypothesisOperand):
    """P06-only decimal lexical source, frozen before execution."""

    value_type: Literal["integer", "number"]
    lexical: str | None = None

    @field_validator("value")
    @classmethod
    def _finite_numeric_value(cls, value: Any) -> Any:
        if type(value) not in {int, float} or type(value) is float and not math.isfinite(value):
            raise ValueError("P06 hypothesis must be a finite strict JSON number")
        return value

    @model_validator(mode="after")
    def _numeric_lexical_source(self) -> "NumericHypothesisOperand":
        if self.value_type == "number" and self.lexical is None:
            raise ValueError("exact number hypothesis requires its frozen JSON numeric lexical source")
        if self.lexical is not None:
            if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", self.lexical) is None:
                raise ValueError("hypothesis lexical must be one JSON number token")
            parsed = json.loads(self.lexical)
            if type(parsed) is float and not math.isfinite(parsed):
                raise ValueError("hypothesis lexical must be a finite JSON number")
            if _json_type(parsed) != self.value_type or parsed != self.value:
                raise ValueError("hypothesis lexical must preserve its declared JSON numeric type and value")
        return self


class NumericRequestValueRef(_StrictModel):
    role: Literal["producer_request"]
    location: Literal["body"]
    path: str = Field(pattern=r"^\$(?:\.[^.*\[\]]+)*$")
    value_type: Literal["integer", "number"]


class NumericRequestOperand(_StrictModel):
    source: Literal["request"]
    ref: NumericRequestValueRef


class NumericDeltaPredicate(_StrictModel):
    family: Literal["P06"]
    before: ValueRef | LocatedMemberFieldRef
    after: ValueRef | LocatedMemberFieldRef
    delta: RoleOperand | TransitionFactConstant | NumericHypothesisOperand | NumericRequestOperand
    multiplier: Literal[-1, 1] = 1
    numeric_mode: Literal["exact", "approximate"] = "exact"
    unit: HypothesisOperand | None = None
    tolerance: NumericHypothesisOperand | None = None
    tolerance_kind: Literal["absolute", "relative"] | None = None
    rounding: HypothesisOperand | None = None
    conversions: HypothesisOperand | None = None

    @model_validator(mode="after")
    def _numeric_transition_is_closed(self) -> "NumericDeltaPredicate":
        if isinstance(self.delta, (NumericHypothesisOperand, NumericRequestOperand)):
            _validate_workflow_value_ref_pair(self.before, self.after)
            if self.unit is None:
                raise ValueError("new P06 amount sources require a frozen common unit")
        else:
            _validate_transition_value_ref_pair(self.before, self.after)
        if self.unit is not None and (
            self.unit.value_type != "string" or not self.unit.value.strip()
        ):
            raise ValueError("P06 common unit must be a nonblank frozen string hypothesis")
        _validate_numeric_rules(self)
        return self

    @model_serializer(mode="wrap")
    def _numeric_optional_rules(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None or key == "unit"}


def _validate_numeric_rules(predicate: Any) -> None:
    if predicate.numeric_mode == "approximate":
        if predicate.tolerance is None or predicate.tolerance_kind is None or predicate.tolerance.value < 0:
            raise ValueError("approximate comparison requires a frozen nonnegative explicit error")
    elif predicate.tolerance is not None or predicate.tolerance_kind is not None:
        raise ValueError("exact comparison forbids an error tolerance")
    if predicate.rounding is not None:
        rule = predicate.rounding.value
        if (predicate.rounding.value_type != "object" or set(rule) != {"scale", "mode", "position"}
            or type(rule["scale"]) is not int or rule["scale"] < 0
            or rule["mode"] not in {"half_even", "half_up", "down"} or rule["position"] != "result"):
            raise ValueError("rounding requires a frozen result scale and supported mode")
    if predicate.conversions is not None:
        rules = predicate.conversions.value
        names = set(predicate.units.value) if predicate.family == "P08" and predicate.operator == "linear_delta" else {"before", "after", "delta"} if predicate.family == "P06" else {"left", "right", "output"} if predicate.family == "P08" else {"item", "factor", "output"}
        if predicate.conversions.value_type != "object" or not rules or not set(rules) <= names:
            raise ValueError("conversion must name a frozen numeric operand")
        for rule in rules.values():
            if (not isinstance(rule, dict) or set(rule) != {"from", "to", "factor"}
                or any(not isinstance(rule[key], str) or not rule[key].strip() for key in rule)
                or re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", rule["factor"]) is None
                or not Decimal(rule["factor"]).is_finite() or Decimal(rule["factor"]) <= 0):
                raise ValueError("unit conversion requires positive exact numeric text and named units")


class ResourceDeltaTerm(_StrictModel):
    before: ValueRef
    after: ValueRef
    coefficient: NumericHypothesisOperand

    @model_validator(mode="after")
    def _closed_delta(self):
        if self.before.role == self.after.role or self.before.path != self.after.path or self.before.value_type != self.after.value_type or self.before.value_type not in {"integer", "number"}:
            raise ValueError("resource delta requires separate checkpoints of the same numeric field")
        return self


class ArithmeticPredicate(_StrictModel):
    family: Literal["P08"]
    operator: Literal["add", "subtract", "multiply", "divide", "linear_delta"]
    left: RoleOperand | NumericHypothesisOperand | QueryRequestOperand | None = None
    right: RoleOperand | NumericHypothesisOperand | QueryRequestOperand | None = None
    output: ValueRef | NumericHypothesisOperand
    terms: list[ResourceDeltaTerm] | None = Field(default=None, min_length=2, max_length=16)
    numeric_mode: Literal["exact", "approximate"] = "exact"
    units: HypothesisOperand
    tolerance: NumericHypothesisOperand | None = None
    tolerance_kind: Literal["absolute", "relative"] | None = None
    rounding: HypothesisOperand | None = None
    conversions: HypothesisOperand | None = None

    @model_validator(mode="after")
    def _closed_arithmetic(self):
        if self.operator == "linear_delta":
            if self.terms is None or self.left is not None or self.right is not None or not isinstance(self.output, NumericHypothesisOperand):
                raise ValueError("linear delta requires finite resource terms and a frozen numeric result")
            names = {"output", *(f"before:{i}" for i in range(len(self.terms))), *(f"after:{i}" for i in range(len(self.terms)))}
            if self.units.value_type != "object" or set(self.units.value) != names or any(not isinstance(v, str) or not v.strip() for v in self.units.value.values()):
                raise ValueError("resource delta requires every frozen operand unit")
            if len({term.before.role for term in self.terms}) != len(self.terms) or len({term.after.role for term in self.terms}) != len(self.terms):
                raise ValueError("resource delta terms must refer to distinct resources")
            _validate_numeric_rules(self)
            return self
        if self.terms is not None or self.left is None or self.right is None or not isinstance(self.output, ValueRef):
            raise ValueError("binary arithmetic requires two operands and an observed output")
        if self.units.value_type != "object" or set(self.units.value) != {"left", "right", "output"} or any(not isinstance(v, str) or not v.strip() for v in self.units.value.values()):
            raise ValueError("arithmetic requires the frozen input to result unit relation")
        if self.output.value_type not in {"integer", "number"}:
            raise ValueError("arithmetic requires a numeric observation output")
        for value in (self.left, self.right):
            kind = value.value_type if isinstance(value, NumericHypothesisOperand) else value.ref.value_type
            if kind not in {"integer", "number"}:
                raise ValueError("arithmetic operands must be numeric")
        _validate_numeric_rules(self)
        return self

    @model_serializer(mode="wrap")
    def _numeric_optional_rules(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


class AggregationPredicate(_StrictModel):
    family: Literal["P19"]
    operator: Literal["count", "sum", "min", "max"]
    collection: ValueRef
    scope: Literal["actual_response", "finite_query_plan"]
    item: ValueRef | None = None
    factor: ValueRef | None = None
    output: ValueRef
    numeric_mode: Literal["exact", "approximate"] = "exact"
    units: HypothesisOperand
    tolerance: NumericHypothesisOperand | None = None
    tolerance_kind: Literal["absolute", "relative"] | None = None
    rounding: HypothesisOperand | None = None
    conversions: HypothesisOperand | None = None

    @model_validator(mode="after")
    def _closed_aggregation(self):
        if self.collection.value_type != "array" or self.output.value_type not in {"integer", "number"}:
            raise ValueError("aggregation requires a response array and numeric summary")
        if (self.operator == "count") != (self.item is None) or self.factor is not None and self.operator != "sum":
            raise ValueError("count has no member field; only sum allows one member product")
        for ref in (self.item, self.factor):
            if ref is not None and (ref.role != "item" or ref.value_type not in {"integer", "number"}):
                raise ValueError("aggregate member fields must be numeric item references")
        keys = {"output", *({"item"} if self.item is not None else set()), *({"factor"} if self.factor is not None else set())}
        if self.units.value_type != "object" or set(self.units.value) != keys or any(not isinstance(v, str) or not v.strip() for v in self.units.value.values()):
            raise ValueError("aggregation requires frozen operand units")
        if self.operator == "count" and self.units.value["output"] != "items":
            raise ValueError("count result unit is items")
        _validate_numeric_rules(self)
        return self

    @model_serializer(mode="wrap")
    def _numeric_optional_rules(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


def _validate_transition_value_ref_pair(
    before: ValueRef | LocatedMemberFieldRef,
    after: ValueRef | LocatedMemberFieldRef,
) -> None:
    if isinstance(before, LocatedMemberFieldRef) != isinstance(
        after, LocatedMemberFieldRef
    ):
        raise ValueError("transition endpoints must use one reference shape")
    if isinstance(before, LocatedMemberFieldRef):
        assert isinstance(after, LocatedMemberFieldRef)
        if (
            before.role != "before"
            or after.role != "after"
            or before.collection_path != after.collection_path
            or before.field_path != after.field_path
            or before.value_type != after.value_type
            or before.member != after.member
            or before.identity != after.identity
        ):
            raise ValueError(
                "located transition endpoints must share one member identity and field"
            )


def _validate_workflow_value_ref_pair(
    before: ValueRef | LocatedMemberFieldRef,
    after: ValueRef | LocatedMemberFieldRef,
) -> None:
    """Freeze one field and a locator available before the action."""
    _validate_transition_value_ref_pair(before, after)
    roles_match = (before.role == "before" and after.role == "after" or
                   before.role.startswith("actor_before:") and after.role == before.role.replace("actor_before:", "actor_after:", 1))
    if not roles_match or before.value_type != after.value_type:
        raise ValueError("workflow endpoints require the same before/after field type")
    if isinstance(before, LocatedMemberFieldRef):
        if before.member.ref.role != "producer_request":
            raise ValueError("workflow member identity must be available in the action request")
    elif before.path != after.path:
        raise ValueError("workflow endpoints require the same frozen field path")


class CountDeltaPredicate(_StrictModel):
    family: Literal["P12"]
    before: ValueRef
    after: ValueRef
    delta: int

    @field_validator("delta")
    @classmethod
    def _delta_is_nonzero(cls, value: int) -> int:
        if isinstance(value, bool) or value == 0:
            raise ValueError("P12 delta must be a nonzero integer")
        return value


class CollectionMembershipPredicate(_StrictModel):
    family: Literal["P13"]
    operator: Literal["contains", "not_contains"]
    collection: ValueRef
    member: SingleStateOperand | NumericHypothesisOperand
    identity: MemberIdentitySpec | None = None

    @model_validator(mode="after")
    def _membership_shape(self):
        if isinstance(self.member, HypothesisOperand) and self.member.value_type == "number" and not isinstance(self.member, NumericHypothesisOperand):
            raise ValueError("number membership hypothesis requires a frozen JSON numeric lexical source")
        if self.collection.role in {"observation", "item"}:
            if self.identity is not None:
                raise ValueError("single-response scalar membership uses strict values")
            kind = self.member.value_type if isinstance(self.member, HypothesisOperand) else self.member.ref.value_type
            if kind in {"array", "object"}:
                raise ValueError("scalar membership requires a JSON scalar")
        elif self.identity is None or not isinstance(self.member, RoleOperand):
            raise ValueError("cross-checkpoint membership requires role identity")
        return self


class MembershipPredicate(_StrictModel):
    family: Literal["P14"]
    operator: Literal["added", "removed"]
    before: ValueRef
    after: ValueRef
    member: RoleOperand
    identity: MemberIdentitySpec


class CollectionRelationPredicate(_StrictModel):
    family: Literal["P17"]
    operator: Literal["subset", "superset", "equal"]
    left: ValueRef
    right: ValueRef
    identity: IdentitySpec | None = None
    expected_difference: None = None
    representation: Literal["set", "multiset", "sequence"] = "set"
    comparison_basis: Literal["full_json_value", "frozen_projection", "identity_tuple"] = "identity_tuple"
    projection: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _collection_basis(self):
        _validate_collection_basis(self)
        if self.representation != "set" and self.operator != "equal":
            raise ValueError("sequence supports equality only")
        return self


def _validate_collection_basis(predicate: Any) -> None:
    if predicate.comparison_basis == "identity_tuple":
        if predicate.identity is None or predicate.projection:
            raise ValueError("identity basis requires exactly a frozen identity tuple")
    elif predicate.comparison_basis == "frozen_projection":
        if predicate.identity is not None or not predicate.projection or len(set(predicate.projection)) != len(predicate.projection):
            raise ValueError("projection basis requires unique frozen field paths")
    elif predicate.identity is not None or predicate.projection:
        raise ValueError("full JSON basis does not discard member fields")
    if any(not re.fullmatch(r"\$(?:\.[^.*\[\]]+)*", path) for path in predicate.projection):
        raise ValueError("projection paths must be concrete member-relative fields")


class OrderingPredicate(_StrictModel):
    family: Literal["P16"]
    before: ValueRef
    after: ValueRef
    key: str = Field(pattern=r"^\$(?:\.[^.*\[\]]+)*$")
    direction: Literal["asc", "desc"] = "asc"
    nulls: Literal["first", "last"] = "last"
    ties: Literal["unordered"] = "unordered"
    comparison_basis: Literal["full_json_value", "frozen_projection", "identity_tuple"] = "full_json_value"
    projection: list[str] = Field(default_factory=list)
    identity: IdentitySpec | None = None
    parameters: HypothesisOperand

    @model_validator(mode="after")
    def _ordering_shape(self):
        _validate_collection_basis(self)
        if (self.before.role, self.after.role, self.before.value_type, self.after.value_type) != ("source_query", "followup_query:q1", "array", "array"):
            raise ValueError("sort requires source and one followup array")
        if self.parameters.value_type != "object" or self.parameters.value != {"key": self.key, "direction": self.direction, "nulls": self.nulls, "ties": self.ties}:
            raise ValueError("sort rules require frozen parameter provenance")
        return self


class PartitionRelationPredicate(_StrictModel):
    family: Literal["P18"]
    operator: Literal["pairwise_disjoint", "complete_union", "partition_difference"]
    source: ValueRef
    partitions: list[ValueRef] = Field(min_length=1)
    identity: IdentitySpec
    expected_remainder: ValueRef | None

    @model_validator(mode="after")
    def _partition_shape_is_closed(self) -> "PartitionRelationPredicate":
        roles = [item.role for item in self.partitions]
        if len(roles) != len(set(roles)):
            raise ValueError("P18 partition roles must be distinct")
        requires_remainder = self.operator == "partition_difference"
        if requires_remainder != (self.expected_remainder is not None):
            raise ValueError("P18 expected_remainder is required only for partition_difference")
        if not requires_remainder and len(self.partitions) < 2:
            raise ValueError("partition union/disjoint requires at least two parts")
        return self


class StateEquivalencePredicate(_StrictModel):
    family: Literal["P20"]
    operator: Literal["equal"]
    left: ValueRef | LocatedMemberFieldRef
    right: ValueRef | LocatedMemberFieldRef
    projection_ref: str | None = Field(default=None, pattern=r"^state-projection-[0-9a-f]{24}$")
    projection: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _state_projection_is_closed(self) -> "StateEquivalencePredicate":
        _validate_workflow_value_ref_pair(self.left, self.right)
        if len(set(self.projection)) != len(self.projection) or any(not path.startswith("$") or "[*]" in path for path in self.projection):
            raise ValueError("preservation projection requires distinct concrete JSON paths")
        if self.projection and self.left.value_type != "object":
            raise ValueError("multiple preserved fields require an object projection")
        return self


class RepeatEqualPredicate(_StrictModel):
    family: Literal["repeat_equal"]
    projection: StateEquivalencePredicate


class RepeatRejectedPredicate(_StrictModel):
    family: Literal["repeat_rejected"]
    projection: StateEquivalencePredicate
    rejection: EqualityPredicate | None = None


class RepeatDeltaPredicate(_StrictModel):
    family: Literal["repeat_delta"]
    delta: NumericDeltaPredicate


PrimaryPredicate = Annotated[
    PresencePredicate | EqualityPredicate | StateTransitionPredicate
    | NumericDeltaPredicate | NumericDirectionPredicate | ArithmeticPredicate | AggregationPredicate | CountDeltaPredicate
    | CollectionMembershipPredicate | MembershipPredicate
    | CollectionUniquenessPredicate | CollectionRelationPredicate | OrderingPredicate
    | PartitionRelationPredicate | StateEquivalencePredicate
    | JsonTypePredicate | CountBoundPredicate | ValueDomainPredicate | StringPredicate | FormatPredicate | ForallPredicate
    | RepeatEqualPredicate | RepeatRejectedPredicate | RepeatDeltaPredicate,
    Field(discriminator="family"),
]


def _validate_predicate_type_semantics(
    predicate: PrimaryPredicate,
) -> None:
    """Reject mechanically impossible predicate/value-type combinations."""

    numeric_types = {"integer", "number"}
    if isinstance(predicate, ForallPredicate):
        _validate_predicate_type_semantics(predicate.body)
        if predicate.item_guard is not None:
            _validate_predicate_type_semantics(predicate.item_guard)
    elif isinstance(predicate, ValueDomainPredicate):
        def operand_type(operand: SingleStateOperand) -> str:
            return operand.value_type if isinstance(operand, HypothesisOperand) else operand.ref.value_type
        if predicate.operator == "range":
            if any(value not in numeric_types for value in (predicate.target.value_type, operand_type(predicate.lower), operand_type(predicate.upper))):
                raise CandidateAdmissionError("numeric_predicate_requires_numeric_values")
        elif operand_type(predicate.domain) != "array":
            raise CandidateAdmissionError("enum_domain_requires_array")
    elif isinstance(predicate, EqualityPredicate):
        left_type = predicate.left.value_type
        right_type = predicate.right.value_type if isinstance(predicate.right, HypothesisOperand) else predicate.right.ref.value_type
        if predicate.operator not in {"eq", "neq"} and not {left_type, right_type} <= numeric_types:
            raise CandidateAdmissionError("numeric_predicate_requires_numeric_values")
        if predicate.left.role not in {"observation", "item"} and left_type != right_type and not {
            left_type, right_type
        } <= numeric_types:
            raise CandidateAdmissionError("predicate_value_types_incompatible")
    elif isinstance(predicate, NumericDeltaPredicate):
        delta_type = (
            predicate.delta.ref.value_type
            if isinstance(predicate.delta, (RoleOperand, NumericRequestOperand))
            else predicate.delta.value_type
        )
        if (
            predicate.before.value_type not in numeric_types
            or predicate.after.value_type not in numeric_types
            or delta_type not in numeric_types
        ):
            raise CandidateAdmissionError("numeric_predicate_requires_numeric_values")
    elif isinstance(predicate, CountDeltaPredicate):
        if {predicate.before.value_type, predicate.after.value_type} != {"array"}:
            raise CandidateAdmissionError("count_predicate_requires_collections")
    elif isinstance(predicate, CollectionMembershipPredicate):
        if predicate.collection.value_type != "array":
            raise CandidateAdmissionError("membership_predicate_requires_collection")
    elif isinstance(predicate, MembershipPredicate):
        if {predicate.before.value_type, predicate.after.value_type} != {"array"}:
            raise CandidateAdmissionError("membership_predicate_requires_collections")
    elif isinstance(predicate, CollectionUniquenessPredicate):
        if predicate.collection.value_type != "array":
            raise CandidateAdmissionError("collection_predicate_requires_collection")
    elif isinstance(predicate, CollectionRelationPredicate):
        if {predicate.left.value_type, predicate.right.value_type} != {"array"}:
            raise CandidateAdmissionError("collection_relation_requires_collections")
    elif isinstance(predicate, PartitionRelationPredicate):
        values = [predicate.source, *predicate.partitions]
        if predicate.expected_remainder is not None:
            values.append(predicate.expected_remainder)
        if any(value.value_type != "array" for value in values):
            raise CandidateAdmissionError("partition_predicate_requires_collections")


def _validate_current_predicate_scope(contract: str, predicate: PrimaryPredicate) -> None:
    repeated = isinstance(predicate, (RepeatEqualPredicate, RepeatRejectedPredicate, RepeatDeltaPredicate))
    if repeated != (contract == "C05"):
        raise ValueError("repeated execution uses only its three closed C05 predicates")
    if repeated:
        if isinstance(predicate, RepeatRejectedPredicate) and predicate.rejection is not None and predicate.rejection.left.role not in {"producer_status", "producer_response"}:
            raise ValueError("repeat rejection must check the second action response")
        return
    if contract in {"C04", "inverse_restoration", "read_preservation"} and not isinstance(predicate, StateEquivalencePredicate):
        raise ValueError("C04 currently requires one P20 field preservation")
    if isinstance(predicate, (StateTransitionPredicate, NumericDirectionPredicate)) and (
        isinstance(predicate, NumericDirectionPredicate) or predicate.before.value_type != "boolean"
    ) and contract != "C02":
        raise ValueError("general state and numeric direction workflows require C02")
    if isinstance(predicate, ForallPredicate) and predicate.scope == "finite_query_plan":
        if contract != "single_state_constraint":
            raise ValueError("finite query forall uses the constraint entry")
        return
    if contract in {"single_state_constraint", "C14"}:
        if contract == "C14" and not isinstance(predicate, (ArithmeticPredicate, AggregationPredicate)):
            raise ValueError("C14 single-response entry requires arithmetic or aggregation")
        if contract == "C14":
            return
        if not isinstance(predicate, (PresencePredicate, JsonTypePredicate, CountBoundPredicate, EqualityPredicate, ValueDomainPredicate, StringPredicate, FormatPredicate, CollectionUniquenessPredicate, CollectionMembershipPredicate, ArithmeticPredicate, AggregationPredicate, ForallPredicate)):
            raise ValueError("predicate is outside the current single-state subset")
        if not isinstance(predicate, (ForallPredicate, AggregationPredicate)) and any(not isinstance(ref, ValueRef) or ref.role != "observation" for ref in _predicate_value_refs(predicate)):
            raise ValueError("single-state atom requires observation fields")
    else:
        if isinstance(predicate, (ForallPredicate, ValueDomainPredicate, StringPredicate, FormatPredicate, CountBoundPredicate)):
            raise ValueError("this predicate currently requires single_state_constraint")
        if isinstance(predicate, EqualityPredicate) and contract not in {"C01", "C02", "C03", "C06", "C11", "C12", "self_exclusion"}:
            raise ValueError("action value comparison requires a registered contract")
        if any(ref.role in {"observation", "item"} for ref in _predicate_value_refs(predicate)):
            raise ValueError("single-state fields require single_state_constraint")


class QueryTermination(_StrictModel):
    kind: Literal["terminal_value", "total_count"]
    ref: ValueRef
    expected: HypothesisOperand | None = None

    @model_validator(mode="after")
    def _termination_shape(self):
        if (self.kind == "terminal_value") != (self.expected is not None):
            raise ValueError("terminal value requires one frozen expected parameter")
        if self.kind == "total_count" and self.ref.value_type != "integer":
            raise ValueError("total count must be an exact integer")
        return self


class QueryClosure(_StrictModel):
    roles: list[str] = Field(min_length=1)
    collection_path: str = Field(pattern=r"^\$(?:\.[^.*\[\]]+)*$")
    termination: QueryTermination
    traversal: HypothesisOperand

    @model_validator(mode="after")
    def _closed_traversal(self):
        if len(set(self.roles)) != len(self.roles) or self.termination.ref.role != self.roles[-1]:
            raise ValueError("closure requires distinct ordered roles and a final response termination")
        rule = self.traversal.value
        if self.traversal.value_type != "object" or not isinstance(rule, dict):
            raise ValueError("finite traversal requires a frozen algorithm with provenance")
        kind = rule.get("kind")
        keys = {"single_response": {"kind"}, "page_number": {"kind", "location", "parameter", "first"},
                "offset": {"kind", "location", "parameter", "limit_parameter"}, "cursor": {"kind", "location", "parameter", "next_path"}}
        if kind not in keys or set(rule) != keys[kind]:
            raise ValueError("unsupported finite traversal rule")
        if kind == "single_response":
            if len(self.roles) != 1 or self.termination.kind != "total_count":
                raise ValueError("one-response closure requires its exact total count")
        else:
            if rule["location"] not in {"query", "body"} or any(not isinstance(rule[key], str) or not re.fullmatch(r"\$(?:\.[^.*\[\]]+)*", rule[key]) for key in ("parameter", *({"offset": ["limit_parameter"], "cursor": ["next_path"]}.get(kind, [])))):
                raise ValueError("traversal requires concrete request/response parameter paths")
            if kind == "page_number" and (type(rule["first"]) is not int or rule["first"] not in {0, 1}):
                raise ValueError("page numbers start at the frozen zero or one and advance by one")
        return self


class QueryScope(_StrictModel):
    scope: Literal["actual_response", "finite_query_plan"] = "actual_response"
    closures: list[QueryClosure] = Field(default_factory=list)

    @model_validator(mode="after")
    def _scope_shape(self):
        if (self.scope == "finite_query_plan") != bool(self.closures):
            raise ValueError("only a finite query scope requires termination closures")
        return self


class JointObservation(_StrictModel):
    consistency: Literal["common_version", "common_as_of", "no_competing_writes_workflow"]
    consistency_refs: list[ValueRef] = Field(default_factory=list)
    no_competing_writes: HypothesisOperand | None = None
    scope: HypothesisOperand
    query_scope: QueryScope = Field(default_factory=QueryScope)

    @model_validator(mode="after")
    def _closed_consistency(self):
        if self.scope.value_type != "string" or not self.scope.value.strip():
            raise ValueError("joint observation requires a frozen descriptive business scope")
        if self.consistency == "no_competing_writes_workflow":
            if self.consistency_refs or self.no_competing_writes is None or self.no_competing_writes.value_type != "boolean" or self.no_competing_writes.value is not True:
                raise ValueError("finite workflow requires the explicit no competing writes condition")
        elif self.no_competing_writes is not None or len(self.consistency_refs) < 2 or any(ref.value_type not in {"string", "integer"} for ref in self.consistency_refs):
            raise ValueError("joint consistency requires observed comparable version/as-of fields")
        return self


class TimestampEvidence(_StrictModel):
    origin_time_path: str
    clock_id_path: str
    items_path: str
    time_path: str
    unit: Literal["nanoseconds", "milliseconds", "seconds"]
    value_path: str = "$"
    end_time_path: str | None = None
    coverage_start_path: str | None = None
    coverage_end_path: str | None = None
    complete_path: str | None = None


class TemporalRequirement(_StrictModel):
    kind: Literal["deadline_state", "appearance_preservation", "event_occurrence"]
    observation_mode: Literal["returned_sample", "sampled", "exact_time", "continuous", "event_log"]
    origin: Literal["send", "ack", "event"]
    unit: Literal["nanoseconds", "milliseconds", "seconds"]
    duration_parameter: NumericHypothesisOperand | NumericRequestOperand | RoleOperand
    hold_duration_parameter: NumericHypothesisOperand | NumericRequestOperand | RoleOperand | None = None
    error_before_parameter: NumericHypothesisOperand | NumericRequestOperand | RoleOperand | None = None
    error_after_parameter: NumericHypothesisOperand | NumericRequestOperand | RoleOperand | None = None
    timestamp_evidence: TimestampEvidence | None = None

    @model_validator(mode="after")
    def _closed_time(self):
        modes = {"deadline_state": {"returned_sample", "exact_time"}, "appearance_preservation": {"sampled", "continuous"}, "event_occurrence": {"event_log"}}
        if self.observation_mode not in modes[self.kind]:
            raise ValueError("time requirement kind and evidence mode differ")
        timestamped = self.observation_mode in {"exact_time", "continuous", "event_log"}
        if timestamped != (self.timestamp_evidence is not None) or timestamped != (self.origin == "event"):
            raise ValueError("timestamped claims require an observed comparable event origin")
        if self.kind != "appearance_preservation" and self.hold_duration_parameter is not None:
            raise ValueError("only preservation has a hold duration")
        if self.observation_mode != "returned_sample" and any(value is not None for value in (self.error_before_parameter, self.error_after_parameter)):
            raise ValueError("only a returned sample declares a receive window")
        for value in (self.duration_parameter, self.hold_duration_parameter, self.error_before_parameter, self.error_after_parameter):
            if isinstance(value, NumericHypothesisOperand) and value.value < 0:
                raise ValueError("duration must be nonnegative")
            if isinstance(value, RoleOperand) and (value.ref.role not in {"producer_request", "producer_response"} or value.ref.value_type not in {"integer", "number"}):
                raise ValueError("duration source must be an actual numeric action operand")
        if self.timestamp_evidence is not None:
            evidence = self.timestamp_evidence
            paths = evidence.model_dump(exclude_none=True, exclude={"unit"})
            if any(not re.fullmatch(r"\$(?:\.[^.*\[\]]+)*", path) for path in paths.values()):
                raise ValueError("timestamp evidence needs concrete observed field paths")
            if self.observation_mode == "continuous" and evidence.end_time_path is None:
                raise ValueError("continuous evidence needs interval endpoints")
            coverage = (evidence.coverage_start_path, evidence.coverage_end_path, evidence.complete_path)
            if any(value is not None for value in coverage) and any(value is None for value in coverage):
                raise ValueError("event coverage requires both bounds and a completeness field")
        return self


class QueryTransform(_StrictModel):
    kind: Literal["equivalent_input", "filter_refinement", "filter_expansion", "sort", "pagination_partition", "finite_query_plan"]
    location: Literal["query", "body"]
    keys: list[str] = Field(min_length=1)
    semantics: HypothesisOperand

    @model_validator(mode="after")
    def _transformation_shape(self):
        if len(set(self.keys)) != len(self.keys) or any(not key.strip() for key in self.keys):
            raise ValueError("query transform keys must be nonblank and unique")
        values = {"equivalent_input": {"equivalent"}, "filter_refinement": {"and", "or"}, "filter_expansion": {"and", "or"}, "sort": {"sort"}, "pagination_partition": {"partition"}, "finite_query_plan": {"traversal"}}
        if self.semantics.value_type != "string" or self.semantics.value not in values[self.kind]:
            raise ValueError("query transformation requires its frozen finite semantics")
        return self


class V2ProposalCandidate(_StrictModel):
    schema_version: Literal["uisemtest-oracle-candidate-v1"] | None = None
    candidate_id: str | None = Field(default=None, min_length=1)
    evidence_card_id: str = Field(min_length=1)
    contract_kind: Literal[
        "C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11", "C12", "C14", "single_state_constraint", "inverse_restoration", "read_preservation", "self_exclusion"
    ]
    observation_opportunity_ref: str = Field(min_length=1)
    primary_predicate: PrimaryPredicate
    producer: ProposalEndpoint | None
    consumer: ProposalEndpoint
    setup: list[str]
    evidence_refs: list[str] = Field(min_length=1)
    rationale: str | None = None

    @model_validator(mode="after")
    def _candidate_strings_are_nonblank_and_unique(self) -> "V2ProposalCandidate":
        _validate_current_predicate_scope(self.contract_kind, self.primary_predicate)
        static = self.contract_kind == "C14" and not (isinstance(self.primary_predicate, ArithmeticPredicate) and self.primary_predicate.operator == "linear_delta") or self.contract_kind == "single_state_constraint" and not (isinstance(self.primary_predicate, ForallPredicate) and self.primary_predicate.scope == "finite_query_plan")
        if static != (self.producer is None):
            raise ValueError("only single-state candidates omit a producer")
        if self.rationale is not None and not self.rationale.strip():
            raise ValueError("candidate rationale must be nonblank")
        if any(not item.strip() for item in (*self.setup, *self.evidence_refs)):
            raise ValueError("candidate setup/evidence references must be nonblank")
        if len(self.setup) != len(set(self.setup)):
            raise ValueError("candidate setup references must be unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("candidate evidence references must be unique")
        return self


class RelationRoleBinding(_StrictModel):
    role: str = Field(min_length=1)
    request_ref: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    session_ref: str | None = None


class V2RelationProposal(_StrictModel):
    """Provider output: a grounded relation, without any execution protocol."""

    detail_region_id: str | None = None
    evidence_card_id: str = Field(min_length=1)
    contract_kind: str = Field(min_length=1)
    primary_predicate: PrimaryPredicate
    role_bindings: list[RelationRoleBinding] = Field(min_length=1)
    catalog_observer_operation_id: str | None = Field(default=None, min_length=1)
    setup: list[str]
    evidence_refs: list[str] = Field(min_length=1)
    rationale: str | None = None
    query_scope: QueryScope | None = None
    query_transform: QueryTransform | None = None
    joint_observation: JointObservation | None = None
    time_requirement: TemporalRequirement | None = None
    rejection: EqualityPredicate | None = None
    negative_context: Literal["auth_preserved", "auth_absent"] | None = None

    @model_validator(mode="after")
    def _closed_relation(self) -> "V2RelationProposal":
        _validate_current_predicate_scope(self.contract_kind, self.primary_predicate)
        if self.time_requirement is not None and (self.contract_kind not in {"C01", "C02", "C03", "C11", "C12", "self_exclusion"} or self.primary_predicate.family not in {"P01", "P02", "P13"} or self.joint_observation is not None or self.query_scope is not None or self.query_transform is not None or self.rejection is not None or self.negative_context is not None):
            raise ValueError("time requirement requires one registered target proposition")
        if (self.rejection is not None or self.negative_context is not None) and self.contract_kind not in {"C06", "C12"}:
            raise ValueError("negative request parameters require rejection contract")
        if self.rejection is not None and self.rejection.left.role not in {"producer_status", "producer_response"}:
            raise ValueError("rejection detector requires the actual response")
        rows = [(row.role, row.request_ref, row.actor) for row in self.role_bindings]
        if len(rows) != len(set(rows)):
            raise ValueError("relation role bindings must be unique")
        finite_forall = isinstance(self.primary_predicate, ForallPredicate) and self.primary_predicate.scope == "finite_query_plan"
        if self.joint_observation is not None:
            if self.contract_kind != "C14" or len(rows) < 2 or self.catalog_observer_operation_id is not None or self.query_scope is not None or self.query_transform is not None:
                raise ValueError("joint observations require only a C14 relation with finite recorded roles")
        elif (self.contract_kind in {"single_state_constraint", "C14"}) and not finite_forall:
            if len(rows) != 1 or rows[0][0] != "observation" or self.catalog_observer_operation_id is not None:
                raise ValueError("single-state constraint requires one recorded observation")
            if self.query_scope is not None or self.query_transform is not None:
                raise ValueError("one response does not accept a query plan")
        elif self.catalog_observer_operation_id is None and len(rows) < 2:
            raise ValueError("recorded-request relations require at least two roles")
        if self.catalog_observer_operation_id is not None and (
            len(rows) != 1 or rows[0][0] != "effect_source"
        ):
            raise ValueError(
                "catalog-observer relation requires one effect_source role"
            )
        if self.rationale is not None and not self.rationale.strip():
            raise ValueError("relation rationale must be nonblank")
        if any(not item.strip() for item in (*self.setup, *self.evidence_refs)):
            raise ValueError("relation setup/evidence references must be nonblank")
        if len(self.setup) != len(set(self.setup)):
            raise ValueError("relation setup references must be unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("relation evidence references must be unique")
        return self


class V2ProposalResponse(_StrictModel):
    scientific_input_version: Literal["preproposal-evidence-v2"]
    candidates: list[Any]


class CandidateAdmissionError(ValueError):
    """One candidate violates an existing structural or view-grounding gate."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class CandidateValidationBatch:
    payloads: tuple[dict[str, Any], ...]
    constructed_execution_plans: tuple[dict[str, Any], ...]
    report: dict[str, Any]


class V2ProposalRunProvenance(Contract):
    artifact_type: Literal["v2_proposal_run_provenance"] = "v2_proposal_run_provenance"
    proposal_run_id: str
    scientific_input_version: Literal["preproposal-evidence-v2"] = "preproposal-evidence-v2"
    input_freeze_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    view_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendered_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendered_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_set_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_count: int = Field(ge=0)
    model: str
    endpoint_shape: str
    endpoint_host: str
    temperature: float
    retry_count: int = Field(ge=0)
    input_frozen_at: str
    response_received_at: str
    rendered_prompt_delivery_count: Literal[1] = 1
    additional_evidence_payload_count: Literal[0] = 0


@dataclass(frozen=True)
class V2ProposalRunResult:
    candidate_set: CandidateSet
    provenance: V2ProposalRunProvenance
    candidate_set_path: Path
    provenance_path: Path


@dataclass(frozen=True)
class V2FrozenInput:
    manifest: HardenedV2InputFreezeManifest
    manifest_path: Path
    manifest_raw_sha256: str
    lineage: V2RenderedInputLineage
    artifact_paths: dict[str, Path]


def load_hardened_v2_input(
    *,
    input_freeze_manifest_path: str | Path,
    expected_manifest_sha256: str,
    require_current_revision: bool = True,
) -> V2FrozenInput:
    """Load the manifest trust root before any provider can be called."""

    manifest_path = _regular_file(input_freeze_manifest_path, "input freeze manifest")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha != expected_manifest_sha256:
        raise ValueError("input freeze manifest raw SHA-256 does not match the prebound trust root")
    manifest = HardenedV2InputFreezeManifest.model_validate_json(manifest_bytes, strict=True)
    if require_current_revision and manifest.schema_version != "uisemtest-current-v2-input-freeze-v2":
        raise ValueError("current proposer accepts only the current v2 input-freeze revision")
    lineage, paths = _load_and_validate_frozen_input(manifest_path.parent, manifest)
    return V2FrozenInput(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_raw_sha256=manifest_sha,
        lineage=lineage,
        artifact_paths=paths,
    )


def propose_v2_from_frozen_input(
    *,
    input_freeze_manifest_path: str | Path,
    expected_manifest_sha256: str,
    provider: RenderedProposalProvider,
    proposal_run_id: str,
    output_root: str | Path,
) -> V2ProposalRunResult:
    """Validate one frozen closure, deliver one string, and persist v2 output.

    ``expected_manifest_sha256`` is the externally prebound raw-file trust root.
    The provider receives exactly one keyword argument, ``rendered_prompt``.
    """

    frozen = load_hardened_v2_input(
        input_freeze_manifest_path=input_freeze_manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
        require_current_revision=False,
    )
    manifest_path = frozen.manifest_path
    root = manifest_path.parent
    target_root = Path(output_root).resolve()
    if target_root != root:
        raise ValueError("v2 CandidateSet must be persisted beside its frozen rendered input")
    manifest_sha = frozen.manifest_raw_sha256
    manifest = frozen.manifest
    lineage = frozen.lineage
    paths = frozen.artifact_paths

    raw_response = provider.propose_rendered(
        rendered_prompt=lineage.rendered_input.rendered_text
    )
    parsed = _parse_response(raw_response.content)
    payloads = _validated_candidate_payloads(parsed, lineage.view)
    response_payload = parsed.model_dump(mode="json")
    canonical_response_sha = _canonical_sha256(response_payload)
    raw_response_sha = hashlib.sha256(raw_response.content.encode("utf-8")).hexdigest()
    seed = _canonical_sha256(
        {
            "package_sha256": lineage.package.canonical_sha256(),
            "view_sha256": lineage.view.canonical_sha256(),
            "rendered_input_sha256": lineage.rendered_input.canonical_sha256(),
            "response_sha256": canonical_response_sha,
        }
    )
    records = tuple(
        CandidateRecord(
            candidate_id=candidate_id,
            scientific_input_version=SCIENTIFIC_INPUT_VERSION,
            payload=normalized,
            payload_sha256=_canonical_sha256(normalized),
        )
        for index, payload in enumerate(payloads, start=1)
        for candidate_id in (f"v2-candidate-{index:04d}",)
        for normalized in ({
            "schema_version": "uisemtest-oracle-candidate-v1",
            "candidate_id": candidate_id,
            **payload,
        },)
    )
    candidate_set = CandidateSet(
        candidate_set_id=f"v2-candidate-set-{seed[:24]}",
        scientific_input_version=SCIENTIFIC_INPUT_VERSION,
        candidates=records,
        preproposal_evidence_package_sha256=lineage.package.canonical_sha256(),
        proposal_evidence_view_sha256=lineage.view.canonical_sha256(),
        rendered_input_ref=manifest.artifacts.rendered.ref,
        rendered_input_sha256=lineage.rendered_input.canonical_sha256(),
        source_refs=(manifest_path.name, manifest.artifacts.rendered.ref),
        source_sha256={
            "input_freeze_manifest": manifest_sha,
            "preproposal_evidence_package": lineage.package.canonical_sha256(),
            "proposal_evidence_view": lineage.view.canonical_sha256(),
            "rendered_candidate_input": lineage.rendered_input.canonical_sha256(),
            "canonical_template": canonical_v2_template_sha256(),
            "canonical_response": canonical_response_sha,
        },
    )
    candidate_set_path = target_root / "candidate_set.json"
    provenance_path = target_root / "proposal_run_provenance.json"
    if candidate_set_path.exists() or provenance_path.exists():
        raise ValueError("v2 proposer refuses to overwrite an existing run artifact")
    candidate_set_path.write_bytes(candidate_set.canonical_bytes())
    load_v2_candidate_lineage(
        candidate_set_path=candidate_set_path,
        package_path=paths["package"],
        view_path=paths["view"],
        rendered_input_path=paths["rendered"],
    )
    provenance = V2ProposalRunProvenance(
        proposal_run_id=proposal_run_id,
        input_freeze_manifest_sha256=manifest_sha,
        package_sha256=lineage.package.canonical_sha256(),
        view_sha256=lineage.view.canonical_sha256(),
        rendered_input_sha256=lineage.rendered_input.canonical_sha256(),
        rendered_text_sha256=lineage.rendered_input.rendered_sha256,
        template_sha256=canonical_v2_template_sha256(),
        response_sha256=raw_response_sha,
        canonical_response_sha256=canonical_response_sha,
        candidate_set_sha256=candidate_set.canonical_sha256(),
        candidate_set_file_sha256=_sha256_file(candidate_set_path),
        candidate_count=len(candidate_set.candidates),
        model=raw_response.model,
        endpoint_shape=raw_response.endpoint_shape,
        endpoint_host=raw_response.endpoint_host,
        temperature=raw_response.temperature,
        retry_count=raw_response.retry_count,
        input_frozen_at=manifest.frozen_at,
        response_received_at=raw_response.response_received_at,
        source_refs=(manifest_path.name, candidate_set_path.name),
        source_sha256={
            "input_freeze_manifest": manifest_sha,
            "candidate_set": candidate_set.canonical_sha256(),
            "raw_response": raw_response_sha,
        },
    )
    provenance_path.write_bytes(provenance.canonical_bytes())
    return V2ProposalRunResult(
        candidate_set=candidate_set,
        provenance=provenance,
        candidate_set_path=candidate_set_path,
        provenance_path=provenance_path,
    )


def _load_and_validate_frozen_input(
    root: Path,
    manifest: HardenedV2InputFreezeManifest,
) -> tuple[V2RenderedInputLineage, dict[str, Path]]:
    paths = {
        "package": _resolve_ref(root, manifest.artifacts.package.ref, "package"),
        "view": _resolve_ref(root, manifest.artifacts.view.ref, "view"),
        "rendered": _resolve_ref(root, manifest.artifacts.rendered.ref, "rendered input"),
        "template": _resolve_ref(root, manifest.template.frozen_copy_ref, "template"),
    }
    frozen_refs = {
        "package": manifest.artifacts.package,
        "view": manifest.artifacts.view,
        "rendered": manifest.artifacts.rendered,
    }
    for name, frozen in frozen_refs.items():
        if _sha256_file(paths[name]) != frozen.file_sha256:
            raise ValueError(f"frozen {name} raw-file SHA-256 mismatch")
    template_bytes = paths["template"].read_bytes()
    if template_bytes != canonical_v2_template_bytes():
        raise ValueError("frozen template copy is not the unique canonical v2 template")
    if hashlib.sha256(template_bytes).hexdigest() != manifest.template.file_sha256:
        raise ValueError("frozen template SHA-256 mismatch")

    lineage = load_v2_rendered_input_lineage(
        package_path=paths["package"],
        view_path=paths["view"],
        rendered_input_path=paths["rendered"],
    )
    contract_hashes = {
        "package": lineage.package.canonical_sha256(),
        "view": lineage.view.canonical_sha256(),
        "rendered": lineage.rendered_input.canonical_sha256(),
    }
    for name, observed in contract_hashes.items():
        if observed != frozen_refs[name].contract_sha256:
            raise ValueError(f"frozen {name} contract SHA-256 mismatch")
    if lineage.rendered_input.rendered_sha256 != manifest.artifacts.rendered.rendered_text_sha256:
        raise ValueError("frozen rendered-text SHA-256 mismatch")
    if lineage.rendered_input.template_sha256 != canonical_v2_template_sha256():
        raise ValueError("rendered input does not bind the unique canonical v2 template")
    rebuilt = render_preproposal_candidate_input(
        lineage.package,
        lineage.view,
        input_id=lineage.rendered_input.input_id,
        template=canonical_v2_template_text(),
        template_sha256=canonical_v2_template_sha256(),
    )
    if rebuilt.canonical_bytes() != lineage.rendered_input.canonical_bytes():
        raise ValueError("rendered input is not the canonical rendering of the supplied package/view")
    return lineage, paths


def _parse_response(content: str) -> V2ProposalResponse:
    if not isinstance(content, str):
        raise ValueError("v2 proposer response content must be a JSON string")
    try:
        payload = json.loads(
            content,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant is forbidden: {value}")
            ),
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("v2 proposer response is not strict JSON") from exc
    return V2ProposalResponse.model_validate(payload, strict=True)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _validated_candidate_payloads(
    response: V2ProposalResponse,
    view: Any,
) -> list[dict[str, Any]]:
    batch = _validate_candidate_batch(response, view)
    if batch.report["invalid_rejected_count"]:
        raise ValueError("direct proposer response contains an invalid candidate")
    if batch.report["deduplicated_count"]:
        raise ValueError("direct proposer response contains a duplicate candidate")
    return list(batch.payloads)


def _validate_candidate_batch(
    response: V2ProposalResponse,
    view: Any,
    *,
    detail_region_id: str | None = None,
    visible_request_refs: set[str] | None = None,
    visible_action_ids: set[str] | None = None,
    visible_evidence_refs: set[str] | None = None,
    request_execution_kinds: Mapping[str, str] | None = None,
    request_execution_evidence: Mapping[str, Mapping[str, Any]] | None = None,
    observer_operation_catalog: tuple[dict[str, Any], ...] | None = None,
    required_effect_source_request_refs: set[str] | None = None,
    required_query_pair: tuple[str, str] | None = None,
) -> CandidateValidationBatch:
    requests = {str(item["request_ref"]): item for item in view.api_requests}
    if request_execution_kinds is not None:
        requests = {
            ref: {
                **request,
                "_execution_kind": request_execution_kinds.get(ref, "unknown"),
                **(
                    {
                        "_execution_read_evidence": dict(
                            request_execution_evidence[ref]
                        )
                    }
                    if request_execution_evidence is not None
                    and ref in request_execution_evidence
                    else {}
                ),
            }
            for ref, request in requests.items()
        }
    allowed_evidence = {
        *(str(item["event_id"]) for item in view.ui_actions),
        *requests,
        *(str(card.card_id) for card in view.evidence_cards),
        *(str(item["binding_id"]) for item in view.automatic_bindings),
        *(str(item["edge_id"]) for item in view.dependency_edges),
        *(str(item["flow_id"]) for item in view.observed_value_flows),
        *(str(item.opportunity_id) for item in view.binding_opportunities),
        *(str(item.witness_flow_id) for item in view.binding_opportunities),
        *(
            str(item["record_id"])
            for item in (
                view.evidence_channel_summaries
                .get("ui_diff", {})
                .get("semantic_projection", {})
                .get("rows", ())
            )
        ),
        *(str(item.fact_id) for item in view.transition_facts),
        *(
            str(item.fact_id)
            for item in getattr(view, "negative_request_facts", ())
        ),
    }
    executable_language = {
        (
            row["contract_kind"],
            row["predicate_family"],
            row["operator"],
        )
        for row in current_executable_relation_language()
    }
    payloads: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    seen_payloads: set[str] = set()
    invalid_count = 0
    duplicate_count = 0
    for ordinal, raw_item in enumerate(response.candidates, start=1):
        evidence_card_id = (
            raw_item.get("evidence_card_id")
            if isinstance(raw_item, dict)
            and isinstance(raw_item.get("evidence_card_id"), str)
            else None
        )
        if not _raw_candidate_literals_are_strict(raw_item):
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "candidate_schema_invalid",
            })
            continue
        try:
            relation = V2RelationProposal.model_validate(raw_item, strict=True)
        except (TypeError, ValueError) as error:
            invalid_count += 1
            unsupported_pattern = isinstance(error, ValidationError) and any(
                isinstance(issue.get("ctx", {}).get("error"), UnsupportedTextPattern)
                for issue in error.errors()
            )
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "unsupported_text_pattern" if unsupported_pattern else "candidate_schema_invalid",
            })
            continue
        relation = _normalize_removal_contract(relation, requests=requests)
        relation = _normalize_membership_to_reusable_observer(
            relation,
            requests=requests,
            view=view,
            visible_evidence_refs=visible_evidence_refs,
        )
        relation = _normalize_unique_collection_member_locator(
            relation,
            raw_candidates=response.candidates,
            requests=requests,
            view=view,
            visible_evidence_refs=visible_evidence_refs,
        )
        relation = _normalize_redundant_scalar_member_identity(
            relation,
            requests=requests,
        )
        relation = _normalize_unused_region_outside_action_ref(
            relation,
            requests=requests,
            allowed_evidence=allowed_evidence,
            view=view,
            visible_request_refs=visible_request_refs,
            visible_evidence_refs=visible_evidence_refs,
            observer_operation_catalog=observer_operation_catalog,
        )
        predicate = relation.primary_predicate
        relation_key = (
            relation.contract_kind,
            predicate.family,
            getattr(predicate, "operator", None),
        )
        if relation_key not in executable_language:
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "relation_not_in_current_executable_subset",
            })
            continue
        if detail_region_id is not None and relation.detail_region_id != detail_region_id:
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "detail_region_id_mismatch",
            })
            continue
        if detail_region_id is None and relation.detail_region_id is not None:
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "unexpected_detail_region_id",
            })
            continue
        if visible_request_refs is not None and any(
            row.request_ref not in visible_request_refs
            for row in relation.role_bindings
        ):
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "role_binding_outside_detail_region",
            })
            continue
        if visible_action_ids is not None and any(
            ref not in visible_action_ids for ref in relation.setup
        ):
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "setup_outside_detail_region",
            })
            continue
        if visible_evidence_refs is not None and any(
            ref not in visible_evidence_refs for ref in relation.evidence_refs
        ):
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": "evidence_ref_outside_detail_region",
            })
            continue
        if required_effect_source_request_refs is not None:
            centered_sources = [
                row
                for row in relation.role_bindings
                if row.role in {"effect_source", "negative_effect_source"}
                and row.request_ref in required_effect_source_request_refs
            ]
            if len(centered_sources) != 1:
                invalid_count += 1
                rows.append({
                    "ordinal": ordinal,
                    "evidence_card_id": evidence_card_id,
                    "disposition": "rejected",
                    "reason_code": "center_completion_effect_source_mismatch",
                })
                continue
        if required_query_pair is not None:
            source_ref, followup_ref = required_query_pair
            predicate = relation.primary_predicate
            query_bindings = {
                row.role: row.request_ref
                for row in relation.role_bindings
                if row.role in {"source_query", "followup_query:q1"}
            }
            if (
                relation.contract_kind != "C08"
                or predicate.family != "P17"
                or getattr(predicate, "operator", None) != "subset"
                or query_bindings != {
                    "source_query": source_ref,
                    "followup_query:q1": followup_ref,
                }
                or len(query_bindings) != 2
            ):
                invalid_count += 1
                rows.append({
                    "ordinal": ordinal,
                    "evidence_card_id": evidence_card_id,
                    "disposition": "rejected",
                    "reason_code": "query_completion_opportunity_mismatch",
                })
                continue
        try:
            payload, plan = _construct_candidate_and_plan(
                relation,
                requests=requests,
                allowed_evidence=allowed_evidence,
                view=view,
                visible_request_refs=visible_request_refs,
                visible_evidence_refs=visible_evidence_refs,
                observer_operation_catalog=observer_operation_catalog,
            )
        except CandidateAdmissionError as exc:
            invalid_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "rejected",
                "reason_code": exc.reason_code,
            })
            continue
        canonical_core_identity = canonical_relation_core_identity(
            payload,
            plan,
            view.api_requests,
        )
        payload_sha = _canonical_sha256(payload)
        relation_sha = _canonical_sha256(_scientific_relation_payload(payload))
        if relation_sha in seen_payloads:
            duplicate_count += 1
            rows.append({
                "ordinal": ordinal,
                "evidence_card_id": evidence_card_id,
                "disposition": "deduplicated",
                "reason_code": "duplicate_candidate_payload",
                "payload_sha256": payload_sha,
                "relation_sha256": relation_sha,
                "canonical_relation_core_identity": canonical_core_identity,
            })
            continue
        seen_payloads.add(relation_sha)
        payloads.append(payload)
        plans.append(plan)
        rows.append({
            "ordinal": ordinal,
            "evidence_card_id": evidence_card_id,
            "disposition": "admitted",
            "reason_code": "candidate_valid",
            "payload_sha256": payload_sha,
            "relation_sha256": relation_sha,
            "canonical_relation_core_identity": canonical_core_identity,
            "constructed_execution_plan_ref": plan["plan_id"],
        })
    report = {
        "schema_version": "uisemtest-v2-candidate-validation-report-v1",
        "status": "complete",
        "scientific_input_version": SCIENTIFIC_INPUT_VERSION,
        "raw_proposed_count": len(response.candidates),
        "valid_admitted_count": len(payloads),
        "invalid_rejected_count": invalid_count,
        "deduplicated_count": duplicate_count,
        "candidates": rows,
    }
    if len(response.candidates) != len(payloads) + invalid_count + duplicate_count:
        raise RuntimeError("candidate validation partition did not close")
    return CandidateValidationBatch(
        payloads=tuple(payloads),
        constructed_execution_plans=tuple(plans),
        report=report,
    )


def _normalize_unused_region_outside_action_ref(
    relation: V2RelationProposal,
    *,
    requests: dict[str, dict[str, Any]],
    allowed_evidence: set[str],
    view: Any,
    visible_request_refs: set[str] | None,
    visible_evidence_refs: set[str] | None,
    observer_operation_catalog: tuple[dict[str, Any], ...] | None,
) -> V2RelationProposal:
    """Drop one extraneous action citation only when execution is invariant.

    Detail visibility remains fail-closed for requests and scientific witnesses.
    This normalization is limited to a single globally recorded UI action and
    proves, by constructing both interpretations, that neither the executable
    relation nor its unique plan uses that citation.
    """

    if visible_evidence_refs is None:
        return relation
    outside = [
        ref for ref in relation.evidence_refs if ref not in visible_evidence_refs
    ]
    action_ids = {str(item["event_id"]) for item in view.ui_actions}
    if len(outside) != 1 or not _resolves_as_unique_workflow_action(
        outside[0], action_ids
    ):
        return relation
    filtered = relation.model_copy(
        update={
            "evidence_refs": [
                ref for ref in relation.evidence_refs if ref != outside[0]
            ]
        }
    )
    if not filtered.evidence_refs:
        return relation
    try:
        filtered_payload, filtered_plan = _construct_candidate_and_plan(
            filtered,
            requests=requests,
            allowed_evidence=allowed_evidence,
            view=view,
            visible_request_refs=visible_request_refs,
            visible_evidence_refs=visible_evidence_refs,
            observer_operation_catalog=observer_operation_catalog,
        )
    except CandidateAdmissionError:
        return relation
    if outside[0] in allowed_evidence:
        try:
            full_payload, full_plan = _construct_candidate_and_plan(
                relation,
                requests=requests,
                allowed_evidence=allowed_evidence,
                view=view,
                visible_request_refs=visible_request_refs,
                visible_evidence_refs=allowed_evidence,
                observer_operation_catalog=observer_operation_catalog,
            )
        except CandidateAdmissionError:
            return relation
        if (
            _scientific_relation_payload(full_payload)
            != _scientific_relation_payload(filtered_payload)
            or full_plan != filtered_plan
        ):
            return relation
    return filtered


def _resolves_as_unique_workflow_action(
    reference: str, recorded_action_ids: set[str]
) -> bool:
    """Recognize one action citation without guessing its actor/session prefix."""

    if reference in recorded_action_ids:
        return True
    match = re.fullmatch(r"[^:]+:workflow-action-(\d{4})", reference)
    if match is None:
        return False
    suffix = f":workflow-action-{match.group(1)}"
    return sum(action_id.endswith(suffix) for action_id in recorded_action_ids) == 1


def _scientific_relation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the exact executable relation, excluding only proposal provenance."""

    return {
        key: _predicate_identity_payload(payload[key]) if key == "primary_predicate" else payload[key]
        for key in (
            "contract_kind",
            "observation_opportunity_ref",
            "primary_predicate",
            "producer",
            "consumer",
            "setup",
        )
    }


def _predicate_identity_payload(value: Any) -> Any:
    """Normalize finite equivalent spellings without rewriting source evidence."""
    if isinstance(value, Mapping):
        if value.get("source") == "hypothesis":
            # The value is opaque JSON data, even if its keys resemble DSL or
            # provenance fields. Only this operand's provenance is excluded.
            result = {key: copy.deepcopy(item) for key, item in value.items() if key not in {"rationale", "evidence_refs"}}
            if result.get("value_type") == "number" and result.get("lexical") is not None:
                numerator, denominator = Decimal(result.pop("lexical")).as_integer_ratio()
                result["value"] = {"numerator": numerator, "denominator": denominator}
            elif result.get("value_type") == "integer":
                # Admission already proves any numeric lexical token denotes
                # this exact integer; its optional spelling is not a new rule.
                result.pop("lexical", None)
            return result
        result = {key: _predicate_identity_payload(item) for key, item in value.items()}
        if result.get("family") in {"P06", "P08", "P19"} and result.get("conversions") is not None:
            for conversion in result["conversions"]["value"].values():
                numerator, denominator = Decimal(conversion["factor"]).as_integer_ratio()
                conversion["factor"] = {"numerator": numerator, "denominator": denominator}
        if result.get("family") in {"P16", "P17"}:
            result["projection"] = sorted(result.get("projection", []))
            if result.get("identity") is not None:
                result["identity"]["paths"] = sorted(result["identity"]["paths"])
        if result.get("kind") in {"equivalent_input", "filter_refinement", "filter_expansion", "sort", "pagination_partition", "finite_query_plan"} and "keys" in result:
            result["keys"] = sorted(result["keys"])
        domain = result.get("domain")
        if (
            result.get("family") == "P03" and result.get("operator") == "in"
            and isinstance(domain, dict) and domain.get("source") == "hypothesis"
            and domain.get("value_type") == "array" and isinstance(domain.get("value"), list)
        ):
            members = {}
            for item in domain["value"]:
                item = _enum_identity_value(item)
                key = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                members[key] = item
            domain["value"] = [members[key] for key in sorted(members)]
        return result
    if isinstance(value, (list, tuple)):
        return [_predicate_identity_payload(item) for item in value]
    return copy.deepcopy(value)


def _enum_identity_value(value: Any) -> Any:
    """Canonicalize one strict JSON enum member, retaining array order and type."""
    if type(value) is float and value == 0:
        return 0.0  # The existing strict equality treats signed float zeros alike.
    if isinstance(value, dict):
        return {key: _enum_identity_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_enum_identity_value(item) for item in value]
    return value


def canonical_relation_core_payload(
    payload: Mapping[str, Any],
    constructed_plan: Mapping[str, Any],
    api_requests: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Project one relation to the reporting-only WP7 canonical core.

    Physical identifiers and proposal provenance are intentionally excluded.
    Literal actors become stable role slots, preserving only their equality
    topology. Request bindings contribute their canonical operation/resource
    facts, never their recording-local references.
    """

    requests = {str(row["request_ref"]): row for row in api_requests}
    raw_roles: dict[str, Mapping[str, Any]] = {}
    plan_roles = constructed_plan.get("roles", {})
    if isinstance(plan_roles, Mapping):
        raw_roles.update(
            (str(role), binding)
            for role, binding in plan_roles.items()
            if isinstance(binding, Mapping)
        )
    for role in ("producer", "consumer"):
        binding = payload.get(role)
        if isinstance(binding, Mapping):
            raw_roles.setdefault(role, binding)

    priority = {
        name: index
        for index, name in enumerate(
            (
                "producer", "before", "after", "control_before",
                "control_after", "consumer", "observer", "source",
                "followup", "actor_before", "actor_after",
            )
        )
    }
    ordered_roles = sorted(
        raw_roles,
        key=lambda role: (priority.get(role.split(":", 1)[0], 100), role),
    )
    actor_slots: dict[str, str] = {}
    for role in ordered_roles:
        actor = raw_roles[role].get("actor")
        if isinstance(actor, str) and actor not in actor_slots:
            actor_slots[actor] = f"actor_slot_{len(actor_slots) + 1}"

    def normalize_role(value: str) -> str:
        if ":" not in value:
            return value
        prefix, actor = value.split(":", 1)
        if prefix not in {"actor_before", "actor_after"}:
            return value
        slot = actor_slots.get(actor)
        if slot is None:
            slot = f"actor_slot_{len(actor_slots) + 1}"
            actor_slots[actor] = slot
        return f"{prefix}:{slot}"

    def normalize(value: Any, *, key: str | None = None) -> Any:
        if isinstance(value, Mapping):
            normalized = {
                str(name): copy.deepcopy(item) if value.get("source") == "hypothesis" and name == "value" else normalize(item, key=str(name))
                for name, item in sorted(value.items(), key=lambda row: str(row[0]))
                if str(name) != "fact_ref"
            }
            if value.get("family") == "P20":
                normalized.pop("projection_ref", None)
                if "projection" in normalized:
                    normalized["projection"] = sorted(normalized["projection"])
            return normalized
        if isinstance(value, (list, tuple)):
            return [normalize(item, key=key) for item in value]
        if key == "role" and isinstance(value, str):
            return normalize_role(value)
        return copy.deepcopy(value)

    canonical_roles: dict[str, dict[str, Any]] = {}
    actor_topology: dict[str, str] = {}
    for role in ordered_roles:
        binding = raw_roles[role]
        canonical_role = normalize_role(role)
        actor = binding.get("actor")
        if isinstance(actor, str):
            actor_topology[canonical_role] = actor_slots[actor]
        request_ref = binding.get("request_ref")
        request = requests.get(str(request_ref))
        if request is None:
            raise ValueError("canonical relation core request binding is unresolved")
        canonical_roles[canonical_role] = {
            "method": request.get("method"),
            "operation_id": request.get("operation_id"),
            "canonical_path": request.get("canonical_path"),
        }

    raw_predicate = payload["primary_predicate"]
    p06_workflow = (
        raw_predicate.get("family") == "P06"
        and constructed_plan.get("shape_kind") == "lifecycle_workflow"
        and constructed_plan.get("workflow_kind") == "before_write_after"
    )
    workflow_effect = (
        payload["contract_kind"] == "C04" and raw_predicate.get("family") == "P20"
        or payload["contract_kind"] == "C02" and raw_predicate.get("family") == "P07"
        or p06_workflow
        or payload["contract_kind"] == "C02" and raw_predicate.get("family") == "P04"
        and raw_predicate.get("before", {}).get("value_type") in {"string", "integer"}
    )
    if workflow_effect or constructed_plan.get("shape_kind") in {"metamorphic_query", "lifecycle_workflow", "repeated_execution", "actor_matrix", "negative_no_effect"}:
        for role, binding in raw_roles.items():
            request = requests[str(binding["request_ref"])]
            if constructed_plan.get("shape_kind") != "metamorphic_query" and not _is_read(dict(request)):
                continue
            # These are frozen M9 selector values, not recording occurrence IDs.
            # Do not guess a fresh-binding recipe from an ID-like parameter name.
            canonical_roles[normalize_role(role)]["query_parameters"] = copy.deepcopy(request.get("query") or {})
            body_shape = request.get("request_body_shape") or {}
            body_values = _query_selector_values(request, "body") if constructed_plan.get("shape_kind") == "metamorphic_query" else None
            canonical_roles[normalize_role(role)]["body_selector"] = (
                {"body_kind": body_shape.get("body_kind"), "parameters": body_values}
                if body_values is not None else
                {"body_kind": body_shape.get("body_kind"), "body_sha256": body_shape.get("body_sha256")}
            )

    predicate = normalize(_predicate_identity_payload(payload["primary_predicate"]))
    if (
        p06_workflow and predicate["delta"].get("source") == "role"
        and predicate["delta"]["ref"]["role"] == "producer_request"
    ):
        # The legacy producer_request role reads the same body as the explicit
        # request operand. Normalize only this reporting projection, not exact
        # relation identity or the original admitted predicate.
        predicate["delta"]["source"] = "request"
        predicate["delta"]["ref"]["location"] = "body"
    if payload["contract_kind"] == "C04" and predicate.get("family") == "P20":
        predicate.pop("projection_ref", None)
    if workflow_effect and (
        constructed_plan.get("shape_kind") == "lifecycle_workflow"
        and constructed_plan.get("workflow_kind") == "before_write_after"
    ):
        endpoint_keys = ("left", "right") if predicate["family"] == "P20" else ("before", "after")
        for endpoint in (predicate[key] for key in endpoint_keys):
            if endpoint.get("source") != "collection_member":
                continue
            member = endpoint.pop("member")["ref"]
            binding = raw_roles["producer"]
            request = requests[str(binding["request_ref"])]
            shape_key = (
                "response_body_shape"
                if member["role"] == "producer_response"
                else "request_body_shape"
            )
            shape = _shape_path_types(request[shape_key])
            identity_fields = []
            for pair in endpoint["identity"]["field_pairs"]:
                path = _identity_path(member["path"], pair["member_path"])
                identity_fields.append({
                    "role": member["role"], "path": path,
                    "value_type": shape[path],
                    "collection_item_path": pair["collection_item_path"],
                })
            endpoint["identity"] = {
                "semantics": "strict-tuple",
                "fields": sorted(identity_fields, key=lambda item: json.dumps(item, sort_keys=True)),
            }
    field_roles: list[dict[str, Any]] = []

    def collect_fields(value: Any) -> None:
        if isinstance(value, Mapping):
            if value.get("source") == "hypothesis":
                return
            if isinstance(value.get("role"), str) and isinstance(value.get("path"), str):
                field_roles.append({
                    key: copy.deepcopy(value[key])
                    for key in ("role", "location", "path", "value_type")
                    if key in value
                })
            for item in value.values():
                collect_fields(item)
        elif isinstance(value, list):
            for item in value:
                collect_fields(item)

    collect_fields(predicate)
    return {
        "contract_kind": "C14" if constructed_plan["shape_kind"] == "single_state" and predicate["family"] in {"P08", "P19"} else payload["contract_kind"],
        "primary_predicate": predicate,
        "protocol": {
            "shape": constructed_plan["shape_kind"],
            **({"time_requirement": normalize(_predicate_identity_payload(constructed_plan["time_requirement"])), "observation_count": len(constructed_plan["observation_plan"])} if constructed_plan["shape_kind"] == "temporal" else {}),
            **({"joint_observation": normalize(_predicate_identity_payload(constructed_plan["joint_observation"])), "checkpoints": [{"role": row["role"], "phase": row["phase"]} for row in constructed_plan["observation_plan"]]} if constructed_plan["shape_kind"] == "multi_resource" else {}),
            "variant": constructed_plan.get("workflow_kind", constructed_plan.get("transform_kind", constructed_plan.get("repetition_kind", constructed_plan.get("negative_kind")))),
            **({"identity_topology": {
                "left_actor": actor_slots[constructed_plan["identity_topology"]["left_actor_id"]],
                "right_actor": actor_slots[constructed_plan["identity_topology"]["right_actor_id"]],
                "principal_relation": constructed_plan["identity_topology"]["principal_relation"],
                "session_relation": constructed_plan["identity_topology"]["session_relation"],
            }} if constructed_plan.get("identity_topology") is not None else {}),
            **({"negative_session_boundary": constructed_plan["session_boundary"]["kind"], "rejection_detector": normalize(_predicate_identity_payload(constructed_plan["rejection_detector"]))} if constructed_plan.get("shape_kind") == "negative_no_effect" else {}),
            **({"query_scope": normalize(_predicate_identity_payload(constructed_plan.get("query_scope"))), "query_transform": normalize(_predicate_identity_payload(constructed_plan.get("query_transform")))} if constructed_plan["shape_kind"] == "metamorphic_query" else {}),
        },
        "role_operations": canonical_roles,
        "field_roles": field_roles,
        "actor_topology": actor_topology,
    }


def canonical_relation_core_identity(
    payload: Mapping[str, Any],
    constructed_plan: Mapping[str, Any],
    api_requests: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> str:
    return _canonical_sha256(
        canonical_relation_core_payload(payload, constructed_plan, api_requests)
    )


def _raw_candidate_literals_are_strict(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    predicate = value.get("primary_predicate")
    if not isinstance(predicate, dict):
        return True
    predicate_type = predicate.get("family")
    keys = {"P06": ("multiplier",), "P12": ("delta",)}.get(
        predicate_type, ()
    )
    if not all(
        key not in predicate or type(predicate[key]) is int
        for key in keys
    ):
        return False
    constants = []
    if predicate_type == "P04":
        constants = [row for row in (predicate.get("from_value"), predicate.get("to_value")) if isinstance(row, dict) and row.get("source") == "transition_fact"]
    elif predicate_type == "P06" and isinstance(predicate.get("delta"), dict):
        if predicate["delta"].get("source") == "transition_fact":
            constants = [predicate["delta"]]
    expected = {"boolean": bool, "integer": int, "number": float}
    return all(
        not isinstance(row, dict)
        or type(row.get("value")) is expected.get(row.get("value_type"))
        for row in constants
    )


def _normalize_removal_contract(
    relation: V2RelationProposal,
    *,
    requests: dict[str, dict[str, Any]],
) -> V2RelationProposal:
    """Map an unambiguous lifecycle removal to the existing C03 contract."""

    predicate = relation.primary_predicate
    if not (
        relation.contract_kind == "C01"
        and isinstance(predicate, MembershipPredicate)
        and predicate.operator == "removed"
        and predicate.before.role == "before"
        and predicate.after.role == "after"
    ):
        return relation
    by_role = _bindings_by_role(relation)
    if set(by_role) != {"before", "effect_source", "after"} or any(
        len(rows) != 1 for rows in by_role.values()
    ):
        return relation
    before = _binding_endpoint(by_role["before"][0])
    producer = _binding_endpoint(by_role["effect_source"][0])
    after = _binding_endpoint(by_role["after"][0])
    if _v4_plan(before, producer, after, requests) is None:
        return relation
    return relation.model_copy(update={"contract_kind": "C03"})


def _normalize_membership_to_reusable_observer(
    relation: V2RelationProposal,
    *,
    requests: dict[str, dict[str, Any]],
    view: Any,
    visible_evidence_refs: set[str] | None,
) -> V2RelationProposal:
    """Use one repeatable after-read when an unrelated before cannot form V4."""

    predicate = relation.primary_predicate
    if not (
        relation.contract_kind == "C01"
        and isinstance(predicate, MembershipPredicate)
        and predicate.operator == "added"
        and predicate.before.role == "before"
        and predicate.after.role == "after"
    ):
        return relation
    by_role = _bindings_by_role(relation)
    if set(by_role) != {"before", "effect_source", "after"} or any(
        len(rows) != 1 for rows in by_role.values()
    ):
        return relation
    before_binding = by_role["before"][0]
    producer_binding = by_role["effect_source"][0]
    after_binding = by_role["after"][0]
    before = _binding_endpoint(before_binding)
    producer = _binding_endpoint(producer_binding)
    after = _binding_endpoint(after_binding)
    before_row = requests.get(before.request_ref)
    producer_row = requests.get(producer.request_ref)
    after_row = requests.get(after.request_ref)
    if any(row is None for row in (before_row, producer_row, after_row)):
        return relation
    assert before_row is not None and producer_row is not None and after_row is not None
    if (
        _v4_plan(before, producer, after, requests) is not None
        or not _is_write(producer_row)
        or not _is_read(after_row)
        or before.actor != producer.actor
        or producer.actor != after.actor
        or len({
            str(before_row["session_run_id"]),
            str(producer_row["session_run_id"]),
            str(after_row["session_run_id"]),
        }) != 1
        or not (
            int(before_row["global_order"])
            < int(producer_row["global_order"])
            < int(after_row["global_order"])
        )
        or before_row["operation_id"] == after_row["operation_id"]
    ):
        return relation
    before_shape = _shape_path_types(before_row["response_body_shape"])
    after_shape = _shape_path_types(after_row["response_body_shape"])
    normalized_before_path = _indexed_path_to_wildcard(predicate.before.path)
    if (
        before_shape.get(normalized_before_path) != "array"
        or after_shape.get(predicate.after.path) != "array"
    ):
        return relation
    endpoint_refs = {before.request_ref, producer.request_ref, after.request_ref}
    visible = visible_evidence_refs
    linked = False
    for flow in view.observed_value_flows:
        flow_id = str(flow["flow_id"])
        if flow_id not in relation.evidence_refs:
            continue
        if visible is not None and flow_id not in visible:
            continue
        source_ref = str(flow.get("producer_request_ref") or flow.get("from_request_ref") or "")
        target_ref = str(flow.get("consumer_request_ref") or flow.get("to_request_ref") or "")
        if (
            source_ref in endpoint_refs
            and target_ref in endpoint_refs
            and source_ref != target_ref
            and (
                _identity_like_path(str(flow.get("from_field") or ""))
                or _identity_like_path(str(flow.get("to_field") or ""))
            )
        ):
            linked = True
            break
    if not linked:
        return relation
    normalized_predicate = predicate.model_copy(update={
        "before": predicate.after.model_copy(update={"role": "before"}),
    })
    normalized_bindings = [
        RelationRoleBinding(
            role="effect_source",
            request_ref=producer.request_ref,
            actor=producer.actor,
        ),
        RelationRoleBinding(
            role="reusable_observer",
            request_ref=after.request_ref,
            actor=after.actor,
        ),
    ]
    return relation.model_copy(update={
        "primary_predicate": normalized_predicate,
        "role_bindings": normalized_bindings,
    })


def _bindings_by_role(
    relation: V2RelationProposal,
) -> dict[str, list[RelationRoleBinding]]:
    by_role: dict[str, list[RelationRoleBinding]] = {}
    for binding in relation.role_bindings:
        by_role.setdefault(binding.role, []).append(binding)
    return by_role


def _binding_endpoint(binding: RelationRoleBinding) -> ProposalEndpoint:
    return ProposalEndpoint(
        request_ref=binding.request_ref,
        actor=binding.actor,
    )


def _normalize_unique_collection_member_locator(
    relation: V2RelationProposal,
    *,
    raw_candidates: list[Any],
    requests: dict[str, dict[str, Any]],
    view: Any,
    visible_evidence_refs: set[str] | None,
) -> V2RelationProposal:
    """Materialize a wildcard P02 only when one explicit identity locator exists."""

    predicate = relation.primary_predicate
    if (
        not isinstance(predicate, EqualityPredicate)
        or not isinstance(predicate.right, RoleOperand)
        or not isinstance(predicate.left, ValueRef)
        or predicate.left.role != "after"
        or "[*]" not in predicate.left.path
        or predicate.right.ref.role
        not in {"producer_request", "producer_response"}
    ):
        return relation
    endpoints = _unique_effect_and_observer(relation)
    if endpoints is None:
        return relation
    producer_ref, observer_ref = endpoints
    producer_request = requests.get(producer_ref)
    observer_request = requests.get(observer_ref)
    if producer_request is None or observer_request is None:
        return relation
    collection_path, field_path = _split_collection_item_path(
        predicate.left.path
    )
    if collection_path is None:
        return relation
    if (
        _identity_like_path(field_path or "")
        and _identity_like_path(predicate.right.ref.path)
    ):
        return relation
    producer_shapes = {
        "producer_request": _shape_path_types(
            producer_request["request_body_shape"]
        ),
        "producer_response": _shape_path_types(
            producer_request["response_body_shape"]
        ),
    }
    producer_shape = producer_shapes["producer_request"]
    observer_shape = _shape_path_types(observer_request["response_body_shape"])

    locator_pairs: set[tuple[str, str, str]] = set()
    binding_key = tuple(sorted(
        (row.role, row.actor, row.request_ref) for row in relation.role_bindings
    ))
    for raw in raw_candidates:
        try:
            sibling = V2RelationProposal.model_validate(raw, strict=True)
        except (TypeError, ValueError):
            continue
        sibling_predicate = sibling.primary_predicate
        if (
            sibling.detail_region_id != relation.detail_region_id
            or tuple(sorted(
                (row.role, row.actor, row.request_ref)
                for row in sibling.role_bindings
            )) != binding_key
            or not isinstance(sibling_predicate, EqualityPredicate)
            or not isinstance(sibling_predicate.left, ValueRef)
            or sibling_predicate.left.role != "after"
            or sibling_predicate.right.ref.role
            not in {"producer_request", "producer_response"}
            or "[*]" not in sibling_predicate.left.path
        ):
            continue
        sibling_collection, sibling_item_path = _split_collection_item_path(
            sibling_predicate.left.path
        )
        pair = (
            sibling_predicate.right.ref.role,
            sibling_predicate.right.ref.path,
            sibling_item_path or "",
        )
        if (
            sibling_collection == collection_path
            and pair
            != (
                predicate.right.ref.role,
                predicate.right.ref.path,
                field_path,
            )
            and producer_shapes.get(pair[0], {}).get("$") == "object"
            and _identity_like_path(pair[1])
            and _identity_like_path(pair[2])
            and producer_shapes[pair[0]].get(pair[1])
            == observer_shape.get(sibling_predicate.left.path)
        ):
            locator_pairs.add(pair)

    visible = visible_evidence_refs
    for flow in view.observed_value_flows:
        if visible is not None and str(flow["flow_id"]) not in visible:
            continue
        if (
            str(flow["consumer_request_ref"]) != producer_ref
            or str(flow["producer_operation_id"])
            != str(observer_request["operation_id"])
            or str(flow["from_location"]) != "response_body"
            or str(flow["to_location"]) != "body"
        ):
            continue
        observed_path = _indexed_path_to_wildcard(str(flow["from_field"]))
        observed_collection, observed_item_path = _split_collection_item_path(
            observed_path
        )
        producer_path = str(flow["to_field"])
        if (
            observed_collection == collection_path
            and observed_item_path is not None
            and _identity_like_path(producer_path)
            and _identity_like_path(observed_item_path)
            and producer_shape.get(producer_path)
            == observer_shape.get(observed_path)
        ):
            locator_pairs.add((
                "producer_request",
                producer_path,
                observed_item_path,
            ))

    for opportunity in view.binding_opportunities:
        if visible is not None and opportunity.opportunity_id not in visible:
            continue
        if (
            opportunity.consumer_operation_id
            != str(producer_request["operation_id"])
            or opportunity.producer_operation_id
            != str(observer_request["operation_id"])
            or opportunity.from_location != "response_body"
            or opportunity.to_location != "body"
        ):
            continue
        observed_path = _indexed_path_to_wildcard(opportunity.from_field)
        observed_collection, observed_item_path = _split_collection_item_path(
            observed_path
        )
        if (
            observed_collection == collection_path
            and observed_item_path is not None
            and _identity_like_path(opportunity.to_field)
            and _identity_like_path(observed_item_path)
            and producer_shape.get(opportunity.to_field)
            == observer_shape.get(observed_path)
        ):
            locator_pairs.add((
                "producer_request",
                opportunity.to_field,
                observed_item_path,
            ))

    if len(locator_pairs) != 1:
        return relation
    member_role, member_path, collection_item_path = next(iter(locator_pairs))
    located = LocatedMemberFieldRef(
        source="collection_member",
        role="after",
        collection_path=collection_path,
        field_path=field_path,
        value_type=predicate.left.value_type,
        member=RoleOperand(
            source="role",
            ref=ValueRef(
                role=member_role,
                path="$",
                value_type="object",
            ),
        ),
        identity=MemberIdentitySpec(
            field_pairs=[IdentityFieldPair(
                member_path=member_path,
                collection_item_path=collection_item_path,
            )],
            semantics="strict-tuple",
        ),
    )
    return relation.model_copy(update={
        "primary_predicate": EqualityPredicate(
            family="P02",
            operator="eq",
            left=located,
            right=predicate.right,
        )
    })


def _normalize_redundant_scalar_member_identity(
    relation: V2RelationProposal,
    *,
    requests: dict[str, dict[str, Any]],
) -> V2RelationProposal:
    """Canonicalize one shape-proven redundant P13/P14 member path.

    A provider can describe the same scalar identity both as the member ref and
    as the sole member-side field pair.  Treat that spelling as an absolute
    member path only when the effect-source shape uniquely proves an object
    root and the exact scalar path/type.  All other path compositions retain
    their ordinary relative-path meaning and fail closed downstream.
    """

    predicate = relation.primary_predicate
    if not isinstance(
        predicate, (CollectionMembershipPredicate, MembershipPredicate)
    ):
        return relation
    if predicate.identity is None:
        return relation
    pairs = predicate.identity.field_pairs
    member_ref = predicate.member.ref
    if (
        len(pairs) != 1
        or member_ref.role not in {"producer_request", "producer_response"}
        or member_ref.path != pairs[0].member_path
        or not member_ref.path.startswith("$.")
        or "[*]" in member_ref.path
        or member_ref.value_type in {"object", "array", "null"}
    ):
        return relation
    by_role = _bindings_by_role(relation)
    effect_sources = by_role.get("effect_source", ())
    if len(effect_sources) != 1:
        return relation
    request = requests.get(effect_sources[0].request_ref)
    if request is None:
        return relation
    shape_key = (
        "request_body_shape"
        if member_ref.role == "producer_request"
        else "response_body_shape"
    )
    shape_rows = request[shape_key].get("shape_rows", ())
    types_by_path: dict[str, set[str]] = {}
    for row in shape_rows:
        types_by_path.setdefault(str(row.get("path")), set()).add(
            str(row.get("type"))
        )
    if (
        types_by_path.get("$") != {"object"}
        or types_by_path.get(member_ref.path) != {member_ref.value_type}
    ):
        return relation
    canonical_member = predicate.member.model_copy(update={
        "ref": member_ref.model_copy(update={
            "path": "$",
            "value_type": "object",
        })
    })
    return relation.model_copy(update={
        "primary_predicate": predicate.model_copy(update={
            "member": canonical_member,
        })
    })


def _unique_effect_and_observer(
    relation: V2RelationProposal,
) -> tuple[str, str] | None:
    by_role: dict[str, list[str]] = {}
    for row in relation.role_bindings:
        by_role.setdefault(row.role, []).append(row.request_ref)
    if any(len(rows) != 1 for rows in by_role.values()):
        return None
    if set(by_role) == {"effect_source", "reusable_observer"}:
        return by_role["effect_source"][0], by_role["reusable_observer"][0]
    if (
        set(by_role) == {"before", "effect_source", "after"}
        and "before" not in _predicate_referenced_roles(
            relation.primary_predicate
        )
    ):
        return by_role["effect_source"][0], by_role["after"][0]
    return None


def _split_collection_item_path(path: str) -> tuple[str | None, str | None]:
    if path.count("[*]") != 1:
        return None, None
    collection, suffix = path.split("[*]", 1)
    if not collection.startswith("$") or not suffix:
        return None, None
    return collection, f"${suffix}"


def _shape_path_types(shape: dict[str, Any]) -> dict[str, str]:
    return {
        str(row["path"]): str(row["type"])
        for row in shape.get("shape_rows", ())
    }


def _identity_like_path(path: str) -> bool:
    token = path.rsplit(".", 1)[-1].lower()
    return (
        token in {"id", "uuid", "slug", "key", "code", "username"}
        or token.endswith(("_id", "-id", "uuid", "slug", "key", "code"))
        or (token.endswith("id") and len(token) > 2)
    )


def _indexed_path_to_wildcard(path: str) -> str:
    parts: list[str] = []
    cursor = 0
    while cursor < len(path):
        if path[cursor] == "[":
            end = path.find("]", cursor + 1)
            if end != -1 and path[cursor + 1:end].isdigit():
                parts.append("[*]")
                cursor = end + 1
                continue
        parts.append(path[cursor])
        cursor += 1
    return "".join(parts)


def _predicate_referenced_roles(predicate: PrimaryPredicate) -> set[str]:
    roles: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            role = value.get("role")
            if isinstance(role, str):
                roles.add(role)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(predicate.model_dump(mode="json"))
    return roles


def _catalog_observer_plan(
    relation: V2RelationProposal,
    *,
    producer: ProposalEndpoint,
    requests: dict[str, dict[str, Any]],
    view: Any,
    observer_operation_catalog: tuple[dict[str, Any], ...] | None,
) -> dict[str, Any]:
    """Resolve one model-selected M5 operation to one observed request template."""

    selected_id = relation.catalog_observer_operation_id
    if selected_id is None:
        raise CandidateAdmissionError("observer_catalog_unavailable")
    options = [
        row
        for row in (observer_operation_catalog or ())
        if str(row.get("operation_id")) == selected_id
    ]
    if not options:
        raise CandidateAdmissionError("observer_catalog_unavailable")
    if len(options) != 1:
        raise CandidateAdmissionError("observer_catalog_ambiguous")
    option = options[0]
    view_operations = [
        row
        for row in getattr(view, "api_operations", ())
        if str(row.get("operation_id")) == selected_id
    ]
    if len(view_operations) != 1:
        raise CandidateAdmissionError(
            "observer_catalog_ambiguous"
            if len(view_operations) > 1
            else "observer_catalog_unavailable"
        )
    view_operation = view_operations[0]
    if any(
        str(option.get(key)) != str(view_operation.get(key))
        for key in ("method", "canonical_path", "readiness")
    ) or str(option.get("catalog_operation_sha256")) != str(
        view_operation.get("full_row_sha256")
    ):
        raise CandidateAdmissionError("observer_catalog_unavailable")

    producer_row = requests[producer.request_ref]
    candidates: dict[str, tuple[ProposalEndpoint, dict[str, Any]]] = {}
    for template in option.get("templates", ()):
        if not isinstance(template, Mapping):
            continue
        request_ref = str(template.get("request_ref") or "")
        request = requests.get(request_ref)
        if not isinstance(request, Mapping):
            continue
        response_shape = dict(request.get("response_body_shape") or {})
        template_payload = {
            "actor_id": str(request.get("actor_id") or ""),
            "session_run_id": str(request.get("session_run_id") or ""),
            "operation_id": str(request.get("operation_id") or ""),
            "method": str(request.get("method") or "").upper(),
            "canonical_path": str(request.get("canonical_path") or ""),
            "selector_snapshot_sha256": _selector_snapshot_sha256(request),
            "response_body_shape_sha256": _canonical_sha256(response_shape),
        }
        template_sha = _canonical_sha256(template_payload)
        has_prewrite_template = any(
            _is_read(dict(row))
            and str(row.get("actor_id") or "") == template_payload["actor_id"]
            and str(row.get("session_run_id") or "")
            == template_payload["session_run_id"]
            and str(row.get("operation_id") or "")
            == template_payload["operation_id"]
            and str(row.get("method") or "").upper()
            == template_payload["method"]
            and str(row.get("canonical_path") or "")
            == template_payload["canonical_path"]
            and _selector_snapshot_sha256(dict(row))
            == template_payload["selector_snapshot_sha256"]
            and _canonical_sha256(dict(row.get("response_body_shape") or {}))
            == template_payload["response_body_shape_sha256"]
            and int(row["global_order"]) < int(producer_row["global_order"])
            for row in requests.values()
        )
        if (
            request_ref not in set(map(str, view_operation.get("stage1_request_refs", ())))
            or any(
                str(template.get(key)) != str(template_payload[key])
                for key in template_payload
            )
            or str(template.get("template_sha256")) != template_sha
            or template_payload["operation_id"] != selected_id
            or template_payload["actor_id"] != producer.actor
            or template_payload["session_run_id"]
            != str(producer_row.get("session_run_id"))
            or template_payload["method"] != str(option["method"]).upper()
            or template_payload["canonical_path"] != str(option["canonical_path"])
            or not _is_read(dict(request))
            or (
                str(producer_row.get("method") or "").upper() == "POST"
                and not has_prewrite_template
            )
        ):
            continue
        observer = ProposalEndpoint(
            request_ref=request_ref,
            actor=template_payload["actor_id"],
        )
        if int(request["global_order"]) < int(producer_row["global_order"]):
            # This exact catalog template was already runnable before the write.
            # Its actor, session and selector were verified above; post-write
            # observer dependency rules do not apply to replaying that template.
            dependency_mode = "independent"
        else:
            dependency_mode, _deferred = _observer_dependency_mode(
                relation,
                producer=producer,
                observer=observer,
                requests=requests,
                view=view,
            )
        if dependency_mode != "independent" or not _is_write(producer_row):
            continue
        plan = _v1_plan(producer, observer)
        if not current_shape_supports_relation(
            plan["shape_kind"],
            relation.contract_kind,
            relation.primary_predicate.family,
            getattr(relation.primary_predicate, "operator", None),
            signed_delta=(
                relation.primary_predicate.delta
                if relation.primary_predicate.family == "P12"
                else None
            ),
        ):
            continue
        try:
            _validate_predicate_against_visible_shapes(
                relation.primary_predicate,
                producer_row,
                dict(request),
                plan,
                requests,
            )
        except CandidateAdmissionError:
            continue
        provenance = {
            "source": "observed_api_catalog",
            "operation_id": selected_id,
            "catalog_operation_sha256": str(option["catalog_operation_sha256"]),
            "request_ref": request_ref,
            "actor_id": template_payload["actor_id"],
            "session_run_id": template_payload["session_run_id"],
            "method": template_payload["method"],
            "canonical_path": template_payload["canonical_path"],
            "selector_snapshot_sha256": template_payload[
                "selector_snapshot_sha256"
            ],
            "response_body_shape_sha256": template_payload[
                "response_body_shape_sha256"
            ],
            "template_sha256": template_sha,
        }
        candidates[template_sha] = (observer, provenance)
    if not candidates:
        raise CandidateAdmissionError("observer_catalog_unavailable")
    if len(candidates) != 1:
        raise CandidateAdmissionError("observer_catalog_ambiguous")
    observer, provenance = next(iter(candidates.values()))
    base = _v1_plan(producer, observer)
    return _with_plan_id({
        key: value for key, value in base.items() if key != "plan_id"
    } | {"observer_catalog_selection": provenance})


def _construct_candidate_and_plan(
    relation: V2RelationProposal,
    *,
    requests: dict[str, dict[str, Any]],
    allowed_evidence: set[str],
    view: Any,
    visible_request_refs: set[str] | None = None,
    visible_evidence_refs: set[str] | None = None,
    observer_operation_catalog: tuple[dict[str, Any], ...] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cards = {card.card_id: card for card in view.evidence_cards}
    card = cards.get(relation.evidence_card_id)
    if card is None or relation.evidence_card_id not in view.proposal_target_card_ids:
        raise CandidateAdmissionError("evidence_card_not_scheduled")
    if any(ref not in allowed_evidence for ref in relation.evidence_refs):
        raise CandidateAdmissionError("evidence_ref_absent_from_view")
    request_scope = (
        visible_request_refs
        if visible_request_refs is not None
        else set(card.request_refs)
    )
    if any(row.request_ref not in request_scope for row in relation.role_bindings):
        raise CandidateAdmissionError("candidate_request_outside_evidence_card")
    if any(
        row.request_ref not in requests
        or requests[row.request_ref]["actor_id"] != row.actor
        for row in relation.role_bindings
    ):
        raise CandidateAdmissionError("role_binding_request_or_actor_mismatch")
    if any(row.session_ref is not None and row.session_ref != requests[row.request_ref].get("session_ref", requests[row.request_ref].get("session_run_id")) for row in relation.role_bindings):
        raise CandidateAdmissionError("role_binding_session_mismatch")

    card_evidence = visible_evidence_refs if visible_evidence_refs is not None else {
        *card.request_refs,
        *card.action_event_ids,
        *card.ui_diff_record_ids,
        *card.value_flow_ids,
        *card.dependency_edge_ids,
        *card.binding_opportunity_ids,
        *getattr(card, "negative_request_fact_ids", ()),
    }
    if any(ref not in card_evidence for ref in relation.evidence_refs):
        raise CandidateAdmissionError("evidence_ref_outside_evidence_card")
    def check_hypothesis_provenance(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("source") == "hypothesis":
                if any(ref not in card_evidence or ref not in relation.evidence_refs for ref in value["evidence_refs"]):
                    raise CandidateAdmissionError("hypothesis_evidence_outside_candidate")
                return
            for item in value.values():
                check_hypothesis_provenance(item)
        elif isinstance(value, list):
            for item in value:
                check_hypothesis_provenance(item)
    check_hypothesis_provenance(relation.primary_predicate.model_dump(mode="json"))
    for parameter in (relation.query_scope, relation.query_transform, relation.rejection, relation.joint_observation, relation.time_requirement):
        if parameter is not None:
            check_hypothesis_provenance(parameter.model_dump(mode="json"))

    by_role: dict[str, list[ProposalEndpoint]] = {}
    for binding in relation.role_bindings:
        by_role.setdefault(binding.role, []).append(
            ProposalEndpoint(request_ref=binding.request_ref, actor=binding.actor)
        )
    predicate = relation.primary_predicate
    operator = getattr(predicate, "operator", None)
    plan_candidates: list[dict[str, Any]] = []
    v3_rejection_reasons: list[str] = []
    observer_post_read_unavailable = False
    role_names = set(by_role)
    if relation.joint_observation is not None:
        plan_candidates.append(_joint_observation_plan(relation, by_role, requests))

    if relation.contract_kind == "C05" and role_names == {"before", "effect_source", "after"}:
        before, producer, after = (by_role[name][0] for name in ("before", "effect_source", "after"))
        base = _v4_plan(before, producer, after, requests)
        if base is not None and _same_workflow_observer_selector(base, requests):
            epochs = ("repeat_once", "repeat_twice") if predicate.family == "repeat_equal" else ("repeat_twice",)
            steps = []
            for epoch in epochs:
                prefix = "A" if epoch == "repeat_once" else "B"
                steps.append({"reset_epoch": epoch, "step_id": prefix + "0", "kind": "observe", "role": "before", "occurrence_index": 0})
                for occurrence in range(1, 2 if epoch == "repeat_once" else 3):
                    steps.extend([{"reset_epoch": epoch, "step_id": f"{prefix}_action{occurrence}", "kind": "request", "role": "producer", "occurrence_index": occurrence},
                                  {"reset_epoch": epoch, "step_id": f"{prefix}{occurrence}", "kind": "observe", "role": "after", "occurrence_index": occurrence}])
            plan_candidates.append(_with_plan_id({"shape_kind": "repeated_execution", "repetition_kind": predicate.family,
                "roles": base["roles"], "repeated_plan": steps,
                "required_checks": {"repeat_equal": ["projection_equal"], "repeat_rejected": ["second_rejection", "preservation"], "repeat_delta": ["first_delta", "second_delta"]}[predicate.family]}))

    if relation.contract_kind in {"inverse_restoration", "read_preservation"}:
        expected_roles = {"before", "effect_source", "after"} | ({"inverse"} if relation.contract_kind == "inverse_restoration" else set())
        if role_names == expected_roles and all(len(rows) == 1 for rows in by_role.values()):
            before, producer, after = (by_role[name][0] for name in ("before", "effect_source", "after"))
            base = _v4_plan(before, producer, after, requests, read_action=relation.contract_kind == "read_preservation")
            if base is not None and _same_workflow_observer_selector(base, requests):
                base = {key: value for key, value in base.items() if key != "plan_id"}
                base["workflow_kind"] = relation.contract_kind
                if relation.contract_kind == "inverse_restoration":
                    inverse = by_role["inverse"][0]
                    inv, prod, aft = (requests[item.request_ref] for item in (inverse, producer, after))
                    if not (_is_write(inv) and inverse.actor == producer.actor and inv["session_run_id"] == prod["session_run_id"] and prod["global_order"] < inv["global_order"] < aft["global_order"]):
                        raise CandidateAdmissionError("inverse_action_not_bound")
                    base["roles"]["inverse"] = _endpoint_payload(inverse)
                    base["workflow_plan"][2:2] = [{"step_id": "intermediate", "request_ref": before.request_ref}, {"step_id": "inverse", "request_ref": inverse.request_ref}]
                plan_candidates.append(_with_plan_id(base))

    if relation.contract_kind in {"single_state_constraint", "C14"} and role_names == {"observation"}:
        observation = by_role["observation"][0]
        if _is_read(requests[observation.request_ref]):
            plan_candidates.append(_with_plan_id({
                "shape_kind": "single_state",
                "roles": {"observation": _endpoint_payload(observation)},
                "observation_plan": [{"role": "observation", **_endpoint_payload(observation)}],
                "sampling": {
                    "instance_count": 1,
                    "input_relation_to_generation": "same_input_fresh_replay",
                    "observation_source": "new_run",
                    "generation_request_refs": [observation.request_ref],
                },
            }))

    if relation.catalog_observer_operation_id is not None:
        producer = by_role["effect_source"][0]
        plan_candidates.append(
            _catalog_observer_plan(
                relation,
                producer=producer,
                requests=requests,
                view=view,
                observer_operation_catalog=observer_operation_catalog,
            )
        )

    if role_names == {"effect_source", "reusable_observer"}:
        for producer, observer in itertools.product(
            by_role["effect_source"], by_role["reusable_observer"]
        ):
            observer_row = requests[observer.request_ref]
            if (
                _is_write(requests[producer.request_ref])
                and str(observer_row.get("method", "")).upper() == "POST"
                and not _is_read(observer_row)
            ):
                observer_post_read_unavailable = True
            if _is_write(requests[producer.request_ref]) and _is_read(
                observer_row
            ):
                dependency_mode, deferred_binding = _observer_dependency_mode(
                    relation,
                    producer=producer,
                    observer=observer,
                    requests=requests,
                    view=view,
                )
                if dependency_mode == "independent":
                    if _has_typed_v1_baseline(
                        relation,
                        producer=producer,
                        observer=observer,
                        requests=requests,
                        visible_request_refs=request_scope,
                    ):
                        plan_candidates.append(_v1_plan(producer, observer))
                    else:
                        postcondition, reason = _v4_postcondition_read_plan(
                            relation,
                            producer=producer,
                            observer=observer,
                            requests=requests,
                            view=view,
                            visible_evidence_refs=card_evidence,
                        )
                        if reason == "ambiguous":
                            raise CandidateAdmissionError(
                                "execution_plan_ambiguous"
                            )
                        if postcondition is not None:
                            plan_candidates.append(postcondition)
                elif dependency_mode == "deferred" and deferred_binding is not None:
                    plan_candidates.append(
                        _v4_create_capture_read_plan(
                            producer,
                            observer,
                            deferred_binding=deferred_binding,
                        )
                    )
                elif dependency_mode == "ambiguous":
                    raise CandidateAdmissionError("execution_plan_ambiguous")

    if role_names == {"before", "effect_source", "after"} and relation.contract_kind not in {"C05", "inverse_restoration", "read_preservation"}:
        for before, producer, after in itertools.product(
            by_role["before"], by_role["effect_source"], by_role["after"]
        ):
            if _is_write(requests[producer.request_ref]) and any(
                str(requests[endpoint.request_ref].get("method", "")).upper()
                == "POST"
                and not _is_read(requests[endpoint.request_ref])
                for endpoint in (before, after)
            ):
                observer_post_read_unavailable = True
            candidate = _v4_plan(before, producer, after, requests)
            if candidate is not None:
                plan_candidates.append(candidate)
        if "before" not in _predicate_referenced_roles(predicate) and not (relation.contract_kind == "C02" and predicate.family == "P02") and not (isinstance(predicate, PresencePredicate) and predicate.target.value_type == "object"):
            for producer, observer in itertools.product(
                by_role["effect_source"], by_role["after"]
            ):
                if _is_write(requests[producer.request_ref]) and _is_read(
                    requests[observer.request_ref]
                ):
                    if _has_typed_v1_baseline(
                        relation,
                        producer=producer,
                        observer=observer,
                        requests=requests,
                        visible_request_refs=request_scope,
                    ):
                        plan_candidates.append(_v1_plan(producer, observer))
                    else:
                        postcondition, reason = _v4_postcondition_read_plan(
                            relation,
                            producer=producer,
                            observer=observer,
                            requests=requests,
                            view=view,
                            visible_evidence_refs=card_evidence,
                        )
                        if reason == "ambiguous":
                            raise CandidateAdmissionError(
                                "execution_plan_ambiguous"
                            )
                        if postcondition is not None:
                            plan_candidates.append(postcondition)

    if role_names in ({"before", "negative_effect_source", "after"}, {"negative_effect_source", "after"}):
        for before, producer, after in itertools.product(
            by_role.get("before", by_role["after"]),
            by_role["negative_effect_source"],
            by_role["after"],
        ):
            candidate = _negative_no_effect_plan(
                relation,
                before=before,
                producer=producer,
                after=after,
                requests=requests,
                view=view,
                visible_evidence_refs=card_evidence,
            )
            if candidate is not None:
                plan_candidates.append(candidate)

    before_roles = sorted(role for role in role_names if role.startswith("actor_before:"))
    after_roles = sorted(role for role in role_names if role.startswith("actor_after:"))
    if (
        role_names == {"effect_source", *before_roles, *after_roles}
        and len(before_roles) == len(after_roles) == 1
        and before_roles[0].removeprefix("actor_before:")
        == after_roles[0].removeprefix("actor_after:")
    ):
        for producer, before, after in itertools.product(
            by_role["effect_source"],
            by_role[before_roles[0]],
            by_role[after_roles[0]],
        ):
            if _is_write(requests[producer.request_ref]) and any(
                str(requests[endpoint.request_ref].get("method", "")).upper()
                == "POST"
                and not _is_read(requests[endpoint.request_ref])
                for endpoint in (before, after)
            ):
                observer_post_read_unavailable = True
            candidate = _v7_plan(
                producer,
                before_roles[0],
                before,
                after_roles[0],
                after,
                requests,
                contract=relation.contract_kind,
            )
            if candidate is not None:
                plan_candidates.append(candidate)

    followup_roles = sorted(
        (role for role in role_names if role.startswith("followup_query:q")),
        key=lambda role: int(role.removeprefix("followup_query:q")),
    )
    if role_names == {"source_query", *followup_roles} and followup_roles:
        endpoint_lists = [by_role["source_query"], *(by_role[role] for role in followup_roles)]
        for endpoints in itertools.product(*endpoint_lists):
            candidate, reason = _v3_plan(
                endpoints[0],
                followup_roles,
                endpoints[1:],
                requests,
                relation=relation,
                view=view,
            )
            if candidate is not None:
                plan_candidates.append(candidate)
            elif reason is not None:
                v3_rejection_reasons.append(reason)

    if (
        _is_workflow_effect_predicate(relation.contract_kind, predicate)
        and not before_roles
        # P02 also has causal and no-before read plans. Only its explicit
        # before/action/after roles select this workflow-specific restriction.
        and (
            not isinstance(predicate, EqualityPredicate)
            or role_names == {"before", "effect_source", "after"}
        )
    ):
        plan_candidates = [
            plan for plan in plan_candidates
            if plan["shape_kind"] == "lifecycle_workflow"
            and plan.get("workflow_kind") in {"before_write_after", "inverse_restoration", "read_preservation"}
            and _same_workflow_observer_selector(plan, requests)
        ]

    if relation.time_requirement is not None:
        plan_candidates = [_temporal_observation_plan(relation, by_role, requests)]
    plan_candidates = [
        _attach_read_execution_evidence(plan, requests)
        for plan in plan_candidates
    ]
    plan_candidates = [
        plan
        for plan in plan_candidates
        if current_shape_supports_relation(
            plan["shape_kind"],
            relation.contract_kind,
            predicate.family,
            operator,
            transform_kind=plan.get("transform_kind"),
            signed_delta=(
                predicate.delta if predicate.family == "P12" else None
            ),
        )
    ]
    unique = {
        _canonical_sha256({key: value for key, value in plan.items() if key != "plan_id"}): plan
        for plan in plan_candidates
    }
    if not unique:
        if observer_post_read_unavailable:
            raise CandidateAdmissionError(
                "rest_post_observer_not_mechanically_read_like"
            )
        if v3_rejection_reasons and len(set(v3_rejection_reasons)) == 1:
            raise CandidateAdmissionError(v3_rejection_reasons[0])
        raise CandidateAdmissionError("execution_plan_unavailable")
    if len(unique) != 1:
        raise CandidateAdmissionError("execution_plan_ambiguous")
    plan = next(iter(unique.values()))
    single_state = plan["shape_kind"] == "single_state"
    producer = ProposalEndpoint.model_validate(plan["roles"]["producer"], strict=True) if "producer" in plan["roles"] else None
    consumer = ProposalEndpoint.model_validate(
        _plan_consumer(plan), strict=True
    )

    query_relation = plan["shape_kind"] == "metamorphic_query" or relation.contract_kind == "read_preservation"
    domain = view.request_setup_domains.get(producer.request_ref) if producer is not None else None
    if single_state or plan["shape_kind"] == "multi_resource" and producer is None:
        if relation.setup:
            raise CandidateAdmissionError("single_state_setup_is_mechanically_closed")
    elif query_relation:
        if relation.setup:
            raise CandidateAdmissionError("metamorphic_query_setup_must_be_empty")
    else:
        if not isinstance(domain, dict) or domain.get("status") != "available":
            raise CandidateAdmissionError("producer_request_ref_unavailable")
        setup_domain = list(domain.get("eligible_setup_action_ids") or [])
        positions = {ref: index for index, ref in enumerate(setup_domain)}
        if any(ref not in positions for ref in relation.setup):
            raise CandidateAdmissionError("setup_outside_producer_domain")
        if [positions[ref] for ref in relation.setup] != sorted(
            positions[ref] for ref in relation.setup
        ):
            raise CandidateAdmissionError("setup_order_mismatch")
        _require_referenced_business_setup(
            relation,
            plan=plan,
            requests=requests,
            setup_domain=set(setup_domain),
        )

    _validate_predicate_against_visible_shapes(
        predicate,
        requests[producer.request_ref] if producer is not None else requests[consumer.request_ref],
        requests[consumer.request_ref],
        plan,
        requests,
    )
    _validate_transition_fact_grounding(
        relation,
        view=view,
        visible_evidence_refs=card_evidence,
    )
    payload = V2ProposalCandidate(
        evidence_card_id=relation.evidence_card_id,
        contract_kind=relation.contract_kind,
        observation_opportunity_ref=plan["plan_id"],
        primary_predicate=predicate,
        producer=producer,
        consumer=consumer,
        setup=relation.setup,
        evidence_refs=relation.evidence_refs,
        rationale=relation.rationale,
    ).model_dump(
        mode="json",
        exclude={"schema_version", "candidate_id", "rationale"},
    )
    return payload, plan


def _is_write(request: dict[str, Any]) -> bool:
    if "_execution_kind" in request:
        return request["_execution_kind"] == "write"
    return str(request.get("method", "")).upper() in WRITE_METHODS


def _is_read(request: dict[str, Any]) -> bool:
    if "_execution_kind" in request:
        return request["_execution_kind"] == "read"
    return str(request.get("method", "")).upper() in READ_METHODS


def _endpoint_payload(endpoint: ProposalEndpoint) -> dict[str, str]:
    return endpoint.model_dump(mode="json")


def _with_plan_id(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": f"constructed-plan-{_canonical_sha256(payload)[:24]}",
        **payload,
    }


def _attach_read_execution_evidence(
    plan: dict[str, Any], requests: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    refs = {
        str(endpoint["request_ref"])
        for endpoint in plan.get("roles", {}).values()
        if isinstance(endpoint, Mapping) and endpoint.get("request_ref")
    }
    evidence = {
        ref: dict(requests[ref]["_execution_read_evidence"])
        for ref in sorted(refs)
        if requests.get(ref, {}).get("_execution_kind") == "read"
        and requests.get(ref, {}).get("_execution_read_evidence")
    }
    if not evidence:
        return plan
    payload = {key: value for key, value in plan.items() if key != "plan_id"}
    payload["read_execution_evidence"] = evidence
    return _with_plan_id(payload)


def _v1_plan(
    producer: ProposalEndpoint, observer: ProposalEndpoint
) -> dict[str, Any]:
    producer_payload = _endpoint_payload(producer)
    observer_payload = _endpoint_payload(observer)
    return _with_plan_id({
        "shape_kind": "causal_two_arm",
        "roles": {
            "producer": producer_payload,
            "before": observer_payload,
            "after": observer_payload,
            "control_before": observer_payload,
            "control_after": observer_payload,
        },
    })


def _scalar_c02_p02_refs(
    relation: V2RelationProposal,
) -> tuple[ValueRef, ValueRef] | None:
    predicate = relation.primary_predicate
    if not (
        relation.contract_kind == "C02"
        and isinstance(predicate, EqualityPredicate)
        and isinstance(predicate.right, RoleOperand)
        and isinstance(predicate.left, ValueRef)
        and predicate.left.role == "after"
        and predicate.right.ref.role
        in {"producer_request", "producer_response"}
        and predicate.left.value_type
        not in {"array", "object", "null"}
        and predicate.left.value_type == predicate.right.ref.value_type
    ):
        return None
    return predicate.left, predicate.right.ref


def _has_typed_v1_baseline(
    relation: V2RelationProposal,
    *,
    producer: ProposalEndpoint,
    observer: ProposalEndpoint,
    requests: Mapping[str, Mapping[str, Any]],
    visible_request_refs: set[str],
) -> bool:
    """Require an observed, typed pre-write target before choosing V1.

    Re-executing a later authenticated read before login is not an observed
    baseline.  A usable V1 target is instead proven by an earlier visible read
    of the same operation, actor and recording session whose response exposes
    the exact predicate path and type.
    """

    predicate = relation.primary_predicate
    if not (
        relation.contract_kind == "C02"
        and isinstance(predicate, EqualityPredicate)
    ):
        return True
    left = predicate.left
    if isinstance(left, LocatedMemberFieldRef):
        return True
    if isinstance(left, ValueRef) and "[*]" in left.path:
        return True
    if not (
        isinstance(left, ValueRef)
        and left.role == "after"
        and left.value_type not in {"array", "object", "null"}
    ):
        return False
    producer_row = requests[producer.request_ref]
    observer_row = requests[observer.request_ref]
    observer_session = str(observer_row.get("session_run_id") or "")
    if not observer_session:
        return False
    for request_ref in visible_request_refs:
        row = requests.get(request_ref)
        if row is None or not _is_read(dict(row)):
            continue
        if (
            str(row.get("actor_id")) == observer.actor
            and str(row.get("session_run_id") or "") == observer_session
            and str(row.get("operation_id"))
            == str(observer_row.get("operation_id"))
            and int(row["global_order"]) < int(producer_row["global_order"])
            and _shape_path_types(dict(row["response_body_shape"])).get(
                left.path
            )
            == left.value_type
        ):
            return True
    return False


def _v4_postcondition_read_plan(
    relation: V2RelationProposal,
    *,
    producer: ProposalEndpoint,
    observer: ProposalEndpoint,
    requests: Mapping[str, Mapping[str, Any]],
    view: Any,
    visible_evidence_refs: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Construct the no-before C02/P02 workflow from one direct witness.

    This is deliberately observational.  The witness closes only the recorded
    producer-to-read workflow; it does not manufacture a control arm or a
    causal claim.
    """

    refs = _scalar_c02_p02_refs(relation)
    if refs is None:
        return None, None
    left, right = refs
    producer_row = requests[producer.request_ref]
    observer_row = requests[observer.request_ref]
    producer_session = str(producer_row.get("session_run_id") or "")
    observer_session = str(observer_row.get("session_run_id") or "")
    source_shape_key = (
        "request_body_shape"
        if right.role == "producer_request"
        else "response_body_shape"
    )
    if not (
        _is_write(dict(producer_row))
        and _is_read(dict(observer_row))
        and producer.actor == observer.actor
        and producer_session
        and producer_session == observer_session
        and int(producer_row["global_order"]) < int(observer_row["global_order"])
        and _shape_path_types(dict(producer_row[source_shape_key])).get(
            right.path
        )
        == right.value_type
        and _shape_path_types(dict(observer_row["response_body_shape"])).get(
            left.path
        )
        == left.value_type
    ):
        return None, None

    cited = set(relation.evidence_refs)
    witnesses = [
        flow
        for flow in view.observed_value_flows
        if str(flow.get("flow_id")) in visible_evidence_refs
        and str(flow.get("producer_request_ref")) == producer.request_ref
        and str(flow.get("consumer_request_ref")) == observer.request_ref
        and str(flow.get("producer_actor_id")) == producer.actor
        and str(flow.get("consumer_actor_id")) == observer.actor
        and str(flow.get("producer_session_run_id")) == producer_session
        and str(flow.get("consumer_session_run_id")) == observer_session
        and str(flow.get("producer_operation_id"))
        == str(producer_row.get("operation_id"))
        and str(flow.get("consumer_operation_id"))
        == str(observer_row.get("operation_id"))
    ]
    if len(witnesses) != 1:
        return None, "ambiguous" if witnesses else "unavailable"
    witness = witnesses[0]
    if str(witness.get("flow_id")) not in cited:
        return None, "unavailable"
    roles = {
        "producer": _endpoint_payload(producer),
        "after": _endpoint_payload(observer),
    }
    return _with_plan_id({
        "shape_kind": "lifecycle_workflow",
        "workflow_kind": "postcondition_read",
        "roles": roles,
        "postcondition_flow": {
            "producer_request_ref": producer.request_ref,
            "after_request_ref": observer.request_ref,
            "source_role": right.role,
            "source_path": right.path,
            "target_role": left.role,
            "target_path": left.path,
            "value_type": left.value_type,
            "witness_flow_id": str(witness["flow_id"]),
        },
        "workflow_plan": [
            {"step_id": "producer", "request_ref": producer.request_ref},
            {"step_id": "settle", "source": "profile_settle_policy"},
            {
                "step_id": "after",
                "request_ref": observer.request_ref,
                "source": "recorded_checkpoint",
            },
        ],
    }), None


def _v4_plan(
    before: ProposalEndpoint,
    producer: ProposalEndpoint,
    after: ProposalEndpoint,
    requests: dict[str, dict[str, Any]],
    *, read_action: bool = False,
) -> dict[str, Any] | None:
    before_row, producer_row, after_row = (
        requests[before.request_ref],
        requests[producer.request_ref],
        requests[after.request_ref],
    )
    if not (
        _is_read(before_row)
        and (_is_read(producer_row) if read_action else _is_write(producer_row))
        and (not read_action or producer_row["operation_id"] != before_row["operation_id"])
        and _is_read(after_row)
        and before.actor == producer.actor == after.actor
        and len({
            str(before_row["session_run_id"]),
            str(producer_row["session_run_id"]),
            str(after_row["session_run_id"]),
        }) == 1
        and before.request_ref != after.request_ref
        and before_row["operation_id"] == after_row["operation_id"]
        and int(before_row["global_order"])
        < int(producer_row["global_order"])
        < int(after_row["global_order"])
    ):
        return None
    roles = {
        "producer": _endpoint_payload(producer),
        "before": _endpoint_payload(before),
        "after": _endpoint_payload(after),
    }
    return _with_plan_id({
        "shape_kind": "lifecycle_workflow",
        "workflow_kind": "before_write_after",
        "roles": roles,
        "workflow_plan": [
            {"step_id": "before", "request_ref": before.request_ref, "source": "recorded_checkpoint"},
            {"step_id": "producer", "request_ref": producer.request_ref},
            {"step_id": "settle", "source": "profile_settle_policy"},
            {"step_id": "after", "request_ref": after.request_ref, "source": "recorded_checkpoint"},
        ],
    })


def _is_workflow_effect_predicate(contract: str, predicate: PrimaryPredicate) -> bool:
    return (
        contract in {"C04", "inverse_restoration", "read_preservation"} and isinstance(predicate, StateEquivalencePredicate)
        or contract == "C02" and isinstance(predicate, EqualityPredicate)
        or contract == "C02" and isinstance(predicate, NumericDirectionPredicate)
        or contract == "C02" and isinstance(predicate, NumericDeltaPredicate)
        and isinstance(predicate.delta, (NumericHypothesisOperand, NumericRequestOperand))
        or contract == "C02" and isinstance(predicate, StateTransitionPredicate)
        and not isinstance(predicate.from_value, TransitionFactConstant)
    )


def _same_workflow_observer_selector(
    plan: Mapping[str, Any], requests: Mapping[str, Mapping[str, Any]],
) -> bool:
    before = requests[plan["roles"]["before"]["request_ref"]]
    after = requests[plan["roles"]["after"]["request_ref"]]
    return (
        before.get("canonical_path") == after.get("canonical_path")
        and _selector_snapshot_sha256(before) == _selector_snapshot_sha256(after)
    )


def _negative_no_effect_plan(
    relation: V2RelationProposal,
    *,
    before: ProposalEndpoint,
    producer: ProposalEndpoint,
    after: ProposalEndpoint,
    requests: Mapping[str, Mapping[str, Any]],
    view: Any,
    visible_evidence_refs: set[str],
) -> dict[str, Any] | None:
    """Derive V6 only from one exact frozen M9 negative-request fact."""

    predicate = relation.primary_predicate
    if relation.contract_kind not in {"C06", "C12"} or not isinstance(predicate, (StateEquivalencePredicate, EqualityPredicate)):
        return None
    if relation.negative_context is not None or relation.contract_kind == "C12" or isinstance(predicate, EqualityPredicate):
        negative_kind = "rejection" if isinstance(predicate, EqualityPredicate) else "rejection_preservation"
        if not _is_write(dict(requests[producer.request_ref])):
            return None
        if negative_kind == "rejection_preservation" and not (_is_read(dict(requests[before.request_ref])) and _is_read(dict(requests[after.request_ref])) and before.actor == after.actor):
            return None
        topology = None
        if relation.contract_kind == "C12":
            topology = _verified_role_topology(producer, after, requests)
            if topology is None or topology["principal_relation"] != "different":
                return None
        elif producer.actor != after.actor:
            return None
        detector = relation.rejection or (predicate if isinstance(predicate, EqualityPredicate) else None)
        plan = {"shape_kind": "negative_no_effect", "negative_kind": negative_kind,
                "roles": {"producer": _endpoint_payload(producer), "before": _endpoint_payload(before), "after": _endpoint_payload(after)},
                "rejection_detector": {"kind": "predicate", "predicate": detector.model_dump(mode="json")} if detector is not None else {"kind": "http_status_class", "expected_class": "client_error"},
                "session_boundary": {"kind": "recorded_logout_and_runtime_auth_absence" if relation.negative_context == "auth_absent" else "recorded_auth_preserved", "negative_request_ref": producer.request_ref},
                "projection": predicate.model_dump(mode="json") if negative_kind == "rejection_preservation" else None,
                "negative_plan": ([{"step_id": "before", "request_ref": before.request_ref}] if negative_kind == "rejection_preservation" else []) + [{"step_id": "negative_producer", "request_ref": producer.request_ref}, {"step_id": "rejection_gate"}] + ([{"step_id": "settle", "source": "profile_settle_policy"}, {"step_id": "after", "request_ref": after.request_ref}] if negative_kind == "rejection_preservation" else [])}
        if topology is not None:
            plan["identity_topology"] = topology
        return _with_plan_id(plan)
    matching = [
        fact
        for fact in getattr(view, "negative_request_facts", ())
        if fact.fact_id in visible_evidence_refs
        and fact.fact_id in relation.evidence_refs
        and fact.projection.projection_ref == predicate.projection_ref
        and fact.negative_request_ref == producer.request_ref
        and fact.projection.before_request_ref == before.request_ref
        and fact.projection.after_request_ref == after.request_ref
        and fact.actor_id == before.actor == producer.actor == after.actor
        and fact.projection.path == predicate.left.path == predicate.right.path
        and fact.projection.value_type
        == predicate.left.value_type
        == predicate.right.value_type
    ]
    if len(matching) != 1:
        return None
    fact = matching[0]
    catalog_observer = fact.projection.before_request_ref == fact.projection.after_request_ref
    setup_action = requests[fact.setup_request_ref].get("action_event_id")
    if not isinstance(setup_action, str) or setup_action not in relation.setup:
        return None
    roles = {
        "producer": _endpoint_payload(producer),
        "before": _endpoint_payload(before),
        "after": _endpoint_payload(after),
    }
    return _with_plan_id({
        "shape_kind": "negative_no_effect",
        "negative_kind": "rejection_preservation",
        "roles": roles,
        "negative_request_fact_ref": fact.fact_id,
        "projection": fact.projection.model_dump(mode="json"),
        "rejection_detector": fact.rejection_detector,
        "session_boundary": {
            "kind": (
                "recorded_logout_and_runtime_auth_absence"
                if fact.context_mode == "auth_absent"
                else "recorded_auth_preserved"
            ),
            "event_id": fact.session_boundary_event_id,
            "setup_request_ref": fact.setup_request_ref,
            "negative_request_ref": fact.negative_request_ref,
        },
        **(
            {
                "catalog_observer_template": {
                    "source": "observed_api_catalog",
                    "request_ref": before.request_ref,
                    "operation_id": requests[before.request_ref]["operation_id"],
                    "actor_id": before.actor,
                    "session_run_id": requests[before.request_ref]["session_run_id"],
                    "method": requests[before.request_ref]["method"],
                    "canonical_path": requests[before.request_ref]["canonical_path"],
                    "response_shape_sha256": _canonical_sha256(
                        dict(requests[before.request_ref].get("response_body_shape") or {})
                    ),
                    "projection_path": fact.projection.path,
                }
            }
            if catalog_observer
            else {}
        ),
        "negative_plan": [
            {
                "step_id": "before",
                "request_ref": before.request_ref,
                "source": "recorded_checkpoint",
            },
            {"step_id": "negative_producer", "request_ref": producer.request_ref},
            {
                "step_id": "rejection_gate",
                "detector": "client_error",
            },
            {"step_id": "settle", "source": "profile_settle_policy"},
            {
                "step_id": "after",
                "request_ref": after.request_ref,
                "source": "recorded_checkpoint",
            },
        ],
    })


def _observer_dependency_mode(
    relation: V2RelationProposal,
    *,
    producer: ProposalEndpoint,
    observer: ProposalEndpoint,
    requests: Mapping[str, Mapping[str, Any]],
    view: Any,
) -> tuple[str, dict[str, Any] | None]:
    """Distinguish an independently runnable observer from a deferred one.

    M10 uses only recorded flow direction and order here.  The exact producer
    response identity path and physical request target remain fail-closed M11b
    materialization facts.
    """

    if str(requests[producer.request_ref].get("method", "")).upper() != "POST":
        return "independent", None
    producer_order = int(requests[producer.request_ref]["global_order"])
    observer_order = int(requests[observer.request_ref]["global_order"])
    producer_session = requests[producer.request_ref].get("session_run_id")
    observer_session = requests[observer.request_ref].get("session_run_id")
    if (
        producer_order >= observer_order
        or not isinstance(producer_session, str)
        or not producer_session
        or not isinstance(observer_session, str)
        or not observer_session
        or (
            producer.actor == observer.actor
            and producer_session != observer_session
        )
        or (
            producer.actor != observer.actor
            and producer_session == observer_session
        )
    ):
        return "ambiguous", None
    cited = set(relation.evidence_refs)
    by_target: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for flow in view.observed_value_flows:
        if (
            str(flow.get("consumer_request_ref")) != observer.request_ref
            or str(flow.get("to_location")) not in {"path", "query", "body"}
            or str(flow.get("producer_request_ref")) not in requests
        ):
            continue
        source_order = int(
            requests[str(flow["producer_request_ref"])]["global_order"]
        )
        if source_order >= observer_order:
            continue
        by_target.setdefault(
            (str(flow["to_location"]), str(flow["to_field"])), []
        ).append(flow)
    post_only: list[tuple[tuple[str, str], list[Mapping[str, Any]]]] = []
    for target, rows in by_target.items():
        prior = [
            row
            for row in rows
            if int(requests[str(row["producer_request_ref"])]["global_order"])
            < producer_order
        ]
        post = [
            row
            for row in rows
            if int(requests[str(row["producer_request_ref"])]["global_order"])
            >= producer_order
        ]
        if prior and post:
            return "ambiguous", None
        if post:
            post_only.append((target, post))
    if not post_only:
        return "independent", None
    if len(post_only) != 1:
        return "ambiguous", None
    (location, target_field), rows = post_only[0]
    cited_witnesses = sorted(
        str(row["flow_id"]) for row in rows if str(row["flow_id"]) in cited
    )
    if not cited_witnesses:
        return "ambiguous", None
    if not (
        relation.contract_kind == "C02"
        and relation.primary_predicate.family == "P02"
    ):
        # The observer is demonstrably unavailable before this create, but the
        # current registered create/capture/read workflow only carries C02/P02.
        # Do not misclassify the point read as an independent V1 control arm.
        return "dependent_unsupported", None
    return "deferred", {
        "source_request_ref": producer.request_ref,
        "source_role": "producer_response",
        "source_identity_rule": "unique_recorded_creator_response_identity",
        "target_request_ref": observer.request_ref,
        "target_actor": observer.actor,
        "target_location": location,
        "target_field": target_field,
        "witness_flow_ids": cited_witnesses,
    }


def _require_referenced_business_setup(
    relation: V2RelationProposal,
    *,
    plan: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
    setup_domain: set[str],
) -> None:
    """Reject an omitted cited write that establishes an actor observation.

    This is deliberately narrower than technical dependency closure.  It only
    applies to an actor-matrix before/after pair and only to a request that the
    proposal itself cites, that is mechanically anchored to a state-changing
    UI action, and that lies inside the recorded observer interval.  M11 may
    close technical resources, but it must not invent this business action.
    """

    if plan.get("shape_kind") != "actor_matrix":
        return
    roles = plan.get("roles") or {}
    before_roles = [key for key in roles if str(key).startswith("actor_before:")]
    after_roles = [key for key in roles if str(key).startswith("actor_after:")]
    if len(before_roles) != 1 or len(after_roles) != 1:
        return
    before_role = next(iter(before_roles))
    after_role = next(iter(after_roles))
    before = requests.get(str(roles[before_role].get("request_ref")))
    after = requests.get(str(roles[after_role].get("request_ref")))
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return
    if (
        before.get("actor_id") != after.get("actor_id")
        or before.get("session_run_id") != after.get("session_run_id")
    ):
        return
    lower = int(before["global_order"])
    upper = int(after["global_order"])
    selected = set(relation.setup)
    producer_ref = str((plan.get("roles") or {}).get("producer", {}).get("request_ref") or "")
    for ref in relation.evidence_refs:
        request = requests.get(str(ref))
        if (
            not isinstance(request, Mapping)
            or str(ref) == producer_ref
            or not _is_write(dict(request))
            or request.get("actor_id") != before.get("actor_id")
            or request.get("session_run_id") != before.get("session_run_id")
            or not lower < int(request["global_order"]) < upper
            or request.get("association_status") != "anchored"
            or "state_change_like" not in set(request.get("weak_roles") or ())
        ):
            continue
        action_id = request.get("action_event_id")
        if (
            isinstance(action_id, str)
            and action_id in setup_domain
            and action_id not in selected
        ):
            raise CandidateAdmissionError("referenced_business_setup_incomplete")


def _v4_create_capture_read_plan(
    producer: ProposalEndpoint,
    observer: ProposalEndpoint,
    *,
    deferred_binding: Mapping[str, Any],
) -> dict[str, Any]:
    roles = {
        "producer": _endpoint_payload(producer),
        "after": _endpoint_payload(observer),
    }
    return _with_plan_id({
        "shape_kind": "lifecycle_workflow",
        "workflow_kind": "create_capture_read",
        "roles": roles,
        "deferred_fresh_binding": dict(deferred_binding),
        "workflow_plan": [
            {"step_id": "producer", "request_ref": producer.request_ref},
            {
                "step_id": "capture_fresh_identity",
                "source_role": "producer_response",
            },
            {"step_id": "settle", "source": "profile_settle_policy"},
            {"step_id": "after", "request_ref": observer.request_ref},
        ],
    })


def _v7_plan(
    producer: ProposalEndpoint,
    before_role: str,
    before: ProposalEndpoint,
    after_role: str,
    after: ProposalEndpoint,
    requests: dict[str, dict[str, Any]],
    *, contract: str,
) -> dict[str, Any] | None:
    producer_row, before_row, after_row = (
        requests[producer.request_ref],
        requests[before.request_ref],
        requests[after.request_ref],
    )
    if not (
        _is_write(producer_row)
        and _is_read(before_row)
        and _is_read(after_row)
        and before.actor == after.actor
        and before_row["session_run_id"] == after_row["session_run_id"]
        and before.request_ref != after.request_ref
        and before_row["operation_id"] == after_row["operation_id"]
        and int(before_row["global_order"])
        < int(producer_row["global_order"])
        < int(after_row["global_order"])
    ):
        return None
    topology = _verified_role_topology(producer, after, requests)
    if topology is None:
        return None
    if contract == "self_exclusion" and topology["principal_relation"] != "same":
        return None
    if contract in {"C11", "C12"} and topology["principal_relation"] != "different":
        return None
    if contract == "C04" and (topology["principal_relation"] != "same" or topology["session_relation"] != "different"):
        return None
    roles = {
        "producer": _endpoint_payload(producer),
        before_role: _endpoint_payload(before),
        after_role: _endpoint_payload(after),
    }
    return _with_plan_id({
        "shape_kind": "actor_matrix",
        "identity_topology": topology,
        "roles": roles,
        "actor_plan": [
            {"step_id": "before", "role": before_role},
            {"step_id": "producer", "role": "producer"},
            {"step_id": "settle", "source": "profile_settle_policy"},
            {"step_id": "after", "role": after_role},
        ],
    })


def _verified_role_topology(producer: ProposalEndpoint, observer: ProposalEndpoint, requests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    left, right = requests[producer.request_ref], requests[observer.request_ref]
    left_session = left.get("session_ref", left.get("session_run_id"))
    right_session = right.get("session_ref", right.get("session_run_id"))
    if producer.actor == observer.actor and left_session == right_session:
        return {"left_actor_id": producer.actor, "right_actor_id": observer.actor,
                "left_session_ref": left_session, "right_session_ref": right_session,
                "principal_relation": "same", "session_relation": "same", "verification_source": "same_authenticated_session", "verified": True}
    facts = [row for row in left.get("identity_relations", []) if row.get("verified") is True and row.get("verification_source") == "authenticated_probe"
             and {row.get("left_actor_id"), row.get("right_actor_id")} == {producer.actor, observer.actor}]
    if not facts or any(row != facts[0] for row in facts):
        return None
    fact = copy.deepcopy(facts[0])
    if fact["left_actor_id"] != producer.actor:
        for suffix in ("actor_id", "session_ref"):
            fact["left_" + suffix], fact["right_" + suffix] = fact["right_" + suffix], fact["left_" + suffix]
    if (fact["left_session_ref"], fact["right_session_ref"]) != (left_session, right_session):
        return None
    return fact


_NON_FILTER_QUERY_KEYS = frozenset({
    "after",
    "before",
    "cursor",
    "direction",
    "limit",
    "offset",
    "order",
    "orderby",
    "page",
    "pagesize",
    "perpage",
    "sort",
    "sortby",
})


def _normalized_query_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _query_is_filter_refinement(
    source_query: Mapping[str, Any], followup_query: Mapping[str, Any]
) -> bool:
    added = set(followup_query) - set(source_query)
    return bool(added) and set(source_query) < set(followup_query) and all(
        followup_query[key] == value for key, value in source_query.items()
    ) and all(
        _normalized_query_key(key) not in _NON_FILTER_QUERY_KEYS for key in added
    )


def _typed_selector_value_transform(
    source_query: Mapping[str, Any],
    followup_query: Mapping[str, Any],
    *,
    source_row: Mapping[str, Any],
    followup_row: Mapping[str, Any],
    relation: V2RelationProposal,
    view: Any,
) -> tuple[str | None, dict[str, str] | None]:
    if set(source_query) != set(followup_query):
        return None, None
    changed = [
        key for key in source_query if source_query[key] != followup_query[key]
    ]
    if len(changed) != 1:
        return None, None
    key = changed[0]
    if _normalized_query_key(key) in _NON_FILTER_QUERY_KEYS:
        return None, None
    source_value = source_query[key]
    followup_value = followup_query[key]
    if not all(isinstance(value, str) and value for value in (source_value, followup_value)):
        return None, None
    if any(
        value.startswith(("<", "[REDACTED:"))
        for value in (source_value, followup_value)
    ):
        return None, None
    action_ref = source_row.get("action_event_id")
    if (
        not action_ref
        or action_ref != followup_row.get("action_event_id")
        or action_ref not in set(relation.evidence_refs)
    ):
        return None, None
    actions = {
        str(row.get("event_id")): row
        for row in view.ui_actions
        if isinstance(row, Mapping) and row.get("event_id")
    }
    action = actions.get(str(action_ref))
    if not isinstance(action, Mapping) or action.get("action_type") not in {
        "input", "fill", "type"
    }:
        return None, None
    if followup_value.startswith(source_value) and len(followup_value) > len(source_value):
        transform = "filter_refinement"
    elif source_value.startswith(followup_value) and len(source_value) > len(followup_value):
        transform = "filter_expansion"
    else:
        return None, None
    return transform, {
        "kind": "typed_literal_prefix",
        "action_ref": str(action_ref),
        "selector_key": str(key),
    }


def _post_selector_comparison_reason(
    source_row: Mapping[str, Any],
    followup_row: Mapping[str, Any],
) -> str | None:
    evidence = []
    for row in (source_row, followup_row):
        value = row.get("_execution_read_evidence")
        if not isinstance(value, Mapping) or value.get("kind") != "recorded_post_query":
            return None
        selector_hash = value.get("selector_body_sha256")
        if not isinstance(selector_hash, str):
            return None
        evidence.append(selector_hash)
    return (
        "identical_queries_claimed_as_filter_refinement"
        if evidence[0] == evidence[1]
        else "query_selector_value_direction_unproven"
    )


def _cross_operation_collection_shapes_are_compatible(
    source_row: Mapping[str, Any],
    followup_row: Mapping[str, Any],
    predicate: CollectionRelationPredicate,
    *,
    expected_operator: str = "subset",
) -> tuple[bool, str | None, dict[str, Any]]:
    if not (
        predicate.operator == expected_operator
        and predicate.left.role.startswith("followup_query:q")
        and predicate.right.role == "source_query"
        and predicate.left.value_type == predicate.right.value_type == "array"
    ):
        return False, "query_contract_transform_mismatch", {}

    def shape_rows(row: Mapping[str, Any]) -> list[tuple[str, str]]:
        return [
            (str(item.get("path", "")), str(item.get("type", "")))
            for item in row.get("response_body_shape", {}).get("shape_rows", ())
            if isinstance(item, dict)
        ]

    source_rows = shape_rows(source_row)
    followup_rows = shape_rows(followup_row)
    source_collection = predicate.right.path
    followup_collection = predicate.left.path
    if (
        source_rows.count((source_collection, "array")) != 1
        or followup_rows.count((followup_collection, "array")) != 1
    ):
        return False, "collection_path_not_unique", {}

    source_member_prefix = f"{source_collection}[*]"
    followup_member_prefix = f"{followup_collection}[*]"
    source_member_shape = {
        (path.removeprefix(source_member_prefix), value_type)
        for path, value_type in source_rows
        if path == source_member_prefix or path.startswith(f"{source_member_prefix}.")
    }
    followup_member_shape = {
        (path.removeprefix(followup_member_prefix), value_type)
        for path, value_type in followup_rows
        if path == followup_member_prefix or path.startswith(f"{followup_member_prefix}.")
    }
    shared_paths = {path for path, _ in source_member_shape} & {
        path for path, _ in followup_member_shape
    }
    if not shared_paths or any(
        {value_type for path, value_type in source_member_shape if path == shared}
        != {value_type for path, value_type in followup_member_shape if path == shared}
        for shared in shared_paths
    ):
        return False, "collection_member_shape_incompatible", {}

    identity_rows: list[dict[str, str]] = []
    for identity_path in (predicate.identity.paths if predicate.identity is not None else predicate.projection):
        source_path = _identity_path(source_member_prefix, identity_path)
        followup_path = _identity_path(followup_member_prefix, identity_path)
        source_types = [
            value_type for path, value_type in source_rows if path == source_path
        ]
        followup_types = [
            value_type for path, value_type in followup_rows if path == followup_path
        ]
        if len(source_types) != 1 or len(followup_types) != 1:
            return False, "collection_identity_path_not_unique", {}
        if source_types[0] != followup_types[0]:
            return False, "collection_identity_type_incompatible", {}
        identity_rows.append({
            "identity_path": identity_path,
            "value_type": source_types[0],
        })
    return True, None, {
        "source_collection_path": source_collection,
        "followup_collection_path": followup_collection,
        "identity_paths": identity_rows,
    }


def _pagination_collection_shapes_are_compatible(
    rows: list[Mapping[str, Any]],
    followup_roles: list[str],
    predicate: PrimaryPredicate,
) -> tuple[bool, str | None]:
    def shape_rows(row: Mapping[str, Any]) -> list[tuple[str, str]]:
        return [
            (str(item.get("path", "")), str(item.get("type", "")))
            for item in row.get("response_body_shape", {}).get("shape_rows", ())
            if isinstance(item, Mapping)
        ]

    if isinstance(predicate, CollectionUniquenessPredicate):
        if predicate.collection.role != "followup_query":
            return False, "numbered_query_roles_incomplete"
        paths = [predicate.collection.path] * len(rows)
        identity_paths = predicate.identity.paths
    elif isinstance(predicate, PartitionRelationPredicate):
        operands = [*predicate.partitions, *([predicate.expected_remainder] if predicate.expected_remainder is not None else [])]
        if predicate.source.role != "source_query" or {
            item.role for item in operands
        } != set(followup_roles):
            return False, "numbered_query_roles_incomplete"
        by_role = {item.role: item.path for item in operands}
        paths = [predicate.source.path, *(by_role[role] for role in followup_roles)]
        identity_paths = predicate.identity.paths
    else:
        return False, "query_contract_transform_mismatch"

    value_types: dict[str, set[str]] = {path: set() for path in identity_paths}
    for row, collection_path in zip(rows, paths, strict=True):
        shapes = shape_rows(row)
        if shapes.count((collection_path, "array")) != 1:
            return False, "collection_path_not_unique"
        member_prefix = f"{collection_path}[*]"
        for identity_path in identity_paths:
            full_path = _identity_path(member_prefix, identity_path)
            types = [value_type for path, value_type in shapes if path == full_path]
            if len(types) != 1:
                return False, "collection_identity_path_not_unique"
            value_types[identity_path].add(types[0])
    if any(len(types) != 1 for types in value_types.values()):
        return False, "collection_identity_type_incompatible"
    return True, None


def _cross_operation_collection_witnesses(
    source_row: Mapping[str, Any],
    followup_row: Mapping[str, Any],
    *,
    relation: V2RelationProposal,
    view: Any,
) -> list[dict[str, str]]:
    source_ref = str(source_row["request_ref"])
    followup_ref = str(followup_row["request_ref"])
    source_operation = str(source_row["operation_id"])
    followup_operation = str(followup_row["operation_id"])
    evidence_refs = set(relation.evidence_refs)
    witnesses: list[dict[str, str]] = []
    source_group = source_row.get("request_group_id")
    if source_group and source_group == followup_row.get("request_group_id"):
        witnesses.append({"kind": "request_group", "ref": str(source_group)})
    source_action = source_row.get("action_event_id")
    if (
        source_action
        and source_action in evidence_refs
        and source_action == followup_row.get("action_event_id")
    ):
        witnesses.append({"kind": "ui_action", "ref": str(source_action)})
    for flow in view.observed_value_flows:
        if not isinstance(flow, dict):
            continue
        if (
            flow.get("flow_id") in evidence_refs
            and flow.get("producer_request_ref") == source_ref
            and flow.get("consumer_request_ref") == followup_ref
        ):
            witnesses.append({"kind": "value_flow", "ref": str(flow["flow_id"])})
    for edge in view.dependency_edges:
        if not isinstance(edge, dict):
            continue
        if (
            edge.get("edge_id") in evidence_refs
            and edge.get("producer_operation_id") == source_operation
            and edge.get("consumer_operation_id") == followup_operation
        ):
            witnesses.append({"kind": "dependency", "ref": str(edge["edge_id"])})
    ui_diff = view.evidence_channel_summaries.get("ui_diff", {}).get(
        "semantic_projection", {}
    )
    for row in ui_diff.get("rows", ()):
        if not isinstance(row, dict) or row.get("record_id") not in evidence_refs:
            continue
        preceding = set(row.get("preceding_request_refs", ()))
        following = set(row.get("following_request_refs", ()))
        if source_ref in preceding and followup_ref in following:
            witnesses.append({"kind": "ui_diff", "ref": str(row["record_id"])})
    return sorted(witnesses, key=lambda row: (row["kind"], row["ref"]))


def _query_selector_values(request: Mapping[str, Any], location: str) -> dict[str, Any] | None:
    """Read only exact recorded selector evidence; no normalized aliases."""
    evidence = request.get("parameter_evidence")
    if location == "query":
        if isinstance(evidence, Mapping) and any(row.get("literal_available") is not True for row in evidence.get("parameters", ()) if row.get("location") == "query"):
            return None
        return copy.deepcopy(request.get("query") or {})
    if not isinstance(evidence, Mapping) or any(row.get("location") == "body" for row in evidence.get("unsupported", ())):
        return None
    values = {}
    containers = {}
    for row in evidence.get("parameters", ()):
        if row.get("location") != "body":
            continue
        if row.get("literal_available") is not True:
            return None
        path = row.get("path")
        if not isinstance(path, str) or not re.fullmatch(r"\$(?:\.[^.*\[\]]+)*", path) or path in values:
            return None
        kind = row.get("value_type")
        if kind in {"object", "array"}:
            count = row.get("property_count" if kind == "object" else "length")
            if type(count) is not int or count < 0:
                return None
            containers[path] = (kind, count)
            values[path] = {"value_type": kind}
            continue
        if "value" not in row and "lexical" not in row:
            return None
        value = row.get("value")
        if "lexical" in row:
            number = Decimal(row["lexical"])
            numerator, denominator = number.as_integer_ratio()
            value = {"numerator": numerator, "denominator": denominator}
        values[path] = {"value_type": kind, "value": value}
    if not values:
        return {} if request.get("request_body_shape", {}).get("body_kind") == "absent" else None
    if "$" not in values:
        return None
    children: dict[str, set[str]] = {path: set() for path in containers}
    for path in values:
        if path == "$":
            continue
        parent, key = path.rsplit(".", 1)
        if parent not in containers:
            return None
        children[parent].add(key)
    for path, (kind, count) in containers.items():
        if len(children[path]) != count or kind == "array" and children[path] != {str(index) for index in range(count)}:
            return None
    # Every real container and indexed child is retained; counts above prove
    # completeness. Wildcard shape rows cannot reconstruct missing members.
    return values


def _v3_plan(
    source: ProposalEndpoint,
    followup_roles: list[str],
    followups: tuple[ProposalEndpoint, ...],
    requests: dict[str, dict[str, Any]],
    *,
    relation: V2RelationProposal,
    view: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    endpoints = (source, *followups)
    rows = [requests[item.request_ref] for item in endpoints]
    orders = [int(row["global_order"]) for row in rows]
    same_operation = len({row["operation_id"] for row in rows}) == 1
    expected_followup_roles = [
        f"followup_query:q{index}" for index in range(1, len(followup_roles) + 1)
    ]
    if followup_roles != expected_followup_roles:
        return None, "numbered_query_roles_incomplete"
    if any(
        str(row.get("method", "")).upper() == "POST" and not _is_read(row)
        for row in rows
    ):
        return None, "rest_post_read_like_request_not_mechanically_available"
    if not (
        all(_is_read(row) for row in rows)
        and len({item.actor for item in endpoints}) == 1
        and all(left < right for left, right in zip(orders, orders[1:]))
        and len({item.request_ref for item in endpoints}) == len(endpoints)
    ):
        return None, (
            "cross_operation_query_actor_or_order_mismatch"
            if not same_operation
            else "query_actor_or_order_mismatch"
        )
    if len({str(row.get("session_run_id", "")) for row in rows}) != 1:
        return None, (
            "cross_operation_query_session_mismatch"
            if not same_operation
            else "query_session_mismatch"
        )
    if any(
        orders[0] < int(row["global_order"]) < orders[-1] and _is_write(row)
        for row in requests.values()
    ):
        return None, "query_snapshot_contaminated_by_write"
    queries = [row.get("query") or {} for row in rows]
    source_query, followup_queries = queries[0], queries[1:]
    transform: str | None = None
    selector_transform_witness: dict[str, str] | None = None
    if relation.query_transform is not None:
        declaration = relation.query_transform
        transform = declaration.kind
        selectors = [_query_selector_values(row, declaration.location) for row in rows]
        if any(value is None for value in selectors):
            return None, "query_selector_exact_source_unavailable"
        base, others = selectors[0], selectors[1:]
        changed = {key for query in others for key in set(base) | set(query) if base.get(key) != query.get(key) or (key in base) != (key in query)}
        if not changed <= set(declaration.keys):
            return None, "query_transform_changes_unrelated_selector"
        if not any(key in query for key in declaration.keys for query in selectors):
            return None, "query_transform_key_absent_from_requests"
        if declaration.location == "body" and any(query != source_query for query in followup_queries):
            return None, "query_transform_changes_unrelated_selector"
        if declaration.location == "query":
            bodies = [_query_selector_values(row, "body") for row in rows]
            body_changed = (
                any(body != bodies[0] for body in bodies[1:]) if all(body is not None for body in bodies)
                else len({row.get("request_body_shape", {}).get("body_sha256") for row in rows}) > 1
            )
            if body_changed:
                return None, "query_transform_changes_unrelated_selector"
    elif isinstance(relation.primary_predicate, ForallPredicate) and relation.primary_predicate.scope == "finite_query_plan":
        transform = "finite_query_plan"
    elif (
        len(followup_queries) == 1
        and "page" not in source_query
        and "page" not in followup_queries[0]
        and set(source_query) < set(followup_queries[0])
        and all(followup_queries[0][key] == value for key, value in source_query.items())
    ):
        transform = "filter_refinement"
    elif (
        len(followup_queries) == 1
        and "page" not in source_query
        and "page" not in followup_queries[0]
        and set(followup_queries[0]) < set(source_query)
        and all(source_query[key] == value for key, value in followup_queries[0].items())
    ):
        transform = "filter_expansion"
    elif len(followup_queries) == 1:
        transform, selector_transform_witness = _typed_selector_value_transform(
            source_query,
            followup_queries[0],
            source_row=rows[0],
            followup_row=rows[1],
            relation=relation,
            view=view,
        )
    elif (
        len(followup_queries) >= 2
        and "page" not in source_query
        and all(
            "page" in query
            and {key: value for key, value in query.items() if key != "page"}
            == source_query
            for query in followup_queries
        )
        and len({_canonical_sha256(query["page"]) for query in followup_queries})
        == len(followup_queries)
    ):
        transform = "pagination_partition"
    if transform is None:
        same_keys_changed = (
            len(followup_queries) == 1
            and set(source_query) == set(followup_queries[0])
            and source_query != followup_queries[0]
        )
        post_selector_reason = (
            _post_selector_comparison_reason(rows[0], rows[1])
            if len(followup_queries) == 1
            else None
        )
        if post_selector_reason is not None:
            return None, post_selector_reason
        if same_keys_changed:
            return None, "query_selector_value_direction_unproven"
        return None, "query_transform_unavailable" if not same_operation else None

    operation_scope = "same_operation"
    logical_collection_witness: dict[str, Any] | None = None
    predicate = relation.primary_predicate
    if relation.contract_kind in {"C07", "C08", "C09"} and relation.query_transform is None:
        return None, "query_transform_semantics_source_missing"
    if transform == "equivalent_input":
        if relation.contract_kind != "C07" or not isinstance(predicate, CollectionRelationPredicate) or predicate.operator != "equal" or len(followups) != 1:
            return None, "query_contract_transform_mismatch"
    elif transform == "sort":
        if relation.contract_kind != "C09" or not isinstance(predicate, OrderingPredicate) or len(followups) != 1:
            return None, "query_contract_transform_mismatch"
    elif transform == "finite_query_plan":
        if not isinstance(predicate, ForallPredicate) or predicate.scope != "finite_query_plan":
            return None, "query_contract_transform_mismatch"
    if isinstance(predicate, ForallPredicate):
        for operand in _single_state_operands(relation.primary_predicate):
            if not isinstance(operand, QueryRequestOperand):
                continue
            if operand.ref.role != "source_query_request":
                return None, "finite_forall_requires_common_source_request_parameter"
            if operand.ref.location not in {"query", "body"}:
                return None, "finite_forall_parameter_location_unsupported"
            try:
                from .dsl import parse_request_value
                values = [get_path(row.get("query", {}), operand.ref.path) for row in rows] if operand.ref.location == "query" else [(_query_selector_values(row, "body") or {})[operand.ref.path] for row in rows]
                if any(value != values[0] for value in values[1:]):
                    return None, "finite_forall_selector_changes_between_pages"
                if operand.ref.location == "query":
                    for value in values:
                        parse_request_value(value, operand.ref.value_type, "query")
            except (KeyError, TypeError, ValueError):
                return None, "finite_forall_parameter_unavailable"
    query_scope = relation.query_scope or QueryScope()
    if isinstance(predicate, ForallPredicate) or isinstance(predicate, PartitionRelationPredicate) and predicate.operator == "complete_union":
        if query_scope.scope != "finite_query_plan":
            return None, "query_complete_scope_requires_termination"
    plan_roles_for_scope = ["source_query", *followup_roles]
    if query_scope.scope == "finite_query_plan":
        covered = set()
        for closure in query_scope.closures:
            if any(role not in plan_roles_for_scope for role in closure.roles) or closure.roles != [role for role in plan_roles_for_scope if role in closure.roles]:
                return None, "query_closure_roles_or_order_invalid"
            covered.update(closure.roles)
            endpoint = endpoints[plan_roles_for_scope.index(closure.termination.ref.role)]
            visible = _shape_path_types(requests[endpoint.request_ref]["response_body_shape"])
            if visible.get(closure.termination.ref.path) != closure.termination.ref.value_type:
                return None, "query_termination_ref_absent_from_visible_shape"
        if covered != set(plan_roles_for_scope):
            return None, "query_closure_scope_incomplete"
        if isinstance(predicate, (ForallPredicate, CollectionUniquenessPredicate)):
            roles = plan_roles_for_scope if isinstance(predicate, ForallPredicate) else followup_roles
            for role in roles:
                if not any(role in closure.roles and closure.collection_path == predicate.collection.path for closure in query_scope.closures):
                    return None, "query_collection_scope_unclosed"
        if isinstance(predicate, (CollectionRelationPredicate, OrderingPredicate)):
            operands = (predicate.left, predicate.right) if isinstance(predicate, CollectionRelationPredicate) else (predicate.before, predicate.after)
            for operand in operands:
                if not any(closure.roles == [operand.role] and closure.collection_path == operand.path for closure in query_scope.closures):
                    return None, "query_operand_scope_unclosed"
        if isinstance(predicate, PartitionRelationPredicate):
            for operand in [predicate.source, *predicate.partitions, *([predicate.expected_remainder] if predicate.expected_remainder else [])]:
                if not any(closure.roles == [operand.role] and closure.collection_path == operand.path for closure in query_scope.closures):
                    return None, "partition_operands_require_independent_closed_scopes"
    if transform in {"filter_refinement", "filter_expansion"}:
        if relation.contract_kind != "C08" or not isinstance(
            predicate, CollectionRelationPredicate
        ):
            return None, "query_contract_transform_mismatch"
        expected_operator = (
            "subset" if transform == "filter_refinement" else "superset"
        )
        compatible, reason, _shape_witness = (
            _cross_operation_collection_shapes_are_compatible(
                rows[0],
                rows[1],
                predicate,
                expected_operator=expected_operator,
            )
        )
        if not compatible:
            return None, reason
    elif transform == "pagination_partition":
        if relation.contract_kind != "C10":
            return None, "numbered_query_followups_incomplete"
        compatible, reason = _pagination_collection_shapes_are_compatible(
            rows, followup_roles, predicate
        )
        if not compatible:
            return None, reason
    if not same_operation:
        if (
            len(followups) != 1
            or transform != "filter_refinement"
            or not _query_is_filter_refinement(source_query, followup_queries[0])
        ):
            return None, "query_transform_unavailable"
        if relation.contract_kind != "C08" or not isinstance(
            predicate, CollectionRelationPredicate
        ):
            return None, "query_contract_transform_mismatch"
        compatible, reason, shape_witness = (
            _cross_operation_collection_shapes_are_compatible(
                rows[0], rows[1], predicate
            )
        )
        if not compatible:
            return None, reason
        witnesses = _cross_operation_collection_witnesses(
            rows[0], rows[1], relation=relation, view=view
        )
        if not witnesses:
            return None, "logical_collection_witness_missing"
        operation_scope = "cross_operation_same_logical_collection"
        logical_collection_witness = {
            **shape_witness,
            "association_kind": (
                "shared_recording_context"
                if any(
                    row["kind"] in {"request_group", "ui_action"}
                    for row in witnesses
                )
                else "explicit_recorded_relation"
            ),
        }
    roles = {
        "producer": _endpoint_payload(source),
        "source_query": _endpoint_payload(source),
        **{
            role: _endpoint_payload(endpoint)
            for role, endpoint in zip(followup_roles, followups, strict=True)
        },
    }
    plan_roles = ["source_query", *followup_roles]
    payload = {
        "shape_kind": "metamorphic_query",
        "roles": roles,
        "transform_kind": transform,
        "query_scope": query_scope.model_dump(mode="json", exclude_none=True),
        "query_transform": relation.query_transform.model_dump(mode="json") if relation.query_transform is not None else None,
        "query_plan": [
            {
                "role": role,
                "request_ref": roles[role]["request_ref"],
                "query": requests[roles[role]["request_ref"]].get("query", {}),
                "action_event_ids": requests[roles[role]["request_ref"]].get(
                    "automatic_event_ids", ()
                ),
            }
            for role in plan_roles
        ],
    }
    if logical_collection_witness is not None:
        payload["operation_scope"] = operation_scope
        payload["logical_collection_witness"] = logical_collection_witness
    if selector_transform_witness is not None:
        payload["selector_transform_witness"] = selector_transform_witness
    return _with_plan_id(payload), None


def _temporal_observation_plan(relation: V2RelationProposal, by_role: Mapping[str, list[ProposalEndpoint]], requests: Mapping[str, Any]) -> dict[str, Any]:
    if any(len(rows) != 1 for rows in by_role.values()) or "effect_source" not in by_role:
        raise CandidateAdmissionError("temporal_action_roles_unclosed")
    after_roles = [role for role in by_role if role in {"after", "reusable_observer"} or role.startswith("actor_after:")]
    before_roles = [role for role in by_role if role == "before" or role.startswith("actor_before:")]
    if len(after_roles) != 1 or len(before_roles) > 1 or set(by_role) != {"effect_source", *after_roles, *before_roles}:
        raise CandidateAdmissionError("temporal_target_roles_unclosed")
    producer, observer = by_role["effect_source"][0], by_role[after_roles[0]][0]
    action, after = requests[producer.request_ref], requests[observer.request_ref]
    if not _is_write(action) or not _is_read(after) or action["global_order"] >= after["global_order"]:
        raise CandidateAdmissionError("temporal_action_observer_order_invalid")
    topology = _verified_role_topology(producer, observer, requests)
    if topology is None or relation.contract_kind == "self_exclusion" and topology["principal_relation"] != "same":
        raise CandidateAdmissionError("temporal_principal_session_unverified")
    allowed = {"after", "after_status", "producer_request", "producer_response", after_roles[0]}
    if any(ref.role not in allowed for ref in _predicate_value_refs(relation.primary_predicate)):
        raise CandidateAdmissionError("temporal_predicate_not_one_target")
    target = relation.primary_predicate.target if isinstance(relation.primary_predicate, PresencePredicate) else relation.primary_predicate.left if isinstance(relation.primary_predicate, EqualityPredicate) else relation.primary_predicate.collection
    if target.role not in {"after", "after_status", after_roles[0]}:
        raise CandidateAdmissionError("temporal_predicate_requires_observer_target")
    roles = {"producer": _endpoint_payload(producer), "after": _endpoint_payload(observer)}
    if before_roles:
        before = by_role[before_roles[0]][0]
        row = requests[before.request_ref]
        if not _is_read(row) or before.actor != observer.actor or row["session_run_id"] != after["session_run_id"] or row["global_order"] >= action["global_order"]:
            raise CandidateAdmissionError("temporal_before_unclosed")
        roles["before"] = _endpoint_payload(before)
    count = 3 if relation.time_requirement.observation_mode == "sampled" else 1
    return _with_plan_id({"shape_kind": "temporal", "roles": roles, "identity_topology": topology,
        "time_requirement": relation.time_requirement.model_dump(mode="json", exclude_none=True),
        "observation_plan": [{"role": f"D{index}", "phase": "after", **_endpoint_payload(observer)} for index in range(1, count + 1)]})


def _joint_observation_plan(relation: V2RelationProposal, by_role: Mapping[str, list[ProposalEndpoint]], requests: Mapping[str, Any]) -> dict[str, Any]:
    predicate = relation.primary_predicate
    delta = isinstance(predicate, ArithmeticPredicate) and predicate.operator == "linear_delta"
    if any(len(rows) != 1 for rows in by_role.values()):
        raise CandidateAdmissionError("joint_roles_not_unique")
    read_roles = set(by_role) - {"effect_source"}
    needed = {ref.role for ref in _predicate_value_refs(predicate) if ref.role != "item"}
    joint = relation.joint_observation.model_dump(mode="json", exclude_none=True)
    for closure in joint["query_scope"]["closures"]:
        needed.update(closure["roles"])
        if not isinstance(predicate, AggregationPredicate) or predicate.scope != "finite_query_plan" or predicate.collection.role not in closure["roles"] or closure["collection_path"] != predicate.collection.path:
            raise CandidateAdmissionError("joint_collection_scope_mismatch")
    if isinstance(predicate, AggregationPredicate) and (predicate.scope == "finite_query_plan") != (joint["query_scope"]["scope"] == "finite_query_plan"):
        raise CandidateAdmissionError("joint_collection_scope_mismatch")
    if read_roles != needed or len({by_role[role][0].request_ref for role in read_roles}) < 2 or delta != ("effect_source" in by_role):
        raise CandidateAdmissionError("joint_independent_responses_unclosed")
    endpoints = {role: rows[0] for role, rows in by_role.items()}
    actual = [requests[endpoint.request_ref] for endpoint in endpoints.values()]
    if len({(row["actor_id"], row["session_run_id"]) for row in actual}) != 1 or any(not _is_read(requests[endpoints[role].request_ref]) for role in read_roles):
        raise CandidateAdmissionError("joint_finite_read_session_unclosed")
    before = {term.before.role for term in predicate.terms} if delta else set()
    after = {term.after.role for term in predicate.terms} if delta else read_roles
    if delta:
        action = requests[endpoints["effect_source"].request_ref]
        if not _is_write(action) or before & after or before | after != read_roles:
            raise CandidateAdmissionError("joint_delta_checkpoints_unclosed")
        for term in predicate.terms:
            first, last = (requests[endpoints[role].request_ref] for role in (term.before.role, term.after.role))
            if not first["global_order"] < action["global_order"] < last["global_order"] or any(first.get(key) != last.get(key) for key in ("operation_id", "canonical_path", "query")):
                raise CandidateAdmissionError("joint_resource_checkpoint_mismatch")
    if joint["consistency"] != "no_competing_writes_workflow" and {row["role"] for row in joint["consistency_refs"]} != read_roles:
        raise CandidateAdmissionError("joint_consistency_roles_unclosed")
    ordered = sorted(read_roles, key=lambda role: requests[endpoints[role].request_ref]["global_order"])
    return _with_plan_id({"shape_kind": "multi_resource", "roles": {("producer" if role == "effect_source" else role): _endpoint_payload(endpoint) for role, endpoint in endpoints.items()},
        "observation_plan": [{"role": role, "phase": "before" if role in before else "after", **_endpoint_payload(endpoints[role])} for role in ordered],
        "joint_observation": joint})


def _plan_consumer(plan: dict[str, Any]) -> dict[str, str]:
    shape = plan["shape_kind"]
    roles = plan["roles"]
    if shape == "temporal":
        return roles["after"]
    if shape == "multi_resource":
        return roles[plan["observation_plan"][-1]["role"]]
    if shape == "single_state":
        return roles["observation"]
    if shape == "causal_two_arm":
        return roles["after"]
    if shape in {"lifecycle_workflow", "repeated_execution"}:
        return roles["after"]
    if shape == "actor_matrix":
        role = next(key for key in roles if key.startswith("actor_after:"))
        return roles[role]
    if shape == "negative_no_effect":
        return roles["after"]
    role = sorted(
        (key for key in roles if key.startswith("followup_query:")),
        key=lambda key: int(key.removeprefix("followup_query:q")),
    )[-1]
    return roles[role]
def _validate_predicate_against_visible_shapes(
    predicate: PrimaryPredicate,
    producer_request: dict[str, Any],
    consumer_request: dict[str, Any],
    plan: dict[str, Any],
    requests: dict[str, Any],
) -> None:
    _validate_predicate_type_semantics(predicate)
    if plan.get("shape_kind") == "temporal":
        spec = plan["time_requirement"]
        evidence = spec.get("timestamp_evidence")
        producer_visible = _shape_path_types(producer_request["response_body_shape"])
        observer_visible = _shape_path_types(consumer_request["response_body_shape"])
        for key in ("duration_parameter", "hold_duration_parameter", "error_before_parameter", "error_after_parameter"):
            operand = spec.get(key)
            if operand is None or operand["source"] == "hypothesis":
                continue
            ref = operand["ref"]
            visible = _shape_path_types(producer_request["request_body_shape"]) if ref["role"] == "producer_request" else producer_visible
            if visible.get(ref["path"]) != ref["value_type"]:
                raise CandidateAdmissionError("temporal_parameter_source_not_observed")
        if evidence is not None:
            required = [(producer_visible, evidence["origin_time_path"], "integer"), (producer_visible, evidence["clock_id_path"], "string"),
                (observer_visible, evidence["clock_id_path"], "string"), (observer_visible, evidence["items_path"], "array"),
                (observer_visible, _identity_path(evidence["items_path"] + "[*]", evidence["time_path"]), "integer")]
            for key in ("end_time_path", "coverage_start_path", "coverage_end_path", "complete_path"):
                if key in evidence:
                    path = _identity_path(evidence["items_path"] + "[*]", evidence[key]) if key == "end_time_path" else evidence[key]
                    required.append((observer_visible, path, "boolean" if key == "complete_path" else "integer"))
            if any(visible.get(path) != kind for visible, path, kind in required):
                raise CandidateAdmissionError("temporal_timestamp_capability_not_observed")
        for ref in _predicate_value_refs(predicate):
            if ref.role in {"after", "after_status"} or ref.role.startswith("actor_after:"):
                if ref.role == "after_status":
                    continue
                path = _identity_path(_identity_path(evidence["items_path"] + "[*]", evidence.get("value_path", "$")), ref.path) if evidence else ref.path
                visible = observer_visible
            else:
                path = ref.path
                visible = _shape_path_types(producer_request["request_body_shape" if ref.role == "producer_request" else "response_body_shape"])
            if visible.get(path) != ref.value_type:
                raise CandidateAdmissionError("predicate_ref_absent_from_visible_shape")
        return
    if plan.get("shape_kind") == "multi_resource":
        for ref in (*_predicate_value_refs(predicate), *(ValueRef.model_validate(row) for row in plan["joint_observation"]["consistency_refs"])):
            role, path = ref.role, ref.path
            if role == "item" and isinstance(predicate, AggregationPredicate):
                role, path = predicate.collection.role, _identity_path(predicate.collection.path + "[*]", path)
            endpoint = plan["roles"].get(role)
            if endpoint is None or (path, ref.value_type) not in {(row["path"], row["type"]) for row in requests[endpoint["request_ref"]]["response_body_shape"]["shape_rows"]}:
                raise CandidateAdmissionError("predicate_ref_absent_from_visible_shape")
        return
    if isinstance(predicate, (RepeatEqualPredicate, RepeatRejectedPredicate, RepeatDeltaPredicate)):
        _validate_predicate_against_visible_shapes(predicate.delta if isinstance(predicate, RepeatDeltaPredicate) else predicate.projection, producer_request, consumer_request, plan, requests)
        if isinstance(predicate, RepeatRejectedPredicate) and predicate.rejection is not None:
            _validate_predicate_against_visible_shapes(predicate.rejection, producer_request, consumer_request, plan, requests)
        return
    if plan.get("shape_kind") == "single_state":
        _validate_single_state_visible_shapes(predicate, consumer_request)
        return
    shape_rows = {
        "producer_status": [{"path": "$", "type": "integer"}],
        "after_status": [{"path": "$", "type": "integer"}],
        "before": consumer_request["response_body_shape"]["shape_rows"],
        "after": consumer_request["response_body_shape"]["shape_rows"],
        "producer_request": producer_request["request_body_shape"]["shape_rows"],
        "producer_response": producer_request["response_body_shape"]["shape_rows"],
    }
    if plan.get("shape_kind") == "actor_matrix":
        roles = plan["roles"]
        for role, endpoint in roles.items():
            if role.startswith("actor_after:"):
                shape_rows[role] = consumer_request["response_body_shape"]["shape_rows"]
            elif role.startswith("actor_before:"):
                request = requests[str(endpoint["request_ref"])]
                shape_rows[role] = request["response_body_shape"]["shape_rows"]
    if plan.get("shape_kind") in {"lifecycle_workflow", "repeated_execution", "negative_no_effect"}:
        for role in ("before", "after"):
            if role not in plan["roles"]:
                continue
            endpoint = plan["roles"][role]
            request = requests[str(endpoint["request_ref"])]
            shape_rows[role] = request["response_body_shape"]["shape_rows"]
    if plan.get("shape_kind") == "negative_no_effect":
        for role in ("before", "after"):
            endpoint = plan["roles"][role]
            request = requests[str(endpoint["request_ref"])]
            shape_rows[role] = request["response_body_shape"]["shape_rows"]
    if plan.get("shape_kind") == "metamorphic_query":
        followup_shapes: list[set[tuple[str, str]]] = []
        for role, endpoint in plan["roles"].items():
            if role == "producer":
                continue
            request = requests[str(endpoint["request_ref"])]
            rows = request["response_body_shape"]["shape_rows"]
            shape_rows[role] = rows
            if role.startswith("followup_query:"):
                followup_shapes.append({
                    (str(row.get("path")), str(row.get("type"))) for row in rows
                })
        common_followup_shape = set.intersection(*followup_shapes)
        shape_rows["followup_query"] = [
            {"path": path, "type": value_type}
            for path, value_type in sorted(common_followup_shape)
        ]
    visible = {
        role: {(str(row.get("path")), str(row.get("type"))) for row in rows}
        for role, rows in shape_rows.items()
    }
    if isinstance(predicate, ForallPredicate):
        for role in [step["role"] for step in plan["query_plan"]]:
            row = requests[plan["roles"][role]["request_ref"]]
            value = predicate.model_dump(mode="json")
            value["scope"] = "actual_response"
            value["collection"]["role"] = "observation"
            for atom in (value["body"], value.get("item_guard")):
                if atom is not None:
                    for key in ("right", "lower", "upper", "domain"):
                        operand = atom.get(key)
                        if isinstance(operand, dict) and operand.get("source") == "request":
                            operand["ref"]["role"] = "observation_request"
            _validate_single_state_visible_shapes(ForallPredicate.model_validate(value), row)
        return
    refs: list[ValueRef] = []
    if isinstance(predicate, OrderingPredicate):
        refs.extend((predicate.before, predicate.after))
        path = _identity_path(predicate.after.path + "[*]", predicate.key)
        if not any(row_path == path for row_path, _ in visible[predicate.after.role]):
            raise CandidateAdmissionError("sort_key_absent_from_visible_shape")
    elif isinstance(predicate, PresencePredicate):
        refs.append(predicate.target)
        if predicate.member is not None:
            refs.append(predicate.member.ref)
    elif isinstance(predicate, JsonTypePredicate):
        refs.append(predicate.target)
    elif isinstance(predicate, CountBoundPredicate):
        refs.append(predicate.collection)
    elif isinstance(predicate, EqualityPredicate):
        if isinstance(predicate.left, LocatedMemberFieldRef):
            refs.append(predicate.left.member.ref)
        else:
            refs.append(predicate.left)
        if isinstance(predicate.right, RoleOperand):
            refs.append(predicate.right.ref)
    elif isinstance(predicate, (StateTransitionPredicate, NumericDirectionPredicate)):
        for transition_ref in (predicate.before, predicate.after):
            refs.append(
                transition_ref.member.ref
                if isinstance(transition_ref, LocatedMemberFieldRef)
                else transition_ref
            )
        if isinstance(predicate, StateTransitionPredicate):
            refs.extend(value.ref for value in (predicate.from_value, predicate.to_value) if isinstance(value, RoleOperand))
    elif isinstance(predicate, NumericDeltaPredicate):
        for transition_ref in (predicate.before, predicate.after):
            refs.append(
                transition_ref.member.ref
                if isinstance(transition_ref, LocatedMemberFieldRef)
                else transition_ref
            )
        if isinstance(predicate.delta, (RoleOperand, NumericRequestOperand)):
            refs.append(predicate.delta.ref)
    elif isinstance(predicate, CountDeltaPredicate):
        refs.extend((predicate.before, predicate.after))
    elif isinstance(predicate, CollectionMembershipPredicate):
        refs.extend((predicate.collection, predicate.member.ref))
    elif isinstance(predicate, MembershipPredicate):
        refs.extend((predicate.before, predicate.after, predicate.member.ref))
    elif isinstance(predicate, CollectionUniquenessPredicate):
        refs.append(predicate.collection)
    elif isinstance(predicate, CollectionRelationPredicate):
        refs.extend((predicate.left, predicate.right))
    elif isinstance(predicate, StateEquivalencePredicate):
        refs.extend(ref.member.ref if isinstance(ref, LocatedMemberFieldRef) else ref for ref in (predicate.left, predicate.right))
    else:
        refs.extend((predicate.source, *predicate.partitions))
        if predicate.expected_remainder is not None:
            refs.append(predicate.expected_remainder)
    for ref in refs:
        if isinstance(predicate, PresencePredicate) and ref == predicate.target and ref.value_type == "object" and predicate.operator == "absent" and predicate.absent_statuses:
            if (ref.path, "object") not in visible.get("before", set()):
                raise CandidateAdmissionError("delete_point_preexistence_shape_missing")
            continue
        if "[*]" in ref.path:
            raise CandidateAdmissionError(
                "wildcard_value_ref_requires_identity_locator"
            )
        if ref.role not in visible or (ref.path, ref.value_type) not in visible[ref.role]:
            raise CandidateAdmissionError("predicate_ref_absent_from_visible_shape")
    request_operands = []
    if isinstance(predicate, EqualityPredicate) and isinstance(predicate.right, QueryRequestOperand):
        request_operands.append(predicate.right)
    if isinstance(predicate, StateTransitionPredicate):
        request_operands.extend(value for value in (predicate.from_value, predicate.to_value) if isinstance(value, QueryRequestOperand))
    for operand in request_operands:
        ref = operand.ref
        if ref.role != "producer_request":
            raise CandidateAdmissionError("workflow_request_parameter_role_unavailable")
        if ref.location == "body":
            if (ref.path, ref.value_type) not in visible["producer_request"]:
                raise CandidateAdmissionError("request_parameter_absent_from_visible_shape")
        else:
            from .dsl import get_path, parse_request_value
            try:
                parameters = [row for row in producer_request.get("parameter_evidence", {}).get("parameters", ()) if row.get("location") == ref.location and row.get("path") == ref.path]
                if len(parameters) != 1 or parameters[0].get("occurrence_count", 1) != 1:
                    raise ValueError("request parameter is not a unique visible literal")
                if parameters[0].get("literal_available") is True:
                    parse_request_value(parameters[0]["value"], ref.value_type, ref.location)
                elif ref.value_type != parameters[0].get("value_type"):
                    raise ValueError("unavailable request parameter type is not established")
            except (KeyError, TypeError, ValueError) as error:
                raise CandidateAdmissionError("request_parameter_absent_from_visible_shape") from error
    located_refs: list[LocatedMemberFieldRef] = []
    if isinstance(predicate, EqualityPredicate) and isinstance(
        predicate.left, LocatedMemberFieldRef
    ):
        located_refs.append(predicate.left)
    if isinstance(predicate, (StateTransitionPredicate, NumericDeltaPredicate, NumericDirectionPredicate)):
        located_refs.extend(
            item
            for item in (predicate.before, predicate.after)
            if isinstance(item, LocatedMemberFieldRef)
        )
    if isinstance(predicate, StateEquivalencePredicate):
        located_refs.extend(ref for ref in (predicate.left, predicate.right) if isinstance(ref, LocatedMemberFieldRef))
    for located in located_refs:
        if (
            located.role not in visible
            or (located.collection_path, "array") not in visible[located.role]
        ):
            raise CandidateAdmissionError(
                "located_collection_absent_from_visible_shape"
            )
        selected_path = _identity_path(
            f"{located.collection_path}[*]", located.field_path
        )
        if (selected_path, located.value_type) not in visible[located.role]:
            raise CandidateAdmissionError(
                "located_field_absent_from_visible_shape"
            )
        member = located.member.ref
        for pair in located.identity.field_pairs:
            member_path = _identity_path(member.path, pair.member_path)
            collection_path = _identity_path(
                f"{located.collection_path}[*]",
                pair.collection_item_path,
            )
            member_types = {
                value_type
                for row_path, value_type in visible[member.role]
                if row_path == member_path
            }
            collection_types = {
                value_type
                for row_path, value_type in visible[located.role]
                if row_path == collection_path
            }
            if not member_types or not collection_types:
                raise CandidateAdmissionError(
                    "located_identity_absent_from_visible_shape"
                )
            if member_types.isdisjoint(collection_types):
                raise CandidateAdmissionError(
                    "located_identity_types_incompatible"
                )
    identity = getattr(predicate, "identity", None)
    if identity is not None and hasattr(predicate, "member"):
        member = predicate.member.ref
        if isinstance(predicate, PresencePredicate):
            collections = [
                predicate.target.model_copy(update={"role": "before"})
                if (
                    predicate.operator == "absent"
                    and predicate.target.role == "after"
                    and plan.get("shape_kind") == "lifecycle_workflow"
                )
                else predicate.target
            ]
        elif isinstance(predicate, CollectionMembershipPredicate):
            collections = [predicate.collection]
        else:
            collections = [
                predicate.after
                if predicate.operator == "added"
                else predicate.before
            ]
        for pair in identity.field_pairs:
            member_path = _identity_path(member.path, pair.member_path)
            member_types = {
                value_type
                for row_path, value_type in visible[member.role]
                if row_path == member_path
            }
            if not member_types:
                raise CandidateAdmissionError(
                    "predicate_member_identity_absent_from_opportunity"
                )
            for collection in collections:
                item_path = _identity_path(
                    f"{collection.path}[*]", pair.collection_item_path
                )
                collection_types = {
                    value_type
                    for row_path, value_type in visible[collection.role]
                    if row_path == item_path
                }
                if not collection_types:
                    raise CandidateAdmissionError(
                        "predicate_collection_identity_absent_from_opportunity"
                    )
                if member_types.isdisjoint(collection_types):
                    raise CandidateAdmissionError(
                        "predicate_identity_types_incompatible"
                    )
    elif identity is not None or isinstance(predicate, (CollectionRelationPredicate, OrderingPredicate)):
        collections = [ref for ref in refs if ref.value_type == "array"]
        for collection in collections:
            for path in identity.paths if identity is not None else predicate.projection:
                item_path = _identity_path(f"{collection.path}[*]", path)
                if not any(
                    row_path == item_path for row_path, _ in visible[collection.role]
                ):
                    raise CandidateAdmissionError("predicate_identity_absent_from_opportunity")


def _validate_transition_fact_grounding(
    relation: V2RelationProposal,
    *,
    view: Any,
    visible_evidence_refs: set[str],
) -> None:
    predicate = relation.primary_predicate
    facts = {item.fact_id: item for item in view.transition_facts}
    constants: tuple[TransitionFactConstant, ...]
    if isinstance(predicate, StateTransitionPredicate) and isinstance(predicate.from_value, TransitionFactConstant):
        constants = (predicate.from_value, predicate.to_value)
    elif isinstance(predicate, NumericDeltaPredicate) and isinstance(
        predicate.delta, TransitionFactConstant
    ):
        constants = (predicate.delta,)
        if predicate.multiplier != 1:
            raise CandidateAdmissionError(
                "fixed_signed_delta_multiplier_must_be_one"
            )
    elif isinstance(predicate, CountDeltaPredicate):
        constants = ()
    else:
        return
    fact_refs = (
        {item.fact_ref for item in constants}
        if constants
        else set(relation.evidence_refs) & set(facts)
    )
    if len(fact_refs) != 1:
        raise CandidateAdmissionError("transition_fact_reference_ambiguous")
    fact_ref = next(iter(fact_refs))
    if (
        fact_ref not in visible_evidence_refs
        or fact_ref not in relation.evidence_refs
    ):
        raise CandidateAdmissionError("transition_fact_reference_not_visible")
    fact = facts.get(fact_ref)
    expected_kind = (
        "collection_count" if isinstance(predicate, CountDeltaPredicate) else "scalar"
    )
    if fact is None or fact.observation_kind != expected_kind:
        raise CandidateAdmissionError("transition_fact_reference_invalid")
    by_role = _bindings_by_role(relation)
    before_role = predicate.before.role
    after_role = predicate.after.role
    if len(by_role.get("effect_source", ())) != 1:
        raise CandidateAdmissionError("transition_fact_roles_not_unique")
    if before_role in by_role or after_role in by_role:
        if any(len(by_role.get(role, ())) != 1 for role in (before_role, after_role)):
            raise CandidateAdmissionError("transition_fact_roles_not_unique")
        if (
            by_role[before_role][0].request_ref != fact.before_request_ref
            or by_role[after_role][0].request_ref != fact.after_request_ref
        ):
            raise CandidateAdmissionError("transition_fact_provenance_mismatch")
    elif set(by_role) == {"effect_source", "reusable_observer"}:
        if (
            len(by_role["reusable_observer"]) != 1
            or by_role["reusable_observer"][0].request_ref
            != fact.after_request_ref
        ):
            raise CandidateAdmissionError("transition_fact_provenance_mismatch")
    else:
        raise CandidateAdmissionError("transition_fact_roles_not_unique")
    competition = fact.write_competition
    if (
        competition.grounding_status != "unique_target_relevant"
        or competition.groundable_effect_source_request_ref
        != by_role["effect_source"][0].request_ref
    ):
        raise CandidateAdmissionError(
            "transition_fact_effect_source_not_uniquely_target_relevant"
        )
    if isinstance(predicate, CountDeltaPredicate):
        if (
            predicate.before.path != predicate.after.path
            or predicate.before.path != fact.target_path
            or predicate.before.value_type != "array"
            or predicate.after.value_type != "array"
            or type(predicate.delta) is not int
            or type(fact.signed_delta) is not int
            or predicate.delta != fact.signed_delta
        ):
            raise CandidateAdmissionError("transition_fact_constant_mismatch")
        return
    if fact.identity.get("kind") == "collection_member":
        if not (
            isinstance(predicate.before, LocatedMemberFieldRef)
            and isinstance(predicate.after, LocatedMemberFieldRef)
        ):
            raise CandidateAdmissionError("transition_fact_locator_missing")
        before_ref = predicate.before
        after_ref = predicate.after
        witness = fact.locator_witness
        if witness is None:
            raise CandidateAdmissionError("transition_fact_locator_missing")
        effect_sources = by_role.get("effect_source", ())
        pairs = before_ref.identity.field_pairs
        if (
            len(effect_sources) != 1
            or effect_sources[0].request_ref != witness.request_ref
            or witness.flow_id not in visible_evidence_refs
            or witness.flow_id not in relation.evidence_refs
            or before_ref.collection_path != after_ref.collection_path
            or before_ref.collection_path != fact.identity["collection_path"]
            or before_ref.field_path != after_ref.field_path
            or before_ref.field_path != fact.target_path
            or before_ref.value_type != after_ref.value_type
            or before_ref.value_type != fact.value_type
            or before_ref.member != after_ref.member
            or before_ref.identity != after_ref.identity
            or len(pairs) != 1
            or pairs[0].collection_item_path != fact.identity["member_path"]
            or before_ref.member.ref.role != witness.operand_role
            or _identity_path(
                before_ref.member.ref.path, pairs[0].member_path
            )
            != witness.operand_path
        ):
            raise CandidateAdmissionError("transition_fact_locator_mismatch")
    elif (
        isinstance(predicate.before, LocatedMemberFieldRef)
        or isinstance(predicate.after, LocatedMemberFieldRef)
        or predicate.before.path != predicate.after.path
        or predicate.before.path != fact.target_path
        or predicate.before.value_type != predicate.after.value_type
        or predicate.before.value_type != fact.value_type
    ):
        raise CandidateAdmissionError("transition_fact_provenance_mismatch")
    if isinstance(predicate, StateTransitionPredicate):
        if not (
            type(predicate.from_value.value) is type(fact.before_value) is bool
            and type(predicate.to_value.value) is type(fact.after_value) is bool
            and predicate.from_value.value == fact.before_value
            and predicate.to_value.value == fact.after_value
        ):
            raise CandidateAdmissionError("transition_fact_constant_mismatch")
    else:
        delta = predicate.delta
        assert isinstance(delta, TransitionFactConstant)
        if (
            fact.value_type not in {"integer", "number"}
            or type(delta.value) is not type(fact.signed_delta)
            or delta.value != fact.signed_delta
        ):
            raise CandidateAdmissionError("transition_fact_constant_mismatch")


def _single_state_operands(predicate: PrimaryPredicate) -> tuple[SingleStateOperand, ...]:
    if isinstance(predicate, (EqualityPredicate, StringPredicate)):
        return (predicate.right,)
    if isinstance(predicate, CountBoundPredicate):
        return (predicate.right,)
    if isinstance(predicate, FormatPredicate):
        return (predicate.pattern,) if predicate.pattern is not None else ()
    if isinstance(predicate, ValueDomainPredicate):
        return tuple(item for item in (predicate.lower, predicate.upper, predicate.domain) if item is not None)
    if isinstance(predicate, ForallPredicate):
        return _single_state_operands(predicate.body) + (_single_state_operands(predicate.item_guard) if predicate.item_guard is not None else ())
    if isinstance(predicate, ArithmeticPredicate):
        if predicate.operator == "linear_delta":
            return ()
        return predicate.left, predicate.right
    if isinstance(predicate, CollectionMembershipPredicate):
        return (predicate.member,)
    return ()


def _validate_single_state_visible_shapes(predicate: PrimaryPredicate, request: Mapping[str, Any]) -> None:
    from .dsl import parse_request_value
    if isinstance(predicate, CountBoundPredicate) and predicate.collection is not None and predicate.collection.value_type != "array":
        raise CandidateAdmissionError("count_predicate_requires_observed_collection")
    visible = {(str(row["path"]), str(row["type"])) for row in request["response_body_shape"]["shape_rows"]}
    collection = predicate.collection if isinstance(predicate, (ForallPredicate, AggregationPredicate)) else None
    for ref in _predicate_value_refs(predicate):
        if not isinstance(ref, ValueRef) or not re.fullmatch(r"\$(?:\.[^.*\[\]]+)*", ref.path):
            raise CandidateAdmissionError("single_state_requires_concrete_field_path")
        if ref.role == "item" and collection is not None:
            path = _identity_path(f"{collection.path}[*]", ref.path)
        elif ref.role == "observation":
            path = ref.path
        else:
            raise CandidateAdmissionError("single_state_requires_observation_operand")
        if (path, ref.value_type) not in visible:
            raise CandidateAdmissionError("predicate_ref_absent_from_visible_shape")
    atom = predicate.body if isinstance(predicate, ForallPredicate) else predicate
    if isinstance(atom, CollectionUniquenessPredicate):
        root = atom.collection.path
        if atom.collection.role == "item":
            root = _identity_path(f"{predicate.collection.path}[*]", root)
        visible_paths = {path for path, _ in visible}
        if any(_identity_path(root + "[*]", path) not in visible_paths for path in atom.identity.paths):
            raise CandidateAdmissionError("uniqueness_key_absent_from_visible_shape")
    for operand in _single_state_operands(predicate):
        if not isinstance(operand, QueryRequestOperand):
            continue
        ref = operand.ref
        if ref.role != "observation_request":
            raise CandidateAdmissionError("single_response_parameter_requires_its_request")
        if any(sensitive_field_category(token) is not None for token in ref.path.removeprefix("$.").split(".")):
            raise CandidateAdmissionError("request_operand_is_sensitive")
        if ref.location == "query":
            try:
                value = get_path(request.get("query", {}), ref.path)
                if isinstance(predicate, CountBoundPredicate) and predicate.collection is not None:
                    parse_query_limit(value)
                else:
                    parse_request_value(value, ref.value_type, ref.location)
            except (KeyError, TypeError, ValueError) as error:
                reason = "query_limit_not_unique_nonnegative_integer" if isinstance(predicate, CountBoundPredicate) and predicate.collection is not None else "request_operand_unavailable_or_type_mismatch"
                raise CandidateAdmissionError(reason) from error
        elif ref.location == "body":
            rows = request["request_body_shape"]["shape_rows"]
            if not any(row["path"] == ref.path and row["type"] == ref.value_type for row in rows):
                raise CandidateAdmissionError("request_operand_absent_from_visible_shape")
        elif ref.location == "path":
            if ref.path != "$" or ref.value_type != "string":
                raise CandidateAdmissionError("request_path_operand_requires_complete_path")
        elif ref.path.removeprefix("$.") not in request.get("request_header_names", ()) or ref.value_type != "string":
            raise CandidateAdmissionError("request_header_operand_unavailable")


def _predicate_value_refs(predicate: PrimaryPredicate) -> tuple[ValueRef, ...]:
    if isinstance(predicate, ArithmeticPredicate):
        if predicate.operator == "linear_delta":
            return tuple(ref for term in predicate.terms for ref in (term.before, term.after))
        return (predicate.output, *(value.ref for value in (predicate.left, predicate.right) if isinstance(value, RoleOperand)))
    if isinstance(predicate, AggregationPredicate):
        return tuple(value for value in (predicate.collection, predicate.output, predicate.item, predicate.factor) if value is not None)
    if isinstance(predicate, OrderingPredicate):
        return predicate.before, predicate.after
    if isinstance(predicate, ForallPredicate):
        return (predicate.collection, *_predicate_value_refs(predicate.body), *(_predicate_value_refs(predicate.item_guard) if predicate.item_guard is not None else ()))
    if isinstance(predicate, EqualityPredicate):
        return (predicate.left, *((predicate.right.ref,) if isinstance(predicate.right, RoleOperand) else ()))
    if isinstance(predicate, ValueDomainPredicate):
        return (predicate.target, *(operand.ref for operand in _single_state_operands(predicate) if isinstance(operand, RoleOperand)))
    if isinstance(predicate, (PresencePredicate, JsonTypePredicate, FormatPredicate)):
        return (predicate.target,)
    if isinstance(predicate, (CountBoundPredicate, StringPredicate)):
        target = (predicate.collection or predicate.target) if isinstance(predicate, CountBoundPredicate) else predicate.target
        return (target, *(operand.ref for operand in _single_state_operands(predicate) if isinstance(operand, RoleOperand)))
    if isinstance(predicate, (StateTransitionPredicate, NumericDirectionPredicate)):
        return predicate.before, predicate.after
    if isinstance(predicate, NumericDeltaPredicate):
        refs = [predicate.before, predicate.after]
        if isinstance(predicate.delta, (RoleOperand, NumericRequestOperand)):
            refs.append(predicate.delta.ref)
        return tuple(refs)
    if isinstance(predicate, CountDeltaPredicate):
        return predicate.before, predicate.after
    if isinstance(predicate, MembershipPredicate):
        return predicate.before, predicate.after, predicate.member.ref
    if isinstance(predicate, CollectionMembershipPredicate):
        return (predicate.collection, *((predicate.member.ref,) if isinstance(predicate.member, RoleOperand) else ()))
    if isinstance(predicate, CollectionUniquenessPredicate):
        return (predicate.collection,)
    if isinstance(predicate, CollectionRelationPredicate):
        return predicate.left, predicate.right
    if isinstance(predicate, PartitionRelationPredicate):
        return (
            predicate.source,
            *predicate.partitions,
            *((predicate.expected_remainder,) if predicate.expected_remainder else ()),
        )
    if isinstance(predicate, StateEquivalencePredicate):
        return predicate.left, predicate.right
    return ()


def _identity_path(root: str, relative: str) -> str:
    suffix = "" if relative == "$" else relative.removeprefix("$")
    return f"{root}{suffix}"


def _regular_file(path: str | Path, label: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"{label} does not exist") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} is not a regular file")
    return resolved


def _resolve_ref(root: Path, raw_ref: str, label: str) -> Path:
    ref = PurePosixPath(raw_ref)
    windows = PureWindowsPath(raw_ref)
    if (
        "\\" in raw_ref
        or ref.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ref.as_posix() != raw_ref
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
        raise ValueError(f"{label} ref must be a normalized relative POSIX path")
    try:
        resolved = (root / Path(*ref.parts)).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"{label} ref does not exist") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"{label} ref escapes the input-freeze root")
    return resolved


def _sha256_file(path: Path) -> str:
    return attested_sha256(path)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
