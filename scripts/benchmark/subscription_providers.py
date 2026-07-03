"""Serialize concurrent benchmark runs that share one CLI subscription."""

from __future__ import annotations

from typing import Any

# Providers whose models authenticate through a single shared subscription
# session (``claude login``, ``codex login``, ``agent login``). Only one such
# model per provider may run at a time across parallel dispatch pools.
SUBSCRIPTION_PROVIDERS = frozenset({"anthropic", "openai", "cursor"})


def subscription_provider(model_row: dict[str, Any]) -> str | None:
    """Return the provider key when ``model_row`` uses subscription auth."""
    provider = model_row.get("provider", "")
    if provider in SUBSCRIPTION_PROVIDERS:
        return str(provider)
    return None


def build_job_concurrency_keys(
    *,
    harness: str,
    model_row: dict[str, Any],
) -> frozenset[str]:
    """Return scheduler keys that must not overlap for one build job."""
    keys: set[str] = set()
    if harness == "opencode":
        keys.add("harness:opencode")
    provider = subscription_provider(model_row)
    if provider is not None:
        keys.add(f"subscription:{provider}")
    return frozenset(keys)


def build_campaign_concurrency_keys(
    *,
    harness: str,
    model_row: dict[str, Any],
) -> frozenset[str]:
    """Scheduler keys for one parallel campaign replicate job."""
    keys = set(build_job_concurrency_keys(harness=harness, model_row=model_row))
    slug = model_row.get("slug")
    if slug:
        keys.add(f"model:{slug}")
    return frozenset(keys)
