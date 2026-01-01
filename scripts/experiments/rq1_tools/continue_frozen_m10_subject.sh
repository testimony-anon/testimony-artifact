#!/usr/bin/env bash
# Continue M11a-M14 from the frozen M10 union of each case (no provider calls) for one subject.
# Usage: continue_frozen_m10_subject.sh <subject> <runs_root> <source-run> <new-run> <CASE> [<CASE> ...]
#   e.g. continue_frozen_m10_subject.sh vikunja eval/ui_semantics/vikunja-20260921 full-01 m11fix-01 L1-PROJECT-01
#   writes: <runs_root>/<subject>/<new-run>/cases/<CASE>/union (+ run_manifest.json copy and attempts symlink)
# Parameterised counterpart of the frozen eval/ui_semantics/deepseek-full-20260912/continue_frozen_m10.sh
# (same run flags); the profile is the fixture whose bytes match the frozen copy in the source union.
set -uo pipefail
subject="$1"; runs_root="$2"; src_run="$3"; run_name="$4"; shift 4
cd "$(dirname "$0")/../../.." || exit 1
if [ -f .env ]; then set -a; source .env; set +a; fi
export PYTHONPATH=src NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1 PYTHONDONTWRITEBYTECODE=1
adapter="fixtures/adapters/${subject}_current_local.json"
root="$runs_root/$subject"
profile_for() {
  .venv/bin/python - "$1" <<'PY'
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
  src="$root/$src_run/cases/$case_id/union"
  if [ ! -f "$src/M10/proposal_run_completion.json" ]; then echo "SKIP $case_id (no completed frozen M10)"; continue; fi
  target="$root/$run_name/cases/$case_id/union"
  if [ -f "$target/M14/final_calibrated_suite.json" ]; then echo "DONE $case_id (already continued)"; ok=$((ok+1)); continue; fi
  sha=$(shasum -a 256 "$src/M10/proposal_run_completion.json" | cut -d' ' -f1)
  profile=$(profile_for "$src")
  if [ -z "$profile" ]; then echo "FAIL $case_id (no profile fixture matches the frozen copy)"; fail=$((fail+1)); continue; fi
  log="$root/$run_name/logs/$case_id.log"
  echo "RUN  $case_id from $src ($(date '+%H:%M:%S'))"
  if caffeinate -i scripts/uisemtest run --profile "$profile" --adapter "$adapter" \
       --frozen-m10-source "$src" --frozen-m10-completion-sha256 "$sha" \
       --output-root "$target" --output-level forensic --probe-budget 0 > "$log" 2>&1; then
    [ -f "$root/$run_name/cases/$case_id/run_manifest.json" ] || cp "$(dirname "$src")/run_manifest.json" "$root/$run_name/cases/$case_id/run_manifest.json"
    [ -e "$root/$run_name/cases/$case_id/attempts" ] || ln -s "$(.venv/bin/python -c "import os;print(os.path.relpath('$(dirname "$src")/attempts', '$root/$run_name/cases/$case_id'))")" "$root/$run_name/cases/$case_id/attempts"
    echo "OK   $case_id retained=$(.venv/bin/python -c "import json;print(json.load(open('$target/M14/final_calibrated_suite.json')).get('retained_count'))" 2>/dev/null) ($(date '+%H:%M:%S'))"; ok=$((ok+1))
  else
    echo "FAIL $case_id (see $log)"; tail -3 "$log" | cut -c1-200; fail=$((fail+1))
  fi
done
echo "summary: ok=$ok fail=$fail"
