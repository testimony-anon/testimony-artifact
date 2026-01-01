"""Review sheet for M12-refuted candidates of the DeepSeek run (read-only).

For every refuted candidate in full-01 and retry-01: the producer action, the
observer, the predicate, the failing checks, and the observed values at the
failing projection paths taken from the execution evidence (before/after
bodies).  Output: refuted-review.md and refuted-review.json next to this file.
The classification column is filled by the model-assisted review afterwards.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Run roots in precedence order; a case is taken from the first run whose union holds a complete M14 suite
# (the same "first complete wins" rule as summarize_full_run.py / export_final.sh).  DEEPSEEK_RUNS overrides.
RUNS = tuple(x for x in os.environ.get("DEEPSEEK_RUNS", "full-01,retry-01").split(",") if x)
RUNS_LABEL = " + ".join(RUNS)
OUT_PREFIX = os.environ.get("REFUTED_OUT", "refuted-review")           # <prefix>.json / <prefix>.md next to this file
CLASSIFICATION = os.environ.get("REFUTED_CLASSIFICATION", "refuted-classification.json")


def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def jpath(value, path: str):
    """Minimal $.a.b[0] resolver."""
    cur = value
    for part in [p for p in path.replace("$", "", 1).replace("[", ".").replace("]", "").split(".") if p]:
        if isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def checkpoints(protocol):
    """checkpoint id -> {method, path, status, body} for every recorded HTTP checkpoint."""
    out = {}
    items = []
    for key, step in (protocol or {}).items():
        if isinstance(step, list):
            # single-state / query protocols keep their reads in a list
            items.extend((f"{key}[{index}]", item) for index, item in enumerate(step))
        else:
            items.append((key, step))
    for key, step in items:
        if not isinstance(step, dict) or "response" not in step:
            continue
        req = step.get("transport_request") or step.get("physical_transport_request") or step.get("request") or {}
        resp = step.get("response")
        if isinstance(resp, dict) and "status" in resp and "body" in resp:
            status, rbody = resp.get("status"), resp.get("body")
        else:
            status, rbody = None, resp
        meta = step.get("physical_transport_metadata") if isinstance(step.get("physical_transport_metadata"), dict) else {}
        out[key] = {"method": req.get("method") if isinstance(req, dict) else None,
                    "path": req.get("path") if isinstance(req, dict) else None,
                    "request_body": (req.get("body") if isinstance(req, dict) and "body" in req else step.get("request")),
                    "status": status, "body": rbody,
                    "checkpoint_id": step.get("checkpoint_id"), "actor_id": step.get("actor_id"), "finished_at": step.get("finished_at"),
                    "checkpoint_status": step.get("status") if isinstance(step.get("status"), str) else None,
                    "query": meta.get("query") or None}
    return out


def pick(cps, *names):
    for name in names:
        if name in cps:
            return cps[name]
    return None


def body(step):
    return (step or {}).get("body")


def summarize_step(step):
    if not step:
        return "-"
    return f"{step.get('method', '?')} {step.get('path', '?')} -> {step.get('status', '?')}"


def failing_values(pred, result, cps):
    """Observed values behind each failing check."""
    out = []
    before = pick(cps, "before", "Ot0", "Oc1")
    after = pick(cps, "after", "Ot1", "Oc2")
    producer = pick(cps, "producer", "P")
    b, a = body(before), body(after)
    fam = pred.get("family")
    obs = (result.get("observed") or {})
    if fam == "P20":
        base_l, base_r = pred["left"]["path"], pred["right"]["path"]
        for check in obs.get("checks", []):
            if check.get("satisfied") is False:
                sub = check["check_id"].replace("$", "", 1)
                out.append({"check": check["check_id"], "before": jpath(b, base_l + sub) if b is not None else None,
                            "after": jpath(a, base_r + sub) if a is not None else None})
    elif fam == "P02" and isinstance(pred.get("left"), dict):
        lp = pred["left"]["path"]
        role = pred["left"].get("role")
        src = a if role in ("after", "observation") else b
        lv = jpath(src, lp) if src is not None else None
        right = pred.get("right") or {}
        if right.get("source") == "hypothesis":
            rv, rdesc = right.get("value"), "hypothesis literal"
        else:
            ref = right.get("ref") or {}
            rrole = ref.get("role")
            if rrole == "producer_request":
                rv = jpath((producer or {}).get("request_body"), ref.get("path", "$"))
            elif rrole == "before":
                rv = jpath(b, ref.get("path", "$"))
            elif rrole in ("after", "observation"):
                rv = jpath(a, ref.get("path", "$"))
            else:
                rv = None
            rdesc = f"{rrole} {ref.get('path')}"
        out.append({"left": f"{role} {lp}", "left_value": lv, "right": rdesc, "right_value": rv, "observed": obs})
    else:
        out.append({"observed": obs})
    return out


def main():
    rows = []
    for subject in ("conduit", "rwa"):
        seen_cases = set()
        for run in RUNS:
            cases_dir = HERE / subject / run / "cases"
            if not cases_dir.exists():
                continue
            for case_dir in sorted(cases_dir.iterdir()):
                if case_dir.name.startswith("."):
                    continue
                u = case_dir / "union"
                if case_dir.name in seen_cases or not (u / "M14/final_calibrated_suite.json").exists():
                    continue
                seen_cases.add(case_dir.name)
                rr = load(u / "M12/run_report.json")
                if not rr:
                    continue
                cs = load(u / "M10/union/candidate_set.json") or {"candidates": []}
                payloads = {c["candidate_id"]: c["payload"] for c in cs["candidates"]}
                trace = (load(u / "M01_09/ui_api_trace.json") or {}).get("trace", {}).get("api_requests", [])
                req = {r["request_ref"]: f"{r['actor_id']} {r['method']} {r['canonical_path']}" for r in trace}
                for row in rr.get("rows", []):
                    pr = row.get("protocol_result") or {}
                    if pr.get("protocol_verdict") != "refuted":
                        continue
                    p = payloads.get(row["candidate_id"], {})
                    pred = p.get("primary_predicate", {})
                    ev = load(u / pr["evidence_ref"]) if pr.get("evidence_ref") else None
                    cps = checkpoints((ev or {}).get("protocol") or {})
                    rows.append({
                        "subject": subject, "run": run, "case": case_dir.name, "candidate_id": row["candidate_id"],
                        "contract_kind": p.get("contract_kind"), "protocol": pr.get("protocol_kind"),
                        "producer": req.get(str((p.get("producer") or {}).get("request_ref")), "-"),
                        "consumer": req.get(str((p.get("consumer") or {}).get("request_ref")), "-"),
                        "predicate": pred,
                        "predicate_result": pr.get("predicate_result"),
                        "checkpoints": sorted(cps),
                        "producer_call": summarize_step(pick(cps, "producer", "P")),
                        "before_call": summarize_step(pick(cps, "before", "Ot0", "Oc1")),
                        "after_call": summarize_step(pick(cps, "after", "Ot1", "Oc2")),
                        "failing_values": failing_values(pred, pr.get("predicate_result") or {}, cps),
                        "evidence": str((u / pr["evidence_ref"]).relative_to(HERE)) if pr.get("evidence_ref") else None,
                        "classification": None,
                    })
    classification = load(HERE / CLASSIFICATION) or {}
    for r in rows:
        key = f"{r['subject']}/{r['case']}/{r['candidate_id']}"
        r["classification"] = classification.get(key)
    (HERE / f"{OUT_PREFIX}.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    lines = ["# M12 refuted candidates — DeepSeek run (auto-extracted sheet)", "",
             "| # | subject | case | candidate | kind/protocol | producer | observer | predicate | failing values | classification |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        pred = r["predicate"]
        pdesc = f"{pred.get('family')} {pred.get('operator', '')} " + (
            f"{pred.get('left', {}).get('role', '')} {pred.get('left', {}).get('path', '')}" if isinstance(pred.get("left"), dict) else "")
        if pred.get("family") == "P20":
            pdesc += f" proj={pred.get('projection')}"
        fv = json.dumps(r["failing_values"], ensure_ascii=False)
        c = r["classification"] or {}
        lines.append(f"| {i} | {r['subject']} | {r['case']} | {r['candidate_id']} | {r['contract_kind']}/{r['protocol']} | {r['producer']} | {r['consumer']} | {pdesc[:120]} | {fv[:220].replace('|', '/')} | {c.get('code', '')} {c.get('lead', '')} |")
    (HERE / f"{OUT_PREFIX}.md").write_text("\n".join(lines) + "\n")
    render_doc(rows)
    unclassified = [f"{r['subject']}/{r['case']}/{r['candidate_id']}" for r in rows if not r["classification"]]
    print(json.dumps({"refuted": len(rows), "by_subject": {s: sum(r["subject"] == s for r in rows) for s in ("conduit", "rwa")},
                      "unclassified": unclassified}))


CODE_LABEL = {"RD": "real defect (RD)", "RD?": "candidate wrong but exposes a defect (RD?)", "WH": "wrong hypothesis (WH)", "IP": "ill-posed instance (IP)"}


def render_doc(rows):
    """Review document for docs/design/cpv-expansion (regenerated on every run)."""
    from collections import Counter
    doc = REPO_DOC
    counts = Counter((r["subject"], (r["classification"] or {}).get("code", "unclassified")) for r in rows)
    lines = ["# Review of the M12-refuted candidates of the DeepSeek main line (2026-09-12)", "",
             f"Candidates that M12 judges refuted do not enter the M14 suite; when the application itself is defective, however, a correct candidate is exactly what gets \"refuted\" here. This table re-examines every refuted candidate of the DeepSeek main line ({RUNS_LABEL}).",
             "Method: author review drafted with AI assistance against the execution evidence (the actual before/after/producer requests and responses in `M12/<candidate>/execution_evidence.json`); not independent human labeling. The classification of every candidate (code, lead id, note) is embedded in `refuted-review-final.json` next to `review_refuted.py`, which generates the tables.", "",
             "Codes: RD = real application defect (consistent with a reproduced lead or self-evident from the evidence); RD? = the candidate's claim itself does not hold, but the observation exposes a defect that still needs a separate reproduction; WH = wrong hypothesis (the candidate was correctly refuted); IP = ill-posed plan instance (no effect to observe: neither a defect nor evaluable).", "",
             "## Summary", "", "| subject | RD | RD? | WH | IP | unclassified | total |", "|---|---:|---:|---:|---:|---:|---:|"]
    for subject in ("conduit", "rwa"):
        c = {k: counts.get((subject, k), 0) for k in ("RD", "RD?", "WH", "IP", "unclassified")}
        lines.append(f"| {subject} | {c['RD']} | {c['RD?']} | {c['WH']} | {c['IP']} | {c['unclassified']} | {sum(c.values())} |")
    lines += ["", "## Real defects and items awaiting reproduction", "", "| subject/case/candidate | lead | observation | evidence |", "|---|---|---|---|"]
    for r in rows:
        c = r["classification"] or {}
        if c.get("code") in ("RD", "RD?"):
            lines.append(f"| {r['subject']}/{r['case']}/{r['candidate_id']} | {c.get('lead') or '-'} | {c.get('note', '')} | `{r['evidence']}` |")
    lines += ["", "## All refuted candidates", "", "| # | subject/case/candidate | kind/plan | producer | observer | predicate | failing observation | code | note |", "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        pred = r["predicate"]
        pdesc = f"{pred.get('family')} {pred.get('operator', '')}"
        if isinstance(pred.get("left"), dict):
            pdesc += f" {pred['left'].get('role', '')} {pred['left'].get('path', '')}"
        if pred.get("family") == "P20":
            pdesc += f" projection {pred.get('projection')}"
        fv = json.dumps(r["failing_values"], ensure_ascii=False)[:160].replace("|", "/")
        c = r["classification"] or {}
        lines.append(f"| {i} | {r['subject']}/{r['case']}/{r['candidate_id']} | {r['contract_kind']}/{r['protocol']} | {r['producer']} | {r['consumer']} | {pdesc[:90].replace('|', '/')} | {fv} | {c.get('code', 'unclassified')} | {c.get('note', '')[:140].replace('|', '/')} |")
    lines += ["", f"Notes: run roots {RUNS_LABEL} (each case is taken from the first run whose union holds a complete M14 suite); the `evidence` paths are relative to `eval/ui_semantics/deepseek-full-20260912/`. The lead ids of RD items refer to DEFECTS.md; RD? items count as real defects only after a separate reproduction in a clean environment.", ""]
    doc.write_text("\n".join(lines))


REPO_DOC = HERE.parents[2] / "docs/design/cpv-expansion" / os.environ.get("REFUTED_DOC", "refuted-review-20260912.md")


if __name__ == "__main__":
    sys.exit(main())
