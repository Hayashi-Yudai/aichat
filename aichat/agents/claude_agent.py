from enum import StrEnum
import json
import os

from typing import Any, AsyncGenerator, cast

from loguru import logger
import anthropic

from agents.mcp_tools import McpHandler, ClaudeToolFormatter
from anthropic.types import (
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
        request = {"role": ("assistant" if message.is_assistant_message() else "user")}

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

                        logger.info(
                            f"Calling tool (continue): {current_tool_name}({tool_input})"
                        )

                        messages.append(
                            {
                                "role": "assistant",
                                "content": assistant_message_content,
                            }
                        )
                        tool_result = await self._process_function_call(
                            {
                                "name": current_tool_name,
                                "args": tool_input,
                                "id": current_tool_use_id,
                            }
                        )
                        messages.extend(tool_result)

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

    async def request(self, messages: list[Message]) -> str:
        logger.info("Sending message to Claude...")
        claude_messages = [self._construct_request(m) for m in messages]
        final_text_parts = []
        call_count = 0

        available_tools = ClaudeToolFormatter.format(self.mcp_handler.tools)

        while call_count < config.MAX_REQUEST_COUNT:
            response = await self.client.messages.create(
                messages=claude_messages,
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                tools=available_tools,
            )

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
                    tool_result = await self._process_function_call(
                        tool_use_block.name, tool_use_block.input, tool_use_block.id
                    )
                    claude_messages.extend(tool_result)

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
        async for chunk in self._continue_stream(
            claude_messages,
            available_tools,
            self.mcp_handler,
        ):
            yield chunk

    async def _process_function_call(self, function_call):
        name = function_call["name"]
        args = function_call["args"]
        tool_id = function_call["id"]

        new_request_body = []
        try:
            tool_result_data = await self.mcp_handler.call_tool(name, args)
            tool_result_message = {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": tool_result_data["content"],
                    }
                ],
            }
        except Exception as e:
            logger.error(f"Error calling tool: {e}")
            tool_result_message = {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": str(e),
                    }
                ],
            }

        new_request_body.append(tool_result_message)

        return new_request_body
