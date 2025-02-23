from typing import Any, Protocol

import flet as ft

from models.message import Message
from models.role import Role


class Agent(Protocol):
    def _construct_request(self, messages: list[Message]) -> Any: ...

    def request(self, messages: list[Message]) -> Message: ...


class DummyAgent:
    """
    デバッグ用のエージェント
    """

    def __init__(self):
        self.role = Role("Agent", ft.Colors.BLUE)

    def _construct_request(self, messages: list[Message]) -> Any:
        pass

    def request(self, messages: list[Message]) -> Message:
        role = Role("Agent", ft.Colors.BLUE)

        return Message.construct_auto(messages[-1].text, role)
