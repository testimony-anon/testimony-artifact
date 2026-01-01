#!/usr/bin/env bash
# Shared naming for the Umami two-tier deployment.
#
# The application container is owned by `subject_adapters.docker_single_local`
# (adapter fixtures/adapters/umami_current_local.json).  Its name is
#   <container_name_prefix>-<sha256(instance key)[:16]>
# exactly as load_spec() computes it (src/subject_adapters/docker_single_local.py:
# `instance_source` -> resolve() when absolute -> sha256 -> [:16]).  The data tier
# (PostgreSQL) is *not* a docker_single container, so this file recomputes the
# same suffix and derives every other name from it.  Nothing here starts or
# stops the application container.

set -euo pipefail

UMAMI_DEPLOY_ROOT="${UMAMI_DEPLOY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)}"
UMAMI_RUNTIME_DIR="$UMAMI_DEPLOY_ROOT/.runtime"

UMAMI_APP_PREFIX="uisemtest-umami"
UMAMI_INSTANCE_KEY_ENV="UISEMTEST_UMAMI_OUTPUT_ROOT"

# Pinned images (digest is the addressing form; the tag is documentation only).
UMAMI_APP_IMAGE_REPOSITORY="ghcr.io/umami-software/umami"
UMAMI_APP_IMAGE_DIGEST="sha256:85909afc45bdcda1917394594a087421fdbb05610fded0fa9f6fb861abb2f367"
UMAMI_APP_IMAGE_TAG="postgresql-latest"   # resolves to umami 3.4.0 (package.json inside the image)
UMAMI_DB_IMAGE_REPOSITORY="postgres"
UMAMI_DB_IMAGE_DIGEST="sha256:3c5c8892d184f738f4fe282d14ddaa613a38f00f4189d2d94725ebe6f2909ddb"
UMAMI_DB_IMAGE_TAG="16-alpine"

UMAMI_DB_NAME="umami"
UMAMI_DB_GOLDEN="umami_golden"
UMAMI_DB_USER="umami"
UMAMI_DB_PASSWORD="umami"       # loopback-only, never published; not a study credential
UMAMI_BASE_URL="${UMAMI_BASE_URL:-http://127.0.0.1:18090}"

umami_instance_suffix() {
  python3 - "$UMAMI_INSTANCE_KEY_ENV" <<'PY'
import hashlib, os, sys
from pathlib import Path
name = sys.argv[1]
key = os.environ.get(name) or ""
if not key:
    sys.exit(f"{name} is unset; source the repository .env first")
if os.path.isabs(key):
    key = str(Path(key).resolve())
print(hashlib.sha256(key.encode()).hexdigest()[:16])
PY
}

umami_resolve_names() {
  local suffix
  suffix="$(umami_instance_suffix)"
  UMAMI_APP_CONTAINER="${UMAMI_APP_PREFIX}-${suffix}"
  UMAMI_DB_CONTAINER="${UMAMI_APP_PREFIX}-db-${suffix}"
  # Declared in the adapter as docker_single volume `pgsock`; docker_single names
  # a named volume <app container>-<name>, so both tiers must agree on this.
  UMAMI_SOCKET_VOLUME="${UMAMI_APP_CONTAINER}-pgsock"
  UMAMI_DATA_VOLUME="${UMAMI_DB_CONTAINER}-pgdata"
  UMAMI_GOLDEN_MARKER="${UMAMI_RUNTIME_DIR}/${UMAMI_APP_CONTAINER}.golden"
  export UMAMI_APP_CONTAINER UMAMI_DB_CONTAINER UMAMI_SOCKET_VOLUME UMAMI_DATA_VOLUME UMAMI_GOLDEN_MARKER
}

umami_psql() {
  # $1 = database, rest = psql arguments.  Runs inside the data-tier container,
  # so PostgreSQL is reachable over the container's own unix socket only.
  local database="$1"; shift
  docker exec "$UMAMI_DB_CONTAINER" psql -U "$UMAMI_DB_USER" -d "$database" \
    -q -v ON_ERROR_STOP=1 "$@"
}
