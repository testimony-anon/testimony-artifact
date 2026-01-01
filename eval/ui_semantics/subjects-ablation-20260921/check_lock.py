# -*- coding: utf-8 -*-
"""Validate a candidate ablation lock against the real suite/per-case guards in a temporary repo root (fixtures copied, eval refs absolute)."""
import json, sys, shutil, tempfile
from pathlib import Path
W = Path("<PAPER_CODE_WORKTREE>")
sys.path.insert(0, str(W / "src"))
from ui_semantics.current_suite import _require_suite_execution_lock
from ui_semantics.current_orchestrator import _require_execution_lock
lock = json.load(open(sys.argv[1])); ok = True
with tempfile.TemporaryDirectory() as raw:
    root = Path(raw) / "repo"; (root / "docs").mkdir(parents=True)
    (root / "docs/ACTIVE-EXECUTION.json").write_text(json.dumps(lock))
    for cap in lock["current_execution_capabilities"]:
        s = cap["subject_id"]
        for rel in (cap["suite_ref"], cap["adapter_ref"], cap["profile_ref"], cap["proposal_plan_ref"], f"fixtures/profiles/{s}_modular_guest_local.json"):
            if (W / rel).exists():
                (root / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(W / rel, root / rel)
        suite = root / cap["suite_ref"]; config = Path(cap["qualification_root_ref"]).name.split("-")[0]
        try:
            _require_suite_execution_lock(root, entrypoint="scripts/uisemtest run", suite_path=suite, subject=json.loads(suite.read_text())["subject"],
                recording_root=Path(cap["recording_root_ref"]), qualification_root=Path(cap["qualification_root_ref"]),
                adapter_path=root / cap["adapter_ref"], proposal_path=root / cap["proposal_plan_ref"], provider_kind="openai_compatible",
                output_level="forensic", probe_budget=0, stop_after_m9=False, m10_samples=3, m10_sample_mode="union", provider_concurrency=48)
            print(f"suite {s:9s} {config:8s} ACCEPTED")
        except Exception as exc:
            ok = False; print(f"suite {s:9s} {config:8s} REJECTED ({exc})")
        for profile in ([f"{s}_modular_local.json"] + (["umami_modular_guest_local.json"] if s == "umami" else [])):
            try:
                _require_execution_lock(root, live_requested=True, subject_id=s, provider_kind="openai_compatible", runtime_kind="local_http",
                    profile_path=root / "fixtures/profiles" / profile, adapter_path=root / cap["adapter_ref"],
                    output_root=Path(cap["qualification_root_ref"]) / "cases/X/union")
                print(f"  case {s:9s} {profile:34s} ACCEPTED")
            except Exception as exc:
                ok = False; print(f"  case {s:9s} {profile:34s} REJECTED ({exc})")
print("ALL ACCEPTED" if ok else "SOME REJECTED")
