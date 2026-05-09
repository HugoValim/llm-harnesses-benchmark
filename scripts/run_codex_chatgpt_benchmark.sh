#!/usr/bin/env bash
set -euo pipefail

# Run the Codex CLI benchmark against ChatGPT-linked models (plain `codex`, no Ollama).
# Models are defined in config/codex_chatgpt_models.json (e.g. gpt-5.5, gpt-5.4, gpt-5.3-codex).
#
# Prerequisites: `codex` on PATH and `codex login` (ChatGPT OAuth) as needed for your plan.
#
# Example:
#   ./scripts/run_codex_chatgpt_benchmark.sh
#   ./scripts/run_codex_chatgpt_benchmark.sh --force
#   ./scripts/run_codex_chatgpt_benchmark.sh --model codex_gpt_5_5
#   ./scripts/run_codex_chatgpt_benchmark.sh --jobs 1

cd "$(dirname "$0")/.."

python3 scripts/run_benchmark.py --harness codex \
  --config config/codex_chatgpt_models.json \
  --report docs/report.codex.chatgpt.md \
  "$@"
