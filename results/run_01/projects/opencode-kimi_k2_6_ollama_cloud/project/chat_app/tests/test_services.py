from chat_app.tests.fake_streamer import FakeLlmStreamer


async def test_fake_streamer_yields_multiple_chunks() -> None:
    streamer = FakeLlmStreamer()
    chunks = []
    async for token in streamer.astream([]):
        chunks.append(token)
    assert len(chunks) >= 2
    assert "".join(chunks) == "Hello, world!"
