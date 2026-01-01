# Umami deployment (subject id `umami`)

Two layers: the **application container** is supervised by the generic adapter
`subject_adapters.docker_single_local` (configuration in `fixtures/adapters/umami_current_local.json`), and the
**PostgreSQL data layer** is started separately by the scripts in this directory. The two communicate only
through a **unix socket** inside a shared named volume; Postgres publishes no host port at all. The single port
occupied on the host is `127.0.0.1:18090` (the application).

| Item | Value |
|---|---|
| Application image | `ghcr.io/umami-software/umami@sha256:85909afc45bdcda1917394594a087421fdbb05610fded0fa9f6fb861abb2f367` (tag `postgresql-latest`; version **3.4.0** in `/app/package.json`) |
| Database image | `postgres@sha256:3c5c8892d184f738f4fe282d14ddaa613a38f00f4189d2d94725ebe6f2909ddb` (tag `16-alpine`) |
| Ports | `127.0.0.1:18090 -> 3000`; Postgres publishes nothing |
| Connection string | `postgresql://umami:umami@localhost/umami?host=/var/run/postgresql` (Prisma's unix-socket form) |
| Accounts | actor_a is the single account the image bootstraps; actor_b is created by `seed.sh` through `POST /api/users` (role `user`). User names and passwords live only in `UISEMTEST_UMAMI_ACTOR_{A,B}_{USERNAME,PASSWORD}` of the package's `.env` (see `.env.example`) |
| Readiness probe | `GET http://127.0.0.1:18090/api/heartbeat` -> 200 `{"ok":true}` (no authentication, cheapest probe) |
| Reset | restore from a template database, see below |

## Files

| File | Purpose |
|---|---|
| `lib.sh` | Recomputes the docker_single instance name (`sha256(instance key)[:16]`), derives the data-layer container and volume names, and pins the image digests |
| `db_up.sh` | Starts the data layer: create the shared socket volume and the data volume, start Postgres, wait for `pg_isready`, write `.runtime/names.env` |
| `db_down.sh` | Removes the data-layer container and both volumes |
| `seed.sh` | The docker_single `seed` hook. On the first call it creates actor_b and one website and then freezes the result into the template database `umami_golden`; later calls only check a marker file and return immediately |
| `reset.sh` | The docker_single `reset.script`: `DROP DATABASE umami WITH (FORCE); CREATE DATABASE umami TEMPLATE umami_golden;` |
| `.runtime/` | Per-instance runtime state (container names, golden marker); not tracked |

## Start order (**`db_up.sh` must run first**)

```bash
set -a; source .env; set +a
bash deploy/umami/db_up.sh                       # data layer
.venv/bin/python -m subject_adapters.docker_single_local supervise \
    --adapter fixtures/adapters/umami_current_local.json    # application layer (long-running)
```

Why the data layer comes first: the shared volume is mounted at `/var/run/postgresql`, and Docker initialises
such a volume from the content and ownership of that directory in the **first** image that mounts it. Mounting
Postgres first yields `postgres:postgres` ownership; mounting umami first yields an empty root-owned directory
in which Postgres can no longer create its socket. `db_up.sh` refuses to run while the application container
exists.

On SIGTERM, `supervise` removes the application container; the data layer and the socket volume
(`reset_scope: persistent`) are kept, so the application can be restarted repeatedly without re-running the
migrations and the seed. To clean up completely:

```bash
bash deploy/umami/db_down.sh
```

## Reset

```
DROP DATABASE umami WITH (FORCE);           -- also drops the application's Prisma connection pool
CREATE DATABASE umami TEMPLATE umami_golden;
```

The **application process is not restarted** (the `Pid` and `RestartCount` of `docker inspect` are unchanged
across ten resets); only the data is replaced. The template database is the seeded state frozen by `seed.sh`
with `CREATE DATABASE ... TEMPLATE`, so the restored UUIDs and time stamps are **bit-identical** to the seeded
ones.

`recreate_with_fresh_volume` is not used: that path would rebuild the application container and re-run 26
Prisma migrations, measured at 12.9 s during the survey, above the 3 s reset budget of the study's deployment
requirements.

## Known quirks

- `POST /api/websites/{id}` with a `teamId` answers 200 but has **no effect**; transferring a website to a team
  must go through `POST /api/websites/{id}/transfer` (measured during the survey).
- The adapter injects `DISABLE_TELEMETRY=1` and `DISABLE_UPDATES=1` into the container; without them the
  front end requests `https://api.umami.is/v1/updates` and `https://i.umami.is/a.png` on every load, and the
  first of these is a JSON `fetch` that the recorder would capture into the trace.
- Logging in returns the JWT in the JSON body only and sets **no cookie**; the front end keeps it in
  `localStorage['umami.auth']`.
