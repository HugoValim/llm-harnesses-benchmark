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
    ModelSlotLocks,
    VariantCampaignConfig,
    benchmark_job_workers,
    expand_model_jobs_to_replicate_jobs,
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


class TestExpandModelJobs(unittest.TestCase):
    def test_expands_num_runs_per_model(self) -> None:
        items = [
            (1, {"slug": "a", "num_runs": 2}),
            (2, {"slug": "b", "num_runs": 1}),
        ]
        expanded = expand_model_jobs_to_replicate_jobs(items)
        self.assertEqual(len(expanded), 3)
        self.assertEqual(
            [(job.model["slug"], job.replicate_index) for job in expanded],
            [("a", 1), ("b", 1), ("a", 2)],
        )

    def test_filters_single_replicate_index(self) -> None:
        items = [(1, {"slug": "a", "num_runs": 3})]
        expanded = expand_model_jobs_to_replicate_jobs(items, replicate_index=2)
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].replicate_index, 2)


class TestRunModelJobBatch(unittest.TestCase):
    def _dispatch_replicate(
        self,
        calls: list[tuple[str, int]],
        model: dict,
        index: int,
        replicate_index: int,
        num_runs: int,
        *,
        skip_stale_kill: bool = False,
    ) -> dict:
        calls.append((model["slug"], replicate_index))
        return {"slug": model["slug"], "status": "completed"}

    def test_parallel_submits_all_models(self) -> None:
        calls: list[tuple[str, int]] = []

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            calls.append((model["slug"], 1))
            return {"slug": model["slug"], "status": "completed"}

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
        ) -> dict:
            return self._dispatch_replicate(
                calls, model, index, replicate_index, num_runs
            )

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
                dispatch_model=dispatch_model,
                dispatch_replicate=dispatch_replicate,
            )
        kill_mock.assert_not_called()
        self.assertEqual(sorted(calls), [("a", 1), ("b", 1)])

    def test_parallel_schedules_replicates_independently(self) -> None:
        calls: list[tuple[str, int]] = []

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            raise AssertionError("sequential dispatch should not run in parallel mode")

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
        ) -> dict:
            return self._dispatch_replicate(
                calls, model, index, replicate_index, num_runs
            )

        items = [
            (1, {"slug": "a", "provider": "openai", "num_runs": 2}),
            (2, {"slug": "b", "provider": "openai", "num_runs": 1}),
        ]
        run_model_job_batch(
            job_items=items,
            workers=2,
            harness="codex",
            abort_flag=threading.Event(),
            local_gpu_lock=None,
            model_slot_locks=ModelSlotLocks(),
            dispatch_model=dispatch_model,
            dispatch_replicate=dispatch_replicate,
        )
        self.assertEqual(
            sorted(calls),
            [("a", 1), ("a", 2), ("b", 1)],
        )

    def test_parallel_keeps_worker_pool_full(self) -> None:
        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            raise AssertionError("sequential dispatch should not run in parallel mode")

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
        ) -> dict:
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with active_lock:
                active -= 1
            return {"status": "completed"}

        items = [
            (1, {"slug": "a", "provider": "openai", "num_runs": 1}),
            (2, {"slug": "b", "provider": "openai", "num_runs": 1}),
            (3, {"slug": "c", "provider": "openai", "num_runs": 1}),
            (4, {"slug": "d", "provider": "openai", "num_runs": 1}),
        ]
        run_model_job_batch(
            job_items=items,
            workers=3,
            harness="codex",
            abort_flag=threading.Event(),
            local_gpu_lock=None,
            dispatch_model=dispatch_model,
            dispatch_replicate=dispatch_replicate,
        )
        self.assertEqual(max_active, 3)

    def test_parallel_opencode_kills_stale_once(self) -> None:
        def dispatch_model(model: dict, index: int, *, skip_stale_kill: bool = False) -> dict:
            return {"status": "completed"}

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
        ) -> dict:
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
                dispatch_model=dispatch_model,
                dispatch_replicate=dispatch_replicate,
            )
        kill_mock.assert_called_once()

    def test_local_gpu_lock_serializes_ollama_runs(self) -> None:
        gpu_lock = threading.Lock()
        overlap = threading.Event()
        in_local = threading.Event()
        calls: list[str] = []

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            calls.append(model["slug"])
            return {"status": "completed"}

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
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
            dispatch_model=dispatch_model,
            dispatch_replicate=dispatch_replicate,
        )
        self.assertFalse(overlap.is_set(), "two local runs overlapped on GPU lock")
        self.assertEqual(len(calls), 3)

    def test_skip_stale_opencode_kill_in_sequential_batch(self) -> None:
        seen: list[bool] = []

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            seen.append(skip_stale_kill)
            return {"status": "completed"}

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
        ) -> dict:
            raise AssertionError("sequential dispatch should run in sequential mode")

        items = [(1, {"slug": "a", "provider": "ollama_cloud"})]
        run_model_job_batch(
            job_items=items,
            workers=1,
            harness="opencode",
            abort_flag=threading.Event(),
            local_gpu_lock=None,
            dispatch_model=dispatch_model,
            dispatch_replicate=dispatch_replicate,
            skip_stale_opencode_kill=True,
        )
        self.assertEqual(seen, [True])

    def test_parallel_passes_skip_stale_kill(self) -> None:
        seen: list[bool] = []

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            seen.append(skip_stale_kill)
            return {"status": "completed"}

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
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
            dispatch_model=dispatch_model,
            dispatch_replicate=dispatch_replicate,
        )
        self.assertEqual(seen, [True, True])

    def test_parallel_never_runs_same_model_replicate_overlap(self) -> None:
        active_by_slug: dict[str, int] = {}
        overlap = threading.Event()
        active_lock = threading.Lock()
        slot_locks = ModelSlotLocks()

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            raise AssertionError("sequential dispatch should not run in parallel mode")

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
        ) -> dict:
            slug = model["slug"]
            with active_lock:
                active_by_slug[slug] = active_by_slug.get(slug, 0) + 1
                if active_by_slug[slug] > 1:
                    overlap.set()
            time.sleep(0.05)
            with active_lock:
                active_by_slug[slug] -= 1
            return {"status": "completed"}

        items = [(1, {"slug": "solo", "provider": "openai", "num_runs": 3})]
        run_model_job_batch(
            job_items=items,
            workers=3,
            harness="codex",
            abort_flag=threading.Event(),
            local_gpu_lock=None,
            model_slot_locks=slot_locks,
            dispatch_model=dispatch_model,
            dispatch_replicate=dispatch_replicate,
        )
        self.assertFalse(overlap.is_set(), "same model ran overlapping replicates")

    def test_parallel_prefers_different_models_at_same_replicate(self) -> None:
        calls: list[tuple[str, int]] = []
        call_lock = threading.Lock()
        slot_locks = ModelSlotLocks()

        def dispatch_model(
            model: dict, index: int, *, skip_stale_kill: bool = False
        ) -> dict:
            raise AssertionError("sequential dispatch should not run in parallel mode")

        def dispatch_replicate(
            model: dict,
            index: int,
            replicate_index: int,
            num_runs: int,
            *,
            skip_stale_kill: bool = False,
        ) -> dict:
            with call_lock:
                calls.append((model["slug"], replicate_index))
            time.sleep(0.02)
            return {"status": "completed"}

        items = [
            (1, {"slug": "a", "provider": "openai", "num_runs": 3}),
            (2, {"slug": "b", "provider": "openai", "num_runs": 3}),
            (3, {"slug": "c", "provider": "openai", "num_runs": 3}),
        ]
        run_model_job_batch(
            job_items=items,
            workers=3,
            harness="codex",
            abort_flag=threading.Event(),
            local_gpu_lock=None,
            model_slot_locks=slot_locks,
            dispatch_model=dispatch_model,
            dispatch_replicate=dispatch_replicate,
        )
        first_wave = sorted(calls[:3])
        self.assertEqual(
            first_wave,
            [("a", 1), ("b", 1), ("c", 1)],
        )


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

    def test_replicate_index_runs_single_replicate(self) -> None:
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
                {"slug": "demo", "provider": "openai", "num_runs": 3}
            ],
            replicate_index=2,
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

        run_model_campaign(
            bench,
            jobs=1,
            validate_results=False,
            max_validation_retries=0,
            run_model_fn=run_model_fn,
        )

        self.assertEqual(calls, [(2, 3, False)])


