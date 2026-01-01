"""RQ3 paired comparison for the added subjects: Full (paper run) vs an ablation configuration, by input case.

Usage: ablation_compare_subjects.py <temporal|flat> [subject ...]
Same metrics as eval/ui_semantics/deepseek-ablation-20260913/ablation_compare.py (funnel, retained business/structural,
correct business instances and distinct core identities, E, cases with >=1 correct business assertion, per-case paired
outcome on correct business instances, tokens).  Labels: the audit dirs' tests-labeled.jsonl (initial review for the
added subjects, plus the author-adjudicated items of the Full audits).  Primary-target coverage is not computed for the
added subjects (their effect lists were written after the fact; Section IV-A).
Writes docs/design/subjects-expansion-20260919/rq3-<config>-comparison.md and
eval/ui_semantics/subjects-ablation-20260921/rq3-<config>-comparison.json.
"""
import json, sys
from collections import Counter
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "eval/ui_semantics/deepseek-ablation-20260913"))
from ablation_compare import funnel, usage, per_case  # noqa: E402
FULL = {  # subject -> (runs_root, runs in precedence order, audit dir)
    "umami": (REPO / "eval/ui_semantics/umami-20260921", ["full-01"], REPO / "docs/design/subjects-expansion-20260919/rq1-audit-umami"),
    "paperless": (REPO / "eval/ui_semantics/paperless-20260921", ["m11fix-03", "full-01"], REPO / "docs/design/subjects-expansion-20260919/rq1-audit-paperless"),
    "ghost": (REPO / "eval/ui_semantics/ghost-20260921", ["full-01"], REPO / "docs/design/subjects-expansion-20260919/rq1-audit-ghost"),
}
ABL_ROOT = REPO / "eval/ui_semantics/subjects-ablation-20260921"

def main(argv):
    name = argv[1]; subjects = argv[2:] or list(FULL)
    report = {"config": name, "subjects": {}}
    md = [f"# RQ3 paired comparison on the added subjects: Full vs {name}", "",
          "Same recordings, model, generation rounds and validation pipeline; Paperless-ngx compares the 32 inputs of the reduced ablation suite (L1-DOCLIST-01/02/04 excluded: their Full M10 never completed). Labels are model-assisted initial labels (Full: plus the author-adjudicated items).", "",
          "| Subject | Configuration | M10 candidates | Constructible | M12 validated/refuted/not evaluable/infrastructure failed | Retained (business/structural) | Correct business instances | Correct semantic groups | E | Cases with at least one correct business assertion | Tokens (prompt/completion, M) |",
          "|---|---|---:|---:|---|---|---:|---:|---:|---:|---|"]
    for subject in subjects:
        full_root, full_runs, full_audit = FULL[subject]
        abl_audit = REPO / f"docs/design/subjects-expansion-20260919/rq1-audit-{subject}-{name}"
        full = per_case(full_audit); abl = per_case(abl_audit)
        rows = {}
        for cfg, (root, runs, pc) in {"Full": (full_root, full_runs, full), name: (ABL_ROOT, [f"{name}-01"], abl)}.items():
            f = funnel(str(root), subject, runs); u = usage(str(root), subject, runs)
            cases = {k: v for k, v in pc.items() if k[0] == subject}
            if subject == "paperless" and cfg == "Full":
                cases = {k: v for k, v in cases.items() if k[1] not in {"L1-DOCLIST-01", "L1-DOCLIST-02", "L1-DOCLIST-04"}}
            agg = Counter()
            for v in cases.values(): agg.update(v)
            rows[cfg] = {"funnel": dict(f), "usage": dict(u), "agg": dict(agg), "cases_with_C": sum(1 for v in cases.values() if v["C"] > 0)}
            md.append(f"| {subject} | {cfg} | {f['exact']} | {f['exact'] - f['ineligible']} | {f['m12_validated']}/{f['m12_refuted']}/{f['m12_not_evaluable']}/{f['m12_infrastructure_failed']} | {agg['retained']} ({agg['business']}/{agg['basic']}) | {agg['C']} | {agg['C_groups']} | {agg['E']} | {rows[cfg]['cases_with_C']} | {u['prompt']/1e6:.1f}/{u['completion']/1e6:.1f} |")
        paired = Counter()
        keys = {k for k in list(full) + list(abl) if k[0] == subject}
        if subject == "paperless":
            keys = {k for k in keys if k[1] not in {"L1-DOCLIST-01", "L1-DOCLIST-02", "L1-DOCLIST-04"}}
        for k in keys:
            a, b = full.get(k, Counter())["C"], abl.get(k, Counter())["C"]
            paired["improve" if b > a else "degrade" if b < a else "same"] += 1
        rows["paired_on_correct_business_instances"] = dict(paired)
        report["subjects"][subject] = rows
        md.append(f"| {subject} | Paired by input (correct business instances, {name} vs Full) | | | | | | | | | improved {paired['improve']} / degraded {paired['degrade']} / same {paired['same']} |")
    (REPO / f"docs/design/subjects-expansion-20260919/rq3-{name}-comparison.md").write_text("\n".join(md) + "\n")
    (ABL_ROOT / f"rq3-{name}-comparison.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\n".join(md[4:]))

if __name__ == "__main__":
    main(sys.argv)
