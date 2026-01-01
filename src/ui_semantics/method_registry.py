"""Machine-readable ownership registry for the current UISemTest method."""

from __future__ import annotations

from typing import Final


def _stage(
    stage: str,
    owner: str,
    symbol: str,
    input_name: str,
    output_name: str,
    downstream: str,
    status: str,
    entrypoint: str,
) -> dict[str, object]:
    return {
        "stage": stage,
        "classification": "current",
        "owner": owner,
        "current_symbol": symbol,
        "input": input_name,
        "output": output_name,
        "downstream_consumer": downstream,
        "status": status,
        "canonical_entrypoint": entrypoint,
        "paper_data": False,
    }


METHOD_STAGE_REGISTRY: Final[tuple[dict[str, object], ...]] = (
    _stage("M0", "stage0_launch.stage0", "stage0_launch.stage0:run_recording_reset", "typed N-actor workflow plus AppProfile", "one reset epoch with strict declared baseline verification and independently authenticated actor environments; the recording coordinator validates nonempty typed probe identities against explicit principal groups (different principals by default), with raw identity retained only in memory", "M1/M12 runtime", "current_typed_workflow_bootstrap", "scripts/uisemtest record|run"),
    _stage("M1", "stage1_record.workflow", "stage1_record.workflow:execute_recording_workflow", "typed workflow plus ready actor environments", "completed/rejected typed workflow with ordered action/decision correspondence, immediate action-local before/after page states, scoped locators, one-shot native dialog handling, body drains and actor bundles; explicit principal_group/session_ref is checked with actual authenticated probes and independent browser contexts before recording, persisting only verified principal/session relations, not raw identity", "M2", "current_n_actor_workflow_recording", "scripts/uisemtest record --workflow|--suite"),
    _stage("M2", "ui_semantics.offline_pipeline", "ui_semantics.offline_pipeline:build_trace", "completed workflow result and frozen actor bundles", "UiApiTrace ordered by global_step_index with preserved scenario_step_id, exact step windows, complete ordered action request groups, one fail-closed anchor from unique exact typed JSON-scalar input material or exact string locator-leaf evidence, explicit unassigned requests, and internal fail-closed GraphQL operation-kind facts", "M3/M6", "current_workflow_windows_complete_request_groups", "scripts/uisemtest run"),
    _stage("M3", "ui_semantics.offline_pipeline", "ui_semantics.offline_pipeline:build_observational_structure", "RecordingBundle", "observational Stage2/2.5/3 products, including an explicit empty observation structure for a completed UI case with zero admitted API observations", "M4/M5", "current_empty_occurrence_connected", "scripts/uisemtest run"),
    _stage("M4", "ui_semantics.preproposal", "ui_semantics.preproposal:build_discovery_candidate_audit", "Stage2.5 plans and validated probe observations", "DiscoveryCandidateAudit", "M5", "current_local_http_active_offline_audit_only", "scripts/uisemtest run"),
    _stage("M5", "ui_semantics.preproposal", "ui_semantics.preproposal:build_observed_api_catalog", "Stage3 observations", "ObservedApiCatalog with execution-ready operation identity, request/response shapes and Stage1 request refs, possibly empty when no execution-ready operation exists", "M6/M9", "current_r3_observed_request_templates_connected", "scripts/uisemtest run"),
    _stage("M6", "ui_semantics.preproposal", "ui_semantics.preproposal:build_observed_value_flows", "trace plus catalog", "ObservedValueFlowSet", "M7/M11b", "current_connected", "scripts/uisemtest run"),
    _stage("M7", "ui_semantics.preproposal", "ui_semantics.preproposal:build_observed_dependency_graph", "observed value flows", "DependencyGraph", "M8", "current_connected", "scripts/uisemtest run"),
    _stage("M8", "ui_semantics.preproposal", "ui_semantics.preproposal:build_binding_opportunity_set", "dependency graph", "BindingOpportunitySet", "M9", "current_connected", "scripts/uisemtest run"),
    _stage("M9", "ui_semantics.current_freeze", "ui_semantics.current_freeze:write_current_v2_input_freeze", "M2-M8 frozen observations", "protocol-neutral atomic action cards and bounded one-hop neighborhoods preserving complete request groups, UI changes, value flow, dependencies, setup domains, catalog observations, strict transition facts and identity-lineage clues; neutral recorded DOM declarations and exact typed request parameter evidence preserve provenance, sensitive exclusions and dynamic binding needs. M1 verified principal/session relations and session_ref accompany request evidence. The global executable language is the finite 20P/17C subset with current detail v22; no per-card predicate restrictions, actor-name oracle, new scan schedule or producer-denominator change", "M10", "current_cpv_workflow_repetition_participants_connected", "scripts/uisemtest run"),
    _stage("M10", "ui_semantics.proposal_run", "ui_semantics.proposal_run:execute_v2_proposal_run", "M9 complete fact freeze plus frozen compact scan batches and frozen Codex CLI provider policy; one complete independent proposal round with explicitly requested gpt-6-astra / xhigh, canonical union mode, runtime concurrency twelve, per-call retry_limit three, then one bounded completion call for each uncovered mechanically unique write-center or current query-relation opportunity", "the existing bounded scan/detail/completion and independent-round union process admits one frozen hypothesis per candidate using observed roles, strict parameter provenance and the executable C/P language; the program alone constructs V1-V9. Finite signatures cover producer-free S, exact finite Q, W point/create/delete/state/projection/inverse/read preservation, C05 repeated equal/rejected/delta, C06 or C12 negative rejection/preservation and A principal/session relations. J freezes finite multi-response P08/P19 observation roles and consistency; D freezes time origin, exact duration sources, finite sample schedule or observed timestamped evidence. Candidates never choose protocol_kind. Fixed composites remain one primary proposition. Core normalization removes P20 physical projection references and unordered field-list differences while retaining real selector, comparison, principal/session and negative-boundary semantics; no raw-response or exact-payload rewrite", "M11a", "current_cpv_multi_resource_temporal_connected", "scripts/uisemtest run"),
    _stage("M11a", "ui_semantics.m11_bridge", "ui_semantics.m11_bridge:bridge_v2_proposal_run_to_m11", "V2ProposalRunLineage with M10 constructed execution plans plus frozen trace/applicability/value-flow/dependency facts, either produced in the same run or loaded from a prebound complete self-contained M1-M10 forensic source through the sole current entrypoint", "a faithful candidate/constructed-plan bridge carrying all parameter, finite step/checkpoint/occurrence, identity/session, query and negative-detector fields unchanged; reconstructs the bounded ordered setup domain from frozen recording facts outside the provider view. A producer-free S remains producer-free. This bridge is not yet executable material and does not invent setup outcomes or choose a different protocol", "M11b", "current_cpv_multi_resource_temporal_connected", "scripts/uisemtest run"),
    _stage("M11b", "ui_semantics.m11b_materializer", "ui_semantics.m11b_materializer:materialize_current_route_s_inputs", "M11a plus bounded setup domain, typed value flow, exact M2 recording identities, M9 request projections, reset material aliases, authenticated profile identity paths, exact byte-pinned recording workflow dynamic-input symbols, and protocol shape", "the existing ordered setup and technical dependency closure plus exact resource, workflow-input and logical/fresh binding produce execution_material for V1-V9. Name-agnostic stable locators, equivalent P14 expressions, exact dynamic-input symbols and deferred producer/before captures retain uniqueness/type/scope requirements. New W includes point resource read, two real inverse actions and independent read preservation; V5 retains every occurrence and per-epoch request recipe; N distinguishes standalone from preservation and preserves actual auth/session boundary; A carries verified principal/session topology. J preserves exact resource/phase/query selectors and finite scope; D preserves the same fresh action and observer endpoints plus its original timing operands. Only earlier same-epoch sources may supply fresh values; no cross-session authentication copying, guessed locator, filtered target field or subject semantic oracle", "M12", "current_cpv_multi_resource_temporal_connected", "scripts/uisemtest run"),
    _stage("M12", "ui_semantics.current_protocols", "ui_semantics.current_protocols:execute_current_protocol", "materialized canonical candidates plus protocol evidence and frozen neutral bounded semantic-stability policy", "the sole current protocol facade executes finite V1-V9 plans. V1 causal validity gates remain prior to comparison. S and Q retain strict actual JSON, exact arithmetic, scope and selector validation. W checks general P04 applicability before acting, point-delete existence and frozen absence criteria, actual independent read or forward/intermediate/inverse sequence. V5 freezes actual request parameters before first send, executes each occurrence separately and compares the prescribed single/two-epoch checkpoints through repeated_execution. N evaluates a standalone frozen P02 rejection detector or rejection AND P20 preservation through negative_no_effect; real 5xx/transport is not rejection success. A verifies actual principal/session topology after setup and evaluates one target relation; pure point-status claims need no unrelated JSON body. V9 reuses exact arithmetic and finite collection closure across frozen responses; sequential reads prove only their stated consistency, not an atomic snapshot. V8 records actual transport send/receive times, uses a frozen finite schedule, and separates returned samples from observed historical state/event/interval evidence. Shared DSL preserves exact numeric rules, projection checks and sensitive-value boundaries. Trusted false survives later unrelated unknown/fault with diagnostics after required validity/applicability is established; missing evidence is never substituted with a favorable value", "M13", "current_cpv_multi_resource_temporal_connected", "scripts/uisemtest run"),
    _stage("M13", "ui_semantics.current_protocols", "ui_semantics.current_protocols:build_current_protocol_tests", "validated V1-V9 protocol results", "validated V1-V9 results compile to one immutable certified primary assertion plus its actual generic checks; preserve every finite reset/setup/prepare/request/observation occurrence, role, session topology, parameter, scope, detector and fixed component check. V5 compiles only the required one/two epochs; standalone N has no invented observer, inverse retains its real second action and intermediate observation. J and D retain every observation checkpoint, consistency or timing parameter and identity requirement; temporal setup/before observation is not a timed business sample. Fixed composites do not increase candidate count. Existing reporting distinguishes basic constraints, business relations and generic partial overlap; no M12 boolean becomes a fresh M14 assertion result", "M14", "current_cpv_multi_resource_temporal_connected", "scripts/uisemtest run"),
    _stage("M14", "ui_semantics.current_protocols", "ui_semantics.current_protocols:run_current_protocol_calibration", "protocol-tagged certified suite with normal_runs frozen at one and the same neutral bounded semantic-stability policy", "normal_runs remains 1 with 1-of-1 retention; each certified test re-executes its frozen finite plan and recomputes through the same shared DSL or protocol evaluator using this run actual requests and new responses. V5 retains unique reset_refs per required epoch but counts as one normal run; frozen repeated request bytes are sent per occurrence and fresh resources are rebuilt across epochs. N verifies actual authorization material and optional principal topology; standalone and preserve shapes stay distinct. W inverse/point and A identity/status checks retain their actual runtime evidence. After protocol validity/applicability, trusted primary false is not hidden by unrelated generic unknown, with diagnostics retained. No retention from incomplete required evidence or reused M12 truth. Twenty named P families, seventeen C entries and V1-V9 are finite implemented subsets; V8 and V9 are connected through fresh common evaluators; no polling-based exact-time or continuous-state claim without timestamped server evidence. Export displays the full plan and delegates to this same runtime; no claim of repeated-reset stability from normal_runs=1", "terminal consumer", "current_cpv_multi_resource_temporal_connected", "scripts/uisemtest run"),
)


