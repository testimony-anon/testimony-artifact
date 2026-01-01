"""Post-M14 suite evaluation; execution and assertions remain owned by M14."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import time
from decimal import Decimal
from typing import Any, Mapping
from urllib.parse import parse_qsl

from stage6_ground.http_client import HttpResult
from .current_http_runtime import _encode_exact_request_json
from .pytest_export import FrozenSuitePytestRuntime
from .route_s_capture_redaction import sanitize_capture

REPO = Path(__file__).resolve().parents[2]
# Inputs (test map, normal qualification, source-version registry, pristine
# subjects) and outputs (registration, isolated runtimes, outcomes) of one
# suite evaluation.  The defaults are the frozen Astra evaluation; a new
# evaluation (for example the DeepSeek suite) points both at its own roots.
LEGACY = Path(os.environ.get("UISEMTEST_RQ2_LEGACY") or REPO / "eval/ui_semantics/rq2-20260907")
ROOT = Path(os.environ.get("UISEMTEST_RQ2_ROOT") or REPO / "eval/ui_semantics/rq2-suite-20260908")
PROGRESS = REPO / "docs/design/cpv-expansion/rq2-suite-progress-20260908.md"
# The frozen Astra evaluation reused the completed legacy RWA source-fault
# results; any other evaluation executes the RWA source faults itself.
RWA_SOURCE_REUSE = os.environ.get("UISEMTEST_RQ2_RWA_SOURCE", "reuse") == "reuse"
COMPOSE_PREFIX = os.environ.get("UISEMTEST_RQ2_COMPOSE_PREFIX", "uisemtest-rq2-suite")
# Conditional Conduit source faults have no route row in the legacy registry;
# their pairing routes reproduce the frozen test map exactly (verified on all
# 1,983 Astra tests on 2026-09-12).
CONDITIONAL_SOURCE_ROUTES = {"H-C01": [["POST", "/api/users"]], "H-C03": [["POST", "/api/articles"]]}


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def append(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def normal_records() -> dict[str, dict[str, Any]]:
    return {r["test_key"]: r for name in ("normal.jsonl", "normal-conduit.jsonl", "normal-rwa.jsonl")
            for r in lines(LEGACY / name)}


def normal_evidence_dir(evidence_ref: str, evidence_root: str | None = None) -> Path:
    """Normal-qualification evidence lives under the root that executed it."""
    return Path(evidence_root) / evidence_ref if evidence_root else LEGACY / evidence_ref


def object_paths(value: Any, path: list[Any] | None = None):
    path = [] if path is None else path
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from object_paths(item, path + [key])
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from object_paths(item, path + [index])


def at(value: Any, path: list[Any]) -> Any:
    for key in path:
        value = value[key]
    return value


def query(event: Mapping[str, Any]) -> dict[str, Any]:
    return event.get("query") or dict(parse_qsl(event.get("query_string", "")))


def route(event: Mapping[str, Any]) -> str:
    value = event.get("path", "")
    return value.rstrip("/") if isinstance(value, str) else ""


def successful(event: Mapping[str, Any]) -> bool:
    return 200 <= event.get("status", 0) < 300


def named_objects(body: Any, field: str):
    return [(path, obj) for path, obj in object_paths(body) if field in obj]


def collections(body: Any, field: str):
    return [(path + [field], obj[field]) for path, obj in object_paths(body)
            if isinstance(obj.get(field), list)]


def is_list_bank_query(event: Mapping[str, Any]) -> bool:
    body = event.get("request_body") or {}
    if not isinstance(body, dict):
        return False
    document = body.get("query", "")
    return (route(event) == "/graphql" and isinstance(document, str)
            and bool(re.search(r"\blistBankAccount\b", document))
            and not re.search(r"\bmutation\b", document))


def fault_catalog() -> list[dict[str, Any]]:
    # These fixed definitions are independent of test identities and outcomes.
    specs = [
        ("C01", "user.username", "rewrite", ["register", "login", "current_user"]),
        ("C02", "article.body", "rewrite", ["create"]),
        ("C03", "article.tagList", "remove_lexical_first", ["nonempty_tags"]),
        ("C04", "article.body", "old_value", ["edit"]),
        ("C05", "articles", "restore_deleted", ["delete"]),
        ("C06", "comment.body", "rewrite", ["create_comment"]),
        ("C07", "comments", "restore_deleted", ["delete_comment"]),
        ("C08", "article.favorited", "flip", ["favorite", "unfavorite"]),
        ("C09", "article.favoritesCount", "add_one", ["favorite", "unfavorite"]),
        ("C10", "profile.following", "flip", ["follow", "unfollow"]),
        ("C11", "articles", "insert_outside_filter", ["tag"]),
        ("C12-author", "articles", "insert_outside_filter", ["author"]),
        ("C12-favorited", "articles", "insert_outside_filter", ["favorited"]),
        ("C13", "articles", "first_page", ["nonfirst_page"]),
        ("C14-feed", "articles", "remove_identity_first", ["feed"]),
        ("C14-bio", "profile.bio", "old_value", ["update_profile"]),
        ("R01", "user.username", "rewrite", ["check_auth"]),
        ("R02", "account.bankName", "rewrite", ["list_bank_account"]),
        ("R03", "listBankAccount", "insert_other_user", ["list_bank_account"]),
        ("R04", "account.isDeleted", "false", ["soft_delete"]),
        ("R05", "user.firstName", "old_value", ["update_user"]),
        ("R06", "results", "insert_self", ["search"]),
        ("R07", "transaction.amount", "add_one", ["read_transactions"]),
        ("R08", "transaction.description", "rewrite", ["read_transactions"]),
        ("R09-sender", "user.balance", "add_one", ["payment_sender"]),
        ("R09-receiver", "user.balance", "add_one", ["payment_receiver"]),
        ("R10", "transaction.requestStatus", "enum_toggle", ["pending_to_accepted", "accepted_to_pending"]),
        ("R11-participant", "results", "insert_outside_filter", ["participant"]),
        ("R11-date", "results", "insert_outside_filter", ["date"]),
        ("R11-amount", "results", "insert_outside_filter", ["amount"]),
        ("R12", "results", "first_page", ["nonfirst_page"]),
        ("R13-likes", "transaction.likes", "remove_action_member", ["like"]),
        ("R13-comments", "transaction.comments", "remove_action_member", ["comment"]),
        ("R14", "results", "remove_effect_notification", ["payment", "request", "like", "comment"]),
        ("R15", "results", "restore_cleared", ["clear_notification"]),
    ]
    return [{"fault_id": "PR-" + fid, "kind": "response", "subject": "conduit" if fid[0] == "C" else "rwa",
             "legacy_rule": "A-" + fid.split("-")[0], "field": field, "operator": op,
             "substates": variants, "definition_ref": "docs/design/cpv-expansion/rq2-suite-todo-20260908.md#4"}
            for fid, field, op, variants in specs]


def reading_matches(fid: str, event: Mapping[str, Any]) -> bool:
    """Conservative API-only scope; no predicates, phases, arms, or test keys."""
    p, method = route(event), event.get("method")
    if fid == "PR-C01":
        return (method, p) in {("POST", "/api/users"), ("POST", "/api/users/login"), ("GET", "/api/user")}
    if fid in {"PR-R02", "PR-R03", "PR-R04"}:
        return is_list_bank_query(event)
    if method not in {"GET", "HEAD"}:
        return False
    if fid.startswith("PR-C"):
        if fid in {"PR-C02", "PR-C04"}:
            return bool(re.fullmatch(r"/api/articles/[^/]+", p)) and p != "/api/articles/feed"
        if fid in {"PR-C03", "PR-C08", "PR-C09"}:
            return bool(re.fullmatch(r"/api/articles(?:/[^/]+)?", p))
        if fid in {"PR-C05", "PR-C11", "PR-C12-author", "PR-C12-favorited", "PR-C13"}:
            return p == "/api/articles"
        if fid in {"PR-C06", "PR-C07"}:
            return bool(re.fullmatch(r"/api/articles/[^/]+/comments", p))
        if fid in {"PR-C10", "PR-C14-bio"}:
            return bool(re.fullmatch(r"/api/profiles/[^/]+", p))
        return fid == "PR-C14-feed" and p == "/api/articles/feed"
    if fid == "PR-R01":
        return p == "/checkAuth"
    if fid in {"PR-R05", "PR-R09-sender", "PR-R09-receiver"}:
        return p == "/checkAuth" or p == "/users/search" or bool(re.fullmatch(r"/users/[^/]+", p))
    if fid == "PR-R06":
        return p == "/users/search"
    if fid in {"PR-R14", "PR-R15"}:
        return p == "/notifications"
    if fid in {"PR-R11-participant", "PR-R11-date", "PR-R11-amount", "PR-R12"}:
        return p == "/transactions" if fid == "PR-R11-participant" else p in {"/transactions", "/transactions/public", "/transactions/contacts"}
    return bool(re.fullmatch(r"/transactions(?:/[^/]+)?", p))


class PersistentResponseFault:
    """One fixed API behavior, with raw business history scoped to real resets."""

    def __init__(self, definition: Mapping[str, Any]):
        self.definition = dict(definition)
        self.fid = definition["fault_id"]
        self.epoch: Any = None
        self.history: list[dict[str, Any]] = []
        self.activations = 0
        self.changed_responses = 0
        self.substate_counts = {name: 0 for name in definition["substates"]}
        self.misses: dict[str, int] = {}

    def previous_objects(self, identity: str, value: Any, before: int | None = None):
        for event in reversed(self.history if before is None else self.history[:before]):
            for path, obj in object_paths(event.get("body")):
                if obj.get(identity) == value:
                    yield event, path, obj

    def actor_user(self, actor: Any) -> dict[str, Any] | None:
        for event in reversed(self.history):
            if event.get("actor_id") != actor or route(event) not in {"/checkAuth", "/api/user", "/api/users", "/api/users/login"}:
                continue
            for _, obj in named_objects(event.get("body"), "username"):
                if "id" in obj or "email" in obj or "token" in obj:
                    return obj
        return None

    def writes(self, pattern: str, methods: tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE")):
        return [(i, e) for i, e in enumerate(self.history) if successful(e)
                and e.get("method") in methods and re.fullmatch(pattern, route(e))]

    def old_value(self, identity: str, value: Any, field: str, before: int, current: Any) -> Any:
        for _, _, obj in self.previous_objects(identity, value, before):
            if field in obj:
                if type(obj[field]) is type(current) and obj[field] != current:
                    return copy.deepcopy(obj[field])
                break
        raise ValueError("no_observed_different_prior_value")

    def original_resources(self, field: str) -> list[dict[str, Any]]:
        found: dict[Any, dict[str, Any]] = {}
        for event in self.history:
            if not successful(event):
                continue
            for _, obj in named_objects(event.get("body"), field):
                identity = obj.get("slug") if field == "slug" else obj.get("id")
                if isinstance(identity, (str, int)):
                    found[identity] = obj
        return [found[k] for k in sorted(found, key=str)]

    def transform(self, event: Mapping[str, Any], body: Any) -> tuple[Any, list[str]]:
        epoch = event.get("reset_epoch")
        if epoch != self.epoch:
            self.history = []
            self.epoch = epoch
        changed = copy.deepcopy(body)
        activated: list[str] = []
        if successful(event) and reading_matches(self.fid, event):
            try:
                self._apply(event, changed, activated)
            except (KeyError, IndexError, TypeError, ValueError) as error:
                reason = str(error) if isinstance(error, ValueError) else type(error).__name__
                self.misses[reason] = self.misses.get(reason, 0) + 1
        # Raw originals only; never feed an injected value back into its source.
        self.history.append({**event, "body": copy.deepcopy(body)})
        for name in set(activated):
            self.substate_counts[name] += 1
        if activated:
            self.activations += 1
        if changed != body:
            self.changed_responses += 1
        return changed, sorted(set(activated))

    def _apply(self, event: Mapping[str, Any], body: Any, active: list[str]) -> None:
        fid, p, actor, q = self.fid, route(event), event.get("actor_id"), query(event)
        objects = list(object_paths(body))

        def scalar(obj, field, op, substate):
            value = obj.get(field)
            if op == "rewrite" and isinstance(value, str):
                obj[field] = value + " [RQ2]"
            elif op == "add_one" and type(value) in {int, Decimal}:
                obj[field] = value + 1
            elif op == "flip" and type(value) is bool:
                obj[field] = not value
            else:
                return
            active.append(substate)

        def insert(array, obj, identity="id"):
            if not any(isinstance(member, dict) and member.get(identity) == obj.get(identity) for member in array):
                array.append(copy.deepcopy(obj))
                return True
            return False

        if fid in {"PR-C01", "PR-R01"}:
            substate = {"/api/users": "register", "/api/users/login": "login", "/api/user": "current_user"}.get(p, "check_auth")
            for path, obj in objects:
                if fid == "PR-R01" or path == ["user"]:
                    scalar(obj, "username", "rewrite", substate)
        elif fid == "PR-C02":
            created = {obj.get("slug") for _, e in self.writes("/api/articles", ("POST",))
                       for _, obj in named_objects(e.get("body"), "slug")}
            for _, obj in objects:
                if obj.get("slug") in created:
                    scalar(obj, "body", "rewrite", "create")
        elif fid == "PR-C03":
            for _, obj in objects:
                tags = obj.get("tagList")
                if isinstance(tags, list) and tags and all(isinstance(tag, str) for tag in tags):
                    tags.remove(min(tags))
                    active.append("nonempty_tags")
        elif fid == "PR-C04":
            for _, obj in objects:
                for index, write in reversed(self.writes(r"/api/articles/[^/]+", ("PUT",))):
                    returned_slugs = {article.get("slug") for _, article in named_objects(write.get("body"), "slug")}
                    if obj.get("slug") in returned_slugs and "body" in obj:
                        try:
                            obj["body"] = self.old_value("slug", route(write).split("/")[-1], "body", index, obj["body"])
                        except ValueError:
                            break
                        active.append("edit")
                        break
        elif fid in {"PR-C05", "PR-C07"}:
            comment = fid == "PR-C07"
            pattern = re.escape(p) + r"/[^/]+" if comment else r"/api/articles/[^/]+"
            identity, collection_name = ("id", "comments") if comment else ("slug", "articles")
            for index, write in self.writes(pattern, ("DELETE",)):
                value = route(write).split("/")[-1]
                prior = [(e, obj) for e in self.history[:index] for _, obj in object_paths(e.get("body"))
                         if str(obj.get(identity)) == value and "body" in obj]
                if not prior:
                    continue
                obj = prior[-1][1]
                if not comment and not self.article_in_query(obj, q, actor):
                    continue
                for _, array in collections(body, collection_name):
                    if insert(array, obj, identity):
                        active.append("delete_comment" if comment else "delete")
        elif fid == "PR-C06":
            created = {str(obj.get("id")) for _, e in self.writes(re.escape(p), ("POST",))
                       for _, obj in named_objects(e.get("body"), "body") if "id" in obj}
            for _, obj in objects:
                if str(obj.get("id")) in created:
                    scalar(obj, "body", "rewrite", "create_comment")
        elif fid in {"PR-C08", "PR-C09"}:
            latest = {}
            for _, write in self.writes(r"/api/articles/[^/]+/favorite", ("POST", "DELETE")):
                if write.get("actor_id") == actor:
                    latest[route(write).split("/")[-2]] = write["method"]
            for _, obj in objects:
                if obj.get("slug") in latest:
                    scalar(obj, "favorited" if fid == "PR-C08" else "favoritesCount",
                           "flip" if fid == "PR-C08" else "add_one",
                           "favorite" if latest[obj["slug"]] == "POST" else "unfavorite")
        elif fid == "PR-C10":
            writes = [(i, e) for i, e in self.writes(re.escape(p) + "/follow", ("POST", "DELETE"))
                      if e.get("actor_id") == actor]
            if writes:
                for path, obj in objects:
                    if path == ["profile"]:
                        scalar(obj, "following", "flip", "follow" if writes[-1][1]["method"] == "POST" else "unfollow")
        elif fid in {"PR-C11", "PR-C12-author", "PR-C12-favorited"}:
            selector = {"PR-C11": "tag", "PR-C12-author": "author", "PR-C12-favorited": "favorited"}[fid]
            if not q.get(selector):
                return
            for _, array in collections(body, "articles"):
                for article in self.original_resources("slug"):
                    wrong = (q[selector] not in article.get("tagList", []) if selector == "tag"
                             else (article.get("author") or {}).get("username") != q[selector] if selector == "author"
                             else self.favorite_known_false(article.get("slug"), q[selector]))
                    other = {key: val for key, val in q.items() if key != selector}
                    if wrong and self.article_in_query(article, other, actor) and insert(array, article, "slug"):
                        active.append(selector)
                        break
        elif fid in {"PR-C13", "PR-R12"}:
            page_key, first, field = ("offset", "0", "articles") if fid == "PR-C13" else ("page", "1", "results")
            if str(q.get(page_key, first)) in {first, "", "0"}:
                return
            selectors = {k: str(v) for k, v in q.items() if k != page_key}
            for previous in reversed(self.history):
                pq = query(previous)
                if (route(previous) != p or previous.get("actor_id") != actor or previous.get("method") != "GET"
                    or str(pq.get(page_key, first)) != first
                    or {k: str(v) for k, v in pq.items() if k != page_key} != selectors):
                    continue
                for path, array in collections(body, field):
                    prior_arrays = collections(previous.get("body"), field)
                    if len(prior_arrays) == 1 and len(prior_arrays[0][1]) == len(array) and array:
                        parent = at(body, path[:-1])
                        parent[path[-1]] = copy.deepcopy(prior_arrays[0][1])
                        active.append("nonfirst_page")
                break
        elif fid == "PR-C14-feed":
            for _, array in collections(body, "articles"):
                if array and all(isinstance(a, dict) and isinstance(a.get("slug"), str) for a in array):
                    array.pop(min(range(len(array)), key=lambda i: array[i]["slug"]))
                    active.append("feed")
        elif fid == "PR-C14-bio":
            for path, obj in objects:
                if path == ["profile"] and "bio" in obj:
                    for index, write in reversed(self.writes("/api/user", ("PUT",))):
                        usernames = {user.get("username") for _, user in named_objects(write.get("body"), "username")}
                        if obj.get("username") in usernames:
                            try:
                                obj["bio"] = self.old_value("username", obj["username"], "bio", index, obj["bio"])
                            except ValueError:
                                break
                            active.append("update_profile")
                            break
        else:
            self._apply_rwa(event, body, active, scalar, insert)

    def favorite_known_false(self, slug: Any, username: Any) -> bool:
        for event in reversed(self.history):
            user = self.actor_user(event.get("actor_id"))
            if user is None or user.get("username") != username:
                continue
            for _, obj in object_paths(event.get("body")):
                if obj.get("slug") == slug and type(obj.get("favorited")) is bool:
                    return obj["favorited"] is False
        return False

    def article_in_query(self, article: Mapping[str, Any], q: Mapping[str, Any], actor: Any) -> bool:
        if q.get("tag") and q["tag"] not in article.get("tagList", []):
            return False
        if q.get("author") and (article.get("author") or {}).get("username") != q["author"]:
            return False
        if q.get("favorited"):
            for event in reversed(self.history):
                user = self.actor_user(event.get("actor_id"))
                if user and user.get("username") == q["favorited"]:
                    for _, obj in object_paths(event.get("body")):
                        if obj.get("slug") == article.get("slug") and type(obj.get("favorited")) is bool:
                            return obj["favorited"]
            return False
        return True

    def _apply_rwa(self, event, body, active, scalar, insert):
        fid, p, actor, q = self.fid, route(event), event.get("actor_id"), query(event)
        objects = list(object_paths(body))
        if fid == "PR-R02":
            for _, array in collections(body, "listBankAccount"):
                for account in array:
                    if isinstance(account, dict):
                        scalar(account, "bankName", "rewrite", "list_bank_account")
        elif fid == "PR-R03":
            user = self.actor_user(actor)
            for _, array in collections(body, "listBankAccount"):
                owners = {a.get("userId") for a in array if isinstance(a, dict)}
                owner = user.get("id") if user else next(iter(owners)) if len(owners) == 1 else None
                if owner is None:
                    continue
                for account in self.original_resources("bankName"):
                    if account.get("userId") is not None and account["userId"] != owner and insert(array, account):
                        active.append("list_bank_account")
                        break
        elif fid == "PR-R04":
            deleted = set()
            for _, write in self.writes("/graphql", ("POST",)):
                request = write.get("request_body") or {}
                if (isinstance(request, dict) and "deleteBankAccount" in str(request.get("query", ""))
                    and (write.get("body") or {}).get("data", {}).get("deleteBankAccount") is True):
                    identifier = (request.get("variables") or {}).get("id")
                    if isinstance(identifier, (str, int)):
                        deleted.add(identifier)
            for _, obj in objects:
                if obj.get("id") in deleted and obj.get("isDeleted") is True:
                    obj["isDeleted"] = False
                    active.append("soft_delete")
        elif fid == "PR-R05":
            for _, obj in objects:
                if "id" not in obj or "firstName" not in obj:
                    continue
                for index, write in reversed(self.writes(r"/users/[^/]+", ("PATCH",))):
                    if route(write).split("/")[-1] != obj["id"] or "firstName" not in (write.get("request_body") or {}):
                        continue
                    try:
                        obj["firstName"] = self.old_value("id", obj["id"], "firstName", index, obj["firstName"])
                    except ValueError:
                        continue
                    active.append("update_user")
                    break
        elif fid == "PR-R06":
            user = self.actor_user(actor)
            if user and "id" in user:
                # checkAuth's user is the ordinary public user object; never copy
                # token/password/session fields from another response envelope.
                public = {k: copy.deepcopy(v) for k, v in user.items()
                          if k not in {"password", "token", "accessToken", "refreshToken"}}
                for _, array in collections(body, "results"):
                    if insert(array, public):
                        active.append("search")
        elif fid in {"PR-R07", "PR-R08", "PR-R10"}:
            for _, obj in objects:
                if not all(key in obj for key in ("id", "senderId", "receiverId")):
                    continue
                if fid == "PR-R07":
                    scalar(obj, "amount", "add_one", "read_transactions")
                elif fid == "PR-R08":
                    scalar(obj, "description", "rewrite", "read_transactions")
                elif obj.get("requestStatus") in {"pending", "accepted"}:
                    before = obj["requestStatus"]
                    obj["requestStatus"] = "accepted" if before == "pending" else "pending"
                    active.append(before + "_to_" + obj["requestStatus"])
        elif fid in {"PR-R09-sender", "PR-R09-receiver"}:
            field = "senderId" if fid.endswith("sender") else "receiverId"
            participants = set()
            for _, write in self.writes("/transactions", ("POST",)):
                request = write.get("request_body") or {}
                if isinstance(request, dict) and request.get("transactionType") == "payment":
                    participants.update(obj[field] for _, obj in object_paths(write.get("body")) if field in obj)
            for _, obj in objects:
                if obj.get("id") in participants:
                    scalar(obj, "balance", "add_one", "payment_sender" if field == "senderId" else "payment_receiver")
        elif fid.startswith("PR-R11-"):
            kind = fid.rsplit("-", 1)[-1]
            user = self.actor_user(actor)
            for _, array in collections(body, "results"):
                resources = self.original_resources("senderId") if kind == "participant" else self.filter_scope_resources(event, kind)
                for transaction in resources:
                    if not {"id", "senderId", "receiverId", "amount"} <= transaction.keys():
                        continue
                    wrong = False
                    if kind == "participant" and user and user.get("id") is not None:
                        wrong = user["id"] not in {transaction["senderId"], transaction["receiverId"]}
                    elif kind == "amount" and q.get("amountMin") is not None and q.get("amountMax") is not None:
                        lower, upper = Decimal(str(q["amountMin"])), Decimal(str(q["amountMax"]))
                        wrong = lower != 0 and upper != 0 and lower < upper and not lower <= transaction["amount"] < upper
                    elif kind == "date" and q.get("dateRangeStart") and q.get("dateRangeEnd") and transaction.get("createdAt"):
                        start, end, value = [parse_time(v) for v in (q["dateRangeStart"], q["dateRangeEnd"], transaction["createdAt"])]
                        wrong = start <= end and not start <= value <= end
                    if wrong and self.other_transaction_filters(transaction, q, kind) and insert(array, transaction):
                        active.append(kind)
                        break
        elif fid in {"PR-R13-likes", "PR-R13-comments"}:
            field = "likes" if fid.endswith("likes") else "comments"
            for _, obj in objects:
                if "id" not in obj or not isinstance(obj.get(field), list):
                    continue
                actions = self.writes("/" + field + "/" + re.escape(str(obj["id"])), ("POST",))
                for index, action in actions:
                    member_ids = {item["id"] for _, item in object_paths(action.get("body"))
                                  if "id" in item and item.get("transactionId") == obj["id"]}
                    if not member_ids:
                        prior_arrays = [old_obj[field] for old in reversed(self.history[:index])
                                        for _, old_obj in object_paths(old.get("body"))
                                        if old_obj.get("id") == obj["id"] and isinstance(old_obj.get(field), list)]
                        if prior_arrays:
                            old_ids = {member.get("id") for member in prior_arrays[0] if isinstance(member, dict)}
                            new_ids = {member.get("id") for member in obj[field] if isinstance(member, dict)} - old_ids
                            if len(new_ids) == 1:
                                member_ids = new_ids
                    candidates = [i for i, member in enumerate(obj[field]) if isinstance(member, dict)
                                  and member.get("id") in member_ids]
                    if len(candidates) == 1:
                        obj[field].pop(candidates[0])
                        active.append("like" if field == "likes" else "comment")
        elif fid == "PR-R14":
            user = self.actor_user(actor)
            for _, array in collections(body, "results"):
                recipients = {n.get("userId") for n in array if isinstance(n, dict) and n.get("userId") is not None}
                recipient = user.get("id") if user else next(iter(recipients)) if len(recipients) == 1 else None
                if recipient is None:
                    continue
                remove = set()
                for index, action in self.writes(r"/(?:transactions|likes/[^/]+|comments/[^/]+)", ("POST",)):
                    ap = route(action)
                    kind = "like" if ap.startswith("/likes/") else "comment" if ap.startswith("/comments/") else "transaction"
                    if kind == "transaction":
                        request = action.get("request_body") or {}
                        if not isinstance(request, dict) or request.get("transactionType") not in {"payment", "request"}:
                            continue
                        kind = request["transactionType"]
                        transaction_ids = {o["id"] for _, o in object_paths(action.get("body")) if "id" in o and "senderId" in o}
                    else:
                        transaction_ids = {ap.split("/")[-1]}
                    effect_key = {"payment": "status", "request": "status", "like": "likeId", "comment": "commentId"}[kind]
                    interaction_ids = {o["id"] for _, o in object_paths(action.get("body"))
                                       if "id" in o and o.get("transactionId") in transaction_ids}
                    matches = [i for i, notification in enumerate(array) if isinstance(notification, dict)
                               and notification.get("transactionId") in transaction_ids
                               and effect_key in notification
                               and notification.get("userId") == recipient
                               and (kind not in {"payment", "request"} or notification.get("status") ==
                                    ("received" if kind == "payment" else "requested"))
                               and (kind in {"payment", "request"} or not interaction_ids or notification.get(effect_key) in interaction_ids)]
                    if kind not in {"payment", "request"} and not interaction_ids:
                        prior_arrays = [arr for old in reversed(self.history[:index])
                                        if route(old) == p and old.get("actor_id") == actor
                                        for _, arr in collections(old.get("body"), "results")]
                        if not prior_arrays:
                            continue
                        prior_ids = {n.get("id") for n in prior_arrays[0] if isinstance(n, dict)}
                        matches = [i for i in matches if array[i].get("id") not in prior_ids]
                        if len(matches) != 1:
                            continue
                    if matches:
                        remove.update(matches)
                        active.append(kind)
                for index in sorted(remove, reverse=True):
                    array.pop(index)
        elif fid == "PR-R15":
            user = self.actor_user(actor)
            for index, clear in self.writes(r"/notifications/[^/]+", ("PATCH",)):
                if clear.get("actor_id") != actor or (clear.get("request_body") or {}).get("isRead") is not True:
                    continue
                identifier = route(clear).split("/")[-1]
                old = list(self.previous_objects("id", identifier, index))
                old = [obj for _, _, obj in old if "transactionId" in obj and
                       (not user or obj.get("userId") == user.get("id"))]
                if old:
                    for _, array in collections(body, "results"):
                        if insert(array, old[0]):
                            active.append("clear_notification")

    def filter_scope_resources(self, event, kind):
        excluded = {"dateRangeStart", "dateRangeEnd"} if kind == "date" else {"amountMin", "amountMax"}
        excluded |= {"page", "limit"}
        selectors = {k: str(v) for k, v in query(event).items() if k not in excluded}
        found = {}
        for old in self.history:
            if (route(old) != route(event) or old.get("actor_id") != event.get("actor_id")
                or old.get("method") != "GET" or not successful(old)
                or {k: str(v) for k, v in query(old).items() if k not in excluded} != selectors):
                continue
            for _, array in collections(old.get("body"), "results"):
                for obj in array:
                    if isinstance(obj, dict) and "id" in obj:
                        found[obj["id"]] = obj
        return [found[key] for key in sorted(found, key=str)]

    def other_transaction_filters(self, transaction, q, changed_filter):
        if changed_filter != "amount" and q.get("amountMin") is not None and q.get("amountMax") is not None:
            lower, upper = Decimal(str(q["amountMin"])), Decimal(str(q["amountMax"]))
            if lower != 0 and upper != 0 and not lower <= transaction["amount"] < upper:
                return False
        if changed_filter != "date" and q.get("dateRangeStart") and q.get("dateRangeEnd"):
            if not transaction.get("createdAt") or not parse_time(q["dateRangeStart"]) <= parse_time(transaction["createdAt"]) <= parse_time(q["dateRangeEnd"]):
                return False
        return True


def parse_time(value: Any) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.UTC)


class ResponseRecorder:
    """HTTP seam before parsing/capture, with raw-only in-memory fault state."""
    def __init__(self, path: Path, definition: Mapping[str, Any] | None = None):
        self.path = path
        self.fault = PersistentResponseFault(definition) if definition else None
        self.events: list[dict[str, Any]] = []

    @property
    def hit(self) -> bool:
        return bool(self.fault and self.fault.changed_responses)

    def __call__(self, metadata: Mapping[str, Any], result: HttpResult | OSError) -> HttpResult | OSError:
        meta = dict(metadata)
        secrets = meta.pop("sensitive_values", ())
        removed = list(meta.pop("removed_strings", ()))
        replacement = result
        active: list[str] = []
        original = changed = None
        parseable = False
        if not isinstance(result, OSError):
            try:
                exact = json.loads(result.body_text, parse_float=Decimal)
                parseable = True
            except (ValueError, TypeError):
                exact = None
            if parseable:
                original = result.json()
                transformed = exact
                if self.fault:
                    transformed, active = self.fault.transform({**meta, "status": result.status}, exact)
                if transformed != exact:
                    replacement = copy.deepcopy(result)
                    replacement.body_text = _encode_exact_request_json(transformed)
                changed = replacement.json()
            elif self.fault:
                self.fault.transform({**meta, "status": result.status}, None)
        elif self.fault:
            self.fault.transform({**meta, "status": 0}, None)
        record = {**meta, "event_index": len(self.events), "status": result.status if not isinstance(result, OSError) else 0,
                  "json_parseable": parseable, "original_body": original, "body": changed,
                  "mutation_applied": replacement is not result, "activation_substates": active,
                  "transport_error": type(result).__name__ if isinstance(result, OSError) else None}
        if not parseable and not isinstance(result, OSError):
            record.update(non_json_body_text=(result.body_text or "")[:8192],
                          non_json_body_truncated=len(result.body_text or "") > 8192)
        safe, _ = sanitize_capture(record, sensitive_values=secrets, removed_strings=removed)
        self.events.append(safe)
        append(self.path, safe)
        return replacement


def registration_events(row: Mapping[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = copy.deepcopy(events)
    for event in events:
        if isinstance(event.get("path"), str):
            continue
        matches = {request["canonical_path"] for request in row["request_coverage"]
                   if all(request.get(key) == event.get(key) for key in ("request_ref", "actor_id", "method"))}
        if len(matches) != 1:
            raise ValueError("redacted HTTP route lacks unique frozen request coverage")
        event["path"] = matches.pop()
    return events


def impossible_trigger(definition, events, matched):
    """Exclude only absent structural prerequisites in complete normal plans."""
    fid = definition["fault_id"]
    writes = {
        "PR-C02": ("/api/articles", {"POST"}),
        "PR-C04": (r"/api/articles/[^/]+", {"PUT"}),
        "PR-C05": (r"/api/articles/[^/]+", {"DELETE"}),
        "PR-C06": (r"/api/articles/[^/]+/comments", {"POST"}),
        "PR-C07": (r"/api/articles/[^/]+/comments/[^/]+", {"DELETE"}),
        "PR-C08": (r"/api/articles/[^/]+/favorite", {"POST", "DELETE"}),
        "PR-C09": (r"/api/articles/[^/]+/favorite", {"POST", "DELETE"}),
        "PR-C10": (r"/api/profiles/[^/]+/follow", {"POST", "DELETE"}),
        "PR-C14-bio": ("/api/user", {"PUT"}),
        "PR-R04": ("/graphql", {"POST"}),
        "PR-R05": (r"/users/[^/]+", {"PATCH"}),
        "PR-R09-sender": ("/transactions", {"POST"}),
        "PR-R09-receiver": ("/transactions", {"POST"}),
        "PR-R13-likes": (r"/likes/[^/]+", {"POST"}),
        "PR-R13-comments": (r"/comments/[^/]+", {"POST"}),
        "PR-R14": (r"/(?:transactions|likes/[^/]+|comments/[^/]+)", {"POST"}),
        "PR-R15": (r"/notifications/[^/]+", {"PATCH"}),
    }
    if fid in writes:
        pattern, methods = writes[fid]
        if not any(e.get("method") in methods and re.fullmatch(pattern, route(e)) for e in events):
            return "complete_normal_plan_has_no_required_business_write"
    if fid == "PR-R04":
        graph = [e.get("request_body") for e in events if route(e) == "/graphql" and e.get("method") == "POST"]
        if graph and all(isinstance(body, dict) and isinstance(body.get("query"), str)
                         and "deleteBankAccount" not in body["query"] for body in graph):
            return "complete_normal_graphql_plan_has_no_deleteBankAccount"
    query_fields = {
        "PR-C11": {"tag"}, "PR-C12-author": {"author"}, "PR-C12-favorited": {"favorited"},
        "PR-R11-date": {"dateRangeStart", "dateRangeEnd"}, "PR-R11-amount": {"amountMin", "amountMax"},
    }
    if fid in query_fields:
        fields = query_fields[fid]
        if all(not fields <= query(e).keys() and "$route_s_redacted" not in query(e) for e in matched):
            return "all_normal_reads_lack_required_filter_keys"
    if fid in {"PR-C13", "PR-R12"}:
        key, default = ("offset", "0") if fid == "PR-C13" else ("page", "1")
        if all(str(query(e).get(key, default)) in {"", "0", default} and "$route_s_redacted" not in query(e) for e in matched):
            return "all_normal_reads_are_first_page"
    return None


def register() -> None:
    if (ROOT / "selection.json").exists():
        raise ValueError("suite registration is already frozen")
    normal = normal_records()
    tests = lines(LEGACY / "test-map.jsonl")
    if any(row["test_key"] not in normal for row in tests):
        raise ValueError("normal qualification is incomplete")
    facts = {}
    for row in tests:
        if normal[row["test_key"]].get("qualified"):
            facts[row["test_key"]] = registration_events(
                row, lines(normal_evidence_dir(normal[row["test_key"]]["evidence_ref"],
                                               normal[row["test_key"]].get("evidence_root")) / "http.jsonl"))
    catalog = fault_catalog()
    for definition in catalog:
        paired = []
        skipped = []
        read_pairs = 0
        for row in tests:
            if row["subject"] != definition["subject"] or row["test_key"] not in facts:
                continue
            matched = [e for e in facts[row["test_key"]] if reading_matches(definition["fault_id"], e)]
            # A completed normal execution provides all originally scheduled
            # reads; matching any read is conservative even if trigger is absent.
            if matched:
                read_pairs += 1
                skip = impossible_trigger(definition, facts[row["test_key"]], matched)
                if skip:
                    skipped.append({"test_key": row["test_key"], "skip_basis": skip})
                    continue
                pair = {"fault_id": definition["fault_id"], "test_key": row["test_key"],
                        "subject": row["subject"], "basis": "all qualified tests with matching actual normal API reads",
                        "normal_evidence_ref": normal[row["test_key"]]["evidence_ref"],
                        "normal_evidence_root": normal[row["test_key"]].get("evidence_root"),
                        "matched_request_refs": sorted({e["request_ref"] for e in matched})}
                paired.append(pair)
                append(ROOT / "test-fault-map.jsonl", pair)
        definition["paired_tests"] = len(paired)
        definition["read_route_pairs_before_trigger_filter"] = read_pairs
        definition["structurally_impossible_tests"] = skipped
        definition["estimated_seconds_from_normal"] = sum(normal[p["test_key"]]["elapsed_seconds"] for p in paired)
        definition["substate_status"] = {name: "pending_activation_evaluation" for name in definition["substates"]}
        append(ROOT / "response-faults.jsonl", definition)
    source_counts = {}
    executed_subjects = ("conduit",) if RWA_SOURCE_REUSE else ("conduit", "rwa")
    for version in lines(LEGACY / "source-versions.jsonl"):
        if version["subject"] in executed_subjects and version["fault_id"] != "normal" and version["status"] == "included":
            fid = version["fault_id"]
            source_counts[fid] = sum(row["test_key"] in facts and fid in row["fault_ids"] for row in tests)
    save(ROOT / "selection.json", {
        "registered_at": dt.datetime.now(dt.UTC).isoformat(), "fault_definitions": catalog,
        "legacy_root": str(LEGACY), "normal_qualification_ref": [name for name in ("normal.jsonl", "normal-conduit.jsonl", "normal-rwa.jsonl")
                                                               if (LEGACY / name).is_file()],
        "test_selection": ("RQ1 correct and original normal_pass; API-only read coverage, trigger uncertainty retained"
                           if RWA_SOURCE_REUSE else
                           "qualified normal_pass on the isolated normal version; API-only read coverage, trigger uncertainty retained; RQ1 labels joined at reporting time"),
        "excluded_tests": [{"test_key": row["test_key"], "reason": "original_qualification_not_passed_or_RQ1_not_correct"}
                           for row in tests if row["test_key"] not in facts],
        "qualified_tests": {subject: sum(row["subject"] == subject and row["test_key"] in facts for row in tests)
                            for subject in ("conduit", "rwa")},
        "persistent_response_faults": len(catalog), "source_conduit_pairs": source_counts,
        "rwa_source_results": "reuse_existing_completed_results" if RWA_SOURCE_REUSE else "executed_in_this_root",
        "no_response_location_or_test_id_in_fault_identity": True,
        "prior_results_disclosure": "revised after old single-location diagnostic; not a holdout",
    })
    reference = {"patches_and_versions_ref": str(LEGACY / "source-versions.jsonl"),
                 "new_conduit_output": str(ROOT / "outcomes-source-conduit.jsonl"), "planned_pairs": source_counts}
    if RWA_SOURCE_REUSE:
        reference["reused_rwa"] = {"outcomes_ref": str(LEGACY / "outcomes-rwa.jsonl"), "fault_ids": [f"B-R{i:02}" for i in range(1, 25)],
                                   "qualified_pairs": 11456, "status": "reuse_existing_completed_results"}
    else:
        reference["new_rwa_output"] = str(ROOT / "outcomes-source-rwa.jsonl")
    save(ROOT / "source-results-reference.json", reference)
    print(json.dumps({"response_pairs": {s: sum(f["paired_tests"] for f in catalog if f["subject"] == s) for s in ("conduit", "rwa")},
                      "read_route_pairs_before": {s: sum(f["read_route_pairs_before_trigger_filter"] for f in catalog if f["subject"] == s) for s in ("conduit", "rwa")},
                      "estimated_seconds": {s: sum(f["estimated_seconds_from_normal"] for f in catalog if f["subject"] == s) for s in ("conduit", "rwa")},
                      "source_conduit_pairs": sum(source_counts.values()),
                      "per_fault": {f["fault_id"]: f["paired_tests"] for f in catalog}}), flush=True)


def project_outcome(result: Mapping[str, Any] | None, layer: str, http: list[Mapping[str, Any]],
                    expected: list[Mapping[str, Any]], *, error: str | None = None) -> dict[str, Any]:
    runs = list((result or {}).get("runs", []))
    actual = [a for run in runs for a in run.get("assertion_results", [])]
    completed = bool(runs) and all(r.get("mechanical_status") == "complete" for r in runs)
    by_id = {a["assertion_id"]: a for a in actual}
    generic = [a for a in expected if a["assertion_class"] == "generic"]
    primary = [a for a in expected if a["assertion_class"] != "generic"]
    app_failure = any(e.get("status", 0) >= 500 for e in http)
    selected = list(generic)
    states = []
    for level in range(3):
        if level == 1 and layer == "basic_constraint":
            selected += primary
        if level == 2 and layer == "business_relation":
            selected += primary
        verdicts = [by_id.get(a["assertion_id"], {}).get("verdict", "unable") for a in selected]
        failed = app_failure or "failed" in verdicts
        complete = completed and bool(http) and all(v == "passed" for v in verdicts)
        states.append("detected" if failed else "completed_not_detected" if complete else "unknown")
    business = layer == "business_relation" and any(by_id.get(a["assertion_id"], {}).get("verdict") == "failed" for a in primary)
    business_state = "no_business_tests" if layer != "business_relation" else (
        "detected" if business else "completed_not_detected" if completed and primary and
        all(by_id.get(a["assertion_id"], {}).get("verdict") == "passed" for a in primary) else "unknown")
    all_evaluable = completed and all(by_id.get(a["assertion_id"], {}).get("verdict") in {"passed", "failed"} for a in expected)
    return {"O0": states[0], "O1": states[1], "O2": states[2], "B": business_state, "business_direct_alarm": business,
            "common_observation": all_evaluable, "mechanical_complete": completed, "application_5xx": app_failure,
            "error": error, "assertion_results": actual}


def reduce_fault(outcomes: list[Mapping[str, Any]], key: str) -> str:
    if not outcomes:
        return "no_eligible_tests"
    if any(r[key] == "detected" for r in outcomes):
        return "detected"
    if all(r[key] == "completed_not_detected" for r in outcomes):
        return "completed_not_detected"
    return "unknown"


def prepare_isolation() -> None:
    """New writable runtime directories; old images and results stay unchanged."""
    if (ROOT / "source-versions.jsonl").exists():
        return
    for version in lines(LEGACY / "source-versions.jsonl"):
        if version["status"] != "included":
            continue
        subject, fid = version["subject"], version["fault_id"]
        if subject == "rwa" and fid != "normal" and RWA_SOURCE_REUSE:
            continue
        row = copy.deepcopy(version)
        row["original_version_ref"] = str(LEGACY / "source-versions.jsonl")
        if subject == "rwa":
            destination = ROOT / "subjects/rwa" / fid
            if not destination.exists():
                # The normal version is a fresh copy of the never-run pristine
                # checkout; a fault version copies its registered patched checkout.
                origin = LEGACY / "subjects/rwa/pristine" if fid == "normal" else Path(version["source_root"]).resolve(strict=True)
                shutil.copytree(origin, destination, symlinks=True)
                node_modules = destination / "node_modules"
                if not node_modules.is_symlink() and not node_modules.exists():
                    node_modules.symlink_to((LEGACY / "subjects/rwa/normal/node_modules").resolve(strict=True),
                                            target_is_directory=True)
            row["source_root"] = str(destination)
        else:
            destination = ROOT / "deploy" / fid
            destination.mkdir(parents=True, exist_ok=True)
            old_deploy = Path(version["deploy_root"])
            compose = (old_deploy / "docker-compose.yml").read_text()
            compose = re.sub(r"(?m)^name: .*", f"name: {COMPOSE_PREFIX}-" + fid.lower(), compose)
            (destination / "docker-compose.yml").write_text(compose)
            shutil.copy2(old_deploy / "reset.sh", destination / "reset.sh")
            row["deploy_root"] = str(destination)
        append(ROOT / "source-versions.jsonl", row)


def require_live() -> None:
    from .execution_guard import require_active_authorization
    require_active_authorization(repo_root=REPO, entrypoint="scripts/uisemtest-rq2", capability="live")


def configure_subject(subject: str, fid: str) -> None:
    versions = [v for v in lines(ROOT / "source-versions.jsonl")
                if v["subject"] == subject and v["fault_id"] == fid and v["status"] == "included"]
    if len(versions) != 1:
        raise ValueError("expected exactly one isolated runtime version")
    version = versions[0]
    if subject == "rwa":
        source = Path(version["source_root"]).resolve(strict=True)
        if not source.is_relative_to(ROOT / "subjects"):
            raise ValueError("refusing writable RWA checkout outside new isolation")
        os.environ["UISEMTEST_RWA_CHECKOUT"] = str(source)
    else:
        deploy = Path(version["deploy_root"]).resolve(strict=True)
        if not deploy.is_relative_to(ROOT / "deploy"):
            raise ValueError("refusing old/nonisolated Conduit deployment")
        os.environ["UISEMTEST_CONDUIT_DEPLOY_ROOT"] = str(deploy)
        os.environ["UISEMTEST_CONDUIT_OUTPUT_ROOT"] = str(ROOT / "runs/conduit/lifecycle" / fid)


def execute_pairs(subject: str, pairs: list[dict[str, Any]], *, kind: str,
                  definition: Mapping[str, Any] | None = None, source_fault: str = "normal",
                  retry_errors: bool = False, limit: int | None = None) -> None:
    require_live()
    configure_subject(subject, source_fault)
    tests = {r["test_key"]: r for r in lines(LEGACY / "test-map.jsonl")}
    output = ROOT / f"outcomes-{kind}-{subject}.jsonl"
    latest = {(r["fault_id"], r["test_key"]): r for r in lines(output)}
    pending = [p for p in pairs if (p["fault_id"], p["test_key"]) not in latest or
               (retry_errors and latest[p["fault_id"], p["test_key"]].get("error"))]
    if limit is not None:
        pending = pending[:limit]
    owner = runtime = recorder = None
    current_source = None

    def transform(meta, result):
        if recorder is None:
            raise RuntimeError("response outside a registered test execution")
        return recorder(meta, result)

    try:
        for index, pair in enumerate(pending):
            row = tests[pair["test_key"]]
            if current_source != row["source_run"]:
                if runtime is not None and runtime is not owner:
                    runtime.close()
                base = ROOT / "runs" / subject / kind / "runtime" / source_fault / row["case_id"]
                attempt = 1
                while (base / f"{attempt:04}").exists():
                    attempt += 1
                runtime = FrozenSuitePytestRuntime(Path(row["source_run"]), base / f"{attempt:04}")
                runtime.open(external_lifecycle=owner is not None, response_transform=transform)
                if owner is None:
                    owner = runtime
                current_source = row["source_run"]
            path = ROOT / "runs" / subject / kind / pair["fault_id"] / row["case_id"] / row["test_id"]
            attempt = 1
            while (path / f"attempt-{attempt:03}").exists():
                attempt += 1
            path = path / f"attempt-{attempt:03}"
            path.mkdir(parents=True, exist_ok=False)
            recorder = ResponseRecorder(path / "http.jsonl", definition)
            started = time.monotonic()
            result = error = None
            try:
                result = runtime.run_retained_test(row["test_id"], execution_id=f'{pair["fault_id"]}-{attempt}')
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started
            save(path / "result.json", {"result": result, "error": error, "elapsed_seconds": elapsed})
            projection = project_outcome(result, row["layer"], recorder.events,
                                         runtime._tests[row["test_id"]]["assertions"], error=error)
            record = {**pair, "kind": kind, "subject": subject, "layer": row["layer"],
                      "attempt": attempt, "retry_reason": "engineering error or interrupted directory" if attempt > 1 else None,
                      "elapsed_seconds": elapsed, "evidence_ref": str(path.relative_to(ROOT)), **projection}
            if recorder.fault:
                fault = recorder.fault
                record.update(activation_count=fault.activations, changed_response_count=fault.changed_responses,
                              activation_substates=fault.substate_counts, mutation_misses=fault.misses,
                              activation_status="activated" if fault.changed_responses else "no_activation")
                if not fault.changed_responses and any(record[key] == "detected" for key in ("O0", "O1", "O2")):
                    # A failure before any injected change cannot substantiate
                    # detection of this response fault.
                    record.update(O0="unknown", O1="unknown", O2="unknown", B="unknown", business_direct_alarm=False,
                                  common_observation=False, attribution_reason="failure_without_response_change")
            append(output, record)
            print(json.dumps({"subject": subject, "kind": kind, "fault": pair["fault_id"],
                              "completed": index + 1, "planned": len(pending), "test": row["test_key"],
                              "O2": record["O2"], "activation": record.get("activation_count"),
                              "seconds": round(elapsed, 2), "error": error}), flush=True)
            if (kind == "response" and not recorder.hit
                and (error or (result or {}).get("final_status") != "normal_pass")):
                raise RuntimeError("normal-version execution failed before any response change; preserved attempt, stop dispatch for engineering diagnosis")
    finally:
        if runtime is not None and runtime is not owner:
            runtime.close()
        if owner is not None:
            owner.close()


def run_responses(subject: str, *, fault_id: str | None = None, limit: int | None = None,
                  retry_errors: bool = False) -> None:
    catalog = [d for d in lines(ROOT / "response-faults.jsonl") if d["subject"] == subject
               and (fault_id is None or d["fault_id"] == fault_id)]
    mapped = lines(ROOT / "test-fault-map.jsonl")
    for definition in catalog:
        pairs = [p for p in mapped if p["fault_id"] == definition["fault_id"]]
        execute_pairs(subject, pairs, kind="response", definition=definition, retry_errors=retry_errors, limit=limit)


def run_sources(subject: str, *, fault_id: str | None = None, limit: int | None = None,
                retry_errors: bool = False) -> None:
    if subject != "conduit" and RWA_SOURCE_REUSE:
        raise ValueError("RWA source results are complete and must be reused")
    normal = normal_records()
    mapped = lines(LEGACY / "test-map.jsonl")
    versions = [v for v in lines(ROOT / "source-versions.jsonl") if v["subject"] == subject
                and v["fault_id"] != "normal" and v["status"] == "included"
                and (fault_id is None or v["fault_id"] == fault_id)]
    for version in sorted(versions, key=lambda v: v["fault_id"]):
        pairs = [{"fault_id": version["fault_id"], "test_key": r["test_key"]} for r in mapped
                 if r["subject"] == subject and version["fault_id"] in r["fault_ids"] and normal[r["test_key"]].get("qualified")]
        execute_pairs(subject, pairs, kind="source", source_fault=version["fault_id"], retry_errors=retry_errors, limit=limit)


def composition_catalog():
    # Fixed compositions (rq2-flow-compositions-20260907): the Astra-round anchor
    # test ids are kept for provenance; on any other evaluated suite the anchor is
    # re-selected by case, protocol and producer route (lexicographically first
    # retained business test), never by outcome.
    fixed_defs = [
        ("C-C01", "conduit", "L4-FAVORITE-01", "V4", "POST", r"/api/articles/[^/]+/favorite",
         "0b3b538a92bb7d351204", "edit after favorite"),
        ("C-C02", "conduit", "L4-COMMENT-01", "V4", "POST", r"/api/articles/[^/]+/comments",
         "7f0c758889696e58b940", "edit after comment"),
        ("C-C03", "conduit", "L4-FOLLOW-01", "V4", "POST", r"/api/articles",
         "839a7b6499644ed42dad", "follow before publish; delete after original checks"),
        ("C-C04", "conduit", "L4-DELETE-01", "V7", "DELETE", r"/api/articles/[^/]+",
         "df397af9da9b9dc6192e", "favorite and comment before delete"),
        ("C-C05", "conduit", "L2-SETTINGS-01", "V7", "PUT", r"/api/user",
         "401134af22be1782015d", "publish and comment before profile update"),
        ("C-R01", "rwa", "L3-PAYMENT-01", "V4", "POST", r"/transactions",
         "21f255bf575e9e90dfc9", "recipient profile and sender search before payment"),
        ("C-R02", "rwa", "L4-THIRD-PARTY-LIKE-01", "V4", "POST", r"/likes/[^/]+",
         "9d5920a0e0310117904d", "manual payment/third-party interaction/clear; no generated interaction assertion"),
        ("C-R03", "rwa", "L3-PAYMENT-01", "V4", "POST", r"/transactions",
         "21f255bf575e9e90dfc9", "second payment before read; filter and pagination after original checks"),
        ("C-R04", "rwa", "L3-PAYMENT-01", "V4", "POST", r"/transactions",
         "21f255bf575e9e90dfc9", "independent bank account create/delete before payment"),
        ("C-R05", "rwa", "L3-REQUEST-ACCEPT-01", "V4", "PATCH", r"/transactions/[^/]+",
         "acbadbc6a811a15749b2", "interaction after one accept; clear before original status read"),
    ]
    fixed = [{"composition_id": cid, "subject": subject, "test_key": None,
              "astra_anchor_test_key": f"{subject}/{case}/relation-test-{tid}",
              "anchor": {"case_id": case, "protocol": protocol, "layer": "business_relation",
                         "producer_method": method, "producer_path_regex": path},
              "schedule": schedule,
              "generated_assertion_reused": cid != "C-R02",
              "input_status": "new composition input, not byte-for-byte frozen replay"}
             for cid, subject, case, protocol, method, path, tid, schedule in fixed_defs]
    # Defect-targeted compositions (author-approved 2026-09-12): the anchor is
    # selected from the evaluated suite by case, protocol and producer route
    # (lexicographically first retained test), never by outcome.
    targeted = [
        ("C-R06", "rwa", "L3-REQUEST-REJECT-01", "PATCH", r"/transactions/[^/]+",
         "balances and transaction status read before and after the recorded reject", "L1"),
        ("C-R07", "rwa", "L3-REQUEST-ACCEPT-01", "PATCH", r"/transactions/[^/]+",
         "second identical accept after the recorded accept; balances compared", "L2"),
        ("C-R08", "rwa", "L4-REQUEST-NOTIFY-01", "PATCH", r"/transactions/[^/]+",
         "the other actor PATCHes the owner's notification after the recorded request update", "L3"),
        ("C-R09", "rwa", "L3-REQUEST-ACCEPT-01", "PATCH", r"/transactions/[^/]+",
         "actor likes and comments its own new payment before the recorded accept; own notifications compared", "L4"),
        ("C-R10", "rwa", "L3-BANK-01", "POST", r"/graphql",
         "after the original checks the actor logs out and repeats ListBankAccount", "L8"),
        ("C-C06", "conduit", "L1-ARTICLE-07", "POST", r"/api/articles",
         "after the recorded creation the article and /api/tags are read; submitted tags compared", "L6"),
        ("C-C07", "conduit", "L1-ARTICLE-01", "POST", r"/api/articles",
         "the created article is read immediately five times without settling", "L7"),
    ]
    return fixed + [{"composition_id": cid, "subject": subject, "test_key": None,
                     "anchor": {"case_id": case, "protocol": "V4", "layer": "business_relation",
                                "producer_method": method, "producer_path_regex": path},
                     "schedule": schedule, "targets_lead": lead, "generated_assertion_reused": True,
                     "input_status": "new composition input, not byte-for-byte frozen replay"}
                    for cid, subject, case, method, path, schedule, lead in targeted]


def resolve_composition_anchor(definition: Mapping[str, Any], tests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Return the definition with a concrete test_key from the evaluated test map."""
    if definition.get("test_key"):
        return dict(definition)
    anchor = definition["anchor"]
    candidates = sorted(
        row["test_key"] for row in tests.values()
        if row["subject"] == definition["subject"] and row["case_id"] == anchor["case_id"]
        and row.get("protocol") == anchor["protocol"] and row.get("layer") == anchor["layer"]
        and isinstance(row.get("producer"), Mapping)
        and row["producer"]["method"] == anchor["producer_method"]
        and re.fullmatch(anchor["producer_path_regex"], row["producer"]["canonical_path"].rstrip("/") or "/")
    )
    resolved = dict(definition)
    resolved["test_key"] = candidates[0] if candidates else None
    resolved["anchor_resolution"] = {"matching_tests": len(candidates), "selection": "lexicographically_first_test_id"}
    return resolved


