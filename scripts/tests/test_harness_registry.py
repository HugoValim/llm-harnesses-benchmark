"""Tests for the Harness registry — single lookup point for harness adapters."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.harnesses import (  # noqa: E402
    HARNESS_REGISTRY,
    Harness,
    UnknownHarnessError,
    canonical_harness_name,
    check_harness_cli_requirements,
    get_harness,
    list_harnesses,
    model_matches_harness,
)


class TestHarnessRegistry(unittest.TestCase):
    def test_all_canonical_harnesses_registered(self) -> None:
        self.assertEqual(
            set(list_harnesses()),
            {"opencode", "codex", "claude", "cursor"},
        )

    def test_get_harness_returns_named_adapter(self) -> None:
        h = get_harness("claude")
        self.assertIsInstance(h, Harness)
        self.assertEqual(h.name, "claude")

    def test_unknown_harness_raises(self) -> None:
        with self.assertRaises(UnknownHarnessError) as ctx:
            get_harness("nonexistent")
        msg = str(ctx.exception)
        self.assertIn("nonexistent", msg)
        # Error message includes available harnesses for discoverability.
        for canonical in ("opencode", "codex", "claude", "cursor"):
            self.assertIn(canonical, msg)

    def test_registry_has_run_variant_for_each_cli(self) -> None:
        for name in list_harnesses():
            h = get_harness(name)
            self.assertTrue(
                callable(h.run_variant),
                f"{name} harness has no run_variant",
            )

    def test_only_model_harnesses_expose_run_model(self) -> None:
        # opencode + codex are "model harnesses" — benchmark entrypoint
        # dispatches per model row, not per variant.
        for name in ("opencode", "codex"):
            self.assertTrue(
                callable(get_harness(name).run_model),
                f"{name} harness has no run_model",
            )
        # claude + cursor are variant-only — no run_model.
        for name in ("claude", "cursor"):
            self.assertIsNone(get_harness(name).run_model)

    def test_ollama_alias_routes_to_codex_harness(self) -> None:
        self.assertEqual(canonical_harness_name("ollama"), "codex")

    def test_model_runner_types_are_harness_owned(self) -> None:
        self.assertTrue(model_matches_harness({"runner_type": "ollama"}, "codex"))
        self.assertFalse(model_matches_harness({"runner_type": "ollama"}, "opencode"))

    def test_codex_ollama_model_requires_ollama_binary(self) -> None:
        with patch("benchmark.harnesses.shutil.which", return_value=None):
            ok, err = check_harness_cli_requirements(
                "codex", [{"runner_type": "ollama"}]
            )
        self.assertFalse(ok)
        self.assertIn("ollama", err)


class TestHarnessIdentity(unittest.TestCase):
    def test_registry_dict_keys_match_names(self) -> None:
        for key, harness in HARNESS_REGISTRY.items():
            self.assertEqual(key, harness.name)


if __name__ == "__main__":
    unittest.main()
