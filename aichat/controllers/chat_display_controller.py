from typing import Type

import flet as ft

from agents.agent import DummyAgent


class ChatDisplayController:
    def __init__(self, item_builder: Type[ft.Row]):
        self.item_builder = item_builder

    def get_agent_response(self, controls: list) -> ft.Row:
        messages = []
        for ctl in controls:
            messages.append(ctl.message)

        agent = DummyAgent()
        response = agent.request(messages)
        return self.item_builder(response)
