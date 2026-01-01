# Installation

## Requirements
- macOS or Linux, Python 3.12, Node.js 22 (`yarn` classic for RWA), Docker (Conduit, Umami, Paperless-ngx, Ghost), Chrome/Chromium (installed by Playwright).
- ~20 GB free disk for the package with every data volume extracted; the model-call and evidence volumes are shipped as `tar.zst` archives (see `VOLUMES.md`) and must be extracted into this directory tree before level-2 commands. Each volume is independent — extract only the ones you need.

## Python environment (level 1 needs only this)
```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/playwright install chromium     # only for recording (level 3)
```
`scripts/uisemtest` expects `.venv/bin/python` in the package root.

## Subjects (level 2 and 3)

Every subject is reachable only on `127.0.0.1`, is reset from a frozen seed state before each validation run and holds no real data. Test accounts come from environment variables; `.env.example` lists the values used in the study.

**Conduit** (TonyMckes/conduit-realworld-example-app, commit 5e127d8): only Docker has to be running. The runtime starts, resets and stops the stack itself through `subject_adapters.conduit_local supervise` (docker compose project `uisemtest-conduit-<hash>` built from `deploy/conduit/`, app on `http://localhost:3001`, PostgreSQL on 5433); the first start builds the image (a few minutes). Do **not** start the compose file by hand — a manually started stack occupies the ports and the runtime's own project then fails to reset. Test accounts are registered at every reset from `UISEMTEST_CONDUIT_ACTOR_{A,B}_{USERNAME,EMAIL,PASSWORD}`.

**RWA** (cypress-io/cypress-realworld-app, commit bdf6169): clone the repository, `git checkout bdf6169`, `yarn install`, then point `UISEMTEST_RWA_CHECKOUT` at the checkout and set `UISEMTEST_RWA_ACTOR_{A,B}_USERNAME/PASSWORD` to two seeded users (defaults used in the study: `Heath93` and `Arvilla_Hegmann`, password `s3cret`). The runtime adapter starts the backend on port 14001 and the Vite dev server on 14000 and resets the seed through `/testData/seed`.

The next three subjects all run under the generic adapter `subject_adapters.docker_single_local`, which supervises one container per subject; their image digests are pinned in `fixtures/adapters/<subject>_current_local.json` and are pulled on the first start.

**Umami 3.4.0** (`ghcr.io/umami-software/umami`, tag `postgresql-latest`): two layers. Start the PostgreSQL data layer **first**, once per machine:
```bash
set -a; source .env; set +a
bash deploy/umami/db_up.sh
```
The database publishes no host port; application and database talk over a unix socket in a shared named volume, and the volume takes its ownership from the first image that mounts it, so starting the application first breaks the socket. The application is then supervised by the runtime on `127.0.0.1:18090`; readiness is `GET /api/heartbeat`. Resets restore a template database (`CREATE DATABASE umami TEMPLATE umami_golden`) without restarting the application process. `bash deploy/umami/db_down.sh` removes the data layer. Details and the known quirks are in `deploy/umami/README.md`.

**Paperless-ngx 3.2.0** (`ghcr.io/paperless-ngx/paperless-ngx`): the application container needs two sidecars, PostgreSQL and Valkey (the Redis-compatible broker). Neither publishes a host port; they reach the application over unix sockets in shared named volumes. The adapter's materialize step starts them:
```bash
bash deploy/paperless/stack.sh sidecars-up
```
It also runs the migrations and the in-container seed (61 documents and the golden template database) in a throw-away `<app>-prewarm` container, so the first reset after the real container starts does not race the seed. The application listens on `127.0.0.1:18091` and its readiness probe is `GET /accounts/login/`; reset and seed scripts live in `deploy/paperless/container/`. `bash deploy/paperless/stack.sh down` removes the sidecars. Details in `deploy/paperless/README.md`.

**Ghost 5.130.6** (`ghost:5-alpine`): one container with SQLite. `deploy/ghost/materialize.sh` builds the content directory (SQLite database, uploads, members key pair) and freezes a golden snapshot under `UISEMTEST_GHOST_RUNTIME_ROOT`, which must be **outside** the package; `deploy/ghost/reset.sh` stops the container, restores the snapshot and starts it again. `deploy/ghost/seed.sh` creates the owner through the setup endpoint and the second actor through the invitation flow, reading the invite token from the instance's own database (no mailbox is involved; the mailer is the nodemailer stub transport). The application listens on `127.0.0.1:18093`. Variables and defaults are in `deploy/ghost/env.example`; details in `deploy/ghost/README.md`.

Ports used by the five subjects: 3001 and 5433 (Conduit), 14000 and 14001 (RWA), 18090 (Umami), 18091 (Paperless-ngx), 18093 (Ghost). One instance per subject: an ablation run, an RQ2 run and a suite run of the same subject cannot run at the same time.

