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

from benchmark.campaign_dispatch import (  # noqa: E402
    VariantCampaignConfig,
    benchmark_job_workers,
    needs_local_gpu_lock,
    run_model_campaign,
    run_model_job_batch,
    run_variant_campaign,
)
from benchmark.config import BenchmarkConfig  # noqa: E402
from benchmark.rate_limit import RateLimitWaitPolicy  # noqa: E402


class TestBenchmarkJobWorkers(unittest.TestCase):
    def test_caps_at_jobs(self) -> None:
        self.assertEqual(benchmark_job_workers(9, 2), 2)

    def test_jobs_zero_means_all_models(self) -> None:
        self.assertEqual(benchmark_job_workers(5, 0), 5)

    def test_single_model(self) -> None:
        self.assertEqual(benchmark_job_workers(1, 2), 1)


class TestLocalGpuLock(unittest.TestCase):
    def test_ollama_provider_needs_lock(self) -> None:
        self.assertTrue(needs_local_gpu_lock([{"provider": "ollama", "slug": "x"}]))

    def test_cloud_provider_does_not(self) -> None:
        self.assertFalse(
            needs_local_gpu_lock([{"provider": "ollama_cloud", "slug": "x"}])
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
        with patch("benchmark.campaign_dispatch.kill_stale_opencode_processes") as kill_mock:
            run_model_job_batch(
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
        with patch("benchmark.campaign_dispatch.kill_stale_opencode_processes") as kill_mock:
            run_model_job_batch(
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
        run_model_job_batch(
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
        run_model_job_batch(
            job_items=items,
            workers=2,
            harness="codex",
            abort_flag=threading.Event(),
            local_gpu_lock=None,
            dispatch_model=dispatch,
        )
        self.assertEqual(seen, [True, True])


class TestRunModelCampaign(unittest.TestCase):
    def test_runs_configured_replicates(self) -> None:
        bench = BenchmarkConfig(
            runner={},
            config_path=REPO_ROOT / "config" / "models.json",
            results_dir=REPO_ROOT / "tmp" / "results",
            harness="codex",
            timeout_seconds=60,
            no_progress_timeout_seconds=30,
            min_preview_output_tps=None,
            min_preview_samples=3,
            auto_skip_slow_preview=False,
            force=False,
            selected_models=[
                {"slug": "demo", "provider": "openai", "num_runs": 2}
            ],
        )
        calls: list[tuple[int, int | None, bool]] = []

        def run_model_fn(
            model: dict,
            active_bench: BenchmarkConfig,
            index: int,
            total: int,
            *,
            skip_stale_kill: bool = False,
            replicate_index: int = 1,
            num_runs: int | None = None,
        ) -> dict:
            calls.append((replicate_index, num_runs, active_bench.force))
            return {"status": "completed", "slug": model["slug"]}

        result = run_model_campaign(
            bench,
            jobs=1,
            validate_results=False,
            max_validation_retries=0,
            run_model_fn=run_model_fn,
        )

        self.assertFalse(result.usage_limit_aborted)
        self.assertEqual(calls, [(1, 2, False), (2, 2, False)])


class TestRunVariantCampaign(unittest.TestCase):
    def test_runs_configured_replicates(self) -> None:
        calls: list[tuple[int, int | None, bool, bool | None]] = []

        def run_variant(**kwargs: object) -> dict[str, str]:
            num_runs = kwargs["num_runs"] if isinstance(kwargs["num_runs"], int) else None
            isolate_home = (
                kwargs.get("isolate_home")
                if isinstance(kwargs.get("isolate_home"), bool)
                else None
            )
            calls.append(
                (
                    int(kwargs["replicate_index"]),
                    num_runs,
                    bool(kwargs["force"]),
                    isolate_home,
                )
            )
            return {"status": "completed"}

        config = VariantCampaignConfig(
            variants=[
                {
                    "slug": "demo",
                    "provider": "anthropic",
                    "main_model": "claude-test",
                    "num_runs": 2,
                }
            ],
            jobs=1,
            harness_name="claude",
            run_variant=run_variant,
            accepts_isolate_home=True,
            prompt="build app",
            results_dir=REPO_ROOT / "tmp" / "variant-results",
            timeout_seconds=60,
            no_progress_timeout_seconds=30,
            force=False,
            runner_command_prefix=None,
            isolate_home=True,
            followup_prompt="check app",
            rate_limit_policy=RateLimitWaitPolicy(),
            validate_results=False,
            max_validation_retries=0,
        )

        result = run_variant_campaign(config)

        self.assertFalse(result.usage_limit_aborted)
        self.assertEqual(calls, [(1, 2, False, True), (2, 2, False, True)])


if __name__ == "__main__":
    unittest.main()
