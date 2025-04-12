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
        self.streamable = True

        self.client = pipeline(
            "text-generation",
            model=model,
            device="cuda" if torch.cuda.is_available() else "cpu",
            torch_dtype=torch.bfloat16,
        )

        self.streamer = TextIteratorStreamer(
            self.client.tokenizer, skip_prompt=True, skip_special_tokens=True
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
        elif (
            message.content_type == ContentType.PNG
            or message.content_type == ContentType.JPEG
        ):
            logger.error("Image content type is not supported for now")
        else:
            logger.error(f"Invalid content type: {message.content_type}")
            raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def request(self, messages: list[Message]) -> list[str]:
        logger.info("Generating message with Gemma...")

        request_body = [self._construct_request(m) for m in messages]
        output = self.client(text_inputs=request_body, max_new_tokens=5000)
        content = output[0]["generated_text"][-1]["content"]
        if content is None:
            logger.error("Gemma returned None")
            return ""

        return [content]

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        logger.info("Generate message with gemma in streaming.")
        request_body = [self._construct_request(m) for m in messages]
        generation_kwargs = {
            "text_inputs": request_body,
            "max_new_tokens": 5000,
            "streamer": self.streamer,
        }

        thread = Thread(target=self.client, kwargs=generation_kwargs)
        thread.start()

        for new_text in self.streamer:
            yield new_text

        thread.join()
