"""Tests for scripts/benchmark/full_pipeline.py build matrix."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import resolve_build_harness_config  # noqa: E402
from benchmark.defaults import DEFAULT_AUDITOR_SLUG, DEFAULT_JOBS  # noqa: E402
from benchmark.full_pipeline import (  # noqa: E402
    BuildJob,
    build_benchmark_argv,
    build_job_argv,
    build_matrix,
    dispatch_build_jobs,
    dispatch_build_jobs_by_replicate_wave,
    dispatch_build_jobs_pipelined,
    expand_build_matrix_to_jobs,
    group_build_batches,
    phase_audit,
    phase_build,
    reject_forwarded_model_flag,
    resolve_meta_config,
)
from benchmark.harnesses import list_harnesses  # noqa: E402
from benchmark.util import load_json  # noqa: E402

MODELS_CONFIG = REPO_ROOT / "config" / "models.json"
HARNESSES_CONFIG = REPO_ROOT / "config" / "harnesses.json"


def _expected_matrix_steps() -> list[tuple[str, str]]:
    from benchmark.config import _normalize_registry_models, registry_harness_values
    from benchmark.harnesses import dispatch_harness

    config = load_json(MODELS_CONFIG)
    steps: list[tuple[str, str]] = []
    for model in _normalize_registry_models(config.get("models")):
        slug = model.get("slug")
        if not slug:
            continue
        for registry_harness in registry_harness_values(model):
            steps.append((dispatch_harness(registry_harness), str(slug)))
    return steps


def test_build_matrix_expands_harness_list(tmp_path: Path) -> None:
    config_path = tmp_path / "models.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": [
                            "ollama_claude",
                            "ollama_codex",
                            "ollama_opencode",
                        ],
                        "num_runs": 3,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    steps = build_matrix(config_path)
    assert {(s.harness, s.model_slug) for s in steps} == {
        ("claude", "kimi_k2_6"),
        ("codex", "kimi_k2_6"),
        ("opencode", "kimi_k2_6"),
    }


def test_build_matrix_covers_all_registry_harness_pairs() -> None:
    steps = build_matrix(MODELS_CONFIG)
    assert {(s.harness, s.model_slug) for s in steps} == set(_expected_matrix_steps())


def test_build_matrix_includes_cursor_models() -> None:
    steps = build_matrix(MODELS_CONFIG)
    cursor_slugs = {s.model_slug for s in steps if s.harness == "cursor"}
    assert cursor_slugs == {"composer_2_5"}


def test_build_matrix_includes_ollama_opencode_models() -> None:
    steps = build_matrix(MODELS_CONFIG)
    opencode_slugs = {s.model_slug for s in steps if s.harness == "opencode"}
    assert "kimi_k2_6" in opencode_slugs
    assert "deepseek_v4_pro" in opencode_slugs


def test_reject_forwarded_model_flag() -> None:
    try:
        reject_forwarded_model_flag(["--force", "--model", "x"])
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_group_build_batches_batches_by_harness() -> None:
    steps = build_matrix(MODELS_CONFIG)
    batches = group_build_batches(steps)
    assert {b.harness for b in batches} == set(list_harnesses())
    assert sum(len(b.model_slugs) for b in batches) == len(steps)


def test_build_benchmark_argv_includes_jobs() -> None:
    steps = build_matrix(MODELS_CONFIG)
    batch = group_build_batches(steps)[0]
    argv = build_benchmark_argv(
        batch,
        models_config=MODELS_CONFIG,
        results_dir=REPO_ROOT / "results",
        jobs=DEFAULT_JOBS,
        extra_args=[],
    )
    j_index = argv.index("-j")
    assert argv[j_index + 1] == str(DEFAULT_JOBS)


def test_default_auditor_is_codex_gpt_5_5() -> None:
    assert DEFAULT_AUDITOR_SLUG == "codex_gpt_5_5"


def test_default_jobs_is_three() -> None:
    assert DEFAULT_JOBS == 3


def test_resolve_meta_config_default_auditor_uses_codex() -> None:
    auditor_harness, meta_slug, meta_harness, meta_input = resolve_meta_config(
        HARNESSES_CONFIG,
        MODELS_CONFIG,
        DEFAULT_AUDITOR_SLUG,
        None,
        None,
        None,
    )
    assert auditor_harness == "codex"
    assert meta_slug == DEFAULT_AUDITOR_SLUG
    assert meta_harness == "codex"
    assert meta_input == DEFAULT_AUDITOR_SLUG


def test_phase_audit_dry_run_passes_codex_harness(capsys: pytest.CaptureFixture[str]) -> None:
    phase_audit(
        MODELS_CONFIG,
        REPO_ROOT / "results" / "run_02" / "projects",
        REPO_ROOT / "results" / "run_02" / "audit-reports",
        DEFAULT_AUDITOR_SLUG,
        "codex",
        jobs=DEFAULT_JOBS,
        run_id="run_02",
        dry_run=True,
    )
    out = capsys.readouterr().out
    assert "--run-id run_02" in out
    assert "--harness codex" in out
    assert f"--model {DEFAULT_AUDITOR_SLUG}" in out
    assert f"-j {DEFAULT_JOBS}" in out


def test_build_benchmark_argv_with_run_id() -> None:
    steps = build_matrix(MODELS_CONFIG)
    batch = group_build_batches(steps)[0]
    argv = build_benchmark_argv(
        batch,
        models_config=MODELS_CONFIG,
        results_dir=REPO_ROOT / "results",
        jobs=DEFAULT_JOBS,
        extra_args=[],
        run_id="run_02",
    )
    assert "--run-id" in argv
    assert "run_02" in argv
    assert "--results-dir" not in argv


def test_list_steps_cli() -> None:
    import subprocess

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_full_benchmark.py"),
            "--run-id",
            "run_01",
            "--list-steps",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    lines = [ln for ln in completed.stdout.strip().splitlines() if ln]
    assert len(lines) == len(_expected_matrix_steps())
    assert "claude_opus_4_7" in completed.stdout
    assert "codex_gpt_5_5" in completed.stdout
    assert "composer_2_5" in completed.stdout


def test_expand_build_matrix_to_jobs_includes_all_replicates(tmp_path: Path) -> None:
    config_path = tmp_path / "models.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": ["ollama_claude", "ollama_codex"],
                        "num_runs": 3,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    steps = build_matrix(config_path)
    jobs = expand_build_matrix_to_jobs(steps, models_config=config_path)
    assert len(jobs) == 6
    assert {(j.harness, j.model_slug, j.replicate_index) for j in jobs} == {
        ("claude", "kimi_k2_6", 1),
        ("claude", "kimi_k2_6", 2),
        ("claude", "kimi_k2_6", 3),
        ("codex", "kimi_k2_6", 1),
        ("codex", "kimi_k2_6", 2),
        ("codex", "kimi_k2_6", 3),
    }


def test_expand_build_matrix_orders_replicate_first_within_harness(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "models.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": ["ollama_codex"],
                        "num_runs": 3,
                    },
                    {
                        "slug": "qwen3_5_plus",
                        "provider": "openrouter",
                        "id": "qwen/qwen3.5-plus",
                        "harness": ["codex"],
                        "num_runs": 3,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    steps = build_matrix(config_path)
    jobs = expand_build_matrix_to_jobs(steps, models_config=config_path)
    assert [(j.model_slug, j.replicate_index) for j in jobs] == [
        ("kimi_k2_6", 1),
        ("qwen3_5_plus", 1),
        ("kimi_k2_6", 2),
        ("qwen3_5_plus", 2),
        ("kimi_k2_6", 3),
        ("qwen3_5_plus", 3),
    ]


def test_build_job_argv_runs_single_replicate_with_global_pool_defaults() -> None:
    argv = build_job_argv(
        BuildJob("codex", "kimi_k2_6", 2, 3),
        models_config=MODELS_CONFIG,
        results_dir=REPO_ROOT / "results",
        extra_args=["--no-docker-prune"],
        run_id="run_02",
    )
    assert "--harness codex".split()[0] in argv
    assert argv[argv.index("--harness") + 1] == "codex"
    assert argv[argv.index("--model") + 1] == "kimi_k2_6"
    assert argv[argv.index("--replicate-index") + 1] == "2"
    assert argv[argv.index("-j") + 1] == "1"
    assert "--no-docker-prune" in argv


def test_build_job_argv_adds_skip_stale_opencode_kill_for_opencode() -> None:
    argv = build_job_argv(
        BuildJob("opencode", "kimi_k2_6", 1, 3),
        models_config=MODELS_CONFIG,
        results_dir=REPO_ROOT / "results",
        extra_args=[],
        run_id="run_02",
    )
    assert "--skip-stale-opencode-kill" in argv

    codex_argv = build_job_argv(
        BuildJob("codex", "kimi_k2_6", 1, 3),
        models_config=MODELS_CONFIG,
        results_dir=REPO_ROOT / "results",
        extra_args=[],
        run_id="run_02",
    )
    assert "--skip-stale-opencode-kill" not in codex_argv


def test_dispatch_build_jobs_pipelined_serializes_opencode() -> None:
    import threading
    import time

    active_opencode = 0
    overlap = threading.Event()
    active_lock = threading.Lock()

    def fake_run_cmd(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        harness = cmd[cmd.index("--harness") + 1]
        nonlocal active_opencode
        if harness != "opencode":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with active_lock:
            active_opencode += 1
            if active_opencode > 1:
                overlap.set()
        time.sleep(0.05)
        with active_lock:
            active_opencode -= 1
        return subprocess.CompletedProcess(cmd, 0, "", "")

    jobs = [
        BuildJob("opencode", "kimi_k2_6", 1, 1),
        BuildJob("codex", "kimi_k2_6", 1, 1),
        BuildJob("opencode", "qwen3_5", 1, 1),
    ]
    with patch("benchmark.full_pipeline.kill_stale_opencode_processes") as kill_mock:
        dispatch_build_jobs_pipelined(
            jobs,
            workers=3,
            models_config=MODELS_CONFIG,
            results_dir=REPO_ROOT / "results",
            extra_args=[],
            run_cmd=fake_run_cmd,
        )
    kill_mock.assert_called_once()
    assert not overlap.is_set()


def test_dispatch_build_jobs_starts_second_harness_before_first_finishes() -> None:
    import threading
    import time

    started: list[str] = []
    lock = threading.Lock()
    claude_release = threading.Event()

    def fake_run_cmd(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        harness = cmd[cmd.index("--harness") + 1]
        with lock:
            started.append(harness)
        if harness == "claude":
            claude_release.wait(timeout=5.0)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    jobs = [
        BuildJob("claude", "kimi_k2_6", 1, 1),
        BuildJob("codex", "kimi_k2_6", 1, 1),
    ]
    results: list[tuple[str, int]] = []

    def runner() -> None:
        results.extend(
            dispatch_build_jobs(
                jobs,
                workers=2,
                models_config=MODELS_CONFIG,
                results_dir=REPO_ROOT / "results",
                extra_args=[],
                run_cmd=fake_run_cmd,
            )
        )

    thread = threading.Thread(target=runner)
    thread.start()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        with lock:
            if len(started) >= 2:
                break
        time.sleep(0.01)
    assert sorted(started[:2]) == ["claude", "codex"]
    claude_release.set()
    thread.join(timeout=5.0)
    assert set(results) == {("claude:kimi_k2_6", 0), ("codex:kimi_k2_6", 0)}


def test_dispatch_build_jobs_never_overlaps_same_target_replicates(
    tmp_path: Path,
) -> None:
    import threading
    import time

    active: dict[tuple[str, str], int] = {}
    overlap = threading.Event()
    active_lock = threading.Lock()

    def fake_run_cmd(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        harness = cmd[cmd.index("--harness") + 1]
        model = cmd[cmd.index("--model") + 1]
        key = (harness, model)
        with active_lock:
            active[key] = active.get(key, 0) + 1
            if active[key] > 1:
                overlap.set()
        time.sleep(0.05)
        with active_lock:
            active[key] -= 1
        return subprocess.CompletedProcess(cmd, 0, "", "")

    jobs = [
        BuildJob("codex", "kimi_k2_6", 1, 3),
        BuildJob("codex", "kimi_k2_6", 2, 3),
        BuildJob("codex", "kimi_k2_6", 3, 3),
    ]
    dispatch_build_jobs_pipelined(
        jobs,
        workers=3,
        models_config=MODELS_CONFIG,
        results_dir=tmp_path,
        extra_args=[],
        run_cmd=fake_run_cmd,
    )
    assert not overlap.is_set(), "same harness/model replicates overlapped"


def test_dispatch_build_jobs_pipelined_starts_run2_while_straggler_on_run1(
    tmp_path: Path,
) -> None:
    import threading
    import time

    started: list[tuple[str, int]] = []
    lock = threading.Lock()
    slow_release = threading.Event()

    def fake_run_cmd(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        model = cmd[cmd.index("--model") + 1]
        replicate = int(cmd[cmd.index("--replicate-index") + 1])
        with lock:
            started.append((model, replicate))
        if model == "slow" and replicate == 1:
            slow_release.wait(timeout=5.0)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    jobs = [
        BuildJob("codex", "slow", 1, 2),
        BuildJob("codex", "slow", 2, 2),
        BuildJob("codex", "fast", 1, 2),
        BuildJob("codex", "fast", 2, 2),
    ]
    results: list[tuple[str, int]] = []

    def runner() -> None:
        results.extend(
            dispatch_build_jobs_pipelined(
                jobs,
                workers=3,
                models_config=MODELS_CONFIG,
                results_dir=tmp_path,
                extra_args=[],
                run_cmd=fake_run_cmd,
            )
        )

    thread = threading.Thread(target=runner)
    thread.start()
    deadline = time.time() + 2.0
    while time.time() < deadline:
        with lock:
            if ("fast", 2) in started:
                break
        time.sleep(0.01)
    with lock:
        fast_run2_started_before_release = ("fast", 2) in started
    assert fast_run2_started_before_release, (
        "expected fast run_02 to start while slow run_01 still blocked"
    )
    slow_release.set()
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert set(results) == {
        ("codex:slow/run_01", 0),
        ("codex:slow/run_02", 0),
        ("codex:fast/run_01", 0),
        ("codex:fast/run_02", 0),
    }


def test_phase_build_forwards_no_docker_prune_and_prunes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "models.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": ["ollama_claude"],
                        "num_runs": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    captured_extra: list[list[str]] = []
    prune_calls: list[int] = []

    def fake_dispatch(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured_extra.append(list(kwargs["extra_args"]))
        jobs = args[0] if args else kwargs["jobs"]
        return [(job.label(), 0) for job in jobs]

    monkeypatch.setattr(
        "benchmark.full_pipeline.dispatch_build_jobs_pipelined", fake_dispatch
    )
    monkeypatch.setattr(
        "benchmark.full_pipeline._cleanup_docker_after_phase_build",
        lambda extra_args: prune_calls.append(1),
    )

    phase_build(
        config_path,
        tmp_path,
        [],
        jobs=1,
        dry_run=False,
        sequential_build=False,
    )
    assert captured_extra
    assert "--no-docker-prune" in captured_extra[0]
    assert prune_calls == [1]


def test_phase_build_raises_when_any_job_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "models.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": ["ollama_claude"],
                        "num_runs": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "benchmark.full_pipeline.dispatch_build_jobs_pipelined",
        lambda *args, **kwargs: [("claude:kimi_k2_6", 1)],
    )

    with pytest.raises(SystemExit, match="build failed"):
        phase_build(
            config_path,
            tmp_path,
            [],
            jobs=1,
            dry_run=False,
            sequential_build=False,
        )


def test_phase_build_uses_pipelined_dispatcher_not_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "models.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": ["ollama_claude"],
                        "num_runs": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pipelined_called = False
    wave_called = False

    def fake_pipelined(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal pipelined_called
        pipelined_called = True
        jobs = args[0] if args else kwargs["jobs"]
        return [(job.label(), 0) for job in jobs]

    def fake_wave(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal wave_called
        wave_called = True
        return []

    monkeypatch.setattr(
        "benchmark.full_pipeline.dispatch_build_jobs_pipelined", fake_pipelined
    )
    monkeypatch.setattr(
        "benchmark.full_pipeline.dispatch_build_jobs_by_replicate_wave", fake_wave
    )
    monkeypatch.setattr(
        "benchmark.full_pipeline._cleanup_docker_after_phase_build",
        lambda extra_args: None,
    )

    phase_build(
        config_path,
        tmp_path,
        [],
        jobs=1,
        dry_run=False,
        sequential_build=False,
    )
    assert pipelined_called
    assert not wave_called


def test_sequential_build_uses_harness_batches_not_global_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "models.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": ["ollama_claude"],
                        "num_runs": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    dispatch_called = False
    batch_called = False

    def fake_dispatch(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal dispatch_called
        dispatch_called = True
        return []

    def fake_batch(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal batch_called
        batch_called = True
        return 0

    monkeypatch.setattr("benchmark.full_pipeline.dispatch_build_jobs", fake_dispatch)
    monkeypatch.setattr("benchmark.full_pipeline.run_build_batch", fake_batch)

    phase_build(
        config_path,
        tmp_path,
        [],
        jobs=1,
        dry_run=False,
        sequential_build=True,
    )
    assert batch_called
    assert not dispatch_called
