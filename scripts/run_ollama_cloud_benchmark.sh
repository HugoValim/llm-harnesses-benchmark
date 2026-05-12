#!/usr/bin/env bash
set -euo pipefail

# End-to-end Ollama Cloud benchmark + audit pipeline.
#
# Phase 1 - Build: run the Claude Code, Codex, and OpenCode benchmarks against
# the shared Ollama Cloud model set (Kimi K2.6, Qwen 3.5, GLM 5.1,
# MiniMax M2.7, DeepSeek V4 Pro). Outputs land under:
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

# Phase 1 - Build ------------------------------------------------------------

# python3 scripts/run_benchmark.py --harness claude \
#   --config config/claude_code_ollama_cloud_models.json \
#   --report docs/report.ollama-cloud.claude.md \
#   "$@"

# python3 scripts/run_benchmark.py --harness ollama \
#   --report docs/report.ollama-cloud.codex.md \
#   "$@"

# python3 scripts/run_benchmark.py --harness opencode \
#   --config config/opencode_ollama_cloud_models.json \
#   --report docs/report.ollama-cloud.opencode.md \
#   "$@"

# Phase 2 - Audit (Role 1) ---------------------------------------------------
# DeepSeek V4 Pro via `ollama launch codex` audits every discovered
# results/<harness>-<slug>/project against prompts/audit_prompt_template.txt.
# -j 3 mirrors run_ollama_cloud_audit.sh.

python3 scripts/run_audit.py \
  --auditor deepseek_v4_pro_ollama_codex_auditor \
  --target all \
  -j 3

# Phase 3 - Meta-analysis (Role 2) -------------------------------------------
# DeepSeek V4 Pro via `ollama launch codex` reads every
# audit-reports/deepseek_v4_pro_ollama_codex_auditor/*/report.md and writes
# audit-reports/meta-analysis.md (best-harness, best-model, cost verdicts).

python3 scripts/run_meta_analysis.py \
  --meta-harness ollama \
  --meta-model deepseek_v4_pro_ollama_codex_auditor
