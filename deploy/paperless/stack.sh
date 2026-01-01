#!/bin/bash
# Sidecar lifecycle for the uisemtest Paperless-ngx subject.
#
# `docker_single_local` supervises exactly one container and its `docker run`
# argv carries no `--network` flag, so the PostgreSQL and Valkey sidecars cannot
# be reached by container DNS and must not take a host port.  They therefore
# talk to the application over **unix sockets on shared named volumes**:
#
#   <app>-pgsock     -> postgres:/var/run/postgresql , app:/var/run/postgresql
#   <app>-redissock  -> valkey:/var/run/redis        , app:/var/run/redis
#
# so PAPERLESS_DBHOST=/var/run/postgresql and
# PAPERLESS_REDIS=unix:///var/run/redis/redis.sock (both are upstream-supported
# configurations: see paperless settings parse_db_settings/parse_redis_url).
# No port is published for either sidecar.
#
# Usage (from the repository root, with .env sourced):
#   bash deploy/paperless/stack.sh sidecars-up      # idempotent, also used as the
#                                                   # adapter's materialize command
#   bash deploy/paperless/stack.sh sidecars-down    # remove sidecars + their volumes
#   bash deploy/paperless/stack.sh down             # sidecars-down + the app container
#   bash deploy/paperless/stack.sh status
#   bash deploy/paperless/stack.sh name             # print the app container name
set -euo pipefail

REPO_ROOT="${UISEMTEST_REPO_ROOT:?UISEMTEST_REPO_ROOT is unset}"
PYTHON="${UISEMTEST_PYTHON:-${REPO_ROOT}/.venv/bin/python}"
ADAPTER="${UISEMTEST_DOCKER_SINGLE_ADAPTER:-${REPO_ROOT}/fixtures/adapters/paperless_current_local.json}"
export UISEMTEST_DOCKER_SINGLE_ADAPTER="${ADAPTER}"

# `docker` is outside the sanitized PATH the pipeline hands to reset/materialize
# subprocesses; the generic adapter patches the same two directories back in.
case ":${PATH}:" in
  *:/usr/local/bin:*) ;;
  *) PATH="${PATH}:/usr/local/bin" ;;
esac
case ":${PATH}:" in
  *:/opt/homebrew/bin:*) ;;
  *) PATH="${PATH}:/opt/homebrew/bin" ;;
esac
export PATH

# Pinned by digest, exactly like the application image.
PG_IMAGE="postgres@sha256:f02121de6f74d30d8a94cd1d9584125e2178d7e6c377d8130112d4e52d867995"
VALKEY_IMAGE="valkey/valkey@sha256:a0dbf4c1d5708782907c10e2c72deff317518518b5288a58416981d9db95d30b"

app_container_name() {
  PYTHONPATH="${REPO_ROOT}/src" "${PYTHON}" -c \
    'from subject_adapters.docker_single_local import load_spec; print(load_spec().container_name)'
}

APP="$(app_container_name)"
PG="${APP}-pg"
VALKEY="${APP}-valkey"
PGDATA_VOLUME="${APP}-pgdata"
PGSOCK_VOLUME="${APP}-pgsock"
REDISSOCK_VOLUME="${APP}-redissock"
DB_USER="paperless"
DB_NAME="paperless"
DB_PASS="${UISEMTEST_PAPERLESS_DBPASS:?UISEMTEST_PAPERLESS_DBPASS is unset}"

sidecars_down() {
  docker rm -f -v "${APP}-prewarm" >/dev/null 2>&1 || true
  docker rm -f -v "${PG}" "${VALKEY}" >/dev/null 2>&1 || true
  docker volume rm -f "${PGDATA_VOLUME}" "${PGSOCK_VOLUME}" "${REDISSOCK_VOLUME}" >/dev/null 2>&1 || true
}

