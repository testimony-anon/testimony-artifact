"""Model-assisted initial review of *structural constraints* (RQ1, assertion layer basic_constraint).

Companion of rq1_review_deepseek.py, which reviews the business-relation layer.  The client, the
concurrency, the retry policy and the record format are the same; what differs is the review object
(the 1,580 ``layer == "basic_constraint"`` rows of the five subjects, all of them single-response
V2 reads) and therefore the criterion, so this tool carries **its own prompt and its own version
label** (``structural-v1.0``, full text in prompts/structural_review_v1.0.md).

It never touches the frozen audit artefacts: it reads <audit dir>/tests.jsonl and *appends* to the
new files structural-reviews.jsonl / structural-review-failures.jsonl (the only files it opens for
writing; see WRITABLE below).  Rows carry the same fields as reviews.jsonl
(test_key, subject, case_id, candidate_id, label, reason, reviewer, prompt_version, prompt_sha256,
response_sha256, usage, reviewed_at) plus ``predicate_family`` for the per-family breakdown.

Each packet restates, from the untruncated response body in the M12 execution evidence, the facts
the predicate talks about (``observed``), so a truncated excerpt never hides the asserted value.

Usage (from the repository root, with LLM_BASE_URL / LLM_API_KEY in the environment)::

    set -a; set +a
    PY=.venv/bin/python
    # Conduit + RWA (audit dir lives under the protected docs/design/cpv-expansion tree, and the
    # tool only ever creates new files there, so the guard is waived explicitly):
    $PY scripts/experiments/rq1_tools/rq1_review_structural.py \
        --config scripts/experiments/rq1_tools/configs/conduit-rwa.json \
        --allow-frozen-audit-dir --workers 8
    # one of the three added subjects:
    $PY scripts/experiments/rq1_tools/rq1_review_structural.py \
        --config scripts/experiments/rq1_tools/configs/ghost-20260921.json --workers 8

``--dry-run`` plans without calling the API; ``--limit N`` / ``--subject S`` / ``--case C`` restrict
the batch; re-running resumes (rows already in structural-reviews.jsonl are skipped).
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
from rq1_config import add_common_args, fail, jsonl, load_config, load_helpers  # noqa: E402

PROMPT_VERSION = "structural-v1.0"
DEFAULT_PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "structural_review_v1.0.md"
DEFAULT_REVIEWER_DATE = "2026-09-21"
LAYER = "basic_constraint"

# The only files this tool may create or append to, inside the audit directory.  Everything else
# there (tests.jsonl, reviews.jsonl, main-review.jsonl, tests-labeled.jsonl, summary.md, ...) is a
# frozen source of the paper's numbers and is opened read-only.
WRITABLE = ("structural-reviews.jsonl", "structural-review-failures.jsonl", "structural-summary.md")

# Pinned versions of the subjects, given to the reviewer so it can reason about the actual code.
APPLICATIONS = {
    "conduit": "Conduit, the RealWorld (Medium-like) blogging API; implementation "
               "TonyMckes/conduit-realworld-example-app at commit 5e127d8 (Express + Sequelize + PostgreSQL).",
    "rwa": "RWA, the Cypress Real World App payment API; cypress-io/cypress-realworld-app at commit "
           "bdf6169 (Express backend over a lowdb JSON database).",
    "umami": "Umami 3.4.0 (commit ec0ff50), a self-hosted web analytics application; Next.js API routes, "
             "Prisma over PostgreSQL.",
    "paperless": "Paperless-ngx 3.2.0 (commit 961f018), a document management system; Django REST Framework "
                 "API over PostgreSQL.",
    "ghost": "Ghost 5.130.6 (commit a07c753), a publishing platform; its Admin API (/ghost/api/admin/...) "
             "and Content API, Express + Bookshelf/Knex over SQLite.",
}

MISSING = object()
# Sensitive captured values are replaced in the persisted bodies by this sentinel object
# (src/ui_semantics/route_s_capture_redaction.py); it carries the original JSON type, which is what
# a type or presence constraint is really about.
SENTINEL_KEY = "$route_s_redacted"


# --- reading the observed facts out of the evidence -------------------------------------------

def redaction(value):
    """The sentinel payload when ``value`` is a redacted capture, else None."""
    if isinstance(value, dict) and set(value) == {SENTINEL_KEY}:
        return value[SENTINEL_KEY] if isinstance(value[SENTINEL_KEY], dict) else {}
    return None

def jget(value, path):
    """Resolve a minimal JSONPath ($, $.a.b, $.a[0]); MISSING when the path does not resolve."""
    if path in (None, "", "$"):
        return value
    cur = value
    for part in [p for p in str(path).replace("$", "", 1).replace("[", ".").replace("]", "").split(".") if p]:
        if isinstance(cur, list) and part.lstrip("-").isdigit():
            index = int(part)
            if index >= len(cur) or index < -len(cur):
                return MISSING
            cur = cur[index]
        elif isinstance(cur, dict):
            if part not in cur:
                return MISSING
            cur = cur[part]
        else:
            return MISSING
    return cur


def jtype(value) -> str:
    if value is MISSING:
        return "absent"
    sentinel = redaction(value)
    if sentinel is not None:
        return f"{sentinel.get('original_json_type') or 'unknown'} (value redacted)"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def preview(value, limit=220):
    if value is MISSING:
        return None
    sentinel = redaction(value)
    if sentinel is not None:
        return f"<redacted {sentinel.get('category') or ''} value, original JSON type " \
               f"{sentinel.get('original_json_type') or 'unknown'}>"
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "…"


def at(body, path, limit=220) -> dict:
    value = jget(body, path)
    out = {"path": path, "resolves": value is not MISSING, "json_type": jtype(value), "value": preview(value, limit)}
    if redaction(value) is not None:
        out["redacted"] = True
        return out
    if isinstance(value, list):
        out["size"] = len(value)
    elif isinstance(value, str):
        out["length"] = len(value)
    elif isinstance(value, dict):
        out["keys"] = sorted(value)[:25]
    return out


def collection_facts(body, spec: dict, identity_paths=None) -> dict:
    """Size, member shape and (for a uniqueness identity) the distinct identity tuples."""
    path = (spec or {}).get("path", "$")
    value = jget(body, path)
    facts = at(body, path)
    if not isinstance(value, list):
        return facts
    member_types = sorted({jtype(m) for m in value})
    facts["member_json_types"] = member_types
    keys = []
    for member in value[:3]:
        if isinstance(member, dict):
            keys.extend(k for k in member if k not in keys)
    if keys:
        facts["member_keys_first_3"] = keys[:30]
    facts["members_preview"] = [preview(m, 160) for m in value[:3]]
    if identity_paths:
        tuples = [tuple(preview(jget(m, p), 80) for p in identity_paths) for m in value]
        facts["identity_paths"] = list(identity_paths)
        facts["identity_values"] = [list(x) for x in tuples[:8]]
        facts["distinct_identity_values"] = len(set(tuples))
        facts["duplicate_identity_values_in_this_response"] = len(tuples) - len(set(tuples))
    return facts


def observed_facts(test: dict, body, query: dict | None) -> dict:
    """Restate, from the untruncated response body, the facts the predicate talks about."""
    pred = test.get("predicate") or {}
    family = pred.get("family")
    out: dict = {"family": family, "response_json_type": jtype(body)}
    notes = []
    if isinstance(body, dict):
        out["response_top_level_keys"] = sorted(body)[:40]
    if body is MISSING or body is None:
        notes.append("the evidence holds no JSON response body for this read")

    if family in ("P01", "P21", "P10", "P03"):
        out["target"] = at(body, (pred.get("target") or {}).get("path", "$"), 400)
        if family == "P21":
            out["expected_type"] = pred.get("expected_type")
        if family == "P03":
            out["range"] = {"lower": (pred.get("lower") or {}).get("value"), "upper": (pred.get("upper") or {}).get("value"),
                            "domain": pred.get("domain")}
        if family == "P10":
            out["format"] = pred.get("format") or pred.get("pattern")
        if family == "P01":
            out["operator"] = pred.get("operator")
            out["absent_statuses"] = pred.get("absent_statuses")
    elif family == "P02":
        out["left"] = at(body, (pred.get("left") or {}).get("path", "$"), 400)
        right = pred.get("right") or {}
        out["operator"] = pred.get("operator")
        if right.get("source") == "hypothesis":
            out["right"] = {"source": "frozen hypothesis literal", "value": preview(right.get("value"), 220)}
        elif right.get("source") == "role":
            out["right"] = {"source": "same response", **at(body, (right.get("ref") or {}).get("path", "$"), 220)}
        else:
            ref = right.get("ref") or {}
            out["right"] = {"source": "this request", "location": ref.get("location"), "path": ref.get("path"),
                            "value": preview(jget(query or {}, ref.get("path", "$")), 220)}
    elif family == "P11":
        out["collection"] = collection_facts(body, pred.get("collection"))
        right = pred.get("right") or {}
        out["operator"] = pred.get("operator")
        if right.get("source") == "request":
            ref = right.get("ref") or {}
            value = jget(query or {}, ref.get("path", "$"))
            out["right"] = {"source": "this request", "location": ref.get("location"), "path": ref.get("path"),
                            "value": preview(value, 80)}
            if value is MISSING:
                notes.append("the named request parameter is not present in this request's query")
        elif right.get("source") == "role":
            out["right"] = {"source": "same response", **at(body, (right.get("ref") or {}).get("path", "$"), 120)}
        else:
            out["right"] = {"source": "frozen hypothesis literal", "value": preview(right.get("value"), 80)}
    elif family == "P13":
        member = pred.get("member") or {}
        out["collection"] = collection_facts(body, pred.get("collection"),
                                             (pred.get("identity") or {}).get("paths"))
        out["operator"] = pred.get("operator")
        out["member"] = {"source": member.get("source"), "value": preview(member.get("value"), 220)}
    elif family == "P15":
        out["collection"] = collection_facts(body, pred.get("collection"),
                                             (pred.get("identity") or {}).get("paths") or ["$"])
        out["identity_semantics"] = (pred.get("identity") or {}).get("semantics")
        out["scope"] = pred.get("scope")
    elif family == "forall":
        inner = pred.get("body") or {}
        out["collection"] = collection_facts(body, pred.get("collection"),
                                             (inner.get("identity") or {}).get("paths") if inner.get("family") == "P15" else None)
        out["scope"] = pred.get("scope")
        out["item_guard"] = pred.get("item_guard")
        out["item_predicate_family"] = inner.get("family")
        members = jget(body, (pred.get("collection") or {}).get("path", "$"))
        item_path = ((inner.get("target") or inner.get("left") or inner.get("collection") or {}).get("path")) or "$"
        if isinstance(members, list):
            values = [jget(m, item_path) for m in members]
            out["item_values"] = {"path_in_member": item_path,
                                  "json_types": sorted({jtype(v) for v in values}),
                                  "first_5": [preview(v, 120) for v in values[:5]]}
    else:
        out["target"] = at(body, ((pred.get("target") or pred.get("collection") or pred.get("left") or {}).get("path")) or "$", 400)
        notes.append(f"unhandled predicate family {family!r}; only the raw predicate and the body are given")

    if notes:
        out["note"] = "; ".join(notes)
    return out


def read_observation(test: dict, helpers, cache: dict):
    """(untruncated response body, query) of this test's single read, from the M12 evidence."""
    ref = test.get("source_evidence_ref")
    if not ref:
        return MISSING, None
    path = Path(ref)
    if path not in cache:
        try:
            cache[path] = json.loads(path.read_text()) if path.exists() else {}
        except Exception:
            cache[path] = {}
    evidence = cache[path]
    cps = helpers.checkpoints(evidence.get("protocol") or {})
    step = helpers.pick(cps, "observation", "observations[0]", "after", "Ot1", "Oc2")
    if step is None:
        candidates = [v for k, v in cps.items() if k not in ("reset", "setup") and not k.startswith("setup")]
        step = candidates[0] if len(candidates) == 1 else None
    if step is None:
        return MISSING, ((test.get("calls") or [{}])[0].get("query"))
    query = step.get("query") or ((test.get("calls") or [{}])[0].get("query"))
    return (step.get("body") if step.get("body") is not None else None), query


