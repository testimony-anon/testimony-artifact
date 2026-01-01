#!/usr/bin/env bash
# Ghost read/query-behaviour extension (B-G04, B-G05, PR-G04..06): prepare/register in append mode, then run the new faults.
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
export UISEMTEST_RQ2_LEGACY=$PWD/eval/ui_semantics/rq2-subjects-20260921/inputs UISEMTEST_RQ2_ROOT=$PWD/eval/ui_semantics/rq2-subjects-20260921/suite
export UISEMTEST_PYTHON="$PWD/.venv/bin/python" NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
L=eval/ui_semantics/rq2-subjects-20260921/logs
run() { echo "ghost $1 (ext) started $(date '+%F %H:%M:%S')" >> "$L/status-ghost.txt"; caffeinate -i .venv/bin/python scripts/experiments/rq2_subjects/rq2_subjects.py "$@" --subject ghost > "$L/$1-ghost-ext.log" 2>&1; local rc=$?; echo "ghost $1 (ext) exit=$rc $(date '+%F %H:%M:%S')" >> "$L/status-ghost.txt"; return $rc; }
run prepare --append && run register --append && run responses && run sources && run summarize
