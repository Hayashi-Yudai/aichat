from enum import StrEnum
import os

from typing import Any, AsyncGenerator
from contextlib import AsyncExitStack
from loguru import logger
from openai import AsyncOpenAI
from openai._streaming import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from .mcp_handler import McpHandler
import config
from models.role import Role
from models.message import Message, ContentType


class OpenAIModel(StrEnum):
    GPT4OMINI = "gpt-4o-mini"
    GPT4O = "gpt-4o"
    O1 = "o1"
    O3MINI = "o3-mini"
    GPT45PREVIEW = "gpt-4.5-preview"


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
            "role": ("assistant" if message.is_asistant_message() else "user")
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

    async def _setup_mcp_handler(
        self, exit_stack: AsyncExitStack
    ) -> list[dict[str, Any]]:
        """Sets up the MCP handler for tool calls."""
        if self.mcp_handler:
            await self.mcp_handler.connect(exit_stack)
            mcp_tools = await self.mcp_handler.list_tools()
            available_tools = self.mcp_handler.format_tools_for_openai(mcp_tools)
            return available_tools
        else:
            logger.warning("McpHandler not provided, tool use disabled.")
            return []

    async def request(self, messages: list[Message]) -> str:
        """Handles non-streaming requests with potential tool calls."""
        logger.info("Sending non-streaming message to OpenAI with MCP support...")
        openai_messages = [self._construct_request(m) for m in messages]
        final_text_parts = []
        call_count = 0

        async with AsyncExitStack() as exit_stack:
            available_tools = await self._setup_mcp_handler(exit_stack)

            while call_count < config.MAX_REQUEST_COUNT:
                logger.info(f"Calling OpenAI API (Turn {call_count + 1})...")

                request_params = {"messages": openai_messages, "model": self.model}
                if len(available_tools) > 0:
                    request_params["tools"] = available_tools
                    request_params["tool_choice"] = "auto"

                chat_completion: ChatCompletion = (
                    await self.client.chat.completions.create(**request_params)
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
                        mcp_tool_name = openai_tool_name.replace("__", "/")
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

    async def _continue_stream(
        self,
        messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        mcp_handler: McpHandler | None,
    ) -> AsyncGenerator[str, None]:
        """Helper function to manage streaming and tool calls with OpenAI."""
        logger.info(f"Starting/Continuing stream with {len(messages)} messages.")
        current_tool_calls: dict[int, ChoiceDeltaToolCall] = {}
        current_tool_args_str: dict[int, str] = {}

        stream: AsyncStream[ChatCompletionChunk] = (
            await self.client.chat.completions.create(
                messages=messages,
                model=self.model,
                tools=available_tools,
                tool_choice="auto",
                stream=True,
            )
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if delta and delta.content:
                yield delta.content

            if delta and delta.tool_calls:
                for tool_call_chunk in delta.tool_calls:
                    index = tool_call_chunk.index
                    if index not in current_tool_calls:
                        current_tool_calls[index] = tool_call_chunk
                        current_tool_args_str[index] = ""
                        tool_id = tool_call_chunk.id
                        tool_func_name = (
                            tool_call_chunk.function.name
                            if tool_call_chunk.function
                            else "N/A"
                        )
                        start_log = f"Tool call [{index}] started: ID {tool_id}, Name: {tool_func_name}"
                        logger.info(start_log)
                    else:
                        if (
                            tool_call_chunk.function
                            and tool_call_chunk.function.arguments
                        ):
                            current_tool_args_str[
                                index
                            ] += tool_call_chunk.function.arguments

            if finish_reason:
                logger.info(f"Stream finished with reason: {finish_reason}")
                if finish_reason == "tool_calls":
                    logger.info("Processing tool calls after stream finished.")
                    if not mcp_handler:
                        logger.error(
                            "MCP handler not available for tool call processing in stream."
                        )
                        yield "\n[Error: Tool call processing failed - MCP handler unavailable]"
                        return

                    assistant_message_tool_calls = []
                    for index, tool_call_start in current_tool_calls.items():
                        if tool_call_start.function:
                            assistant_message_tool_calls.append(
                                {
                                    "id": tool_call_start.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_call_start.function.name,
                                        "arguments": current_tool_args_str.get(
                                            index, ""
                                        ),
                                    },
                                }
                            )

                    if assistant_message_tool_calls:
                        messages.append(
                            {
                                "role": "assistant",
                                "tool_calls": assistant_message_tool_calls,
                            }
                        )
                    else:
                        logger.warning(
                            "Finish reason was 'tool_calls' but no complete tool calls were parsed."
                        )
                        yield "\n[Error: Tool call processing failed]"
                        return

                    tool_results_for_next_call = []
                    for index, tool_call_start in current_tool_calls.items():
                        tool_call_id = tool_call_start.id
                        if (
                            not tool_call_start.function
                            or not tool_call_start.function.name
                        ):
                            logger.error(
                                f"Tool call [{index}] missing function name or ID."
                            )
                            continue  # Skip this malformed tool call

                        openai_tool_name = tool_call_start.function.name
                        mcp_tool_name = openai_tool_name.replace("__", "/")
                        full_args_str = current_tool_args_str.get(index, "")
                        exec_log = (
                            f"Executing tool call [{index}]: {openai_tool_name} "
                            f"(as {mcp_tool_name}), ID: {tool_call_id}"
                        )
                        args_log = f"Args: {full_args_str}"
                        logger.info(exec_log)
                        logger.info(args_log)

                        # Use McpHandler to call the tool with the original name
                        tool_result = await mcp_handler.call_tool(
                            mcp_tool_name, full_args_str, tool_call_id
                        )
                        tool_result_formatted = {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": tool_result.get("content", ""),
                        }
                        tool_results_for_next_call.append(tool_result_formatted)

                    if tool_results_for_next_call:
                        messages.extend(tool_results_for_next_call)
                        logger.info("Continuing stream recursively after tool calls...")
                        async for chunk in self._continue_stream(
                            messages, available_tools, mcp_handler
                        ):
                            yield chunk
                    else:
                        logger.warning(
                            "Tool calls finished, but no results generated for next call."
                        )

                    return

                elif finish_reason == "stop":
                    logger.info("Stream finished normally.")
                    return
                elif finish_reason == "length":
                    logger.warning("Stream finished due to max tokens.")
                    yield "\n[Warning: Response truncated due to length limit]"
                    return
                else:
                    logger.warning(
                        f"Stream finished with unhandled reason: {finish_reason}"
                    )
                    return

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        """Initiates the streaming request with MCP support."""
        logger.info("Starting streaming request with OpenAI and MCP support...")
        openai_messages = [self._construct_request(m) for m in messages]
        available_tools = []

        async with AsyncExitStack() as exit_stack:
            available_tools = await self._setup_mcp_handler(exit_stack)

            # Start the potentially recursive streaming process, passing handler
            async for chunk in self._continue_stream(
                openai_messages, available_tools, self.mcp_handler
            ):
                yield chunk
