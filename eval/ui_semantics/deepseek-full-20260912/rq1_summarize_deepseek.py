"""RQ1 summary for the final DeepSeek suite (read-only over the frozen runs).

Inputs (docs/design/cpv-expansion/rq1-audit-deepseek/):
  tests.jsonl, cases.jsonl      from rq1_extract.py
  reviews.jsonl                 model-assisted initial review (rq1_review_deepseek.py), last row per test_key wins
  main-review.jsonl (optional)  main-line decisions {test_key, label, reason, basis}; override the initial label
  targets.jsonl (optional)      per case {subject, case_id, has_correct_target, target_test_keys, reason}
Also joins canonical_relation_core_identity from the pytest-export-final catalogs (semantic groups = same
core identity, a mechanical proxy for "same proposition"), and calibrates against the Astra-round labels
(docs/design/cpv-expansion/rq1-audit/tests.jsonl) through the Astra export catalogs' core identities.
Outputs: tests-labeled.jsonl, groups.jsonl, calibration.jsonl, review-queue.md, summary.md (same directory).
Usage: rq1_summarize_deepseek.py [export-name]   (default pytest-export-final)
"""
from __future__ import annotations

import glob
import json
import os
import re
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AUDIT = Path(os.environ.get("RQ1_AUDIT_DIR") or REPO / "docs/design/cpv-expansion/rq1-audit-deepseek")
RUNS_ROOT = Path(os.environ.get("DEEPSEEK_RUNS_ROOT") or HERE)   # ablation roots override this
ASTRA_AUDIT = REPO / "docs/design/cpv-expansion/rq1-audit"
ASTRA_EXPORTS = REPO / "eval/ui_semantics/cpv-astra-qualification-20260906"
LABEL_WORD = {"C": "correct", "E": "incorrect", "U": "insufficient", "W": "unreviewed"}
ASTRA_TO_CODE = {"correct": "C", "incorrect": "E", "insufficient": "U", None: "W"}


def goal_ids(goals):
    """Stable ids for a case's goals: keep a leading code like CA1/RB2/RP10, otherwise G<n>."""
    out = []
    for n, g in enumerate(goals, 1):
        head = g.split(" ")[0]
        out.append(head if re.fullmatch(r"[A-Z]+[0-9]+", head) else f"G{n}")
    return out


def lines(p: Path):
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def pct(a, b):
    return f"{a}/{b} ({100.0 * a / b:.1f}%)" if b else f"{a}/{b} (-)"


def core_identities(root: Path, export_glob: str) -> dict:
    out = {}
    for p in glob.glob(str(root / export_glob)):
        case = Path(p).parent.name
        for t in json.load(open(p))["tests"]:
            out[(case, t["test_id"])] = t.get("canonical_relation_core_identity")
    return out