class CompositionControlComplete(Exception):
    """Intentional end of the independent extra-module control, not a test verdict."""


class CompositionUnavailable(Exception):
    pass


class FlowComposition:
    """Evaluation-only scheduling at the existing fresh HTTP boundary."""
    def __init__(self, core, recorder, definition, mode):
        self.core, self.recorder, self.definition, self.mode = core, recorder, definition, mode
        self.cid = definition["composition_id"]
        self.context = None
        self.endpoint = None
        self.started = False
        self.finished = False
        self.checks = []
        self.state = {}
        self.send_original = core._send
        self.transform_original = core._transform_response
        self.endpoint_original = core.execute_endpoint
        core.execute_endpoint = self.endpoint_call
        core._send = self.send
        core._transform_response = self.transform

    def restore(self):
        self.core.execute_endpoint = self.endpoint_original
        self.core._send = self.send_original
        self.core._transform_response = self.transform_original

    def check(self, name, condition):
        self.checks.append({"name": name, "source": "manual_exploratory", "verdict": "passed" if condition else "failed"})

    def call(self, actor, method, path, body=None, query=None, statuses=(200, 201, 204), graphql_errors="raise"):
        """Send one extra action; ``graphql_errors="return"`` hands a GraphQL error
        response back to the schedule (the composition's own check inspects it)
        instead of treating it as an unavailable precondition."""
        context = self.context
        if actor not in context.replay.sessions:
            raise CompositionUnavailable(f"required recorded actor unavailable: {actor}")
        headers = dict(context.replay.sessions[actor].headers)
        headers["Content-Type"] = "application/json"
        result = self.send_original(method, path, query or {}, headers, body)
        self.transform_original(context, {"phase": "composition", "actor_id": actor,
            "method": method, "path": path, "query": query or {}, "request_body": body,
            "composition_id": self.cid, "mode": self.mode}, result)
        if result.status not in statuses:
            raise CompositionUnavailable(f"extra action {method} {path.split('/')[1]} HTTP {result.status}")
        try:
            parsed = result.json()
        except (ValueError, TypeError):
            parsed = {}
        # REST endpoints may legitimately return an ``errors`` object for an
        # expected status (for example DELETE followed by GET -> 404).  Only
        # GraphQL responses use a top-level ``errors`` member as an execution
        # failure signal here.
        if path == "/graphql" and isinstance(parsed, dict) and parsed.get("errors") and graphql_errors != "return":
            raise CompositionUnavailable("extra GraphQL action returned errors")
        return parsed

    def endpoint_call(self, context, **kwargs):
        self.context, self.endpoint = context, kwargs
        try:
            return self.endpoint_original(context, **kwargs)
        finally:
            self.endpoint = None

    def is_producer(self, ref):
        return ref == self.context.material.candidate.get("producer", {}).get("request_ref")

    def send(self, method, path, query, headers, body, **kwargs):
        if self.endpoint and self.is_producer(self.endpoint["request_ref"]) and not self.started:
            if self.context.material.candidate.get("protocol_kind") not in (None, "V4", "V7"):
                raise CompositionUnavailable("composition requires existing single-workflow protocol")
            self.started = True
            self.state.update(actor=self.endpoint["actor_id"], path=path, request=copy.deepcopy(body))
            self.before()
        return self.send_original(method, path, query, headers, body, **kwargs)

    def transform(self, context, request, result):
        value = self.transform_original(context, request, result)
        if self.started and self.is_producer(request.get("request_ref")) and not self.finished:
            self.finished = True
            if isinstance(result, OSError) or not 200 <= result.status < 300:
                raise CompositionUnavailable("original producer did not succeed")
            try:
                self.state["response"] = result.json()
            except (ValueError, TypeError):
                self.state["response"] = {}
            self.after()
        return value

    def identities(self):
        endpoint = "/api/user" if self.definition["subject"] == "conduit" else "/checkAuth"
        return {actor: self.call(actor, "GET", endpoint)["user"] for actor in self.context.replay.sessions}

    def actor_for(self, users, field, value):
        matches = [actor for actor, user in users.items() if user.get(field) == value]
        if len(matches) != 1:
            raise CompositionUnavailable("shared resource has no unique recorded authenticated actor")
        return matches[0]

    def article_edit(self, path, reader):
        article = self.call(reader, "GET", path)["article"]
        author = self.actor_for(self.identities(), "username", article["author"]["username"])
        updated = self.call(author, "PUT", path, {"article": {"body": article["body"] + " RQ2 composition edit"}})["article"]
        self.check("independent article body edit persisted", self.call(reader, "GET", path)["article"]["body"] == updated["body"])
        self.state.update(article_path=path, edited_body=updated["body"])

    def before(self):
        cid, state = self.cid, self.state
        actor, path, body = state["actor"], state["path"], state["request"]
        if cid in {"C-C01", "C-C02"}:
            state["article_path"] = path.rsplit("/", 1)[0]
            if self.mode == "module_control":
                self.article_edit(state["article_path"], actor)
        elif cid == "C-C03":
            users = self.identities()
            other = next((a for a in users if a != actor), None)
            if other is None:
                raise CompositionUnavailable("follow requires second recorded actor")
            profile = "/api/profiles/" + users[actor]["username"]
            self.call(other, "POST", profile + "/follow")
            self.check("independent follow persisted", self.call(other, "GET", profile)["profile"]["following"] is True)
            state.update(other=other, profile=profile)
        elif cid == "C-C04":
            article_path = path.rstrip("/")
            users = self.identities()
            other = next((a for a in users if a != actor), None)
            if other is None:
                raise CompositionUnavailable("interaction requires second recorded actor")
            article = self.call(other, "GET", article_path)["article"]
            if not article.get("tagList"):
                self.call(actor, "PUT", article_path, {"article": {"tagList": ["rq2-composition"]}})
            state["tag"] = (article.get("tagList") or ["rq2-composition"])[0]
            self.call(other, "POST", article_path + "/favorite")
            comment = self.call(other, "POST", article_path + "/comments", {"comment": {"body": "RQ2 composition comment"}})["comment"]
            self.check("independent favorite present", self.call(other, "GET", article_path)["article"]["favorited"] is True)
            self.check("independent comment present", any(c["id"] == comment["id"] for c in self.call(other, "GET", article_path + "/comments")["comments"]))
            state.update(article_path=article_path, other=other)
        elif cid == "C-C05":
            users = self.identities()
            other = next((a for a in users if a != actor), None)
            if other is None:
                raise CompositionUnavailable("content composition requires second recorded actor")
            article = self.call(actor, "POST", "/api/articles", {"article": {"title": "RQ2 profile composition", "description": "composition", "body": "preserved article", "tagList": []}})["article"]
            article_path = "/api/articles/" + article["slug"]
            comment = self.call(other, "POST", article_path + "/comments", {"comment": {"body": "preserved comment"}})["comment"]
            state.update(article_path=article_path, other=other, comment_id=comment["id"])
            self.check("independent content present", self.call(other, "GET", article_path)["article"]["body"] == "preserved article")
        elif cid == "C-R01":
            users = self.identities()
            recipient = self.actor_for(users, "id", body["receiverId"])
            name = users[recipient]["firstName"] + "Compose"
            self.call(recipient, "PATCH", "/users/" + body["receiverId"], {"firstName": name})
            found = self.call(actor, "GET", "/users/search", query={"q": name})["results"]
            self.check("updated recipient searchable by new name", any(u["id"] == body["receiverId"] for u in found))
            state["users_before"] = self.identities()
        elif cid == "C-R04":
            created = self.call(actor, "POST", "/graphql", {"query": "mutation Create($bankName:String!,$accountNumber:String!,$routingNumber:String!){createBankAccount(bankName:$bankName,accountNumber:$accountNumber,routingNumber:$routingNumber){id userId isDeleted}}", "variables": {"bankName": "RQ2 Composition Bank", "accountNumber": "123456789", "routingNumber": "987654321"}})["data"]["createBankAccount"]
            self.call(actor, "POST", "/graphql", {"query": "mutation Delete($id:ID!){deleteBankAccount(id:$id)}", "variables": {"id": created["id"]}})
            accounts = self.call(actor, "POST", "/graphql", {"query": "query {listBankAccount{id userId isDeleted}}"})["data"]["listBankAccount"]
            self.check("new account soft deleted", any(a["id"] == created["id"] and a["isDeleted"] is True for a in accounts))
            state["users_before"] = self.identities()
            if state["users_before"][actor]["balance"] < float(body["amount"]) * 100:
                raise CompositionUnavailable("payment requires sufficient existing app balance")
        elif cid == "C-R03":
            state["users_before"] = self.identities()
            if self.mode == "module_control":
                state["second"] = self.call(actor, "POST", "/transactions", body)["transaction"]
                self.check("independent payment readable", self.call(actor, "GET", "/transactions/" + state["second"]["id"])["transaction"]["receiverId"] == body["receiverId"])
        elif cid == "C-R02":
            self.third_party_flow()
        elif cid in {"C-R06", "C-R07", "C-R08"}:
            tid = path.rsplit("/", 1)[1]
            state["tid"] = tid
            state["before"] = self.call(actor, "GET", "/transactions/" + tid)["transaction"]
            state["users_before"] = self.identities()
            if cid == "C-R08":
                other = next((a for a in state["users_before"] if a != actor), None)
                if other is None:
                    raise CompositionUnavailable("notification ownership check requires second recorded actor")
                state["other"] = other
                state["other_unread_before"] = [n["id"] for n in self.call(other, "GET", "/notifications")["results"]]
        elif cid == "C-R09":
            users = self.identities()
            other = next((a for a in users if a != actor), None)
            if other is None:
                raise CompositionUnavailable("self-notification check requires second recorded actor")
            own_before = {n["id"] for n in self.call(actor, "GET", "/notifications")["results"]}
            payment = self.call(actor, "POST", "/transactions", {"transactionType": "payment", "receiverId": users[other]["id"],
                                                                  "amount": 1, "description": "RQ2 self-notification composition"})["transaction"]
            self.call(actor, "POST", "/likes/" + payment["id"])
            self.call(actor, "POST", "/comments/" + payment["id"], {"content": "RQ2 own comment"})
            own_after = [n for n in self.call(actor, "GET", "/notifications")["results"] if n["id"] not in own_before]
            self.check("no notification to the actor for liking/commenting its own transaction",
                       not any(n.get("transactionId") == payment["id"] for n in own_after))
            state["users_before"] = self.identities()
        elif cid in {"C-R10", "C-C06", "C-C07"}:
            state["users_before"] = None
        if self.mode == "module_control" and cid != "C-R05":
            raise CompositionControlComplete()

    def after(self):
        cid, state = self.cid, self.state
        actor = state["actor"]
        if cid in {"C-C01", "C-C02"}:
            self.article_edit(state["article_path"], actor)
            if cid == "C-C02":
                state["comment_id"] = state["response"]["comment"]["id"]
        elif cid == "C-C03":
            state["article_path"] = "/api/articles/" + state["response"]["article"]["slug"]
            feed = self.call(state["other"], "GET", "/api/articles/feed")["articles"]
            self.check("followed author new article in feed", any(a["slug"] == state["response"]["article"]["slug"] for a in feed))
        elif cid == "C-R03":
            state["second"] = self.call(actor, "POST", "/transactions", state["request"])["transaction"]
        elif cid == "C-R06":
            after = self.call(actor, "GET", "/transactions/" + state["tid"])["transaction"]
            users_after = self.identities()
            self.check("reject changed the request status to rejected", after.get("requestStatus") == "rejected")
            self.check("reject did not mark the transaction complete", after.get("status") != "complete")
            self.check("reject moved no funds", {a: u["balance"] for a, u in users_after.items()}
                       == {a: u["balance"] for a, u in state["users_before"].items()})
        elif cid == "C-R07":
            first = {a: u["balance"] for a, u in self.identities().items()}
            self.call(actor, "PATCH", "/transactions/" + state["tid"], state["request"], statuses=(200, 204, 400, 403, 409, 422))
            second = {a: u["balance"] for a, u in self.identities().items()}
            self.check("second accept of the same request did not settle again", first == second)
        elif cid == "C-R08":
            other = state["other"]
            notes = [n for n in self.call(actor, "GET", "/notifications")["results"] if n.get("transactionId") == state["tid"]]
            if not notes:
                raise CompositionUnavailable("recorded request update produced no notification for the actor")
            target = notes[0]
            self.call(other, "PATCH", "/notifications/" + target["id"], {"isRead": True}, statuses=(200, 204, 400, 401, 403, 404))
            still_unread = any(n["id"] == target["id"] for n in self.call(actor, "GET", "/notifications")["results"])
            self.check("another user's PATCH did not change the owner's notification", still_unread)
        elif cid == "C-R05":
            tid = state["path"].rsplit("/", 1)[1]
            state["accepted_balances"] = {a: u["balance"] for a, u in self.identities().items()}
            self.interact_and_clear(actor, tid)
            self.check("accepted status preserved", self.call(actor, "GET", "/transactions/" + tid)["transaction"]["requestStatus"] == "accepted")
            self.check("interaction did not repeat settlement", {a: u["balance"] for a, u in self.identities().items()} == state["accepted_balances"])
            if self.mode == "module_control":
                raise CompositionControlComplete()

    def interact_and_clear(self, actor, tid):
        self.call(actor, "POST", "/likes/" + tid)
        self.call(actor, "POST", "/comments/" + tid, {"content": "RQ2 composition interaction"})
        before = self.call(actor, "GET", "/transactions/" + tid)["transaction"]
        for recipient in self.context.replay.sessions:
            notes = self.call(recipient, "GET", "/notifications")["results"]
            relevant = [n for n in notes if n.get("transactionId") == tid]
            for note in relevant:
                self.call(recipient, "PATCH", "/notifications/" + note["id"], {"isRead": True})
            unread = self.call(recipient, "GET", "/notifications")["results"]
            self.check("cleared own transaction notifications absent", not any(n["id"] in {x["id"] for x in relevant} for n in unread))
        after = self.call(actor, "GET", "/transactions/" + tid)["transaction"]
        self.check("clearing preserved likes and comments", before.get("likes") == after.get("likes") and before.get("comments") == after.get("comments"))

    def third_party_flow(self):
        users = self.identities()
        actor = self.state["actor"]
        other = next((a for a in users if a != actor), None)
        if other is None:
            raise CompositionUnavailable("no recorded third-party session")
        candidates = self.call(actor, "GET", "/users")["results"]
        receiver = next((u for u in candidates if u["id"] not in {x["id"] for x in users.values()}), None)
        if receiver is None:
            raise CompositionUnavailable("no distinct existing receiver for recorded third party")
        transaction = self.call(actor, "POST", "/transactions", {"transactionType": "payment", "receiverId": receiver["id"], "amount": 1, "description": "RQ2 third party composition", "privacyLevel": "public"})["transaction"]
        self.check("third party distinct from transaction participants", users[other]["id"] not in {transaction["senderId"], transaction["receiverId"]})
        self.check("independent payment readable by third party", self.call(other, "GET", "/transactions/" + transaction["id"])["transaction"]["receiverId"] == receiver["id"])
        if self.mode == "composed":
            self.interact_and_clear(other, transaction["id"])
        self.state["limitation"] = "receiver is an existing non-session user; receiver-side notification clearing unavailable, sender-side only"

    def finish(self):
        state, cid = self.state, self.cid
        if not self.finished:
            raise CompositionUnavailable("registered producer boundary was not reached")
        actor = state["actor"]
        if cid == "C-C01":
            self.check("edit preserved favorite", self.call(actor, "GET", state["article_path"])["article"]["favorited"] is True)
            self.call(actor, "DELETE", state["article_path"] + "/favorite")
        elif cid == "C-C02":
            for reader in self.context.replay.sessions:
                self.check("edit preserved comment for each actor", any(c["id"] == state["comment_id"] for c in self.call(reader, "GET", state["article_path"] + "/comments")["comments"]))
            self.call(actor, "DELETE", state["article_path"] + "/comments/" + str(state["comment_id"]))
            self.check("comment deletion preserved article edit", self.call(actor, "GET", state["article_path"])["article"]["body"] == state["edited_body"])
        elif cid == "C-C03":
            self.call(actor, "DELETE", state["article_path"])
            feed = self.call(state["other"], "GET", "/api/articles/feed")["articles"]
            self.check("deleted article absent from feed", not any(a["slug"] == state["response"]["article"]["slug"] for a in feed))
            self.check("delete preserved follow", self.call(state["other"], "GET", state["profile"])["profile"]["following"] is True)
            self.call(state["other"], "DELETE", state["profile"] + "/follow")
        elif cid == "C-C04":
            self.call(state["other"], "GET", state["article_path"], statuses=(404,))
            slug = state["article_path"].rsplit("/", 1)[1]
            for query in ({}, {"tag": state["tag"]}):
                self.check("deleted article absent from list query", not any(a["slug"] == slug for a in self.call(state["other"], "GET", "/api/articles", query=query)["articles"]))
        elif cid == "C-C05":
            self.check("profile update preserved article", self.call(state["other"], "GET", state["article_path"])["article"]["body"] == "preserved article")
            self.check("profile update preserved comment", any(c["id"] == state["comment_id"] for c in self.call(state["other"], "GET", state["article_path"] + "/comments")["comments"]))
        elif cid == "C-R10":
            self.call(actor, "POST", "/logout", statuses=(200, 204, 302))
            # the check below judges the GraphQL error itself (a resolver TypeError is
            # the defect), so error responses must reach it instead of aborting
            answer = self.call(actor, "POST", "/graphql", {"operationName": "ListBankAccount",
                               "query": "query ListBankAccount { listBankAccount { id userId bankName } }"},
                               statuses=(200, 401, 403), graphql_errors="return")
            errors = [str(e.get("message", "")) for e in (answer.get("errors") or [])] if isinstance(answer, dict) else []
            self.check("unauthenticated GraphQL query is refused without a server-side TypeError",
                       (not isinstance(answer, dict) or answer.get("data", {}).get("listBankAccount") in (None, []))
                       and not any("TypeError" in e for e in errors))
        elif cid == "C-C06":
            article = state["response"]["article"]
            submitted = list((state["request"].get("article") or {}).get("tagList") or [])
            stored = self.call(actor, "GET", "/api/articles/" + article["slug"])["article"].get("tagList") or []
            self.check("every submitted tag persisted on the article", set(submitted) <= set(stored))
            tags = self.call(actor, "GET", "/api/tags").get("tags") or []
            self.check("every submitted tag listed by /api/tags", set(submitted) <= set(tags))
        elif cid == "C-C07":
            slug = state["response"]["article"]["slug"]
            statuses = []
            for _ in range(5):
                result = self.send_original("GET", "/api/articles/" + slug, {}, dict(self.context.replay.sessions[actor].headers), None)
                statuses.append(result.status)
            self.check("immediate reads after creation never fail with 5xx", all(200 <= code < 500 for code in statuses))
            state["immediate_read_statuses"] = statuses
        elif cid in {"C-R01", "C-R03", "C-R04"}:
            transaction = state["response"]["transaction"]
            before, after = state["users_before"], self.identities()
            amount = transaction["amount"] * (2 if cid == "C-R03" else 1)
            self.check("payment debited sender exactly", after[actor]["balance"] == before[actor]["balance"] - amount)
            recipient = self.actor_for(after, "id", transaction["receiverId"])
            self.check("payment credited receiver exactly", after[recipient]["balance"] == before[recipient]["balance"] + amount)
            if cid == "C-R03":
                ids = {transaction["id"], state["second"]["id"]}
                for reader in (actor, recipient):
                    all_rows = self.call(reader, "GET", "/transactions", query={"page": 1, "limit": 100})["results"]
                    self.check("both new payments in Mine", ids <= {t["id"] for t in all_rows})
                    date = transaction["createdAt"][:10]
                    dates = self.call(reader, "GET", "/transactions", query={"dateRangeStart": date + "T00:00:00.000Z", "dateRangeEnd": date + "T23:59:59.999Z", "page": 1, "limit": 100})["results"]
                    self.check("date filter retains both new payments", ids <= {t["id"] for t in dates} and all(t["createdAt"][:10] == date for t in dates))
                    amounts = self.call(reader, "GET", "/transactions", query={"amountMin": max(1, transaction["amount"] - 1), "amountMax": transaction["amount"] + 1, "page": 1, "limit": 100})["results"]
                    self.check("amount filter retains both new payments", ids <= {t["id"] for t in amounts} and all(abs(t["amount"] - transaction["amount"]) <= 1 for t in amounts))
                    first = self.call(reader, "GET", "/transactions", query={"page": 1, "limit": 1})["results"]
                    second = self.call(reader, "GET", "/transactions", query={"page": 2, "limit": 1})["results"]
                    self.check("adjacent pages do not duplicate identities without intervening writes", not ({t["id"] for t in first} & {t["id"] for t in second}))
                    cleared = self.call(reader, "GET", "/transactions", query={"page": 1, "limit": 100})["results"]
                    self.check("clearing filter preserved both payments", ids <= {t["id"] for t in cleared})


