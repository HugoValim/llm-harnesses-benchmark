"""Per-run agent runtime env: isolated CODEX_HOME and XDG_DATA_HOME.

Codex 0.134+ rejects ``--profile ollama-launch`` when the base ``config.toml``
still contains legacy ``profile = "ollama-launch"`` or ``[profiles.ollama-launch]``.
Benchmark runs materialize a per-result ``.codex-home`` without those blocks.

OpenCode stores state under ``$XDG_DATA_HOME/opencode``; parallel benchmark runs
set ``XDG_DATA_HOME`` to ``{result_dir}/.xdg-data`` to avoid SQLite lock contention.

Claude and Cursor benchmark builds isolate ``$HOME`` under ``{result_dir}/.agent-home``
and stage subscription auth from the real home when available.

Codex subscription auth is staged by copying ``auth.json`` from the source
``~/.codex`` into per-replicate ``.codex-home`` when present.

Cursor subscription auth is staged by copying ``auth.json`` from the source
``~/.config/cursor`` into ``{result_dir}/.agent-home/.config/cursor`` when
present (fallback: ``CURSOR_API_KEY`` in the environment).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from benchmark.util import ollama_launch_integration

AGENT_HOME_DIRNAME = ".agent-home"

_LEGACY_PROFILE_SELECTOR = re.compile(
    r'^\s*profile\s*=\s*["\']ollama-launch["\']\s*$',
    re.MULTILINE,
)
_LEGACY_PROFILE_TABLE_HEADER = re.compile(
    r"^\s*\[profiles\.ollama-launch\]\s*$",
    re.MULTILINE,
)

_DEFAULT_OLLAMA_LAUNCH_PROFILE = """\
# Minimal ollama-launch profile overlay for benchmark runs.
openai_base_url = "http://127.0.0.1:11434/v1/"
forced_login_method = "api"
model_provider = "ollama-launch"
"""


def config_has_legacy_ollama_launch_profile(text: str) -> bool:
    """Return True when *text* contains legacy ollama-launch profile selectors."""
    if _LEGACY_PROFILE_SELECTOR.search(text):
        return True
    return _LEGACY_PROFILE_TABLE_HEADER.search(text) is not None


def strip_legacy_ollama_launch_profile(text: str) -> str:
    """Remove legacy ollama-launch profile lines from base config TOML."""
    without_selector = _LEGACY_PROFILE_SELECTOR.sub("", text)
    return _strip_profiles_ollama_launch_table(without_selector)


def _strip_profiles_ollama_launch_table(text: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skip_table = False
    for line in lines:
        if _LEGACY_PROFILE_TABLE_HEADER.match(line.rstrip("\n")):
            skip_table = True
            continue
        if skip_table:
            if line.strip().startswith("[") and line.strip().endswith("]"):
                skip_table = False
                out.append(line)
            continue
        out.append(line)
    return "".join(out).rstrip() + "\n"


def prepare_isolated_codex_home(
    result_dir: Path,
    *,
    source_home: Path | None = None,
) -> Path:
    """Create ``{result_dir}/.codex-home`` safe for ``--profile ollama-launch``."""
    source = source_home if source_home is not None else Path.home() / ".codex"
    dest = result_dir / ".codex-home"
    dest.mkdir(parents=True, exist_ok=True)

    source_config = source / "config.toml"
    if source_config.is_file():
        base_text = source_config.read_text(encoding="utf-8")
        dest_config_text = strip_legacy_ollama_launch_profile(base_text)
    else:
        dest_config_text = ""
    (dest / "config.toml").write_text(dest_config_text, encoding="utf-8")

    profile_src = source / "ollama-launch.config.toml"
    profile_dest = dest / "ollama-launch.config.toml"
    if profile_src.is_file():
        shutil.copy2(profile_src, profile_dest)
    else:
        profile_dest.write_text(_DEFAULT_OLLAMA_LAUNCH_PROFILE, encoding="utf-8")

    stage_codex_auth(source, dest)
    return dest.resolve()


def stage_codex_auth(source_home: Path, dest_home: Path) -> list[str]:
    """Copy ``auth.json`` from source Codex home into isolated ``CODEX_HOME``."""
    copied: list[str] = []
    auth_src = source_home / "auth.json"
    if auth_src.is_file():
        auth_dest = dest_home / "auth.json"
        shutil.copy2(auth_src, auth_dest)
        copied.append(str(auth_dest))
    return copied


def cursor_config_dir(home: Path, *, xdg_config_home: Path | None = None) -> Path:
    """Return the Cursor CLI config directory under *home*."""
    base = xdg_config_home if xdg_config_home is not None else home / ".config"
    return base / "cursor"


def stage_cursor_auth(
    isolated_home: Path,
    source_home: Path,
    *,
    source_xdg_config_home: Path | None = None,
) -> list[str]:
    """Copy ``auth.json`` from source Cursor config into isolated ``HOME/.config/cursor``."""
    auth_src = (
        cursor_config_dir(source_home, xdg_config_home=source_xdg_config_home)
        / "auth.json"
    )
    if not auth_src.is_file():
        return []
    dest_dir = cursor_config_dir(isolated_home)
    dest_dir.mkdir(parents=True, exist_ok=True)
    auth_dest = dest_dir / "auth.json"
    shutil.copy2(auth_src, auth_dest)
    return [str(auth_dest)]


def prepare_isolated_opencode_data_home(result_dir: Path) -> Path:
    """Return parent for XDG_DATA_HOME; opencode uses {parent}/opencode."""
    data_home = result_dir / ".xdg-data"
    data_home.mkdir(parents=True, exist_ok=True)
    return data_home.resolve()


def codex_env_for_phase(
    base_env: dict[str, str],
    *,
    result_dir: Path,
    command_prefix: list[str] | None,
    source_codex_home: Path | None = None,
) -> dict[str, str]:
    """Return process env; set ``CODEX_HOME`` when using ollama launch codex."""
    if ollama_launch_integration(command_prefix or []) != "codex":
        return dict(base_env)
    env = dict(base_env)
    isolated = prepare_isolated_codex_home(
        result_dir, source_home=source_codex_home
    )
    env["CODEX_HOME"] = str(isolated)
    return env


def opencode_env_for_phase(
    base_env: dict[str, str],
    *,
    result_dir: Path,
    command_prefix: list[str] | None = None,
) -> dict[str, str]:
    """Return process env with per-run ``XDG_DATA_HOME`` for OpenCode."""
    del command_prefix  # reserved for future ollama-launch-specific overrides
    env = dict(base_env)
    isolated = prepare_isolated_opencode_data_home(result_dir)
    env["XDG_DATA_HOME"] = str(isolated)
    return env


def prepare_isolated_agent_home(result_dir: Path) -> Path:
    """Create ``{result_dir}/.agent-home`` for Claude/Cursor benchmark runs."""
    agent_home = result_dir / AGENT_HOME_DIRNAME
    agent_home.mkdir(parents=True, exist_ok=True)
    return agent_home.resolve()


def stage_subscription_auth(
    isolated_home: Path,
    source_home: Path,
    harness: str,
    *,
    source_xdg_config_home: Path | None = None,
) -> list[str]:
    """Copy subscription auth dirs from source home into isolated home."""
    copied: list[str] = []
    if harness == "claude":
        source = source_home / ".claude"
        if source.is_dir():
            dest = isolated_home / ".claude"
            shutil.copytree(source, dest, dirs_exist_ok=True)
            copied.append(str(dest))
    elif harness == "cursor":
        source = source_home / ".cursor"
        if source.is_dir():
            dest = isolated_home / ".cursor"
            shutil.copytree(source, dest, dirs_exist_ok=True)
            copied.append(str(dest))
        copied.extend(
            stage_cursor_auth(
                isolated_home,
                source_home,
                source_xdg_config_home=source_xdg_config_home,
            )
        )
    return copied


def benchmark_env_for_harness(
    harness: str,
    base_env: dict[str, str],
    *,
    result_dir: Path,
    command_prefix: list[str] | None = None,
    isolate_home: bool = True,
) -> dict[str, str]:
    """Return benchmark build env with per-replicate isolation for *harness*."""
    if harness == "opencode":
        return opencode_env_for_phase(
            base_env,
            result_dir=result_dir,
            command_prefix=command_prefix,
        )
    env = dict(base_env)
    if harness == "codex":
        isolated = prepare_isolated_codex_home(result_dir)
        env["CODEX_HOME"] = str(isolated)
        return env
    if harness in ("claude", "cursor") and isolate_home:
        agent_home = prepare_isolated_agent_home(result_dir)
        source_xdg = base_env.get("XDG_CONFIG_HOME")
        stage_subscription_auth(
            agent_home,
            Path.home(),
            harness,
            source_xdg_config_home=Path(source_xdg) if source_xdg else None,
        )
        env["HOME"] = str(agent_home)
    return env


def runtime_isolation_for_env(env: dict[str, str]) -> dict[str, str]:
    """Return isolation env keys set during a benchmark build phase."""
    keys = ("XDG_DATA_HOME", "CODEX_HOME", "HOME")
    return {key: env[key] for key in keys if key in env}


def uses_isolated_codex_home(command_prefix: list[str] | None) -> bool:
    """True when this phase should isolate CODEX_HOME."""
    return ollama_launch_integration(command_prefix or []) == "codex"
