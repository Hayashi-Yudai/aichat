import asyncio
import json
from pathlib import Path
from typing import Any
from contextlib import AsyncExitStack

from loguru import logger

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from google.genai import types


class McpHandler:
    def __init__(self, config_path: str | Path):
        self._config = self._load_config(config_path)
        self._cache_tools = asyncio.run(self._cache_tool_list(self._config))

    def _load_config(self, config_path: str | Path) -> dict[str, Any]:
        with open(config_path) as f:
            return json.load(f)

    async def _cache_tool_list(self, config: dict[str, Any]) -> list[Tool]:
        all_tools: list[Tool] = []
        async with AsyncExitStack() as exit_stack:
            for server_name in config.keys():
                if config[server_name].get("disabled", False):
                    continue

                session = await self.connect_with_server_name(server_name, exit_stack)
                res = await session.list_tools()
                for tool in res.tools:
                    prefixed_tool = Tool(
                        name=f"{server_name}__{tool.name}",
                        description=tool.description,
                        inputSchema=tool.inputSchema,
                    )
                    all_tools.append(prefixed_tool)

        return all_tools

    @property
    def tools(self) -> list[Tool]:
        """
        Returns the cached list of tools from all connected MCP servers.
        """
        return self._cache_tools

    async def connect_with_server_name(
        self, server_name: str, exit_stack: AsyncExitStack
    ) -> ClientSession:
        logger.info(f"Connecting to MCP server: {server_name}...")
        if "command" in self._config[server_name]:
            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_client(StdioServerParameters(**self._config[server_name]))  # type: ignore
            )
        elif "url" in self._config[server_name]:
            read_stream, write_stream = await exit_stack.enter_async_context(
                sse_client(self._config[server_name]["url"])
            )
        else:
            raise ValueError("Invalid MCP server config")

        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        return session

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        server_name, tool_name = name.split("__", 1)

        async with AsyncExitStack() as exit_stack:
            session = await self.connect_with_server_name(server_name, exit_stack)
            result = await session.call_tool(tool_name, args)

            return {"content": result.content[0].text}

    async def get_prompt(self, name: str, args: dict[str, Any] | None = None) -> str:
        server_name, prompt_name = name.split("__", 1)
        async with AsyncExitStack() as exit_stack:
            session = await self.connect_with_server_name(server_name, exit_stack)
            prompt = await session.get_prompt(prompt_name, args)
            logger.debug(f"Prompt: {prompt.messages[0].content}")

            return prompt.messages[0].content.text

    async def read_resource(self, name: str) -> str:
        server_name, resource_name = name.split("__", 1)
        async with AsyncExitStack() as exit_stack:
            session = await self.connect_with_server_name(server_name, exit_stack)
            resources = await session.read_resource(resource_name)
            logger.debug(f"Resource: {resources.contents[0].text}")

            return resources.contents[0].text


class GeminiToolFormatter:
    @classmethod
    def format(cls, tools: list[Tool]) -> list[dict[str, Any]]:
        def format_schema(s: dict) -> dict:
            # Recursively format for 'Schema' class
            if s.get("items"):
                s["items"] = format_schema(s["items"])
            if s.get("properties"):
                s["properties"] = {
                    k: format_schema(v) for k, v in s["properties"].items()
                }

            # Gemini does not support these properties
            if s.get("additionalProperties") is not None:
                s.pop("additionalProperties")
            if s.get("$schema") is not None:
                s.pop("$schema")
            if s.get("default") is not None:
                s.pop("default")

            return s

        logger.info("Formatting tools for Gemini...")
        formatted_tools = []
        for tool in tools:
            tools_dict = {
                "name": tool.name,
                "description": tool.description,
            }
            parameters = {
                "type": tool.inputSchema["type"],
                "required": tool.inputSchema.get("required", []),
                "properties": tool.inputSchema.get("properties", {}),
            }

            for k, v in parameters["properties"].items():
                parameters["properties"][k] = format_schema(v)

            tools_dict["parameters"] = parameters
            formatted_tools.append(types.Tool(function_declarations=[tools_dict]))

        return formatted_tools


class OpenAIToolFormatter:
    @classmethod
    def format(cls, tools: list[Tool]) -> list[dict[str, Any]]:
        logger.info("Formatting tools for OpenAI...")
        formatted_tools = []
        for tool in tools:
            # Ensure parameters schema is valid for OpenAI (requires properties)
            params = tool.inputSchema or {"type": "object", "properties": {}}
            if (
                isinstance(params, dict)
                and params.get("type") == "object"
                and "properties" not in params
            ):
                logger.warning(
                    f"Tool '{tool.name}' has no properties in schema for OpenAI. Adding empty properties."
                )
                params["properties"] = {}  # Add empty properties if missing

            formatted_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": params,
                    },
                }
            )
        return formatted_tools


class ClaudeToolFormatter:
    @classmethod
    def format(cls, tools: list[Tool]) -> list[dict[str, Any]]:
        logger.info("Formatting tools for Claude...")
        formatted_tools = []
        for tool in tools:
            # Ensure input_schema is valid (add empty properties if needed for consistency)
            input_schema = tool.inputSchema or {"type": "object", "properties": {}}
            if (
                isinstance(input_schema, dict)
                and input_schema.get("type") == "object"
                and "properties" not in input_schema
            ):
                logger.warning(
                    f"Tool '{tool.name}' schema for Claude lacks properties. "
                    "Adding empty properties for consistency."
                )
                input_schema["properties"] = {}  # Add empty properties if missing

            formatted_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": input_schema,  # Use potentially modified input_schema
                }
            )
        return formatted_tools
