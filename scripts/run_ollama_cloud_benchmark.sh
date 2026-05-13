#!/usr/bin/env bash
set -euo pipefail

# End-to-end Ollama Cloud benchmark + audit pipeline.
#
# Phase 1 - Build: run the Claude Code, Codex, and OpenCode benchmarks against
# the shared Ollama Cloud model set in config/ollama_cloud_models.json (Kimi K2.6,
# Qwen 3.5, GLM 5.1, MiniMax M2.7, DeepSeek V4 Pro, DeepSeek V4 Flash, Gemma 4,
# Nemotron 3 Super, Gemini 3 Flash preview). Outputs land under:
#   Claude   uses `ollama launch claude`   -> results/claude-<slug>/
#   Codex    uses `ollama launch codex`    -> results/codex-<slug>/
#   OpenCode uses `ollama launch opencode` -> results/opencode-<slug>/
#
# Phase 2 - Audit (Role 1): dispatch the Kimi K2.6 auditor against every
# `results/<harness>-<slug>/project` and write per-target rubric reports to
# `audit-reports/kimi_k2_6_auditor/<harness>-<slug>/report.md`. Also rebuilds
# `audit-reports/comparison.md`.
#
# Phase 3 - Meta-analysis (Role 2): dispatch Kimi K2.6 as the meta-analyst
# over every audit report and write `audit-reports/meta-analysis.md`
# (best-harness, best-model, cost, dimension verdicts).
#
# Forwarded args (`"$@"`) target the build phase only; audit + meta-analysis
# use fixed canonical args so the end-to-end pipeline is deterministic.
#
# Examples:
#   ./scripts/run_ollama_cloud_benchmark.sh
#   ./scripts/run_ollama_cloud_benchmark.sh --force
#   ./scripts/run_ollama_cloud_benchmark.sh --variant qwen3_5_ollama_cloud --model qwen3_5_ollama_cloud

cd "$(dirname "$0")/.."

# Phase 2/3: must match ``slug`` in config/audit_models.json for this pipeline.
# OLLAMA_CLOUD_AUDITOR_SLUG=deepseek_v4_pro_ollama_codex_auditor  # DeepSeek V4 Pro via `ollama launch codex`
OLLAMA_CLOUD_AUDITOR_SLUG=kimi_k2_6_ollama_codex_auditor

# Phase 1 - Build ------------------------------------------------------------

python3 scripts/run_benchmark.py --harness claude \
  --config config/ollama_cloud_models.json \
  --report docs/report.ollama-cloud.claude.md \
  "$@"

python3 scripts/run_benchmark.py --harness codex \
  --config config/ollama_cloud_models.json \
  --report docs/report.ollama-cloud.codex.md \
  "$@"

python3 scripts/run_benchmark.py --harness opencode \
  --config config/ollama_cloud_models.json \
  --report docs/report.ollama-cloud.opencode.md \
  "$@"

# Phase 2 - Audit (Role 1) ---------------------------------------------------
# Auditor from $OLLAMA_CLOUD_AUDITOR_SLUG (see config/audit_models.json) runs
# every discovered results/<harness>-<slug>/project against
# prompts/audit_prompt_template.txt. -j 3 mirrors run_ollama_cloud_audit.sh.

python3 scripts/run_audit.py \
  --auditor "$OLLAMA_CLOUD_AUDITOR_SLUG" \
  --target all \
  -j 3


# Phase 3 - Meta-analysis (Role 2) -------------------------------------------
# Same harness/model as the auditor reads reports under
# audit-reports/$OLLAMA_CLOUD_AUDITOR_SLUG/ (``--meta-input-dir`` avoids
# discover skipping that tree when no ``*/report.md`` exists yet) and writes
# audit-reports/meta-analysis.md.

python3 scripts/run_meta_analysis.py \
  --meta-harness ollama \
  --meta-model "$OLLAMA_CLOUD_AUDITOR_SLUG" \
  --meta-input-dir "$OLLAMA_CLOUD_AUDITOR_SLUG"
