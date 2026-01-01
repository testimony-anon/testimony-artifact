# Author adjudications of the RQ1 semantic review: rules and decisions

**Two layers.** Every retained test carries an assertion layer. *Business relations* connect several requests, or a request and a later read, and are reviewed against the business semantics of the application; *structural constraints* evaluate one condition on a single response. The two layers were reviewed separately, with their own prompts and their own criteria: the business layer is the subject of the sections up to and including *Ablation suites*, the structural layer of the last section of this document. The paper's correctness rate over the business assertions and the rate over all retained tests are therefore both reproducible from the files in this package.

**Scope.** The initial labels (C = correct, E = incorrect, U = insufficient evidence) come from the model-assisted initial review (`reviews.jsonl`; prompt v2 for the Conduit/RWA Full suite, v2.1 for the instances added after the D6 fix, for the Conduit/RWA ablation suites and for every suite of Umami, Paperless-ngx and Ghost). The authors then adjudicated, item by item against the execution evidence and the pinned source code, every E/U instance and every instance whose label disagrees with the previous round, and spot-checked C instances by semantic group (the two largest and two random groups per subject). The adjudication notes were drafted with AI assistance and confirmed item by item by the authors. The M12/M14 verdicts, the test set and the method were not changed by the review.

**Review status differs between subjects, and the paper says so (Sections IV-E and VII).** The Conduit and RWA suites are adjudicated as described above. For Umami, Paperless-ngx and Ghost the reported labels are the initial ones; only the instances the initial review labelled incorrect were adjudicated (one for Umami, two for Ghost, none for Paperless-ngx, whose initial review returned no incorrect instance), and the ablation suites of these three subjects carry initial labels throughout.

**Records.** `docs/design/cpv-expansion/rq1-audit-deepseek{,-temporal,-flat}/main-review.jsonl` and `docs/design/subjects-expansion-20260919/rq1-audit-{umami,ghost}/main-review.jsonl`: one row per adjudicated instance with `test_key`, `label` (final), `rule` (A/B/C), `scenario_specific`, `reason`, `basis` (evidence and source locations), `reviewed_at`, `reviewer`. The merged labels are in `tests-labeled.jsonl` (`label_source` tells whether the final label comes from the initial review or from the adjudication); `summary.md` counts the scenario-specific instances separately and reports C/T with and without them.

## Rules

- **Rule A — scenario-specific instantiation of the business intent → C, flagged `scenario_specific`.** The assertion checks the effect that the recorded step was meant to achieve and holds for the data and parameters of the recorded scenario, but its form is stronger than the application's general semantics (examples: an exact user-name search returns that user; `articlesCount` equals the array length when the result set fits on one page; accepting a private request leaves the public feed unchanged). This follows the previous round's treatment of the same propositions ("correct in the empty state"). The paper reports the business correctness rate with and without these instances.
- **Rule B — coincidental equality between different inputs → E.** The generator treated two different inputs (different search terms; a list with and without a filter) as equivalent and asserted equal results, but the equality only comes from a coincidence of the recorded data (one user matches both terms; every article has the same author; both results are empty). The application's semantics defines no such equivalence, and the correct relation (for instance, subset) is not the one asserted.
- **Rule C — the initial review applied general semantics that this implementation contradicts → the source code and the execution evidence decide.** When the initial reviewer judged by RealWorld or general-application assumptions, the implementation behaves differently, and the M12 evidence agrees with the implementation, the label becomes C; when the implementation shows the assertion to be wrong, E is kept.

## Conduit and RWA, Full suite (final test set): 29 adjudicated instances

The interim export (59 cases, 701 business instances) had 24 E from the v2 initial review; the instances added by the final export were reviewed with the same prompt and adjudicated with the same rules (items 8–9).

