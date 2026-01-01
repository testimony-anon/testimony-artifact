"""Mechanical boundary audit for the actual current import closure."""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .method_registry import (
    AUTH_SESSION_STRATUM,
    CODE_OWNERSHIP,
    HISTORICAL_OR_COMPATIBILITY,
    METHOD_STAGE_REGISTRY,
)


CURRENT_IMPORT_SEEDS = (
    "ui_semantics.cli",
    "ui_semantics.current_orchestrator",
    "ui_semantics.auth_session_stratum",
)
FORBIDDEN_CLOSURE_PREFIXES = (
    "ui_semantics.coordinator",
    "ui_semantics.pipeline",
    "ui_semantics.providers",
    "ui_semantics.proposers",
    "ui_semantics.semantic_edges",
    "v2_pipeline",
    "src.v2_pipeline",
    "scripts.e1",
    "scripts.e3",
)
RETIRED_CURRENT_ROUTE_S_MODULES = frozenset({
    "ui_semantics.route_s",
    "ui_semantics.route_s_v2",
    "ui_semantics.route_s_v3",
    "ui_semantics.route_s_v4",
    "ui_semantics.route_s_v5",
    "ui_semantics.route_s_runtime_v5",
    "ui_semantics.route_s_validation_v5",
    "ui_semantics.runtime",
})
INTERNAL_STAGE_ROOT_SYMBOLS = frozenset({
    "V2CandidateLineage",
    "load_v2_candidate_lineage",
    "BindingOpportunitySet",
    "DiscoveryCandidateAudit",
    "ObservedApiCatalog",
    "ObservedValueFlowSet",
    "PreProposalEvidencePackage",
    "ProposalEvidenceView",
    "RenderedCandidateInput",
    "build_preproposal_mainline",
    "build_ui_trace",
    "build_ui_trace_from_bundles",
    "RenderedProposalProvider",
    "RenderedProposalProviderAdapter",
    "ProposalCallSpec",
    "ProposalRunPlan",
    "V2ProposalRunLineage",
    "execute_v2_proposal_run",
    "load_v2_proposal_run_lineage",
    "bridge_v2_proposal_run_to_m11",
})
LEGACY_ROOT_SYMBOLS = frozenset({
    "OpenAICompatibleProvider",
    "ProposalProvider",
    "ProposalBatch",
    "propose_assertion_transfer",
    "propose_constraint_inputs",
    "propose_semantic_edges",
    "propose_ui_diff_assertions",
    "UiSemanticsConfig",
})
HISTORICAL_MARKERS = (
    "src/v2_pipeline/README.md",
    "scripts/e1/README.md",
    "scripts/e1g3/README.md",
    "scripts/e1r2/README.md",
    "scripts/e1r3/README.md",
    "scripts/e1r4/README.md",
    "scripts/e1r5/README.md",
    "scripts/e1r6/README.md",
    "scripts/e1r7/README.md",
    "scripts/e3/README.md",
)
_DIRECT_VERSION_IMPORT = re.compile(
    r"(?:from\s+\.|from\s+ui_semantics\.)(route_s(?:_v[1-5]|_runtime_v5|_validation_v5)?)\s+import"
)
_CURRENT_ROUTE_S_FACADE_IMPORT = re.compile(
    r"from\s+(?:\.current_route_s|ui_semantics\.current_route_s)\s+import"
)
_CURRENT_ROUTE_S_IMPLEMENTATION_IMPORT = re.compile(
    r"(?:from\s+(?:\.current_route_s|ui_semantics\.current_route_s)\."
    r"(?:core|runtime|validation)\s+import|"
    r"import\s+ui_semantics\.current_route_s\."
    r"(?:core|runtime|validation)(?:\s+as\s+\w+)?)"
)


