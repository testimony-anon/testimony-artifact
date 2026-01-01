"""Closed current predicate DSL and deterministic assertion evaluation."""

from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache
from typing import Any

from pydantic import TypeAdapter, ValidationError

SEMANTIC_TYPES = {"P01", "P02", "P03", "P04", "P06", "P07", "P08", "P09", "P10", "P11", "P12", "P13", "P14", "P15", "P16", "P17", "P18", "P19", "P20", "P21", "forall"}
SEMANTIC_TYPES.update({"repeat_equal", "repeat_rejected", "repeat_delta"})
ASSERTION_TYPES = SEMANTIC_TYPES | {"status_success", "status_class", "schema_type"}
JSON_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


@dataclass(frozen=True)
class LintResult:
    verdict: str
    predicate: dict[str, Any] | None
    reason: str | None = None


class PredicateNotEvaluable(ValueError):
    """An incomplete conjunction, with each completed check still retained."""

    def __init__(self, reason_code: str, observed: dict[str, Any]) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.observed = observed


class NumericObservation(dict):
    """JSON-safe observation with volatile original numeric values.

    Attributes survive in-memory copies, but never enter JSON artifacts. Losing
    these attributes makes a float operand unavailable for exact P06 evaluation.
    """


def with_numeric_body(observation: Mapping[str, Any], body_text: str) -> NumericObservation:
    value = NumericObservation(observation)
    value.numeric_body = json.loads(body_text, parse_float=Decimal)
    return value


