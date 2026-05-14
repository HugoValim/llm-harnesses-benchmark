#!/usr/bin/env bash
set -euo pipefail

# End-to-end Ollama Cloud benchmark + audit pipeline.
#
# Phase 1 - Build: five ``run_benchmark.py`` invocations, all with explicit
# ``--config`` / ``--results-dir`` / ``--report`` (same flag order everywhere):
#   1–3. Ollama Cloud matrix — ``$OLLAMA_CLOUD_CONFIG`` expanded per harness
#        (``ollama launch {claude,codex,opencode}``) -> results/{claude,codex,opencode}-<slug>/
#   4. Anthropic subscription baseline — ``$CLAUDE_CODE_CONFIG`` (plain ``claude``) ->
#      results/claude-claude_opus_4_7/
#   5. ChatGPT-linked Codex baseline — ``$CODEX_CHATGPT_CONFIG`` (plain ``codex``) ->
#      results/codex-codex_gpt_5_5/
#
# Phase 2 - Audit (Role 1): ``run_audit.py`` with ``$AUDIT_MODELS_CONFIG``; reports under
#   ``$AUDIT_REPORTS_DIR/$OLLAMA_CLOUD_AUDITOR_SLUG/<harness>-<slug>/report.md``.
#   Rebuilds ``$AUDIT_REPORTS_DIR/comparison.md``.
#
# Phase 3 - Meta-analysis (Role 2): ``run_meta_analysis.py`` reads the same auditor tree
# and writes ``$AUDIT_REPORTS_DIR/meta-analysis.md``.
#
# Forwarded args (``"$@"``) apply only to the five build steps; audit + meta use fixed args.
#
# Examples:
#   ./scripts/run_ollama_cloud_benchmark.sh
#   ./scripts/run_ollama_cloud_benchmark.sh --force
#   ./scripts/run_ollama_cloud_benchmark.sh --variant qwen3_5_ollama_cloud --model qwen3_5_ollama_cloud

cd "$(dirname "$0")/.."

# Phase 2/3: slug must exist in ``$AUDIT_MODELS_CONFIG`` (see config/audit_models.json).
# OLLAMA_CLOUD_AUDITOR_SLUG=deepseek_v4_pro_ollama_codex
OLLAMA_CLOUD_AUDITOR_SLUG=kimi_k2_6_ollama_codex

OLLAMA_CLOUD_CONFIG=config/ollama_cloud_models.json
CLAUDE_CODE_CONFIG=config/claude_code_models.json
CODEX_CHATGPT_CONFIG=config/codex_chatgpt_models.json
AUDIT_MODELS_CONFIG=config/audit_models.json
BENCHMARK_RESULTS_DIR=results
AUDIT_REPORTS_DIR=audit-reports

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

python3 scripts/run_audit.py \
  --audit-config "$AUDIT_MODELS_CONFIG" \
  --benchmark-results-dir "$BENCHMARK_RESULTS_DIR" \
  --results-dir "$AUDIT_REPORTS_DIR" \
  --auditor "$OLLAMA_CLOUD_AUDITOR_SLUG" \
  --target all \
  -j 3

# Phase 3 - Meta-analysis (Role 2) -------------------------------------------

python3 scripts/run_meta_analysis.py \
  --audit-config "$AUDIT_MODELS_CONFIG" \
  --results-dir "$AUDIT_REPORTS_DIR" \
  --meta-harness ollama \
  --meta-model "$OLLAMA_CLOUD_AUDITOR_SLUG" \
  --meta-input-dir "$OLLAMA_CLOUD_AUDITOR_SLUG"
