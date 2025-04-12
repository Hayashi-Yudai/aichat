from enum import StrEnum
from typing import Any, Protocol, Generator

import flet as ft
from loguru import logger

import config
from topics import Topics
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


class AgentController:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.pubsub.subscribe_topic(
            Topics.REQUEST_TO_AGENT,
            self.recieve_message,
        )

    def recieve_message(self, topic: Topics, messages: list[Message]):
        if messages[-1].role.name != config.USER_NAME:
            return

        logger.info(f"{self.__class__.__name__}: Request to agent...")

        agent: Agent = self.page.session.get("agent")
        chat_id: str = self.page.session.get("chat_id")

        if agent.streamable:
            response = ""
            for i, chunk in enumerate(agent.request_streaming(messages)):
                response += chunk
                response_message = Message.construct_auto(chat_id, response, agent.role)
                if i == 0:
                    topic = Topics.APPEND_MESSAGE
                else:
                    topic = Topics.UPDATE_MESSAGE_STREAMLY

                self.page.pubsub.send_all_on_topic(topic, response_message)
        else:
            response = agent.request(messages)
            response_message = Message.construct_auto(chat_id, response, agent.role)
            self.page.pubsub.send_all_on_topic(Topics.APPEND_MESSAGE, response_message)

        response_message.insert_into_db()
