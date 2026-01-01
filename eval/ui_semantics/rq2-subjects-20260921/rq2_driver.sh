#!/usr/bin/env bash
# RQ2-lite driver for one added subject: waits until no RQ3 ablation run of that subject is alive (one application
# instance per subject), installs the RQ2 lock in this worktree if needed, then runs
#   prepare (if not yet) -> normal -> register -> responses -> sources -> summarize
# Usage: rq2_driver.sh <subject>      (catalogue inputs/faults-<subject>.jsonl must have been reviewed and frozen)
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
subj=${1:?subject}
R=$PWD/eval/ui_semantics/rq2-subjects-20260921; L=$R/logs; mkdir -p "$L"
log() { echo "$(date '+%F %H:%M:%S') $subj $*" >> "$L/driver-$subj.log"; }
[ -f "$R/inputs/faults-$subj.jsonl" ] || { log "no catalogue; abort"; exit 2; }
rq3_alive() { pgrep -f "ui_semantics.cli run .*subjects-ablation-20260921/$subj/" | wc -l | tr -d ' '; }
AB=$PWD/eval/ui_semantics/subjects-ablation-20260921
# the subject is free only after BOTH ablation configurations finished (flat is the last one for every subject)
while ! grep -q "^$subj flat exit=" "$AB/run-flat.status" 2>/dev/null; do sleep 120; done
while [ "$(rq3_alive)" != "0" ]; do sleep 60; done
log "RQ3 finished for $subj (flat exit line present) and no RQ3 run of $subj alive"
if ! .venv/bin/python - <<'PY'
import json,sys; d=json.load(open('docs/ACTIVE-EXECUTION.json')); sys.exit(0 if d.get('live_allowed') and 'scripts/uisemtest-rq2' in d.get('allowed_entrypoints',[]) and d.get('target_running') is False else 1)
PY
then
  if pgrep -f 'ui_semantics.cli run ' >/dev/null && ! pgrep -f 'ui_semantics.cli run .*subjects-ablation-20260921' >/dev/null; then log "a main-worktree run is alive; refusing to change the lock"; exit 3; fi
  cp docs/ACTIVE-EXECUTION.json "$R/ACTIVE-main-before-rq2-$(date '+%Y%m%d%H%M%S').json"
  cp "$R/ACTIVE-rq2-subjects.json" docs/ACTIVE-EXECUTION.json && log "RQ2 lock installed in the main worktree"
fi
[ -f "$R/inputs/source-versions-$subj.jsonl" ] || bash "$R/run_rq2_subjects.sh" prepare "$subj" || { log "prepare failed"; exit 4; }
for phase in normal register responses sources summarize; do
  bash "$R/run_rq2_subjects.sh" "$phase" "$subj"; rc=$?; log "$phase exit=$rc"
  [ "$rc" = "0" ] || { log "stopping after $phase"; exit 5; }
done
log "all phases done"
