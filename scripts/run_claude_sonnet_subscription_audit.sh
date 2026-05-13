#!/usr/bin/env bash
set -euo pipefail

# Audit (Role 1) + meta-analysis (Role 2) using Claude Max / subscription via
# Claude Code CLI — Sonnet 4.6 (no ``ollama launch``).
#
# Prerequisites: ``claude`` on PATH and subscription auth (``claude login``).
# Variant slug must match ``config/audit_models.json`` (runner_type: claude).
#
# Outputs:
#   audit-reports/<AUDITOR_SLUG>/<harness>-<slug>/report.md
#   audit-reports/comparison.md (rebuilt by run_audit.py / run_meta_analysis.py)
#   audit-reports/meta-analysis.md
#
# ``--meta-input-dir`` scopes Role 2 to this auditor only (same pattern as
# scripts/run_ollama_cloud_benchmark.sh for the Ollama Cloud auditor).
#
# Examples:
#   ./scripts/run_claude_sonnet_subscription_audit.sh
#   AUDITOR_SLUG=claude_opus_4_7 ./scripts/run_claude_sonnet_subscription_audit.sh

cd "$(dirname "$0")/.."

AUDITOR_SLUG="${AUDITOR_SLUG:-claude_sonnet_4_6}"

# Phase 2 - Audit (Role 1) -----------------------------------------------------

python3 scripts/run_audit.py \
  --auditor "$AUDITOR_SLUG" \
  --target all \
  -j 3

# Phase 3 - Meta-analysis (Role 2) -------------------------------------------

python3 scripts/run_meta_analysis.py \
  --meta-harness claude \
  --meta-model "$AUDITOR_SLUG" \
  --meta-input-dir "$AUDITOR_SLUG"
