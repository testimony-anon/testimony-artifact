#!/usr/bin/env bash
# RQ2-lite on the added subjects. Usage: run_rq2_subjects.sh <phase> <subject>
#   phase in {prepare, normal, register, responses, sources, faults (responses then sources), summarize}
# Preconditions: docs/ACTIVE-EXECUTION.json (this worktree) = ACTIVE-rq2-subjects.json (allows scripts/uisemtest-rq2 live);
# no RQ3 ablation run in flight on the same subject (one application instance per subject: fixed ports 18090/18091/18093).
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
export UISEMTEST_RQ2_LEGACY=$PWD/eval/ui_semantics/rq2-subjects-20260921/inputs
export UISEMTEST_RQ2_ROOT=$PWD/eval/ui_semantics/rq2-subjects-20260921/suite
export UISEMTEST_PYTHON="$PWD/.venv/bin/python" NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
phase=${1:?phase}; subj=${2:?subject}
L=eval/ui_semantics/rq2-subjects-20260921/logs; mkdir -p "$L"
run() { echo "$subj $1 started $(date '+%F %H:%M:%S')" >> "$L/status-$subj.txt"; caffeinate -i .venv/bin/python scripts/experiments/rq2_subjects/rq2_subjects.py "$1" --subject "$subj" > "$L/$1-$subj.log" 2>&1; local rc=$?; echo "$subj $1 exit=$rc $(date '+%F %H:%M:%S')" >> "$L/status-$subj.txt"; return $rc; }
case "$phase" in
  faults) run responses && run sources ;;
  all) run normal && run register && run responses && run sources && run summarize ;;
  *) run "$phase" ;;
esac
