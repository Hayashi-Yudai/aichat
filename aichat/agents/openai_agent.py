from enum import StrEnum
import json
import os

from typing import Any, AsyncGenerator
from loguru import logger
from openai import AsyncOpenAI
from openai._streaming import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from agents.mcp_tools import McpHandler, OpenAIToolFormatter
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
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.mcp_handler = mcp_handler

    async def _construct_request(self, message: Message) -> list[dict[str, Any]]:
        """Constructs the request dictionary for a single message."""
        requests = []

        mcp_prompt = await self.mcp_handler.watch_prompt_call(message.system_content)
        for p in mcp_prompt:
            requests.append({"role": p.role, "content": p.content.text})

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

        requests.append(request)

        return requests

    async def prepare_prompt(self, messages: list[Message]) -> list[dict[str, Any]]:
        prompt = []
        for m in messages:
            prompt += await self._construct_request(m)

        return prompt

    def prepare_tools(self) -> list[dict[str, Any]]:
        available_tools = OpenAIToolFormatter.format(self.mcp_handler.tools)
        return available_tools

    async def request_once(
        self, prompt: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        logger.debug(f"Prompt: {prompt}")
        request_body = {
            "model": self.model,
            "messages": prompt,
            "tools": tools,
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
            tool_args_dict = json.loads(str(tool_args))
            logger.debug(f"Tool ID: {tool_id}")
            logger.debug(f"Tool Name: {tool_name}")
            logger.debug(f"Tool Args: {tool_args}")

            yield f"Tool Call: {tool_name}({tool_args_dict})"

            prompt.extend(
                await self._process_function_call(
                    {"id": tool_id, "name": tool_name, "args": tool_args_dict}
                )
            )

        elif finish_reason == "stop":
            logger.debug("Finished streaming.")

    async def _process_function_call(self, function_call: dict[str, Any]) -> list[Any]:
        function_call_id = function_call["id"]
        name = function_call["name"]
        args = function_call["args"]

        new_request_body = []
        new_request_body.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": function_call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(args),
                        },
                    }
                ],
            }
        )
        logger.debug(f"function_call: {name}({args})")
        try:
            function_result = await self.mcp_handler.call_tool(name, args=args)
            logger.debug(f"Tool result: {function_result['content']}")
            new_request_body.append(
                {
                    "role": "tool",
                    "tool_call_id": function_call_id,
                    "content": function_result.get("content", ""),
                }
            )
        except Exception as e:
            logger.error(f"Error calling tool: {e}")
            new_request_body.append(
                {
                    "role": "tool",
                    "tool_call_id": function_call_id,
                    "content": e,
                }
            )

        return new_request_body
