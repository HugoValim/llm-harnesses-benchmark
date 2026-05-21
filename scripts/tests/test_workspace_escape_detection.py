"""Regression tests for root-level workspace escape detection."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import summarize_project  # noqa: E402
from benchmark.workspace import (  # noqa: E402
    detect_workspace_escape,
    snapshot_root_generated_markers,
)


class TestWorkspaceEscapeDetection(unittest.TestCase):
    def test_root_manage_py_marks_empty_project_phase_failed(self) -> None:
        with TemporaryDirectory() as tmp:
            root_dir = Path(tmp)
            results_dir = root_dir / "results"
            project_dir = results_dir / "opencode-demo" / "project"
            project_dir.mkdir(parents=True)

            before = snapshot_root_generated_markers(root_dir, results_dir)
            (root_dir / "manage.py").write_text("print('escaped')\n")

            phase_payload: dict[str, Any] = {
                "status": "completed",
                "project_summary": summarize_project(project_dir),
            }
            checked = detect_workspace_escape(
                phase_payload,
                root_dir=root_dir,
                results_dir=results_dir,
                project_dir=project_dir,
                before_markers=before,
            )

            self.assertEqual(checked["status"], "failed")
            self.assertTrue(checked["workspace_escape_detected"])
            self.assertEqual(checked["workspace_escape_paths"], ["manage.py"])
            self.assertTrue((root_dir / "manage.py").exists())

    def test_opencode_session_root_directory_marks_empty_project_failed(self) -> None:
        with TemporaryDirectory() as tmp:
            root_dir = Path(tmp)
            results_dir = root_dir / "results"
            project_dir = results_dir / "opencode-qwen3_5_ollama_cloud" / "project"
            project_dir.mkdir(parents=True)
            session_export_path = project_dir.parent / "session-export.json"
            session_export_path.write_text(
                json.dumps(
                    {
                        "info": {
                            "id": "ses_qwen_regression",
                            "directory": str(root_dir),
                            "model": {
                                "id": "qwen3.5:cloud",
                                "providerID": "ollama",
                            },
                        },
                        "messages": [],
                    }
                )
            )

            phase_payload: dict[str, Any] = {
                "status": "completed",
                "paths": {"project_dir": str(project_dir)},
                "project_summary": summarize_project(project_dir),
            }
            checked = detect_workspace_escape(
                phase_payload,
                root_dir=root_dir,
                results_dir=results_dir,
                project_dir=project_dir,
                before_markers=frozenset(),
                session_export_path=session_export_path,
            )

            self.assertEqual(checked["status"], "failed")
            self.assertTrue(checked["workspace_escape_detected"])
            self.assertEqual(
                checked["workspace_escape_session_directory"], str(root_dir)
            )
            self.assertEqual(checked["paths"]["project_dir"], str(project_dir))


if __name__ == "__main__":
    unittest.main()