# --- the packet, the request and the run -------------------------------------------------------

def packet(test: dict, helpers, cache: dict) -> str:
    body, query = read_observation(test, helpers, cache)
    call = (test.get("calls") or [{}])[0]
    return json.dumps({
        "application": APPLICATIONS.get(test["subject"], test["subject"]),
        "subject": test["subject"], "case": test["case_id"],
        "read": {"actor": call.get("actor"), "method": call.get("method"), "path": call.get("path"),
                 "query": query, "status": call.get("status")},
        "constraint_summary": test.get("business_summary"),
        "predicate": test.get("predicate"),
        "observed": observed_facts(test, body, query if isinstance(query, dict) else {}),
        "response_body_excerpt": json.dumps(body, ensure_ascii=False, sort_keys=True)[:2000] if body is not MISSING else None,
    }, ensure_ascii=False)


def resolve_prompt(cfg, prompt_file: str | None) -> tuple[str, str, str]:
    """(system prompt, prompt version, reviewer label); the prompt always comes from a file."""
    review = cfg.review or {}
    model = review.get("model") or "deepseek-flash"
    path = Path(prompt_file or review.get("structural_prompt_file") or DEFAULT_PROMPT_FILE)
    if not path.is_absolute():
        path = cfg.repo / path
    if not path.exists():
        fail(f"structural review prompt not found: {path}")
    version = review.get("structural_prompt_version") or PROMPT_VERSION
    # ``review.reviewer_date`` belongs to the frozen business review of that configuration (2026-09-12
    # for conduit-rwa.json) and must not leak into this round's label.
    reviewer = review.get("structural_reviewer") or (
        f"{model}/reasoning_effort=medium (model-assisted initial review of structural constraints, "
        f"prompt {version}, {review.get('structural_reviewer_date') or DEFAULT_REVIEWER_DATE})")
    return path.read_text(), version, reviewer


