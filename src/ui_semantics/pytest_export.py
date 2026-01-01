"""Deterministic pytest representation of a frozen M14 business suite.

This module is deliberately downstream of M14.  It renders readable Python
tests, then executes their exact frozen M13 definitions through the existing
normal-state calibration runtime.  It does not re-derive predicates, protocol
semantics, outcomes, or retention.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pprint
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from stage2_recover.loader import LoadedBundle, load_bundle
from stage6_ground.relation_test_execution import execute_certified_relation_test

from .contracts import UiApiTrace
from .current_adapter import (
    DeterministicFixtureRuntimeConfig,
    load_current_adapter,
    resolve_current_request_bindings,
    resolve_recording_material_aliases,
)
from .current_calibration import (
    _is_candidate_local_execution_error,
    validate_final_calibrated_suite,
)
from .current_route_s import canonical_json_bytes, validate_current_route_s_material
from .current_runtime_factory import build_current_runtime_factory
from .dsl import workflow_applicability_predicate
from .m11b_materializer import RouteSPreLiveMaterializedCandidate
from .relation_phase_b import (
    canonical_sha256,
    classify_assertion_layer,
    generic_baseline_overlap,
    validate_certified_relation_tests,
)
from .v2_proposer import _scientific_relation_payload


_FUNCTION_NAME = re.compile(r"[^a-zA-Z0-9_]+")
SCHEMA_TYPE_ASSERTION_SCOPE = (
    "schema_type checks only the JSON type at one frozen target JSONPath; "
    "it is not full response-schema or OpenAPI validation."
)


@dataclass(frozen=True)
class ExportedPytestCase:
    test_id: str
    candidate_id: str
    protocol_kind: str
    normal_runs: int
    source_test_sha256: str
    steps: tuple[dict[str, Any], ...]
    assertions: tuple[dict[str, Any], ...]
    business_summary: str
    canonical_relation_core_identity: str | None = None
    rationale_sources: tuple[dict[str, Any], ...] = ()

    def comparison_payload(self) -> dict[str, Any]:
        """Return only the frozen executable definition checked at runtime."""

        return {
            "test_id": self.test_id,
            "candidate_id": self.candidate_id,
            "protocol_kind": self.protocol_kind,
            "normal_runs": self.normal_runs,
            "source_test_sha256": self.source_test_sha256,
            "steps": [copy.deepcopy(row) for row in self.steps],
            "assertions": [copy.deepcopy(row) for row in self.assertions],
        }

    def reporting_payload(self) -> dict[str, Any]:
        producer = next(
            (
                copy.deepcopy(row)
                for row in self.steps
                if row.get("kind") == "http"
                and (row.get("phase") in {"producer", "source_query/producer"}
                     or row.get("role") == "producer")
            ),
            None,
        )
        observers = [
            copy.deepcopy(row)
            for row in self.steps
            if row.get("kind") == "http"
            and (
                row.get("phase") in {"observation", "before_observer", "after_observer", "intermediate_observer"}
                or row.get("role") in {"before", "after"}
                or str(row.get("phase", "")).startswith("followup_query[")
            )
        ]
        business = [row for row in self.assertions if row["class"] == "business"]
        if len(business) != 1:
            raise ValueError("pytest export requires exactly one business assertion")
        return {
            "test_id": self.test_id,
            "candidate_id": self.candidate_id,
            "canonical_relation_core_identity": self.canonical_relation_core_identity,
            "business_summary": self.business_summary,
            **classify_assertion_layer(self.protocol_kind, business[0]["predicate"]),
            "generic_baseline_overlap": _generic_baseline_overlap(self.assertions),
            "producer": producer,
            "actions": [copy.deepcopy(row) for row in self.steps
                        if row.get("kind") == "http" and
                        (row.get("role") == "producer" or row.get("phase") in {"producer", "inverse"})],
            "observers": observers,
            "business_predicate": copy.deepcopy(business[0]),
            "rationale_sources": [
                copy.deepcopy(row) for row in self.rationale_sources
            ],
            "rationale_semantics": (
                "non_normative_raw_M10_proposal_metadata_not_used_by_identity_"
                "dedup_setup_verdict_or_retention"
            ),
            "schema_type_assertion_scope": SCHEMA_TYPE_ASSERTION_SCOPE,
        }


def export_pytest_project(*, run_root: Path, output_root: Path) -> dict[str, Any]:
    """Render one immutable final calibrated business suite as pytest source."""

    root = run_root.resolve(strict=True)
    output = output_root.resolve()
    if output.exists():
        raise ValueError("pytest export output already exists")
    suite, calibration, final_suite = _load_final_suite(root)
    trace = UiApiTrace.model_validate_json(
        (root / "M01_09/ui_api_trace.json").read_bytes(), strict=True
    )
    materials = _load_material_documents(
        root, [str(test["candidate_id"]) for test in final_suite["retained_tests"]]
    )
    retained_ids = [
        str(test["candidate_id"]) for test in final_suite["retained_tests"]
    ]
    retained_cores = calibration.get(
        "retained_canonical_relation_core_identities"
    )
    if not isinstance(retained_cores, list) or len(retained_ids) != len(
        retained_cores
    ):
        raise ValueError("pytest export requires aligned retained canonical cores")
    core_by_candidate = dict(zip(retained_ids, retained_cores, strict=True))
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in core_by_candidate.values()
    ):
        raise ValueError("pytest export retained canonical core is invalid")
    candidate_set = _read_object(root / "M10/union/candidate_set.json")
    payload_by_candidate = {
        str(row["candidate_id"]): row["payload"]
        for row in candidate_set.get("candidates", [])
        if str(row.get("candidate_id")) in core_by_candidate
    }
    if set(payload_by_candidate) != set(retained_ids):
        raise ValueError("pytest export retained candidate is missing from M10 union")
    rationale_by_candidate = load_raw_rationale_sources(
        root, payload_by_candidate
    )
    if any(not rationale_by_candidate[candidate_id] for candidate_id in retained_ids):
        raise ValueError("pytest export raw M10 rationale provenance is incomplete")
    cases = build_export_cases(
        final_suite["retained_tests"],
        materials=materials,
        trace=trace,
        reporting_by_candidate={
            candidate_id: {
                "canonical_relation_core_identity": core_by_candidate[candidate_id],
                "rationale_sources": rationale_by_candidate[candidate_id],
            }
            for candidate_id in retained_ids
        },
    )
    if len(cases) != int(final_suite["retained_count"]):
        raise ValueError("pytest export does not close the retained suite")

    output.mkdir(parents=True)
    (output / "conftest.py").write_text(
        _render_conftest(root), encoding="utf-8"
    )
    (output / "test_final_calibrated_suite.py").write_text(
        render_test_module(cases), encoding="utf-8"
    )
    catalog = build_business_test_catalog(cases)
    (output / "business_test_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        _render_readme(root, output, len(cases)), encoding="utf-8"
    )
    return {
        "schema_version": "uisemtest-pytest-export-report-v1",
        "status": "pass",
        "source_run_root": str(root),
        "output_root": str(output),
        "retained_test_count": len(cases),
        "protocol_distribution": _count_protocols(cases),
        "files": [
            "README.md",
            "business_test_catalog.json",
            "conftest.py",
            "test_final_calibrated_suite.py",
        ],
        "physical_retained_test_occurrence_count": catalog["summary"][
            "physical_retained_test_occurrence_count"
        ],
        "unique_canonical_relation_core_count": catalog["summary"][
            "unique_canonical_relation_core_count"
        ],
        "source_suite_sha256": canonical_sha256(suite),
        "source_final_suite_sha256": canonical_sha256(final_suite),
        "provider_llm_calls": 0,
    }


def build_export_cases(
    tests: Sequence[Mapping[str, Any]],
    *,
    materials: Mapping[str, Mapping[str, Any]],
    trace: UiApiTrace | Mapping[str, Any],
    reporting_by_candidate: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[ExportedPytestCase, ...]:
    """Project explicit steps/assertions without interpreting their verdicts."""

    trace_payload = trace.trace if isinstance(trace, UiApiTrace) else trace
    requests = {
        str(row["request_ref"]): copy.deepcopy(row)
        for row in trace_payload["api_requests"]
    }
    cases: list[ExportedPytestCase] = []
    for test in tests:
        candidate_id = str(test["candidate_id"])
        material = materials.get(candidate_id)
        if material is None:
            raise ValueError(f"pytest export material missing: {candidate_id}")
        cases.append(
            _project_case(
                test,
                material=material,
                requests=requests,
                reporting=(reporting_by_candidate or {}).get(candidate_id, {}),
            )
        )
    return tuple(cases)


def render_test_module(cases: Sequence[ExportedPytestCase]) -> str:
    lines = [
        '"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""',
        "",
    ]
    for case in cases:
        function = _function_name(case.test_id)
        rationale_refs = [
            str(row["rationale_ref"]) for row in case.rationale_sources
        ]
        docstring = "\n".join(
            [
                "Business summary: " + case.business_summary,
                "Candidate ID: " + case.candidate_id,
                "Canonical relation core: "
                + (case.canonical_relation_core_identity or "unavailable"),
                "Original M10 rationale sources (non-normative metadata):",
                *(
                    [f"- {value}" for value in rationale_refs]
                    if rationale_refs
                    else ["- unavailable"]
                ),
                "schema_type scope: " + SCHEMA_TYPE_ASSERTION_SCOPE,
            ]
        )
        lines.extend(
            [
                f"def test_{function}(uisemtest_runtime):",
                f"    {docstring!r}",
                f"    # {case.protocol_kind}: {case.candidate_id}",
                "    steps = " + _python_literal(list(case.steps), indent=4),
                "    assertions = " + _python_literal(list(case.assertions), indent=4),
                "    result = uisemtest_runtime.run_case(",
                f"        test_id={case.test_id!r},",
                f"        candidate_id={case.candidate_id!r},",
                f"        protocol_kind={case.protocol_kind!r},",
                f"        normal_runs={case.normal_runs!r},",
                f"        source_test_sha256={case.source_test_sha256!r},",
                "        steps=steps,",
                "        assertions=assertions,",
                "    )",
                "    assert result['final_status'] == 'normal_pass'",
                "    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])",
                "",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def deterministic_business_summary(test: Mapping[str, Any]) -> str:
    """Describe one frozen test from only its producer, observer, and predicate."""

    blueprint = test["blueprint"]
    if test["protocol_kind"] == "V2":
        primary = next(row for row in test["assertions"] if row["assertion_class"] == "business")
        layer = classify_assertion_layer("V2", primary["predicate"])["assertion_layer"].replace("_", " ")
        return f"Observation {_endpoint_summary(blueprint['observer'])}; {layer} {_predicate_summary(primary['predicate'])}; one fresh response ({blueprint['sampling']['input_relation_to_generation']})."
    if test["protocol_kind"] == "V8":
        primary = next(row for row in test["assertions"] if row["assertion_class"] == "business")
        return f"Temporal target {_endpoint_summary(blueprint['observer'])}; {_predicate_summary(primary['predicate'])}; frozen time requirement {blueprint['time_requirement']}."
    if test["protocol_kind"] == "V9":
        primary = next(row for row in test["assertions"] if row["assertion_class"] == "business")
        roles = [row['role'] for row in blueprint['observation_plan']]
        return f"Joint observations {roles}; {_predicate_summary(primary['predicate'])}; scope={blueprint['joint_observation']}. Sequential finite workflow observations."
    producer = _endpoint_summary(blueprint["producer"])
    if "query_plan" in blueprint:
        observer_rows = [
            f"{row['role']} {_endpoint_summary(row)}"
            for row in blueprint["query_plan"]
        ]
    else:
        observer_rows = [_endpoint_summary(blueprint["observer"])]
    business = [
        row
        for row in test["assertions"]
        if row["assertion_class"] == "business"
    ]
    if len(business) != 1:
        raise ValueError("business summary requires exactly one business assertion")
    predicate = _predicate_summary(business[0]["predicate"])
    if test["protocol_kind"] == "V5":
        return (
            f"Repeated action {producer}; reset arms {blueprint['reset_epochs']}; "
            f"actual checkpoints/actions {[row['step_id'] for row in blueprint['execution_steps']]}; "
            f"fixed checks {blueprint['required_checks']}; {predicate}."
        )
    if test["protocol_kind"] == "V6":
        observation = ("no before/after observation or settling" if blueprint["negative_kind"] == "rejection"
                       else f"fresh preservation observers {'; '.join(observer_rows)}")
        return (f"Negative request {producer}; {blueprint['negative_kind']}; {observation}; "
                f"frozen rejection detector {blueprint['rejection_detector']}; {predicate}.")
    if test["protocol_kind"] == "V3":
        return (
            f"Queries {'; '.join(observer_rows)}; business predicate {predicate}; "
            f"query scope={blueprint.get('query_scope', {'scope': 'actual_response'})}; "
            f"input transform={blueprint.get('query_transform')}."
        )
    workflow = ""
    if blueprint.get("workflow_kind") == "inverse_restoration":
        workflow = f"Inverse action {_endpoint_summary(blueprint['inverse'])} after a fresh intermediate read; "
    elif blueprint.get("workflow_kind") == "read_preservation":
        workflow = "Read-preservation action; "
    identity = f"verified identity/session relation {blueprint['identity_topology']}; " if "identity_topology" in blueprint else ""
    return (
        workflow + identity +
        f"Producer {producer}; observer {'; '.join(observer_rows)}; "
        f"business predicate {predicate}."
    )


def _generic_baseline_overlap(assertions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    primary = next(row["predicate"] for row in assertions if row["class"] == "business")
    return generic_baseline_overlap(primary, (row for row in assertions if row["class"] == "generic"))


def build_business_test_catalog(
    cases: Sequence[ExportedPytestCase],
) -> dict[str, Any]:
    """Build a reporting-only catalog whose counts can be recomputed from rows."""

    rows = [case.reporting_payload() for case in cases]
    cores = [row["canonical_relation_core_identity"] for row in rows]
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in cores
    ):
        raise ValueError("business test catalog requires canonical relation cores")
    unique_cores = sorted(set(cores))
    return {
        "schema_version": "uisemtest-post-m14-business-test-catalog-v1",
        "scope": "post_M14_non_scientific_reporting_metadata",
        "summary": {
            "physical_retained_test_occurrence_count": len(rows),
            "unique_canonical_relation_core_count": len(unique_cores),
            "duplicate_core_occurrence_count": len(rows) - len(unique_cores),
            "physical_candidate_ids": [row["candidate_id"] for row in rows],
            "canonical_relation_core_identities": unique_cores,
            "basic_constraint_occurrence_count": sum(row["assertion_layer"] == "basic_constraint" for row in rows),
            "business_relation_occurrence_count": sum(row["assertion_layer"] == "business_relation" for row in rows),
            "generic_baseline_partial_overlap_candidate_ids": [row["candidate_id"] for row in rows if row["generic_baseline_overlap"]],
        },
        "schema_type_assertion_scope": SCHEMA_TYPE_ASSERTION_SCOPE,
        "tests": rows,
    }


def load_raw_rationale_sources(
    run_root: Path,
    candidate_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Trace final normalized relations to raw M10 call/ordinal rationales.

    Rationale text is read-only proposal metadata.  Matching uses M10's existing
    exact-relation projection and persisted candidate-validation relation hash;
    it does not add rationale to any normalized candidate or identity.
    """

    root = run_root.resolve(strict=True)
    if not candidate_payloads:
        return {}
    candidate_by_relation: dict[str, list[str]] = {}
    for candidate_id, payload in candidate_payloads.items():
        relation_sha = canonical_sha256(_scientific_relation_payload(dict(payload)))
        candidate_by_relation.setdefault(relation_sha, []).append(candidate_id)
    result = {candidate_id: [] for candidate_id in candidate_payloads}
    for logical_call_id, call_root in _proposal_call_roots(root):
        report_path = call_root / "candidate_validation_report.json"
        envelope_path = call_root / "provider_response_envelope.json"
        if not report_path.is_file() or not envelope_path.is_file():
            raise ValueError(f"raw M10 rationale artifact missing: {call_root}")
        report = _read_object(report_path)
        matching = [
            row
            for row in report.get("candidates", [])
            if row.get("disposition") in {"admitted", "deduplicated"}
            and row.get("relation_sha256") in candidate_by_relation
        ]
        if not matching:
            continue
        envelope = _read_object(envelope_path)
        content = envelope.get("content")
        raw = json.loads(content) if isinstance(content, str) else content
        raw_candidates = raw.get("candidates") if isinstance(raw, Mapping) else None
        if not isinstance(raw_candidates, list):
            raise ValueError(f"raw M10 rationale content is invalid: {envelope_path}")
        source_ref = os.path.relpath(envelope_path, start=root)
        for row in matching:
            ordinal = row.get("ordinal")
            if not isinstance(ordinal, int) or isinstance(ordinal, bool):
                raise ValueError("M10 rationale provenance ordinal is invalid")
            index = ordinal - 1
            if index < 0 or index >= len(raw_candidates):
                raise ValueError("M10 rationale provenance ordinal is out of range")
            raw_candidate = raw_candidates[index]
            if not isinstance(raw_candidate, Mapping):
                raise ValueError("raw M10 rationale candidate is invalid")
            rationale = raw_candidate.get("rationale")
            if rationale is not None and not isinstance(rationale, str):
                raise ValueError("raw M10 rationale must be text or null")
            rationale_ref = (
                f"{source_ref}#content(from-json).candidates[{index}].rationale"
            )
            source = {
                "call_id": logical_call_id,
                "candidate_ordinal": ordinal,
                "source_ref": source_ref,
                "rationale_ref": rationale_ref,
                "raw_rationale": rationale,
                "normative": False,
            }
            for candidate_id in candidate_by_relation[str(row["relation_sha256"])]:
                result[candidate_id].append(copy.deepcopy(source))
    return result


