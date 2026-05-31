"""Regression tests for isolated CODEX_HOME used with ollama launch codex."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.codex_home import (  # noqa: E402
    codex_env_for_phase,
    config_has_legacy_ollama_launch_profile,
    prepare_isolated_codex_home,
    strip_legacy_ollama_launch_profile,
)

LEGACY_CONFIG = """\
model = "gpt-5.5"

[model_providers.ollama-launch]
name = "Ollama"
base_url = "http://127.0.0.1:11434/v1/"

[profiles.ollama-launch]
openai_base_url = "http://127.0.0.1:11434/v1/"
forced_login_method = "api"
model_provider = "ollama-launch"
"""

CLEAN_BASE_CONFIG = """\
model = "gpt-5.5"

[model_providers.ollama-launch]
name = "Ollama"
base_url = "http://127.0.0.1:11434/v1/"
"""

PROFILE_OVERLAY = """\
openai_base_url = "http://127.0.0.1:11434/v1/"
forced_login_method = "api"
model_provider = "ollama-launch"
"""


class TestLegacyOllamaLaunchProfileDetection(unittest.TestCase):
    def test_detects_profiles_table(self) -> None:
        self.assertTrue(config_has_legacy_ollama_launch_profile(LEGACY_CONFIG))

    def test_detects_top_level_profile_selector(self) -> None:
        text = 'profile = "ollama-launch"\nmodel = "gpt-5.5"\n'
        self.assertTrue(config_has_legacy_ollama_launch_profile(text))

    def test_model_providers_only_is_not_legacy(self) -> None:
        self.assertFalse(config_has_legacy_ollama_launch_profile(CLEAN_BASE_CONFIG))

    def test_profile_overlay_file_content_is_not_legacy(self) -> None:
        self.assertFalse(config_has_legacy_ollama_launch_profile(PROFILE_OVERLAY))


class TestStripLegacyOllamaLaunchProfile(unittest.TestCase):
    def test_removes_profiles_table_keeps_model_providers(self) -> None:
        stripped = strip_legacy_ollama_launch_profile(LEGACY_CONFIG)
        self.assertIn("[model_providers.ollama-launch]", stripped)
        self.assertNotIn("[profiles.ollama-launch]", stripped)
        self.assertFalse(config_has_legacy_ollama_launch_profile(stripped))

    def test_removes_top_level_profile_selector(self) -> None:
        text = 'profile = "ollama-launch"\nmodel = "gpt-5.5"\n'
        stripped = strip_legacy_ollama_launch_profile(text)
        self.assertNotIn("profile", stripped.lower().split("ollama-launch")[0])
        self.assertFalse(config_has_legacy_ollama_launch_profile(stripped))


class TestPrepareIsolatedCodexHome(unittest.TestCase):
    def test_creates_stripped_config_and_profile_overlay(self) -> None:
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            source_home.mkdir()
            (source_home / "config.toml").write_text(LEGACY_CONFIG, encoding="utf-8")
            (source_home / "ollama-launch.config.toml").write_text(
                PROFILE_OVERLAY, encoding="utf-8"
            )
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()

            isolated = prepare_isolated_codex_home(result_dir, source_home=source_home)

            self.assertEqual(isolated, result_dir / ".codex-home")
            config_text = (isolated / "config.toml").read_text(encoding="utf-8")
            self.assertFalse(config_has_legacy_ollama_launch_profile(config_text))
            self.assertIn("[model_providers.ollama-launch]", config_text)
            overlay = (isolated / "ollama-launch.config.toml").read_text(encoding="utf-8")
            self.assertEqual(overlay, PROFILE_OVERLAY)


class TestCodexEnvForPhase(unittest.TestCase):
    def test_ollama_launch_codex_sets_codex_home(self) -> None:
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            source_home.mkdir()
            (source_home / "config.toml").write_text(LEGACY_CONFIG, encoding="utf-8")
            (source_home / "ollama-launch.config.toml").write_text(
                PROFILE_OVERLAY, encoding="utf-8"
            )
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = codex_env_for_phase(
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
                command_prefix=["ollama", "launch", "--yes", "codex"],
                source_codex_home=source_home,
            )
            self.assertIn("CODEX_HOME", env)
            isolated = Path(env["CODEX_HOME"])
            self.assertTrue((isolated / "config.toml").is_file())
            self.assertFalse(
                config_has_legacy_ollama_launch_profile(
                    (isolated / "config.toml").read_text(encoding="utf-8")
                )
            )

    def test_plain_codex_leaves_codex_home_unset(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = codex_env_for_phase(
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
                command_prefix=None,
            )
            self.assertNotIn("CODEX_HOME", env)


if __name__ == "__main__":
    unittest.main()
