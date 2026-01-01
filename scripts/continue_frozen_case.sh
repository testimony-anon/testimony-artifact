#!/usr/bin/env bash
# Continue M11-M14 for one case from its frozen model output (no provider calls).
# Usage: scripts/continue_frozen_case.sh <conduit|rwa> <CASE> [source-run]
#   source-run defaults to the run root that forms the final suite (conduit: m11fix-01; rwa: m11fix-02, rerecord-01, m11fix-01 in that order)
#   output: eval/ui_semantics/reviewer-continuation/<subject>/cases/<CASE>/union
# Requires: subject deployed (INSTALL.md), .env sourced, docs/ACTIVE-EXECUTION.json = docs/active-templates/continue-<subject>.json
set -uo pipefail
subject="$1"; case_id="$2"; source_run="${3:-}"
cd "$(dirname "$0")/.." || exit 1
root="eval/ui_semantics/deepseek-full-20260912/$subject"
case "$subject" in conduit) adapter=fixtures/adapters/conduit_current_local.json; runs="m11fix-01" ;; rwa) adapter=fixtures/adapters/rwa_current_local.json; runs="m11fix-02 rerecord-01 m11fix-01" ;; *) echo "unknown subject" >&2; exit 2 ;; esac
[ -n "$source_run" ] && runs="$source_run"
src=""; for run in $runs; do [ -f "$root/$run/cases/$case_id/union/M10/proposal_run_completion.json" ] && { src="$root/$run/cases/$case_id/union"; break; }; done
[ -n "$src" ] || { echo "no frozen M10 for $case_id under $root ($runs); is the data volume extracted?" >&2; exit 2; }
profile=$(python3 - "$src" <<'PY'
import hashlib, glob, sys
from pathlib import Path
want = hashlib.sha256(Path(sys.argv[1], "inputs/subject/profile.json").read_bytes()).hexdigest()
for path in sorted(glob.glob("fixtures/profiles/*.json")):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() == want: print(path); break
PY
)
[ -n "$profile" ] || { echo "no profile fixture matches the frozen copy in $src/inputs/subject/profile.json" >&2; exit 2; }
sha=$(shasum -a 256 "$src/M10/proposal_run_completion.json" | cut -d' ' -f1)
target="eval/ui_semantics/reviewer-continuation/$subject/cases/$case_id/union"; mkdir -p "$(dirname "$target")"
echo "continuing $case_id from $src with $profile -> $target"
exec scripts/uisemtest run --profile "$profile" --adapter "$adapter" --frozen-m10-source "$src" --frozen-m10-completion-sha256 "$sha" \
  --output-root "$target" --output-level forensic --probe-budget 0