1. **RWA notification list — 7 instances relabeled C (rule C).** `L1-NOTIFY-01`, P14: "after `PATCH /notifications/:id` with `isRead=true`, the notification is removed from `GET /notifications`". The initial review assumed that the list returns all notifications. In this implementation the `GET` route calls `getUnreadNotificationsByUserId` (`backend/notification-routes.ts:20-22`, `backend/database.ts:700-701`, filter `isRead: false`), so a notification marked read disappears from the unread list; the evidence contains the id before and not after. The assertion states a correct business rule.
2. **RWA notifications and public feed after accepting a request — 2 relabeled C.** `L3-REQUEST-ACCEPT-01/…7b40862f` (P20: actor_b's own notification list is unchanged around accepting the request): `database.ts:578-595` creates a notification only for `transaction.senderId`, the requester; the acceptor's unread list is unchanged and the original "requested" notification is not marked read (rule C). `L4-REQUEST-NOTIFY-01/…6efb02ed` (P20: `GET /transactions/public` unchanged around accepting): the accepted request is not in the public feed (its first entry is a seeded 2023 transaction), so the feed being unchanged is the correct outcome under the request's privacy level; C, scenario-specific (rule A).
3. **RWA user search — 9 relabeled C, scenario-specific (rule A).** `L1-TXN-01`, `L1-DETAIL-01/02/03`, `L2-PAYMENT-01`, `L2-REQUEST-01`: "for every result of `GET /users/search?q=Dina20`, `username` equals / starts with / contains q". `database.ts:156-162` matches firstName, lastName, username, email and phoneNumber, so "username equals q" is not a general rule; but the recorded step's intent is to find the payee by user name, and the assertion instantiates that intent on the recorded data: it fails if the search no longer returns Dina20 or returns unrelated users. Consistent with the previous round's C label for the same core identity.
4. **Conduit count proposition — 1 relabeled C, scenario-specific (rule A).** `L2-SETTINGS-01/…8c8ae48d`: `GET /api/articles?author=carver&limit=3` returns an empty page and P19 asserts `articlesCount = count(articles)`. `articlesCount` is the size of the matching set; the scenario's matching set fits on one page, so the equality is the degenerate instance of the counting rule, and the test fails if the backend counts all articles when filtering by author.
5. **Kept E — 5 instances (rule B).** `conduit/L2-ARTICLE-01/…71b77cf7`: the unfiltered list equals the `author=carver` list; the correct relation of a filter refinement is subset, and equality holds only because every article in the scenario is carver's. `rwa/L1-SEARCH-01/…8b6d36b8`: `q=Darrel` and `q=Ortiz` return equal sets only because one user (Darrel Ortiz) matches both terms and nobody else does. `rwa/L4-SETTINGS-SEARCH-01` (3 instances): `q=6155551212` (a phone number) and `q=CrossFirst` (a name) both return an empty array; the equality is a data coincidence.
6. **Sampled C groups — confirmed.** Conduit `7a713940260a` (46 instances, P19 count on `GET /api/articles`) and `005217d34575` (24, P19 count on `/api/articles/feed`): the counting rule of item 4 with result sets within one page, all M12 validated. Conduit `07d5d0611337` (2, session relations of two distinct actors) and `e124b064f459` (1, article title after `POST /api/articles` equals the request title). RWA `ae424b77d8d9` (37, two identical `POST /graphql` listBankAccount queries return equal results: an idempotent read of equivalent inputs), `12e6cf1637d3` (27, `GET /users/search` results are a subset of `GET /users`), `6bde5574214b` (4, the transaction id after `PATCH /transactions/:id` equals the request id) and `bb459eac719d` (1, identity relation).
7. **Calibration of the initial review (disclosure).** Prompt v1 gave 23 E on 89 instances, 21 of them from misapplied criteria; prompt v2 gave 24 E on 701 instances, of which 5 remained E after adjudication. The v1 labels are not part of any statistic; the prompt was adjusted against the previous round's labels of the same core identities (`calibration.jsonl`).
8. **Final export supplement.** The business instances added by the final export (the last 15 Conduit cases of the continued run and 6 re-recorded RWA cases) were labeled by the same v2 initial review; the new E/U items were adjudicated with the rules above. RWA `L4-THIRD-PARTY-LIKE-01` (2) and `L4-THIRD-PARTY-COMMENT-01` (2), user-search assertions (username equals / contains `q=Dina20`): as item 3, C, scenario-specific. RWA `L3-LIKE-01/…7a45ebee` (P20: the public feed is unchanged around a like): the liked transaction is not in the public feed (none of the 5 public transaction ids after the like is this transaction), so the unchanged feed is correct under the privacy level; U → C, scenario-specific. 5 instances left unlabeled by an interrupted API connection were reviewed afterwards: all C (a like or comment leaves the transaction's frozen fields unchanged).
9. **The 47 relations added after the D6 fix.** After the fix of pipeline defect D6 (two id domains: fresh replay ids versus recorded ids), 10 RWA cases were continued into `m11fix-02` and 47 retained tests were added (added/removed relations on likes, comments and notifications). The v2 initial review labeled 32 of them E and left 5 unreviewed after a network interruption. Every E had the same misreading: the review packet showed the request path and body with the fresh replay id (for example `POST /comments/0JBjYxQER`) while the persisted response body had been normalized back to the recorded id (`transactionId: Gr3YrXAaN`), and the reviewer took them for two different resources. This is the evidence-presentation side of the same two-domain issue, not an assertion error. Handling: the packets were extended with the recorded-domain request body and a fresh-id → recorded-id alias table (`alias_pairs_fresh_to_recorded` and `producer_request_body_recorded_domain` in `tests.jsonl`), prompt v2.1 states that both denote the same resource, and only these 37 E/W items were re-reviewed (the superseded v2 rows are not part of this package). Result: all 37 C; the adjudication changed no label. The relations state that after a participant or third party likes or comments, `GET /transactions/:id` has a new member in `likes`/`comments`, and that a notification leaves the unread list after being marked read. Spot checks of 3 items each of `L4-THIRD-PARTY-LIKE-01` and `L3-COMMENT-01` agree with the execution evidence.

Final tally of the Full suite: 1,047 business instances, C 1,042, E 5 (all of item 5), U 0.

## Conduit and RWA, Temporal ablation suite: 20 adjudicated instances

The v2.1 initial review gave E 19 and U 1 on the suite's business instances. Decisions:

- 14 × rule A (→ C, scenario-specific): user search by user name `Dina20`, as item 3 of the Full suite (initial E/U).
- 3 × rule A (→ C, scenario-specific): the liked or commented transaction is not in the public feed, so the feed being unchanged is correct under the privacy level, as item 2 of the Full suite (initial E).
- 1 × rule C (→ C): `GET /notifications` returns only unread notifications in this implementation, so removal after marking read is the correct rule, as item 1 (initial E).
- 1 × rule C (→ C): `rwa/L4-SETTINGS-SEARCH-01/…a837ec8f`: the assertion is that after `PATCH /users` the user entry with the new name and phone number appears in `GET /users` (identity matched on the new field values; before 0, after 1). This is the correct visible effect of a profile update in the list; "added" is only the template's wording (initial E).
- 1 × rule B (E kept): `q=6155551212` and `q=CrossFirst` both return empty results; a data coincidence, as item 5.

After adjudication: E 1 of 644 business instances.

## Conduit and RWA, Flat ablation suite: 15 adjudicated instances

The v2.1 initial review gave E 15 and U 0 on the suite's business instances. Decisions:

- 13 × rule A (→ C, scenario-specific): RWA `/users/search` results' `username` equals (5), contains (6) or starts with (2) q. `database.ts:156-162` `searchUsers` is a multi-field containment match; the recorded query `q=Dina20` has the single result `username=Dina20`; as item 3 of the Full suite.
- 2 × rule A (→ C, scenario-specific): Conduit empty feed, `count(articles) = articlesCount`, as item 4 of the Full suite (an empty matching set fits on one page).

After adjudication: E 0 of 359 business instances (count after the 2026-09-15 export correction described in `RUN-NOTES.md`; the three business instances added by that correction were labeled C by the initial review and needed no adjudication).

## Umami: 1 adjudicated instance

The v2.1 initial review labelled 109 of the 110 business instances correct and one incorrect. Decision:

- **1 relabeled C (the initial label is overturned; the initial review read a truncated excerpt).** `umami/L1-WEBSITE-03/…a26f7ee5`: the assertion states that the projected pagination fields `page`, `pageSize` and `orderBy` of `GET /api/users/{id}/websites` are equal across the two observations. The initial review judged them absent from the observed response bodies. They are present in both the `before` and the `after` slot of `M12/v2-candidate-0004/execution_evidence.json`; Umami places them after the `data` array, and the review packet truncates the excerpt at 1,500 and 700 characters, so they fell outside it. The sibling instance `…a8b4d4f5` of the same case, with the identical predicate and call sites, was labelled C. Reported tally: 110 correct of 110 business instances.

## Paperless-ngx: no adjudicated instance

The v2.1 initial review labelled all 444 business instances correct and returned no incorrect or insufficient-evidence instance, so there was nothing to adjudicate. Reported tally: 444 correct of 444.

## Ghost: 2 adjudicated instances

The v2.1 initial review labelled 596 of the 598 business instances correct and two incorrect. Both are the same proposition, and both keep the initial label:

- **2 × rule B (E kept).** `ghost/L1-MEMBER-01/…aa612176` and `ghost/L2-MEMBER-03/…624c2faf`: "the `meta.totals.free` of `GET /ghost/api/admin/stats/member_count/` equals the sum of the `free` fields of the `stats[]` rows" (P19, a sum). In Ghost 5.130.6, `getCountHistory` of `core/server/services/stats/MembersStatsService.js` (lines 81–124) derives the daily rows backwards from the current totals, so each row is the member count accumulated **up to that day**, not the change on that day. The equality holds in the recorded data only because every earlier day is zero (2026-09-19 zero, 2026-09-20 one); with one new member on each of two days the rows would be 1 and 1 while the total is 1. This is a coincidental equality proposed from a single observation, of the same kind as the five incorrect instances of Conduit and RWA. Reported tally: 596 correct, 2 incorrect of 598 business instances.

The remaining correct instances of these three subjects were not re-examined item by item, as for Conduit and RWA.

## Ablation suites of Umami, Paperless-ngx and Ghost

The labels reported for these six suites are the initial ones; no instance was adjudicated. The counts of instances the initial review labelled incorrect are in `docs/ABLATION-RESULTS.md` and in each audit directory's `summary.md`.

## Structural constraints (the single-response layer)

**Object.** The structural constraints of the five Full suites: the rows of each audit directory's `tests.jsonl` whose
`layer` is `basic_constraint`. Every one of them is a single-response V2 read: the test replays the recorded input
sequence and then evaluates one condition on one response. The ablation suites were not reviewed at this layer.

**Criterion — the same question as for the business relations, asked about one response.** A constraint is **correct**
when it follows from the application's logic under the preconditions of the recorded sequence: it is a stable property of
that endpoint's response in the pinned version, given the same authenticated user, the same operations and the same data
(a property of the response serializer, the schema or the framework). It is **incorrect** when the pinned version admits
a clear counterexample, that is, when the constraint only states what happened to hold in this one recording; it is
**insufficient evidence** when neither can be decided from the packet. That the assertion passed in the recording is
never a reason on its own: the recorded response satisfies it by construction. This is the criterion of the business
review, applied to a single response; both layers are judged by it, which is why a constraint that instantiates a
general rule on the data of the recorded scenario is correct in both.

**Procedure and records.** The initial labels come from a model-assisted review with its own prompt
(`scripts/experiments/rq1_tools/prompts/structural_review_v1.0.md`, version `structural-v1.0`, run by
`scripts/experiments/rq1_tools/rq1_review_structural.py`); each packet restates, from the untruncated response body in
the M12 execution evidence, the facts the predicate talks about, so a truncated excerpt cannot hide the asserted value.
The per-item labels are in `structural-reviews.jsonl`, the per-directory breakdown by predicate family and the list of
the items labelled incorrect in `structural-summary.md`, and the calls that returned no label in
`structural-review-failures.jsonl`. The authors then adjudicated the items the initial review labelled incorrect and the
items that received no label; their decisions are in `structural-main-review.jsonl`, and the final label of every
constraint is in `structural-labels-final.jsonl`. The counts of `structural-summary.md` are the **initial** ones and
differ from the final ones wherever the adjudication changed a label; `structural-labels-final.jsonl` is the file the
reported numbers come from, and its `initial_label` field keeps the initial label of every constraint. As for the business layer, the adjudication notes were drafted with AI
assistance and confirmed by the authors, and no verdict, test or method was changed by the review.

**What the adjudication looked at.** The authors examined every constraint the initial review labelled incorrect, the
one constraint for which the review returned no label, and — because the same constraint occurs in several sequences —
every group of constraints that states the same predicate on the same endpoint of the same subject but received
different initial labels. The `rule` field of `structural-labels-final.jsonl` records where each final label comes
from:

| `rule` | Meaning | Outcome |
|---|---|---|
| `structural_initial_review` | The initial label was kept. | 1,522 correct, 9 incorrect |
| `classA_business_parity` | Single-response constraints that equate the number of members on the returned page with a count field of the same response, on a paginated endpoint. They were re-labelled by the authors so that this layer applies the same criterion as the business review, under which a result set that fits on one page satisfies the counting rule. | 15 correct kept, 6 changed from incorrect to correct |
| `group_amount_integer` | The RWA group that asserts, for every member, that `amount` is an integer. Made consistent after reading `backend/validators.ts`, which coerces `amount` with `toInt()`. | 23 correct kept, 1 changed from incorrect to correct |
| `group_ui_settings_uniqueness` | The Paperless-ngx group that asserts uniqueness of `dashboard_views_visible_ids`, a list of ids inside a user-writable JSON document. Made consistent. | 2 incorrect kept, 1 changed from correct to incorrect |
| `author_adjudication` | The one constraint the initial review never labelled (12 calls returned no label): `forall $.results: balanceAtCompletion >= 0` on RWA's `GET /transactions/public`. That field is written only by the seed generator and never by the backend, so its non-negativity is a fact about the seed data and not a property of the endpoint. | incorrect |

## Structural constraints: results

| Subject | Structural constraints | Correct | Incorrect | Insufficient evidence |
|---|---:|---:|---:|---:|
| Conduit | 225 | 225 | 0 | 0 |
| RWA | 888 | 880 | 8 | 0 |
| Conduit + RWA | 1,113 | 1,105 | 8 | 0 |
| Umami | 23 | 23 | 0 | 0 |
| Paperless-ngx | 294 | 289 | 5 | 0 |
| Ghost | 150 | 150 | 0 | 0 |
| **All five subjects** | **1,580** | **1,567** | **13** | **0** |

Correctness rate of the structural layer: **99.2%** (1,567 of 1,580). Correctness rate over all retained tests, business
relations and structural constraints together: **99.5%** (3,759 of 3,779); the business layer contributes 2,192 correct
of 2,199, unchanged by this review. Both rates are recomputed from `structural-labels-final.jsonl` and
`tests-labeled.jsonl` of the four Full audit directories.

The 13 incorrect constraints, with the reason in each row of `structural-labels-final.jsonl`:

- **RWA, 8.** Four freeze a bound on the number of members of a list that does not paginate and whose endpoint only
  filters by the current user, so an empty or longer list is a legal answer (`GET /graphql` `listBankAccount` twice,
  `GET /notifications` twice). One asserts uniqueness of `accountNumber`, which is not the primary key. Three freeze a
  value for every member without a basis in the model or the serializer: `isRead == false`, `balance >= 0` and
  `balanceAtCompletion >= 0`.
- **Paperless-ngx, 5.** Three assert uniqueness of `dashboard_views_visible_ids`, a list of ids inside a user-writable
  JSON document; two assert uniqueness of the `key` field of PDF metadata entries.

No incorrect structural constraint was found for Conduit, Umami or Ghost. As with the business layer, no verdict, test
or method was changed by the review: the incorrect constraints stay in the exported test suites and are reported as
incorrect.
