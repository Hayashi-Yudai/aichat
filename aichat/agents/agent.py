from enum import StrEnum
from typing import Any, Protocol


import config
from models.message import Message
from models.role import Role


class Agent(Protocol):
    def _construct_request(self, message: Message) -> dict[str, Any]: ...

    def request(self, messages: list[Message]) -> Message: ...


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

    def _construct_request(self, message: Message) -> dict[str, Any]:
        pass

    def request(self, messages: list[Message]) -> Message:
        chat_id = messages[0].chat_id

        return Message.construct_auto(chat_id, messages[-1].display_content, self.role)
