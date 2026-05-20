#!/usr/bin/env bash
set -euo pipefail

# Legacy entrypoint — delegates to the full benchmark pipeline.
cd "$(dirname "$0")/.."
exec ./scripts/run_full_benchmark.sh "$@"
