from typing import Type

import flet as ft
from loguru import logger

from agents.agent import Agent, DummyAgent, DummyModel
from agents.openai_agent import OpenAIAgent, OpenAIModel
from database.db import DB


class ChatDisplayController:
    def __init__(self, item_builder: Type[ft.Row], agent: Agent, db: DB):
        self.item_builder = item_builder
        self.agent = agent
        self.db = db

    def get_agent_response(self, controls: list[ft.Row]) -> ft.Row:
        messages = []
        for ctl in controls:
            messages.append(ctl.message)

        if messages[-1].role.name == "App":
            logger.info("Message from app. Skipping requesting to agent.")
            return

        logger.info("Request to agent...")
        response = self.agent.request(messages)
        self.db.insert_from_model(response)
        return self.item_builder(response)

    def change_agent(self, model: str):
        if model in OpenAIModel:
            self.agent = OpenAIAgent(model)
        elif model in DummyModel:
            self.agent = DummyAgent()

        logger.debug(f"Agent model changed to: {self.agent.model}")
