"""Shared stall-detection constants used across all Harness adapters.

These were previously duplicated across runner.py, claude_code_runner.py,
cursor_runner.py, and stream_state.py. Centralising them here means tuning
the threshold is one edit, not four.
"""

from __future__ import annotations

# Abort the run after this many consecutive error events from the CLI.
ERROR_LOOP_THRESHOLD: int = 5

# Abort the run after this many identical consecutive tool calls.
TOOL_LOOP_THRESHOLD: int = 5

# Heartbeat cadence for the streaming loops — how often to print "still
# running, idle for Xs" lines.
HEARTBEAT_INTERVAL_SECONDS: float = 10.0
