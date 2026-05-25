#!/usr/bin/env python3
"""Verify docs/PRICING.md covers every slug in config/models.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.pricing import PricingError, assert_registry_coverage  # noqa: E402
from benchmark.util import load_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models-config",
        type=Path,
        default=REPO_ROOT / "config" / "models.json",
    )
    parser.add_argument(
        "--pricing",
        type=Path,
        default=REPO_ROOT / "docs" / "PRICING.md",
    )
    args = parser.parse_args()
    models = load_json(args.models_config).get("models", [])
    if not isinstance(models, list):
        print("models.json has no models list", file=sys.stderr)
        return 1
    try:
        assert_registry_coverage(models, pricing_path=args.pricing)
    except PricingError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"OK: all {len(models)} registry slugs covered by {args.pricing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
