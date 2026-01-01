#!/usr/bin/env bash
# Export the final DeepSeek suite (first complete union per case across DEEPSEEK_RUNS,
# default "rerecord-01,m11fix-01") as pytest projects under <subject>/pytest-export-final/.
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
runs="${DEEPSEEK_RUNS:-m11fix-02,rerecord-01,m11fix-01}"
runs_root="${DEEPSEEK_RUNS_ROOT:-eval/ui_semantics/deepseek-full-20260912}"   # ablation roots override this
export_name="${DEEPSEEK_EXPORT_NAME:-pytest-export-final}"
for subject in conduit rwa; do
  root=$runs_root/$subject; out=$root/$export_name; mkdir -p "$out"
  ok=0; empty=0; fail=0; missing=0
  for c in $(cat eval/ui_semantics/deepseek-full-20260912/$subject/all-cases.txt); do
    src=""
    for run in ${runs//,/ }; do u=$root/$run/cases/$c/union; [ -f "$u/M14/final_calibrated_suite.json" ] && { src=$u; break; }; done
    [ -z "$src" ] && { echo "MISSING $subject $c"; missing=$((missing+1)); continue; }
    status=$(python3 -c "import json;print(json.load(open('$src/M14/final_calibrated_suite.json')).get('status'))")
    [ "$status" = "complete_empty" ] && { empty=$((empty+1)); continue; }
    [ -f "$out/$c/test_final_calibrated_suite.py" ] && { ok=$((ok+1)); continue; }
    if scripts/uisemtest export-pytest --run-root "$src" --output "$out/$c" > "$out/$c.export.log" 2>&1; then ok=$((ok+1)); rm -f "$out/$c.export.log"; else echo "FAIL $subject $c"; fail=$((fail+1)); fi
  done
  echo "$subject: exported=$ok empty=$empty failed=$fail missing=$missing"
done
