from dataclasses import dataclass
from typing import Literal

ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatTurn:
    role: ChatRole
    content: str