def summarize(cfg, tests: list, version: str, reviewer: str, system: str) -> str:
    """structural-summary.md: counts, per-family breakdown and the E/U items with their reasons."""
    AUDIT = cfg.audit_dir
    rows = jsonl(AUDIT / "structural-reviews.jsonl")
    by_key = {t["test_key"]: t for t in tests}
    rows = [r for r in rows if r["test_key"] in by_key]
    structural = [t for t in tests if t["layer"] == LAYER]
    subjects = [s for s in cfg.subject_ids if any(t["subject"] == s for t in structural)]
    usage = Counter()
    for r in rows:
        u = r.get("usage") or {}
        usage["prompt"] += u.get("prompt_tokens", 0) or 0
        usage["completion"] += u.get("completion_tokens", 0) or 0
        usage["cache_hit"] += u.get("prompt_cache_hit_tokens", 0) or 0
        usage["cache_miss"] += u.get("prompt_cache_miss_tokens", 0) or 0

    def count(rs, label):
        return sum(1 for r in rs if r["label"] == label)

    out = [f"# Structural-constraint semantic review (initial), `{cfg.rel(AUDIT)}`", "",
           f"Generated by `scripts/experiments/rq1_tools/rq1_review_structural.py --summarize` "
           f"({time.strftime('%Y-%m-%d %H:%M %z')}).", "",
           f"- Object: the `layer == \"basic_constraint\"` rows of `tests.jsonl` "
           f"({len(structural)} tests; every one of them is a single-response V2 read).",
           f"- Reviewer: `{reviewer}`.",
           f"- Prompt: `scripts/experiments/rq1_tools/prompts/structural_review_v1.0.md`, version `{version}`, "
           f"sha256 `{hashlib.sha256(system.encode()).hexdigest()[:16]}…`.",
           "- Criterion: **C** = the constraint is a stable property of that endpoint's response in the pinned "
           "version under the recorded sequence's preconditions; **E** = there is a clear counterexample in the "
           "pinned version; **U** = the evidence is insufficient.",
           "- These are **initial, model-assisted** labels; the E and U items below are what an author "
           "adjudication has to look at. No file of this directory other than `structural-reviews.jsonl`, "
           "`structural-review-failures.jsonl` and this summary is written by the tool.",
           f"- Token usage of the rows in this directory: prompt {usage['prompt']:,} "
           f"(cache hit {usage['cache_hit']:,} / miss {usage['cache_miss']:,}), completion {usage['completion']:,}.",
           "", "## Counts", "", "| Subject | Structural tests | reviewed | C | E | U |", "|---|---:|---:|---:|---:|---:|"]
    for s in subjects:
        rs = [r for r in rows if r["subject"] == s]
        out.append(f"| {s} | {sum(1 for t in structural if t['subject'] == s)} | {len(rs)} | "
                   f"{count(rs, 'C')} | {count(rs, 'E')} | {count(rs, 'U')} |")
    if len(subjects) > 1:
        out.append(f"| **total** | {len(structural)} | {len(rows)} | {count(rows, 'C')} | "
                   f"{count(rows, 'E')} | {count(rows, 'U')} |")

    out += ["", "## By predicate family", "", "| Subject | Family | n | C | E | U |", "|---|---|---:|---:|---:|---:|"]
    for s in subjects:
        for family in sorted({r.get("predicate_family") for r in rows if r["subject"] == s}, key=str):
            rs = [r for r in rows if r["subject"] == s and r.get("predicate_family") == family]
            out.append(f"| {s} | {family} | {len(rs)} | {count(rs, 'C')} | {count(rs, 'E')} | {count(rs, 'U')} |")

    for label, title in (("E", "E (incorrect) items"), ("U", "U (insufficient evidence) items")):
        items = [r for r in rows if r["label"] == label]
        out += ["", f"## {title} — {len(items)}", ""]
        if not items:
            out.append("_none_")
            continue
        for r in sorted(items, key=lambda r: (r["subject"], r["case_id"], r["test_key"])):
            t = by_key[r["test_key"]]
            out += [f"- **`{r['test_key']}`** ({r.get('predicate_family')}, case {r['case_id']}, "
                    f"{t.get('observation_call') or t.get('after_call')})",
                    f"  - constraint: {t.get('business_summary')}",
                    f"  - reviewer's reason: {r['reason']}"]
    missing = [t["test_key"] for t in structural if t["test_key"] not in {r["test_key"] for r in rows}]
    if missing:
        errors = {}
        for f in jsonl(AUDIT / "structural-review-failures.jsonl"):
            errors[f["test_key"]] = f"{f.get('error')} (last attempt {f.get('failed_at')})"
        out += ["", f"## Not reviewed — {len(missing)}", "",
                "These rows have no label: the model call never returned a parseable answer, so they are "
                "counted neither as C nor as E nor as U.", ""]
        out += [f"- `{k}` — {errors.get(k, 'no recorded failure')}" for k in missing[:50]]
    return "\n".join(out) + "\n"


