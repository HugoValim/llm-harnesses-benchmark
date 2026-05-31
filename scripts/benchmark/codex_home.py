"""Isolated CODEX_HOME for ollama launch codex benchmark runs.

Codex 0.134+ rejects ``--profile ollama-launch`` when the base ``config.toml``
still contains legacy ``profile = "ollama-launch"`` or ``[profiles.ollama-launch]``.
Benchmark runs materialize a per-result ``.codex-home`` without those blocks.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from benchmark.util import ollama_launch_integration

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

    return dest.resolve()


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


def uses_isolated_codex_home(command_prefix: list[str] | None) -> bool:
    """True when this phase should isolate CODEX_HOME."""
    return ollama_launch_integration(command_prefix or []) == "codex"
