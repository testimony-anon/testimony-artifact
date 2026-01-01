# Fault catalogue specification for the added subjects (RQ2-lite, 2026-09-21)

Scope: a reduced fault-detection experiment (RQ2) on Umami 3.4.0, Paperless-ngx 3.2.0 and Ghost 5.130.6, run by a
generic, data-driven runner (scripts/experiments/rq2_subjects/). Faults are designed from the applications' feature
descriptions, source code and the recorded UI sequences (the input side) and are FIXED BEFORE any execution; nobody
designing a fault may read the generated tests or assertions (never open */M14/*, */pytest-export*/*, rq1-audit-*/tests*.jsonl,
business_test_catalog.json). Paper protocol (Section IV-F): a *source fault* modifies one piece of business logic
(missing state update or side effect, wrong quantity or amount, wrong object or user, wrong deletion or duplicate
handling, wrong query condition) and keeps responses shape- and type-preserving (the request still succeeds, the
business effect is wrong; no 5xx by design); a *response fault* applies a fixed, shape- and type-preserving
transformation, where the client receives it, to every response that meets a predefined condition.

## Files

* `eval/ui_semantics/rq2-subjects-20260921/inputs/faults-<subject>.jsonl` — one JSON object per line (rows below).
* `eval/ui_semantics/rq2-subjects-20260921/patches/<fault_id>/<basename>` — the complete patched file (mounted read-only
  over `container_path`), plus `patches/<fault_id>.patch` — unified diff original -> patched (`diff -u`).
* `the authors' per-subject fault design notes (summarised in docs/FAULT-CATALOGUE.md)` — the design note (Chinese or English): per
  fault the module, the business rule, the single modification, why a user of the UI would notice, and the routes.

## Source fault row (Paperless-ngx and Ghost only)

```json
{"fault_id": "B-P01", "subject": "paperless", "kind": "source", "status": "included",
 "module": "documents", "business_rule": "one sentence: the rule the application must uphold",
 "description": "one sentence: the single local modification",
 "routes": [["POST", "/api/documents/bulk_edit/?"]],
 "patch": {"container_path": "/usr/src/paperless/src/documents/bulk_edit.py",
           "patched_file": "eval/ui_semantics/rq2-subjects-20260921/patches/B-P01/bulk_edit.py",
           "diff": "eval/ui_semantics/rq2-subjects-20260921/patches/B-P01.patch",
           "original_sha256": "<sha256 of the original file taken from the pinned image>"},
 "observable_effect": "one sentence: what a correct business assertion would observe (design note only)"}
```

* `routes`: `[method, path_regex]` pairs; `path_regex` is a Python `re.fullmatch` on the canonical request path with the
  trailing slash stripped (so write `/api/tags/?` or `/api/tags` interchangeably). Tests are paired with the fault when
  any request of their frozen blueprint matches one of the routes. List every route whose behaviour the modification
  changes (the write itself and, when the modification changes what a read returns, that read).
* Fault ids: `B-P01..` (Paperless source), `B-G01..` (Ghost source); response faults `PR-U01..`, `PR-P01..`, `PR-G01..`.
* The patched file must be the whole file as it exists in the pinned image (`docker run --rm --entrypoint cat <image@digest> <path>`),
  with exactly one local change; verify it compiles (`python3 -m py_compile` with the image's interpreter, or `node --check`
  with the image's node) using a throwaway container WITHOUT published ports (never touch the running instances on
  127.0.0.1:18090 / 18091 / 18093 and never start containers named uisemtest-*).

Images (pinned):
* Paperless: `ghcr.io/paperless-ngx/paperless-ngx@sha256:22dc423ff48ac1629977dbf0c9625ba9f60d3bd1291a2ff173c65351984a14c2`, Django code at `/usr/src/paperless/src/` (apps `documents`, `paperless`); runs as user paperless.
* Ghost: `ghost@sha256:a0506f3f05f5bdc6c950c5113cdcdb1e1f96fbf15f6dc0a39fc093c25348bdb5` (5.130.6-alpine), server code at
  `/var/lib/ghost/versions/5.130.6/core/server/` (plain JavaScript, no build step; the same files as `ghost/core/core/server/`
  of the local checkout `<SUBJECTS>/ghost` at tag v5.130.6 — confirm by diffing the file taken from the image).

## Response fault row (all three subjects)

```json
{"fault_id": "PR-U01", "subject": "umami", "kind": "response", "status": "included",
 "module": "websites", "business_rule": "…", "description": "…",
 "reads": [["GET", "/api/websites/[^/]+"]],
 "writes": [{"method": "POST", "path": "/api/websites", "role": "create", "id_path": "$.id"}],
 "operator": "rewrite_string",
 "target": {"field": "name", "scope": "created", "id_field": "id"},
 "substates": ["create"],
 "observable_effect": "…"}
```

