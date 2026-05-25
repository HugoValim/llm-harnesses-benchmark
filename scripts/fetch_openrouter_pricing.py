#!/usr/bin/env python3
"""Compare OpenRouter catalog prices against docs/PRICING.md."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.pricing import (  # noqa: E402
    OPENROUTER_ID_TO_SLUG,
    PricingError,
    load_pricing_table,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def fetch_openrouter_models() -> list[dict]:
    request = urllib.request.Request(
        OPENROUTER_MODELS_URL,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"failed to fetch OpenRouter models: {exc}") from exc
    data = payload.get("data")
    if not isinstance(data, list):
        raise SystemExit("unexpected OpenRouter /models response shape")
    return data


def _price_per_million(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pricing",
        type=Path,
        default=REPO_ROOT / "docs" / "PRICING.md",
        help="Path to PRICING.md (default: docs/PRICING.md).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when OpenRouter prices differ from PRICING.md rows.",
    )
    args = parser.parse_args()

    try:
        table = load_pricing_table(args.pricing)
    except PricingError as exc:
        print(f"PRICING.md error: {exc}", file=sys.stderr)
        return 1

    by_id = {m.get("id"): m for m in fetch_openrouter_models() if m.get("id")}
    drift: list[str] = []

    for or_id, slug in sorted(OPENROUTER_ID_TO_SLUG.items()):
        model = by_id.get(or_id)
        if not model:
            print(f"WARN: OpenRouter model not found: {or_id}")
            continue
        pricing = model.get("pricing") or {}
        or_in = _price_per_million(pricing.get("prompt"))
        or_out = _price_per_million(pricing.get("completion"))
        row = table.get((slug, "ollama_cloud")) or table.get((slug, "openrouter"))
        if row is None:
            print(f"WARN: no PRICING row for slug={slug}")
            continue
        in_ok = or_in is None or abs(or_in - row.input_per_million) < 0.02
        out_ok = or_out is None or abs(or_out - row.output_per_million) < 0.02
        status = "ok" if in_ok and out_ok else "DRIFT"
        print(
            f"{status} {slug}: PRICING {row.input_per_million}/{row.output_per_million} "
            f"OpenRouter {or_in}/{or_out} ({or_id})"
        )
        if status == "DRIFT":
            drift.append(slug)

    if args.check and drift:
        print(
            f"\n{len(drift)} slug(s) drift from OpenRouter: {', '.join(drift)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
