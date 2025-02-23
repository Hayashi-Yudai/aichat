from enum import StrEnum
import os
from typing import Any

import flet as ft
from loguru import logger
from openai import OpenAI

from models.role import Role
from models.message import Message


class OpenAIModel(StrEnum):
    GPT4O = "gpt-4o"
    GPT4OMINI = "gpt-4o-mini"
    O1MINI = "o1-mini"
    O1PREVIEW = "o1-preview"
    O1 = "o1"
    O3MINI = "o3-mini"


class OpenAIAgent:
    def __init__(self, model: OpenAIModel):
        self.model = model
        self.role = Role("Agent", ft.Colors.BLUE)

        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def _construct_request(self, message: Message) -> list[Any]:
        return {
            "role": "assistant" if message.role.name == "Assistant" else "user",
            "content": message.text,
        }

    def request(self, messages: list[Message]) -> Message:
        logger.info("Sending message to OpenAI...")

        request_body = [self._construct_request(m) for m in messages]
        chat_completion = self.client.chat.completions.create(
            messages=request_body,
            model=self.model,
        )
        content = chat_completion.choices[0].message.content
        if content is None:
            logger.error("OpenAI returned None")
            return ""

        return Message.construct_auto(content, self.role)
