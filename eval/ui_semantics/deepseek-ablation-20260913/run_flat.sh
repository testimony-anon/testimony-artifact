#!/usr/bin/env bash
# RQ3 ablation: full DeepSeek run (M1-M14, three-round union) of all 83 cases with --evidence-organization flat.
# Precondition: ACTIVE lists the two suite capabilities (scratchpad ACTIVE-ablation-flat.json); no other run in flight.
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
AB=eval/ui_semantics/deepseek-ablation-20260913
run_subject() {
  local subj=$1
  caffeinate -i scripts/uisemtest run \
    --suite fixtures/recording_workflows/${subj}_modular/inventory.json \
    --recording-root $AB/$subj/recordings-final \
    --adapter fixtures/adapters/${subj}_current_local.json \
    --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
    --output-root $AB/$subj/flat-01 --output-level forensic \
    --m10-samples 3 --m10-sample-mode union --provider-concurrency 48 --probe-budget 0 \
    --evidence-organization flat \
    > $AB/$subj/run-flat.log 2>&1
  echo "$subj exit=$?"
}
run_subject conduit & c=$!
run_subject rwa & r=$!
wait $c; wait $r
echo "ablation run finished at $(date '+%H:%M')"
