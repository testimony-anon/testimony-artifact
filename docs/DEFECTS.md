# Confirmed defects of the subject applications (Table V of the paper)

This document records the controlled reproduction of the defect leads that came out of the study. Every defect confirmed this way is in Conduit or RWA; the leads came from their refuted candidate oracles and their composed executions, which is the part of the study this document covers. It is an independent reproduction, not a new generation experiment: no model was called, no pipeline code was used, and no frozen result, label or method was modified. The paper's defect ids D1–D7 correspond to the lead ids L1–L8 used by the scripts (L5 was not reproduced and has no paper id).

## Environments

- **RWA**: an unpatched copy of the pinned commit `bdf6169` (the pristine checkout used for RQ2), Node.js 22, backend alone on port 14101; before and after every lead the seed data is restored with `POST /testData/seed`. Seed users: A = `Heath93`, B = `Arvilla_Hegmann`, C = `Dina20`; amounts are in cents.
- **Conduit**: the unpatched normal image of the pinned commit `5e127d8` (`uisemtest-rq2-normal:20260907`, the same image the RQ2 normal runs use) deployed as a separate stack on port 3301 with a fresh database.

## Scripts and evidence (`eval/ui_semantics/bug-leads-20260912/`)

| Script | Leads | Evidence | Verdicts | Base URL |
|---|---|---|---|---|
| `reproduce_rwa_leads.py` | L1–L5 | `evidence.jsonl` (request body, status and response body of every HTTP exchange) | `summary.json` (balances, transaction fields and notification counts before/after) | `RWA_BASE_URL` (default `http://localhost:14101`) |
| `reproduce_conduit_leads.py` | L6, L7 | `conduit-evidence.jsonl` | `conduit-summary.json` | `CONDUIT_BASE_URL` (default `http://localhost:3301`) |
| `reproduce_rwa_lead8.py` | L8 | `evidence-lead8.jsonl` | `summary-lead8.json` | as `reproduce_rwa_leads.py` |

The scripts use plain HTTP (`urllib`) only; each run appends to its evidence file and rewrites its verdict file.

## 1. Where the leads came from

| Source | Leads |
|---|---|
| Candidate oracles refuted by the real system (M12 `refuted`). At the time of reproduction (2026-09-12, before the final export) 25 refuted candidates had been examined (Conduit 5, RWA 20); 8 RWA ones concentrated on rejected or repeatedly accepted payment requests (`L3-REQUEST-REJECT-01` and `L4-REQUEST-REJECT-01`: 2 C04/P20 candidates each, "the other transaction fields stay unchanged after a rejection"; `L3-REQUEST-ACCEPT-01`, `L3-REQUEST-REJECT-01`, `L4-REQUEST-REJECT-01`: 4 C05 `repeat_rejected` candidates, "a repeated operation is rejected"), and one Conduit candidate (`L1-ARTICLE-07`, C02/P02, "the read-back tagList equals the submitted tagList"). The complete review of the 57 refuted candidates of the final run is in `REFUTED-REVIEW.md`. | L1, L2, L6, L8 |
| The semantic review of the previous round (RQ1): 12 incorrect RWA assertions all involved notification updates addressed with a stale id, and the review had noted that "another seeded notification was removed". | L3 |
| Source-code suspicions noted while designing the RQ2 fault catalogue: the transfer and notification on a rejected request, the OR condition of self-notifications on interactions, the zero lower bound of the amount filter. | L1, L4, L5 |
| Direct reading of the pinned source: `backend/database.ts` (`updateTransactionById`, `updateNotificationById`, `createComments`, `createLikes`, `transactionsWithinAmountRange`). | L1–L5 |
| Observed while reproducing L6. | L7 |

## 2. Reproduction results

