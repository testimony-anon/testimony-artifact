# Method supplement: pipeline stages, template catalogue, validation plans, bounded rules

Companion to Section III of the paper (*Testimony: Deriving and Validating Business-Level API Test Oracles from Web UI Execution Evidence*). Names follow the paper; identifiers in parentheses are the ones used in the code and in the data files of this package. The authoritative definitions are the prompt template `src/ui_semantics/templates/effect_contract_v2.txt` and the JSON schemas under `contracts/`.

## Terms used in the paper and in this package
| Paper term | Meaning | Name in the code and data files |
|---|---|---|
| target | an action for which candidate oracles are proposed: every UI action containing a write, plus each read-only action that summary screening expands | write centre / scheduled read-only card (`center_action_id`, `detail_region_id`) |
| evidence card | one UI action with its request group, page-state differences, related data flows, dependencies, negative facts and prerequisite references; unattributed requests form cards of their own; API state differences are not stored on the card but enter the associated evidence view through the one-hop expansion | `evidence_cards[]` in the M9 evidence package (`ui_diff_record_ids`, `value_flow_ids`, `dependency_edge_ids`, `negative_request_fact_ids`, `setup_domain_refs`) |
| associated evidence view | the cards and visible requests the model sees for one target | `detail_region` / proposal evidence view (M9/M10) |
| effect source | the write that a candidate names as the cause of an observed change; for an API state difference, the unique write acting on the resource between the two reads | `effect_source` role; `groundable_effect_source_request_ref` |
| prerequisite (business prerequisite, prerequisite request, prerequisite scope) | recorded actions or requests that are replayed before the checked write | `setup`, `setup_domain`, M11 setup closure |
| precondition | a condition under which an assertion is evaluated (identity bindings, established `before` state, applicability of a from–to predicate) | applicability gates in M12 |
| reset (freshly reset application) | the subject re-initialised from its seed state before a validation run or a calibration run | `reset` step of the subject adapter |
| network failure | a request of the plan that could not be completed at the HTTP transport level | `request_transport_failure` |

## Pipeline stages (M0–M14) and code modules
| Stage | What it does | Main modules |
|---|---|---|
| M0–M1 | launch, reset and record the cross-layer trace (UI actions, page states, HTTP traffic, sessions) | `src/stage0_launch`, `src/stage1_record` |
| M2 | attribute requests to UI actions (request groups, anchor requests) | `src/ui_semantics/trace_builder.py`, `binder.py` |
| M3–M5 | observed API structure and catalogue (operations, path templates, shapes) | `src/stage2_recover`, `src/stage3_gate` |
| M6–M8 | data flows, dependency edges, rebinding opportunities | `src/stage4_deps`, `src/ui_semantics/preproposal.py` |
| M9 | evidence cards, negative facts, frozen proposal evidence view | `src/ui_semantics/preproposal.py` |
| M10 | two-stage generation (summary screening, detail proposals), rounds, completion, admission, dedup | `src/ui_semantics/proposal_run.py`, `v2_proposer.py` |
| M11 | prerequisite reconstruction and execution material (plan derivation, rebinding) | `src/ui_semantics/m11_bridge.py`, `m11b_materializer.py`, `binder.py` |
| M12 | execution of the validation plan on a freshly reset application; verdicts | `src/ui_semantics/current_orchestrator.py`, `current_protocols/`, `dsl.py` |
| M13 | compilation into certified relation tests with generic checks | `src/ui_semantics/relation_phase_b.py` |
| M14 | calibration on a fresh normal state; export to pytest | `src/ui_semantics/current_calibration.py`, `pytest_export.py` |

## Relation kinds (17; "contract kinds" in the code)
Allowed predicate families and operators are the legal combinations enforced at admission (`current_executable_relation_language()` in `src/ui_semantics/current_protocols/__init__.py`, 154 rows of contract kind × predicate family × operator; the same table is rendered into every proposal prompt as `relation_language`). "Retained" counts correct business-level tests of the Conduit and RWA final test set (Section V-A); their structural constraints are the 1,113 single-response tests of the basic layer. The same breakdown for Umami, Paperless-ngx and Ghost is obtained from `docs/design/subjects-expansion-20260919/rq1-audit-<subject>/tests-labeled.jsonl` (their retained totals are 133, 738 and 748, of which 23, 294 and 150 are structural constraints). The 1,580 structural constraints of the five Full suites were reviewed separately, with their own criterion; `docs/REVIEW-ADJUDICATIONS.md` states it and reports the outcome, and the per-constraint labels are the `structural-*` files of the four Full audit directories. Examples name the input sequence; the full test is in `docs/design/cpv-expansion/rq1-audit-deepseek/tests-labeled.jsonl` (field `case_id`).

