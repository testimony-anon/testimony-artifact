#!/usr/bin/env bash
# One document-list case, full single-case run (M1-M14, DeepSeek) into the suite tree full-01/cases/<CASE>.
# The three cases run concurrently; if two reach M11 at once the later one fails on the shared target and is
# continued afterwards from its completed M10 union with continue_frozen_m10_subject.sh.
set -uo pipefail
c="${1:?case}"
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a
export UISEMTEST_PYTHON="$PWD/.venv/bin/python" PYTHONPATH=src NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
out="eval/ui_semantics/paperless-20260921/paperless/full-01/cases/$c"
echo "RUN  $c ($(date '+%H:%M:%S'))"
caffeinate -i scripts/uisemtest run --profile fixtures/profiles/paperless_modular_local.json \
  --adapter fixtures/adapters/paperless_current_local.json \
  --recording-root "eval/ui_semantics/paperless-20260921/recordings-01/cases/$c" \
  --provider openai_compatible --provider-policy fixtures/provider_configs/deepseek_flash_current.json \
  --output-root "$out" --output-level forensic --probe-budget 0 \
  --m10-samples 3 --m10-sample-mode union --provider-concurrency 48 > "eval/ui_semantics/paperless-20260921/rerun-$c.log" 2>&1
rc=$?
echo "EXIT $c rc=$rc ($(date '+%H:%M:%S')) union M10: $([ -f "$out/union/M10/proposal_run_completion.json" ] && echo present || echo missing) M14: $([ -f "$out/union/M14/final_calibrated_suite.json" ] && echo present || echo missing)"
tail -2 "eval/ui_semantics/paperless-20260921/rerun-$c.log" | cut -c1-200
