#!/usr/bin/env python3
"""Generate docs/FAULT-CATALOGUE.md for the reproduction package (English) from the RQ2 data files.

Business rules, source-fault designs and composition descriptions are the authors' translations of the
pre-registered design notes; response-fault instances come from suite/response-faults.jsonl.
Usage: make_fault_catalogue.py <repo root> <output md>
"""
import json, sys
from pathlib import Path
REPO = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2])
RQ2 = REPO / "eval/ui_semantics/rq2-deepseek-final2-20260912/suite"
RQ2S = REPO / "eval/ui_semantics/rq2-subjects-20260921"
SUBJECT_LABEL = {"umami": "Umami 3.4.0", "paperless": "Paperless-ngx 3.2.0", "ghost": "Ghost 5.130.6"}
# The recorded input sequences whose write (or, for the read/query faults, whose read) activates the fault;
# from the pre-registered design notes, checked against the recorded HAR entries before any run.
TRIGGERS = {
 "PR-U01": "L1-WEBSITE-01, L3-TEAM-04",
 "PR-U02": "L1-WEBSITE-03, L1-WEBSITE-04",
 "PR-U03": "L1-SHARE-01, L2-SHARE-02",
 "PR-U04": "L1-USER-04, L3-USER-05, L2-USER-02",
 "B-P01": "L2-DOCEDIT-01 (L2-DOCEDIT-03 patches the same route without a title and pairs without activating)",
 "B-P02": "L2-DOCEDIT-02",
 "B-P03": "L1-DOCLIST-06",
 "PR-P01": "L2-DOCEDIT-01 (L2-DOCEDIT-03 does not change the title)",
 "PR-P02": "L3-SHARING-01, L3-SHARING-02",
 "PR-P03": "L3-SHARING-01, L3-SHARING-02",
 "B-G01": "L1-POST-04, L1-POST-05",
 "B-G02": "L2-MEMBER-03",
 "B-G03": "L1-SETTING-01, L1-SETTING-02",
 "PR-G01": "L1-POST-01, L1-POST-04, L1-POST-05, L2-POST-03, L2-POST-10, L2-AUTHOR-03, L2-PERM-02",
 "PR-G02": "L1-POST-01, L1-POST-04, L1-POST-05, L2-POST-03, L2-POST-10, L2-AUTHOR-03, L2-PERM-02, L1-PAGE-01",
 "PR-G03": "L2-MEMBER-03",
 "B-G04": "the dashboard read `GET posts/?…&fields=…` (recorded 44x in 19 sequences)",
 "B-G05": "`GET search-index/posts/` (recorded 22x in 19 sequences)",
 "PR-G04": "every `GET posts/` read that carries `fields` (the dashboard read, recorded 44x in 19 sequences)",
 "PR-G05": "every `GET newsletters/` read that carries `include` (recorded 50x)",
 "PR-G06": "every `GET posts/` read that carries `order` (the dashboard and post-list reads, recorded 65x)",
}
GHOST_EXTENSION = {"B-G04", "B-G05", "PR-G04", "PR-G05", "PR-G06"}

