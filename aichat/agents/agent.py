from enum import StrEnum
from typing import Any, Protocol, Generator


import config
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


class DummyModel(StrEnum):
    DUMMY = "Dummy"


class DummyAgent:
    """
    デバッグ用のエージェント
    """

    def __init__(self, model: str):
        self.model = DummyModel.DUMMY
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.streamable = False

    def _construct_request(self, message: Message) -> dict[str, Any]:
        pass

    def request(self, messages: list[Message]) -> list[str]:
        return messages[-1].display_content
