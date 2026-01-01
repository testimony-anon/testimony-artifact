"""Controlled reproduction of the Conduit tag-echo lead on an unpatched normal image.

Lead L6: createArticle silently drops tags whose length <= 2 but echoes the submitted
tagList in the 201 response; a subsequent read returns only the persisted tags.
Runs against a separately deployed stack of the unpatched normal image (port 3301).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("CONDUIT_BASE_URL", "http://localhost:3301")
OUT = Path(__file__).resolve().parent
EVIDENCE = OUT / "conduit-evidence.jsonl"
_seq = 0
STAMP = str(int(time.time()))


def call(method: str, path: str, body=None, token: str | None = None, note: str = ""):
    global _seq
    _seq += 1
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Token {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, raw = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode("utf-8", "replace")
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw[:2000]
    rec = {"seq": _seq, "method": method, "path": path, "request_body": body, "status": status,
           "response": parsed, "note": note, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    with EVIDENCE.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return status, parsed


def main():
    if EVIDENCE.exists():
        EVIDENCE.rename(OUT / f"conduit-evidence-{STAMP}.jsonl")
    username = f"lead6user{STAMP[-6:]}"
    st, body = call("POST", "/api/users", {"user": {"username": username, "email": f"{username}@example.local",
                                                     "password": "lead6-local-pw"}}, note="register fresh user")
    assert st in (200, 201), (st, body)
    token = body["user"]["token"]
    results = {"base_url": BASE, "user": username, "cases": []}
    # Each case: submitted tagList -> create-response tagList -> read-back tagList -> global /api/tags membership
    for label, tags in [("short_and_long", ["xy", "lastingtag"]),
                        ("one_char", ["q"]),
                        ("three_chars", ["abc"]),
                        ("two_chars_only", ["zz"])]:
        title = f"lead6 {label} {STAMP}"
        st, created = call("POST", "/api/articles",
                           {"article": {"title": title, "description": "lead6", "body": "lead6 body", "tagList": tags}},
                           token, note=f"create article with tagList={tags}")
        art = (created or {}).get("article", {})
        slug = art.get("slug")
        st2, read = call("GET", f"/api/articles/{slug}", None, token, note="read back the article")
        st3, taglist = call("GET", "/api/tags", None, None, note="global tag list")
        read_tags = (read or {}).get("article", {}).get("tagList")
        global_tags = (taglist or {}).get("tags", [])
        results["cases"].append({
            "label": label, "submitted": tags, "create_status": st, "create_response_tagList": art.get("tagList"),
            "read_status": st2, "read_back_tagList": read_tags,
            "submitted_tags_present_in_global_tags": {t: (t in global_tags) for t in tags},
            "create_response_matches_read_back": art.get("tagList") == read_tags,
        })
    mismatch = [c for c in results["cases"] if not c["create_response_matches_read_back"]]
    results["verdict"] = "BUG_REPRODUCED" if mismatch else "NOT_REPRODUCED"
    results["business_rule"] = ("the tag list returned by the create response must equal what was persisted; "
                                "silently dropping submitted tags without an error or without reflecting it in the response is a defect")
    results["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (OUT / "conduit-summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    for c in results["cases"]:
        print(c["label"], "submitted", c["submitted"], "-> create says", c["create_response_tagList"],
              "-> read back", c["read_back_tagList"], "| global:", c["submitted_tags_present_in_global_tags"])
    print("verdict:", results["verdict"])


if __name__ == "__main__":
    sys.exit(main())
