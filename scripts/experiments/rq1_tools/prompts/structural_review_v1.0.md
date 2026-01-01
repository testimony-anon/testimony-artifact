# Structural-constraint review, prompt structural-v1.0

You review one automatically generated API regression test for a web application. The test is a
**structural constraint** (assertion layer `basic_constraint`), not a business relation: the test
replays exactly the recorded input sequence (same users, same data, same request parameters, no
interleaved traffic), then issues **one** read request, and evaluates **one** constraint on that
single response. The `read` block of the packet gives that request (method, path, query, actor,
status) and `response_body_excerpt` is the body the endpoint actually returned in that scenario
(possibly truncated; secrets are redacted). `observed` restates, from the untruncated body, the
facts that the constraint talks about, so you can rely on it even where the excerpt is cut.

## What you must decide

Judge whether the asserted constraint is a **stable property of this endpoint's response in the
pinned version of this application, under the preconditions of the recorded sequence** (the same
authenticated user, the same operations, the same data). Do **not** judge whether the assertion
happened to pass: the recorded response satisfies it by construction, so "it held in this recording"
is never a reason on its own.

- **C** — the constraint is such a stable property. Typical grounds: the response serializer, the
  schema or the API specification makes the field always present or always of that JSON type; the
  collection is keyed by a primary key or is a group-by/aggregate whose grouping key is the identity;
  the framework's pagination makes the page size bounded by the requested limit; the value is a
  constant of the pinned version or is fixed by this very request. Use the application's source
  code, its OpenAPI/API documentation and framework semantics (Django REST Framework pagination and
  serializers, Prisma/Sequelize/Bookshelf models, Express/Next.js handlers, primary-key uniqueness,
  JSON:API-style `meta.pagination`). A property that is true but weaker than the real rule (a range
  wider than the implementation's, uniqueness over a collection that is unique for a stronger reason,
  `<=` where the implementation always returns exactly one value) is still **C**.
- **E** — you can name a clear counterexample in the pinned version under these same preconditions.
  Typical grounds: the field is legitimately absent or `null` in a valid state while the constraint
  asserts presence or a non-null JSON type; the identity of a uniqueness constraint is an ordinary
  attribute that two legitimate members may share (a status, a type, a name, a foreign key); a
  count/limit relation is written the wrong way round or compares quantities that are not related
  (a page's length against a total that is not a page bound); the frozen literal being compared is
  not determined by the sequence but is an auto-generated identifier, a timestamp, a clock-dependent
  counter, or a value another part of the same sequence changes. Also **E** when the constraint only
  holds *because this particular recording happened to look like that* and would not hold generally
  under the same preconditions.
- **U** — the packet and your knowledge of this application are not enough to decide.

Do **not** label E only because the constraint would fail under a **different** request, a
**different** data volume, a different pagination window, or concurrent traffic that the recorded
sequence does not contain: a result set that fits in one page, or a list whose single member makes
a uniqueness rule trivial, is still evaluated as the rule for this endpoint under these
preconditions. Conversely, do not label C for a rule that is simply an accident of the recorded
values with no serializer, schema or framework reason behind it.

## How to read `predicate`

`predicate.family` names the constraint form; `role: "observation"` means "in the body of the read
shown in `read`", `role: "observation_request"` means "in that same request".

- `P01` presence/absence of a field or point resource at `target.path` (`operator: present` or
  `absent`, with the declared `absent_statuses`).
- `P02` a typed comparison of the value at `left.path` with `right`: a frozen hypothesis literal
  (`right.source == "hypothesis"`, field `value`), a value of this request (`source == "request"`)
  or another value of the same response (`source == "role"`, field `ref`). `operator` is `eq`,
  `numeric_eq`, `le`, `ge`, ….
- `P03` the value at `target.path` lies in the closed range `[lower.value, upper.value]` (or in a
  finite `domain`).
- `P10` the string at `target.path` matches a format (`date_yyyy_mm_dd`) or a frozen pattern.
- `P11` the count of the array (or the length of the string) at `collection.path` compared with
  `right`: this request's query parameter (`right.source == "request"`, `ref.location == "query"`),
  another field of the same response (`source == "role"`), or a frozen integer
  (`source == "hypothesis"`). `operator` is `le`, `ge` or `eq`.
- `P13` the collection at `collection.path` contains (or does not contain) the member named by
  `member` — a frozen scalar, or a member matched by an identity tuple.
- `P15` the members of the array at `collection.path` are unique under the identity tuple
  `identity.paths` (`strict-tuple` = strict JSON equality of the listed projections; `$` means the
  whole member). `scope: "actual_response"` = over the members this response actually returned.
- `P21` the value at `target.path` has JSON type `expected_type`.
- `forall` applies the single predicate in `body` to every member of the array at `collection.path`
  (`role: "item"` paths are relative to the member, `$` being the member itself); `item_guard`, when
  present, restricts the members it ranges over.

`observed` gives, for the paths the predicate mentions, whether the path resolves, the JSON type
found, a preview of the value, the size of the collection, the number of distinct identity values,
a preview of the identity values, and — for `P11` against the request — the value of the query
parameter. `observed.note` flags anything unusual.

A captured value that the recorder treats as sensitive is stored in the body as the sentinel object
`{"$route_s_redacted": {"category": …, "original_json_type": …}}`. `observed` reports its *original*
JSON type and marks the entry `"redacted": true`. A redacted value is neither evidence of a
different JSON type nor evidence that the field is missing; judge it by its original type.

Request query parameters are given as the strings they were sent as, so a numeric `limit` appears as
`"3"`; that is the transport form, not a type violation.

## Answer format

Answer **strictly** as JSON and nothing else:

{"label": "C"|"E"|"U", "reason": "<one or two sentences naming the concrete ground: the serializer,
schema, framework rule or source-code fact that makes it stable, or the concrete counterexample>"}
