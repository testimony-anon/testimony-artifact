#!/usr/bin/env bash
# One document-list case: M1-M10 only (DeepSeek; --stop-after-m10) into the suite tree full-01/cases/<CASE>;
# the three cases run concurrently in separate processes, M11a-M14 follows via the frozen-M10 continuation driver.
set -uo pipefail
c="${1:?case}"
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a
export UISEMTEST_PYTHON="$PWD/.venv/bin/python" PYTHONPATH=src NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
out="eval/ui_semantics/paperless-20260921/paperless/full-01/cases/$c"
echo "RUN  $c M10-only ($(date '+%H:%M:%S'))"
caffeinate -i scripts/uisemtest run --profile fixtures/profiles/paperless_modular_local.json \
  --adapter fixtures/adapters/paperless_current_local.json \
  --recording-root "eval/ui_semantics/paperless-20260921/recordings-01/cases/$c" \
  --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
  --output-root "$out" --output-level forensic --probe-budget 0 --stop-after-m10 \
  --m10-samples 3 --m10-sample-mode union --provider-concurrency 48 > "eval/ui_semantics/paperless-20260921/rerun-m10-$c.log" 2>&1 \
  && echo "OK   $c M10 done ($(date '+%H:%M:%S')) union M10: $([ -f "$out/union/M10/proposal_run_completion.json" ] && echo present || echo MISSING)" \
  || { echo "FAIL $c"; tail -3 "eval/ui_semantics/paperless-20260921/rerun-m10-$c.log" | cut -c1-200; }
