"""Post-benchmark Docker disk cleanup (build cache and unused images)."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

PRUNE_TIMEOUT_SECONDS = 600
RECLAIMED_SPACE_RE = re.compile(r"Total reclaimed space:\s*(.+)", re.IGNORECASE)


def _extract_reclaimed(stdout: str) -> str | None:
    for line in stdout.splitlines():
        match = RECLAIMED_SPACE_RE.search(line)
        if match:
            return match.group(1).strip()
    return None


def _run_prune_step(label: str, command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PRUNE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "label": label,
            "command": command,
            "returncode": None,
            "ok": False,
            "reclaimed": None,
            "stdout": "",
            "stderr": f"timed out after {PRUNE_TIMEOUT_SECONDS}s",
        }
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = f"{stdout}\n{stderr}"
    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "reclaimed": _extract_reclaimed(combined),
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def prune_docker_after_benchmark(*, force: bool = True) -> dict[str, Any]:
    """Run builder then system prune to reclaim disk after a benchmark batch.

    Example:
        result = prune_docker_after_benchmark()
        if result.get("skipped"):
            ...
    """
    if shutil.which("docker") is None:
        return {"skipped": True, "reason": "docker not on PATH"}

    force_args = ["-f"] if force else []
    steps: list[dict[str, Any]] = []
    for label, base_cmd in (
        ("builder", ["docker", "builder", "prune", "-a"]),
        ("system", ["docker", "system", "prune", "-a"]),
    ):
        steps.append(_run_prune_step(label, [*base_cmd, *force_args]))

    return {"skipped": False, "steps": steps}
