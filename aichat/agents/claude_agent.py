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
        for _ in range(config.MAX_REQUEST_COUNT):
            used_tools = False
            async with self.client.messages.stream(
                messages=claude_messages,
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                tools=available_tools,
            ) as stream:
                assistant_message = []
                async for event in stream:
                    match event.type:
                        case "content_block_start":
                            assistant_message = self._process_block_start(
                                event, assistant_message
                            )
                        case "content_block_delta":
                            assistant_message, output_text = self._process_block_delta(
                                event, assistant_message
                            )
                            yield output_text
                        case "content_block_stop":
                            assistant_message = self._process_block_stop(
                                event, assistant_message
                            )
                        case "message_stop":
                            claude_messages, used_tools = (
                                await self._process_message_stop(
                                    claude_messages, assistant_message
                                )
                            )
                        case _:
                            continue

            if not used_tools:
                break
        logger.info("Streaming request completed.")

    def _process_block_start(
        self, event: ContentBlockStartEvent, assistant_message: list[Any]
    ) -> list[Any]:
        match event.content_block.type:
            case "tool_use":
                assistant_message.append(
                    {
                        "type": "tool_use",
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "input": "",  # block_stop event で dictに変換する
                    }
                )
            case "text":
                assistant_message.append({"type": "text", "text": ""})
            case _:
                pass

        return assistant_message

    def _process_block_delta(
        self, event: ContentBlockDeltaEvent, assistant_message: list[Any]
    ) -> tuple[list[Any], str]:
        output_text = ""
        match event.delta.type:
            case "text_delta":
                assistant_message[event.index]["text"] += event.delta.text
                output_text = event.delta.text
            case "input_json_delta":
                assistant_message[event.index]["input"] += event.delta.partial_json
            case _:
                pass

        return assistant_message, output_text

    def _process_block_stop(
        self, event: ContentBlockStopEvent, assistant_message: list[Any]
    ) -> list[Any]:
        if assistant_message[event.index]["type"] != "tool_use":
            return assistant_message

        assistant_message[event.index]["input"] = json.loads(
            assistant_message[event.index]["input"]
        )

        return assistant_message

    async def _process_message_stop(
        self, claude_messages: list[Any], assistant_message: list[Any]
    ) -> tuple[list[Any], bool]:
        used_tools = False
        claude_messages.append(
            {
                "role": "assistant",
                "content": assistant_message,
            }
        )
        for msg in assistant_message:
            if msg["type"] == "tool_use":
                tool_result = await self._process_function_call(msg)
                claude_messages.extend(tool_result)
                used_tools = True

        return claude_messages, used_tools

    async def _process_function_call(self, function_call) -> list[dict[str, Any]]:
        name = function_call["name"]
        args = function_call["input"]
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
