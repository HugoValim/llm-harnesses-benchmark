"""Tests for the Harness registry — single lookup point for harness adapters."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.harnesses import (  # noqa: E402
    HARNESS_REGISTRY,
    Harness,
    UnknownHarnessError,
    get_harness,
    list_harnesses,
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


class TestHarnessIdentity(unittest.TestCase):
    def test_registry_dict_keys_match_names(self) -> None:
        for key, harness in HARNESS_REGISTRY.items():
            self.assertEqual(key, harness.name)


if __name__ == "__main__":
    unittest.main()
