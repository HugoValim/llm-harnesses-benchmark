"""Benchmark agent runtime env — isolates Codex home when Ollama overrides leak in."""

from __future__ import annotations

import re
from pathlib import Path

from benchmark.util import ollama_launch_integration


_CODEX_PROFILE_ASSIGNMENT_RE = re.compile(
    r"^\s*profile\s*=\s*(['\"])ollama-launch\1\s*$"
)
_CODEX_MODEL_PROVIDER_ASSIGNMENT_RE = re.compile(
    r"^\s*model_provider\s*=\s*(['\"])ollama-launch\1\s*$"
)
_CODEX_MODEL_CATALOG_JSON_RE = re.compile(r"^\s*model_catalog_json\s*=")
_CODEX_OLLAMA_LAUNCH_TABLE_RE = re.compile(r"^\s*\[profiles\.ollama-launch\]\s*$")
_CODEX_OLLAMA_LAUNCH_PROVIDER_TABLE_RE = re.compile(
    r"^\s*\[model_providers\.ollama-launch\]\s*$"
)
_CODEX_ANY_TABLE_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")
_CODEX_OLLAMA_LAUNCH_TABLES = (
    _CODEX_OLLAMA_LAUNCH_TABLE_RE,
    _CODEX_OLLAMA_LAUNCH_PROVIDER_TABLE_RE,
)


def config_has_ollama_launch_overrides(config_toml: str) -> bool:
    """Return True when Codex config.toml routes plain ``codex`` through Ollama."""

    for raw in config_toml.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if _CODEX_PROFILE_ASSIGNMENT_RE.match(line):
            return True
        if _CODEX_MODEL_PROVIDER_ASSIGNMENT_RE.match(line):
            return True
        for table_re in _CODEX_OLLAMA_LAUNCH_TABLES:
            if table_re.match(line):
                return True
    return False


def config_has_legacy_ollama_launch_profile(config_toml: str) -> bool:
    """Return True when Codex config.toml embeds the legacy ollama-launch profile."""

    return config_has_ollama_launch_overrides(config_toml)


def strip_ollama_launch_overrides(config_toml: str) -> str:
    """Remove ollama-launch profile/provider directives from a Codex config.toml."""

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
        if _CODEX_MODEL_PROVIDER_ASSIGNMENT_RE.match(line):
            continue
        if _CODEX_MODEL_CATALOG_JSON_RE.match(line):
            continue

        for table_re in _CODEX_OLLAMA_LAUNCH_TABLES:
            if table_re.match(line):
                skipping_table = True
                break
        else:
            stripped.append(raw)
            continue

        # matched an ollama-launch table header; skip it and its body
        continue

    return "".join(stripped)


def strip_legacy_ollama_launch_profile(config_toml: str) -> str:
    """Remove legacy ollama-launch profile directives from a Codex config.toml."""

    return strip_ollama_launch_overrides(config_toml)


def prepare_isolated_codex_home(*, source_home: Path, dest_home: Path) -> None:
    """Materialize a benchmark-scoped Codex home directory for ollama launch runs."""

    dest_home.mkdir(parents=True, exist_ok=True)
    source_config = source_home / "config.toml"
    dest_config = dest_home / "config.toml"
    if source_config.exists():
        config_toml = source_config.read_text()
        dest_config.write_text(strip_ollama_launch_overrides(config_toml))
    else:
        dest_config.write_text("")

    # Do not copy auth.json here. Codex treats that as ChatGPT OAuth state and
    # may refuse API-key flows (ollama launch codex requires API-key mode).
    for filename in ("ollama-launch.config.toml",):
        src = source_home / filename
        if src.exists():
            (dest_home / filename).write_text(src.read_text())


def prepare_subscription_codex_home(*, source_home: Path, dest_home: Path) -> None:
    """Materialize a ChatGPT-linked Codex home without Ollama provider overrides."""

    dest_home.mkdir(parents=True, exist_ok=True)
    source_config = source_home / "config.toml"
    dest_config = dest_home / "config.toml"
    if source_config.exists():
        config_toml = source_config.read_text()
        dest_config.write_text(strip_ollama_launch_overrides(config_toml))
    else:
        dest_config.write_text("")

    auth_src = source_home / "auth.json"
    if auth_src.exists():
        (dest_home / "auth.json").write_text(auth_src.read_text())


def codex_env_for_phase(
    base_env: dict[str, str],
    *,
    result_dir: Path,
    command_prefix: list[str] | None,
) -> dict[str, str]:
    """Return phase env with benchmark-scoped Codex home when isolation is required."""

    integration = ollama_launch_integration(command_prefix or [])
    source_home = Path.home() / ".codex"
    source_config = source_home / "config.toml"
    config_toml = source_config.read_text() if source_config.exists() else ""

    if integration == "codex":
        env = dict(base_env)
        dest_home = result_dir / ".codex-home"
        prepare_isolated_codex_home(source_home=source_home, dest_home=dest_home)
        env["CODEX_HOME"] = str(dest_home)
        return env

    if config_has_ollama_launch_overrides(config_toml):
        env = dict(base_env)
        dest_home = result_dir / ".codex-home"
        prepare_subscription_codex_home(source_home=source_home, dest_home=dest_home)
        env["CODEX_HOME"] = str(dest_home)
        return env

    return dict(base_env)


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
