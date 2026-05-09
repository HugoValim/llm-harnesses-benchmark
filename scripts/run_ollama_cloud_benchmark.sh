#!/usr/bin/env bash
set -euo pipefail

# Run both Claude Code and Codex benchmarks against the shared Ollama Cloud model set:
#   - Kimi K2.6, Qwen 3.5, GLM 5.1, MiniMax M2.7, DeepSeek V4 Pro
#
# Claude uses `ollama launch claude`; Codex uses `ollama launch codex`.
# Results land under results/claude-<slug>/ and results/codex-<slug>/.
#
# Example:
#   ./scripts/run_ollama_cloud_benchmark.sh
#   ./scripts/run_ollama_cloud_benchmark.sh --force
#   ./scripts/run_ollama_cloud_benchmark.sh --variant qwen3_5_ollama_cloud --model qwen3_5_ollama_cloud

cd "$(dirname "$0")/.."

python3 scripts/run_benchmark.py --harness claude \
  --config config/claude_code_ollama_cloud_models.json \
  --report docs/report.ollama-cloud.claude.md \
  "$@"

python3 scripts/run_benchmark.py --harness codex \
  --config config/codex_ollama_cloud_models.json \
  --report docs/report.ollama-cloud.codex.md \
  "$@"

python3 scripts/run_benchmark.py --harness opencode \
  --config config/claude_code_ollama_cloud_models.json \
  --report docs/report.ollama-cloud.claude.md \
  "$@"
