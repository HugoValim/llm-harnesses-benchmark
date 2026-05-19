#!/usr/bin/env python3
"""Print runner_type for an audit_models.json variant slug."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import audit_variant_runner_type  # noqa: E402
from benchmark.util import load_json  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: audit_variant_runner_type.py CONFIG SLUG",
            file=sys.stderr,
        )
        return 2
    config_path = Path(sys.argv[1])
    slug = sys.argv[2]
    try:
        config = load_json(config_path)
        print(audit_variant_runner_type(config, slug))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
