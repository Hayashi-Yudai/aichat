from enum import StrEnum
import json
import os

from typing import Any, AsyncGenerator
from loguru import logger
from openai import AsyncOpenAI
from openai._streaming import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion import ChatCompletion
from mcp.shared.exceptions import McpError

from .mcp_tools.mcp_handler import McpHandler, OpenAIToolFormatter
import config
from models.role import Role
from models.message import Message, ContentType


class OpenAIModel(StrEnum):
    GPT4OMINI = "gpt-4o-mini"
    GPT4O = "gpt-4o"
    O1 = "o1"
    O3 = "o3"
    # O3MINI = "o3-mini"
    O4MINI = "o4-mini"
    # GPT45PREVIEW = "gpt-4.5-preview"
    GPT41 = "gpt-4.1"
    GPT41MINI = "gpt-4.1-mini"
    GPT41NANO = "gpt-4.1-nano"


class OpenAIAgent:
    def __init__(self, model: OpenAIModel, mcp_handler: McpHandler):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.streamable = True
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.mcp_handler = mcp_handler

    def _construct_request(self, message: Message) -> dict[str, Any]:
        """Constructs the request dictionary for a single message."""
        request: dict[str, Any] = {
            "role": ("assistant" if message.is_assistant_message() else "user")
        }
        match message.content_type:
            case ContentType.TEXT:
                request["content"] = message.system_content
            case ContentType.PNG | ContentType.JPEG:
                request["content"] = [
                    {"type": "text", "text": message.display_content},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{message.content_type};base64,{message.system_content}"
                        },
                    },
                ]
            case ContentType.UNKNOWN:
                logger.error(f"Invalid content type: {message.content_type}")
                raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def request(self, messages: list[Message]) -> str:
        """Handles non-streaming requests with potential tool calls."""
        logger.info("Sending non-streaming message to OpenAI with MCP support...")
        openai_messages = [self._construct_request(m) for m in messages]
        final_text_parts = []
        call_count = 0

        available_tools = OpenAIToolFormatter.format(self.mcp_handler.tools)

        while call_count < config.MAX_REQUEST_COUNT:
            logger.info(f"Calling OpenAI API (Turn {call_count + 1})...")

            request_params = {"messages": openai_messages, "model": self.model}
            if len(available_tools) > 0:
                request_params["tools"] = available_tools
                request_params["tool_choice"] = "auto"

            chat_completion: ChatCompletion = await self.client.chat.completions.create(
                **request_params
            )
            response_message = chat_completion.choices[0].message
            finish_reason = chat_completion.choices[0].finish_reason

            openai_messages.append(response_message.model_dump(exclude_unset=True))

            if response_message.content:
                logger.info("Received text content.")
                final_text_parts.append(response_message.content)

            if response_message.tool_calls:
                logger.info(
                    f"Received {len(response_message.tool_calls)} tool call(s)."
                )

                tool_results = []
                for tool_call in response_message.tool_calls:
                    openai_tool_name = tool_call.function.name
                    mcp_tool_name = openai_tool_name
                    tool_args_str = tool_call.function.arguments
                    tool_call_id = tool_call.id
                    logger.info(
                        f"Received tool call for {openai_tool_name}, converting to {mcp_tool_name}"
                    )
                    tool_result = await self.mcp_handler.call_tool(
                        mcp_tool_name,
                        tool_args_str,
                        tool_call_id,
                    )

                    tool_result_formatted = {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": tool_result.get("content", ""),
                    }
                    tool_results.append(tool_result_formatted)

                openai_messages.extend(tool_results)
                call_count += 1
                continue

            if finish_reason == "stop":
                logger.info("Finish reason 'stop'. Ending interaction.")
                break
            elif finish_reason == "length":
                logger.warning("Finish reason 'length'. Max tokens reached.")
                break
            elif finish_reason == "tool_calls":
                logger.debug("Finish reason 'tool_calls'. Loop will continue.")
            else:
                logger.warning(f"Unexpected finish reason: {finish_reason}")
                break

            call_count += 1
            if call_count >= config.MAX_REQUEST_COUNT:
                logger.warning("Reached max request count.")
                break

        content_text = "\n".join(final_text_parts).strip()
        assistant_had_tool_calls = any(
            msg.get("role") == "assistant" and msg.get("tool_calls")
            for msg in openai_messages
        )

        if not content_text and not assistant_had_tool_calls:
            logger.warning("OpenAI returned no text and no tool use was processed.")
            return "No response generated."
        elif not content_text and assistant_had_tool_calls:
            logger.info("OpenAI response consisted only of tool use(s).")
            return "[Tool use completed]"

        logger.info("Successfully received response from OpenAI.")
        return content_text

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        """Initiates the streaming request with MCP support."""
        logger.info("Starting streaming request with OpenAI and MCP support...")
        prompt = [self._construct_request(m) for m in messages]

        available_tools = OpenAIToolFormatter.format(self.mcp_handler.tools)

        for _ in range(config.MAX_REQUEST_COUNT):
            is_final_response = True
            request_body = {
                "model": self.model,
                "messages": prompt,
                "tools": available_tools,
                "tool_choice": "auto",
                "stream": True,
            }

            stream: AsyncStream[ChatCompletionChunk] = (
                await self.client.chat.completions.create(**request_body)
            )

            tool_id = None
            tool_name = None
            tool_args = None

            async for chunk in stream:
                for choice in chunk.choices:
                    delta = choice.delta
                    finish_reason = choice.finish_reason

                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            if tool_id is None:
                                tool_id = tool_call.id
                            if tool_name is None:
                                tool_name = tool_call.function.name

                            if tool_args is None:
                                tool_args = tool_call.function.arguments
                            else:
                                tool_args += tool_call.function.arguments
                    if delta.content:
                        yield delta.content

            if finish_reason == "tool_calls":
                is_final_response = False

                tool_args_dict = json.loads(tool_args)
                logger.debug(f"Tool ID: {tool_id}")
                logger.debug(f"Tool Name: {tool_name}")
                logger.debug(f"Tool Args: {tool_args}")

                prompt.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_args,
                                },
                            }
                        ],
                    }
                )

                try:
                    result = await self.mcp_handler.call_tool(
                        tool_name, args=tool_args_dict
                    )
                    prompt.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result.get("content", ""),
                        }
                    )
                except McpError as e:
                    logger.error(f"Error calling tool: {e}")
                    prompt.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": e,
                        }
                    )

            elif finish_reason == "stop":
                logger.debug("Finished streaming.")
                break

            if is_final_response:
                break
