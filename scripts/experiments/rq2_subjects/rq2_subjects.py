"""RQ2 (fault detection) on the added subjects umami / paperless / ghost with data-driven faults.

The frozen evaluator ``ui_semantics.rq2_evaluation`` hard-codes the Conduit/RWA routes, fault
catalogue and deployments; it stays untouched.  This runner reuses its projection (O0/O1/O2,
business-only, unknown), its per-fault reduction and summary, its test-map builder and its HTTP
seam (``ResponseRecorder``), and adds

* a data-driven fault catalogue per subject (``inputs/faults-<subject>.jsonl``; format in
  ``inputs/FAULT-CATALOG-SPEC.md``),
* a generic, stateful response-fault engine with seven shape-preserving operators,
* per-version *fault roots*: a directory that mimics the repository root (symlinked ``src``,
  ``deploy``, ``contracts``, ``.venv``, ``fixtures``) and carries one modified subject adapter whose
  ``docker_single`` block bind-mounts the patched source file read-only over the original path.
  The frozen suite runtime expands ``${UISEMTEST_REPO_ROOT}`` from the environment, so pointing it
  at a fault root makes the supervise/reset subprocesses start the faulted container; the image,
  the reset scripts and the recorded inputs are unchanged.

Roots (environment): ``UISEMTEST_RQ2_LEGACY`` = ``<root>/inputs`` (test map, normal qualification,
catalogues, source versions) and ``UISEMTEST_RQ2_ROOT`` = ``<root>/suite`` (registration, runs,
outcomes, summaries).  Default root: ``eval/ui_semantics/rq2-subjects-20260921``.

Commands (``--subject`` is mandatory except for ``summarize`` which accepts it optionally):
  test-map   register every retained test of the subject's final suite (no outcome consulted)
  prepare    build the fault roots (normal + every source fault) and validate their docker argv
  normal     execute every registered test once on the normal version; derive qualification
  register   pair response faults with qualified tests by matching normal reads (frozen before execution)
  responses  execute the response faults          sources  execute the source faults
  summarize  per-subject report in the Table III layout (report-<subject>.md, summary-<subject>.json)
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = REPO / "eval/ui_semantics/rq2-subjects-20260921"
os.environ.setdefault("UISEMTEST_RQ2_LEGACY", str(DEFAULT_ROOT / "inputs"))
os.environ.setdefault("UISEMTEST_RQ2_ROOT", str(DEFAULT_ROOT / "suite"))
sys.path.insert(0, str(REPO / "src"))

from ui_semantics import rq2_evaluation as base  # noqa: E402
from ui_semantics.rq2_evaluation import (  # noqa: E402
    ResponseRecorder, append, build_test_map, fault_summary, latest_outcomes, lines, normal_evidence_dir,
    object_paths, project_outcome, query, read, registration_events, require_live, route, route_matches, save,
    successful,
)
from ui_semantics.pytest_export import FrozenSuitePytestRuntime  # noqa: E402

LEGACY = base.LEGACY
ROOT = base.ROOT

SUBJECTS: dict[str, dict[str, Any]] = {
    "umami": {
        "adapter": "umami_current_local.json",
        "output_env": "UISEMTEST_UMAMI_OUTPUT_ROOT",
        "runtime_env": None,
        "run_roots": ["eval/ui_semantics/umami-20260921/umami/full-01"],
        "export_roots": ["eval/ui_semantics/umami-20260921/umami/pytest-export-final"],
    },
    "paperless": {
        "adapter": "paperless_current_local.json",
        "output_env": "UISEMTEST_PAPERLESS_OUTPUT_ROOT",
        "runtime_env": None,
        "run_roots": ["eval/ui_semantics/paperless-20260921/paperless/m11fix-03",
                      "eval/ui_semantics/paperless-20260921/paperless/full-01"],
        "export_roots": ["eval/ui_semantics/paperless-20260921/paperless/pytest-export-final"],
    },
    "ghost": {
        "adapter": "ghost_current_local.json",
        "output_env": "UISEMTEST_GHOST_OUTPUT_ROOT",
        "runtime_env": "UISEMTEST_GHOST_RUNTIME_ROOT",
        "run_roots": ["eval/ui_semantics/ghost-20260921/ghost/full-01"],
        "export_roots": ["eval/ui_semantics/ghost-20260921/ghost/pytest-export-final"],
    },
}

SITECUSTOMIZE = '''# Temporary hook (docs/RUN-NOTES.md §3): the reset
# subprocess of docker_single_local may start outside the repository .venv on macOS; make the venv's
# site-packages importable there.  Interpreters already inside the venv are unaffected.
import os, sys
_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
_SITE = os.path.join(_VENV, "lib", "python3.12", "site-packages")
if os.path.realpath(sys.prefix) != os.path.realpath(_VENV) and os.path.isdir(_SITE) and _SITE not in sys.path:
    sys.path.append(_SITE)
'''


# ---------------------------------------------------------------------------
# catalogue
# ---------------------------------------------------------------------------


def catalogue(subject: str) -> list[dict[str, Any]]:
    rows = lines(LEGACY / f"faults-{subject}.jsonl")
    if not rows:
        raise ValueError(f"no fault catalogue for {subject}: {LEGACY / f'faults-{subject}.jsonl'}")
    seen = set()
    for row in rows:
        if row.get("subject") != subject or row.get("kind") not in {"source", "response"}:
            raise ValueError(f"malformed catalogue row: {row.get('fault_id')}")
        if row["fault_id"] in seen:
            raise ValueError(f"duplicate fault id {row['fault_id']}")
        seen.add(row["fault_id"])
    return [row for row in rows if row.get("status", "included") == "included"]


def source_faults(subject: str) -> list[dict[str, Any]]:
    return [row for row in catalogue(subject) if row["kind"] == "source"]


def response_faults(subject: str) -> list[dict[str, Any]]:
    return [row for row in catalogue(subject) if row["kind"] == "response"]


def _fullmatch(pattern: str, value: str) -> bool:
    return bool(re.fullmatch(pattern, value.rstrip("/") or "/")) or bool(re.fullmatch(pattern, value))


def reads_match(definition: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    method = str(event.get("method") or "")
    path = route(event)
    return any(re.fullmatch(m, method) is not None and _fullmatch(p, path) for m, p in definition["reads"])


def write_match(write: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    return (str(event.get("method") or "").upper() == str(write["method"]).upper()
            and _fullmatch(str(write["path"]), route(event)))


def impossible_trigger(definition: Mapping[str, Any], events: list[Mapping[str, Any]]) -> str | None:
    """Exclude only absent structural prerequisites in complete normal plans (as the frozen evaluator does)."""
    writes = definition.get("writes") or []
    if writes and not any(write_match(w, e) for w in writes for e in events):
        return "complete_normal_plan_has_no_required_business_write"
    keys = definition.get("required_query_keys") or []
    if keys:
        matched = [e for e in events if reads_match(definition, e)]
        if matched and all(not set(keys) <= query(e).keys() and "$route_s_redacted" not in query(e) for e in matched):
            return "all_normal_reads_lack_required_filter_keys"
    return None


# ---------------------------------------------------------------------------
# generic response-fault engine
# ---------------------------------------------------------------------------


_PATH_TOKEN = re.compile(r"\.([A-Za-z0-9_-]+)|\[(\d+)\]")


def path_tokens(path: str) -> list[Any]:
    text = str(path).strip()
    if not text.startswith("$"):
        raise ValueError(f"JSON path must start with $: {path}")
    tokens: list[Any] = []
    for match in _PATH_TOKEN.finditer(text[1:]):
        tokens.append(int(match.group(2)) if match.group(2) is not None else match.group(1))
    return tokens


def get_path(body: Any, path: str) -> Any:
    value = body
    for token in path_tokens(path):
        value = value[token]
    return value


def _id(value: Any) -> str:
    return str(value)


class GenericResponseFault:
    """One fixed, shape-preserving API behaviour; raw business history scoped to real resets."""

    def __init__(self, definition: Mapping[str, Any]):
        self.definition = dict(definition)
        self.fid = definition["fault_id"]
        self.operator = definition["operator"]
        self.target = dict(definition.get("target") or {})
        self.writes = list(definition.get("writes") or [])
        self.epoch: Any = None
        self.history: list[dict[str, Any]] = []
        self.created: dict[str, int] = {}
        self.updated: dict[str, int] = {}
        self.deleted: dict[str, int] = {}
        self.activations = 0
        self.changed_responses = 0
        self.substate_counts: dict[str, int] = {name: 0 for name in definition.get("substates", [])}
        self.misses: dict[str, int] = {}

    # -- bookkeeping ---------------------------------------------------------
    def _write_id(self, write: Mapping[str, Any], event: Mapping[str, Any], body: Any) -> str | None:
        source = write.get("id_from", "path" if write.get("role") != "create" else "response")
        if write.get("id_path"):
            try:
                return _id(get_path(body, write["id_path"]))
            except (KeyError, IndexError, TypeError, ValueError):
                return None
        if source.startswith("query:"):
            value = query(event).get(source.split(":", 1)[1])
            return _id(value) if value not in (None, "") else None
        if source == "path":
            segments = [s for s in route(event).split("/") if s]
            return segments[-1] if segments else None
        return None

    def _classify_write(self, event: Mapping[str, Any], body: Any) -> None:
        if not successful(event):
            return
        for write in self.writes:
            if not write_match(write, event):
                continue
            identifier = self._write_id(write, event, body)
            if identifier is None:
                self.misses["write_without_identifier"] = self.misses.get("write_without_identifier", 0) + 1
                continue
            role = write.get("role", "update")
            table = {"create": self.created, "update": self.updated, "delete": self.deleted}[role]
            table[identifier] = len(self.history)

    def _last_observed(self, id_field: str, identifier: str, before: int | None = None) -> dict[str, Any] | None:
        events = self.history if before is None else self.history[:before]
        for event in reversed(events):
            for _, obj in object_paths(event.get("body")):
                if id_field in obj and _id(obj[id_field]) == identifier:
                    return obj
        return None

    def _scoped_objects(self, body: Any, field: str):
        scope = self.target.get("scope", "all")
        id_field = self.target.get("id_field", "id")
        for path, obj in object_paths(body):
            if field not in obj:
                continue
            if scope == "all":
                yield path, obj
            elif scope == "created" and id_field in obj and _id(obj[id_field]) in self.created:
                yield path, obj
            elif scope == "updated" and id_field in obj and _id(obj[id_field]) in self.updated:
                yield path, obj

    # -- transformation --------------------------------------------------------
    def transform(self, event: Mapping[str, Any], body: Any) -> tuple[Any, list[str]]:
        epoch = event.get("reset_epoch")
        if epoch != self.epoch:
            self.history, self.created, self.updated, self.deleted = [], {}, {}, {}
            self.epoch = epoch
        self._classify_write(event, body)
        changed = copy.deepcopy(body)
        activated: list[str] = []
        if successful(event) and body is not None and reads_match(self.definition, event):
            try:
                self._apply(event, changed, activated)
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
                reason = str(error) if isinstance(error, ValueError) else type(error).__name__
                self.misses[reason] = self.misses.get(reason, 0) + 1
        # raw originals only; an injected value never feeds back into its source
        self.history.append({**event, "body": copy.deepcopy(body)})
        for name in set(activated):
            self.substate_counts[name] = self.substate_counts.get(name, 0) + 1
        if activated:
            self.activations += 1
        if changed != body:
            self.changed_responses += 1
        return changed, sorted(set(activated))

    def _query_gate(self, event: Mapping[str, Any]) -> bool:
        key = self.target.get("when_query_key")
        if not key:
            return True
        q = query(event)
        if key not in q:
            return False
        value = self.target.get("when_query_value")
        return value is None or str(q.get(key)) == str(value)

    def _apply(self, event: Mapping[str, Any], body: Any, active: list[str]) -> None:
        op, target = self.operator, self.target
        field = target.get("field")
        if not self._query_gate(event):
            raise ValueError("read_lacks_gating_query_key")
        if op == "omit_first_member":
            id_field = target.get("id_field", "id")
            array = get_path(body, target.get("list_path", "$"))
            if not isinstance(array, list):
                raise ValueError("list_path_is_not_an_array")
            members = [(i, m) for i, m in enumerate(array) if isinstance(m, dict) and id_field in m]
            if not members:
                raise ValueError("no_member_with_identity")
            array.pop(min(members, key=lambda im: str(im[1][id_field]))[0])
            active.append(target.get("substate", "omit_first"))
        elif op == "drop_last_member":
            array = get_path(body, target.get("list_path", "$"))
            if not isinstance(array, list):
                raise ValueError("list_path_is_not_an_array")
            if not array:
                raise ValueError("empty_list")
            array.pop()
            active.append(target.get("substate", "drop_last"))
        elif op == "rewrite_string":
            for _, obj in self._scoped_objects(body, field):
                if isinstance(obj[field], str):
                    obj[field] = obj[field] + " [RQ2]"
                    active.append(target.get("substate", "rewrite"))
        elif op == "add_one_number":
            for _, obj in self._scoped_objects(body, field):
                if type(obj[field]) in {int, Decimal}:
                    obj[field] = obj[field] + 1
                    active.append(target.get("substate", "add_one"))
        elif op == "flip_boolean":
            for _, obj in self._scoped_objects(body, field):
                if type(obj[field]) is bool:
                    obj[field] = not obj[field]
                    active.append(target.get("substate", "flip"))
        elif op == "old_value_after_update":
            id_field = target.get("id_field", "id")
            for _, obj in object_paths(body):
                if field not in obj or id_field not in obj:
                    continue
                identifier = _id(obj[id_field])
                if identifier not in self.updated:
                    continue
                prior = self._last_observed(id_field, identifier, before=self.updated[identifier])
                if prior is None or field not in prior:
                    raise ValueError("no_observed_prior_value")
                if type(prior[field]) is type(obj[field]) and prior[field] != obj[field]:
                    obj[field] = copy.deepcopy(prior[field])
                    active.append(target.get("substate", "update"))
        elif op == "omit_created_member":
            id_field = target.get("id_field", "id")
            array = get_path(body, target.get("list_path", "$"))
            if not isinstance(array, list):
                raise ValueError("list_path_is_not_an_array")
            victims = [i for i, member in enumerate(array)
                       if isinstance(member, dict) and id_field in member and _id(member[id_field]) in self.created]
            for index in reversed(victims):
                array.pop(index)
                active.append(target.get("substate", "create"))
        elif op == "reinsert_deleted_member":
            id_field = target.get("id_field", "id")
            array = get_path(body, target.get("list_path", "$"))
            if not isinstance(array, list):
                raise ValueError("list_path_is_not_an_array")
            present = {_id(m[id_field]) for m in array if isinstance(m, dict) and id_field in m}
            for identifier, index in sorted(self.deleted.items(), key=lambda kv: kv[1]):
                if identifier in present:
                    continue
                prior = self._last_observed(id_field, identifier, before=index)
                if prior is None:
                    continue
                array.append(copy.deepcopy(prior))
                active.append(target.get("substate", "delete"))
        elif op == "stale_count":
            key = (event.get("actor_id"), event.get("method"), route(event),
                   tuple(sorted((k, str(v)) for k, v in query(event).items())))
            previous = None
            for old in reversed(self.history):
                if (old.get("actor_id"), old.get("method"), route(old),
                        tuple(sorted((k, str(v)) for k, v in query(old).items()))) == key and successful(old):
                    previous = old
                    break
            if previous is None:
                raise ValueError("no_previous_read_of_same_route")
            prior_values = [obj[field] for _, obj in object_paths(previous.get("body")) if field in obj]
            current = [(path, obj) for path, obj in object_paths(body) if field in obj]
            if not prior_values or not current:
                raise ValueError("count_field_absent")
            path, obj = current[0]
            if type(prior_values[0]) in {int, Decimal} and type(obj[field]) in {int, Decimal} and prior_values[0] != obj[field]:
                obj[field] = prior_values[0]
                active.append(target.get("substate", "count"))
        else:
            raise ValueError(f"unsupported_operator:{op}")


class GenericResponseRecorder(ResponseRecorder):
    def __init__(self, path: Path, definition: Mapping[str, Any] | None = None):
        super().__init__(path, None)
        self.fault = GenericResponseFault(definition) if definition else None


# ---------------------------------------------------------------------------
# fault roots (one mimicked repository root per source version)
# ---------------------------------------------------------------------------


def fault_root(subject: str, fault_id: str) -> Path:
    return ROOT / "fault-roots" / subject / fault_id


def _symlink(target: Path, link: Path) -> None:
    if link.is_symlink() or link.exists():
        return
    link.symlink_to(target, target_is_directory=target.is_dir())


def build_fault_root(subject: str, fault: Mapping[str, Any] | None) -> Path:
    fid = "normal" if fault is None else fault["fault_id"]
    root = fault_root(subject, fid)
    root.mkdir(parents=True, exist_ok=True)
    for name in ("src", "deploy", "contracts", ".venv", "scripts"):
        _symlink(REPO / name, root / name)
    (root / "fixtures").mkdir(exist_ok=True)
    for entry in (REPO / "fixtures").iterdir():
        if entry.name != "adapters":
            _symlink(entry, root / "fixtures" / entry.name)
    (root / "fixtures/adapters").mkdir(exist_ok=True)
    adapter_name = SUBJECTS[subject]["adapter"]
    for entry in (REPO / "fixtures/adapters").iterdir():
        if entry.name != adapter_name:
            _symlink(entry, root / "fixtures/adapters" / entry.name)
    adapter = json.loads((REPO / "fixtures/adapters" / adapter_name).read_text())
    if fault is not None:
        patch = fault["patch"]
        patched = (REPO / patch["patched_file"]).resolve(strict=True)
        adapter["docker_single"]["volumes"].append({
            "kind": "bind", "source": str(patched), "container_path": patch["container_path"],
            "read_only": True, "reset_scope": "persistent",
        })
        # the adapter schema forbids extra keys; provenance goes to source-versions-<subject>.jsonl
    (root / "fixtures/adapters" / adapter_name).write_text(json.dumps(adapter, ensure_ascii=False, indent=2) + "\n")
    (root / "sitecustomize.py").write_text(SITECUSTOMIZE)
    return root


def configure_env(subject: str, fault_id: str) -> dict[str, str]:
    """Point the frozen runtime at the fault root and give this version its own container identity."""
    root = fault_root(subject, fault_id)
    if not (root / "fixtures/adapters" / SUBJECTS[subject]["adapter"]).is_file():
        raise ValueError(f"fault root is not prepared: {root}")
    values = {"UISEMTEST_REPO_ROOT": str(root)}
    if subject == "umami":
        # Umami's data tier (deploy/umami/db_up.sh) is keyed by the same instance key as the application
        # container and is materialized outside the adapter; keep the repository .env instance key so the
        # existing database container and its golden template are reused (Umami has no source faults).
        if not os.environ.get(SUBJECTS[subject]["output_env"]):
            raise ValueError("UISEMTEST_UMAMI_OUTPUT_ROOT must come from the repository .env")
    else:
        values[SUBJECTS[subject]["output_env"]] = str(ROOT / "runs" / subject / "lifecycle" / fault_id)
    if SUBJECTS[subject]["runtime_env"]:
        values[SUBJECTS[subject]["runtime_env"]] = str(ROOT / "runtime" / subject / fault_id)
    for key, value in values.items():
        os.environ[key] = value
        if key != "UISEMTEST_REPO_ROOT":
            Path(value).mkdir(parents=True, exist_ok=True)
    return values


def wait_for_seed(subject: str, source_fault: str = "normal", *, timeout_seconds: int = 1500) -> float:
    """Block until the freshly started target has finished seeding its golden state.

    The frozen suite runtime returns as soon as the health probes pass, but ``docker_single_local``
    seeds the golden state after readiness; a reset issued before the seed finished fails (Paperless,
    Ghost) or would drop the database under the seed (Umami).  The main line never met this race
    because its first reset comes minutes after the start; RQ2 replays start at once.
    """
    import subprocess
    from subject_adapters.docker_single_local import load_spec

    spec = load_spec(fault_root(subject, source_fault) / "fixtures/adapters" / SUBJECTS[subject]["adapter"], validate=False)

    def seeded() -> bool:
        if subject == "ghost":
            return (Path(os.environ["UISEMTEST_GHOST_RUNTIME_ROOT"]) / "golden/.uisemtest-ghost-golden").is_file()
        if subject == "paperless":
            probe = subprocess.run(["docker", "exec", spec.container_name, "test", "-f", "/usr/src/paperless/golden/.seeded"],
                                   capture_output=True, timeout=60)
            return probe.returncode == 0
        if subject == "umami":
            probe = subprocess.run(["docker", "exec", f"uisemtest-umami-db-{spec.instance_key}", "psql", "-U", "umami", "-d", "postgres",
                                    "-tAc", "select 1 from pg_database where datname='umami_golden'"], capture_output=True, timeout=60)
            return probe.returncode == 0 and probe.stdout.strip() == b"1"
        raise ValueError(subject)

    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        if seeded():
            return time.monotonic() - started
        time.sleep(5)
    raise RuntimeError(f"{subject}: golden state not seeded within {timeout_seconds}s")


def prepare_subject(subject: str, *, append_mode: bool = False) -> None:
    from subject_adapters.docker_single_local import load_spec, run_argv

    target = LEGACY / f"source-versions-{subject}.jsonl"
    if target.exists() and not append_mode:
        raise ValueError(f"source versions already prepared: {target}")
    prepared = {v["fault_id"] for v in lines(target)} if append_mode else set()
    rows = []
    for fault in ([None] if not append_mode else []) + [f for f in source_faults(subject) if f["fault_id"] not in prepared]:
        fid = "normal" if fault is None else fault["fault_id"]
        root = build_fault_root(subject, fault)
        saved = {k: os.environ.get(k) for k in ("UISEMTEST_REPO_ROOT", SUBJECTS[subject]["output_env"], SUBJECTS[subject]["runtime_env"] or "")}
        try:
            configure_env(subject, fid)
            spec = load_spec(root / "fixtures/adapters" / SUBJECTS[subject]["adapter"], validate=True)
            argv = run_argv(spec)
        finally:
            for key, value in saved.items():
                if not key:
                    continue
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        mounted = fault is None or any(f'{fault["patch"]["container_path"]}:ro' in item for item in argv)
        if not mounted:
            raise ValueError(f"patched file is not mounted for {fid}")
        rows.append({"fault_id": fid, "subject": subject, "status": "included", "fault_root": str(root),
                     "container_name": spec.container_name, "image": spec.image_reference,
                     "docker_run_argv": argv,
                     "patch": None if fault is None else fault["patch"],
                     "routes": None if fault is None else fault["routes"],
                     "prepared_at": dt.datetime.now(dt.UTC).isoformat()})
    for row in rows:
        append(target, row)
    print(json.dumps({"subject": subject, "versions": [r["fault_id"] for r in rows],
                      "containers": {r["fault_id"]: r["container_name"] for r in rows}}), flush=True)


# ---------------------------------------------------------------------------
# execution (mirrors rq2_evaluation.execute_pairs with subject-agnostic configuration)
# ---------------------------------------------------------------------------


def test_rows(subject: str) -> dict[str, dict[str, Any]]:
    rows = {r["test_key"]: r for r in lines(LEGACY / "test-map.jsonl") if r["subject"] == subject}
    if not rows:
        raise ValueError(f"test map has no tests for {subject}")
    return rows


def normal_rows(subject: str) -> dict[str, dict[str, Any]]:
    return {r["test_key"]: r for r in lines(LEGACY / f"normal-{subject}.jsonl")}


def execute_pairs(subject: str, pairs: list[dict[str, Any]], *, kind: str,
                  definition: Mapping[str, Any] | None = None, source_fault: str = "normal",
                  retry_errors: bool = False, limit: int | None = None) -> None:
    require_live()
    configure_env(subject, source_fault)
    tests = test_rows(subject)
    output = ROOT / f"outcomes-{kind}-{subject}.jsonl"
    latest = {(r["fault_id"], r["test_key"]): r for r in lines(output)}
    pending = [p for p in pairs if (p["fault_id"], p["test_key"]) not in latest
               or (retry_errors and latest[p["fault_id"], p["test_key"]].get("error"))]
    if limit is not None:
        pending = pending[:limit]
    owner = runtime = recorder = None
    current_source = None

    def transform(meta, result):
        if recorder is None:
            raise RuntimeError("response outside a registered test execution")
        return recorder(meta, result)

    try:
        for index, pair in enumerate(pending):
            row = tests[pair["test_key"]]
            if current_source != row["source_run"]:
                if runtime is not None and runtime is not owner:
                    runtime.close()
                base_dir = ROOT / "runs" / subject / kind / "runtime" / source_fault / row["case_id"]
                attempt = 1
                while (base_dir / f"{attempt:04}").exists():
                    attempt += 1
                runtime = FrozenSuitePytestRuntime(Path(row["source_run"]), base_dir / f"{attempt:04}")
                runtime.open(external_lifecycle=owner is not None, response_transform=transform)
                if owner is None:
                    owner = runtime
                    waited = wait_for_seed(subject, source_fault)
                    print(json.dumps({"subject": subject, "kind": kind, "source_fault": source_fault,
                                      "seed_wait_seconds": round(waited, 1)}), flush=True)
                current_source = row["source_run"]
            path = ROOT / "runs" / subject / kind / pair["fault_id"] / row["case_id"] / row["test_id"]
            attempt = 1
            while (path / f"attempt-{attempt:03}").exists():
                attempt += 1
            path = path / f"attempt-{attempt:03}"
            path.mkdir(parents=True, exist_ok=False)
            recorder = GenericResponseRecorder(path / "http.jsonl", definition)
            started = time.monotonic()
            result = error = None
            try:
                result = runtime.run_retained_test(row["test_id"], execution_id=f'{pair["fault_id"]}-{attempt}')
            except Exception as exc:  # noqa: BLE001 - recorded as an engineering error of this pair
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started
            save(path / "result.json", {"result": result, "error": error, "elapsed_seconds": elapsed})
            projection = project_outcome(result, row["layer"], recorder.events,
                                         runtime._tests[row["test_id"]]["assertions"], error=error)
            record = {**pair, "kind": kind, "subject": subject, "layer": row["layer"],
                      "attempt": attempt, "retry_reason": "engineering error or interrupted directory" if attempt > 1 else None,
                      "elapsed_seconds": elapsed, "evidence_ref": str(path.relative_to(ROOT)), **projection}
            if recorder.fault:
                fault = recorder.fault
                record.update(activation_count=fault.activations, changed_response_count=fault.changed_responses,
                              activation_substates=fault.substate_counts, mutation_misses=fault.misses,
                              activation_status="activated" if fault.changed_responses else "no_activation")
                if not fault.changed_responses and any(record[key] == "detected" for key in ("O0", "O1", "O2")):
                    record.update(O0="unknown", O1="unknown", O2="unknown", B="unknown", business_direct_alarm=False,
                                  common_observation=False, attribution_reason="failure_without_response_change")
            append(output, record)
            print(json.dumps({"subject": subject, "kind": kind, "fault": pair["fault_id"],
                              "completed": index + 1, "planned": len(pending), "test": row["test_key"],
                              "O2": record["O2"], "activation": record.get("activation_count"),
                              "seconds": round(elapsed, 2), "error": error}), flush=True)
            if (kind == "response" and not recorder.hit
                    and (error or (result or {}).get("final_status") != "normal_pass")):
                raise RuntimeError("normal-version execution failed before any response change; preserved attempt, stop dispatch for engineering diagnosis")
    finally:
        if runtime is not None and runtime is not owner:
            runtime.close()
        if owner is not None:
            owner.close()


def run_normal(subject: str, *, limit: int | None = None, retry_errors: bool = False) -> None:
    mapped = list(test_rows(subject).values())
    pairs = [{"fault_id": "normal", "test_key": r["test_key"], "subject": subject} for r in mapped]
    execute_pairs(subject, pairs, kind="normal", retry_errors=retry_errors, limit=limit)
    records = latest_outcomes(lines(ROOT / f"outcomes-normal-{subject}.jsonl"))
    rows = []
    for record in records:
        saved = read(ROOT / record["evidence_ref"] / "result.json")
        status = (saved.get("result") or {}).get("final_status")
        row = dict(record)
        row.update(qualified=record.get("error") is None and bool(record.get("mechanical_complete")) and status == "normal_pass",
                   normal_final_status=status, evidence_root=str(ROOT),
                   qualification_basis="last attempt: error-free, mechanically complete, final_status normal_pass on the isolated normal version")
        rows.append(row)
    target = LEGACY / f"normal-{subject}.jsonl"
    temporary = target.with_suffix(".jsonl.tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    os.replace(temporary, target)
    print(json.dumps({"subject": subject, "tests": len(mapped), "executed": len(rows),
                      "qualified": sum(r["qualified"] for r in rows),
                      "not_qualified": [r["test_key"] for r in rows if not r["qualified"]]}), flush=True)


def register(subject: str, *, append_mode: bool = False) -> None:
    marker = ROOT / f"selection-{subject}.json"
    if marker.exists() and not append_mode:
        raise ValueError(f"registration of {subject} is already frozen: {marker}")
    if append_mode:
        marker = ROOT / f"selection-{subject}-append-{dt.datetime.now(dt.UTC).strftime('%Y%m%d%H%M%S')}.json"
    normal = normal_rows(subject)
    tests = list(test_rows(subject).values())
    if any(row["test_key"] not in normal for row in tests):
        raise ValueError("normal qualification is incomplete")
    facts = {}
    for row in tests:
        if normal[row["test_key"]].get("qualified"):
            facts[row["test_key"]] = registration_events(
                row, lines(normal_evidence_dir(normal[row["test_key"]]["evidence_ref"],
                                               normal[row["test_key"]].get("evidence_root")) / "http.jsonl"))
    registered = {d["fault_id"] for d in lines(ROOT / "response-faults.jsonl") if d["subject"] == subject}
    catalog = [copy.deepcopy(d) for d in response_faults(subject) if not append_mode or d["fault_id"] not in registered]
    if append_mode and not catalog:
        raise ValueError("no unregistered response faults to append")
    for definition in catalog:
        paired, skipped, read_pairs = [], [], 0
        for row in tests:
            if row["test_key"] not in facts:
                continue
            matched = [e for e in facts[row["test_key"]] if reads_match(definition, e)]
            if not matched:
                continue
            read_pairs += 1
            skip = impossible_trigger(definition, facts[row["test_key"]])
            if skip:
                skipped.append({"test_key": row["test_key"], "skip_basis": skip})
                continue
            pair = {"fault_id": definition["fault_id"], "test_key": row["test_key"], "subject": subject,
                    "basis": "all qualified tests with matching actual normal API reads",
                    "normal_evidence_ref": normal[row["test_key"]]["evidence_ref"],
                    "normal_evidence_root": normal[row["test_key"]].get("evidence_root"),
                    "matched_request_refs": sorted({e["request_ref"] for e in matched})}
            paired.append(pair)
            append(ROOT / "test-fault-map.jsonl", pair)
        definition["paired_tests"] = len(paired)
        definition["read_route_pairs_before_trigger_filter"] = read_pairs
        definition["structurally_impossible_tests"] = skipped
        definition["estimated_seconds_from_normal"] = sum(normal[p["test_key"]]["elapsed_seconds"] for p in paired)
        definition["substate_status"] = {name: "pending_activation_evaluation" for name in definition.get("substates", [])}
        definition["definition_ref"] = str(LEGACY / "FAULT-CATALOG-SPEC.md")
        append(ROOT / "response-faults.jsonl", definition)
    source_counts = {f["fault_id"]: sum(row["test_key"] in facts and route_matches(f["routes"], row["request_coverage"]) for row in tests)
                     for f in source_faults(subject)}
    save(marker, {
        "registered_at": dt.datetime.now(dt.UTC).isoformat(), "subject": subject, "appended": append_mode,
        "fault_definitions": catalog, "source_pairs": source_counts,
        "test_selection": "qualified normal_pass on the isolated normal version; API-only read coverage, trigger uncertainty retained; RQ1 labels joined at reporting time",
        "excluded_tests": [{"test_key": row["test_key"], "reason": "original_qualification_not_passed"} for row in tests if row["test_key"] not in facts],
        "qualified_tests": len(facts),
        "no_response_location_or_test_id_in_fault_identity": True,
    })
    print(json.dumps({"subject": subject, "qualified_tests": len(facts),
                      "response_pairs": {d["fault_id"]: d["paired_tests"] for d in catalog},
                      "source_pairs": source_counts}), flush=True)


def run_responses(subject: str, *, fault_id: str | None = None, limit: int | None = None, retry_errors: bool = False) -> None:
    catalog = [d for d in lines(ROOT / "response-faults.jsonl") if d["subject"] == subject
               and (fault_id is None or d["fault_id"] == fault_id)]
    if not catalog:
        raise ValueError("no registered response faults for the subject (run register first)")
    mapped = lines(ROOT / "test-fault-map.jsonl")
    for definition in catalog:
        pairs = [p for p in mapped if p["fault_id"] == definition["fault_id"]]
        execute_pairs(subject, pairs, kind="response", definition=definition, retry_errors=retry_errors, limit=limit)


def source_pairs(subject: str, fault: Mapping[str, Any]) -> list[dict[str, Any]]:
    normal = normal_rows(subject)
    return [{"fault_id": fault["fault_id"], "test_key": r["test_key"], "subject": subject}
            for r in test_rows(subject).values()
            if normal.get(r["test_key"], {}).get("qualified") and route_matches(fault["routes"], r["request_coverage"])]


def run_sources(subject: str, *, fault_id: str | None = None, limit: int | None = None, retry_errors: bool = False) -> None:
    versions = [v for v in lines(LEGACY / f"source-versions-{subject}.jsonl")
                if v["fault_id"] != "normal" and v["status"] == "included" and (fault_id is None or v["fault_id"] == fault_id)]
    if not versions:
        if not source_faults(subject):
            print(json.dumps({"subject": subject, "kind": "source", "note": "the catalogue has no source faults for this subject"}), flush=True)
            return
        raise ValueError("no prepared source versions for the subject (run prepare first)")
    for version in sorted(versions, key=lambda v: v["fault_id"]):
        fault = next(f for f in source_faults(subject) if f["fault_id"] == version["fault_id"])
        execute_pairs(subject, source_pairs(subject, fault), kind="source", source_fault=fault["fault_id"],
                      retry_errors=retry_errors, limit=limit)


# ---------------------------------------------------------------------------
# summary (Table III layout)
# ---------------------------------------------------------------------------


def summarize(subject: str) -> None:
    response_defs = [d for d in lines(ROOT / "response-faults.jsonl") if d["subject"] == subject]
    response_records = latest_outcomes(lines(ROOT / f"outcomes-response-{subject}.jsonl"))
    response = [fault_summary(d, response_records, d["paired_tests"]) for d in response_defs]
    source_records = latest_outcomes(lines(ROOT / f"outcomes-source-{subject}.jsonl"))
    source = []
    for fault in source_faults(subject):
        planned = len(source_pairs(subject, fault)) if (LEGACY / f"normal-{subject}.jsonl").exists() else 0
        source.append(fault_summary({"fault_id": fault["fault_id"], "subject": subject, "kind": "source",
                                     "module": fault.get("module"), "business_rule": fault.get("business_rule")},
                                    source_records, planned))
    summary = {"subject": subject, "response": response, "source": source,
               "updated_at": dt.datetime.now(dt.UTC).isoformat()}
    save(ROOT / f"summary-{subject}.json", summary)
    table = [f"# RQ2 results for {subject} (reduced fault set, added subject)", "",
             "|Kind|Subject|Faults|O0 detected|O1 detected|O2 detected|Business-only|O2 undetected|O2 unknown|No test|",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for kind, rows in (("response", response), ("source", source)):
        values = [len(rows)] + [sum(r[k] == "detected" for r in rows) for k in ("O0", "O1", "O2")]
        values += [sum(r["business_only"] for r in rows)] + [sum(r["O2"] == state for r in rows)
                                                             for state in ("completed_not_detected", "unknown", "no_eligible_tests")]
        table.append("|" + "|".join([kind, subject] + [str(v) for v in values]) + "|")
    table += ["", "Incomplete pairs stay unknown; non-activated faults and faults without tests remain in the catalogue denominator; "
              "O0 is the generic checks plus application 5xx; a response fault detected without any changed response is rewritten to unknown.", "",
              "## Per-fault results", "",
              "|Kind|Fault|Module|Completed/planned tests|Changed responses|O0|O1|O2|B vs O1|", "|---|---|---|---:|---:|---|---|---|---|"]
    for kind, rows in (("response", response), ("source", source)):
        for row in rows:
            table.append("|" + "|".join(str(v) for v in (kind, row["fault_id"], row.get("module", "-"),
                         f'{row["completed_tests"]}/{row["planned_tests"]}', row["changed_responses"] if kind == "response" else "—",
                         row["O0"], row["O1"], row["O2"], row["B_vs_O1"])) + "|")
    (ROOT / f"report-{subject}.md").write_text("\n".join(table) + "\n")
    print(json.dumps({"subject": subject, "response_faults": len(response), "source_faults": len(source),
                      "O2_detected": sum(r["O2"] == "detected" for r in response + source),
                      "business_only": sum(r["business_only"] for r in response + source)}), flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["test-map", "prepare", "normal", "register", "responses", "sources", "summarize"])
    parser.add_argument("--subject", choices=sorted(SUBJECTS), required=True)
    parser.add_argument("--fault")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--append", action="store_true", help="prepare/register only faults added to the catalogue after the first registration")
    args = parser.parse_args()
    if args.command in {"normal", "responses", "sources"}:
        print(json.dumps({"runner_pid": os.getpid(), "command": args.command, "subject": args.subject,
                          "started_at": dt.datetime.now(dt.UTC).isoformat()}), flush=True)
    config = SUBJECTS[args.subject]
    if args.command == "test-map":
        registry = LEGACY / f"faults-{args.subject}.jsonl"
        if not registry.exists():
            registry = LEGACY / "empty-registry.jsonl"
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.touch()
        build_test_map(subject=args.subject, run_roots=[REPO / p for p in config["run_roots"]],
                       export_roots=[REPO / p for p in config["export_roots"]], fault_registry=registry)
    elif args.command == "prepare":
        prepare_subject(args.subject, append_mode=args.append)
    elif args.command == "normal":
        run_normal(args.subject, limit=args.limit, retry_errors=args.retry_errors)
    elif args.command == "register":
        register(args.subject, append_mode=args.append)
    elif args.command == "responses":
        run_responses(args.subject, fault_id=args.fault, limit=args.limit, retry_errors=args.retry_errors)
    elif args.command == "sources":
        run_sources(args.subject, fault_id=args.fault, limit=args.limit, retry_errors=args.retry_errors)
    else:
        summarize(args.subject)


if __name__ == "__main__":
    main()