def audit_current_boundary(
    repo_root: str | Path,
    *,
    proposal_run_roots: tuple[str | Path, ...] = (),
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    active = json.loads((root / "docs/ACTIVE-EXECUTION.json").read_text(encoding="utf-8"))
    closure = _runtime_import_closure(root)
    forbidden = sorted(
        module
        for module in closure
        if module.startswith(FORBIDDEN_CLOSURE_PREFIXES)
        or module in RETIRED_CURRENT_ROUTE_S_MODULES
    )
    retired_route_s = sorted(RETIRED_CURRENT_ROUTE_S_MODULES & set(closure))
    direct_route_s_imports = _direct_route_s_consumer_imports(root, closure)
    implementation_imports = _current_route_s_implementation_consumer_imports(
        root, closure
    )
    facade_imports = _current_route_s_facade_consumer_imports(root, closure)
    symbol_rows = [*_registry_symbols(METHOD_STAGE_REGISTRY), *_registry_symbols(AUTH_SESSION_STRATUM)]
    package = importlib.import_module("ui_semantics")
    compatibility = importlib.import_module("ui_semantics.compatibility")
    root_exports = set(package.__all__)
    run_roots = [Path(item).resolve() for item in proposal_run_roots]
    provider_calls = sum(
        int(json.loads((run_root / "proposal_run_completion.json").read_text())["provider_logical_call_count"])
        for run_root in run_roots
    )
    stages = {str(row["stage"]) for row in METHOD_STAGE_REGISTRY}
    checks = {
        "current_import_closure_excludes_legacy_modules": not forbidden,
        "current_import_closure_excludes_retired_route_s_modules": not retired_route_s,
        "current_consumers_exclude_versioned_route_s_imports": not direct_route_s_imports,
        "current_consumers_exclude_route_s_implementation_imports": not implementation_imports,
        "current_route_s_consumers_use_facade": bool(facade_imports),
        "package_root_has_no_internal_stage_api": not root_exports
        and all(not hasattr(package, name) for name in INTERNAL_STAGE_ROOT_SYMBOLS),
        "package_root_does_not_recommend_legacy_providers_or_proposers": root_exports.isdisjoint(LEGACY_ROOT_SYMBOLS)
        and all(not hasattr(package, name) for name in LEGACY_ROOT_SYMBOLS),
        "compatibility_namespace_exposes_legacy_symbols": all(
            hasattr(compatibility, name) for name in LEGACY_ROOT_SYMBOLS
        ),
        "registry_current_symbols_exist": all(item["exists"] for item in symbol_rows),
        "registry_has_unique_stage_owners_and_consumers": all(
            row.get("owner") and row.get("downstream_consumer") and row.get("paper_data") is False
            for row in (*METHOD_STAGE_REGISTRY, *AUTH_SESSION_STRATUM)
        ),
        "historical_directories_have_scope_markers": all(
            (root / ref).is_file() for ref in HISTORICAL_MARKERS
        ),
        "active_live_disabled": active.get("live_allowed") is False,
        "active_target_stopped": active.get("target_running") is False,
        "this_work_package_proposal_run_roots_empty": not run_roots,
        "this_work_package_provider_calls_zero": provider_calls == 0,
        "registry_covers_current_m0_m14": stages >= {
            "M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9",
            "M10", "M11a", "M11b", "M12", "M13", "M14",
        },
        "active_lock_remains_closed": active.get("live_allowed") is False
        and active.get("allowed_entrypoints") == []
        and active.get("target_running") is False,
    }
    return {
        "schema_version": "uisemtest-current-boundary-audit-v3",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "registry": list(METHOD_STAGE_REGISTRY),
        "auth_session_stratum": list(AUTH_SESSION_STRATUM),
        "code_ownership": CODE_OWNERSHIP,
        "historical_or_compatibility": list(HISTORICAL_OR_COMPATIBILITY),
        "current_import_seeds": list(CURRENT_IMPORT_SEEDS),
        "current_import_closure": closure,
        "forbidden_imports": forbidden,
        "retired_route_s_modules_in_current_closure": retired_route_s,
        "direct_versioned_route_s_imports": direct_route_s_imports,
        "current_route_s_implementation_imports": implementation_imports,
        "current_route_s_facade_imports": facade_imports,
        "registry_symbols": symbol_rows,
        "derived_ledger": {
            "proposal_run_root_count": len(run_roots),
            "provider_logical_call_count": provider_calls,
            "live_allowed": active.get("live_allowed"),
            "target_running": active.get("target_running"),
        },
    }


def _runtime_import_closure(root: Path) -> list[str]:
    script = (
        "import json,sys;"
        + ";".join(f"__import__({name!r})" for name in CURRENT_IMPORT_SEEDS)
        + ";print(json.dumps(sorted(name for name in sys.modules "
        "if name.startswith(('ui_semantics','stage0_launch','stage1_record','stage2_recover',"
        "'stage2_5_probe','stage3_gate','stage4_deps','stage5_synth','stage6_ground',"
        "'common','scripts','v2_pipeline','src.v2_pipeline')))))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root)))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return list(json.loads(completed.stdout))


def _direct_route_s_consumer_imports(root: Path, closure: list[str]) -> list[str]:
    hits: list[str] = []
    for module in closure:
        if module.startswith("ui_semantics.current_route_s") or not (
            module.startswith("ui_semantics") or module == "stage6_ground.relation_test_execution"
        ):
            continue
        path = root / "src" / Path(*module.split("."))
        path = path.with_suffix(".py") if path.with_suffix(".py").is_file() else path / "__init__.py"
        if path.is_file() and _DIRECT_VERSION_IMPORT.search(path.read_text(encoding="utf-8")):
            hits.append(module)
    return sorted(hits)


def _current_route_s_facade_consumer_imports(
    root: Path, closure: list[str]
) -> list[str]:
    hits: list[str] = []
    for module in closure:
        if module.startswith("ui_semantics.current_route_s") or not (
            module.startswith("ui_semantics")
            or module == "stage6_ground.relation_test_execution"
        ):
            continue
        path = root / "src" / Path(*module.split("."))
        path = (
            path.with_suffix(".py")
            if path.with_suffix(".py").is_file()
            else path / "__init__.py"
        )
        if path.is_file() and _CURRENT_ROUTE_S_FACADE_IMPORT.search(
            path.read_text(encoding="utf-8")
        ):
            hits.append(module)
    return sorted(hits)


def _current_route_s_implementation_consumer_imports(
    root: Path, closure: list[str]
) -> list[str]:
    hits: list[str] = []
    for module in closure:
        if module.startswith("ui_semantics.current_route_s") or not (
            module.startswith("ui_semantics")
            or module == "stage6_ground.relation_test_execution"
        ):
            continue
        path = root / "src" / Path(*module.split("."))
        path = (
            path.with_suffix(".py")
            if path.with_suffix(".py").is_file()
            else path / "__init__.py"
        )
        if path.is_file() and _CURRENT_ROUTE_S_IMPLEMENTATION_IMPORT.search(
            path.read_text(encoding="utf-8")
        ):
            hits.append(module)
    return sorted(hits)


def _registry_symbols(rows: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    result = []
    for row in rows:
        module_name, symbol = str(row["current_symbol"]).split(":", 1)
        result.append({
            "stage": row["stage"],
            "symbol": row["current_symbol"],
            "exists": hasattr(importlib.import_module(module_name), symbol),
        })
    return result
