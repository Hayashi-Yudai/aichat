import json
from pathlib import Path
from typing import Any, Dict
from contextlib import AsyncExitStack

from loguru import logger

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from google.genai import types


class McpHandler:
    """Handles interactions with multiple MCP servers defined in servers.json."""

    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.server_configs: Dict[str, Dict] = {}

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        """
        Connects to all MCP servers defined in servers.json using a provided AsyncExitStack.

        Args:
            exit_stack: An AsyncExitStack to manage the connection resources for all servers.
        """
        config_path = Path(__file__).parent / "servers.json"
        if not config_path.exists():
            logger.warning(f"MCP server config file not found: {config_path}")
            return

        try:
            with open(config_path) as f:
                self.server_configs = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse servers.json: {e}", exc_info=True)
            return

        logger.debug(
            f"Found server configurations for: {list(self.server_configs.keys())}"
        )

        for server_name, config in self.server_configs.items():
            if config.get("disabled", False):
                logger.info(f"Skipping disabled MCP server: {server_name}")
                continue

            try:
                logger.info(f"Attempting to connect to MCP server: {server_name}...")
                if "command" in config:
                    if "args" not in config:
                        logger.error(
                            f"Missing 'args' in config for server {server_name}"
                        )
                        continue  # Skip this server

                    read_stream, write_stream = await exit_stack.enter_async_context(
                        stdio_client(StdioServerParameters(**config))
                    )
                elif "url" in config:
                    read_stream, write_stream = await exit_stack.enter_async_context(
                        sse_client(config["url"])
                    )
                else:
                    logger.warning(
                        f"Server config for {server_name} has neither 'command' nor 'url'. Skipping."
                    )
                    continue

                session = await exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                self.sessions[server_name] = session

            except Exception as e:
                logger.error(
                    f"Failed to connect to MCP server {server_name}: {e}", exc_info=True
                )

    async def list_tools(self) -> list[Tool]:
        """
        Lists available tools from all connected MCP servers, prefixing names.

        Returns:
            A list of available Tool objects with prefixed names (e.g., 'server/tool').
        """
        all_tools: list[Tool] = []
        logger.info("Listing tools from all connected MCP servers...")
        for server_name, session in self.sessions.items():
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    prefixed_tool = Tool(
                        name=f"{server_name}__{tool.name}",
                        description=tool.description,
                        inputSchema=tool.inputSchema,
                    )
                    all_tools.append(prefixed_tool)
                logger.info(
                    f"Found tools from {server_name}: {[tool.name for tool in response.tools]}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to list tools from server {server_name}: {e}",
                    exc_info=True,
                )

        logger.info(f"Total tools found across all servers: {len(all_tools)}")
        return all_tools

    def format_tools_for_openai(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """
        Formats the MCP tools list into the format expected by OpenAI API.

        Args:
            tools: A list of Tool objects from the MCP server.

        Returns:
            A list of tool definitions in OpenAI format.
        """
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

    def format_tools_for_claude(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """
        Formats the MCP tools list into the format expected by Anthropic Claude API.

        Args:
            tools: A list of Tool objects from the MCP server.

        Returns:
            A list of tool definitions in Claude format.
        """
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

    def format_tools_for_gemini(self, tools: list[Tool]) -> list[dict[str, Any]]:
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

    async def call_tool(
        self,
        name: str,
        args: dict | str,
        tool_call_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Calls a specific tool on the appropriate MCP server based on the prefixed name.

        Args:
            name: The prefixed name of the tool to call (e.g., '{server_name}__{tool_name}').
            args: The arguments for the tool (JSON string or dictionary).
            tool_call_id: The unique ID for this tool call instance (optional).

        Returns:
            A dictionary representing the tool result message.
        """
        log_id_part = f" (ID: {tool_call_id})" if tool_call_id else ""
        logger.info(f"Attempting to call MCP tool: {name}{log_id_part}")

        server_name, actual_tool_name = name.split("__", 1)

        session = self.sessions.get(server_name)
        if not session:
            error_content = (
                f"Error: No active session for server '{server_name}'. "
                f"Cannot call tool '{actual_tool_name}'."
            )
            logger.error(error_content)
            return {
                "tool_use_id": tool_call_id,
                "content": error_content,
            }

        logger.info(
            f"Routing tool call to server: {server_name}, tool: {actual_tool_name}"
        )

        tool_args_dict = {}
        if isinstance(args, str):
            try:
                tool_args_dict = json.loads(args)
            except json.JSONDecodeError:
                logger.warning(
                    f"Argument for tool {name} is a string but not valid JSON: {args}. Assuming dict required."
                )
                raise TypeError("Tool arguments must be a JSON string or a dictionary.")

        elif isinstance(args, dict):
            tool_args_dict = args
        else:
            raise TypeError("Tool arguments must be a JSON string or a dictionary.")

        logger.info(
            f"Calling MCP tool: {actual_tool_name} on server {server_name} with args: {tool_args_dict}"
        )
        # Call the tool using the actual_tool_name on the specific server's session
        result = await session.call_tool(actual_tool_name, tool_args_dict)

        log_msg = (
            f"Tool {actual_tool_name} on server {server_name} executed. "
            f"Content available: {bool(result.content)}. "
        )
        logger.info(log_msg)

        content_text = ""
        if result.content:
            if isinstance(result.content, list) and len(result.content) > 0:
                first_part = result.content[0]
                if hasattr(first_part, "text") and isinstance(first_part.text, str):
                    content_text = first_part.text
                elif all(isinstance(item, str) for item in result.content):
                    content_text = "\n".join(result.content)

        return {
            "tool_use_id": tool_call_id,
            "content": content_text,
        }