sidecars_up() {
  # The database cluster and the application's data/media/golden volumes must
  # share one lifetime: `supervise` drops the fresh_on_reset volumes on
  # teardown, so a surviving cluster would pair a seeded database with an empty
  # media directory.  Sidecars are therefore rebuilt from scratch whenever the
  # application container is absent, and left completely alone while it runs.
  if [ -n "$(docker ps -q -f "name=^${APP}$" 2>/dev/null)" ]; then
    echo "[uisemtest-paperless] application container is running; sidecars left untouched"
    docker exec "${PG}" pg_isready -q -h /var/run/postgresql -U "${DB_USER}" >/dev/null
    return 0
  fi
  sidecars_down
  docker volume create "${PGDATA_VOLUME}" >/dev/null
  docker volume create "${PGSOCK_VOLUME}" >/dev/null
  docker volume create "${REDISSOCK_VOLUME}" >/dev/null

  # valkey runs as uid 999 and cannot bind a socket in a root-owned volume root.
  docker run --rm -v "${REDISSOCK_VOLUME}:/sock" "${VALKEY_IMAGE}" chmod 777 /sock >/dev/null

  docker run -d --name "${PG}" \
    -v "${PGDATA_VOLUME}:/var/lib/postgresql/data" \
    -v "${PGSOCK_VOLUME}:/var/run/postgresql" \
    -e "POSTGRES_USER=${DB_USER}" \
    -e "POSTGRES_PASSWORD=${DB_PASS}" \
    -e "POSTGRES_DB=${DB_NAME}" \
    "${PG_IMAGE}" \
    -c fsync=off -c synchronous_commit=off -c full_page_writes=off \
    -c max_connections=200 >/dev/null

  docker run -d --name "${VALKEY}" \
    -v "${REDISSOCK_VOLUME}:/var/run/redis" \
    "${VALKEY_IMAGE}" \
    valkey-server --port 0 --unixsocket /var/run/redis/redis.sock \
                  --unixsocketperm 777 --save '' >/dev/null

  echo "[uisemtest-paperless] waiting for the sidecars"
  for _ in $(seq 1 120); do
    if docker exec "${PG}" pg_isready -q -h /var/run/postgresql -U "${DB_USER}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  docker exec "${PG}" pg_isready -h /var/run/postgresql -U "${DB_USER}" >/dev/null
  echo "[uisemtest-paperless] sidecars ready (${PG}, ${VALKEY})"
  prewarm_app
}

# Pre-warm (2026-09-21): run the application once as a throw-away container
# against the freshly built cluster, so that the database migrations and the
# in-container golden seed are complete BEFORE `supervise` starts the real
# container.  The pipeline's run path (current_http_runtime) waits only for the
# HTTP readiness probes and issues its first data-only reset right away; the
# seed that supervise runs after readiness takes several seconds, so without
# this step the first reset raced the seed ("golden state missing").  The
# named volumes are created here under the exact names docker_single uses, so
# the real container mounts the already seeded golden/data/media volumes and
# seed.sh returns at once (marker present).  `docker rm -f` without -v keeps
# the volumes; supervise's teardown still removes the fresh_on_reset volumes
# at the end of a run, and the next sidecars-up rebuilds everything.
prewarm_app() {
  local name line
  name="${APP}-prewarm"
  docker rm -f -v "${name}" >/dev/null 2>&1 || true
  docker volume create "${APP}-data" >/dev/null
  docker volume create "${APP}-media" >/dev/null
  docker volume create "${APP}-golden" >/dev/null
  local argv=()
  while IFS= read -r line; do argv+=("$line"); done < <(
    PYTHONPATH="${REPO_ROOT}/src" "${PYTHON}" -c '
from subject_adapters.docker_single_local import load_spec, run_argv
argv = run_argv(load_spec())
i = argv.index("--name"); argv[i + 1] = argv[i + 1] + "-prewarm"
print("\n".join(argv))')
  docker "${argv[@]}" >/dev/null
  echo "[uisemtest-paperless] pre-warm container started; waiting for readiness"
  local ok=0
  for _ in $(seq 1 600); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:18091/accounts/login/ 2>/dev/null)" = "200" ]; then ok=1; break; fi
    sleep 0.5
  done
  if [ "${ok}" != "1" ]; then
    echo "[uisemtest-paperless] pre-warm container did not become ready" >&2
    docker logs --tail 40 "${name}" >&2 || true
    docker rm -f "${name}" >/dev/null 2>&1 || true
    return 1
  fi
  docker exec -w /usr/src/paperless "${name}" /bin/bash /opt/uisemtest/seed.sh
  docker rm -f "${name}" >/dev/null
  echo "[uisemtest-paperless] application pre-warmed: migrations applied, golden seeded"
}

case "${1:-}" in
  sidecars-up) sidecars_up ;;
  sidecars-down) sidecars_down ;;
  down)
    docker rm -f -v "${APP}" "${APP}-prewarm" >/dev/null 2>&1 || true
    docker volume rm -f "${APP}-data" "${APP}-media" "${APP}-golden" >/dev/null 2>&1 || true
    sidecars_down
    echo "[uisemtest-paperless] stack removed"
    ;;
  name) echo "${APP}" ;;
  status)
    printf 'app     %-40s %s\n' "${APP}" "$(docker inspect -f '{{.State.Status}}' "${APP}" 2>/dev/null || echo absent)"
    printf 'pg      %-40s %s\n' "${PG}" "$(docker inspect -f '{{.State.Status}}' "${PG}" 2>/dev/null || echo absent)"
    printf 'valkey  %-40s %s\n' "${VALKEY}" "$(docker inspect -f '{{.State.Status}}' "${VALKEY}" 2>/dev/null || echo absent)"
    ;;
  *)
    echo "usage: stack.sh {sidecars-up|sidecars-down|down|status|name}" >&2
    exit 2
    ;;
esac
