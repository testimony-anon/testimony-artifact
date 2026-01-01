"""Model-assisted initial review of business tests (RQ1), DeepSeek API, resumable, any subject list.

Parameterised copy of eval/ui_semantics/deepseek-full-20260912/rq1_review_deepseek.py.  The audit
directory, the subject list, the model and the reviewer label are configuration.  **The v2.1
system prompt below is a verbatim copy of the frozen one** (it is part of the research record);
tests/test_rq1_tools.py checks the two byte for byte.  A different prompt for a new subject must
be supplied explicitly through `review.system_prompt_file` together with `review.prompt_version`.

Reads <audit dir>/tests.jsonl (from rq1_extract.py), sends one packet per business-relation test
to the model (JSON mode) and appends {test_key, label C/E/U, reason, reviewer, prompt_sha256,
response} to reviews.jsonl.  The reviewer never sees the M14 verdict or any earlier label.

Usage: rq1_review_deepseek.py [--limit N] [--subject S] [--case C] [--workers N] [--dry-run]
Environment for a real run: LLM_BASE_URL, LLM_API_KEY.  --dry-run makes no request and writes
nothing; it reports how many packets would be sent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rq1_config import add_common_args, fail, jsonl, load_config  # noqa: E402

PROMPT_VERSION = "v2.1"
DEFAULT_REVIEWER_DATE = "2026-09-12"

# --- frozen prompt v2.1, byte-identical to the eval/ copy; do not edit -------------------------
SYSTEM = (
    "You review one automatically generated API regression test for a web application "
    "(Conduit: a Medium-like blogging API; RWA: the Cypress Real World App payment API). "
    "The test replays exactly the recorded scenario (same users, same data volume, same request parameters, "
    "no interleaved traffic) and then evaluates one business assertion on the observed responses. "
    "The calls listed in the evidence were actually executed in that scenario and returned the bodies shown "
    "(excerpts may be truncated; secrets are redacted). "
    "Judge whether the asserted relation is a correct business rule of this application as instantiated in the "
    "recorded scenario. Ignore whether the assertion happened to pass. "
    "C = the relation follows from the application's business logic given the scenario's preconditions "
    "(for example a result set that fits within one page, or a read repeated with no intervening write); a true but "
    "weaker property (multiset instead of ordered equality) is still C; the test would catch a real deviation. "
    "E = the assertion is semantically wrong for this scenario, contradicts the evidence, or equates quantities that "
    "merely happen to coincide (an accidental value with no business reason). "
    "U = the evidence given is insufficient to decide. "
    "Do not label E only because the rule would fail under a different data volume, pagination window, or concurrent "
    "traffic that the scenario does not contain, and do not assume the generic RealWorld or Cypress specification where "
    "the recorded evidence shows how this implementation actually behaves. "
    "Identifiers in request paths and bodies are the fresh values used at replay time, while response bodies show the "
    "corresponding recorded identifiers; alias_pairs_fresh_to_recorded lists which fresh id denotes which recorded id, "
    "and request_body_recorded_domain gives each request body with the recorded identifiers. A fresh id and its "
    "recorded alias denote the same resource; never treat that difference as a mismatch. "
    "Answer strictly as JSON: {\"label\": \"C\"|\"E\"|\"U\", \"reason\": \"<one or two sentences>\"}."
)
# --- end frozen prompt ------------------------------------------------------------------------


def resolve_prompt(cfg) -> tuple[str, str, str]:
    """(system prompt, prompt version, reviewer label) from the configuration."""
    review = cfg.review or {}
    model = review.get("model") or "deepseek-flash"
    version = review.get("prompt_version")
    system = SYSTEM
    if review.get("system_prompt_file"):
        p = Path(review["system_prompt_file"])
        p = p if p.is_absolute() else cfg.repo / p
        if not p.exists():
            fail(f"review.system_prompt_file not found: {p}")
        if not version:
            fail("review.system_prompt_file is set but review.prompt_version is not; "
                 "a replaced prompt must carry its own version label")
        system = p.read_text()
    version = version or PROMPT_VERSION
    reviewer = review.get("reviewer") or (
        f"{model}/reasoning_effort=medium (model-assisted initial review, prompt {version}, "
        f"{review.get('reviewer_date') or DEFAULT_REVIEWER_DATE})")
    return system, version, reviewer


def packet(t: dict) -> str:
    return json.dumps({
        "subject": t["subject"], "case": t["case_id"], "protocol": t["protocol"], "claim_kind": t["claim_kind"],
        "business_summary": t["business_summary"], "predicate": t["predicate"],
        "producer_call": t["producer_call"], "producer_request_body": t["producer_request_body"],
        "before_call": t["before_call"], "before_body_excerpt": t["before_body_excerpt"],
        "after_call": t["after_call"] if t["after_call"] != "-" else t["observation_call"],
        "after_body_excerpt": t["after_body_excerpt"],
        "executed_calls_in_order": t.get("calls"),
        "alias_pairs_fresh_to_recorded": t.get("alias_pairs_fresh_to_recorded"),
        "producer_request_body_recorded_domain": t.get("producer_request_body_recorded_domain"),
        "rejection_evidence": t.get("rejection"),
    }, ensure_ascii=False)


def ask(text: str, system: str, model: str) -> dict:
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    body = {"model": model, "reasoning_effort": "medium", "temperature": 0.1,
            "response_format": {"type": "json_object"}, "max_tokens": 16000,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                envelope = json.loads(resp.read().decode())
            choice = envelope["choices"][0]
            content = choice["message"].get("content") or ""
            if not content.strip():
                raise ValueError(f"empty content (finish_reason={choice.get('finish_reason')})")
            answer = json.loads(content)
            if answer.get("label") in ("C", "E", "U") and isinstance(answer.get("reason"), str):
                return {"answer": answer, "usage": envelope.get("usage"), "raw_sha256": hashlib.sha256(content.encode()).hexdigest()}
            raise ValueError("malformed review answer")
        except Exception as exc:  # retry transient/malformed
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 3:
                raise RuntimeError(last_error)
            time.sleep(3 * (attempt + 1))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int); ap.add_argument("--subject"); ap.add_argument("--case")
    ap.add_argument("--workers", type=int, default=1, help="parallel API calls (single writer thread appends the rows)")
    ap.add_argument("--dry-run", action="store_true", help="count the packets that would be sent; no request, no write")
    add_common_args(ap)
    args = ap.parse_args(argv[1:])
    cfg = load_config(args)
    AUDIT = cfg.audit_dir
    system, version, reviewer = resolve_prompt(cfg)
    model = (cfg.review or {}).get("model") or "deepseek-flash"

    if args.subject and args.subject not in cfg.subject_ids:
        fail(f"--subject {args.subject} is not in the configured subject list {cfg.subject_ids}")
    tests_path = AUDIT / "tests.jsonl"
    if not tests_path.exists():
        fail(f"no tests.jsonl in {AUDIT} (run rq1_extract.py first)")
    known = set(cfg.subject_ids)
    tests = [t for t in jsonl(tests_path) if t["subject"] in known]
    out = AUDIT / "reviews.jsonl"
    done = {r["test_key"] for r in jsonl(out)}
    todo = [t for t in tests if t["layer"] == "business_relation" and t["test_key"] not in done
            and (not args.subject or t["subject"] == args.subject) and (not args.case or t["case_id"] == args.case)]
    if args.limit:
        todo = todo[: args.limit]

    if args.dry_run:
        packets = [packet(t) for t in todo]
        print(json.dumps({
            "dry_run": True, "audit_dir": cfg.rel(AUDIT), "model": model, "prompt_version": version,
            "reviewer": reviewer, "system_prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
            "business_tests": sum(t["layer"] == "business_relation" for t in tests),
            "already_reviewed": len(done), "would_send": len(todo),
            "by_subject": dict(Counter(t["subject"] for t in todo)),
            "prompt_chars_total": sum(len(system) + len(p) for p in packets),
            "sample": [{"test_key": t["test_key"],
                        "prompt_sha256": hashlib.sha256((system + p).encode()).hexdigest()}
                       for t, p in list(zip(todo, packets))[:3]],
        }, ensure_ascii=False))
        return 0

    cfg.guard_audit_dir()
    for var in ("LLM_BASE_URL", "LLM_API_KEY"):
        if not os.environ.get(var):
            fail(f"{var} is not set (use --dry-run to plan without calling the API)")
    print(json.dumps({"business_tests": sum(t["layer"] == "business_relation" for t in tests), "already_reviewed": len(done), "to_review": len(todo)}), flush=True)
    usage_total = {"prompt": 0, "completion": 0}

    def review_one(t):
        text = packet(t)
        try:
            return t, text, ask(text, system, model), None
        except Exception as exc:  # recorded by the writer; failures are re-tried by a later invocation
            return t, text, None, exc

    from concurrent.futures import ThreadPoolExecutor
    with out.open("a") as stream, ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, (t, text, result, error) in enumerate(pool.map(review_one, todo), 1):
            if error is not None:
                with (AUDIT / "review-failures.jsonl").open("a") as failures:
                    failures.write(json.dumps({"test_key": t["test_key"], "error": str(error), "failed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
                print(json.dumps({"failed": t["test_key"], "error": str(error)[:200]}), flush=True)
                continue
            row = {"test_key": t["test_key"], "subject": t["subject"], "case_id": t["case_id"], "candidate_id": t["candidate_id"],
                   "label": result["answer"]["label"], "reason": result["answer"]["reason"], "reviewer": reviewer, "prompt_version": version,
                   "prompt_sha256": hashlib.sha256((system + text).encode()).hexdigest(), "response_sha256": result["raw_sha256"],
                   "usage": result["usage"], "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            stream.write(json.dumps(row, ensure_ascii=False) + "\n"); stream.flush()
            u = result["usage"] or {}
            usage_total["prompt"] += u.get("prompt_tokens", 0) or 0; usage_total["completion"] += u.get("completion_tokens", 0) or 0
            if i % 20 == 0 or i == len(todo):
                print(json.dumps({"reviewed": i, "of": len(todo), "last": (t["test_key"], row["label"]), "usage": usage_total}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
