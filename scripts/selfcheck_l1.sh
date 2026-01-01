#!/usr/bin/env bash
# Level-1 self-check: regenerate the shipped summaries and compare them with the shipped copies.
# Usage: scripts/selfcheck_l1.sh   (from anywhere; uses .venv/bin/python if present, else python3)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY=${PY:-.venv/bin/python}; [ -x "$PY" ] || PY=python3
$PY scripts/relocate.py >/dev/null
D=eval/ui_semantics/deepseek-full-20260912; AB=eval/ui_semantics/deepseek-ablation-20260913; C=docs/design/cpv-expansion
tmp=$(mktemp -d); fail=0
same_json(){ python3 - "$1" "$2" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
for d in (a, b):
    if isinstance(d, dict): d.pop("updated_at", None); d.pop("generated_at", None)
sys.exit(0 if a == b else 1)
PY
}
check(){ # $1 = shipped copy, $2 = regenerated file
  case "$2" in *.json) same_json "$1" "$2" ;; *) diff -q "$1" "$2" >/dev/null ;; esac
  if [ $? -eq 0 ]; then echo "OK   $2"; else echo "DIFF $2"; fail=1; fi; }
for cfg in full temporal flat; do
  if [ $cfg = full ]; then R=$D; E=pytest-export-final; A=$C/rq1-audit-deepseek; else R=$AB; E=pytest-export-$cfg; A=$C/rq1-audit-deepseek-$cfg; fi
  cp $A/summary.md $tmp/$cfg.md; DEEPSEEK_RUNS_ROOT=$R RQ1_AUDIT_DIR=$A $PY $D/rq1_summarize_deepseek.py $E >/dev/null 2>&1; check $tmp/$cfg.md $A/summary.md
done
for cfg in temporal flat; do
  if [ $cfg = temporal ]; then runs=temporal-retry-02,temporal-01; else runs=flat-fix-01,flat-retry-01,flat-01; fi
  cp $AB/rq3-$cfg-comparison.json $tmp/$cfg.json; $PY $AB/ablation_compare.py $cfg $C/rq1-audit-deepseek-$cfg $AB $runs >/dev/null 2>&1; check $tmp/$cfg.json $AB/rq3-$cfg-comparison.json
done
S=eval/ui_semantics/rq2-deepseek-final2-20260912; cp $S/suite/summary.json $tmp/rq2.json; cp $S/suite/report.md $tmp/rq2.md
UISEMTEST_RQ2_ROOT=$PWD/$S/suite UISEMTEST_RQ2_LEGACY=$PWD/$S/inputs UISEMTEST_RQ2_RWA_SOURCE=run PYTHONPATH=src $PY -m ui_semantics.rq2_evaluation summarize >/dev/null 2>&1
check $tmp/rq2.json $S/suite/summary.json; check $tmp/rq2.md $S/suite/report.md
# Umami / Paperless-ngx / Ghost: RQ1 summaries, the two ablation comparisons and the per-subject RQ2 reports
X=docs/design/subjects-expansion-20260919; AB2=eval/ui_semantics/subjects-ablation-20260921; S2=eval/ui_semantics/rq2-subjects-20260921
T=scripts/experiments/rq1_tools
for subj in umami paperless ghost; do
  for cfg in "" -ablation-temporal -ablation-flat; do
    case "$cfg" in "") A=$X/rq1-audit-$subj; cfgfile=$T/configs/$subj-20260921.json ;;
                    *)  A=$X/rq1-audit-$subj${cfg#-ablation}; cfgfile=$T/configs/$subj$cfg.json ;; esac
    [ -f "$cfgfile" ] && [ -f "$A/summary.md" ] || continue
    cp $A/summary.md $tmp/$subj$cfg.md; $PY $T/rq1_summarize_deepseek.py --config "$cfgfile" >/dev/null 2>&1
    check $tmp/$subj$cfg.md $A/summary.md
  done
done
for cfg in temporal flat; do
  cp $AB2/rq3-$cfg-comparison.json $tmp/sub-$cfg.json; $PY $AB2/ablation_compare_subjects.py $cfg >/dev/null 2>&1
  check $tmp/sub-$cfg.json $AB2/rq3-$cfg-comparison.json
done
for subj in umami paperless ghost; do
  cp $S2/suite/summary-$subj.json $tmp/rq2-$subj.json; cp $S2/suite/report-$subj.md $tmp/rq2-$subj.md
  UISEMTEST_RQ2_ROOT=$PWD/$S2/suite UISEMTEST_RQ2_LEGACY=$PWD/$S2/inputs PYTHONPATH=src \
    $PY scripts/experiments/rq2_subjects/rq2_subjects.py summarize --subject $subj >/dev/null 2>&1
  check $tmp/rq2-$subj.json $S2/suite/summary-$subj.json; check $tmp/rq2-$subj.md $S2/suite/report-$subj.md
done
if [ $fail = 0 ]; then echo "ALL OK"; else echo "SOME DIFFERENCES"; fi; exit $fail
