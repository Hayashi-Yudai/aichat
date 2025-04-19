from enum import StrEnum
import os
from typing import Any, AsyncGenerator
from contextlib import AsyncExitStack

from google import genai
from google.genai import types
from loguru import logger

import config
from models.role import Role
from models.message import Message, ContentType
from .mcp_handler import McpHandler


class GeminiModel(StrEnum):
    GEMINI2FLASHLITE = "gemini-2.0-flash-lite"
    GEMINI2FLASH = "gemini-2.0-flash"
    GEMINI25FLASH = "gemini-2.5-flash-preview-04-17"
    GEMINI25PRO = "gemini-2.5-pro-exp-03-25"


class GeminiAgent:
    def __init__(self, model: GeminiModel, mcp_handler: McpHandler):
        self.model = model
        self.role = Role(f"{config.AGENT_NAME} ({model})", config.AGENT_AVATAR_COLOR)
        self.mcp_handler = mcp_handler

        self.streamable = False

        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def _construct_request(self, message: Message) -> dict[str, Any]:
        request = types.Content(
            role="model" if message.is_asistant_message() else "user"
        )

        match message.content_type:
            case ContentType.TEXT:
                request.parts = [types.Part(text=message.system_content)]
            case ContentType.PNG | ContentType.JPEG:
                request.parts = [
                    types.Part(text=message.display_content),
                    types.Part(
                        inline_data=types.Blob(
                            mime_type=f"image/{message.content_type}",
                            data=message.system_content,
                        ),
                    ),
                ]
            case ContentType.UNKNOWN:
                logger.error(f"Invalid content type: {message.content_type}")
                raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def _setup_mcp_handler(
        self, exit_stack: AsyncExitStack
    ) -> list[dict[str, Any]]:
        """Sets up the MCP handler for tool calls."""
        if self.mcp_handler:
            await self.mcp_handler.connect(exit_stack)
            mcp_tools = await self.mcp_handler.list_tools()
            available_tools = self.mcp_handler.format_tools_for_gemini(mcp_tools)
            return available_tools
        else:
            logger.warning("McpHandler not provided, tool use disabled.")
            return []

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to Google Gemini...")

        async with AsyncExitStack() as exit_stack:
            available_tools = await self._setup_mcp_handler(exit_stack)

            request_body = [self._construct_request(m) for m in messages]

            cnt = 0
            final_content = []
            while cnt < config.MAX_REQUEST_COUNT:
                is_final_response = True
                content = self.client.models.generate_content(
                    model=self.model,
                    contents=request_body,
                    config=types.GenerateContentConfig(tools=available_tools),
                )

                for candidate in content.candidates:
                    for part in candidate.content.parts:
                        if part.function_call:
                            function_call = part.function_call
                            function_call.name = function_call.name.replace("__", "/")
                            logger.debug(
                                f"function_call: {function_call.name}({function_call.args})"
                            )
                            result = await self.mcp_handler.call_tool(
                                function_call.name, args=function_call.args
                            )
                            logger.debug(f"Tool result: {result['content']}")
                            is_final_response = False

                            request_body += [
                                types.Content(
                                    role="model",
                                    parts=[types.Part(function_call=function_call)],
                                ),
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_function_response(
                                            name=function_call.name,
                                            response={"result": result},
                                        )
                                    ],
                                ),
                            ]
                        else:
                            logger.debug("No function call found in the response.")
                            logger.info(f"response.text: {content.text}")
                            final_content.append(part.text)
                if is_final_response:
                    break
                cnt += 1

        return " ".join(final_content)

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