| Relation kind (paper) | Identifier | Meaning | Allowed predicate families (operators) | Retained | Example from the final test set |
|---|---|---|---|---|---|
| create / appear | C01 | a lifecycle or state effect of a write observed by a read of the same actor | P01 (exists/absent), P02, P12, P13, P14 (added) | 62 | after `createBankAccount`, the actor's `listBankAccount` has one more member (RWA L2-ONBOARD-01; P12, workflow check) |
| written-value propagation | C02 | a submitted or returned value is read back after the write | P01, P02, P04 (from_to/toggle), P06, P07, P13 | 204 | after `POST /api/users`, `GET /api/user` returns the submitted `username` (Conduit L1-AUTH-01; P02, workflow check); after `POST /transactions`, the payer's `balance` from `GET /checkAuth` decreases by exactly the amount (RWA L2-PAYMENT-01; P06) |
| delete / disappear | C03 | a member or resource is absent after the write | P01 (absent), P02, P12, P13, P14 (removed) | 64 | after `DELETE /api/articles/{slug}/favorite`, the favourited-articles list has one member fewer (Conduit L4-FAVORITE-01; P12) |
| state preservation | C04 | frozen fields of one object are unchanged across an action and a fresh read | P20 | 320 | `POST /transactions` leaves `$.user.email` of `GET /checkAuth` unchanged (RWA L2-PAYMENT-01; P20) |
| repeated operation (idempotent / rejected / accumulating) | C05 | executing the same write twice yields equal, rejected or accumulated results | repeat_equal (P20 projection), repeat_rejected (P20 + optional P02 rejection), repeat_delta (P06) | 0 | no retained test; symbolic examples `repeat_equal`, `repeat_rejected`, `repeat_delta` in `src/ui_semantics/templates/effect_contract_v2.txt` |
| rejected request | C06 | a request that must be rejected, optionally with unchanged state | P02 (status or body rule), P20 (preservation around the rejection) | 6 | re-posting `POST /api/articles` with an existing title is rejected with status 422 (Conduit L1-ARTICLE-03; P02, rejection check) |
| equivalent query | C07 | two queries with equivalent inputs return equal results | P17 (equal; set / multiset / sequence) | 90 (+5 incorrect) | two `GET /api/articles/feed` reads with equivalent query inputs return the same multiset of articles (Conduit L3-ARTICLE-01; P17 equal, query-relation check) |
| query filtering | C08 | a refined or expanded query returns a subset or superset | P17 (subset/superset) | 85 | the result set of `GET /users/search?q=…` is a subset (by `id`) of `GET /users` (RWA L1-DETAIL-01; P17 subset) |
| ordering and member preservation | C09 | ordered follow-up queries preserve order and member multiset | P16 | 0 | no retained test |
| pagination / partition | C10 | pages partition the source result without duplicates | P15, P18 (complete_union / pairwise_disjoint / partition_difference) | 0 | no retained test |
| cross-user propagation | C11 | one actor's operation is observed by another actor | P01, P02, P12, P13, P14 (actor_before / actor_after roles) | 26 | after A's `PUT /api/user`, B's `GET /api/profiles/{username}` returns the updated field (Conduit L2-SETTINGS-01; P02, user/session relation check) |
| cross-user visibility / permission | C12 | isolation from another actor's operation, or a non-owner rejection | P01 (absent), P02 (status), P13 (not_contains), P20 | 6 | after A creates a bank account, B's `listBankAccount` does not contain it (RWA L3-BANK-01; P13 not_contains, user/session relation check) |
| field computation and aggregation | C14 | arithmetic or aggregation over one or several independent reads | P08 (add/subtract/multiply/divide/linear_delta), P19 (count/sum/min/max) | 49 | `GET /api/articles` returns `articlesCount` equal to the number of members of `articles` (Conduit L1-AUTH-02; P19 count, single-response check) |
| single-response constraint | single_state_constraint | a constraint inside one read (presence, type, range, count, format, uniqueness, string, arithmetic, aggregation, quantified member rule) | P01, P02, P03, P08, P09, P10, P11, P13, P15, P19, P21, forall | 93 business-level (+1,113 structural) | business-level: every member of `GET /users/search?q=…` has `username` equal to the query parameter `q` (RWA L1-TXN-01; forall over P02); structural: `count($.articles) <= query.limit` (Conduit L1-AUTH-01; P11) |
| inverse-operation restoration | inverse_restoration | a write followed by its inverse restores the frozen state | P20 | 6 | favourite then unfavourite restores the article list to its before state (Conduit L4-FAVORITE-01; P20) |
| read-only preservation | read_preservation | a read-only action leaves the state unchanged | P20 | 31 | opening the home page (`GET /`) leaves the `GET /notifications` results unchanged (RWA L4-REQUEST-NOTIFY-01; P20) |
| actor self-exclusion | self_exclusion | an actor does not observe an effect addressed to others | P01, P02, P13 (not_contains) | 0 | no retained test |

