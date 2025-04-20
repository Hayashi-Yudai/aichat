from enum import StrEnum
import json
import os

from typing import Any, AsyncGenerator, cast

from loguru import logger
import anthropic

from .mcp_handler import McpHandler, ClaudeToolFormatter
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
    MAX_TOKENS = 2048

    def __init__(self, model: ClaudeModel, mcp_handler: McpHandler):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.streamable = True
        self.client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        self.mcp_handler = mcp_handler

    def _construct_request(self, message: Message) -> dict[str, Any]:
        request = {"role": ("assistant" if message.is_asistant_message() else "user")}

        match message.content_type:
            case ContentType.TEXT:
                request["content"] = [{"type": "text", "text": message.system_content}]
            case ContentType.PNG | ContentType.JPEG:
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
            case ContentType.UNKNOWN:
                logger.error(f"Invalid content type: {message.content_type}")
                raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def _continue_stream(
        self,
        messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        mcp_handler: McpHandler | None,
    ) -> AsyncGenerator[str, None]:
        """Helper function to continue the stream after a tool call."""
        logger.info(f"Continuing stream with {len(messages)} messages.")
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
                        assistant_message_content.append({"type": "text", "text": ""})

                elif event.type == "content_block_delta":
                    event = cast(ContentBlockDeltaEvent, event)
                    if event.delta.type == "text_delta":
                        yield event.delta.text
                        if (
                            assistant_message_content
                            and assistant_message_content[-1]["type"] == "text"
                        ):
                            assistant_message_content[-1]["text"] += event.delta.text
                    elif event.delta.type == "input_json_delta":
                        if current_tool_name:
                            current_tool_input_chunks.append(event.delta.partial_json)

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
                        logger.debug(full_tool_input_str)
                        tool_input = (
                            json.loads(full_tool_input_str)
                            if full_tool_input_str
                            else {}
                        )

                        for block in assistant_message_content:
                            if block.get("id") == current_tool_use_id:
                                block["input"] = tool_input
                                break

                        if not mcp_handler:
                            logger.error(
                                "MCP session or handler not available for tool call processing in stream."
                            )
                            yield "\n[Error: Tool call processing failed - MCP handler/session unavailable]"
                            return

                        logger.info(
                            f"Calling tool (continue): {current_tool_name} with args: {tool_input}"
                        )
                        tool_result_data = await mcp_handler.call_tool(
                            current_tool_name,
                            tool_input,
                        )
                        log_msg = (
                            f"Tool {current_tool_name} result received (continue). "
                        )
                        logger.info(log_msg)

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
                                    "content": tool_result_data["content"],
                                }
                            ],
                        }
                        messages.append(tool_result_message)

                        # Reset state
                        current_tool_use_id = None
                        current_tool_name = None
                        current_tool_input_chunks = []
                        assistant_message_content = []

                        # Recursive call, passing the session and handler along
                        logger.info("Continuing stream again after tool call...")
                        async for chunk in self._continue_stream(
                            messages,
                            available_tools,
                            mcp_handler,
                        ):
                            yield chunk
                        return  # Exit this stream branch

                elif event.type == "message_delta":
                    event = cast(MessageDeltaEvent, event)
                    if event.delta.stop_reason == "tool_use":
                        logger.info(
                            "Message delta indicates tool use is coming (continue)."
                        )

                elif event.type == "message_stop":
                    logger.info("Continued stream processing finished.")

    async def _handle_tool_use(
        self,
        mcp_handler: McpHandler | None,
        tool_use: ToolUseBlock,
        claude_messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
    ) -> AnthropicMessage:
        """Handles a tool use request from Claude (non-streaming)."""
        tool_name = tool_use.name
        tool_args = tool_use.input
        tool_use_id = tool_use.id
        logger.info(f"Calling tool {tool_name} with args {tool_args}")

        if not mcp_handler:
            logger.error(
                "MCP session or handler not available for tool call in _handle_tool_use."
            )
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
                            "content": "Error: MCP handler/session not available.",
                        }
                    ],
                }
            )
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                messages=claude_messages,
                tools=available_tools,
            )
            return response

        result_data = await mcp_handler.call_tool(tool_name, tool_args)

        if claude_messages and claude_messages[-1]["role"] == "assistant":
            current_content = claude_messages[-1].get("content", [])
            if not isinstance(current_content, list):
                logger.warning(
                    f"Expected list content for assistant message, got {type(current_content)}. Resetting."
                )
                current_content = []
                claude_messages[-1]["content"] = current_content

            if not any(
                c.get("type") == "tool_use" and c.get("id") == tool_use_id
                for c in current_content
            ):
                current_content.append(tool_use.model_dump())
        else:
            # If last message wasn't assistant or no messages, add new assistant message
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
                        "content": result_data["content"],
                    }
                ],
            }
        )

        logger.info("Calling Claude API again with tool result...")
        response = await self.client.messages.create(
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

        available_tools = ClaudeToolFormatter.format(self.mcp_handler.tools)
        try:
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
                        logger.info(f"Received tool use request: {content_block.name}")
                        tool_use_block = cast(ToolUseBlock, content_block)
                        assistant_responses_content.append(tool_use_block.model_dump())

                        claude_messages.append(
                            {
                                "role": "assistant",
                                "content": assistant_responses_content,
                            }
                        )

                        response = await self._handle_tool_use(
                            self.mcp_handler,
                            tool_use_block,
                            claude_messages,
                            available_tools,
                        )
                        tool_use_occurred = True
                        break  # Break inner loop to process new response
                else:
                    if assistant_responses_content:
                        claude_messages.append(
                            {
                                "role": "assistant",
                                "content": assistant_responses_content,
                            }
                        )

                    if stop_reason in ["end_turn", "max_tokens", "stop_sequence"]:
                        logger.info(f"Stopping loop. Final stop reason: {stop_reason}")
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

        available_tools = ClaudeToolFormatter.format(self.mcp_handler.tools)
        try:
            # Initial stream call, passing the session and handler
            async for chunk in self._continue_stream(
                claude_messages,
                available_tools,
                self.mcp_handler,
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
            logger.error(f"Error during Claude streaming request: {e}", exc_info=True)
            yield f"\nAn error occurred during streaming: {e}"
        finally:
            logger.info(
                "Top-level streaming request finished or errored. Exit stack will close."
            )
