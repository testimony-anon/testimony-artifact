#!/usr/bin/env bash
# Single-case full runs (M1-M14, DeepSeek) for the three document-list cases whose suite M10 was cut short on 2026-09-21.
# Sequential: they share the Paperless target. Output goes into the suite tree full-01/cases/<CASE> so the RQ1 tools pick them up.
set -uo pipefail
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a
export UISEMTEST_PYTHON="$PWD/.venv/bin/python" PYTHONPATH=src NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
for c in L1-DOCLIST-01 L1-DOCLIST-02 L1-DOCLIST-04; do
  out="eval/ui_semantics/paperless-20260921/paperless/full-01/cases/$c"
  if [ -f "$out/union/M14/final_calibrated_suite.json" ]; then echo "DONE $c"; continue; fi
  echo "RUN  $c ($(date '+%H:%M:%S'))"
  caffeinate -i scripts/uisemtest run --profile fixtures/profiles/paperless_modular_local.json \
    --adapter fixtures/adapters/paperless_current_local.json \
    --recording-root "eval/ui_semantics/paperless-20260921/recordings-01/cases/$c" \
    --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
    --output-root "$out" --output-level forensic --probe-budget 0 \
    --m10-samples 3 --m10-sample-mode union --provider-concurrency 48 > "eval/ui_semantics/paperless-20260921/rerun-$c.log" 2>&1 \
    && echo "OK   $c retained=$(.venv/bin/python -c "import json;print(json.load(open('$out/union/M14/final_calibrated_suite.json')).get('retained_count'))" 2>/dev/null) ($(date '+%H:%M:%S'))" \
    || { echo "FAIL $c"; tail -3 "eval/ui_semantics/paperless-20260921/rerun-$c.log" | cut -c1-200; }
done
echo "rerun done $(date '+%H:%M:%S')"
