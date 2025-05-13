from enum import StrEnum
import json
import re
from typing import Any, AsyncGenerator

from loguru import logger
from transformers import TextIteratorStreamer
from mlx_lm import load, generate, stream_generate

import config
from models.role import Role
from models.message import Message, ContentType
from agents.mcp_tools import McpHandler


class MLXModel(StrEnum):
    # GEMMA3_27B_4BIT = "mlx-community/gemma-3-27b-it-4bit"
    # DEEPSEEK_R1_32B_4BIT = "mlx-community/DeepSeek-R1-Distill-Qwen-32B-4bit"
    QWEN3_30B_4BIT = "mlx-community/Qwen3-30B-A3B-4bit"


class MLXAgent:
    def __init__(self, model: MLXModel, mcp_handler: McpHandler):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.max_tokens = 4096
        self.streamable = True

        self.client, self.tokenizer = load(self.model)
        self.mcp_handler = mcp_handler

        self.streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

    def __del__(self):
        del self.client
        del self.tokenizer

        logger.info("MLX agent deleted.")

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

        request_body = []
        for m in messages:
            prompts = await self.mcp_handler.watch_prompt_call(m.system_content)
            for p in prompts:
                request_body.append({"role": p.role, "content": p.content.text})
            request_body.append(self._construct_request(m))
        output = generate(
            self.client, self.tokenizer, prompt=request_body, max_tokens=self.max_tokens
        )

        return [output]

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        logger.info("Generate message with mlx-model in streaming.")
        request_messages = []
        for m in messages:
            prompts = await self.mcp_handler.watch_prompt_call(m.system_content)
            for p in prompts:
                request_messages.append({"role": p.role, "content": p.content.text})
            request_messages.append(self._construct_request(m))

        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in self.mcp_handler.tools
        ]
        for _ in range(5):
            request_body = self.tokenizer.apply_chat_template(
                request_messages,
                tools=available_tools,
                add_generation_prompt=True,
            )

            all_text = ""
            for response in stream_generate(
                self.client, self.tokenizer, request_body, max_tokens=self.max_tokens
            ):
                all_text += response.text
                yield response.text

            # FIXME: たまにjsonのパースに失敗する
            match_tool = re.search(r"<tool_call>(.*?)</tool_call>", all_text, re.DOTALL)
            if match_tool:
                json_str = match_tool.group(1)
                data = json.loads(json_str)
                result = await self.mcp_handler.call_tool(
                    data["name"],
                    data["arguments"],
                )

                request_messages.append(
                    {
                        "role": "tool",
                        "name": data["name"],
                        "content": result["content"],
                    }
                )
            else:
                break