RULES = {
 "C01": "Registration persists the identity; a duplicate e-mail must not overwrite an existing account.",
 "C02": "Correct credentials return the corresponding user; wrong credentials must not establish a session.",
 "C03": "Guests can read public articles; logout, hidden buttons and client-side route guards are not server-side rejection of unauthorised requests.",
 "C04": "Created content, its author and its valid tags can be read back.",
 "C05": "A duplicate title (slug conflict) is rejected; the original article is not overwritten.",
 "C06": "Edits persist; after a title change the new slug and reads by another user resolve to the same article.",
 "C07": "After a confirmed deletion the article can no longer be read (cancelling the dialog is a UI-only branch).",
 "C08": "Non-existent articles or profiles yield not-found results.",
 "C09": "A comment stores its content, author and article and is visible to legitimate readers.",
 "C10": "Deleting a comment as its author removes that comment; a missing delete button for others does not prove server-side authorisation.",
 "C11": "Favoriting creates the association for the acting user; status, count and the user's favourites list agree.",
 "C12": "Unfavoriting removes that user's association without deleting the article or other users' associations.",
 "C13": "Follow/unfollow affects the designated relationship without confusing actor and target.",
 "C14": "Tag, author and favorited filters each satisfy their own scope (three distinct rules).",
 "C15": "Pagination: offset = page x limit; the response is the corresponding slice with a matching count.",
 "C16": "\"Your Feed\" contains articles of followed authors; after unfollowing, new reads no longer include that author's articles through that relationship.",
 "C17": "After deleting an article, tag queries no longer contain it (global tags may persist in this version).",
 "C18": "After updating the public profile, the user and another user read the new values.",
 "C19": "Login and identity migration after credential changes.",
 "C20": "Browser-only properties (required fields, blank comments, HTML validation, logout navigation): UI-only, not in the API fault denominator.",
 "R01": "Credentials and session identity are correct; server-side logout invalidates the session.",
 "R02": "A new user registers and creates a first bank account; quitting onboarding creates no later business state.",
 "R03": "Bank-account name, routing number and account number persist; the owner comes from the login context.",
 "R04": "Bank-account queries are isolated per logged-in user.",
 "R05": "Soft delete: isDeleted becomes true; the record is still listed, shown as Deleted, without a Delete button.",
 "R06": "Name, e-mail and phone updates persist, and another user's search reads the new fields.",
 "R07": "Search matches fixed fields and excludes the current user (fuzzy match, not exact equality).",
 "R08": "A transaction stores the amount (dollars to cents), the description and both identities; both parties read the same transaction.",
 "R09": "With sufficient balance the payer is debited by the transaction amount.",
 "R10": "The payee is credited by the transaction amount.",
 "R11": "With insufficient balance the internal top-up branch runs and the visible app balance becomes zero, not negative.",
 "R12": "A request is created as pending and is not an immediate payment debit.",
 "R13": "Accepting a request stores accepted; the direction of funds differs from a plain payment.",
 "R14": "The status of a rejected request can be read back (its fund side effect is a specification doubt).",
 "R15": "Mine = participant, Friends = contacts, Everyone = the fixed version's merge logic; the entries do not share one scope.",
 "R16": "Date and amount filters, their combination and their clearing.",
 "R17": "Pagination slices by page and limit.",
 "R18": "A like stores its transaction and user and legitimate reads contain it (UI double-click prevention does not prove backend idempotence).",
 "R19": "Comment content, author and transaction are consistent; several comments read back independently.",
 "R20": "Payment and request notifications reference the same transaction with the right recipient and type.",
 "R21": "Third-party comments and likes propagate to the transaction's participants; notifications reference the same transaction and interaction.",
 "R22": "The unread list contains only the current user's unread items; clearing does not delete transactions, comments or likes.",
 "R23": "Browser form validation, drawers and routes: UI-only.",
}
SOURCE = [  # id, subject, rules, location, change
 ("B-C01","conduit","C04","controllers/articles.js: createArticle","appends a fixed non-empty string to the persisted body; title, slug and author unchanged"),
 ("B-C02","conduit","C04, C14","createArticle, tagList loop","omits the article.addTagList association for new tags (the tags are still created)"),
 ("B-C03","conduit","C06","controllers/articles.js: updateArticle","omits the body update assignment; other fields save normally"),
 ("B-C04","conduit","C07, C17","controllers/articles.js: deleteArticle","omits article.destroy while keeping the response path"),
 ("B-C05","conduit","C09","controllers/comments.js: createComment","deterministically rewrites comment.body on storage; author and article unchanged"),
 ("B-C06","conduit","C10","controllers/comments.js: deleteComment","omits comment.destroy"),
 ("B-C07","conduit","C11","controllers/favorites.js: favoriteToggler (POST branch)","omits article.addUser"),
 ("B-C08","conduit","C12","favoriteToggler (DELETE branch)","omits article.removeUser"),
 ("B-C09","conduit","C13","controllers/profiles.js: followToggler (POST branch)","omits profile.addFollower"),
 ("B-C10","conduit","C13","followToggler (DELETE branch)","omits profile.removeFollower"),
 ("B-C11","conduit","C14","controllers/articles.js: allArticles, tag include","drops the existing tag.name filter"),
 ("B-C12","conduit","C14","allArticles, author include","drops the existing author.username filter"),
 ("B-C13","conduit","C14","allArticles, favorited branch","returns the plain article list instead of the target user's favourites (same response container)"),
 ("B-C14","conduit","C16","controllers/articles.js: articlesFeed","drops the author scope derived from the following relation"),
 ("B-C15","conduit","C15","controllers/articles.js: allArticles","offset fixed to 0; limit and ordering unchanged"),
 ("B-C16","conduit","C18","controllers/user.js: updateUser field loop","skips writing the bio field only"),
 ("H-C01","conduit","C01","users.signUp duplicate-e-mail guard","removes the duplicate check (database uniqueness verified separately)"),
 ("H-C03","conduit","C05","articles.createArticle duplicate-slug guard","removes the duplicate-title protection"),
 ("B-R01","rwa","R03","database.createBankAccountForUser","fixed non-empty rewrite of bankName on storage"),
 ("B-R02","rwa","R04","graphql/resolvers/Query.ts: listBankAccount","drops the ctx.user.id scope and returns all accounts"),
 ("B-R03","rwa","R05","database.removeBankAccountById","omits persisting isDeleted = true (no hard delete)"),
 ("B-R04","rwa","R06","database.updateUserById","skips the firstName update only"),
 ("B-R05","rwa","R07","user-routes.ts: /search","omits removeUserFromResults; the fuzzy search itself is kept"),
 ("B-R06","rwa","R08","database.createTransaction, amount","drops the x100 dollars-to-cents conversion"),
 ("B-R07","rwa","R08","database.createTransaction, description","fixed rewrite of the description; transaction id unchanged"),
 ("B-R08","rwa","R09","createTransaction, payment branch","omits debitPayAppBalance(sender, transaction)"),
 ("B-R09","rwa","R10","createTransaction, payment branch","omits creditPayAppBalance(receiver, transaction)"),
 ("B-R10","rwa","R11","database.resetPayAppBalance","the insufficient-balance branch keeps 1 cent instead of zeroing; the bank top-up call is unchanged"),
 ("B-R11","rwa","R12","createTransaction, requestStatus","a new request is created as accepted instead of pending"),
 ("B-R12","rwa","R13","database.updateTransactionById, final assign","discards the submitted requestStatus update (old status kept); funds logic untouched"),
 ("B-R13","rwa","R15","database.getAllTransactionsForUserByObj","drops the receiverId participant branch (Mine misses transactions where the user is the payee)"),
 ("B-R14","rwa","R15","database.getTransactionsForUserContacts","returns an empty contacts transaction set (valid array; the public merge code is unchanged)"),
 ("B-R15","rwa","R16","database.transactionsWithinDateRange","skips filtering for requests with a complete valid date range"),
 ("B-R16","rwa","R16","database.transactionsWithinAmountRange","skips filtering for requests with complete non-zero bounds"),
 ("B-R17","rwa","R17","utils/transactionUtils.ts: getPaginatedItems","offset fixed to 0; pageData computation kept"),
 ("B-R18","rwa","R18","database.getLikesByTransactionId","returns an empty likes set on read (a query fault, not a persistence fault)"),
 ("B-R19","rwa","R19","database.createComment","fixed rewrite of the content on storage; identities and transaction unchanged"),
 ("B-R20","rwa","R20","createTransaction, payment branch","omits creating the received-payment notification; transaction and funds are updated"),
 ("B-R21","rwa","R21","database.createLikes","omits the receiver notification in the two-recipient branch"),
 ("B-R22","rwa","R21","database.createComments","omits the receiver notification in the two-recipient branch"),
 ("B-R23","rwa","R22","database.getUnreadNotificationsByUserId","keeps userId but drops isRead = false, so cleared notifications are read"),
 ("B-R24","rwa","R22","database.updateNotificationById","omits persisting the notification edits; transactions, comments and likes untouched"),
]
RESPONSE_RULES = {
 "A-C01": ("C01, C02", "user.username in the register/login/current-user response is rewritten to another non-empty string (token and password untouched)"),
 "A-C02": ("C04", "after creation, article.body in the GET response is deterministically rewritten (slug and author unchanged)"),
 "A-C03": ("C04", "one existing valid tag is removed from article.tagList"),
 "A-C04": ("C06", "after an edit, article.body in the GET response reverts to the pre-edit content of the same resource"),
 "A-C05": ("C07", "after a deletion, the list response re-includes the deleted article"),
 "A-C06": ("C09", "in the comments GET, the target comment.body is rewritten (identity and author unchanged)"),
 "A-C07": ("C10", "after deleting a comment, the comments GET re-inserts the deleted comment"),
 "A-C08": ("C11, C12", "after favorite/unfavorite, article.favorited is flipped in one observation"),
 "A-C09": ("C11, C12", "at the same position, article.favoritesCount is increased by 1"),
 "A-C10": ("C13", "after follow/unfollow, profile.following is flipped"),
 "A-C11": ("C14", "a tag-filtered list gains an existing article that lacks the requested tag"),
 "A-C12": ("C14", "an author- or favorited-filtered list gains an existing article that does not satisfy the filter"),
 "A-C13": ("C15", "a non-first page is replaced by the first-page slice of the same limit"),
 "A-C14": ("C16, C18", "the feed misses one due article, or profile.bio reverts to the pre-update value (two operators, per route)"),
 "A-R01": ("R01", "/checkAuth: a non-secret public identity field of the logged-in user is rewritten"),
 "A-R02": ("R03", "GraphQL bank-account read-back: bankName is rewritten (id, type and other fields kept)"),
 "A-R03": ("R04", "listBankAccount gains another user's existing account"),
 "A-R04": ("R05", "after deletion, the account's isDeleted is changed from true to false"),
 "A-R05": ("R06", "after an update, public user/search responses revert firstName to the old value"),
 "A-R06": ("R07", "search results gain the current user's own public record"),
 "A-R07": ("R08", "transaction.amount is increased by 1 cent"),
 "A-R08": ("R08", "transaction.description is deterministically rewritten"),
 "A-R09": ("R09-R11", "after a payment, one user's balance is increased by 1 cent (sender and receiver instantiated separately)"),
 "A-R10": ("R12, R13", "a request's requestStatus is replaced within the valid pending/accepted enumeration"),
 "A-R11": ("R15, R16", "a transaction list gains an existing transaction that violates the participant, date or amount filter (each filter separately)"),
 "A-R12": ("R17", "a later page is replaced by the first-page slice of equal length"),
 "A-R13": ("R18, R19", "transaction read-back: one target like or comment is removed (two collections separately)"),
 "A-R14": ("R20, R21", "notifications GET: one notification for this transaction or interaction is removed"),
 "A-R15": ("R22", "after clearing, the unread list re-includes the notification just cleared"),
}
COMPOSITIONS = [
 ("C-C01","conduit","C06, C11-C12, C14","L4-EDIT-01, L4-FAVORITE-01","A publishes; B favorites; A edits the same article; B reads favourites/detail; B unfavorites. The earlier favourite still points to the same article after the edit; counts change only through that user's actions.",""),
 ("C-C02","conduit","C06, C09-C10","L4-COMMENT-01, L4-EDIT-01","A publishes; B comments; A edits; both read comments; B deletes the comment. Body edits do not delete others' comments; deleting a comment does not roll back the article.",""),
 ("C-C03","conduit","C07, C13, C16","L4-FOLLOW-01, L4-PUBLISH-01, L4-DELETE-01","B follows A; A publishes; B reads the feed; A deletes; B reads the feed; B unfollows. Follow state and article lifecycle are independent.",""),
 ("C-C04","conduit","C07, C09, C11, C17","L4-FAVORITE-01, L4-COMMENT-01, L4-DELETE-01, L2-TAG-01","A publishes with tags; B favorites/comments; A deletes; list, detail and tag queries. The deleted article is not returned; global tag deletion is not assumed.",""),
 ("C-C05","conduit","C04, C09, C18","L2-SETTINGS-01, L4-PUBLISH-01, L4-COMMENT-01","A publishes; B comments; A changes only bio/image; B re-reads the author profile and content. The profile refresh loses no articles or comments.",""),
 ("C-C06","conduit","C04, C17","L1-ARTICLE-07","After the recorded creation the article and /api/tags are read and the submitted tags are compared.","D5"),
 ("C-C07","conduit","C04","L1-ARTICLE-07","The created article is read immediately five times without settling.","D6"),
 ("C-R01","rwa","R06-R10","L4-SETTINGS-SEARCH-01, L3-PAYMENT-01","A updates the public profile; B searches A by the new fields; B pays A; both read back. New fields do not redirect funds to another identity.",""),
 ("C-R02","rwa","R08-R10, R18-R22","L4-PAYMENT-NOTIFY-01, L4-THIRD-PARTY-COMMENT-01, L4-THIRD-PARTY-LIKE-01","One transaction; third-party interactions; participants read and clear notifications one by one; the transaction is re-read. Clearing deletes no interaction and repeats no transfer.",""),
 ("C-R03","rwa","R08-R10, R15-R17","L2-PAYMENT-01, L4-PAYMENT-FEEDS-01, L1-FEED-04","Two valid payments; both read Mine; date and amount filters; filters cleared.",""),
 ("C-R04","rwa","R03-R05, R08-R10","L3-BANK-01, L3-PAYMENT-01","A non-essential bank account is created and soft-deleted; a payment is made from the existing sufficient app balance; both parties' accounts and transactions are read.",""),
 ("C-R05","rwa","R12-R13, R18-R22","L3-REQUEST-ACCEPT-01, L4-REQUEST-NOTIFY-01, L3-COMMENT-01","A requests; B accepts once; both interact; notifications are cleared; status and balances are re-read. No repeated settlement, no rollback of accepted.",""),
 ("C-R06","rwa","R12-R14","L3-REQUEST-REJECT-01","Balances and the transaction status are read before and after the recorded reject.","D1"),
 ("C-R07","rwa","R13","L3-REQUEST-ACCEPT-01","A second identical accept after the recorded accept; balances compared.","D2"),
 ("C-R08","rwa","R22","L1-NOTIFY-01","The other actor PATCHes the owner's notification after the recorded request update.","D3"),
 ("C-R09","rwa","R21","L4-LIKE-NOTIFY-01","The actor likes and comments its own new payment before the recorded accept; the actor's own notifications are compared.","D4"),
 ("C-R10","rwa","R01, R04","L3-REQUEST-REJECT-01","After the original checks the actor logs out and repeats ListBankAccount.","D7"),
]
def routes_of(r: dict) -> str:
    def fmt(pairs): return ", ".join(f"`{m} {p}`" for m, p in pairs)
    if r["kind"] == "source":
        parts = ["pairing route(s): " + fmt(r.get("routes") or [])]
        if r.get("affected_reads"): parts.append("affected reads: " + fmt(r["affected_reads"]))
        return "; ".join(parts)
    parts = []
    if r.get("writes"): parts.append("trigger write: " + ", ".join(f"`{w['method']} {w['path']}` ({w.get('role')})" for w in r["writes"]))
    else: parts.append("no trigger write (a read/query rule)")
    if r.get("reads"): parts.append("reads: " + fmt(r["reads"]))
    return "; ".join(parts)

