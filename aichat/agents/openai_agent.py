from enum import StrEnum
import os

from typing import Any, AsyncGenerator
from contextlib import AsyncExitStack
from loguru import logger
from openai import AsyncOpenAI
from mcp import ClientSession  # Added import for type hint

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
    MAX_TOKENS = 2048

    def __init__(
        self, model: OpenAIModel, mcp_handler: McpHandler
    ):  # Added mcp_handler
        self.model = model
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )
        self.streamable = True
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.mcp_handler = mcp_handler  # Store McpHandler instance

    # Removed connect_to_mcp_server method

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

    async def request(self, messages: list[Message]) -> str:
        """Handles non-streaming requests with potential tool calls."""
        logger.info("Sending non-streaming message to OpenAI with MCP support...")
        openai_messages = [self._construct_request(m) for m in messages]
        final_text_parts = []
        call_count = 0
        session = None

        async with AsyncExitStack() as exit_stack:
            session = None  # Initialize session to None
            available_tools = []  # Initialize available_tools
            try:
                # Use McpHandler to connect and get tools
                if self.mcp_handler:
                    session = await self.mcp_handler.connect(exit_stack)
                    mcp_tools = await self.mcp_handler.list_tools(session)
                    available_tools = self.mcp_handler.format_tools_for_openai(
                        mcp_tools
                    )
                else:
                    logger.warning("McpHandler not provided, tool use disabled.")

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
                        if not session or not self.mcp_handler:  # Check for handler too
                            logger.error(
                                "MCP session or handler not available for tool call."
                            )
                            # Append error messages for each tool call requested
                            tool_results = [
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": "Error: MCP handler/session not available.",
                                }
                                for tc in response_message.tool_calls
                            ]
                            openai_messages.extend(tool_results)
                            # Decide whether to break or continue; let's break here
                            # as tool execution failed fundamentally.
                            break
                        else:
                            tool_results = []
                            for tool_call in response_message.tool_calls:
                                tool_name = tool_call.function.name
                                tool_args_str = tool_call.function.arguments
                                tool_call_id = tool_call.id
                                # Use McpHandler to call the tool
                                tool_result = await self.mcp_handler.call_tool(
                                    session,
                                    tool_name,
                                    tool_args_str,
                                    tool_call_id,
                                )
                                tool_results.append(tool_result)

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
        session: ClientSession | None,  # Session can be None if handler is None
        messages: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        mcp_handler: McpHandler | None,  # Pass McpHandler explicitly
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
                        if not session or not mcp_handler:  # Check handler too
                            logger.error(
                                "MCP session or handler not available for tool call processing in stream."
                            )
                            yield "\n[Error: Tool call processing failed - MCP handler/session unavailable]"
                            # Decide how to proceed. Let's stop the stream here.
                            return

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
                            logger.info(exec_log)  # Corrected indentation
                            logger.info(args_log)  # Corrected indentation

                            # Use McpHandler to call the tool
                            tool_result = (
                                await mcp_handler.call_tool(  # Corrected indentation
                                    session,
                                    tool_name,
                                    full_args_str,
                                    tool_call_id,
                                )
                            )
                            tool_results_for_next_call.append(tool_result)

                        # Append tool results and continue the stream recursively
                        if tool_results_for_next_call:
                            messages.extend(tool_results_for_next_call)
                            logger.info(
                                "Continuing stream recursively after tool calls..."
                            )
                            # Pass mcp_handler in recursive call
                            async for chunk in self._continue_stream(
                                session, messages, available_tools, mcp_handler
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
        available_tools = []

        async with AsyncExitStack() as exit_stack:
            try:
                # Use McpHandler to connect and get tools
                if self.mcp_handler:
                    session = await self.mcp_handler.connect(exit_stack)
                    mcp_tools = await self.mcp_handler.list_tools(session)
                    available_tools = self.mcp_handler.format_tools_for_openai(
                        mcp_tools
                    )
                else:
                    logger.warning(
                        "McpHandler not provided, tool use disabled for stream."
                    )

                # Start the potentially recursive streaming process, passing handler
                async for chunk in self._continue_stream(
                    session, openai_messages, available_tools, self.mcp_handler
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
