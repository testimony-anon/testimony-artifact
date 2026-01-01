# Paperless-ngx deployment for uisemtest (subject id `paperless`)

Phase A deliverable of `the authors' Paperless-ngx onboarding brief`.
Progress and measurements: `the authors' Paperless-ngx onboarding notes`.

## 1. What runs

| Role | Image (pinned by digest) | Ports | Managed by |
|---|---|---|---|
| application | `ghcr.io/paperless-ngx/paperless-ngx@sha256:22dc423ff48ac1629977dbf0c9625ba9f60d3bd1291a2ff173c65351984a14c2` (version **3.2.0**, upstream `54e332d25943`) | `127.0.0.1:18091 -> 8000` | `subject_adapters.docker_single_local` via `fixtures/adapters/paperless_current_local.json` |
| database | `postgres@sha256:f02121de6f74d30d8a94cd1d9584125e2178d7e6c377d8130112d4e52d867995` (`postgres:17-alpine`, server 17.11) | **none** | `deploy/paperless/stack.sh` |
| broker | `valkey/valkey@sha256:a0dbf4c1d5708782907c10e2c72deff317518518b5288a58416981d9db95d30b` (`valkey:9-alpine`, server 9.1.2) | **none** | `deploy/paperless/stack.sh` |

Container names are derived from the adapter's `instance_key_env`
(`UISEMTEST_PAPERLESS_OUTPUT_ROOT`), so different output roots never share a
stack: `uisemtest-paperless-<sha16>` plus `-pg` / `-valkey` sidecars.

### Why the sidecars talk over unix sockets

`docker_single_local.run_argv` publishes ports and mounts volumes but passes no
`--network`, so the application container always lands on the default bridge,
where container names do not resolve. Rather than take two more host ports, the
sidecars expose their sockets on **named volumes shared with the application**:

```
<app>-pgsock     postgres:/var/run/postgresql  <->  app:/var/run/postgresql
<app>-redissock  valkey:/var/run/redis         <->  app:/var/run/redis
```

and the application is configured with the two upstream-supported socket forms
`PAPERLESS_DBHOST=/var/run/postgresql` (`parse_db_settings`, psycopg socket dir)
and `PAPERLESS_REDIS=unix:///var/run/redis/redis.sock` (`parse_redis_url`, which
rewrites it to `redis+socket:` for celery). Neither sidecar publishes a port.

## 2. Start and stop

```bash
set -a; source .env; set +a
export UISEMTEST_DOCKER_SINGLE_ADAPTER="$UISEMTEST_REPO_ROOT/fixtures/adapters/paperless_current_local.json"
export PYTHONPATH="$UISEMTEST_REPO_ROOT/src"

bash deploy/paperless/stack.sh sidecars-up          # ~1.4 s
"$UISEMTEST_PYTHON" -m subject_adapters.docker_single_local supervise   # blocks
# ... SIGTERM tears the application container and its fresh volumes down ...
bash deploy/paperless/stack.sh down                 # also removes the sidecars
```

The pipeline does both steps by itself: `runtime.materialize_commands` runs
`stack.sh sidecars-up` and `runtime.server_commands` runs `supervise`.

`sidecars-up` rebuilds the cluster from scratch whenever the application
container is absent, and does nothing while it is running. The two lifetimes
must match: `supervise` drops the `fresh_on_reset` volumes (`data`, `media`,
`golden`) on teardown, so a surviving database would pair a seeded schema with
an empty media directory.

Readiness probe: `GET /accounts/login/ -> 200` (unauthenticated, no template
work beyond the login form, and it is the cheapest 200 the app serves).
`GET /api/ui_settings/ -> 401` is the second `runtime.health_probe`, and doubles
as the `unauthenticated_status` of both actors' identity probes.

## 3. Seed

`container/seed.sh` runs once per `supervise` (the generic adapter also calls it
after every reset, where it is a single `test -f` on `golden/.seeded`). It

1. replays `container/seed_database.py` — a port of upstream
   `src-ui/e2e/backend.py::seed_database()` at `54e332d25943` — through
   `manage.py shell`, as the `paperless` user;
2. waits for `documents_paperlesstask` to drain, then deletes those rows;
3. copies `media/documents` and `data/index` to `/usr/src/paperless/golden/`;
4. freezes the database as the template `paperless_golden`
   (`ALTER DATABASE ... ALLOW_CONNECTIONS false` + `pg_terminate_backend` +
   `CREATE DATABASE ..._golden TEMPLATE paperless`, then re-allow).

**Fidelity to the official fixture.** All 61 documents are created, with the
upstream titles, contents, checksums, filenames, original filenames, archive
serial numbers, created dates, owners, document types, correspondents and
storage paths, plus the 3 tags (`Inbox`, `Another Sample Tag`,
`TagWithPartial`), 2 correspondents, 1 document type, 1 storage path, 1 custom
field, 4 notes on document 1, the `Inbox` saved view with its filter rule, and
the admin's `UiSettings`. Known, deliberate differences from upstream:

