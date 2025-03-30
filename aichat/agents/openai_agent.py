from enum import StrEnum
import os
from typing import Any, Generator

from loguru import logger
from openai import OpenAI

import config
from models.role import Role
from models.message import Message, ContentType


class OpenAIModel(StrEnum):
    GPT4OMINI = "gpt-4o-mini"
    GPT4O = "gpt-4o"
    O1 = "o1"
    O3MINI = "o3-mini"
    GPT45PREVIEW = "gpt-4.5-preview"


class OpenAIAgent:
    def __init__(self, model: OpenAIModel):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.streamable = True

        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
        elif (
            message.content_type == ContentType.PNG
            or message.content_type == ContentType.JPEG
        ):
            request["content"] = [
                {"type": "text", "text": message.display_content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{message.content_type};base64,{message.system_content}"
                    },
                },
            ]
        else:
            logger.error(f"Invalid content type: {message.content_type}")
            raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    def request(self, messages: list[Message]) -> list[str]:
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

        return [content]

    def request_streaming(self, messages: list[Message]) -> Generator[str, None, None]:
        logger.info("Sending message to OpenAI...")

        request_body = [self._construct_request(m) for m in messages]
        chat_completion = self.client.chat.completions.create(
            messages=request_body,
            model=self.model,
            stream=True,
        )
        for chunk in chat_completion:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
