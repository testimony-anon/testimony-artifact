#!/bin/bash
# In-container data-only reset for the uisemtest Paperless-ngx subject.
#
# Called by `docker_single_local` as the declared `reset.script`
# (strategy `run_script`, location `container`).  The application process is
# never restarted: only data is restored, per
# the authors' Paperless-ngx onboarding brief §0b.
#
#   1. database  DROP ... WITH (FORCE) + CREATE ... TEMPLATE <db>_golden
#   2. files     media/documents and data/index restored from the golden copy
#   3. cache     Redis flushed, because SESSION_ENGINE is `cached_db` and the
#                Django cache would otherwise outlive the rows it mirrors
#
# Set UISEMTEST_PAPERLESS_RESET_SKIP_FILES=1 / _SKIP_CACHE=1 to measure the cost
# of each phase separately; both default to on.
set -euo pipefail

GOLDEN_ROOT=/usr/src/paperless/golden
MEDIA_ROOT=/usr/src/paperless/media
DATA_ROOT=/usr/src/paperless/data
DB_NAME="${PAPERLESS_DBNAME:-paperless}"
DB_USER="${PAPERLESS_DBUSER:-paperless}"
DB_HOST="${PAPERLESS_DBHOST:-/var/run/postgresql}"
REDIS_SOCKET="${UISEMTEST_PAPERLESS_REDIS_SOCKET:-/var/run/redis/redis.sock}"

if [ ! -f "${GOLDEN_ROOT}/.seeded" ]; then
  echo "[uisemtest-reset] golden state missing; run the seed first" >&2
  exit 1
fi

export PGPASSWORD="${PAPERLESS_DBPASS:-paperless}"
psql -h "${DB_HOST}" -U "${DB_USER}" -d postgres -v ON_ERROR_STOP=1 -qtAX <<SQL
DROP DATABASE IF EXISTS "${DB_NAME}" WITH (FORCE);
CREATE DATABASE "${DB_NAME}" TEMPLATE "${DB_NAME}_golden" OWNER "${DB_USER}";
SQL

if [ "${UISEMTEST_PAPERLESS_RESET_SKIP_FILES:-0}" != "1" ]; then
  rm -rf "${MEDIA_ROOT}/documents" "${DATA_ROOT}/index"
  cp -a "${GOLDEN_ROOT}/documents" "${MEDIA_ROOT}/documents"
  cp -a "${GOLDEN_ROOT}/index" "${DATA_ROOT}/index"
fi

if [ "${UISEMTEST_PAPERLESS_RESET_SKIP_CACHE:-0}" != "1" ]; then
  python3 -c "import redis; redis.Redis(unix_socket_path='${REDIS_SOCKET}').flushall()"
fi
