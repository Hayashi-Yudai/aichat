from typing import Type

import flet as ft

from agents.agent import Agent


class ChatDisplayController:
    def __init__(self, item_builder: Type[ft.Row], agent: Agent):
        self.item_builder = item_builder
        self.agent = agent

    def get_agent_response(self, controls: list[ft.Row]) -> ft.Row:
        messages = []
        for ctl in controls:
            messages.append(ctl.message)

        response = self.agent.request(messages)
        return self.item_builder(response)
