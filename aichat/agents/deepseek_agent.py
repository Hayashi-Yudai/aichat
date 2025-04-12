from enum import StrEnum
import os
from typing import Any, AsyncGenerator

from loguru import logger
from openai import OpenAI

import config
from models.role import Role
from models.message import Message, ContentType


class DeepSeekModel(StrEnum):
    DEEPSEEKCHAT = "deepseek-chat"
    DEEPSEEKREASONER = "deepseek-reasoner"


class DeepSeekAgent:
    def __init__(self, model: DeepSeekModel):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )

        self.streamable = True

        # Use openai library
        self.client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )

    def _construct_request(self, message: Message) -> dict[str, Any]:
        request = {
            "role": (
                "assistant"
                if message.role.avatar_color == config.AGENT_AVATAR_COLOR
                else "user"
            )
        }

        if message.content_type == ContentType.TEXT:
            request["content"] = message.system_content
        else:
            logger.error(f"Invalid content type: {message.content_type}")
            raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to DeepSeek...")

        request_body = [self._construct_request(m) for m in messages]
        chat_completion = self.client.chat.completions.create(
            messages=request_body,
            model=self.model,
        )
        content = chat_completion.choices[0].message.content
        if content is None:
            logger.error("DeepSeek returned None")
            return ""

        return content

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        logger.info("Sending message to DeepSeek...")

        request_body = [self._construct_request(m) for m in messages]
        chat_completion = self.client.chat.completions.create(
            messages=request_body,
            model=self.model,
            stream=True,
        )
        for chunk in chat_completion:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
