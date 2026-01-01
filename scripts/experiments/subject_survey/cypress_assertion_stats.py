#!/usr/bin/env python3
"""Count assertions in Cypress spec files, and where in the test they occur.

Written for task A of the authors' subject-survey brief.
Read-only: parses .spec.ts / .spec.js / .cy.ts / .cy.js sources, runs nothing.

Method (approximate, deliberately simple so the numbers can be re-derived by hand):

1.  Comments and string/template literals are masked out (replaced by spaces of
    the same length) before any token is searched for, so that a ``.click(`` that
    appears inside a comment or a string is not counted.  Offsets are preserved,
    so argument text is still read back from the ORIGINAL source.
2.  ``it(...)`` / ``specify(...)`` bodies are located by brace matching; the same
    is done for ``beforeEach`` / ``before`` / ``after`` / ``afterEach`` hooks, which are
    reported separately (they are setup, not the test's own checks).
3.  Inside a body, three kinds of tokens are collected in *source* order:
      - assertion  : ``.should(``  ``.and(``  ``expect(``  ``assert(``  ``assert.``
      - contains   : ``.contains(``  (locator that doubles as an implicit assertion)
      - action     : see ACTIONS_STRICT / ACTIONS_BROAD below
    Cypress enqueues commands in source order, and in the specs analysed here the
    ``.then()`` callbacks are also written in execution order, so source order is
    used as a proxy for execution order.  This is an approximation and is stated
    as such in the report.
4.  "Position" = whether an assertion token appears after the LAST action token of
    the body.  Two action definitions are reported:
      - strict: only click / type / visit / request  (the wording of the task brief)
      - broad : + select, check, clear, blur, focus, submit, trigger, scrollTo, ...
                + the project's own action-performing custom commands (--action-cmd)
5.  "Target" = what the assertion checks, classified from the enclosing top-level
    statement text (top-level = brace/paren depth 0 inside the body):
      network  - the statement waits on an intercept alias and reads the response
                 (cy.wait('@x').its('response...')), or asserts on cy.request(...)
      db_state - the statement goes through cy.database(...) / cy.task(...)
      url      - the statement reads cy.location(...) / cy.url(...)
      ui       - everything else (DOM text, visibility, element count, ...)

Usage:
  python3 cypress_assertion_stats.py --root <repo> --glob 'cypress/tests/ui/*.spec.ts' \
      [--glob ...] [--action-cmd loginByXstate --action-cmd ...] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from glob import glob

# --------------------------------------------------------------------------- #
# 1. masking
# --------------------------------------------------------------------------- #


#: Words after which a `/` opens a regular expression rather than being division.
_REGEX_KEYWORDS = frozenset(
    """return typeof case in of new delete void instanceof do else yield await""".split()
)
#: Punctuation after which a `/` opens a regular expression.
_REGEX_PUNCTUATION = frozenset("(,=:[!&|?{};+-*%<>~^")


def _opens_regex(src: str, slash: int) -> bool:
    """Is the `/` at `slash` the start of a regular-expression literal?

    Looking only at the previous significant character is enough for the spec
    dialect handled here: a regex literal always follows `(`, `,`, `=`, `:`,
    `!`, an operator, or one of the keywords above, while division always
    follows an identifier, a number, `)` or `]`.
    """
    index = slash - 1
    while index >= 0 and src[index].isspace():
        index -= 1
    if index < 0:
        return True
    previous = src[index]
    if previous in _REGEX_PUNCTUATION:
        return True
    if previous.isalnum() or previous in "_$":
        end = index + 1
        start = end
        while start > 0 and (src[start - 1].isalnum() or src[start - 1] in "_$"):
            start -= 1
        return src[start:end] in _REGEX_KEYWORDS
    return False


def mask_source(src: str) -> str:
    """Replace comment, string- and regex-literal characters with spaces, keeping offsets.

    Newlines are preserved so that line numbers still work.

    Regular expressions are masked for the same reason strings are: their body
    is data, not code.  Skipping them used to corrupt the whole file whenever a
    regex carried a quote character - for example the apostrophe in
    ``/You don't have permissions to do that/i`` made the scanner treat
    everything up to the next apostrophe, several tests further down, as one
    string literal, so those tests and their assertions disappeared from the
    statistics (paperless-ngx's global-permissions.spec.ts reported 4 tests
    instead of 8; fixed 2026-09-21).
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            if i < n:
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
        elif c == "/" and _opens_regex(src, i):
            i += 1  # keep the opening delimiter, as for strings
            in_class = False
            while i < n and src[i] != "\n":
                if src[i] == "\\":
                    out[i] = " "
                    if i + 1 < n and src[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                    continue
                if src[i] == "[":
                    in_class = True
                elif src[i] == "]":
                    in_class = False
                elif src[i] == "/" and not in_class:
                    break
                out[i] = " "
                i += 1
            i += 1  # skip the closing delimiter (left intact)
            while i < n and (src[i].isalpha()):  # flags: gimsuyd
                out[i] = " "
                i += 1
        elif c in "\"'`":
            quote = c
            i += 1  # keep the opening quote so `cy.get("` still looks like a call
            while i < n:
                if src[i] == "\\":
                    if src[i] != "\n":
                        out[i] = " "
                    if i + 1 < n and src[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                    continue
                if src[i] == quote:
                    break
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            i += 1  # skip closing quote (left intact)
        else:
            i += 1
    return "".join(out)


# --------------------------------------------------------------------------- #
# 2. block extraction
# --------------------------------------------------------------------------- #


def match_brace(masked: str, open_idx: int) -> int:
    """Index just past the '}' matching the '{' at open_idx."""
    depth = 0
    i = open_idx
    n = len(masked)
    while i < n:
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


IT_RE = re.compile(r"\b(it|specify)(?:\.(?:only|skip))?\s*\(")
HOOK_RE = re.compile(r"\b(beforeEach|before|afterEach|after)\s*\(")
DESCRIBE_RE = re.compile(r"\b(describe|context)(?:\.(?:only|skip))?\s*\(")
TITLE_RE = re.compile(r"""["'`](.*?)["'`]""", re.S)


def _matching_paren(masked: str, open_idx: int) -> int:
    """Index of the ')' matching the '(' at open_idx, or -1."""
    if open_idx < 0 or open_idx >= len(masked) or masked[open_idx] != "(":
        return -1
    depth = 0
    for j in range(open_idx, len(masked)):
        if masked[j] == "(":
            depth += 1
        elif masked[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _callback_body_brace(masked: str, start: int, limit: int) -> int:
    """Index of the '{' that opens the callback body of a test/hook call.

    Must skip the parameter list: Playwright writes ``async ({ page }) => {``, so
    the first '{' after ``test(`` is a destructuring pattern, not the body.
    """
    i = start
    while i < limit and i < len(masked):
        if masked.startswith("=>", i):
            return masked.find("{", i + 2)
        if masked.startswith("function", i) and (i == 0 or not (masked[i - 1].isalnum() or masked[i - 1] == "_")):
            paren = masked.find("(", i)
            if paren < 0:
                return -1
            depth, j = 0, paren
            while j < len(masked):
                if masked[j] == "(":
                    depth += 1
                elif masked[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            return masked.find("{", j)
        i += 1
    return -1


def find_blocks(src: str, masked: str, pattern: re.Pattern):
    """Yield (kind, title, body_start, body_end) for each matching callback block."""
    for m in pattern.finditer(masked):
        nxt = pattern.search(masked, m.end())
        limit = nxt.start() if nxt else len(masked)
        brace = _callback_body_brace(masked, m.end(), limit)
        if brace < 0:
            continue
        # guard: the '{' must belong to this call, not to a later one
        if nxt and brace > nxt.start():
            continue
        end = match_brace(masked, brace)
        header = src[m.end():brace]
        tm = TITLE_RE.search(header)
        title = tm.group(1).strip() if tm else "(no title)"
        kind = next((g for g in m.groups() if g), m.group(0).strip("( "))
        yield kind, title, m.start(), brace, end


# --------------------------------------------------------------------------- #
# 3. tokens
# --------------------------------------------------------------------------- #

ASSERT_RE = re.compile(r"\.should\s*\(|\.and\s*\(|\bexpect\s*\(|\bassert\s*[.(]")
CONTAINS_RE = re.compile(r"\.contains\s*\(")

ACTIONS_STRICT = ["click", "type", "visit", "request"]
ACTIONS_BROAD_EXTRA = [
    "dblclick", "rightclick", "select", "check", "uncheck", "clear", "blur",
    "focus", "submit", "trigger", "scrollTo", "selectFile", "selectNth",
]

# ---- Playwright dialect -------------------------------------------------- #
# Same counting rules, different vocabulary.  `expect(` is the only assertion
# form; there is no locator-that-also-asserts, so the "contains" column is
# structurally 0 for Playwright and the report says so.
PW_ASSERT_RE = re.compile(r"\bexpect\s*\(|\bassert\s*[.(]")
PW_CONTAINS_RE = re.compile(r"(?!x)x")  # matches nothing
PW_ACTIONS_STRICT = ["click", "fill", "goto", "press"]
PW_ACTIONS_BROAD_EXTRA = [
    "type", "check", "uncheck", "selectOption", "setInputFiles", "hover",
    "dblclick", "tap", "dragTo", "clear", "focus", "blur", "selectText",
    "post", "put", "patch", "delete", "reload", "waitForURL",
]
PW_TEST_RE = re.compile(r"\b(test)\s*\(")
PW_HOOK_RE = re.compile(r"\btest\.(beforeEach|beforeAll|afterEach|afterAll)\s*\(|"
                        r"\b(beforeEach|before|afterEach|after)\s*\(")
PW_NETWORK_RE = re.compile(r"waitForResponse\s*\(|\brequest\s*\.|\.status\s*\(|"
                           r"\bresponse\b|APIResponse")
PW_URL_RE = re.compile(r"toHaveURL|page\.url\s*\(")


def build_action_re(names, custom_cmds):
    parts = [r"\.%s\s*\(" % re.escape(nm) for nm in names]
    parts += [r"\.%s\s*\(" % re.escape(c) for c in custom_cmds]
    return re.compile("|".join(parts))


NETWORK_RE = re.compile(r"cy\.wait\s*\(\s*[\"'`]@")
RESPONSE_RE = re.compile(r"\.its\s*\(\s*[\"'`]\s*(response|request)|\bresponse\b|\bstatusCode\b")
DB_RE = re.compile(r"cy\.(database|task)\s*\(")
URL_RE = re.compile(r"cy\.(location|url|hash)\s*\(")
REQUEST_RE = re.compile(r"cy\.request\s*\(")


def top_level_statements(masked: str, start: int, end: int):
    """Split [start, end) into top-level statement spans (depth-0 ';' or '}')."""
    spans = []
    depth = 0
    s = start
    i = start
    while i < end:
        ch = masked[i]
        if ch in "({[":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "}":
            depth -= 1
            if depth <= 0:
                spans.append((s, i + 1))
                s = i + 1
                depth = 0
        elif ch == ";" and depth == 0:
            spans.append((s, i + 1))
            s = i + 1
        i += 1
    if s < end:
        spans.append((s, end))
    return [(a, b) for a, b in spans if masked[a:b].strip()]


def classify_playwright(stmt_text: str) -> str:
    if PW_NETWORK_RE.search(stmt_text):
        return "network"
    if PW_URL_RE.search(stmt_text):
        return "url"
    return "ui"


def classify(stmt_text: str) -> str:
    if DIALECT == "playwright":
        return classify_playwright(stmt_text)
    if NETWORK_RE.search(stmt_text) and RESPONSE_RE.search(stmt_text):
        return "network"
    if REQUEST_RE.search(stmt_text):
        return "network"
    if DB_RE.search(stmt_text):
        return "db_state"
    if URL_RE.search(stmt_text):
        return "url"
    return "ui"


DIALECT = "cypress"


def analyse_body(src, masked, bstart, bend, action_re_strict, action_re_broad):
    """Return a dict of counts for one it()/hook body."""
    seg_m = masked[bstart:bend]
    a_re = PW_ASSERT_RE if DIALECT == "playwright" else ASSERT_RE
    c_re = PW_CONTAINS_RE if DIALECT == "playwright" else CONTAINS_RE
    asserts = [bstart + m.start() for m in a_re.finditer(seg_m)]
    contains = [bstart + m.start() for m in c_re.finditer(seg_m)]
    act_strict = [bstart + m.start() for m in action_re_strict.finditer(seg_m)]
    act_broad = [bstart + m.start() for m in action_re_broad.finditer(seg_m)]

    stmts = top_level_statements(masked, bstart, bend)

    def stmt_for(off):
        for a, b in stmts:
            if a <= off < b:
                return src[a:b]
        return src[max(bstart, off - 200):off + 200]

    targets = Counter()
    for off in asserts:
        targets[classify(stmt_for(off))] += 1
    targets_contains = Counter()
    for off in contains:
        targets_contains[classify(stmt_for(off))] += 1

    def after_last(offsets, actions):
        if not actions:
            # no action at all -> every assertion is trivially "after the last action"
            return len(offsets), True
        last = max(actions)
        return sum(1 for o in offsets if o > last), False

    a_strict, no_act_s = after_last(asserts, act_strict)
    a_broad, no_act_b = after_last(asserts, act_broad)
    c_strict, _ = after_last(contains, act_strict)
    c_broad, _ = after_last(contains, act_broad)

    total_checks = len(asserts) + len(contains)
    tail_strict = a_strict + c_strict
    tail_broad = a_broad + c_broad

    # targets split by position (broad action set): what do MID checks look at,
    # versus what do the TAIL checks look at?
    last_broad = max(act_broad) if act_broad else -1
    tg_mid, tg_tail = Counter(), Counter()
    for off in asserts + contains:
        bucket = tg_tail if off > last_broad else tg_mid
        bucket[classify(stmt_for(off))] += 1

    return {
        "targets_mid_broad": dict(tg_mid),
        "targets_tail_broad": dict(tg_tail),
        "line": src[:bstart].count("\n") + 1,
        "n_assert": len(asserts),
        "n_contains": len(contains),
        "n_checks": total_checks,
        "n_actions_strict": len(act_strict),
        "n_actions_broad": len(act_broad),
        "checks_after_last_action_strict": tail_strict,
        "checks_after_last_action_broad": tail_broad,
        "checks_mid_strict": total_checks - tail_strict,
        "checks_mid_broad": total_checks - tail_broad,
        "has_mid_check_strict": (total_checks - tail_strict) > 0,
        "has_mid_check_broad": (total_checks - tail_broad) > 0,
        "no_action_strict": no_act_s,
        "no_action_broad": no_act_b,
        "targets": dict(targets),
        "targets_contains": dict(targets_contains),
    }


def analyse_file(path, custom_cmds):
    src = open(path, encoding="utf-8").read()
    masked = mask_source(src)
    if DIALECT == "playwright":
        strict, extra = PW_ACTIONS_STRICT, PW_ACTIONS_BROAD_EXTRA
        test_re, hook_re = PW_TEST_RE, PW_HOOK_RE
    else:
        strict, extra = ACTIONS_STRICT, ACTIONS_BROAD_EXTRA
        test_re, hook_re = IT_RE, HOOK_RE
    a_strict = build_action_re(strict, [])
    a_broad = build_action_re(strict + extra, custom_cmds)

    # hook bodies must be excluded from it() bodies? they are siblings, so no overlap.
    tests = []
    for kind, title, _tstart, bstart, bend in find_blocks(src, masked, test_re):
        rec = analyse_body(src, masked, bstart, bend, a_strict, a_broad)
        rec["title"] = title
        tests.append(rec)

    hooks = []
    for kind, title, _tstart, bstart, bend in find_blocks(src, masked, hook_re):
        rec = analyse_body(src, masked, bstart, bend, a_strict, a_broad)
        rec["hook"] = kind
        hooks.append(rec)

    # raw grep-style counts, for cross-checking against `grep -c`
    raw = {
        "should(": len(re.findall(r"\.should\s*\(", masked)),
        "and(": len(re.findall(r"\.and\s*\(", masked)),
        "expect(": len(re.findall(r"\bexpect\s*\(", masked)),
        "contains(": len(CONTAINS_RE.findall(masked)),
        "it(": len(IT_RE.findall(masked)),
        "test(": len(PW_TEST_RE.findall(masked)),
    }
    return {"path": path, "tests": tests, "hooks": hooks, "raw": raw}


def summarise(files):
    tests = [t for f in files for t in f["tests"]]
    n = len(tests)
    agg = OrderedDict()
    agg["n_spec_files"] = len(files)
    agg["n_tests"] = n
    if n == 0:
        return agg
    tot_assert = sum(t["n_assert"] for t in tests)
    tot_contains = sum(t["n_contains"] for t in tests)
    tot_checks = tot_assert + tot_contains
    agg["total_should_and_expect"] = tot_assert
    agg["total_contains"] = tot_contains
    agg["total_checks"] = tot_checks
    agg["mean_assert_per_test"] = round(tot_assert / n, 2)
    agg["mean_checks_per_test"] = round(tot_checks / n, 2)
    agg["median_checks_per_test"] = sorted(t["n_checks"] for t in tests)[n // 2]
    agg["min_checks"] = min(t["n_checks"] for t in tests)
    agg["max_checks"] = max(t["n_checks"] for t in tests)
    for mode in ("strict", "broad"):
        tail = sum(t["checks_after_last_action_%s" % mode] for t in tests)
        agg["checks_after_last_action_%s" % mode] = tail
        agg["pct_checks_after_last_action_%s" % mode] = round(100.0 * tail / tot_checks, 1)
        mids = sum(1 for t in tests if t["has_mid_check_%s" % mode])
        agg["tests_with_mid_check_%s" % mode] = mids
        agg["pct_tests_with_mid_check_%s" % mode] = round(100.0 * mids / n, 1)
        agg["tests_with_no_action_%s" % mode] = sum(1 for t in tests if t["no_action_%s" % mode])
    tg = Counter()
    for t in tests:
        tg.update(t["targets"])
    tgc = Counter()
    for t in tests:
        tgc.update(t["targets_contains"])
    agg["targets_should_expect"] = dict(tg)
    agg["targets_contains"] = dict(tgc)
    tmid, ttail = Counter(), Counter()
    for t in tests:
        tmid.update(t["targets_mid_broad"])
        ttail.update(t["targets_tail_broad"])
    agg["targets_mid_broad"] = dict(tmid)
    agg["targets_tail_broad"] = dict(ttail)
    # "server-observable" = network response or database/task state
    def server(c):
        return c.get("network", 0) + c.get("db_state", 0)
    agg["mid_checks_server_observable"] = server(tmid)
    agg["mid_checks_ui_or_url"] = tmid.get("ui", 0) + tmid.get("url", 0)
    agg["tail_checks_server_observable"] = server(ttail)
    agg["tail_checks_ui_or_url"] = ttail.get("ui", 0) + ttail.get("url", 0)
    # distribution of checks per test
    agg["checks_per_test_histogram"] = dict(
        sorted(Counter(t["n_checks"] for t in tests).items()))
    hooks = [h for f in files for h in f["hooks"]]
    agg["n_hooks"] = len(hooks)
    agg["checks_in_hooks"] = sum(h["n_checks"] for h in hooks)
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--glob", action="append", required=True)
    ap.add_argument("--action-cmd", action="append", default=[],
                    help="project custom command that performs actions (broad mode)")
    ap.add_argument("--json", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--framework", choices=("cypress", "playwright"), default="cypress")
    args = ap.parse_args()
    global DIALECT
    DIALECT = args.framework

    paths = []
    for g in args.glob:
        paths.extend(sorted(glob(os.path.join(args.root, g))))
    if not paths:
        sys.exit("no files matched under %s" % args.root)

    files = [analyse_file(p, args.action_cmd) for p in paths]
    agg = summarise(files)

    print("# %s assertion stats %s" % (args.framework, args.label))
    print("root: %s" % args.root)
    print("globs: %s" % ", ".join(args.glob))
    print("action custom commands (broad): %s" % (", ".join(args.action_cmd) or "-"))
    print()
    hdr = ("| file | tests | should/and/expect | contains | checks | actions(broad) "
           "| checks after last action (broad) | tests w/ mid check (broad) |")
    print(hdr)
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for f in files:
        ts = f["tests"]
        if not ts:
            continue
        print("| %s | %d | %d | %d | %d | %d | %d | %d |" % (
            os.path.relpath(f["path"], args.root),
            len(ts),
            sum(t["n_assert"] for t in ts),
            sum(t["n_contains"] for t in ts),
            sum(t["n_checks"] for t in ts),
            sum(t["n_actions_broad"] for t in ts),
            sum(t["checks_after_last_action_broad"] for t in ts),
            sum(1 for t in ts if t["has_mid_check_broad"]),
        ))
    print()
    print("## summary")
    for k, v in agg.items():
        print("%-42s %s" % (k, v))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"root": args.root, "globs": args.glob,
                       "action_cmds": args.action_cmd,
                       "files": files, "summary": agg}, fh, indent=2)
        print("\nwrote %s" % args.json)


if __name__ == "__main__":
    main()
