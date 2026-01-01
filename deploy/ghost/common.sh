#!/usr/bin/env bash
# Shared helpers for the Ghost subject lifecycle scripts.
#
# These scripts are called by src/subject_adapters/docker_single_local.py as the
# `materialize` / `seed` / `reset` hooks of fixtures/adapters/ghost_current_local.json.
# They run with the sanitized reset environment (PATH=/usr/bin:/bin:/usr/sbin:/sbin
# plus the docker client directory, and only UISEMTEST_* variables), so every
# required value has to arrive through a UISEMTEST_GHOST_* environment variable.
#
# Important (learned on Vikunja, the authors' onboarding notes of a candidate subject that was not used §C.4 round 1): the RECORDING
# entry point runs profile.reset.command without the adapter's runtime.environment
# (src/stage2_5_probe/assemble.py:48 passes no env=), so the only variables these
# scripts may *require* are the ones that live in the repository .env.  Everything
# else must have a default.
#
# No credential value is ever written into this repository: the scripts only read
# the variable names below, whose values live in the repository .env.

set -euo pipefail

require_env() {
  local name
  for name in "$@"; do
    if [ -z "${!name:-}" ]; then
      echo "ghost deploy: required environment variable is unset: $name" >&2
      exit 2
    fi
  done
}

require_env UISEMTEST_GHOST_RUNTIME_ROOT

RUNTIME_ROOT="$UISEMTEST_GHOST_RUNTIME_ROOT"
CONTENT_DIR="$RUNTIME_ROOT/content"
GOLDEN_DIR="$RUNTIME_ROOT/golden"
GOLDEN_MARKER="$GOLDEN_DIR/.uisemtest-ghost-golden"
DB_FILE="$CONTENT_DIR/data/ghost.db"

BASE_URL="${UISEMTEST_GHOST_BASE_URL:-http://127.0.0.1:18093}"
BASE_URL="${BASE_URL%/}"
CONTAINER_PREFIX="${UISEMTEST_GHOST_CONTAINER_PREFIX:-uisemtest-ghost}"
READY_TIMEOUT_S="${UISEMTEST_GHOST_READY_TIMEOUT_S:-120}"

# The cheapest unauthenticated Admin API read; it is also the adapter readiness
# probe and the profile reset verify_request.
READY_PATH="/ghost/api/admin/site/"

# The container name is <prefix>-<sha256(instance key)[:16]>, computed by
# docker_single_local.load_spec().  Rather than duplicating that derivation in
# shell, the scripts resolve the single container that carries the prefix.
resolve_container() {
  local names count
  names="$(docker ps -a --filter "name=^/${CONTAINER_PREFIX}-" --format '{{.Names}}')"
  count="$(printf '%s' "$names" | grep -c . || true)"
  if [ "$count" != "1" ]; then
    echo "ghost deploy: expected exactly one ${CONTAINER_PREFIX}-* container, found ${count}" >&2
    [ -n "$names" ] && printf '%s\n' "$names" >&2
    exit 3
  fi
  printf '%s' "$names"
}

wait_ready() {
  local deadline
  deadline=$(( $(date +%s) + READY_TIMEOUT_S ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if curl -fsS --max-time 2 "$BASE_URL$READY_PATH" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.05
  done
  echo "ghost deploy: readiness deadline exceeded for $BASE_URL$READY_PATH" >&2
  exit 4
}

# Docker Desktop (macOS) reliably fails the first `docker start` after the host
# replaced files under a bind mount that the killed process still held open
# (docs/RUN-NOTES.md §5, observed on Vikunja).  Start, confirm the
# process survived its first second, retry if it did not.
start_container_with_retry() {  # start_container_with_retry <container>
  local container="$1" started=0 _ i
  for _ in 1 2 3 4; do
    docker start "$container" >/dev/null
    for i in 1 2 3 4 5 6 7 8 9 10; do
      sleep 0.1
      [ "$(docker inspect -f '{{.State.Status}}' "$container")" = "running" ] || break
    done
    if [ "$(docker inspect -f '{{.State.Status}}' "$container")" = "running" ]; then
      started=1
      break
    fi
  done
  if [ "$started" != "1" ]; then
    echo "ghost deploy: container did not stay up after start" >&2
    docker logs --tail 10 "$container" >&2 || true
    exit 8
  fi
}
