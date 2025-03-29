from typing import Generator

import flet as ft
from loguru import logger

from agents import Agent, get_agent_by_model
from models.message import Message


class ChatDisplayController:
    def __init__(self, agent: Agent):
        self.agent = agent

    def get_agent_response(
        self, controls: list[ft.Row]
    ) -> Generator[Message, None, None]:
        chat_id = controls[0].message.chat_id
        messages: list[Message] = [
            ctl.message for ctl in controls if not ctl.exclude_from_agent_request
        ]

        if messages[-1].role.name == "App":
            logger.info("Message from app. Skipping requesting to agent.")
            return

        logger.info("Request to agent...")
        response = ""

        if self.agent.streamable:
            request_func = self.agent.request_streaming
        else:
            request_func = self.agent.request

        for chunk in request_func(messages):
            response += chunk
            yield Message.construct_auto(chat_id, response, self.agent.role)

        response_message = Message.construct_auto(
            messages[-1].chat_id, response, self.agent.role
        )
        response_message.insert_into_db()

        return response_message

    def change_agent(self, model: str):
        self.agent = get_agent_by_model(model)

        logger.debug(f"Agent model changed to: {self.agent.model}")

    def get_all_messages_by_chat_id(self, chat_id: int) -> list[Message]:
        return Message.get_all_by_chat_id(chat_id)
