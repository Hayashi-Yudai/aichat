import asyncio
from enum import StrEnum
from typing import Any, Protocol, AsyncGenerator

import flet as ft
from loguru import logger

import config
from topics import Topics
from models.message import Message, ContentType
from models.role import Role


class StreamableAgent(Protocol):
    model: StrEnum
    role: Role

    async def prepare_prompt(self, messages: list[Message]) -> list[dict[str, Any]]: ...

    def prepare_tools(self) -> list[dict[str, Any]]: ...

    async def request_once(
        self, prompt: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncGenerator[str, None]: ...


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

        agent: StreamableAgent = self.page.session.get("agent")
        chat_id: str = self.page.session.get("chat_id")

        request_func = self.stream_request
        asyncio.run(request_func(chat_id, messages, agent))

    async def stream_request(
        self, chat_id: str, messages: list[Message], agent: StreamableAgent
    ) -> None:
        prompt = await agent.prepare_prompt(messages)
        tools = agent.prepare_tools()

        for _ in range(5):
            msg_count = len(prompt)
            response = ""
            message_start = True
            async for chunk in agent.request_once(prompt, tools):
                response += chunk
                response_message = Message.construct_auto_file(
                    chat_id, response, response, agent.role, ContentType.TEXT
                )

                self.page.pubsub.send_all_on_topic(
                    Topics.UPDATE_MESSAGE_STREAMLY, (response_message, message_start)
                )
                message_start = False

            response_message.insert_into_db()

            if msg_count == len(prompt):
                break
