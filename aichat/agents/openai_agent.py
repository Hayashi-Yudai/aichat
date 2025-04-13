from enum import StrEnum
import json
import os
from pathlib import Path
from typing import Any, AsyncGenerator  # Removed cast
from contextlib import AsyncExitStack

from loguru import logger
from openai import AsyncOpenAI  # Use AsyncOpenAI

# Removed unused ChatCompletion types
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
    MAX_TOKENS = 2048  # Define max_tokens

    def __init__(self, model: OpenAIModel):
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.streamable = True

        # Use AsyncOpenAI client
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
        # OpenAI expects tools in a specific format
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tools
        ]
        return session, available_tools

    def _construct_request(self, message: Message) -> dict[str, Any]:
        """Constructs the request dictionary for a single message."""
        role = (
            "assistant"
            if message.role.avatar_color == config.AGENT_AVATAR_COLOR
            else "user"
        )

        # Handle tool call results (represented as user messages in our model)
        if message.content_type == ContentType.TOOL_RESULT:
            # OpenAI expects tool results with role 'tool'
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.system_content,  # The result content
            }
        # Handle tool calls made by the assistant
        elif message.content_type == ContentType.TOOL_CALL:
            return {
                "role": "assistant",
                "tool_calls": json.loads(
                    message.system_content
                ),  # Assuming tool calls are stored as JSON string
            }

        # Handle regular text and image messages
        request: dict[str, Any] = {"role": role}
        if message.content_type == ContentType.TEXT:
            request["content"] = message.system_content
        elif (
            message.content_type == ContentType.PNG
            or message.content_type == ContentType.JPEG
        ):
            request["content"] = [
                {"type": "text", "text": message.display_content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{message.content_type};base64,{message.system_content}"
                    },
                },
            ]
        else:
            logger.error(f"Invalid or unhandled content type: {message.content_type}")
            raise ValueError(f"Invalid content type: {message.content_type}")

        return request

    async def request(self, messages: list[Message]) -> str:
        """Handles non-streaming requests with potential tool calls."""
        logger.info("Sending non-streaming message to OpenAI with MCP support...")
        openai_messages = [self._construct_request(m) for m in messages]
        final_text_parts = []
        call_count = 0
        session = None

        async with AsyncExitStack() as exit_stack:
            try:
                session, available_tools = await self.connect_to_mcp_server(exit_stack)

                while call_count < config.MAX_REQUEST_COUNT:
                    logger.info(f"Calling OpenAI API (Turn {call_count + 1})...")
                    chat_completion = await self.client.chat.completions.create(
                        messages=openai_messages,
                        model=self.model,
                        max_tokens=self.MAX_TOKENS,
                        tools=available_tools,
                        tool_choice="auto",  # Let OpenAI decide when to use tools
                    )
                    response_message = chat_completion.choices[0].message
                    finish_reason = chat_completion.choices[0].finish_reason

                    # Append assistant's response (text or tool_calls) to history
                    openai_messages.append(
                        response_message.model_dump(exclude_unset=True)
                    )

                    if response_message.content:
                        logger.info("Received text content.")
                        final_text_parts.append(response_message.content)

                    if response_message.tool_calls:
                        logger.info(
                            f"Received {len(response_message.tool_calls)} tool call(s)."
                        )
                        if not session:
                            raise RuntimeError(
                                "MCP session not available for tool call."
                            )

                        tool_results = []
                        for tool_call in response_message.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args_str = tool_call.function.arguments
                            tool_call_id = tool_call.id
                            logger.info(
                                f"Processing tool call: {tool_name}, ID: {tool_call_id}"
                            )
                            try:
                                tool_args = json.loads(tool_args_str)
                                logger.info(
                                    f"Calling MCP tool: {tool_name} with args: {tool_args}"
                                )
                                result = await session.call_tool(tool_name, tool_args)
                                logger.info(
                                    f"Tool {tool_name} executed. Result content available: {bool(result.content)}"
                                )
                                tool_results.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "content": (
                                            result.content if result.content else ""
                                        ),  # Ensure content is string
                                    }
                                )
                            except json.JSONDecodeError:
                                logger.error(
                                    f"Failed to decode JSON arguments for tool {tool_name}: {tool_args_str}"
                                )
                                tool_results.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "content": f"Error: Invalid JSON arguments received: {tool_args_str}",
                                    }
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error executing tool {tool_name}: {e}",
                                    exc_info=True,
                                )
                                tool_results.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "content": f"Error executing tool {tool_name}: {e}",
                                    }
                                )

                        # Append all tool results for the next API call
                        openai_messages.extend(tool_results)
                        call_count += 1
                        continue  # Continue the loop to send results back to OpenAI

                    # If no tool calls or after processing text, check finish reason
                    if finish_reason == "stop":
                        logger.info("Finish reason 'stop'. Ending interaction.")
                        break
                    elif finish_reason == "length":
                        logger.warning("Finish reason 'length'. Max tokens reached.")
                        break
                    elif finish_reason == "tool_calls":
                        # This case is handled by the tool_calls check above, but log if reached unexpectedly
                        logger.debug("Finish reason 'tool_calls'. Loop will continue.")
                    else:
                        logger.warning(f"Unexpected finish reason: {finish_reason}")
                        break

                    # Safety break if something unexpected happens
                    call_count += 1
                    if call_count >= config.MAX_REQUEST_COUNT:
                        logger.warning("Reached max request count.")
                        break

            except Exception as e:
                logger.error(
                    f"Error during OpenAI non-streaming request: {e}", exc_info=True
                )
                return f"An error occurred: {e}"
            finally:
                logger.info(
                    "Non-streaming request finished or errored. Exit stack will close."
                )

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
            return (
                "[Tool use completed]"  # Or potentially return tool results if needed
            )

        logger.info("Successfully received response from OpenAI.")
        return content_text

    async def _continue_stream(
        self,
        session: ClientSession,
        messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """Helper function to manage streaming and tool calls with OpenAI."""
        logger.info(f"Starting/Continuing stream with {len(messages)} messages.")
        current_tool_calls: dict[int, ChoiceDeltaToolCall] = (
            {}
        )  # Store partial tool calls by index
        current_tool_args_str: dict[int, str] = {}  # Store partial args string by index

        try:
            stream = await self.client.chat.completions.create(
                messages=messages,
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                tools=available_tools,
                tool_choice="auto",
                stream=True,
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
                            # Start of a new tool call
                            current_tool_calls[index] = tool_call_chunk
                            current_tool_args_str[index] = ""
                            # Break down log message for line length
                            tool_id = tool_call_chunk.id
                            tool_func_name = (
                                tool_call_chunk.function.name
                                if tool_call_chunk.function
                                else "N/A"
                            )
                            start_log = f"Tool call [{index}] started: ID {tool_id}, Name: {tool_func_name}"
                            logger.info(start_log)
                        else:
                            # Append arguments
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
                        if not session:
                            raise RuntimeError(
                                "MCP session not available for tool call."
                            )

                        # Construct the assistant message with completed tool calls
                        assistant_message_tool_calls = []
                        for index, tool_call_start in current_tool_calls.items():
                            if (
                                tool_call_start.function
                            ):  # Ensure function details exist
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
                            # Decide how to handle this - maybe yield an error message or just stop.
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

                            tool_name = tool_call_start.function.name
                            full_args_str = current_tool_args_str.get(index, "")
                            # Explicitly format log message parts
                            exec_log = f"Executing tool call [{index}]: {tool_name}, ID: {tool_call_id}"
                            args_log = f"Args: {full_args_str}"
                            logger.info(exec_log)
                            logger.info(args_log)

                            try:
                                tool_args = json.loads(full_args_str)
                                result = await session.call_tool(tool_name, tool_args)
                                # Split this log message too for safety
                                exec_done_log = f"Tool {tool_name} executed."
                                result_log = (
                                    f"Result content available: {bool(result.content)}"
                                )
                                logger.info(exec_done_log)
                                logger.info(result_log)
                                tool_results_for_next_call.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "content": (
                                            result.content if result.content else ""
                                        ),
                                    }
                                )
                            except json.JSONDecodeError:
                                logger.error(
                                    f"Failed to decode JSON arguments for tool {tool_name}: {full_args_str}"
                                )
                                tool_results_for_next_call.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "content": f"Error: Invalid JSON arguments received: {full_args_str}",
                                    }
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error executing tool {tool_name}: {e}",
                                    exc_info=True,
                                )
                                tool_results_for_next_call.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_id,
                                        "content": f"Error executing tool {tool_name}: {e}",
                                    }
                                )

                        # Append tool results and continue the stream recursively
                        if tool_results_for_next_call:
                            messages.extend(tool_results_for_next_call)
                            logger.info(
                                "Continuing stream recursively after tool calls..."
                            )
                            async for chunk in self._continue_stream(
                                session, messages, available_tools
                            ):
                                yield chunk
                        else:
                            logger.warning(
                                "Tool calls finished, but no results generated for next call."
                            )

                        # Important: Return after handling tool calls to prevent falling through
                        return

                    elif finish_reason == "stop":
                        logger.info("Stream finished normally.")
                        # Append final assistant message if needed (though content yielded already)
                        # final_assistant_message = {"role": "assistant", "content": accumulated_content}
                        # messages.append(final_assistant_message)
                        return  # End the generator
                    elif finish_reason == "length":
                        logger.warning("Stream finished due to max tokens.")
                        yield "\n[Warning: Response truncated due to length limit]"
                        return
                    else:
                        logger.warning(
                            f"Stream finished with unhandled reason: {finish_reason}"
                        )
                        return

        except Exception as e:
            logger.error(f"Error during OpenAI streaming: {e}", exc_info=True)
            yield f"\nAn error occurred during streaming: {e}"

    async def request_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[str, None]:
        """Initiates the streaming request with MCP support."""
        logger.info("Starting streaming request with OpenAI and MCP support...")
        openai_messages = [self._construct_request(m) for m in messages]
        session = None

        async with AsyncExitStack() as exit_stack:
            try:
                session, available_tools = await self.connect_to_mcp_server(exit_stack)

                # Start the potentially recursive streaming process
                async for chunk in self._continue_stream(
                    session, openai_messages, available_tools
                ):
                    yield chunk

            except Exception as e:
                logger.error(
                    f"Error setting up OpenAI streaming request: {e}", exc_info=True
                )
                yield f"\nAn error occurred setting up the stream: {e}"
            finally:
                logger.info(
                    "Top-level streaming request finished or errored. Exit stack will close."
                )