def _proposal_call_roots(root: Path) -> tuple[tuple[str, Path], ...]:
    provenance = _read_object(root / "M10/union/union_provenance.json")
    call_ids = provenance.get("call_ids")
    if not isinstance(call_ids, list) or any(
        not isinstance(value, str) for value in call_ids
    ):
        raise ValueError("M10 union call IDs are invalid")
    sampling_manifest = root.parent / "run_manifest.json"
    round_roots: dict[int, Path] = {}
    if any(call_id.startswith("round-") for call_id in call_ids):
        sampling = _read_object(sampling_manifest)
        rows = sampling.get("rounds")
        if not isinstance(rows, list):
            raise ValueError("sampled M10 rationale roots are unavailable")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("sampled M10 rationale root is invalid")
            index = row.get("round_index")
            source_ref = row.get("m10_source_ref")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not isinstance(source_ref, str)
            ):
                raise ValueError("sampled M10 rationale root is invalid")
            round_roots[index] = root.parent / source_ref
    resolved: list[tuple[str, Path]] = []
    for logical_call_id in call_ids:
        if logical_call_id.startswith("round-"):
            prefix, call_id = logical_call_id.split(":", 1)
            match = re.fullmatch(r"round-(\d{4})", prefix)
            if match is None or int(match.group(1)) not in round_roots:
                raise ValueError("sampled M10 rationale call cannot resolve its round")
            call_root = (
                round_roots[int(match.group(1))] / "M10/calls" / call_id
            )
        elif logical_call_id.startswith("center-completion:"):
            call_id = logical_call_id.split(":", 1)[1]
            call_root = root / "M10/center_completion/calls" / call_id
        else:
            call_root = root / "M10/calls" / logical_call_id
        resolved.append((logical_call_id, call_root))
    return tuple(resolved)


