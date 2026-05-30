from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama

from chat.config import read_ollama_settings
from chat.messages import ChatTurn


class ChatStreamer(Protocol):
    def stream_reply(self, turns: Sequence[ChatTurn]) -> AsyncIterator[str]:
        """Stream assistant tokens.

        Example:
            chunks = streamer.stream_reply(turns)
        """


class OllamaChatStreamer:
    def __init__(self) -> None:
        config = read_ollama_settings()
        self._client = ChatOllama(
            model=config.model,
            base_url=config.host,
        )

    async def stream_reply(self, turns: Sequence[ChatTurn]) -> AsyncIterator[str]:
        messages = _to_langchain_messages(turns)
        async for chunk in self._client.astream(messages):
            content = _chunk_content(chunk)
            if content:
                yield content


def build_chat_streamer() -> ChatStreamer:
    """Build the production Ollama-backed streamer.

    Example:
        streamer = build_chat_streamer()
    """
    return OllamaChatStreamer()


def _to_langchain_messages(turns: Sequence[ChatTurn]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in turns:
        if turn.role == "user":
            messages.append(HumanMessage(content=turn.content))
        else:
            messages.append(AIMessage(content=turn.content))
    return messages


def _chunk_content(chunk: object) -> str:
    content: object = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_content_part_text(part) for part in content)
    return ""


def _content_part_text(part: object) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, Mapping):
        text: object = part.get("text")
        return text if isinstance(text, str) else ""
    return ""
