from enum import StrEnum
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from loguru import logger
import anthropic
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
        self.streamable = False

        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_mcp_server(self):
        logger.info("Connecting to MCP server...")
        command = "python"
        server_params = StdioServerParameters(
            command=command,
            args=[str(Path(__file__).parent / "mcp_servers/weather.py")],
            env=None,
        )
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        logger.info(f"Connected to server with tools: {[tool.name for tool in tools]}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

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
        try:
            await self.connect_to_mcp_server()

            response = await self.session.list_tools()
            available_tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in response.tools
            ]
            response = self.client.messages.create(
                messages=request_body,
                model=self.model,
                max_tokens=2048,
                tools=available_tools,
            )

            final_text = []
            assistant_message_content = []
            for content in response.content:
                if content.type == "text":
                    logger.info("Received text response")
                    final_text.append(content.text)
                    assistant_message_content.append(content)
                elif content.type == "tool_use":
                    tool_name = content.name
                    tool_args = content.input
                    result = await self.session.call_tool(tool_name, tool_args)
                    logger.info(f"Calling tool {tool_name} with args {tool_args}")

                    assistant_message_content.append(content)
                    request_body.append(
                        {"role": "assistant", "content": assistant_message_content}
                    )
                    request_body.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": content.id,
                                    "content": result.content,
                                }
                            ],
                        }
                    )
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=2048,
                        messages=request_body,
                        tools=available_tools,
                    )
                    final_text.append(response.content[0].text)
        finally:
            await self.cleanup()

        content_text = "\n".join(final_text)

        if content_text is None:
            logger.error("Claude returned None")
            return ""

        return content_text

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
