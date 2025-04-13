from enum import StrEnum
import json  # Import standard json module
import os
from pathlib import Path
from typing import Any, AsyncGenerator, cast

from loguru import logger
import anthropic
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from anthropic.types import (
    Message as AnthropicMessage,
    ToolUseBlock,
    ContentBlockStartEvent,
    ContentBlockDeltaEvent,
    ContentBlockStopEvent,
    MessageDeltaEvent,
    TextBlock,
)

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
        self.streamable = True

        self.client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )

    async def connect_to_mcp_server(
        self, exit_stack: AsyncExitStack
    ) -> tuple[ClientSession, list[dict[str, Any]]]:
        """Connects to the MCP server using a provided AsyncExitStack."""
        logger.info("Connecting to MCP server...")
        command = "python"
        server_params = StdioServerParameters(
            command=command,
            args=[str(Path(__file__).parent / "mcp_servers/weather.py")],
            env=None,
        )
        # Ensure stdio_client and ClientSession are managed by the provided exit_stack
        stdio_transport = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        stdio, write = stdio_transport
        session = await exit_stack.enter_async_context(ClientSession(stdio, write))

        await session.initialize()

        # List available tools
        response = await session.list_tools()
        tools = response.tools
        logger.info(f"Connected to server with tools: {[tool.name for tool in tools]}")
        available_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools
        ]
        return session, available_tools

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

    async def _continue_stream(
        self,
        session: ClientSession,  # Pass session explicitly
        messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """Helper function to continue the stream after a tool call."""
        logger.info(f"Continuing stream with {len(messages)} messages.")
        try:
            async with self.client.messages.stream(
                messages=messages,
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                tools=available_tools,
            ) as stream:
                # --- State variables for tool use within stream ---
                current_tool_use_id: str | None = None
                current_tool_name: str | None = None
                current_tool_input_chunks: list[str] = []
                assistant_message_content: list[dict] = []

                async for event in stream:
                    if event.type == "content_block_start":
                        event = cast(ContentBlockStartEvent, event)
                        if event.content_block.type == "tool_use":
                            logger.info(
                                f"Tool use block started (continue): {event.content_block.name}"
                            )
                            current_tool_use_id = event.content_block.id
                            current_tool_name = event.content_block.name
                            current_tool_input_chunks = []
                            assistant_message_content.append(
                                {
                                    "type": "tool_use",
                                    "id": current_tool_use_id,
                                    "name": current_tool_name,
                                    "input": {},
                                }
                            )
                        elif event.content_block.type == "text":
                            assistant_message_content.append(
                                {"type": "text", "text": ""}
                            )

                    elif event.type == "content_block_delta":
                        event = cast(ContentBlockDeltaEvent, event)
                        if event.delta.type == "text_delta":
                            yield event.delta.text
                            if (
                                assistant_message_content
                                and assistant_message_content[-1]["type"] == "text"
                            ):
                                assistant_message_content[-1][
                                    "text"
                                ] += event.delta.text
                        elif event.delta.type == "input_json_delta":
                            if current_tool_name:
                                current_tool_input_chunks.append(
                                    event.delta.partial_json
                                )

                    elif event.type == "content_block_stop":
                        event = cast(ContentBlockStopEvent, event)
                        if current_tool_name and current_tool_use_id:
                            full_tool_input_str = "".join(current_tool_input_chunks)
                            logger.info(
                                (
                                    f"Tool use block finished (continue): {current_tool_name}."
                                    f" Input JSON: {full_tool_input_str}"
                                )
                            )
                            try:
                                tool_input = json.loads(
                                    full_tool_input_str
                                )  # Use standard json.loads

                                # Update the tool_use block in assistant message content
                                for block in assistant_message_content:
                                    if block.get("id") == current_tool_use_id:
                                        block["input"] = tool_input
                                        break

                                if not session:  # Check passed session
                                    raise RuntimeError(
                                        "MCP session lost during streaming continuation."
                                    )
                                logger.info(
                                    f"Calling tool (continue): {current_tool_name} with args: {tool_input}"
                                )
                                tool_result = (
                                    await session.call_tool(  # Use passed session
                                        current_tool_name, tool_input
                                    )
                                )
                                logger.info(
                                    f"Tool {current_tool_name} result received (continue)."
                                )

                                # Append messages for the *next* recursive call
                                messages.append(
                                    {
                                        "role": "assistant",
                                        "content": assistant_message_content,
                                    }
                                )
                                tool_result_message = {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": current_tool_use_id,
                                            "content": (
                                                tool_result.content
                                                if tool_result.content
                                                else ""
                                            ),
                                            # "is_error": tool_result.is_error, # Remove is_error access
                                        }
                                    ],
                                }
                                messages.append(tool_result_message)

                                # Reset state
                                current_tool_use_id = None
                                current_tool_name = None
                                current_tool_input_chunks = []
                                assistant_message_content = []

                                # Recursive call, passing the session along
                                logger.info(
                                    "Continuing stream again after tool call..."
                                )
                                async for chunk in self._continue_stream(
                                    session, messages, available_tools  # Pass session
                                ):
                                    yield chunk
                                return  # Exit this stream branch

                            except Exception as e:
                                logger.error(
                                    f"Error processing tool use {current_tool_name} (continue): {e}",
                                    exc_info=True,
                                )
                                yield f"\nError using tool {current_tool_name}: {e}"
                                return  # Stop this stream branch

                    elif event.type == "message_delta":
                        event = cast(MessageDeltaEvent, event)
                        if event.delta.stop_reason == "tool_use":
                            logger.info(
                                "Message delta indicates tool use is coming (continue)."
                            )

                    elif event.type == "message_stop":
                        logger.info("Continued stream processing finished.")

        except Exception as e:
            logger.error(f"Error during continued Claude streaming: {e}", exc_info=True)
            yield f"\nAn error occurred during continued streaming: {e}"

    async def _handle_tool_use(
        self,
        session: ClientSession,  # Add session parameter
        tool_use: ToolUseBlock,
        claude_messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
    ) -> AnthropicMessage:
        """Handles a tool use request from Claude (non-streaming)."""
        tool_name = tool_use.name
        tool_args = tool_use.input
        tool_use_id = tool_use.id
        logger.info(f"Calling tool {tool_name} with args {tool_args}")

        # Use the passed session directly
        if not session:
            raise RuntimeError(
                "MCP session is required but was not provided to _handle_tool_use."
            )

        result = await session.call_tool(tool_name, tool_args)  # Use passed session
        logger.info(f"Tool {tool_name} executed. Result is_error={result.is_error}")

        # Append the assistant's tool use message and the user's tool result message
        if claude_messages and claude_messages[-1]["role"] == "assistant":
            content = claude_messages[-1].get("content", [])
            if not any(
                c.get("type") == "tool_use" and c.get("id") == tool_use_id
                for c in content
            ):
                content.append(tool_use.model_dump())
        else:
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
                        "content": (result.content if result.content else ""),
                    }
                ],
            }
        )

        # Call Claude API again with the tool result
        logger.info("Calling Claude API again with tool result...")
        response = await self.client.messages.create(  # Use await
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            messages=claude_messages,
            tools=available_tools,
        )
        logger.info("Received response after tool call.")
        return response

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to Claude...")
        claude_messages = [self._construct_request(m) for m in messages]
        final_text_parts = []
        call_count = 0
        session = None  # Initialize session variable

        # Use a local AsyncExitStack for this request
        async with AsyncExitStack() as exit_stack:
            try:
                # Connect to MCP and get tools within the stack's context
                session, available_tools = await self.connect_to_mcp_server(exit_stack)

                logger.info("Sending initial message to Claude with tools...")
                response = await self.client.messages.create(
                    messages=claude_messages,
                    model=self.model,
                    max_tokens=self.MAX_TOKENS,
                    tools=available_tools,
                )
                logger.info("Initial response received.")

                while call_count < config.MAX_REQUEST_COUNT:
                    stop_reason = response.stop_reason
                    assistant_responses_content = []
                    tool_use_occurred = False

                    logger.debug(
                        f"Processing response turn {call_count + 1}. Stop reason: {stop_reason}"
                    )

                    for content_block in response.content:
                        if content_block.type == "text":
                            logger.info("Received text block.")
                            text_block = cast(TextBlock, content_block)
                            final_text_parts.append(text_block.text)
                            assistant_responses_content.append(text_block.model_dump())
                        elif content_block.type == "tool_use":
                            logger.info(
                                f"Received tool use request: {content_block.name}"
                            )
                            tool_use_block = cast(ToolUseBlock, content_block)
                            assistant_responses_content.append(
                                tool_use_block.model_dump()
                            )

                            claude_messages.append(
                                {
                                    "role": "assistant",
                                    "content": assistant_responses_content,
                                }
                            )

                            # Pass the current session to _handle_tool_use
                            response = await self._handle_tool_use(
                                session,
                                tool_use_block,
                                claude_messages,
                                available_tools,
                            )
                            tool_use_occurred = True
                            break
                    else:
                        if assistant_responses_content:
                            claude_messages.append(
                                {
                                    "role": "assistant",
                                    "content": assistant_responses_content,
                                }
                            )

                        if stop_reason in ["end_turn", "max_tokens", "stop_sequence"]:
                            logger.info(
                                f"Stopping loop. Final stop reason: {stop_reason}"
                            )
                            break
                        elif stop_reason == "tool_use":
                            logger.warning(
                                "Reached end of content blocks, but stop_reason is 'tool_use'. "
                                + "This might indicate an issue."
                            )
                            break

                    if tool_use_occurred:
                        logger.debug("Continuing loop after handling tool use.")
                        call_count += 1
                        if call_count >= config.MAX_REQUEST_COUNT:
                            logger.warning("Reached max request count after tool use.")
                            break
                        continue

                    if not tool_use_occurred and stop_reason not in [
                        "end_turn",
                        "max_tokens",
                        "stop_sequence",
                        "tool_use",
                    ]:
                        logger.warning(
                            f"Loop continued unexpectedly with non-terminal stop_reason: {stop_reason}"
                        )
                        break

                    call_count += 1
                    if call_count >= config.MAX_REQUEST_COUNT:
                        logger.warning("Reached max request count.")
                        break

            except anthropic.APIConnectionError as e:
                logger.error(f"Anthropic API connection error: {e}", exc_info=True)
                return f"API Connection Error: {e}"
            except anthropic.RateLimitError as e:
                logger.error(f"Anthropic rate limit exceeded: {e}", exc_info=True)
                return f"Rate Limit Exceeded: {e}"
            except anthropic.APIStatusError as e:
                logger.error(
                    f"Anthropic API status error: {e.status_code} - {e.response}",
                    exc_info=True,
                )
                return f"API Error {e.status_code}: {e.message}"
            except Exception as e:
                logger.error(f"Error during Claude request: {e}", exc_info=True)
                return f"An error occurred: {e}"
            finally:
                logger.info(
                    "Non-streaming request finished or errored. Exit stack will close."
                )
                # Exit stack automatically cleans up resources (session, stdio)

        content_text = "\n".join(final_text_parts).strip()
        assistant_had_content = any(
            msg["role"] == "assistant" and msg.get("content") for msg in claude_messages
        )

        if not content_text and not assistant_had_content:
            final_stop_reason = (
                response.stop_reason if "response" in locals() else "N/A"
            )
            logger.warning("Claude returned no text and no tool use was processed.")
            logger.warning(f"Stop reason: {final_stop_reason}")
            # Shorten the return message line
            return f"No response generated (Stop: {final_stop_reason})."
        elif not content_text and assistant_had_content:
            logger.info("Claude response consisted only of tool use(s).")
            return "[Tool use completed]"

        logger.info("Successfully received response from Claude.")
        return content_text

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        logger.info("Starting streaming request with MCP support...")
        claude_messages = [self._construct_request(m) for m in messages]
        session = None  # Initialize session variable

        # Use a local AsyncExitStack for this streaming request
        async with AsyncExitStack() as exit_stack:
            try:
                # Connect to MCP within the stack's context
                session, available_tools = await self.connect_to_mcp_server(exit_stack)

                # Initial stream call, passing the session
                async for chunk in self._continue_stream(
                    session, claude_messages, available_tools
                ):
                    yield chunk

            except anthropic.APIConnectionError as e:
                logger.error(f"Anthropic API connection error: {e}", exc_info=True)
                yield f"\nAPI Connection Error: {e}"
            except anthropic.RateLimitError as e:
                logger.error(f"Anthropic rate limit exceeded: {e}", exc_info=True)
                yield f"\nRate Limit Exceeded: {e}"
            except anthropic.APIStatusError as e:
                logger.error(
                    f"Anthropic API status error: {e.status_code} - {e.response}",
                    exc_info=True,
                )
                yield f"\nAPI Error {e.status_code}: {e.message}"
            except Exception as e:
                logger.error(
                    f"Error during Claude streaming request: {e}", exc_info=True
                )
                yield f"\nAn error occurred during streaming: {e}"
            finally:
                logger.info(
                    "Top-level streaming request finished or errored. Exit stack will close."
                )
                # Exit stack automatically cleans up resources (session, stdio)
