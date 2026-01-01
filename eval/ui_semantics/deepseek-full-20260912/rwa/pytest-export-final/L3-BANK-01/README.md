# UISemTest exported pytest suite

This directory is a deterministic, non-scientific Python representation of
the 22 retained business tests in `<ARTIFACT_ROOT>/eval/ui_semantics/deepseek-full-20260912/rwa/m11fix-02/cases/L3-BANK-01/union`.  The generated test
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
.venv/bin/python -m pytest -q <ARTIFACT_ROOT>/eval/ui_semantics/deepseek-full-20260912/rwa/pytest-export-final/L3-BANK-01
```
