from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from langchain_ollama import ChatOllama


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Conversation:
    messages: list[Message] = field(default_factory=list)

    def add(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def to_langchain_messages(self) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.messages]


def create_chat_client(base_url: str, model: str) -> ChatOllama:
    return ChatOllama(base_url=base_url, model=model)


async def stream_response(client: ChatOllama, conversation: Conversation) -> AsyncIterator[str]:
    lc_messages = conversation.to_langchain_messages()
    async for chunk in client.astream(lc_messages):
        content: str = str(chunk.content) if chunk.content else ""
        if content:
            yield content
