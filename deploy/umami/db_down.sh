#!/usr/bin/env bash
# Remove the Umami data tier and its volumes for one adapter instance.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/lib.sh"
umami_resolve_names
docker rm -f -v "$UMAMI_DB_CONTAINER" >/dev/null 2>&1 || true
docker volume rm -f "$UMAMI_SOCKET_VOLUME" "$UMAMI_DATA_VOLUME" >/dev/null 2>&1 || true
rm -f "$UMAMI_GOLDEN_MARKER" "$UMAMI_RUNTIME_DIR/names.env"
echo "data tier removed: ${UMAMI_DB_CONTAINER}"
