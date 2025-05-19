from enum import StrEnum
from threading import Thread
from typing import Any, AsyncGenerator

from loguru import logger
import torch
from transformers import pipeline, TextIteratorStreamer

import config
from models.role import Role
from models.message import Message, ContentType


class LocalModel(StrEnum):
    PHI4MINI = "microsoft/Phi-4-mini-instruct"


class LocalAgent:
    def __init__(self, model: LocalModel):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )

        self.client = pipeline(
            "text-generation",
            model=model,
            device="cuda" if torch.cuda.is_available() else "cpu",
            torch_dtype=torch.bfloat16,
        )

        self.streamer = TextIteratorStreamer(
            self.client.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

    async def _construct_request(self, message: Message) -> list[dict[str, Any]]:
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
            logger.error("Image content type is not supported for now")
        else:
            logger.error(f"Invalid content type: {message.content_type}")
            raise ValueError(f"Invalid content type: {message.content_type}")

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
        logger.info("Generate message with gemma in streaming.")
        generation_kwargs = {
            "text_inputs": prompt,
            "max_new_tokens": 4096,
            "streamer": self.streamer,
        }

        thread = Thread(target=self.client, kwargs=generation_kwargs)
        thread.start()

        for new_text in self.streamer:
            yield new_text

        thread.join()
