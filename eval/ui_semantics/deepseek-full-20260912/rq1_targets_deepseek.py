"""Model-assisted main-target determination per case (RQ1 K/N_API), DeepSeek API, resumable.

For every case whose Astra-round scope is api/mixed (docs/design/cpv-expansion/rq1-audit/scopes.jsonl, the fixed
goal list of the 83 inputs), the C-labeled business tests of the final DeepSeek suite (tests-labeled.jsonl from
rq1_summarize_deepseek.py) are shown to deepseek-flash, which maps goals to the tests that verify them.
Output: rq1-audit-deepseek/targets.jsonl rows {subject, case_id, scope, goals, covered_goals, has_correct_target,
reason, reviewer, prompt_sha256, response_sha256}.  Cases without any C test get has_correct_target=false without a call.
Usage: rq1_targets_deepseek.py [--workers N] [--subject S] [--case C]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AUDIT = Path(os.environ.get("RQ1_AUDIT_DIR") or REPO / "docs/design/cpv-expansion/rq1-audit-deepseek")
SCOPES = REPO / "docs/design/cpv-expansion/rq1-audit/scopes.jsonl"
MODEL = "deepseek-flash"
REVIEWER = f"{MODEL}/reasoning_effort=medium (model-assisted goal-coverage mapping v2, 2026-09-12)"
SYSTEM = (
    "You map the business goals of one recorded UI scenario to the automatically generated API regression tests that "
    "verify them. Each goal is a short Chinese phrase with an id (e.g. CA1) and may list several effects. Each test is a "
    "business assertion already judged a correct rule for this scenario; you only decide which goal effects it verifies. "
    "For every goal report coverage: full = every effect the goal lists is checked by some test (a test checks an effect "
    "when its assertion would fail if the application violated that effect, not merely because it issues a related call); "
    "partial = at least one but not all listed effects are checked; none = no listed effect is checked. Answer strictly as JSON: "
    "{\"goals\": {\"<goal id>\": {\"coverage\": \"full\"|\"partial\"|\"none\", \"tests\": [\"<test_key>\", ...], "
    "\"note\": \"<which effects are checked or missing>\"}}, \"reason\": \"<one or two sentences>\"}; "
    "list every goal id given; use only the test_keys given."
)


def goal_ids(goals):
    """Stable ids for a case's goals: keep a leading code like CA1/RB2/RP10, otherwise G<n>."""
    out = []
    for n, g in enumerate(goals, 1):
        head = g.split(" ")[0]
        out.append(head if re.fullmatch(r"[A-Z]+[0-9]+", head) else f"G{n}")
    return out


def lines(p: Path):
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def ask(text: str) -> dict:
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    body = {"model": MODEL, "reasoning_effort": "medium", "temperature": 0.1, "response_format": {"type": "json_object"},
            "max_tokens": 16000, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                envelope = json.loads(resp.read().decode())
            content = (envelope["choices"][0]["message"].get("content") or "").strip()
            if not content:
                raise ValueError("empty content")
            answer = json.loads(content)
            if isinstance(answer.get("goals"), dict) and isinstance(answer.get("reason"), str):
                return {"answer": answer, "usage": envelope.get("usage"), "raw_sha256": hashlib.sha256(content.encode()).hexdigest()}
            raise ValueError("malformed answer")
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt == 3:
                raise RuntimeError(last)
            time.sleep(3 * (attempt + 1))


def main(argv):
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--subject"); ap.add_argument("--case")
    args = ap.parse_args(argv[1:])
    labeled = lines(AUDIT / "tests-labeled.jsonl")
    # only cases whose final suite is complete and exported (or complete_empty) can be judged
    ready = {(c["subject"], c["case_id"]) for c in lines(AUDIT / "cases.jsonl")
             if c.get("status") not in (None, "no_complete_run") and (c.get("exported") or c.get("status") == "complete_empty")}
    out = AUDIT / "targets.jsonl"
    done = {(r["subject"], r["case_id"]) for r in lines(out)}
    todo, rows_now, skipped = [], [], 0
    for sc in lines(SCOPES):
        key = (sc["subject"], sc["case_id"])
        if key in done or sc["scope"] not in ("api", "mixed") or (args.subject and sc["subject"] != args.subject) or (args.case and sc["case_id"] != args.case):
            continue
        if key not in ready:
            skipped += 1
            continue
        tests = [t for t in labeled if t["subject"] == sc["subject"] and t["case_id"] == sc["case_id"] and t["layer"] == "business_relation" and t.get("label") == "C"]
        base = {"subject": sc["subject"], "case_id": sc["case_id"], "scope": sc["scope"], "goals": sc["goals"], "correct_tests": len(tests)}
        if not tests:
            rows_now.append({**base, "goal_coverage": {gid: {"coverage": "none", "tests": [], "note": "", "text": g} for gid, g in zip(goal_ids(sc["goals"]), sc["goals"])},
                             "covered_goals": {}, "has_correct_target": False, "reason": "no business test of this case is labeled C", "reviewer": "rule"})
            continue
        packet = json.dumps({"subject": sc["subject"], "case": sc["case_id"],
                             "goals": [{"id": gid, "text": g} for gid, g in zip(goal_ids(sc["goals"]), sc["goals"])],
                             "tests": [{"test_key": t["test_key"], "protocol": t["protocol"], "summary": t.get("business_summary"),
                                        "producer_call": t.get("producer_call"), "after_call": t.get("after_call") if t.get("after_call") != "-" else t.get("observation_call"),
                                        "calls": [{k: c.get(k) for k in ("checkpoint", "method", "path", "query", "status")} for c in (t.get("calls") or [])]} for t in tests]},
                            ensure_ascii=False)
        todo.append((base, packet, {t["test_key"] for t in tests}))
    print(json.dumps({"api_cases_pending": len(todo) + len(rows_now), "already_done": len(done), "not_ready_skipped": skipped}), flush=True)

    def one(item):
        base, packet, keys = item
        try:
            return base, packet, keys, ask(packet), None
        except Exception as exc:
            return base, packet, keys, None, exc

    with out.open("a") as stream, ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for row in rows_now:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n"); stream.flush()
        for base, packet, keys, result, error in pool.map(one, todo):
            if error is not None:
                print(json.dumps({"failed": f"{base['subject']}/{base['case_id']}", "error": str(error)[:200]}), flush=True)
                continue
            coverage = {}
            for gid, text in zip(goal_ids(base["goals"]), base["goals"]):
                a = result["answer"]["goals"].get(gid) or {}
                tests_ = [k for k in (a.get("tests") or []) if k in keys]
                level = a.get("coverage") if a.get("coverage") in ("full", "partial", "none") else "none"
                if level != "none" and not tests_:
                    level = "none"
                coverage[gid] = {"coverage": level, "tests": tests_, "note": str(a.get("note") or "")[:400], "text": text}
            covered = {g: c["tests"] for g, c in coverage.items() if c["coverage"] != "none"}
            row = {**base, "goal_coverage": coverage, "covered_goals": covered, "has_correct_target": bool(covered), "reason": result["answer"]["reason"],
                   "reviewer": REVIEWER, "prompt_sha256": hashlib.sha256((SYSTEM + packet).encode()).hexdigest(),
                   "response_sha256": result["raw_sha256"], "usage": result["usage"], "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            stream.write(json.dumps(row, ensure_ascii=False) + "\n"); stream.flush()
            print(json.dumps({"case": f"{base['subject']}/{base['case_id']}", "coverage": {g: c["coverage"] for g, c in coverage.items()}}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
