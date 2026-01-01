#!/usr/bin/env bash
# Export + RQ1 initial review pipeline for one subject (DeepSeek calls for the review and the target mapping).
# Usage: run_rq1_subject.sh <subject> <runs_root> <runs-comma-separated>
#   e.g. run_rq1_subject.sh vikunja eval/ui_semantics/vikunja-20260921 m11fix-02,full-01
# Requires LLM_BASE_URL / LLM_API_KEY in the environment (source .env first; never print them).
set -uo pipefail
subject="${1:?subject}"; runs_root="${2:?runs_root}"; runs="${3:?runs}"
cd "$(dirname "$0")/../../.." || exit 1
cfg="scripts/experiments/rq1_tools/configs/${subject}-20260921.json"
bash scripts/experiments/rq1_tools/export_final_subject.sh "$subject" "$runs_root" "$runs" | tail -3
.venv/bin/python scripts/experiments/rq1_tools/rq1_extract.py --config "$cfg" | tail -1
.venv/bin/python scripts/experiments/rq1_tools/rq1_review_deepseek.py --config "$cfg" --workers 8 | grep -v "sk-" | tail -2
.venv/bin/python scripts/experiments/rq1_tools/rq1_summarize_deepseek.py --config "$cfg" | tail -1
.venv/bin/python scripts/experiments/rq1_tools/rq1_targets_deepseek.py --config "$cfg" --workers 6 | grep -v "sk-" | tail -2
.venv/bin/python scripts/experiments/rq1_tools/rq1_summarize_deepseek.py --config "$cfg" | tail -1
grep -A4 "## Primary-target results" "docs/design/subjects-expansion-20260919/rq1-audit-${subject}/summary.md" | tail -3
