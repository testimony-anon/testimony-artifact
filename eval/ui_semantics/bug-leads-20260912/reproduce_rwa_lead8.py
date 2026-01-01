"""Controlled reproduction of RWA lead L8 on the unpatched copy (bdf6169).

Lead L8 (from DeepSeek run, rwa/L3-REQUEST-REJECT-01 v2-candidate-0015):
after logout, the GraphQL query ListBankAccount answered HTTP 200 with a
server-side TypeError in `errors` instead of an authentication error.
Same style as reproduce_rwa_leads.py: plain HTTP, no pipeline code; evidence
appended to evidence-lead8.jsonl, verdict in summary-lead8.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reproduce_rwa_leads as base  # noqa: E402

OUT = Path(__file__).resolve().parent
base.EVIDENCE = OUT / "evidence-lead8.jsonl"

QUERY = {"operationName": "ListBankAccount",
         "query": "query ListBankAccount { listBankAccount { id uuid userId bankName accountNumber routingNumber isDeleted createdAt modifiedAt } }"}


def lead_8_unauthenticated_graphql(results):
    anon = base.Session("anon")
    base.seed(anon)
    A = base.login("A")
    status_in, body_in = A.call("POST", "/graphql", QUERY, "ListBankAccount while logged in")
    status_out, _ = A.call("POST", "/logout", None, "A logs out")
    status_after, body_after = A.call("POST", "/graphql", QUERY, "ListBankAccount after logout (same session jar)")
    status_anon, body_anon = base.Session("anon2").call("POST", "/graphql", QUERY, "ListBankAccount with no session at all")
    status_rest, body_rest = base.Session("anon3").call("GET", "/bankAccounts", None, "REST bank accounts with no session (control)")

    def errors(body):
        return [e.get("message") for e in (body or {}).get("errors", [])] if isinstance(body, dict) else body

    results["lead_8_unauthenticated_graphql"] = {
        "business_rule": "an unauthenticated GraphQL query must be rejected with an authentication error, not answered with an internal TypeError",
        "steps": "seed; A logs in; ListBankAccount; A logs out; ListBankAccount again; ListBankAccount with a fresh session; GET /bankAccounts with a fresh session as REST control",
        "logged_in": {"status": status_in, "accounts": len(((body_in or {}).get("data") or {}).get("listBankAccount") or []) if isinstance(body_in, dict) else None},
        "logout_status": status_out,
        "after_logout": {"status": status_after, "data": (body_after or {}).get("data") if isinstance(body_after, dict) else body_after, "errors": errors(body_after)},
        "fresh_session": {"status": status_anon, "data": (body_anon or {}).get("data") if isinstance(body_anon, dict) else body_anon, "errors": errors(body_anon)},
        "rest_control": {"status": status_rest, "body": body_rest if not isinstance(body_rest, dict) else {k: body_rest[k] for k in list(body_rest)[:3]}},
    }
    type_error = any("TypeError" in (m or "") for m in (errors(body_after) or []) + (errors(body_anon) or []) if isinstance(m, str))
    results["lead_8_unauthenticated_graphql"]["verdict"] = "BUG_REPRODUCED" if type_error and status_after == 200 else "NOT_REPRODUCED"


def main():
    if base.EVIDENCE.exists():
        base.EVIDENCE.rename(OUT / f"evidence-lead8-{int(time.time())}.jsonl")
    results = {"base_url": base.BASE, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "leads": {}}
    try:
        lead_8_unauthenticated_graphql(results["leads"])
    except Exception as e:
        results["leads"]["lead_8_unauthenticated_graphql"] = {"verdict": "ERROR", "error": repr(e)}
    base.Session("anon").call("POST", "/testData/seed", None, "final reseed to leave the copy clean")
    results["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (OUT / "summary-lead8.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    for name, r in results["leads"].items():
        print(f"{name}: {r.get('verdict')}")
    print("evidence:", base.EVIDENCE)


if __name__ == "__main__":
    sys.exit(main())
