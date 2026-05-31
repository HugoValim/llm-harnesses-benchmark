"""Shared target run lifecycle orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.build_parity import (
    FOLLOWUP_CONTINUITY_COLD,
    build_followup_prompt,
    build_parity_metadata,
    wrap_primary_prompt,
)
from benchmark.config import existing_terminal_result
from benchmark.rate_limit import RateLimitWaitPolicy, run_with_rate_limit_retry
from benchmark.replicates import attach_replicate_fields
from benchmark.run_status import payload_hit_usage_limit
from benchmark.workspace import prepare_project_workspace
from benchmark.util import (
    RESULT_SCHEMA_VERSION,
    agent_coding_rules_sha256,
    prompt_sha256,
    save_json,
    utc_now,
)


@dataclass(frozen=True)
class TargetRunPaths:
    """Filesystem layout for one target result directory."""

    result_dir: Path
    project_dir: Path
    result_path: Path
    prompt_path: Path
    stdout_path: Path
    stderr_path: Path
    followup_prompt_path: Path
    followup_stdout_path: Path
    followup_stderr_path: Path
    phase1_result_path: Path | None = None
    phase2_result_path: Path | None = None
    session_export_path: Path | None = None
    stdout_payload_key: str = "stdout"
    stderr_payload_key: str = "stderr"
    followup_stdout_payload_key: str = "followup_stdout"
    followup_stderr_payload_key: str = "followup_stderr"

    @classmethod
    def opencode(cls, result_dir: Path) -> "TargetRunPaths":
        """Return the opencode/codex-compatible artifact names."""
        return cls(
            result_dir=result_dir,
            project_dir=result_dir / "project",
            result_path=result_dir / "result.json",
            prompt_path=result_dir / "prompt.txt",
            stdout_path=result_dir / "opencode-output.ndjson",
            stderr_path=result_dir / "opencode-stderr.log",
            followup_prompt_path=result_dir / "followup-prompt.txt",
            followup_stdout_path=result_dir / "followup-opencode-output.ndjson",
            followup_stderr_path=result_dir / "followup-opencode-stderr.log",
            phase1_result_path=result_dir / "phase1-result.json",
            phase2_result_path=result_dir / "phase2-result.json",
            session_export_path=result_dir / "session-export.json",
        )

    @classmethod
    def cli(cls, result_dir: Path) -> "TargetRunPaths":
        """Return the Claude/Cursor CLI-compatible artifact names."""
        return cls(
            result_dir=result_dir,
            project_dir=result_dir / "project",
            result_path=result_dir / "result.json",
            prompt_path=result_dir / "prompt.txt",
            stdout_path=result_dir / "stream.ndjson",
            stderr_path=result_dir / "stderr.log",
            followup_prompt_path=result_dir / "followup-prompt.txt",
            followup_stdout_path=result_dir / "followup-stream.ndjson",
            followup_stderr_path=result_dir / "followup-stderr.log",
            stdout_payload_key="stream_ndjson",
            stderr_payload_key="stderr_log",
            followup_stdout_payload_key="followup_stream_ndjson",
            followup_stderr_payload_key="followup_stderr_log",
        )


@dataclass(frozen=True)
class PhaseRunRequest:
    """Inputs a harness adapter needs to execute one prompt phase."""

    phase_name: str
    prompt: str
    started_at: str
    paths: TargetRunPaths
    project_dir: Path
    prompt_path: Path
    stdout_path: Path
    stderr_path: Path
    result_path: Path | None
    continue_session_id: str | None = None


PhaseRunner = Callable[[PhaseRunRequest], dict[str, Any]]
PromptBuilder = Callable[[str, str | None], str]
BeforePhases = Callable[[], dict[str, Any] | None]
FinalPayloadHook = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]
AfterSave = Callable[[dict[str, Any]], None]
PhaseLogTag = Callable[[str], str]
SessionSelector = Callable[[dict[str, Any]], str | None]


def _phase_capture_paths(payload: dict[str, Any]) -> list[Path | None]:
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return []
    captured: list[Path | None] = []
    for key in ("stdout", "stderr", "stream_ndjson", "stderr_log"):
        value = paths.get(key)
        captured.append(Path(value) if isinstance(value, str) else None)
    return captured


def _should_run_followup(
    phase: dict[str, Any],
    followup_prompt: str | None,
) -> bool:
    if followup_prompt is None:
        return False
    if payload_hit_usage_limit(phase):
        return False
    if phase.get("timed_out"):
        return False
    return not bool(phase.get("stalled"))


@dataclass
class TargetRunLifecycle:
    """Run one target through workspace prep, phases, retry, save, and cache."""

    harness: str
    slug: str
    results_dir: Path
    paths: TargetRunPaths
    force: bool
    prompt: str
    followup_prompt: str | None
    run_phase: PhaseRunner
    rate_limit_policy: RateLimitWaitPolicy = field(default_factory=RateLimitWaitPolicy)
    followup_prompt_builder: PromptBuilder | None = None
    before_phases: BeforePhases | None = None
    final_payload_hook: FinalPayloadHook | None = None
    after_save: AfterSave | None = None
    phase_log_tag: PhaseLogTag | None = None
    followup_session_selector: SessionSelector | None = None
    followup_continuity: str = FOLLOWUP_CONTINUITY_COLD
    wrap_primary_prompt: bool = True
    replicate_index: int = 1
    num_runs: int = 1
    include_agent_rules: bool = True
    extra_payload_fields: dict[str, Any] = field(default_factory=dict)
    _effective_prompt: str = field(default="", init=False, repr=False)

    def run(self) -> dict[str, Any]:
        """Execute the target lifecycle and return the final payload."""
        self._prepare_workspace()
        cached = self._cached_payload()
        if cached is not None:
            return cached
        early_payload = self._before_phases_payload()
        if early_payload is not None:
            self._save_payload(early_payload)
            return early_payload

        effective_prompt = (
            wrap_primary_prompt(self.prompt, include_agent_rules=self.include_agent_rules)
            if self.wrap_primary_prompt
            else self.prompt
        )
        self._effective_prompt = effective_prompt
        phase1 = self._run_phase(
            phase_name="phase1",
            prompt=effective_prompt,
            started_at=utc_now(),
            prompt_path=self.paths.prompt_path,
            stdout_path=self.paths.stdout_path,
            stderr_path=self.paths.stderr_path,
            result_path=self.paths.phase1_result_path,
            continue_session_id=None,
        )
        phases = [phase1]
        final_phase = phase1

        if _should_run_followup(phase1, self.followup_prompt):
            followup = self._build_followup_prompt(phase1)
            phase2 = self._run_phase(
                phase_name="phase2",
                prompt=followup,
                started_at=utc_now(),
                prompt_path=self.paths.followup_prompt_path,
                stdout_path=self.paths.followup_stdout_path,
                stderr_path=self.paths.followup_stderr_path,
                result_path=self.paths.phase2_result_path,
                continue_session_id=(
                    None
                    if self.followup_continuity == FOLLOWUP_CONTINUITY_COLD
                    else self._session_id_for_followup(phase1)
                ),
            )
            phases.append(phase2)
            final_phase = phase2

        payload = self._build_final_payload(phases, final_phase)
        if self.final_payload_hook is not None:
            payload = self.final_payload_hook(payload, phases)
        self._save_payload(payload)
        return payload

    def _prepare_workspace(self) -> None:
        prepare_project_workspace(
            self.results_dir,
            self.paths.result_dir,
            self.paths.project_dir,
            include_agent_rules=self.include_agent_rules,
        )

    def _cached_payload(self) -> dict[str, Any] | None:
        if self.force:
            return None
        return existing_terminal_result(self.paths.result_path)

    def _before_phases_payload(self) -> dict[str, Any] | None:
        if self.before_phases is None:
            return None
        return self.before_phases()

    def _save_payload(self, payload: dict[str, Any]) -> None:
        saved = attach_replicate_fields(
            payload,
            replicate_index=self.replicate_index,
            num_runs=self.num_runs,
        )
        save_json(self.paths.result_path, saved)
        if self.after_save is not None:
            self.after_save(saved)

    def _run_phase(
        self,
        *,
        phase_name: str,
        prompt: str,
        started_at: str,
        prompt_path: Path,
        stdout_path: Path,
        stderr_path: Path,
        result_path: Path | None,
        continue_session_id: str | None,
    ) -> dict[str, Any]:
        request = PhaseRunRequest(
            phase_name=phase_name,
            prompt=prompt,
            started_at=started_at,
            paths=self.paths,
            project_dir=self.paths.project_dir,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            result_path=result_path,
            continue_session_id=continue_session_id,
        )
        return run_with_rate_limit_retry(
            log_tag=self._phase_log_tag(phase_name),
            policy=self.rate_limit_policy,
            run_once=lambda: self.run_phase(request),
            capture_paths=_phase_capture_paths,
        )

    def _phase_log_tag(self, phase_name: str) -> str:
        if self.phase_log_tag is None:
            return f"{self.harness}-{self.slug}-{phase_name}"
        return self.phase_log_tag(phase_name)

    def _build_followup_prompt(self, phase1: dict[str, Any]) -> str:
        assert self.followup_prompt is not None
        if self.followup_continuity == FOLLOWUP_CONTINUITY_COLD:
            return build_followup_prompt(
                self.followup_prompt,
                continuity=FOLLOWUP_CONTINUITY_COLD,
            )
        if self.followup_prompt_builder is None:
            return self.followup_prompt
        return self.followup_prompt_builder(
            self.followup_prompt,
            self._session_id_for_followup(phase1),
        )

    def _session_id_for_followup(self, phase1: dict[str, Any]) -> str | None:
        if self.followup_session_selector is not None:
            return self.followup_session_selector(phase1)
        value = phase1.get("opencode_session_id")
        return value if isinstance(value, str) else None

    def _build_final_payload(
        self,
        phases: list[dict[str, Any]],
        final_phase: dict[str, Any],
    ) -> dict[str, Any]:
        total_elapsed = round(
            sum(float(phase.get("elapsed_seconds") or 0.0) for phase in phases),
            2,
        )
        runtime_isolation = self.extra_payload_fields.get("runtime_isolation", {})
        if not isinstance(runtime_isolation, dict):
            runtime_isolation = {}
        payload = {
            **final_phase,
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "harness": self.harness,
            "elapsed_seconds": total_elapsed,
            "ended_at": utc_now(),
            "paths": self._build_paths_payload(),
            "primary_prompt_sha256": prompt_sha256(self.prompt),
            "effective_primary_prompt_sha256": prompt_sha256(self._effective_prompt),
            "followup_prompt_sha256": prompt_sha256(self.followup_prompt)
            if self.followup_prompt
            else None,
            "agent_coding_rules_sha256": agent_coding_rules_sha256(
                include_agent_rules=self.include_agent_rules
            ),
            "build_parity": build_parity_metadata(
                continuity=self.followup_continuity,
                primary_prompt_wrapped=self.wrap_primary_prompt,
                runtime_isolation=runtime_isolation,
            ),
            "phases": phases,
            **self.extra_payload_fields,
        }
        return payload

    def _build_paths_payload(self) -> dict[str, str | None]:
        paths: dict[str, str | None] = {
            "project_dir": str(self.paths.project_dir),
            "prompt": str(self.paths.prompt_path),
            self.paths.stderr_payload_key: str(self.paths.stderr_path),
            self.paths.stdout_payload_key: str(self.paths.stdout_path),
            "followup_prompt": str(self.paths.followup_prompt_path)
            if self.paths.followup_prompt_path.exists()
            else None,
            self.paths.followup_stderr_payload_key: str(self.paths.followup_stderr_path)
            if self.paths.followup_stderr_path.exists()
            else None,
            self.paths.followup_stdout_payload_key: str(self.paths.followup_stdout_path)
            if self.paths.followup_stdout_path.exists()
            else None,
        }
        if self.paths.session_export_path is not None:
            paths["session_export"] = (
                str(self.paths.session_export_path)
                if self.paths.session_export_path.exists()
                else None
            )
        return paths
