"""Stage 2.5 orchestration and probe_results assembly (004 D30 + D34 set-level determinism + D18 redaction exit)."""

from __future__ import annotations

import json
import secrets as _pysecrets
import subprocess
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from common.location_link_valueflow import parse_link_header
from common.contracts import REPO_ROOT, make_envelope, validate_artifact
from stage1_record.secrets import SecretRegistry
from stage0_launch.profile import (
    actor_auth,
    load_app_profile,
    resolve_actor_credentials,
    resolve_credentials,
)
from stage6_ground import ReplayConfig, ScheduledDiscoveryRunner, build_op_index
from stage6_ground.http_client import Throttle
from stage6_ground.valuepath import extract_value

from .candidate_url_canonicalization import canonicalize_candidate_url_probe
from .discovery_planner import audit_record_for_scheduled_plan, plan_discovery_candidates
from .loader import Stage25Inputs, load_inputs
from .planner import plan_probes
from .prober import Prober, RuntimeAuth, login_auth, login_token
from .scheduled import ScheduledProbePlan, execute_scheduled_probe

_SCHEDULED_EXECUTION_METHODS = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH"}
_DIAGNOSTIC_EXECUTION_METHODS = {"HEAD", "OPTIONS"}
_DIAGNOSTIC_STATUS_CODES = {401, 403, 405}
_READ_EXECUTION_KINDS = {"response", "intermediate", "bipartite"}
_BODY_BEARING_METHODS = {"POST", "PUT", "PATCH"}


def _reset_and_verify(profile) -> None:
    """D60: run the full reset per app_profile.reset plus a baseline check, delivering environment-level reversibility."""
    reset = getattr(profile, "reset", None)
    if reset is None:
        raise RuntimeError("D60 environment_reset requires app_profile.reset to declare the reset command and verify_request")
    r = subprocess.run(_reset_command(reset), cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"D60 end-of-batch reset failed: {r.stderr[-300:]}")

    verify = reset.verify_request
    status, body_text = _verify_request(profile.base_url, verify.method, verify.path)
    if status != verify.expect_status:
        raise RuntimeError(
            f"D60 post-reset baseline check failed (expected status={verify.expect_status}, got status={status})")
    if verify.expect_json_path is None:
        return
    try:
        doc = json.loads(body_text or "null")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"D60 post-reset baseline check response is not JSON: {exc}") from exc
    actual = extract_value(doc, verify.expect_json_path)
    if actual != verify.expect_json_equals:
        raise RuntimeError(
            f"D60 post-reset baseline check failed ({verify.expect_json_path} expected "
            f"{verify.expect_json_equals!r}, got {actual!r})")


def _reset_command(reset) -> list[str]:
    if getattr(reset, "command", None):
        return list(reset.command)
    script = getattr(reset, "script", None)
    if not script:
        raise RuntimeError("D60 reset lacks command/script")
    return ["bash", str((REPO_ROOT / script).resolve())]


def _verify_request(base_url: str, method: str, path: str) -> tuple[int, str | None]:
    req = urllib.request.Request(base_url.rstrip("/") + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8", errors="replace") or None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace") or None
    except Exception as exc:
        raise RuntimeError(f"D60 post-reset baseline check request failed: {exc}") from exc


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r{stamp}-{_pysecrets.token_hex(2)}"


def _prepare_recovery(initial_oas_path: str | Path, bundle_dirs: list[str | Path],
                      profile_path: str | Path, trust_basis: str):
    inp = load_inputs(initial_oas_path, bundle_dirs)
    profile = load_app_profile(profile_path)
    email, password = _credentials_for_profile(profile)  # plaintext stays in memory only (D12/D18)
    auth_context = _runtime_auth_for_profile(profile, email, password)  # real auth material stays in memory only (D29)

    secrets = SecretRegistry()  # fresh salt: redaction only needs equality to hold within this artifact
    for secret in (email, password, *auth_context.secret_values()):
        if secret:
            secrets.register(secret)

    prober = Prober(
        base_url=profile.base_url,
        token=auth_context.token,
        token_scheme=profile.auth.token_scheme,
        secrets=secrets,
        session_cookie_header=auth_context.session_cookie_header,
        session_cookie_name=auth_context.session_cookie_name,
        min_interval_ms=profile.rate_limit.min_interval_ms,
        trust_basis=trust_basis,
    )
    return inp, profile, email, password, secrets, prober


def _runtime_auth_for_profile(profile, email: str, password: str) -> RuntimeAuth:
    if getattr(profile.auth, "method", None) == "cookie_session":
        return login_auth(profile.base_url, email, password, profile.auth)
    token = login_token(profile.base_url, email, password, profile.auth)
    return RuntimeAuth(token=token, token_scheme=getattr(profile.auth, "token_scheme", "Token"))


def _credentials_for_profile(profile) -> tuple[str, str]:
    if getattr(profile.auth, "credentials_ref", None) is None:
        return "", ""
    return resolve_credentials(profile)


def _run_legacy_probes(inp, prober: Prober) -> list[dict]:
    targets = plan_probes(inp)
    probes: list[dict] = []
    for i, target in enumerate(targets, start=1):
        if prober.fused:
            break  # D28b: stop further probes after the circuit breaker trips
        probes.append(prober.execute(target, f"pr-{i:04d}"))
    return probes


def _probe_document(
    initial_oas_path: str | Path,
    inp,
    probes: list[dict],
    secrets: SecretRegistry,
    *,
    initial_oas_source_ref: str | None = None,
) -> dict:
    run_id = _new_run_id()
    document = {
        "metadata": make_envelope(
            artifact_type="probe_results",
            stage="stage2_5",
            run_id=run_id,
            upstream_refs=(
                [{"artifact_type": "initial_oas", "run_id": inp.initial_oas["x-carverflow-meta"]["run_id"],
                  "path": initial_oas_source_ref or str(initial_oas_path)}]
                + [{"artifact_type": "session_bundle", "run_id": rid, "path": str(b.bundle_dir)}
                   for rid, b in sorted(inp.bundles.items())]
            ),
        ),
        "probes": probes,
    }
    return secrets.redact_obj(document)  # D18 single redaction exit: tokens etc. never reach disk


def recover_probe_results(
    initial_oas_path: str | Path,
    bundle_dirs: list[str | Path],
    profile_path: str | Path,
    trust_basis: str = "per_probe_cleanup",
) -> tuple[dict, Prober]:
    """Plan → run probes → assemble probe_results (with D18 redaction). Returns (document, prober).
    trust_basis (D60): environment_reset trusts 2xx write probes via environment-level reversibility and forces a reset+check at batch end."""
    inp, profile, _email, _password, secrets, prober = _prepare_recovery(
        initial_oas_path, bundle_dirs, profile_path, trust_basis
    )

    probes = _run_legacy_probes(inp, prober)
    probes.extend(plan_discovery_candidates(inp).audit_records)

    if trust_basis == "environment_reset":
        _reset_and_verify(profile)  # D60: forced end-of-batch reset + baseline check (raises if the check fails)

    return _probe_document(initial_oas_path, inp, probes, secrets), prober


