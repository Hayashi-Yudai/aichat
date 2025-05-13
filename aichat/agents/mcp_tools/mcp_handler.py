import asyncio
import json
from pathlib import Path
from typing import Any
from contextlib import AsyncExitStack
import re

from loguru import logger

from mcp import ClientSession, StdioServerParameters, Tool, Resource, ReadResourceResult
from mcp.server.fastmcp.prompts import base
from mcp.types import Prompt
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


class McpHandler:
    def __init__(self, config_path: str | Path):
        self._config = self._load_config(config_path)

        self._tool_handler = _McpToolHandler()
        self._prompt_handler = _McpPromptHandler(self._config)
        self._resource_handler = _McpResourceHandler(self._config)

        asyncio.run(self._create_cache(self._config))

    def _load_config(self, config_path: str | Path) -> dict[str, Any]:
        with open(config_path) as f:
            return json.load(f)

    async def _create_cache(self, config: dict[str, Any]):
        tasks = []
        for server_name in config.keys():
            if config[server_name].get("disabled", False):
                continue

            tasks.append(self.__create_cache_for_one_server(server_name))

        await asyncio.gather(*tasks)

    async def __create_cache_for_one_server(self, server_name: str):
        tasks = []
        async with AsyncExitStack() as exit_stack:
            session = await self.connect_with_server_name(server_name, exit_stack)
            tasks.append(self._tool_handler.cache_tools(session, server_name))
            tasks.append(self._prompt_handler.cache_prompts(session, server_name))
            tasks.append(self._resource_handler.cache_resources(session, server_name))
            await asyncio.gather(*tasks)

    @property
    def tools(self) -> list[Tool]:
        return self._tool_handler._tools

    @property
    def resources(self) -> list[Resource]:
        return self._resource_handler._resources

    @property
    def prompts(self) -> list[Prompt]:
        return self._prompt_handler._prompts

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
            result = await self._tool_handler.call_tool(session, tool_name, args)

            return result

    async def get_prompt(
        self, name: str, args: dict[str, Any] | None = None
    ) -> list[base.Message]:
        server_name, prompt_name = name.split("__", 1)
        async with AsyncExitStack() as exit_stack:
            session = await self.connect_with_server_name(server_name, exit_stack)
            prompt = await self._prompt_handler.get_prompt(session, prompt_name, args)

            return prompt

    async def read_resource(self, name: str) -> str:
        server_name, resource_name = name.split("__", 1)
        async with AsyncExitStack() as exit_stack:
            session = await self.connect_with_server_name(server_name, exit_stack)
            resources = await self._resource_handler.read_resource(
                session, resource_name
            )

            return resources.contents[0].text

    async def watch_prompt_call(self, text: str) -> list[base.Message]:
        # Pattern to find "/" followed by non-whitespace characters
        prompt_pattern = r"(?:^| )/(\S+)"
        matches = re.findall(prompt_pattern, text)

        response = []
        for match in matches:
            logger.debug(f"Match: {match}")
            if prompt_name := self._prompt_handler.get_prompt_name_from_command(match):
                prompt = await self.get_prompt(prompt_name)
                response += prompt

        return response


class _McpToolHandler:
    def __init__(self):
        self._tools = []

    async def cache_tools(self, session: ClientSession, server_name: str):
        tool_response = await session.list_tools()

        for tool in tool_response.tools:
            prefixed_tool = Tool(
                name=f"{server_name}__{tool.name}",
                description=tool.description,
                inputSchema=tool.inputSchema,
            )
            self._tools.append(prefixed_tool)

    async def call_tool(
        self, session: ClientSession, name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        result = await session.call_tool(name, args)

        return {"content": result.content[0].text}


class _McpPromptHandler:
    def __init__(self, config: dict[str, Any]):
        self._prompts = []
        self._command_prompt_map = {}

        self.config = config

    async def cache_prompts(self, session: ClientSession, server_name: str):
        if not self.config[server_name].get("prompt_call", False):
            return

        prompt_response = await session.list_prompts()
        for prompt in prompt_response.prompts:
            prefixed_prompt = Prompt(
                name=f"{server_name}__{prompt.name}",
                description=prompt.description,
                arguments=prompt.arguments,
            )
            self._prompts.append(prefixed_prompt)
            self._command_prompt_map[
                self.config[server_name]["prompt_call"][prompt.name]
            ] = prefixed_prompt.name
            logger.debug(f"map: {self._command_prompt_map}")

    async def get_prompt(
        self, session: ClientSession, name: str, args: dict[str, Any] | None = None
    ) -> list[base.Message]:
        prompt = await session.get_prompt(name, args)

        return prompt.messages

    def get_prompt_name_from_command(self, command: str) -> str | None:
        return self._command_prompt_map.get(command, None)


class _McpResourceHandler:
    def __init__(self, config: dict[str, Any]):
        self._resources = []
        self.config = config

    async def cache_resources(self, session: ClientSession, server_name: str):
        if not self.config[server_name].get("resource_call", False):
            return

        resource_response = await session.list_resources()
        for resource in resource_response.resources:
            prefixed_resource = Resource(
                name=f"{server_name}__{resource.name}",
                description=resource.description,
                mimeType=resource.mimeType,
            )
            self._resources.append(prefixed_resource)
            logger.debug(f"Resource: {prefixed_resource.name}")

    async def read_resource(
        self, session: ClientSession, name: str
    ) -> ReadResourceResult:
        resource = await session.read_resource(name)
        return resource
