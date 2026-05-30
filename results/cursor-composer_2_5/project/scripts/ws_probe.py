#!/usr/bin/env python3
"""Probe WebSocket streaming with mocked LLM path via env patch."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
if not os.environ.get("DJANGO_SECRET_KEY"):
    import secrets

    os.environ["DJANGO_SECRET_KEY"] = secrets.token_hex(32)

import django

django.setup()

from channels.testing import WebsocketCommunicator

from config.asgi import application


async def _fake_stream(_history: list, _user_text: str) -> AsyncIterator[str]:
    for token in ("alpha", "beta", "gamma"):
        yield token


async def _run_probe() -> list[str]:
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    if not connected:
        raise RuntimeError("websocket connect rejected")
    await communicator.send_json_to({"message": "probe"})
    frames: list[str] = []
    for _ in range(6):
        frames.append(await communicator.receive_from())
    await communicator.disconnect()
    return frames


async def main() -> int:
    with patch("chat.consumers.llm.stream_chat_tokens", side_effect=_fake_stream):
        frames = await _run_probe()

    token_frames = [frame for frame in frames if "alpha" in frame or "beta" in frame or "gamma" in frame]
    if len(token_frames) < 3:
        print(f"FAIL: expected 3 token frames, got {len(token_frames)}")
        print(json.dumps(frames, indent=2)[:500])
        return 1
    print("PASS: websocket connected and streamed", len(token_frames), "token frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
