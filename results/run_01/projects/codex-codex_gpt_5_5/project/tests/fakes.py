from collections.abc import AsyncIterator, Sequence

from chat.messages import ChatTurn


class FakeStreamingClient:
    def __init__(
        self,
        chunks_by_call: Sequence[Sequence[str]],
        *,
        fail: bool = False,
    ) -> None:
        self.chunks_by_call = [list(chunks) for chunks in chunks_by_call]
        self.fail = fail
        self.calls: list[tuple[ChatTurn, ...]] = []

    async def stream_reply(self, turns: Sequence[ChatTurn]) -> AsyncIterator[str]:
        self.calls.append(tuple(turns))
        if self.fail:
            raise RuntimeError("fake stream failure")
        call_index = len(self.calls) - 1
        chunks = self.chunks_by_call[min(call_index, len(self.chunks_by_call) - 1)]
        for chunk in chunks:
            yield chunk
