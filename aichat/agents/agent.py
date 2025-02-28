from enum import StrEnum
from typing import Any, Protocol

import flet as ft

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

    def __init__(self):
        self.role = Role("Agent", ft.Colors.BLUE)
        self.model = DummyModel.DUMMY

    def _construct_request(self, message: Message) -> dict[str, Any]:
        pass

    def request(self, messages: list[Message]) -> Message:
        role = Role("Agent", ft.Colors.BLUE)
        chat_id = messages[0].chat_id

        return Message.construct_auto(chat_id, messages[-1].display_content, role)