def recover_probe_results_audit_only(
    initial_oas_path: str | Path,
    bundle_dirs: list[str | Path],
    profile_path: str | Path,
    trust_basis: str = "per_probe_cleanup",
) -> tuple[dict, None]:
    """Build Stage2.5 audit records without resolving credentials or sending HTTP.

    This is the Web manual-recording analysis path: a user can record a real
    session without configured automation credentials, then recover API
    artifacts from the bundle. Explicit scheduled execution remains available
    through recover_probe_results_with_scheduled_execution.
    """
    inp = load_inputs(initial_oas_path, bundle_dirs)
    load_app_profile(profile_path)  # contract validation only; do not resolve credentials
    secrets = SecretRegistry()
    discovery = plan_discovery_candidates(inp)
    return _probe_document(initial_oas_path, inp, list(discovery.audit_records), secrets), None


def recover_probe_results_with_scheduled_execution(
    initial_oas_path: str | Path,
    bundle_dirs: list[str | Path],
    profile_path: str | Path,
    *,
    actor_by_run_id: Mapping[str, str],
    probe_budget: int,
    trust_basis: str = "per_probe_cleanup",
    initial_oas_source_ref: str | None = None,
) -> tuple[dict, dict[str, ScheduledDiscoveryRunner]]:
    """Execute a frozen budget through actor-isolated authenticated runners."""

    inp = load_inputs(initial_oas_path, bundle_dirs)
    profile = load_app_profile(profile_path)
    if set(actor_by_run_id) != set(inp.bundles):
        raise ValueError("Stage2.5 trace actor mapping does not close over bundles")
    actors = tuple(sorted(set(actor_by_run_id.values())))
    if not actors or any(not actor for actor in actors):
        raise ValueError("Stage2.5 trace actor mapping is invalid")
    for actor_id in actors:
        actor_auth(profile, actor_id)

    discovery = plan_discovery_candidates(inp)
    probe_actors = assign_probe_actors(discovery, actor_by_run_id)
    selected = select_active_probe_assignments(
        discovery,
        budget=probe_budget,
        probe_actors=probe_actors,
    )

    secrets = SecretRegistry()
    runners: dict[str, ScheduledDiscoveryRunner] = {}
    operation_index = build_op_index(inp.initial_oas)
    for actor_id in actors:
        auth = actor_auth(profile, actor_id)
        email = password = ""
        runtime_auth = RuntimeAuth(token_scheme=getattr(auth, "token_scheme", "Token"))
        if auth.method != "none":
            email, password = resolve_actor_credentials(profile, actor_id)
            runtime_auth = login_auth(profile.base_url, email, password, auth)
        for secret in (email, password, *runtime_auth.secret_values()):
            secrets.register(secret)
        runners[actor_id] = ScheduledDiscoveryRunner(
            ReplayConfig(
                base_url=profile.base_url.rstrip("/"),
                email=email,
                password=password,
                token_scheme=runtime_auth.token_scheme,
                auth_token=runtime_auth.token,
                session_cookie_header=runtime_auth.session_cookie_header,
                session_cookie_name=runtime_auth.session_cookie_name,
                trust_basis=trust_basis,
            ),
            operation_index,
            Throttle(profile.rate_limit.min_interval_ms),
        )

    probes = _explicit_scheduled_records(
        discovery,
        runners,
        inp,
        probe_actors=probe_actors,
        selected=selected,
    )
    if trust_basis == "environment_reset":
        _reset_and_verify(profile)
    return _probe_document(
        initial_oas_path,
        inp,
        probes,
        secrets,
        initial_oas_source_ref=initial_oas_source_ref,
    ), runners


def assign_probe_actors(
    discovery,
    actor_by_run_id: Mapping[str, str],
) -> dict[str, str | None]:
    plans = {plan.probe_id: plan for plan in discovery.scheduled_plans}
    return {
        str(record["probe_id"]): _probe_actor(
            record,
            plans.get(record.get("probe_id")),
            actor_by_run_id,
        )
        for record in discovery.audit_records
    }


def select_active_probe_assignments(
    discovery,
    *,
    budget: int,
    probe_actors: Mapping[str, str | None],
) -> tuple[tuple[str, str], ...]:
    """Freeze actor-stratified selection before login or probe transport."""

    if budget < 0:
        raise ValueError("active probe budget must be nonnegative")
    plans = {plan.probe_id: plan for plan in discovery.scheduled_plans}
    strata: dict[str, dict[tuple[str, str], list[dict]]] = {}
    for record in discovery.audit_records:
        probe_id = str(record["probe_id"])
        actor_id = probe_actors.get(probe_id)
        if actor_id is None or not _statically_executable_record(
            record, plans.get(probe_id)
        ):
            continue
        target = record.get("target", {})
        key = (
            str(record.get("probe_kind") or "unknown"),
            str(target.get("method") or "").upper(),
        )
        strata.setdefault(actor_id, {}).setdefault(key, []).append(record)
    for actor_strata in strata.values():
        for rows in actor_strata.values():
            rows.sort(key=_active_probe_sort_key)

    selected: list[tuple[str, str]] = []
    offsets = {
        (actor_id, key): 0
        for actor_id, actor_strata in strata.items()
        for key in actor_strata
    }
    cursors = {actor_id: 0 for actor_id in strata}
    while len(selected) < budget:
        progressed = False
        for actor_id in sorted(strata):
            keys = sorted(strata[actor_id])
            for step in range(len(keys)):
                key_index = (cursors[actor_id] + step) % len(keys)
                key = keys[key_index]
                offset_key = (actor_id, key)
                offset = offsets[offset_key]
                rows = strata[actor_id][key]
                if offset >= len(rows):
                    continue
                selected.append((str(rows[offset]["probe_id"]), actor_id))
                offsets[offset_key] = offset + 1
                cursors[actor_id] = (key_index + 1) % len(keys)
                progressed = True
                break
            if len(selected) == budget:
                break
        if not progressed:
            break
    return tuple(selected)


def _probe_actor(
    record: dict,
    plan: ScheduledProbePlan | None,
    actor_by_run_id: Mapping[str, str],
) -> str | None:
    basis = record.get("construction_basis", {}).get("generation_basis", {})
    schedule = record.get("schedule", {})
    refs = [
        basis.get("source_entry_id"),
        schedule.get("anchor_entry_id"),
        schedule.get("checkpoint_entry_id"),
    ]
    if plan is not None:
        refs.extend(
            [
                (plan.generation_basis or {}).get("source_entry_id"),
                plan.anchor_entry_id,
                plan.checkpoint_entry_id,
            ]
        )
    run_ids: set[str] = set()
    for ref in refs:
        if not isinstance(ref, str):
            continue
        run_id, separator, entry_index = ref.partition("#")
        if separator and run_id and entry_index.isdigit():
            run_ids.add(run_id)
    if not run_ids:
        return None
    actors = {actor_by_run_id.get(run_id) for run_id in run_ids}
    if None in actors or len(actors) != 1:
        return None
    return next(iter(actors))