def run_compositions(subject, *, fault_id=None, retry_errors=False):
    require_live()
    configure_subject(subject, "normal")
    tests = {r["test_key"]: r for r in lines(LEGACY / "test-map.jsonl")}
    normal = normal_records()
    output = ROOT / "compositions.jsonl"
    done = {r["composition_id"]: r for r in lines(output)}
    for definition in composition_catalog():
        cid = definition["composition_id"]
        if definition["subject"] != subject or (fault_id and cid != fault_id):
            continue
        definition = resolve_composition_anchor(definition, tests)
        if definition["test_key"] is None:
            record = {**definition, "attempt": 0, "runs": [], "engineering_error": False,
                      "status": "anchor_unavailable", "manual_alarm": False,
                      "independent_control_passed": False, "confirmed_application_bug": False}
            append(output, record)
            print(json.dumps({"composition": cid, "status": "anchor_unavailable"}), flush=True)
            continue
        retryable = retry_errors and (
            done[cid].get("engineering_error")
            or done[cid].get("status") == "incomplete_or_unavailable"
        ) if cid in done else False
        if cid in done and not retryable:
            continue
        row = tests[definition["test_key"]]
        if not normal[row["test_key"]].get("qualified"):
            raise ValueError("composition anchor lacks original normal qualification")
        path = ROOT / "runs" / subject / "composition" / cid
        attempt = 1
        while (path / f"attempt-{attempt:03}").exists():
            attempt += 1
        path = path / f"attempt-{attempt:03}"
        runtime = FrozenSuitePytestRuntime(Path(row["source_run"]), path / "runtime")
        active = None
        runtime.open(response_transform=lambda meta, result: active(meta, result))
        modes = []
        try:
            for mode in ("module_control", "composed"):
                active = ResponseRecorder(path / mode / "http.jsonl")
                hook = FlowComposition(runtime._factory.core, active, definition, mode)
                result = error = None
                intentional_stop = False
                started = time.monotonic()
                try:
                    result = runtime.run_retained_test(row["test_id"], execution_id=f"{cid}-{mode}-{attempt}")
                    if mode == "composed":
                        hook.finish()
                except CompositionControlComplete:
                    intentional_stop = True
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                finally:
                    hook.restore()
                record = {"mode": mode, "elapsed_seconds": time.monotonic() - started, "error": error,
                    "independent_module_control_complete": intentional_stop,
                    "manual_checks": hook.checks, "limitation": hook.state.get("limitation"),
                    "generated_result": result if mode == "composed" and definition["generated_assertion_reused"] else None,
                    "generated_alarm": bool(mode == "composed" and definition["generated_assertion_reused"] and result and
                        any(a.get("verdict") == "failed" and a.get("assertion_class") != "generic" for run in result.get("runs", []) for a in run.get("assertion_results", []))),
                    "evidence_ref": str((path / mode).relative_to(ROOT))}
                save(path / mode / "result.json", record)
                modes.append(record)
                if error or (mode == "module_control" and not intentional_stop):
                    break
        finally:
            runtime.close()
        record = {**definition, "attempt": attempt, "normal_anchor_reference": normal[row["test_key"]].get("evidence_ref"),
                  "runs": modes, "engineering_error": any(r["error"] and not r["error"].startswith("CompositionUnavailable:") for r in modes),
                  "status": "incomplete_or_unavailable" if len(modes) != 2 or any(r["error"] for r in modes) else "completed",
                  "manual_alarm": any(c["verdict"] == "failed" for r in modes for c in r["manual_checks"]),
                  "independent_control_passed": bool(modes and modes[0]["independent_module_control_complete"] and
                      not modes[0]["error"] and all(c["verdict"] == "passed" for c in modes[0]["manual_checks"])),
                  "confirmed_application_bug": False}
        if record["status"] == "completed" and not record["independent_control_passed"]:
            record["status"] = "independent_control_alarm_requires_diagnosis"
        append(output, record)
        print(json.dumps({"composition": cid, "status": record["status"], "manual_alarm": record["manual_alarm"],
                          "errors": [r["error"] for r in modes]}), flush=True)


