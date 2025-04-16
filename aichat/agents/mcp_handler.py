import json
from pathlib import Path
from typing import Any, Dict
from contextlib import AsyncExitStack

from loguru import logger

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


class McpHandler:
    """Handles interactions with multiple MCP servers defined in servers.json."""

    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.server_configs: Dict[str, Dict] = {}

    async def connect(self, exit_stack: AsyncExitStack) -> None:  # Return type changed
        """
        Connects to all MCP servers defined in servers.json using a provided AsyncExitStack.

        Args:
            exit_stack: An AsyncExitStack to manage the connection resources for all servers.
        """
        config_path = Path(__file__).parent / "servers.json"
        if not config_path.exists():
            logger.warning(f"MCP server config file not found: {config_path}")
            # Consider raising an error or handling this case appropriately
            return

        try:
            with open(config_path) as f:
                self.server_configs = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse servers.json: {e}", exc_info=True)
            return  # Or raise

        logger.info(
            f"Found server configurations for: {list(self.server_configs.keys())}"
        )

        for server_name, config in self.server_configs.items():
            # Skip servers marked as disabled (optional feature)
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

                    server_params = StdioServerParameters(**config)
                    stdio_transport = await exit_stack.enter_async_context(
                        stdio_client(server_params)
                    )
                    stdio, write = stdio_transport
                    session = await exit_stack.enter_async_context(
                        ClientSession(stdio, write)
                    )
                    await session.initialize()
                    self.sessions[server_name] = session  # stdio の session を登録
                    logger.info(
                        f"Successfully connected to MCP server (stdio): {server_name}"
                    )
                elif "url" in config:  # elif に変更
                    # sse_client と ClientSession を exit_stack で管理する
                    streams = await exit_stack.enter_async_context(
                        sse_client(config["url"])
                    )
                    session = await exit_stack.enter_async_context(
                        ClientSession(streams[0], streams[1])
                    )
                    await session.initialize()
                    self.sessions[server_name] = session  # sse の session を登録
                    logger.info(
                        f"Successfully connected to MCP server (sse): {server_name}"
                    )
                else:
                    logger.warning(
                        f"Server config for {server_name} has neither 'command' nor 'url'. Skipping."
                    )
                    continue  # 設定がない場合はスキップ

            except Exception as e:
                logger.error(
                    f"Failed to connect to MCP server {server_name}: {e}", exc_info=True
                )

        logger.info(f"Connected MCP servers: {list(self.sessions.keys())}")
        # No return value needed

    async def list_tools(self) -> list[Tool]:  # Removed session argument
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
                    # Create a new Tool object with a prefixed name
                    prefixed_tool = Tool(
                        name=f"{server_name}/{tool.name}",
                        description=tool.description,
                        inputSchema=tool.inputSchema,
                        # Copy other relevant fields if necessary, e.g., outputSchema if used
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
                # Continue to next server even if one fails

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
                        "name": tool.name.replace("/", "__"),  # Replace '/' with '__'
                        "description": tool.description,
                        "parameters": params,  # Use potentially modified params
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
                    "name": tool.name.replace("/", "__"),
                    "description": tool.description,
                    "input_schema": input_schema,  # Use potentially modified input_schema
                }
            )
        return formatted_tools

    async def call_tool(
        self,
        name: str,  # Expected format: "server_name/tool_name"
        args: dict | str,
        tool_call_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Calls a specific tool on the appropriate MCP server based on the prefixed name.

        Args:
            name: The prefixed name of the tool to call (e.g., 'server_name/tool_name').
            args: The arguments for the tool (JSON string or dictionary).
            tool_call_id: The unique ID for this tool call instance (optional).

        Returns:
            A dictionary representing the tool result message.
        """
        log_id_part = f" (ID: {tool_call_id})" if tool_call_id else ""
        logger.info(f"Attempting to call MCP tool: {name}{log_id_part}")

        # Parse server_name and actual_tool_name
        try:
            if "/" not in name:
                raise ValueError("Tool name does not contain '/' separator.")
            server_name, actual_tool_name = name.split("/", 1)
        except ValueError as e:
            error_content = (
                f"Error: Invalid tool name format '{name}'. "
                f"Expected 'server_name/tool_name'. Details: {e}"
            )
            logger.error(error_content)
            return {
                "tool_use_id": tool_call_id,
                "content": error_content,
                "is_error": True,
            }

        # Find the correct session
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
                "is_error": True,
            }

        logger.info(
            f"Routing tool call to server: {server_name}, tool: {actual_tool_name}"
        )

        tool_args_dict = {}
        try:
            # Handle both string and dict arguments
            if isinstance(args, str):
                # Attempt to parse if it looks like JSON, otherwise treat as string arg if schema allows
                try:
                    tool_args_dict = json.loads(args)
                except json.JSONDecodeError:
                    # If JSON parsing fails, maybe the tool expects a single string argument?
                    # This depends heavily on the tool's inputSchema.
                    # For simplicity now, we'll assume JSON or dict is required.
                    # A more robust solution would check the inputSchema.
                    logger.warning(
                        f"Argument for tool {name} is a string but not valid JSON: {args}. Assuming dict required."
                    )
                    raise TypeError(
                        "Tool arguments must be a JSON string or a dictionary."
                    )

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
                # Check if is_error exists and log it, default to False if not present
                f"Is error: {getattr(result, 'is_error', False)}"
            )
            logger.info(log_msg)

            content_text = ""
            if result.content:
                # Simplify content handling without ContentPart type check
                if isinstance(result.content, list) and len(result.content) > 0:
                    # Attempt to extract text from the first element if it has a 'text' attribute
                    first_part = result.content[0]
                    if hasattr(first_part, "text") and isinstance(first_part.text, str):
                        content_text = first_part.text
                    # Fallback: if it's a list of strings, join them
                    elif all(isinstance(item, str) for item in result.content):
                        content_text = "\n".join(result.content)
                    else:
                        # Fallback: convert the first element to string if possible
                        try:
                            content_text = str(first_part)
                            logger.warning(
                                f"Content list item type unknown ({type(first_part)}), converted first item to string."
                            )
                        except Exception:
                            logger.error(
                                f"Could not convert content list item to string: {first_part}"
                            )
                            content_text = "[Error processing content list]"

                elif isinstance(result.content, str):
                    content_text = result.content
                else:
                    # Attempt to convert other types to string representation
                    try:
                        content_text = str(result.content)
                        log_message = (
                            f"Unexpected content format for tool {actual_tool_name} "
                            f"on {server_name}: {type(result.content)}. Converted to string."
                        )
                        logger.warning(log_message)
                    except Exception:
                        logger.error(
                            f"Could not convert content to string for tool {actual_tool_name} on {server_name}"
                        )

            # Use getattr to safely check for is_error attribute
            is_error_flag = getattr(result, "is_error", False)

            return {
                "tool_use_id": tool_call_id,
                "content": content_text,
                "is_error": is_error_flag,
            }
        except json.JSONDecodeError:
            error_content = (
                f"Error: Invalid JSON arguments received for tool {name}: {args}"
            )
            logger.error(f"Failed to decode JSON arguments for tool {name}: {args}")
            return {
                "tool_use_id": tool_call_id,
                "content": error_content,
                "is_error": True,
            }
        except TypeError as e:  # Catch specific TypeError from arg handling
            error_content = f"Error processing arguments for tool {name}: {e}"
            logger.error(error_content, exc_info=True)
            return {
                "tool_use_id": tool_call_id,
                "content": error_content,
                "is_error": True,
            }
        except Exception as e:  # Corrected indentation
            # Shorten the error message line
            error_content = (
                f"Tool execution error ({server_name}/{actual_tool_name}): {e}"
            )
            logger.error(
                f"Error executing tool {actual_tool_name} on server {server_name}: {e}",
                exc_info=True,
            )
            # Ensure the error response structure is consistent
            return {
                "tool_use_id": tool_call_id,
                "content": error_content,
                "is_error": True,
            }