def _explicit_scheduled_records(
    discovery,
    runners: Mapping[str, ScheduledDiscoveryRunner],
    inp: Stage25Inputs,
    *,
    probe_actors: Mapping[str, str | None],
    selected: tuple[tuple[str, str], ...],
) -> list[dict]:
    plans = {plan.probe_id: plan for plan in discovery.scheduled_plans}
    selected_actor = dict(selected)
    if len(selected_actor) != len(selected):
        raise ValueError("active probe selection contains duplicate IDs")
    source_records = list(discovery.audit_records)
    rank = {probe_id: index for index, (probe_id, _actor) in enumerate(selected)}
    original = {
        str(record["probe_id"]): index for index, record in enumerate(source_records)
    }
    execution_records = sorted(
        source_records,
        key=lambda record: (
            0 if record.get("probe_id") in rank else 1,
            rank.get(
                record.get("probe_id"),
                original[str(record.get("probe_id"))],
            ),
        ),
    )
    records: list[dict] = []
    for record in execution_records:
        probe_id = str(record["probe_id"])
        plan = plans.get(probe_id)
        if not _statically_executable_record(record, plan):
            records.append(record)
            continue
        actor_id = probe_actors.get(probe_id)
        if actor_id is None:
            records.append(
                _with_not_executed_reason(record, "active_probe_actor_unresolved")
            )
            continue
        if probe_id not in selected_actor:
            records.append(
                _with_not_executed_reason(record, "active_probe_budget_exhausted")
            )
            continue
        if selected_actor[probe_id] != actor_id or actor_id not in runners:
            raise ValueError("active probe actor assignment changed after selection")
        runner = runners[actor_id]
        if plan is None:
            records.append(
                _explicit_read_candidate_record(
                    record,
                    runner,
                    inp,
                    canonical_origin_only=True,
                )
            )
            continue
        executed = _execute_probe_or_record_transport_failure(
            runner,
            plan,
            record,
            canonical_origin_only=True,
        )
        if (
            plan.method.upper() in _DIAGNOSTIC_EXECUTION_METHODS
            and executed.get("execution_mode") != "not_executed"
        ):
            _mark_protocol_diagnostic(executed)
        records.append(executed)
    by_probe_id = {str(record["probe_id"]): record for record in records}
    return [by_probe_id[str(record["probe_id"])] for record in source_records]


def _execute_probe_or_record_transport_failure(
    runner: ScheduledDiscoveryRunner,
    plan: ScheduledProbePlan,
    audit_record: dict,
    *,
    canonical_origin_only: bool = False,
) -> dict:
    execution_plan = plan
    if canonical_origin_only and plan.canonical_path is not None:
        execution_plan = deepcopy(plan)
        execution_plan.candidate_url = None
    try:
        return execute_scheduled_probe(runner, execution_plan)
    except (urllib.error.URLError, TimeoutError, OSError):
        return _with_not_executed_reason(
            audit_record,
            "active_probe_transport_failed",
        )


def _statically_executable_record(
    record: dict,
    plan: ScheduledProbePlan | None,
) -> bool:
    if plan is None:
        if not _read_candidate(record):
            return False
        target = record.get("target", {})
        canonical_path = target.get("canonical_path")
        return (
            isinstance(canonical_path, str)
            and "{" not in canonical_path
            and "}" not in canonical_path
        )
    if record.get("not_executed_reason") != "scheduled_execution_disabled":
        return False
    if _recorded_state_delete_plan(plan) or _same_turn_creator_delete_plan(plan):
        return False
    return (
        plan.method.upper() in _SCHEDULED_EXECUTION_METHODS
        or _fresh_created_delete_plan(plan)
    )


def _active_probe_sort_key(record: dict) -> tuple[str, str, str, str, str]:
    target = record.get("target", {})
    basis = record.get("construction_basis", {}).get("generation_basis", {})
    return (
        str(record.get("probe_kind") or ""),
        str(target.get("method") or "").upper(),
        str(target.get("canonical_path") or ""),
        str(basis.get("generation_rule") or ""),
        str(record.get("probe_id") or ""),
    )


def _resolve_same_turn_fresh_creator_deletes(
    records: list[dict],
    plans: dict[str, ScheduledProbePlan],
    executed_plans: dict[str, tuple[ScheduledProbePlan, dict]],
    runner: ScheduledDiscoveryRunner,
) -> list[dict]:
    resolved: list[dict] = []
    for record in records:
        target = record.get("target", {})
        canonical_path = target.get("canonical_path")
        if (
            record.get("probe_kind") == "operation"
            and target.get("method") == "DELETE"
            and isinstance(canonical_path, str)
            and record.get("success") is not True
        ):
            fallback_plan = plans.get(record.get("probe_id"))
            creator = _same_turn_creator_execution(fallback_plan, executed_plans)
            if creator is not None:
                same_turn = _same_turn_fresh_delete_plan(record, fallback_plan, creator)
                if same_turn is not None:
                    same_turn_plan, same_turn_identity = same_turn
                    resolved.append(
                        _execute_same_turn_fresh_delete(
                            runner,
                            same_turn_plan,
                            creator,
                            same_turn_identity,
                        )
                    )
                    continue
            if fallback_plan is not None and _same_turn_creator_delete_plan(fallback_plan):
                resolved.append(_with_not_executed_reason(record, "unsafe_destructive_without_fresh_anchor"))
                continue
            if (
                fallback_plan is not None
                and record.get("not_executed_reason") == "scheduled_execution_disabled"
                and _recorded_state_delete_plan(fallback_plan)
            ):
                resolved.append(execute_scheduled_probe(runner, fallback_plan))
                continue
        resolved.append(record)
    return resolved


def _same_turn_collection_post_creators(
    executed_plans: dict[str, tuple[ScheduledProbePlan, dict]],
) -> dict[str, tuple[ScheduledProbePlan, dict, Any]]:
    creators: dict[str, tuple[ScheduledProbePlan, dict, Any]] = {}
    for probe_id in sorted(executed_plans):
        plan, record = executed_plans[probe_id]
        if plan.method.upper() != "POST" or not plan.canonical_path or "{" in plan.canonical_path:
            continue
        if record.get("success") is not True:
            continue
        body = _response_body_json(record)
        if body is None:
            continue
        creators.setdefault(plan.canonical_path, (plan, record, body))
    return creators


