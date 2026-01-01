#!/usr/bin/env bash
# Export + RQ1 initial review of one ablation suite of an added subject (no primary-target step).
# Usage: run_rq1_ablation.sh <subject> <temporal|flat>   (source .env first; never print the key)
set -uo pipefail
subject="${1:?subject}"; config="${2:?temporal|flat}"
cd "$(dirname "$0")/../../.." || exit 1
cfg="scripts/experiments/rq1_tools/configs/${subject}-ablation-${config}.json"
bash scripts/experiments/rq1_tools/export_final_subject.sh "$subject" eval/ui_semantics/subjects-ablation-20260921 "${config}-01" "pytest-export-${config}" | tail -3
.venv/bin/python scripts/experiments/rq1_tools/rq1_extract.py --config "$cfg" | tail -1
.venv/bin/python scripts/experiments/rq1_tools/rq1_review_deepseek.py --config "$cfg" --workers 8 | grep -v "sk-" | tail -2
.venv/bin/python scripts/experiments/rq1_tools/rq1_summarize_deepseek.py --config "$cfg" | tail -1