`forall` (a quantified single-response rule whose body is one P01/P21/P02/P03/P09/P10/P11/P15 predicate over each member) and the three C05 repeat forms (which wrap a P20 or P06 predicate) are composite forms of the families below; they are not counted as separate families. A `time_requirement` may additionally be attached to a P01/P02/P13 point proposition under C01, C02, C03, C11, C12 or self_exclusion (validation plan V8; no retained test).

## Predicate families (20)
Canonical JSON forms of every family are in `src/ui_semantics/templates/effect_contract_v2.txt` (lines `P01:` … `P21:`); the JSON schemas are under `contracts/`. Examples name the input sequence of a test in the final test set (correct business-level test unless marked *structural*).

| Family | Identifier | Meaning | Example from the final test set |
|---|---|---|---|
| presence / absence | P01 | a field or point resource exists (or is absent, with declared absence statuses) in a read | after `POST /likes/{id}`, `GET /transactions/{id}` still returns the transaction object (RWA L3-LIKE-01; C01) |
| typed value comparison | P02 | a value at a path equals / differs from / is ordered against another value (role, request or frozen hypothesis) with strict JSON or numeric comparison | `GET /api/user` returns the `username` submitted in `POST /api/users` (Conduit L1-AUTH-01; C02) |
| range / finite enumeration | P03 | a value lies in a closed range or in a finite set | `$.pageData.limit` of `GET /transactions` lies within [1, 100] (RWA L1-FEED-04; *structural*) |
| boolean toggle / from-to state pair | P04 | a field changes from a stated value to another across the write (the from-value is an applicability check) | deleting a bank account changes its `isDeleted` in `listBankAccount` from false to true (RWA L1-BANK-03; C02) |
| exact numeric delta | P06 | after − before equals a signed constant, a request value or a response value (exact arithmetic) | after `POST /transactions`, the payer's `balance` decreases by exactly the transaction amount (RWA L2-PAYMENT-01; C02) |
| numeric direction | P07 | after is strictly / weakly greater or smaller than before | after a payment the balance is strictly lower than before (RWA L2-PAYMENT-01; C02) |
| field arithmetic | P08 | output = left (add / subtract / multiply / divide) right over fields of one response, or a linear combination of resource deltas | no retained test; form in the template: e.g. `total = quantity × unit_price` within one response |
| string contains / prefix / suffix | P09 | a string field contains, starts with or ends with another string (case-sensitive) | no retained test |
| format | P10 | a string matches `YYYY-MM-DD` or a frozen restricted pattern | no retained test |
| count / length (including count ≤ query limit) | P11 | the count of an array or the length of a string compared with an integer operand; the original form compares the array count with this request's `limit` | `count($.articles) <= query.limit` for `GET /api/articles` (Conduit L1-AUTH-02; *structural*) |
| collection count change | P12 | the count of an array changes by a signed integer between before and after | `listBankAccount` has one more member after `createBankAccount` (RWA L2-ONBOARD-01; C01) |
| member containment | P13 | a collection contains / does not contain a member identified by a scalar or an identity tuple | after A updates its profile, B's `GET /users` contains the member with the updated field (RWA L4-SETTINGS-SEARCH-01; C11) |
| member added / removed | P14 | a member (identified by an identity tuple) is present after but not before, or vice versa | the transaction returned by `POST /transactions` appears in `GET /transactions` results, by `id` (RWA L1-DETAIL-02; C01, two-arm control) |
| uniqueness | P15 | members of an array are unique under an identity tuple | members of `GET /api/tags` are unique (Conduit L1-FEED-02; *structural*) |
| ordering and member preservation | P16 | a follow-up query preserves the order (by key and direction) and the member multiset of the source query | no retained test |
| collection equality / subset | P17 | one collection equals / is a subset or superset of another under a set, multiset or sequence representation and a comparison basis | `GET /users/search?q=…` results are a subset (by `id`) of `GET /users` (RWA L1-DETAIL-01; C08) |
| partition relation | P18 | pages form a complete union of / are pairwise disjoint within / differ by a partition of the source result | no retained test |
| aggregation | P19 | a value equals count / sum / min / max over a collection of the same or another response | `articlesCount` equals the number of members of `articles` in `GET /api/articles` (Conduit L1-AUTH-02; C14) |
| state projection comparison | P20 | a frozen field or a projection of one object is equal before and after | `$.user.email` of `GET /checkAuth` is unchanged across `POST /transactions` (RWA L2-PAYMENT-01; C04) |
| JSON type | P21 | a value has the stated JSON type | `$.tags` of `GET /api/tags` is an array (Conduit L1-AUTH-06; *structural*) |