def change_of(r: dict) -> str:
    if r["kind"] == "source":
        p = r.get("patch") or {}
        return f"{r['description']} Patched file `{p.get('patched_file','')}`, diff `{p.get('diff','')}`, laid read-only over `{p.get('container_path','')}` in the image (original SHA-256 `{p.get('original_sha256','')[:16]}…`)."
    return f"`{r.get('operator')}` {json.dumps(r.get('target'), sort_keys=True)} — {r['description']}"

def added_subject_sections(out: list):
    rows = {}
    for s in ("umami", "paperless", "ghost"):
        p = RQ2S / "inputs" / f"faults-{s}.jsonl"
        if not p.exists(): continue
        rows[s] = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    if not rows: return 0
    total = sum(len(v) for v in rows.values())
    out += ["", f"## 5. Faults of Umami, Paperless-ngx and Ghost ({total})", "",
            "The same registry format and the same protocol: designed from the functional description, the pinned source "
            "version and the recorded UI action sequences, frozen before any detection result was seen, and evaluated with "
            "the pairing, the O0/O1/O2 projection and the business-only and unknown definitions of Section IV-F. Umami has "
            "response faults only: its subject is a pre-built image and no source tree was available on the machine, so no "
            "source fault could be laid over it. Identifiers, registry rows and per-fault outcomes are in "
            "`eval/ui_semantics/rq2-subjects-20260921/` (`inputs/faults-<subject>.jsonl` with the frozen copies "
            "`inputs/faults-<subject>.frozen-*.jsonl.bak`, `suite/outcomes-*.jsonl`, `suite/report-<subject>.md`); the "
            "registry format is specified in `inputs/FAULT-CATALOG-SPEC.md`.", ""]
    for s, rs in rows.items():
        src = [r for r in rs if r["kind"] == "source"]; resp = [r for r in rs if r["kind"] == "response"]
        out += [f"### 5.{list(rows).index(s) + 1} {SUBJECT_LABEL[s]} ({len(src)} source, {len(resp)} response)", "",
                "| Fault | Kind | Module | Business rule | One local change / operator | Routes | Activated by |",
                "|---|---|---|---|---|---|---|"]
        for r in rs:
            out.append(f"| {r['fault_id']} | {r['kind']} | {r.get('module')} | {r['business_rule']} | "
                       f"{change_of(r)} | {routes_of(r)} | {TRIGGERS.get(r['fault_id'], '-')} |")
        out.append("")
    ghost = rows.get("ghost") or []
    if any(r["fault_id"] in GHOST_EXTENSION for r in ghost):
        out += ["### 5.4 The read and query rules of the Ghost registry", "",
                "The first six Ghost faults (B-G01..B-G03, PR-G01..PR-G03) target the effects of writes. After the "
                "registration step paired them with the qualified tests it became visible that the Ghost test suite contains "
                "almost no writes: of its 739 qualified tests, 563 are read-to-read query relations and 176 are single-response "
                "checks, and the only writes in the plans are 7 `POST members/` and the settings `PUT`. Five further faults were "
                "therefore designed from the read and query rules that the recorded reads exercise — B-G04 and B-G05 (wrong query "
                "condition in the source: a column-projected browse and the posts search index are restricted to the page type) "
                "and PR-G04..PR-G06 (response faults with no trigger write, gated on a query key: `fields`, `include`, `order`). "
                "The first six faults stay in the denominator of the reported results.", ""]
    return total