def latest_outcomes(records):
    return list({(r["fault_id"], r["test_key"]): r for r in records}.values())


def business_state(row):
    if "B" in row:
        return row["B"]
    if row.get("layer") != "business_relation":
        return "no_business_tests"
    primary = [a for a in row.get("assertion_results", []) if a.get("assertion_class") != "generic"]
    if any(a.get("verdict") == "failed" for a in primary):
        return "detected"
    if primary and row.get("mechanical_complete") and all(a.get("verdict") == "passed" for a in primary):
        return "completed_not_detected"
    return "unknown"


def fault_summary(definition, records, planned):
    actual = [r for r in records if r["fault_id"] == definition["fault_id"]]
    missing = max(0, planned - len(actual))
    projection = actual + [{"O0": "unknown", "O1": "unknown", "O2": "unknown"}] * missing
    result = {**definition, "planned_tests": planned, "completed_tests": len(actual), "missing_tests": missing,
              **{key: reduce_fault(projection, key) for key in ("O0", "O1", "O2")},
              "business_direct_alarm": any(r.get("business_direct_alarm") for r in actual),
              "changed_responses": sum(r.get("changed_response_count", 0) for r in actual),
              "activated_tests": sum(r.get("changed_response_count", 0) > 0 for r in actual),
              "elapsed_seconds": sum(r.get("elapsed_seconds", 0) for r in actual)}
    result["business_only"] = result["O1"] == "completed_not_detected" and result["business_direct_alarm"]
    baseline = result["O1"]
    bstates = [business_state(r) for r in actual if business_state(r) != "no_business_tests"]
    result["B"] = ("detected" if "detected" in bstates else "unknown" if missing or "unknown" in bstates
                   else "completed_not_detected" if bstates else "no_business_tests")
    result["B_vs_O1"] = ("unknown" if baseline not in {"detected", "completed_not_detected"} or result["B"] == "unknown"
                        else "no_business_tests" if result["B"] == "no_business_tests"
                        else "both" if baseline == "detected" and result["B"] == "detected"
                        else "baseline-only" if baseline == "detected"
                        else "business-only" if result["B"] == "detected" else "neither")
    if definition.get("kind") == "response":
        result["substates"] = {
            name: {"activated_responses": sum(r.get("activation_substates", {}).get(name, 0) for r in actual),
                   "status": "activated" if any(r.get("activation_substates", {}).get(name, 0) for r in actual)
                   else "pending" if missing else "no_eligible_tests" if not planned else "not_activated"}
            for name in definition["substates"]}
    conditional = [r for r in actual if r.get("common_observation") and
                   (definition.get("kind") != "response" or r.get("changed_response_count", 0))]
    result["conditional"] = {key: reduce_fault(conditional, key) for key in ("O0", "O1", "O2")}
    result["conditional"]["tests"] = len(conditional)
    return result


