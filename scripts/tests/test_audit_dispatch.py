"""Tests for audit job dispatch retries."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_dispatch import (  # noqa: E402
    AuditDispatchConfig,
    _audit_job_retryable,
    _dispatch_audit_job,
)
from benchmark.audit_finalize import INCOMPLETE_REPORT_STATUS  # noqa: E402
from benchmark.rate_limit import RateLimitWaitPolicy  # noqa: E402


def test_audit_job_retryable_for_incomplete_report() -> None:
    assert _audit_job_retryable(
        INCOMPLETE_REPORT_STATUS,
        {"status": "failed", "stalled": True},
    )


def test_audit_job_not_retryable_on_usage_limit() -> None:
    assert not _audit_job_retryable(
        INCOMPLETE_REPORT_STATUS,
        {"status": "usage_limit_reached"},
    )


def test_dispatch_audit_job_retries_incomplete_report_once(
    tmp_path: Path,
) -> None:
    auditor = {"slug": "composer_2_5", "runner_type": "cursor"}
    target = {
        "slug": "claude-demo/run_01",
        "project_dir": tmp_path / "projects" / "claude-demo" / "run_01" / "project",
        "harness": "claude",
    }
    target["project_dir"].mkdir(parents=True)
    (target["project_dir"].parent / "result.json").write_text("{}\n")

    config = AuditDispatchConfig(
        results_dir=tmp_path / "audit-reports",
        prompt_template="audit {project_dir} {model_slug}",
        timeout_seconds=60,
        no_progress_timeout_seconds=60,
        force=True,
        runner_command_prefix=None,
        rate_limit_policy=RateLimitWaitPolicy(cap_seconds=0),
        model_registry={},
    )

    run_calls = {"count": 0}

    def fake_run_auditor(*_args, **_kwargs):
        run_calls["count"] += 1
        if run_calls["count"] == 1:
            return {"status": "failed", "stalled": True}
        return {"status": "completed"}

    def fake_finalize(job_slug, run_result, report_path, *_args, **_kwargs):
        if run_result.get("status") == "completed":
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("## C. Total score / 100\n\n**80 / 100**\n")
            return job_slug, "ok", None
        return job_slug, INCOMPLETE_REPORT_STATUS, "missing report"

    with patch(
        "benchmark.audit_dispatch._run_auditor",
        side_effect=fake_run_auditor,
    ), patch(
        "benchmark.audit_dispatch._finalize_audit_job",
        side_effect=fake_finalize,
    ), patch(
        "benchmark.audit_dispatch._write_generation_metrics",
        return_value={},
    ):
        job_slug, status, err = _dispatch_audit_job(
            auditor,
            target,
            config,
            "composer_2_5__auditing__claude-demo/run_01",
        )

    assert run_calls["count"] == 2
    assert status == "ok"
    assert err is None
