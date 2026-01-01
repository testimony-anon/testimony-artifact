#!/usr/bin/env bash
# Retry of the two RWA flat-ablation cases that failed on provider response schema violations
# (L4-REQUEST-NOTIFY-01 center completion, L4-REQUEST-REJECT-01 round shortfall), after the
# schema-rejection retry fix. Precondition: ACTIVE lists the flat retry capability (rwa/flat-retry-01).
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
AB=eval/ui_semantics/deepseek-ablation-20260913
caffeinate -i scripts/uisemtest run --suite fixtures/recording_workflows/rwa_modular/retry-ablation-flat-20260913.json \
  --recording-root $AB/rwa/recordings-retry-flat --adapter fixtures/adapters/rwa_current_local.json \
  --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
  --output-root $AB/rwa/flat-retry-01 --output-level forensic --m10-samples 3 --m10-sample-mode union \
  --provider-concurrency 48 --probe-budget 0 --evidence-organization flat > $AB/rwa/run-flat-retry.log 2>&1
echo "flat retry exit=$? at $(date '+%H:%M')"