SUITE_ORCHESTRATION: Final[dict[str, object]] = {
    "stage": "SUITE_ORGANIZATION",
    "classification": "current_non_scientific_organization",
    "owner": "ui_semantics.current_suite",
    "current_symbol": "ui_semantics.current_suite:record_current_suite/run_current_suite/aggregate_suite_case_summaries",
    "input": "recording suite manifest partitioning independent typed workflows into cases and modules",
    "output": "independent case roots with cross-case M10 preparation sharing one global provider concurrency bound when union mode has no active probes; all recording, target/reset and M11-M14 work stays serial in manifest order. Case/module/system occurrence summaries keep separate admitted-M10 and retained-M14 canonical relation-core dedup only after downstream identities exist; post-hoc UI-only coverage remains outside the API relation funnel",
    "downstream_consumer": "existing M0-M14 owners per case",
    "status": "current_dual_system_r7_ui_only_reporting_complete",
    "canonical_entrypoint": "scripts/uisemtest record|run --suite",
    "paper_data": False,
}


AUTH_SESSION_STRATUM: Final[tuple[dict[str, object], ...]] = (
    {
        "stage": "AUTH_PARTITION",
        "classification": "current",
        "owner": "ui_semantics.offline_producer_partition",
        "current_symbol": "ui_semantics.offline_producer_partition:partition_offline_producers",
        "input": "UiApiTrace plus typed AppProfile and exact frozen HAR response statuses",
        "output": "domain_business plus exact typed/grounded/2xx auth_session strata; non-2xx occurrences retained outside the positive auth denominator",
        "downstream_consumer": "M12_AUTH_SESSION",
        "status": "current_partition_connected_frozen_status_2xx_fail_closed",
        "canonical_entrypoint": "scripts/uisemtest run",
        "paper_data": False,
    },
    {
        "stage": "M12_AUTH_SESSION",
        "classification": "current",
        "owner": "ui_semantics.auth_session_stratum",
        "current_symbol": "ui_semantics.auth_session_stratum:evaluate_auth_session_stratum",
        "input": "typed auth_session producer stratum",
        "output": "auth_session_qualification",
        "downstream_consumer": "M13_AUTH_SESSION",
        "status": "current_qualification_connected",
        "canonical_entrypoint": "scripts/uisemtest run",
        "paper_data": False,
    },
    {
        "stage": "M13_AUTH_SESSION",
        "classification": "current",
        "owner": "ui_semantics.auth_session_stratum",
        "current_symbol": "ui_semantics.auth_session_stratum:compile_auth_session_tests",
        "input": "confirmed auth_session qualification rows",
        "output": "auth_session_tests",
        "downstream_consumer": "M14_AUTH_SESSION",
        "status": "current_qualification_connected",
        "canonical_entrypoint": "scripts/uisemtest run",
        "paper_data": False,
    },
    {
        "stage": "M14_AUTH_SESSION",
        "classification": "current",
        "owner": "ui_semantics.auth_session_stratum",
        "current_symbol": "ui_semantics.auth_session_stratum:calibrate_auth_session_tests",
        "input": "compiled auth_session tests",
        "output": "auth_session_calibration plus final_suite_index",
        "downstream_consumer": "terminal final suite index",
        "status": "current_qualification_connected",
        "canonical_entrypoint": "scripts/uisemtest run",
        "paper_data": False,
    },
)


