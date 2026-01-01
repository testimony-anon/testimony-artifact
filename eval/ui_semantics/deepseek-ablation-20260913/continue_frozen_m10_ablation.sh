#!/usr/bin/env bash
# Continue M11a-M14 from the frozen M10 union of an ablation case (no provider calls).
# Usage: continue_frozen_m10_ablation.sh <cfg: temporal|flat> <subject> <source-run> <new-run-name> <CASE> [...]
#   source: eval/ui_semantics/deepseek-ablation-20260913/<subject>/<source-run>/cases/<CASE>/union (needs M10/proposal_run_completion.json)
#   writes: eval/ui_semantics/deepseek-ablation-20260913/<subject>/<new-run-name>/cases/<CASE>/union
# The evidence organization of the source run must be passed so the reconstructed M9 matches the frozen M10 input.
set -uo pipefail
cfg="$1"; subject="$2"; source_run="$3"; run_name="$4"; shift 4
cd "$(dirname "$0")/../../.." || exit 1
set -a; source .env; set +a
root="eval/ui_semantics/deepseek-ablation-20260913/$subject"
case "$subject" in
  conduit) adapter=fixtures/adapters/conduit_current_local.json ;;
  rwa)     adapter=fixtures/adapters/rwa_current_local.json ;;
  *) echo "unknown subject $subject" >&2; exit 2 ;;
esac
profile_for() {
  python3 - "$1" <<'PY'
import hashlib, glob, sys
from pathlib import Path
want = hashlib.sha256(Path(sys.argv[1], "inputs/subject/profile.json").read_bytes()).hexdigest()
for path in sorted(glob.glob("fixtures/profiles/*.json")):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() == want:
        print(path); break
PY
}
mkdir -p "$root/$run_name/cases" "$root/$run_name/logs"
ok=0; fail=0
for case_id in "$@"; do
  src="$root/$source_run/cases/$case_id/union"
  if [ ! -f "$src/M10/proposal_run_completion.json" ]; then echo "SKIP $case_id (no completed frozen M10 in $src)"; continue; fi
  target="$root/$run_name/cases/$case_id/union"
  if [ -f "$target/M14/final_calibrated_suite.json" ]; then echo "DONE $case_id (already continued)"; ok=$((ok+1)); continue; fi
  sha=$(shasum -a 256 "$src/M10/proposal_run_completion.json" | cut -d' ' -f1)
  profile=$(profile_for "$src")
  if [ -z "$profile" ]; then echo "FAIL $case_id (no profile fixture matches the frozen copy)"; fail=$((fail+1)); continue; fi
  log="$root/$run_name/logs/$case_id.log"
  echo "RUN  $case_id from $src ($(date '+%H:%M:%S'))"
  if caffeinate -i scripts/uisemtest run --profile "$profile" --adapter "$adapter" \
       --frozen-m10-source "$src" --frozen-m10-completion-sha256 "$sha" \
       --evidence-organization "$cfg" \
       --output-root "$target" --output-level forensic --probe-budget 0 > "$log" 2>&1; then
    [ -f "$root/$run_name/cases/$case_id/run_manifest.json" ] || cp "$(dirname "$src")/run_manifest.json" "$root/$run_name/cases/$case_id/run_manifest.json"
    [ -e "$root/$run_name/cases/$case_id/attempts" ] || ln -s "$(python3 -c "import os;print(os.path.relpath('$(dirname "$src")/attempts', '$root/$run_name/cases/$case_id'))")" "$root/$run_name/cases/$case_id/attempts"
    echo "OK   $case_id retained=$(python3 -c "import json;print(json.load(open('$target/M14/final_calibrated_suite.json')).get('retained_count'))" 2>/dev/null)"; ok=$((ok+1))
  else
    echo "FAIL $case_id (see $log)"; tail -3 "$log" | cut -c1-200; fail=$((fail+1))
  fi
done
echo "summary: ok=$ok fail=$fail"