def _same_turn_creator_execution(
    plan: ScheduledProbePlan | None,
    executed_plans: dict[str, tuple[ScheduledProbePlan, dict]],
) -> tuple[ScheduledProbePlan, dict, Any] | None:
    if plan is not None and _same_turn_creator_delete_plan(plan):
        creator_probe_id = plan.checkpoint_entry_id
        if creator_probe_id:
            creator = executed_plans.get(creator_probe_id)
            if creator is not None:
                creator_plan, creator_record = creator
                if creator_record.get("success") is True:
                    creator_body = _response_body_json(creator_record)
                    if creator_body is not None:
                        return creator_plan, creator_record, creator_body
        return None
    creators = _same_turn_collection_post_creators(executed_plans)
    if plan is None or not plan.canonical_path:
        return None
    collection_path, _param = _collection_and_trailing_param(plan.canonical_path)
    return creators.get(collection_path or "")


def _same_turn_fresh_delete_plan(
    target_record: dict,
    fallback_plan: ScheduledProbePlan | None,
    creator: tuple[ScheduledProbePlan, dict, Any],
) -> tuple[ScheduledProbePlan, dict[str, str]] | None:
    creator_plan, creator_record, creator_body = creator
    target = target_record.get("target", {})
    canonical_path = target.get("canonical_path")
    if not isinstance(canonical_path, str):
        return None
    _collection_path, param = _collection_and_trailing_param(canonical_path)
    if param is None:
        return None
    selected = _select_creator_leaf(creator_body, param)
    if selected is None:
        return None
    jsonpath, value, evidence = selected
    auth_prefix = _same_turn_auth_prefix(creator_plan)
    probe_step = len(auth_prefix["steps"])
    basis = _same_turn_generation_basis(target_record, creator_record, jsonpath, evidence)
    identity = {
        "path_param": param,
        "source_field": jsonpath,
        "source_value": value,
        "evidence": evidence,
    }
    return ScheduledProbePlan(
        probe_id=target_record["probe_id"],
        method="DELETE",
        canonical_path=canonical_path,
        operation_id=target.get("operation_id"),
        prefix_steps=list(auth_prefix["steps"]),
        bindings=auth_prefix["bindings"],
        parameters=[
            *auth_prefix["parameters"],
            *_same_turn_creator_path_parameters(creator_plan, creator_record, probe_step),
            {
                "to_step": probe_step,
                "to_location": "path",
                "to_field": param,
                "value": value,
            },
        ],
        generation_basis=basis,
        schedule_kind="checkpoint",
        anchor_entry_id=target_record.get("schedule", {}).get("anchor_entry_id"),
        checkpoint_entry_id=creator_record["probe_id"],
        checkpoint_type="operation_based",
        checkpoint_method="POST",
        insertion_policy="after_checkpoint",
        suffix_policy="skip",
        prefix_body_templates=auth_prefix["body_templates"],
    ), identity


def _execute_same_turn_fresh_delete(
    runner: ScheduledDiscoveryRunner,
    plan: ScheduledProbePlan,
    creator: tuple[ScheduledProbePlan, dict, Any],
    identity: dict[str, str],
) -> dict:
    record = execute_scheduled_probe(runner, plan)
    _annotate_same_turn_delete_record(record, plan, creator, identity)
    return record


def _resolve_fresh_producer_bridges(
    records: list[dict],
    inp: Stage25Inputs,
    runner: ScheduledDiscoveryRunner,
) -> list[dict]:
    """Verify existing instance consumers against successful scheduled POSTs.

    A scheduled POST /collection may create a fresh resource that can safely
    prove existing /collection/{param} consumers.  The POST itself is not an
    initial replay step, so bridge probes use the just-observed fresh identity
    as audited material rather than pretending to replay the POST as prefix.
    """
    bridge_records: list[dict] = []
    existing_probe_ids = {str(record.get("probe_id")) for record in records if record.get("probe_id")}
    for producer in _fresh_producer_records(records):
        target = producer.get("target", {})
        collection_path = target.get("canonical_path")
        if not isinstance(collection_path, str):
            continue
        identities = _fresh_identity_candidates(producer, collection_path, runner.cfg.base_url)
        if not identities:
            continue
        consumers = _fresh_bridge_consumers(inp, collection_path)
        for consumer in consumers:
            probe_id = _fresh_bridge_probe_id(producer["probe_id"], consumer)
            if probe_id in existing_probe_ids:
                continue
            existing_probe_ids.add(probe_id)
            bridge_records.append(_execute_fresh_bridge_consumer(runner, producer, identities, consumer, inp))
    return _replace_or_append_bridge_records(records, bridge_records)


def _replace_or_append_bridge_records(records: list[dict], bridge_records: list[dict]) -> list[dict]:
    bridge_by_target: dict[tuple[str, str], list[dict]] = {}
    for record in bridge_records:
        target = record.get("target", {})
        method = target.get("method")
        canonical_path = target.get("canonical_path")
        if isinstance(method, str) and isinstance(canonical_path, str):
            bridge_by_target.setdefault((method.upper(), canonical_path), []).append(record)
    for values in bridge_by_target.values():
        values.sort(key=lambda item: item.get("probe_id", ""))

    used: set[int] = set()
    out: list[dict] = []
    for record in records:
        target = record.get("target", {})
        key = (str(target.get("method") or "").upper(), target.get("canonical_path"))
        replacements = bridge_by_target.get(key)
        if (
            replacements
            and record.get("execution_mode") == "not_executed"
            and record.get("probe_kind") == "operation"
        ):
            replacement = replacements[0]
            used.add(id(replacement))
            out.append(replacement)
            continue
        out.append(record)
    for record in bridge_records:
        if id(record) not in used:
            out.append(record)
    return out


def _fresh_producer_records(records: list[dict]) -> list[dict]:
    producers = []
    for record in records:
        target = record.get("target", {})
        method = str(target.get("method") or "").upper()
        canonical_path = target.get("canonical_path")
        if (
            record.get("execution_mode") != "scheduled"
            or record.get("success") is not True
            or method != "POST"
            or not isinstance(canonical_path, str)
            or "{" in canonical_path
            or "}" in canonical_path
        ):
            continue
        material = record.get("material") or {}
        if material.get("material_sufficiency") != "sufficient":
            continue
        if material.get("value_basis") in {"recorded_literal", "recorded_literal_assumption"}:
            continue
        generation_basis = (
            (record.get("construction_basis") or {}).get("generation_basis")
            if isinstance(record.get("construction_basis"), dict)
            else None
        )
        if (
            isinstance(generation_basis, dict)
            and generation_basis.get("generation_rule") == "oas_destructive_probe_candidate"
        ):
            continue
        producers.append(record)
    producers.sort(key=lambda item: item.get("probe_id", ""))
    return producers


