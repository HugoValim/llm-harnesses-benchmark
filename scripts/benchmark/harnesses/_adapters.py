"""Concrete Harness adapters wiring existing runner functions into the registry.

Each adapter is a thin shim: it points the registry at the current
``run_variant`` / ``run_model`` callables, giving entrypoints one lookup
table instead of four hard-coded import branches.

The runner module names (``claude_code_runner``, ``cursor_runner``,
``runner``) remain unchanged; only the dispatch surface moves.
"""

from __future__ import annotations

from benchmark.harnesses import Harness, register


def _opencode_run_variant(*args, **kwargs):
    # Opencode is driven from the model loop, not from variants. Audit code
    # never targets opencode as an auditor — but the registry exposes a
    # run_variant for symmetry. Today there is no opencode variant runner;
    # callers that need one should use run_model instead.
    raise NotImplementedError(
        "opencode is driven via run_model; no run_variant exists yet"
    )


def _codex_run_variant(*args, **kwargs):
    from benchmark.runner import run_codex_variant  # noqa: PLC0415

    return run_codex_variant(*args, **kwargs)


def _claude_run_variant(*args, **kwargs):
    from benchmark.claude_code_runner import run_variant  # noqa: PLC0415

    return run_variant(*args, **kwargs)


def _cursor_run_variant(*args, **kwargs):
    from benchmark.cursor_runner import run_variant  # noqa: PLC0415

    return run_variant(*args, **kwargs)


def _opencode_run_model(*args, **kwargs):
    from benchmark.runner import run_model  # noqa: PLC0415

    return run_model(*args, **kwargs)


def _codex_run_model(*args, **kwargs):
    from benchmark.runner import run_model  # noqa: PLC0415

    return run_model(*args, **kwargs)


register(Harness(
    name="opencode",
    run_variant=_opencode_run_variant,
    run_model=_opencode_run_model,
    cli_binary="opencode",
    cli_install_hint="opencode is not available on PATH",
))

register(Harness(
    name="codex",
    run_variant=_codex_run_variant,
    run_model=_codex_run_model,
    cli_binary="codex",
    cli_install_hint="codex is not available on PATH",
))

register(Harness(
    name="claude",
    run_variant=_claude_run_variant,
    run_model=None,
    cli_binary="claude",
    cli_install_hint="claude (Claude Code CLI) is not available on PATH",
    accepts_isolate_home=True,
))

register(Harness(
    name="cursor",
    run_variant=_cursor_run_variant,
    run_model=None,
    cli_binary="agent",
    cli_install_hint=(
        "agent (Cursor CLI) is not available on PATH. "
        "Install: curl https://cursor.com/install -fsS | bash"
    ),
))
