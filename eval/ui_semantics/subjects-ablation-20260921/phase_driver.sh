#!/usr/bin/env bash
# Phase driver v2 for the RQ3 ablation of the added subjects (2026-09-21, author authorized).
# Phase 1 (running): umami + ghost temporal.  Waits until no ablation run is alive AND no RQ2 run of paperless is alive
# (RQ2-lite for Paperless runs now, while its application instance is otherwise idle), then
#   phase 2: installs ACTIVE-ablation-phase2.json in the paper-code worktree and launches umami flat + ghost flat +
#            paperless temporal (32-case suite);
#   phase 3: installs ACTIVE-ablation-phase3.json and launches paperless flat.
# The worktree lock is only ever replaced while no run of the worktree is alive.
set -uo pipefail
W=<PAPER_CODE_WORKTREE>
M=<ARTIFACT_ROOT>
AB=$M/eval/ui_semantics/subjects-ablation-20260921
log() { echo "$(date '+%F %H:%M:%S') $*" >> "$AB/phase-driver.log"; }
alive() { pgrep -f 'ui_semantics.cli run .*subjects-ablation-20260921' | wc -l | tr -d ' '; }
rq2_paperless_alive() { pgrep -f 'rq2_subjects.py .* --subject paperless' | wc -l | tr -d ' '; }
wait_idle() { while [ "$(alive)" != "0" ]; do sleep 60; done; }
log "driver v2 started; alive=$(alive) rq2_paperless_alive=$(rq2_paperless_alive)"
while ! grep -q '^temporal finished' "$AB/run-temporal.status" 2>/dev/null; do sleep 60; done
wait_idle
while [ "$(rq2_paperless_alive)" != "0" ] || pgrep -f 'run_rq2_subjects.sh all paperless' >/dev/null; do sleep 60; done
sleep 15; [ "$(alive)" = "0" ] || { log "runs still alive after temporal finished; abort"; exit 1; }
log "phase 1 done and RQ2 paperless finished; installing phase-2 lock"
cp "$AB/ACTIVE-ablation-phase2.json" "$W/docs/ACTIVE-EXECUTION.json" && log "phase-2 lock installed"
( bash "$AB/run_ablation_subject.sh" flat umami umami_modular/inventory.json ) & u=$!
( bash "$AB/run_ablation_subject.sh" flat ghost ghost_modular/inventory.json ) & g=$!
( bash "$AB/run_ablation_subject.sh" temporal paperless paperless_modular/inventory-ablation.json ) & p=$!
log "phase 2 launched (umami flat, ghost flat, paperless temporal)"
wait $u; wait $g; wait $p
wait_idle; sleep 15; [ "$(alive)" = "0" ] || { log "runs still alive after phase 2; abort"; exit 1; }
log "phase 2 done: $(tail -3 "$AB/run-flat.status" | tr '\n' ';') $(grep paperless "$AB/run-temporal.status" | tail -1)"
cp "$AB/ACTIVE-ablation-phase3.json" "$W/docs/ACTIVE-EXECUTION.json" && log "phase-3 lock installed"
bash "$AB/run_ablation_subject.sh" flat paperless paperless_modular/inventory-ablation.json
log "phase 3 done: $(grep paperless "$AB/run-flat.status" | tail -1)"
log "all ablation phases finished"
