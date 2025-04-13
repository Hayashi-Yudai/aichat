import json
from pathlib import Path
from typing import Any  # Removed AsyncGenerator
from contextlib import AsyncExitStack

from loguru import logger
from mcp import ClientSession, StdioServerParameters, Tool  # Corrected Tool import
from mcp.client.stdio import stdio_client

# Removed incorrect Tool import


class McpHandler:
    """Handles interactions with an MCP server."""

    def __init__(self, server_script_path: str | Path):
        """
        Initializes the McpHandler.

        Args:
            server_script_path: Path to the MCP server script (e.g., weather.py).
        """
        self.server_script_path = Path(server_script_path)
        if not self.server_script_path.is_absolute():
            # Assuming the script is relative to this handler file's directory
            # Adjust if the assumption is different
            self.server_script_path = (
                Path(__file__).parent / self.server_script_path
            ).resolve()

    async def connect(self, exit_stack: AsyncExitStack) -> ClientSession:
        """
        Connects to the MCP server using a provided AsyncExitStack.

        Args:
            exit_stack: An AsyncExitStack to manage the connection resources.

        Returns:
            An active ClientSession.
        """
        logger.info(f"Connecting to MCP server: {self.server_script_path}...")
        command = "python"  # Assuming python execution
        server_params = StdioServerParameters(
            command=command,
            args=[str(self.server_script_path)],
            env=None,  # Pass environment variables if needed
        )
        # Ensure stdio_client and ClientSession are managed by the provided exit_stack
        stdio_transport = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        stdio, write = stdio_transport
        session = await exit_stack.enter_async_context(ClientSession(stdio, write))

        await session.initialize()
        logger.info("Successfully connected to MCP server.")
        return session

    async def list_tools(self, session: ClientSession) -> list[Tool]:
        """
        Lists available tools from the connected MCP server.

        Args:
            session: An active ClientSession.

        Returns:
            A list of available Tool objects.
        """
        logger.info("Listing tools from MCP server...")
        response = await session.list_tools()
        tools = response.tools
        logger.info(f"Found tools: {[tool.name for tool in tools]}")
        return tools

    def format_tools_for_openai(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """
        Formats the MCP tools list into the format expected by OpenAI API.

        Args:
            tools: A list of Tool objects from the MCP server.

        Returns:
            A list of tool definitions in OpenAI format.
        """
        logger.info("Formatting tools for OpenAI...")
        formatted_tools = [
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
        formatted_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,  # Claude uses 'input_schema'
            }
            for tool in tools
        ]
        return formatted_tools

    async def call_tool(
        self,
        session: ClientSession,
        name: str,
        args: dict | str,
        tool_call_id: str | None = None,  # Allow dict args, optional tool_call_id
    ) -> dict[str, Any]:
        """
        Calls a specific tool on the MCP server.

        Args:
            session: An active ClientSession.
            name: The name of the tool to call.
            args_str: The JSON string arguments for the tool.
            tool_call_id: The unique ID for this tool call instance.

        Returns:
            A dictionary representing the tool result message (generic format).
            For Claude, the caller needs to format this into a 'tool_result' content block.
            For OpenAI, the caller uses this directly.
        """
        log_id_part = f" (ID: {tool_call_id})" if tool_call_id else ""
        logger.info(f"Attempting to call MCP tool: {name}{log_id_part}")
        tool_args_dict = {}
        try:
            # Handle both string and dict arguments
            if isinstance(args, str):
                tool_args_dict = json.loads(args)
            elif isinstance(args, dict):
                tool_args_dict = args
            else:
                raise TypeError("Tool arguments must be a JSON string or a dictionary.")

            logger.info(f"Calling MCP tool: {name} with args: {tool_args_dict}")
            result = await session.call_tool(name, tool_args_dict)
            # Remove access to result.is_error as it doesn't exist
            log_msg = (
                f"Tool {name} executed. "
                f"Content available: {bool(result.content)}. "
                # Removed is_error check here
            )
            logger.info(log_msg)
            # Ensure content is always a string, even if empty or None
            content_text = ""
            if result.content:
                # Assuming result.content is a list of ContentPart, take the first text part
                # Adjust this logic if the structure of result.content can vary
                if isinstance(result.content, list) and len(result.content) > 0:
                    # Find the first text part, or default to empty string
                    text_part = next(
                        (part.text for part in result.content if hasattr(part, "text")),
                        "",
                    )
                    content_text = text_part
                elif isinstance(
                    result.content, str
                ):  # Handle if content is already a string
                    content_text = result.content
                else:
                    logger.warning(
                        f"Unexpected content format for tool {name}: {type(result.content)}"
                    )

            # Return a more generic result structure, assume no error on success
            return {
                "tool_use_id": tool_call_id,
                "content": content_text,
                "is_error": False,  # Assume False on successful execution
            }
        except json.JSONDecodeError:
            error_content = f"Error: Invalid JSON arguments received: {args}"
            logger.error(f"Failed to decode JSON arguments for tool {name}: {args}")
            return {
                "tool_use_id": tool_call_id,
                "content": error_content,
                "is_error": True,
            }
        except Exception as e:
            error_content = f"Error executing tool {name}: {e}"
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return {
                "tool_use_id": tool_call_id,
                "content": error_content,
                "is_error": True,
            }