def _endpoint_summary(endpoint: Mapping[str, Any]) -> str:
    return " ".join(
        str(endpoint[key]) for key in ("actor_id", "method", "path")
    )


def _value_ref_summary(value: Mapping[str, Any]) -> str:
    if value.get("source") == "collection_member":
        return (
            f"{value['role']} member {value['collection_path']}"
            f"{value['field_path']} ({value['value_type']})"
        )
    return f"{value['role']} {value['path']} ({value['value_type']})"


def _operand_summary(value: Mapping[str, Any]) -> str:
    if value.get("source") == "role":
        return _value_ref_summary(value["ref"])
    if value.get("source") == "transition_fact":
        return f"transition value {value['value']!r} ({value['value_type']})"
    if value.get("source") == "request":
        reference = value["ref"]
        return f"actual request {reference['location']} {reference['path']} ({reference['value_type']})"
    if value.get("source") == "hypothesis":
        return f"frozen hypothesis {value.get('lexical', value['value'])!r} ({value['value_type']})"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identity_summary(value: Mapping[str, Any]) -> str:
    if "paths" in value:
        fields = ", ".join(str(path) for path in value["paths"])
    else:
        fields = ", ".join(
            f"{row['member_path']}->{row['collection_item_path']}"
            for row in value["field_pairs"]
        )
    return f"{value['semantics']} identity [{fields}]"


