#!/usr/bin/env bash
set -euo pipefail

# End-to-end Ollama Cloud benchmark + audit pipeline (audit-v3.1).
#
# Phase 1 - Build: six ``run_benchmark.py`` invocations, all with explicit
# ``--config`` / ``--results-dir`` / ``--report`` (same flag order everywhere):
#   1–3. Ollama Cloud matrix — ``$OLLAMA_CLOUD_CONFIG`` expanded per harness
#        (``ollama launch {claude,codex,opencode}``) -> results/{claude,codex,opencode}-<slug>/
#   4. Cursor subscription baseline — ``$CURSOR_CONFIG`` (``agent`` CLI) ->
#      results/cursor-composer_2_5/, results/cursor-composer_2_0/
#   5. Anthropic subscription baseline — ``$CLAUDE_CODE_CONFIG`` (plain ``claude``) ->
#      results/claude-claude_opus_4_7/   **leader anchor — required by audit-v3.1**
#   6. ChatGPT-linked Codex baseline — ``$CODEX_CHATGPT_CONFIG`` (plain ``codex``) ->
#      results/codex-codex_gpt_5_5/      **leader anchor — required by audit-v3.1**
#
# The two leader baselines are not optional: ``audit-v3.1`` calibrates the rubric
# against ``gpt_5_5`` and ``claude_opus_4_7`` (expected 95-97/100). Phase 3's
# Check 5 records ``insufficient-data`` if fewer than 2 leader reports exist.
#
# Phase 2 - Audit (Role 1, audit-v3.1): ``run_audit.py`` with ``$AUDIT_MODELS_CONFIG``;
#   reports under ``$AUDIT_REPORTS_DIR/$AUDITOR_SLUG/<harness>-<slug>/report.md``.
#   Rebuilds ``$AUDIT_REPORTS_DIR/comparison.md``. The pre-flight below detects any
#   stale ``audit-v3.0`` reports and aborts with instructions, since the meta-analyst
#   excludes v3.0 reports from cross-cell comparison.
#
# Phase 3 - Meta-analysis (Role 2, meta-v3.1): ``run_meta_analysis.py`` reads
#   ``$META_ANALYSIS_INPUT_DIR`` (default: same tree Phase 2 wrote) and dispatches the
#   variant ``$META_ANALYSIS_AUDITOR_SLUG`` via harness ``$META_ANALYSIS_HARNESS``
#   (default: that variant's ``runner_type`` in audit_models.json). Writes
#   ``$AUDIT_REPORTS_DIR/meta-analysis.md``.
#
# Auditor / meta knobs (all slugs must exist in ``$AUDIT_MODELS_CONFIG``):
#   AUDITOR_SLUG              — Role 1 auditor (required).
#   META_ANALYSIS_AUDITOR_SLUG — Role 2 meta-analyst; default = AUDITOR_SLUG.
#   META_ANALYSIS_HARNESS     — claude | codex | ollama; default = runner_type of meta slug.
#   META_ANALYSIS_INPUT_DIR   — report tree to read; default = AUDITOR_SLUG.
#
# Example — Kimi via ``ollama launch claude`` for audit + meta:
#   AUDITOR_SLUG=kimi_k2_6_ollama_cloud
#
# Example — Kimi audit on claude harness, meta via ``ollama launch codex``:
#   AUDITOR_SLUG=kimi_k2_6_ollama_cloud
#   META_ANALYSIS_AUDITOR_SLUG=kimi_k2_6_ollama_codex
#   META_ANALYSIS_HARNESS=ollama
#   META_ANALYSIS_INPUT_DIR=kimi_k2_6_ollama_cloud
#
# Forwarded args (``"$@"``) apply only to the six build steps; audit + meta use fixed args.
#
# Examples:
#   ./scripts/run_ollama_cloud_benchmark.sh
#   ./scripts/run_ollama_cloud_benchmark.sh --force
#   ./scripts/run_ollama_cloud_benchmark.sh --variant qwen3_5_ollama_cloud --model qwen3_5_ollama_cloud
#
# Cutover note (audit-v3.0 -> audit-v3.1): on first run after the prompt bump,
# delete or move existing audit reports for the active auditor so phase 2
# regenerates them under v3.1. The pre-flight check enforces this.

cd "$(dirname "$0")/.."

# --- Paths -------------------------------------------------------------------
OLLAMA_CLOUD_CONFIG=config/ollama_cloud_models.json
CURSOR_CONFIG=config/cursor_models.json
CLAUDE_CODE_CONFIG=config/claude_code_models.json
CODEX_CHATGPT_CONFIG=config/codex_chatgpt_models.json
AUDIT_MODELS_CONFIG=config/audit_models.json
BENCHMARK_RESULTS_DIR=results
AUDIT_REPORTS_DIR=audit-reports

# --- Phase 2 & 3: auditor / meta-analyst (config/audit_models.json) ----------
# Role 1 auditor slug. Reports -> audit-reports/<slug>/
AUDITOR_SLUG=kimi_k2_6_ollama_cloud
# AUDITOR_SLUG=deepseek_v4_pro_ollama_codex

# Role 2 meta-analyst slug. Empty = same as AUDITOR_SLUG.
META_ANALYSIS_AUDITOR_SLUG=
# META_ANALYSIS_AUDITOR_SLUG=kimi_k2_6_ollama_codex

# Role 2 harness: claude | codex | ollama. Empty = runner_type of meta slug in AUDIT_MODELS_CONFIG.
META_ANALYSIS_HARNESS=

# Role 2 input tree (auditor subdir under AUDIT_REPORTS_DIR). Empty = AUDITOR_SLUG.
META_ANALYSIS_INPUT_DIR=

