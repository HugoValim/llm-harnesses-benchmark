#!/usr/bin/env bash
set -euo pipefail

# Thin wrapper — pipeline logic lives in scripts/run_full_benchmark.py
cd "$(dirname "$0")/.."
exec python3 scripts/run_full_benchmark.py "$@"