def _predicate_summary(predicate: Mapping[str, Any]) -> str:
    family = str(predicate["family"])
    if family == "repeat_equal":
        return "repeat_equal requires comparable A0/B0 and frozen logical inputs, then A1 = B2; " + _predicate_summary(predicate["projection"])
    if family == "repeat_rejected":
        detector = (_predicate_summary(predicate["rejection"]) if predicate.get("rejection") is not None else "healthy HTTP 4xx")
        return f"repeat_rejected requires first success, second rejection ({detector}), and B1 = B2; " + _predicate_summary(predicate["projection"])
    if family == "repeat_delta":
        return "repeat_delta requires both B0→B1 and B1→B2; a wrong first delta refutes; " + _predicate_summary(predicate["delta"])
    if family == "P01":
        target = _value_ref_summary(predicate["target"])
        if predicate["member"] is None:
            if predicate["target"]["value_type"] == "object" and predicate["target"]["role"] not in {"observation", "item"}:
                return (f"P01 requires point resource {target} to {predicate['operator']}; "
                        f"declared absence HTTP statuses={predicate.get('absent_statuses', [])}; "
                        "other unsuccessful responses are unavailable, not absence")
            if predicate["target"]["role"] in {"observation", "item"}:
                return f"P01 requires field {target} to be {predicate['operator']}"
            expected = (
                "true/present"
                if predicate["operator"] == "exists"
                else "false/absent"
            )
            return f"P01 requires {target} to be {expected}"
        membership = (
            "to contain" if predicate["operator"] == "exists" else "not to contain"
        )
        return (
            f"P01 requires {target} {membership} "
            f"{_operand_summary(predicate['member'])} by "
            f"{_identity_summary(predicate['identity'])}"
        )
    if family == "P02":
        operator = {"eq": "strictly equal", "neq": "strictly differ from", "numeric_eq": "numerically equal", "numeric_neq": "numerically differ from", "lt": "be less than", "le": "be at most", "gt": "be greater than", "ge": "be at least"}[predicate["operator"]]
        return (
            f"P02 requires {_value_ref_summary(predicate['left'])} to {operator} "
            f"{_operand_summary(predicate['right'])}"
        )
    if family == "P03":
        if predicate["operator"] == "in":
            return f"P03 requires {_value_ref_summary(predicate['target'])} to belong to {_operand_summary(predicate['domain'])} by strict JSON equality"
        return (
            f"P03 requires {_operand_summary(predicate['lower'])} {'<=' if predicate['lower_inclusive'] else '<'} "
            f"{_value_ref_summary(predicate['target'])} {'<=' if predicate['upper_inclusive'] else '<'} {_operand_summary(predicate['upper'])}"
        )
    if family == "forall":
        guard = predicate.get("item_guard")
        applicability = "" if guard is None else f" when {_predicate_summary(guard)}"
        return f"For every member of {_value_ref_summary(predicate['collection'])} in {predicate['scope']}{applicability}: {_predicate_summary(predicate['body'])}"
    if family == "P04":
        if workflow_applicability_predicate(predicate) is not None:
            return (
                f"P04 checks before action that {_value_ref_summary(predicate['before'])} equals "
                f"{_operand_summary(predicate['from_value'])}; if established, requires the fresh "
                f"{_value_ref_summary(predicate['after'])} to equal {_operand_summary(predicate['to_value'])}"
            )
        return (
            f"P04 requires {_value_ref_summary(predicate['before'])} to change "
            f"from {_operand_summary(predicate['from_value'])} to "
            f"{_operand_summary(predicate['to_value'])} at "
            f"{_value_ref_summary(predicate['after'])}"
        )
    if family == "P06":
        return (
            f"P06 requires {_value_ref_summary(predicate['after'])} minus "
            f"{_value_ref_summary(predicate['before'])} to equal "
            f"{predicate['multiplier']} times {_operand_summary(predicate['delta'])}; "
            f"numeric_mode={predicate.get('numeric_mode', 'exact')}; "
            f"unit={_operand_summary(predicate['unit']) if predicate.get('unit') is not None else 'existing source declaration'}; "
            f"rounding={predicate.get('rounding')}, tolerance_kind={predicate.get('tolerance_kind')}, "
            f"tolerance={predicate.get('tolerance')}, conversions={predicate.get('conversions')}"
        )
    if family == "P07":
        direction = {"gt": "be greater than", "lt": "be less than", "ge": "be at least", "le": "be at most"}[predicate["operator"]]
        return (
            f"P07 requires the fresh {_value_ref_summary(predicate['after'])} to {direction} "
            f"{_value_ref_summary(predicate['before'])} at two checkpoints"
        )
    if family == "P09":
        direction = {"contains": "contain", "prefix": "start with", "suffix": "end with"}[predicate["operator"]]
        return f"P09 requires {_value_ref_summary(predicate['target'])} to {direction} {_operand_summary(predicate['right'])}; case-sensitive, no normalization"
    if family == "P10":
        rule = "a valid Gregorian YYYY-MM-DD date" if predicate["format"] == "date_yyyy_mm_dd" else f"a full match of {_operand_summary(predicate['pattern'])} with Python re flags=0"
        return f"P10 requires {_value_ref_summary(predicate['target'])} to be {rule}"
    if family == "P11" and predicate.get("target") is not None:
        options = f"unit={predicate['unit']}"
        if predicate["projection"] == "length":
            options += f", newline={predicate['newline']}, empty={predicate['empty']}"
        return f"P11 requires {predicate['projection']}({_value_ref_summary(predicate['target'])}; {options}) {predicate['operator']} {_operand_summary(predicate['right'])}"
    if family == "P11":
        return f"P11 requires count({_value_ref_summary(predicate['collection'])}) <= this request's query.limit"
    if family == "P21":
        return f"P21 requires {_value_ref_summary(predicate['target'])} to have JSON type {predicate['expected_type']}"
    if family == "P12":
        return (
            f"P12 requires collection count {_value_ref_summary(predicate['after'])} "
            f"minus {_value_ref_summary(predicate['before'])} to equal "
            f"{predicate['delta']}"
        )
    if family == "P08" and predicate.get("operator") == "linear_delta":
        return f"P08 linear delta sum: {predicate['terms']} = {predicate['output']}; units={predicate['units']['value']}, numeric_mode={predicate['numeric_mode']}, rounding={predicate.get('rounding')}, tolerance={predicate.get('tolerance')}, conversions={predicate.get('conversions')}"
    if family == "P08":
        return f"P08 requires {_value_ref_summary(predicate['output'])} = {_operand_summary(predicate['left'])} {predicate['operator']} {_operand_summary(predicate['right'])}; numeric_mode={predicate['numeric_mode']}, units={predicate['units']['value']}, rounding={predicate.get('rounding')}, tolerance_kind={predicate.get('tolerance_kind')}, tolerance={predicate.get('tolerance')}, conversions={predicate.get('conversions')}"
    if family == "P19":
        return f"P19 requires {_value_ref_summary(predicate['output'])} = {predicate['operator']}({_value_ref_summary(predicate['collection'])}); scope={predicate['scope']}, item={predicate.get('item')}, factor={predicate.get('factor')}, numeric_mode={predicate['numeric_mode']}, units={predicate['units']['value']}, rounding={predicate.get('rounding')}, tolerance_kind={predicate.get('tolerance_kind')}, tolerance={predicate.get('tolerance')}, conversions={predicate.get('conversions')}"
    if family == "P16":
        return f"P16 requires order by {predicate['key']} {predicate['direction']}, nulls {predicate['nulls']}, ties {predicate['ties']}, AND multiset preservation; basis={predicate['comparison_basis']}, projection={predicate['projection']}, identity={predicate['identity']}"
    if family == "P13":
        membership = (
            "to contain"
            if predicate["operator"] == "contains"
            else "not to contain"
        )
        return (
            f"P13 requires {_value_ref_summary(predicate['collection'])} "
            f"{membership} {_operand_summary(predicate['member'])} "
            f"by {_identity_summary(predicate['identity']) if predicate.get('identity') is not None else 'strict JSON scalar equality'}"
        )
    if family == "P14":
        return (
            f"P14 requires {_operand_summary(predicate['member'])} to be "
            f"{predicate['operator']} between {_value_ref_summary(predicate['before'])} "
            f"and {_value_ref_summary(predicate['after'])} by "
            f"{_identity_summary(predicate['identity'])}"
        )
    if family == "P15":
        return (
            f"P15 requires {_value_ref_summary(predicate['collection'])} ({predicate.get('scope', 'frozen query plan')}) to have "
            f"unique members by {_identity_summary(predicate['identity'])}"
        )
    if family == "P17":
        return f"P17 requires {_value_ref_summary(predicate['left'])} {predicate['operator']} {_value_ref_summary(predicate['right'])}; representation={predicate['representation']}, basis={predicate['comparison_basis']}, projection={predicate['projection']}, identity={predicate['identity']}"
    if family == "P18":
        partitions = ", ".join(
            _value_ref_summary(row) for row in predicate["partitions"]
        )
        suffix = (
            ""
            if predicate["expected_remainder"] is None
            else " with remainder "
            + _value_ref_summary(predicate["expected_remainder"])
        )
        return (
            f"P18 requires {predicate['operator']} for source "
            f"{_value_ref_summary(predicate['source'])} and partitions "
            f"[{partitions}] by {_identity_summary(predicate['identity'])}{suffix}"
        )
    if family == "P20":
        return (
            f"P20 requires strict equality between "
            f"{_value_ref_summary(predicate['left'])} and "
            f"{_value_ref_summary(predicate['right'])}"
            + (f" for every frozen field {predicate['projection']}; known false survives another unavailable field"
               if predicate.get("projection") else "")
        )
    raise ValueError(f"business summary predicate unsupported: {family}")