def main(argv):
    export_name = argv[1] if len(argv) > 1 else "pytest-export-final"
    tests = lines(AUDIT / "tests.jsonl")
    cases = lines(AUDIT / "cases.jsonl")
    initial = {}
    for r in lines(AUDIT / "reviews.jsonl"):
        initial[r["test_key"]] = r
    main_review = {r["test_key"]: r for r in lines(AUDIT / "main-review.jsonl")}
    targets = {(r["subject"], r["case_id"]): r for r in lines(AUDIT / "targets.jsonl")}
    scopes = {(r["subject"], r["case_id"]): r for r in lines(ASTRA_AUDIT / "scopes.jsonl")}
    failures = {r["test_key"] for r in lines(AUDIT / "review-failures.jsonl")}
    inventories = {s: json.load(open(REPO / f"fixtures/recording_workflows/{s}_modular/inventory.json")) for s in ("conduit", "rwa")}
    module_by_case = {(s, c): m.get("module_id") or m.get("id") for s, inv in inventories.items() for m in inv.get("modules", []) for c in m.get("case_ids", [])}
    cores = {s: core_identities(RUNS_ROOT / s / export_name, "*/business_test_catalog.json") for s in ("conduit", "rwa")}
    astra_cores = {s: core_identities(ASTRA_EXPORTS / s, "pytest-export-*/*/business_test_catalog.json") for s in ("conduit", "rwa")}
    astra_labels = defaultdict(list)  # (subject, core) -> [(label code, test_key)]
    for t in lines(ASTRA_AUDIT / "tests.jsonl"):
        if t.get("classifier_layer") != "business_relation":
            continue
        core = astra_cores[t["subject"]].get((t["case_id"], t["test_id"]))
        if core:
            astra_labels[(t["subject"], core)].append((ASTRA_TO_CODE.get(t.get("semantic_label"), "W"), t["test_key"]))

    labeled = []
    for t in tests:
        row = dict(t)
        row["core_identity"] = cores[t["subject"]].get((t["case_id"], t["test_id"]))
        if t["layer"] != "business_relation":
            row.update(label=None, label_source=None, review_reason=None)
        elif t["test_key"] in main_review:
            m = main_review[t["test_key"]]
            row.update(label=m["label"], label_source="main_review", review_reason=m.get("reason"),
                       initial_label=(initial.get(t["test_key"]) or {}).get("label"),
                       scenario_specific=bool(m.get("scenario_specific")), main_review_rule=m.get("rule"))
        elif t["test_key"] in initial:
            r = initial[t["test_key"]]
            row.update(label=r["label"], label_source=r.get("reviewer"), review_reason=r.get("reason"))
        else:
            row.update(label="W", label_source="review_failed" if t["test_key"] in failures else None, review_reason=None)
        labeled.append(row)
    (AUDIT / "tests-labeled.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in labeled))

    # semantic groups by core identity (business tests only)
    groups = []
    members_by = defaultdict(list)
    for r in labeled:
        if r["layer"] == "business_relation":
            members_by[(r["subject"], r["core_identity"] or f"nocore:{r['test_key']}")].append(r)
    for (subject, core), members in sorted(members_by.items()):
        counts = Counter(m["label"] for m in members)
        groups.append({"subject": subject, "group_id": f"{subject}-{(core or '')[:12]}", "core_identity": core,
                       "size": len(members), "cases": sorted({m["case_id"] for m in members}),
                       "test_keys": [m["test_key"] for m in members],
                       "example_summary": members[0].get("business_summary"),
                       "C": counts["C"], "E": counts["E"], "U": counts["U"], "W": counts["W"],
                       "all_correct": counts["C"] == len(members), "contains_incorrect": counts["E"] > 0,
                       "pending": counts["E"] == 0 and (counts["U"] > 0 or counts["W"] > 0),
                       "mixed_quality": counts["C"] > 0 and counts["E"] > 0,
                       "astra_labels": [c for c, _ in astra_labels.get((subject, core), [])]})
    (AUDIT / "groups.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in groups))

    # calibration against the Astra round (instances whose core identity carries Astra labels)
    calib = []
    for r in labeled:
        if r["layer"] != "business_relation" or not r["core_identity"]:
            continue
        al = astra_labels.get((r["subject"], r["core_identity"]))
        if al:
            calib.append({"test_key": r["test_key"], "subject": r["subject"], "deepseek_label": r["label"],
                          "astra_labels": sorted({c for c, _ in al}), "astra_test_keys": [k for _, k in al][:5]})
    (AUDIT / "calibration.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in calib))

    # summary tables
    out = ["# RQ1 semantic review summary: DeepSeek final test set (generated)", "",
           f"Generated by `eval/ui_semantics/deepseek-full-20260912/rq1_summarize_deepseek.py` from `tests.jsonl` ({export_name} export plus frozen M12/M14 evidence), `reviews.jsonl` (model-assisted initial review), `main-review.jsonl` (author adjudications, which override the initial labels) and `targets.jsonl` (primary-effect judgements, optional).",
           "Review procedure: model-assisted initial labels plus author adjudication of every incorrect or insufficient-evidence item and every disagreement with the previous round; structural constraints (basic layer) carry no correctness label and do not enter the business correctness rate.", "",
           "## Counts and business instances", "", "| Subject | Input cases | Completed cases | Main-chain tests | Structural | Business T | C/E/U/W | C/T | C/(C+E) | Scenario-specific C | Strict C/T (excl. scenario-specific) |", "|---|---:|---:|---:|---:|---:|---|---|---|---:|---|"]
    tot = Counter()
    for subject in ("conduit", "rwa", "total"):
        rs = [r for r in labeled if subject == "total" or r["subject"] == subject]
        cs = [c for c in cases if subject == "total" or c["subject"] == subject]
        biz = [r for r in rs if r["layer"] == "business_relation"]
        n = Counter(r["label"] for r in biz)
        basic = sum(r["layer"] == "basic_constraint" for r in rs)
        ss = sum(1 for r in biz if r["label"] == "C" and r.get("scenario_specific"))
        out.append(f"| {subject} | {len(cs)} | {sum(c.get('status') not in (None, 'no_complete_run') for c in cs)} | {len(rs)} | {basic} | {len(biz)} | {n['C']}/{n['E']}/{n['U']}/{n['W']} | {pct(n['C'], len(biz))} | {pct(n['C'], n['C'] + n['E'])} | {ss} | {pct(n['C'] - ss, len(biz))} |")
    # generation funnel per subject (paper table 2), read from the frozen run roots named in cases.jsonl
    out += ["", "## Generation funnel (Section V-A)", "", "| Subject | M10 candidates (admitted, deduplicated) | M11b constructible | M12 validated / refuted / not evaluable / infrastructure failed | M14 retained (business relations / structural constraints) | Semantic relation groups (business) |", "|---|---:|---:|---|---|---:|"]
    funnel_total = Counter()
    for subject in ("conduit", "rwa", "total"):
        if subject != "total":
            f = Counter()
            for c in cases:
                if c["subject"] != subject or c.get("status") in (None, "no_complete_run"):
                    continue
                u = RUNS_ROOT / subject / c["run"] / "cases" / c["case_id"] / "union"
                cs = json.load(open(u / "M10/union/candidate_set.json")) if (u / "M10/union/candidate_set.json").exists() else {"candidates": []}
                f["exact"] += len(cs["candidates"])
                elig = json.load(open(u / "M11b/materialization_eligibility.json")) if (u / "M11b/materialization_eligibility.json").exists() else {}
                f["ineligible"] += elig.get("materialization_ineligible_count", elig.get("ineligible_count", 0)) or 0
                rr = json.load(open(u / "M12/run_report.json")) if (u / "M12/run_report.json").exists() else {}
                for r in rr.get("rows", []):
                    f["m12_" + str((r.get("protocol_result") or {}).get("protocol_verdict"))] += 1
            f["retained"] = sum(1 for r in labeled if r["subject"] == subject)
            f["business"] = sum(1 for r in labeled if r["subject"] == subject and r["layer"] == "business_relation")
            f["basic"] = sum(1 for r in labeled if r["subject"] == subject and r["layer"] == "basic_constraint")
            f["groups"] = sum(1 for g in groups if g["subject"] == subject)
            funnel_total.update(f)
        else:
            f = funnel_total
        out.append(f"| {subject} | {f['exact']} | {f['exact'] - f['ineligible']} | {f['m12_validated']} / {f['m12_refuted']} / {f['m12_not_evaluable']} / {f['m12_infrastructure_failed']} | {f['retained']} ({f['business']} / {f['basic']}) | {f['groups']} |")
    out += ["", "M11b constructible = M10 candidates minus M11b not constructible; M12 counts are the verdict of one complete validation plan per candidate; retained counts follow the layer labels of the export directory (cases without an export are counted as retained without a layer label).", ""]
    out += ["", "## Semantic relation groups of business instances (mechanical grouping by canonical_relation_core_identity)", "",
            "| Subject | Groups | Entirely correct / containing incorrect / pending | Mixed-quality groups | Share entirely correct | At least one correct instance | Singleton groups | Largest group |", "|---|---:|---|---:|---|---:|---:|---:|"]
    for subject in ("conduit", "rwa", "total"):
        gs = [g for g in groups if subject == "total" or g["subject"] == subject]
        out.append(f"| {subject} | {len(gs)} | {sum(g['all_correct'] for g in gs)}/{sum(g['contains_incorrect'] for g in gs)}/{sum(g['pending'] for g in gs)} | {sum(g['mixed_quality'] for g in gs)} | {pct(sum(g['all_correct'] for g in gs), len(gs))} | {sum(g['C'] > 0 for g in gs)} | {sum(g['size'] == 1 for g in gs)} | {max((g['size'] for g in gs), default=0)} |")
    out += ["", "Difference from the previous round: its groups were merged manually by full proposition during review (Conduit 74, RWA 96 groups); this round groups mechanically by the export directory's `canonical_relation_core_identity`, a finer granularity, so the group counts of the two rounds are not directly comparable.", ""]
    out += ["## Calibration against the previous round's labels (same core identity)", "", "| Subject | Calibratable instances | DeepSeek C / E / U / W | Previous round all C | DeepSeek differs from previous round (excl. W) |", "|---|---:|---|---:|---:|"]
    for subject in ("conduit", "rwa"):
        cs_ = [c for c in calib if c["subject"] == subject]
        n = Counter(c["deepseek_label"] for c in cs_)
        astra_c = sum(c["astra_labels"] == ["C"] for c in cs_)
        disagree = sum(1 for c in cs_ if c["deepseek_label"] in ("C", "E", "U") and c["deepseek_label"] not in c["astra_labels"])
        out.append(f"| {subject} | {len(cs_)} | {n['C']}/{n['E']}/{n['U']}/{n['W']} | {astra_c} | {disagree} |")
    out += ["", "The previous round's labels serve only as a cross-check, not as ground truth; disagreements enter the adjudication queue.", ""]
    out += ["## Primary-target results", "", "| Subject | API/mixed/UI-only | N_API | K (cases with a correct primary-target test) | K/N_API | Pending |", "|---|---|---:|---:|---|---:|"]
    for subject in ("conduit", "rwa", "total"):
        sc = [s for (subj, _), s in scopes.items() if subject == "total" or subj == subject]
        n = Counter(s["scope"] for s in sc)
        api_cases = [s for s in sc if s["scope"] in ("api", "mixed")]
        k = sum(1 for s in api_cases if (targets.get((s["subject"], s["case_id"])) or {}).get("has_correct_target") is True)
        undecided = sum(1 for s in api_cases if (s["subject"], s["case_id"]) not in targets)
        out.append(f"| {subject} | {n['api']}/{n['mixed']}/{n['ui_only']} | {len(api_cases)} | {k} | {pct(k, len(api_cases))} | {undecided} |")
    out += ["", "The effect lists are those of the previous round (`rq1-audit/scopes.jsonl`; the 83 inputs are unchanged); K counts cases in which at least one listed effect is checked by a correct assertion (full or partial); cases missing from `targets.jsonl` are counted as pending.", ""]
    out += ["## Cases with at least one correct business assertion", "", "| Subject | API/mixed cases | of which with at least one correct business instance | All input cases | of which with at least one correct business instance |", "|---|---:|---:|---:|---:|"]
    for subject in ("conduit", "rwa", "total"):
        sc = [s for (subj, _), s in scopes.items() if subject == "total" or subj == subject]
        with_c = {(r["subject"], r["case_id"]) for r in labeled if r["layer"] == "business_relation" and r["label"] == "C"}
        api_cases = [s for s in sc if s["scope"] in ("api", "mixed")]
        out.append(f"| {subject} | {len(api_cases)} | {sum((s['subject'], s['case_id']) in with_c for s in api_cases)} | {len(sc)} | {sum((s['subject'], s['case_id']) in with_c for s in sc)} |")
    out += ["", "## Post-hoc effect-list coverage (items of API/mixed cases)", "", "| Subject | Full (every effect of every item checked by a correct assertion) | Partial (at least one effect checked) | Uncovered (correct assertions that check no item) | No correct business assertion | Pending | Items (fully + partially covered / total) |", "|---|---:|---:|---:|---:|---:|---|"]
    for subject in ("conduit", "rwa", "total"):
        sc = [s for (subj, _), s in scopes.items() if (subject == "total" or subj == subject) and s["scope"] in ("api", "mixed")]
        n = Counter(); goals_total = goals_covered = goals_partial = 0
        for s_ in sc:
            t = targets.get((s_["subject"], s_["case_id"]))
            ids = goal_ids(s_["goals"])
            if t is None:
                n["pending"] += 1; continue
            cov = t.get("goal_coverage") or {}
            levels = [(cov.get(g) or {}).get("coverage", "none") for g in ids]
            goals_total += len(ids); goals_covered += sum(1 for l in levels if l == "full"); goals_partial += sum(1 for l in levels if l == "partial")
            if t.get("correct_tests", 0) == 0 or t.get("reviewer") == "rule":
                n["no_correct"] += 1
            elif ids and all(l == "full" for l in levels):
                n["full"] += 1
            elif any(l in ("full", "partial") for l in levels):
                n["partial"] += 1
            else:
                n["none"] += 1
        out.append(f"| {subject} | {n['full']} | {n['partial']} | {n['none']} | {n['no_correct']} | {n['pending']} | {goals_covered} full + {goals_partial} partial / {goals_total} |")
    out.append("")
    out += ["## Distribution by module (business instances)", "", "| Subject/module | Cases | Business T | C/E/U/W | Groups | Entirely correct |", "|---|---:|---:|---|---:|---:|"]
    for subject in ("conduit", "rwa"):
        by_mod = defaultdict(list)
        for r in labeled:
            if r["subject"] == subject and r["layer"] == "business_relation":
                by_mod[module_by_case.get((subject, r["case_id"])) or "?"].append(r)
        for mod, rs in sorted(by_mod.items()):
            n = Counter(r["label"] for r in rs)
            gs = {r["core_identity"] for r in rs}
            allc = sum(1 for g in groups if g["subject"] == subject and g["core_identity"] in gs and g["all_correct"])
            out.append(f"| {subject}/{mod} | {len({r['case_id'] for r in rs})} | {len(rs)} | {n['C']}/{n['E']}/{n['U']}/{n['W']} | {len(gs)} | {allc} |")
    out += ["", "## Author adjudication", "", "| Subject | Adjudicated instances | Initial label to final label | Scenario-specific C |", "|---|---:|---|---:|"]
    for subject in ("conduit", "rwa"):
        mr = [r for r in labeled if r["subject"] == subject and r.get("label_source") == "main_review"]
        moves = Counter(f"{r.get('initial_label')}→{r['label']}" for r in mr)
        out.append(f"| {subject} | {len(mr)} | {', '.join(f'{k} {v}' for k, v in sorted(moves.items())) or '-'} | {sum(1 for r in mr if r.get('scenario_specific') and r['label'] == 'C')} |")
    out += ["", "Scenario-specific C: the assertion instantiates the business intent of the recorded scenario in a form stronger than the application's general semantics (e.g., an exact user-name search, or a count when the result set fits on one page) and is not a universal rule; counted separately, following the previous round's treatment of the same propositions.", ""]
    out += ["", "## Sources of the initial labels", ""]
    src = Counter((r["subject"], r.get("label_source") or "-") for r in labeled if r["layer"] == "business_relation")
    for (subject, s), n in sorted(src.items()):
        out.append(f"- {subject}: {s}: {n}")
    (AUDIT / "summary.md").write_text("\n".join(out) + "\n")

    # review queue: every E/U/W business instance, Astra disagreements, and sampled C groups per subject
    q = ["# RQ1 adjudication queue (generated)", "", "Every E/U instance is checked against the execution evidence; instances disagreeing with the previous round; C instances are sampled by semantic group (the two largest and two random groups per subject).", ""]
    for subject in ("conduit", "rwa"):
        rs = [r for r in labeled if r["subject"] == subject and r["layer"] == "business_relation"]
        q += [f"## {subject}", "", "### E / U / W instances", "", "| test_key | Label | Summary | Initial rationale |", "|---|---|---|---|"]
        for r in rs:
            if r["label"] in ("E", "U", "W"):
                q.append(f"| {r['test_key']} | {r['label']} | {(r.get('business_summary') or '')[:200].replace('|', '/')} | {(r.get('review_reason') or '')[:300].replace('|', '/')} |")
        dis = [c for c in calib if c["subject"] == subject and c["deepseek_label"] in ("C", "E", "U") and c["deepseek_label"] not in c["astra_labels"]]
        q += ["", "### Disagreements with the previous round", "", "| test_key | DeepSeek | Previous round | Previous-round instances |", "|---|---|---|---|"]
        for c in dis:
            q.append(f"| {c['test_key']} | {c['deepseek_label']} | {','.join(c['astra_labels'])} | {'; '.join(c['astra_test_keys'][:2])} |")
        gs = [g for g in groups if g["subject"] == subject and g["C"] > 0]
        rng = random.Random(20260912)
        sample = sorted(gs, key=lambda g: -g["size"])[:2] + rng.sample([g for g in sorted(gs, key=lambda g: -g["size"])[2:]], min(2, max(0, len(gs) - 2)))
        q += ["", "### Sampled C groups", ""]
        for g in sample:
            q += [f"- Group `{g['group_id']}` ({g['size']} instances, cases {', '.join(g['cases'])}): {(g['example_summary'] or '')[:220]}",
                  "  - Members: " + ", ".join(k.split('/')[-1] for k in g["test_keys"][:12]) + (" …" if g["size"] > 12 else "")]
        q.append("")
    (AUDIT / "review-queue.md").write_text("\n".join(q) + "\n")
    biz = [r for r in labeled if r["layer"] == "business_relation"]
    print(json.dumps({"tests": len(labeled), "business": len(biz), "labels": dict(Counter(r["label"] for r in biz)),
                      "groups": len(groups), "calibration_instances": len(calib),
                      "queue_EUW": sum(r["label"] in ("E", "U", "W") for r in biz)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
