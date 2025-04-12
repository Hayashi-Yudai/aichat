from enum import StrEnum
import os
from typing import Any, AsyncGenerator

from loguru import logger
import anthropic

import config
from models.role import Role
from models.message import Message, ContentType


class ClaudeModel(StrEnum):
    CALUDE35HAIKU = "claude-3-5-haiku-latest"
    CLAUDE37SONNET = "claude-3-7-sonnet-latest"


class ClaudeAgent:
    def __init__(self, model: ClaudeModel):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.streamable = True

        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def _construct_request(self, message: Message) -> dict[str, Any]:
        request = {
            "role": (
                "assistant"
                if message.role.avatar_color == config.AGENT_AVATAR_COLOR
                else "user"
            )
        }

        if message.content_type == ContentType.TEXT:
            request["content"] = [{"type": "text", "text": message.system_content}]
        elif (
            message.content_type == ContentType.PNG
            or message.content_type == ContentType.JPEG
        ):
            request["content"] = [
                {
                    "type": "text",
                    "text": message.display_content,
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": f"image/{message.content_type}",
                        "data": message.system_content,
                    },
                },
            ]
        else:
            logger.error(f"Invalid content type: {message.content_type}")
            raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to Claude...")

        request_body = [self._construct_request(m) for m in messages]
        chat_completion = self.client.messages.create(
            messages=request_body,
            model=self.model,
            max_tokens=2048,
        )
        content = chat_completion.content[0].text
        if content is None:
            logger.error("Claude returned None")
            return ""

        return content

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        request_body = [self._construct_request(m) for m in messages]

        with self.client.messages.stream(
            messages=request_body,
            model=self.model,
            max_tokens=2048,
        ) as stream:
            for chunk in stream:
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
