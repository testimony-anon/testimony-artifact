#!/usr/bin/env bash
# Full DeepSeek main-line run (M1-M14) for umami; paper protocol. Requires ACTIVE with the umami run capability.
set -euo pipefail
cd "$(dirname "$0")/../../.."   # repo root when placed at eval/ui_semantics/umami-20260921/
set -a; source .env; set +a
export UISEMTEST_PYTHON="$PWD/.venv/bin/python" PYTHONPATH=src NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
mkdir -p eval/ui_semantics/umami-20260921/umami
caffeinate -i scripts/uisemtest run \
  --suite fixtures/recording_workflows/umami_modular/inventory.json \
  --adapter fixtures/adapters/umami_current_local.json \
  --recording-root eval/ui_semantics/umami-20260921/recordings-01 \
  --provider openai_compatible \
  --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
  --output-root eval/ui_semantics/umami-20260921/umami/full-01 \
  --output-level forensic --probe-budget 0 \
  --m10-samples 3 --m10-sample-mode union --provider-concurrency 48 \
  > eval/ui_semantics/umami-20260921/run-full-01.log 2>&1
echo "exit=$?" >> eval/ui_semantics/umami-20260921/run-full-01.log
