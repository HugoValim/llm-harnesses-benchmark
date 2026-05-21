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

from dataclasses import dataclass
from typing import Callable

from benchmark.result_layout import HARNESS_PREFIXES


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


# Lazy adapter wiring — imported here so ``from benchmark.harnesses import …``
# triggers registration without callers needing to import each adapter.
from benchmark.harnesses import _adapters  # noqa: E402, F401
