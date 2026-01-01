#!/bin/bash
# In-container seed for the uisemtest Paperless-ngx subject.
#
# Called by `docker_single_local` as the declared `seed` script, i.e. once after
# `supervise` starts the container and once after every `reset`.  The reset path
# must stay cheap, so everything after the first call is a single `test -f`.
#
# First call: replay the upstream Playwright fixture (seed_database.py), then
# freeze it as the golden state that `reset.sh` restores:
#   * media/documents + data/index copied to /usr/src/paperless/golden/
#   * database copied to <db>_golden, used as a PostgreSQL TEMPLATE afterwards
set -euo pipefail

GOLDEN_ROOT=/usr/src/paperless/golden
MARKER="${GOLDEN_ROOT}/.seeded"
MEDIA_ROOT=/usr/src/paperless/media
DATA_ROOT=/usr/src/paperless/data
DB_NAME="${PAPERLESS_DBNAME:-paperless}"
DB_USER="${PAPERLESS_DBUSER:-paperless}"
DB_HOST="${PAPERLESS_DBHOST:-/var/run/postgresql}"

if [ -f "${MARKER}" ]; then
  exit 0
fi

export PGPASSWORD="${PAPERLESS_DBPASS:-paperless}"
psql_admin() {
  psql -h "${DB_HOST}" -U "${DB_USER}" -d postgres -v ON_ERROR_STOP=1 -qtAX "$@"
}
psql_app() {
  psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -qtAX "$@"
}

run_as_paperless() {
  if command -v s6-setuidgid >/dev/null 2>&1; then
    s6-setuidgid paperless "$@"
  else
    su paperless -s /bin/bash -c "$(printf '%q ' "$@")"
  fi
}

echo "[uisemtest-seed] replaying the upstream Playwright fixture"
cd /usr/src/paperless/src
run_as_paperless python3 manage.py shell -c \
  "exec(open('/opt/uisemtest/seed_database.py').read())"

# The live celery workers may still be finishing signal-triggered work; the
# golden snapshot must be taken after the queue drains, otherwise two resets
# would not restore the same state.
echo "[uisemtest-seed] waiting for the task queue to drain"
for _ in $(seq 1 60); do
  pending="$(psql_app -c "SELECT count(*) FROM documents_paperlesstask WHERE status IN ('PENDING','STARTED');" || echo 0)"
  [ "${pending}" = "0" ] && break
  sleep 0.5
done
psql_app -c "DELETE FROM documents_paperlesstask;" >/dev/null

echo "[uisemtest-seed] freezing the golden file state"
mkdir -p "${GOLDEN_ROOT}"
rm -rf "${GOLDEN_ROOT}/documents" "${GOLDEN_ROOT}/index"
cp -a "${MEDIA_ROOT}/documents" "${GOLDEN_ROOT}/documents"
cp -a "${DATA_ROOT}/index" "${GOLDEN_ROOT}/index"

echo "[uisemtest-seed] freezing the golden template database"
psql_admin <<SQL
ALTER DATABASE "${DB_NAME}" WITH ALLOW_CONNECTIONS false;
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
 WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${DB_NAME}_golden";
CREATE DATABASE "${DB_NAME}_golden" TEMPLATE "${DB_NAME}" OWNER "${DB_USER}";
ALTER DATABASE "${DB_NAME}" WITH ALLOW_CONNECTIONS true;
SQL

touch "${MARKER}"
echo "[uisemtest-seed] done"
