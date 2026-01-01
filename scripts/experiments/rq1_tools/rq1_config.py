"""Shared configuration for the parameterised RQ1 evaluation tools (subject-agnostic).

The four scripts next to this module are parameterised copies of the frozen tools in
``eval/ui_semantics/deepseek-full-20260912/`` (which must not be modified).  They accept the
same environment variables as the frozen copies, plus a JSON configuration file and command
line flags, so that a run root whose subjects are not ``conduit``/``rwa`` can be evaluated.

Precedence (highest first): command line flag > environment variable > ``--config`` file >
built-in default.

Configuration keys (all paths are either absolute or relative to the repository root)::

  repo_root            repository root; default: auto-detected upwards from this file
  runs_root            parent of <subject>/<run>/cases/...   (env DEEPSEEK_RUNS_ROOT)
  audit_dir            audit directory read and written by the tools (env RQ1_AUDIT_DIR)
  export_name          pytest export directory name (env DEEPSEEK_EXPORT_NAME)
  export_glob          glob for the export catalogs under <runs_root>/<subject>/<export_name>
  runs                 run-name priority list; first run with a complete M14 union wins
                       (env DEEPSEEK_RUNS, comma separated)
  subjects             list of subject ids, or of objects
                       {"id", "runs"?, "export_name"?, "export_glob"?, "inventory"?}
                       (env RQ1_SUBJECTS, comma separated -> ids with the global defaults)
  scopes               goal list jsonl (env RQ1_SCOPES); may be absent for a new subject
  previous_round       {"enabled": bool, "audit_dir", "exports_root", "export_glob",
                        "subjects": [ids that have a previous round],
                        "group_note": str|null, "scopes_note": str|null}
                       ``enabled: false`` (or ``--no-previous-round``) switches the whole
                       calibration off; the summary then records "no previous round".
  queue_sample_seed    seed of the sampled-C-groups section of review-queue.md
  summary_generator_label   provenance path printed in the header line of summary.md
  helpers_module       path of review_refuted.py (checkpoints/pick/summarize_step)
  review               {"model", "prompt_version", "reviewer", "system_prompt_file"}
  targets              {"model", "reviewer", "system_prompt_file"}

Keys whose name starts with ``_`` are ignored, so a JSON config may carry comments.

Note on the shipped defaults: the frozen scripts default ``DEEPSEEK_RUNS`` to
``rerecord-01,m11fix-01``, but the frozen artefacts under
``docs/design/cpv-expansion/rq1-audit-deepseek/`` were produced with ``m11fix-02,m11fix-01``
(verified by byte-identical re-extraction, 2026-09-20).  The default here is kept identical to
the frozen scripts for compatibility; ``configs/conduit-rwa.json`` carries the run order that
actually reproduces the frozen numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULTS = {
    "runs_root": "eval/ui_semantics/deepseek-full-20260912",
    "audit_dir": "docs/design/cpv-expansion/rq1-audit-deepseek",
    "export_name": "pytest-export-final",
    "export_glob": "*/business_test_catalog.json",
    "runs": ["rerecord-01", "m11fix-01"],
    "subjects": ["conduit", "rwa"],
    "scopes": "docs/design/cpv-expansion/rq1-audit/scopes.jsonl",
    "queue_sample_seed": 20260912,
    "summary_generator_label": "scripts/experiments/rq1_tools/rq1_summarize_deepseek.py",
    "helpers_module": "eval/ui_semantics/deepseek-full-20260912/review_refuted.py",
    "inventory_template": "fixtures/recording_workflows/{subject}_modular/inventory.json",
    "protected_dirs": ["docs/design/cpv-expansion", "docs/paper", "eval"],
    "previous_round": {
        "enabled": True,
        "audit_dir": "docs/design/cpv-expansion/rq1-audit",
        "exports_root": "eval/ui_semantics/cpv-astra-qualification-20260906",
        "export_glob": "pytest-export-*/*/business_test_catalog.json",
        "subjects": ["conduit", "rwa"],
        "group_note": None,
        "scopes_note": None,
    },
    "review": {"model": "deepseek-flash", "prompt_version": None, "reviewer": None, "system_prompt_file": None},
    "targets": {"model": "deepseek-flash", "reviewer": None, "system_prompt_file": None},
}


class ConfigError(RuntimeError):
    """Raised for a configuration that cannot produce trustworthy numbers."""


def fail(message: str, code: int = 2) -> "NoReturn":  # noqa: F821
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr, flush=True)
    raise SystemExit(code)


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists() and (candidate / "src").is_dir():
            return candidate
    return start.parents[2] if len(start.parents) >= 3 else start


def _strip_comments(obj):
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_comments(v) for v in obj]
    return obj


def _csv(value):
    return [x.strip() for x in str(value).split(",") if x.strip()]


@dataclass
class Subject:
    id: str
    runs: tuple[str, ...]
    export_name: str
    export_glob: str
    inventory: Path

    def union(self, runs_root: Path, case: str) -> Path | None:
        """First run (in priority order) whose union holds a complete M14 suite."""
        for run in self.runs:
            u = runs_root / self.id / run / "cases" / case / "union"
            if (u / "M14/final_calibrated_suite.json").exists():
                return u
        return None

    def export_root(self, runs_root: Path) -> Path:
        return runs_root / self.id / self.export_name


@dataclass
class PreviousRound:
    enabled: bool
    audit_dir: Path
    exports_root: Path
    export_glob: str
    subjects: tuple[str, ...]
    group_note: str | None = None
    scopes_note: str | None = None

    def active_for(self, subject_ids) -> list[str]:
        """Subjects of this run that actually have a previous round to calibrate against."""
        if not self.enabled:
            return []
        return [s for s in subject_ids if s in self.subjects]


@dataclass
class Config:
    repo: Path
    runs_root: Path
    audit_dir: Path
    export_name: str
    subjects: list[Subject]
    scopes: Path
    queue_sample_seed: int
    summary_generator_label: str
    helpers_module: Path
    previous_round: PreviousRound
    review: dict = field(default_factory=dict)
    targets: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    allow_frozen_audit_dir: bool = False

    @property
    def subject_ids(self) -> list[str]:
        return [s.id for s in self.subjects]

    def subject(self, subject_id: str) -> Subject:
        for s in self.subjects:
            if s.id == subject_id:
                return s
        raise KeyError(subject_id)

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.repo))
        except ValueError:
            return str(path)

    def guard_audit_dir(self) -> None:
        """Refuse to write into the frozen result trees unless explicitly allowed.

        The parameterised tools default to the same audit directory as the frozen ones, so an
        unguarded run would overwrite the frozen artefacts under docs/design/cpv-expansion/.
        """
        if self.allow_frozen_audit_dir:
            return
        target = Path(self.audit_dir).resolve()
        for prefix in self.raw.get("protected_dirs") or []:
            root = (self.repo / prefix).resolve()
            if target == root or root in target.parents:
                fail(f"refusing to write into the frozen tree '{prefix}' (audit_dir={self.rel(target)}); "
                     "pass --audit-dir <temp dir> or --allow-frozen-audit-dir")

    def describe(self) -> dict:
        return {
            "repo": str(self.repo), "runs_root": self.rel(self.runs_root), "audit_dir": self.rel(self.audit_dir),
            "export_name": self.export_name,
            "subjects": [{"id": s.id, "runs": list(s.runs), "export_name": s.export_name,
                          "inventory": self.rel(s.inventory), "inventory_exists": s.inventory.exists()} for s in self.subjects],
            "scopes": self.rel(self.scopes), "scopes_exists": self.scopes.exists(),
            "previous_round": {"enabled": self.previous_round.enabled,
                               "subjects_with_previous_round": self.previous_round.active_for(self.subject_ids)},
        }


def add_common_args(ap: argparse.ArgumentParser) -> None:
    g = ap.add_argument_group("configuration (flag > environment > --config > default)")
    g.add_argument("--config", help="JSON configuration file (env RQ1_CONFIG)")
    g.add_argument("--repo", help="repository root (default: auto-detected)")
    g.add_argument("--subjects", help="comma separated subject ids (env RQ1_SUBJECTS)")
    g.add_argument("--runs-root", help="parent of <subject>/<run>/cases (env DEEPSEEK_RUNS_ROOT)")
    g.add_argument("--audit-dir", help="audit directory to read/write (env RQ1_AUDIT_DIR)")
    g.add_argument("--export-name", help="pytest export directory name (env DEEPSEEK_EXPORT_NAME)")
    g.add_argument("--runs", help="comma separated run priority for every subject (env DEEPSEEK_RUNS)")
    g.add_argument("--scopes", help="goal list jsonl (env RQ1_SCOPES)")
    g.add_argument("--no-previous-round", action="store_true", help="switch the previous-round calibration off entirely")
    g.add_argument("--previous-round-audit", help="previous round audit directory (scopes.jsonl, tests.jsonl)")
    g.add_argument("--previous-round-exports", help="previous round export root")
    g.add_argument("--generator-label", help="provenance path printed in the summary header")
    g.add_argument("--helpers", help="path of review_refuted.py (checkpoints/pick/summarize_step)")
    g.add_argument("--allow-frozen-audit-dir", action="store_true",
                   help="allow writing into docs/design/cpv-expansion, docs/paper or eval (refused by default)")
    g.add_argument("--print-config", action="store_true", help="print the resolved configuration and exit")


def load_config(args: argparse.Namespace, positional_export_name: str | None = None) -> Config:
    here = Path(__file__).resolve().parent
    raw = dict(DEFAULTS)
    raw["previous_round"] = dict(DEFAULTS["previous_round"])
    raw["review"] = dict(DEFAULTS["review"])
    raw["targets"] = dict(DEFAULTS["targets"])

    config_path = getattr(args, "config", None) or os.environ.get("RQ1_CONFIG")
    if config_path:
        p = Path(config_path)
        if not p.is_absolute():
            p = (Path.cwd() / p) if (Path.cwd() / p).exists() else (here / p)
        if not p.exists():
            fail(f"config file not found: {config_path}")
        loaded = _strip_comments(json.loads(p.read_text()))
        for key, value in loaded.items():
            if key in ("previous_round", "review", "targets") and isinstance(value, dict):
                raw[key] = {**raw[key], **value}
            else:
                raw[key] = value

    repo = Path(getattr(args, "repo", None) or raw.get("repo_root") or os.environ.get("RQ1_REPO") or find_repo_root(here)).resolve()

    def path_of(value, default=None):
        value = value if value is not None else default
        if value is None:
            return None
        p = Path(value)
        return p if p.is_absolute() else (repo / p)

    runs_root = path_of(getattr(args, "runs_root", None) or os.environ.get("DEEPSEEK_RUNS_ROOT") or raw["runs_root"])
    audit_dir = path_of(getattr(args, "audit_dir", None) or os.environ.get("RQ1_AUDIT_DIR") or raw["audit_dir"])
    export_name = (getattr(args, "export_name", None) or os.environ.get("DEEPSEEK_EXPORT_NAME")
                   or positional_export_name or raw["export_name"])
    runs_flag = getattr(args, "runs", None) or os.environ.get("DEEPSEEK_RUNS")
    global_runs = tuple(_csv(runs_flag)) if runs_flag else tuple(raw["runs"])
    if not global_runs:
        fail("no run names configured (--runs / DEEPSEEK_RUNS / config 'runs')")
    inventory_template = raw.get("inventory_template") or DEFAULTS["inventory_template"]

    declared = {}
    order = []
    for entry in raw["subjects"]:
        entry = {"id": entry} if isinstance(entry, str) else dict(entry)
        if not entry.get("id"):
            fail(f"subject entry without an id: {entry!r}")
        declared[entry["id"]] = entry
        order.append(entry["id"])
    selected = _csv(getattr(args, "subjects", None) or os.environ.get("RQ1_SUBJECTS") or "") or order
    runs_overridden = bool(runs_flag)

    subjects = []
    for sid in selected:
        entry = declared.get(sid, {"id": sid})
        runs = global_runs if runs_overridden else tuple(entry.get("runs") or global_runs)
        subjects.append(Subject(
            id=sid,
            runs=runs,
            export_name=entry.get("export_name") or export_name,
            export_glob=entry.get("export_glob") or raw["export_glob"],
            inventory=path_of(entry.get("inventory"), inventory_template.format(subject=sid)),
        ))
    if not subjects:
        fail("no subjects configured")

    pr_raw = raw["previous_round"]
    previous = PreviousRound(
        enabled=bool(pr_raw.get("enabled", True)) and not getattr(args, "no_previous_round", False),
        audit_dir=path_of(getattr(args, "previous_round_audit", None) or pr_raw.get("audit_dir"),
                          DEFAULTS["previous_round"]["audit_dir"]),
        exports_root=path_of(getattr(args, "previous_round_exports", None) or pr_raw.get("exports_root"),
                             DEFAULTS["previous_round"]["exports_root"]),
        export_glob=pr_raw.get("export_glob") or DEFAULTS["previous_round"]["export_glob"],
        subjects=tuple(pr_raw["subjects"]) if isinstance(pr_raw.get("subjects"), list) else tuple(s.id for s in subjects),
        group_note=pr_raw.get("group_note"),
        scopes_note=pr_raw.get("scopes_note"),
    )

    cfg = Config(
        repo=repo, runs_root=runs_root, audit_dir=audit_dir, export_name=export_name, subjects=subjects,
        scopes=path_of(getattr(args, "scopes", None) or os.environ.get("RQ1_SCOPES") or raw["scopes"]),
        queue_sample_seed=int(raw["queue_sample_seed"]),
        summary_generator_label=(getattr(args, "generator_label", None) or os.environ.get("RQ1_GENERATOR_LABEL")
                                 or raw["summary_generator_label"]),
        helpers_module=path_of(getattr(args, "helpers", None) or os.environ.get("RQ1_HELPERS") or raw["helpers_module"]),
        previous_round=previous, review=raw["review"], targets=raw["targets"], raw=raw,
        allow_frozen_audit_dir=bool(getattr(args, "allow_frozen_audit_dir", False)
                                    or raw.get("allow_frozen_audit_dir")
                                    or os.environ.get("RQ1_ALLOW_FROZEN_AUDIT_DIR")),
    )
    if getattr(args, "print_config", False):
        print(json.dumps(cfg.describe(), ensure_ascii=False, indent=2))
        raise SystemExit(0)
    return cfg


def load_helpers(cfg: Config):
    """Import checkpoints/pick/summarize_step from the frozen review_refuted.py without touching it."""
    import importlib.util

    path = cfg.helpers_module
    if not path.exists():
        fail(f"helpers module not found: {path} (set 'helpers_module' / --helpers)")
    spec = importlib.util.spec_from_file_location("rq1_review_refuted_helpers", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True          # never write __pycache__ next to the frozen copy
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    missing = [n for n in ("checkpoints", "pick", "summarize_step") if not hasattr(module, n)]
    if missing:
        fail(f"helpers module {path} lacks {missing}")
    return module


def jsonl(path: Path) -> list:
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []


def load_inventory(cfg: Config, subject: Subject, required: bool):
    """Inventory of a subject's recording workflow suite; ``required`` makes a miss fatal."""
    if subject.inventory.exists():
        return json.loads(subject.inventory.read_text())
    if required:
        fail(f"inventory not found for subject '{subject.id}': {subject.inventory} "
             f"(set subjects[].inventory or 'inventory_template' in the config)")
    return None
