#!/usr/bin/env python3
"""Run benchmark retries from a JSON target list (meta-analysis [retry] items)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = REPO_ROOT / "config" / "retry_targets_run_03.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--targets",
        type=Path,
        default=DEFAULT_TARGETS,
        help=f"Retry manifest JSON (default: {DEFAULT_TARGETS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing",
    )
    args = parser.parse_args()
    payload = __import__("json").loads(args.targets.read_text(encoding="utf-8"))
    run_id = payload["run_id"]
    reason = payload.get("reason", "")
    cells = payload.get("cells", [])
    if not cells:
        print(f"No cells in {args.targets}", file=sys.stderr)
        return 1
    print(f"Retry manifest: {args.targets}")
    if reason:
        print(f"Reason: {reason}")
    exit_code = 0
    for cell in cells:
        harness = cell["harness"]
        model = cell["model"]
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_benchmark.py"),
            "--run-id",
            run_id,
            "--harness",
            harness,
            "--model",
            model,
        ]
        print(f"\n>>> {' '.join(cmd)}")
        if args.dry_run:
            continue
        result = subprocess.run(cmd, cwd=REPO_ROOT)
        if result.returncode != 0:
            exit_code = result.returncode
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