def ask(text: str, system: str, model: str) -> dict:
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    body = {"model": model, "reasoning_effort": "medium", "temperature": 0.1,
            "response_format": {"type": "json_object"}, "max_tokens": 16000,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
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
                return {"answer": answer, "usage": envelope.get("usage"),
                        "raw_sha256": hashlib.sha256(content.encode()).hexdigest()}
            raise ValueError("malformed review answer")
        except Exception as exc:  # retry transient/malformed
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 3:
                raise RuntimeError(last_error)
            time.sleep(3 * (attempt + 1))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--subject")
    ap.add_argument("--case")
    ap.add_argument("--workers", type=int, default=1, help="parallel API calls (a single writer appends the rows)")
    ap.add_argument("--prompt-file", help=f"system prompt (default {DEFAULT_PROMPT_FILE.name})")
    ap.add_argument("--dry-run", action="store_true", help="count the packets that would be sent; no request, no write")
    ap.add_argument("--print-packet", type=int, metavar="N", help="print N packets and exit (no request, no write)")
    ap.add_argument("--summarize", action="store_true",
                    help="write structural-summary.md from structural-reviews.jsonl and exit (no API call)")
    add_common_args(ap)
    args = ap.parse_args(argv[1:])
    cfg = load_config(args)
    AUDIT = cfg.audit_dir
    system, version, reviewer = resolve_prompt(cfg, args.prompt_file)
    model = (cfg.review or {}).get("model") or "deepseek-flash"
    helpers = load_helpers(cfg)

    if args.subject and args.subject not in cfg.subject_ids:
        fail(f"--subject {args.subject} is not in the configured subject list {cfg.subject_ids}")
    tests_path = AUDIT / "tests.jsonl"
    if not tests_path.exists():
        fail(f"no tests.jsonl in {AUDIT} (run rq1_extract.py first)")
    known = set(cfg.subject_ids)
    tests = [t for t in jsonl(tests_path) if t["subject"] in known]

    if args.summarize:
        target = AUDIT / "structural-summary.md"
        assert target.name in WRITABLE
        target.write_text(summarize(cfg, tests, version, reviewer, system))
        print(json.dumps({"wrote": cfg.rel(target)}, ensure_ascii=False))
        return 0

    out = AUDIT / "structural-reviews.jsonl"
    assert out.name in WRITABLE
    done = {r["test_key"] for r in jsonl(out)}
    todo = [t for t in tests if t["layer"] == LAYER and t["test_key"] not in done
            and (not args.subject or t["subject"] == args.subject) and (not args.case or t["case_id"] == args.case)]
    if args.limit:
        todo = todo[: args.limit]
    cache: dict = {}

    if args.print_packet:
        for t in todo[: args.print_packet]:
            print(json.dumps({"test_key": t["test_key"], "packet": json.loads(packet(t, helpers, cache))},
                             ensure_ascii=False, indent=1))
        return 0

    if args.dry_run:
        packets = [packet(t, helpers, cache) for t in todo]
        print(json.dumps({
            "dry_run": True, "audit_dir": cfg.rel(AUDIT), "model": model, "prompt_version": version,
            "reviewer": reviewer, "system_prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
            "structural_tests": sum(t["layer"] == LAYER for t in tests),
            "already_reviewed": len(done), "would_send": len(todo),
            "by_subject": dict(Counter(t["subject"] for t in todo)),
            "by_family": dict(Counter((t.get("predicate") or {}).get("family") for t in todo)),
            "prompt_chars_total": sum(len(system) + len(p) for p in packets),
            "sample": [{"test_key": t["test_key"], "prompt_sha256": hashlib.sha256((system + p).encode()).hexdigest()}
                       for t, p in list(zip(todo, packets))[:3]],
        }, ensure_ascii=False))
        return 0

    cfg.guard_audit_dir()
    for var in ("LLM_BASE_URL", "LLM_API_KEY"):
        if not os.environ.get(var):
            fail(f"{var} is not set (use --dry-run to plan without calling the API)")
    print(json.dumps({"structural_tests": sum(t["layer"] == LAYER for t in tests),
                      "already_reviewed": len(done), "to_review": len(todo)}), flush=True)
    usage_total = {"prompt": 0, "completion": 0, "cache_hit": 0, "cache_miss": 0}

    def review_one(t):
        text = packet(t, helpers, cache)
        try:
            return t, text, ask(text, system, model), None
        except Exception as exc:  # recorded by the writer; failures are re-tried by a later invocation
            return t, text, None, exc

    from concurrent.futures import ThreadPoolExecutor
    failures_path = AUDIT / "structural-review-failures.jsonl"
    assert failures_path.name in WRITABLE
    started = time.time()
    with out.open("a") as stream, ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, (t, text, result, error) in enumerate(pool.map(review_one, todo), 1):
            if error is not None:
                with failures_path.open("a") as failures:
                    failures.write(json.dumps({"test_key": t["test_key"], "error": str(error),
                                               "failed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
                print(json.dumps({"failed": t["test_key"], "error": str(error)[:200]}), flush=True)
                continue
            row = {"test_key": t["test_key"], "subject": t["subject"], "case_id": t["case_id"],
                   "candidate_id": t["candidate_id"], "predicate_family": (t.get("predicate") or {}).get("family"),
                   "label": result["answer"]["label"], "reason": result["answer"]["reason"],
                   "reviewer": reviewer, "prompt_version": version,
                   "prompt_sha256": hashlib.sha256((system + text).encode()).hexdigest(),
                   "response_sha256": result["raw_sha256"], "usage": result["usage"],
                   "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            u = result["usage"] or {}
            usage_total["prompt"] += u.get("prompt_tokens", 0) or 0
            usage_total["completion"] += u.get("completion_tokens", 0) or 0
            usage_total["cache_hit"] += u.get("prompt_cache_hit_tokens", 0) or 0
            usage_total["cache_miss"] += u.get("prompt_cache_miss_tokens", 0) or 0
            if i % 25 == 0 or i == len(todo):
                print(json.dumps({"reviewed": i, "of": len(todo), "last": (t["test_key"], row["label"]),
                                  "usage": usage_total, "elapsed_s": round(time.time() - started)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
