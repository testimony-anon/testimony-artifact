# -*- coding: utf-8 -*-
"""Per sequence: does any request after the last business write read the written entity back?

Reads only M01_09/ui_api_trace.json of each case root given on the command line (glob of
<run>/cases/<case>/union directories). A write is POST/PUT/PATCH/DELETE whose canonical path is not
a profile-declared read-semantic endpoint (Ghost's /stats/ POST is excluded by path). Identifier forms: 24-hex, UUID or integer only (slug identifiers such as Conduit article slugs are not detected). A by-id read is
a later GET on the written collection whose last path segment is an identifier (24-hex, UUID, or integer).

Usage: .venv/bin/python scripts/experiments/subjects/readback_after_write.py 'eval/ui_semantics/ghost-20260921/ghost/full-01/cases/*/union'
"""
import glob, io, json, re, sys

ID = re.compile(r"/([0-9a-f]{24}|[0-9a-f-]{36}|\d+)/?$")
rows = []
for pattern in sys.argv[1:]:
    for union in sorted(glob.glob(pattern)):
        if "/." in union:
            continue
        case_id = union.rstrip("/").split("/cases/")[1].split("/")[0]
        try:
            trace = json.load(io.open(union + "/M01_09/ui_api_trace.json", encoding="utf-8"))["trace"]["api_requests"]
        except (OSError, KeyError, ValueError):
            rows.append((case_id, "no trace", None, None)); continue
        reqs = [(r["global_order"], r["method"], r["canonical_path"]) for r in trace]
        writes = [(o, m, p) for o, m, p in reqs if m in ("POST", "PUT", "PATCH", "DELETE") and "/stats/" not in p]
        if not writes:
            rows.append((case_id, "no write", None, None)); continue
        lo, lm, lp = writes[-1]
        coll = ID.sub("/", lp).rstrip("/")
        after = [(m, p) for o, m, p in reqs if o > lo]
        by_id = sum(1 for m, p in after if m == "GET" and ID.search(p) and p.startswith(coll))
        lists = sum(1 for m, p in after if m == "GET" and p.rstrip("/") == coll)
        rows.append((case_id, f"{lm} {lp}", by_id, lists))
for r in rows:
    print("%-20s %-60s by-id reads after: %-4s list reads after: %s" % (r[0], r[1][:60], r[2], r[3]))
with_write = [r for r in rows if r[2] is not None]
print("sequences with trace:", sum(1 for r in rows if r[1] != "no trace"),
      "| with a business write:", len(with_write),
      "| of which no by-id read of the written collection afterwards:", sum(1 for r in with_write if r[2] == 0),
      "| without any write:", sum(1 for r in rows if r[1] == "no write"))
