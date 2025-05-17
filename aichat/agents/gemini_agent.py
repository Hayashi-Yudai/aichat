from enum import StrEnum
import os
from typing import Any, AsyncGenerator

from google import genai
from google.genai import types
from loguru import logger
from mcp.shared.exceptions import McpError
from mcp import Tool

import config
from models.role import Role
from models.message import Message, ContentType
from agents.mcp_tools import McpHandler, GeminiToolFormatter


class GeminiModel(StrEnum):
    GEMINI2FLASHLITE = "gemini-2.0-flash-lite"
    GEMINI2FLASH = "gemini-2.0-flash"
    GEMINI25FLASH = "gemini-2.5-flash-preview-04-17"
    GEMINI25PRO = "gemini-2.5-pro-preview-05-06"


class GeminiAgent:
    def __init__(self, model: GeminiModel, mcp_handler: McpHandler):
        self.model = model
        self.role = Role(f"{config.AGENT_NAME} ({model})", config.AGENT_AVATAR_COLOR)
        self.mcp_handler = mcp_handler

        self.streamable = True

        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def _construct_request(self, message: Message) -> dict[str, Any]:
        request = types.Content(
            role="model" if message.is_assistant_message() else "user"
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

        return request  # type: ignore

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to Google Gemini...")

        available_tools = GeminiToolFormatter.format(self.mcp_handler.tools)

        request_body = []
        for m in messages:
            prompts = await self.mcp_handler.watch_prompt_call(m.system_content)
            for p in prompts:
                request_body.append(
                    types.Content(
                        role=p.role,
                        parts=[
                            types.Part(text=p.content.text),
                        ],
                    )
                )
            request_body.append(self._construct_request(m))
            logger.debug(f"request_body: {request_body}")

        cnt = 0
        final_content = []
        while cnt < config.MAX_REQUEST_COUNT:
            is_final_response = True
            content = self.client.models.generate_content(
                model=self.model,
                contents=request_body,
                config=types.GenerateContentConfig(tools=available_tools),  # type: ignore
            )

            for candidate in content.candidates:
                for part in candidate.content.parts:
                    if part.function_call:
                        tool_result = await self._process_function_call(
                            part.function_call
                        )
                        request_body.extend(tool_result)
                        is_final_response = False
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

        available_tools = GeminiToolFormatter.format(self.mcp_handler.tools)

        request_body = []
        for m in messages:
            prompts = await self.mcp_handler.watch_prompt_call(m.system_content)
            for p in prompts:
                request_body.append(
                    types.Content(
                        role=p.role,
                        parts=[
                            types.Part(text=p.content.text),
                        ],
                    )
                )
            request_body.append(self._construct_request(m))

        for _ in range(config.MAX_REQUEST_COUNT):
            is_final_response = True
            content_stream = self.client.models.generate_content_stream(
                model=self.model,
                contents=request_body,
                config=types.GenerateContentConfig(tools=available_tools),  # type: ignore
            )

            for content in content_stream:
                for candidate in content.candidates:
                    for part in candidate.content.parts:
                        if part.function_call:
                            tool_result = await self._process_function_call(
                                part.function_call
                            )
                            request_body.extend(tool_result)
                            is_final_response = False
                        else:
                            yield content.text
            if is_final_response:
                break

    async def _process_function_call(self, function_call: types.FunctionCall) -> Any:
        name = function_call.name
        args = function_call.args

        logger.debug(f"function_call: {name}({args})")
        function_result = await self.mcp_handler.call_tool(name, args=args)
        logger.debug(f"Tool result: {function_result['content']}")

        new_request_body = [
            types.Content(
                role="model",
                parts=[types.Part(function_call=function_call)],
            ),
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=function_call.name,
                        response={"result": function_result},
                    )
                ],
            ),
        ]

        return new_request_body