Composite forms: `forall` applies one of P01/P21/P02/P03/P09/P10/P11/P15 to every member of an array (business-level example: every member of `GET /users/search?q=…` has `username` equal to the query parameter `q`, RWA L1-TXN-01); `repeat_equal`, `repeat_rejected` and `repeat_delta` (C05) wrap a P20 or P06 predicate around two executions of the same write.

## Validation plans (9) with examples from the final test set
| Plan | What it executes | Typical relation kinds | Example (input sequence) |
|---|---|---|---|
| V1 two-arm control | two independent initializations; the treatment arm executes the checked write, the control arm does not; the before/after difference of the observation is compared across arms; a change in the control arm or a baseline mismatch fails | create/appear, written-value propagation, delete/disappear, cross-user propagation | after `PATCH /users/{id}` the `lastName` returned by `GET /checkAuth` equals the submitted value; the control arm's two reads agree (RWA L2-SETTINGS-01) |
| V2 single-response check | constraints inside one read: presence, JSON type, count vs `limit`, format, field arithmetic, aggregation | single-response constraint, field computation | every transaction returned by `GET /transactions/contacts?amountMin=…&amountMax=…` has `amount` within the requested range (RWA L1-FEED-05) |
| V3 query-relation check | relations between a source query and derived queries: equivalent inputs, refinement/expansion, ordering, pagination | equivalent query, query filtering, ordering, pagination | the result set of `GET /users/search?q=…` (by id) is a subset of `GET /users` (RWA L1-SEARCH-01) |
| V4 workflow check | before read, write, after read in one actor's session; includes inverse restoration and read-only preservation | create/appear, written-value propagation, delete/disappear, state preservation, cross-user kinds when the observer is the same session | accepting a request (`PATCH /transactions/{id}`) changes `requestStatus` from `pending` to `accepted` (RWA L4-REQUEST-NOTIFY-01); liking a transaction leaves its frozen fields unchanged (RWA L1-DETAIL-02) |
| V5 repeated-operation check | the same write once and twice; equal, rejected or accumulated | repeated operation | no retained test on any of the five subjects |
| V6 rejection check | send a request that must be rejected; judge by status class or predicate; optionally check unchanged state | rejected request, cross-user visibility/permission | re-posting `POST /api/articles` with an existing title returns 422 and the existing article is unchanged (Conduit L1-ARTICLE-03) |
| V7 user/session relation check | multi-user, multi-session execution; verifies identity and session topology by an authenticated probe before evaluating the cross-user relation | cross-user propagation, cross-user visibility, state preservation, actor self-exclusion | after user B comments on A's article, A's comment list has one more member (Conduit L4-COMMENT-01); after B unfavorites, A still sees the article (Conduit L3-SOCIAL-02) |
| V8 time-requirement check | fixed sampling of server-timestamped evidence | relations with a time requirement | one retained test in the RWA Flat ablation suite; none in any Full suite |
| V9 multi-response relation check | arithmetic or aggregation across two or more independent reads | field computation across responses | no retained test on Conduit or RWA; 11 correct instances on Paperless-ngx (aggregation over the document list and the tag counts) |