| Paper | Lead | Business rule (as the UI expresses it) | Steps | Observation | Verdict |
|---|---|---|---|---|---|
| D1 | L1 | Rejecting a payment request must not move funds, must not mark the transaction complete, and must not send the requester a "received" notification | A requests $10 from B; B `PATCH /transactions/:id {requestStatus: rejected}` → 204 | transaction `status: pending → complete`, `requestStatus: rejected`; balance A +1000, B −1000; A receives 1 `received` notification | **reproduced** |
| D2 | L2 | A request settles only once | A requests $10 from B; B accepts twice; both `PATCH` return 204 | first accept: A +1000 / B −1000; second accept: again A +1000 / B −1000; A receives 2 `received` notifications | **reproduced** |
| D3 | L3 | Users may modify only their own notifications | C `PATCH /notifications/<id of A's notification> {isRead: true}` → 204; A reads the unread list | A's notification has disappeared from A's unread list; a non-existent id also returns 204 | **reproduced** (cross-user write; it also explains why the 12 stale-id tests of the previous round "succeeded") |
| D4 | L4 | An interaction notifies only the other party of the transaction | A pays B $5; A comments on and likes that transaction | A receives 1 comment notification and 1 like notification; B receives one of each as well | **reproduced** (`createComments`/`createLikes` test `userId !== senderId \|\| userId !== receiverId`, which is always true) |
| — | L5 | An amount filter with lower bound 0 must still exclude transactions above the upper bound | `GET /transactions/public?amountMin=0&amountMax=20000` compared with `amountMin=1&amountMax=20000` | identical results, none above the upper bound; the query parameter reaches the backend as the string `"0"`, so `!amountMin` is false and the filter works | **not reproduced**; the source-code suspicion does not hold (a first attempt used `amountMax=1000`, below every seeded amount, and returned empty on both sides; it was redone) |
| D5 | L6 | The create response must reflect the persisted tag list | a newly registered user creates 4 articles with tagList `['xy','lastingtag']`, `['q']`, `['abc']`, `['zz']` | every create response echoes the submitted tagList; reading the articles back returns `['lastingtag']`, `[]`, `['abc']`, `[]`; `/api/tags` lacks `xy`, `q`, `zz` and contains `abc`. Consistent with the frozen evidence of the refuted candidate (`eval/ui_semantics/deepseek-full-20260912/conduit/m11fix-01/cases/L1-ARTICLE-07/union/M12/v2-candidate-0004/execution_evidence.json`) | **reproduced**: `createArticle` silently drops tags of length ≤ 2 without an error but writes the request's tagList back into the response |
| D6 | L7 | A created article must be readable immediately | (found while reproducing L6) for 2 of the 4 articles, `GET /api/articles/:slug` immediately after creation returned 500 `toAppend.hasFollower is not a function` (evidence sequence numbers 6 and 9); the same request returned 200 a few seconds later | `createArticle` calls `article.setAuthor(loggedUser)` without `await`, so 201 can be returned before the author association is written; `singleArticle` then calls `appendFollowers(loggedUser, article)` on the missing author object | **reproduced** (race condition; directly relevant to composed executions and rapid successive calls) |
| D7 | L8 | An unauthenticated GraphQL query must receive an authentication error (the REST counterpart `GET /bankAccounts` returns 401), not a server-side exception | source: candidate `v2-candidate-0015` of `rwa/L3-REQUEST-REJECT-01` (refuted; its claim that `listBankAccount` is unchanged across actor_b's logout is wrong, but the after observation showed the logged-out query answering HTTP 200 with `{"data":{"listBankAccount":null},"errors":[{"message":"TypeError: Cannot read properties of undefined (reading 'id')"}]}`). Logged in: 200 with 1 account; same session after logout: 200 with the TypeError; a fresh session: 200 with the TypeError; REST control `GET /bankAccounts`: 401 | `backend/graphql/resolvers/Query.ts` lines 4–7: `listBankAccount` returns `getBankAccountsByUserId(ctx.user.id)`; `backend/app.ts` lines 102–110 mount `/graphql` with the context `{ user: req.raw.user }` and without `ensureAuthenticated` (unlike `bankaccount-routes.ts`), so `ctx.user` is undefined when logged out and the TypeError is returned as a GraphQL error with status 200. `createBankAccount` in `resolvers/Mutation.ts` reads `ctx.user.id` the same way (not reproduced separately) | **reproduced** |

## 3. Relation to the upstream repositories

- RWA (`cypress-io/cypress-realworld-app`): several pull requests from January 2026 (#1678, #1681, #1682, #1683, #1685, #1688) claim that the payment/request logic of `createTransaction` and `updateTransactionById` is inverted; none was merged as of 2026-09-12 (#1688 still open). The pinned commit `bdf6169` postdates these pull requests: its `createTransaction` already settles payments immediately, but `updateTransactionById` still transfers funds, marks the transaction complete and notifies on every update of a request transaction, whatever the new `requestStatus`. The description of #1688 says its fix only negates `if (isRequestTransaction(transaction))` in `updateTransactionById`, without distinguishing accept from reject and without an idempotency guard (its diff was not checked line by line). No upstream issue or pull request was found for notification ownership (D3), self-notification (D4) or the unauthenticated GraphQL resolver (D7).
- Conduit (`TonyMckes/conduit-realworld-example-app`): no upstream report was found for D5 or D6.

D1–D7 are application defects brought up by refuted generated oracles, by the semantic review and by source reading, and confirmed by controlled reproduction; they are not automatic detections of the generated test suite. Section V-B of the paper reports which of them raise an alarm in the composed executions of RQ2.