class TestRunVariantCampaign(unittest.TestCase):
    def test_runs_configured_replicates(self) -> None:
        calls: list[tuple[int, int | None, bool]] = []

        def run_variant(**kwargs: object) -> dict[str, str]:
            num_runs = kwargs["num_runs"] if isinstance(kwargs["num_runs"], int) else None
            calls.append(
                (
                    int(kwargs["replicate_index"]),
                    num_runs,
                    bool(kwargs["force"]),
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
            prompt="build app",
            results_dir=REPO_ROOT / "tmp" / "variant-results",
            timeout_seconds=60,
            no_progress_timeout_seconds=30,
            force=False,
            runner_command_prefix=None,
            followup_prompt="check app",
            rate_limit_policy=RateLimitWaitPolicy(),
            validate_results=False,
            max_validation_retries=0,
        )

        result = run_variant_campaign(config)

        self.assertFalse(result.usage_limit_aborted)
        self.assertEqual(calls, [(1, 2, False), (2, 2, False)])
        # Campaign always passes build parity flags for benchmark builds.
        # Verified via run_variant kwargs capture in TestBuildParityDispatch.


class TestBuildParityDispatch(unittest.TestCase):
    def test_variant_campaign_passes_build_parity_kwargs(self) -> None:
        captured: list[dict[str, object]] = []

        def run_variant(**kwargs: object) -> dict[str, str]:
            captured.append(dict(kwargs))
            return {"status": "completed"}

        config = VariantCampaignConfig(
            variants=[
                {
                    "slug": "demo",
                    "provider": "anthropic",
                    "main_model": "claude-test",
                    "num_runs": 1,
                }
            ],
            jobs=1,
            harness_name="claude",
            run_variant=run_variant,
            prompt="build app",
            results_dir=REPO_ROOT / "tmp" / "parity-variant-results",
            timeout_seconds=60,
            no_progress_timeout_seconds=30,
            force=False,
            runner_command_prefix=None,
            followup_prompt="check app",
            rate_limit_policy=RateLimitWaitPolicy(),
            validate_results=False,
            max_validation_retries=0,
        )

        run_variant_campaign(config)

        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0]["for_benchmark_build"])
        self.assertTrue(captured[0]["wrap_primary_prompt"])

    def test_parallel_schedules_replicates_independently(self) -> None:
        calls: list[tuple[int, int | None]] = []

        def run_variant(**kwargs: object) -> dict[str, str]:
            calls.append(
                (
                    int(kwargs["replicate_index"]),
                    kwargs["num_runs"] if isinstance(kwargs["num_runs"], int) else None,
                )
            )
            time.sleep(0.02)
            return {"status": "completed"}

        config = VariantCampaignConfig(
            variants=[
                {
                    "slug": "demo_a",
                    "provider": "anthropic",
                    "main_model": "claude-test",
                    "num_runs": 2,
                },
                {
                    "slug": "demo_b",
                    "provider": "anthropic",
                    "main_model": "claude-test",
                    "num_runs": 1,
                },
            ],
            jobs=2,
            harness_name="claude",
            run_variant=run_variant,
            prompt="build app",
            results_dir=REPO_ROOT / "tmp" / "variant-results-parallel",
            timeout_seconds=60,
            no_progress_timeout_seconds=30,
            force=False,
            runner_command_prefix=None,
            followup_prompt="check app",
            rate_limit_policy=RateLimitWaitPolicy(),
            validate_results=False,
            max_validation_retries=0,
        )

        result = run_variant_campaign(config)

        self.assertFalse(result.usage_limit_aborted)
        self.assertEqual(sorted(calls), [(1, 1), (1, 2), (2, 2)])


if __name__ == "__main__":
    unittest.main()
