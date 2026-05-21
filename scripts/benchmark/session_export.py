"""Opencode session export — post-run capture of opencode's session JSON.

Separate from the streaming subprocess in ``runner.py``: this fires after
the agent process has exited, invokes ``opencode export <session_id>`` to
dump the session transcript, and writes it next to the run's other
artefacts. Extracted from ``runner.py`` so the session-export pathway is
maintainable without reading the whole orchestration giant.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from benchmark.util import print_line


def export_opencode_session(
    session_id: str,
    export_path: Path,
    process_env: dict[str, str],
    model_slug: str,
) -> Path | None:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    error_path = export_path.with_suffix(".stderr.log")
    completed = subprocess.run(
        ["opencode", "export", session_id],
        capture_output=True,
        text=True,
        env=process_env,
        check=False,
    )
    if completed.returncode == 0:
        export_path.write_text(completed.stdout)
        if completed.stderr:
            error_path.write_text(completed.stderr)
        return export_path
    error_path.write_text(
        completed.stderr or completed.stdout or "opencode export failed"
    )
    print_line(f"[{model_slug}] opencode export failed for session {session_id}")
    return None
