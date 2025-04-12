from typing import Callable, Generator

import flet as ft
from loguru import logger

import config
from agents import Agent
from models.message import Message


class ChatDisplayController:
    def __init__(
        self,
        agent: Agent,
        update_content_callback: Callable[[list[ft.Row]], None],
        item_builder: Callable[[Message], ft.Row],
    ):
        self.agent = agent
        self.update_content_callback = update_content_callback
        self.item_builder = item_builder

    def restore_past_chat(self, chat_id: str):
        messages = self._get_all_messages_by_chat_id(chat_id)
        self.update_content_callback([self.item_builder(m) for m in messages])

    def clear_controls(self):
        self.update_content_callback([])

    def change_agent(self, agent: Agent):
        self.agent = agent
        logger.debug(f"Agent model changed to: {self.agent.model}")

    def append_in_progress_message(self, controls: list[ft.Row], message: ft.Row):
        self.update_content_callback(controls + [message])

    def get_agent_response(
        self, chat_id: int, messages: list[Message]
    ) -> Generator[Message, None, None]:
        if messages[-1].role.name == config.APP_ROLE_NAME:
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

        response_message = Message.construct_auto(chat_id, response, self.agent.role)
        response_message.insert_into_db()

        return response_message

    def _get_all_messages_by_chat_id(self, chat_id: int) -> list[Message]:
        return Message.get_all_by_chat_id(chat_id)
