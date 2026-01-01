"""Post-hoc effect-level reference reporting for the modular UI suites.

This module is deliberately downstream of M10--M14.  It reads frozen run
artifacts and design documents, but it is not imported by the proposer and it
does not alter any scientific input, candidate, execution, or calibration
artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .pytest_export import (
    SCHEMA_TYPE_ASSERTION_SCOPE,
    deterministic_business_summary,
    load_raw_rationale_sources,
)

SCHEMA_VERSION = "uisemtest-effect-reference-report-v2"
UI_COVERAGE_SCHEMA_VERSION = "uisemtest-ui-only-coverage-report-v1"

SUITES = {
    "conduit": {
        "inventory": "fixtures/recording_workflows/conduit_modular/inventory.json",
        "design": "docs/design/modular-ui-suite/conduit-wp1-design.md",
    },
    "rwa": {
        "inventory": "fixtures/recording_workflows/rwa_modular/inventory.json",
        "design": "docs/design/modular-ui-suite/rwa-wp4-design.md",
    },
}

CONDUIT_AUTH_SESSION_CANDIDATE_CASES = frozenset({"L1-AUTH-03", "L2-AUTH-01"})

# Explicit references from the independent design goal to typed-workflow
# action labels.  An empty set is an intentional N/A (for example UI-only or
# auth/session cases), never an implicit setup classification.
CONDUIT_TARGET_STEP_LABELS: dict[str, frozenset[str]] = {
    "L1-AUTH-01": frozenset({"submit-register"}),
    "L1-AUTH-02": frozenset({"submit-duplicate-register"}),
    "L1-COMMENT-01": frozenset({"post-comment", "accept-comment-delete"}),
    "L1-FEED-02": frozenset({"select-global-feed", "select-popular-tag"}),
    "L1-ARTICLE-01": frozenset({"publish-article"}),
    "L2-ARTICLE-01": frozenset({"publish-article", "select-global-feed", "select-discovery-tag"}),
    "L3-COMMENT-01": frozenset({"accept-comment-delete"}),
    "L4-COMMENT-01": frozenset({"post-comment", "accept-comment-delete"}),
    "L4-DELETE-01": frozenset({"accept-article-delete"}),
    "L4-EDIT-01": frozenset({"publish-edit"}),
    "L4-FAVORITE-01": frozenset({"favorite-article", "select-favorites", "unfavorite-detail", "select-favorites-after-remove"}),
    "L4-FOLLOW-01": frozenset({"select-your-feed"}),
    "L4-PUBLISH-01": frozenset({"publish-article", "select-global-feed", "select-publish-tag"}),
    "L1-AUTH-04": frozenset({"submit-unknown", "submit-wrong-password"}),
    "L1-FEED-01": frozenset({"select-global-feed"}),
    "L1-FEED-03": frozenset({"select-global-feed", "open-page-two", "return-page-one"}),
    "L1-ARTICLE-03": frozenset({"submit-duplicate-title"}),
    "L1-ARTICLE-04": frozenset({"update-article", "select-global-feed"}),
    "L1-ARTICLE-05": frozenset({"accept-article-delete", "select-global-after-delete", "open-deleted-route"}),
    "L1-ARTICLE-07": frozenset({"publish-article"}),
    "L1-SOCIAL-01": frozenset({"follow-profile", "unfollow-profile"}),
    "L2-SETTINGS-01": frozenset({"update-public-profile"}),
    "L2-TAG-01": frozenset({"accept-article-delete", "select-orphan-tag"}),
    "L3-SOCIAL-02": frozenset({"favorite-article", "unfavorite-article"}),
    "L2-SETTINGS-02": frozenset({"update-identity"}),
}

RWA_TARGET_STEP_LABELS: dict[str, frozenset[str]] = {
    "L1-BANK-01": frozenset({"save-bank-account"}), "L1-BANK-03": frozenset({"delete-bank-account"}),
    "L1-DETAIL-01": frozenset({"open-transaction-detail"}), "L1-DETAIL-02": frozenset({"like-transaction"}),
    "L1-DETAIL-03": frozenset({"submit-comment"}), "L1-FEED-01": frozenset({"open-everyone", "open-friends", "open-mine"}),
    "L1-FEED-02": frozenset({"open-everyone"}), "L1-SETTINGS-01": frozenset({"save-settings"}),
    "L1-FEED-03": frozenset({"open-everyone", "open-friends", "open-mine", "paginate-everyone-0", "paginate-everyone-1", "paginate-everyone-2", "paginate-friends-0", "paginate-friends-1", "paginate-friends-2", "paginate-mine-0", "paginate-mine-1", "paginate-mine-2"}),
    "L1-FEED-04": frozenset({"change-amount-max", "clear-combined-amount", "clear-date", "clear-future-date", "select-date-end", "select-date-start"}),
    "L1-FEED-05": frozenset({"change-amount-max", "change-amount-min", "clear-everyone-amount", "clear-friends-amount", "clear-mine-amount"}),
    "L1-NOTIFY-01": frozenset({"open-notifications", "observe-empty-notifications", "dismiss-seed-5lyq9USjvrJT", "dismiss-seed-8NnQy36xaMtB", "dismiss-seed-W0NefbvUhE5h", "dismiss-seed-Wn3GmlnhnfiJ", "dismiss-seed-YcLyZdwuGZAe", "dismiss-seed-dicyOI5JYOvr", "dismiss-seed-mqn7Xnln74JR", "dismiss-seed-n90uuJAZrMPg"}),
    "L1-SEARCH-01": frozenset({"search-email", "search-first", "search-last", "search-phone", "search-self", "search-username"}),
    "L1-TXN-02": frozenset({"submit-payment"}), "L2-ONBOARD-01": frozenset({"onboarding-save"}),
    "L2-PAYMENT-01": frozenset({"open-transaction-detail", "submit-payment"}), "L2-REQUEST-01": frozenset({"open-transaction-detail", "submit-request"}),
    "L2-SETTINGS-01": frozenset({"save-settings"}), "L3-BANK-01": frozenset({"b-open-bankaccounts", "b-reload-bankaccounts", "save-bank-account", "delete-bank-account"}),
    "L3-COMMENT-01": frozenset({"submit-comment"}), "L3-LIKE-01": frozenset({"like-transaction"}),
    "L3-PAYMENT-01": frozenset({"open-mine-feed", "open-transaction-detail", "submit-payment"}),
    "L3-REQUEST-ACCEPT-01": frozenset({"b-accept-request"}), "L3-REQUEST-REJECT-01": frozenset({"b-reject-request"}),
    "L4-COMMENT-NOTIFY-01": frozenset({"submit-comment"}), "L4-LIKE-NOTIFY-01": frozenset({"like-transaction"}),
    "L4-PAYMENT-NOTIFY-01": frozenset({"dismiss-notification", "submit-payment"}), "L4-REQUEST-NOTIFY-01": frozenset({"b-accept-request", "submit-request"}),
    "L4-REQUEST-REJECT-01": frozenset({"b-reject-request", "dismiss-notification", "submit-request"}), "L4-SETTINGS-SEARCH-01": frozenset({"save-settings"}),
    "L4-PAYMENT-FEEDS-01": frozenset({"actor_a-everyone", "actor_a-friends", "actor_a-mine", "actor_a-open-detail", "actor_b-everyone", "actor_b-friends", "actor_b-mine", "actor_b-open-detail", "submit-payment"}),
    "L4-THIRD-PARTY-COMMENT-01": frozenset({"submit-comment"}), "L4-THIRD-PARTY-LIKE-01": frozenset({"like-transaction"}),
}


def _load_target_step_references() -> dict[str, dict[str, frozenset[str]]]:
    return {"conduit": CONDUIT_TARGET_STEP_LABELS, "rwa": RWA_TARGET_STEP_LABELS}

CONDUIT_UI_ONLY_CASES = frozenset(
    {
        "L1-AUTH-06",
        "L1-AUTH-07",
        "L1-ARTICLE-02",
        "L1-ARTICLE-06",
        "L1-COMMENT-02",
        "L1-PROFILE-01",
        "L1-PROFILE-02",
        "L1-SETTINGS-01",
        "L2-GUEST-01",
        "L3-ARTICLE-01",
    }
)

CONDUIT_AUTH_SESSION_CASES = frozenset({"L1-AUTH-03", "L1-AUTH-05", "L2-AUTH-01"})
CONDUIT_MIXED_AUTH_CASES = frozenset({"L2-SETTINGS-02"})

# These business cases have a central API-observable effect plus additional UI
# or navigation claims that the business-relation DSL does not encode.
CONDUIT_PARTIAL_DSL_CASES = frozenset(
    {
        "L1-AUTH-02",
        "L1-AUTH-04",
        "L1-FEED-01",
        "L1-FEED-03",
        "L1-ARTICLE-03",
        "L1-ARTICLE-05",
        "L1-ARTICLE-07",
        "L1-PROFILE-01",
        "L1-PROFILE-02",
        "L2-GUEST-01",
        "L2-SETTINGS-01",
        "L2-SETTINGS-02",
        "L2-TAG-01",
        "L3-ARTICLE-01",
        "L3-COMMENT-01",
        "L3-SOCIAL-02",
        "L4-COMMENT-01",
        "L4-DELETE-01",
        "L4-EDIT-01",
        "L4-FAVORITE-01",
        "L4-FOLLOW-01",
        "L4-PUBLISH-01",
    }
)

RWA_UI_ONLY_CASES = frozenset(
    {
        "L1-AUTH-01",
        "L1-AUTH-03",
        "L1-AUTH-05",
        "L1-NAV-01",
        "L1-BANK-02",
        "L1-SETTINGS-02",
        "L2-FILTER-01",
    }
)
RWA_AUTH_SESSION_CASES = frozenset({"L1-AUTH-02", "L1-AUTH-04", "L1-AUTH-06"})
RWA_MIXED_AUTH_CASES = frozenset({"L2-ONBOARD-01", "L2-ONBOARD-02"})

# RWA targets generally combine a business effect with UI presentation,
# routing, ordering, isolation, or notification claims.  The exceptions below
# have a central relation that the current DSL can express directly.
RWA_FULL_DSL_CASES = frozenset(
    {
        "L1-BANK-01",
        "L1-BANK-03",
        "L1-SETTINGS-01",
        "L1-SEARCH-01",
        "L1-DETAIL-02",
        "L1-DETAIL-03",
        "L2-SETTINGS-01",
        "L3-BANK-01",
        "L3-LIKE-01",
        "L3-COMMENT-01",
        "L4-SETTINGS-SEARCH-01",
    }
)

# Post-R12 semantic classification is deliberately post-hoc.  It describes
# whether the normalized candidate covers the design dimension, separately
# from the mechanical workflow-step association below.
CONDUIT_C_CLASS_CASES = frozenset(
    {"L1-FEED-01", "L1-ARTICLE-03", "L1-ARTICLE-07", "L2-TAG-01"}
)
CONDUIT_NON_CPV_CASES = frozenset({"L1-AUTH-01", "L1-AUTH-02", "L1-AUTH-04"})
RWA_C_CLASS_CASES = frozenset(
    {
        "L1-TXN-02",
        "L1-FEED-01",
        "L1-FEED-02",
        "L1-FEED-03",
        "L1-FEED-04",
        "L1-FEED-05",
        "L4-THIRD-PARTY-LIKE-01",
        "L4-THIRD-PARTY-COMMENT-01",
    }
)

SEMANTIC_DIMENSIONS: dict[tuple[str, str], tuple[dict[str, str], ...]] = {
    ("conduit", "L1-FEED-01"): (
        {"dimension": "empty_global_feed_invariant", "capability": "deferred_current_cpv", "reason": "Fresh-reset empty collection semantics require deferred P11/V2; no fixed seed oracle is assumed.", "signature": {}},
    ),
    ("conduit", "L1-FEED-03"): (
        {"dimension": "pagination_query_relation", "capability": "current_p17", "reason": "Observed pagination queries are expressible by P15/P17/P18.", "signature": {"predicate_family": {"P15", "P17", "P18"}}},
        {"dimension": "pagination_order_and_partition", "capability": "deferred_current_cpv", "reason": "Ordering and static partition semantics are not an approved current predicate.", "signature": {}},
    ),
    ("conduit", "L1-ARTICLE-04"): (
        {"dimension": "article_edit_read_after_write", "capability": "current_cpv", "reason": "Edit propagation is expressible by the observed article producer and detail observer.", "signature": {"contract_kind": {"C02", "C03"}, "predicate_family": {"P02", "P14"}}},
    ),
    ("conduit", "L1-ARTICLE-05"): (
        {"dimension": "article_delete_projection", "capability": "current_cpv", "reason": "Delete/removal projection is expressible by C03/P01/P12/P14.", "signature": {"contract_kind": {"C03"}, "predicate_family": {"P01", "P12", "P14"}}},
    ),
    ("conduit", "L1-SOCIAL-01"): (
        {"dimension": "follow_lifecycle_projection", "capability": "current_cpv", "reason": "Follow/unfollow projection is expressible by the observed lifecycle relation families.", "signature": {"contract_kind": {"C01", "C03", "C11"}, "predicate_family": {"P01", "P12", "P13", "P14"}}},
    ),
    ("conduit", "L3-SOCIAL-02"): (
        {"dimension": "cross_actor_favorite_projection", "capability": "current_cpv", "reason": "Cross-actor favorite membership/count propagation is expressible by C11 and current member/count predicates.", "signature": {"contract_kind": {"C11"}, "predicate_family": {"P06", "P12", "P13", "P14"}}},
    ),
    ("conduit", "L1-ARTICLE-03"): (
        {
            "dimension": "negative_request_and_state_equivalence",
            "capability": "current_cpv_c06_p20_v6",
            "reason": "Observer/negative-fact evidence is missing; HTTP status alone is generic, while the target needs a negative request plus exact unchanged-state observer.",
        },
    ),
    ("conduit", "L1-ARTICLE-07"): (
        {
            "dimension": "same_actor_tag_length_retention_boundary",
            "capability": "deferred_current_cpv",
            "reason": "Current P13 does not define the approved same-actor retain/drop boundary contract.",
        },
    ),
    ("conduit", "L2-TAG-01"): (
        {
            "dimension": "same_actor_tag_persistence_after_article_delete",
            "capability": "deferred_current_cpv",
            "reason": "Current CPV has no approved same-actor no-effect/persistence mapping for this projection.",
        },
    ),
    ("rwa", "L1-FEED-04"): (
        {
            "dimension": "filter_query_subset_or_intersection",
            "capability": "current_p17_partial",
            "reason": "P17 can express an observed query-result subset, but not the complete UI filter boundary claim.",
        },
        {
            "dimension": "static_date_amount_boundary_domain",
            "capability": "deferred_current_cpv",
            "reason": "Static date/amount boundary domains are deferred; no fixed seed oracle is assumed.",
        },
    ),
    ("rwa", "L1-FEED-03"): (
        {"dimension": "recording_pagination_observability", "capability": "current_recording_gap", "reason": "The frozen recording has no target pagination API request for the full design claim.", "signature": {}},
        {"dimension": "pagination_order_and_partition", "capability": "deferred_current_cpv", "reason": "Ordering and static partition semantics are deferred.", "signature": {}},
    ),
    ("rwa", "L1-FEED-01"): (
        {"dimension": "feed_endpoint_membership_variant", "capability": "deferred_current_cpv", "reason": "Public/contacts/personal are distinct endpoints, not a P17 selector-refinement query pair; member/variant semantics are deferred.", "signature": {}},
        {"dimension": "static_feed_order_and_domain", "capability": "deferred_current_cpv", "reason": "Static ordering and value-domain semantics are deferred.", "signature": {}},
    ),
    ("rwa", "L1-FEED-02"): (
        {"dimension": "feed_item_variant_membership", "capability": "deferred_current_cpv", "reason": "Only the public feed is observed; item variant/member semantics and ordering are deferred.", "signature": {}},
    ),
    ("rwa", "L1-TXN-02"): (
        {"dimension": "balance_conservation", "capability": "deferred_current_cpv", "reason": "Aggregate balance/ conservation requires deferred C14/P19/V9.", "signature": {}},
    ),
    ("rwa", "L1-BANK-03"): (
        {"dimension": "bank_account_delete_projection", "capability": "current_cpv", "reason": "Account deletion/member removal is expressible by C03/P14.", "signature": {"contract_kind": {"C03"}, "predicate_family": {"P14"}}},
    ),
    ("rwa", "L1-DETAIL-02"): (
        {"dimension": "transaction_like_lifecycle", "capability": "current_cpv", "reason": "Like/unlike lifecycle is expressible by current member/count transition predicates.", "signature": {"contract_kind": {"C01", "C03"}, "predicate_family": {"P06", "P12", "P13", "P14"}}},
    ),
    ("rwa", "L4-LIKE-NOTIFY-01"): (
        {"dimension": "participant_notification_propagation", "capability": "current_c11", "reason": "C11 notification propagation accepts the current member/count predicates P01/P12/P13/P14.", "signature": {"contract_kind": {"C11"}, "predicate_family": {"P01", "P12", "P13", "P14"}}},
    ),
    ("rwa", "L4-SETTINGS-SEARCH-01"): (
        {"dimension": "settings_cross_actor_propagation", "capability": "current_c11", "reason": "C11 cross-actor propagation accepts the observed scalar/member predicate families.", "signature": {"contract_kind": {"C11"}, "predicate_family": {"P01", "P02", "P12", "P13", "P14"}}},
    ),
    ("rwa", "L1-FEED-05"): (
        {
            "dimension": "filter_query_subset_or_intersection",
            "capability": "current_p17_partial",
            "reason": "P17 can express an observed query-result subset, but not the complete UI filter boundary claim.",
        },
        {
            "dimension": "static_amount_boundary_domain",
            "capability": "deferred_current_cpv",
            "reason": "Static amount boundary domains are deferred; clear/reset UI semantics are not an API predicate.",
        },
    ),
    ("rwa", "L4-THIRD-PARTY-LIKE-01"): (
        {
            "dimension": "third_party_notification_propagation",
            "capability": "current_c11",
            "reason": "C11 can express notification propagation to the other participant.",
            "signature": {"contract_kind": {"C11"}, "predicate_family": {"P01", "P12", "P13", "P14"}},
        },
        {
            "dimension": "same_actor_self_exclusion",
            "capability": "deferred_current_cpv",
            "reason": "Current V7 gate requires different producer and target actors; same-actor self-exclusion is not approved.",
        },
    ),
    ("rwa", "L4-THIRD-PARTY-COMMENT-01"): (
        {
            "dimension": "third_party_notification_propagation",
            "capability": "current_c11",
            "reason": "C11 can express notification propagation to the other participant.",
            "signature": {"contract_kind": {"C11"}, "predicate_family": {"P01", "P12", "P13", "P14"}},
        },
        {
            "dimension": "same_actor_self_exclusion",
            "capability": "deferred_current_cpv",
            "reason": "Current V7 gate requires different producer and target actors; same-actor self-exclusion is not approved.",
        },
    ),
}


def _semantic_classification(reference: Mapping[str, Any]) -> str:
    if "business_relation" not in reference["target_strata"] or (
        reference["subject"] == "conduit"
        and reference["case_id"] in CONDUIT_NON_CPV_CASES
    ):
        return "non_cpv"
    return "not_assessed"


def _semantic_dimensions(reference: Mapping[str, Any]) -> list[dict[str, str]]:
    explicit = SEMANTIC_DIMENSIONS.get((str(reference["subject"]), str(reference["case_id"])))
    if explicit:
        signatures = {
            "negative_request_and_state_equivalence": {"contract_kind": "C06", "predicate_family": "P20"},
            "filter_query_subset_or_intersection": {"predicate_family": "P17"},
            "third_party_notification_propagation": {"contract_kind": "C11", "predicate_family": "P02"},
        }
        return [
            {
                **row,
                "signature": {
                    key: sorted(value) if isinstance(value, (set, frozenset)) else value
                    for key, value in row.get("signature", signatures.get(row["dimension"], {})).items()
                },
            }
            for row in explicit
        ]
    return []


DEFAULT_RECORDING_ROOTS = {
    "conduit": "eval/ui_semantics/paper-input-freeze-20260902/conduit/wp3-recordings-03/cases",
    "rwa": "eval/ui_semantics/paper-input-freeze-20260902/rwa/wp6-recordings-01/cases",
}

# These cases retain a non-UI primary reporting stratum, but their frozen
# workflows also contain a UI-only claim required by R7.  The UI claim is
# evaluated independently; it does not move the case or enter an API funnel.
SUPPLEMENTAL_UI_CLAIMS: dict[str, dict[str, str]] = {
    "conduit": {
        "L1-AUTH-04": "invalid_credentials_feedback",
        "L1-AUTH-05": "logout_session_ui",
    },
    "rwa": {
        "L1-AUTH-04": "invalid_credentials_feedback",
        "L1-AUTH-06": "logout_session_ui",
    },
}

FORM_VALIDATION_CASES = frozenset(
    {
        "L1-AUTH-03",
        "L1-AUTH-05",
        "L1-AUTH-07",
        "L1-ARTICLE-02",
        "L1-BANK-02",
        "L1-COMMENT-02",
        "L1-SETTINGS-01",
        "L1-SETTINGS-02",
    }
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _artifact_ref(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _primary_reporting_stratum(row: Mapping[str, Any]) -> str:
    strata = list(row["target_strata"])
    if strata == ["ui_only"]:
        return "ui_only"
    if strata == ["auth_session"]:
        return "auth_session"
    return "business_relation"


def _dialog_expectation(action: Mapping[str, Any]) -> dict[str, str] | None:
    if action.get("close_alert") is True:
        return {"dialog_type": "alert", "disposition": "close"}
    if action.get("accept_confirm") is True:
        return {"dialog_type": "confirm", "disposition": "accept"}
    if action.get("dismiss_confirm") is True:
        return {"dialog_type": "confirm", "disposition": "dismiss"}
    return None


def _wait_projection(wait: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: wait[key]
        for key in ("kind", "pattern", "state", "locator", "duration_ms")
        if key in wait
    }


def _check_category(
    *,
    case_id: str,
    workflow_step_id: str,
    wait: Mapping[str, Any] | None = None,
    dialog: Mapping[str, Any] | None = None,
) -> str:
    label = workflow_step_id.lower()
    if dialog is not None:
        return "native_dialog"
    if case_id in {"L1-AUTH-04"} and "submit" in label:
        return "invalid_credentials_feedback"
    if "logout" in label or "reload-signin" in label:
        return "logout_session_ui"
    if case_id in FORM_VALIDATION_CASES and any(
        token in label
        for token in ("required", "invalid", "short", "mismatch", "empty", "blank")
    ):
        return "form_validation"
    if wait is not None and wait.get("kind") == "url":
        return "redirect_or_navigation"
    if wait is not None and wait.get("kind") == "locator":
        return "control_or_page_state"
    return "workflow_settle"


def _api_relation_not_applicable() -> dict[str, str]:
    return {
        "applicability": "not_applicable",
        "proposed": "N/A",
        "materialized": "N/A",
        "evaluated": "N/A",
        "retained": "N/A",
        "reason": "This row evaluates a frozen UI check, not an API relation candidate.",
    }


def _terminal_ui_row(
    *,
    subject: str,
    case_id: str,
    reference: Mapping[str, Any],
    coverage_scope: str,
    status: str,
    reason_codes: Sequence[str],
    recording_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "case_id": case_id,
        "module_id": reference["module_id"],
        "design_goal": reference["design_goal"],
        "ui_observations": reference["ui_observations"],
        "primary_reporting_stratum": _primary_reporting_stratum(reference),
        "coexisting_target_strata": list(reference["target_strata"]),
        "coverage_scope": coverage_scope,
        "coverage_status": status,
        "reason_codes": list(reason_codes),
        "recording_root": _artifact_ref(recording_root, repo_root),
        "workflow_result_ref": None,
        "workflow_status": None,
        "reported_categories": [],
        "evidence_counts": {
            "workflow_steps": 0,
            "completed_steps": 0,
            "ui_checks": 0,
            "passed_ui_checks": 0,
            "action_decisions": 0,
            "before_page_states": 0,
            "after_page_states": 0,
        },
        "steps": [],
        "api_relation_funnel": _api_relation_not_applicable(),
        "claim_boundary": "The UI result is single-recording evidence. It does not claim cross-reset stability or inspect localStorage contents.",
    }


def evaluate_ui_recording_case(
    *,
    repo_root: Path,
    subject: str,
    reference: Mapping[str, Any],
    workflow_path: Path,
    recording_root: Path,
    coverage_scope: str,
) -> dict[str, Any]:
    """Evaluate one frozen M1 workflow without deriving an API assertion."""

    case_id = str(reference["case_id"])
    result_path = recording_root / "recording_workflow_result.json"
    if not result_path.is_file():
        return _terminal_ui_row(
            subject=subject,
            case_id=case_id,
            reference=reference,
            coverage_scope=coverage_scope,
            status="unavailable",
            reason_codes=("recording_workflow_result_unavailable",),
            recording_root=recording_root,
            repo_root=repo_root,
        )

    workflow = _read_json(workflow_path)
    result = _read_json(result_path)
    workflow_status = result.get("status")
    if workflow_status == "rejected":
        row = _terminal_ui_row(
            subject=subject,
            case_id=case_id,
            reference=reference,
            coverage_scope=coverage_scope,
            status="failed",
            reason_codes=("recording_workflow_rejected",),
            recording_root=recording_root,
            repo_root=repo_root,
        )
        row["workflow_result_ref"] = _artifact_ref(result_path, repo_root)
        row["workflow_status"] = workflow_status
        row["recording_failure"] = result.get("failure")
        return row
    if workflow_status != "completed":
        row = _terminal_ui_row(
            subject=subject,
            case_id=case_id,
            reference=reference,
            coverage_scope=coverage_scope,
            status="incomplete",
            reason_codes=("recording_workflow_not_terminal_complete",),
            recording_root=recording_root,
            repo_root=repo_root,
        )
        row["workflow_result_ref"] = _artifact_ref(result_path, repo_root)
        row["workflow_status"] = workflow_status
        return row

    failed_reasons: list[str] = []
    incomplete_reasons: list[str] = []
    if result.get("workflow_id") != workflow.get("workflow_id"):
        incomplete_reasons.append("workflow_identity_mismatch")

    correspondence_rows = result.get("step_correspondence", [])
    correspondence_by_step = {
        row.get("workflow_step_id"): row for row in correspondence_rows
    }
    if len(correspondence_by_step) != len(correspondence_rows):
        incomplete_reasons.append("duplicate_step_correspondence")

    bundle_by_actor: dict[str, dict[str, Any]] = {}
    for bundle_row in result.get("actor_bundles", []):
        actor_id = bundle_row.get("actor_id")
        manifest_ref = bundle_row.get("manifest_ref")
        if not isinstance(actor_id, str) or not isinstance(manifest_ref, str):
            incomplete_reasons.append("invalid_actor_bundle_reference")
            continue
        manifest_path = recording_root / manifest_ref
        if not manifest_path.is_file():
            incomplete_reasons.append("actor_bundle_manifest_unavailable")
            continue
        manifest = _read_json(manifest_path)
        members = manifest.get("members", {})
        bundle_root = manifest_path.parent
        action_path = bundle_root / str(members.get("ui_action_log", ""))
        decision_path = bundle_root / str(members.get("action_decision_log", ""))
        if not action_path.is_file() or not decision_path.is_file():
            incomplete_reasons.append("actor_bundle_log_unavailable")
            continue
        actions = _read_jsonl(action_path)
        decisions = _read_jsonl(decision_path)
        action_rows: dict[str, tuple[int, dict[str, Any]]] = {}
        decision_rows: dict[str, tuple[int, dict[str, Any]]] = {}
        for line, row in enumerate(actions, start=1):
            action_id = row.get("action_id")
            if action_id in action_rows:
                incomplete_reasons.append("duplicate_ui_action")
            elif isinstance(action_id, str):
                action_rows[action_id] = (line, row)
        for line, row in enumerate(decisions, start=1):
            action_id = row.get("action_id")
            if action_id in decision_rows:
                incomplete_reasons.append("duplicate_action_decision")
            elif isinstance(action_id, str):
                decision_rows[action_id] = (line, row)
        page_state_rows: dict[str, tuple[Path, dict[str, Any]]] = {}
        for page_state in members.get("page_state", []):
            action_id = page_state.get("action_id")
            file_ref = page_state.get("file")
            if not isinstance(action_id, str) or not isinstance(file_ref, str):
                incomplete_reasons.append("invalid_page_state_reference")
                continue
            page_path = bundle_root / file_ref
            if action_id in page_state_rows:
                incomplete_reasons.append("duplicate_page_state")
            else:
                page_state_rows[action_id] = (page_path, page_state)
                if not page_path.is_file():
                    incomplete_reasons.append("page_state_file_unavailable")
        bundle_by_actor[actor_id] = {
            "manifest_path": manifest_path,
            "action_path": action_path,
            "decision_path": decision_path,
            "actions": action_rows,
            "decisions": decision_rows,
            "page_states": page_state_rows,
        }

    step_rows: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    completed_steps = 0
    decision_count = 0
    before_count = 0
    after_count = 0
    workflow_steps = workflow.get("steps", [])
    for step in workflow_steps:
        workflow_step_id = str(step.get("workflow_step_id"))
        actor_id = str(step.get("actor_id"))
        correspondence = correspondence_by_step.get(workflow_step_id)
        action_id = correspondence.get("action_id") if correspondence else None
        step_reasons: list[str] = []
        if correspondence is None:
            step_reasons.append("step_correspondence_unavailable")
        else:
            if correspondence.get("status") != "step_completed":
                failed_reasons.append("step_not_completed")
                step_reasons.append("step_not_completed")
            else:
                completed_steps += 1
            for key in (
                "scenario_step_id",
                "workflow_step_id",
                "global_step_index",
                "actor_id",
            ):
                if correspondence.get(key) != step.get(key):
                    step_reasons.append("step_correspondence_mismatch")
                    incomplete_reasons.append("step_correspondence_mismatch")

        bundle = bundle_by_actor.get(actor_id)
        action_entry = (
            bundle["actions"].get(action_id) if bundle and action_id else None
        )
        decision_entry = (
            bundle["decisions"].get(action_id) if bundle and action_id else None
        )
        before_entry = (
            bundle["page_states"].get(f"before:{action_id}")
            if bundle and action_id
            else None
        )
        after_entry = (
            bundle["page_states"].get(action_id) if bundle and action_id else None
        )
        if action_entry is None:
            step_reasons.append("ui_action_unavailable")
            incomplete_reasons.append("ui_action_unavailable")
        else:
            action_row = action_entry[1]
            for key in (
                "scenario_step_id",
                "workflow_step_id",
                "global_step_index",
            ):
                if action_row.get(key) != step.get(key):
                    step_reasons.append("ui_action_step_identity_mismatch")
                    incomplete_reasons.append("ui_action_step_identity_mismatch")
            if action_row.get("action_type") != (step.get("action") or {}).get("kind"):
                step_reasons.append("ui_action_type_mismatch")
                incomplete_reasons.append("ui_action_type_mismatch")
        if decision_entry is None:
            step_reasons.append("action_decision_unavailable")
            incomplete_reasons.append("action_decision_unavailable")
        else:
            decision_count += 1
        if before_entry is None:
            step_reasons.append("before_page_state_unavailable")
            incomplete_reasons.append("before_page_state_unavailable")
        else:
            before_count += 1
        if after_entry is None:
            step_reasons.append("after_page_state_unavailable")
            incomplete_reasons.append("after_page_state_unavailable")
        else:
            after_count += 1

        decision = decision_entry[1] if decision_entry else {}
        detail = decision.get("detail", {})
        if decision_entry:
            if decision.get("strategy") != "deterministic_workflow":
                step_reasons.append("decision_strategy_mismatch")
                incomplete_reasons.append("decision_strategy_mismatch")
            if detail.get("executed") is not True:
                step_reasons.append("action_not_executed")
                failed_reasons.append("action_not_executed")
            for key in (
                "scenario_step_id",
                "workflow_step_id",
                "global_step_index",
                "actor_id",
            ):
                if detail.get(key) != step.get(key):
                    step_reasons.append("decision_step_identity_mismatch")
                    incomplete_reasons.append("decision_step_identity_mismatch")

        expected_waits = list(step.get("waits", []))
        actual_waits = list(detail.get("wait_results", [])) if decision_entry else []
        if len(expected_waits) != len(actual_waits):
            step_reasons.append("wait_result_count_mismatch")
            incomplete_reasons.append("wait_result_count_mismatch")
        for index, expected in enumerate(expected_waits):
            actual = actual_waits[index] if index < len(actual_waits) else None
            check_status = "incomplete"
            if actual is not None:
                if actual.get("kind") != expected.get("kind"):
                    step_reasons.append("wait_kind_mismatch")
                    incomplete_reasons.append("wait_kind_mismatch")
                elif actual.get("status") == "satisfied":
                    check_status = "passed"
                else:
                    check_status = "failed"
                    step_reasons.append("wait_not_satisfied")
                    failed_reasons.append("wait_not_satisfied")
            checks.append(
                {
                    "check_id": f"{subject}:{case_id}:{action_id}:wait:{index}",
                    "workflow_step_id": workflow_step_id,
                    "scenario_step_id": step.get("scenario_step_id"),
                    "actor_id": actor_id,
                    "action_id": action_id,
                    "category": _check_category(
                        case_id=case_id,
                        workflow_step_id=workflow_step_id,
                        wait=expected,
                    ),
                    "check_kind": "workflow_wait",
                    "expected": _wait_projection(expected),
                    "actual": actual,
                    "status": check_status,
                    "decision_ref": (
                        f"{_artifact_ref(bundle['decision_path'], repo_root)}#L{decision_entry[0]}"
                        if bundle and decision_entry
                        else None
                    ),
                    "after_page_state_ref": (
                        _artifact_ref(after_entry[0], repo_root)
                        if after_entry
                        else None
                    ),
                    "api_relation_funnel": _api_relation_not_applicable(),
                }
            )

        dialog_expected = _dialog_expectation(step.get("action", {}))
        if dialog_expected is not None:
            actual_dialog = detail.get("dialog_result") if decision_entry else None
            dialog_status = "incomplete"
            if actual_dialog is not None:
                if (
                    actual_dialog.get("dialog_type") == dialog_expected["dialog_type"]
                    and actual_dialog.get("disposition")
                    == dialog_expected["disposition"]
                    and actual_dialog.get("status") == "handled"
                ):
                    dialog_status = "passed"
                else:
                    dialog_status = "failed"
                    step_reasons.append("dialog_not_handled_as_declared")
                    failed_reasons.append("dialog_not_handled_as_declared")
            else:
                step_reasons.append("dialog_result_unavailable")
                incomplete_reasons.append("dialog_result_unavailable")
            checks.append(
                {
                    "check_id": f"{subject}:{case_id}:{action_id}:dialog",
                    "workflow_step_id": workflow_step_id,
                    "scenario_step_id": step.get("scenario_step_id"),
                    "actor_id": actor_id,
                    "action_id": action_id,
                    "category": _check_category(
                        case_id=case_id,
                        workflow_step_id=workflow_step_id,
                        dialog=dialog_expected,
                    ),
                    "check_kind": "native_dialog",
                    "expected": dialog_expected,
                    "actual": actual_dialog,
                    "status": dialog_status,
                    "decision_ref": (
                        f"{_artifact_ref(bundle['decision_path'], repo_root)}#L{decision_entry[0]}"
                        if bundle and decision_entry
                        else None
                    ),
                    "after_page_state_ref": (
                        _artifact_ref(after_entry[0], repo_root)
                        if after_entry
                        else None
                    ),
                    "api_relation_funnel": _api_relation_not_applicable(),
                }
            )

        step_rows.append(
            {
                "workflow_step_id": workflow_step_id,
                "scenario_step_id": step.get("scenario_step_id"),
                "global_step_index": step.get("global_step_index"),
                "actor_id": actor_id,
                "action_id": action_id,
                "action_type": (step.get("action") or {}).get("kind"),
                "correspondence_status": (
                    correspondence.get("status") if correspondence else None
                ),
                "decision_executed": detail.get("executed") if decision_entry else None,
                "wait_result_statuses": [row.get("status") for row in actual_waits],
                "dialog_status": (
                    (detail.get("dialog_result") or {}).get("status")
                    if dialog_expected is not None
                    else "not_applicable"
                ),
                "action_ref": (
                    f"{_artifact_ref(bundle['action_path'], repo_root)}#L{action_entry[0]}"
                    if bundle and action_entry
                    else None
                ),
                "decision_ref": (
                    f"{_artifact_ref(bundle['decision_path'], repo_root)}#L{decision_entry[0]}"
                    if bundle and decision_entry
                    else None
                ),
                "before_page_state_ref": (
                    _artifact_ref(before_entry[0], repo_root) if before_entry else None
                ),
                "after_page_state_ref": (
                    _artifact_ref(after_entry[0], repo_root) if after_entry else None
                ),
                "reason_codes": sorted(set(step_reasons)),
            }
        )

    if len(correspondence_rows) != len(workflow_steps):
        incomplete_reasons.append("workflow_step_count_mismatch")
    if not checks:
        incomplete_reasons.append("ui_check_evidence_unavailable")

    if failed_reasons:
        coverage_status = "failed"
        reason_codes = sorted(set(failed_reasons + incomplete_reasons))
    elif incomplete_reasons:
        coverage_status = "incomplete"
        reason_codes = sorted(set(incomplete_reasons))
    else:
        coverage_status = "passed"
        reason_codes = ["all_frozen_ui_checks_satisfied"]

    return {
        "subject": subject,
        "case_id": case_id,
        "module_id": reference["module_id"],
        "design_goal": reference["design_goal"],
        "ui_observations": reference["ui_observations"],
        "primary_reporting_stratum": _primary_reporting_stratum(reference),
        "coexisting_target_strata": list(reference["target_strata"]),
        "coverage_scope": coverage_scope,
        "coverage_status": coverage_status,
        "reason_codes": reason_codes,
        "recording_root": _artifact_ref(recording_root, repo_root),
        "workflow_ref": _artifact_ref(workflow_path, repo_root),
        "workflow_result_ref": _artifact_ref(result_path, repo_root),
        "workflow_status": workflow_status,
        "reset_epoch": (result.get("reset_epoch") or {}).get("record_id"),
        "reported_categories": sorted({check["category"] for check in checks}),
        "evidence_counts": {
            "workflow_steps": len(workflow_steps),
            "completed_steps": completed_steps,
            "ui_checks": len(checks),
            "passed_ui_checks": sum(check["status"] == "passed" for check in checks),
            "action_decisions": decision_count,
            "before_page_states": before_count,
            "after_page_states": after_count,
        },
        "steps": step_rows,
        "checks": checks,
        "api_relation_funnel": _api_relation_not_applicable(),
        "claim_boundary": "Pass means this one frozen workflow completed with matching deterministic actions, satisfied declared waits or dialog handling, and paired page-state artifacts. It does not prove cross-reset stability or directly inspect localStorage contents.",
    }


def _workflow_paths(repo_root: Path, subject: str) -> dict[str, Path]:
    inventory_path = repo_root / SUITES[subject]["inventory"]
    inventory = _read_json(inventory_path)
    return {
        row["case_id"]: inventory_path.parent / row["workflow"]
        for row in inventory["cases"]
    }


def build_ui_coverage_report(
    repo_root: Path,
    recording_roots: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Build the independent R7 UI-only coverage report from frozen M1 data."""

    reference = build_reference_rows(repo_root)
    roots = {
        subject: (
            Path(recording_roots[subject])
            if recording_roots is not None
            else repo_root / DEFAULT_RECORDING_ROOTS[subject]
        ).resolve()
        for subject in SUITES
    }
    partition_ids: dict[str, dict[str, list[str]]] = {}
    coverage_rows: dict[str, list[dict[str, Any]]] = {}
    for subject, reference_rows in reference.items():
        workflow_paths = _workflow_paths(repo_root, subject)
        partition_ids[subject] = {
            stratum: sorted(
                str(row["case_id"])
                for row in reference_rows
                if _primary_reporting_stratum(row) == stratum
            )
            for stratum in ("business_relation", "auth_session", "ui_only")
        }
        coverage_rows[subject] = []
        supplemental = SUPPLEMENTAL_UI_CLAIMS[subject]
        for row in reference_rows:
            case_id = str(row["case_id"])
            primary = _primary_reporting_stratum(row)
            if primary == "ui_only":
                scope = "primary_ui_only_design_goal"
            elif case_id in supplemental:
                scope = f"supplemental_ui_claim:{supplemental[case_id]}"
            else:
                continue
            coverage_rows[subject].append(
                evaluate_ui_recording_case(
                    repo_root=repo_root,
                    subject=subject,
                    reference=row,
                    workflow_path=workflow_paths[case_id],
                    recording_root=roots[subject] / case_id,
                    coverage_scope=scope,
                )
            )

    all_reference_ids = {
        subject: {str(row["case_id"]) for row in rows}
        for subject, rows in reference.items()
    }
    disjoint_checks: dict[str, dict[str, Any]] = {}
    for subject, strata in partition_ids.items():
        sets = {key: set(value) for key, value in strata.items()}
        intersections = {
            f"{left}__{right}": sorted(sets[left].intersection(sets[right]))
            for index, left in enumerate(sets)
            for right in tuple(sets)[index + 1 :]
        }
        union = set().union(*sets.values())
        disjoint_checks[subject] = {
            "pairwise_intersections": intersections,
            "union_case_count": len(union),
            "reference_case_count": len(all_reference_ids[subject]),
            "missing_case_ids": sorted(all_reference_ids[subject] - union),
            "unexpected_case_ids": sorted(union - all_reference_ids[subject]),
            "pass": not any(intersections.values())
            and union == all_reference_ids[subject],
        }

    system_summary: dict[str, Any] = {}
    for subject in SUITES:
        primary_ui_ids = set(partition_ids[subject]["ui_only"])
        primary_rows = [
            row for row in coverage_rows[subject] if row["case_id"] in primary_ui_ids
        ]
        supplemental_rows = [
            row
            for row in coverage_rows[subject]
            if row["case_id"] not in primary_ui_ids
        ]
        system_summary[subject] = {
            "api_business": {
                "primary_case_count": len(partition_ids[subject]["business_relation"]),
                "reporting": "separate Candidate-to-M14 business relation funnel",
            },
            "auth_session": {
                "primary_case_count": len(partition_ids[subject]["auth_session"]),
                "reporting": "separate auth/session qualification and calibration",
            },
            "ui_only": {
                "primary_case_count": len(primary_ui_ids),
                "coverage_status_counts": dict(
                    sorted(
                        Counter(row["coverage_status"] for row in primary_rows).items()
                    )
                ),
                "api_relation_funnel": "N/A",
            },
            "supplemental_ui_claims": {
                "case_count": len(supplemental_rows),
                "coverage_status_counts": dict(
                    sorted(
                        Counter(
                            row["coverage_status"] for row in supplemental_rows
                        ).items()
                    )
                ),
                "api_relation_funnel": "N/A for the UI claim; any coexisting API or auth claim is reported in its own stratum",
            },
        }

    all_coverage = [row for rows in coverage_rows.values() for row in rows]
    return {
        "schema_version": UI_COVERAGE_SCHEMA_VERSION,
        "report_scope": "R7_post_hoc_ui_only_coverage",
        "paper_result_eligible": False,
        "source": {
            "recording_roots": {
                subject: _artifact_ref(path, repo_root)
                for subject, path in roots.items()
            },
            "evidence_boundary": "frozen typed workflow plus M1 recording_workflow_result, UI action log, deterministic decision log, and page-state manifest",
            "provider_calls": 0,
            "target_runs": 0,
        },
        "evaluation_rule": {
            "passed": "completed workflow; exact step/action/decision identity; every declared wait satisfied; every declared native dialog handled; paired before/after page-state files present",
            "failed": "M1 rejected the workflow, a step/action did not complete, a wait was unsatisfied, or declared dialog handling failed",
            "incomplete": "the workflow claims completion but required action, decision, wait, identity, or page-state evidence is missing or inconsistent",
            "unavailable": "no frozen recording_workflow_result is available",
            "api_relation_funnel": "N/A for every UI coverage row",
        },
        "summary": {
            "reference_case_count": sum(len(rows) for rows in reference.values()),
            "selected_ui_coverage_case_count": len(all_coverage),
            "primary_ui_only_case_count": sum(
                len(partition_ids[subject]["ui_only"]) for subject in SUITES
            ),
            "supplemental_ui_claim_case_count": len(all_coverage)
            - sum(len(partition_ids[subject]["ui_only"]) for subject in SUITES),
            "coverage_status_counts": dict(
                sorted(Counter(row["coverage_status"] for row in all_coverage).items())
            ),
            "system_strata": system_summary,
            "primary_case_partition": {
                subject: {
                    stratum: len(case_ids)
                    for stratum, case_ids in partition_ids[subject].items()
                }
                for subject in SUITES
            },
            "primary_case_partition_checks": disjoint_checks,
        },
        "primary_case_partition_ids": partition_ids,
        "cases": coverage_rows,
        "claim_boundary": "UI-only pass is not an API test, not an API recall failure, and not evidence of cross-reset stability. Logout rows prove only the declared UI route/control behavior after logout and reload, not direct localStorage content deletion.",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _combined_sha256(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode("utf-8"))
        digest.update(_sha256(path).encode("ascii"))
    return digest.hexdigest()


def _parse_design_table(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| L"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 9:
            raise ValueError(f"unexpected_design_table_row:{path}:{line}")
        (
            case_id,
            goal,
            actors,
            auth,
            setup,
            workflow,
            observations,
            applicability,
            evidence,
        ) = cells
        rows[case_id] = {
            "design_goal": goal,
            "actors": actors,
            "initial_auth": auth,
            "setup_goal": setup,
            "workflow_goal": workflow,
            "ui_observations": observations,
            "applicability": applicability,
            "evidence_categories": evidence,
        }
    return rows


def _module_by_case(inventory: Mapping[str, Any]) -> dict[str, str]:
    return {
        case_id: module["module_id"]
        for module in inventory["modules"]
        for case_id in module["case_ids"]
    }


def _reference_fields(subject: str, case_id: str) -> dict[str, Any]:
    if subject == "conduit":
        if case_id in CONDUIT_UI_ONLY_CASES:
            return {
                "target_strata": ["ui_only"],
                "api_observability": "not_api_observable",
                "dsl_expressibility": "not_expressible",
                "reference_rationale": "The designed target is a browser-visible state, route, validation, or control claim rather than an API relation.",
            }
        if case_id in CONDUIT_AUTH_SESSION_CASES:
            return {
                "target_strata": ["auth_session"],
                "api_observability": "auth_session_observable",
                "dsl_expressibility": "outside_business_relation_dsl",
                "reference_rationale": "The designed target depends on authenticated session state and is reported in the separate auth/session stratum.",
            }
        if case_id in CONDUIT_MIXED_AUTH_CASES:
            return {
                "target_strata": ["business_relation", "auth_session"],
                "api_observability": "partially_api_observable",
                "dsl_expressibility": "partially_expressible",
                "reference_rationale": "The workflow combines business-field propagation with credential and session lifecycle effects.",
            }
        partial = case_id in CONDUIT_PARTIAL_DSL_CASES
        return {
            "target_strata": ["business_relation"],
            "api_observability": "api_observable",
            "dsl_expressibility": "partially_expressible" if partial else "expressible",
            "reference_rationale": (
                "The central business effect is API-observable, while additional UI, route, ordering, or visibility claims remain outside the business-relation DSL."
                if partial
                else "The central designed effect is API-observable and representable by the current business-relation DSL."
            ),
        }

    if case_id in RWA_UI_ONLY_CASES:
        return {
            "target_strata": ["ui_only"],
            "api_observability": "not_api_observable",
            "dsl_expressibility": "not_expressible",
            "reference_rationale": "The designed target is a browser-visible state, route, validation, or control claim rather than an API relation.",
        }
    if case_id in RWA_AUTH_SESSION_CASES:
        return {
            "target_strata": ["auth_session"],
            "api_observability": "auth_session_observable",
            "dsl_expressibility": "outside_business_relation_dsl",
            "reference_rationale": "The designed target depends on authenticated session state and belongs to the separate auth/session stratum.",
        }
    if case_id in RWA_MIXED_AUTH_CASES:
        return {
            "target_strata": ["business_relation", "auth_session", "ui_only"],
            "api_observability": "partially_api_observable",
            "dsl_expressibility": "partially_expressible",
            "reference_rationale": "The workflow combines account creation or onboarding effects with session and UI lifecycle claims.",
        }
    full = case_id in RWA_FULL_DSL_CASES
    return {
        "target_strata": ["business_relation"],
        "api_observability": "api_observable",
        "dsl_expressibility": "expressible" if full else "partially_expressible",
        "reference_rationale": (
            "The central designed effect is API-observable and representable by the current business-relation DSL."
            if full
            else "The central business effect is API-observable, while additional UI, route, ordering, isolation, balance, or notification claims require separate observations."
        ),
    }


def build_reference_rows(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for subject, paths in SUITES.items():
        inventory = _read_json(repo_root / paths["inventory"])
        design = _parse_design_table(repo_root / paths["design"])
        module_by_case = _module_by_case(inventory)
        inventory_ids = [case["case_id"] for case in inventory["cases"]]
        if set(inventory_ids) != set(design):
            raise ValueError(f"design_inventory_case_mismatch:{subject}")
        result[subject] = []
        for case in inventory["cases"]:
            case_id = case["case_id"]
            result[subject].append(
                {
                    "subject": subject,
                    "suite_id": inventory["suite_id"],
                    "case_id": case_id,
                    "module_id": module_by_case[case_id],
                    "layer": case["layer"],
                    "workflow_file": case["workflow"],
                    **design[case_id],
                    **_reference_fields(subject, case_id),
                }
            )
    return result


def _request_step_labels(trace: Mapping[str, Any]) -> dict[str, str]:
    event_by_id = {event["event_id"]: event for event in trace["trace"]["events"]}
    result: dict[str, str] = {}
    for binding in trace["trace"]["bindings"]:
        event = event_by_id[binding["event_id"]]
        result[binding["request_ref"]] = event["workflow_step_id"].rsplit(".", 1)[-1]
    return result


def _validate_target_step_references(
    repo_root: Path, reference_rows: Sequence[Mapping[str, Any]]
) -> None:
    for reference in reference_rows:
        if "business_relation" not in reference["target_strata"]:
            continue
        case_id = str(reference["case_id"])
        target_references = _load_target_step_references()[reference["subject"]]
        if case_id not in target_references:
            if reference["subject"] != "rwa":
                raise ValueError(f"target_step_reference_missing:{case_id}")
            target_references[case_id] = frozenset()
        workflow_dir = f"{reference['subject']}_modular"
        workflow = _read_json(
            repo_root
            / "fixtures/recording_workflows"
            / workflow_dir
            / str(reference["workflow_file"])
        )
        labels = {
            str(step["workflow_step_id"]).rsplit(".", 1)[-1]
            for step in workflow["steps"]
        }
        unknown = sorted(target_references[case_id] - labels)
        if unknown:
            raise ValueError(f"target_step_reference_unknown:{case_id}:{unknown}")


def _candidate_association(
    subject: str,
    case_id: str,
    candidate_id: str,
    payload: Mapping[str, Any],
    request_steps: Mapping[str, str],
    target_steps: frozenset[str],
) -> str:
    if (subject == "conduit" and case_id in CONDUIT_AUTH_SESSION_CANDIDATE_CASES
            and isinstance(payload.get("producer"), Mapping)):
        return "auth_session_associated"
    relation_steps = {
        request_steps.get(payload[side]["request_ref"], "")
        for side in ("producer", "consumer")
        if isinstance(payload.get(side), Mapping)
    }
    if target_steps.intersection(relation_steps):
        return "target_associated"
    return "setup_associated"


def _candidate_association_basis(
    subject: str,
    case_id: str,
    candidate_id: str,
    association: str,
    payload: Mapping[str, Any],
    request_steps: Mapping[str, str],
    target_steps: frozenset[str],
) -> str:
    if association == "auth_session_associated":
        return "designed_auth_session_target"
    relation_steps = {
        request_steps.get(payload[side]["request_ref"], "")
        for side in ("producer", "consumer")
        if isinstance(payload.get(side), Mapping)
    }
    matched = sorted(target_steps.intersection(relation_steps))
    if matched:
        return "designed_target_step:" + ",".join(matched)
    return "non_target_prerequisite_or_auxiliary_relation"


def _candidate_matches_dimension(
    candidate: Mapping[str, Any], dimension: Mapping[str, str]
) -> bool:
    """Match normalized candidate signature, never just its workflow step."""
    signature = dimension.get("signature")
    if not signature:
        return False
    return all(
        candidate.get(key) in value if isinstance(value, (set, frozenset, tuple, list))
        else candidate.get(key) == value
        for key, value in signature.items()
        if value is not None
    )


def _candidate_semantic_coverage(
    reference: Mapping[str, Any], association: str, candidate: Mapping[str, Any]
) -> tuple[str, list[dict[str, str]]]:
    if _semantic_classification(reference) == "non_cpv":
        return "not_applicable", []
    dimensions = _semantic_dimensions(reference)
    if not dimensions:
        return "not_assessed", []
    if association != "target_associated":
        return "uncovered", [
            {**row, "status": "uncovered", "classification": "not_assessed"}
            for row in dimensions
        ]
    matched = [_candidate_matches_dimension(candidate, row) for row in dimensions]
    if any(matched):
        return "covered", [
            {**row, "status": "covered" if is_match else "uncovered", "classification": "not_assessed"}
            for row, is_match in zip(dimensions, matched, strict=True)
        ]
    return "uncovered", [
        {**row, "status": "uncovered", "classification": "not_assessed"}
        for row in dimensions
    ]


def _case_semantic_coverage(
    reference: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    classification = _semantic_classification(reference)
    dimensions = _semantic_dimensions(reference)
    if classification == "non_cpv":
        return {
            "classification": classification,
            "status": "not_applicable",
            "dimensions": [],
            "reason_codes": ["no_api_business_relation_design_target"],
        }
    if not dimensions:
        return {
            "classification": "not_assessed",
            "status": "not_assessed",
            "dimensions": [],
            "reason_codes": ["design_dimension_signature_not_assessed"],
        }
    target = [row for row in candidates if row["association"] == "target_associated"]
    statuses = [row["design_semantic_coverage"] for row in target]
    if "covered" in statuses:
        status = "covered"
    elif "partial" in statuses:
        status = "partial"
    else:
        status = "uncovered"
    dimension_rows = []
    for dimension in dimensions:
        matching = [
            candidate for candidate in target
            if _candidate_matches_dimension(candidate, dimension)
        ]
        if matching:
            status = "covered"
            classification = "not_assessed"
        elif dimension["capability"] == "deferred_current_cpv":
            status = "uncovered"
            classification = "C"
        elif dimension["capability"] == "current_recording_gap":
            status = "uncovered"
            classification = "B"
        elif dimension["capability"].startswith("current_"):
            status = "uncovered"
            classification = "B" if reference["case_id"] == "L1-ARTICLE-03" else "A"
        else:
            status = "uncovered"
            classification = "not_assessed"
        dimension_rows.append({**dimension, "status": status, "classification": classification})
    reasons = []
    if not target:
        reasons.append("no_target_associated_candidate")
    if reference["case_id"] == "L1-ARTICLE-03":
        reasons.append("observer_negative_fact_evidence_gap")
    if any(not row["capability"].startswith("current_") for row in dimensions):
        reasons.append("current_cpv_capability_gap")
    if any(_candidate_matches_dimension(candidate, dimension) for candidate in target for dimension in dimensions):
        reasons.append("normalized_predicate_matches_design_dimension")
    if any(row["classification"] in {"A", "B", "C"} for row in dimension_rows):
        reasons.append("uncovered_design_dimension_classified_by_current_method")
    case_classifications = {row["classification"] for row in dimension_rows}
    classification = (
        "+".join(key for key in ("A", "B", "C") if key in case_classifications)
        if case_classifications.intersection({"A", "B", "C"})
        else "not_assessed"
    )
    return {
        "classification": classification,
        "status": status,
        "dimensions": dimension_rows,
        "reason_codes": reasons,
    }


def _materialization_rows(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in value.get("ineligible", []):
        rows[row["candidate_id"]] = row
    return rows


def _case_business_candidates(
    case_root: Path,
    target_steps: frozenset[str],
    subject: str,
) -> list[dict[str, Any]]:
    candidate_set = _read_json(case_root / "M10/union/candidate_set.json")
    eligibility = _read_json(case_root / "M11b/materialization_eligibility.json")
    run_report = _read_json(case_root / "M12/run_report.json")
    calibration = _read_json(case_root / "M14/calibration_report.json")
    trace = _read_json(case_root / "M01_09/ui_api_trace.json")
    request_steps = _request_step_labels(trace)
    ineligible = _materialization_rows(eligibility)
    run_by_id = {row["candidate_id"]: row for row in run_report.get("rows", [])}
    calibration_by_id = {
        row["candidate_id"]: row for row in calibration.get("per_candidate", [])
    }
    retained_ids = calibration.get("candidate_partition", {}).get("retained", [])
    retained_cores = calibration.get("retained_canonical_relation_core_identities", [])
    if len(retained_ids) != len(retained_cores):
        raise ValueError(f"retained_core_alignment_mismatch:{case_root}")
    core_by_id = dict(zip(retained_ids, retained_cores, strict=True))
    final_suite = _read_json(case_root / "M14/final_calibrated_suite.json")
    test_by_candidate = {
        str(test["candidate_id"]): test
        for test in final_suite.get("retained_tests", [])
    }
    if set(test_by_candidate) != set(retained_ids):
        raise ValueError(f"retained_test_alignment_mismatch:{case_root}")
    retained_payloads = {
        str(row["candidate_id"]): row["payload"]
        for row in candidate_set.get("candidates", [])
        if str(row.get("candidate_id")) in test_by_candidate
    }
    if set(retained_payloads) != set(retained_ids):
        raise ValueError(f"retained_payload_alignment_mismatch:{case_root}")
    rationale_sources = load_raw_rationale_sources(
        case_root, retained_payloads
    )
    if any(not rationale_sources[candidate_id] for candidate_id in retained_ids):
        raise ValueError(f"retained_rationale_provenance_missing:{case_root}")

    rows: list[dict[str, Any]] = []
    for wrapped in candidate_set.get("candidates", []):
        candidate_id = wrapped["candidate_id"]
        payload = wrapped["payload"]
        materialized = candidate_id not in ineligible
        run_row = run_by_id.get(candidate_id)
        calibration_row = calibration_by_id.get(candidate_id)
        retained = candidate_id in retained_ids
        if not materialized:
            exit_reason = (
                ineligible[candidate_id].get("reason_code")
                or ineligible[candidate_id].get("reason")
                or "materialization_ineligible"
            )
        elif run_row is None:
            exit_reason = "not_evaluated"
        elif not retained:
            protocol_result = run_row.get("protocol_result") or {}
            exit_reason = (
                protocol_result.get("failure_class")
                or (protocol_result.get("predicate_result") or {}).get("reason_code")
                or run_row.get("outcome")
                or "not_retained"
            )
        else:
            exit_reason = "retained_normal_pass"
        predicate = payload["primary_predicate"]
        association = _candidate_association(
            subject,
            case_root.parent.name,
            candidate_id,
            payload,
            request_steps,
            target_steps,
        )
        semantic_coverage, semantic_dimensions = _candidate_semantic_coverage(
            {"subject": subject, "case_id": case_root.parent.name, "target_strata": (
                ["auth_session"] if case_root.parent.name in CONDUIT_AUTH_SESSION_CASES else ["business_relation"]
            )},
            association,
            {
                "contract_kind": payload["contract_kind"],
                "predicate_family": predicate["family"],
                "predicate_path": (
                    predicate.get("left") or predicate.get("collection") or {}
                ).get("path"),
            },
        )
        rows.append(
            {
                "candidate_id": candidate_id,
                "association": association,
                "step_association": association,
                "association_basis": _candidate_association_basis(
                    subject,
                    case_root.parent.name,
                    candidate_id,
                    association,
                    payload,
                    request_steps,
                    target_steps,
                ),
                "design_semantic_coverage": semantic_coverage,
                "design_semantic_dimensions": semantic_dimensions,
                "contract_kind": payload["contract_kind"],
                "predicate_family": predicate["family"],
                "predicate_path": (
                    predicate.get("left") or predicate.get("collection") or {}
                ).get("path"),
                "business_summary": (
                    deterministic_business_summary(test_by_candidate[candidate_id])
                    if retained
                    else None
                ),
                "rationale_sources": (
                    rationale_sources[candidate_id] if retained else []
                ),
                "rationale_semantics": (
                    "non_normative_raw_M10_proposal_metadata"
                    if retained
                    else None
                ),
                "schema_type_assertion_scope": (
                    SCHEMA_TYPE_ASSERTION_SCOPE if retained else None
                ),
                "producer_request_ref": (payload.get("producer") or {}).get("request_ref"),
                "producer_step": request_steps.get((payload.get("producer") or {}).get("request_ref")),
                "consumer_request_ref": payload["consumer"]["request_ref"],
                "consumer_step": request_steps.get(payload["consumer"]["request_ref"]),
                "proposed": True,
                "materialized": materialized,
                "evaluated": run_row is not None and bool(run_row.get("attempted")),
                "evaluation_outcome": run_row.get("outcome") if run_row else None,
                "retained": retained,
                "calibration_status": (
                    calibration_row.get("final_status") if calibration_row else None
                ),
                "canonical_relation_core_identity": core_by_id.get(candidate_id),
                "exit_reason": exit_reason,
            }
        )
    return rows


def _counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "proposed": len(rows),
        "materialized": sum(bool(row["materialized"]) for row in rows),
        "evaluated": sum(bool(row["evaluated"]) for row in rows),
        "retained": sum(bool(row["retained"]) for row in rows),
    }


def _auth_session_counts(case_root: Path) -> dict[str, int]:
    qualification = _read_json(case_root / "M12/auth_session_qualification.json")
    calibration = _read_json(case_root / "M14/auth_session_calibration.json")
    denominator = qualification.get("denominator", {})
    test_denominator = calibration.get("test_denominator", {})
    return {
        "proposed": int(denominator.get("attempted", 0)),
        "materialized": int(denominator.get("evaluable", 0)),
        "evaluated": int(denominator.get("attempted", 0)),
        "retained": int(test_denominator.get("retained", 0)),
    }


def _case_exit_reason(
    row: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    auth_counts: Mapping[str, int],
) -> str:
    target = [item for item in candidates if item["association"] == "target_associated"]
    auth = [
        item for item in candidates if item["association"] == "auth_session_associated"
    ]
    if any(item["retained"] for item in target):
        return "target_relation_retained"
    if target:
        return ";".join(sorted({str(item["exit_reason"]) for item in target}))
    if auth:
        return ";".join(sorted({str(item["exit_reason"]) for item in auth}))
    if auth_counts["retained"]:
        if "business_relation" in row["target_strata"]:
            return "business_target_relation_not_proposed;auth_session_retained"
        return "auth_session_retained"
    if row["target_strata"] == ["ui_only"]:
        return "ui_only_api_relation_not_applicable"
    if row["target_strata"] == ["auth_session"]:
        return "auth_session_relation_not_proposed_or_reported_separately"
    return "target_relation_not_proposed"


def _proposer_artifacts(conduit_root: Path) -> list[Path]:
    patterns = (
        "*/union/M01_09/rendered_candidate_input.json",
        "*/union/M10/union/candidate_set.json",
        "*/union/M10/union/union_provenance.json",
    )
    return [path for pattern in patterns for path in conduit_root.glob(pattern)]


def _feedback_references(conduit_root: Path, output_dir: Path) -> list[str]:
    forbidden_fragments = {
        output_dir.name,
        "effect_reference_report.py",
        "build_effect_reference_report.py",
    }
    hits: list[str] = []
    for path in conduit_root.glob("*/union/M10/union/candidate_set.json"):
        value = _read_json(path)
        refs = [value.get("rendered_input_ref"), *value.get("source_refs", [])]
        for ref in refs:
            text = str(ref)
            if any(fragment in text for fragment in forbidden_fragments):
                hits.append(f"{path}:{text}")
    return hits


def _build_effect_rows(
    reference_rows: Sequence[Mapping[str, Any]], root: Path,
    target_references: Mapping[str, frozenset[str]], subject: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    for reference in reference_rows:
        case_id = reference["case_id"]
        case_root = root / case_id / "union"
        target_steps = target_references.get(case_id, frozenset())
        candidates = _case_business_candidates(case_root, target_steps, subject)
        candidates_with_case = [
            {"case_id": case_id, **candidate} for candidate in candidates
        ]
        all_candidates.extend(candidates_with_case)
        target = [c for c in candidates if c["association"] == "target_associated"]
        setup = [c for c in candidates if c["association"] == "setup_associated"]
        auth = [c for c in candidates if c["association"] == "auth_session_associated"]
        auth_counts = _auth_session_counts(case_root)
        semantic = _case_semantic_coverage(reference, candidates)
        cases.append(
            {
                **reference,
                "availability": "available",
                "business_relation_counts": _counts(candidates),
                "target_associated_counts": _counts(target),
                "setup_associated_counts": _counts(setup),
                "auth_session_candidate_counts": _counts(auth),
                "auth_session_counts": auth_counts,
                "design_semantic_coverage": semantic,
                "design_semantic_classification": semantic["classification"],
                "exit_reason": _case_exit_reason(reference, candidates, auth_counts),
                "exit_reason_counts": dict(
                    sorted(Counter(c["exit_reason"] for c in candidates).items())
                ),
            }
        )
    return cases, all_candidates


def _canonical_summary(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    retained = [candidate for candidate in candidates if candidate["retained"]]
    target = [c for c in retained if c["association"] == "target_associated"]
    setup = [c for c in retained if c["association"] == "setup_associated"]
    auth = [c for c in retained if c["association"] == "auth_session_associated"]
    target_cores = {c["canonical_relation_core_identity"] for c in target}
    setup_cores = {c["canonical_relation_core_identity"] for c in setup}
    all_cores = {
        c["canonical_relation_core_identity"]
        for c in retained
        if c["canonical_relation_core_identity"]
    }
    def occurrence_ref(row: Mapping[str, Any]) -> str:
        return f"{row['case_id']}:{row['candidate_id']}"

    return {
        "retained_business_relation_occurrences": len(retained),
        "target_associated_retained_occurrences": len(target),
        "setup_associated_retained_occurrences": len(setup),
        "auth_session_associated_business_candidate_occurrences": len(auth),
        "unique_retained_canonical_relation_cores": len(all_cores),
        "target_associated_unique_canonical_relation_cores": len(target_cores),
        "setup_associated_unique_canonical_relation_cores": len(setup_cores),
        "target_setup_canonical_core_overlap": len(
            target_cores.intersection(setup_cores)
        ),
        "recalculation_basis": {
            "physical_occurrences": {
                "all": [occurrence_ref(c) for c in retained],
                "target_associated": [occurrence_ref(c) for c in target],
                "setup_associated": [occurrence_ref(c) for c in setup],
                "auth_session_associated": [occurrence_ref(c) for c in auth],
            },
            "canonical_relation_cores": {
                "all": sorted(all_cores),
                "target_associated": sorted(target_cores),
                "setup_associated": sorted(setup_cores),
                "target_setup_overlap": sorted(
                    target_cores.intersection(setup_cores)
                ),
            },
        },
    }


def _semantic_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dimensions = [
        dimension
        for case in cases
        for dimension in case["design_semantic_coverage"]["dimensions"]
    ]
    return {
        "classification_counts": dict(
            sorted(Counter(row["design_semantic_classification"] for row in cases).items())
        ),
        "coverage_status_counts": dict(
            sorted(Counter(row["design_semantic_coverage"]["status"] for row in cases).items())
        ),
        "dimension_classification_counts": dict(
            sorted(Counter(row["classification"] for row in dimensions).items())
        ),
        "dimension_coverage_status_counts": dict(
            sorted(Counter(row["status"] for row in dimensions).items())
        ),
        "cases_by_dimension_classification": {
            key: sorted({
                case["case_id"]
                for case in cases
                for dimension in case["design_semantic_coverage"]["dimensions"]
                if dimension["classification"] == key
            })
            for key in sorted({row["classification"] for row in dimensions})
        },
        "cases_by_classification": {
            key: sorted(
                row["case_id"] for row in cases
                if row["design_semantic_classification"] == key
            )
            for key in sorted({row["design_semantic_classification"] for row in cases})
        },
    }


def build_report(
    repo_root: Path,
    conduit_root: Path,
    output_dir: Path,
    rwa_root: Path | None = None,
) -> dict[str, Any]:
    reference = build_reference_rows(repo_root)
    _validate_target_step_references(repo_root, reference["conduit"])
    if rwa_root is not None:
        _validate_target_step_references(repo_root, reference["rwa"])
    proposer_paths = _proposer_artifacts(conduit_root)
    digest_before = _combined_sha256(proposer_paths)
    refs = _load_target_step_references()
    conduit_cases, candidates = _build_effect_rows(reference["conduit"], conduit_root, refs["conduit"], "conduit")
    if rwa_root is None:
        rwa_candidates = []
        rwa_cases = [
            {
                **row,
                "availability": "downstream_unavailable",
                "business_relation_counts": {k: None for k in ("proposed", "materialized", "evaluated", "retained")},
                "target_associated_counts": {k: None for k in ("proposed", "materialized", "evaluated", "retained")},
                "setup_associated_counts": {k: None for k in ("proposed", "materialized", "evaluated", "retained")},
                "auth_session_counts": {k: None for k in ("proposed", "materialized", "evaluated", "retained")},
                "design_semantic_coverage": {
                    "classification": _semantic_classification(row),
                    "status": "unavailable",
                    "dimensions": [
                        {**dimension, "status": "not_assessed", "classification": "not_assessed"}
                        for dimension in _semantic_dimensions(row)
                    ],
                    "reason_codes": ["downstream_M10_M14_unavailable"],
                },
                "design_semantic_classification": _semantic_classification(row),
                "exit_reason": "downstream_M10_M14_unavailable",
                "exit_reason_counts": {"downstream_M10_M14_unavailable": 1},
            }
            for row in reference["rwa"]
        ]
    else:
        rwa_cases, rwa_candidates = _build_effect_rows(reference["rwa"], rwa_root, refs["rwa"], "rwa")
    digest_after = _combined_sha256(proposer_paths)
    feedback_hits = _feedback_references(conduit_root, output_dir)
    business_counts = _counts(candidates)
    auth_counts = {
        stage: sum(case["auth_session_counts"][stage] for case in conduit_cases)
        for stage in ("proposed", "materialized", "evaluated", "retained")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_scope": "R0_post_hoc_diagnostic_baseline",
        "paper_result_eligible": False,
        "stage_definitions": {
            "business_relation": {
                "proposed": "candidate present in M10 union candidate_set.json",
                "materialized": "candidate counted as materialized by M11b",
                "evaluated": "candidate attempted by M12, including infrastructure/setup inconclusive attempts",
                "retained": "candidate retained after M14 normal-state calibration",
            },
            "auth_session": {
                "proposed": "auth/session qualification attempt present in M12",
                "materialized": "auth/session attempt marked evaluable in M12",
                "evaluated": "auth/session qualification attempt executed in M12",
                "retained": "auth/session test retained after M14 calibration",
            },
        },
        "source": {
            "conduit_root": str(conduit_root.relative_to(repo_root)),
            "conduit_case_count": len(conduit_cases),
            "rwa_case_count": len(rwa_cases),
            "rwa_root": str(rwa_root.relative_to(repo_root)) if rwa_root else None,
        },
        "summary": {
            "reference_case_count": len(conduit_cases) + len(rwa_cases),
            "conduit_case_count": len(conduit_cases),
            "rwa_case_count": len(rwa_cases),
            "conduit_business_relation_counts": business_counts,
            "conduit_auth_session_counts": auth_counts,
            "rwa_business_relation_counts": _counts(rwa_candidates) if rwa_candidates else None,
            "rwa_auth_session_counts": {
                stage: sum(case["auth_session_counts"][stage] for case in rwa_cases)
                for stage in ("proposed", "materialized", "evaluated", "retained")
            } if rwa_candidates else None,
            "canonical_relation_core": _canonical_summary(candidates),
            "rwa_canonical_relation_core": _canonical_summary(rwa_candidates) if rwa_candidates else None,
            "candidate_association_counts": dict(
                sorted(Counter(c["association"] for c in candidates).items())
            ),
            "rwa_candidate_association_counts": dict(
                sorted(Counter(c["association"] for c in rwa_candidates).items())
            ) if rwa_candidates else None,
            "conduit_design_semantic": _semantic_summary(conduit_cases),
            "rwa_design_semantic": _semantic_summary(rwa_cases),
        },
        "feedback_guard": {
            "reference_feedback_to_proposer": not (
                not feedback_hits and digest_before == digest_after
            ),
            "proposer_artifact_count": len(proposer_paths),
            "proposer_artifact_digest_before": digest_before,
            "proposer_artifact_digest_after": digest_after,
            "reference_paths_in_proposer_source_refs": feedback_hits,
            "boundary": "post_hoc_read_only_reporting_after_M14",
        },
        "cases": {"conduit": conduit_cases, "rwa": rwa_cases},
        "conduit_candidates": candidates,
        "rwa_candidates": rwa_candidates,
    }


CASE_CSV_FIELDS = (
    "subject",
    "case_id",
    "module_id",
    "layer",
    "design_goal",
    "target_strata",
    "api_observability",
    "dsl_expressibility",
    "availability",
    "proposed",
    "materialized",
    "evaluated",
    "retained",
    "target_proposed",
    "target_materialized",
    "target_evaluated",
    "target_retained",
    "setup_proposed",
    "setup_materialized",
    "setup_evaluated",
    "setup_retained",
    "auth_session_proposed",
    "auth_session_materialized",
    "auth_session_evaluated",
    "auth_session_retained",
        "exit_reason",
        "step_association_summary",
        "design_semantic_classification",
        "design_semantic_coverage",
        "design_semantic_reason_codes",
)


def _flat_case(row: Mapping[str, Any]) -> dict[str, Any]:
    business = row["business_relation_counts"]
    target = row["target_associated_counts"]
    setup = row["setup_associated_counts"]
    auth = row["auth_session_counts"]
    return {
        "subject": row["subject"],
        "case_id": row["case_id"],
        "module_id": row["module_id"],
        "layer": row["layer"],
        "design_goal": row["design_goal"],
        "target_strata": "+".join(row["target_strata"]),
        "api_observability": row["api_observability"],
        "dsl_expressibility": row["dsl_expressibility"],
        "availability": row["availability"],
        "proposed": business["proposed"],
        "materialized": business["materialized"],
        "evaluated": business["evaluated"],
        "retained": business["retained"],
        "target_proposed": target["proposed"],
        "target_materialized": target["materialized"],
        "target_evaluated": target["evaluated"],
        "target_retained": target["retained"],
        "setup_proposed": setup["proposed"],
        "setup_materialized": setup["materialized"],
        "setup_evaluated": setup["evaluated"],
        "setup_retained": setup["retained"],
        "auth_session_proposed": auth["proposed"],
        "auth_session_materialized": auth["materialized"],
        "auth_session_evaluated": auth["evaluated"],
        "auth_session_retained": auth["retained"],
        "exit_reason": row["exit_reason"],
        "step_association_summary": "target/setup/auth-session counts are joined by producer and consumer workflow steps",
        "design_semantic_classification": row["design_semantic_classification"],
        "design_semantic_coverage": row["design_semantic_coverage"]["status"],
        "design_semantic_reason_codes": ";".join(row["design_semantic_coverage"]["reason_codes"]),
    }


def _write_case_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASE_CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(_flat_case(row) for row in rows)


def _write_candidate_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = tuple(rows[0]) if rows else ("case_id", "candidate_id")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: Any) -> str:
    return "unavailable" if value is None else str(value)


def _markdown_report(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    core = summary["canonical_relation_core"]
    feedback = report["feedback_guard"]
    lines = [
        "# R0 effect-level reference and diagnostic baseline",
        "",
        "> Diagnostic only: this post-hoc report is not a paper result and did not enter the proposer.",
        "",
        "## Summary",
        "",
        f"- Reference cases: {summary['reference_case_count']} (Conduit {summary['conduit_case_count']}; RWA {summary['rwa_case_count']}).",
        f"- Conduit business relations: {summary['conduit_business_relation_counts']}.",
        f"- RWA business relations: {summary['rwa_business_relation_counts']}.",
        f"- Conduit retained business relation occurrences: target-associated {core['target_associated_retained_occurrences']}, setup-associated {core['setup_associated_retained_occurrences']}.",
        f"- Retained canonical relation cores: all {core['unique_retained_canonical_relation_cores']}, target-associated {core['target_associated_unique_canonical_relation_cores']}, setup-associated {core['setup_associated_unique_canonical_relation_cores']}, overlap {core['target_setup_canonical_core_overlap']}.",
        f"- Conduit auth/session retained tests: {summary['conduit_auth_session_counts']['retained']} (reported separately).",
        f"- Conduit candidate associations: {summary['candidate_association_counts']}; RWA candidate associations: {summary['rwa_candidate_association_counts']}.",
        f"- Design-semantic classification: Conduit {summary['conduit_design_semantic']['classification_counts']}; RWA {summary['rwa_design_semantic']['classification_counts']} (A=current CPV opportunity, C=capability gap, non_cpv=not an API business target).",
        f"- Design-semantic coverage status: Conduit {summary['conduit_design_semantic']['coverage_status_counts']}; RWA {summary['rwa_design_semantic']['coverage_status_counts']}.",
        f"- RWA canonical relation core summary: {summary['rwa_canonical_relation_core']}.",
        f"- Reference feedback to proposer: {str(feedback['reference_feedback_to_proposer']).lower()}; proposer-input digest unchanged: {feedback['proposer_artifact_digest_before'] == feedback['proposer_artifact_digest_after']}.",
        "- Business funnel semantics: proposed=M10 union candidate; materialized=M11b materialized; evaluated=M12 attempted; retained=M14 normal-state retained. Auth/session counts use the parallel M12 qualification and M14 calibration artifacts.",
        "",
        "## Conduit cases",
        "",
            "| Case | Design goal | Target stratum | A/C/non-CPV | Semantic coverage | Observability | DSL expressibility | Proposed | Materialized | Evaluated | Retained | Target retained | Setup retained | Auth/session retained | Exit / reason |",
            "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["cases"]["conduit"]:
        flat = _flat_case(row)
        lines.append(
            "| {case_id} | {goal} | {strata} | {classification} | {coverage} | {obs} | {dsl} | {p} | {m} | {e} | {r} | {tr} | {sr} | {ar} | {reason} |".format(
                case_id=row["case_id"],
                goal=row["design_goal"].replace("|", "\\|"),
                strata="+".join(row["target_strata"]),
                classification=row["design_semantic_classification"],
                coverage=row["design_semantic_coverage"]["status"],
                obs=row["api_observability"],
                dsl=row["dsl_expressibility"],
                p=_fmt(flat["proposed"]),
                m=_fmt(flat["materialized"]),
                e=_fmt(flat["evaluated"]),
                r=_fmt(flat["retained"]),
                tr=_fmt(flat["target_retained"]),
                sr=_fmt(flat["setup_retained"]),
                ar=_fmt(flat["auth_session_retained"]),
                reason=row["exit_reason"],
            )
        )
    lines.extend(
        [
            "",
            "## Retained Conduit business tests",
            "",
            "Each row is one physical M14-retained test occurrence. The canonical relation core may repeat across rows. Raw M10 rationale is non-normative proposal metadata and is never used for candidate identity, exact deduplication, setup, verdict, or retention.",
            "",
            f"`schema_type` scope: {SCHEMA_TYPE_ASSERTION_SCOPE}",
            "",
            "| Case | Step association | Semantic coverage | Candidate | Canonical relation core | Deterministic business summary | Original M10 rationale source(s) |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for candidate in report["conduit_candidates"]:
        if not candidate["retained"]:
            continue
        source_refs = "<br>".join(
            f"`{row['rationale_ref']}`"
            for row in candidate["rationale_sources"]
        )
        lines.append(
            "| {case} | {association} | {coverage} | {candidate} | `{core}` | {summary} | {sources} |".format(
                case=candidate["case_id"],
                association=candidate["association"],
                coverage=candidate["design_semantic_coverage"],
                candidate=candidate["candidate_id"],
                core=candidate["canonical_relation_core_identity"],
                summary=str(candidate["business_summary"]).replace("|", "\\|"),
                sources=source_refs,
            )
        )
    lines.extend(
        [
            "",
            "## RWA cases",
            "",
            "| Case | Design goal | Target stratum | A/C/non-CPV | Semantic coverage | Observability | DSL expressibility | Proposed | Materialized | Evaluated | Retained | Exit / reason |",
            "|---|---|---|---|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in report["cases"]["rwa"]:
        flat = _flat_case(row)
        lines.append(
            "| {case_id} | {goal} | {strata} | {classification} | {coverage} | {obs} | {dsl} | {p} | {m} | {e} | {r} | {reason} |".format(
                case_id=row["case_id"],
                goal=row["design_goal"].replace("|", "\\|"),
                strata="+".join(row["target_strata"]),
                classification=row["design_semantic_classification"],
                coverage=row["design_semantic_coverage"]["status"],
                obs=row["api_observability"],
                dsl=row["dsl_expressibility"],
                p=_fmt(flat["proposed"]),
                m=_fmt(flat["materialized"]),
                e=_fmt(flat["evaluated"]),
                r=_fmt(flat["retained"]),
                reason=row["exit_reason"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "`step_association` means that the candidate producer/consumer is joined to a designed target step, prerequisite step, or auth/session step. `design_semantic_coverage` is a separate post-hoc join over the normalized predicate and the design dimensions: `covered`, `partial`, `uncovered`, or `not_applicable`. Thus a target-associated C02/P02 candidate can remain semantically uncovered (for example Article07 tag length boundaries). A/C/non-CPV is a reporting classification only: A is a current CPV opportunity, C is a current capability gap, and non-CPV is not an API business target. Counts of canonical relation cores remove duplicate physical occurrences; target and setup core sets may overlap because the same relation shape can play different roles in different cases.",
            "",
            "The reference fields are joined only after M14. The report does not change provider inputs, candidate admission, materialization, evaluation, calibration, or retained suites.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "PYTHONPATH=src python3 scripts/build_effect_reference_report.py",
            "python3 scripts/review_effect_reference_artifacts.py",
            "uv run --isolated --python 3.12 --with pytest python -m pytest -q tests/ui_semantics/test_effect_reference_report.py tests/ui_semantics/test_conduit_modular_workflows.py tests/ui_semantics/test_rwa_modular_workflows.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def emit_report(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "r0-effect-reference.json", report)
    _write_case_csv(
        output_dir / "conduit-effect-reference.csv", report["cases"]["conduit"]
    )
    _write_case_csv(output_dir / "rwa-effect-reference.csv", report["cases"]["rwa"])
    _write_candidate_csv(
        output_dir / "conduit-candidate-associations.csv",
        report["conduit_candidates"],
    )
    (output_dir / "r0-effect-reference.md").write_text(
        _markdown_report(report), encoding="utf-8"
    )


UI_COVERAGE_CSV_FIELDS = (
    "subject",
    "case_id",
    "module_id",
    "design_goal",
    "primary_reporting_stratum",
    "coverage_scope",
    "coverage_status",
    "reported_categories",
    "workflow_status",
    "workflow_steps",
    "completed_steps",
    "ui_checks",
    "passed_ui_checks",
    "action_decisions",
    "before_page_states",
    "after_page_states",
    "api_relation_funnel",
    "reason_codes",
    "workflow_result_ref",
)


def _flat_ui_coverage_case(row: Mapping[str, Any]) -> dict[str, Any]:
    counts = row["evidence_counts"]
    return {
        "subject": row["subject"],
        "case_id": row["case_id"],
        "module_id": row["module_id"],
        "design_goal": row["design_goal"],
        "primary_reporting_stratum": row["primary_reporting_stratum"],
        "coverage_scope": row["coverage_scope"],
        "coverage_status": row["coverage_status"],
        "reported_categories": "+".join(row["reported_categories"]),
        "workflow_status": row["workflow_status"],
        "workflow_steps": counts["workflow_steps"],
        "completed_steps": counts["completed_steps"],
        "ui_checks": counts["ui_checks"],
        "passed_ui_checks": counts["passed_ui_checks"],
        "action_decisions": counts["action_decisions"],
        "before_page_states": counts["before_page_states"],
        "after_page_states": counts["after_page_states"],
        "api_relation_funnel": "N/A",
        "reason_codes": ";".join(row["reason_codes"]),
        "workflow_result_ref": row["workflow_result_ref"],
    }


def _ui_coverage_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# R7 UI-only coverage report",
        "",
        "> Engineering evidence only. UI-only results are independent of the API Candidate-to-M14 funnel and are not paper data.",
        "",
        "## Summary",
        "",
        f"- Frozen UI coverage cases: {summary['selected_ui_coverage_case_count']} ({summary['primary_ui_only_case_count']} primary UI-only design goals; {summary['supplemental_ui_claim_case_count']} supplemental UI claims in business/auth cases).",
        f"- UI coverage outcomes: {summary['coverage_status_counts']}.",
        "- Every UI row reports the API relation funnel as N/A. A passed UI flow with no API assertion is therefore a UI pass, not an API failure.",
        "- Pass means one frozen M1 workflow completed with exact action/decision identity, all declared waits or native-dialog handling satisfied, and paired before/after page-state artifacts present.",
        "- Logout evidence covers the declared post-logout route/control behavior after reload; it does not directly inspect localStorage contents or claim cross-reset stability.",
        "",
        "## Mutually exclusive primary case partition",
        "",
        "| System | API business | Auth/session | UI-only | Partition check |",
        "|---|---:|---:|---:|---|",
    ]
    for subject in SUITES:
        counts = summary["primary_case_partition"][subject]
        check = summary["primary_case_partition_checks"][subject]
        lines.append(
            f"| {subject} | {counts['business_relation']} | {counts['auth_session']} | {counts['ui_only']} | {'pass' if check['pass'] else 'fail'} |"
        )
    lines.extend(
        [
            "",
            "## Frozen UI results",
            "",
            "| System | Case | Design goal | Scope | UI status | Categories | Checks | API relation funnel | Evidence |",
            "|---|---|---|---|---|---|---:|---|---|",
        ]
    )
    for subject in SUITES:
        for row in report["cases"][subject]:
            counts = row["evidence_counts"]
            result_ref = row["workflow_result_ref"] or row["recording_root"]
            lines.append(
                "| {subject} | {case_id} | {goal} | {scope} | {status} | {categories} | {passed}/{total} | N/A | `{evidence}` |".format(
                    subject=subject,
                    case_id=row["case_id"],
                    goal=str(row["design_goal"]).replace("|", "\\|"),
                    scope=row["coverage_scope"],
                    status=row["coverage_status"],
                    categories="+".join(row["reported_categories"]),
                    passed=counts["passed_ui_checks"],
                    total=counts["ui_checks"],
                    evidence=result_ref,
                )
            )
    lines.extend(
        [
            "",
            "## Evidence and interpretation boundary",
            "",
            "The JSON artifact records every covered workflow step, its action and deterministic-decision JSONL line, declared wait and observed wait status, native-dialog result when applicable, and exact before/after page-state file. Missing evidence is `incomplete`; a rejected workflow or unsatisfied recorded check is `failed`; a missing recording is `unavailable`.",
            "",
            "The primary case partition is mutually exclusive. Supplemental UI claims remain UI checks only: any coexisting business relation or auth/session result stays in its own report and denominator.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "PYTHONPATH=src python3 scripts/build_ui_coverage_report.py",
            "uv run --isolated --python 3.12 --with pytest python -m pytest -q tests/ui_semantics/test_effect_reference_report.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def emit_ui_coverage_report(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "r7-ui-coverage.json", report)
    rows = [row for subject in SUITES for row in report["cases"][subject]]
    with (output_dir / "r7-ui-coverage.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=UI_COVERAGE_CSV_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(_flat_ui_coverage_case(row) for row in rows)
    (output_dir / "r7-ui-coverage.md").write_text(
        _ui_coverage_markdown(report), encoding="utf-8"
    )


def ui_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit the R7 UI-only coverage report from frozen M1 recordings."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--conduit-recording-root",
        type=Path,
        default=Path(DEFAULT_RECORDING_ROOTS["conduit"]),
    )
    parser.add_argument(
        "--rwa-recording-root",
        type=Path,
        default=Path(DEFAULT_RECORDING_ROOTS["rwa"]),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/modular-ui-suite/r7-ui-coverage-20260903"),
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()

    def resolved(path: Path) -> Path:
        return (path if path.is_absolute() else repo_root / path).resolve()

    report = build_ui_coverage_report(
        repo_root,
        {
            "conduit": resolved(args.conduit_recording_root),
            "rwa": resolved(args.rwa_recording_root),
        },
    )
    output_dir = resolved(args.output_dir)
    emit_ui_coverage_report(report, output_dir)
    print(output_dir / "r7-ui-coverage.md")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--conduit-root",
        type=Path,
        default=Path(
            "eval/ui_semantics/paper-results-20260902/wp9-restart-02/conduit/cases"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/design/modular-ui-suite/r0-effect-reference-20260903"),
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    conduit_root = (
        args.conduit_root
        if args.conduit_root.is_absolute()
        else repo_root / args.conduit_root
    ).resolve()
    output_dir = (
        args.output_dir
        if args.output_dir.is_absolute()
        else repo_root / args.output_dir
    ).resolve()
    report = build_report(repo_root, conduit_root, output_dir)
    emit_report(report, output_dir)
    print(output_dir / "r0-effect-reference.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
