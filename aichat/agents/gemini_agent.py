from enum import StrEnum
import os
from typing import Any

import google.generativeai as genai
from loguru import logger

import config
from models.role import Role
from models.message import Message, ContentType


class GeminiModel(StrEnum):
    GEMINI15PRO = "gemini-1.5-pro"
    GEMINI2FLASH = "gemini-2.0-flash"
    GEMINI2FLASHLITE = "gemini-2.0-flash-lite"
    GEMINI2PRO = "gemini-2.0-pro-exp-02-05"


class GeminiAgent:
    def __init__(self, model: GeminiModel):
        self.role = Role(config.AGENT_NAME, config.AGENT_AVATAR_COLOR)

        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(model_name=model)

    def _construct_request(self, message: Message) -> dict[str, Any]:
        request = {"role": "model" if message.role.name == "Assistant" else "user"}

        if message.content_type == ContentType.TEXT:
            request["parts"] = [{"text": message.system_content}]
        elif (
            message.content_type == ContentType.PNG
            or message.content_type == ContentType.JPEG
        ):
            request["parts"] = [
                {"text": message.display_content},
                {
                    "mime_type": f"image/{message.content_type}",
                    "data": message.system_content,
                },
            ]
        else:
            logger.error(f"Invalid content type: {message.content_type}")
            raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    def request(self, messages: list[Message]) -> Message:
        logger.info("Sending message to Google Gemini...")

        chat_id = messages[0].chat_id

        request_body = [self._construct_request(m) for m in messages]
        content = self.model.generate_content(request_body).text

        return Message.construct_auto(chat_id, content, self.role)
