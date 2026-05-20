#!/usr/bin/env bash
set -euo pipefail

# End-to-end Ollama Cloud benchmark + audit pipeline (audit-v3.1).
#
# Phase 1 - Build: four ``run_benchmark.py`` invocations, all with explicit
# ``--models-config`` / ``--results-dir`` / ``--report`` (same flag order everywhere):
#   1. Shared opencode registry rows -> results/opencode-<slug>/
#   2. Shared codex registry rows -> results/codex-<slug>/
#   3. Cursor subscription baseline — shared cursor registry rows (``agent`` CLI) ->
#      results/cursor-composer_2_5/, results/cursor-composer_2_0/
#   4. Anthropic subscription baseline — shared Claude registry row (plain ``claude``) ->
#      results/claude-claude_opus_4_7/   **leader anchor — required by audit-v3.1**
#
# The leader baselines are not optional: ``audit-v3.1`` calibrates the rubric
# against ``codex_gpt_5_5`` and ``claude_opus_4_7`` (expected 95-97/100). Phase 3's
# Check 5 records ``insufficient-data`` if fewer than 2 leader reports exist.
#
# Phase 2 - Audit (Role 1, audit-v3.1): ``run_audit.py`` with ``$MODELS_CONFIG``;
#   reports under ``$AUDIT_REPORTS_DIR/$AUDITOR_SLUG/<harness>-<slug>/report.md``.
#   Rebuilds ``$AUDIT_REPORTS_DIR/$AUDITOR_SLUG/comparison.md``. The pre-flight below detects any
#   stale ``audit-v3.0`` reports and aborts with instructions, since the meta-analyst
#   excludes v3.0 reports from cross-cell comparison.
#
# Phase 3 - Meta-analysis (Role 2, meta-v3.1): ``run_meta_analysis.py`` reads
#   ``$META_ANALYSIS_INPUT_DIR`` (default: same tree Phase 2 wrote) and dispatches the
#   model ``$META_ANALYSIS_AUDITOR_SLUG`` via harness ``$META_ANALYSIS_HARNESS``
#   (default: the first matching harness in harnesses.json). Writes
#   ``$AUDIT_REPORTS_DIR/$META_ANALYSIS_AUDITOR_SLUG/meta-analysis.md``.
#
# Auditor / meta knobs (all slugs must exist in ``$MODELS_CONFIG``):
#   AUDITOR_SLUG              — Role 1 auditor (required).
#   META_ANALYSIS_AUDITOR_SLUG — Role 2 meta-analyst; default = AUDITOR_SLUG.
#   META_ANALYSIS_HARNESS     — claude | codex; default = first harness mapping for meta slug.
#   META_ANALYSIS_INPUT_DIR   — report tree to read; default = AUDITOR_SLUG.
#
# Example — Kimi via ``ollama launch claude`` for audit + meta:
#   AUDITOR_SLUG=kimi_k2_6_ollama_cloud
#
# Example — Kimi audit on claude harness, meta via ``ollama launch codex``:
#   AUDITOR_SLUG=kimi_k2_6_ollama_cloud
#   META_ANALYSIS_AUDITOR_SLUG=kimi_k2_6_ollama_cloud
#   META_ANALYSIS_HARNESS=codex
#   META_ANALYSIS_INPUT_DIR=kimi_k2_6_ollama_cloud
#
# Forwarded args (``"$@"``) apply only to the build steps; audit + meta use fixed args.
#
# Examples:
#   ./scripts/run_ollama_cloud_benchmark.sh
#   ./scripts/run_ollama_cloud_benchmark.sh --force
#   python3 scripts/run_benchmark.py --harness codex --model codex_gpt_5_5
#
# Cutover note (audit-v3.0 -> audit-v3.1): on first run after the prompt bump,
# delete or move existing audit reports for the active auditor so phase 2
# regenerates them under v3.1. The pre-flight check enforces this.

cd "$(dirname "$0")/.."

# --- Paths -------------------------------------------------------------------
MODELS_CONFIG=config/models.json
HARNESSES_CONFIG=config/harnesses.json
BENCHMARK_RESULTS_DIR=results
AUDIT_REPORTS_DIR=audit-reports

# --- Phase 2 & 3: auditor / meta-analyst (config/models.json) ----------------
# Role 1 auditor slug. Reports -> audit-reports/<slug>/
AUDITOR_SLUG=kimi_k2_6_ollama_cloud
# AUDITOR_SLUG=deepseek_v4_pro_ollama_cloud

# Role 2 meta-analyst slug. Empty = same as AUDITOR_SLUG.
META_ANALYSIS_AUDITOR_SLUG=
# META_ANALYSIS_AUDITOR_SLUG=kimi_k2_6_ollama_cloud

# Role 2 harness: claude | codex. Empty = first harness mapping for the meta slug.
META_ANALYSIS_HARNESS=

# Role 2 input tree (auditor subdir under AUDIT_REPORTS_DIR). Empty = AUDITOR_SLUG.
META_ANALYSIS_INPUT_DIR=