UI_ONLY_COVERAGE_STRATUM: Final[dict[str, object]] = {
    "stage": "UI_ONLY_COVERAGE",
    "classification": "current_non_scientific_evaluation",
    "owner": "ui_semantics.effect_reference_report",
    "current_symbol": "ui_semantics.effect_reference_report:build_ui_coverage_report/evaluate_ui_recording_case",
    "input": "frozen typed workflows plus M1 workflow result, action log, deterministic decision log, and page-state manifest",
    "output": "auditable passed/failed/incomplete/unavailable UI coverage rows with API relation funnel explicitly not applicable",
    "downstream_consumer": "suite report/export only",
    "status": "current_r7_frozen_m1_ui_only_coverage",
    "canonical_entrypoint": "scripts/build_ui_coverage_report.py",
    "paper_data": False,
}


POST_M14_REPORTING: Final[tuple[dict[str, object], ...]] = (
    {
        "stage": "POST_M14_PYTEST_EXPORT",
        "classification": "current_non_scientific_reporting",
        "owner": "ui_semantics.pytest_export",
        "current_symbol": "ui_semantics.pytest_export:export_pytest_project",
        "input": "immutable M14 final calibrated suite, aligned retained canonical relation-core occurrences, M11b execution material, and read-only M10 raw call/ordinal provenance",
        "output": "readable pytest plus catalog with deterministic producer/observer/predicate summary, physical occurrence versus canonical-core counts, non-normative raw rationale references, and exact single-JSONPath schema_type scope; V2 shows only its actual setup/observation steps, shows P02 operators, P03 bounds/enumeration, P09 target/reference direction, P10 frozen calendar/pattern rule, P11 units/newline/empty/comparison and P15 actual-response key basis, plus forall guard/body/scope, labels basic constraints separately from structurally defined request semantic relations and generic baseline through the shared classification owner, and preserves the shared generic_baseline_overlap associations for P01 present/P21 as same-field partial overlap, explicitly not full-verdict equivalent or usable for net-increment deduplication, without counting these as business gains; new V4 summaries show one-field preservation, P04 pre-action from and post-action to, or P07 two-checkpoint direction, while execution still delegates to the same fresh M14 runtime; sixth-slice descriptions expose P08/P19 formulas and all frozen numeric rules, P13 scalar membership, P16 order/multiset checks, P17 representation/basis and query transform/scope without copying their execution logic",
        "downstream_consumer": "human review or unchanged current M14 runtime",
        "status": "current_cpv_arithmetic_query_readable_export",
        "canonical_entrypoint": "scripts/uisemtest export-pytest",
        "paper_data": False,
    },
    {
        "stage": "POST_M14_EFFECT_REFERENCE",
        "classification": "current_non_scientific_reporting",
        "owner": "ui_semantics.effect_reference_report",
        "current_symbol": "ui_semantics.effect_reference_report:build_report",
        "input": "frozen per-case M10-M14 artifacts plus independently defined target-workflow reference",
        "output": "physical retained occurrences and canonical relation cores split into target-associated and setup-associated reporting sets, with deterministic business summaries and non-normative raw rationale references",
        "downstream_consumer": "suite report/export only",
        "status": "current_r9_readable_effect_reference",
        "canonical_entrypoint": "scripts/build_effect_reference_report.py",
        "paper_data": False,
    },
)

