#!/usr/bin/env bash
# RQ2 on the FINAL DeepSeek suite: test-map -> normal -> register -> responses/sources (per subject, parallel) -> compositions -> summarize.
# Preconditions: pytest-export-final complete for every non-empty case; ACTIVE allows scripts/uisemtest-rq2 (live, target_running false);
# no `scripts/uisemtest run` in flight. Usage: run_rq2_final.sh <phase> where phase in {map,normal,register,faults,compositions,summarize,all}
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
export UISEMTEST_RQ2_LEGACY=$PWD/eval/ui_semantics/rq2-deepseek-final2-20260912/inputs
export UISEMTEST_RQ2_ROOT=$PWD/eval/ui_semantics/rq2-deepseek-final2-20260912/suite
export UISEMTEST_RQ2_RWA_SOURCE=run UISEMTEST_RQ2_COMPOSE_PREFIX=uisemtest-rq2-dsfinal2
D=eval/ui_semantics/deepseek-full-20260912; L=eval/ui_semantics/rq2-deepseek-final2-20260912/logs; mkdir -p "$L"
phase="${1:-all}"
run_map() {
  .venv/bin/python scripts/uisemtest-rq2 test-map --subject conduit --run-root $D/conduit/m11fix-01 --export-root $D/conduit/pytest-export-final --fault-registry eval/ui_semantics/rq2-20260907/faults.jsonl | tee "$L/test-map-conduit.log"
  .venv/bin/python scripts/uisemtest-rq2 test-map --subject rwa --run-root $D/rwa/m11fix-02 --run-root $D/rwa/rerecord-01 --run-root $D/rwa/m11fix-01 --export-root $D/rwa/pytest-export-final --fault-registry eval/ui_semantics/rq2-20260907/faults.jsonl | tee "$L/test-map-rwa.log"
}
run_normal() {
  caffeinate -i .venv/bin/python scripts/uisemtest-rq2 normal --subject conduit > "$L/normal-conduit.log" 2>&1 &
  c=$!; caffeinate -i .venv/bin/python scripts/uisemtest-rq2 normal --subject rwa > "$L/normal-rwa.log" 2>&1 & r=$!
  wait $c; echo "normal conduit exit=$?"; wait $r; echo "normal rwa exit=$?"; grep -h '"qualified"' "$L"/normal-*.log | cut -c1-300
}
run_register() { .venv/bin/python scripts/uisemtest-rq2 register | tee "$L/register.log" | cut -c1-600; }
run_faults() {
  ( caffeinate -i .venv/bin/python scripts/uisemtest-rq2 responses --subject conduit > "$L/responses-conduit.log" 2>&1 && caffeinate -i .venv/bin/python scripts/uisemtest-rq2 sources --subject conduit > "$L/sources-conduit.log" 2>&1; echo "conduit faults exit=$?" ) &
  c=$!
  ( caffeinate -i .venv/bin/python scripts/uisemtest-rq2 responses --subject rwa > "$L/responses-rwa.log" 2>&1 && caffeinate -i .venv/bin/python scripts/uisemtest-rq2 sources --subject rwa > "$L/sources-rwa.log" 2>&1; echo "rwa faults exit=$?" ) &
  r=$!; wait $c; wait $r
}
run_compositions() {
  caffeinate -i .venv/bin/python scripts/uisemtest-rq2 compositions --subject conduit > "$L/compositions-conduit.log" 2>&1; echo "compositions conduit exit=$?"
  caffeinate -i .venv/bin/python scripts/uisemtest-rq2 compositions --subject rwa > "$L/compositions-rwa.log" 2>&1; echo "compositions rwa exit=$?"
}
run_summarize() { .venv/bin/python scripts/uisemtest-rq2 summarize | tee "$L/summarize.log"; }
case "$phase" in
  map) run_map ;; normal) run_normal ;; register) run_register ;; faults) run_faults ;; compositions) run_compositions ;; summarize) run_summarize ;;
  all) run_map && run_normal && run_register && run_faults && run_compositions && run_summarize ;;
  *) echo "unknown phase $phase"; exit 2 ;;
esac
