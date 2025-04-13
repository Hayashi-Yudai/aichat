from enum import StrEnum
import os
from typing import Any, AsyncGenerator

from google import genai
from loguru import logger

import config
from models.role import Role
from models.message import Message, ContentType


class GeminiModel(StrEnum):
    GEMINI2FLASHLITE = "gemini-2.0-flash-lite"
    GEMINI2FLASH = "gemini-2.0-flash"
    GEMINI25PRO = "gemini-2.5-pro-exp-03-25"


class GeminiAgent:
    def __init__(self, model: GeminiModel):
        self.model = model
        self.role = Role(f"{config.AGENT_NAME} ({model})", config.AGENT_AVATAR_COLOR)

        self.streamable = True

        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def _construct_request(self, message: Message) -> dict[str, Any]:
        request = {"role": ("model" if message.is_asistant_message() else "user")}

        match message.content_type:
            case ContentType.TEXT:
                request["parts"] = [{"text": message.system_content}]
            case ContentType.PNG | ContentType.JPEG:
                request["parts"] = [
                    {"text": message.display_content},
                    {
                        "inline_data": {
                            "mime_type": f"image/{message.content_type}",
                            "data": message.system_content,
                        }
                    },
                ]
            case ContentType.UNKNOWN:
                logger.error(f"Invalid content type: {message.content_type}")
                raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to Google Gemini...")

        request_body = [self._construct_request(m) for m in messages]
        content = self.client.models.generate_content(
            model=self.model, contents=request_body
        ).text

        return content

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        logger.info("Sending message to Google Gemini with streaming...")

        request_body = [self._construct_request(m) for m in messages]
        response = self.client.models.generate_content_stream(
            model=self.model, contents=request_body
        )

        for chunk in response:
            if hasattr(chunk, "text") and chunk.text:
                yield chunk.text