CODE_OWNERSHIP: Final[dict[str, tuple[str, ...]]] = {
    "current": (
        "scripts/uisemtest",
        "ui_semantics.cli",
        "ui_semantics.current_orchestrator",
        "ui_semantics.current_suite",
        "ui_semantics.current_providers",
        "ui_semantics.current_protocols",
        "ui_semantics.current_route_s",
        "ui_semantics.route_s_capture_redaction",
        "ui_semantics.auth_session_stratum",
    ),
    "compatibility": (
        "ui_semantics.compatibility",
        "ui_semantics.coordinator",
        "ui_semantics.maintenance_cli",
        "ui_semantics.pipeline",
        "ui_semantics.proposers",
        "ui_semantics.providers",
        "ui_semantics.semantic_edges",
    ),
    "historical": (
        "v2_pipeline",
        "scripts.e1",
        "scripts.e1g3",
        "scripts.e1r2",
        "scripts.e1r3",
        "scripts.e1r4",
        "scripts.e1r5",
        "scripts.e1r6",
        "scripts.e1r7",
        "scripts.e3",
        "ui_semantics.route_s",
        "ui_semantics.route_s_v2",
        "ui_semantics.route_s_v3",
        "ui_semantics.route_s_v4",
        "ui_semantics.route_s_v5",
        "ui_semantics.route_s_runtime_v5",
        "ui_semantics.route_s_validation_v5",
    ),
    "evaluation": ("ui_semantics.eval_replay", "eval.ui_semantics", "research.graphamp"),
    "reporting": (
        "ui_semantics.effect_reference_report",
        "ui_semantics.pytest_export",
    ),
}


HISTORICAL_OR_COMPATIBILITY: Final[tuple[str, ...]] = (
    *CODE_OWNERSHIP["compatibility"],
    *CODE_OWNERSHIP["historical"],
    *CODE_OWNERSHIP["evaluation"],
)
