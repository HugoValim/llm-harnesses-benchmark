"""Unit tests for EventStreamState — stream event parsing state machine."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from benchmark.stream_state import ActionKind, EventStreamState, StreamAction  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step_finish(
    *,
    reason: str = "stop",
    output_tokens: int = 100,
    step_duration_ms: int = 1000,
    started_at: int = 1_000_000,
) -> dict:
    """Minimal step_finish event with TPS-relevant fields."""
    finished_at = started_at + step_duration_ms
    return {
        "type": "step_finish",
        "timestamp": finished_at,
        "part": {
            "reason": reason,
            "tokens": {"output": output_tokens},
        },
    }


def _make_step_start(started_at: int = 1_000_000) -> dict:
    return {"type": "step_start", "timestamp": started_at}


def _make_error_event() -> dict:
    return {"type": "error", "message": "something went wrong"}


def _make_tool_use(tool_name: str = "bash", input_val: str = "ls") -> dict:
    return {
        "type": "tool_use",
        "part": {
            "tool": tool_name,
            "state": {"input": {"command": input_val}},
        },
    }


def _make_command_execution(cmd: str = "ls") -> dict:
    return {
        "type": "item.completed",
        "item": {"type": "command_execution", "command": cmd},
    }


# ---------------------------------------------------------------------------
# 1. Terminal stop grace
# ---------------------------------------------------------------------------


class TestTerminalStopGrace:
    def _state(self) -> EventStreamState:
        return EventStreamState(
            model_slug="test",
            min_preview_output_tps=None,
            min_preview_samples=2,
        )

    def test_no_stop_before_step_finish(self) -> None:
        """Before any step_finish with reason=stop, check_terminal_grace returns CONTINUE."""
        state = self._state()
        action = state.check_terminal_grace(now=time.monotonic(), grace_seconds=5.0)
        assert action.kind == ActionKind.CONTINUE

    def test_graceful_stop_after_grace_elapses(self) -> None:
        """GRACEFUL_STOP returned once grace period has elapsed after terminal stop."""
        state = self._state()
        state.process_event(_make_step_start())
        state.process_event(_make_step_finish(reason="stop"))
        # Drive check_terminal_grace with 'now' well past the 5s grace period
        future_now = time.monotonic() + 10.0
        action = state.check_terminal_grace(now=future_now, grace_seconds=5.0)
        assert action.kind == ActionKind.GRACEFUL_STOP

    def test_continue_within_grace_period(self) -> None:
        """CONTINUE returned while still within grace period after terminal stop."""
        state = self._state()
        state.process_event(_make_step_start())
        state.process_event(_make_step_finish(reason="stop"))
        # Check immediately (0 seconds elapsed)
        action = state.check_terminal_grace(now=time.monotonic(), grace_seconds=60.0)
        assert action.kind == ActionKind.CONTINUE

    def test_turn_completed_sets_terminal_stop(self) -> None:
        """Codex turn.completed also triggers terminal stop grace."""
        state = self._state()
        state.process_event({"type": "turn.completed"})
        action = state.check_terminal_grace(now=time.monotonic(), grace_seconds=0.0)
        assert action.kind == ActionKind.GRACEFUL_STOP

    def test_step_start_clears_terminal_stop(self) -> None:
        """A new step_start clears any prior terminal stop (multi-step scenario)."""
        state = self._state()
        state.process_event(_make_step_start())
        state.process_event(_make_step_finish(reason="stop"))
        # New step begins — should clear terminal stop
        state.process_event(_make_step_start())
        action = state.check_terminal_grace(now=time.monotonic(), grace_seconds=0.0)
        assert action.kind == ActionKind.CONTINUE


# ---------------------------------------------------------------------------
# 2. Preview TPS gate fail
# ---------------------------------------------------------------------------


class TestTpsGateFail:
    def _state(self, *, threshold: float = 5.0, samples: int = 2) -> EventStreamState:
        return EventStreamState(
            model_slug="test",
            min_preview_output_tps=threshold,
            min_preview_samples=samples,
        )

    def _drive_step(
        self,
        state: EventStreamState,
        *,
        output_tokens: int,
        duration_ms: int,
        started_at: int = 1_000_000,
    ) -> StreamAction:
        state.process_event(_make_step_start(started_at))
        return state.process_event(
            _make_step_finish(
                output_tokens=output_tokens,
                step_duration_ms=duration_ms,
                started_at=started_at,
            )
        )

    def test_no_gate_decision_before_min_samples(self) -> None:
        state = self._state(threshold=5.0, samples=2)
        action = self._drive_step(state, output_tokens=1, duration_ms=10_000)
        assert action.kind == ActionKind.CONTINUE

    def test_tps_gate_pass(self) -> None:
        """Average TPS above threshold → CONTINUE after gate decides."""
        state = self._state(threshold=5.0, samples=2)
        # Step 1: 100 tokens / 1s = 100 TPS
        self._drive_step(state, output_tokens=100, duration_ms=1_000, started_at=0)
        # Step 2: 100 tokens / 1s = 100 TPS — gate decides now
        action = self._drive_step(
            state, output_tokens=100, duration_ms=1_000, started_at=2_000
        )
        assert action.kind == ActionKind.CONTINUE

    def test_tps_gate_fail(self) -> None:
        """Average TPS below threshold → TPS_GATE_FAIL after min_samples."""
        state = self._state(threshold=100.0, samples=2)
        # Step 1: 1 token / 10s = 0.1 TPS
        self._drive_step(state, output_tokens=1, duration_ms=10_000, started_at=0)
        # Step 2: 1 token / 10s = 0.1 TPS — gate decides now
        action = self._drive_step(
            state, output_tokens=1, duration_ms=10_000, started_at=20_000
        )
        assert action.kind == ActionKind.TPS_GATE_FAIL

    def test_tps_gate_no_threshold(self) -> None:
        """When min_preview_output_tps is None, gate never fires."""
        state = EventStreamState(
            model_slug="test",
            min_preview_output_tps=None,
            min_preview_samples=1,
        )
        action = self._drive_step(state, output_tokens=1, duration_ms=1_000_000)
        assert action.kind == ActionKind.CONTINUE

    def test_gate_only_decided_once(self) -> None:
        """After gate fires CONTINUE, subsequent slow steps do not re-trigger gate."""
        state = self._state(threshold=5.0, samples=2)
        # Two fast steps satisfy gate (CONTINUE)
        self._drive_step(state, output_tokens=100, duration_ms=1_000, started_at=0)
        self._drive_step(
            state, output_tokens=100, duration_ms=1_000, started_at=2_000
        )
        # Now slow step — gate already decided, should not fire
        action = self._drive_step(
            state, output_tokens=1, duration_ms=100_000, started_at=4_000
        )
        assert action.kind == ActionKind.CONTINUE

    def test_tps_averages_accessible(self) -> None:
        state = self._state(threshold=5.0, samples=2)
        self._drive_step(state, output_tokens=100, duration_ms=1_000, started_at=0)
        self._drive_step(
            state, output_tokens=200, duration_ms=1_000, started_at=2_000
        )
        assert state.latest_preview_output_tps is not None
        assert state.preview_average_output_tps is not None


# ---------------------------------------------------------------------------
# 3. Repeated error events → STALL
# ---------------------------------------------------------------------------


class TestErrorLoop:
    def _state(self, threshold: int = 5) -> EventStreamState:
        return EventStreamState(
            model_slug="test",
            min_preview_output_tps=None,
            min_preview_samples=2,
            error_loop_threshold=threshold,
        )

    def test_single_error_is_continue(self) -> None:
        state = self._state()
        action = state.process_event(_make_error_event())
        assert action.kind == ActionKind.CONTINUE

    def test_below_threshold_is_continue(self) -> None:
        state = self._state(threshold=5)
        for _ in range(4):
            action = state.process_event(_make_error_event())
        assert action.kind == ActionKind.CONTINUE

    def test_at_threshold_is_stall(self) -> None:
        state = self._state(threshold=5)
        actions = [state.process_event(_make_error_event()) for _ in range(5)]
        assert actions[-1].kind == ActionKind.STALL

    def test_stall_reason_mentions_error_count(self) -> None:
        state = self._state(threshold=3)
        for _ in range(3):
            action = state.process_event(_make_error_event())
        assert action.reason is not None
        assert "3" in action.reason or "error" in action.reason.lower()

    def test_non_error_event_resets_consecutive_count(self) -> None:
        state = self._state(threshold=5)
        for _ in range(4):
            state.process_event(_make_error_event())
        # A non-error event resets the count
        state.process_event({"type": "step_start", "timestamp": 0})
        # Now 4 more errors should not trigger (only 4 consecutive)
        for _ in range(4):
            action = state.process_event(_make_error_event())
        assert action.kind == ActionKind.CONTINUE

    def test_is_error_event_property(self) -> None:
        state = self._state()
        state.process_event(_make_error_event())
        assert state.is_error_event is True
        state.process_event({"type": "step_start", "timestamp": 0})
        assert state.is_error_event is False


# ---------------------------------------------------------------------------
# 4. Repeated command_execution events → STALL
# ---------------------------------------------------------------------------


class TestCommandExecutionLoop:
    def _state(self, threshold: int = 5) -> EventStreamState:
        return EventStreamState(
            model_slug="test",
            min_preview_output_tps=None,
            min_preview_samples=2,
            tool_loop_threshold=threshold,
        )

    def test_single_command_is_continue(self) -> None:
        state = self._state()
        action = state.process_event(_make_command_execution("ls"))
        assert action.kind == ActionKind.CONTINUE

    def test_varied_commands_are_continue(self) -> None:
        state = self._state(threshold=3)
        for cmd in ["ls", "pwd", "echo hi", "cat foo", "rm bar"]:
            action = state.process_event(_make_command_execution(cmd))
        assert action.kind == ActionKind.CONTINUE

    def test_repeated_command_at_threshold_is_stall(self) -> None:
        state = self._state(threshold=5)
        for _ in range(5):
            action = state.process_event(_make_command_execution("ls -la"))
        assert action.kind == ActionKind.STALL

    def test_tool_use_loop_is_stall(self) -> None:
        state = self._state(threshold=3)
        for _ in range(3):
            action = state.process_event(_make_tool_use("bash", "ls"))
        assert action.kind == ActionKind.STALL


# ---------------------------------------------------------------------------
# 5. check_idle
# ---------------------------------------------------------------------------


class TestCheckIdle:
    def _state(self) -> EventStreamState:
        return EventStreamState(
            model_slug="test",
            min_preview_output_tps=None,
            min_preview_samples=2,
        )

    def test_below_timeout_is_continue(self) -> None:
        state = self._state()
        action = state.check_idle(
            idle_seconds=10.0,
            no_progress_timeout_seconds=60,
            last_activity_detail="processing",
        )
        assert action.kind == ActionKind.CONTINUE

    def test_at_timeout_is_stall(self) -> None:
        state = self._state()
        action = state.check_idle(
            idle_seconds=60.0,
            no_progress_timeout_seconds=60,
            last_activity_detail="waiting",
        )
        assert action.kind == ActionKind.STALL

    def test_stall_reason_includes_detail(self) -> None:
        state = self._state()
        action = state.check_idle(
            idle_seconds=90.0,
            no_progress_timeout_seconds=60,
            last_activity_detail="last known step",
        )
        assert action.reason is not None
        assert "last known step" in action.reason


# ---------------------------------------------------------------------------
# 6. session_id and last_description properties
# ---------------------------------------------------------------------------


class TestProperties:
    def _state(self) -> EventStreamState:
        return EventStreamState(
            model_slug="test",
            min_preview_output_tps=None,
            min_preview_samples=2,
        )

    def test_session_id_extracted_from_event(self) -> None:
        state = self._state()
        assert state.session_id is None
        state.process_event({"type": "step_start", "timestamp": 0, "sessionID": "abc-123"})
        assert state.session_id == "abc-123"

    def test_session_id_not_overwritten(self) -> None:
        """First sessionID wins (opencode session continuity)."""
        state = self._state()
        state.process_event({"type": "step_start", "timestamp": 0, "sessionID": "first"})
        state.process_event({"type": "step_start", "timestamp": 0, "sessionID": "second"})
        assert state.session_id == "first"
