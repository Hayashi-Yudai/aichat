from enum import StrEnum
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from loguru import logger
import anthropic
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from anthropic.types import Message as AnthropicMessage, ToolUseBlock

import config
from models.role import Role
from models.message import Message, ContentType


class ClaudeModel(StrEnum):
    CALUDE35HAIKU = "claude-3-5-haiku-latest"
    CLAUDE37SONNET = "claude-3-7-sonnet-latest"


class ClaudeAgent:
    MAX_TOKENS = 2048  # Define max_tokens as a class variable

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
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools
        ]

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

    async def _handle_tool_use(
        self,
        tool_use: ToolUseBlock,
        claude_messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
    ) -> AnthropicMessage:
        """Handles a tool use request from Claude."""
        tool_name = tool_use.name
        tool_args = tool_use.input
        tool_use_id = tool_use.id
        logger.info(f"Calling tool {tool_name} with args {tool_args}")

        if not self.session:
            raise RuntimeError("MCP session is not initialized.")

        result = await self.session.call_tool(tool_name, tool_args)

        # Append the assistant's tool use message and the user's tool result message
        claude_messages.append(
            {"role": "assistant", "content": [tool_use.model_dump()]}
        )
        claude_messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result.content,  # Assuming result.content is the expected format
                    }
                ],
            }
        )

        # Call Claude API again with the tool result
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            messages=claude_messages,
            tools=available_tools,
        )
        return response

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to Claude...")
        claude_messages = [self._construct_request(m) for m in messages]
        final_text_parts = []
        call_count = 0

        try:
            available_tools = await self.connect_to_mcp_server()

            response = self.client.messages.create(
                messages=claude_messages,
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                tools=available_tools,
            )

            while call_count < config.MAX_REQUEST_COUNT:
                stop_reason = response.stop_reason
                assistant_responses = []

                for content_block in response.content:
                    if content_block.type == "text":
                        logger.info("Received text response")
                        final_text_parts.append(content_block.text)
                        assistant_responses.append(content_block.model_dump())
                    elif content_block.type == "tool_use":
                        logger.info("Received tool use request")
                        assistant_responses.append(content_block.model_dump())
                        response = await self._handle_tool_use(
                            content_block, claude_messages, available_tools
                        )
                        # Break inner loop to process the new response in the outer loop
                        break
                else:
                    # This else block executes if the inner loop completes without break
                    # Append the full assistant message for this turn if it wasn't a tool use turn that broke early
                    if assistant_responses:
                        claude_messages.append(
                            {"role": "assistant", "content": assistant_responses}
                        )

                    # Check stop reason after processing all content blocks
                    if stop_reason in ["end_turn", "max_tokens", "stop_sequence"]:
                        logger.info(f"Stopping loop due to reason: {stop_reason}")
                        break  # Exit the while loop

                call_count += 1
                if call_count >= config.MAX_REQUEST_COUNT:
                    logger.warning("Reached max request count.")
                    break

        except Exception as e:
            logger.error(f"Error during Claude request: {e}", exc_info=True)
            return f"An error occurred: {e}"  # Return error message to the user
        finally:
            await self.cleanup()

        content_text = "\n".join(final_text_parts).strip()

        if not content_text:
            logger.warning("Claude returned empty content.")
            # Consider returning a specific message or handling based on stop_reason
            return "No response generated."

        logger.info("Successfully received response from Claude.")
        return content_text

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        # Note: Streaming with tool use requires more complex handling
        # to manage the back-and-forth. This basic implementation
        # might not fully support tool use within a stream.
        logger.warning("Streaming with tool use is experimental.")
        claude_messages = [self._construct_request(m) for m in messages]

        try:
            # Streaming doesn't easily support multi-turn tool calls like the non-streaming version.
            # For simplicity, we won't connect to MCP or pass tools here.
            # If tool use is needed with streaming, a different approach is required.
            async with self.client.messages.stream(
                messages=claude_messages,
                model=self.model,
                max_tokens=self.MAX_TOKENS,
            ) as stream:
                async for chunk in stream:
                    # Check for text delta
                    if hasattr(chunk, "delta") and hasattr(chunk.delta, "text"):
                        yield chunk.delta.text
                    # Handle other chunk types if necessary (e.g., message start/stop)
                    # elif chunk.type == "message_start":
                    #     logger.debug("Stream started.")
                    # elif chunk.type == "message_delta":
                    #      # Potentially handle other delta types
                    #      pass
                    # elif chunk.type == "message_stop":
                    #      logger.debug("Stream stopped.")
                    # elif chunk.type == "content_block_delta":
                    #      if chunk.delta.type == "text_delta":
                    #           yield chunk.delta.text

        except Exception as e:
            logger.error(f"Error during Claude streaming request: {e}", exc_info=True)
            yield f"\nAn error occurred during streaming: {e}"
