"""Shared utilities for the benchmark harness."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Directories that contain vendored / generated artifacts rather than
# project source. Excluded from file counting and structural scaffold
# detection so phase-2 `.venv` / `node_modules` creation doesn't drown
# the real project tree.
_EXCLUDED_DIRS = frozenset(
    {
        ".venv",
        "venv",
        ".git",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "_runtime_verification",
        "staticfiles",
        ".coverage_html",
        "htmlcov",
        "dist",
        "build",
        ".next",
        ".cache",
    }
)


def init_project_git(project_dir: Path) -> None:
    """Initialize an isolated git repo in ``project_dir``.

    Prevents git traversal from reaching the harness repo root when a
    generated project runs ``git rev-parse --show-toplevel``. Without this,
    ``project_dir`` lives inside the harness checkout and git would return
    the harness root — causing models to write files there.

    Idempotent: no-op if ``.git`` already exists.

    Example:
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     p = Path(tmp) / "project"
        ...     p.mkdir()
        ...     init_project_git(p)
        ...     assert (p / ".git").is_dir()
    """
    import subprocess as _sp

    if (project_dir / ".git").exists():
        return
    completed = _sp.run(
        ["git", "init", str(project_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(
            f"git init failed in {project_dir!s} (exit {completed.returncode}); stderr={stderr!r}"
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def save_json_preserve_order(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def uses_ollama_launch_codex(model: dict[str, Any]) -> bool:
    """True when the model is routed through ``ollama launch codex``."""
    cp = model.get("command_prefix") or []
    return (
        len(cp) >= 3
        and cp[0] == "ollama"
        and cp[1] == "launch"
        and cp[2] == "codex"
    )


def model_matches_harness(model: dict[str, Any], harness: str) -> bool:
    """Whether a ``models`` registry entry is in scope for ``--harness``.

    Ollama Cloud rows use ``command_prefix: [\"ollama\", \"launch\", \"codex\"]``
    and may declare ``runner_type`` as ``\"codex\"`` (canonical) or ``\"ollama\"``
    (legacy). Both match ``--harness codex`` and ``--harness ollama`` so results
    can live under either ``results/codex-<slug>/`` or ``results/ollama-<slug>/``.
    Plain ``runner_type: \"codex\"`` without that prefix only matches codex.
    """
    rt = model.get("runner_type", "opencode")
    if harness == "opencode":
        return rt == "opencode"
    if harness == "codex":
        if rt == "codex":
            return True
        return bool(rt == "ollama" and uses_ollama_launch_codex(model))
    if harness == "ollama":
        if rt == "ollama":
            return True
        return bool(rt == "codex" and uses_ollama_launch_codex(model))
    return False


def clone_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def print_line(message: str) -> None:
    print(message, flush=True)


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def count_files(path: Path) -> int:
    """Count regular files under ``path``, skipping vendored/cache trees.

    Pruning ``.venv``, ``node_modules``, caches, etc. keeps the count
    representative of actual project source even after phase 2 creates
    a virtualenv. Also called every ~10s by the heartbeat loop, so this
    must stay cheap — single ``os.walk`` traversal with directory pruning.
    """
    if not path.exists():
        return 0
    total = 0
    for _root, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        total += len(filenames)
    return total


def count_files_matching(path: Path, pattern: str, *, limit: int | None = None) -> int:
    """Count files under ``path`` whose basename matches ``pattern`` (fnmatch).

    Skips the same vendored/cache directories as :func:`count_files`.
    Pass ``limit`` to short-circuit once that many matches are found
    (useful when the caller only needs a presence boolean).
    """
    if not path.exists():
        return 0
    total = 0
    for _root, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for name in filenames:
            if fnmatch.fnmatch(name, pattern):
                total += 1
                if limit is not None and total >= limit:
                    return total
    return total


def has_file_matching(path: Path, pattern: str) -> bool:
    """Return True if at least one file under ``path`` matches ``pattern``."""
    return count_files_matching(path, pattern, limit=1) > 0


def shorten_text(text: str, limit: int = 100) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def http_request(
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 3.0,
) -> dict[str, Any] | None:
    """Send a GET or POST (if payload given) and return parsed JSON, or None on failure."""
    import urllib.error
    import urllib.request

    data = None
    headers: dict[str, str] = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