Retained business-level tests per plan in the final test set (instances labelled correct): Conduit V2 102 / V3 76 / V4 117 / V6 6 / V7 21; RWA V1 11 / V2 40 / V3 99 / V4 559 / V7 11; Umami V2 44 / V4 66; Paperless-ngx V2 290 / V3 59 / V4 74 / V6 10 / V9 11; Ghost V2 25 / V3 563 / V4 8. The same breakdown for the ablation suites is in `docs/ABLATION-RESULTS.md`; the relations that connect a write to its effects are the instances outside V2 and V3.

## Plan dispatch
Every role shape that matches the candidate produces one plan; candidates with the roles before/write/after that claim a workflow effect keep only workflow plans; plans, relation and predicate combinations the executor does not support are removed; duplicates collapse. Exactly one plan must remain; zero or more than one rejects the candidate at admission with a diagnostic. A candidate with a time requirement is always executed by V8. Cross-user candidates are executed by V7 only when the recorded identity probe proves that operator and observer are different principals; V4 requires before read, write and after read from one actor and session; V1 requires an observation request that uses no value created by the write, so that the control arm can issue the same observation without the write.

## Completion calls (M10) in the final test set
Conduit: 5 of 59 write centres had no admitted candidate after the three rounds; completion calls on 3 inputs produced 13 proposals, 0 admitted. RWA: 26 of 89; completion calls on 14 inputs produced 25 proposals, 1 admitted. The corresponding counts for Umami, Paperless-ngx and Ghost are in the `counters` section of their run manifests.

## Bounded rules and their current values
| Rule | Value |
|---|---|
| attribution window | from action start to action end plus a 500 ms settle, extended by page/network quiet waits; requests outside every window are kept as unassigned |
| values excluded from data-flow matching | booleans, all numbers, strings of two characters or fewer, pure-integer strings, enumeration words (identity-like fields flowing into paths or query parameters are exempt) |
| comparable reads | same actor, session, operation template, query and body hash; adjacent pairs only; path parameters are not part of the key |
| summary screening batch | at most 24 evidence cards (96 KiB rendered) per call |
| detail proposal view | at most 48 requests or 240 KiB per call; larger views are split by request group |
| generation | 3 rounds per input, union with canonical dedup; one completion call per uncovered write centre; network retries up to 3 |
| stabilization wait | poll every 100 ms; stable after three consecutive identical observations (status and body); at least 500 ms, at most 2 s; timeout is classified not-evaluable; the same policy is used by validation, calibration and the exported tests |
| runtime rebinding | every request position to be bound needs exactly one source (the unique earlier response position that created the value); one source may feed several positions |

## Two mechanisms that are inactive in every reported run

The shipped code contains two mechanisms that no reported run used. They are documented here so that a reviewer who reads the source is not misled about what produced the results.

1. **Declared read-semantic endpoints.** An application profile may declare request routes that are reads although their method is not `GET` (`read_semantic_endpoints` in `contracts/app_profile.schema.json`). A declared request is not counted as a write when M2 chooses the anchor of a UI action, is marked `declared_read_semantic: true` in the trace (`contracts/ui_trace.schema.json`), does not enter the producer set in M3, and is treated as read-only by the proposer, by M11b and by the runtime observer checks. The motivating case is Ghost's admin interface, which issues `POST /ghost/api/admin/stats/posts-member-counts/` — a read expressed as a POST — inside the same operation window as a write, which makes the anchor ambiguous. **No profile of any reported run declares such endpoints.** The shipped fixture `fixtures/profiles/ghost_modular_local.json` is the current one and does declare the endpoint; the version the reported Ghost run used is shipped as `fixtures/profiles/ghost_modular_local.paper-run.json`, and every case carries its own frozen copy in `…/union/inputs/subject/profile.json`.
2. **Location header shadowed by the response body.** In the value-flow extraction of stage 4, a path segment of a `Location` response header is no longer registered as an identifier source when the same scalar already appears as a scalar in that response's body; segments absent from the body are registered as before. **The reported runs predate this rule** (the run manifests' `environment.git_head` is earlier than the commit that added it), and a rebuild of M1–M9 over the 83 frozen Conduit and RWA cases before and after the change produced byte-identical artifacts, so it changes nothing that this package reports.

`docs/RUN-NOTES.md` records when the two mechanisms were added and what was measured with them.
