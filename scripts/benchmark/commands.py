"""Shell command builders for the opencode and codex harnesses.

These are pure functions: given a model id and project dir, they emit the
argv list that gets handed to ``subprocess.Popen``. Extracted from
``runner.py`` so the command shape (including the ``ollama launch`` shim)
is reviewable without scrolling through orchestration code.
"""

from __future__ import annotations

from pathlib import Path
from shlex import quote as shlex_quote
from typing import Any


def _opencode_args_with_dir(args: list[str], project_dir: Path) -> list[str]:
    command_args = list(args)
    command_args[1:1] = ["--dir", str(project_dir.resolve())]
    return command_args


def build_opencode_command(
    runner: dict[str, Any],
    model_id: str,
    prompt: str,
    project_dir: Path,
    continue_session_id: str | None = None,
    command_prefix: list[str] | None = None,
) -> list[str]:
    """Build an opencode CLI command.

    ``command_prefix`` mirrors the codex path: when set to something like
    ``["ollama", "launch", "opencode"]`` the model id is forwarded to the
    shim via ``--model`` and the rest of the opencode argv comes after ``--``.
    The ``-m`` flag is dropped because the shim injects the model itself.
    """
    is_ollama_launch = (
        command_prefix is not None
        and len(command_prefix) >= 2
        and command_prefix[0] == "ollama"
        and command_prefix[1] == "launch"
    )

    if is_ollama_launch:
        inner = _opencode_args_with_dir(runner["args"], project_dir)
        if continue_session_id:
            inner.extend(["--session", continue_session_id])
        inner.append(prompt)
        return [*command_prefix, "--model", model_id, "--", *inner]

    command = [runner["command"], *_opencode_args_with_dir(runner["args"], project_dir)]
    if continue_session_id:
        command.extend(["--session", continue_session_id])
    else:
        command.extend(["-m", model_id])
    command.append(prompt)
    return command


def write_codex_subagent_toml(project_dir: Path, subagent: dict[str, Any]) -> Path:
    """Write a Codex subagent TOML config file inside the project directory.

    Returns the absolute path suitable for passing via
    ``-c agents.<name>.config_file=...``.
    """
    agent_name = subagent.get("name", "coder")
    agent_model = subagent.get("model", "gpt-5.4")
    agent_effort = subagent.get("reasoning_effort")
    agent_prompt = subagent.get("prompt", "")
    toml_path = project_dir / f".codex-{agent_name}.toml"
    lines = [
        f'model = "{agent_model}"',
    ]
    if agent_effort:
        lines.append(f'model_reasoning_effort = "{agent_effort}"')
    if agent_prompt:
        # TOML triple-quote for multi-line strings.
        escaped = agent_prompt.replace('"""', '\\"\\"\\"')
        lines.append(f'instructions = """{escaped}"""')
    toml_path.write_text("\n".join(lines) + "\n")
    return toml_path.resolve()


def build_codex_command(
    model_id: str,
    project_dir: Path,
    reasoning_effort: str | None = None,
    codex_subagent: dict[str, Any] | None = None,
    command_prefix: list[str] | None = None,
    auto_compact_token_limit: int | None = None,
) -> list[str]:
    """Build a codex exec command for a fully autonomous benchmark run.

    See the previous docstring in ``runner.py`` for the ``ollama launch``
    contract and the auto-compact knob caveats.
    """
    prefix = command_prefix if command_prefix else ["codex"]
    is_ollama_launch = (
        len(prefix) >= 2 and prefix[0] == "ollama" and prefix[1] == "launch"
    )

    exec_tail: list[str] = [
        "exec",
        "--json",
        "--ephemeral",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-s",
        "danger-full-access",
        "-C",
        str(project_dir.resolve()),
    ]
    if not is_ollama_launch:
        exec_tail.extend(["-m", model_id])
    if reasoning_effort:
        exec_tail.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])
    if auto_compact_token_limit is not None and auto_compact_token_limit > 0:
        exec_tail.extend(
            ["-c", f"model_auto_compact_token_limit={auto_compact_token_limit}"]
        )
    if codex_subagent:
        sub_name = codex_subagent.get("name", "coder")
        sub_desc = codex_subagent.get(
            "description", f"Delegate coding tasks to {sub_name}"
        )
        toml_path = write_codex_subagent_toml(project_dir, codex_subagent)
        exec_tail.extend(
            [
                "-c",
                f'agents.{sub_name}.config_file="{toml_path}"',
                "-c",
                f'agents.{sub_name}.description="{sub_desc}"',
            ]
        )
    exec_tail.append("-")

    if is_ollama_launch:
        inner = [*prefix, "--model", model_id, "--", *exec_tail]
    else:
        inner = [*prefix, *exec_tail]

    return ["bash", "-lc", " ".join(shlex_quote(a) for a in inner)]
