from enum import StrEnum
from typing import Any, Protocol, Generator


from models.message import Message
from models.role import Role


class Agent(Protocol):
    model: StrEnum
    role: Role
    streamable: bool

    def _construct_request(self, message: Message) -> dict[str, Any]: ...

    def request(self, messages: list[Message]) -> str: ...

    def request_streaming(
        self, messages: list[Message]
    ) -> Generator[str, None, None]: ...
