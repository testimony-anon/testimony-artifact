"""Controlled reproduction of RWA business-rule leads on an unpatched copy.

Runs against a locally started, unmodified cypress-realworld-app backend.
Every HTTP exchange is appended to evidence.jsonl; verdicts go to summary.json.
No LLM, no UISemTest pipeline code, no fault patches.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("RWA_BASE_URL", "http://localhost:14101")
OUT = Path(__file__).resolve().parent
EVIDENCE = OUT / "evidence.jsonl"
PASSWORD = os.environ.get("RWA_SEED_PASSWORD", "s3cret")

USERS = {
    "A": ("Heath93", "uBmeaz5pX"),
    "B": ("Arvilla_Hegmann", "GjWovtg2hr"),
    "C": ("Dina20", "_XblMqbuoP"),
}

_seq = 0


class Session:
    def __init__(self, label: str):
        self.label = label
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method: str, path: str, body=None, note: str = ""):
        global _seq
        _seq += 1
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        started = time.time()
        try:
            with self.opener.open(req, timeout=30) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw[:2000]
        record = {
            "seq": _seq, "actor": self.label, "method": method, "path": path,
            "request_body": body, "status": status,
            "response": parsed if not isinstance(parsed, str) else parsed[:2000],
            "elapsed_ms": round((time.time() - started) * 1000, 1), "note": note,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        with EVIDENCE.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return status, parsed


def login(label: str) -> Session:
    s = Session(label)
    username, _ = USERS[label]
    status, body = s.call("POST", "/login", {"username": username, "password": PASSWORD}, "login")
    assert status == 200, f"login {label} failed: {status} {body}"
    return s


def seed(anon: Session):
    status, _ = anon.call("POST", "/testData/seed", None, "reseed database")
    assert status == 200, f"seed failed {status}"


def balance(s: Session, label: str) -> int:
    _, uid = USERS[label]
    status, body = s.call("GET", f"/users/{uid}", None, f"balance of {label}")
    assert status == 200, (status, body)
    return body["user"]["balance"]


def transaction(s: Session, tx_id: str):
    status, body = s.call("GET", f"/transactions/{tx_id}", None, "read transaction")
    assert status == 200, (status, body)
    return body["transaction"]


def notifications(s: Session, note: str):
    status, body = s.call("GET", "/notifications", None, note)
    assert status == 200, (status, body)
    return body["results"]


def lead_1_reject_transfers_funds(results):
    anon = Session("anon")
    seed(anon)
    A, B = login("A"), login("B")
    a0, b0 = balance(A, "A"), balance(B, "B")
    status, body = A.call("POST", "/transactions", {
        "transactionType": "request", "receiverId": USERS["B"][1],
        "amount": 10, "description": "lead1 request $10"}, "A requests $10 from B")
    tx = body["transaction"]
    tx_id = tx["id"]
    notes_before = notifications(A, "A notifications before reject")
    status_patch, _ = B.call("PATCH", f"/transactions/{tx_id}", {"requestStatus": "rejected"}, "B rejects the request")
    tx_after = transaction(A, tx_id)
    a1, b1 = balance(A, "A"), balance(B, "B")
    notes_after = notifications(A, "A notifications after reject")
    new_received = [n for n in notes_after if n.get("transactionId") == tx_id and n.get("status") == "received"]
    results["lead_1_reject_transfers_funds"] = {
        "business_rule": "rejecting a money request must not move funds, must not mark the transaction complete, and must not notify the requester of a received payment",
        "steps": "seed; A requests $10 from B; B PATCH requestStatus=rejected",
        "patch_status": status_patch,
        "transaction_before": {k: tx.get(k) for k in ("id", "status", "requestStatus", "amount")},
        "transaction_after": {k: tx_after.get(k) for k in ("id", "status", "requestStatus", "amount")},
        "balances_before": {"A": a0, "B": b0}, "balances_after": {"A": a1, "B": b1},
        "balance_delta": {"A": a1 - a0, "B": b1 - b0},
        "received_notifications_for_requester_after_reject": len(new_received),
        "verdict": ("BUG_REPRODUCED" if (a1 - a0 != 0 or b1 - b0 != 0 or tx_after.get("status") == "complete" or new_received)
                    else "NOT_REPRODUCED"),
    }


def lead_2_double_accept(results):
    anon = Session("anon")
    seed(anon)
    A, B = login("A"), login("B")
    a0, b0 = balance(A, "A"), balance(B, "B")
    _, body = A.call("POST", "/transactions", {
        "transactionType": "request", "receiverId": USERS["B"][1],
        "amount": 10, "description": "lead2 request $10"}, "A requests $10 from B")
    tx_id = body["transaction"]["id"]
    s1, _ = B.call("PATCH", f"/transactions/{tx_id}", {"requestStatus": "accepted"}, "B accepts (1st)")
    a1, b1 = balance(A, "A"), balance(B, "B")
    s2, _ = B.call("PATCH", f"/transactions/{tx_id}", {"requestStatus": "accepted"}, "B accepts (2nd, same request)")
    a2, b2 = balance(A, "A"), balance(B, "B")
    tx_after = transaction(A, tx_id)
    notes = notifications(A, "A notifications after two accepts")
    received = [n for n in notes if n.get("transactionId") == tx_id and n.get("status") == "received"]
    results["lead_2_double_accept"] = {
        "business_rule": "accepting the same money request twice must settle it only once",
        "steps": "seed; A requests $10 from B; B accepts twice",
        "patch_status": [s1, s2],
        "balances": {"before": {"A": a0, "B": b0}, "after_1st": {"A": a1, "B": b1}, "after_2nd": {"A": a2, "B": b2}},
        "delta_1st": {"A": a1 - a0, "B": b1 - b0}, "delta_2nd": {"A": a2 - a1, "B": b2 - b1},
        "transaction_after": {k: tx_after.get(k) for k in ("id", "status", "requestStatus", "amount")},
        "received_notifications_for_requester": len(received),
        "verdict": "BUG_REPRODUCED" if (a2 - a1 != 0 or b2 - b1 != 0) else "NOT_REPRODUCED",
    }


def lead_3_notification_ownership(results):
    anon = Session("anon")
    seed(anon)
    A, C = login("A"), login("C")
    a_notes = notifications(A, "A unread notifications")
    target = a_notes[0]
    status_c, body_c = C.call("PATCH", f"/notifications/{target['id']}", {"isRead": True},
                              "C (unrelated user) marks A's notification as read")
    a_notes_after = notifications(A, "A unread notifications after C's patch")
    still_present = any(n["id"] == target["id"] for n in a_notes_after)
    # also a well-formed but nonexistent id
    status_nx, body_nx = C.call("PATCH", "/notifications/zzzzzzzzz", {"isRead": True}, "C patches a nonexistent notification id")
    results["lead_3_notification_ownership"] = {
        "business_rule": "a user may only change their own notifications; other users' notifications must be rejected",
        "steps": "seed; C PATCH /notifications/<A's id> isRead=true; A re-reads unread list",
        "target_notification": {k: target.get(k) for k in ("id", "userId", "isRead", "status")},
        "patch_status_by_other_user": status_c, "patch_response": body_c,
        "notification_still_unread_for_owner": still_present,
        "nonexistent_id_patch_status": status_nx, "nonexistent_id_response": body_nx if isinstance(body_nx, str) else body_nx,
        "verdict": "BUG_REPRODUCED" if (status_c in (200, 204) and not still_present) else "NOT_REPRODUCED",
    }


def lead_4_self_notification(results):
    anon = Session("anon")
    seed(anon)
    A, B = login("A"), login("B")
    _, body = A.call("POST", "/transactions", {
        "transactionType": "payment", "receiverId": USERS["B"][1],
        "amount": 5, "description": "lead4 payment $5"}, "A pays $5 to B")
    tx_id = body["transaction"]["id"]
    a_before = notifications(A, "A notifications before commenting on own transaction")
    b_before = notifications(B, "B notifications before A comments")
    sc, _ = A.call("POST", f"/comments/{tx_id}", {"content": "lead4 comment by sender"}, "A comments on own transaction")
    sl, _ = A.call("POST", f"/likes/{tx_id}", None, "A likes own transaction")
    a_after = notifications(A, "A notifications after own comment+like")
    b_after = notifications(B, "B notifications after A's comment+like")
    def new_ids(before, after):
        old = {n["id"] for n in before}
        return [n for n in after if n["id"] not in old]
    a_new = new_ids(a_before, a_after)
    b_new = new_ids(b_before, b_after)
    a_self = [n for n in a_new if n.get("transactionId") == tx_id and n.get("userId") == USERS["A"][1]]
    results["lead_4_self_notification"] = {
        "business_rule": "commenting on or liking a transaction notifies the other party, not the acting user themself",
        "steps": "seed; A pays B; A comments and likes that transaction; compare both users' notification lists",
        "comment_status": sc, "like_status": sl,
        "new_notifications_for_actor_A": [{k: n.get(k) for k in ("id", "userId", "transactionId", "commentId", "likeId")} for n in a_new],
        "new_notifications_for_B": [{k: n.get(k) for k in ("id", "userId", "transactionId", "commentId", "likeId")} for n in b_new],
        "verdict": "BUG_REPRODUCED" if a_self else "NOT_REPRODUCED",
    }


def lead_5_amount_filter_zero_lower_bound(results):
    anon = Session("anon")
    seed(anon)
    A = login("A")
    _, unfiltered = A.call("GET", "/transactions/public", None, "public feed, no filter")
    _, zero_min = A.call("GET", "/transactions/public?amountMin=0&amountMax=1000", None, "public feed, amountMin=0 amountMax=1000")
    _, one_min = A.call("GET", "/transactions/public?amountMin=1&amountMax=1000", None, "public feed, amountMin=1 amountMax=1000")
    def amounts(b):
        return [t.get("amount") for t in (b or {}).get("results", [])]
    z, o, u = amounts(zero_min), amounts(one_min), amounts(unfiltered)
    results["lead_5_amount_filter_zero_lower_bound"] = {
        "business_rule": "an amount filter with lower bound 0 must still exclude transactions above the upper bound",
        "steps": "seed; GET /transactions/public with amountMin=0&amountMax=1000 vs amountMin=1&amountMax=1000",
        "unfiltered_count": len(u), "zero_min_count": len(z), "one_min_count": len(o),
        "zero_min_amounts_above_max": [a for a in z if isinstance(a, (int, float)) and a > 1000][:10],
        "one_min_amounts_above_max": [a for a in o if isinstance(a, (int, float)) and a > 1000][:10],
        "verdict": "BUG_REPRODUCED" if any(isinstance(a, (int, float)) and a > 1000 for a in z) and not any(isinstance(a, (int, float)) and a > 1000 for a in o) else "NOT_REPRODUCED",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if EVIDENCE.exists():
        EVIDENCE.rename(OUT / f"evidence-{int(time.time())}.jsonl")
    results = {"base_url": BASE, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "leads": {}}
    for fn in (lead_1_reject_transfers_funds, lead_2_double_accept, lead_3_notification_ownership,
               lead_4_self_notification, lead_5_amount_filter_zero_lower_bound):
        try:
            fn(results["leads"])
        except Exception as e:  # keep going, record the failure
            results["leads"][fn.__name__] = {"verdict": "ERROR", "error": repr(e)}
    Session("anon").call("POST", "/testData/seed", None, "final reseed to leave the copy clean")
    results["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (OUT / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    for name, r in results["leads"].items():
        print(f"{name}: {r.get('verdict')}")
    print("evidence:", EVIDENCE)


if __name__ == "__main__":
    sys.exit(main())