class FrozenSuitePytestRuntime:
    """Session-scoped bridge from readable pytest cases to current M14 runtime."""

    def __init__(self, source_run_root: Path, runtime_root: Path) -> None:
        self.source_run_root = source_run_root.resolve(strict=True)
        self.runtime_root = runtime_root.resolve()
        self._factory: Any | None = None
        self._runtime: Any | None = None
        self._tests: dict[str, dict[str, Any]] = {}
        self._cases: dict[str, ExportedPytestCase] = {}
        self._executed: set[str | tuple[str, str]] = set()

    def open(self, *, external_lifecycle: bool = False, response_transform: Any = None) -> "FrozenSuitePytestRuntime":
        if self._factory is not None:
            raise RuntimeError("pytest runtime already opened")
        _suite, _calibration, final_suite = _load_final_suite(
            self.source_run_root
        )
        trace = UiApiTrace.model_validate_json(
            (self.source_run_root / "M01_09/ui_api_trace.json").read_bytes(),
            strict=True,
        )
        candidate_ids = [
            str(test["candidate_id"]) for test in final_suite["retained_tests"]
        ]
        material_documents = _load_material_documents(
            self.source_run_root, candidate_ids
        )
        self._cases = {
            case.test_id: case
            for case in build_export_cases(
                final_suite["retained_tests"],
                materials=material_documents,
                trace=trace,
            )
        }
        self._tests = {
            str(test["test_id"]): copy.deepcopy(test)
            for test in final_suite["retained_tests"]
        }

        profile = self.source_run_root / "inputs/subject/profile.json"
        adapter = self.source_run_root / "inputs/subject/adapter.json"
        bundle = load_current_adapter(profile, adapter)
        explicit_fixture = (
            isinstance(bundle.adapter.runtime, DeterministicFixtureRuntimeConfig)
            and bundle.adapter.request_mapping.mode == "explicit_adapter"
        )
        recorded_bundles = (
            {} if explicit_fixture else _load_recorded_bundles(self.source_run_root, trace)
        )
        request_bindings = resolve_current_request_bindings(
            bundle,
            trace=trace,
            recording_root=self.source_run_root,
            recorded_bundles=recorded_bundles,
        )
        factory = build_current_runtime_factory(
            bundle,
            run_id="pytest-export-" + canonical_sha256(final_suite)[:16],
            request_bindings=request_bindings,
            trace=trace if explicit_fixture else _trace_with_resolved_recording_paths(trace, self.source_run_root),
            recording_material_aliases=() if explicit_fixture else resolve_recording_material_aliases(self.source_run_root),
            recorded_bundles=recorded_bundles,
        )
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        if any(self.runtime_root.iterdir()):
            raise ValueError("pytest runtime output root must be empty")
        workflows = self.source_run_root / "inputs/recording/workflows"
        if workflows.is_dir():
            shutil.copytree(workflows, self.runtime_root / "inputs/recording/workflows")
        factory.preflight()
        if external_lifecycle or response_transform is not None:
            from .current_http_runtime import LocalHttpCurrentRuntimeFactory
            if not isinstance(factory, LocalHttpCurrentRuntimeFactory):
                raise TypeError("evaluation transport/lifecycle requires local HTTP runtime")
            factory.core.response_transform = response_transform
        if external_lifecycle:
            factory.core.attach(self.runtime_root)
        else:
            try:
                factory.start(run_root=self.runtime_root)
            except BaseException:
                factory.teardown()
                raise
        try:
            for candidate_id in candidate_ids:
                factory.route_s_runtime(
                    _load_runtime_material(
                        self.source_run_root,
                        candidate_id,
                        material_documents[candidate_id],
                    )
                )
            factory.assert_route_s_complete(len(candidate_ids))
            runtime = factory.calibration_runtime(
                {"tests": copy.deepcopy(final_suite["retained_tests"])}
            )
        except BaseException:
            factory.teardown()
            raise
        self._factory = factory
        self._runtime = runtime
        return self

    def run_case(
        self,
        *,
        test_id: str,
        candidate_id: str,
        protocol_kind: str,
        normal_runs: int,
        source_test_sha256: str,
        steps: Sequence[Mapping[str, Any]],
        assertions: Sequence[Mapping[str, Any]],
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        if self._runtime is None:
            raise RuntimeError("pytest runtime is not open")
        expected = self._cases.get(test_id)
        if expected is None:
            raise ValueError("generated pytest test is not retained by the source suite")
        actual = {
            "test_id": test_id,
            "candidate_id": candidate_id,
            "protocol_kind": protocol_kind,
            "normal_runs": normal_runs,
            "source_test_sha256": source_test_sha256,
            "steps": copy.deepcopy(list(steps)),
            "assertions": copy.deepcopy(list(assertions)),
        }
        if actual != expected.comparison_payload():
            raise ValueError("generated pytest case differs from the frozen M13/M14 definition")
        execution_key = test_id if execution_id is None else (test_id, execution_id)
        if execution_key in self._executed:
            raise ValueError("generated pytest case executed more than once")
        self._executed.add(execution_key)
        return execute_certified_relation_test(
            copy.deepcopy(self._tests[test_id]),
            self._runtime,
            mode="qualifying-formal",
            is_candidate_local_error=_is_candidate_local_execution_error,
        )

    def close(self) -> None:
        factory, self._factory = self._factory, None
        self._runtime = None
        if factory is not None:
            factory.teardown()

    def run_retained_test(self, test_id: str, *, execution_id: str | None = None) -> dict[str, Any]:
        """Execute one retained definition without reconstructing its pytest text."""
        case = self._cases.get(test_id)
        if case is None:
            raise ValueError("test is not retained by the source suite")
        return self.run_case(**case.comparison_payload(), execution_id=execution_id)


def _project_case(
    test: Mapping[str, Any],
    *,
    material: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
    reporting: Mapping[str, Any],
) -> ExportedPytestCase:
    protocol = str(test["protocol_kind"])
    blueprint = test["blueprint"]
    arm = {
        "V1": "treatment",
        "V2": "single_state",
        "V3": "metamorphic_query",
        "V4": "workflow",
        "V5": "repeat_twice",
        "V6": "negative_no_effect",
        "V7": "actor_matrix",
        "V9": "multi_resource",
        "V8": "temporal",
    }.get(protocol)
    if arm is None:
        raise ValueError(f"pytest export protocol unsupported: {protocol}")
    plans = material.get("resource_binding_plans") or {}
    plan = plans.get(arm) or {}
    sources = list(plan.get("sources") or [])
    uses = list(plan.get("uses") or [])
    steps: list[dict[str, Any]] = [] if protocol == "V5" else [
        {
            "kind": "reset_and_authenticate",
            "arm": arm,
            "actors": list(blueprint["actors"]),
        }
    ]

    def append_http(
        phase: str, endpoint: Mapping[str, Any], *,
        occurrence: Mapping[str, Any] | None = None,
        bind_request: bool = True, prepare_request: bool = False,
    ) -> None:
        metadata = dict(occurrence or {})
        request_ref = str(endpoint["request_ref"])
        for use in uses:
            if bind_request and str(use.get("consumer_request_ref")) == request_ref:
                steps.append(
                    {
                        "kind": "fresh_bind",
                        "phase": phase,
                        "actor": str(use["actor_id"]),
                        "request_ref": request_ref,
                        "location": str(use["location"]),
                        "target_path": str(use["target_path"]),
                        "source_id": str(use["source_id"]),
                        **metadata,
                    }
                )
        if prepare_request:
            steps.append({
                "kind": "prepare_producer", "phase": phase, **metadata,
                "frozen_fields": ["method", "path", "query", "body", "idempotency_key"],
                "reuse_for_second_send": True,
            })
        row = requests.get(request_ref, {})
        steps.append(
            {
                "kind": "http",
                "phase": phase,
                "actor": str(endpoint.get("actor_id") or row.get("actor_id")),
                "method": str(endpoint.get("method") or row.get("method")),
                "path": str(endpoint.get("path") or row.get("canonical_path")),
                "request_ref": request_ref,
                **metadata,
            }
        )
        for source in sources:
            if str(source.get("creator_request_ref")) == request_ref:
                steps.append(
                    {
                        "kind": "capture",
                        "phase": phase,
                        "actor": str(source["actor_id"]),
                        "request_ref": request_ref,
                        "response_path": str(source["response_path"]),
                        "scalar_type": str(source["scalar_type"]),
                        "source_id": str(source["source_id"]),
                        **metadata,
                    }
                )

    def append_setup(epoch: str | None = None) -> None:
        for index, setup in enumerate(blueprint["setup"]):
            ref = str(setup["request_ref"])
            row = requests.get(ref)
            if row is None:
                raise ValueError(f"pytest export setup request missing from trace: {ref}")
            append_http(
                f"setup[{index}]",
                {"actor_id": setup["actor_id"], "request_ref": ref,
                 "method": row["method"], "path": row["canonical_path"]},
                occurrence={"reset_epoch": epoch} if epoch is not None else None,
            )

    if protocol != "V5":
        append_setup()
    if "identity_topology" in blueprint:
        steps.append({"kind": "verify_identity_topology", "topology": copy.deepcopy(blueprint["identity_topology"])})
    if protocol == "V6":
        steps.append({"kind": "verify_session_boundary", "boundary": copy.deepcopy(blueprint["session_boundary"])})

    if protocol == "V8":
        if blueprint.get("before_observer") is not None:
            append_http("before", blueprint["before_observer"])
        append_http("producer", blueprint["producer"])
        steps.append({"kind": "frozen_time_requirement", "time_requirement": copy.deepcopy(blueprint["time_requirement"])})
        for row in blueprint["observation_plan"]:
            append_http(row["role"], row["endpoint"])
    elif protocol == "V9":
        action_sent = False
        for row in blueprint["observation_plan"]:
            if row["phase"] == "after" and blueprint["producer"] is not None and not action_sent:
                append_http("producer", blueprint["producer"])
                action_sent = True
            append_http(row["role"], row["endpoint"])
        steps.append({"kind": "joint_observation_scope", "joint_observation": copy.deepcopy(blueprint["joint_observation"])})
    elif protocol == "V2":
        append_http("observation", blueprint["observer"])
    elif protocol == "V3":
        for index, query in enumerate(blueprint["query_plan"]):
            phase = "source_query/producer" if index == 0 else f"followup_query[{index}]"
            append_http(phase, query)
    elif protocol == "V5":
        for epoch in blueprint["reset_epochs"]:
            plan = plans[epoch]
            sources, uses = list(plan.get("sources") or []), list(plan.get("uses") or [])
            steps.append({"kind": "reset_and_authenticate", "arm": epoch,
                          "actors": list(blueprint["actors"])})
            append_setup(epoch)
            for row in blueprint["execution_steps"]:
                if row["reset_epoch"] != epoch:
                    continue
                action = row["kind"] == "request"
                metadata = {key: copy.deepcopy(row[key]) for key in ("reset_epoch", "occurrence_index", "role")}
                metadata["checkpoint_id"] = row["step_id"]
                if action:
                    metadata["request_policy"] = "reuse_prepared_request"
                append_http(
                    row["step_id"], row["endpoint"], occurrence=metadata,
                    bind_request=not action or row["occurrence_index"] == 1,
                    prepare_request=action and row["occurrence_index"] == 1,
                )
        steps.append({"kind": "business_checks", "check_ids": copy.deepcopy(blueprint["required_checks"]),
                      "evaluation_owner": "M14", "false_precedes_unknown": True})
    elif protocol == "V6" and blueprint["negative_kind"] == "rejection":
        append_http("producer", blueprint["producer"])
        steps.append({"kind": "business_checks", "check_ids": ["rejection"],
                      "rejection_detector": copy.deepcopy(blueprint["rejection_detector"]), "evaluation_owner": "M14"})
    else:
        workflow_kind = blueprint.get("workflow_kind")
        create_capture = protocol == "V4" and workflow_kind == "create_capture_read"
        no_before_workflow = protocol == "V4" and workflow_kind in {
            "create_capture_read",
            "postcondition_read",
        }
        if not no_before_workflow:
            append_http("before_observer", blueprint.get("before_observer", blueprint["observer"]))
        primary = next(row["predicate"] for row in test["assertions"] if row["assertion_class"] == "business")
        if protocol == "V4" and workflow_applicability_predicate(primary) is not None:
            steps.append({
                "kind": "applicability", "phase": "before_action",
                "before": copy.deepcopy(primary["before"]),
                "from_value": copy.deepcopy(primary["from_value"]),
                "on_not_established": "not_evaluable_without_action",
            })
        append_http("producer", blueprint["producer"])
        if protocol == "V4" and workflow_kind == "inverse_restoration":
            append_http("intermediate_observer", blueprint["intermediate_observer"])
            append_http("inverse", blueprint["inverse"])
        if create_capture and not any(
            step["kind"] == "capture" and step["phase"] == "producer"
            for step in steps
        ):
            steps.append(
                {
                    "kind": "capture",
                    "phase": "producer",
                    "source": "producer_response",
                    "purpose": "fresh_identity",
                }
            )
        steps.append(
            {"kind": "settle", "policy": copy.deepcopy(blueprint["settle_policy"])}
        )
        append_http("after_observer", blueprint["observer"])
        if protocol == "V6":
            steps.append({"kind": "business_checks", "check_ids": ["rejection", "preservation"],
                          "rejection_detector": copy.deepcopy(blueprint["rejection_detector"]),
                          "evaluation_owner": "M14", "false_precedes_unknown": True})

    assertions = tuple(
        {
            "assertion_id": str(row["assertion_id"]),
            "class": str(row["assertion_class"]),
            "predicate_type": str(row["predicate_type"]),
            "predicate": copy.deepcopy(row["predicate"]),
        }
        for row in test["assertions"]
    )
    return ExportedPytestCase(
        test_id=str(test["test_id"]),
        candidate_id=str(test["candidate_id"]),
        protocol_kind=protocol,
        normal_runs=int(test["normal_runs"]),
        source_test_sha256=canonical_sha256(test),
        steps=tuple(steps),
        assertions=assertions,
        business_summary=deterministic_business_summary(test),
        canonical_relation_core_identity=reporting.get(
            "canonical_relation_core_identity"
        ),
        rationale_sources=tuple(
            copy.deepcopy(row) for row in reporting.get("rationale_sources", ())
        ),
    )


def _load_final_suite(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    suite = _read_object(root / "M13/certified_relation_tests.json")
    calibration = _read_object(root / "M14/calibration_report.json")
    final_view = _read_object(root / "M14/final_calibrated_view.json")
    final_suite = _read_object(root / "M14/final_calibrated_suite.json")
    validate_certified_relation_tests(suite)
    validate_final_calibrated_suite(
        final_suite,
        suite=suite,
        calibration=calibration,
        final_view=final_view,
        run_root=root,
    )
    if final_suite["status"] != "pass":
        raise ValueError("pytest export requires a terminal PASS final calibrated suite")
    return suite, calibration, final_suite


def _load_material_documents(
    root: Path, candidate_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    materials: dict[str, dict[str, Any]] = {}
    for candidate_id in candidate_ids:
        path = root / f"M11b/{candidate_id}/execution_material.json"
        if not path.is_file():
            raise ValueError(f"pytest export material missing: {candidate_id}")
        value = _read_object(path)
        validate_current_route_s_material(value)
        if value["candidate_id"] != candidate_id:
            raise ValueError("pytest export material candidate mismatch")
        materials[candidate_id] = value
    return materials


def _load_runtime_material(
    root: Path,
    candidate_id: str,
    execution_material: Mapping[str, Any],
) -> RouteSPreLiveMaterializedCandidate:
    candidate_path = root / f"M11b/{candidate_id}/candidate.json"
    candidate = _read_object(candidate_path)
    material = copy.deepcopy(dict(execution_material))
    candidate_bytes = canonical_json_bytes(candidate)
    material_bytes = canonical_json_bytes(material)
    prefix = f"M11b/{candidate_id}"
    artifacts = {
        f"{prefix}/candidate.json": candidate_bytes,
        f"{prefix}/execution_material.json": material_bytes,
    }
    return RouteSPreLiveMaterializedCandidate(
        candidate_id=candidate_id,
        bound_candidate_sha256=str(material["bound_candidate_sha256"]),
        candidate=candidate,
        execution_binding={"payload": copy.deepcopy(material["execution_binding"])},
        execution_binding_bytes=canonical_json_bytes(material["execution_binding"]),
        pre_live_binding_pins={},
        pre_live_binding_pins_bytes=b"",
        projection_plan=copy.deepcopy(material["projection_plan"]),
        observer_policy=copy.deepcopy(material["observer_policy"]),
        settle_policy=copy.deepcopy(material["settle_policy"]),
        sensitive_classification=copy.deepcopy(material["sensitive_classification"]),
        resource_binding_plans=copy.deepcopy(material["resource_binding_plans"]),
        scientific_pins={},
        artifact_bytes=artifacts,
        artifact_hashes={
            ref: hashlib.sha256(payload).hexdigest()
            for ref, payload in artifacts.items()
        },
        artifact_inventory=(),
        execution_material=material,
        execution_material_bytes=material_bytes,
        output_level="paper",
    )


def _load_recorded_bundles(root: Path, trace: UiApiTrace) -> dict[str, LoadedBundle]:
    result: dict[str, LoadedBundle] = {}
    resolved = _trace_with_resolved_recording_paths(trace, root)
    for actor in resolved.trace["actors"]:
        bundle = load_bundle(Path(actor["session_bundle_ref"]["path"]))
        if bundle.run_id in result:
            raise ValueError("pytest runtime source has duplicate recording run IDs")
        result[bundle.run_id] = bundle
    if not result:
        raise ValueError("pytest runtime source has no actor recording bundles")
    return result


def _trace_with_resolved_recording_paths(
    trace: UiApiTrace, recording_root: Path
) -> UiApiTrace:
    payload = copy.deepcopy(trace.trace)
    root = recording_root.resolve(strict=True)
    for actor in payload["actors"]:
        ref = actor["session_bundle_ref"]
        relative = Path(str(ref["path"]))
        if relative.is_absolute() or relative == Path(".") or ".." in relative.parts:
            raise ValueError("pytest runtime recording path is not root-relative")
        path = (root / relative).resolve(strict=True)
        if not path.is_dir() or not path.is_relative_to(root):
            raise ValueError("pytest runtime recording path escapes the source root")
        ref["path"] = str(path)
    return trace.model_copy(update={"trace": payload})


def _render_conftest(source_root: Path) -> str:
    return f'''"""Runtime fixture for the generated frozen UISemTest suite."""

from pathlib import Path

import pytest

from ui_semantics.pytest_export import FrozenSuitePytestRuntime


SOURCE_RUN_ROOT = Path({str(source_root)!r})


@pytest.fixture(scope="session")
def uisemtest_runtime(tmp_path_factory):
    runtime = FrozenSuitePytestRuntime(
        SOURCE_RUN_ROOT,
        tmp_path_factory.mktemp("uisemtest-pytest-runtime", numbered=True),
    ).open()
    try:
        yield runtime
    finally:
        runtime.close()
'''


def _render_readme(source_root: Path, output_root: Path, count: int) -> str:
    return f"""# UISemTest exported pytest suite

This directory is a deterministic, non-scientific Python representation of
the {count} retained business tests in `{source_root}`.  The generated test
functions expose every ordered HTTP, capture, binding, settle, and assertion
step.  Each function docstring identifies the normalized producer, observer,
business predicate, candidate ID, canonical relation core, and every raw M10
rationale source.  Raw rationales are non-normative proposal metadata: they do
not affect candidate identity, exact deduplication, setup, verdict, or M14
retention.  `business_test_catalog.json` contains the same reporting metadata
and a physical-test-occurrence versus canonical-core summary.

The exported `schema_type` assertion checks only the JSON type at one frozen
target JSONPath; it is not full response-schema or OpenAPI validation.  M11a is
the faithful lineage bridge.  Only M11b `execution_material.json` supplies the
material needed to execute these tests.  Execution delegates to the
repository's unchanged current M14 runtime.

Target-associated versus setup-associated labels require an independently
defined target-workflow reference and therefore remain in the post-M14 effect
reference report; this generic exporter does not infer those labels from a test
outcome or rationale.

Run from the repository root:

```sh
.venv/bin/python -m pytest -q {output_root}
```
"""


def _python_literal(value: Any, *, indent: int) -> str:
    rendered = pprint.pformat(value, width=100, sort_dicts=False)
    continuation = "\n" + " " * indent
    return rendered.replace("\n", continuation)


def _function_name(value: str) -> str:
    result = _FUNCTION_NAME.sub("_", value).strip("_").lower()
    if not result:
        raise ValueError("pytest export test ID cannot form a Python function name")
    return result


def _count_protocols(cases: Sequence[ExportedPytestCase]) -> dict[str, int]:
    return {
        kind: sum(case.protocol_kind == kind for case in cases)
        for kind in sorted({case.protocol_kind for case in cases})
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


__all__ = [
    "ExportedPytestCase",
    "FrozenSuitePytestRuntime",
    "SCHEMA_TYPE_ASSERTION_SCOPE",
    "build_business_test_catalog",
    "build_export_cases",
    "deterministic_business_summary",
    "export_pytest_project",
    "load_raw_rationale_sources",
    "render_test_module",
]
