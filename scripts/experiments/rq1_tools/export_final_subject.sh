#!/usr/bin/env bash
# Export the final suite of one subject (first run in RUNS whose union holds M14/final_calibrated_suite.json,
# per case) as pytest projects under <runs_root>/<subject>/<export_name>/<case>/.
# Usage: export_final_subject.sh <subject> <runs_root> [runs-comma-separated] [export_name]
#   e.g. export_final_subject.sh umami eval/ui_semantics/umami-20260921 full-01
# Parameterised counterpart of the frozen eval/ui_semantics/deepseek-full-20260912/export_final.sh
# (same selection rule and the same export-pytest entrypoint); the case list comes from the suite inventory.
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
subject="${1:?subject}"; runs_root="${2:?runs_root}"; runs="${3:-full-01}"; export_name="${4:-pytest-export-final}"
if [ -f .env ]; then set -a; source .env; set +a; fi
inventory="fixtures/recording_workflows/${subject}_modular/inventory.json"
root="$runs_root/$subject"; out="$root/$export_name"; mkdir -p "$out"
ok=0; empty=0; fail=0; missing=0
for c in $(.venv/bin/python -c "import json,sys; d=json.load(open('$inventory')); print('\n'.join(x['case_id'] if isinstance(x,dict) else x for x in (d.get('cases') or d.get('workflows') or d.get('case_ids') or [])))"); do
  src=""
  for run in ${runs//,/ }; do u=$root/$run/cases/$c/union; [ -f "$u/M14/final_calibrated_suite.json" ] && { src=$u; break; }; done
  [ -z "$src" ] && { echo "MISSING $subject $c"; missing=$((missing+1)); continue; }
  status=$(.venv/bin/python -c "import json;print(json.load(open('$src/M14/final_calibrated_suite.json')).get('status'))")
  [ "$status" = "complete_empty" ] && { empty=$((empty+1)); continue; }
  [ -f "$out/$c/test_final_calibrated_suite.py" ] && { ok=$((ok+1)); continue; }
  if scripts/uisemtest export-pytest --run-root "$src" --output "$out/$c" > "$out/$c.export.log" 2>&1; then ok=$((ok+1)); rm -f "$out/$c.export.log"; else echo "FAIL $subject $c"; fail=$((fail+1)); fi
done
echo "$subject: exported=$ok empty=$empty failed=$fail missing=$missing"
