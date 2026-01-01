# Ghost subject deployment (`subject_id: ghost`)

Single container, SQLite, `NODE_ENV=development`, published on `127.0.0.1:18093`.
Lifecycle is expressed entirely through the generic adapter
`src/subject_adapters/docker_single_local.py`; there is no
`src/subject_adapters/ghost_local.py`.

## 1. Pinned version

| item | value |
|---|---|
| image | `ghost@sha256:a0506f3f05f5bdc6c950c5113cdcdb1e1f96fbf15f6dc0a39fc093c25348bdb5` |
| image tag pulled | `ghost:5-alpine` (documented in the adapter as `5.130.6-alpine`) |
| Ghost version in the image | `GHOST_VERSION=5.130.6` (`docker image inspect … .Config.Env`); the Admin API reports `"version":"5.130"` |
| upstream tag | `v5.130.6` = commit `a07c753c8a08c38d264b429b2a19873b152c097a` (2026-01-08) |
| official test corpus | `<SUBJECTS>/ghost` checked out at `v5.130.6` (sparse, read-only) |

`docker_single_local` always addresses the image as `repository@digest`; the tag
is documentation only.

**Deviation from the survey (`the authors' subject-survey report`)**: the survey measured the
top-level `e2e/tests/**` suite of the default branch at `8e2eb8abfccd`
(327→337 cases).  That is not a release tag, and at `v5.130.6` the top-level
`e2e/` directory contains one single test.  The official Playwright suite that
ships **with this version** is `ghost/core/test/e2e-browser/**/*.spec.js`:
19 spec files, 74 tests, 203 assertions (2.74 per test, 52.7% after the last
action, 39.2% of tests with a mid-test assertion), measured with
`scripts/experiments/subject_survey/cypress_assertion_stats.py --framework playwright`.

## 2. Commands

```bash
set -a; . ./.env; set +a

# one-shot preparation of $UISEMTEST_GHOST_RUNTIME_ROOT (runtime.materialize_commands)
bash deploy/ghost/materialize.sh

# start + seed + block (what runtime.server_commands does)
.venv/bin/python -m subject_adapters.docker_single_local supervise \
    --adapter fixtures/adapters/ghost_current_local.json

# data-only reset (what profile.reset.command does)
.venv/bin/python -m subject_adapters.docker_single_local reset \
    --adapter fixtures/adapters/ghost_current_local.json --output /tmp/unused.json

.venv/bin/python -m subject_adapters.docker_single_local readiness \
    --adapter fixtures/adapters/ghost_current_local.json
```

`supervise` is long-lived and, on this machine, long-lived supervisors are
reaped mid-suite (`the authors' onboarding notes of a candidate subject that was not used` §C.4 round 3).  For recording, hand the
container to the Docker daemon from a short-lived process that calls
`docker_single_local._start_container(spec)` and tear it down later with
`_teardown(spec)`.

## 3. Configuration and why

| container env | why |
|---|---|
| `NODE_ENV=development` | task book requirement; selects the SQLite defaults |
| `url=http://127.0.0.1:18093` | drives the admin URL, the session origin check and the public site |
| `database__client=sqlite3`, `database__connection__filename=/var/lib/ghost/content/data/ghost.db`, `database__useNullAsDefault=true` | one file inside the bind mount; `PRAGMA journal_mode` is `delete`, so a stopped server leaves a single self-contained file (no `-wal`/`-shm`) |
| `mail__transport=stub` | `@tryghost/nodemailer` maps this to `nodemailer-stub-transport`, which is bundled in the image and always succeeds. Without it `POST /ghost/api/admin/invites/` returns 500 (`Failed to send email`) even though it has already written the invite row, and the sign-in flow below cannot be repeated at all |
| `security__staffDeviceVerification=false` | `session/index.js: isStaffDeviceVerificationDisabled()` returns `config.get('security:staffDeviceVerification') !== true`. Without it **only the first sign-in of each user succeeds**: `api/endpoints/session.js` sets `skipVerification` only when the user has never logged in, and every later sign-in tries to mail a 6-digit code (`middleware.js: createSession`) |
| `updateCheck=false` | no outbound update ping |
| `logging__level=error` | keeps `content/logs` empty |

