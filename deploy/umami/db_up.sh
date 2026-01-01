#!/usr/bin/env bash
# Bring up the Umami data tier (PostgreSQL) for one adapter instance.
#
# Run this BEFORE `subject_adapters.docker_single_local supervise`: the shared
# socket volume must be initialised from the postgres image (owner postgres),
# not from the umami image (which has no /var/run/postgresql).
#
#   set -a; source .env; set +a
#   bash deploy/umami/db_up.sh
#
# PostgreSQL publishes NO host port.  The only channel between the two tiers is
# the unix socket in the shared named volume, so the database is unreachable
# from outside the Docker VM by construction.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/lib.sh"
umami_resolve_names

if [ -n "$(docker ps -aq --filter "name=^/${UMAMI_APP_CONTAINER}$")" ]; then
  echo "refusing to rebuild the data tier while the application container ${UMAMI_APP_CONTAINER} exists" >&2
  exit 1
fi

mkdir -p "$UMAMI_RUNTIME_DIR"
rm -f "$UMAMI_GOLDEN_MARKER"

docker rm -f -v "$UMAMI_DB_CONTAINER" >/dev/null 2>&1 || true
docker volume rm -f "$UMAMI_SOCKET_VOLUME" "$UMAMI_DATA_VOLUME" >/dev/null 2>&1 || true
docker volume create "$UMAMI_SOCKET_VOLUME" >/dev/null
docker volume create "$UMAMI_DATA_VOLUME" >/dev/null

docker image inspect "${UMAMI_DB_IMAGE_REPOSITORY}@${UMAMI_DB_IMAGE_DIGEST}" >/dev/null 2>&1 \
  || docker pull "${UMAMI_DB_IMAGE_REPOSITORY}@${UMAMI_DB_IMAGE_DIGEST}" >/dev/null

docker run -d --name "$UMAMI_DB_CONTAINER" \
  -e "POSTGRES_DB=${UMAMI_DB_NAME}" \
  -e "POSTGRES_USER=${UMAMI_DB_USER}" \
  -e "POSTGRES_PASSWORD=${UMAMI_DB_PASSWORD}" \
  -v "${UMAMI_SOCKET_VOLUME}:/var/run/postgresql" \
  -v "${UMAMI_DATA_VOLUME}:/var/lib/postgresql/data" \
  "${UMAMI_DB_IMAGE_REPOSITORY}@${UMAMI_DB_IMAGE_DIGEST}" >/dev/null

for _ in $(seq 1 120); do
  if docker exec "$UMAMI_DB_CONTAINER" pg_isready -U "$UMAMI_DB_USER" -d "$UMAMI_DB_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
docker exec "$UMAMI_DB_CONTAINER" pg_isready -U "$UMAMI_DB_USER" -d "$UMAMI_DB_NAME" >/dev/null

cat > "$UMAMI_RUNTIME_DIR/names.env" <<EOF
UMAMI_APP_CONTAINER=$UMAMI_APP_CONTAINER
UMAMI_DB_CONTAINER=$UMAMI_DB_CONTAINER
UMAMI_SOCKET_VOLUME=$UMAMI_SOCKET_VOLUME
UMAMI_DATA_VOLUME=$UMAMI_DATA_VOLUME
UMAMI_GOLDEN_MARKER=$UMAMI_GOLDEN_MARKER
EOF

echo "data tier ready: ${UMAMI_DB_CONTAINER} (socket volume ${UMAMI_SOCKET_VOLUME}, no host port)"
