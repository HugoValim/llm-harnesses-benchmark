"""Tests for the shared CLI-style harness stream loop.

Exercises ``run_cli_stream_loop`` through a ``FakeCliAdapter`` so the
loop's heartbeat/stall/grace/abort behavior is pinned independently of
the claude or cursor adapters.
"""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.cli_stream import (  # noqa: E402
    CliStreamAdapter,
    EventDecision,
    run_cli_stream_loop,
)


@dataclass
class _FakeResult:
    stdout: str
    stderr: str
    timed_out: bool
    stalled: bool
    stall_reason: str | None
    seen_events: int
    last_terminal: bool


class _FakeCliAdapter(CliStreamAdapter[_FakeResult]):
    def __init__(
        self,
        *,
        terminal_on: str | None = None,
        abort_on: str | None = None,
    ) -> None:
        self.model_slug = "fake"
        self._terminal_on = terminal_on
        self._abort_on = abort_on
        self.seen_events = 0
        self.last_terminal = False

    def on_event(self, event: dict[str, Any], now: float) -> EventDecision:
        self.seen_events += 1
        kind = event.get("kind", "")
        if self._abort_on and kind == self._abort_on:
            return EventDecision(
                description=f"abort:{kind}",
                mark_activity=False,
                abort_reason="fake_abort",
            )
        if self._terminal_on and kind == self._terminal_on:
            self.last_terminal = True
            return EventDecision(description=f"terminal:{kind}", is_terminal=True)
        return EventDecision(description=f"event:{kind}")

    def heartbeat_detail(self) -> str:
        return f"events={self.seen_events}"

    def build_result(
        self,
        *,
        stdout: str,
        stderr: str,
        timed_out: bool,
        stalled: bool,
        stall_reason: str | None,
    ) -> _FakeResult:
        return _FakeResult(
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            stalled=stalled,
            stall_reason=stall_reason,
            seen_events=self.seen_events,
            last_terminal=self.last_terminal,
        )


class _FakeStream:
    """Iterates over a fixed list of lines, returning '' once exhausted."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self._exhausted = False

    def readline(self) -> str:
        if not self._lines:
            self._exhausted = True
            return ""
        return self._lines.pop(0)


def _make_fake_process(
    stdout_lines: list[str], stderr_lines: list[str] | None = None, *, poll_exit: int | None = 0
) -> MagicMock:
    process = MagicMock()
    process.stdout = _FakeStream(stdout_lines)
    process.stderr = _FakeStream(stderr_lines or [])
    process.poll.return_value = poll_exit
    process.wait.return_value = 0
    return process


def _run_loop(
    adapter: _FakeCliAdapter,
    *,
    stdout_lines: list[str],
    stderr_lines: list[str] | None = None,
    poll_exit: int | None = 0,
    timeout_seconds: int = 30,
    no_progress_timeout_seconds: int = 30,
) -> _FakeResult:
    process = _make_fake_process(stdout_lines, stderr_lines, poll_exit=poll_exit)
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        return run_cli_stream_loop(
            process,
            adapter,
            stdout_path=root / "out.ndjson",
            stderr_path=root / "err.log",
            project_dir=root / "project",
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
        )


# Bypass select.select so the loop reads the fake stream synchronously.
def _patch_select(stdout_first: bool = True):
    from unittest.mock import patch

    def fake_select(streams, *_args, **_kwargs):
        ready = [s for s in streams if not getattr(s, "_exhausted", False)]
        return (ready, [], [])

    return patch("benchmark.cli_stream.select.select", side_effect=fake_select)


class TestCliStreamLoop(unittest.TestCase):
    def test_terminal_event_grace_exits_cleanly(self) -> None:
        adapter = _FakeCliAdapter(terminal_on="result")
        with _patch_select(), unittest.mock.patch(
            "benchmark.cli_stream.time.monotonic",
            side_effect=[
                0.0,  # loop start
                0.1,  # iter 1 now
                10.0,  # iter 2 now — past grace window
                10.1,  # final
            ],
        ):
            result = _run_loop(
                adapter,
                stdout_lines=[json.dumps({"kind": "result"}) + "\n"],
                poll_exit=0,
            )
        self.assertFalse(result.timed_out)
        self.assertFalse(result.stalled)
        self.assertIsNone(result.stall_reason)
        self.assertTrue(result.last_terminal)
        self.assertEqual(result.seen_events, 1)

    def test_abort_reason_kills_and_returns_stall(self) -> None:
        adapter = _FakeCliAdapter(abort_on="rate_limit")
        with _patch_select(), unittest.mock.patch(
            "benchmark.cli_stream.terminate_process_group"
        ) as kill:
            result = _run_loop(
                adapter,
                stdout_lines=[json.dumps({"kind": "rate_limit"}) + "\n"],
            )
        self.assertTrue(result.stalled)
        self.assertEqual(result.stall_reason, "fake_abort")
        self.assertFalse(result.timed_out)
        kill.assert_called_once()

    def test_invalid_json_is_treated_as_activity_not_event(self) -> None:
        adapter = _FakeCliAdapter(terminal_on="result")
        with _patch_select(), unittest.mock.patch(
            "benchmark.cli_stream.time.monotonic",
            side_effect=[0.0, 0.1, 10.0, 10.1, 10.2],
        ):
            result = _run_loop(
                adapter,
                stdout_lines=[
                    "not-json\n",
                    json.dumps({"kind": "result"}) + "\n",
                ],
                poll_exit=0,
            )
        self.assertEqual(result.seen_events, 1)
        self.assertTrue(result.last_terminal)

    def test_process_exit_without_pending_data_returns_clean(self) -> None:
        adapter = _FakeCliAdapter()
        with _patch_select():
            result = _run_loop(adapter, stdout_lines=[], poll_exit=0)
        self.assertFalse(result.stalled)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.seen_events, 0)

    def test_timeout_triggers_timed_out_result(self) -> None:
        adapter = _FakeCliAdapter()
        # First monotonic = 0 (started). Second iter past timeout.
        with _patch_select(), unittest.mock.patch(
            "benchmark.cli_stream.time.monotonic",
            side_effect=[0.0, 999.0],
        ), unittest.mock.patch(
            "benchmark.cli_stream.terminate_process_group"
        ) as kill:
            result = _run_loop(
                adapter,
                stdout_lines=[],
                poll_exit=None,
                timeout_seconds=10,
            )
        self.assertTrue(result.timed_out)
        self.assertFalse(result.stalled)
        kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
