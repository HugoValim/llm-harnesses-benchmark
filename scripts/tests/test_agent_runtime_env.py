"""Regression tests for per-run agent runtime env (CODEX_HOME, XDG_DATA_HOME)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.agent_runtime_env import (  # noqa: E402
    AGENT_HOME_DIRNAME,
    benchmark_env_for_harness,
    codex_env_for_phase,
    config_has_legacy_ollama_launch_profile,
    opencode_env_for_phase,
    prepare_isolated_codex_home,
    stage_cursor_auth,
    stage_subscription_auth,
    strip_legacy_ollama_launch_profile,
)
from benchmark.harnesses import check_harness_cli_requirements  # noqa: E402

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


class TestOpenCodeEnvForPhase(unittest.TestCase):
    def test_opencode_env_sets_xdg_data_home(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = opencode_env_for_phase(
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
            )
            self.assertEqual(env["XDG_DATA_HOME"], str(result_dir / ".xdg-data"))

    def test_opencode_env_plain_opencode_still_isolates(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = opencode_env_for_phase(
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
                command_prefix=None,
            )
            self.assertIn("XDG_DATA_HOME", env)
            self.assertTrue((result_dir / ".xdg-data").is_dir())


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

    def test_prepare_isolated_codex_home_stages_auth_json_when_present(
        self,
    ) -> None:
        auth_content = '{"token":"test"}\n'
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            source_home.mkdir()
            (source_home / "config.toml").write_text(CLEAN_BASE_CONFIG, encoding="utf-8")
            (source_home / "auth.json").write_text(auth_content, encoding="utf-8")
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()

            isolated = prepare_isolated_codex_home(result_dir, source_home=source_home)

            self.assertEqual(
                (isolated / "auth.json").read_text(encoding="utf-8"),
                auth_content,
            )

    def test_prepare_isolated_codex_home_skips_auth_json_when_absent(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            source_home.mkdir()
            (source_home / "config.toml").write_text(CLEAN_BASE_CONFIG, encoding="utf-8")
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()

            isolated = prepare_isolated_codex_home(result_dir, source_home=source_home)

            self.assertFalse((isolated / "auth.json").exists())


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


class TestBenchmarkEnvForHarness(unittest.TestCase):
    def test_benchmark_env_opencode_sets_xdg(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = benchmark_env_for_harness(
                "opencode",
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
            )
            self.assertEqual(env["XDG_DATA_HOME"], str(result_dir / ".xdg-data"))

    def test_benchmark_env_codex_always_sets_codex_home(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = benchmark_env_for_harness(
                "codex",
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
                command_prefix=None,
            )
            self.assertIn("CODEX_HOME", env)
            self.assertTrue(Path(env["CODEX_HOME"]).is_dir())

    def test_benchmark_env_claude_sets_home_under_result_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = benchmark_env_for_harness(
                "claude",
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
            )
            self.assertEqual(
                env["HOME"],
                str((result_dir / AGENT_HOME_DIRNAME).resolve()),
            )

    def test_benchmark_env_cursor_sets_home_under_result_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            env = benchmark_env_for_harness(
                "cursor",
                {"PATH": "/usr/bin"},
                result_dir=result_dir,
            )
            self.assertEqual(
                env["HOME"],
                str((result_dir / AGENT_HOME_DIRNAME).resolve()),
            )


class TestStageSubscriptionAuth(unittest.TestCase):
    def test_stage_subscription_auth_copies_claude_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            isolated_home = Path(tmp) / "isolated"
            claude_dir = source_home / ".claude"
            claude_dir.mkdir(parents=True)
            (claude_dir / "settings.json").write_text("{}", encoding="utf-8")
            isolated_home.mkdir()

            copied = stage_subscription_auth(isolated_home, source_home, "claude")

            self.assertEqual(len(copied), 1)
            self.assertTrue((isolated_home / ".claude" / "settings.json").is_file())


class TestStageCursorAuth(unittest.TestCase):
    def test_stage_cursor_auth_stages_auth_json_when_present(self) -> None:
        auth_content = '{"accessToken":"test"}\n'
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            isolated_home = Path(tmp) / "isolated"
            cursor_config = source_home / ".config" / "cursor"
            cursor_config.mkdir(parents=True)
            (cursor_config / "auth.json").write_text(auth_content, encoding="utf-8")
            isolated_home.mkdir()

            copied = stage_cursor_auth(isolated_home, source_home)

            self.assertEqual(len(copied), 1)
            self.assertEqual(
                (isolated_home / ".config" / "cursor" / "auth.json").read_text(
                    encoding="utf-8"
                ),
                auth_content,
            )

    def test_stage_cursor_auth_skips_auth_json_when_absent(self) -> None:
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            isolated_home = Path(tmp) / "isolated"
            source_home.mkdir()
            isolated_home.mkdir()

            copied = stage_cursor_auth(isolated_home, source_home)

            self.assertEqual(copied, [])
            self.assertFalse(
                (isolated_home / ".config" / "cursor" / "auth.json").exists()
            )

    def test_stage_subscription_auth_cursor_stages_config_auth(self) -> None:
        auth_content = '{"accessToken":"test"}\n'
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            isolated_home = Path(tmp) / "isolated"
            cursor_dir = source_home / ".cursor"
            cursor_dir.mkdir(parents=True)
            (cursor_dir / "cli-config.json").write_text("{}", encoding="utf-8")
            cursor_config = source_home / ".config" / "cursor"
            cursor_config.mkdir(parents=True)
            (cursor_config / "auth.json").write_text(auth_content, encoding="utf-8")
            isolated_home.mkdir()

            copied = stage_subscription_auth(isolated_home, source_home, "cursor")

            self.assertEqual(len(copied), 2)
            self.assertTrue((isolated_home / ".cursor" / "cli-config.json").is_file())
            self.assertEqual(
                (isolated_home / ".config" / "cursor" / "auth.json").read_text(
                    encoding="utf-8"
                ),
                auth_content,
            )

    def test_benchmark_env_cursor_stages_auth_under_isolated_config(self) -> None:
        auth_content = '{"accessToken":"test"}\n'
        with TemporaryDirectory() as tmp:
            source_home = Path(tmp) / "source"
            cursor_config = source_home / ".config" / "cursor"
            cursor_config.mkdir(parents=True)
            (cursor_config / "auth.json").write_text(auth_content, encoding="utf-8")
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()

            with patch(
                "benchmark.agent_runtime_env.Path.home",
                return_value=source_home,
            ):
                env = benchmark_env_for_harness(
                    "cursor",
                    {"PATH": "/usr/bin"},
                    result_dir=result_dir,
                )

            agent_home = result_dir / AGENT_HOME_DIRNAME
            self.assertEqual(env["HOME"], str(agent_home.resolve()))
            self.assertEqual(
                (agent_home / ".config" / "cursor" / "auth.json").read_text(
                    encoding="utf-8"
                ),
                auth_content,
            )


class TestOpenCodeHarnessOllamaPreflight(unittest.TestCase):
    def test_opencode_harness_requires_ollama_binary(self) -> None:
        with patch("benchmark.harnesses.shutil.which", return_value=None):
            ok, err = check_harness_cli_requirements(
                "opencode",
                [{"command_prefix": ["ollama", "launch", "--yes", "opencode"]}],
            )
        self.assertFalse(ok)
        self.assertIn("ollama", err)


if __name__ == "__main__":
    unittest.main()
