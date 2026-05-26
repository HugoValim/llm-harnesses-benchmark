"""Tests for unified parallel model dispatch in run_benchmark.py."""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_benchmark import (  # noqa: E402
    _benchmark_job_workers,
    _needs_local_gpu_lock,
    _run_model_job_batch,
)


class TestBenchmarkJobWorkers(unittest.TestCase):
    def test_caps_at_jobs(self) -> None:
        self.assertEqual(_benchmark_job_workers(9, 2), 2)

    def test_jobs_zero_means_all_models(self) -> None:
        self.assertEqual(_benchmark_job_workers(5, 0), 5)

    def test_single_model(self) -> None:
        self.assertEqual(_benchmark_job_workers(1, 2), 1)


class TestLocalGpuLock(unittest.TestCase):
    def test_ollama_provider_needs_lock(self) -> None:
        self.assertTrue(_needs_local_gpu_lock([{"provider": "ollama", "slug": "x"}]))

    def test_cloud_provider_does_not(self) -> None:
        self.assertFalse(
            _needs_local_gpu_lock([{"provider": "ollama_cloud", "slug": "x"}])
        )


class TestRunModelJobBatch(unittest.TestCase):
    def test_parallel_submits_all_models(self) -> None:
        calls: list[str] = []

        def dispatch(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            calls.append(model["slug"])
            return {"slug": model["slug"], "status": "completed"}

        items = [
            (1, {"slug": "a", "provider": "openai"}),
            (2, {"slug": "b", "provider": "ollama_cloud"}),
        ]
        abort = threading.Event()
        with patch("run_benchmark._kill_stale_opencode_processes") as kill_mock:
            _run_model_job_batch(
                job_items=items,
                workers=2,
                harness="codex",
                abort_flag=abort,
                local_gpu_lock=None,
                dispatch_model=dispatch,
            )
        kill_mock.assert_not_called()
        self.assertEqual(sorted(calls), ["a", "b"])

    def test_parallel_opencode_kills_stale_once(self) -> None:
        def dispatch(model: dict, index: int, *, skip_stale_kill: bool = False) -> dict:
            return {"status": "completed"}

        items = [
            (1, {"slug": "a", "provider": "openrouter"}),
            (2, {"slug": "b", "provider": "openrouter"}),
        ]
        with patch("run_benchmark._kill_stale_opencode_processes") as kill_mock:
            _run_model_job_batch(
                job_items=items,
                workers=2,
                harness="opencode",
                abort_flag=threading.Event(),
                local_gpu_lock=None,
                dispatch_model=dispatch,
            )
        kill_mock.assert_called_once()

    def test_local_gpu_lock_serializes_ollama_runs(self) -> None:
        gpu_lock = threading.Lock()
        overlap = threading.Event()
        in_local = threading.Event()
        calls: list[str] = []

        def dispatch(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            calls.append(model["slug"])
            if model["provider"] == "ollama":
                if in_local.is_set():
                    overlap.set()
                in_local.set()
                time.sleep(0.05)
                in_local.clear()
            else:
                time.sleep(0.02)
            return {"status": "completed"}

        items = [
            (1, {"slug": "local_a", "provider": "ollama"}),
            (2, {"slug": "cloud_b", "provider": "ollama_cloud"}),
            (3, {"slug": "local_c", "provider": "ollama"}),
        ]
        _run_model_job_batch(
            job_items=items,
            workers=2,
            harness="codex",
            abort_flag=threading.Event(),
            local_gpu_lock=gpu_lock,
            dispatch_model=dispatch,
        )
        self.assertFalse(overlap.is_set(), "two local runs overlapped on GPU lock")
        self.assertEqual(len(calls), 3)

    def test_parallel_passes_skip_stale_kill(self) -> None:
        seen: list[bool] = []

        def dispatch(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            seen.append(skip_stale_kill)
            return {"status": "completed"}

        items = [
            (1, {"slug": "a", "provider": "openai"}),
            (2, {"slug": "b", "provider": "openai"}),
        ]
        _run_model_job_batch(
            job_items=items,
            workers=2,
            harness="codex",
            abort_flag=threading.Event(),
            local_gpu_lock=None,
            dispatch_model=dispatch,
        )
        self.assertEqual(seen, [True, True])


if __name__ == "__main__":
    unittest.main()
