"""Benchmark agent runtime env — uses the operator's normal CLI home config."""

from __future__ import annotations

import re
from pathlib import Path

from benchmark.util import ollama_launch_integration


_CODEX_PROFILE_ASSIGNMENT_RE = re.compile(
    r"^\s*profile\s*=\s*(['\"])ollama-launch\1\s*$"
)
_CODEX_OLLAMA_LAUNCH_TABLE_RE = re.compile(r"^\s*\[profiles\.ollama-launch\]\s*$")
_CODEX_ANY_TABLE_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")


def config_has_legacy_ollama_launch_profile(config_toml: str) -> bool:
    """Return True when Codex config.toml embeds the legacy ollama-launch profile."""

    for raw in config_toml.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if _CODEX_PROFILE_ASSIGNMENT_RE.match(line):
            return True
        if _CODEX_OLLAMA_LAUNCH_TABLE_RE.match(line):
            return True
    return False


def strip_legacy_ollama_launch_profile(config_toml: str) -> str:
    """Remove legacy ollama-launch profile directives from a Codex config.toml."""

    lines = config_toml.splitlines(keepends=True)
    stripped: list[str] = []
    skipping_table = False

    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if skipping_table:
            if _CODEX_ANY_TABLE_RE.match(line):
                skipping_table = False
            else:
                continue

        if _CODEX_PROFILE_ASSIGNMENT_RE.match(line):
            continue

        if _CODEX_OLLAMA_LAUNCH_TABLE_RE.match(line):
            skipping_table = True
            continue

        stripped.append(raw)

    return "".join(stripped)


def prepare_isolated_codex_home(*, source_home: Path, dest_home: Path) -> None:
    """Materialize a benchmark-scoped Codex home directory for ollama launch runs."""

    dest_home.mkdir(parents=True, exist_ok=True)
    source_config = source_home / "config.toml"
    dest_config = dest_home / "config.toml"
    if source_config.exists():
        config_toml = source_config.read_text()
        dest_config.write_text(strip_legacy_ollama_launch_profile(config_toml))
    else:
        dest_config.write_text("")

    # Do not copy auth.json here. Codex treats that as ChatGPT OAuth state and
    # may refuse API-key flows (ollama launch codex requires API-key mode).
    for filename in ("ollama-launch.config.toml",):
        src = source_home / filename
        if src.exists():
            (dest_home / filename).write_text(src.read_text())


def codex_env_for_phase(
    base_env: dict[str, str],
    *,
    result_dir: Path,
    command_prefix: list[str] | None,
) -> dict[str, str]:
    """Return phase env, isolating Codex home only for ``ollama launch codex``."""

    integration = ollama_launch_integration(command_prefix or [])
    if integration != "codex":
        return dict(base_env)

    env = dict(base_env)
    dest_home = result_dir / ".codex-home"
    prepare_isolated_codex_home(source_home=Path.home() / ".codex", dest_home=dest_home)
    env["CODEX_HOME"] = str(dest_home)
    return env


def benchmark_env_for_harness(
    harness: str,
    base_env: dict[str, str],
    *,
    result_dir: Path,
    command_prefix: list[str] | None = None,
) -> dict[str, str]:
    """Return benchmark build env without per-replicate isolation overrides."""
    del harness, result_dir, command_prefix
    return dict(base_env)


def runtime_isolation_for_env(env: dict[str, str]) -> dict[str, str]:
    """Return isolation env keys set during a benchmark build phase."""
    keys = ("XDG_DATA_HOME", "CODEX_HOME", "HOME")
    return {key: env[key] for key in keys if key in env}