def main():
    rf = [json.loads(l) for l in open(RQ2 / "response-faults.jsonl", encoding="utf-8") if l.strip()]
    out = ["# Fault catalogue (RQ2)", "",
           "Everything here was fixed before any detection result was seen (Section IV-F of the paper). The business rules come from the functional description, the fixed source versions and the recorded UI action sequences; each seeded source fault changes one place of business logic, each injected response fault applies one fixed transformation to every matching response on the client side. Sections 1-4 cover Conduit and RWA (identifiers as used in `eval/ui_semantics/rq2-deepseek-final2-20260912/suite/`: `outcomes-*.jsonl`, `test-fault-map.jsonl`), section 5 covers Umami, Paperless-ngx and Ghost (`eval/ui_semantics/rq2-subjects-20260921/`). The `definition_ref` field of `response-faults.jsonl` points at the authors' internal design notes, which this catalogue supersedes.", "",
           "## 1. Business rules of Conduit and RWA", "", "| Rule | Statement |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in RULES.items()]
    out += ["", "## 2. Seeded source faults of Conduit and RWA (42; patches in `eval/ui_semantics/rq2-20260907/patches/`)", "",
            "| Fault | Subject | Rule(s) | Location | One local change |", "|---|---|---|---|---|"]
    out += [f"| {i} | {s} | {r} | `{loc}` | {chg} |" for i, s, r, loc, chg in SOURCE]
    out += ["", "## 3. Injected response faults of Conduit and RWA (35 instances; definitions in `suite/response-faults.jsonl`)", "",
            "| Fault | Subject | Field | Operator | Applied to responses of | Rule(s) | Transformation |", "|---|---|---|---|---|---|---|"]
    for r in rf:
        rule, text = RESPONSE_RULES.get(r.get("legacy_rule"), ("", ""))
        out.append(f"| {r['fault_id']} | {r['subject']} | `{r.get('field')}` | {r.get('operator')} | {', '.join(r.get('substates') or [])} | {rule} | {text} |")
    out += ["", "## 4. Cross-flow compositions of Conduit and RWA (17; schedules in `suite/compositions.jsonl`)", "",
            "| Composition | Subject | Rules | Sequences | Schedule and checks | Targets confirmed defect |", "|---|---|---|---|---|---|"]
    out += [f"| {i} | {s} | {r} | {seq} | {d} | {t or '-'} |" for i, s, r, seq, d, t in COMPOSITIONS]
    added = added_subject_sections(out)
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rf)} Conduit/RWA response faults, {added} faults of the three other subjects)")
if __name__ == "__main__": main()