def copy_numeric_sources(source: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    value = NumericObservation(target)
    for key in ("numeric_body", "numeric_request_body"):
        if hasattr(source, key):
            setattr(value, key, copy.deepcopy(getattr(source, key)))
    return value


def request_numeric_observation(source: Mapping[str, Any], body: Any) -> dict[str, Any]:
    value = NumericObservation({"body": body})
    fields = source.get("request_fields")
    if isinstance(fields, Mapping):
        value["request"] = copy.deepcopy(dict(fields))
    elif isinstance(source.get("physical_transport_request"), Mapping):
        transport = source["physical_transport_request"]
        metadata = source.get("physical_transport_metadata") or {}
        value["request"] = {**copy.deepcopy(dict(transport)), "query": copy.deepcopy(metadata.get("query", {})), "headers": copy.deepcopy(metadata.get("request_headers", {}))}
    if hasattr(source, "numeric_request_body"):
        value.numeric_body = copy.deepcopy(source.numeric_request_body)
    return value


def _exact_number(value: Any, lexical_value: Any = None, *, frozen: bool = False) -> tuple[int | Fraction, str]:
    if type(value) is int:
        return value, "integer"
    if type(value) is not float or not math.isfinite(value):
        raise TypeError("arithmetic requires finite JSON numbers; bool and strings are not numbers")
    if not isinstance(lexical_value, Decimal):
        raise PredicateNotEvaluable("numeric_precision_source_missing", {})
    if not lexical_value.is_finite():
        raise TypeError("arithmetic requires finite JSON numbers")
    # Fraction(Decimal) is exact and does not consult Decimal's arithmetic context.
    return Fraction(lexical_value), "frozen_number_text" if frozen else "json_number_text"


def _exact_ref(ref: Mapping[str, Any], observations: Mapping[str, Any]) -> tuple[int | Fraction, str]:
    value = _resolve_value_ref(ref, observations)
    if ref["value_type"] == "integer" and type(value) is not int:
        raise TypeError("P06 integer operand requires an integer")
    if ref["value_type"] not in {"integer", "number"}:
        raise TypeError("P06 requires numeric operand types")
    source = observations[ref["role"]]
    lexical_root = getattr(source, "numeric_body", None)
    lexical_value = None
    if lexical_root is not None:
        if ref.get("source") == "collection_member":
            plain_collection = get_path(_body(source), ref["collection_path"])
            member = _strict_identity_member(plain_collection, _resolve_operand(ref["member"], observations), ref["identity"])
            index = next(index for index, item in enumerate(plain_collection) if item is member)
            lexical_value = get_path(get_path(lexical_root, ref["collection_path"])[index], ref["field_path"])
        else:
            lexical_value = get_path(lexical_root, ref["path"])
    return _exact_number(value, lexical_value)


def _exact_operand(operand: Mapping[str, Any], observations: Mapping[str, Any]) -> tuple[int | Fraction, str]:
    if operand["source"] in {"transition_fact", "hypothesis"}:
        lexical = operand.get("lexical")
        lexical_value = json.loads(lexical, parse_float=Decimal) if lexical is not None else None
        return _exact_number(operand["value"], lexical_value, frozen=True)
    ref = operand["ref"]
    if operand["source"] != "request":
        return _exact_ref(ref, observations)
    value = _resolve_operand(operand, observations)
    raw = _request_operand_value(ref, observations)
    if ref["location"] != "body":
        lexical = json.loads(raw, parse_float=Decimal) if isinstance(raw, str) else None
        return _exact_number(value, lexical)
    source = observations[ref["role"]]
    lexical_root = getattr(source, "numeric_body", None)
    if lexical_root is None:
        lexical_root = getattr(source, "numeric_request_body", None)
    return _exact_number(value, get_path(lexical_root, ref["path"]) if lexical_root is not None else None)


def _frozen_rule(predicate: Mapping[str, Any], name: str) -> dict[str, Any]:
    operand = predicate.get(name)
    if operand is None:
        return {}
    if operand.get("source") != "hypothesis" or type(operand.get("value")) is not dict:
        raise ValueError(f"{name} requires a frozen object rule")
    return operand["value"]


def _convert_numeric_inputs(
    predicate: Mapping[str, Any], values: Mapping[str, int | Fraction], units: Mapping[str, str],
) -> tuple[dict[str, int | Fraction], dict[str, str]]:
    """Apply only declared multiplicative conversions, never infer dimensions."""
    converted, result_units = dict(values), dict(units)
    conversions = _frozen_rule(predicate, "conversions")
    if set(conversions) - set(values):
        raise ValueError("unit conversion names an unavailable operand")
    for name, rule in conversions.items():
        if type(rule) is not dict or set(rule) != {"from", "to", "factor"}:
            raise ValueError("unit conversion requires from/to/factor")
        if predicate["family"] != "P06" and rule["from"] != units[name]:
            raise PredicateNotEvaluable("numeric_unit_incompatible", {})
        if predicate["family"] == "P06" and rule["to"] != units[name]:
            raise PredicateNotEvaluable("numeric_unit_incompatible", {})
        if not all(isinstance(rule[key], str) and rule[key].strip() for key in ("from", "to", "factor")):
            raise ValueError("unit conversion requires explicit units and a numeric token")
        if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", rule["factor"]) is None:
            raise ValueError("unit conversion factor requires a JSON numeric token")
        factor = Fraction(Decimal(rule["factor"]))
        if factor <= 0:
            raise ValueError("unit conversion factor must be positive")
        converted[name] *= factor
        result_units[name] = rule["to"]
    return converted, result_units


def _round_numeric_result(expected: int | Fraction, rule: Mapping[str, Any]) -> int | Fraction:
    if not rule:
        return expected
    if set(rule) != {"scale", "mode", "position"} or type(rule["scale"]) is not int or rule["scale"] < 0 or rule["position"] != "result":
        raise ValueError("rounding requires a nonnegative scale at the result")
    if rule["mode"] not in {"half_even", "half_up", "down"}:
        raise ValueError("unsupported numeric rounding mode")
    factor = 10 ** rule["scale"]
    scaled = Fraction(expected) * factor
    magnitude = abs(scaled)
    integer, remainder = divmod(magnitude.numerator, magnitude.denominator)
    halfway = remainder * 2 - magnitude.denominator
    if rule["mode"] != "down" and (halfway > 0 or halfway == 0 and (rule["mode"] == "half_up" or integer % 2)):
        integer += 1
    return Fraction(integer if scaled >= 0 else -integer, factor)


def _numeric_result_equal(predicate: Mapping[str, Any], actual: int | Fraction, expected: int | Fraction) -> bool:
    expected = _round_numeric_result(expected, _frozen_rule(predicate, "rounding"))
    mode = predicate.get("numeric_mode", "exact")
    tolerance = predicate.get("tolerance")
    if mode == "exact":
        if tolerance is not None or predicate.get("tolerance_kind") is not None:
            raise ValueError("exact arithmetic cannot have an error tolerance")
        return actual == expected
    if mode != "approximate" or tolerance is None:
        raise ValueError("approximate arithmetic requires a frozen error tolerance")
    limit, _ = _exact_operand(tolerance, {})
    if limit < 0:
        raise ValueError("numeric tolerance must be nonnegative")
    kind = predicate.get("tolerance_kind")
    if kind == "relative":
        limit *= abs(expected)
    elif kind != "absolute":
        raise ValueError("numeric tolerance requires absolute or relative semantics")
    return abs(actual - expected) <= limit


def evaluate_numeric_delta(predicate: Mapping[str, Any], observations: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    """The sole P06 after-before = amount×sign evaluator and numeric policy."""
    before, before_source = _exact_ref(predicate["before"], observations)
    after, after_source = _exact_ref(predicate["after"], observations)
    amount, amount_source = _exact_operand(predicate["delta"], observations)
    unit = predicate.get("unit")
    if unit is not None:
        values, _ = _convert_numeric_inputs(predicate, {"before": before, "after": after, "delta": amount}, dict.fromkeys(("before", "after", "delta"), unit["value"]))
        before, after, amount = values["before"], values["after"], values["delta"]
    elif predicate.get("conversions") is not None:
        raise PredicateNotEvaluable("numeric_unit_missing", {})
    multiplier = predicate.get("multiplier", 1)
    if type(multiplier) is not int or multiplier not in {-1, 1}:
        raise TypeError("P06 multiplier requires integer -1 or 1")
    satisfied = _numeric_result_equal(predicate, after - before, amount * multiplier)
    return satisfied, {"numeric_mode": predicate.get("numeric_mode", "exact"), "values_equal": satisfied,
                       "precision_sources": {"before": before_source, "after": after_source, "delta": amount_source}}


def validate_numeric_delta_observed(observed: Mapping[str, Any], satisfied: bool, predicate: Mapping[str, Any] | None = None) -> None:
    if set(observed) != {"numeric_mode", "values_equal", "precision_sources"} or (
        observed.get("numeric_mode") not in {"exact", "approximate"} or observed.get("values_equal") is not satisfied
    ):
        raise ValueError("P06 exact comparison evidence drift")
    if predicate is not None and observed["numeric_mode"] != predicate.get("numeric_mode", "exact"):
        raise ValueError("P06 numeric mode differs from its frozen predicate")
    sources = observed.get("precision_sources")
    if not isinstance(sources, Mapping) or set(sources) != {"before", "after", "delta"} or any(
        value not in ({"integer", "json_number_text", "frozen_number_text"} if key == "delta" else {"integer", "json_number_text"})
        for key, value in sources.items()
    ):
        raise ValueError("P06 exact precision evidence drift")


def validate_arithmetic_observed(observed: Mapping[str, Any], satisfied: bool, predicate: Mapping[str, Any] | None = None) -> None:
    """Validate safe arithmetic evidence without persisting operand values."""
    aggregate = "member_count" in observed
    linear_delta = predicate is not None and predicate.get("operator") == "linear_delta"
    expected_keys = {"numeric_mode", "values_equal", "precision_sources"} | ({"member_count"} if aggregate else set()) | ({"resource_count"} if linear_delta else set())
    if set(observed) != expected_keys or observed["numeric_mode"] not in {"exact", "approximate"} or observed["values_equal"] is not satisfied:
        raise ValueError("arithmetic comparison evidence drift")
    if predicate is not None and ((predicate["family"] == "P19") != aggregate or observed["numeric_mode"] != predicate.get("numeric_mode", "exact")):
        raise ValueError("arithmetic evidence differs from its frozen predicate")
    sources = observed["precision_sources"]
    if not isinstance(sources, Mapping):
        raise TypeError("arithmetic precision evidence is missing")
    if linear_delta:
        count = len(predicate["terms"])
        if observed["resource_count"] != count or set(sources) != {"output", *(f"{name}:{i}" for i in range(count) for name in ("before", "after", "coefficient"))}:
            raise ValueError("linear delta evidence does not cover every frozen resource")
    elif aggregate:
        count = observed["member_count"]
        if type(count) is not int or count < 0:
            raise ValueError("aggregate member count must be nonnegative")
        fields = ([name for name in ("item", "factor") if predicate.get(name) is not None] if predicate is not None
                  else sorted({name.split(":")[0] for name in sources if ":" in name}))
        if set(fields) - {"item", "factor"} or set(sources) != {"output", *(f"{name}:{index}" for name in fields for index in range(count))}:
            raise ValueError("aggregate precision evidence does not cover every member")
    elif set(sources) != {"left", "right", "output"}:
        raise ValueError("arithmetic precision evidence operands drift")
    for name, source in sources.items():
        allowed = {"integer", "json_number_text", "frozen_number_text"} if name in {"left", "right"} or linear_delta and (name == "output" or name.startswith("coefficient:")) else {"integer", "json_number_text"}
        if source not in allowed:
            raise ValueError("arithmetic precision evidence source drift")


def _arithmetic_units(predicate: Mapping[str, Any], names: set[str]) -> dict[str, str]:
    units = _frozen_rule(predicate, "units")
    if set(units) != names or any(type(unit) is not str or not unit.strip() for unit in units.values()):
        raise PredicateNotEvaluable("numeric_unit_missing", {})
    return units


def _evaluate_arithmetic(predicate: Mapping[str, Any], observations: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    if predicate["operator"] == "linear_delta":
        terms = predicate["terms"]
        units = _arithmetic_units(predicate, {"output", *(f"{phase}:{i}" for i in range(len(terms)) for phase in ("before", "after"))})
        output, source = _exact_operand(predicate["output"], observations)
        values, sources, coefficients = {"output": output}, {"output": source}, []
        for index, term in enumerate(terms):
            coefficient, source = _exact_operand(term["coefficient"], observations)
            coefficients.append(coefficient)
            sources[f"coefficient:{index}"] = source
            for phase in ("before", "after"):
                values[f"{phase}:{index}"], sources[f"{phase}:{index}"] = _exact_ref(term[phase], observations)
        values, units = _convert_numeric_inputs(predicate, values, units)
        if len(set(units.values())) != 1:
            raise PredicateNotEvaluable("numeric_unit_incompatible", {})
        expected = sum(coefficient * (values[f"after:{index}"] - values[f"before:{index}"]) for index, coefficient in enumerate(coefficients))
        satisfied = _numeric_result_equal(predicate, values["output"], expected)
        return satisfied, {"numeric_mode": predicate.get("numeric_mode", "exact"), "values_equal": satisfied, "precision_sources": sources, "resource_count": len(terms)}
    units = _arithmetic_units(predicate, {"left", "right", "output"})
    left, left_source = _exact_operand(predicate["left"], observations)
    right, right_source = _exact_operand(predicate["right"], observations)
    output, output_source = _exact_ref(predicate["output"], observations)
    values, units = _convert_numeric_inputs(predicate, {"left": left, "right": right, "output": output}, units)
    left, right, output = values["left"], values["right"], values["output"]
    operator = predicate["operator"]
    if operator in {"add", "subtract"} and len(set(units.values())) != 1:
        raise PredicateNotEvaluable("numeric_unit_incompatible", {})
    if operator == "divide" and right == 0:
        raise PredicateNotEvaluable("numeric_division_by_zero", {})
    expected = {"add": lambda: left + right, "subtract": lambda: left - right,
                "multiply": lambda: left * right, "divide": lambda: Fraction(left) / right}[operator]()
    satisfied = _numeric_result_equal(predicate, output, expected)
    return satisfied, {"numeric_mode": predicate.get("numeric_mode", "exact"), "values_equal": satisfied,
                       "precision_sources": {"left": left_source, "right": right_source, "output": output_source}}


def _evaluate_aggregation(
    predicate: Mapping[str, Any], observations: Mapping[str, Any], dependency_checker: Callable[..., None] | None,
) -> tuple[bool, dict[str, Any]]:
    collection = predicate["collection"]
    if predicate["scope"] != "actual_response":
        raise ValueError("P19 requires the declared complete actual response")
    if dependency_checker is not None:
        dependency_checker({"family": "P21", "target": collection, "expected_type": "array"})
        dependency_checker(predicate["output"])
    members = _collection(_resolve_value_ref(collection, observations))
    output, output_source = _exact_ref(predicate["output"], observations)
    operator = predicate["operator"]
    fields = [name for name in ("item", "factor") if predicate.get(name) is not None]
    units = _arithmetic_units(predicate, {*fields, "output"})
    sources = {"output": output_source}
    terms = []
    effective_units = units
    for index, member in enumerate(members):
        item_observation = NumericObservation({"body": member})
        lexical_root = getattr(observations[collection["role"]], "numeric_body", None)
        if lexical_root is not None:
            item_observation.numeric_body = get_path(lexical_root, collection["path"])[index]
        item_observations = {**observations, "item": item_observation}
        values: dict[str, int | Fraction] = {"output": output}
        for name in fields:
            ref = predicate[name]
            if dependency_checker is not None:
                dependency_checker(ref, item_bindings={"item": {"role": collection["role"], "path": f'{collection["path"]}.{index}'}})
            values[name], source = _exact_ref(ref, item_observations)
            sources[f"{name}:{index}"] = source
        values, effective_units = _convert_numeric_inputs(predicate, values, units)
        term = values.get("item", 1)
        if "factor" in fields:
            term *= values["factor"]
        terms.append(term)
    # Validate declared conversion/unit policy even for an empty array.
    zeros, effective_units = _convert_numeric_inputs(predicate, {name: 0 for name in units}, units)
    del zeros
    converted_output, _ = _convert_numeric_inputs(predicate, {**{name: 0 for name in fields}, "output": output}, units)
    output = converted_output["output"]
    if operator == "count":
        if fields or units["output"] != "items" or predicate.get("conversions") is not None:
            raise ValueError("count aggregation has only an items output unit")
        expected = len(members)
    else:
        if "item" not in fields or "factor" in fields and operator != "sum":
            raise ValueError("aggregation requires one field; only sum permits a product")
        if "factor" not in fields and effective_units["item"] != effective_units["output"]:
            raise PredicateNotEvaluable("numeric_unit_incompatible", {})
        if operator in {"min", "max"} and not terms:
            raise PredicateNotEvaluable("numeric_empty_extremum", {"member_count": 0})
        expected = {"sum": lambda: sum(terms), "min": lambda: min(terms), "max": lambda: max(terms)}[operator]()
    satisfied = _numeric_result_equal(predicate, output, expected)
    return satisfied, {"numeric_mode": predicate.get("numeric_mode", "exact"), "values_equal": satisfied,
                       "precision_sources": sources, "member_count": len(members)}


def exact_numeric_projection(value: Any, lexical_value: Any = None) -> Any:
    """Volatile typed projection for P06's existing V1 equivalence gates."""
    if type(value) is float:
        number, _ = _exact_number(value, lexical_value)
        return ("number", number)
    if isinstance(value, dict):
        return ("object", tuple((key, exact_numeric_projection(item, lexical_value.get(key) if isinstance(lexical_value, dict) else None)) for key, item in sorted(value.items())))
    if isinstance(value, list):
        return ("array", tuple(exact_numeric_projection(item, lexical_value[index] if isinstance(lexical_value, list) and index < len(lexical_value) else None) for index, item in enumerate(value)))
    return (_json_type(value), value)


def lint_predicate(
    predicate: Any,
    *,
    assertion: bool,
    improved: bool = False,
    enum_evidence: Mapping[str, Any] | None = None,
) -> LintResult:
    del improved, enum_evidence
    if not isinstance(predicate, dict):
        return LintResult("rejected_malformed", None, "predicate must be an object")
    value = copy.deepcopy(predicate)
    if "family" in value:
        from .v2_proposer import PrimaryPredicate

        try:
            typed = TypeAdapter(PrimaryPredicate).validate_python(value, strict=True)
        except ValidationError as exc:
            return LintResult("rejected_malformed", None, str(exc.errors()[0]["msg"]))
        return LintResult("pass", typed.model_dump(mode="json"))
    if not assertion:
        return LintResult("rejected_malformed", None, "predicate family is outside the approved DSL")
    kind = value.get("type")
    if kind == "status_success" and set(value) == {"type", "response_ref"} and _nonempty(value["response_ref"]):
        return LintResult("pass", value)
    if kind == "status_class" and set(value) == {
        "type", "response_ref", "expected_class"
    }:
        if (
            _nonempty(value["response_ref"])
            and value["expected_class"] in {"client_error", "success_or_client_error"}
        ):
            return LintResult("pass", value)
        return LintResult(
            "rejected_malformed", None,
            "status_class currently supports only client_error",
        )
    if kind == "schema_type" and set(value) == {"type", "response_ref", "target_path", "expected_type"}:
        if not _nonempty(value["response_ref"]) or not isinstance(value["target_path"], str):
            return LintResult("rejected_malformed", None, "schema_type refs and path must be strings")
        if (
            not isinstance(value["expected_type"], str)
            or value["expected_type"] not in JSON_TYPES
        ):
            return LintResult("rejected_malformed", None, "schema_type expected_type is outside the JSON type domain")
        return LintResult("pass", value)
    return LintResult("rejected_malformed", None, "predicate type is outside the approved DSL")


def evaluate_predicate(
    predicate: dict[str, Any], observations: Mapping[str, Any]
) -> tuple[bool, dict[str, Any]]:
    if predicate.get("family") in {"forall", "P15", "P16", "P19"} or (predicate.get("family") == "P18" and predicate.get("operator") == "pairwise_disjoint") or (
        predicate.get("family") == "P03" and predicate.get("operator") == "range"
    ):
        result = evaluate_predicate_result(predicate, observations)
        if result["satisfied"] is None:
            raise PredicateNotEvaluable(result["reason_code"], result["observed"])
        return result["satisfied"], result["observed"]
    if "family" in predicate:
        return _evaluate_canonical(predicate, observations)
    kind = predicate["type"]
    if kind == "status_success":
        status = _response(observations[predicate["response_ref"]]).get("status")
        return isinstance(status, int) and 200 <= status < 400, {"status": status}
    if kind == "status_class":
        status = _response(observations[predicate["response_ref"]]).get("status")
        return type(status) is int and (400 <= status < 500 or predicate["expected_class"] == "success_or_client_error" and 200 <= status < 300), {"status": status}
    target = get_path(_body(observations[predicate["response_ref"]]), predicate["target_path"])
    actual = _json_type(target)
    return actual == predicate["expected_type"], {
        "actual_type": actual,
        "expected_type": predicate["expected_type"],
    }


def evaluate_predicate_result(
    predicate: Mapping[str, Any],
    observations: Mapping[str, Any],
    *,
    dependency_checker: Callable[..., None] | None = None,
    item_bindings: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Evaluate one frozen proposition without losing independent counterexamples.

    Transport, response completeness, and role binding validity are established by
    the protocol before this function.  Dependency checks are local to each atom,
    so an unavailable operand cannot erase another conjunct's trustworthy false.
    """

    from .route_s_capture_redaction import SensitiveMaterialUnavailable

    try:
        if predicate.get("family") == "P20" and predicate.get("projection"):
            checks = []
            for path in predicate["projection"]:
                atom = copy.deepcopy(dict(predicate))
                atom["projection"] = []
                for name in ("left", "right"):
                    key = "field_path" if atom[name].get("source") == "collection_member" else "path"
                    atom[name][key] += "" if path == "$" else path.removeprefix("$")
                    # Individual preserved field types come from actual strict
                    # values; the enclosing object identity is fixed separately.
                try:
                    if not isinstance(_resolve_value_ref(predicate["left"], observations), dict) or not isinstance(_resolve_value_ref(predicate["right"], observations), dict):
                        raise TypeError("P20 projection requires object endpoints")
                    if dependency_checker is not None:
                        dependency_checker(atom, item_bindings=item_bindings)
                    left = _resolve_value_ref(atom["left"], observations)
                    right = _resolve_value_ref(atom["right"], observations)
                    state, reason = _strict_equal(left, right), None
                except (KeyError, TypeError, ValueError, SensitiveMaterialUnavailable) as error:
                    detail = _not_evaluable_result(error)
                    state, reason = None, detail["reason_code"]
                checks.append({"check_id": path, "satisfied": state, "observed": {}, "reason_code": reason})
            result = _conjunction_result(checks, {"checks": checks})
            if result["satisfied"] is not None:
                result["observed"]["equal"] = result["satisfied"]
            return result
        if predicate.get("family") == "forall":
            return _evaluate_forall(predicate, observations, dependency_checker)
        if predicate.get("family") == "P15":
            return _evaluate_uniqueness(predicate, observations, dependency_checker, item_bindings)
        if predicate.get("family") == "P16":
            return _evaluate_ordering(predicate, observations, dependency_checker)
        if predicate.get("family") == "P19":
            satisfied, observed = _evaluate_aggregation(predicate, observations, dependency_checker)
            return {"satisfied": satisfied, "observed": observed, "reason_code": None}
        if predicate.get("family") == "P18" and predicate.get("operator") == "pairwise_disjoint":
            return _evaluate_disjoint(predicate, observations, dependency_checker)
        if predicate.get("family") == "P03" and predicate["operator"] == "range":
            checks = []
            for bound, inclusive, closed_operator, open_operator in (
                ("lower", "lower_inclusive", "ge", "gt"),
                ("upper", "upper_inclusive", "le", "lt"),
            ):
                atom = {
                    "family": "P02", "left": predicate["target"],
                    "operator": closed_operator if predicate[inclusive] else open_operator,
                    "right": predicate[bound],
                }
                checks.append({
                    "check_id": bound,
                    **evaluate_predicate_result(
                        atom, observations, dependency_checker=dependency_checker,
                        item_bindings=item_bindings,
                    ),
                })
            return _conjunction_result(checks, {"checks": checks})
        if dependency_checker is not None:
            dependency_checker(predicate, item_bindings=item_bindings)
        satisfied, observed = evaluate_predicate(dict(predicate), observations)
        return {"satisfied": satisfied, "observed": observed, "reason_code": None}
    except PredicateNotEvaluable as exc:
        return {"satisfied": None, "observed": exc.observed, "reason_code": exc.reason_code}
    except (KeyError, TypeError, ValueError, OverflowError, SensitiveMaterialUnavailable) as exc:
        return _not_evaluable_result(exc)


def _not_evaluable_result(exc: Exception) -> dict[str, Any]:
    from .route_s_capture_redaction import SensitiveMaterialUnavailable

    if isinstance(exc, PredicateNotEvaluable):
        return {"satisfied": None, "observed": exc.observed, "reason_code": exc.reason_code}
    reason = (
        "sensitive_material_unavailable" if isinstance(exc, SensitiveMaterialUnavailable)
        else "identity_ambiguous" if isinstance(exc, ValueError) and "identity_ambiguous" in str(exc)
        else "identity_missing" if isinstance(exc, ValueError) and "identity_missing" in str(exc)
        else "predicate_operand_missing" if isinstance(exc, KeyError)
        else "predicate_operand_type_mismatch" if isinstance(exc, TypeError)
        else "predicate_operand_invalid"
    )
    return {
        "satisfied": None, "reason_code": reason,
        "observed": {"diagnostics": [{"reason_code": reason, "error_type": type(exc).__name__}]},
    }


def _conjunction_result(
    checks: list[dict[str, Any]], observed: dict[str, Any]
) -> dict[str, Any]:
    states = [check["satisfied"] for check in checks]
    satisfied = False if False in states else None if None in states else True
    return {
        "satisfied": satisfied, "observed": observed,
        "reason_code": "predicate_required_check_unknown" if satisfied is None else None,
    }


def _evaluate_forall(
    predicate: Mapping[str, Any], observations: Mapping[str, Any],
    dependency_checker: Callable[..., None] | None,
) -> dict[str, Any]:
    collection_ref = predicate["collection"]
    if predicate["scope"] not in {"actual_response", "finite_query_plan"}:
        raise ValueError("forall requires an explicit response or finite query scope")
    if dependency_checker is not None:
        dependency_checker({"family": "P21", "target": collection_ref, "expected_type": "array"})
    members = _collection(_resolve_value_ref(collection_ref, observations))
    checks: list[dict[str, Any]] = []
    applicable_count = 0
    for index, member in enumerate(members):
        item_observation = NumericObservation({"body": member})
        lexical_root = getattr(observations[collection_ref["role"]], "numeric_body", None)
        if lexical_root is not None:
            item_observation.numeric_body = get_path(lexical_root, collection_ref["path"])[index]
        item_observations = {**observations, "item": item_observation}
        bindings = {"item": {
            "role": collection_ref["role"],
            "path": f'{collection_ref["path"]}.{index}',
        }}
        guard = (
            evaluate_predicate_result(
                predicate["item_guard"], item_observations,
                dependency_checker=dependency_checker, item_bindings=bindings,
            ) if predicate.get("item_guard") is not None
            else {"satisfied": True, "observed": {}, "reason_code": None}
        )
        if guard["satisfied"] is not True:
            checks.append({
                "member_index": index, "guard": guard, "body": None,
                "satisfied": True if guard["satisfied"] is False else None,
                "reason_code": guard["reason_code"],
            })
            continue
        applicable_count += 1
        body = evaluate_predicate_result(
            predicate["body"], item_observations,
            dependency_checker=dependency_checker, item_bindings=bindings,
        )
        checks.append({
            "member_index": index, "guard": guard, "body": body,
            "satisfied": body["satisfied"], "reason_code": body["reason_code"],
        })
    parameter_checks = (
        _empty_forall_parameter_checks(predicate["body"], observations, dependency_checker)
        if applicable_count == 0 else []
    )
    if applicable_count == 0 and predicate.get("item_guard") is not None:
        parameter_checks.extend(
            {**check, "check_id": f'item_guard.{check["check_id"]}'}
            for check in _empty_forall_parameter_checks(
                predicate["item_guard"], observations, dependency_checker,
            )
        )
    return _conjunction_result(checks + parameter_checks, {
        "member_count": len(members), "applicable_member_count": applicable_count,
        "nonempty_support": applicable_count > 0, "checks": checks,
        "parameter_checks": parameter_checks,
    })


def _empty_forall_parameter_checks(
    body: Mapping[str, Any], observations: Mapping[str, Any],
    dependency_checker: Callable[..., None] | None,
) -> list[dict[str, Any]]:
    """An empty domain does not manufacture an unavailable external parameter."""

    from .route_s_capture_redaction import SensitiveMaterialUnavailable

    fields = (
        ("right",) if body["family"] in {"P02", "P09", "P11"}
        else ("lower", "upper") if body["family"] == "P03" and body["operator"] == "range"
        else ("domain",) if body["family"] == "P03"
        else ()
    )
    checks = []
    for field in fields:
        operand = body[field]
        if operand.get("ref", {}).get("role") == "item":
            continue
        try:
            if dependency_checker is not None:
                dependency_checker(operand)
            value = _resolve_operand(operand, observations)
            if body["family"] == "P03" and body["operator"] == "in":
                _collection(value)
            elif body["family"] == "P09":
                if type(value) is not str:
                    raise TypeError("string relation requires a string reference")
            elif body["family"] == "P11":
                if type(value) is not int:
                    raise TypeError("count/length requires an integer threshold")
            elif body.get("operator") not in {"eq", "neq"} and not _json_number(value):
                raise TypeError("numeric comparison requires finite JSON numbers, excluding booleans")
            result = {"satisfied": True, "observed": {}, "reason_code": None}
        except (KeyError, TypeError, ValueError, OverflowError, SensitiveMaterialUnavailable) as exc:
            result = _not_evaluable_result(exc)
        checks.append({"check_id": field, **result})
    return checks


class UnsupportedTextPattern(ValueError):
    """A preserved pattern outside the implemented standard-library subset."""


@lru_cache(maxsize=128)
def validate_text_pattern(pattern: str) -> tuple[int, re.Pattern[str]]:
    """Admit a fixed-width concatenation; matching stays in the standard library.

    Python re syntax: literal characters, escaped punctuation, explicit character
    classes/ranges, and exact bounded repetition {n}. No alternation, groups,
    variable repetition, lookaround, backreferences or inline flags. Each token
    consumes a fixed number of code points, so there is no combinatorial search.
    The library's own repetition bound applies; no candidate/input cap is added.
    """
    token = re.compile(r"(?:[^.\^$*+?{}\[\]()|\\]|\\[.\^$*+?{}\[\]()|\\\-]|\[(?:[A-Za-z0-9 _]|[A-Za-z0-9]-[A-Za-z0-9])+\])(?:\{(?P<count>0|[1-9][0-9]*)\})?")
    position, width = 0, 0
    while position < len(pattern):
        match = token.match(pattern, position)
        if match is None:
            raise UnsupportedTextPattern("unsupported_text_pattern: requires literal/class concatenation and exact bounded repetition")
        try:
            width += int(match["count"]) if match["count"] is not None else 1
        except ValueError as exc:
            raise UnsupportedTextPattern("unsupported_text_pattern: repeat integer outside Python parsing limits") from exc
        position = match.end()
    try:
        compiled = re.compile(pattern, flags=0)
    except (re.error, OverflowError) as exc:
        raise UnsupportedTextPattern("unsupported_text_pattern: outside standard-library syntax or repetition bound") from exc
    return width, compiled


def _collection_keys(predicate: Mapping[str, Any], ref: Mapping[str, Any], observations: Mapping[str, Any]) -> list[Any]:
    """Keep exact numeric members in memory while retaining strict JSON types."""
    members = _collection(_resolve_value_ref(ref, observations))
    lexical_root = getattr(observations[ref["role"]], "numeric_body", None)
    lexical_members = get_path(lexical_root, ref["path"]) if lexical_root is not None else None
    basis = predicate.get("comparison_basis", "identity_tuple")
    paths = None if basis == "full_json_value" else predicate["projection"] if basis == "frozen_projection" else predicate["identity"]["paths"]
    keys = []
    for index, member in enumerate(members):
        lexical_member = lexical_members[index] if isinstance(lexical_members, list) and index < len(lexical_members) else None
        try:
            if paths is None:
                keys.append(exact_numeric_projection(member, lexical_member))
            else:
                projected = []
                for path in paths:
                    try:
                        lexical_value = get_path(lexical_member, path) if lexical_member is not None else None
                    except KeyError:
                        lexical_value = None
                    projected.append(exact_numeric_projection(get_path(member, path), lexical_value))
                keys.append(tuple(projected))
        except PredicateNotEvaluable as exc:
            raise PredicateNotEvaluable(exc.reason_code, {"diagnostics": [{"reason_code": exc.reason_code, "error_type": type(exc).__name__}]}) from exc
    return keys


def _collection_relation(predicate: Mapping[str, Any], observations: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    left = _collection_keys(predicate, predicate["left"], observations)
    right = _collection_keys(predicate, predicate["right"], observations)
    representation = predicate.get("representation", "set")
    if representation == "set":
        left_value, right_value = set(left), set(right)
    elif representation == "multiset":
        left_value, right_value = Counter(left), Counter(right)
    elif representation == "sequence":
        left_value, right_value = left, right
    else:
        raise ValueError("unsupported collection representation")
    operator = predicate["operator"]
    if operator != "equal" and representation != "set":
        raise ValueError("subset and superset require set representation")
    satisfied = {"equal": lambda: left_value == right_value, "subset": lambda: left_value <= right_value,
                 "superset": lambda: left_value >= right_value}[operator]()
    return satisfied, {"relation": satisfied, "representation": representation,
                       "comparison_basis": predicate.get("comparison_basis", "identity_tuple"),
                       "left_count": len(left), "right_count": len(right)}


def _evaluate_ordering(
    predicate: Mapping[str, Any], observations: Mapping[str, Any], dependency_checker: Callable[..., None] | None,
) -> dict[str, Any]:
    from .route_s_capture_redaction import SensitiveMaterialUnavailable

    checks = []
    try:
        after = predicate["after"]
        if dependency_checker is not None:
            dependency_checker({"family": "P21", "target": after, "expected_type": "array"})
        members = _collection(_resolve_value_ref(after, observations))
        key_results = []
        for index, member in enumerate(members):
            try:
                path = predicate["key"]
                if dependency_checker is not None:
                    dependency_checker({"role": after["role"], "path": f'{after["path"]}.{index}{path.removeprefix("$")}'})
                value = get_path(member, path)
                if value is not None and type(value) is not str and not _json_number(value):
                    raise TypeError("sort keys require strings, finite numbers or explicit null")
                if _json_number(value):
                    value, _ = _exact_ref({"role": after["role"], "path": f'{after["path"]}.{index}{path.removeprefix("$")}', "value_type": "number"}, observations)
                key_results.append((value, None))
            except (KeyError, TypeError, ValueError, OverflowError, SensitiveMaterialUnavailable) as exc:
                key_results.append((None, _not_evaluable_result(exc)))
        order_checks = []
        # An unavailable key is required even in a one-member collection.
        for index, (_, missing) in enumerate(key_results):
            if missing is not None:
                order_checks.append({"member_index": index, **missing})
        for index in range(1, len(key_results)):
            left, left_missing = key_results[index - 1]
            right, right_missing = key_results[index]
            if left_missing is not None or right_missing is not None:
                continue
            try:
                if left is None or right is None:
                    ordered = left is right or (left is None) == (predicate["nulls"] == "first")
                elif isinstance(left, str) != isinstance(right, str):
                    raise TypeError("sort keys must have comparable types")
                else:
                    ordered = left <= right if predicate["direction"] == "asc" else left >= right
                detail = {"satisfied": ordered, "observed": {}, "reason_code": None}
            except TypeError as exc:
                detail = _not_evaluable_result(exc)
            order_checks.append({"member_index": index, "previous_index": index - 1, **detail})
        order = _conjunction_result(order_checks, {"member_count": len(members), "ordering_checks": order_checks})
    except (KeyError, TypeError, ValueError, OverflowError, SensitiveMaterialUnavailable) as exc:
        order = _not_evaluable_result(exc)
    checks.append({"check_id": "order", **order})
    preserving = {"family": "P17", "operator": "equal", "left": predicate["before"], "right": predicate["after"],
                  "representation": "multiset", "comparison_basis": predicate.get("comparison_basis", "full_json_value"),
                  "projection": predicate.get("projection"), "identity": predicate.get("identity")}
    checks.append({"check_id": "multiset", **evaluate_predicate_result(preserving, observations, dependency_checker=dependency_checker)})
    return _conjunction_result(checks, {"checks": checks})


def _evaluate_disjoint(
    predicate: Mapping[str, Any], observations: Mapping[str, Any], dependency_checker: Callable[..., None] | None,
) -> dict[str, Any]:
    from .route_s_capture_redaction import SensitiveMaterialUnavailable

    partitions = []
    for ref in predicate["partitions"]:
        try:
            if dependency_checker is not None:
                dependency_checker(ref)
            keys = set(_collection_keys(predicate, ref, observations))
            partitions.append((keys, None))
        except (KeyError, TypeError, ValueError, OverflowError, SensitiveMaterialUnavailable) as exc:
            partitions.append((set(), _not_evaluable_result(exc)))
    checks = []
    for index, (left, left_error) in enumerate(partitions):
        for right_index in range(index + 1, len(partitions)):
            right, right_error = partitions[right_index]
            result = left_error or right_error or {"satisfied": not bool(left & right), "observed": {}, "reason_code": None}
            checks.append({"left_partition": index, "right_partition": right_index, **result})
    return _conjunction_result(checks, {"partition_checks": checks})


def _evaluate_uniqueness(
    predicate: Mapping[str, Any], observations: Mapping[str, Any],
    dependency_checker: Callable[..., None] | None,
    item_bindings: Mapping[str, Mapping[str, str]] | None,
) -> dict[str, Any]:
    from .route_s_capture_redaction import SensitiveMaterialUnavailable

    collection = predicate["collection"]
    if dependency_checker is not None:
        dependency_checker({"family": "P21", "target": collection, "expected_type": "array"}, item_bindings=item_bindings)
    members = _collection(_resolve_value_ref(collection, observations))
    lexical_root = getattr(observations[collection["role"]], "numeric_body", None)
    lexical_members = get_path(lexical_root, collection["path"]) if lexical_root is not None else None
    seen: dict[Any, int] = {}
    checks = []
    for index, member in enumerate(members):
        duplicate_of = None
        try:
            values = []
            lexical_member = lexical_members[index] if isinstance(lexical_members, list) and index < len(lexical_members) else None
            for path in predicate["identity"]["paths"]:
                if dependency_checker is not None:
                    suffix = "" if path == "$" else path.removeprefix("$")
                    dependency_checker({"role": collection["role"], "path": f'{collection["path"]}.{index}{suffix}'}, item_bindings=item_bindings)
                try:
                    lexical_value = get_path(lexical_member, path) if lexical_member is not None else None
                except KeyError:
                    lexical_value = None
                values.append(exact_numeric_projection(get_path(member, path), lexical_value))
            key = tuple(values)
            duplicate_of = seen.get(key)
            if duplicate_of is None:
                seen[key] = index
            satisfied, reason = duplicate_of is None, None
        except (KeyError, TypeError, ValueError, OverflowError, SensitiveMaterialUnavailable) as exc:
            result = _not_evaluable_result(exc)
            satisfied, reason = None, result["reason_code"]
        checks.append({"member_index": index, "duplicate_of": duplicate_of, "satisfied": satisfied, "reason_code": reason})
    return _conjunction_result(checks, {"member_count": len(members), "uniqueness_checks": checks})


def is_workflow_effect_predicate(predicate: Mapping[str, Any]) -> bool:
    """The finite before/write/after additions; callers also require V4."""
    return predicate.get("family") in {"P01", "P02", "P06", "P07", "P20", "repeat_equal", "repeat_rejected", "repeat_delta"} or (
        predicate.get("family") == "P04"
        and predicate.get("from_value", {}).get("source") != "transition_fact"
    )


def workflow_applicability_predicate(predicate: Mapping[str, Any]) -> dict[str, Any] | None:
    if predicate.get("family") != "P04" or not is_workflow_effect_predicate(predicate):
        return None
    return {"family": "P02", "operator": "eq", "left": predicate["before"], "right": predicate["from_value"]}


def evaluate_workflow_applicability(
    predicate: Mapping[str, Any], observations: Mapping[str, Any],
    *, dependency_checker: Callable[..., None] | None = None,
) -> dict[str, Any] | None:
    """Check the frozen from-state before sending the workflow action."""
    atom = workflow_applicability_predicate(predicate)
    if atom is None:
        return None
    try:
        if dependency_checker is not None:
            dependency_checker(atom)
        before = _resolve_value_ref(predicate["before"], observations)
        expected = _resolve_operand(predicate["from_value"], observations)
        _require_operand_type(before, predicate["before"]["value_type"])
        _require_operand_type(expected, predicate["before"]["value_type"])
        matched = _compare_values(before, expected, "eq")
        return {"status": "satisfied" if matched else "not_evaluable",
                "observed": {"before_matches": matched},
                "reason_code": None if matched else "workflow_from_not_established"}
    except (KeyError, TypeError, ValueError) as error:
        reason = ("identity_ambiguous" if "identity_ambiguous" in str(error) else "identity_missing" if "identity_missing" in str(error)
                  else "path_missing" if isinstance(error, KeyError) else "type_mismatch" if isinstance(error, TypeError) else "identity_missing")
        return {"status": "not_evaluable", "observed": {}, "reason_code": reason}


def _compare_values(left: Any, right: Any, operator: str) -> bool:
    if operator in {"eq", "neq"}:
        equal = _strict_equal(left, right)
        return equal if operator == "eq" else not equal
    if not all(_json_number(value) for value in (left, right)):
        raise TypeError("numeric comparison requires finite JSON numbers, excluding booleans")
    return {"numeric_eq": lambda: left == right, "numeric_neq": lambda: left != right,
            "lt": lambda: left < right, "le": lambda: left <= right,
            "gt": lambda: left > right, "ge": lambda: left >= right}[operator]()


def _evaluate_canonical(
    predicate: Mapping[str, Any], observations: Mapping[str, Any]
) -> tuple[bool, dict[str, Any]]:
    family = str(predicate["family"])
    if family == "P01":
        if predicate["target"]["role"] in {"observation", "item"} and predicate["member"] is None:
            present, _ = _observation_field(predicate["target"], observations)
            expected = predicate["operator"] == "present"
            return present is expected, {"present": present, "expected_present": expected}
        if predicate["target"]["value_type"] == "object":
            response = observations[predicate["target"]["role"]]
            status = response.get("status")
            if status in predicate.get("absent_statuses", []):
                return predicate["operator"] == "absent", {"actual": False, "expected": predicate["operator"] == "exists"}
            if type(status) is not int or not 200 <= status < 300:
                raise PredicateNotEvaluable("point_resource_observation_unavailable", {})
            present, value = _observation_field(predicate["target"], observations)
            if present and type(value) is not dict:
                raise TypeError("point resource must be a JSON object")
            return present is (predicate["operator"] == "exists"), {"actual": present, "expected": predicate["operator"] == "exists"}
        target = _resolve_value_ref(predicate["target"], observations)
        actual = (
            target is True
            if predicate["member"] is None
            else _strict_member_count(
                target,
                _resolve_operand(predicate["member"], observations),
                predicate["identity"],
            ) == 1
        )
        expected = predicate["operator"] == "exists"
        return actual is expected, {"actual": actual, "expected": expected}
    if family == "P02":
        left = _resolve_value_ref(predicate["left"], observations)
        right = _resolve_operand(predicate["right"], observations)
        return _compare_values(left, right, predicate["operator"]), {"left": left, "right": right}
    if family == "P03":
        target = _resolve_value_ref(predicate["target"], observations)
        domain = _collection(_resolve_operand(predicate["domain"], observations))
        return any(_strict_equal(target, value) for value in domain), {"target": target, "domain": domain}
    if family == "P04":
        applicability = evaluate_workflow_applicability(predicate, observations)
        if applicability is not None and applicability["status"] != "satisfied":
            raise PredicateNotEvaluable(applicability["reason_code"], applicability["observed"])
        before = _resolve_value_ref(predicate["before"], observations)
        after = _resolve_value_ref(predicate["after"], observations)
        expected_before = (predicate["from_value"]["value"] if predicate["from_value"].get("source") == "transition_fact" else _resolve_operand(predicate["from_value"], observations))
        expected_after = (predicate["to_value"]["value"] if predicate["to_value"].get("source") == "transition_fact" else _resolve_operand(predicate["to_value"], observations))
        for value in (before, after, expected_before, expected_after):
            _require_operand_type(value, predicate["before"]["value_type"])
        after_matches = _compare_values(after, expected_after, "eq")
        if applicability is not None:
            return after_matches, {"applicability_satisfied": True, "after_matches": after_matches}
        satisfied = (_compare_values(before, expected_before, "eq") and after_matches
                     and _compare_values(before, after, "neq"))
        return satisfied, {"before": before, "after": after,
                           "expected_before": expected_before, "expected_after": expected_after}
    if family == "P07":
        before = _resolve_value_ref(predicate["before"], observations)
        after = _resolve_value_ref(predicate["after"], observations)
        _require_operand_type(before, predicate["before"]["value_type"])
        _require_operand_type(after, predicate["after"]["value_type"])
        satisfied = _compare_values(after, before, predicate["operator"])
        return satisfied, {"direction_satisfied": satisfied}
    if family == "P06":
        return evaluate_numeric_delta(predicate, observations)
    if family == "P08":
        return _evaluate_arithmetic(predicate, observations)
    if family == "P09":
        target = _resolve_value_ref(predicate["target"], observations)
        right = _resolve_operand(predicate["right"], observations)
        if type(target) is not str or type(right) is not str:
            raise TypeError("string relation requires strings without coercion")
        satisfied = {"contains": lambda: right in target, "prefix": lambda: target.startswith(right), "suffix": lambda: target.endswith(right)}[predicate["operator"]]()
        return satisfied, {"left": target, "right": right}
    if family == "P10":
        target = _resolve_value_ref(predicate["target"], observations)
        if type(target) is not str:
            raise TypeError("format requires a string operand")
        if predicate["format"] == "date_yyyy_mm_dd":
            satisfied = False
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", target) is not None:
                try:
                    date.fromisoformat(target)
                    satisfied = True
                except ValueError:
                    pass
        else:
            pattern = predicate["pattern"]["value"]
            width, compiled = validate_text_pattern(pattern)
            satisfied = len(target) == width and compiled.fullmatch(target) is not None
        return satisfied, {"format_valid": satisfied}
    if family == "P11":
        if predicate.get("collection") is not None:
            actual = len(_collection(_resolve_value_ref(predicate["collection"], observations)))
            limit = parse_query_limit(_request_operand_value(predicate["right"]["ref"], observations))
            return actual <= limit, {"actual_count": actual, "request_limit": limit}
        target = _resolve_value_ref(predicate["target"], observations)
        threshold = _resolve_operand(predicate["right"], observations)
        if type(threshold) is not int:
            raise TypeError("count/length requires an exact integer threshold")
        if predicate["projection"] == "count":
            actual = len(_collection(target))
        else:
            if type(target) is not str:
                raise TypeError("length requires a string operand")
            if predicate["newline"] == "html_textarea_api":
                target = target.replace("\r\n", "\n").replace("\r", "\n")
            actual = len(target) if predicate["unit"] == "unicode_code_point" else sum(2 if ord(char) > 0xffff else 1 for char in target)
        satisfied = (
            True if predicate.get("empty") == "allow" and target == ""
            else {"eq": lambda: actual == threshold, "neq": lambda: actual != threshold,
                  "lt": lambda: actual < threshold, "le": lambda: actual <= threshold,
                  "gt": lambda: actual > threshold, "ge": lambda: actual >= threshold}[predicate["operator"]]()
        )
        return satisfied, {"measured_value": actual, "threshold": threshold}
    if family == "P12":
        before = len(
            _collection(_resolve_value_ref(predicate["before"], observations))
        )
        after = len(
            _collection(_resolve_value_ref(predicate["after"], observations))
        )
        actual = after - before
        return actual == predicate["delta"], {
            "before_count": before,
            "after_count": after,
            "actual_delta": actual,
        }
    if family == "P13":
        if predicate.get("identity") is None:
            collection_ref = predicate["collection"]
            collection = _collection(_resolve_value_ref(collection_ref, observations))
            member = _resolve_operand(predicate["member"], observations)
            if type(member) in {list, dict}:
                raise TypeError("scalar membership requires a JSON scalar")
            member_key = (("number", _exact_operand(predicate["member"], observations)[0])
                          if type(member) is float else exact_numeric_projection(member))
            lexical_root = getattr(observations[collection_ref["role"]], "numeric_body", None)
            lexical_members = get_path(lexical_root, collection_ref["path"]) if lexical_root is not None else None
            matches, diagnostics = 0, []
            for index, item in enumerate(collection):
                if _json_type(item) != _json_type(member):
                    continue
                lexical_value = lexical_members[index] if isinstance(lexical_members, list) and index < len(lexical_members) else None
                try:
                    matches += exact_numeric_projection(item, lexical_value) == member_key
                except (TypeError, ValueError, OverflowError) as exc:
                    result = _not_evaluable_result(exc)
                    diagnostics.append({"reason_code": result["reason_code"], "error_type": type(exc).__name__})
            expected = predicate["operator"] == "contains"
            observed = {"matches": matches, "expected_present": expected}
            if diagnostics:
                observed["diagnostics"] = diagnostics
                if not matches:
                    raise PredicateNotEvaluable(diagnostics[0]["reason_code"], observed)
            return (matches > 0) is expected, observed
        matches = _strict_member_count(
            _resolve_value_ref(predicate["collection"], observations),
            _resolve_operand(predicate["member"], observations),
            predicate["identity"],
        )
        expected = predicate["operator"] == "contains"
        return (matches == 1) is expected, {
            "matches": matches,
            "expected": 1 if expected else 0,
        }
    if family == "P17":
        return _collection_relation(predicate, observations)
    if family == "P18":
        def identities(ref: Mapping[str, Any]) -> dict[Any, tuple[Any, ...]]:
            # Keys retain exact lexical values only in memory. Existing evidence
            # keeps ordinary JSON identities and never serializes Fraction.
            keys = _collection_keys(predicate, ref, observations)
            values = _collection_identities(_resolve_value_ref(ref, observations), predicate["identity"])
            return dict(zip(keys, values))
        source = identities(predicate["source"])
        partitions = [identities(ref) for ref in predicate["partitions"]]
        overlaps = [
            list(left[key])
            for index, left in enumerate(partitions)
            for right in partitions[index + 1:]
            for key in left if key in right
        ]
        union = {key: value for part in partitions for key, value in part.items()}
        remainder = {key: value for key, value in source.items() if key not in union}
        if predicate["operator"] == "complete_union":
            satisfied = source.keys() == union.keys()
        else:
            expected = identities(predicate["expected_remainder"])
            satisfied = remainder.keys() == expected.keys()
        return satisfied, {
            "source_ids": [list(item) for item in source.values()],
            "partition_ids": [[list(item) for item in part.values()] for part in partitions],
            "overlaps": overlaps,
            "union": [list(item) for item in union.values()],
            "remainder": [list(item) for item in remainder.values()],
        }
    if family == "P20":
        left = _resolve_value_ref(predicate["left"], observations)
        right = _resolve_value_ref(predicate["right"], observations)
        if _json_type(left) != predicate["left"]["value_type"]:
            raise TypeError("P20 left projection type mismatch")
        if _json_type(right) != predicate["right"]["value_type"]:
            raise TypeError("P20 right projection type mismatch")
        if predicate.get("projection"):
            checks = []
            for path in predicate["projection"]:
                try:
                    state = _strict_equal(get_path(left, path), get_path(right, path))
                    reason = None
                except (KeyError, TypeError):
                    state, reason = None, "projection_field_missing"
                checks.append({"check_id": path, "satisfied": state, "observed": {}, "reason_code": reason})
            result = _conjunction_result(checks, {"checks": checks})
            if result["satisfied"] is None:
                raise PredicateNotEvaluable(result["reason_code"], result["observed"])
            return result["satisfied"], {**result["observed"], "equal": result["satisfied"]}
        equal = _strict_equal(left, right)
        return equal, {"left": left, "right": right, "equal": equal}
    if family == "P21":
        present, value = _observation_field(predicate["target"], observations)
        actual_type = _json_type(value) if present else "missing"
        return actual_type == predicate["expected_type"], {
            "actual_type": actual_type,
            "expected_type": predicate["expected_type"],
        }
    before_count = _strict_member_count(
        _resolve_value_ref(predicate["before"], observations),
        _resolve_operand(predicate["member"], observations),
        predicate["identity"],
    )
    after_count = _strict_member_count(
        _resolve_value_ref(predicate["after"], observations),
        _resolve_operand(predicate["member"], observations),
        predicate["identity"],
    )
    if predicate["operator"] == "removed" and before_count == 0:
        raise ValueError("p14_removed_baseline_missing")
    expected = (0, 1) if predicate["operator"] == "added" else (1, 0)
    return (before_count, after_count) == expected, {
        "before": before_count,
        "after": after_count,
        "expected": list(expected),
    }


def merge_followup_observation(
    predicate: Mapping[str, Any], observations: Mapping[str, Any], *, roles: list[str] | None = None,
) -> dict[str, Any]:
    """Materialize an array in frozen plan order without deduplicating members."""

    if predicate["family"] not in {"P15", "P19", "forall"}:
        return {"body": {}}
    path = str(predicate["collection"]["path"])
    if roles is None:
        roles = [role for role in observations if role.startswith("followup_query:")]
    values = [
        _collection(get_path(observations[role]["body"], path)) for role in roles
    ]
    def containing_body(items: list[Any]) -> Any:
        if path == "$":
            return items
        body: dict[str, Any] = {}
        current = body
        tokens = path.removeprefix("$.").split(".")
        for token in tokens[:-1]:
            current[token] = {}
            current = current[token]
        current[tokens[-1]] = items
        return body
    result = NumericObservation({"body": containing_body([item for value in values for item in value])})
    if any(hasattr(observations[role], "numeric_body") for role in roles):
        # Plain fallback leaves a float a float. It never fabricates Decimal
        # provenance, and exact evaluation still rejects that individual value.
        result.numeric_body = containing_body([
            item for role in roles
            for item in _collection(get_path(getattr(observations[role], "numeric_body", observations[role]["body"]), path))
        ])
    return result


def get_path(value: Any, path: str | None) -> Any:
    if not path or path == "$":
        return value
    current = value
    for token in str(path).removeprefix("$.").split("."):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise KeyError(path)
    return current


def _resolve_operand(operand: Mapping[str, Any], observations: Mapping[str, Any]) -> Any:
    if operand.get("source") == "hypothesis":
        value = operand["value"]
        if _json_type(value) != operand["value_type"]:
            raise TypeError("hypothesis does not match its declared JSON type")
        return value
    if operand.get("source") == "request":
        ref = operand["ref"]
        return parse_request_value(
            _request_operand_value(ref, observations),
            str(ref["value_type"]), str(ref["location"]),
        )
    return _resolve_value_ref(operand["ref"], observations)


def _request_operand_value(ref: Mapping[str, Any], observations: Mapping[str, Any]) -> Any:
    observation = _response(observations[ref["role"]])
    request = _response(observation.get("request", observation))
    return get_path(request[ref["location"]], ref["path"])


def _require_operand_type(value: Any, value_type: str) -> None:
    valid = (
        _json_number(value) if value_type == "number"
        else _json_type(value) == value_type
    )
    if not valid:
        raise TypeError("operand does not match its declared JSON type")


def parse_request_value(value: Any, value_type: str, location: str) -> Any:
    """Parse only the declared, actually sent location; never infer defaults.

    URL/header scalars use JSON lexical syntax.  Integer tokens stay exact;
    fractional/exponent tokens use ordinary parsed JSON floats and do not claim
    exact decimal business arithmetic.  JSON bodies retain their actual types.
    """

    if location not in {"query", "body", "path", "headers"}:
        raise ValueError("unsupported request operand location")
    if location == "body":
        if _json_type(value) != value_type:
            raise TypeError("request body operand does not match its declared JSON type")
        return value
    if isinstance(value, str) and value_type != "string":
        if value_type == "integer" and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value):
            value = int(value)
        elif value_type == "number" and re.fullmatch(
            r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value
        ):
            value = json.loads(value)
        elif value_type == "boolean" and value in {"true", "false"}:
            value = value == "true"
        elif value_type == "null" and value == "null":
            value = None
        else:
            raise TypeError("request operand has no unambiguous scalar lexical representation")
    _require_operand_type(value, value_type)
    return value


def parse_query_limit(value: Any) -> int:
    """Read one nonnegative integer query limit without numeric coercion."""

    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value):
        return int(value)
    raise TypeError("query limit must be one nonnegative integer")


def _observation_field(
    ref: Mapping[str, Any], observations: Mapping[str, Any]
) -> tuple[bool, Any]:
    # Obtaining the response is a prerequisite.  Only the tested field's
    # absence is a predicate result; a missing observation/body is not absence.
    body = _response(observations[ref["role"]])["body"]
    try:
        return True, get_path(body, ref["path"])
    except KeyError:
        return False, None


def _resolve_value_ref(ref: Mapping[str, Any], observations: Mapping[str, Any]) -> Any:
    role = str(ref["role"])
    observation = observations[role]
    if role == "producer_request":
        # The logical request body lives under "body" (recorded-domain aliases,
        # the same domain as the normalized observations); the physical
        # transport request under "request" carries fresh alias values and
        # must not be compared against normalized response collections.
        if isinstance(observation, Mapping) and "body" in observation:
            value = observation["body"]
        else:
            value = observation.get("request", observation)
            value = value.get("body") if isinstance(value, Mapping) and "body" in value else value
    elif role in {"producer_status", "after_status"}:
        value = observation.get("body", observation.get("status"))
    elif role == "producer_response":
        value = _body(observation.get("response", observation))
    elif role == "observation":
        value = _response(observation)["body"]
    else:
        value = _body(observation)
    if ref.get("source") == "collection_member":
        collection = get_path(value, str(ref["collection_path"]))
        member = _resolve_operand(ref["member"], observations)
        item = _strict_identity_member(collection, member, ref["identity"])
        return get_path(item, str(ref["field_path"]))
    return get_path(value, str(ref["path"]))


def _strict_member_count(collection: Any, member: Any, identity: Mapping[str, Any]) -> int:
    item = _strict_identity_member(collection, member, identity, missing_ok=True)
    return 0 if item is _MISSING else 1


_MISSING = object()


def _strict_identity_member(
    collection: Any,
    member: Any,
    identity: Mapping[str, Any],
    *,
    missing_ok: bool = False,
) -> Any:
    values = _collection(collection)
    field_pairs = identity["field_pairs"]
    expected = tuple(
        get_path(member, pair["member_path"])
        for pair in field_pairs
    )
    matches: list[Any] = []
    for item in values:
        try:
            actual = tuple(
                get_path(item, pair["collection_item_path"])
                for pair in field_pairs
            )
        except (KeyError, TypeError, ValueError):
            continue
        if all(_strict_equal(left, right) for left, right in zip(actual, expected)):
            matches.append(item)
    if len(matches) > 1:
        raise ValueError("predicate_identity_ambiguous")
    if not matches:
        if missing_ok:
            return _MISSING
        raise KeyError("predicate_identity_missing")
    return matches[0]


def _collection_identities(collection: Any, identity: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    paths = identity["paths"]
    return [
        (item,) if not isinstance(item, Mapping) and len(paths) == 1
        else tuple(get_path(item, path) for path in paths)
        for item in _collection(collection)
    ]


def _strict_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _strict_equal(left[key], right[key]) for key in left
        )
    return left == right


def _json_number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _collection(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError("predicate collection must be an array")
    return value


def _response(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("observation must be an object")
    return dict(value)


def _body(value: Any) -> Any:
    return _response(value).get("body")


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite value is outside JSON")
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError("value is outside JSON")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)
