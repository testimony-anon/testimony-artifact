#!/usr/bin/env bash
# docker_single `reset.script` for Umami: data-only reset, ~0.3 s.
#
# The application container is NOT restarted and NOT reconfigured; only the
# database is swapped back to the frozen seed state:
#   DROP DATABASE umami WITH (FORCE);  -- also terminates the app's pool
#   CREATE DATABASE umami TEMPLATE umami_golden;
# Prisma reconnects on the next query (measured: the first authenticated call
# after the swap succeeds, see the authors' Umami onboarding notes).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/lib.sh"
umami_resolve_names

if [ ! -f "$UMAMI_GOLDEN_MARKER" ]; then
  echo "no golden template yet for ${UMAMI_APP_CONTAINER}; run deploy/umami/seed.sh first" >&2
  exit 1
fi

umami_psql postgres \
  -c "DROP DATABASE IF EXISTS ${UMAMI_DB_NAME} WITH (FORCE);" \
  -c "CREATE DATABASE ${UMAMI_DB_NAME} TEMPLATE ${UMAMI_DB_GOLDEN};" >/dev/null
