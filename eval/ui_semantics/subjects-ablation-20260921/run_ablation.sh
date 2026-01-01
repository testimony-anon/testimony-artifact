#!/usr/bin/env bash
# RQ3 ablation for the three added subjects (umami / paperless minus 3 doc-list cases / ghost): one evidence-organization
# configuration (temporal | flat), M1-M14 from the frozen recordings-01, three-round union, the paper's protocol.
# Runs from the paper-code worktree <PAPER_CODE_WORKTREE> (src 15cceb33f + Ghost fixtures of adfcae3a5^);
# the worktree's docs/ACTIVE-EXECUTION.json must be ACTIVE-ablation-<config>.json (validated by check_lock.py).
# Usage: run_ablation.sh temporal|flat
set -uo pipefail
CONFIG=${1:?temporal|flat}
W=<PAPER_CODE_WORKTREE>
M=<ARTIFACT_ROOT>
AB=$M/eval/ui_semantics/subjects-ablation-20260921
cd "$W" || exit 1
set -a; source "$M/.env"; set +a
export UISEMTEST_PYTHON="$W/.venv/bin/python" PYTHONPATH="$W/src" NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
echo "$CONFIG started at $(date '+%F %H:%M:%S') pid $$" >> "$AB/run-$CONFIG.status"
run_subject() {
  local subj=$1 inv=$2
  mkdir -p "$AB/$subj"
  caffeinate -i scripts/uisemtest run \
    --suite "fixtures/recording_workflows/$inv" \
    --adapter "fixtures/adapters/${subj}_current_local.json" \
    --recording-root "eval/ui_semantics/${subj}-20260921/recordings-01" \
    --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
    --output-root "eval/ui_semantics/subjects-ablation-20260921/${subj}/${CONFIG}-01" \
    --output-level forensic --probe-budget 0 --m10-samples 3 --m10-sample-mode union --provider-concurrency 48 \
    --evidence-organization "$CONFIG" \
    > "$AB/run-$CONFIG-$subj.log" 2>&1
  echo "$subj $CONFIG exit=$? at $(date '+%F %H:%M:%S')" >> "$AB/run-$CONFIG.status"
}
run_subject umami umami_modular/inventory.json & u=$!
run_subject paperless paperless_modular/inventory-ablation.json & p=$!
run_subject ghost ghost_modular/inventory.json & g=$!
wait $u; wait $p; wait $g
echo "$CONFIG finished at $(date '+%F %H:%M:%S')" >> "$AB/run-$CONFIG.status"