# Return default harness for a model slug. Exits 1 if slug missing.
_audit_model_harness() {
  python3 scripts/audit_model_harness.py "$HARNESSES_CONFIG" "$1"
}

_resolve_meta_config() {
  META_ANALYSIS_AUDITOR_SLUG="${META_ANALYSIS_AUDITOR_SLUG:-$AUDITOR_SLUG}"
  META_ANALYSIS_INPUT_DIR="${META_ANALYSIS_INPUT_DIR:-$AUDITOR_SLUG}"
  local expected_harness
  expected_harness="$(_audit_model_harness "$META_ANALYSIS_AUDITOR_SLUG")"
  if [ -z "${META_ANALYSIS_HARNESS:-}" ]; then
    META_ANALYSIS_HARNESS="$expected_harness"
  elif [ "$META_ANALYSIS_HARNESS" != "$expected_harness" ]; then
    echo "ERROR: META_ANALYSIS_HARNESS=${META_ANALYSIS_HARNESS} but model ${META_ANALYSIS_AUDITOR_SLUG} defaults to harness=${expected_harness} in ${HARNESSES_CONFIG}" >&2
    exit 2
  fi
  case "$META_ANALYSIS_HARNESS" in
    claude|codex) ;;
    *)
      echo "ERROR: META_ANALYSIS_HARNESS must be claude or codex (got ${META_ANALYSIS_HARNESS})" >&2
      exit 2
      ;;
  esac
  echo "Phase 2 auditor: ${AUDITOR_SLUG} -> ${AUDIT_REPORTS_DIR}/${AUDITOR_SLUG}/"
  echo "Phase 3 meta: slug=${META_ANALYSIS_AUDITOR_SLUG} harness=${META_ANALYSIS_HARNESS} input=${META_ANALYSIS_INPUT_DIR}"
}

# Phase 1 - Build ------------------------------------------------------------

python3 scripts/run_benchmark.py \
  --harness opencode \
  --models-config "$MODELS_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --report 'docs/report.ollama-cloud.opencode.md' \
  "$@"

python3 scripts/run_benchmark.py \
  --harness codex \
  --models-config "$MODELS_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --report 'docs/report.ollama-cloud.codex.md' \
  "$@"

python3 scripts/run_benchmark.py \
  --harness cursor \
  --models-config "$MODELS_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --report 'docs/report.ollama-cloud.cursor.md' \
  "$@"

python3 scripts/run_benchmark.py \
  --harness claude \
  --models-config "$MODELS_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --model claude_opus_4_7 \
  --report 'docs/report.ollama-cloud.claude-opus.md' \
  "$@"

# Phase 2 - Audit (Role 1) -----------------------------------------------------

_resolve_meta_config

# Pre-flight: refuse to mix audit-v3.0 reports into a v3.1 meta-analysis.
# run_audit.py caches by result.json, so stale v3.0 report.md files would survive
# a re-run and then get excluded by the meta-analyst (guardrail in meta-v3.1).
AUDITOR_REPORT_DIR="$AUDIT_REPORTS_DIR/$AUDITOR_SLUG"
if [ -d "$AUDITOR_REPORT_DIR" ]; then
  STALE_REPORTS=()
  shopt -s nullglob
  for _report in "$AUDITOR_REPORT_DIR"/*/report.md; do
    if grep -q "Prompt-Version: audit-v3.0" "$_report" 2>/dev/null; then
      STALE_REPORTS+=("$_report")
    fi
  done
  shopt -u nullglob
  if [ "${#STALE_REPORTS[@]}" -gt 0 ]; then
    echo "ERROR: stale audit-v3.0 reports found under $AUDITOR_REPORT_DIR:" >&2
    printf '%s\n' "${STALE_REPORTS[@]}" >&2
    echo "" >&2
    echo "The meta-analysis meta-v3.1 excludes audit-v3.0 reports. Remove them" >&2
    echo "and re-run, or run with --force forwarded only to the audit phase." >&2
    echo "  Example: rm -r $AUDITOR_REPORT_DIR && ./scripts/run_ollama_cloud_benchmark.sh" >&2
    exit 2
  fi
fi

python3 scripts/run_audit.py \
  --models-config "$MODELS_CONFIG" \
  --harness claude \
  --benchmark-results-dir "$BENCHMARK_RESULTS_DIR" \
  --results-dir "$AUDIT_REPORTS_DIR" \
  --model "$AUDITOR_SLUG" \
  --target all \
  -j 3

# Phase 3 - Meta-analysis (Role 2) -------------------------------------------

python3 scripts/run_meta_analysis.py \
  --no-progress-minutes 15 \
  --models-config "$MODELS_CONFIG" \
  --results-dir "$AUDIT_REPORTS_DIR" \
  --harness "$META_ANALYSIS_HARNESS" \
  --model "$META_ANALYSIS_AUDITOR_SLUG" \
  --meta-input-dir "$META_ANALYSIS_INPUT_DIR" \
  --force
