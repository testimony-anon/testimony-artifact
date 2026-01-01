"""Model-assisted main-target determination per case (RQ1 K/N_API), DeepSeek API, resumable, any subjects.

Parameterised copy of eval/ui_semantics/deepseek-full-20260912/rq1_targets_deepseek.py.  The audit
directory, the subject list, the goal list (`scopes.jsonl`), the model and the reviewer label are
configuration.  **The goal-coverage system prompt below is a verbatim copy of the frozen one**
(part of the research record); tests/test_rq1_tools.py checks the two byte for byte.

For every case whose scope is api/mixed in the goal list, the C-labeled business tests of the final
suite (tests-labeled.jsonl from rq1_summarize_deepseek.py) are shown to the model, which maps goals
to the tests that verify them.  Output: <audit dir>/targets.jsonl rows {subject, case_id, scope,
goals, covered_goals, has_correct_target, reason, reviewer, prompt_sha256, response_sha256}.  Cases
without any C test get has_correct_target=false without a call.

A missing goal list is a hard error (a new subject has no goal list until one is written by hand):
pass --skip-missing-scopes to exit cleanly with a note instead of producing empty coverage.

Usage: rq1_targets_deepseek.py [--workers N] [--subject S] [--case C] [--dry-run]
Environment for a real run: LLM_BASE_URL, LLM_API_KEY.
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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rq1_config import add_common_args, fail, jsonl, load_config  # noqa: E402

DEFAULT_REVIEWER_DATE = "2026-09-12"
PROMPT_VERSION = "v2"

# --- frozen goal-coverage prompt v2, byte-identical to the eval/ copy; do not edit -------------
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
# --- end frozen prompt ------------------------------------------------------------------------


def resolve_prompt(cfg) -> tuple[str, str]:
    """(system prompt, reviewer label) from the configuration."""
    conf = cfg.targets or {}
    model = conf.get("model") or "deepseek-flash"
    system = SYSTEM
    version = conf.get("prompt_version") or PROMPT_VERSION
    if conf.get("system_prompt_file"):
        p = Path(conf["system_prompt_file"])
        p = p if p.is_absolute() else cfg.repo / p
        if not p.exists():
            fail(f"targets.system_prompt_file not found: {p}")
        if not conf.get("prompt_version"):
            fail("targets.system_prompt_file is set but targets.prompt_version is not; "
                 "a replaced prompt must carry its own version label")
        system = p.read_text()
    reviewer = conf.get("reviewer") or (
        f"{model}/reasoning_effort=medium (model-assisted goal-coverage mapping {version}, "
        f"{conf.get('reviewer_date') or DEFAULT_REVIEWER_DATE})")
    return system, reviewer


def goal_ids(goals):
    """Stable ids for a case's goals: keep a leading code like CA1/RB2/RP10, otherwise G<n>."""
    out = []
    for n, g in enumerate(goals, 1):
        head = g.split(" ")[0]
        out.append(head if re.fullmatch(r"[A-Z]+[0-9]+", head) else f"G{n}")
    return out


def lines(p: Path):
    return jsonl(p)


def ask(text: str, system: str, model: str) -> dict:
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    body = {"model": model, "reasoning_effort": "medium", "temperature": 0.1, "response_format": {"type": "json_object"},
            "max_tokens": 16000, "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}
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


def plan(cfg, args, labeled, ready, done):
    """(todo packets, rule-decided rows, skipped count) for the cases still to judge."""
    todo, rows_now, skipped = [], [], 0
    known = set(cfg.subject_ids)
    for sc in lines(cfg.scopes):
        if sc["subject"] not in known:
            continue
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
    return todo, rows_now, skipped


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--subject"); ap.add_argument("--case")
    ap.add_argument("--dry-run", action="store_true", help="count the packets that would be sent; no request, no write")
    ap.add_argument("--skip-missing-scopes", action="store_true",
                    help="exit 0 with a note when the goal list does not exist, instead of failing")
    add_common_args(ap)
    args = ap.parse_args(argv[1:])
    cfg = load_config(args)
    AUDIT = cfg.audit_dir
    system, reviewer = resolve_prompt(cfg)
    model = (cfg.targets or {}).get("model") or "deepseek-flash"

    if args.subject and args.subject not in cfg.subject_ids:
        fail(f"--subject {args.subject} is not in the configured subject list {cfg.subject_ids}")
    if not cfg.scopes.exists():
        message = (f"goal list not found: {cfg.scopes}. A new subject needs one row per case "
                   "{subject, case_id, scope, goals} before K/N_API can be judged.")
        if args.skip_missing_scopes:
            print(json.dumps({"skipped": True, "reason": message, "note": "no primary-effect list, so targets.jsonl is not produced for this round"}, ensure_ascii=False))
            return 0
        fail(message)

    labeled = lines(AUDIT / "tests-labeled.jsonl")
    if not labeled:
        fail(f"no tests-labeled.jsonl in {AUDIT} (run rq1_summarize_deepseek.py first)")
    # only cases whose final suite is complete and exported (or complete_empty) can be judged
    ready = {(c["subject"], c["case_id"]) for c in lines(AUDIT / "cases.jsonl")
             if c.get("status") not in (None, "no_complete_run") and (c.get("exported") or c.get("status") == "complete_empty")}
    out = AUDIT / "targets.jsonl"
    done = {(r["subject"], r["case_id"]) for r in lines(out)}
    todo, rows_now, skipped = plan(cfg, args, labeled, ready, done)

    if args.dry_run:
        print(json.dumps({
            "dry_run": True, "audit_dir": cfg.rel(AUDIT), "scopes": cfg.rel(cfg.scopes), "model": model,
            "reviewer": reviewer, "system_prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
            "api_cases_pending": len(todo) + len(rows_now), "would_send": len(todo),
            "decided_by_rule_no_C_test": len(rows_now), "already_done": len(done), "not_ready_skipped": skipped,
            "by_subject": dict(Counter(b["subject"] for b, _, _ in todo)),
            "prompt_chars_total": sum(len(system) + len(p) for _, p, _ in todo),
            "sample": [{"case": f"{b['subject']}/{b['case_id']}", "goals": len(b["goals"]), "correct_tests": b["correct_tests"],
                        "prompt_sha256": hashlib.sha256((system + p).encode()).hexdigest()} for b, p, _ in todo[:3]],
        }, ensure_ascii=False))
        return 0

    cfg.guard_audit_dir()
    for var in ("LLM_BASE_URL", "LLM_API_KEY"):
        if not os.environ.get(var):
            fail(f"{var} is not set (use --dry-run to plan without calling the API)")
    print(json.dumps({"api_cases_pending": len(todo) + len(rows_now), "already_done": len(done), "not_ready_skipped": skipped}), flush=True)

    def one(item):
        base, packet, keys = item
        try:
            return base, packet, keys, ask(packet, system, model), None
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
                   "reviewer": reviewer, "prompt_sha256": hashlib.sha256((system + packet).encode()).hexdigest(),
                   "response_sha256": result["raw_sha256"], "usage": result["usage"], "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            stream.write(json.dumps(row, ensure_ascii=False) + "\n"); stream.flush()
            print(json.dumps({"case": f"{base['subject']}/{base['case_id']}", "coverage": {g: c["coverage"] for g, c in coverage.items()}}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
