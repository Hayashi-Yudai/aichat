import asyncio
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

    async def request(self, messages: list[Message]) -> str: ...

    async def request_streaming(
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


        request_func = self.stream_request if agent.streamable else self.batch_request
        response_message = asyncio.run(request_func(chat_id, messages, agent))
        response_message.insert_into_db()

    async def stream_request(
        self, chat_id: str, messages: list[Message], agent: Agent
    ) -> Message:
        response = ""
        i = 0
        async for chunk in agent.request_streaming(messages):
            response += chunk
            response_message = Message.construct_auto(chat_id, response, agent.role)
            if i == 0:
                topic = Topics.APPEND_MESSAGE
            else:
                topic = Topics.UPDATE_MESSAGE_STREAMLY

            self.page.pubsub.send_all_on_topic(topic, response_message)
            i += 1

        return response_message

    async def batch_request(
        self, chat_id: str, messages: list[Message], agent: Agent
    ) -> Message:
        response = await agent.request(messages)
        response_message = Message.construct_auto(chat_id, response, agent.role)
        self.page.pubsub.send_all_on_topic(Topics.APPEND_MESSAGE, response_message)

        return response_message
