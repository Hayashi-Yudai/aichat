from enum import StrEnum
import os
from typing import Any, AsyncGenerator

from google import genai
from google.genai import types
from loguru import logger

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

        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    async def _construct_request(self, message: Message) -> list[dict[str, Any]]:
        requests = []
        mcp_prompts = await self.mcp_handler.watch_prompt_call(message.system_content)
        for p in mcp_prompts:
            requests.append(
                types.Content(
                    role=p.role,
                    parts=[
                        types.Part(text=p.content.text),
                    ],
                )
            )

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

        requests.append(request)

        return requests  # type: ignore

    async def prepare_prompt(self, messages: list[Message]) -> list[dict[str, Any]]:
        prompt = []
        for m in messages:
            prompt += await self._construct_request(m)

        return prompt

    def prepare_tools(self) -> list[dict[str, Any]]:
        available_tools = GeminiToolFormatter.format(self.mcp_handler.tools)
        return available_tools

    async def request_once(
        self, prompt: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        logger.info("Sending message to Google Gemini with streaming...")

        content_stream = self.client.models.generate_content_stream(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(tools=tools),  # type: ignore
        )

        for content in content_stream:
            for candidate in content.candidates:
                for part in candidate.content.parts:
                    if part.function_call:
                        yield f"Tool call: {part.function_call.name}({part.function_call.args})"
                        tool_result = await self._process_function_call(
                            part.function_call
                        )
                        prompt.extend(tool_result)
                    else:
                        yield content.text

    async def _process_function_call(
        self, function_call: types.FunctionCall
    ) -> list[Any]:
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
                        name=name,  # type: ignore
                        response={"result": function_result},
                    )
                ],
            ),
        ]

        return new_request_body
