#!/usr/bin/env bash
# Single-subject variant of run_ablation.sh (same protocol).
# Usage: run_ablation_subject.sh <temporal|flat> <subject> <inventory-relative-to-fixtures/recording_workflows> [recording-root-name]
# The recording root defaults to recordings-01; an inventory named *-ablation.json uses recordings-ablation
# (Paperless: the 32-case suite whose manifest is that inventory).
set -uo pipefail
CONFIG=${1:?}; subj=${2:?}; inv=${3:?}
case "$inv" in *-ablation.json) recdef=recordings-ablation ;; *) recdef=recordings-01 ;; esac
rec=${4:-$recdef}
W=<PAPER_CODE_WORKTREE>
M=<ARTIFACT_ROOT>
AB=$M/eval/ui_semantics/subjects-ablation-20260921
cd "$W" || exit 1
set -a; source "$M/.env"; set +a
export UISEMTEST_PYTHON="$W/.venv/bin/python" PYTHONPATH="$W/src" NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
mkdir -p "$AB/$subj"
echo "$subj $CONFIG (single, $rec) started at $(date '+%F %H:%M:%S')" >> "$AB/run-$CONFIG.status"
caffeinate -i scripts/uisemtest run \
  --suite "fixtures/recording_workflows/$inv" \
  --adapter "fixtures/adapters/${subj}_current_local.json" \
  --recording-root "eval/ui_semantics/${subj}-20260921/$rec" \
  --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
  --output-root "eval/ui_semantics/subjects-ablation-20260921/${subj}/${CONFIG}-01" \
  --output-level forensic --probe-budget 0 --m10-samples 3 --m10-sample-mode union --provider-concurrency 48 \
  --evidence-organization "$CONFIG" \
  > "$AB/run-$CONFIG-$subj.log" 2>&1
echo "$subj $CONFIG exit=$? at $(date '+%F %H:%M:%S')" >> "$AB/run-$CONFIG.status"