## Environment file
`cp .env.example .env`, edit if needed, then `set -a; source .env; set +a`. `scripts/relocate.py` fills in the `<ARTIFACT_ROOT>`/`<SUBJECTS>` placeholders of the example file as well (pass `--subjects <dir>` to point at the directory that contains the RWA checkout).

## Run lock for live commands
`scripts/uisemtest run` refuses live execution unless `docs/ACTIVE-EXECUTION.json` authorises it (the lock file used during the study to prevent accidental runs). Ready-made lock files are in `docs/active-templates/`: copy one over `docs/ACTIVE-EXECUTION.json` before the corresponding command and copy `closed.json` back afterwards.

| Template | Enables |
|---|---|
| `continue-<subject>.json` (conduit, rwa, umami, paperless, ghost) | continuing a frozen run — M11–M14 from the frozen M10 output, no model calls; output under `eval/ui_semantics/reviewer-continuation/<subject>/` |
| `suite-<subject>.json` | full suite runs with model calls (level 3), output under `eval/ui_semantics/reviewer-run/<subject>/` |
| `closed.json` | offline only (default) |

The RQ2 runners use their own lock, `eval/ui_semantics/rq2-subjects-20260921/ACTIVE-rq2-subjects.json` (it allows only `scripts/uisemtest-rq2`); the lock snapshots of the study's runs are kept next to the data (`ACTIVE-rq2-subjects.as-closed.json`, `eval/ui_semantics/subjects-ablation-20260921/ACTIVE-ablation-*.json`).

## Environment variables used by the scripts
| Variable | Meaning |
|---|---|
| `UISEMTEST_ARTIFACT_ROOT` | Optional override of the package root for the exported pytest suites. |
| `UISEMTEST_REPO_ROOT`, `UISEMTEST_PYTHON`, `UISEMTEST_OPERATOR_PATH` | Package root, its interpreter and the PATH used by adapter subprocesses (docker, psql, curl). |
| `UISEMTEST_CONDUIT_DEPLOY_ROOT`, `UISEMTEST_CONDUIT_OUTPUT_ROOT`, `UISEMTEST_CONDUIT_ACTOR_{A,B}_{USERNAME,EMAIL,PASSWORD}` | Conduit deployment dir (`deploy/conduit`), a scratch dir for reset artifacts, test accounts (see `.env.example`). |
| `UISEMTEST_RWA_CHECKOUT`, `UISEMTEST_NODE22_BIN`, `UISEMTEST_RWA_ACTOR_{A,B}_{USERNAME,PASSWORD}` | RWA checkout, Node.js 22 bin directory, seeded test users. |
| `UISEMTEST_UMAMI_DEPLOY_ROOT`, `UISEMTEST_UMAMI_OUTPUT_ROOT`, `UISEMTEST_UMAMI_APP_SECRET`, `UISEMTEST_UMAMI_ACTOR_{A,B}_{USERNAME,PASSWORD}` | Umami deployment dir, scratch dir, application secret and test accounts. |
| `UISEMTEST_PAPERLESS_OUTPUT_ROOT`, `UISEMTEST_PAPERLESS_SECRET_KEY`, `UISEMTEST_PAPERLESS_DBPASS`, `UISEMTEST_PAPERLESS_REDIS_SOCKET`, `UISEMTEST_PAPERLESS_ACTOR_{A,B}_{USERNAME,PASSWORD}`, `UISEMTEST_PAPERLESS_RESET_SKIP_{CACHE,FILES}` | Paperless-ngx scratch dir, local secrets of the container, test accounts and the two reset switches. |
| `UISEMTEST_GHOST_OUTPUT_ROOT`, `UISEMTEST_GHOST_RUNTIME_ROOT`, `UISEMTEST_GHOST_SITE_TITLE`, `UISEMTEST_GHOST_ACTOR_{A,B}_{NAME,EMAIL,PASSWORD}`, `UISEMTEST_GHOST_ACTOR_B_ROLE`, `UISEMTEST_GHOST_{BASE_URL,CONTAINER_PREFIX,READY_TIMEOUT_S}` | Ghost scratch dir, content directory outside the package, publication title, the two accounts and the optional overrides. |
| `UISEMTEST_RQ2_ROOT`, `UISEMTEST_RQ2_LEGACY`, `UISEMTEST_RQ2_RWA_SOURCE=run` | RQ2 evaluation roots (see README; the added subjects use the same two variables with the `rq2-subjects-20260921` roots). |
| `DEEPSEEK_RUNS_ROOT`, `RQ1_AUDIT_DIR` | RQ1 summariser roots of the Conduit/RWA tools (the parameterised tools in `scripts/experiments/rq1_tools/` take `--config` instead). |
| `DEP_CONFIG`, `DEP_RUNS_ROOT`, `DEP_RUNS_CONDUIT`, `DEP_RUNS_RWA`, `DEP_AUDIT_DIR` | Evidence-dependence analysis (Fig. 3 and Section V-C). |
| `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` | Only for level 3 (model calls). |
