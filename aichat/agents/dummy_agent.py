from enum import StrEnum
from typing import Any


import config
from models.message import Message
from models.role import Role


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
