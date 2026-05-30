"""Tests for benchmark.publish_campaign."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.publish_campaign import (  # noqa: E402
    GITIGNORE_BEGIN,
    GITIGNORE_END,
    TAILWINDCSS_BINARY_PREFIX,
    CampaignManifest,
    build_manifest,
    discover_targets_from_auditor,
    render_gitignore_block,
    strip_project_ephemeral,
    update_gitignore,
    update_symlink,
    validate_no_secrets,
    write_manifest,
)


class TestDiscoverTargets(unittest.TestCase):
    def test_discovers_report_dirs_and_skips_meta_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auditor = root / "codex_gpt_5_5"
            (auditor / "codex-demo" / "report.md").parent.mkdir(parents=True)
            (auditor / "codex-demo" / "report.md").write_text("# report\n")
            (auditor / "_meta-analysis-runs").mkdir()

            targets = discover_targets_from_auditor(root, "codex_gpt_5_5")
            self.assertEqual(targets, ["codex-demo"])


class TestStripProjectEphemeral(unittest.TestCase):
    def test_removes_venv_and_twcli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".venv" / "lib").mkdir(parents=True)
            (project / "twcli").mkdir()
            (project / "chat" / "views.py").parent.mkdir(parents=True)
            (project / "chat" / "views.py").write_text("print('ok')\n")

            removed = strip_project_ephemeral(project)
            self.assertFalse((project / ".venv").exists())
            self.assertFalse((project / "twcli").exists())
            self.assertTrue((project / "chat" / "views.py").exists())
            self.assertTrue(any(".venv" in item for item in removed))


class TestStripTailwindcssBinary(unittest.TestCase):
    def test_removes_standalone_tailwindcss_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "tailwindcss-linux-x64").write_bytes(b"\0" * 1024)
            (project / "chat" / "views.py").parent.mkdir(parents=True)
            (project / "chat" / "views.py").write_text("ok\n")

            removed = strip_project_ephemeral(project)
            self.assertFalse((project / "tailwindcss-linux-x64").exists())
            self.assertTrue((project / "chat" / "views.py").exists())
            self.assertIn("tailwindcss-linux-x64", removed)


class TestStripResultEphemeral(unittest.TestCase):
    def test_removes_stderr_and_session_export_logs(self) -> None:
        from benchmark.publish_campaign import strip_result_ephemeral

        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp)
            (result_dir / "followup-stderr.log").write_text("warn\n")
            (result_dir / "session-export.stderr.log").write_text("export\n")
            (result_dir / "result.json").write_text("{}\n")

            removed = strip_result_ephemeral(result_dir)
            self.assertFalse((result_dir / "followup-stderr.log").exists())
            self.assertFalse((result_dir / "session-export.stderr.log").exists())
            self.assertTrue((result_dir / "result.json").exists())
            self.assertEqual(len(removed), 2)


class TestGitignoreBlock(unittest.TestCase):
    def test_render_contains_campaign_and_targets(self) -> None:
        manifest = CampaignManifest(
            id="2026-05-ollama-cloud-v3.2",
            label="Test campaign",
            date="2026-05-29",
            prompt_versions={"benchmark": "benchmark-v3.2"},
            auditor_slug="codex_gpt_5_5",
            meta_analysis="audit-reports/codex_gpt_5_5/meta-analysis.md",
            audit_root="audit-reports/codex_gpt_5_5",
            benchmark_results_root="results",
            targets=["codex-demo", "claude-demo"],
            harnesses=["claude", "codex"],
            models_config_sha256="abc",
            harnesses_config_sha256="def",
        )
        block = render_gitignore_block(manifest)
        self.assertIn(GITIGNORE_BEGIN, block)
        self.assertIn(GITIGNORE_END, block)
        self.assertIn("!/audit-reports/codex_gpt_5_5/", block)
        self.assertIn("!/results/codex-demo/", block)
        self.assertIn("/results/**/followup-stderr.log", block)
        self.assertIn("/results/**/project/.env", block)
        self.assertIn(f"/results/**/project/{TAILWINDCSS_BINARY_PREFIX}*", block)
        self.assertIn("/results/**/project/.venv/", block)
        self.assertNotIn("results/codex-demo/followup-stderr.log", block)

    def test_update_gitignore_replaces_existing_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            gitignore = repo / ".gitignore"
            gitignore.write_text(
                "# base\n\n"
                f"{GITIGNORE_BEGIN}\nold\n{GITIGNORE_END}\n\n"
                "# tail\n"
            )
            manifest = CampaignManifest(
                id="campaign-a",
                label="A",
                date="2026-05-29",
                prompt_versions={},
                auditor_slug="auditor",
                meta_analysis="audit-reports/auditor/meta-analysis.md",
                audit_root="audit-reports/auditor",
                benchmark_results_root="results",
                targets=["codex-demo"],
                harnesses=["codex"],
                models_config_sha256="x",
                harnesses_config_sha256="y",
            )
            update_gitignore(repo, render_gitignore_block(manifest))
            text = gitignore.read_text()
            self.assertIn("campaign-a", text)
            self.assertNotIn("\nold\n", text)
            self.assertIn("# tail", text)


class TestSymlink(unittest.TestCase):
    def test_update_symlink_points_at_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "codex_gpt_5_5"
            target.mkdir()
            link = root / "latest"
            update_symlink(link, target)
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), target.resolve())


class TestValidateSecrets(unittest.TestCase):
    def test_flags_openrouter_key_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.py"
            path.write_text('OPENROUTER_API_KEY = "sk-abcdefghijklmnopqrstuvwxyz"\n')
            errors = validate_no_secrets([path])
            self.assertGreaterEqual(len(errors), 1)


class TestManifestRoundTrip(unittest.TestCase):
    def test_write_and_load_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            manifest = CampaignManifest(
                id="2026-05-ollama-cloud-v3.2",
                label="Ollama Cloud grid",
                date="2026-05-29",
                prompt_versions={"benchmark": "benchmark-v3.2"},
                auditor_slug="codex_gpt_5_5",
                meta_analysis="audit-reports/codex_gpt_5_5/meta-analysis.md",
                audit_root="audit-reports/codex_gpt_5_5",
                benchmark_results_root="results",
                targets=["codex-demo"],
                harnesses=["codex"],
                models_config_sha256="abc123",
                harnesses_config_sha256="def456",
            )
            write_manifest(path, manifest)
            payload = json.loads(path.read_text())
            self.assertEqual(payload["id"], manifest.id)
            self.assertEqual(payload["targets"], ["codex-demo"])


class TestBuildManifestFromRepo(unittest.TestCase):
    def test_build_manifest_reads_prompt_versions(self) -> None:
        targets = discover_targets_from_auditor(
            REPO_ROOT / "results" / "run_01" / "audit-reports",
            "codex_gpt_5_5",
        )
        manifest = build_manifest(
            campaign_id="2026-05-ollama-cloud-v3.2",
            label="Ollama Cloud grid",
            auditor_slug="codex_gpt_5_5",
            targets=targets,
            repo_root=REPO_ROOT,
            campaign_date="2026-05-29",
            run_id="run_01",
        )
        self.assertEqual(manifest.prompt_versions["benchmark"], "benchmark-v3.3")
        self.assertEqual(manifest.prompt_versions["audit"], "audit-v3.9")
        self.assertEqual(len(manifest.targets), 28)
        self.assertIn("codex", manifest.harnesses)

    def test_build_manifest_run_scoped_paths(self) -> None:
        manifest = build_manifest(
            campaign_id="2026-06-test",
            label="Run scoped",
            auditor_slug="codex_gpt_5_5",
            targets=["codex-demo"],
            repo_root=REPO_ROOT,
            run_id="run_02",
        )
        self.assertEqual(manifest.run_id, "run_02")
        self.assertEqual(manifest.benchmark_results_root, "results/run_02/projects")
        self.assertEqual(
            manifest.audit_root,
            "results/run_02/audit-reports/codex_gpt_5_5",
        )
        self.assertEqual(manifest.meta_analysis, "results/run_02/meta-analysis.md")


if __name__ == "__main__":
    unittest.main()