| # | Upstream | Here | Why |
|---|---|---|---|
| 1 | both account credentials hard-coded in the fixture | read from `UISEMTEST_PAPERLESS_ACTOR_{A,B}_{USERNAME,PASSWORD}`, which must be set | no credential in a tracked file (task brief §0) |
| 2 | sample PDF from `src/documents/tests/samples/simple.pdf` | byte-identical copy at `container/simple.pdf` (sha256 `1093cf6e32adbd16b06969df09215d42c4a3a8938cc18b39455953f08d1ff2ab`) | the published image does not ship `documents/tests/` |
| 3 | in-process instance with `CELERY_TASK_ALWAYS_EAGER` | live container with one celery worker; the `PaperlessTask` rows the workers record during seeding are deleted | `/api/tasks/` must start empty like upstream |
| 4 | SQLite in a temp dir, dev server on `:8001`, Angular dev server on `:4200` | PostgreSQL + the published image on `127.0.0.1:18091` | the pipeline needs one origin and a pinned image |
| 5 | no `PAPERLESS_ADMIN_USER` | none either — actor A is the seeded superuser | avoids a second superuser that upstream's fixture does not have |

Document 1's `created` date is `timezone.localdate()`, exactly as upstream, so
the golden state depends on the day the stack is started (it is constant for the
lifetime of one stack, which is what determinism requires).

## 4. Reset (data only, application process never restarted)

`reset.strategy = run_script`, `location = container`, so one `docker exec` runs
`container/reset.sh`, which does three things and nothing else:

1. `DROP DATABASE paperless WITH (FORCE)` + `CREATE DATABASE paperless TEMPLATE paperless_golden`;
2. `media/documents` and `data/index` restored from the golden copies;
3. `FLUSHALL` on the broker — `SESSION_ENGINE` is `cached_db` and the Django
   cache lives in Redis, so it must not outlive the rows it mirrors.

Measured on this machine (10 consecutive resets, each preceded by real
mutations: new tag, new note, renamed document, deleted document, deleted tag):
see `the authors' Paperless-ngx onboarding notes` §2.

`UISEMTEST_PAPERLESS_RESET_SKIP_FILES=1` / `..._SKIP_CACHE=1` in the container's
environment isolate the cost of phases 2 and 3.

**`PAPERLESS_WEBSERVER_WORKERS=1` is a determinism requirement, not a tuning
knob.** `/api/ui_settings/` serves `user.get_all_permissions()`, a Python `set`,
so its 166 entries come out in per-process hash order; with the upstream default
of 2 gunicorn workers the same request alternates between two byte-different
bodies even with no reset at all. One worker makes the order stable for the
lifetime of the container.

## 5. Accounts

Two actors, both created by the seed, both declared in
`fixtures/profiles/paperless_modular_local.json`; usernames and passwords live
only in `.env`:

* `actor_a` — `UISEMTEST_PAPERLESS_ACTOR_A_*`, the seeded **superuser** (the
  upstream fixture's admin account).
* `actor_b` — `UISEMTEST_PAPERLESS_ACTOR_B_*`, a plain user with **no global
  permissions** (the upstream fixture's read-only account), which is exactly what
  `src-ui/e2e/permissions/global-permissions.spec.ts` assumes. The task brief's
  four extra permissions (`view_document` / `add_tag` / `change_tag` /
  `view_tag`) are **not** granted by the seed, because granting them would
  invalidate those 6 official cases; see the open question in the progress note.

## 6. Login

Paperless's UI login is a Django/allauth server-rendered form (full-page POST),
which the recorder cannot see, and the JSON login endpoint that does set a
session cookie — `POST /api/auth/headless/browser/v1/auth/login` — requires a
per-session CSRF token. The profile therefore declares the recorder's
`cookie_session.csrf` double-submit block:

```json
"csrf": {"cookie_name": "csrftoken", "header_name": "X-CSRFToken"}
```

Stage 0 primes the cookie by navigating to `base_url` (Django redirects to the
login page and sets `csrftoken` there), reads it out of the cookie jar and sends
it back as `X-CSRFToken`. Both actors then pass login and the
`GET /api/profile/` identity probe with distinct identities; the measurement is
in §9.8 of the progress note.

Actor B's degraded SPA is expected, not a defect: without `view_uisettings` the
`/api/ui_settings/` bootstrap returns 403, which is exactly what the official
`permissions/global-permissions.spec.ts` cases assert.

## 7. Files

```
deploy/paperless/
  README.md                     this file
  stack.sh                      sidecar lifecycle (sidecars-up/-down, down, status, name)
  container/reset.sh            in-container data-only reset
  container/seed.sh             in-container seed + golden snapshot
  container/seed_database.py    port of the upstream Playwright fixture
  container/simple.pdf          upstream sample PDF (sha256 1093cf6e…)
```

`container/` is bind-mounted read-only at `/opt/uisemtest` inside the
application container.