* `reads`: `[method_regex, path_regex]` pairs — successful (2xx) responses of these requests are transformed.
* `writes`: the trigger writes of the current reset epoch that scope the transformation and that a test's normal plan must
  contain for the pairing to be kept (`role` create | update | delete; for `create` the new id is read from the write
  response at `id_path` (JSONPath-lite: `$.id`, `$.posts[0].id`, `$.data.id`); for update/delete the id is the last
  non-empty segment of the write path unless `id_path` is given). `[]` for stateless operators.
* `operator` and `target` — exactly one of the seven operators of the generic engine:
  1. `rewrite_string` `{field, scope}` — append the fixed text ` [RQ2]` to the string field of every matching object.
  2. `add_one_number` `{field, scope}` — integer/decimal field + 1.
  3. `flip_boolean` `{field, scope}`.
  4. `old_value_after_update` `{field, id_field}` — for objects whose id was targeted by an update write of this epoch,
     return the value of `field` last observed BEFORE that write when it differs from the current value.
  5. `omit_created_member` `{list_path, id_field}` — remove from the list at `list_path` (`$` = root array, `$.results`,
     `$.data`, `$.posts`, …) every member whose `id_field` is an id created in this epoch.
  6. `reinsert_deleted_member` `{list_path, id_field}` — re-insert into the list the last observed object whose
     `id_field` equals an id deleted in this epoch.
  7. `stale_count` `{field}` — replace the numeric field by the value observed in the previous successful response of the
     same route and query by the same actor in this epoch (only when it differs).
  `scope`: `all` (every object of the response carrying the field), `created` (objects whose `id_field` is an id created
  in this epoch), `updated` (objects targeted by an update write of this epoch). Objects are searched recursively.
* `substates`: names reported per activation branch (one per write role is enough).
* Mutations must keep HTTP status, JSON shape and field types; numeric perturbation is the fixed +1, strings the fixed
  suffix; never read an assertion's expected value.

## What to base the design on (allowed inputs)

* Recorded write routes per subject: `eval/ui_semantics/rq2-subjects-20260921/inputs/routes-<subject>.json` (method, canonical
  path, cases). The recorded sequences: `fixtures/recording_workflows/<subject>_modular/` (inventory.json: modules and
  case ids; one workflow JSON per case with the UI steps) and their recordings `eval/ui_semantics/<subject>-20260921/recordings-01/cases/<case>/`
  (frozen traces with request/response bodies live under `eval/ui_semantics/<subject>-20260921/<subject>/<run>/cases/<case>/union/M01_09/`;
  runs: umami full-01, paperless m11fix-03, ghost full-01) — use them only to learn routes, payloads and response shapes.
* Feature descriptions: `docs/design/subjects-expansion-20260919/` (survey and onboarding notes per subject), the profiles
  `fixtures/profiles/<subject>_modular_local.json`, the application source (image / checkout) and upstream API docs.
* The Conduit/RWA catalogues as style references: `docs/design/cpv-expansion/rq2-source-faults-20260907.md`,
  `rq2-response-mutations-20260907.md`, `eval/ui_semantics/rq2-20260907/patches/*.patch`.

## Addendum (2026-09-21, after registration): read/query-behaviour faults and two more operators

Registration of the Ghost catalogue showed that the generated Ghost tests contain almost no writes (739 qualified tests:
563 read–read query relations, 176 single-response checks; the only writes are 7 `POST /ghost/api/admin/members/` and the
settings PUT), so write-oriented faults have no eligible tests. Faults may therefore also target the read/query rules the
recorded UI reads exercise (GET posts/newsletters/snippets/... with `filter`, `limit`, `order`, `fields`, `formats`, `include`,
`page`, `status`), designed from the recordings and the source code, and fixed before any fault execution. Ids continue
the sequence (B-G04.., PR-G04..). The original faults stay in the catalogue denominator. Two more engine operators:

8. `omit_first_member` `{list_path, id_field, when_query_key?, when_query_value?}` — remove from the list at `list_path` the member
   with the lexicographically smallest `id_field`, only for reads whose query string contains `when_query_key`
   (and, if given, that key equals `when_query_value`); reads without the key are untouched (so two otherwise equivalent
   reads diverge).
9. `drop_last_member` `{list_path, when_query_key?}` — remove the last member of the list for reads whose query contains
   the key (e.g. `limit`): the list keeps its shape and stays within the limit.
`rewrite_string` / `add_one_number` / `flip_boolean` also accept `when_query_key` / `when_query_value` in `target` to
restrict the mutation to reads carrying that query parameter.