def summarize() -> None:
    catalog = lines(ROOT / "response-faults.jsonl")
    records = latest_outcomes([r for subject in ("conduit", "rwa") for r in lines(ROOT / f"outcomes-response-{subject}.jsonl")])
    response = [fault_summary(d, records, d["paired_tests"]) for d in catalog]
    # Report four notification trigger opportunities independently. These are
    # descriptive normal-plan facts, never a post-outcome selection filter.
    r14 = next(d for d in response if d["fault_id"] == "PR-R14")
    opportunity = {s: set() for s in ("payment", "request", "like", "comment", "uncertain_transaction_type")}
    for pair in lines(ROOT / "test-fault-map.jsonl"):
        if pair["fault_id"] != "PR-R14":
            continue
        events = lines(normal_evidence_dir(pair["normal_evidence_ref"], pair.get("normal_evidence_root")) / "http.jsonl")
        for event in events:
            if event.get("method") != "POST":
                continue
            path = route(event).rstrip("/")
            substate = ("like" if re.fullmatch(r"/likes/[^/]+", path) else
                        "comment" if re.fullmatch(r"/comments/[^/]+", path) else None)
            if path == "/transactions":
                value = (event.get("request_body") or {}).get("transactionType")
                substate = value if value in {"payment", "request"} else "uncertain_transaction_type"
            if substate:
                opportunity[substate].add(pair["test_key"])
    r14["normal_trigger_opportunity_tests"] = {key: len(value) for key, value in opportunity.items()}
    if RWA_SOURCE_REUSE:
        rwa_source_records = [r for r in lines(LEGACY / "outcomes-rwa.jsonl") if r["fault_id"].startswith(("B-", "H-"))]
    else:
        rwa_source_records = lines(ROOT / "outcomes-source-rwa.jsonl")
    source_records = latest_outcomes(rwa_source_records + lines(ROOT / "outcomes-source-conduit.jsonl"))
    normal = normal_records()
    mapped = lines(LEGACY / "test-map.jsonl")
    source = []
    for version in lines(LEGACY / "source-versions.jsonl"):
        if version["status"] != "included" or version["fault_id"] == "normal":
            continue
        planned = sum(version["fault_id"] in row["fault_ids"] and normal[row["test_key"]].get("qualified", False) for row in mapped)
        source.append(fault_summary({"fault_id": version["fault_id"], "subject": version["subject"], "kind": "source",
                                     "candidate_tier": version.get("candidate_tier", "main"),
                                     "reused": version["subject"] == "rwa" and RWA_SOURCE_REUSE}, source_records, planned))
    source_caveat = {"fault_id": "B-R14", "raw_verdict_preserved": True,
        "status": "basic_assertion_applicability_unresolved",
        "reason": "page<=totalPages alarms on page=1,totalPages=0, also allowed by the fixed normal empty-list pagination implementation",
        "review_reference": "docs/design/cpv-expansion/rq2-suite-data-20260908.md"}
    compositions = list({r["composition_id"]: r for r in lines(ROOT / "compositions.jsonl")}.values())
    summary = {"response": response, "source": source, "compositions": compositions,
               "source_alarm_caveats": [source_caveat],
               "updated_at": dt.datetime.now(dt.UTC).isoformat()}
    save(ROOT / "summary.json", summary)
    table = ["# RQ2 suite-level results", "",
             "Response faults, source faults and flow compositions are counted separately; the legacy single-position response faults are not in the tables below.", "",
             "|Kind|Subject|Faults|O0 detected|O1 detected|O2 detected|Business-only|O2 undetected|O2 unknown|No test|",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for kind, rows in (("response", response), ("source", source)):
        for subject in ("conduit", "rwa"):
            selected = [r for r in rows if r["subject"] == subject]
            values = [len(selected)] + [sum(r[k] == "detected" for r in selected) for k in ("O0", "O1", "O2")]
            values += [sum(r["business_only"] for r in selected)] + [
                sum(r["O2"] == state for r in selected) for state in ("completed_not_detected", "unknown", "no_eligible_tests")]
            table.append("|" + "|".join([kind, subject] + [str(v) for v in values]) + "|")
    table += ["", "Per-fault details and conditional denominators are in summary.json. Incomplete pairs stay unknown; non-activated faults and faults without tests remain in the catalogue denominator.",
              "O0 is the generic checks plus application 5xx; schema_type is the local type check. This is the revised experiment after the earlier diagnosis, not an independent validation set.",
              ("RWA source faults reuse the earlier complete execution by reference; Conduit source faults were executed anew in this round." if RWA_SOURCE_REUSE
               else "RWA and Conduit source faults were both executed anew under this root."),
              "The 9 machine alarms of the RWA source faults keep their original records: the 8 business alarms are supported by representative evidence; the single structural alarm of B-R14 is of uncertain applicability to a legitimately empty list and is not counted as a trustworthy structural detection.", "",
              "## Per-fault results", "",
              "|Kind|Subject|Fault|Completed/planned tests|Changed responses|O0|O1|O2|B vs O1|", "|---|---|---|---:|---:|---|---|---|---|"]
    for kind, rows in (("response", response), ("source", source)):
        for row in rows:
            table.append("|" + "|".join(str(v) for v in (kind, row["subject"], row["fault_id"],
                f'{row["completed_tests"]}/{row["planned_tests"]}', row["changed_responses"] if kind == "response" else "—",
                row["O0"], row["O1"], row["O2"], row["B_vs_O1"])) + "|")
    table += ["", "## Activation and conditional results", "",
              "PR-R14 reports trigger opportunities and actual activations per branch (payment/request/like/comment); no single branch represents the whole.", "",
              "|Trigger|Qualifying tests with evidence in the normal plan|Actually changed responses|Status|", "|---|---:|---:|---|"]
    for substate, facts in r14["substates"].items():
        table.append(f'|{substate}|{r14["normal_trigger_opportunity_tests"][substate]}|{facts["activated_responses"]}|{facts["status"]}|')
    table += ["", "The conditional denominator includes only tests with an actual activation whose original checks are jointly evaluable, reduced independently per fault; the full detection numerator is not reused.", "",
              "|Subject|Response faults with conditional records|Conditional O0 detected|Conditional O1 detected|Conditional O2 detected|", "|---|---:|---:|---:|---:|"]
    for subject in ("conduit", "rwa"):
        eligible = [r for r in response if r["subject"] == subject and r["conditional"]["tests"]]
        table.append("|" + "|".join([subject, str(len(eligible))] + [str(sum(r["conditional"][k] == "detected" for r in eligible)) for k in ("O0", "O1", "O2")]) + "|")
    table += ["", "## Flow compositions", "", "17 planned (10 reusing original flows and 7 targeting reproduced defects); the composed inputs are new schedules, not byte-for-byte frozen replays, and every added check is listed separately as a manual exploration.", "",
              "|Composition|Status|Reuses generated assertion|Manual-check alarm|Targets lead|Anchor|", "|---|---|---|---|---|---|"]
    by_id = {r["composition_id"]: r for r in compositions}
    for definition in composition_catalog():
        row = by_id.get(definition["composition_id"], {})
        table.append(f'|{definition["composition_id"]}|{row.get("status", "pending")}|{definition["generated_assertion_reused"]}|{row.get("manual_alarm", "pending")}|{definition.get("targets_lead", "-")}|{(row.get("test_key") or definition.get("test_key") or "-").split("/")[-1][:24]}|')
    table += ["", "A manual-check alarm is not a confirmed application defect: broken preconditions and composer wiring must be excluded, and the defect reproduced independently and located in the source.", ""]
    if any(r["composition_id"] == "C-R02" for r in compositions):
        table += ["The independent control of C-R02 only verifies that the payment is readable and does not isolate the third-party interaction; the third, pre-existing receiving user has no recorded session, so receiver-side notification clearing is not covered. This item is a partially covering manual exploration and does not count towards generated-assertion capability; an alarm would still require an isolated reproduction of the interaction.", ""]
    (ROOT / "report.md").write_text("\n".join(table))
    print(json.dumps({"response_faults": len(response), "source_faults": len(source),
                      "response_completed_pairs": len(records), "source_completed_pairs": len(source_records)}), flush=True)


def source_fault_routes(registry: Path) -> dict[str, tuple[str, list[list[str]]]]:
    """fault_id -> (subject, [[method, path_regex], ...]) from the registered source faults."""
    routes = {}
    for row in lines(registry):
        if row.get("kind") == "source" and row.get("routes"):
            routes[row["fault_id"]] = (row["subject"], row["routes"])
    for fid, fault_routes in CONDITIONAL_SOURCE_ROUTES.items():
        routes[fid] = ("conduit", fault_routes)
    return routes


def route_matches(fault_routes: list[list[str]], coverage: list[Mapping[str, Any]]) -> bool:
    return any(request["method"] == method and re.fullmatch(pattern, request["canonical_path"].rstrip("/") or "/")
               for method, pattern in fault_routes for request in coverage)


REQUEST_REF = re.compile(r"^[A-Za-z0-9._-]+:request:[0-9]+$")


def blueprint_request_refs(value: Any) -> set[str]:
    """Every frozen request ref in a retained test's blueprint (setup, producer, observers, plans).

    Only whole-string refs count; free-text rationales that mention a ref are not coverage.
    """
    if isinstance(value, str):
        return {value} if REQUEST_REF.match(value) else set()
    if isinstance(value, dict):
        return set().union(*(blueprint_request_refs(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(blueprint_request_refs(v) for v in value)) if value else set()
    return set()


def build_test_map(*, subject: str, run_roots: list[Path], export_roots: list[Path], fault_registry: Path) -> None:
    """Register every retained test of the frozen M14 suites as an evaluation unit.

    Request coverage is the frozen trace row of each blueprint request ref;
    source faults pair by route regex over that coverage; the layer label is
    the pytest export catalog's assertion_layer.  No outcome is consulted.
    """
    target = LEGACY / "test-map.jsonl"
    if any(row["subject"] == subject for row in lines(target)):
        raise ValueError("test map already holds this subject")
    routes = {fid: fault_routes for fid, (fault_subject, fault_routes) in source_fault_routes(fault_registry).items()
              if fault_subject == subject}
    layers = {}
    for export_root in export_roots:
        for catalog in sorted(Path(export_root).glob("*/business_test_catalog.json")):
            for test in read(catalog)["tests"]:
                layers[(catalog.parent.name, test["test_id"])] = test["assertion_layer"]
    rows = []
    taken: dict[str, str] = {}  # case -> run root that supplied it (first root in the given order wins)
    for run_root in run_roots:
        for case_dir in sorted((Path(run_root) / "cases").iterdir()):
            union = case_dir / "union"
            final_path = union / "M14/final_calibrated_suite.json"
            if case_dir.name.startswith(".") or not final_path.is_file():
                continue
            if case_dir.name in taken:
                # an earlier run root (higher precedence, e.g. a repaired continuation)
                # already supplied this case; later roots are superseded for it
                continue
            taken[case_dir.name] = str(run_root)
            final = read(final_path)
            if not final["retained_tests"]:
                continue
            requests = {r["request_ref"]: r for r in read(union / "M01_09/ui_api_trace.json")["trace"]["api_requests"]}
            for test in final["retained_tests"]:
                refs = blueprint_request_refs(test["blueprint"])
                coverage = sorted((requests[ref] for ref in refs), key=lambda r: r["global_order"])
                test_key = f"{subject}/{case_dir.name}/{test['test_id']}"
                producer_ref = ((test["blueprint"].get("producer") or {}).get("request_ref"))
                producer = requests.get(producer_ref) if producer_ref else None
                rows.append({
                    "test_key": test_key, "subject": subject, "case_id": case_dir.name, "test_id": test["test_id"],
                    "candidate_id": test["candidate_id"], "source_run": str(union.resolve()),
                    "protocol": test["protocol_kind"], "layer": layers[(case_dir.name, test["test_id"])],
                    "producer": ({"actor_id": producer["actor_id"], "method": producer["method"],
                                  "canonical_path": producer["canonical_path"]} if producer else None),
                    "review_label": None, "review_label_status": "RQ1 review pending; joined at reporting time",
                    "fault_ids": sorted(fid for fid, fault_routes in routes.items() if route_matches(fault_routes, coverage)),
                    "request_coverage": coverage, "dedup_execution_key": test_key,
                    "fault_registry_ref": str(fault_registry),
                })
    if not rows:
        raise ValueError("no retained tests found under the run roots")
    for row in rows:
        append(target, row)
    print(json.dumps({"subject": subject, "tests": len(rows), "cases": len({r["case_id"] for r in rows}),
                      "cases_by_run_root": {str(root): sum(1 for c, r in taken.items() if r == str(root)) for root in run_roots},
                      "layers": {layer: sum(r["layer"] == layer for r in rows) for layer in ("basic_constraint", "business_relation")},
                      "source_pairs": {fid: sum(fid in r["fault_ids"] for r in rows) for fid in sorted(routes)}}), flush=True)


def run_normal(subject: str, *, limit: int | None = None, retry_errors: bool = False) -> None:
    """Execute every registered test once on the isolated normal version and derive its qualification."""
    mapped = [r for r in lines(LEGACY / "test-map.jsonl") if r["subject"] == subject]
    if not mapped:
        raise ValueError("test map has no tests for this subject")
    pairs = [{"fault_id": "normal", "test_key": r["test_key"], "subject": subject} for r in mapped]
    execute_pairs(subject, pairs, kind="normal", retry_errors=retry_errors, limit=limit)
    records = latest_outcomes(lines(ROOT / f"outcomes-normal-{subject}.jsonl"))
    rows = []
    for record in records:
        saved = read(ROOT / record["evidence_ref"] / "result.json")
        status = (saved.get("result") or {}).get("final_status")
        row = dict(record)
        row.update(qualified=record.get("error") is None and bool(record.get("mechanical_complete")) and status == "normal_pass",
                   normal_final_status=status, evidence_root=str(ROOT),
                   qualification_basis="last attempt: error-free, mechanically complete, final_status normal_pass on the isolated normal version")
        rows.append(row)
    target = LEGACY / f"normal-{subject}.jsonl"
    temporary = target.with_suffix(".jsonl.tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    os.replace(temporary, target)
    print(json.dumps({"subject": subject, "tests": len(mapped), "executed": len(rows),
                      "qualified": sum(r["qualified"] for r in rows),
                      "not_qualified": [r["test_key"] for r in rows if not r["qualified"]]}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["test-map", "normal", "register", "prepare", "responses", "sources",
                                            "compositions", "summarize"])
    parser.add_argument("--subject", choices=["conduit", "rwa"])
    parser.add_argument("--fault")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--run-root", action="append", default=[], help="frozen suite run root (test-map)")
    parser.add_argument("--export-root", action="append", default=[], help="pytest export root with per-case catalogs (test-map)")
    parser.add_argument("--fault-registry", help="registered source faults with routes (test-map)")
    args = parser.parse_args()
    if args.command in {"normal", "responses", "sources", "compositions"}:
        print(json.dumps({"runner_pid": os.getpid(), "command": args.command, "subject": args.subject,
                          "started_at": dt.datetime.now(dt.UTC).isoformat()}), flush=True)
    if args.command == "test-map":
        if not (args.subject and args.run_root and args.export_root and args.fault_registry):
            parser.error("test-map needs --subject, --run-root, --export-root and --fault-registry")
        build_test_map(subject=args.subject, run_roots=[Path(p) for p in args.run_root],
                       export_roots=[Path(p) for p in args.export_root], fault_registry=Path(args.fault_registry))
    elif args.command == "normal":
        run_normal(args.subject, limit=args.limit, retry_errors=args.retry_errors)
    elif args.command == "register":
        register()
    elif args.command == "prepare":
        prepare_isolation()
    elif args.command == "summarize":
        summarize()
    elif args.command == "responses":
        run_responses(args.subject, fault_id=args.fault, limit=args.limit, retry_errors=args.retry_errors)
    elif args.command == "compositions":
        run_compositions(args.subject, fault_id=args.fault, retry_errors=args.retry_errors)
    else:
        run_sources(args.subject, fault_id=args.fault, limit=args.limit, retry_errors=args.retry_errors)


if __name__ == "__main__":
    main()
