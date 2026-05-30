"""Harness seam: one adapter per coding-agent CLI behind a uniform interface.

The registry is the only lookup point for ``--harness <name>`` dispatch.
Entrypoints (``run_benchmark.py``, ``run_audit.py``) ask the registry for
a :class:`Harness`; the harness exposes ``run_variant`` (used by audit and
variant-style benchmarks) and optionally ``run_model`` (used by the
model-driven benchmark loop for opencode/codex).

Adding a fifth CLI = one new ``Harness`` instance + one ``register()``
call; no edits to entrypoints.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Callable

from benchmark.result_layout import HARNESS_PREFIXES
from benchmark.util import clone_json, ollama_launch_command_prefix, ollama_launch_integration


class UnknownHarnessError(ValueError):
    """Raised when ``get_harness(name)`` cannot locate a registered harness."""


@dataclass(frozen=True)
class Harness:
    """One coding-agent CLI behind a uniform interface.

    ``run_variant`` is the audit-call shape, used by both ``run_audit.py``
    and the variant-style benchmark dispatch (claude, cursor). It accepts a
    variant dict, prompt, results_dir, and per-call overrides.

    ``run_model`` is only present for harnesses driven from the
    ``BenchmarkConfig`` model loop (opencode, codex). For variant-only
    harnesses this is ``None``.

    ``cli_binary`` names the executable that must be on PATH for the
    harness to run; ``cli_install_hint`` is shown when it's missing.
    ``accepts_isolate_home`` flags whether ``run_variant`` accepts the
    ``isolate_home`` keyword (only Claude Code does).
    """

    name: str
    run_variant: Callable[..., dict]
    run_model: Callable[..., dict] | None = None
    cli_binary: str | None = None
    cli_install_hint: str | None = None
    accepts_isolate_home: bool = False
    accepts_runner_command_prefix: bool = False
    model_runner_types: frozenset[str] = frozenset()
    aliases: frozenset[str] = frozenset()


HARNESS_REGISTRY: dict[str, Harness] = {}


def register(harness: Harness) -> None:
    """Register a Harness adapter under its name. Idempotent."""
    HARNESS_REGISTRY[harness.name] = harness


def get_harness(name: str) -> Harness:
    """Return the registered Harness, or raise UnknownHarnessError."""
    try:
        return HARNESS_REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(HARNESS_REGISTRY))
        raise UnknownHarnessError(
            f"Unknown harness {name!r}. Available: {available}"
        ) from exc


def list_harnesses() -> list[str]:
    """Return registered harness names in canonical order."""
    canonical = [n for n in HARNESS_PREFIXES if n in HARNESS_REGISTRY]
    extras = sorted(n for n in HARNESS_REGISTRY if n not in HARNESS_PREFIXES)
    return canonical + extras


PROVIDER_HARNESS_MAP: dict[str, frozenset[str]] = {
    "anthropic": frozenset({"claude"}),
    "openai": frozenset({"codex"}),
    "cursor": frozenset({"cursor"}),
    "ollama_cloud": frozenset({"claude", "codex", "opencode"}),
}


def canonical_harness_name(name: str) -> str:
    """Return the registered harness name for a CLI alias."""
    if name in HARNESS_REGISTRY:
        return name
    for harness in HARNESS_REGISTRY.values():
        if name in harness.aliases:
            return harness.name
    return name


def registry_models_for_harness(
    registry_models: list[dict[str, Any]],
    harness: str,
) -> list[dict[str, Any]]:
    """Return provider-routed model rows for one harness."""
    rows: list[dict[str, Any]] = []
    for model in registry_models:
        row = route_registry_model(model, harness)
        if row is not None:
            rows.append(row)
    return rows


def route_registry_model(
    model: dict[str, Any],
    harness: str,
) -> dict[str, Any] | None:
    """Return a harness-specific model row, or ``None`` when out of scope."""
    provider = model.get("provider", "")
    if harness not in PROVIDER_HARNESS_MAP.get(provider, frozenset()):
        if harness != "opencode" or not model.get("opencode_id"):
            return None
    row = clone_json(model)
    row["harness"] = harness
    if harness == "opencode" and model.get("opencode_id"):
        row["id"] = model["opencode_id"]
    _apply_runner_defaults(row, harness)
    if not isinstance(row.get("id"), str) or not row["id"]:
        raise ValueError(
            f"harness {harness!r} model {row.get('slug')!r} needs string id"
        )
    return row


def model_matches_harness(model: dict[str, Any], harness: str) -> bool:
    """Whether a resolved model row belongs to one benchmark harness."""
    harness = canonical_harness_name(harness)
    runner_type = model.get("runner_type", "opencode")
    registered = get_harness(harness)
    if runner_type in registered.model_runner_types:
        return True
    if harness == "codex" and runner_type == "codex":
        return True
    return False


def check_harness_cli_requirements(
    harness_name: str,
    models: list[dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Validate CLI binaries required by a harness and selected model rows."""
    harness = get_harness(canonical_harness_name(harness_name))
    binaries = _required_binaries(harness, models or [])
    for binary in binaries:
        if shutil.which(binary) is None:
            return False, _missing_binary_message(binary, harness.name)
    return True, ""


def _apply_runner_defaults(row: dict[str, Any], harness: str) -> None:
    provider = row.get("provider", "")
    if provider == "ollama_cloud":
        if harness == "codex":
            row.setdefault("runner_type", "ollama")
            return
        row.setdefault("runner_type", harness)
        row.setdefault("command_prefix", ollama_launch_command_prefix(harness))
        return
    row.setdefault("runner_type", "codex" if provider == "openai" else harness)


def _required_binaries(harness: Harness, models: list[dict[str, Any]]) -> list[str]:
    if harness.name != "codex":
        return [harness.cli_binary] if harness.cli_binary else []
    if not models:
        return ["codex"]
    return sorted({_codex_binary_for_model(model) for model in models})


def _codex_binary_for_model(model: dict[str, Any]) -> str:
    command_prefix = model.get("command_prefix") or []
    runner_type = model.get("runner_type", "codex")
    if runner_type == "ollama" or ollama_launch_integration(command_prefix) == "codex":
        return "ollama"
    return "codex"


def _missing_binary_message(binary: str, harness_name: str) -> str:
    if binary == "ollama":
        return "ollama is not available on PATH (needed for ollama launch codex)"
    harness = get_harness(harness_name)
    return harness.cli_install_hint or f"{binary} is not available on PATH"


# Lazy adapter wiring — imported here so ``from benchmark.harnesses import …``
# triggers registration without callers needing to import each adapter.
from benchmark.harnesses import _adapters  # noqa: E402, F401
