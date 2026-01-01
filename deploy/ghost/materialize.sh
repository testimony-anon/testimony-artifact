#!/usr/bin/env bash
# One-shot preparation of the Ghost runtime root, run once per supervised target
# start (runtime.materialize_commands in the adapter).
#
#   bash deploy/ghost/materialize.sh
#
# When a golden snapshot from an earlier seed exists it is kept and the content
# directory is restored from it, so that seed.sh (which returns at once when the
# snapshot is present) never races the first data-only reset of a run - this is
# the Vikunja fix of docs/RUN-NOTES.md §2.  The state the server starts
# with is then exactly what every reset restores.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/ghost/common.sh
. "$SCRIPT_DIR/common.sh"

case "$RUNTIME_ROOT" in
  /*) ;;
  *) echo "ghost deploy: UISEMTEST_GHOST_RUNTIME_ROOT must be absolute" >&2; exit 2 ;;
esac
if [ "$RUNTIME_ROOT" = "/" ]; then
  echo "ghost deploy: UISEMTEST_GHOST_RUNTIME_ROOT must not be /" >&2
  exit 2
fi

if [ -f "$GOLDEN_MARKER" ]; then
  mkdir -p "$CONTENT_DIR"
  chmod -R u+w "$CONTENT_DIR"
  rsync -a --delete --exclude '.uisemtest-ghost-golden' "$GOLDEN_DIR/" "$CONTENT_DIR/"
  echo "ghost materialize: runtime root prepared at $RUNTIME_ROOT from the existing golden snapshot"
else
  rm -rf "$CONTENT_DIR" "$GOLDEN_DIR"
  mkdir -p "$CONTENT_DIR" "$GOLDEN_DIR"
  echo "ghost materialize: runtime root prepared at $RUNTIME_ROOT"
fi
