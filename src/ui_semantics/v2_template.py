"""Canonical M10 scan and detail templates for preproposal-evidence-v2."""

from __future__ import annotations

import hashlib
import json
import re
from importlib.resources import files

CANONICAL_V2_TEMPLATE_RESOURCE = "templates/effect_contract_v2.txt"
CANONICAL_V2_TEMPLATE_REF = "ui_semantics/templates/effect_contract_v2.txt"
CANONICAL_SCAN_TEMPLATE_RESOURCE = "templates/fact_scan.txt"
CANONICAL_SCAN_TEMPLATE_REF = "ui_semantics/templates/fact_scan.txt"
PROPOSAL_EVIDENCE_PLACEHOLDER = "{{PROPOSAL_EVIDENCE_VIEW_JSON}}"
SCAN_EVIDENCE_PLACEHOLDER = "{{SCAN_EVIDENCE_JSON}}"
CANONICAL_V2_TEMPLATE_REVISION = "effect-contract-detail-region-v23"
CANONICAL_SCAN_TEMPLATE_REVISION = "protocol-neutral-global-scan-v2"
_PREDICATE_EXAMPLE = re.compile(
    r"^(P01|P02|P03|P04|P06|P07|P08|P09|P10|P11|P12|P13|P14|P15|P16|P17|P18|P19|P20|P21|forall|repeat_equal|repeat_rejected|repeat_delta):\s+(\{.*\})$"
)
_RELATION_EXAMPLE = re.compile(r"^Relation example ([a-z0-9_]+):\s+(\{.*\})$")


def canonical_v2_template_bytes() -> bytes:
    payload = files("ui_semantics").joinpath(CANONICAL_V2_TEMPLATE_RESOURCE).read_bytes()
    text = payload.decode("utf-8")
    if text.count(PROPOSAL_EVIDENCE_PLACEHOLDER) != 1:
        raise ValueError("canonical v2 template must contain exactly one evidence-view placeholder")
    if "{{TRACE_EVIDENCE_JSON}}" in text:
        raise ValueError("canonical v2 template cannot expose the legacy trace-only placeholder")
    return payload


def canonical_v2_template_text() -> str:
    return canonical_v2_template_bytes().decode("utf-8")


def canonical_v2_template_sha256() -> str:
    return hashlib.sha256(canonical_v2_template_bytes()).hexdigest()


def canonical_scan_template_bytes() -> bytes:
    payload = files("ui_semantics").joinpath(CANONICAL_SCAN_TEMPLATE_RESOURCE).read_bytes()
    text = payload.decode("utf-8")
    if text.count(SCAN_EVIDENCE_PLACEHOLDER) != 1:
        raise ValueError("canonical scan template must contain exactly one evidence placeholder")
    if PROPOSAL_EVIDENCE_PLACEHOLDER in text:
        raise ValueError("canonical scan template cannot contain the detail placeholder")
    return payload


def canonical_scan_template_text() -> str:
    return canonical_scan_template_bytes().decode("utf-8")


def canonical_scan_template_sha256() -> str:
    return hashlib.sha256(canonical_scan_template_bytes()).hexdigest()


def canonical_v2_predicate_examples() -> dict[str, dict[str, object]]:
    """Return the canonical machine-checkable P-family examples embedded in the template."""

    examples: dict[str, dict[str, object]] = {}
    for line in canonical_v2_template_text().splitlines():
        match = _PREDICATE_EXAMPLE.fullmatch(line)
        if match:
            examples[match.group(1)] = json.loads(match.group(2))
    if set(examples) != {"P01", "P02", "P03", "P04", "P06", "P07", "P08", "P09", "P10", "P11", "P12", "P13", "P14", "P15", "P16", "P17", "P18", "P19", "P20", "P21", "forall", "repeat_equal", "repeat_rejected", "repeat_delta"}:
        raise ValueError("canonical v2 template must contain the current predicate and forall examples")
    return examples


def canonical_v2_relation_examples() -> dict[str, dict[str, object]]:
    """Expose embedded symbolic relation examples for parser-focused tests."""

    examples = {}
    for line in canonical_v2_template_text().splitlines():
        match = _RELATION_EXAMPLE.fullmatch(line)
        if match:
            if match.group(1) in examples:
                raise ValueError("canonical relation example name is duplicated")
            examples[match.group(1)] = json.loads(match.group(2))
    return examples
