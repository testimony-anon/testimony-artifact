#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
AB=eval/ui_semantics/deepseek-ablation-20260913
caffeinate -i scripts/uisemtest run --suite fixtures/recording_workflows/rwa_modular/retry-ablation-temporal-20260913.json \
  --recording-root $AB/rwa/recordings-retry-temporal --adapter fixtures/adapters/rwa_current_local.json \
  --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
  --output-root $AB/rwa/temporal-retry-01 --output-level forensic --m10-samples 3 --m10-sample-mode union \
  --provider-concurrency 48 --probe-budget 0 --evidence-organization temporal > $AB/rwa/run-temporal-retry.log 2>&1
echo "temporal retry exit=$? at $(date '+%H:%M')"
