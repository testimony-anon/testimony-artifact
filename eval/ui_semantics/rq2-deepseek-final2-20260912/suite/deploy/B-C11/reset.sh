#!/usr/bin/env bash
# Full reset of the Conduit application under test (decision appendix 001A, condition 2):
# Truncate the seven business tables and reset the sequences → keep the application running → register two test accounts over plain HTTP.
# Switched on 2026-09-08 after verification against an independent normal image; the previous DROP+CREATE script is kept as reset.drop-create.sh.orig.
# Usage: ./reset.sh   (the compose stack must be up)
set -euo pipefail
cd "$(dirname "$0")"

BASE_URL="${CONDUIT_BASE_URL:-http://localhost:3001}"
ACTOR_A_USERNAME="${UISEMTEST_CONDUIT_ACTOR_A_USERNAME:-carver}"
ACTOR_A_EMAIL="${UISEMTEST_CONDUIT_ACTOR_A_EMAIL:-carver@carverflow.local}"
ACTOR_A_PASSWORD="${UISEMTEST_CONDUIT_ACTOR_A_PASSWORD:-carverflow-test-pw}"
ACTOR_B_USERNAME="${UISEMTEST_CONDUIT_ACTOR_B_USERNAME:-uisemtest_actor_b}"
ACTOR_B_EMAIL="${UISEMTEST_CONDUIT_ACTOR_B_EMAIL:-actor-b@carverflow.local}"
ACTOR_B_PASSWORD="${UISEMTEST_CONDUIT_ACTOR_B_PASSWORD:-uisemtest-local-b}"
PYTHON_BIN="${UISEMTEST_PYTHON:-python3}"

echo "==> Truncating business tables and resetting sequences (application keeps running)"
docker compose exec -T db psql -U conduit -d conduit \
  -c 'TRUNCATE TABLE "Articles", "Comments", "Favorites", "Followers", "TagList", "Tags", "Users" RESTART IDENTITY;'

echo "==> Waiting for the API to become ready"
for _ in $(seq 1 60); do
  if curl -sf "${BASE_URL}/api/tags" >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
[ "${ready:-0}" = "1" ] || { echo "ERROR: API not ready within 60s" >&2; exit 1; }

register_actor() {
  local username="$1"
  local email="$2"
  local password="$3"
  UISEMTEST_ACTOR_USERNAME="$username" \
  UISEMTEST_ACTOR_EMAIL="$email" \
  UISEMTEST_ACTOR_PASSWORD="$password" \
  "$PYTHON_BIN" - <<'PY' | curl -sf -X POST "${BASE_URL}/api/users" \
    -H 'Content-Type: application/json' --data-binary @- >/dev/null
import json
import os

print(json.dumps({
    "user": {
        "username": os.environ["UISEMTEST_ACTOR_USERNAME"],
        "email": os.environ["UISEMTEST_ACTOR_EMAIL"],
        "password": os.environ["UISEMTEST_ACTOR_PASSWORD"],
    }
}))
PY
}

echo "==> Registering two local test accounts"
register_actor "$ACTOR_A_USERNAME" "$ACTOR_A_EMAIL" "$ACTOR_A_PASSWORD"
register_actor "$ACTOR_B_USERNAME" "$ACTOR_B_EMAIL" "$ACTOR_B_PASSWORD"

echo "==> Reset complete: ${BASE_URL} (2 local test accounts)"
