#!/usr/bin/env bash
set -euo pipefail

# Run the Claude Code benchmark against the best available Ollama Cloud models:
#   - Kimi K2.6
#   - Qwen 3.5
#   - GLM 5.1
#   - MiniMax M2.7
#   - DeepSeek V4 Pro
#
# Uses `ollama launch claude` shim so Claude Code routes its tool loop through
# Ollama Cloud rather than Anthropic's native backend.
#
# Example:
#   ./scripts/run_ollama_cloud_claude_benchmark.sh
#   ./scripts/run_ollama_cloud_claude_benchmark.sh --force
#   ./scripts/run_ollama_cloud_claude_benchmark.sh --variant kimi_k2_6_ollama_cloud

cd "$(dirname "$0")/.."

python3 scripts/run_claude_code_benchmark.py \
  --config config/claude_code_ollama_cloud_models.json \
  --results-dir results-claude-code \
  --report docs/report.claude-code-ollama-cloud.md \
  --jobs 0 \
  "$@"
