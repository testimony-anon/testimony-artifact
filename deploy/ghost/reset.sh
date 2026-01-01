#!/usr/bin/env bash
# Data-only reset of the Ghost subject: restore the golden content snapshot.
#
#   bash deploy/ghost/reset.sh
#
# Declared as docker_single.reset.script (strategy run_script, location host) in
# fixtures/adapters/ghost_current_local.json.  docker_single_local waits for the
# readiness probes after this script returns and then runs deploy/ghost/seed.sh,
# which is a no-op because the restored snapshot already carries both actors.
#
# Why the container is stopped and started rather than left running (the subject-onboarding brief, reset-budget section
# point 4, the SQLite exemption): Ghost keeps an open SQLite handle plus an
# in-process settings//routes cache, so replacing the files underneath the live
# process would leave the server serving stale state.  Stopping the process is the
# SQLite equivalent of the "template database restore" the task book prescribes
# for PostgreSQL subjects: image, configuration, port and container all stay in
# place, only the data is swapped, and no account is re-registered and no seed
# request is replayed.  `docker kill` is used because the database that is being
# discarded does not need a clean shutdown.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/ghost/common.sh
. "$SCRIPT_DIR/common.sh"

if [ ! -f "$GOLDEN_MARKER" ]; then
  echo "ghost reset: golden snapshot is missing at $GOLDEN_DIR (run seed.sh first)" >&2
  exit 7
fi

CONTAINER="$(resolve_container)"

docker kill "$CONTAINER" >/dev/null 2>&1 || true
mkdir -p "$CONTENT_DIR"
chmod -R u+w "$CONTENT_DIR"
rsync -a --delete --exclude '.uisemtest-ghost-golden' "$GOLDEN_DIR/" "$CONTENT_DIR/"
start_container_with_retry "$CONTAINER"
wait_ready