def _fresh_identity_candidates(producer: dict, collection_path: str, base_url: str) -> list[dict]:
    candidates: list[dict] = []
    response = producer.get("response") or {}
    headers = response.get("headers") or {}
    for name, value in sorted(headers.items()):
        if str(name).lower() == "location":
            candidate = _identity_from_url_like(
                str(value),
                collection_path,
                base_url,
                source_location="response_header",
                source_field="location",
                source_rank=0,
            )
            if candidate is not None:
                candidates.append(candidate)
        elif str(name).lower() == "link":
            for link in parse_link_header(str(value)):
                url = link.get("url")
                if not url:
                    continue
                rel = link.get("rel") or "link"
                candidate = _identity_from_url_like(
                    url,
                    collection_path,
                    base_url,
                    source_location="response_header",
                    source_field=f"Link;rel={rel}",
                    source_rank=1,
                )
                if candidate is not None:
                    candidates.append(candidate)
    body = _response_body_json(producer)
    if body is not None:
        for jsonpath, key, value in _json_leaves(body):
            text = _scalar_text(value)
            if text is None or _unsafe_identity_text(text) or _sensitive_identity_field(key):
                continue
            candidates.append({
                "value": text,
                "source_location": "response_body",
                "source_field": jsonpath,
                "source_rank": _identity_field_rank(key),
            })
            url_candidate = _identity_from_url_like(
                text,
                collection_path,
                base_url,
                source_location="response_body",
                source_field=jsonpath,
                source_rank=max(0, _identity_field_rank(key) - 1),
            )
            if url_candidate is not None:
                candidates.append(url_candidate)
    deduped: dict[tuple[str, str, str], dict] = {}
    for candidate in candidates:
        key = (candidate["value"], candidate["source_location"], candidate["source_field"])
        deduped.setdefault(key, candidate)
    return sorted(deduped.values(), key=lambda item: (item["source_rank"], item["source_field"], item["value"]))


def _identity_from_url_like(
    raw_value: str,
    collection_path: str,
    base_url: str,
    *,
    source_location: str,
    source_field: str,
    source_rank: int,
) -> dict | None:
    path = _same_origin_path(raw_value, base_url)
    if path is None:
        return None
    collection = _normalize_collection_path(collection_path)
    if collection is None:
        return None
    if not path.startswith(collection + "/"):
        return None
    remainder = path[len(collection):].strip("/")
    if not remainder or "/" in remainder:
        return None
    if _unsafe_identity_text(remainder):
        return None
    return {
        "value": remainder,
        "source_location": source_location,
        "source_field": f"{source_field}.path[-1]",
        "source_rank": source_rank,
    }


