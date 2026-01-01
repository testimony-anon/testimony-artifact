"""Extract the RQ1 review units of a generated suite (read-only), for any subject list.

Parameterised copy of eval/ui_semantics/deepseek-full-20260912/rq1_extract.py: the subject
list, the per-subject run priority, the export directory name, the audit output directory and
the helper module are configuration, not literals.  The row layout is unchanged, so the output
of the two scripts is byte-identical for the frozen conduit+rwa configuration.

Inputs: pytest export catalogs (official layer labels, business summaries) of the run roots
named in ``runs`` (first complete union per case wins) and the M12 execution evidence for
observed values.  Outputs, under the audit directory:
  cases.jsonl   one row per suite case (module, layer, run root, retained count)
  tests.jsonl   one row per retained main-chain test (business + basic), with predicate
                summary, producer/observer calls, observed values and source refs;
                review fields start unreviewed
Usage: rq1_extract.py [export-name] [--config rq1-config.json] [--subjects a,b] ...
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rq1_config import add_common_args, fail, load_config, load_helpers, load_inventory  # noqa: E402


def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def _logical_request_body(ev: dict, key: str):
    step = (ev.get("protocol") or {}).get(key)
    return step.get("request") if isinstance(step, dict) else None


def _scalar_diffs(physical, logical):
    """(fresh, recorded) string pairs where the physical request differs from the logical one."""
    if isinstance(physical, dict) and isinstance(logical, dict):
        for k in physical:
            if k in logical:
                yield from _scalar_diffs(physical[k], logical[k])
    elif isinstance(physical, list) and isinstance(logical, list):
        for a, b in zip(physical, logical):
            yield from _scalar_diffs(a, b)
    elif isinstance(physical, str) and isinstance(logical, str) and physical != logical and "$route_s_redacted" not in logical:
        yield physical, logical


def build(cfg, helpers) -> tuple[list, list]:
    checkpoints, pick, summarize_step = helpers.checkpoints, helpers.pick, helpers.summarize_step
    cases_out, tests_out = [], []
    for subject_cfg in cfg.subjects:
        subject = subject_cfg.id
        inventory = load_inventory(cfg, subject_cfg, required=True)
        module_by_case = {c: m.get("module_id") or m.get("id") for m in inventory.get("modules", []) for c in m.get("case_ids", [])}
        suite_cases = [c["case_id"] for c in inventory.get("cases", [])]
        if not suite_cases:
            fail(f"inventory {subject_cfg.inventory} lists no cases for subject '{subject}'")
        export_root = subject_cfg.export_root(cfg.runs_root)
        for case in suite_cases:
            u = subject_cfg.union(cfg.runs_root, case)
            if u is None:
                cases_out.append({"subject": subject, "case_id": case, "module": module_by_case.get(case), "status": "no_complete_run"})
                continue
            final = load(u / "M14/final_calibrated_suite.json") or {}
            manifest = load(u / "run_manifest.json") or {}
            catalog = load(export_root / case / "business_test_catalog.json")
            layers = {t["test_id"]: t for t in (catalog or {}).get("tests", [])}
            cases_out.append({"subject": subject, "case_id": case, "module": module_by_case.get(case), "layer": case.split("-")[0],
                              "run": u.parents[2].name, "git_head": ((manifest.get("environment") or {}).get("git_head") or "")[:12],
                              "status": final.get("status"), "retained_count": final.get("retained_count"),
                              "exported": catalog is not None})
            rr = load(u / "M12/run_report.json") or {}
            verdict_by_cid = {r["candidate_id"]: (r.get("protocol_result") or {}).get("protocol_verdict") for r in rr.get("rows", [])}
            for test in final.get("retained_tests", []):
                cid, tid = test.get("candidate_id"), test.get("test_id")
                cat = layers.get(tid) or {}
                ev = load(u / f"M12/{cid}/execution_evidence.json") or {}
                cps = checkpoints(ev.get("protocol") or {})
                producer = pick(cps, "producer", "P")
                before = pick(cps, "before", "Ot0", "Oc1")
                after = pick(cps, "after", "Ot1", "Oc2")
                observation = pick(cps, "observation", "observations[0]")
                business = [a for a in test.get("assertions", []) if a.get("assertion_class") == "business"]
                # Requests are sent with fresh replay identifiers (aliases of the recorded ones);
                # persisted response bodies are normalized back to the recorded identifiers.
                # Expose the recorded-domain request body and the fresh->recorded alias pairs so
                # a reviewer can recognise one resource under both identifiers.
                alias_pairs = {}
                for key, cp in cps.items():
                    step = (ev.get("protocol") or {}).get(key.split("[")[0]) if "[" not in key else None
                    logical = (step or {}).get("request") if isinstance(step, dict) else None
                    physical = cp.get("request_body")
                    for fresh, recorded in _scalar_diffs(physical, logical):
                        alias_pairs[fresh] = recorded
                calls = [{"checkpoint": (cp.get("checkpoint_id") or key), "actor": cp.get("actor_id"), "method": cp.get("method"),
                          "path": cp.get("path"), "query": cp.get("query"),
                          "status": cp.get("status") if cp.get("status") is not None else f"checkpoint {cp.get('checkpoint_status')}",
                          "request_body_recorded_domain": _logical_request_body(ev, key),
                          "body_excerpt": json.dumps(cp.get("body"), ensure_ascii=False)[:700]}
                         for key, cp in sorted(cps.items(), key=lambda kv: (kv[1].get("finished_at") is None, kv[1].get("finished_at") or ""))
                         if key not in ("reset", "setup") and not key.startswith("setup")]
                gate = (ev.get("protocol") or {}).get("rejection_gate") if test.get("protocol_kind") == "V6" else None
                rejection = None
                if isinstance(gate, dict):
                    detector = gate.get("detector") or {}
                    right = ((detector.get("predicate") or {}).get("right") or {})
                    rejection = {"observed_status": gate.get("response_status"), "rejected": gate.get("rejected"),
                                 "expected_status": right.get("value"), "expected_rationale": right.get("rationale"),
                                 "response_excerpt": json.dumps((producer or {}).get("body"), ensure_ascii=False)[:500]}
                tests_out.append({
                    "test_key": f"{subject}/{case}/{tid}", "subject": subject, "case_id": case, "stratum": "mainchain",
                    "test_id": tid, "candidate_id": cid, "protocol": test.get("protocol_kind"), "claim_kind": test.get("claim_kind"),
                    "layer": cat.get("assertion_layer"), "business_summary": cat.get("business_summary"),
                    "predicate": (cat.get("business_predicate") or {}).get("predicate") or (business[0].get("predicate") if business else None),
                    "producer_call": summarize_step(producer), "before_call": summarize_step(before),
                    "after_call": summarize_step(after), "observation_call": summarize_step(observation),
                    "producer_request_body": (producer or {}).get("request_body"),
                    "after_body_excerpt": json.dumps((after or observation or {}).get("body"), ensure_ascii=False)[:1500],
                    "before_body_excerpt": json.dumps((before or {}).get("body"), ensure_ascii=False)[:1500] if before else None,
                    "calls": calls, "rejection": rejection, "alias_pairs_fresh_to_recorded": alias_pairs,
                    "producer_request_body_recorded_domain": _logical_request_body(ev, "producer"),
                    "m12_verdict": verdict_by_cid.get(cid), "source_run": str(u), "git_head": ((manifest.get("environment") or {}).get("git_head") or "")[:12],
                    "source_m14_ref": str(u / "M14/final_calibrated_suite.json"), "source_evidence_ref": str(u / f"M12/{cid}/execution_evidence.json"),
                    "review_status": "unreviewed", "semantic_label": None, "semantic_group_id": None, "review_reason": None,
                })
    return cases_out, tests_out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export_name_positional", nargs="?", metavar="export-name",
                    help="pytest export directory name (default from the configuration)")
    ap.add_argument("--dry-run", action="store_true", help="resolve the configuration and count cases, write nothing")
    add_common_args(ap)
    args = ap.parse_args(argv[1:])
    cfg = load_config(args, positional_export_name=args.export_name_positional)
    helpers = load_helpers(cfg)

    if args.dry_run:
        plan = []
        for s in cfg.subjects:
            inv = load_inventory(cfg, s, required=True)
            cases = [c["case_id"] for c in inv.get("cases", [])]
            resolved = sum(1 for c in cases if s.union(cfg.runs_root, c) is not None)
            plan.append({"subject": s.id, "cases": len(cases), "with_complete_union": resolved,
                         "runs": list(s.runs), "export_root": cfg.rel(s.export_root(cfg.runs_root))})
        print(json.dumps({"dry_run": True, "audit_dir": cfg.rel(cfg.audit_dir), "subjects": plan}, ensure_ascii=False))
        return 0

    cfg.guard_audit_dir()
    cfg.audit_dir.mkdir(parents=True, exist_ok=True)
    cases_out, tests_out = build(cfg, helpers)
    (cfg.audit_dir / "cases.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cases_out))
    (cfg.audit_dir / "tests.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in tests_out))
    print(json.dumps({"cases": dict(Counter(str(r.get("status")) for r in cases_out)), "tests": len(tests_out),
                      "by_subject_layer": {f"{s}/{l}": n for (s, l), n in Counter((t["subject"], t["layer"]) for t in tests_out).items()},
                      "unexported": sum(1 for r in cases_out if r.get("status") not in (None, "no_complete_run") and not r.get("exported"))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
