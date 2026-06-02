"""Regression tests for benchmark agent runtime env (no per-run isolation)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.agent_runtime_env import (  # noqa: E402
    benchmark_env_for_harness,
    config_has_legacy_ollama_launch_profile,
    codex_env_for_phase,
    prepare_isolated_codex_home,
    runtime_isolation_for_env,
    strip_legacy_ollama_launch_profile,
)
from benchmark.harnesses import check_harness_cli_requirements  # noqa: E402

_ISOLATION_DIRS = (".codex-home", ".xdg-data", ".agent-home")


class TestBenchmarkEnvForHarness(unittest.TestCase):
    def test_benchmark_env_returns_unchanged_env(self) -> None:
        harnesses = ("opencode", "codex", "claude", "cursor")
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            base = {"PATH": "/usr/bin", "HOME": "/real/home"}
            for harness in harnesses:
                with self.subTest(harness=harness):
                    env = benchmark_env_for_harness(
                        harness,
                        dict(base),
                        result_dir=result_dir,
                    )
                    self.assertEqual(env, base)
                    for dirname in _ISOLATION_DIRS:
                        self.assertFalse((result_dir / dirname).exists())

    def test_benchmark_env_does_not_mutate_base_env(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            base = {"PATH": "/usr/bin"}
            benchmark_env_for_harness("codex", base, result_dir=result_dir)
            self.assertEqual(base, {"PATH": "/usr/bin"})


class TestRuntimeIsolationForEnv(unittest.TestCase):
    def test_returns_empty_when_no_isolation_keys(self) -> None:
        self.assertEqual(runtime_isolation_for_env({"PATH": "/usr/bin"}), {})

    def test_filters_only_isolation_keys_when_present(self) -> None:
        env = {
            "PATH": "/usr/bin",
            "CODEX_HOME": "/tmp/.codex-home",
            "HOME": "/tmp/home",
        }
        self.assertEqual(
            runtime_isolation_for_env(env),
            {"CODEX_HOME": "/tmp/.codex-home", "HOME": "/tmp/home"},
        )


class TestCodexLegacyOllamaLaunchProfile(unittest.TestCase):
    def test_detects_legacy_profile_key(self) -> None:
        payload = 'profile = "ollama-launch"\n[profiles.other]\nfoo="bar"\n'
        self.assertTrue(config_has_legacy_ollama_launch_profile(payload))

    def test_detects_legacy_profiles_table(self) -> None:
        payload = "[profiles.ollama-launch]\nfoo='bar'\n"
        self.assertTrue(config_has_legacy_ollama_launch_profile(payload))

    def test_strip_removes_legacy_profile_key_and_is_idempotent(self) -> None:
        payload = (
            'profile = "ollama-launch"\n'
            "[profiles.ollama-launch]\n"
            "foo = 1\n"
            "\n"
            "[profiles.keep]\n"
            "bar = 2\n"
        )
        stripped = strip_legacy_ollama_launch_profile(payload)
        self.assertNotIn('profile = "ollama-launch"', stripped)
        self.assertNotIn("[profiles.ollama-launch]", stripped)
        self.assertIn("[profiles.keep]", stripped)
        self.assertEqual(strip_legacy_ollama_launch_profile(stripped), stripped)


class TestCodexIsolatedHome(unittest.TestCase):
    def test_prepare_isolated_codex_home_strips_and_copies_expected_files(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "home" / ".codex"
            source.mkdir(parents=True)
            (source / "config.toml").write_text(
                'profile = "ollama-launch"\n[profiles.ollama-launch]\nfoo=1\n'
            )
            (source / "ollama-launch.config.toml").write_text("[x]\n")
            (source / "auth.json").write_text('{"token":"redacted"}\n')

            dest = tmp_path / "dest"
            prepare_isolated_codex_home(source_home=source, dest_home=dest)

            self.assertTrue(dest.is_dir())
            self.assertTrue((dest / "config.toml").is_file())
            self.assertTrue((dest / "ollama-launch.config.toml").is_file())
            self.assertFalse((dest / "auth.json").exists())
            self.assertFalse(
                config_has_legacy_ollama_launch_profile((dest / "config.toml").read_text())
            )

    def test_codex_env_for_phase_only_sets_codex_home_for_ollama_launch_codex(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_home = tmp_path / "home"
            source = fake_home / ".codex"
            source.mkdir(parents=True)
            (source / "config.toml").write_text('profile="ollama-launch"\n')

            result_dir = tmp_path / "run_01"
            result_dir.mkdir()
            base_env = {"PATH": "/usr/bin"}

            with patch("pathlib.Path.home", return_value=fake_home):
                env = codex_env_for_phase(
                    base_env,
                    result_dir=result_dir,
                    command_prefix=["ollama", "launch", "--yes", "codex"],
                )
                self.assertIn("CODEX_HOME", env)
                self.assertTrue((result_dir / ".codex-home").is_dir())

                env_plain = codex_env_for_phase(
                    base_env,
                    result_dir=result_dir,
                    command_prefix=None,
                )
                self.assertNotIn("CODEX_HOME", env_plain)


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