## 4. Two accounts

* `actor_a` — the installation **owner**, created by
  `POST /ghost/api/admin/authentication/setup/` (user id is the fixed string `"1"`).
* `actor_b` — a staff account (`UISEMTEST_GHOST_ACTOR_B_ROLE`, **`Author`** since the
  coordinator's 2026-09-21 decision; id is a 24-hex ObjectID).  The Author role is
  deliberate: it cannot edit another user's post, cannot list members, cannot edit
  settings and cannot create pages, and its admin navigation carries neither Tags
  nor Members nor Settings, so cross-user sequences produce real permission rules.  Ghost only ever mails the
  invitation token, so `seed.sh` creates the invite through
  `POST /ghost/api/admin/invites/`, reads `invites.token` straight out of the
  instance's own SQLite file, and redeems it with
  `POST /ghost/api/admin/authentication/invitation/`.  No mailbox is involved;
  this replaces the `InvitationTokenProvider` of Ghost's own
  `staff-account-factory.ts`.

Credentials live only in the repository `.env` (`UISEMTEST_GHOST_*`); the seed
script builds every request body with `python3` from the environment, so no
password ever appears on a command line.

## 5. Reset

`reset.sh` = `docker kill` → `rsync -a --delete golden/ content/` → `docker start`
(with the retry loop the Vikunja run needed, `docs/RUN-NOTES.md` §5) →
wait for `GET /ghost/api/admin/site/`.

Measured through the exact argv and environment of the replay runtime
(`LocalHttpCurrentTargetRuntime._reset_env()`), 10 consecutive resets with a
write in between each:

| | seconds |
|---|---|
| min | 2.022 |
| median | **2.047** |
| max | 2.093 |
| mean | 2.048 |

Other measured timings: first `docker run` incl. migrations 4.1 s; `supervise`
start + full seed 7.0 s; restart on an existing database 1.8 s.

**Determinism.** After a reset, `sqlite3 .dump` of the restored database is
identical to the golden dump (verified by diffing the two dumps: no lines).
At the API level, over two rounds of `[reset → sign both actors in → read 12
endpoints → write]`: 5/12 byte-identical, 11/12 identical after blanking
`last_seen`/`updated_at`.  The differences are **not** reset non-determinism:

1. Ghost updates the staff user's `last_seen`/`updated_at` on every session
   creation, and the admin `posts`/`pages`/`users` payloads embed the author
   record.  Each round signs in, so the value moves.
2. `GET /` (the public site) carries a per-boot asset cache-buster
   (`?v=<10 hex>`): in development `frontend/meta/asset-url.js` derives it from
   `Date.now()` on first use and `theme-engine/active.js` clears it on boot.
   Document bodies are not captured by the recorder, so this never enters a trace.

## 6. Known facts worth carrying into the sequence design

* **The admin makes no polling/heartbeat requests.** 45 s idle on `#/posts` =
  0 requests.  Nothing to declare as `session_maintenance`.
* A full admin shell load costs ~15 XHR/fetch, among them
  `GET https://ghost.org/changelog.json` (external, hard-coded in the admin
  bundle) and `POST /ghost/api/admin/stats/posts-member-counts/` (a read
  expressed as a POST, i.e. a false producer).  Both are issued during the
  **bootstrap** navigation, which happens before the recording session is
  activated, so neither lands in the session bundle — as long as workflows keep
  to a single `navigate` in the bootstrap.
* `data-test-*` attributes survive in the shipped production admin build
  (16 distinct attribute names live on the posts screen), unlike Vikunja's
  stripped `data-cy`.
* Entity ids are 24-hex ObjectIDs (posts, pages, tags, members, staff users);
  only the owner's user id is the string `"1"`.