# Return runner_type for a variant slug (default claude). Exits 1 if slug missing.
_audit_variant_runner_type() {
  python3 - "$AUDIT_MODELS_CONFIG" "$1" <<'PY'
import json
import sys

path, slug = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    config = json.load(f)
for variant in config.get("variants", []):
    if variant.get("skip_by_default"):
        continue
    if variant.get("slug") == slug:
        print(variant.get("runner_type", "claude"))
        raise SystemExit(0)
print(f"ERROR: slug {slug!r} not found in {path}", file=sys.stderr)
raise SystemExit(1)
PY
}

_resolve_meta_config() {
  META_ANALYSIS_AUDITOR_SLUG="${META_ANALYSIS_AUDITOR_SLUG:-$AUDITOR_SLUG}"
  META_ANALYSIS_INPUT_DIR="${META_ANALYSIS_INPUT_DIR:-$AUDITOR_SLUG}"
  local expected_harness
  expected_harness="$(_audit_variant_runner_type "$META_ANALYSIS_AUDITOR_SLUG")"
  if [ -z "${META_ANALYSIS_HARNESS:-}" ]; then
    META_ANALYSIS_HARNESS="$expected_harness"
  elif [ "$META_ANALYSIS_HARNESS" != "$expected_harness" ]; then
    echo "ERROR: META_ANALYSIS_HARNESS=${META_ANALYSIS_HARNESS} but variant ${META_ANALYSIS_AUDITOR_SLUG} has runner_type=${expected_harness} in ${AUDIT_MODELS_CONFIG}" >&2
    exit 2
  fi
  case "$META_ANALYSIS_HARNESS" in
    claude|codex|ollama) ;;
    *)
      echo "ERROR: META_ANALYSIS_HARNESS must be claude, codex, or ollama (got ${META_ANALYSIS_HARNESS})" >&2
      exit 2
      ;;
  esac
  echo "Phase 2 auditor: ${AUDITOR_SLUG} -> ${AUDIT_REPORTS_DIR}/${AUDITOR_SLUG}/"
  echo "Phase 3 meta: slug=${META_ANALYSIS_AUDITOR_SLUG} harness=${META_ANALYSIS_HARNESS} input=${META_ANALYSIS_INPUT_DIR}"
}

# Phase 1 - Build ------------------------------------------------------------

python3 scripts/run_benchmark.py \
  --harness claude \
  --config "$OLLAMA_CLOUD_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --report docs/report.ollama-cloud.claude.md \
  "$@"

python3 scripts/run_benchmark.py \
  --harness codex \
  --config "$OLLAMA_CLOUD_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --report docs/report.ollama-cloud.codex.md \
  "$@"

python3 scripts/run_benchmark.py \
  --harness opencode \
  --config "$OLLAMA_CLOUD_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --report docs/report.ollama-cloud.opencode.md \
  "$@"

python3 scripts/run_benchmark.py \
  --harness cursor \
  --config "$CURSOR_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --report docs/report.ollama-cloud.cursor.md \
  "$@"

python3 scripts/run_benchmark.py \
  --harness claude \
  --config "$CLAUDE_CODE_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --variant claude_opus_4_7 \
  --report docs/report.ollama-cloud.claude-opus.md \
  "$@"

python3 scripts/run_benchmark.py \
  --harness codex \
  --config "$CODEX_CHATGPT_CONFIG" \
  --results-dir "$BENCHMARK_RESULTS_DIR" \
  --model codex_gpt_5_5 \
  --report docs/report.ollama-cloud.codex-gpt-5-5.md \
  "$@"

# Phase 2 - Audit (Role 1) -----------------------------------------------------

_resolve_meta_config

# Pre-flight: refuse to mix audit-v3.0 reports into a v3.1 meta-analysis.
# run_audit.py caches by result.json, so stale v3.0 report.md files would survive
# a re-run and then get excluded by the meta-analyst (guardrail in meta-v3.1).
AUDITOR_REPORT_DIR="$AUDIT_REPORTS_DIR/$AUDITOR_SLUG"
if [ -d "$AUDITOR_REPORT_DIR" ]; then
  STALE_REPORTS=$(grep -l "Prompt-Version: audit-v3.0" "$AUDITOR_REPORT_DIR"/*/report.md 2>/dev/null || true)
  if [ -n "$STALE_REPORTS" ]; then
    echo "ERROR: stale audit-v3.0 reports found under $AUDITOR_REPORT_DIR:" >&2
    echo "$STALE_REPORTS" >&2
    echo "" >&2
    echo "The meta-analysis (meta-v3.1) excludes audit-v3.0 reports. Remove them" >&2
    echo "and re-run, or run with --force forwarded only to the audit phase." >&2
    echo "  Example: rm -r $AUDITOR_REPORT_DIR && ./scripts/run_ollama_cloud_benchmark.sh" >&2
    exit 2
  fi
fi

python3 scripts/run_audit.py \
  --audit-config "$AUDIT_MODELS_CONFIG" \
  --benchmark-results-dir "$BENCHMARK_RESULTS_DIR" \
  --results-dir "$AUDIT_REPORTS_DIR" \
  --auditor "$AUDITOR_SLUG" \
  --target all \
  -j 3

# Phase 3 - Meta-analysis (Role 2) -------------------------------------------

python3 scripts/run_meta_analysis.py \
  --audit-config "$AUDIT_MODELS_CONFIG" \
  --results-dir "$AUDIT_REPORTS_DIR" \
  --meta-harness "$META_ANALYSIS_HARNESS" \
  --meta-model "$META_ANALYSIS_AUDITOR_SLUG" \
  --meta-input-dir "$META_ANALYSIS_INPUT_DIR"