def _same_origin_path(raw_value: str, base_url: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None
    if value.startswith("/") and not value.startswith("//"):
        parts = urlsplit(value)
        if parts.query or parts.fragment:
            return None
        return parts.path.rstrip("/") or "/"
    parts = urlsplit(value)
    base = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
        return None
    if parts.query or parts.fragment:
        return None
    return parts.path.rstrip("/") or "/"


def _unsafe_identity_text(value: str) -> bool:
    lowered = value.lower()
    if not value or value.startswith("[REDACTED:"):
        return True
    if any(part in lowered for part in ("password", "passwd", "token", "secret", "cookie", "jwt", "credential")):
        return True
    if "@" in value:
        return True
    return False


def _sensitive_identity_field(field: str) -> bool:
    lowered = field.lower()
    return any(part in lowered for part in ("password", "passwd", "token", "secret", "cookie", "jwt", "credential", "email"))


def _identity_field_rank(field: str) -> int:
    key = field.lower().rsplit(".", 1)[-1]
    key = key.split("[", 1)[0]
    if key in {"id", "slug", "uuid"}:
        return 1
    if key.endswith("_id") or key.endswith("id"):
        return 2
    if key in {"code", "key"}:
        return 3
    return 8


def _fresh_bridge_consumers(inp: Stage25Inputs, collection_path: str) -> list[dict]:
    consumers: list[dict] = []
    for canonical_path, item in inp.initial_oas.get("paths", {}).items():
        match = _collection_and_first_param(canonical_path)
        if match is None:
            continue
        consumer_collection, param = match
        if not _same_collection_path(consumer_collection, collection_path):
            continue
        path_info = inp.paths.get(canonical_path)
        for method, op in item.items():
            method_upper = method.upper()
            if method_upper not in {"GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                continue
            consumers.append({
                "method": method_upper,
                "canonical_path": canonical_path,
                "operation_id": op.get("operationId"),
                "path_param": param,
                "path_info": path_info,
                "direct": _direct_instance_template(collection_path, canonical_path),
            })
    consumers.sort(key=lambda item: (
        0 if item["direct"] else 1,
        {"GET": 0, "HEAD": 1, "OPTIONS": 2, "PUT": 3, "PATCH": 4, "DELETE": 5}.get(item["method"], 9),
        item["canonical_path"],
    ))
    return consumers


def _collection_and_first_param(canonical_path: str) -> tuple[str, str] | None:
    parts = [part for part in canonical_path.strip("/").split("/") if part]
    for index, part in enumerate(parts):
        if part.startswith("{") and part.endswith("}") and len(part) > 2:
            if index == 0:
                return None
            return "/" + "/".join(parts[:index]), part[1:-1]
    return None


def _direct_instance_template(collection_path: str, canonical_path: str) -> bool:
    collection = _normalize_collection_path(collection_path)
    if collection is None:
        return False
    collection_parts = [part for part in collection.strip("/").split("/") if part]
    parts = [part for part in canonical_path.strip("/").split("/") if part]
    return (
        len(parts) == len(collection_parts) + 1
        and parts[:len(collection_parts)] == collection_parts
        and parts[-1].startswith("{")
        and parts[-1].endswith("}")
    )


def _normalize_collection_path(path: str | None) -> str | None:
    if not isinstance(path, str):
        return None
    parts = [part for part in path.strip("/").split("/") if part]
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def _same_collection_path(left: str | None, right: str | None) -> bool:
    left_norm = _normalize_collection_path(left)
    right_norm = _normalize_collection_path(right)
    return left_norm is not None and right_norm is not None and left_norm == right_norm


def _execute_fresh_bridge_consumer(
    runner: ScheduledDiscoveryRunner,
    producer: dict,
    identities: list[dict],
    consumer: dict,
    inp: Stage25Inputs,
) -> dict:
    last_record: dict | None = None
    for identity in identities:
        plan = _fresh_bridge_plan(producer, identity, consumer)
        if plan is None:
            continue
        if consumer["method"] in _BODY_BEARING_METHODS:
            body_material = _fresh_bridge_body_material(consumer)
            if body_material is None:
                return _fresh_bridge_not_executed(
                    producer,
                    identity,
                    consumer,
                    "body_template_required_for_write_consumer",
                )
            plan.body_template = body_material[1]
            plan.body_template_source = body_material[0]
            plan.body_material_basis = "mixed"
        record = execute_scheduled_probe(runner, plan)
        _annotate_fresh_bridge_record(record, producer, identity, consumer)
        last_record = record
        if record.get("success") is True:
            return record
    return last_record or _fresh_bridge_not_executed(
        producer,
        identities[0],
        consumer,
        "fresh_identity_not_resolved",
    )


def _fresh_bridge_body_material(consumer: dict) -> tuple[str, str] | None:
    path_info = consumer.get("path_info")
    if path_info is None:
        return None
    ref, body = path_info.reusable_write_body
    if not body:
        return None
    return ref or "reusable_write_body", body


def _fresh_bridge_plan(producer: dict, identity: dict, consumer: dict) -> ScheduledProbePlan | None:
    operation_id = consumer.get("operation_id")
    if not operation_id:
        return None
    return ScheduledProbePlan(
        probe_id=_fresh_bridge_probe_id(producer["probe_id"], consumer),
        method=consumer["method"],
        canonical_path=consumer["canonical_path"],
        operation_id=operation_id,
        prefix_steps=[],
        bindings=[],
        parameters=[{
            "to_step": 0,
            "to_location": "path",
            "to_field": consumer["path_param"],
            "value": identity["value"],
        }],
        generation_basis=_fresh_bridge_generation_basis(producer, identity, consumer),
        schedule_kind="checkpoint",
        checkpoint_entry_id=producer["probe_id"],
        checkpoint_type="operation_based",
        checkpoint_method="POST",
        insertion_policy="after_checkpoint",
        suffix_policy="skip" if consumer["method"] == "DELETE" else "not_applicable",
    )


def _fresh_bridge_probe_id(producer_probe_id: str, consumer: dict) -> str:
    return f"{producer_probe_id}-bridge-{consumer['method'].lower()}-{consumer.get('operation_id') or 'consumer'}"


def _fresh_bridge_generation_basis(producer: dict, identity: dict, consumer: dict) -> dict:
    return {
        "generation_rule": "fresh_producer_bridge",
        "source_location": identity["source_location"],
        "source_field": identity["source_field"],
        "source_value": identity["value"],
        "source_part": "value",
        "derived_candidate": f"{consumer['method']} {consumer['canonical_path']}",
        "reason": (
            f"successful scheduled POST probe {producer['probe_id']} produced a fresh identity; "
            f"verify existing consumer template {consumer['canonical_path']}"
        ),
    }


def _annotate_fresh_bridge_record(
    record: dict,
    producer: dict,
    identity: dict,
    consumer: dict,
) -> None:
    producer_target = producer.get("target") or {}
    material = record.setdefault("material", {})
    fresh_binding = {
        "from_step": 0,
        "from_location": identity["source_location"],
        "from_field": identity["source_field"],
        "to_location": "path",
        "to_field": consumer["path_param"],
    }
    material["fresh_value_bindings"] = [fresh_binding, *material.get("fresh_value_bindings", [])]
    material["value_basis"] = "mixed" if consumer["method"] in _BODY_BEARING_METHODS else "fresh_replay"
    material["material_sufficiency"] = "sufficient"
    material["producer_probe_id"] = producer["probe_id"]
    if producer_target.get("operation_id"):
        material["producer_operation_id"] = producer_target.get("operation_id")
    material["consumer_template"] = consumer["canonical_path"]
    material["fresh_identity_source"] = {
        "source_location": identity["source_location"],
        "source_field": identity["source_field"],
        "source_value": identity["value"],
    }
    material["verification_status"] = "verified" if record.get("success") is True else "failed"


def _fresh_bridge_not_executed(
    producer: dict,
    identity: dict,
    consumer: dict,
    reason: str,
) -> dict:
    record = {
        "probe_id": _fresh_bridge_probe_id(producer["probe_id"], consumer),
        "probe_kind": "operation",
        "execution_mode": "not_executed",
        "not_executed_reason": reason,
        "target": {
            "method": consumer["method"],
            "canonical_path": consumer["canonical_path"],
            "operation_id": consumer["operation_id"],
        },
        "construction_basis": {
            "strategy": "scheduled_discovery",
            "generation_basis": _fresh_bridge_generation_basis(producer, identity, consumer),
        },
        "schedule": {
            "schedule_kind": "not_scheduled",
            "checkpoint_entry_id": producer["probe_id"],
            "checkpoint_type": "operation_based",
            "checkpoint_method": "POST",
            "insertion_policy": "not_scheduled",
            "suffix_policy": "not_applicable",
        },
        "material": {
            "fresh_value_bindings": [{
                "from_step": 0,
                "from_location": identity["source_location"],
                "from_field": identity["source_field"],
                "to_location": "path",
                "to_field": consumer["path_param"],
            }],
            "value_basis": "fresh_replay",
            "material_sufficiency": "insufficient",
            "producer_probe_id": producer["probe_id"],
            "consumer_template": consumer["canonical_path"],
            "fresh_identity_source": {
                "source_location": identity["source_location"],
                "source_field": identity["source_field"],
                "source_value": identity["value"],
            },
            "verification_status": "not_executed",
        },
        "admission": {
            "existence_evidence": "non_evidence",
            "admission_decision": "not_executed",
        },
    }
    producer_operation_id = producer.get("target", {}).get("operation_id")
    if producer_operation_id:
        record["material"]["producer_operation_id"] = producer_operation_id
    return record


def _same_turn_auth_prefix(creator_plan: ScheduledProbePlan) -> dict[str, Any]:
    creator_probe_step = len(creator_plan.prefix_steps)
    auth_producers = sorted({
        binding["from_step"]
        for binding in creator_plan.bindings
        if binding.get("to_step") == creator_probe_step
        and binding.get("to_location") == "header"
        and binding.get("to_field") == "Authorization"
    })
    if not auth_producers:
        return {"steps": [], "bindings": [], "parameters": [], "body_templates": {}}
    keep_step_count = max(auth_producers) + 1
    probe_step = keep_step_count
    return {
        "steps": list(creator_plan.prefix_steps[:keep_step_count]),
        "bindings": [
            *[
                {
                    "from_step": binding["from_step"],
                    "from_location": binding.get("from_location", "response_body"),
                    "from_field": binding["from_field"],
                    "to_step": binding["to_step"],
                    "to_location": binding["to_location"],
                    "to_field": binding["to_field"],
                }
                for binding in creator_plan.bindings
                if binding.get("to_step", 0) < keep_step_count
            ],
            *[
                {
                    "from_step": binding["from_step"],
                    "from_location": binding.get("from_location", "response_body"),
                    "from_field": binding["from_field"],
                    "to_step": probe_step,
                    "to_location": "header",
                    "to_field": binding["to_field"],
                }
                for binding in creator_plan.bindings
                if binding.get("to_step") == creator_probe_step
                and binding.get("to_location") == "header"
                and binding.get("to_field") == "Authorization"
            ],
        ],
        "parameters": [
            {
                "to_step": parameter["to_step"],
                "to_location": parameter["to_location"],
                "to_field": parameter["to_field"],
                "value": parameter["value"],
            }
            for parameter in creator_plan.parameters
            if parameter.get("to_step", 0) < keep_step_count
        ],
        "body_templates": {
            step: body
            for step, body in creator_plan.prefix_body_templates.items()
            if step < keep_step_count
        },
    }


def _same_turn_creator_path_parameters(
    creator_plan: ScheduledProbePlan,
    creator_record: dict,
    probe_step: int,
) -> list[dict]:
    if not creator_plan.canonical_path:
        return []
    request_url = (creator_record.get("request") or {}).get("url")
    if not isinstance(request_url, str) or not request_url:
        return []
    concrete_segments = [segment for segment in urlsplit(request_url).path.strip("/").split("/") if segment]
    template_segments = [segment for segment in creator_plan.canonical_path.strip("/").split("/") if segment]
    if len(concrete_segments) != len(template_segments):
        return []
    parameters = []
    for template, concrete in zip(template_segments, concrete_segments, strict=False):
        if not (template.startswith("{") and template.endswith("}") and len(template) > 2):
            continue
        parameters.append({
            "to_step": probe_step,
            "to_location": "path",
            "to_field": template[1:-1],
            "value": unquote(concrete),
        })
    return parameters


def _same_turn_generation_basis(
    target_record: dict,
    creator_record: dict,
    jsonpath: str,
    evidence: str,
) -> dict:
    basis = target_record.get("construction_basis", {}).get("generation_basis")
    basis = dict(basis) if isinstance(basis, dict) else {
        "generation_rule": "method_gap",
        "source_location": "checkpoint",
        "source_part": "method_gap",
        "derived_candidate": f"DELETE {target_record.get('target', {}).get('canonical_path', '')}",
    }
    reason = basis.get("reason") or "DELETE scheduled from same-turn fresh creator"
    basis["reason"] = (
        f"{reason}; same-turn successful POST probe {creator_record['probe_id']} "
        f"provides fresh path value from {jsonpath} ({evidence})"
    )
    return basis


def _annotate_same_turn_delete_record(
    record: dict,
    plan: ScheduledProbePlan,
    creator: tuple[ScheduledProbePlan, dict, Any],
    identity: dict[str, str],
) -> None:
    creator_plan, creator_record, _creator_body = creator
    material = record.setdefault("material", {})
    preserved = [
        binding
        for binding in material.get("fresh_value_bindings", [])
        if binding.get("to_location") in {"path", "query"}
        or (
            binding.get("to_location") == "header"
            and binding.get("to_field") == "Authorization"
        )
    ]
    param = identity.get("path_param")
    from_field = identity.get("source_field")
    if isinstance(param, str) and isinstance(from_field, str):
        path_binding = {
            "from_step": len(plan.prefix_steps),
            "from_location": "response_body",
            "from_field": from_field,
            "to_location": "path",
            "to_field": param,
        }
        if path_binding not in preserved:
            preserved.append(path_binding)
    material["fresh_value_bindings"] = preserved
    material["value_basis"] = "fresh_replay"
    material["material_sufficiency"] = "sufficient"
    material.pop("literal_assumptions", None)
    material["producer_probe_id"] = creator_record["probe_id"]
    material["consumer_template"] = record.get("target", {}).get("canonical_path")
    if isinstance(from_field, str) and isinstance(param, str):
        material["fresh_identity_source"] = {
            "source_location": "response_body",
            "source_field": from_field,
            "source_value": identity.get("source_value"),
        }
    material["verification_status"] = "verified" if record.get("success") is True else "failed"
    creator_operation_id = (creator_record.get("target") or {}).get("operation_id") or creator_plan.operation_id
    if isinstance(creator_operation_id, str) and creator_operation_id:
        schedule = record.setdefault("schedule", {})
        prefix_steps = list(schedule.get("prefix_steps") or [])
        if creator_operation_id not in prefix_steps:
            prefix_steps.append(creator_operation_id)
        schedule["prefix_steps"] = prefix_steps
        schedule["probe_step"] = len(prefix_steps)


def _response_body_json(record: dict) -> Any | None:
    body = record.get("response", {}).get("body")
    if not isinstance(body, str) or not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _select_creator_leaf(body: Any, param: str) -> tuple[str, str, str] | None:
    candidates: list[tuple[int, str, str, str]] = []
    param_lower = param.lower()
    for jsonpath, key, value in _json_leaves(body):
        text = _scalar_text(value)
        if text is None:
            continue
        key_lower = key.lower()
        if key_lower == param_lower:
            candidates.append((0, jsonpath, text, "response_key_matches_path_param"))
        elif key_lower == "slug":
            candidates.append((1, jsonpath, text, "response_key_is_slug"))
        elif key_lower == "id":
            candidates.append((2, jsonpath, text, "response_key_is_id"))
        elif key_lower == "uuid":
            candidates.append((3, jsonpath, text, "response_key_is_uuid"))
        elif key_lower.endswith("_id"):
            candidates.append((4, jsonpath, text, "response_key_is_id_like"))
    if not candidates:
        return None
    _priority, jsonpath, text, evidence = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    return jsonpath, text, evidence


def _json_leaves(value: Any, path: str = "$") -> list[tuple[str, str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, str, Any]] = []
        for key, child in value.items():
            child_path = f"$.{key}" if path == "$" else f"{path}.{key}"
            out.extend(_json_leaves(child, child_path))
        return out
    if isinstance(value, list):
        out = []
        for i, child in enumerate(value):
            out.extend(_json_leaves(child, f"{path}[{i}]"))
        return out
    return [(path, _leaf_key(path), value)]


def _leaf_key(path: str) -> str:
    tail = path.rsplit(".", 1)[-1]
    if "[" in tail:
        tail = tail.split("[", 1)[0]
    return tail.strip("$")


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value)
        return text if text else None
    return None


def _collection_and_trailing_param(canonical_path: str) -> tuple[str | None, str | None]:
    parts = [part for part in canonical_path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None, None
    tail = parts[-1]
    if not (tail.startswith("{") and tail.endswith("}") and len(tail) > 2):
        return None, None
    return "/" + "/".join(parts[:-1]), tail[1:-1]


def _fresh_created_delete_plan(plan: ScheduledProbePlan) -> bool:
    probe_step = len(plan.prefix_steps)
    return (
        plan.method.upper() == "DELETE"
        and plan.checkpoint_method == "POST"
        and plan.checkpoint_type == "operation_based"
        and plan.suffix_policy == "skip"
        and any(
            binding.get("to_step") == probe_step
            and binding.get("to_location") == "path"
            and binding.get("from_location", "response_body") == "response_body"
            for binding in plan.bindings
        )
    )


def _same_turn_creator_delete_plan(plan: ScheduledProbePlan) -> bool:
    return (
        plan.method.upper() == "DELETE"
        and isinstance(plan.checkpoint_entry_id, str)
        and bool(plan.checkpoint_entry_id)
        and plan.checkpoint_entry_id.startswith("pr-013d-")
        and plan.checkpoint_method == "POST"
        and plan.checkpoint_type == "operation_based"
        and not plan.prefix_steps
    )


def _recorded_state_delete_plan(plan: ScheduledProbePlan) -> bool:
    return (
        plan.method.upper() == "DELETE"
        and plan.checkpoint_method in {None, "GET", "PUT"}
        and plan.checkpoint_type == "operation_based"
        and plan.suffix_policy == "skip"
        and any(
            assumption.get("location") == "path"
            and assumption.get("reason") == "recorded_literal_reused"
            for assumption in plan.literal_assumptions
        )
    )


def _explicit_read_candidate_record(
    record: dict,
    runner: ScheduledDiscoveryRunner,
    inp: Stage25Inputs,
    *,
    canonical_origin_only: bool = False,
) -> dict:
    """Execute 013-E-B read-only candidates when the target is safe to send.

    Canonical-path successes may enter augmented_oas. Candidate-url-only
    successes remain diagnostic because they are not stable API templates.
    """
    if not _read_candidate(record):
        return record

    target = record.get("target", {})
    canonical_path = target.get("canonical_path")
    candidate_url = target.get("candidate_url")
    if canonical_path and ("{" in canonical_path or "}" in canonical_path):
        return _with_not_executed_reason(
            record,
            "scheduled_execution_parameterized_canonical_path_disabled",
        )
    if not canonical_path and not candidate_url:
        return _with_not_executed_reason(record, "scheduled_execution_missing_target")

    executed = _execute_probe_or_record_transport_failure(
        runner,
        _read_plan_from_record(record),
        record,
        canonical_origin_only=canonical_origin_only,
    )
    if executed.get("execution_mode") == "not_executed":
        return executed
    _preserve_read_material(record, executed)
    if candidate_url and not canonical_path:
        _mark_or_upgrade_candidate_url(executed, inp, runner.cfg.base_url)
    return executed


def _read_candidate(record: dict) -> bool:
    target = record.get("target", {})
    return (
        record.get("execution_mode") == "not_executed"
        and record.get("probe_kind") in _READ_EXECUTION_KINDS
        and target.get("method", "").upper() == "GET"
    )


def _read_plan_from_record(record: dict) -> ScheduledProbePlan:
    target = record.get("target", {})
    basis = record.get("construction_basis", {}).get("generation_basis")
    return ScheduledProbePlan(
        probe_id=record["probe_id"],
        method=target.get("method", "GET"),
        canonical_path=target.get("canonical_path"),
        candidate_url=target.get("candidate_url"),
        operation_id=target.get("operation_id"),
        prefix_steps=[],
        bindings=[],
        probe_kind=record.get("probe_kind", "response"),
        generation_basis=dict(basis) if isinstance(basis, dict) else None,
        schedule_kind="standalone",
        checkpoint_type="none",
        insertion_policy="not_scheduled",
        suffix_policy="not_applicable",
    )


def _preserve_read_material(source: dict, executed: dict) -> None:
    material = source.get("material")
    if isinstance(material, dict):
        executed["material"] = json.loads(json.dumps(material, ensure_ascii=False))


def _mark_candidate_url_diagnostic(record: dict) -> None:
    success = bool(record.get("success"))
    record["admission"] = {
        "existence_evidence": "diagnostic_exists" if success else "non_evidence",
        "admission_decision": "diagnostic_only" if success else "not_admitted",
    }


def _mark_or_upgrade_candidate_url(record: dict, inp: Stage25Inputs, base_url: str) -> None:
    if not record.get("success"):
        _mark_candidate_url_diagnostic(record)
        return
    decision = canonicalize_candidate_url_probe(record, inp, base_url)
    if not decision.upgraded:
        _annotate_candidate_url_canonicalization(record, decision.reason, decision.evidence)
        _mark_candidate_url_diagnostic(record)
        return

    target = record.setdefault("target", {})
    target["canonical_path"] = decision.canonical_path
    if decision.operation_id:
        target["operation_id"] = decision.operation_id
    _annotate_candidate_url_canonicalization(record, decision.reason, decision.evidence)
    record["admission"] = {
        "existence_evidence": "strong_success",
        "admission_decision": "admit_augmented_oas",
    }


def _annotate_candidate_url_canonicalization(record: dict, reason: str, evidence: list[str]) -> None:
    basis = record.get("construction_basis", {}).get("generation_basis")
    if not isinstance(basis, dict):
        return
    note = f"candidate_url_canonicalization={reason or 'none'}"
    if evidence:
        note += f"; evidence={','.join(sorted(evidence))}"
    if basis.get("notes"):
        basis["notes"] = f"{basis['notes']}; {note}"
    else:
        basis["notes"] = note


def _mark_protocol_diagnostic(record: dict) -> None:
    response = record.get("response") or {}
    status = response.get("status")
    diagnostic = bool(record.get("success")) or status in _DIAGNOSTIC_STATUS_CODES
    record["admission"] = {
        "existence_evidence": "diagnostic_exists" if diagnostic else "non_evidence",
        "admission_decision": "diagnostic_only" if diagnostic else "not_admitted",
    }


def _with_not_executed_reason(record: dict, reason: str) -> dict:
    out = json.loads(json.dumps(record, ensure_ascii=False))
    out["execution_mode"] = "not_executed"
    out["not_executed_reason"] = reason
    out["admission"] = {
        "existence_evidence": "non_evidence",
        "admission_decision": "not_executed",
    }
    for field in ("request", "response", "success", "cleanup"):
        out.pop(field, None)
    return out


def canonical_dumps(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"


def discovery_set(document: dict) -> frozenset:
    """D34 set-level determinism view: {(method, canonical_path, success)} (no volatile fields/response bodies).

    Since 013-D-E, probe_results also contains not_executed/candidate_url-only audit candidates;
    the set-level view only counts actually executed legacy standalone/scheduled facts that have a canonical_path.
    """
    return frozenset(
        (p["target"]["method"], p["target"]["canonical_path"], p["success"])
        for p in document["probes"]
        if "success" in p and p.get("target", {}).get("canonical_path")
    )


def run_stage2_5(
    initial_oas_path: str | Path,
    bundle_dirs: list[str | Path],
    profile_path: str | Path,
    artifacts_root: str | Path | None = None,
    trust_basis: str = "per_probe_cleanup",
) -> tuple[dict, Path]:
    """Entry point: run probes → contract validation → write to disk (D12 path convention). trust_basis is passed through (D60)."""
    document, _ = recover_probe_results(initial_oas_path, bundle_dirs, profile_path, trust_basis)
    validate_artifact("probe_results.schema.json", document)  # schema-validate before writing
    artifacts_root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = artifacts_root / document["metadata"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "probe_results.json"
    out_path.write_text(canonical_dumps(document))
    return document, out_path
