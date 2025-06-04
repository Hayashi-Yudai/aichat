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

        # Use openai library
        self.client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )

    async def _construct_request(self, message: Message) -> list[dict[str, Any]]:
        request = {"role": ("assistant" if message.is_assistant_message else "user")}

        match message.content_type:
            case ContentType.TEXT:
                request["content"] = message.system_content
            case ContentType.PNG | ContentType.JPEG | ContentType.UNKNOWN:
                msg = "DeepSeek does not support image input."
                logger.error(f"{msg}: {message.content_type}")
                raise ValueError(f"{msg}: {message.content_type}")

        return [request]

    async def prepare_prompt(self, messages: list[Message]) -> list[dict[str, Any]]:
        prompt = []
        for m in messages:
            prompt += await self._construct_request(m)

        return prompt

    def prepare_tools(self) -> list[dict[str, Any]]:
        return []

    async def request_once(
        self, prompt: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        logger.info("Sending message to DeepSeek...")

        chat_completion = self.client.chat.completions.create(
            messages=prompt,
            model=self.model,
            stream=True,
        )
        for chunk in chat_completion:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
